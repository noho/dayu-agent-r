# WU-LAYER-02 Slice 1 Code Review (DS)

- **reviewer**: DS (deepseek-v4)
- **date**: 2026-06-02
- **gate**: code review
- **scope**: WU-LAYER-02 Slice 1 — Runtime Diagnostic Text Primitive
- **design source**: `docs/host/design.md`
- **control doc**: `docs/host/host-core-followup-implementation-control.md`
- **plan**: `docs/host/wu-layer-02-shared-runtime-helper-consolidation-plan.md`
- **implementation report**: `docs/reviews/wu-layer-02-slice1-implementation-report-20260602.md`

## Files Reviewed

| File | Status | Review focus |
|---|---|---|
| `dayu/runtime/diagnostic_text.py` | new | API correctness, regex semantics, layer neutrality |
| `tests/runtime/test_diagnostic_text.py` | new | coverage completeness, test fragility |
| `dayu/runtime/__init__.py` | modified | docstring only, no re-export |
| `tests/runtime/test_weak_typing_guard.py` | modified | helper set update, no guard relaxation |
| `dayu/README.md` | modified | runtime capability list update |
| `tests/README.md` | modified | test layer description update |
| `docs/host/host-core-followup-implementation-control.md` | modified | controller status update only |

## Validation

| Check | Command | Result |
|---|---|---|
| Target tests | `pytest -q tests/runtime/test_diagnostic_text.py tests/runtime/test_weak_typing_guard.py tests/host/test_import_boundary.py` | **47 passed** |
| Pyright | `python -m pyright dayu/ tests/ utils/` | **0 errors, 0 warnings** |
| Import boundary | Verified `diagnostic_text.py` imports only `re`, `typing.Final` | **clean** |
| Layer neutrality | No import of `dayu.engine`/`.host`/`.service`/`.ui`/`.fins` | **clean** |
| No re-export | `__all__: list[str] = []` | **clean** |

## Findings Ordered by Severity

### F1 [LOW] `api key` / `apikey` space-separated pattern without assignment-operator guard

**Evidence**: `_ASSIGNED_SECRET_VALUE_PATTERN` alternation 2 (`(?:api\s+key|apikey)\b\s+`) matches `api key <any-word>` including non-secret plain words. Adversarial verification confirms:

```
"the api key generation failed" → match, value="generation"
"api key validation error"       → match, value="validation"
"apikey rotation scheduled"      → match, value="rotation"
"the API key is invalid"         → match, value="is"
```

**Impact**:
- Engine whole-message redaction path: `contains_sensitive_diagnostic_value` returns `True`, causing messages like `"the api key generation failed"` to be fully replaced by `"exception message redacted"` — complete diagnostic info loss.
- Host value-redaction path: `"the api key generation failed"` → `"the api key <redacted> failed"` — partial info loss but context preserved.
- In practice, `api key generation` / `api key validation` is unlikely in provider exception diagnostic context (which deals with call failures, not workflow descriptions), so the blast radius is small.

**Plan alignment**: This behavior is explicit in the plan (regex difference matrix row 2: `api key <value>` 空格写法, and row 4: `apikey=<value>`). Engine already covers this pattern today.

**Recommendation**: Accept as intentional trade-off. However, the false-positive test matrix (`test_contains_sensitive_diagnostic_value_ignores_plain_diagnostics`) should be extended to include at least one `api key <plain-word>` case to explicitly document the known boundary. This is not a blocker.

### F2 [LOW] `[^\s,;]+` value terminator consumes trailing punctuation

**Evidence**: The negated character class `[^\s,;]+` only terminates on whitespace, `,`, and `;`. Characters like `}`, `]`, `)`, `>`, `"`, `'`, `|` are consumed as part of the captured value. For example:

```
"api_key=abc123} def" → captures "abc123}"
"token=abc] and more" → captures "abc]"
```

After redaction, these trailing punctuation characters are lost from the diagnostic text.

**Impact**: Purely cosmetic. Real API keys and Bearer tokens (base64url: `[A-Za-z0-9_-]`, OpenAI keys: `sk-[A-Za-z0-9_-]`) never contain `}`, `]`, `)`, `>`, `"`, or `'`. The trailing punctuation is formatting artifact from structured logging, JSON fragments, or bracketed error formats. Security guarantee is maintained — secrets are fully redacted.

**Recommendation**: Accept. Not a security issue. Not worth complicating the regex with lookahead assertions for diagnostic text formatting.

### F3 [LOW] False-positive test gap: `api key` plain-word scenarios

**Evidence**: `test_contains_sensitive_diagnostic_value_ignores_plain_diagnostics` parametrizes five cases covering `JWT token` / `Content-Type header` / `authorization header` / `token refresh` scenarios, but does not include any `api key <plain-word>` false-positive scenario (e.g., `"api key generation failed"`).

**Impact**: Even though the behavior is intentional, the test matrix does not document that `api key <plain-word>` false positives are known and accepted. A future developer reviewing the test might reasonably believe these cases are "not matched" when they actually are.

**Recommendation**: Add one or two test cases like `"api key generation failed"` and `"the API key is invalid"` with explicit assertions that they ARE matched (i.e., `assert contains_sensitive_diagnostic_value(...)`) to document the intentional trade-off. Alternatively, add a test comment documenting the known false-positive boundary.

### F4 [INFO] Implementation is faithful to plan

All plan requirements verified:

