# RAGAS Faithfulness: the verdicts of the judge

## RCA-2026-00024 / INC-2026-00101 / HYP-001: 0.67

**Hypothesis:** Database connection exhaustion caused by payroll batch workers scaling up to maximum threads and consuming most PostgreSQL connections, leading to portal API timeouts. ConnectionPoolPressure and TooManyConnections errors indicate the database reached its connection limit. WorkerPoolScaleUp and WorkerPoolAtMaximum warnings show the batch workers were running at full capacity. The payroll‑portal API depends on the same database, so exhaustion would affect it. Historical RCAs and incidents consistently link payroll batch runs to portal timeouts. The timing of the errors aligns with the start of the payroll batch run.

**Cited evidence:**

- EV-003 (LOG, LOG-PAYROLL-20260727-14): 10 ERROR log line(s) of type TooManyConnections between 06:31 and 07:32 UTC, the first 9 minutes before detection. Example: "FATAL: remaining connection slots are reserved for non-replication superuser connections"
- EV-004 (LOG, LOG-PAYROLL-20260727-06): 6 WARN log line(s) of type ConnectionPoolPressure between 06:18 and 06:32 UTC, the first 22 minutes before detection. Example: "payroll-postgresql connections in use 176 of 200 (88%)"
- EV-005 (LOG, LOG-PAYROLL-20260727-02): 4 WARN log line(s) of type WorkerPoolScaleUp between 06:04 and 06:14 UTC, the first 36 minutes before detection. Example: "Autoscaler raised payroll worker threads from 16 to 32 (policy payroll-workers-hpa, max 96)"
- EV-006 (LOG, LOG-PAYROLL-20260727-07): 1 WARN log line(s) of type WorkerPoolAtMaximum between 06:21 and 06:21 UTC, the first 18 minutes before detection. Example: "Payroll worker pool at its maximum: 96 threads, one database connection each (policy payroll-workers-hpa, max 96)"
- EV-007 (CMDB, CI-PAYROLL-DB): payroll-portal-api (CI-PAYROLL-APP) depends_on payroll-postgresql (CI-PAYROLL-DB, database).
- EV-010 (HISTORICAL_RCA, RCA-2025-00042): Past RCA RCA-2025-00042 for Payroll Service, completed 2025-02-14. Summary: The weekly payroll calculation batch did not finish within its window and the employee self-service portal returned HTTP 504 timeouts during the Monday morning peak.
Root Cause: The batch worker pool scaled up to 64 concurrent threads and used almost all of the PostgreSQL connections (max_connections=100) shared with the portal API, so both the batch and the portal waited for connections. Judged relevant because: Payroll Service with portal HTTP 504s during Monday batch, matching symptoms.
- EV-011 (HISTORICAL_INCIDENT, INC-2025-00119): Past Payroll Service incident INC-2025-00119, detected 2025-01-20: Payroll batch delays employee portal requests. The weekly payroll calculation did not finish within its window and the employee self-service portal returned timeouts during the morning peak. Symptoms: HTTP 504 gateway timeout on the employee portal; Payroll batch job exceeded SLA. Judged similar because: Payroll Service incident with portal timeouts during Monday payroll run.
- EV-012 (HISTORICAL_INCIDENT, INC-2026-00188): Past Payroll Service incident INC-2026-00188, detected 2026-05-25: Salary calculation run late on Monday. The Monday salary calculation finished 70 minutes late and the portal was slow while it ran. Symptoms: Payroll batch job exceeded SLA; Portal request timeouts. Judged similar because: Payroll Service incident with late salary run and portal slowness.
- EV-013 (HISTORICAL_INCIDENT, INC-2025-00104): Past Payroll Service incident INC-2025-00104, detected 2025-01-06: Employee portal slow during Monday payroll run. Employees reported slow payslip pages on Monday morning while the weekly payroll batch was running. Symptoms: Slow payslip pages; Portal request timeouts. Judged similar because: Payroll Service incident with slow portal during Monday payroll run.
- EV-014 (HISTORICAL_INCIDENT, INC-2026-00196): Past Payroll Service incident INC-2026-00196, detected 2026-06-29: Employee portal unavailable during salary run. Employees could not open the portal for over an hour during the Monday salary run. Symptoms: HTTP 504 gateway timeout; Database connection acquisition latency. Judged similar because: Payroll Service incident with portal unavailability and HTTP 504 during salary run.
- EV-015 (HISTORICAL_INCIDENT, INC-2026-00167): Past Payroll Service incident INC-2026-00167, detected 2026-04-27: Employee portal timeouts during payroll processing. The employee portal returned timeouts while payroll processing was running. Symptoms: Portal request timeouts; Payroll batch running late. Judged similar because: Payroll Service incident with portal timeouts during payroll processing.

**Statements:**

- YES: Payroll batch workers scaled up to maximum threads and consumed most PostgreSQL connections, causing database connection exhaustion. (Logs show WorkerPoolScaleUp and WorkerPoolAtMaximum reaching the maximum of 96 threads, and TooManyConnections errors indicating connection exhaustion.)
- YES: Database connection exhaustion led to portal API timeouts. (The historical RCA explicitly states that the batch worker pool used almost all PostgreSQL connections, causing both the batch and the portal API to wait for connections, resulting in HTTP 504 timeouts.)
- NO: ConnectionPoolPressure warnings indicate that the database reached its connection limit. (ConnectionPoolPressure warnings show high usage (e.g., 176 of 200 connections) but do not state that the limit was reached; only TooManyConnections errors indicate a limit breach.)
- YES: TooManyConnections errors indicate that the database reached its connection limit. (The TooManyConnections log example explicitly mentions that remaining connection slots are reserved, which means the connection limit was reached.)
- NO: WorkerPoolScaleUp warnings show that the batch workers were running at full capacity. (WorkerPoolScaleUp warnings describe an increase in threads (e.g., from 16 to 32) but do not indicate that the pool was at its maximum capacity; that is shown by WorkerPoolAtMaximum warnings.)
- YES: WorkerPoolAtMaximum warnings show that the batch workers were running at full capacity. (The WorkerPoolAtMaximum log states the pool is at its maximum of 96 threads, confirming full capacity.)
- YES: The payroll-portal API depends on the same database, so database exhaustion would affect the payroll-portal API. (CMDB entry shows payroll-portal-api depends on payroll-postgresql, and exhaustion of that database is linked to portal timeouts in the RCA.)
- YES: Historical RCAs and incidents consistently link payroll batch runs to portal timeouts. (Multiple historical RCA and incident entries (EV-010 to EV-015) describe payroll batch runs causing portal HTTP 504 timeouts or slowness.)
- NO: The timing of the errors aligns with the start of the payroll batch run. (The context provides timestamps for the errors but does not explicitly state the start time of the payroll batch run, so the alignment cannot be directly inferred.)

## RCA-2026-00024 / INC-2026-00101 / HYP-002: 0.38

**Hypothesis:** Misconfiguration of the payroll‑app connection pool caused connections to be held longer than necessary, leading to exhaustion. Connection timeouts and TooManyConnections errors point to a shortage of available connections. ConnectionPoolPressure warnings suggest the pool was under stress. The payroll‑portal API depends on the same database, so a pool misconfiguration would affect it. Historical incidents show similar symptoms during payroll runs, which could be due to pool settings.

**Cited evidence:**

- EV-001 (LOG, LOG-PAYROLL-20260727-09): 26 ERROR log line(s) of type ConnectionTimeout between 06:26 and 07:35 UTC, the first 14 minutes before detection. Example: "HikariPool-payroll - Connection is not available, request timed out after 30000ms."
- EV-003 (LOG, LOG-PAYROLL-20260727-14): 10 ERROR log line(s) of type TooManyConnections between 06:31 and 07:32 UTC, the first 9 minutes before detection. Example: "FATAL: remaining connection slots are reserved for non-replication superuser connections"
- EV-004 (LOG, LOG-PAYROLL-20260727-06): 6 WARN log line(s) of type ConnectionPoolPressure between 06:18 and 06:32 UTC, the first 22 minutes before detection. Example: "payroll-postgresql connections in use 176 of 200 (88%)"
- EV-007 (CMDB, CI-PAYROLL-DB): payroll-portal-api (CI-PAYROLL-APP) depends_on payroll-postgresql (CI-PAYROLL-DB, database).

**Statements:**

- NO: Misconfiguration of the payroll‑app connection pool caused connections to be held longer than necessary. (The context reports connection timeouts, TooManyConnections errors, and pool pressure warnings but does not mention any misconfiguration or that connections were held longer.)
- NO: The held connections led to exhaustion. (The logs show errors and warnings indicating high usage, but they do not explicitly state that connections were being held and caused exhaustion.)
- YES: Connection timeouts and TooManyConnections errors indicate a shortage of available connections. (The context includes ConnectionTimeout errors and TooManyConnections errors, both of which imply that available connections were insufficient.)
- YES: ConnectionPoolPressure warnings suggest that the pool was under stress. (The warning logs show 176 of 200 connections in use (88%), which directly indicates pool pressure and stress.)
- YES: The payroll‑portal API depends on the same database. (EV-007 explicitly states that payroll‑portal‑api depends_on payroll‑postgresql database.)
- NO: A pool misconfiguration would affect the payroll‑portal API. (The context does not provide any information about a misconfiguration or its impact on the API.)
- NO: Historical incidents show similar symptoms during payroll runs. (No historical incident information is present in the provided context.)
- NO: The similar symptoms could be due to pool settings. (The context does not discuss possible causes such as pool settings for the observed symptoms.)

## RCA-2026-00025 / INC-2026-00482 / HYP-001: 0.60

**Hypothesis:** Unclosed database sessions in the payment retry-handler code caused connection pool exhaustion. ConnectionTimeout errors and ConnectionPoolPressure warnings indicate pool exhaustion Retry-handler change was deployed immediately before the first errors Past RCA (RCA-2025-00114) identified the same issue in a previous release

**Cited evidence:**

