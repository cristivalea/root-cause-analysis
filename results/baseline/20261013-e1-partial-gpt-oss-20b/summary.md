# Baseline of the agents (2026-10-13 14:29)

Model: openai/gpt-oss-20b. Investigations: 14 (10 first revisions, 0 expert follow-ups), 4 failed with an error.

| Measure | Value |
|---|---|
| LLM requests per investigation | 4.2 |
| Input tokens per investigation | 8043 |
| Output tokens per investigation | 3353 |
| Input tokens per agent per investigation | investigation_planner 1597, historical_rca_agent 1426, rca_reasoning_agent 5020 |
| LLM time per investigation (s, without rate limit waits) | 113.3 |
| Rate limit waits per investigation (s) | 0.0 |
| Total time per investigation (s) | 125.2 |
| Invalid answers (all requests) | 11/42 |
| Failed requests (all requests) | 0/42 |
| Investigations with more than one reasoning attempt | 7/10 |
| Investigations escalated by the guardrail | 5/10 |
| Expected citations in the ledger (first revisions) | 35/37 |
| Expected citations cited by the main hypothesis (first revisions) | 17/37 |
| First revisions where the main hypothesis cites a red herring | 0/10 |
| Expert follow-ups: new citations in the ledger | 0/0 |
| Expert follow-ups: new citations cited by a hypothesis | 0/0 |

| Story | Rev. | Status | Requests | Input tokens | Output tokens | Time (s) | Reasoning attempts | In ledger | Cited by main | Expert citations | Error |
|---|---|---|---|---|---|---|---|---|---|---|---|
| STORY-001 | 1 | - | - | - | - | 23.9 | - | -/- | -/- | - | APIStatusError: Error code: 413 - {'error': {'message': 'Request too large for model `openai/gpt-oss-20b` in organization `org_<redacted>` service tier `on_demand` on tokens per minute (TPM): Limit 8000, Requested 8919, please reduce your message size and try again. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}} |
| STORY-002 | 1 | ESCALATED | 5 | 8456 | 3382 | 177.2 | 3 | 5/5 | 0/5 | - | - |
| STORY-003 | 1 | DRAFT | 3 | 6384 | 2968 | 61.4 | 1 | 4/4 | 4/4 | - | - |
| STORY-004 | 1 | ESCALATED | 5 | 11072 | 5330 | 150.3 | 3 | 3/4 | 0/4 | - | - |
| STORY-005 | 1 | ESCALATED | 5 | 11127 | 4724 | 167.1 | 3 | 3/3 | 0/3 | - | - |
| STORY-006 | 1 | DRAFT | 4 | 7953 | 2940 | 130.9 | 2 | 5/5 | 5/5 | - | - |
| STORY-007 | 1 | ESCALATED | 5 | 7747 | 2960 | 159.9 | 3 | 4/5 | 0/5 | - | - |
| STORY-008 | 1 | ESCALATED | 5 | 7051 | 3084 | 173.6 | 3 | 3/3 | 0/3 | - | - |
| STORY-009 | 1 | DRAFT | 3 | 6897 | 2629 | 56.5 | 1 | 4/4 | 4/4 | - | - |
| STORY-010 | 1 | DRAFT | 4 | 6818 | 2735 | 118.9 | 2 | 3/3 | 3/3 | - | - |
| STORY-011 | 1 | DRAFT | 3 | 6923 | 2782 | 55.7 | 1 | 1/1 | 1/1 | - | - |
| STORY-011 | 2 | - | - | - | - | 78.0 | - | -/- | -/- | - | RateLimitError: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-20b` in organization `org_<redacted>` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198106, Requested 4681. Please try again in 20m3.984s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}} |
| STORY-012 | 1 | - | - | - | - | 2.2 | - | -/- | -/- | - | RateLimitError: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-20b` in organization `org_<redacted>` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198101, Requested 2245. Please try again in 2m29.472s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}} |
| STORY-013 | 1 | - | - | - | - | 2.4 | - | -/- | -/- | - | RateLimitError: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-20b` in organization `org_<redacted>` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198096, Requested 3329. Please try again in 10m15.6s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}} |

Tokens are those the provider reports. A request it refused (an answer that is not valid JSON, a request too large) reports none, though it used tokens: the totals are lower bounds. The judge requests are not counted in the measures of the investigations.
