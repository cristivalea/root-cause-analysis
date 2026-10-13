# Baseline of the agents (2026-10-13 19:21)

Model: openai/gpt-oss-120b. Investigations: 5 (4 first revisions, 1 expert follow-ups), 0 failed with an error.

| Measure | Value |
|---|---|
| LLM requests per investigation | 3.6 |
| Input tokens per investigation | 10078 |
| Output tokens per investigation | 3247 |
| of which the model's own reasoning (gpt-oss) | 656 |
| Answers cut by the output limit (finish_reason length; measured from E10) | 0/18 |
| Input tokens per agent per investigation | investigation_planner 1257, historical_review 1844, rca_reasoning_agent 6977 |
| LLM time per investigation (s, without rate limit waits) | 82.7 |
| Rate limit waits per investigation (s) | 0.0 |
| Total time per investigation (s) | 95.2 |
| Invalid answers (all requests) | 0/18 |
| Failed requests (all requests) | 0/18 |
| Investigations with more than one reasoning attempt | 2/5 |
| Investigations escalated by the guardrail | 0/5 |
| Expected citations in the ledger (first revisions) | 17/18 |
| Expected citations cited by the main hypothesis (first revisions) | 10/18 |
| First revisions where the main hypothesis cites a red herring | 1/4 |
| Expert follow-ups: new citations in the ledger | 1/1 |
| Expert follow-ups: new citations cited by a hypothesis | 0/1 |

| Story | Rev. | Status | Requests | Input tokens | Output tokens | Time (s) | Reasoning attempts | In ledger | Cited by main | Expert citations | Error |
|---|---|---|---|---|---|---|---|---|---|---|---|
| STORY-001 | 1 | DRAFT | 3 | 8312 | 2516 | 55.5 | 1 | 6/6 | 2/6 | - | - |
| STORY-002 | 1 | DRAFT | 3 | 8074 | 2939 | 83.9 | 1 | 5/5 | 4/5 | - | - |
| STORY-004 | 1 | DRAFT | 3 | 6663 | 2145 | 66.6 | 1 | 3/4 | 2/4 | - | - |
| STORY-004 | 2 | DRAFT | 4 | 12444 | 3613 | 120.1 | 2 | 3/4 | 1/4 | 0/1 | - |
| STORY-008 | 1 | DRAFT | 5 | 14897 | 5020 | 149.8 | 3 | 3/3 | 2/3 | - | - |

Tokens are those the provider reports. A request it refused (an answer that is not valid JSON, a request too large) reports none, though it used tokens: the totals are lower bounds. The judge requests are not counted in the measures of the investigations.
