# Baseline of the agents (2026-10-13 19:13)

Model: openai/gpt-oss-120b. Investigations: 5 (4 first revisions, 1 expert follow-ups), 0 failed with an error.

| Measure | Value |
|---|---|
| LLM requests per investigation | 3.4 |
| Input tokens per investigation | 9261 |
| Output tokens per investigation | 5352 |
| of which the model's own reasoning (gpt-oss) | 3264 |
| Answers cut by the output limit (finish_reason length; measured from E10) | 1/17 |
| Input tokens per agent per investigation | investigation_planner 1257, historical_review 1898, rca_reasoning_agent 6107 |
| LLM time per investigation (s, without rate limit waits) | 82.5 |
| Rate limit waits per investigation (s) | 1.0 |
| Total time per investigation (s) | 96.5 |
| Invalid answers (all requests) | 0/17 |
| Failed requests (all requests) | 0/17 |
| Investigations with more than one reasoning attempt | 2/5 |
| Investigations escalated by the guardrail | 0/5 |
| Expected citations in the ledger (first revisions) | 17/18 |
| Expected citations cited by the main hypothesis (first revisions) | 10/18 |
| First revisions where the main hypothesis cites a red herring | 1/4 |
| Expert follow-ups: new citations in the ledger | 1/1 |
| Expert follow-ups: new citations cited by a hypothesis | 1/1 |

| Story | Rev. | Status | Requests | Input tokens | Output tokens | Time (s) | Reasoning attempts | In ledger | Cited by main | Expert citations | Error |
|---|---|---|---|---|---|---|---|---|---|---|---|
| STORY-001 | 1 | DRAFT | 3 | 8316 | 4552 | 30.8 | 1 | 6/6 | 1/6 | - | - |
| STORY-002 | 1 | DRAFT | 4 | 12608 | 7294 | 141.0 | 2 | 5/5 | 5/5 | - | - |
| STORY-004 | 1 | DRAFT | 4 | 10559 | 6615 | 140.2 | 2 | 3/4 | 1/4 | - | - |
| STORY-004 | 2 | DRAFT | 3 | 7863 | 4690 | 84.1 | 1 | 3/4 | 2/4 | 1/1 | - |
| STORY-008 | 1 | DRAFT | 3 | 6961 | 3611 | 86.2 | 1 | 3/3 | 3/3 | - | - |

Tokens are those the provider reports. A request it refused (an answer that is not valid JSON, a request too large) reports none, though it used tokens: the totals are lower bounds. The judge requests are not counted in the measures of the investigations.