- EV-001 (LOG, LOG-PAY-20260714-14): 24 ERROR log line(s) of type ConnectionTimeout between 14:05 and 14:28 UTC, the first 27 minutes before detection. Example: "HikariPool-1 - Connection is not available, request timed out after 30000ms."
- EV-002 (LOG, LOG-PAY-20260714-15): 8 WARN log line(s) of type ConnectionPoolPressure between 14:11 and 14:27 UTC, the first 20 minutes before detection. Example: "HikariPool-1 active connections reached 96 percent of configured capacity."
- EV-003 (CHANGE, CHG-2026-00871): Deploy Payment API v4.18.2 on CI-PAYMENT-API: Deploy the payment retry-handler changes to production. Implemented at 13:58 UTC, 34 minutes before detection.
- EV-005 (CMDB, CI-PAYMENT-DB): payment-api (CI-PAYMENT-API) connects_to payment-postgresql (CI-PAYMENT-DB, database).
- EV-007 (HISTORICAL_RCA, RCA-2025-00114): Past RCA RCA-2025-00114 for Payment API, completed 2025-12-05. Summary: Intermittent HTTP 500 errors and latency above 5 seconds were observed across card checkout flows after a release of the Payment API.
Root Cause: Database connection pool exhaustion caused by unclosed SQL sessions inside the payment retry handler block during error response flows. Judged relevant because: Intermittent HTTP 500 errors, latency above 5s, and database timeouts match the investigation symptoms.

**Statements:**

- YES: Unclosed database sessions in the payment retry-handler code caused connection pool exhaustion. (The past RCA (RCA-2025-00114) explicitly states that database connection pool exhaustion was caused by unclosed SQL sessions inside the payment retry handler block.)
- NO: ConnectionTimeout errors indicate connection pool exhaustion. (The context reports ConnectionTimeout errors but does not explicitly link them to connection pool exhaustion.)
- NO: ConnectionPoolPressure warnings indicate connection pool exhaustion. (The context shows ConnectionPoolPressure warnings about high usage but does not explicitly state they indicate full exhaustion.)
- YES: A retry-handler change was deployed immediately before the first errors. (The retry-handler change was deployed at 13:58 UTC, and the first ConnectionTimeout errors occurred at 14:05 UTC, a short interval before the errors began.)
- YES: Past RCA (RCA-2025-00114) identified the same issue in a previous release. (The past RCA describes the same root cause—unclosed sessions in the retry handler leading to pool exhaustion—as the current incident.)

## RCA-2026-00025 / INC-2026-00482 / HYP-002: 0.40

**Hypothesis:** The database connection pool was insufficient for the load, leading to exhaustion independent of code changes. ConnectionTimeout and ConnectionPoolPressure warnings are consistent with pool exhaustion The retry-handler change may have increased load but not necessarily caused unclosed sessions Similar symptoms were observed in past incidents during peak traffic

**Cited evidence:**

- EV-001 (LOG, LOG-PAY-20260714-14): 24 ERROR log line(s) of type ConnectionTimeout between 14:05 and 14:28 UTC, the first 27 minutes before detection. Example: "HikariPool-1 - Connection is not available, request timed out after 30000ms."
- EV-002 (LOG, LOG-PAY-20260714-15): 8 WARN log line(s) of type ConnectionPoolPressure between 14:11 and 14:27 UTC, the first 20 minutes before detection. Example: "HikariPool-1 active connections reached 96 percent of configured capacity."
- EV-003 (CHANGE, CHG-2026-00871): Deploy Payment API v4.18.2 on CI-PAYMENT-API: Deploy the payment retry-handler changes to production. Implemented at 13:58 UTC, 34 minutes before detection.

**Statements:**

- NO: The database connection pool was insufficient for the load, leading to exhaustion independent of code changes. (The context shows connection timeout errors and pool pressure warnings, indicating exhaustion, but it does not state whether this was independent of the recent code change.)
- YES: ConnectionTimeout warnings are consistent with pool exhaustion. (The context reports ConnectionTimeout log lines together with high pool usage, which aligns with pool exhaustion.)
- YES: ConnectionPoolPressure warnings are consistent with pool exhaustion. (The context includes ConnectionPoolPressure warnings indicating 96% capacity, which directly reflects pool exhaustion.)
- NO: The retry-handler change may have increased load but did not necessarily cause unclosed sessions. (The context mentions the deployment of the retry-handler change but provides no information about its impact on load or session handling.)
- NO: Similar symptoms were observed in past incidents during peak traffic. (The context does not reference any past incidents or peak‑traffic comparisons.)

## RCA-2026-00026 / INC-2026-00103 / HYP-001: 0.33

**Hypothesis:** Cross‑region latency to the session lock store caused lock acquisition failures and session conflicts during the region failover. Region failover moved traffic to eu-central-1 while the lock store remained in eu-west-1, creating high round‑trip times. Cross‑region latency warnings precede the lock failures, indicating network delay. Lock acquisition failures and session conflicts are typical symptoms of delayed lock release due to latency. The portal’s session lock store is a dedicated Redis instance, as shown in the CMDB. The timing of the errors aligns with the failover event.

**Cited evidence:**

- EV-004 (LOG, LOG-PORTAL-20260810-01): 1 WARN log line(s) of type RegionFailover between 09:31 and 09:31 UTC, the first 14 minutes before detection. Example: "Traffic manager moved 100% of portal traffic to eu-central-1 (health check failures in eu-west-1)"
- EV-003 (LOG, LOG-PORTAL-20260810-02): 8 WARN log line(s) of type CrossRegionLatency between 09:33 and 10:44 UTC, the first 12 minutes before detection. Example: "Session lock store round trip 1,299ms from eu-central-1 (baseline 2ms)"
- EV-001 (LOG, LOG-PORTAL-20260810-03): 30 ERROR log line(s) of type LockAcquisitionFailure between 09:38 and 10:52 UTC, the first 7 minutes before detection. Example: "Failed to acquire session lock portal:session:38723: lock still held by portal-web-prod-02 (lease 100ms expired)"
- EV-002 (LOG, LOG-PORTAL-20260810-04): 20 ERROR log line(s) of type SessionConflict between 09:40 and 10:49 UTC, the first 5 minutes before detection. Example: "Concurrent session update rejected: version conflict on session S-34002; user logged out"
- EV-008 (CMDB, CI-PORTAL-LOCK-REDIS): customer-portal-web (CI-PORTAL-WEB) connects_to portal-session-lock-redis (CI-PORTAL-LOCK-REDIS, cache).

**Statements:**

- NO: Cross‑region latency to the session lock store caused lock acquisition failures and session conflicts during the region failover. (The context reports high cross‑region latency and later lock acquisition failures and session conflicts, but it does not explicitly state that the latency caused those failures.)
- NO: Region failover moved traffic to eu-central-1 while the lock store remained in eu-west-1, creating high round‑trip times. (The context confirms traffic was moved to eu-central-1 and shows high latency from eu-central-1, but it never explicitly says the lock store was located in eu-west-1.)
- YES: Cross‑region latency warnings precede the lock failures, indicating network delay. (CrossRegionLatency logs start at 09:33, while LockAcquisitionFailure logs start at 09:38, showing the latency warnings occur earlier, which supports the indication of network delay.)
- NO: Lock acquisition failures and session conflicts are typical symptoms of delayed lock release due to latency. (The context lists the failures and the latency but does not explicitly link the failures to delayed lock release caused by latency.)
- NO: The portal’s session lock store is a dedicated Redis instance, as shown in the CMDB. (The CMDB entry shows a connection to a Redis cache (portal-session-lock-redis) but does not state that it is a dedicated instance.)
- YES: The timing of the errors aligns with the failover event. (The region failover occurs at 09:31, and the subsequent latency warnings, lock acquisition failures, and session conflicts all happen shortly after, indicating temporal alignment.)

## RCA-2026-00026 / INC-2026-00103 / HYP-002: 0.33

**Hypothesis:** The portal-session-lock-redis instance was overloaded or misconfigured, leading to high latency and lock contention independent of the region failover. LockAcquisitionFailure and SessionConflict errors are consistent with a slow or overloaded lock store. Cross‑region latency warnings could be a symptom of an overloaded Redis instance rather than network delay. The CMDB indicates a dedicated Redis cache for session locks, which could be experiencing resource pressure. The errors began shortly after the region failover, but the failover itself may have increased load on the lock store. No evidence of a recent change to the lock store configuration is present in the ledger.

**Cited evidence:**

- EV-001 (LOG, LOG-PORTAL-20260810-03): 30 ERROR log line(s) of type LockAcquisitionFailure between 09:38 and 10:52 UTC, the first 7 minutes before detection. Example: "Failed to acquire session lock portal:session:38723: lock still held by portal-web-prod-02 (lease 100ms expired)"
- EV-002 (LOG, LOG-PORTAL-20260810-04): 20 ERROR log line(s) of type SessionConflict between 09:40 and 10:49 UTC, the first 5 minutes before detection. Example: "Concurrent session update rejected: version conflict on session S-34002; user logged out"
- EV-008 (CMDB, CI-PORTAL-LOCK-REDIS): customer-portal-web (CI-PORTAL-WEB) connects_to portal-session-lock-redis (CI-PORTAL-LOCK-REDIS, cache).
- EV-003 (LOG, LOG-PORTAL-20260810-02): 8 WARN log line(s) of type CrossRegionLatency between 09:33 and 10:44 UTC, the first 12 minutes before detection. Example: "Session lock store round trip 1,299ms from eu-central-1 (baseline 2ms)"
- EV-004 (LOG, LOG-PORTAL-20260810-01): 1 WARN log line(s) of type RegionFailover between 09:31 and 09:31 UTC, the first 14 minutes before detection. Example: "Traffic manager moved 100% of portal traffic to eu-central-1 (health check failures in eu-west-1)"

**Statements:**

