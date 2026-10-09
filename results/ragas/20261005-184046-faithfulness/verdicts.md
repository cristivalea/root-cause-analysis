# RAGAS Faithfulness: the verdicts of the judge

## RCA-2026-00023 / INC-2026-00482 / HYP-001: 0.58

**Hypothesis:** The new retry‑handler code in Payment API v4.18.2 leaks database connections, exhausting the HikariCP pool and causing timeouts. Connection timeout errors and pool‑pressure warnings started after the retry‑handler deployment (EV-001, EV-002, EV-003). Payment‑api depends on the payment‑postgresql database (EV-005) and uses the retry‑queue (EV-006), the area changed by the deployment. A past RCA identified an identical leak in the retry‑handler as the cause of similar symptoms (EV-007). A previous incident with the same pattern cited database timeout warnings (EV-008). Another incident after a routine release reported latency increase and retry‑queue growth linked to connection exhaustion (EV-010).

**Cited evidence:**

- EV-001 (LOG, LOG-PAY-20260714-14): 2 ERROR log line(s) of type ConnectionTimeout between 14:05 and 14:24 UTC, the first 27 minutes before detection. Example: "HikariPool-1 - Connection is not available, request timed out after 30000ms."
- EV-002 (LOG, LOG-PAY-20260714-15): 1 WARN log line(s) of type ConnectionPoolPressure between 14:11 and 14:11 UTC, the first 20 minutes before detection. Example: "HikariPool-1 active connections reached 96 percent of configured capacity."
- EV-003 (CHANGE, CHG-2026-00871): Deploy Payment API v4.18.2 on CI-PAYMENT-API: Deploy the payment retry-handler changes to production. Implemented at 13:58 UTC, 34 minutes before detection.
- EV-005 (CMDB, CI-PAYMENT-DB): payment-api (CI-PAYMENT-API) connects_to payment-postgresql (CI-PAYMENT-DB, database).
- EV-006 (CMDB, CI-PAYMENT-QUEUE): payment-api (CI-PAYMENT-API) connects_to payment-retry-queue (CI-PAYMENT-QUEUE, queue).
- EV-007 (HISTORICAL_RCA, RCA-2025-00114): Past RCA RCA-2025-00114 for Payment API, completed 2025-11-20. Summary: Intermittent HTTP 500 errors and elevated latencies exceeding 5 seconds were observed across credit card checkout flows following a maintenance window.
Root Cause: Database connection pool exhaustion caused by unclosed SQL sessions inside the payment retry handler block during error response flows. Judged relevant because: Same Payment API service and describes intermittent HTTP 500 errors with >5 s latency and database connection timeouts, directly matching the investigation symptoms.
- EV-008 (HISTORICAL_INCIDENT, INC-2025-00401): Past Payment API incident INC-2025-00401, detected 2025-11-20: Card authorisation requests slow during retry bursts. Checkout requests intermittently returned server errors and some authorisations took longer than five seconds during an afternoon maintenance window. Symptoms: Intermittent HTTP 500 responses; Payment request latency above five seconds; Database timeout warnings. Judged similar because: Incident for Payment API reporting intermittent 500 responses, latency >5 s, and database timeout warnings, matching the search queries.
- EV-010 (HISTORICAL_INCIDENT, INC-2026-00371): Past Payment API incident INC-2026-00371, detected 2026-06-03: Payment authorisation latency increase after routine release. A subset of card payment requests became slow after a routine release, while health checks and non-payment endpoints remained available. Symptoms: Card authorisation latency increase; Retry queue growth; Intermittent gateway errors. Judged similar because: Payment API incident showing increased card authorisation latency and intermittent gateway errors, consistent with the investigation.

**Statements:**

