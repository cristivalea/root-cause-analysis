# Scripts for ChromaDB + Ollama

## Install dependencies

```bash
python -m pip install -r requirements.txt
```

## Pull the embedding model

```bash
ollama pull nomic-embed-text
```

## Ingest the project data

```bash
python scripts/ingest_chroma.py
```

## Query the collections

```bash
python scripts/query_chroma.py --collection historical_incidents --query "database connection pool issue" --limit 5
python scripts/query_chroma.py --collection historical_rcas --query "root cause database timeout" --limit 5
```

## Notes

- ChromaDB is stored locally in the `chroma_db/` folder.
- The script follows the project design described in the docs: one collection for incidents and one for RCA sections.
- Metadata is preserved for filtering before similarity search.