- NO: The portal-session-lock-redis instance was overloaded or misconfigured. (The context reports errors and latency but does not explicitly state that the Redis instance was overloaded or misconfigured.)
- NO: The overload or misconfiguration caused high latency and lock contention independent of the region failover. (The context does not provide a causal link between overload/misconfiguration and the observed latency or lock contention.)
- NO: LockAcquisitionFailure and SessionConflict errors are consistent with a slow or overloaded lock store. (While the errors are listed, the context does not explicitly describe them as being consistent with a slow or overloaded lock store.)
- NO: Cross‑region latency warnings could be a symptom of an overloaded Redis instance rather than network delay. (The context mentions cross‑region latency warnings but does not attribute them to an overloaded Redis instance.)
- YES: The CMDB indicates a dedicated Redis cache for session locks. (EV-008 states that portal-session-lock-redis is a cache used by the portal for session locks.)
- NO: The dedicated Redis cache for session locks could be experiencing resource pressure. (The context does not provide information about the current resource usage of the Redis cache.)
- YES: The errors began shortly after the region failover. (The region failover occurred at 09:31 UTC, and the first error logs (CrossRegionLatency, LockAcquisitionFailure, SessionConflict) start at 09:33, 09:38, and 09:40 UTC respectively, which is shortly after.)
- NO: The region failover may have increased load on the lock store. (The context does not explicitly state that the failover increased load on the lock store; this is a speculative inference.)
- YES: The ledger contains no evidence of a recent change to the lock store configuration. (The provided context contains no mention of any configuration change to the lock store, indicating no evidence of such a change.)

## RCA-2026-00027 / INC-2026-00104 / HYP-001: 1.00

**Hypothesis:** The wildcard TLS certificate for the public API gateway expired because the renewal process was missed or failed, causing handshake failures. CertificateExpired logs (EV-001) indicate the certificate expired at 03:00 UTC TlsHandshakeFailed logs (EV-002) show handshake failures due to expired certificate Historical RCA (EV-010) documents a similar incident caused by missed renewal

**Cited evidence:**

- EV-001 (LOG, LOG-GW-20260501-01): 30 ERROR log line(s) of type CertificateExpired between 03:00 and 04:18 UTC, the first 12 minutes before detection. Example: "Serving certificate *.api.example-bank.com expired at 2026-05-01T03:00:00Z"
- EV-002 (LOG, LOG-GW-20260501-02): 30 ERROR log line(s) of type TlsHandshakeFailed between 03:00 and 04:16 UTC, the first 12 minutes before detection. Example: "SSL_do_handshake() failed (SSL: error:0A000415:SSL routines::sslv3 alert certificate expired) while SSL handshaking"
- EV-010 (HISTORICAL_RCA, RCA-2024-00088): Past RCA RCA-2024-00088 for API Gateway, completed 2024-10-02. Summary: The wildcard TLS certificate of the edge proxy nodes expired during the night and all clients failed the TLS handshake with the public API.
Root Cause: The wildcard certificate was renewed by hand once a year. The reminder was sent to a former team member and the renewal was missed. Judged relevant because: Same service (API Gateway) and describes TLS handshake failures caused by an expired wildcard certificate, directly matching the investigation symptoms.

**Statements:**

- YES: The wildcard TLS certificate for the public API gateway expired because the renewal process was missed or failed. (The historical RCA (EV-010) states the root cause was that the renewal reminder was sent to a former team member and the renewal was missed, leading to the certificate expiration.)
- YES: The expiration of the wildcard TLS certificate caused handshake failures. (Both EV-002 logs and the RCA summary describe TLS handshake failures that occurred because the wildcard certificate had expired.)
- YES: CertificateExpired logs (EV-001) indicate that the wildcard TLS certificate expired at 03:00 UTC. (The example log for EV-001 explicitly shows the certificate expired at 2026-05-01T03:00:00Z, i.e., 03:00 UTC.)
- YES: TlsHandshakeFailed logs (EV-002) show handshake failures due to the expired wildcard TLS certificate. (The EV-002 example log contains "sslv3 alert certificate expired", indicating the handshake failures were caused by the expired certificate.)
- YES: Historical RCA (EV-010) documents a similar incident that was caused by a missed renewal. (The RCA description notes that the wildcard certificate renewal was missed, which caused the certificate to expire and the incident.)

## RCA-2026-00027 / INC-2026-00104 / HYP-002: 0.43

**Hypothesis:** The cert-manager application failed to issue or deploy a new certificate, leaving the edge proxy nodes with an expired certificate. public-api-gateway depends_on cert-manager (EV-004) indicates cert-manager is responsible for certificate issuance Historical RCA (EV-010) suggests renewal was missed, implying cert-manager failure

**Cited evidence:**

- EV-004 (CMDB, CI-CERT-MANAGER): public-api-gateway (CI-API-GATEWAY) depends_on cert-manager (CI-CERT-MANAGER, application).
- EV-010 (HISTORICAL_RCA, RCA-2024-00088): Past RCA RCA-2024-00088 for API Gateway, completed 2024-10-02. Summary: The wildcard TLS certificate of the edge proxy nodes expired during the night and all clients failed the TLS handshake with the public API.
Root Cause: The wildcard certificate was renewed by hand once a year. The reminder was sent to a former team member and the renewal was missed. Judged relevant because: Same service (API Gateway) and describes TLS handshake failures caused by an expired wildcard certificate, directly matching the investigation symptoms.

**Statements:**

- NO: The cert-manager application failed to issue a new certificate. (The context does not mention any failure of cert-manager to issue a certificate; it attributes the missed renewal to a manual process.)
- NO: The cert-manager application failed to deploy a new certificate. (No information in the context indicates that cert-manager failed to deploy a certificate.)
- YES: The failure left the edge proxy nodes with an expired certificate. (The context states that the wildcard TLS certificate of the edge proxy nodes expired, causing the failure.)
- YES: The public-api-gateway depends on cert-manager (EV-004). (EV-004 explicitly records that public-api-gateway depends_on cert-manager.)
- NO: The dependency indicates that cert-manager is responsible for certificate issuance. (The context only states the dependency, not that cert-manager is responsible for issuance; this is an inferred implication, not a direct statement.)
- YES: Historical RCA (EV-010) suggests that the certificate renewal was missed. (The RCA root cause explicitly says the renewal was missed.)
- NO: The missed renewal implies a cert-manager failure. (The missed renewal is attributed to a forgotten manual reminder, not to a cert-manager failure, and the context does not link the two.)

## RCA-2026-00028 / INC-2026-00105 / HYP-002: 0.67

**Hypothesis:** Slow ledger writes during peak hours caused consumer group rebalancing and backlog, similar to past incidents. Consumer lag and rebalance warnings (EV-003, EV-004) match patterns from historical RCA and incidents CommitFailed errors (EV-002) are typical after rebalancing storms Historical incidents (EV-010, EV-011, EV-012, EV-013, EV-014, EV-015) documented similar symptoms

**Cited evidence:**

- EV-003 (LOG, LOG-SETTLE-20260212-04): 12 WARN log line(s) of type ConsumerLag between 22:03 and 23:54 UTC, the first 15 minutes before detection. Example: "Consumer lag on settlement-events: 4,200 records"
- EV-004 (LOG, LOG-SETTLE-20260212-08): 10 WARN log line(s) of type ConsumerRebalance between 22:07 and 23:59 UTC, the first 11 minutes before detection. Example: "Revoking previously assigned partitions [settlement-events-4]"
- EV-002 (LOG, LOG-SETTLE-20260212-22): 5 ERROR log line(s) of type CommitFailed between 22:40 and 23:42 UTC, the first 22 minutes after detection. Example: "CommitFailedException: the group has already rebalanced and assigned the partitions to another member"
- EV-010 (HISTORICAL_RCA, RCA-2025-00192): Past RCA RCA-2025-00192 for Settlement Service, completed 2025-07-25. Summary: Settlement event processing paused repeatedly because the consumer group kept rebalancing during the end-of-day peak.
Root Cause: Slow ledger writes during the end-of-day peak made each batch take longer than max.poll.interval.ms. Consumers were removed from the group, which triggered a rebalance storm and stopped processing. Judged relevant because: Same service (Settlement Service) and symptoms of consumer group rebalancing and backlog during end‑of‑day match the investigation queries.
- EV-011 (HISTORICAL_INCIDENT, INC-2025-00982): Past Settlement Service incident INC-2025-00982, detected 2025-07-11: Settlement events stop processing temporarily. Settlement event processing paused several times during the evening and a backlog built up. Symptoms: Consumer lag; Frequent rebalance events. Judged similar because: Same service and describes settlement events stopping, backlog, consumer lag, and rebalancing—directly matches investigation.
- EV-012 (HISTORICAL_INCIDENT, INC-2024-01407): Past Settlement Service incident INC-2024-01407, detected 2024-11-17: Settlement backlog growing slowly. Consumer lag on settlement events grew during the afternoon and recovered on its own. Symptoms: Consumer lag. Judged similar because: Same service and describes backlog growth, consumer lag, and rebalancing—matches investigation.
- EV-013 (HISTORICAL_INCIDENT, INC-2026-00048): Past Settlement Service incident INC-2026-00048, detected 2026-01-11: Settlement events processed slowly. Consumer lag on settlement events grew during the afternoon and recovered on its own. Symptoms: Frequent rebalance events; Processing throughput drop. Judged similar because: Same service and describes slow processing, consumer lag, rebalancing, and throughput drop—matches investigation.
- EV-014 (HISTORICAL_INCIDENT, INC-2024-00349): Past Settlement Service incident INC-2024-00349, detected 2024-03-20: Settlement backlog growing slowly. Settlement event processing slowed down and a backlog built up for a while. First reports came from customers. Symptoms: Frequent rebalance events; Processing throughput drop. Judged similar because: Same service and describes backlog, rebalancing, and throughput drop—matches investigation.
- EV-015 (HISTORICAL_INCIDENT, INC-2024-00196): Past Settlement Service incident INC-2024-00196, detected 2024-02-14: Settlement events processed slowly. Consumer lag on settlement events grew during the afternoon and recovered on its own. First reports came from customers. Symptoms: Frequent rebalance events; Processing throughput drop. Judged similar because: Same service and describes slow processing, consumer lag, rebalancing, and throughput drop—matches investigation.
- EV-005 (CHANGE, CHG-2026-00188): Register settlement-events schema v7 on CI-SCHEMA-REGISTRY: Register v7 of the settlement-events Avro schema (adds fx_rate_source, amount becomes a string). Compatibility mode set to NONE for this subject to allow the type change. Implemented at 21:05 UTC, 73 minutes before detection.
- EV-001 (LOG, LOG-SETTLE-20260212-01): 40 ERROR log line(s) of type DeserializationError between 21:58 and 00:09 UTC, the first 20 minutes before detection. Example: "Failed to deserialize record at settlement-events-4 offset 1883201: schema id 412 field 'amount' cannot be converted from string to decimal (retry 1)"

