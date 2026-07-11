# Architecture

Every diagram on this page renders natively on GitHub. **Nothing here is an image** — you can read the source, and so can a diff.

- [1. The system, and its trust boundaries](#1-the-system-and-its-trust-boundaries)
- [2. The decision pipeline — three gates](#2-the-decision-pipeline--three-gates)
- [3. End-to-end process flow](#3-end-to-end-process-flow)
- [4. The contract — who is allowed to do what](#4-the-contract--who-is-allowed-to-do-what)
- [5. The state model](#5-the-state-model)

---

## 1. The system, and its trust boundaries

The important line on this diagram is the one between **the assistant** and **the human**. The assistant is *untrusted for irreversible actions* — not because it is unreliable, but because "irreversible" and "automated" is a combination that should always require a person.

Everything the assistant does terminates in **a file on your disk**, which is reversible. The only irreversible outcome in the whole system — a submitted application — is reachable **only** through a human click.

```mermaid
flowchart TB
  subgraph EXT["External"]
    BOARDS["Job boards<br/>and ATS APIs"]:::ent
    ATS["ATS<br/>Greenhouse / Lever / Ashby"]:::ent
    MAIL["Your mailbox"]:::ent
  end

  subgraph RUN["Scheduled run — UNTRUSTED for irreversible actions"]
    P1["Scout + dedupe"]:::proc
    P2["Read the job description"]:::proc
    G1{{"role_fit<br/>HARD GATES, then SCORE 0.00–1.00"}}:::dec
    G2{{"values_veto<br/>THE COMPANY SCREEN"}}:::dec
    P3["Tailor resume + cover letter"]:::proc
    P4["Fill the form — STOP at Submit"]:::proc
    P9["Write the brief"]:::proc
  end

  HUMAN(["THE HUMAN<br/>the only source of<br/>irreversible authority"]):::user

  subgraph STORE["Local state — the source of truth"]
    LOG[("Application log")]:::store
    VERD[("company_verdicts.json<br/>the cache IS the log")]:::store
    RL[("Run log — append-only")]:::store
  end

  BOARDS --> P1 --> P2 --> G1
  G1 -- "gated, or below the floor" --> P9
  G1 -- "clears the floor" --> G2
  G2 -- "FAIL — suppressed, never shown again, but LOGGED" --> VERD
  G2 -- "UNKNOWN — escalated, NEVER guessed" --> HUMAN
  G2 -- "PASS" --> P3 --> P4
  P4 -- "STAGED. The submit POST never fires." --> HUMAN
  HUMAN -- "clicks Submit herself" --> ATS
  ATS --> MAIL
  MAIL -- "confirmation, verified with a positive control" --> LOG
  P1 & P2 & P3 & P4 --> RL
  VERD --> G1

  classDef ent fill:#f0f0f2,stroke:#9a9aa0
  classDef proc fill:#eaf3ff,stroke:#0071e3
  classDef dec fill:#fff4e5,stroke:#e08600
  classDef store fill:#fbf7ea,stroke:#b79433
  classDef user fill:#ede9ff,stroke:#5e5ce6
```

---

## 2. The decision pipeline — three gates

Most job-search automation scouts, tailors and applies. The decision of **whether a role deserves the effort** is usually a vibe, a keyword count, or nothing at all.

Three stages, **cheapest first**, each able to kill the role. The expensive one runs **last**.

```mermaid
flowchart LR
  IN(["A new posting"]):::proc

  G1{{"1 · HARD GATES<br/>free<br/><br/>comp · level · freshness<br/>location · sector · blocklist"}}:::dec
  G2{{"2 · FIT SCORE<br/>free<br/><br/>0.00 – 1.00<br/>apply floor 0.60"}}:::dec
  G3{{"3 · VALUES VETO<br/>one research cycle<br/>per COMPANY, cached forever<br/><br/>PASS / FAIL / UNKNOWN"}}:::dec

  X1["INVISIBLE<br/>not deferred — gone"]:::block
  X2["FEED ONLY<br/>no tailor cycle is spent"]:::block
  X3["SUPPRESSED<br/>never shown again<br/>but LOGGED"]:::block
  X4["ESCALATED TO YOU<br/>the machine does not<br/>break this tie"]:::user

  OUT(["RANK, then CUT<br/>to the weekly budget"]):::ok

  IN --> G1
  G1 -- "fail" --> X1
  G1 -- "pass" --> G2
  G2 -- "below floor" --> X2
  G2 -- "at or above the floor" --> G3
  G3 -- "FAIL" --> X3
  G3 -- "UNKNOWN" --> X4
  G3 -- "PASS" --> OUT

  classDef proc fill:#eaf3ff,stroke:#0071e3
  classDef dec fill:#fff4e5,stroke:#e08600
  classDef block fill:#f6e7e8,stroke:#c0392b
  classDef user fill:#ede9ff,stroke:#5e5ce6
  classDef ok fill:#eafaef,stroke:#34c759
```

**Why the apply floor is low (0.60), not high.** A job description is a **wish list** — it describes a person who does not exist. Scoring against a wish list and then demanding 0.80 rejects roles you would win. So the **gates** disqualify, and the **score** only *ranks* what survives.

Clearing the floor is permission to be **ranked**, not permission to apply. Without that last step, a "strict" gate still passes 30 roles a week against a budget of 8 — and you spend your effort on whichever ones happened to be scouted first.

**Why the veto is a gate and not a weight.** You can match 99% of a job description and still not want to work there. When that happens you do not want the role *ranked slightly lower* — you want it **gone**. A score component can only ever discount. Only a gate makes something invisible.

---

## 3. End-to-end process flow

Note the three **red terminals**. They are the only ways the assistant's authority ends, and they are the whole safety design:

1. the submit POST that never fires,
2. the account wall it refuses to touch,
3. outreach that is drafted and never sent.

```mermaid
flowchart TB
  S(["Scheduled run · 3×/day"]):::sched --> A0["Open a run id"]:::proc
  A0 --> A1["Scout every configured source<br/>coverage is BINARY: all of them, every run"]:::proc
  A1 --> D1{"anything new?"}:::dec
  D1 -- no --> A9
  D1 -- yes --> A2["Read the full job description"]:::proc

  A2 --> F{{"role_fit — gates, then score"}}:::dec
  F -- "gated / below floor" --> A9
  F -- "clears 0.60" --> V{{"values_veto — the company"}}:::dec
  V -- "FAIL" --> SUP[("suppressed + logged")]:::store
  V -- "UNKNOWN" --> A9
  V -- "PASS" --> R{{"is the ATS a guest apply,<br/>or an account wall?"}}:::dec

  R -- "account wall" --> STOP2["HARD STOP<br/>never creates an account<br/>hands the role to you"]:::block
  R -- "guest apply" --> A3["Tailor the resume + cover letter"]:::proc
  A3 --> A4["Fill every field<br/>attach the documents<br/>STOP with the cursor on Submit"]:::proc
  A4 --> STOP1["THE HALT<br/>the submit POST NEVER fires<br/>on a scheduled run"]:::block

  STOP1 --> H(["YOU click Submit"]):::user
  STOP2 --> H
  H --> A5["Log it · verify the confirmation<br/>with a POSITIVE CONTROL"]:::proc
  A5 --> A7["Draft outreach"]:::proc
  A7 --> STOP3["DRAFT ONLY<br/>nothing is ever sent"]:::block
  A5 --> A9["Write the brief:<br/>what needs YOUR ruling"]:::proc
  A9 --> A10(["Close the run · assert the system<br/>agrees with itself"]):::ok

  classDef sched fill:#f0f0f2,stroke:#9a9aa0
  classDef proc fill:#eaf3ff,stroke:#0071e3
  classDef dec fill:#fff4e5,stroke:#e08600
  classDef block fill:#f6e7e8,stroke:#c0392b
  classDef store fill:#fbf7ea,stroke:#b79433
  classDef user fill:#ede9ff,stroke:#5e5ce6
  classDef ok fill:#eafaef,stroke:#34c759
```


---

## 4. The contract — who is allowed to do what

**This swimlane *is* the contract.** Read down a lane and you have that actor's complete authority. Read across and you have the run.

The rule that matters: **the assistant's lane never crosses into anything irreversible.** Every arrow that would do so terminates in a red block instead.

```mermaid
flowchart LR
  subgraph SCHED["SCHEDULER"]
    direction TB
    S1["fires 3×/day"]
    S2["cannot mint an approval —<br/>a scheduled run has no authority<br/>to submit anything, ever"]:::deny
  end

  subgraph ASSIST["ASSISTANT — untrusted for anything irreversible"]
    direction TB
    A1["scouts every source"]
    A2["reads the JD"]
    A3["scores it · screens the company"]
    A4["tailors the documents"]
    A5["fills the form to the submit line"]
    A6["logs · reconciles · briefs"]
    AX["MAY NOT: submit · create an account ·<br/>enter a password · solve a captcha ·<br/>send an email · overturn an exclusion ·<br/>break an UNKNOWN tie"]:::deny
  end

  subgraph GUARD["GUARD — mechanical, not procedural"]
    direction TB
    G1["intercepts every ATS write"]
    G2["ABORTS the POST unless an unconsumed,<br/>role-scoped receipt exists"]
    G3["receipts are single-use"]
    GX["a scheduled run cannot mint one,<br/>so unattended submit is IMPOSSIBLE —<br/>not merely forbidden"]:::deny
  end

  subgraph HUMAN["THE HUMAN — the only irreversible authority"]
    direction TB
    H1["clicks Submit"]
    H2["rules on every UNKNOWN"]
    H3["edits the exclusion list"]
    H4["sends the outreach"]
    H5["drags the cards"]
  end

  SCHED --> ASSIST --> GUARD --> HUMAN

  classDef deny fill:#f6e7e8,stroke:#c0392b,color:#1d1d1f
```

| Actor | May | **May not** |
|---|---|---|
| **Scheduler** | Fire the run | **Mint an approval.** A scheduled run has no submit authority — this is structural, not a policy |
| **Assistant** | Scout, read, score, screen, tailor, fill, log, brief | **Submit · create an account · enter a password · solve a captcha · send an email · overturn an exclusion · break an UNKNOWN tie** |
| **Guard** | Abort any ATS write without a valid receipt | Grant itself a receipt |
| **The human** | **Everything irreversible.** Submit · rule on UNKNOWNs · edit the exclusion list · send outreach | — |

**Capability beats policy.** Every "may not" above is enforced by *removing the ability*, not by writing the rule down and hoping:

| The rule | How it is actually enforced |
|---|---|
| Never submit unattended | The network layer **aborts the POST**. A scheduled run cannot mint a receipt. |
| Never overturn an exclusion | `evaluate()` and `record()` **raise** on an excluded company. |
| Never guess a company verdict | Too few researched signals **forces** `UNKNOWN`. |
| Never invent a finding about a person | An adverse person-signal with no citable URL **raises**. |
| Never claim a submission you cannot prove | `record --not-found` is **refused** without a passing positive control. |

A rule you can forget is not a rule.

---

## 5. The state model

An application has one status at a time, and only some transitions are legal. `Applied` is special: you cannot reach it by asserting it — you reach it by **proving** a confirmation arrived.

```mermaid
stateDiagram-v2
    [*] --> Sourced
    Sourced --> Screened : role_fit — gates, then score
    Screened --> [*] : gated, or below the floor
    Screened --> Vetted : clears the apply floor
    Vetted --> [*] : values veto = FAIL (suppressed, logged)
    Vetted --> AwaitingRuling : values veto = UNKNOWN
    AwaitingRuling --> Vetted : the human rules PASS
    AwaitingRuling --> [*] : the human rules FAIL
    Vetted --> Tailored : veto = PASS and the route is fillable
    Vetted --> OnHold : account wall — never auto-filled
    Tailored --> Staged : filled to the submit line, and STOPPED
    Staged --> Applied : THE HUMAN clicks Submit
    OnHold --> Applied : the human applies directly
    Applied --> Verified : a confirmation is PROVEN, with a positive control
    Verified --> Screen
    Screen --> Interview
    Interview --> Offer
    Interview --> Closed
    Offer --> [*]
    Closed --> [*]
```

**`Applied → Verified` is not a formality.** Under a trust-your-word model, a role that failed to submit sits in `Applied` forever, looking healthy, and you never follow up. So the verifier **refuses** to record a "not found" unless a *positive control* — a known-good search that must return a known result — passed first. **A negative result is not evidence until the tool has proven it can find a positive one.**