- NO: The new retry‑handler code in Payment API v4.18.2 leaks database connections. (The context only mentions a past RCA about a leak; it does not state that the newly deployed code leaks connections.)
- YES: The leaked database connections exhaust the HikariCP pool. (EV-007 explicitly says the pool exhaustion was caused by unclosed SQL sessions (a leak) in the retry handler.)
- NO: Exhaustion of the HikariCP pool causes timeouts. (The context shows both pool‑pressure warnings and connection‑timeout errors, but does not directly state a causal relationship.)
- YES: Connection timeout errors started after the retry‑handler deployment (EV-001, EV-002, EV-003). (Deployment (EV-003) occurred at 13:58 UTC, while the first timeout errors (EV-001) began at 14:05 UTC, i.e., after the deployment.)
- YES: Pool‑pressure warnings started after the retry‑handler deployment (EV-001, EV-002, EV-003). (The warning (EV-002) was logged at 14:11 UTC, which is after the deployment time of 13:58 UTC.)
- YES: Payment‑api depends on the payment‑postgresql database (EV-005). (EV-005 explicitly states that payment‑api connects_to payment‑postgresql.)
- YES: Payment‑api uses the retry‑queue (EV-006). (EV-006 explicitly states that payment‑api connects_to payment‑retry‑queue.)
- NO: The retry‑queue area was changed by the deployment. (The context mentions changes to the retry‑handler code but does not indicate any modification to the retry‑queue itself.)
- YES: A past RCA identified an identical leak in the retry‑handler as the cause of similar symptoms (EV-007). (EV-007 describes a root cause of unclosed SQL sessions (a leak) in the retry‑handler block.)
- YES: A previous incident with the same pattern cited database timeout warnings (EV-008). (EV-008 lists database timeout warnings among its symptoms.)
- NO: Another incident after a routine release reported latency increase linked to connection exhaustion (EV-010). (EV-010 reports latency increase after a release but does not explicitly link it to connection exhaustion.)
- NO: Another incident after a routine release reported retry‑queue growth linked to connection exhaustion (EV-010). (EV-010 mentions retry‑queue growth, yet it does not state that this growth was caused by connection exhaustion.)

## RCA-2026-00023 / INC-2026-00482 / HYP-002: 0.25

**Hypothesis:** The v4.18.2 release introduced a misconfiguration of the HikariCP pool size, making the pool too small for the current load and leading to exhaustion. The deployment (EV-003) coincides with the onset of pool‑pressure warnings and timeouts (EV-001, EV-002). Payment‑api connects to the database via HikariCP (EV-005) and the pool size is defined in the service configuration. A change to monitoring thresholds (EV-004) suggests recent attention to performance metrics, possibly accompanying a config tweak.

**Cited evidence:**

- EV-001 (LOG, LOG-PAY-20260714-14): 2 ERROR log line(s) of type ConnectionTimeout between 14:05 and 14:24 UTC, the first 27 minutes before detection. Example: "HikariPool-1 - Connection is not available, request timed out after 30000ms."
- EV-002 (LOG, LOG-PAY-20260714-15): 1 WARN log line(s) of type ConnectionPoolPressure between 14:11 and 14:11 UTC, the first 20 minutes before detection. Example: "HikariPool-1 active connections reached 96 percent of configured capacity."
- EV-003 (CHANGE, CHG-2026-00871): Deploy Payment API v4.18.2 on CI-PAYMENT-API: Deploy the payment retry-handler changes to production. Implemented at 13:58 UTC, 34 minutes before detection.
- EV-004 (CHANGE, CHG-2026-00873): Update payment dashboard thresholds on CI-PAYMENT-API: Adjust monitoring thresholds for payment latency dashboards. Implemented at 14:10 UTC, 22 minutes before detection.
- EV-005 (CMDB, CI-PAYMENT-DB): payment-api (CI-PAYMENT-API) connects_to payment-postgresql (CI-PAYMENT-DB, database).
- EV-006 (CMDB, CI-PAYMENT-QUEUE): payment-api (CI-PAYMENT-API) connects_to payment-retry-queue (CI-PAYMENT-QUEUE, queue).
- EV-007 (HISTORICAL_RCA, RCA-2025-00114): Past RCA RCA-2025-00114 for Payment API, completed 2025-11-20. Summary: Intermittent HTTP 500 errors and elevated latencies exceeding 5 seconds were observed across credit card checkout flows following a maintenance window.
Root Cause: Database connection pool exhaustion caused by unclosed SQL sessions inside the payment retry handler block during error response flows. Judged relevant because: Same Payment API service and describes intermittent HTTP 500 errors with >5 s latency and database connection timeouts, directly matching the investigation symptoms.
- EV-008 (HISTORICAL_INCIDENT, INC-2025-00401): Past Payment API incident INC-2025-00401, detected 2025-11-20: Card authorisation requests slow during retry bursts. Checkout requests intermittently returned server errors and some authorisations took longer than five seconds during an afternoon maintenance window. Symptoms: Intermittent HTTP 500 responses; Payment request latency above five seconds; Database timeout warnings. Judged similar because: Incident for Payment API reporting intermittent 500 responses, latency >5 s, and database timeout warnings, matching the search queries.
- EV-010 (HISTORICAL_INCIDENT, INC-2026-00371): Past Payment API incident INC-2026-00371, detected 2026-06-03: Payment authorisation latency increase after routine release. A subset of card payment requests became slow after a routine release, while health checks and non-payment endpoints remained available. Symptoms: Card authorisation latency increase; Retry queue growth; Intermittent gateway errors. Judged similar because: Payment API incident showing increased card authorisation latency and intermittent gateway errors, consistent with the investigation.

