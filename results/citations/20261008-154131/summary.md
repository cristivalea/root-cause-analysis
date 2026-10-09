# Citation trace (2026-10-08 15:41)

Stories traced: 13.

| Measure | Value |
|---|---|
| Expected citations in the ledger (preservation) | 39/49 |
| Expected citations cited by the main hypothesis (utilization) | 35/39 of those in the ledger |
| Ledger evidence the answer key names anywhere (precision) | 63/161 |
| Stories where the main hypothesis cites a red herring | 5/13 |

| Story | In ledger | Cited by main | Not in ledger | Red herrings cited by main |
|---|---|---|---|---|
| STORY-001 | 5/6 | 5/6 | CHG-2026-00262 | RCA-2025-00042 |
| STORY-002 | 5/5 | 5/5 | - | - |
| STORY-003 | 4/4 | 4/4 | - | - |
| STORY-004 | 3/4 | 3/4 | LOG-GW-20260424-01 | - |
| STORY-005 | 3/3 | 0/3 | - | RCA-2025-00192 |
| STORY-006 | 4/5 | 4/5 | CHG-2026-00766 | - |
| STORY-007 | 3/5 | 3/5 | LOG-NOTIF-20260317-01, CHG-2026-00329 | CHG-2026-00341 |
| STORY-008 | 2/3 | 2/3 | CHG-2026-00412 | RCA-2025-00305, LOG-AUTH-20260404-02 |
| STORY-009 | 2/4 | 2/4 | CHG-2026-00053, INC-2026-00016 | - |
| STORY-010 | 3/3 | 3/3 | - | - |
| STORY-011 | 1/1 | 1/1 | - | CHG-2026-01102 |
| STORY-012 | 2/2 | 2/2 | - | - |
| STORY-013 | 2/4 | 1/4 | LOG-AUTH-20260911-01, CHG-2026-01118 | - |

