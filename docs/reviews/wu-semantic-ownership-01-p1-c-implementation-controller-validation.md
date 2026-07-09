# WU-SEMANTIC-OWNERSHIP-01 P1-C Implementation Controller Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P1-C`
- Accepted plan commit: `7399aafa`
- AgentCodex implementation artifact: `docs/reviews/wu-semantic-ownership-01-p1-c-implementation-codex.md`
- Controller result: implementation is ready for independent code review after one controller cleanup.

## Motivation Check

The P1-C motivation remains valid. The old compaction prompt asked an LLM to emit Host-owned evidence pipeline labels, RunInput rendered internal `evidence_kind=...` into model context, and cancellation/tool failure text exposed Host governance wording to the LLM. These are real owner-boundary violations under the project LLM-facing text rules.

The fix belongs at the projection boundaries:

- Host compaction input / parser owns compact prompt schema and internal evidence-kind derivation.
- Host RunInput owns memory and accepted compact projection to LLM-facing `SystemMessage`.
- Runtime helper owns cancellation outcome construction policy, while business tools own their business-readable cancellation message and hint.
- ToolRuntime owns governed failure message projection.

## Controller Patch

After inspecting AgentCodex output, the controller removed the now-unused private runtime helper `_blank_to_default_optional()` from `dayu/runtime/tool_call_projection.py`. Keeping that helper would preserve the old "blank value becomes default cancellation text" policy as dead fallback code, which conflicts with P1-C fail-fast semantics.

No other controller code change was applied before review dispatch.

## Propagation Audit

- Compaction prompt: `conversation_compaction_user.md` no longer asks for `evidence_kind` and now exposes `user_visible_progress` instead of `user_visible_run_state`.
- Compaction parser: `llm_compaction.py` derives `FactEvidenceKindVNext.ACCEPTED_EVIDENCE_MATERIAL` internally after label validation.
- Compact/readable projection: `compact_material.py` and `run_input.py` no longer render `evidence_kind=...` into previous compact view, memory fact lines, or fallback semantic compact lines.
- Runtime cancellation: `host_cancelled_outcome()` and `ToolBusinessCancelled` require explicit non-empty business-readable message and hint from callers.
- Business tools: Fins, Doc, and Web call sites now provide business-readable cancellation / startup failure wording.
- ToolRuntime governed failures: LLM-facing messages no longer use `awaiting adapter`, `poll awaiting`, or `tool execution cancelled before completion`.
- P1-A projection source remains referenced by `run_input.py`, `compact_material.py`, and `memory.py`.
- P1-B lifecycle / cancellation durable truth was not changed.

## README Decision

- `dayu/host/README.md`: read; no update. It already describes Host ownership of memory/context governance and accepted-result projection, and this slice did not add a stable Host developer interface.
- `dayu/fins/README.md`: read; no update. It already states Fins exposes business semantic tool results while Host/ToolRuntime own wait/cancel governance.
- `dayu/config/README.md`: read; no update. It documents config/prompt directory responsibilities, not individual compact prompt fields.
- `tests/README.md`: read; no update. No test layer, test running rule, or maintenance rule changed.

## Residual Scan Classification

- `poll`, `adapter`, and `wait id` remain widely present in Host/runtime wait/poller implementation, internal docstrings, diagnostics, and tests. These are internal runtime governance terms, not LLM-facing prompt/tool outcome text.
- `user_visible_run_state`, `tool_source_text`, and `accepted_evidence_material` remain as Host typed enum / internal compact contract terms and tests. They are no longer requested from the LLM or rendered into RunInput semantic text.
- `duplicate` / `governance` remain in Host duplicate policy implementation, config loading, tests, and diagnostics. Duplicate policy user-facing messages are business action guidance, and `base/tools.md` `等待工具结果` remains allowed task guidance under the accepted litmus test.
- No remaining hit for `未进入等待状态`, `后续调度`, `宿主取消`, `不要把本次取消视为业务失败`, `awaiting adapter`, `poll awaiting`, or `tool execution cancelled before completion` was found in the cleaned LLM-facing outcome paths.

## Controller Validation

```bash
source .venv/bin/activate && pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/runtime tests/fins tests/tools
```

Result: `1119 passed, 2 skipped, 3 warnings`.

```bash
source .venv/bin/activate && pytest tests/runtime/test_tool_call_projection.py
```

Result after controller cleanup: `20 passed`.

```bash
source .venv/bin/activate && rg -n "等待状态|未进入等待状态|后续调度|wait id|poll|adapter|user_visible_run_state|tool_source_text|accepted_evidence_material|宿主取消|不要把本次取消视为业务失败" dayu/config dayu/fins dayu/host dayu/runtime tests --glob '!**/*.html' --glob '!**/*.htm' --glob '!**/workspace/**'
```

Result: ran; residual hits classified above.

```bash
source .venv/bin/activate && rg -n "duplicate|governance|等待工具结果|等待结果" dayu/config dayu/fins dayu/host dayu/runtime tests --glob '!**/*.html' --glob '!**/*.htm' --glob '!**/workspace/**'
```

Result: ran; residual hits classified above.

```bash
source .venv/bin/activate && rg -n "accepted_result_projection|AcceptedEvidenceEnvelope|AcceptedEvidenceToolQuery" dayu/host/run_input.py dayu/host/compact_material.py dayu/host/memory.py
```

Result: P1-A projection helper remains referenced by `run_input.py`, `compact_material.py`, and `memory.py`.

```bash
source .venv/bin/activate && pyright
```

Result: `0 errors, 0 warnings, 0 informations`.

```bash
git diff --check
```

Result: passed.

## Review Gate

Dispatch AgentMiMo and AgentDS for independent implementation review. Required focus:

- Whether Host-derived evidence kind from evidence material section is sufficient and correctly validated.
- Whether any LLM-facing text still exposes Host / wait / adapter / poll / governance terms.
- Whether making cancellation message/hint mandatory has complete call-site coverage without compatibility fallback.
- Whether README no-update decisions are valid.
