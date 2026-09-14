#!/usr/bin/env python3
"""Load project data into ChromaDB using Ollama embeddings.

This script matches the structure documented in the project:
- historical_incidents: one record per story/incident
- historical_rcas: one record per RCA section
- embedding model: nomic-embed-text through local Ollama
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable

import chromadb
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OLLAMA_BASE = "http://localhost:11434"
DEFAULT_MODEL = "nomic-embed-text"
BATCH_SIZE = 32


def log(msg: str) -> None:
    print(f"[ingest] {msg}")


def get_ollama_endpoints() -> list[str]:
    return [
        f"{OLLAMA_BASE}/api/embed",
        f"{OLLAMA_BASE}/api/embeddings",
    ]


def ensure_ollama_model(model: str) -> None:
    resp = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=20)
    resp.raise_for_status()
    tags = resp.json().get("models", [])
    available = {item.get("name", "").split(":")[0] for item in tags}
    if model not in available:
        log(f"Model '{model}' is not available in Ollama. Pulling it...")
        pull = requests.post(f"{OLLAMA_BASE}/api/pull", json={"name": model}, timeout=600)
        pull.raise_for_status()
        log(f"Model '{model}' pulled successfully.")


def embed_texts(texts: list[str], model: str = DEFAULT_MODEL) -> list[list[float]]:
    if not texts:
        return []

    errors: list[str] = []
    for url in get_ollama_endpoints():
        try:
            payload = {"model": model, "input": texts}
            resp = requests.post(url, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()

            if "embedding" in data:
                return [data["embedding"]]
            if "embeddings" in data:
                embeddings = data["embeddings"]
                if isinstance(embeddings, list) and embeddings and isinstance(embeddings[0], list):
                    return embeddings
            if "data" in data and isinstance(data["data"], list):
                embedded = []
                for item in data["data"]:
                    if isinstance(item, dict) and "embedding" in item:
                        embedded.append(item["embedding"])
                if len(embedded) == len(texts):
                    return embedded

            errors.append(f"Unexpected response from {url}: {data}")
        except Exception as exc:  # pragma: no cover - fallback loop
            errors.append(f"{url}: {exc}")

    raise RuntimeError("Unable to generate embeddings via Ollama. Tried endpoints: " + "; ".join(errors))


def chunked(items: list[Any], size: int = BATCH_SIZE) -> Iterable[list[Any]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def load_incident_records(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        records = json.load(fh)

    out: list[dict[str, Any]] = []
    for item in records:
        text_parts = [
            item.get("title", ""),
            item.get("service", ""),
            item.get("business_service", ""),
            item.get("true_root_cause", ""),
            item.get("time_pattern") or "",
        ]
        text = " | ".join(part for part in text_parts if part).strip()
        if not text:
            continue

        out.append(
            {
                "id": item.get("story_id", ""),
                "text": text,
                "metadata": {
                    "story_id": item.get("story_id", ""),
                    "service": item.get("service", ""),
                    "business_service": item.get("business_service", ""),
                    "environment": item.get("environment", "unknown"),
                    "severity": item.get("severity", "unknown"),
                    "time_pattern": item.get("time_pattern") or "",
                    "source_type": "incident",
                },
            }
        )
    return out


def split_markdown_sections(markdown_text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current_name = "content"
    current_lines: list[str] = []

    for raw_line in markdown_text.splitlines():
        match = re.match(r"^(#+)\s+(.*)$", raw_line)
        if match:
            if current_lines:
                sections[current_name] = "\n".join(current_lines).strip()
            current_name = match.group(2).strip() or "content"
            current_lines = []
        else:
            current_lines.append(raw_line)

    if current_lines:
        sections[current_name] = "\n".join(current_lines).strip()

    return {k: v for k, v in sections.items() if v}


def load_rca_records(folder: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for md_file in sorted(folder.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        sections = split_markdown_sections(text)
        if not sections:
            sections = {"content": text.strip()}

        for section_name, section_text in sections.items():
            out.append(
                {
                    "id": f"{md_file.stem}::{section_name}",
                    "text": section_text,
                    "metadata": {
                        "document_id": md_file.stem,
                        "section_name": section_name,
                        "source_type": "rca",
                    },
                }
            )
    return out


def get_collection(client: chromadb.PersistentClient, name: str) -> Any:
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


def ingest_records(records: list[dict[str, Any]], collection_name: str, model: str = DEFAULT_MODEL) -> None:
    if not records:
        log(f"No records found for {collection_name}; skipping.")
        return

    client = chromadb.PersistentClient(path=str(ROOT / "chroma_db"))
    collection = get_collection(client, collection_name)

    ids = [record["id"] for record in records]
    texts = [record["text"] for record in records]
    metadatas = [record["metadata"] for record in records]

    embeddings: list[list[float]] = []
    for batch in chunked(texts):
        batch_embeddings = embed_texts(batch, model=model)
        embeddings.extend(batch_embeddings)

    collection.add(
        ids=ids,
        documents=texts,
        metadatas=metadatas,
        embeddings=embeddings,
    )

    log(f"Inserted {len(records)} items into collection '{collection_name}'.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest project mock data into ChromaDB via Ollama embeddings.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Ollama embedding model name")
    parser.add_argument("--stories", type=Path, default=DATA_DIR / "story_definitions.json", help="Path to story definitions JSON")
    parser.add_argument("--rca-folder", type=Path, default=DATA_DIR / "knowledge_base" / "rcas", help="Folder containing RCA markdown files")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_ollama_model(args.model)

    incidents = load_incident_records(args.stories)
    rca_docs = load_rca_records(args.rca_folder)

    ingest_records(incidents, "historical_incidents", model=args.model)
    ingest_records(rca_docs, "historical_rcas", model=args.model)

    log("Ingestion complete.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"Error: {exc}")
