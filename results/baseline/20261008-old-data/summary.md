# Baseline: codul de acum, înainte de redesign

Povești: 13. Investigații reușite: 13. Model: vezi config GROQ_MODEL.

| Măsură | Rezultat |
|---|---|
| Top-1 accuracy (ipoteza #1 = cauza reală, judecător LLM) | 8/13 |
| Top-K accuracy (cauza reală e în listă) | 12/13 |
| Confidence calibrat (toate) | 9/13 |
| Confidence calibrat (success) | 4/7 |
| Confidence calibrat (edge) | 5/6 |
| Citări așteptate găsite în ledger | 41/48 |
| Citări așteptate citate de ipoteza #1 | 31/48 |
| Citări așteptate citate de orice ipoteză | 38/48 |
| Povești în care ipoteza #1 citează o capcană | 3/13 |
| Durată medie investigație (s) | 65.1 |

| Poveste | Tip | Status | Top-1 | Top-K | Confidence (acceptat) | Ledger | Citat #1 | Capcane citate #1 |
|---|---|---|---|---|---|---|---|---|
| STORY-001 | success | DRAFT | nu | da | MEDIUM (HIGH) | 5/5 | 3/5 | RCA-2025-00042 |
| STORY-002 | success | DRAFT | da | da | MEDIUM (HIGH) | 5/5 | 5/5 | - |
| STORY-003 | edge | DRAFT | da | da | MEDIUM (LOW/MEDIUM) | 4/4 | 4/4 | - |
| STORY-004 | success | DRAFT | nu | da | HIGH (HIGH) | 3/4 | 2/4 | - |
| STORY-005 | edge | DRAFT | nu | da | MEDIUM (HIGH/MEDIUM) | 3/3 | 0/3 | RCA-2025-00192 |
| STORY-006 | success | DRAFT | da | da | HIGH (HIGH) | 4/5 | 4/5 | - |
| STORY-007 | edge | DRAFT | da | da | MEDIUM (HIGH) | 3/5 | 2/5 | - |
| STORY-008 | success | DRAFT | nu | da | MEDIUM (HIGH) | 3/3 | 2/3 | RCA-2025-00305, LOG-AUTH-20260404-02 |
| STORY-009 | success | DRAFT | da | da | MEDIUM (HIGH/MEDIUM) | 3/4 | 2/4 | - |
| STORY-010 | success | DRAFT | da | da | HIGH (HIGH) | 3/3 | 3/3 | - |
| STORY-011 | edge | DRAFT | nu | nu | LOW (LOW/MEDIUM) | 1/1 | 0/1 | - |
| STORY-012 | edge | DRAFT | da | da | HIGH (HIGH/MEDIUM) | 2/2 | 2/2 | - |
| STORY-013 | edge | DRAFT | da | da | MEDIUM (LOW/MEDIUM) | 2/4 | 2/4 | - |