**Statements:**

- YES: Slow ledger writes during peak hours caused consumer group rebalancing. (The root cause (EV-010) explicitly states that slow ledger writes during the end‑of‑day peak triggered a rebalance storm, i.e., consumer group rebalancing.)
- NO: Slow ledger writes during peak hours caused backlog. (The context does not explicitly link slow ledger writes to a backlog; it only links them to rebalancing and stopped processing.)
- YES: The situation is similar to past incidents. (Multiple past incidents (EV-010‑EV-015) are described as similar to the current investigation, indicating the situation is similar to past incidents.)
- YES: Consumer lag and rebalance warnings (EV-003, EV-004) match patterns from historical root cause analyses and incidents. (EV-003 and EV-004 show ConsumerLag and ConsumerRebalance warnings, and the historical analyses (EV-010‑EV-015) discuss the same patterns, so they match.)
- NO: CommitFailed errors (EV-002) are typical after rebalancing storms. (The context mentions CommitFailed errors (EV-002) and a rebalance storm, but does not state that such errors are typical after rebalancing storms.)
- YES: Historical incidents (EV-010, EV-011, EV-012, EV-013, EV-014, EV-015) documented similar symptoms. (The listed historical incidents (EV-010‑EV-015) are each noted as having similar symptoms, confirming they documented similar symptoms.)

## RCA-2026-00028 / INC-2026-00105 / HYP-001: 0.60

**Hypothesis:** The schema change that made 'amount' a string caused deserialization failures, leading to consumer lag and rebalancing. Schema change at 21:05 UTC (EV-005) precedes deserialization errors (EV-001) Deserialization errors directly indicate type mismatch (EV-001) Lag and rebalance warnings (EV-003, EV-004) are typical consequences of deserialization failures

**Cited evidence:**

- EV-005 (CHANGE, CHG-2026-00188): Register settlement-events schema v7 on CI-SCHEMA-REGISTRY: Register v7 of the settlement-events Avro schema (adds fx_rate_source, amount becomes a string). Compatibility mode set to NONE for this subject to allow the type change. Implemented at 21:05 UTC, 73 minutes before detection.
- EV-001 (LOG, LOG-SETTLE-20260212-01): 40 ERROR log line(s) of type DeserializationError between 21:58 and 00:09 UTC, the first 20 minutes before detection. Example: "Failed to deserialize record at settlement-events-4 offset 1883201: schema id 412 field 'amount' cannot be converted from string to decimal (retry 1)"
- EV-003 (LOG, LOG-SETTLE-20260212-04): 12 WARN log line(s) of type ConsumerLag between 22:03 and 23:54 UTC, the first 15 minutes before detection. Example: "Consumer lag on settlement-events: 4,200 records"
- EV-004 (LOG, LOG-SETTLE-20260212-08): 10 WARN log line(s) of type ConsumerRebalance between 22:07 and 23:59 UTC, the first 11 minutes before detection. Example: "Revoking previously assigned partitions [settlement-events-4]"

**Statements:**

- YES: The schema change that made "amount" a string caused deserialization failures. (The context states the schema change made "amount" a string and the deserialization errors report that the field 'amount' cannot be converted from string to decimal, indicating the change caused the failures.)
- NO: The deserialization failures led to consumer lag and rebalancing. (Although lag and rebalance warnings occur after the deserialization errors, the context does not explicitly state that the failures caused them, so the causation cannot be directly inferred.)
- YES: The schema change at 21:05 UTC (EV-005) preceded deserialization errors (EV-001). (EV-005 is recorded at 21:05 UTC, while EV-001 errors occur between 21:58 and 00:09 UTC, showing the change happened before the errors.)
- YES: Deserialization errors (EV-001) directly indicate a type mismatch. (The error example explicitly says the field 'amount' cannot be converted from string to decimal, which is a type mismatch.)
- NO: Lag and rebalance warnings (EV-003, EV-004) are typical consequences of deserialization failures. (The context lists lag and rebalance warnings but does not state they are consequences of the deserialization failures, so this cannot be directly inferred.)

## RCA-2026-00029 / INC-2026-00106 / HYP-001: 0.83

**Hypothesis:** Missing composite index (account_id, billing_period) on invoice_lines causing full table scans and timeouts during month‑end aggregation Full table scans indicated by QueryPlanFullScan warnings (EV-002) High CPU on DB during aggregation (EV-003) StatementTimeouts during aggregation (EV-001) Historical RCA identified index drop as root cause (EV-009) Similar incidents with timeouts and CPU spikes (EV-010, EV-011)

**Cited evidence:**

- EV-002 (LOG, LOG-BILL-20260630-02): 8 WARN log line(s) of type QueryPlanFullScan between 22:05 and 23:47 UTC, the first 45 minutes before detection. Example: "duration: 5,359 ms plan: Seq Scan on invoice_lines (cost=0.00..1843201.12 rows=1284112) Filter: (billing_period = '2026-06')"
- EV-003 (LOG, LOG-BILL-20260630-04): 8 WARN log line(s) of type DbCpuHigh between 22:20 and 01:27 UTC, the first 30 minutes before detection. Example: "billing-postgresql CPU 93%"
- EV-001 (LOG, LOG-BILL-20260630-07): 25 ERROR log line(s) of type StatementTimeout between 22:31 and 01:39 UTC, the first 19 minutes before detection. Example: "canceling statement due to statement timeout: SELECT account_id, SUM(amount) FROM invoice_lines WHERE billing_period = $1 GROUP BY account_id"
- EV-009 (HISTORICAL_RCA, RCA-2025-00230): Past RCA RCA-2025-00230 for Billing Service, completed 2025-06-20. Summary: The month-end invoice aggregation ran for hours and timed out two months in a row, delaying the finance reports.
Root Cause: An ORM migration dropped the composite index (account_id, billing_period) on invoice_lines. The month-end aggregation filters by billing period, so every run scanned the whole table. Judged relevant because: Same service (Billing Service) and describes month‑end invoice aggregation timing out, matching the investigation symptoms.
- EV-010 (HISTORICAL_INCIDENT, INC-2025-00548): Past Billing Service incident INC-2025-00548, detected 2025-05-30: Finance reports late after month-end run. The month-end aggregation did not complete before the morning and reports were published late. Symptoms: Aggregation backlog; Invoice query timeouts. Judged similar because: Billing Service incident with month‑end aggregation not completing before morning, matching timeout symptom.
- EV-011 (HISTORICAL_INCIDENT, INC-2025-00512): Past Billing Service incident INC-2025-00512, detected 2025-04-30: Month-end invoice report processing slows. The month-end invoice run took more than three hours and the finance reports were late. Symptoms: Invoice query timeouts; Database CPU spike. Judged similar because: Billing Service incident with month‑end invoice run taking >3 hours, matching timeout symptom.
- EV-004 (CHANGE, CHG-2026-00790): Deploy Billing Service v2.31.0 on CI-BILLING-APP: Release: new wording in invoice e-mails and a PDF footer change. Implemented at 18:10 UTC, 280 minutes before detection.

**Statements:**

- YES: A missing composite index on the invoice_lines table for columns account_id and billing_period caused full table scans and timeouts during month‑end aggregation. (The RCA (EV-009) explicitly states that dropping the composite index caused whole‑table scans, and the logs (EV-001) show statement timeouts during the same aggregation period.)
- YES: Full table scans were indicated by QueryPlanFullScan warnings (EV-002). (EV-002 logs are of type QueryPlanFullScan and the example shows a sequential scan on invoice_lines, directly indicating full table scans.)
- NO: High CPU usage on the database occurred during aggregation (EV-003). (EV-003 records high CPU warnings, but the context does not explicitly link these warnings to the aggregation process.)
- YES: Statement timeouts occurred during aggregation (EV-001). (EV-001 logs statement timeouts for a query that aggregates invoice data, directly showing timeouts during the aggregation.)
- YES: Historical root cause analysis identified that an index drop was the root cause (EV-009). (EV-009 explicitly states that the dropped composite index was the root cause of the issue.)
- YES: Similar incidents exhibited timeouts and CPU spikes (EV-010, EV-011). (Both EV-010 and EV-011 describe past incidents with invoice query timeouts and, for EV-011, a database CPU spike.)

## RCA-2026-00029 / INC-2026-00106 / HYP-002: 0.17

**Hypothesis:** Recent deployment of Billing Service v2.31.0 introduced changes that increased query load or altered query logic, leading to timeouts during month‑end aggregation Deployment occurred before the first timeout (EV-004) Timeouts and CPU spikes coincide with deployment timing (EV-001, EV-003) QueryPlanFullScan warnings suggest heavier queries (EV-002)

**Cited evidence:**

- EV-004 (CHANGE, CHG-2026-00790): Deploy Billing Service v2.31.0 on CI-BILLING-APP: Release: new wording in invoice e-mails and a PDF footer change. Implemented at 18:10 UTC, 280 minutes before detection.
- EV-001 (LOG, LOG-BILL-20260630-07): 25 ERROR log line(s) of type StatementTimeout between 22:31 and 01:39 UTC, the first 19 minutes before detection. Example: "canceling statement due to statement timeout: SELECT account_id, SUM(amount) FROM invoice_lines WHERE billing_period = $1 GROUP BY account_id"
- EV-002 (LOG, LOG-BILL-20260630-02): 8 WARN log line(s) of type QueryPlanFullScan between 22:05 and 23:47 UTC, the first 45 minutes before detection. Example: "duration: 5,359 ms plan: Seq Scan on invoice_lines (cost=0.00..1843201.12 rows=1284112) Filter: (billing_period = '2026-06')"
- EV-003 (LOG, LOG-BILL-20260630-04): 8 WARN log line(s) of type DbCpuHigh between 22:20 and 01:27 UTC, the first 30 minutes before detection. Example: "billing-postgresql CPU 93%"

