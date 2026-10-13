# Baseline of the agents (2026-10-13 16:38)

Model: openai/gpt-oss-120b. Investigations: 2 (1 first revisions, 1 expert follow-ups), 0 failed with an error.

| Measure | Value |
|---|---|
| LLM requests per investigation | 3.5 |
| Input tokens per investigation | 9492 |
| Output tokens per investigation | 5773 |
| Input tokens per agent per investigation | investigation_planner 1184, historical_review 1651, rca_reasoning_agent 6658 |
| LLM time per investigation (s, without rate limit waits) | 70.3 |
| Rate limit waits per investigation (s) | 0.0 |
| Total time per investigation (s) | 84.0 |
| Invalid answers (all requests) | 0/7 |
| Failed requests (all requests) | 0/7 |
| Investigations with more than one reasoning attempt | 1/2 |
| Investigations escalated by the guardrail | 0/2 |
| Expected citations in the ledger (first revisions) | 3/4 |
| Expected citations cited by the main hypothesis (first revisions) | 2/4 |
| First revisions where the main hypothesis cites a red herring | 0/1 |
| Expert follow-ups: new citations in the ledger | 1/1 |
| Expert follow-ups: new citations cited by a hypothesis | 0/1 |

| Story | Rev. | Status | Requests | Input tokens | Output tokens | Time (s) | Reasoning attempts | In ledger | Cited by main | Expert citations | Error |
|---|---|---|---|---|---|---|---|---|---|---|---|
| STORY-004 | 1 | DRAFT | 3 | 6512 | 4633 | 36.1 | 1 | 3/4 | 2/4 | - | - |
| STORY-004 | 2 | DRAFT | 4 | 12473 | 6913 | 131.9 | 2 | 3/4 | 0/4 | 0/1 | - |

Tokens are those the provider reports. A request it refused (an answer that is not valid JSON, a request too large) reports none, though it used tokens: the totals are lower bounds. The judge requests are not counted in the measures of the investigations.
