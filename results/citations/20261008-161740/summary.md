# Citation trace (2026-10-08 16:17)

Stories traced: 5. No investigation for: STORY-006, STORY-007, STORY-008, STORY-009, STORY-010, STORY-011, STORY-012, STORY-013.

| Measure | Value |
|---|---|
| Expected citations in the ledger (preservation) | 21/22 |
| Expected citations cited by the main hypothesis (utilization) | 18/21 of those in the ledger |
| Ledger evidence the answer key names anywhere (precision) | 35/100 |
| Stories where the main hypothesis cites a red herring | 1/5 |

| Story | In ledger | Cited by main | Not in ledger | Red herrings cited by main |
|---|---|---|---|---|
| STORY-001 | 6/6 | 5/6 | - | RCA-2025-00042 |
| STORY-002 | 5/5 | 5/5 | - | - |
| STORY-003 | 4/4 | 2/4 | - | - |
| STORY-004 | 3/4 | 3/4 | LOG-GW-20260424-01 | - |
| STORY-005 | 3/3 | 3/3 | - | - |

```
STORY-001  (RCA-2026-00001, INC-2026-00101)
  LOG-PAYROLL-20260727-08    -> EV-009 CITED by the main hypothesis
  LOG-PAYROLL-20260727-07    -> EV-014 CITED by the main hypothesis
  RCA-2025-00042             -> EV-029 CITED by the main hypothesis
  CI-PAYROLL-DB              -> EV-022 CITED by the main hypothesis
  INC-2025-00119             -> EV-030 in the ledger, NOT CITED   <- lost here
  CHG-2026-00262             -> EV-015 CITED by the main hypothesis

STORY-002  (RCA-2026-00002, INC-2026-00857)
  LOG-PAY-20260714-14        -> EV-001 CITED by the main hypothesis
  LOG-PAY-20260714-15        -> EV-002 CITED by the main hypothesis
  CHG-2026-00871             -> EV-006 CITED by the main hypothesis
  RCA-2025-00114             -> EV-012 CITED by the main hypothesis
  CI-PAYMENT-DB              -> EV-009 CITED by the main hypothesis

STORY-003  (RCA-2026-00003, INC-2026-00103)
  LOG-PORTAL-20260810-03     -> EV-001 CITED by the main hypothesis
  LOG-PORTAL-20260810-02     -> EV-003 cited only by another hypothesis (HYP-001)   <- lost here
  LOG-PORTAL-20260810-01     -> EV-004 cited only by another hypothesis (HYP-001)   <- lost here
  CI-PORTAL-LOCK-REDIS       -> EV-009 CITED by the main hypothesis

STORY-004  (RCA-2026-00004, INC-2026-00104)
  LOG-GW-20260501-01         -> EV-002 CITED by the main hypothesis
  LOG-GW-20260424-01                   NOT IN THE LEDGER: at 2026-04-24 00:05, outside the window(s) 2026-05-01 01:12 - 2026-05-01 04:12   <- lost here
  RCA-2024-00088             -> EV-011 CITED by the main hypothesis
  CI-CERT-MANAGER            -> EV-005 CITED by the main hypothesis

STORY-005  (RCA-2026-00005, INC-2026-00105)
  LOG-SETTLE-20260212-01     -> EV-001 CITED by the main hypothesis
  CHG-2026-00188             -> EV-006 CITED by the main hypothesis
  CI-SCHEMA-REGISTRY         -> EV-009 CITED by the main hypothesis

```