**Statements:**

- NO: The recent deployment of Billing Service v2.31.0 introduced changes that increased query load. (The deployment description only mentions new wording in invoice e‑mails and a PDF footer change; it does not mention any changes affecting query load.)
- NO: The recent deployment of Billing Service v2.31.0 introduced changes that altered query logic. (The context provides no information about alterations to query logic in the deployment.)
- NO: The increased query load and altered query logic led to timeouts during month‑end aggregation. (While timeouts (EV-001) and warnings (EV-002, EV-003) are reported, the context does not explicitly link them to increased query load or altered query logic.)
- NO: The deployment occurred before the first timeout identified as EV-004. (EV-004 is a change event, not a timeout; the first timeout is EV-001, which indeed occurs after the deployment, making the statement inaccurate.)
- NO: Timeouts and CPU spikes coincide with the deployment timing identified as EV-001 and EV-003. (The deployment happened at 18:10 UTC, whereas the timeouts (EV-001) and CPU spikes (EV-003) occurred later (starting around 22:20 UTC), so they do not coincide.)
- YES: QueryPlanFullScan warnings suggest heavier queries, as indicated by EV-002. (EV-002 reports QueryPlanFullScan warnings with long durations and sequential scans, which reasonably imply heavier queries.)

## RCA-2026-00030 / INC-2026-00107 / HYP-001: 1.00

**Hypothesis:** RabbitMQ broker disk space exhaustion caused publisher blocks and queue backlog during the campaign. DiskAlarm and DiskUsageHigh evidence indicate disk usage approaching limits before errors PublisherBlocked errors directly follow disk alarms Historical RCA (RCA-2025-00390) links disk exhaustion to publisher blocks during a campaign CMDB dependencies confirm notif-worker connects to RabbitMQ broker

**Cited evidence:**

- EV-002 (LOG, LOG-NOTIF-20260319-03): 3 ERROR log line(s) of type DiskAlarm between 02:18 and 02:19 UTC, the first 7 minutes before detection. Example: "disk resource limit alarm set on node rabbit@rabbitmq-prod-02. Free bytes: 48.2MB, limit: 50MB"
- EV-004 (LOG, LOG-NOTIF-20260319-01): 1 WARN log line(s) of type DiskUsageHigh between 00:35 and 00:35 UTC, the first 109 minutes before detection. Example: "Disk usage on / is 96% (/var/log/rabbitmq 36GB)"
- EV-001 (LOG, LOG-NOTIF-20260319-06): 20 ERROR log line(s) of type PublisherBlocked between 02:19 and 03:35 UTC, the first 5 minutes before detection. Example: "connection.blocked: publisher notification-worker blocked by resource alarm"
- EV-003 (LOG, LOG-NOTIF-20260319-08): 8 WARN log line(s) of type QueueDepth between 02:22 and 03:28 UTC, the first 3 minutes before detection. Example: "Queue notifications.outbound depth 12,000"
- EV-011 (HISTORICAL_RCA, RCA-2025-00390): Past RCA RCA-2025-00390 for Notification Service, completed 2026-01-09. Summary: Notification delivery stopped during the Christmas campaign because the RabbitMQ broker blocked all publishers after its disk filled up.
Root Cause: The broker host had been rebuilt by hand without log rotation for /var/log/rabbitmq. Broker logs grew until the disk passed the RabbitMQ free space limit and the broker blocked publishers. Judged relevant because: Service is Notification Service and describes delivery stoppage and queue backlog during a campaign, matching the investigation symptoms.
- EV-006 (CMDB, CI-NOTIF-BROKER-HOST): notification-rabbitmq (CI-NOTIF-MQ) hosted_on rabbitmq-prod-hosts (CI-NOTIF-BROKER-HOST, host).
- EV-007 (CMDB, CI-NOTIF-MQ): notification-worker (CI-NOTIF-WORKER) connects_to notification-rabbitmq (CI-NOTIF-MQ, queue).

**Statements:**

- YES: RabbitMQ broker disk space exhaustion caused publisher blocks during the campaign. (The historical RCA explicitly states that the broker blocked all publishers after its disk filled up during the Christmas campaign, and the log shows DiskAlarm followed by PublisherBlocked errors.)
- YES: RabbitMQ broker disk space exhaustion caused queue backlog during the campaign. (The RCA notes a queue backlog as a symptom and attributes it to the broker blocking publishers caused by disk exhaustion during the campaign.)
- YES: DiskAlarm evidence indicates disk usage approaching limits before errors. (The DiskAlarm log example shows free bytes of 48.2 MB against a limit of 50 MB, indicating the disk was near its limit before the error.)
- YES: DiskUsageHigh evidence indicates disk usage approaching limits before errors. (The DiskUsageHigh log reports 96% disk usage (36 GB of /var/log/rabbitmq), demonstrating usage close to the limit prior to errors.)
- YES: PublisherBlocked errors directly follow disk alarms. (DiskAlarm events occurred between 02:18‑02:19 UTC, and PublisherBlocked errors started at 02:19 UTC, showing a direct temporal succession.)
- YES: Historical RCA (RCA-2025-00390) links disk exhaustion to publisher blocks during a campaign. (The RCA summary explicitly links disk space exhaustion to the broker blocking all publishers during the Christmas campaign.)
- YES: CMDB dependencies confirm that notif-worker connects to RabbitMQ broker. (The CMDB entry (EV-007) states that notification‑worker connects_to notification‑rabbitmq, confirming the dependency.)

## RCA-2026-00030 / INC-2026-00107 / HYP-002: 0.20

**Hypothesis:** The large APAC spring campaign load caused resource limits to be hit, leading to publisher blocks and queue backlog. Campaign launch 30 minutes before first error suggests load increase PublisherBlocked and QueueDepth warnings coincide with campaign start Historical RCA (RCA-2025-00390) notes backlog during a campaign CMDB shows notif-worker connects to RabbitMQ and external providers

**Cited evidence:**

- EV-005 (CHANGE, CHG-2026-00341): Start APAC spring campaign send schedule on CI-NOTIF-WORKER: Enable the send schedule of the spring_apac campaign (1.8 million recipients). Implemented at 01:55 UTC, 30 minutes before detection.
- EV-001 (LOG, LOG-NOTIF-20260319-06): 20 ERROR log line(s) of type PublisherBlocked between 02:19 and 03:35 UTC, the first 5 minutes before detection. Example: "connection.blocked: publisher notification-worker blocked by resource alarm"
- EV-003 (LOG, LOG-NOTIF-20260319-08): 8 WARN log line(s) of type QueueDepth between 02:22 and 03:28 UTC, the first 3 minutes before detection. Example: "Queue notifications.outbound depth 12,000"
- EV-011 (HISTORICAL_RCA, RCA-2025-00390): Past RCA RCA-2025-00390 for Notification Service, completed 2026-01-09. Summary: Notification delivery stopped during the Christmas campaign because the RabbitMQ broker blocked all publishers after its disk filled up.
Root Cause: The broker host had been rebuilt by hand without log rotation for /var/log/rabbitmq. Broker logs grew until the disk passed the RabbitMQ free space limit and the broker blocked publishers. Judged relevant because: Service is Notification Service and describes delivery stoppage and queue backlog during a campaign, matching the investigation symptoms.
- EV-006 (CMDB, CI-NOTIF-BROKER-HOST): notification-rabbitmq (CI-NOTIF-MQ) hosted_on rabbitmq-prod-hosts (CI-NOTIF-BROKER-HOST, host).
- EV-007 (CMDB, CI-NOTIF-MQ): notification-worker (CI-NOTIF-WORKER) connects_to notification-rabbitmq (CI-NOTIF-MQ, queue).
- EV-002 (LOG, LOG-NOTIF-20260319-03): 3 ERROR log line(s) of type DiskAlarm between 02:18 and 02:19 UTC, the first 7 minutes before detection. Example: "disk resource limit alarm set on node rabbit@rabbitmq-prod-02. Free bytes: 48.2MB, limit: 50MB"
- EV-004 (LOG, LOG-NOTIF-20260319-01): 1 WARN log line(s) of type DiskUsageHigh between 00:35 and 00:35 UTC, the first 109 minutes before detection. Example: "Disk usage on / is 96% (/var/log/rabbitmq 36GB)"

**Statements:**

- NO: The large APAC spring campaign load caused resource limits to be hit. (The context mentions the campaign start and later resource‑limit alarms, but does not explicitly state that the campaign load caused the limits.)
- NO: The hit resource limits led to publisher blocks. (DiskAlarm (resource limit) and PublisherBlocked errors are both reported, yet the context does not directly link the limits to the publisher blocks.)
- NO: The hit resource limits led to a queue backlog. (QueueDepth warnings appear after the resource‑limit alarms, but the context does not explicitly connect the limits to the backlog.)
- NO: The campaign launch occurred 30 minutes before the first error. (The campaign started at 01:55 UTC and the earliest error (DiskAlarm) occurred at 02:18 UTC, which is about 23 minutes later, not 30 minutes.)
- NO: The campaign launch suggests a load increase. (The context describes a campaign of 1.8 million recipients but does not explicitly state that this implies a load increase.)
- NO: PublisherBlocked warnings coincided with the campaign start. (PublisherBlocked errors began at 02:19 UTC, while the campaign started at 01:55 UTC, so they did not coincide.)
- NO: QueueDepth warnings coincided with the campaign start. (QueueDepth warnings began at 02:22 UTC, well after the campaign start at 01:55 UTC.)
- YES: Historical RCA (RCA-2025-00390) notes a backlog during a campaign. (The RCA summary explicitly mentions a queue backlog occurring during the Christmas campaign.)
- YES: CMDB shows that notif-worker connects to RabbitMQ. (EV-007 states that notification‑worker connects_to notification‑rabbitmq.)
- NO: CMDB shows that notif-worker connects to external providers. (The CMDB entries only describe connections between notif‑worker and the RabbitMQ broker; no external provider connections are mentioned.)

