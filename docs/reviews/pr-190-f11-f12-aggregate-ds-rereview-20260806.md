# PR 190 F11/F12 Aggregate DS Re-Review

## Scope

- **Mode**: Aggregate re-review — independent from MiMo
- **PR**: [#190](https://github.com/noho/dayu-agent-r/pull/190) — `fix(cli): close interactive conformance gaps`
- **Head**: `codex/interactive-oracle` @ `2cf1b4ac`
- **Base**: `main` @ `3087b1b9`
- **Output file**: `docs/reviews/pr-190-f11-f12-aggregate-ds-rereview-20260806.md`
- **Re-review date**: 2026-08-06T01:50:56+08:00
- **Reviewer**: Claude (DeepSeek V4 Pro)
- **Trigger**: Controller adjudication accepted DS-01; fix applied in single-line test addition. This re-review verifies DS-01 exact closure, re-evaluates rejected DS-02/DS-03 against direct ownership/history, confirms no unauthorized changes, and re-validates all original aggregate correctness dimensions.
- **Included scope**:
  - DS-01 fix: `tests/host/test_compaction_contract.py` +1 line (uncommitted)
  - Full PR diff (`3087b1b9..2cf1b4ac`) — 213 files
  - Existing artifacts: DS review, MiMo review, adjudication, fix artifact
  - Key source files: `compact_structure.py`, `compaction.py`, `compact_pipeline.py`, `conversation_compaction_user.md`
- **Excluded scope**: No implementation edits; no test edits beyond verification; no commit/push/PR modification.

---

## DS-01 Closure Verification

### Fix location

`tests/host/test_compaction_contract.py:139` — inside `test_compact_structure_owner_projects_template_schema_rules_and_parser`:

```python
assert tuple(item.value for item in CompactSemanticSectionV3) == tuple(template)[1:]
```

Where `template = compact_output_template_v3()` returns a fresh `Mapping` whose keys are mechanically derived from `_ROOT` descriptor fields. `[1:]` excludes the fixed `"schema"` root key.

### Owner correctness

The assertion lives in the existing owner-level contract test that already centralizes template/schema/rules/parser equality assertions. The test is in `tests/host/test_compaction_contract.py` — correct test owner per the compaction contract test suite. No new test file was created; no existing test was weakened.

### Drift-failure proof

Verified manually against code and confirmed by the focused test node passing:

| Drift scenario | Why it would fail |
|---|---|
| **Add field to `_ROOT`** | `template` gains extra key → `tuple(template)[1:]` length > 5 → assertion fails |
| **Delete field from `_ROOT`** | `template` loses key → `tuple(template)[1:]` length < 5 → assertion fails |
| **Reorder fields in `_ROOT`** | `tuple(template)[1:]` order changes → assertion fails (enum order stable) |
| **Change enum without `_ROOT`** | `tuple(item.value ...)` differs from `tuple(template)[1:]` → assertion fails |
| **Change enum order** | Same as reorder — assertion fails |

### No private descriptor export

The fix does **not** export `_ROOT` or any other private descriptor. It uses only the public `compact_output_template_v3()` and `CompactSemanticSectionV3` — both are already public symbols. No cyclic import or new runtime dependency was introduced.

### Test run

```
pytest tests/host/test_compaction_contract.py::test_compact_structure_owner_projects_template_schema_rules_and_parser -q
1 passed in 0.32s
```

**Verdict: PASS** — DS-01 is exactly closed at the correct test owner and would fail on any enum/template add/delete/reorder drift.

---

## DS-02 Re-Evaluation: Prompt Business Prose vs. Structure Owner

### Controller adjudication

Rejected with reason: "Structure and business meaning are intentionally separate semantic owners."

### Direct evidence

- **Structure owner** (`compact_structure.py:134-155`): `_ROOT` descriptor mechanically defines field names, types, requiredness, allowed values, nested shapes. All five public functions (`compact_output_template_v3`, `compact_output_json_schema_v3`, `compact_output_prompt_rules_v3`, `compact_output_json_schema_digest_v3`, `parse_compact_candidate_v3`) are mechanically derived from `_ROOT`.

- **Prompt owner** (`conversation_compaction_user.md:34-38`): Five per-field business descriptions encode:
  - Source-kind restrictions (e.g., `evidence_facts.support_labels` can only reference `evidence_material` or `previous_evidence_fact`)
  - Null semantics (e.g., `session_summary=null` means "清空旧 summary")
  - Meaningful-or-null rule (e.g., session_summary must be null if cap cannot fit meaningful content)
  - LLM-facing prohibitions (e.g., "禁止用单字符、截断片段或占位文本凑成非空摘要")

These business rules **cannot** be mechanically derived from `_ROOT`'s field descriptors — the descriptor knows types and shapes, not business semantics. Generating them from code would either pollute the structure descriptor with prose or duplicate business semantics.

### LLM-facing text constraint compliance

Per `CLAUDE.md` LLM-facing text constraints, the prompt must be "self-contained" for the model. The prompt (3,337 bytes) is self-contained: it embeds structure rules (`<<compact_output_rules>>`), concrete template (`<<compact_output_template>>`), and human-written business descriptions all within the single markdown file. It does not reference internal module names, code paths, or system internals. No violation.

### Verdict

**DS-02 rejection stands. PASS** — prompt business prose and structure descriptor are legitimately separate owners. No prompt changes were made and none are needed.

---

## DS-03 Re-Evaluation: Broad `except Exception` in Fallback

### Controller adjudication

Rejected for this work unit; recorded as pre-existing observability debt.

### Direct history evidence

```bash
# Base commit (3087b1b9):
git show 3087b1b9:dayu/host/compact_pipeline.py | grep -n "except Exception"
788:    except Exception as error:

# Current HEAD (2cf1b4ac):
git show HEAD:dayu/host/compact_pipeline.py | grep -n "except Exception"
788:    except Exception as error:
```

The `except Exception` at line 788 was **present at the base commit** — it is not introduced by this PR. The try-block body expanded (added `budget = estimate_recent_window_fallback_budget(...)` call in commit `321893e4`), but the exception handler and its fail-closed semantics were not changed.

### Functional analysis

The broad catch implements a safety principle: any unexpected failure in fallback selection/estimation returns a deterministic fail-closed decision (`FALLBACK_ACTION_FAIL_CLOSED`). The caller (`dispatch.py:3462`) logs at ERROR level with the `failure_reason` string. Stack trace is lost, but the system fails closed correctly.

### Verdict

**DS-03 rejection stands. PASS** — the broad `except Exception` is pre-existing behavior unchanged by this PR. It correctly fails closed. Traceback observability is a separate Host observability concern properly deferred to a future work unit.

---

## Unauthorized Changes Check

### Uncommitted diff

```
 tests/host/test_compaction_contract.py | 1 +
 1 file changed, 1 insertion(+)
```

Only the approved DS-01 assertion was added. No other files were modified.

### Committed diff scope verification

The full PR diff (`3087b1b9..2cf1b4ac`) covers only:
- Engine structured-output contracts (`dayu/engine/contracts/structured_output.py`, payload builder, runner)
- Host compaction v3 contract (`compact_structure.py`, `compaction.py`, `context_governance.py`, `context_fallback.py`, `context_event_payload.py`, `context_events.py`, `compaction_operation.py`, `compaction_terminal.py`, `compact_pipeline.py`)
- Tool Trace response identity (F11): `durable/tool_trace.py`, `tool_trace_analysis.py`, `tool_trace_analysis_contracts.py`
- Artifacts, Memory, RunInput: v2→v3 type migration
- LLM-facing prompts: `conversation_compaction.md`, `conversation_compaction_user.md`
- Config: `models.json` (DeepSeek structured output capability)
- Registry: oracles, scenarios
- Tests: all targeted suites
- Docs/README: per AGENTS.md triggers

No unauthorized changes to: normal prompt behavior, interactive UI behavior, provider/model selection (beyond structured output config), Fins/download/process, user authorization, or any area outside compaction/Tool Trace/structured output.

**Verdict: PASS** — no unauthorized changes.

---

## Original Aggregate Correctness Dimensions Re-Validation

Each of the 12 dimensions from the original DS aggregate review is re-validated:

| # | Dimension | Re-validated | Status |
|---|---|---|---|
| 1 | Provider Capability → Strict v3 Parse | `parse_compact_candidate_v3()` still mechanically derived from `_ROOT`; no changes to parser | **PASS** |
| 2 | Context Governance Accept/Reject/Repair/Fallback | `accept_compact_candidate_v3()` unchanged; repair loop unchanged; fallback fail-closed unchanged | **PASS** |
| 3 | Canonical Terminals / Externalized Payloads | `context_event_payload.py`, `context_events.py`, `compaction_terminal.py` unchanged | **PASS** |
| 4 | Artifacts, Memory/RunInput | `compact_artifact.py`, `memory.py`, `run_input.py` unchanged | **PASS** |
| 5 | Public Tool Trace Response Identity | `durable/tool_trace.py`, `tool_trace_analysis.py` unchanged; secret-safe projection intact | **PASS** |
| 6 | Schema/Template/Parser Shared Structure Owner | `_ROOT` descriptor unchanged; all five public functions unchanged; DS-01 fix adds cross-owner invariant | **PASS** |
| 7 | LLM-Facing Text: Minimal Yet Self-Contained | Prompts unchanged; prompt hash tests would catch drift | **PASS** |
| 8 | v2/Drop-Ledger Deletion — No Compat | Zero changes to schema identifiers; zero compat shims added | **PASS** |
| 9 | Success/Rejected Identities — Canonical and Secret-Safe | `CompactAcceptedTruthV3`, `_CompactAcceptancePermit`, identity validation unchanged | **PASS** |
| 10 | Fallback/Late/Corrupt/Mismatch — Fail Closed | All error exits unchanged; broad `except Exception` pre-existing | **PASS** |
| 11 | Registry Lifecycle/Readiness Claims — Honest | Registry unchanged; 3 unadjudicated replacement scenarios unchanged | **PASS** |
| 12 | Tests, Typing, Coverage, README/Design, Exports | See validation results below | **PASS** |

---

## Validation Results

### Focused test with DS-01 assertion

```
pytest tests/host/test_compaction_contract.py::test_compact_structure_owner_projects_template_schema_rules_and_parser -q
1 passed in 0.32s
```

### All targeted suites

```
pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py \
  tests/host/test_run_input_builder.py tests/host/test_memory_projection.py \
  tests/host/test_compaction_operation.py tests/host/test_compaction_terminal.py \
  tests/host/test_compact_artifact_store.py tests/host/test_tool_trace_projection.py \
  tests/host/test_accepted_result_projection.py tests/host/test_context_compact_events.py \
  tests/engine/contracts/ tests/host/test_import_boundary.py \
  tests/engine/test_package_exports.py tests/host/test_public_contracts.py -q
594 passed in 3.99s
```

### compact_structure.py coverage

```
Name                             Stmts   Miss  Cover   Missing
dayu/host/compact_structure.py     203     21    90%    210,213,221,276,284,287,293,323,339,345,374,392,398,435,464,512,514,516,519,538,550
TOTAL                              203     21    90%
Required test coverage of 80% reached. Total coverage: 89.66%
```

### pyright

```
0 errors, 0 warnings, 0 informations
```

### Ruff

```
All checks passed!
```

### JSON validation

```
docs/cli_ci_oracles.json  — valid
docs/cli_ci_scenarios.json — valid
```

### git diff --check

```
(no output — passed)
```

---

## Findings

### 1. PASS-DS01-已修复-`CompactSemanticSectionV3` 与 public template 的跨契约 invariant 已加入 owner test

- **入口/函数**: `test_compact_structure_owner_projects_template_schema_rules_and_parser`
- **文件(行号)**: `tests/host/test_compaction_contract.py:139`
- **状态**: 已在 controller 裁决后修复。单行断言 `tuple(item.value for item in CompactSemanticSectionV3) == tuple(template)[1:]` 在正确 test owner 处闭合，不使用私有 descriptor，会在 enum/template 的 add/delete/reorder 任一方向漂移时失败。
- **直接证据**: 专项 node 通过 (0.32s)；594 targeted tests 全部通过；pyright 0 errors；Ruff clean；compact_structure.py coverage 90%。
- **严重程度**: 低（维护性改进，当前无 bug）— 已闭合。

---

## Open Questions

无。原始 DS review 的三个 open question (OQ-01 coverage gap, OQ-02 Oracle adjudication timing, OQ-03 session_summary=null consumers) 均已在 controller adjudication 中裁决并闭合。

---

## Residual Risk

1. **Replacement scenario adjudication**: 3 个 replacement scenarios 仍为 `unadjudicated`。Owner 为 Oracle controller，不在本 work unit scope。不影响 merge readiness（PR 仍为 draft，不在此 work unit 合并）。

2. **DS-03 traceback observability debt**: 预存债务，分配到后续 Host observability work unit。不影响当前 compaction v3 的 fail-closed 正确性。

3. **Real-provider observation 不可复现**: 与原始 DS review 相同。本 re-review 依赖 implementation 正确性而非 observation 结果。

---

## Conclusion

**PASS**。DS-01 在正确 test owner 处精确闭合，会在 enum/template 任一方向漂移时失败。DS-02/DS-03 拒绝理由经直接 ownership/history 验证成立。无未授权变更。全部 12 个 aggregate correctness 维度保持 PASS。594 tests pass，pyright 0 errors，Ruff clean，JSON valid，coverage 90%。

仅一个 uncommitted 变更：`tests/host/test_compaction_contract.py` +1 行（批准的 DS-01 fix assertion）。