```
STORY-001  (RCA-2026-00025, INC-2026-00101)
  LOG-PAYROLL-20260727-08    -> EV-001 CITED by the main hypothesis
  LOG-PAYROLL-20260727-07    -> EV-006 CITED by the main hypothesis
  RCA-2025-00042             -> EV-010 CITED by the main hypothesis
  CI-PAYROLL-DB              -> EV-007 CITED by the main hypothesis
  INC-2025-00119             -> EV-011 CITED by the main hypothesis
  CHG-2026-00262                       NOT IN THE LEDGER: at 2026-03-11 18:00, outside the window 2026-07-27 02:00 - 2026-07-27 08:15   <- lost here

STORY-002  (RCA-2026-00026, INC-2026-00482)
  LOG-PAY-20260714-14        -> EV-001 CITED by the main hypothesis
  LOG-PAY-20260714-15        -> EV-002 CITED by the main hypothesis
  CHG-2026-00871             -> EV-003 CITED by the main hypothesis
  RCA-2025-00114             -> EV-007 CITED by the main hypothesis
  CI-PAYMENT-DB              -> EV-005 CITED by the main hypothesis

STORY-003  (RCA-2026-00027, INC-2026-00103)
  LOG-PORTAL-20260810-03     -> EV-001 CITED by the main hypothesis
  LOG-PORTAL-20260810-02     -> EV-003 CITED by the main hypothesis
  LOG-PORTAL-20260810-01     -> EV-004 CITED by the main hypothesis
  CI-PORTAL-LOCK-REDIS       -> EV-008 CITED by the main hypothesis

STORY-004  (RCA-2026-00028, INC-2026-00104)
  LOG-GW-20260501-01         -> EV-001 CITED by the main hypothesis
  LOG-GW-20260424-01                   NOT IN THE LEDGER: at 2026-04-24 00:05, outside the window 2026-04-30 20:00 - 2026-05-01 04:35   <- lost here
  RCA-2024-00088             -> EV-011 CITED by the main hypothesis
  CI-CERT-MANAGER            -> EV-005 CITED by the main hypothesis

STORY-005  (RCA-2026-00029, INC-2026-00105)
  LOG-SETTLE-20260212-01     -> EV-001 cited only by another hypothesis (HYP-001)   <- lost here
  CHG-2026-00188             -> EV-005 cited only by another hypothesis (HYP-001)   <- lost here
  CI-SCHEMA-REGISTRY         -> EV-008 in the ledger, NOT CITED   <- lost here

STORY-006  (RCA-2026-00030, INC-2026-00106)
  LOG-BILL-20260630-05       -> EV-001 CITED by the main hypothesis
  LOG-BILL-20260630-02       -> EV-002 CITED by the main hypothesis
  RCA-2025-00230             -> EV-008 CITED by the main hypothesis
  CI-BILLING-DB              -> EV-004 CITED by the main hypothesis
  CHG-2026-00766                       NOT IN THE LEDGER: at 2026-06-24 21:00, outside the window 2026-06-30 20:00 - 2026-07-01 02:10   <- lost here

STORY-007  (RCA-2026-00031, INC-2026-00107)
  LOG-NOTIF-20260317-01                NOT IN THE LEDGER: at 2026-03-17 14:00, outside the window 2026-03-18 22:25 - 2026-03-19 04:05   <- lost here
  LOG-NOTIF-20260319-02      -> EV-002 CITED by the main hypothesis
  CHG-2026-00329                       NOT IN THE LEDGER: at 2026-03-16 10:00, outside the window 2026-03-18 22:25 - 2026-03-19 04:05   <- lost here
  RCA-2025-00390             -> EV-010 CITED by the main hypothesis
  CI-NOTIF-BROKER-HOST       -> EV-005 CITED by the main hypothesis

STORY-008  (RCA-2026-00032, INC-2026-00108)
  LOG-AUTH-20260404-08       -> EV-001 CITED by the main hypothesis
  LOG-AUTH-20260404-03       -> EV-003 CITED by the main hypothesis
  CHG-2026-00412                       NOT IN THE LEDGER: at 2026-04-04 09:40, outside the window 2026-04-04 10:00 - 2026-04-04 13:02   <- lost here

STORY-009  (RCA-2026-00033, INC-2026-00109)
  LOG-REP-20260115-02        -> EV-001 CITED by the main hypothesis
  CHG-2026-00053                       NOT IN THE LEDGER: at 2026-01-12 16:00, outside the window 2026-01-15 02:00 - 2026-01-15 06:40   <- lost here
  CI-COREDNS                 -> EV-003 CITED by the main hypothesis
  INC-2026-00016                       NOT IN THE LEDGER   <- lost here

STORY-010  (RCA-2026-00034, INC-2026-00110)
  LOG-USER-20260522-03       -> EV-001 CITED by the main hypothesis
  CHG-2026-00712             -> EV-003 CITED by the main hypothesis
  RCA-2025-00012             -> EV-007 CITED by the main hypothesis

STORY-011  (RCA-2026-00035, INC-2026-00468)
  LOG-PAY-20260908-01        -> EV-001 CITED by the main hypothesis

STORY-012  (RCA-2026-00036, INC-2026-00449)
  LOG-PORTAL-20260826-01     -> EV-003 CITED by the main hypothesis
  CHG-2026-01058             -> EV-005 CITED by the main hypothesis

STORY-013  (RCA-2026-00037, INC-2026-00491)
  LOG-AUTH-20260911-01                 NOT IN THE LEDGER: at 2026-09-11 09:00, outside the window 2026-09-15 06:00 - 2026-09-15 09:10   <- lost here
  LOG-AUTH-20260915-03       -> EV-001 CITED by the main hypothesis
  CHG-2026-01118                       NOT IN THE LEDGER: at 2026-09-10 11:00, outside the window 2026-09-15 06:00 - 2026-09-15 09:10   <- lost here
  CI-SESSION-REDIS           -> EV-008 in the ledger, NOT CITED   <- lost here

```
