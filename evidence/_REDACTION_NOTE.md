# PII Redaction & Active Guardrails Policy

## Overview
In accordance with enterprise banking and privacy requirements, **NeuroZero Replay** enforces active recursive PII (Personally Identifiable Information) masking across logs, intervention records, and runtime evidence.

---

## Redaction Capabilities & Enforcement

### 1. Extracted Values are Sensitive by Default
- The browser automation engine never writes extracted text to log streams.
- Replay execution logs output only the extraction key, character length, and a truncated SHA-256 hash (`length=...`, `hash=...`), ensuring raw banking data does not leak into log aggregators.

### 2. Escalation Intervention Excerpts
- Human escalation records (`evidence/interventions/*.json`) restrict DOM snapshots to a redacted text excerpt of at most 300 characters (`page_content[:300]`), accompanied by a localized visual screenshot path, eliminating multi-megabyte page memory dumps.

### 3. Business Outcome Evidence
- Page-visible evidence strings (`evidence_text`) are passed through `redact_sensitive_data` and truncated to 300 characters before inclusion in result payloads.

### 4. Dictionary Key Matching (Case-Insensitive)
Any dictionary field matching or containing the following keys is masked immediately upon serialization:
- `password`, `pin`, `cvv`
- `ssn`, `social_security`
- `credit_card`, `creditcard`
- `account_number`, `routing_number`
- `token`, `secret`, `api_key`
- 5–8 digit numeric IDs under keys containing `member` or `id` -> `***REDACTED_ID***`

### 5. Regular Expression Value Patterns
Arbitrary strings, error observations, and free-text page extracts are scanned and scrubbed:
- **Social Security Numbers (SSN)**: `\b\d{3}-\d{2}-\d{4}\b` -> `***REDACTED_SSN***`
- **Bank Account Numbers (9–17 digits)**: `\b\d{9,17}\b` -> `***REDACTED_ACCT***`
- **Bearer Tokens**: `(?i)bearer\s+[a-zA-Z0-9_\-\.]+` -> `Bearer ***REDACTED***`
- **API Keys / Secrets**: `\bsk-[a-zA-Z0-9_\-]{20,}\b` -> `***REDACTED_KEY***`
- **Currency Amounts**: `\$\s?\d[\d,]*\.\d{2}` -> `***REDACTED_CURRENCY***`
- **Synthetic Test Personas**: `\b(Synthetic Member Name)\b` -> `***REDACTED_NAME***`

---

## Explicit Policy Limitations (What Still Leaks & Why)

1. **Arbitrary Human Names in Unstructured Text**:
   - Arbitrary person names (e.g., custom member names outside dictionary keys) cannot be reliably detected or redacted using static regular expressions without introducing massive false positive rates or relying on heavy named-entity recognition (NER) NLP models.
   - For enterprise production deployment, named-entity recognition services (such as Google Cloud DLP or AWS Comprehend) should be integrated into the log aggregation pipeline. For the bundled synthetic test suite, synthetic demo personas are handled via known token patterns.
2. **Visual Screenshots**:
   - Full-page PNG screenshots captured during discovery and escalation contain rendered pixels of the application UI. Visual pixel blurring is not applied in this version and requires server-side image redaction pipelines before external distribution.
