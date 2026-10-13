# Comparison of variants (2026-10-13 21:02)

Each story ran with every variant on the same model; a story without every variant measured is left out.

| Measure | control | v3 | v4 | v5 |
|---|---|---|---|---|
| Investigations (DRAFT / all) | 2/2 | 2/2 | 2/2 | 2/2 |
| LLM requests per investigation | 3.0 | 3.0 | 3.0 | 3.5 |
| Input tokens per investigation | 10420 | 9352 | 10252 | 11432 |
| Output tokens per investigation | 10715 | 10056 | 8662 | 10373 |
| of which the model's own reasoning | 7987 | 7175 | 5815 | 7440 |
| Answers cut by the output limit | 0/6 | 0/6 | 0/6 | 0/7 |
| Invalid answers | 0/6 | 0/6 | 0/6 | 1/7 |
| Investigations with more than one reasoning attempt | 0/2 | 0/2 | 0/2 | 0/2 |
| Escalated or failed | 0/2 | 0/2 | 0/2 | 0/2 |
| LLM time per investigation (s) | 161.9 | 121.2 | 169.6 | 115.7 |
| Expected citations cited by the main hypothesis (revision 1) | 9/11 | 9/11 | 9/11 | 8/11 |
| Main hypothesis cites a red herring (revision 1) | 1/2 | 1/2 | 1/2 | 1/2 |
| Expert follow-ups: new citations cited by a hypothesis | 0/0 | 0/0 | 0/0 | 0/0 |

| Story | Rev. | Model | Variant | Status | Tokens in/out | Attempts | Cited by main | Main hypothesis |
|---|---|---|---|---|---|---|---|---|
| STORY-001 | 1 | openrouter:nvidia/nemotron-3-super-120b-a12b:free | control | DRAFT | 11958/11147 | 1 | 5/6 | Autoscaling configuration allows worker threads to exceed the PostgreSQL connection limit, causing connection exhaustion and timeouts. |
| STORY-001 | 1 | openrouter:nvidia/nemotron-3-super-120b-a12b:free | v3 | DRAFT | 11123/9579 | 1 | 4/6 | The autoscaling policy for payroll batch workers (enabled 2026-03-11) allows the worker pool to scale up to 96 threads, each consuming a Pos |
| STORY-001 | 1 | openrouter:nvidia/nemotron-3-super-120b-a12b:free | v4 | DRAFT | 11893/8883 | 1 | 4/6 | Autoscaling allows the payroll batch worker pool to exceed a safe number of concurrent threads, exhausting the shared PostgreSQL connection  |
| STORY-001 | 1 | openrouter:nvidia/nemotron-3-super-120b-a12b:free | v5 | DRAFT | 14149/11730 | 1 | 4/6 | Autoscaling configuration allows the payroll worker pool to scale up to 96 threads, exceeding the PostgreSQL connection limit shared with th |
| STORY-002 | 1 | openrouter:nvidia/nemotron-3-super-120b-a12b:free | control | DRAFT | 8881/10283 | 1 | 4/5 | The payment retry‑handler changes deployed in Payment API v4.18.2 introduced a regression that leaves SQL sessions unclosed, exhausting the  |
| STORY-002 | 1 | openrouter:nvidia/nemotron-3-super-120b-a12b:free | v3 | DRAFT | 7581/10534 | 1 | 5/5 | Deployment of Payment API v4.18.2 introduced a code defect (e.g., unclosed SQL sessions in the retry handler) that causes connection leaks,  |
| STORY-002 | 1 | openrouter:nvidia/nemotron-3-super-120b-a12b:free | v4 | DRAFT | 8610/8440 | 1 | 5/5 | A regression in the payment retry handler introduced with Payment API v4.18.2 left SQL sessions unclosed, causing connection pool exhaustion |
| STORY-002 | 1 | openrouter:nvidia/nemotron-3-super-120b-a12b:free | v5 | DRAFT | 8716/9016 | 1 | 4/5 | The deployment of Payment API v4.18.2 introduced a defect in the payment retry handler that leaves SQL sessions unclosed during error flows, |

True root causes:
- STORY-001: Worker autoscaling, enabled by CHG-2026-00262 in March 2026, lets the Monday payroll batch grow to 96 threads with no limit per connection pool. The threads use all PostgreSQL connections shared with the employee portal, so portal requests time out. The change replaced the 32-thread cap that was the corrective action of RCA-2025-00042.
- STORY-002: HikariCP database connection leak introduced in Payment API v4.18.2 due to unclosed sessions in the transaction retry block.
