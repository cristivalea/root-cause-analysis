#!/usr/bin/env python3
"""Query the project ChromaDB collections using Ollama embeddings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import chromadb
import requests

ROOT = Path(__file__).resolve().parents[1]
OLLAMA_BASE = "http://localhost:11434"
DEFAULT_MODEL = "nomic-embed-text"


def embed_query(text: str, model: str = DEFAULT_MODEL) -> list[float]:
    for url in [f"{OLLAMA_BASE}/api/embed", f"{OLLAMA_BASE}/api/embeddings"]:
        try:
            resp = requests.post(url, json={"model": model, "input": text}, timeout=120)
            resp.raise_for_status()
            data = resp.json()

            if "embedding" in data:
                return data["embedding"]
            if "embeddings" in data:
                emb = data["embeddings"]
                if isinstance(emb, list) and emb and isinstance(emb[0], list):
                    return emb[0]
            if "data" in data and isinstance(data["data"], list):
                for item in data["data"]:
                    if isinstance(item, dict) and "embedding" in item:
                        return item["embedding"]
        except Exception:
            continue

    raise RuntimeError("Unable to embed query text with Ollama.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query the ChromaDB collections used by this project.")
    parser.add_argument("--collection", choices=["historical_incidents", "historical_rcas"], required=True)
    parser.add_argument("--query", required=True, help="Natural-language query to search for")
    parser.add_argument("--limit", type=int, default=5, help="Maximum number of results to return")
    parser.add_argument("--where", default=None, help="Optional metadata filter in JSON format, e.g. '{\"service\": \"Payroll Service\"}'")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Embedding model used by Ollama")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    client = chromadb.PersistentClient(path=str(ROOT / "chroma_db"))
    collection = client.get_collection(name=args.collection)

    where_filter = None
    if args.where:
        where_filter = json.loads(args.where)

    query_embedding = embed_query(args.query, model=args.model)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=args.limit,
        where=where_filter,
    )

    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"Error: {exc}")