## RCA-2026-00031 / INC-2026-00108 / HYP-001: 0.43

**Hypothesis:** Memory limit set too low by the Helm chart upgrade to the 'small' resource profile, causing OOM under traffic surge. Helm chart upgrade applied small resource profile before incident OOMKilled and high heap usage logs indicate memory exhaustion Traffic surge increased load

**Cited evidence:**

- EV-005 (CHANGE, CHG-2026-00412): Deploy auth-service Helm chart 5.2.0 on CI-AUTH-APP: Chart upgrade: the standard resource profile 'small' is applied to all IAM workloads. Implemented at 09:40 UTC, 150 minutes before detection.
- EV-001 (LOG, LOG-AUTH-20260404-07): 18 ERROR log line(s) of type OOMKilled between 11:58 and 12:47 UTC, the first 12 minutes before detection. Example: "Container auth-service in pod auth-service-7d9f-58733 OOMKilled (exit code 137), restart count 1"
- EV-003 (LOG, LOG-AUTH-20260404-05): 10 WARN log line(s) of type HeapUsageHigh between 11:40 and 12:39 UTC, the first 30 minutes before detection. Example: "JVM heap usage 99% of max 192MB"
- EV-004 (LOG, LOG-AUTH-20260404-02): 4 WARN log line(s) of type TrafficSurge between 11:30 and 12:29 UTC, the first 40 minutes before detection. Example: "Login request rate 2.1x baseline (Easter campaign)"

**Statements:**

- NO: The Helm chart upgrade set the memory limit to the 'small' resource profile. (The context says the upgrade applied the standard resource profile 'small' but does not explicitly mention setting a memory limit.)
- NO: The memory limit was set too low. (No information about the adequacy of the memory limit is provided in the context.)
- NO: The low memory limit caused an out-of-memory (OOM) condition during a traffic surge. (Although OOMKilled and traffic surge logs are present, the context does not link a low memory limit as the cause of the OOM condition.)
- YES: The Helm chart upgrade applied the small resource profile before the incident. (The upgrade was implemented at 09:40 UTC, which is earlier than the first logged events (traffic surge at 11:30 UTC), so it occurred before the incident.)
- YES: The incident resulted in an OOMKilled event. (The context records OOMKilled log lines during the incident period, indicating that an OOMKilled event occurred.)
- NO: High heap usage logs indicate memory exhaustion. (The context reports high heap usage warnings but does not state that they indicate memory exhaustion.)
- YES: A traffic surge increased the load. (WARN logs of type TrafficSurge show a login request rate increase, directly indicating a load increase.)

## RCA-2026-00031 / INC-2026-00108 / HYP-002: 1.00

**Hypothesis:** Unbounded token introspection cache grew during traffic surge, exhausting JVM heap and causing OOM. Historical RCA identified cache size limit as root cause in similar incident High heap usage and OOMKilled logs align with cache growth Traffic surge would trigger more cache entries

**Cited evidence:**

- EV-012 (HISTORICAL_RCA, RCA-2025-00305): Past RCA RCA-2025-00305 for Auth Service, completed 2025-10-24. Summary: Auth Service pods were killed for memory during a traffic peak and part of the logins failed.
Root Cause: The token introspection cache had no size limit. Under high load it grew until the JVM heap was full and the pods were killed. Judged relevant because: Matches Auth Service pods killed for memory during traffic peak and login failures, aligning with search queries about pods restart during traffic spike and OOMKilled.
- EV-001 (LOG, LOG-AUTH-20260404-07): 18 ERROR log line(s) of type OOMKilled between 11:58 and 12:47 UTC, the first 12 minutes before detection. Example: "Container auth-service in pod auth-service-7d9f-58733 OOMKilled (exit code 137), restart count 1"
- EV-003 (LOG, LOG-AUTH-20260404-05): 10 WARN log line(s) of type HeapUsageHigh between 11:40 and 12:39 UTC, the first 30 minutes before detection. Example: "JVM heap usage 99% of max 192MB"
- EV-004 (LOG, LOG-AUTH-20260404-02): 4 WARN log line(s) of type TrafficSurge between 11:30 and 12:29 UTC, the first 40 minutes before detection. Example: "Login request rate 2.1x baseline (Easter campaign)"

**Statements:**

- YES: Unbounded token introspection cache grew during traffic surge. (The root cause description states the token introspection cache had no size limit and grew under high load during a traffic peak.)
- YES: The growth exhausted the JVM heap. (The context says the cache grew until the JVM heap was full, indicating exhaustion of the heap.)
- YES: The exhaustion caused an out-of-memory (OOM) condition. (Full JVM heap led to pods being killed for memory and OOMKilled log entries, showing an OOM condition.)
- YES: Historical root cause analysis identified the cache size limit as the root cause in a similar incident. (The historical RCA explicitly identifies the unbounded token introspection cache as the root cause.)
- YES: High heap usage logs and OOMKilled logs align with cache growth. (The high heap usage (WARN) and OOMKilled (ERROR) logs correspond to the period when the cache grew and exhausted memory.)
- YES: Traffic surge would trigger more cache entries. (The cache grew under high load caused by a traffic surge, implying that the surge generated additional cache entries.)

## RCA-2026-00032 / INC-2026-00109 / HYP-001: 0.60

**Hypothesis:** coredns service is misbehaving or overloaded, causing DNS resolution failures for reporting-batch EV-001 shows DNS timeouts for ledger-api.internal EV-002 shows task retries triggered by DNS errors EV-003 confirms reporting-batch depends on coredns

**Cited evidence:**

- EV-001 (LOG, LOG-REP-20260115-02): 30 ERROR log line(s) of type DnsTimeout between 05:00 and 05:48 UTC, the first 17 minutes before detection. Example: "lookup ledger-api.internal on 10.96.0.10:53: server misbehaving"
- EV-002 (LOG, LOG-REP-20260115-04): 15 WARN log line(s) of type TaskRetry between 05:02 and 05:41 UTC, the first 16 minutes before detection. Example: "Retrying task extract_ledger (attempt 36/5) after DNS error"
- EV-003 (CMDB, CI-COREDNS): reporting-batch (CI-REP-APP) connects_to coredns (CI-COREDNS, application).

**Statements:**

