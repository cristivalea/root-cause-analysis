#!/usr/bin/env python3
"""RAG utilities for the RCA application."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import chromadb
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OLLAMA_BASE = "http://localhost:11434"
DEFAULT_MODEL = "nomic-embed-text"
BATCH_SIZE = 32
DEFAULT_MAX_DISTANCE = 0.45


def log(msg: str) -> None:
    print(f"[rag] {msg}")


def get_ollama_endpoints() -> list[str]:
    return [f"{OLLAMA_BASE}/api/embed", f"{OLLAMA_BASE}/api/embeddings"]


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
        except Exception:
            continue

    raise RuntimeError("Unable to generate embeddings via Ollama.")


def chunked(items: list[Any], size: int = BATCH_SIZE) -> Iterable[list[Any]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _parse_iso_timestamp(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def build_incident_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as fh:
        records = json.load(fh)

    out: list[dict[str, Any]] = []
    for item in records:
        text_parts = [
            item.get("title", ""),
            item.get("description", ""),
            item.get("service", ""),
            item.get("business_service", ""),
            " | ".join(item.get("symptoms", []) or []),
        ]
        text = " | ".join(part for part in text_parts if part).strip()
        if not text:
            continue

        metadata = {
            "incident_id": item.get("incident_id", ""),
            "service": item.get("service", ""),
            "business_service": item.get("business_service", ""),
            "environment": item.get("environment", "unknown"),
            "severity": item.get("severity", "unknown"),
            "detected_at": _parse_iso_timestamp(item.get("detected_at")),
            "source_type": "incident",
        }

        out.append({
            "id": item.get("incident_id", ""),
            "text": text,
            "metadata": metadata,
        })

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

        service = ""
        completion_date = None
        linked_incidents: list[str] = []
        for line in text.splitlines():
            if line.startswith("**Service:**"):
                service = line.split(":", 1)[1].strip().strip("*").strip()
            elif line.startswith("**Completion Date:**"):
                value = line.split(":", 1)[1].strip().strip("*").strip()
                completion_date = _parse_iso_timestamp(value)
            elif line.startswith("**Linked Incidents:**"):
                value = line.split(":", 1)[1].strip().strip("*").strip()
                linked_incidents = [part.strip() for part in value.split(",") if part.strip()]

        for section_name, section_text in sections.items():
            out.append({
                "id": f"{md_file.stem}::{section_name}",
                "text": section_text,
                "metadata": {
                    "document_id": md_file.stem,
                    "section_name": section_name,
                    "service": service,
                    "completion_date": completion_date,
                    "linked_incidents": ",".join(linked_incidents),
                    "source_type": "rca",
                },
            })

    return out


def get_collection(client: chromadb.PersistentClient, name: str) -> Any:
    return client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})


def _combine_filters(*filters: dict[str, Any] | None) -> dict[str, Any] | None:
    present = [item for item in filters if item]
    if not present:
        return None
    if len(present) == 1:
        return present[0]
    return {"$and": present}


def _historical_date_filter(collection_name: str, before_timestamp: int | None) -> dict[str, Any] | None:
    if before_timestamp is None:
        return None
    date_field = "completion_date" if collection_name == "historical_rcas" else "detected_at"
    return {date_field: {"$lt": before_timestamp}}


def _filter_by_distance(results: dict[str, Any], max_distance: float | None, limit: int) -> dict[str, Any]:
    if max_distance is None:
        return results

    distances = results.get("distances", [[]])[0]
    keep_indexes = [index for index, distance in enumerate(distances) if distance <= max_distance][:limit]
    filtered: dict[str, Any] = {}
    for key, value in results.items():
        if isinstance(value, list) and value and isinstance(value[0], list):
            filtered[key] = [[value[0][index] for index in keep_indexes]]
        else:
            filtered[key] = value
    return filtered


def upsert_records(records: list[dict[str, Any]], collection_name: str, model: str = DEFAULT_MODEL) -> None:
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
        embeddings.extend(embed_texts(batch, model=model))

    collection.upsert(
        ids=ids,
        documents=texts,
        metadatas=metadatas,
        embeddings=embeddings,
    )

    log(f"Upserted {len(records)} items into collection '{collection_name}'.")


def query_collection(
    collection_name: str,
    query_text: str,
    limit: int = 5,
    where: dict[str, Any] | None = None,
    before_timestamp: int | None = None,
    max_distance: float | None = DEFAULT_MAX_DISTANCE,
    model: str = DEFAULT_MODEL,
) -> list[dict[str, Any]]:
    client = chromadb.PersistentClient(path=str(ROOT / "chroma_db"))
    collection = client.get_collection(name=collection_name)

    if collection.count() == 0:
        return []

    query_embedding = embed_texts([query_text], model=model)[0]
    where_filter = _combine_filters(where, _historical_date_filter(collection_name, before_timestamp))
    
    n_results = min(max(limit * 3, limit), collection.count())
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        where=where_filter,
    )

    filtered = _filter_by_distance(results, max_distance, limit)

    ids = (filtered.get("ids") or [[]])[0]
    documents = (filtered.get("documents") or [[]])[0]
    metadatas = (filtered.get("metadatas") or [[]])[0]
    distances = (filtered.get("distances") or [[]])[0]

    if not ids:
        return []

    # Keep only the best section per document (sau incident)
    best_results: dict[str, dict[str, Any]] = {}
    for i in range(len(ids)):
        meta = metadatas[i] if i < len(metadatas) and isinstance(metadatas[i], dict) else {}
        dist = distances[i] if i < len(distances) else 0.0
        doc_text = documents[i] if i < len(documents) else ""
        item_id = ids[i]

        # Pentru RCA-uri avem document_id, pentru Incidente avem incident_id
        doc_key = meta.get("document_id") or meta.get("incident_id") or item_id

        if doc_key not in best_results or dist < best_results[doc_key]["score"]:
            best_results[doc_key] = {
                "id": item_id,
                "document": doc_text,
                "metadata": meta,
                "score": dist,
            }

    return list(best_results.values())[:limit]