**Statements:**

- NO: The v4.18.2 release introduced a misconfiguration of the HikariCP pool size. (The context mentions the deployment of version v4.18.2 but does not state any misconfiguration of the HikariCP pool size.)
- NO: The misconfiguration made the HikariCP pool too small for the current load. (No information in the context links a misconfiguration to an undersized pool; the cause of the issues is not described as a size misconfiguration.)
- NO: The insufficient pool size led to exhaustion. (While pool exhaustion is reported (EV-001, EV-002), the context attributes it to unclosed SQL sessions in historical RCA, not to an insufficient pool size.)
- YES: The deployment EV-003 coincides with the onset of pool‑pressure warnings and timeouts EV-001 and EV-002. (EV-003 was implemented at 13:58 UTC, and the first timeout (EV-001) occurred at 14:05 UTC and the warning (EV-002) at 14:11 UTC, showing temporal coincidence.)
- NO: Payment‑api connects to the database via HikariCP EV-005. (EV-005 only states that payment‑api connects to the database; it does not specify that the connection uses HikariCP, so the claim is not directly supported.)
- NO: The pool size is defined in the service configuration. (The context contains no statement about where or how the pool size is configured.)
- YES: A change to monitoring thresholds EV-004 suggests recent attention to performance metrics. (EV-004 explicitly describes an update of payment latency dashboard thresholds, indicating attention to performance metrics.)
- NO: The change to monitoring thresholds possibly accompanies a configuration tweak. (The word "possibly" introduces speculation; the context does not provide evidence that the threshold change was accompanied by a configuration tweak.)

## RCA-2026-00018 / INC-2026-00411 / HYP-001: 0.83

**Hypothesis:** Database connection‑pool exhaustion in the payment‑API caused by unclosed SQL sessions inside the retry‑handler logic. Historical RCA (EV-003) identified exactly this failure mode for the same service. Past incident (EV-004) reported database timeout warnings alongside the same symptoms. CMDB entry (EV-001) shows payment‑API directly uses the payment‑PostgreSQL database, making it a plausible failure point.

**Cited evidence:**

