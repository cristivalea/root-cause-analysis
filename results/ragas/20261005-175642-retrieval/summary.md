# RAGAS: search quality

Run: 2026-10-05 17:56

| Method | Collection | Threshold | Recall | Precision | Nothing to find: returned nothing | Misleading record returned |
|---|---|---|---|---|---|---|
| semantic | historical_incidents | 0.45 | 0.99 | 0.43 | 0 of 4 | 0 of 26 |
| semantic | historical_rcas | 0.45 | 1.00 | 0.16 | 0 of 6 | 1 of 26 |
| keyword | historical_incidents | - | 0.69 | 0.29 | 0 of 4 | 0 of 26 |
| keyword | historical_rcas | - | 1.00 | 0.26 | 0 of 6 | 1 of 26 |

Recall: of the records that should be found, the share found. Precision: of the records returned, the share that is right. Both are averages over the questions; a question with nothing to find has no recall, a search that returned nothing has no precision. Details per question in rows.csv.
