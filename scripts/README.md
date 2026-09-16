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
python scripts/query_chroma.py --collection historical_incidents --query "database connection pool issue" --before "2026-07-14T14:32:00Z" --max-distance 0.45 --limit 5
python scripts/query_chroma.py --collection historical_rcas --query "Payment API database connection timeout after deployment" --before "2026-07-14T14:32:00Z" --max-distance 0.45 --limit 5
```

## Notes

- ChromaDB is stored locally in the `chroma_db/` folder.
- The script follows the project design described in the docs: one collection for incidents and one for RCA sections.
- Metadata is preserved for filtering before similarity search.
- `--before` applies the mandatory historical filter: `completion_date` for RCA sections and `detected_at` for incidents.
- `--limit` returns at most 5 results by default.
- `--max-distance 0.45` is the initial cosine-distance threshold. ChromaDB uses lower distance for more similar text; the value keeps the observed relevant Payment API matches (roughly 0.26-0.42) and drops weaker matches. It should be recalibrated later with the evaluation set.
- Use `--service "Payment API"` when the service is known. Omit it for the MVP acceptance query so the Payment RCA can be compared with the Payroll distractor.
