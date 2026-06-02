# WU-ENGINE-01 Draft PR Review — AgentMiMo

- Reviewer: AgentMiMo
- Date: 2026-06-02
- PR: https://github.com/noho/dayu-agent-r/pull/109
- Branch: `refactor/wu-engine-01-runner-diagnostic-payload-audit`

## Conclusion

**PASS**

All gate checks pass. No blocking, high, or medium findings.

---

## Gate Checklist

| # | Gate | Result | Evidence |
|---|------|--------|----------|
| 1 | Runner diagnostic `raw_payload` is bounded, redacted, summarized | PASS | `diagnostic_payload.py` — `_bounded_payload()` fallback chain: full → truncate_preview → minimal (5 base fields). `_is_sensitive_key()` with `_normalized_sensitive_key()` handles dashed variants. All public APIs return `_bounded_payload()` result. |
| 2 | Stream / non-stream provider error parity | PASS | `test_stream_non_stream_provider_error_object_parity` confirms `canonical_byte_size`, `sha256_digest`, `provider_error` fields are identical. Both paths call `provider_error_diagnostic_payload()`. |
| 3 | HTTP error body byte caps preserved | PASS | `runner.py:882-902` — `_safe_read_error_body` reads bounded bytes first, then parses JSON, then calls `http_error_diagnostic_payload()`. Non-dict / non-JSON returns `raw_payload=None`. |
| 4 | Invalid UTF-8 diagnostics bounded | PASS | `diagnostic_payload.py:119-143` — `invalid_utf8_diagnostic_payload()` stores only `chunk_byte_size`, `chunk_sha256_digest`, and 96-byte base64 prefix. No raw chunk leak. |
| 5 | Host ingest production code unchanged | PASS | `git diff main...HEAD -- dayu/host/` produces empty output. `tests/host/test_engine_ingest_mapping.py` test fixture updated to use new diagnostic shape but host production code untouched. |
| 6 | Engine contracts and README describe stable diagnostic semantics | PASS | `engine_events.py`, `runner_events.py` docstrings updated to "有界诊断载荷；不承诺保留 provider 原始报错载荷". `README.md` adds `raw_payload` bullet documenting bounded diagnostic semantics. |
| 7 | Aggregate fix for dashed sensitive keys and non-string scalars | PASS | `_normalized_sensitive_key()` at line 451 normalizes `-` to `_` before fragment matching. `_provider_error_scalar_preview()` at line 332 passes `bool`, `int`, `float`, `None` through unchanged. Test `test_diagnostic_payload_redacts_sensitive_values` covers `api-key`, `client-secret`, `access-token`, `Authorization`, `credential_id` variants. Test `test_provider_error_summary_preserves_json_scalar_values` covers `code=429`, `type=True`, `param=None`. |
| 8 | Tests meaningful, no production compatibility facade | PASS | 97 tests pass. New `test_diagnostic_payload.py` (288 lines) covers structure, redaction, scalar handling, size bounds, fallback. Updated tests verify bounded payloads in SSE, non-stream, HTTP error, and parity paths. No `metadata` bag or compatibility wrapper introduced. |

## Verification

- **Tests**: 97 passed in 0.58s
- **Pyright**: 0 errors, 0 warnings, 0 informations on `dayu/engine/`
- **Host production diff**: empty (no changes)

## Low Findings

### L1: Test helper duplication across test files

`_leaf_strings()`, `_serialized_size()` are duplicated in `test_diagnostic_payload.py`, `test_http_error_event.py`, and `test_protocol_error.py`.

- Impact: Low — test-only code, no production effect.
- Recommendation: Consider extracting to a shared test helper in a follow-up if more test files need these utilities. Not blocking.

### L2: `_canonical_payload_metadata` serializes full payload for hash

At `diagnostic_payload.py:181`, the full original payload is serialized to compute `canonical_byte_size` and `sha256_digest`. This is necessary for the hash-based diagnostic contract but means the full payload is temporarily in memory during serialization.

- Impact: Low — the full payload is already in memory as the function argument; serialization creates a transient copy that is garbage-collected.
- Recommendation: No action needed. The design is correct — the hash proves payload identity without storing the payload.

---

## Summary

The PR achieves its stated goal: `raw_payload` on Runner diagnostic events is now a bounded, redacted, summarized diagnostic structure instead of raw provider JSON. The bounded payload fallback chain (full → truncate_preview → minimal) guarantees a 4096-byte ceiling. Sensitive key redaction handles both underscore and hyphen variants. Non-string scalar fields in provider error sub-objects are correctly preserved. Stream, non-stream, and HTTP error paths all produce structurally consistent diagnostic payloads. Host ingest code is untouched. Tests are meaningful and comprehensive.
