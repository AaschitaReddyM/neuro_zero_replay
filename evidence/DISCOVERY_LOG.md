# Live Capability Discovery Execution Log

## Overview
This document records the live capability discovery phase executed against the bundled target application. Unlike mock-driven simulation, this run exercised real LLM agent decision-making using Google Gemini and real browser execution via Playwright.

## Execution Details

- **Date**: 2026-09-15
- **Mode**: Live LLM Capability Discovery
- **LLM Provider**: Google Gemini REST API (`https://generativelanguage.googleapis.com/v1beta`)
- **Model**: `gemini-3.5-flash-lite` (low-latency structured JSON generation)
- **Target Application**: `http://localhost:8080` (Bundled Core Banking Portal)
- **Capability Name**: `lookup_member_balance`
- **Execution Latency**: 4.52 seconds
- **Evidence Artifact**: `evidence/discovery_run_20260914_234448/`

## Discovery Process

### Goal
`"Look up member 12345 and read their current savings balance"`

### Target Application Surface
The target application is a core-banking web portal running on `http://localhost:8080` containing:
- Tabbed interface (`Member Lookup`, `Transfer Funds`, `Account Management`)
- Dynamic DOM tables without synthetic test IDs
- Form input for member ID and asynchronous lookup result cards

### Recorded Automation Steps
1. **Step 1: NAVIGATE** (`value="http://localhost:8080"`, Risk: `SAFE`)
   - Initial navigation to target application.
   - Screenshot: `step_1_navigate.png`
2. **Step 2: TYPE** (`target=accessibility_role:textbox:Member ID:`, `value="{{member_id}}"`, Risk: `SAFE`)
   - The LLM observed the accessibility tree, resolved the textbox labelled `Member ID:`, and typed the input value.
   - The orchestrator dynamically parameterized `12345` into `{{member_id}}`.
   - Screenshot: `step_2_type.png`
3. **Step 3: CLICK** (`target=accessibility_role:button:Search`, Risk: `SAFE`)
   - The LLM selected the `Search` button to trigger the lookup query.
   - Screenshot: `step_3_click.png`
4. **Step 4: EXTRACT** (`target=semantic_selector:#lookup-result`, `output_key="account_details"`, Risk: `SAFE`)
   - Extracted live member data (Name, Status, Balance, Account Type).
   - Screenshot: `step_4_extract.png` (or `step_4_done.png`)

### Contract Specifications Generated
- **Parameters**: `member_id` (string, required)
- **Outputs**: `account_details`, `balance`, `member_name`, `account_type`, `status`
- **Checkpoint**: `#lookup-result` element visible, verifying `text_contains="Member Found"`.
- **Business Outcome Rules**: Evaluates `#lookup-result` for `"Member not found"` to cleanly terminate in disjoint `BUSINESS_OUTCOME` state without throwing false technical errors.
- **Error Handlers**: `element_not_found` with `text_content_match` fallback, `timeout` with `increase_wait_time` fallback.

### Full Evidence Artifacts
- Serialized Artifact: `evidence/artifacts/lookup_member_balance.json`
- Full Transcript: `evidence/discovery_run_20260914_234448/transcript.json`
- Step Screenshots: `evidence/discovery_run_20260914_234448/*.png`
- Console Log: `evidence/discovery_run.log`

### Post-Discovery Output Contract Standardization (Round 2 Remediation)
In accordance with Round 2 audit remediation (Phase R4), artifact outputs were refined to enforce a strict 1-to-1 bijection between declared output schemas and extraction steps (`outputs.keys() == {s.output_key for extract steps}`):
- Rather than extracting a single multi-field text block (`account_details`), 4 discrete extraction steps (`member_name`, `savings_balance`, `account_type`, `status`) were defined with explicit extraction regexes and numeric type coercion (`savings_balance` parsed as numeric float).
- In `transfer_funds.json`, `confirmation_number` was configured with an explicit regex `Confirmation Number:\s*(TXN\d+)` to return cleanly coerced transaction IDs matching `^TXN\d+$` rather than an unparsed HTML dump.
- In `account_management.json`, `account_status` was aligned 1-to-1 with its extraction step.