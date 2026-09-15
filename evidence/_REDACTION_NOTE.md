# PII Redaction & Active Guardrails Note

## Overview
In accordance with enterprise banking and privacy guardrails, **NeuroZero Replay** enforces active recursive PII (Personally Identifiable Information) masking across all layers of the automation architecture:
1. **Replay Engine Outputs**: Extracted text, execution metrics, and observed error payloads are sanitized before terminal serialization and caller return.
2. **Structured Logging (structlog)**: A dedicated processor (
edaction_processor) intercepts all log event dictionaries in memory before serialization or console emission.
3. **LLM Context Wire Filter**: Accessibility trees and scraped page content pass through recursive redaction prior to prompt assembly during autonomous discovery.

---

## Redaction Capabilities

### 1. Dictionary Key Matching (Case-Insensitive)
Any dictionary field matching or containing the following keys is masked immediately:
- ssn, social_security
- password, pin, cvv
- credit_card, creditcard
- ccount_number, 
outing_number
- 	oken, secret, pi_key

### 2. Regular Expression Value Patterns
Arbitrary strings, log messages, error observations, and free-text page extracts are scanned and scrubbed:
- **Social Security Numbers (SSN)**: \d{3}-\d{2}-\d{4} -> ***REDACTED_SSN***
- **Bank Account Numbers (9–17 digits)**: \d{9,17} -> ***REDACTED_ACCT***
- **Bearer Tokens**: (?i)bearer\s+[a-zA-Z0-9_\-\.]+ -> Bearer ***REDACTED***
- **API Keys / Secrets**: sk-[a-zA-Z0-9_\-]{20,} -> ***REDACTED_KEY***

### 3. Recursive Traversal
Nested dictionaries and lists are recursively traversed so no deeply nested payloads escape redaction.

---

## Verification
- Unit test: 	ests/probe_audit.py validates recursive masking on nested dictionaries and pattern strings.
- Integration test: Verified during live replay against http://localhost:8080.