- **Three simple functions** with keyword-only `redaction_marker` / `max_chars` / `truncated_suffix`: `contains_sensitive_diagnostic_value`, `redact_sensitive_diagnostic_values`, `truncate_diagnostic_text`. ✓
- **`redaction_marker` literal handling**: lambda callable in `re.sub`, not string replacement. Verified with `r"literal-\1-\g<value>-\\"` marker. ✓
- **Bearer normalization**: lowercase `bearer` → output `Bearer <marker>`. ✓
- **`truncate_diagnostic_text` semantics**: no-op for `len <= max_chars` (identity preserved), exact-boundary no-op, empty string no-op, fail-fast on illegal params. ✓
- **Idempotency**: `redact(redact(msg)) == redact(msg)` with `<redacted>` marker. ✓
- **Composition path**: `truncate(redact(msg))` does not leak secret. ✓
- **Chinese docstrings**: All three functions have complete parameter/return/exception docstrings. ✓
- **Module docstring**: Explicitly states the module does not understand Exception, Run, Attempt, Host diagnostic ref, Engine event, or provider payload. ✓
- **`Final` typed module-level constants**: All regex patterns and error message strings. ✓
- **No `Any` / `object` / untyped signatures**: All function signatures fully typed. ✓
- **No `getattr` / `hasattr` / lazy import / glue seam / compat wrapper**. ✓
- **No magic numbers**: All validation messages and regex patterns are named constants. ✓

### F5 [INFO] README updates are correct and scoped

- `dayu/README.md` line 85: adds `diagnostic_text` capability description in runtime stable capability list. Wording matches plan: "层中立 diagnostic 文本敏感值检测、局部脱敏和有界截断；不承载 Host / Engine 诊断事件语义、provider payload 语义或业务字段语义". ✓
- `tests/README.md` line 91: adds diagnostic text test coverage fact in `tests/runtime/` section. Wording matches current code facts. ✓
- Neither README writes future plans, implementation details, or time-sensitive records. ✓
- Root `README.md`, `dayu/engine/README.md`, `dayu/host/README.md` correctly NOT updated (no trigger). ✓

### F6 [INFO] Controller doc update is status-only

The `host-core-followup-implementation-control.md` diff only updates the status table fields (`implementation status`, `active slice`, `current slice`, `validation`, `next entry point`) and adds WU-LAYER-02 disambiguation to fields that were previously WU-LAYER-01-only (e.g., `accepted slice commits`, `implementation artifact`). No substantive control logic changes. ✓

### F7 [INFO] Weak typing guard correctly extended

`tests/runtime/test_weak_typing_guard.py`: `diagnostic_text.py` added to `_PHASE12_RUNTIME_HELPERS` frozenset. The guard scan is run-length neutral (adds one file, scans one file). No guard relaxation. ✓

## Completeness Against Plan Checklist

| Plan requirement | Status |
|---|---|
| `contains_sensitive_diagnostic_value` detects Bearer / api key spaces / api_key / apikey / api-key / authorization / password / secret / token | ✓ all 14 value patterns tested |
| Does not false-positive `JWT token has expired`, `Content-Type header is invalid` | ✓ parametrized |
| `redact_sensitive_diagnostic_values` preserves field name prefix, only replaces value | ✓ asserted in test |
| Bearer normalized to `Bearer <marker>` | ✓ "bearer" → "Bearer <R>" |
| `redaction_marker` literal — no regex group/backslash interpretation | ✓ `r"literal-\1-\g<value>-\\"` |
| `truncate_diagnostic_text` no-op for `len < max`, `len == max` (identity) | ✓ |
| Truncation yields exact `max_chars` with suffix | ✓ 18 chars |
| Empty string: `contains` False, `redact` no-op, `truncate` no-op | ✓ |
| Redact + truncate composition: no secret leak | ✓ |
| Illegal `max_chars`/suffix: fail fast `ValueError` | ✓ both parametrized |
| `dayu/runtime/__init__.py`: docstring only, no re-export | ✓ |
| `dayu/README.md`: stable capability note | ✓ |
| `tests/README.md`: test layer fact | ✓ |
| `tests/runtime/test_weak_typing_guard.py`: helper set updated | ✓ |
| No `Any`/`object`/untyped/hasattr/getattr/lazy import/compat code | ✓ verified by AST scan |
| Import boundary: no Host/Engine/Service/UI/Fins | ✓ verified by import boundary test |

## Open Questions

1. **Should `contains_sensitive_diagnostic_value("")` explicitly document its `False` return as a design decision?** Currently this falls out naturally from the regex (no pattern matches empty string). The test covers it. No action needed unless the design doc requires explicit documentation.

2. **Should `truncate_diagnostic_text` validate that `truncated_suffix` is a string (not `None`)?** Currently the function would raise `TypeError` from `len(None)` which is obscure. But the plan and type annotations already enforce `str`, and pyright catches `None` at the call site. The runtime `TypeError` is a type-safety backstop, not a design defect. No action needed.

3. **Is the `apikey` form without assignment operator a legitimate concern?** The plan allows `apikey\b\s+` (space-separated, no `:` or `=`). Real diagnostic text is unlikely to contain `apikey` followed by a plain word unless it's actually a secret value. The broader match is intentional and the regex difference matrix documents it.

## Verdict

**PASS** — No blocking issues.

The implementation is clean, faithful to the plan, and all verification gates pass (47/47 tests, 0 pyright errors, clean import boundary, no weak typing violations). The three LOW findings are all intentional trade-offs documented in the plan or minor test coverage documentation gaps. None affect the security or correctness of the runtime primitive.

Recommended follow-up for Slice 2/3: extend the false-positive test matrix in `test_contains_sensitive_diagnostic_value_ignores_plain_diagnostics` with `api key <plain-word>` cases to explicitly document the known boundary (related to F1, F3). This can be done in any subsequent Slice without blocking the current gate.
