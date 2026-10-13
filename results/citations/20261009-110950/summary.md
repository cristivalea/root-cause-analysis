# Citation trace (2026-10-09 11:09)

Stories traced: 5. No investigation for: STORY-006, STORY-007, STORY-008, STORY-009, STORY-010, STORY-011, STORY-012, STORY-013.

| Measure | Value |
|---|---|
| Expected citations in the ledger (preservation) | 21/22 |
| Expected citations cited by the main hypothesis (utilization) | 8/21 of those in the ledger |
| Ledger evidence the answer key names anywhere (precision) | 35/102 |
| Stories where the main hypothesis cites a red herring | 1/5 |

| Story | In ledger | Cited by main | Not in ledger | Red herrings cited by main |
|---|---|---|---|---|
| STORY-001 | 6/6 | 5/6 | - | RCA-2025-00042 |
| STORY-002 | 5/5 | 0/5 | - | - |
| STORY-003 | 4/4 | 0/4 | - | - |
| STORY-004 | 3/4 | 3/4 | LOG-GW-20260424-01 | - |
| STORY-005 | 3/3 | 0/3 | - | - |

```
STORY-001  (RCA-2026-00001, INC-2026-00101)
  LOG-PAYROLL-20260727-08    -> EV-011 CITED by the main hypothesis
  LOG-PAYROLL-20260727-07    -> EV-016 CITED by the main hypothesis
  RCA-2025-00042             -> EV-031 CITED by the main hypothesis
  CI-PAYROLL-DB              -> EV-024 CITED by the main hypothesis
  INC-2025-00119             -> EV-032 in the ledger, NOT CITED   <- lost here
  CHG-2026-00262             -> EV-017 CITED by the main hypothesis

STORY-002  (RCA-2026-00002, INC-2026-00857)
  LOG-PAY-20260714-14        -> EV-002 in the ledger, NOT CITED   <- lost here
  LOG-PAY-20260714-15        -> EV-003 in the ledger, NOT CITED   <- lost here
  CHG-2026-00871             -> EV-007 in the ledger, NOT CITED   <- lost here
  RCA-2025-00114             -> EV-013 in the ledger, NOT CITED   <- lost here
  CI-PAYMENT-DB              -> EV-010 in the ledger, NOT CITED   <- lost here

STORY-003  (RCA-2026-00003, INC-2026-00103)
  LOG-PORTAL-20260810-03     -> EV-002 in the ledger, NOT CITED   <- lost here
  LOG-PORTAL-20260810-02     -> EV-004 in the ledger, NOT CITED   <- lost here
  LOG-PORTAL-20260810-01     -> EV-005 in the ledger, NOT CITED   <- lost here
  CI-PORTAL-LOCK-REDIS       -> EV-010 in the ledger, NOT CITED   <- lost here

STORY-004  (RCA-2026-00004, INC-2026-00104)
  LOG-GW-20260501-01         -> EV-003 CITED by the main hypothesis
  LOG-GW-20260424-01                   NOT IN THE LEDGER: at 2026-04-24 00:05, outside the window(s) 2026-05-01 01:12 - 2026-05-01 04:12   <- lost here
  RCA-2024-00088             -> EV-012 CITED by the main hypothesis
  CI-CERT-MANAGER            -> EV-006 CITED by the main hypothesis

STORY-005  (RCA-2026-00005, INC-2026-00105)
  LOG-SETTLE-20260212-01     -> EV-002 in the ledger, NOT CITED   <- lost here
  CHG-2026-00188             -> EV-007 in the ledger, NOT CITED   <- lost here
  CI-SCHEMA-REGISTRY         -> EV-010 in the ledger, NOT CITED   <- lost here

```
