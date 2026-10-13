# RAGAS: similarity threshold calibration

Run: 2026-10-08 14:19

| Method | Collection | Threshold | Recall | Precision | Nothing to find: returned nothing | Misleading record returned |
|---|---|---|---|---|---|---|
| semantic | historical_incidents | 0.25 | 0.99 | 0.51 | 0 of 4 | 0 of 26 |
| semantic | historical_rcas | 0.25 | 0.60 | 0.85 | 5 of 6 | 1 of 26 |
| semantic | historical_incidents | 0.3 | 0.99 | 0.46 | 0 of 4 | 0 of 26 |
| semantic | historical_rcas | 0.3 | 0.85 | 0.56 | 1 of 6 | 1 of 26 |
| semantic | historical_incidents | 0.35 | 0.99 | 0.43 | 0 of 4 | 0 of 26 |
| semantic | historical_rcas | 0.35 | 1.00 | 0.30 | 0 of 6 | 1 of 26 |
| semantic | historical_incidents | 0.4 | 0.99 | 0.43 | 0 of 4 | 0 of 26 |
| semantic | historical_rcas | 0.4 | 1.00 | 0.20 | 0 of 6 | 1 of 26 |
| semantic | historical_incidents | 0.45 | 0.99 | 0.43 | 0 of 4 | 0 of 26 |
| semantic | historical_rcas | 0.45 | 1.00 | 0.16 | 0 of 6 | 1 of 26 |

The application uses the threshold 0.45 (DEFAULT_MAX_DISTANCE in rca/rag.py). A lower threshold returns fewer records: precision goes up, recall goes down. Recall: of the records that should be found, the share found. Precision: of the records returned, the share that is right. Both are averages over the questions; a question with nothing to find has no recall, a search that returned nothing has no precision. Details per question in rows.csv.