- NO: The coredns service is misbehaving or overloaded. (The context mentions a server misbehaving in EV-001 but does not identify it as the coredns service.)
- NO: The coredns service is causing DNS resolution failures for reporting-batch. (While EV-001 and EV-002 describe DNS timeouts and retries, the context does not directly link these failures to the reporting-batch service.)
- YES: Evidence EV-001 shows DNS timeouts for ledger-api.internal. (EV-001 includes the example "lookup ledger-api.internal on 10.96.0.10:53: server misbehaving", indicating DNS timeouts for that host.)
- YES: Evidence EV-002 shows task retries triggered by DNS errors. (EV-002's example explicitly states "Retrying task extract_ledger ... after DNS error", confirming retries due to DNS errors.)
- YES: Evidence EV-003 confirms that reporting-batch depends on coredns. (EV-003 states that reporting-batch connects_to coredns, indicating a dependency.)

## RCA-2026-00032 / INC-2026-00109 / HYP-002: 0.33

**Hypothesis:** network connectivity issue between reporting-batch and coredns caused DNS resolution failures EV-001 indicates DNS timeouts EV-003 shows dependency path that could be affected by network problems

**Cited evidence:**

- EV-001 (LOG, LOG-REP-20260115-02): 30 ERROR log line(s) of type DnsTimeout between 05:00 and 05:48 UTC, the first 17 minutes before detection. Example: "lookup ledger-api.internal on 10.96.0.10:53: server misbehaving"
- EV-003 (CMDB, CI-COREDNS): reporting-batch (CI-REP-APP) connects_to coredns (CI-COREDNS, application).

**Statements:**

- NO: The network connectivity issue between reporting-batch and coredns caused DNS resolution failures. (The context mentions DNS timeouts and that reporting-batch connects to coredns, but does not explicitly state that a network connectivity issue caused the DNS failures.)
- YES: EV-001 indicates DNS timeouts. (EV-001 is described as containing log lines of type DnsTimeout, directly indicating DNS timeouts.)
- NO: EV-003 shows a dependency path that could be affected by network problems. (The context shows that reporting-batch connects to coredns, indicating a dependency, but it does not mention any potential impact from network problems.)

## RCA-2026-00033 / INC-2026-00110 / HYP-001: 0.67

**Hypothesis:** The contract update reused a protobuf field number that was previously assigned to a different type, causing the API gateway to misinterpret the new field and generate ContractMismatch errors. EV-003 shows the change added a new field at 07:40 UTC EV-001 records ContractMismatch errors shortly after the change EV-002 records SchemaVersionMismatch warnings indicating descriptor mismatch EV-007 past RCA documented a similar field number reuse causing wrong values

**Cited evidence:**

- EV-003 (CHANGE, CHG-2026-00712): Deploy User Profile v3.2 on CI-USER-PROFILE-APP: Deploy the user profile contract update: new preferred_language field in profile.proto. Implemented at 07:40 UTC, 35 minutes before detection.
- EV-001 (LOG, LOG-USER-20260522-03): 25 ERROR log line(s) of type ContractMismatch between 07:52 and 09:04 UTC, the first 23 minutes before detection. Example: "Response for GET /v1/profile/42120 rejected by api-gateway transcoder: wire type mismatch for field 7 (expected string, got varint)"
- EV-002 (LOG, LOG-USER-20260522-01): 2 WARN log line(s) of type SchemaVersionMismatch between 07:45 and 07:45 UTC, the first 30 minutes before detection. Example: "Serving profile.proto v3.2 (descriptor 9f1c2a); api-gateway transcoder reports v3.1 (descriptor 71be04)"
- EV-007 (HISTORICAL_RCA, RCA-2025-00012): Past RCA RCA-2025-00012 for User Profile Service, completed 2025-06-05. Summary: After a profile contract update, the API gateway decoded some profile fields with the wrong type and customers saw empty or wrong values.
Root Cause: Contract v2.7 reused protobuf field number 5 of a removed field for a new field of a different type. The gateway still used the old descriptor and decoded the new field wrongly. Judged relevant because: Same service (User Profile Service) and symptoms of wrong values after contract update match the investigation.

**Statements:**

- NO: The contract update reused a protobuf field number that was previously assigned to a different type. (The context does not state that the current contract update reused a protobuf field number; the reuse is only mentioned in the past RCA.)
- NO: The reuse caused the API gateway to misinterpret the new field and generate ContractMismatch errors. (The context does not link the reuse to the ContractMismatch errors; it only notes that ContractMismatch errors occurred after the change.)
- YES: EV-003 shows that the change added a new field at 07:40 UTC. (EV-003 indicates the contract update added a new preferred_language field and was implemented at 07:40 UTC.)
- YES: EV-001 records ContractMismatch errors shortly after the change. (EV-001 logs ContractMismatch errors between 07:52 and 09:04 UTC, which is shortly after the 07:40 UTC change.)
- YES: EV-002 records SchemaVersionMismatch warnings indicating a descriptor mismatch. (EV-002 logs SchemaVersionMismatch warnings and the example shows a descriptor mismatch between profile.proto v3.2 and the gateway's v3.1.)
- YES: The past RCA documented in EV-007 described a similar field number reuse that caused wrong values. (EV-007's RCA describes a past incident where reusing a protobuf field number caused wrong values.)

## RCA-2026-00033 / INC-2026-00110 / HYP-002: 0.83

**Hypothesis:** The API gateway transcoder was not updated to the new descriptor after the contract change, leading to a mismatch between the service and gateway. EV-003 shows the change at 07:40 UTC EV-001 shows errors after the change EV-002 shows schema version mismatch warnings No evidence indicates the gateway was updated to v3.2

**Cited evidence:**

- EV-003 (CHANGE, CHG-2026-00712): Deploy User Profile v3.2 on CI-USER-PROFILE-APP: Deploy the user profile contract update: new preferred_language field in profile.proto. Implemented at 07:40 UTC, 35 minutes before detection.
- EV-001 (LOG, LOG-USER-20260522-03): 25 ERROR log line(s) of type ContractMismatch between 07:52 and 09:04 UTC, the first 23 minutes before detection. Example: "Response for GET /v1/profile/42120 rejected by api-gateway transcoder: wire type mismatch for field 7 (expected string, got varint)"
- EV-002 (LOG, LOG-USER-20260522-01): 2 WARN log line(s) of type SchemaVersionMismatch between 07:45 and 07:45 UTC, the first 30 minutes before detection. Example: "Serving profile.proto v3.2 (descriptor 9f1c2a); api-gateway transcoder reports v3.1 (descriptor 71be04)"

**Statements:**

- YES: The API gateway transcoder was not updated to the new descriptor after the contract change. (EV-002 log indicates the gateway reports descriptor v3.1 while the service serves v3.2, showing the gateway was not updated.)
- NO: The lack of update caused a mismatch between the service and the gateway. (While the context shows a version mismatch and missing update, it does not explicitly state that the lack of update caused the mismatch.)
- YES: EV-003 shows the change at 07:40 UTC. (EV-003 entry states the change was implemented at 07:40 UTC.)
- YES: EV-001 shows errors after the change. (EV-001 logs occur between 07:52 and 09:04 UTC, which is after the 07:40 UTC change.)
- YES: EV-002 shows schema version mismatch warnings. (EV-002 entry records WARN log lines of type SchemaVersionMismatch.)
- YES: No evidence indicates that the gateway was updated to version 3.2. (The only version information is that the gateway reports v3.1; there is no evidence of an update to v3.2.)

## RCA-2026-00034 / INC-2026-00468 / HYP-001: 0.29

**Hypothesis:** The addition of the 'settlement_date' field in the webhook payload caused the payload to exceed size limits or trigger serialization errors, leading to egress proxy timeouts and webhook delivery failures. Change introduced new field before errors Errors are timeouts at egress proxy Backlog warnings indicate many messages queued

**Cited evidence:**

- EV-003 (CHANGE, CHG-2026-01102): Deploy Payment API v4.21.0 on CI-PAYMENT-API: Release: merchant dashboard exports and a new 'settlement_date' field in the webhook payload. Implemented at 09:45 UTC, 35 minutes before detection.
- EV-001 (LOG, LOG-PAY-20260908-01): 40 ERROR log line(s) of type WebhookDeliveryFailed between 09:02 and 13:10 UTC, the first 78 minutes before detection. Example: "Webhook delivery via relay hooks.relaypartner.example failed: connect timed out after 10000ms (egress-proxy 10.40.2.15)"
- EV-002 (LOG, LOG-PAY-20260908-04): 10 WARN log line(s) of type WebhookRetryBacklog between 09:30 and 12:22 UTC, the first 50 minutes before detection. Example: "Webhook retry backlog 800 messages, oldest 2,125 seconds"

**Statements:**

- NO: The addition of the "settlement_date" field in the webhook payload caused the payload to exceed size limits. (The context does not mention any payload size limits or that the new field caused the payload to exceed them.)
- NO: The addition of the "settlement_date" field in the webhook payload triggered serialization errors. (No information about serialization errors is provided in the context.)
- NO: The payload exceeding size limits and serialization errors led to egress proxy timeouts. (The context gives no evidence of size limit or serialization errors, so this causal link cannot be inferred.)
- NO: The payload exceeding size limits and serialization errors led to webhook delivery failures. (There is no mention of size limits or serialization errors in the context, thus the statement cannot be inferred.)
- NO: The change introduced the "settlement_date" field before errors occurred. (Errors (WebhookDeliveryFailed) began at 09:02 UTC, which is before the change was implemented at 09:45 UTC, so the statement is not supported.)
- YES: Errors are timeouts at the egress proxy. (The error example explicitly describes a timeout at the egress proxy (connect timed out after 10000ms).)
- YES: Backlog warnings indicate that many messages are queued. (The warning example mentions a retry backlog of 800 messages, indicating a large queue.)

## RCA-2026-00034 / INC-2026-00468 / HYP-002: 0.17

**Hypothesis:** The deployment introduced a regression in the webhook retry logic, causing increased retry backlog and eventual delivery failures. Change occurred before errors Backlog warnings indicate retry queue growth Similar symptoms in past incidents

**Cited evidence:**

- EV-003 (CHANGE, CHG-2026-01102): Deploy Payment API v4.21.0 on CI-PAYMENT-API: Release: merchant dashboard exports and a new 'settlement_date' field in the webhook payload. Implemented at 09:45 UTC, 35 minutes before detection.
- EV-001 (LOG, LOG-PAY-20260908-01): 40 ERROR log line(s) of type WebhookDeliveryFailed between 09:02 and 13:10 UTC, the first 78 minutes before detection. Example: "Webhook delivery via relay hooks.relaypartner.example failed: connect timed out after 10000ms (egress-proxy 10.40.2.15)"
- EV-002 (LOG, LOG-PAY-20260908-04): 10 WARN log line(s) of type WebhookRetryBacklog between 09:30 and 12:22 UTC, the first 50 minutes before detection. Example: "Webhook retry backlog 800 messages, oldest 2,125 seconds"

**Statements:**

- NO: The deployment introduced a regression in the webhook retry logic. (The context describes the deployment details but does not mention any regression in the webhook retry logic.)
- NO: The regression caused an increased retry backlog. (No regression is mentioned in the context, so a causal link to the backlog cannot be inferred.)
- NO: The regression caused eventual delivery failures. (The context provides no evidence of a regression, thus it cannot be linked to delivery failures.)
- NO: The change occurred before the errors. (Errors of type WebhookDeliveryFailed occurred starting at 09:02 UTC, which is before the deployment at 09:45 UTC, so the change did not occur before all errors.)
- YES: Backlog warnings indicate that the retry queue grew. (The WARN log lines describe a retry backlog of 800 messages, indicating that the retry queue increased in size.)
- NO: Similar symptoms were observed in past incidents. (The context does not reference any past incidents or similar symptoms.)

## RCA-2026-00035 / INC-2026-00449 / HYP-001: 0.43

**Hypothesis:** The CDN cache rule change adding a Vary: Cookie header caused cache misses for product pages, leading to increased origin load and upstream timeouts. The change was implemented 45 minutes before the first error and directly affects product page caching. Low CDN hit ratio and high origin load coincide with the timing of the change. UpstreamTimeout errors are consistent with origin overload due to cache misses.

**Cited evidence:**

- EV-005 (CHANGE, CHG-2026-01058): Update CDN cache rules for product pages on CI-PORTAL-CDN: Add 'Vary: Cookie' to /products/* responses so that logged-in customers see their own prices. Implemented at 18:20 UTC, 45 minutes before detection.
- EV-003 (LOG, LOG-PORTAL-20260826-01): 6 WARN log line(s) of type CdnHitRatioLow between 18:26 and 19:18 UTC, the first 39 minutes before detection. Example: "CDN cache hit ratio for /products/* 22% (baseline 94%)"
- EV-004 (LOG, LOG-PORTAL-20260826-04): 6 WARN log line(s) of type OriginLoadHigh between 18:40 and 19:30 UTC, the first 25 minutes before detection. Example: "Origin request rate 1,900 req/s (baseline 310)"
- EV-001 (LOG, LOG-PORTAL-20260826-08): 30 ERROR log line(s) of type UpstreamTimeout between 18:52 and 19:57 UTC, the first 13 minutes before detection. Example: "upstream request timeout after 8000ms on GET /products/18855"
- EV-006 (CHANGE, CHG-2026-01060): Customer Portal release 2026.08.4 on CI-PORTAL-WEB: Product page redesign with larger images and a new recommendations widget. Implemented at 18:35 UTC, 30 minutes before detection.

**Statements:**

- NO: The CDN cache rule change that added a Vary: Cookie header caused cache misses for product pages. (The context mentions the rule change and a low CDN hit ratio, but does not explicitly state that the change caused cache misses.)
- NO: The cache misses for product pages led to increased origin load and upstream timeouts. (The context reports low CDN hit ratio, high origin load, and upstream timeouts, but does not directly link cache misses as the cause of the latter events.)
- NO: The CDN cache rule change was implemented 45 minutes before the first error. (The change was implemented at 18:20 UTC and the first UpstreamTimeout error occurred at 18:52 UTC, a difference of 32 minutes, not 45 minutes.)
- YES: The CDN cache rule change directly affects product page caching. (The change updates CDN cache rules for /products/* responses, which directly modifies how product pages are cached.)
- YES: The low CDN hit ratio coincided with the timing of the CDN cache rule change. (The low CDN hit ratio was logged starting at 18:26 UTC, shortly after the rule change at 18:20 UTC, indicating temporal coincidence.)
- YES: The high origin load coincided with the timing of the CDN cache rule change. (The high origin load was logged between 18:40 and 19:30 UTC, overlapping with the period after the 18:20 UTC rule change.)
- NO: UpstreamTimeout errors are consistent with origin overload caused by cache misses. (The context shows upstream timeouts and high origin load but does not explicitly state that the timeouts are due to origin overload from cache misses.)

## RCA-2026-00035 / INC-2026-00449 / HYP-002: 0.18

**Hypothesis:** The portal redesign added larger images and a new recommendations widget, increasing payload size and origin load, which caused upstream timeouts. The redesign was implemented 30 minutes before the first error and introduced heavier content. High origin request rate and UpstreamTimeout errors align with increased payloads. Historical incidents with similar symptoms occurred without this redesign, suggesting a new factor.

**Cited evidence:**

- EV-006 (CHANGE, CHG-2026-01060): Customer Portal release 2026.08.4 on CI-PORTAL-WEB: Product page redesign with larger images and a new recommendations widget. Implemented at 18:35 UTC, 30 minutes before detection.
- EV-004 (LOG, LOG-PORTAL-20260826-04): 6 WARN log line(s) of type OriginLoadHigh between 18:40 and 19:30 UTC, the first 25 minutes before detection. Example: "Origin request rate 1,900 req/s (baseline 310)"
- EV-001 (LOG, LOG-PORTAL-20260826-08): 30 ERROR log line(s) of type UpstreamTimeout between 18:52 and 19:57 UTC, the first 13 minutes before detection. Example: "upstream request timeout after 8000ms on GET /products/18855"
- EV-003 (LOG, LOG-PORTAL-20260826-01): 6 WARN log line(s) of type CdnHitRatioLow between 18:26 and 19:18 UTC, the first 39 minutes before detection. Example: "CDN cache hit ratio for /products/* 22% (baseline 94%)"

**Statements:**

- YES: The portal redesign added larger images. (The context explicitly states that the redesign included larger images.)
- YES: The portal redesign added a new recommendations widget. (The context explicitly states that the redesign included a new recommendations widget.)
- NO: The portal redesign increased payload size. (The context does not mention payload size, so this cannot be inferred.)
- NO: The portal redesign increased origin load. (The context reports high origin load but does not attribute it to the redesign.)
- NO: The increased payload size and origin load caused upstream timeouts. (The context does not mention payload size nor causation between payload/origin load and upstream timeouts.)
- NO: The portal redesign was implemented 30 minutes before the first error. (The redesign was implemented at 18:35 UTC and the first upstream timeout error occurred at 18:52 UTC, which is 17 minutes later, not 30 minutes.)
- NO: The portal redesign introduced heavier content. (The context mentions larger images but does not use the term 'heavier content' nor directly state it.)
- NO: A high origin request rate aligned with increased payloads. (The context mentions a high origin request rate but does not mention increased payloads.)
- NO: UpstreamTimeout errors aligned with increased payloads. (The context mentions upstream timeout errors but does not mention increased payloads.)
- NO: Historical incidents with similar symptoms occurred without the portal redesign. (The context provides no information about historical incidents.)
- NO: The occurrence of historical incidents without the portal redesign suggests a new factor. (The context provides no information about historical incidents, so this cannot be inferred.)

## RCA-2026-00036 / INC-2026-00491 / HYP-001: 0.80

**Hypothesis:** Redis session store eviction due to memory pressure caused loss of active sessions Redis eviction warning (EV-002) occurred before session errors (EV-001) SessionNotFound errors (EV-001) indicate sessions missing in Redis Auth-service depends on session-store-redis (EV-008) Historical incidents (EV-009-EV-013) show similar symptoms linked to session store issues

**Cited evidence:**

- EV-002 (LOG, LOG-AUTH-20260915-01): 1 WARN log line(s) of type RedisEviction between 07:38 and 07:38 UTC, the first 27 minutes before detection. Example: "evicted_keys +48,210 in the last hour (policy allkeys-lru)"
- EV-001 (LOG, LOG-AUTH-20260915-03): 20 ERROR log line(s) of type SessionNotFound between 08:46 and 09:04 UTC, the first 41 minutes after detection. Example: "Session not found for refresh token (user U-12342); forcing re-login"
- EV-008 (CMDB, CI-SESSION-REDIS): auth-service (CI-AUTH-APP) connects_to session-store-redis (CI-SESSION-REDIS, cache).
- EV-009 (HISTORICAL_INCIDENT, INC-2026-00612): Past Auth Service incident INC-2026-00612, detected 2026-05-20: Users signed out unexpectedly. A group of users was signed out and had to log in again. Login itself worked. Symptoms: Session store connection errors; Forced re-login spike. Judged similar because: Matches Auth Service with session store connection errors and forced re-login spike.
- EV-010 (HISTORICAL_INCIDENT, INC-2026-00538): Past Auth Service incident INC-2026-00538, detected 2026-05-03: Users signed out unexpectedly. Customers reported being logged out in the middle of their session. Impact was limited to global. Symptoms: Session store connection errors; Forced re-login spike. Judged similar because: Matches Auth Service with session store connection errors and forced re-login spike.
- EV-011 (HISTORICAL_INCIDENT, INC-2025-01022): Past Auth Service incident INC-2025-01022, detected 2025-08-22: Users signed out unexpectedly. Customers reported being logged out in the middle of their session. Monitoring raised the alert before customers called. Symptoms: Session store connection errors; Forced re-login spike. Judged similar because: Matches Auth Service with session store connection errors and forced re-login spike.
- EV-012 (HISTORICAL_INCIDENT, INC-2024-00883): Past Auth Service incident INC-2024-00883, detected 2024-07-20: Users signed out unexpectedly. A group of users was signed out and had to log in again. Login itself worked. Impact was limited to eu-west-1. Symptoms: Session store connection errors; Forced re-login spike. Judged similar because: Matches Auth Service with session store connection errors and forced re-login spike.
- EV-013 (HISTORICAL_INCIDENT, INC-2025-01535): Past Auth Service incident INC-2025-01535, detected 2025-12-17: Active sessions lost for a group of users. Customers reported being logged out in the middle of their session. Monitoring raised the alert before customers called. Symptoms: Session store connection errors; Forced re-login spike. Judged similar because: Matches Auth Service with session store connection errors and forced re-login spike.

**Statements:**

- NO: Redis session store eviction due to memory pressure caused loss of active sessions. (The context mentions a Redis eviction warning and later SessionNotFound errors, but it does not explicitly state that the eviction caused loss of active sessions.)
- YES: Redis eviction warning (EV-002) occurred before session errors (EV-001). (EV-002 is timestamped at 07:38 UTC, while EV-001 occurs between 08:46 and 09:04 UTC, so the eviction warning happened earlier.)
- YES: SessionNotFound errors (EV-001) indicate sessions missing in Redis. (The EV-001 example shows "Session not found for refresh token" which implies the session could not be retrieved from the session store (Redis).)
- YES: Auth-service depends on session-store-redis (EV-008). (EV-008 explicitly states that auth-service connects_to session-store-redis.)
- YES: Historical incidents (EV-009-EV-013) show similar symptoms linked to session store issues. (Each historical incident (EV-009 to EV-013) describes symptoms of session store connection errors and forced re-login spikes, indicating a link to session store issues.)

## RCA-2026-00036 / INC-2026-00491 / HYP-002: 0.25

**Hypothesis:** Auth-service lost connectivity to session-store-redis due to network or service outage SessionNotFound errors (EV-001) could result from failed lookups Auth-service connects to session-store-redis (EV-008) Log pipeline gap (EV-003) may indicate service restart affecting connectivity

**Cited evidence:**

- EV-001 (LOG, LOG-AUTH-20260915-03): 20 ERROR log line(s) of type SessionNotFound between 08:46 and 09:04 UTC, the first 41 minutes after detection. Example: "Session not found for refresh token (user U-12342); forcing re-login"
- EV-008 (CMDB, CI-SESSION-REDIS): auth-service (CI-AUTH-APP) connects_to session-store-redis (CI-SESSION-REDIS, cache).
- EV-003 (LOG, LOG-AUTH-20260915-02): 1 WARN log line(s) of type LogPipelineGap between 08:45 and 08:45 UTC, the first 40 minutes after detection. Example: "fluent-bit recovered after restart loop: 18,402 records dropped between 07:40 and 08:45"
- EV-002 (LOG, LOG-AUTH-20260915-01): 1 WARN log line(s) of type RedisEviction between 07:38 and 07:38 UTC, the first 27 minutes before detection. Example: "evicted_keys +48,210 in the last hour (policy allkeys-lru)"

**Statements:**

- NO: Auth-service lost connectivity to session-store-redis due to a network or service outage. (The context only states that auth-service connects to session-store-redis; it does not mention any loss of connectivity or outage.)
- NO: SessionNotFound errors (EV-001) could result from failed lookups. (The context reports SessionNotFound errors but does not specify their cause; the possibility of failed lookups is not explicitly stated.)
- YES: Auth-service connects to session-store-redis (EV-008). (The context explicitly says "auth-service (CI-AUTH-APP) connects_to session-store-redis (CI-SESSION-REDIS, cache).")
- NO: Log pipeline gap (EV-003) may indicate a service restart affecting connectivity. (The context mentions a LogPipelineGap and a restart loop, but does not directly link it to connectivity issues; the statement is speculative.)