- EV-003 (HISTORICAL_RCA, RCA-2025-00114): Past RCA RCA-2025-00114 for Payment API, completed 2025-11-20. Summary: Intermittent HTTP 500 errors and elevated latencies exceeding 5 seconds were observed across credit card checkout flows following a maintenance window.
Root Cause: Database connection pool exhaustion caused by unclosed SQL sessions inside the payment retry handler block during error response flows. Judged relevant because: Same Payment API service and reports intermittent HTTP 500 errors and latency >5s, matching the search queries about checkout failures and delayed retries.
- EV-004 (HISTORICAL_INCIDENT, INC-2025-00401): Past Payment API incident INC-2025-00401, detected 2025-11-20: Card authorisation requests slow during retry bursts. Checkout requests intermittently returned server errors and some authorisations took longer than five seconds during an afternoon maintenance window. Symptoms: Intermittent HTTP 500 responses; Payment request latency above five seconds; Database timeout warnings. Judged similar because: Payment API incident describing intermittent server errors and latency spikes, directly matching the search symptoms.
- EV-001 (CMDB, CI-PAYMENT-DB): payment-api (CI-PAYMENT-API) connects_to payment-postgresql (CI-PAYMENT-DB, database).

**Statements:**

- YES: Database connection-pool exhaustion occurred in the payment-API. (The root cause in EV-003 explicitly states that a database connection pool exhaustion occurred for the Payment API service.)
- YES: The exhaustion was caused by unclosed SQL sessions inside the retry-handler logic. (EV-003 specifies the exhaustion was caused by unclosed SQL sessions inside the payment retry handler block.)
- YES: Historical root cause analysis EV-003 identified exactly this failure mode for the same service. (EV-003 is the historical root cause analysis that identifies the database connection pool exhaustion caused by unclosed SQL sessions for the Payment API.)
- YES: Past incident EV-004 reported database timeout warnings alongside the same symptoms. (The description of EV-004 lists "Database timeout warnings" as part of its symptoms.)
- YES: CMDB entry EV-001 shows that the payment-API directly uses the payment-PostgreSQL database. (EV-001 states that payment-api connects_to payment-postgresql, indicating direct use of the database.)
- NO: The direct use of the payment-PostgreSQL database makes the payment-API a plausible failure point. (The context does not explicitly state that this direct use makes the API a plausible failure point; it is an inferred judgment, not a direct fact.)

## RCA-2026-00018 / INC-2026-00411 / HYP-002: 0.60

**Hypothesis:** Back‑pressure from an overloaded payment‑retry‑queue causing request latency spikes and intermittent gateway errors. CMDB (EV-002) confirms payment‑API pushes work to the retry queue. Historical incident (EV-005) described similar latency increase and queue growth. The same pattern of intermittent errors matches the current symptoms.

**Cited evidence:**

- EV-002 (CMDB, CI-PAYMENT-QUEUE): payment-api (CI-PAYMENT-API) connects_to payment-retry-queue (CI-PAYMENT-QUEUE, queue).
- EV-005 (HISTORICAL_INCIDENT, INC-2026-00371): Past Payment API incident INC-2026-00371, detected 2026-06-03: Payment authorisation latency increase after routine release. A subset of card payment requests became slow after a routine release, while health checks and non-payment endpoints remained available. Symptoms: Card authorisation latency increase; Retry queue growth; Intermittent gateway errors. Judged similar because: Payment API incident with latency increase and intermittent gateway errors, aligning with the investigation focus.

**Statements:**

- NO: Back‑pressure from an overloaded payment‑retry‑queue caused request latency spikes. (The context mentions latency increase and queue growth but does not state that back‑pressure from the overloaded queue caused the latency spikes.)
- NO: Back‑pressure from an overloaded payment‑retry‑queue caused intermittent gateway errors. (The context reports intermittent gateway errors and queue growth, but it does not attribute the errors to back‑pressure from the queue.)
- YES: CMDB (EV-002) confirms that the payment‑API pushes work to the retry queue. (EV-002 states that payment‑API connects_to payment‑retry‑queue, which directly implies that the API pushes work to the queue.)
- YES: Historical incident (EV-005) described a similar latency increase and queue growth. (EV-005 describes a payment authorisation latency increase and retry queue growth, matching the stated similarity.)
- YES: The same pattern of intermittent errors matches the current symptoms. (Both the context and EV-005 list intermittent gateway errors as a symptom, indicating the pattern matches.)
