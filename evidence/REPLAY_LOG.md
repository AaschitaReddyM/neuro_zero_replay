# Zero-LLM Deterministic Replay Execution Log

## Overview
This document logs the real execution runs of the deterministic replay engine against `http://localhost:8080`. No LLM is invoked during replay. Actions execute deterministically using Playwright native locators (`get_by_role`, `get_by_label`, `get_by_text`) with automatic waiting.

---

## 1. Successful Deterministic Replay (Lookup Member Balance)

- **Command**:
  ```bash
  python main.py replay --artifact evidence/artifacts/lookup_member_balance.json --params '{"member_id":"67890"}'
  ```
- **Log Source**: `evidence/replay_success_run.log`
- **Measured Latency**: 1.80s
- **Status**: `SUCCESS` (Disjoint terminal state)
- **Steps Completed**: 7/7
- **Extracted Outputs** (masked on console via privacy guardrails):
  ```
  member_name: ***REDACTED***
  savings_balance: ***REDACTED_CURRENCY***
  account_type: Checking
  status: ACTIVE
  ```
- **Checkpoint**: Verified `#lookup-result` element visibility and `"Member Found"` text match.

---

## 2. Business Outcome Detection (Non-Existent Member)

- **Command**:
  ```bash
  python main.py replay --artifact evidence/artifacts/lookup_member_balance.json --params '{"member_id":"99999"}'
  ```
- **Log Source**: `evidence/replay_business_outcome_run.log`
- **Measured Latency**: 1.72s
- **Status**: `BUSINESS_OUTCOME` (Disjoint terminal state, `is_business_outcome: True`)
- **Outcome Identifier**: `member_not_found`
- **Evidence Extracted**: `"Member not found. Please check the member ID and try again."`
- **Architectural Guarantee**: The error handler taxonomy intercepts page-visible business outcomes immediately, distinguishing them from technical system failures (crashes, timeouts, network disconnections).

---

## 3. Risk Gating Policy Enforcement

- **Command (Unapproved)**:
  ```bash
  python main.py replay --artifact evidence/artifacts/account_management.json --params '{"member_id":"12345"}'
  ```
- **Result**: Execution halts at Step 6 (`RISKY` action `Freeze Account`) with status `needs_confirmation`. The step is refused until explicit operator approval is provided.
- **Command (Approved)**:
  ```bash
  python main.py replay --artifact evidence/artifacts/account_management.json --params '{"member_id":"12345"}' --approve-risky
  ```
- **Result**: Replay proceeds through Step 6 and completes successfully.

---

## 4. Human-in-the-Loop Escalation & Control Transfer

- **Log Source**: `evidence/replay_escalation_run.log`
- **Intervention Records**: `evidence/interventions/escalation_*.json`
- **State Machine Transitions**:
  1. `AUTOMATION` -> Step failure detected on page
  2. `PAUSED` -> Replay session paused; screenshot and context captured; structured intervention written to `evidence/interventions/<run_id>.json`
  3. `HUMAN_CONTROL` -> Live Playwright browser session held open for operator intervention
  4. `RESUMING` -> Resumed upon receipt of `<run_id>.resume` signal file
  5. `AUTOMATION` -> Post-intervention state verified; execution resumes and completes cleanly.