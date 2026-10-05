# KPI 1: Reducing human intervention

## Human interaction

```mermaid
flowchart TD
    subgraph F1["Phase I: Initiation and Allocation"]
        A1["The Problem Manager reads reports."] -.-> I1["(Interaction 1)"]
        A2["The Problem Manager opens and assigns a ticket."] -.-> I2["(Interaction 2)"]
    end

    subgraph F2["Phase II: Searching for data across approximately 5 different systems."]
        B1["Manual ticket search in ITSM."] -.-> I3["(Interaction 3)"]
        B2["Search for old RCA documents (Confluence / others)."] -.-> I4["(Interaction 4)"]
        B3["Open the CMDB and manually map dependencies."] -.-> I5["(Interaction 5)"]
        B4["Manual search for deployments in Change Management."] -.-> I6["(Interaction 6)"]
        B5["Extract the errors."] -.-> I7["(Interaction 7)"]
    end

    subgraph F3["Phase III: Correlation and drafting"]
        C1["Copy the data and manually match the times."] -.-> I8["(Interaction 8)"]
        C2["Brainstorming session between the PM and experts."] -.-> I9["(Interaction 9)"]
        C3["Writing an initial RCA report from scratch."] -.-> I10["(Interaction 10)"]
    end

    subgraph F4["Faza IV: Revizuire și închidere"]
        D1["PM requests additions; Expert rewrites; Approval"] -.-> I11["(Interaction 11)"]
    end

    F1 --> F2 --> F3 --> F4 --> EndNode(["RCA COMPLETED (After several days)"])
```

## Multi-agent application-assisted process

```mermaid
flowchart TD
    subgraph F1["Phase I: Opening the application"]
        A1["The PM opens the application, selects the desired incident, and begins the analysis."] -.-> I1["(Interaction 1)"]
    end

    subgraph F2["Phase II: Automated execution of the analysis"]
        direction TB
        B1["• Semantically search the CMDB for similar incidents.<br/>• Service and time slot selection ➔ Scheduler<br/>• Deterministic CMDB query: changes, logs<br/>• Sorts historical RCA documents (RAG)<br/>• Formulate hypotheses and correlate the evidence.<br/>• Validate citations (Guardrails) and calculate score<br/>• Save complete RCA (Initial)"]
        B2["WITHOUT HUMAN INTERACTION"]
    end

    subgraph F3["Phase III: Referral to Technical Expert"]
        C1["The Technical Expert reviews the RCA policy, selects the cause, and chooses one of the three options."] -.-> I2["(Interaction 2)"]
    end

    subgraph F4["Phase IV: Receipt of response from the technician/expert"]
        D1["The PM receives and views the response from the TE."] -.-> I3["(Interaction 3)"]
    end

    F1 --> F2 --> F3 --> F4 --> EndNode(["RCA COMPLETED<br/><i>(After a few minutes)</i>"])
```

## Calculation of process efficiency improvement percentage

### Approach I: Analysis of step weighting

| Sistem metric | Manual | Automated (Agentic) |
| :--- | :---: | :---: |
| **Number of human steps** | 11 | 3 |
| **Percentage / step** | 9,09% / step | 33,33% / step |

* $3 \times 9{,}09\% = 27{,}27\%$ $\rightarrow$ If the number of automated steps were compared to the percentage of a manual step.
* $100\% - 27{,}27\% = \mathbf{72{,}73\%}$ $\rightarrow$ **That is how much the process has been streamlined.**

---

### Approach II: Referencing the manual resolution base

* **$I_{\text{manual}} = 11$** (human interactions in RCA solving)
* **$I_{\text{agentic}} = 3$** (human interactions in app-assisted RCA claims resolution)
* **Diferență pași:** 
  $$I_{\text{manual}} - I_{\text{agentic}} = 11 - 3 = 8 \text{ saved interactions}$$

#### Efficiency calculation:

$$\text{Efficiency} = \frac{I_{\text{manual}} - I_{\text{agentic}}}{I_{\text{manual}}} = \frac{8}{11} \approx 0{,}727272\dots$$

In percentages:
$$0{,}727272\dots \times 100 \approx \mathbf{72{,}73\%}$$

> **RCA Process Efficiency Rate:** **`72,73%`** (reduction of human effort/interaction).


# KPI 2: Self-resolution rate


It measures the software architecture's ability to complete an end-to-end technical workflow—from receiving the problem to fully delivering the analysis—100% autonomously, without human assistance or manual intervention to unblock the process during execution.

### 1. In the traditional process
* **Self-resolution rate = 0%** (no stage can be completed using only one's own resources).
* Ticketing systems, configuration management databases (CMDBs), logs, and deployment (change) processes operate in isolation without communicating with one another; consequently, no correlation is triggered when Root Cause Analysis (RCA) begins, as human interaction is required at each stage.

### 2. App-assisted process
* The user initiates the process by selecting an incident and receives the completed analysis at the end.

---

## Comparison by Execution Stages

| # | Stage| Manual | Automated (Agentic) |
| :-: | :--- | :--- | :--- |
| **1.** | **Case initiation** | The man is looking for a ticket. | The person selects the incident. |
| **2.** | **Identification of similar cases** | The man is manually searching through old tickets. | The system searches the CMDB for past incidents. |
| **3.** | **Investigation planning** | The person (TE) reads and manually selects the period. | Planning agent determines (calculates) the period. |
| **4.** | **Evidence collection – 4 sources** | The man opens the manual. | The System |
| **5.** | **Causal correlation & hypotheses** | The Man| The System |
| **6.** | **Evidence validation & structuring** | The Man | The System |
| **7.** | **Technical approval** | The Man| The Man |
| **8.** | **Process termination** | The Man| The Man |

---

## Comparative Calculation

### The Manual Case:
* $E_{\text{autonomy}} = 0$ *(man intervenes in everything)*
* $N_{\text{steps}} = 8$
* $$\text{Auto-Resolution Rate}_{\text{Manual}} = \frac{0}{8} \times 100 = \mathbf{0\%}$$

### Application Use Case (Agentic)
* $E_{\text{autonomy}} = 5$ *(stages 2, 3, 4, 5, and 6 are executed without human intervention)*
* $N_{\text{steps}} = 8$
* $$\text{Auto-Resolution Rate} = \frac{5}{8} \times 100 = \mathbf{62{,}5\%}$$

> **Conclusion:** After automating the process, the self-resolution rate increases from **`0%`** to **`62,5%`**.
```