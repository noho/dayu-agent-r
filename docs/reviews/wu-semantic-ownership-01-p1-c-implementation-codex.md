# WU-SEMANTIC-OWNERSHIP-01 P1-C Implementation - AgentCodex

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P1-C`
- Accepted plan commit: `7399aafa`
- Plan: `docs/host/wu-semantic-ownership-01-p1-c-plan.md`
- Control doc: `docs/host/issues-implementation-control.md`
- Non-goals preserved:
  - Did not enter P2-A / P2-B / P2-C.
  - Did not change P1-A accepted-result projection contract.
  - Did not change P1-B lifecycle / cancel durable truth.
  - Did not add old compact artifact or old schema compatibility reads.

## S0 Exposure Classification

Targeted scans were run with HTML / htm / workspace exclusions before implementation and again after implementation.

| Hit family | Classification | Decision |
|---|---|---|
| `conversation_compaction_user.md` `trace_kind=user_visible_run_state` | `llm-facing-must-fix` | Changed LLM-facing trace kind to `user_visible_progress`; Host internal block kind remains internal. |
| `conversation_compaction_user.md` LLM output `evidence_kind=tool_result|tool_source_text|accepted_evidence_material` | `llm-facing-must-fix` | Removed from prompt output schema; LLM now outputs only claim, evidence labels, and source labels. |
| `dayu/host/run_input.py` memory and fallback `evidence_kind=...` rendering | `llm-facing-must-fix` | Removed from SystemMessage / accepted compact semantic line rendering. |
| Fins download / upload / preprocess `未进入等待状态` failure outcome | `llm-facing-must-fix` | Reworded as task startup failure: `下载/上传/预处理任务未能启动。` |
| Fins / Doc / Web cancellation `宿主取消` / `后续调度` wording | `llm-facing-must-fix` | Reworded to business-readable stop / retry-after-user-confirmation text. |
| runtime `host_cancelled_outcome()` default Host-governance message / hint | `llm-facing-must-fix` | Removed runtime defaults; message and hint are now required non-empty caller-owned text. |
| ToolRuntime governed failures `awaiting adapter...`, `poll awaiting...`, `tool execution cancelled before completion` | `llm-facing-must-fix` where message enters `ToolFailedOutcome` | Reworded outcome messages as business-readable tool unavailable / background task tracking / stopped text; reason codes retained. |
| `base/tools.md` `调用后等待工具结果` | `business-readable-allowed` | Kept. Litmus test: deleting it would make the model more likely to assume synchronous completion or invent a result before the long-running tool result returns. |
| Duplicate `REUSE` / `HINT` / `HARD_STOP` / `REQUIRE_JUSTIFICATION` / `DURABLE_MISSING` messages | `business-readable-allowed` | These can flow through governed failure outcomes, but default messages are model-action guidance about using prior tool results or explaining insufficiency; they do not expose wait id / poll / adapter / durable governance. |
| Duplicate `AWAITING_FANOUT` message | `internal-diagnostic/fanout`, defensively cleaned | Path is `DuplicateDecision.message` -> awaiting fanout record / diagnostic, not `_governed_failure_outcome()`; still reworded to remove `等待状态`. |
| `poll`, `adapter`, `wait id`, `governance`, `duplicate` in Host/runtime implementation and tests | `internal-diagnostic-only` or `test-only` | Kept where they describe Host wait/poller/adapter implementation, config, docstrings, tests, diagnostics, or reason codes not projected as LLM-facing prompt/tool outcome text. |
| `evidence_kind` typed fields in `dayu.host.compaction`, `dayu.host.memory`, and tests | `internal typed contract` | Kept as Host-owned durable / memory typed value; no longer requested from LLM or rendered as `evidence_kind=...` in RunInput. |

## Evidence Kind Strategy

Chosen strategy: Host-derived evidence kind by material section.

Reasoning:

- In the current compact contract, `EvidenceBackedFactCandidate.evidence_labels` may only cite `evidence_material` labels.
- The quality checker already validates label existence and allowed section membership.
- Therefore the parser can safely assign internal `FactEvidenceKindVNext.ACCEPTED_EVIDENCE_MATERIAL` after parsing, without asking the LLM to classify internal evidence pipeline stages.

Rejected strategies:

- Keeping an LLM-facing source/type field with mapped values: unnecessary because all fact evidence labels come from a single evidence material section in this slice.
- Pre-annotating prompt material with Host-owned metadata: would still risk exposing internal pipeline distinctions unless further projected.

## Owner Boundary

| Semantic family | First producer | Validator | Durable / diagnostic owner | LLM-facing projection owner | Fix location |
|---|---|---|---|---|---|
| Compaction trace category | Host compact material builder | `ConversationCompactInputVNext` / material tests | Compact request material | Compaction prompt / material JSON | `TraceReadableKindVNext.USER_VISIBLE_PROGRESS`, prompt, design |
| Compaction fact evidence kind | Host parser from evidence labels | compaction parser + quality checker | Accepted compact candidate / memory typed view | No LLM-facing field | `llm_compaction.py`, prompt, tests |
| Conversation Memory fact rendering | Host memory / RunInput projection | RunInput builder tests | Memory snapshot remains typed | SystemMessage to LLM | `run_input.py` |
| Accepted compact fallback rendering | Host RunInput fallback codec | RunInput fallback tests | `CONTEXT_COMPACTED` payload | SystemMessage to LLM | `run_input.py` |
| Fins startup failure wording | Fins tool callable | Fins ingestion tools tests | Tool outcome | Tool message / accepted result | Fins download/upload/preprocess tools |
| Cancellation outcome text | Business tool callable | Runtime fail-fast + domain tests | ToolCancelledOutcome | Tool message / accepted result | Fins / Doc / Web callers, runtime helper |
| Duplicate governance messages | Host duplicate policy | Tooling / duplicate tests | ToolTrace / governed outcome | Tool outcome only for policy decisions | `tool_duplicate_governance.py` default awaiting fanout text; policy action text retained |
| ToolRuntime governed failure text | ToolRuntime policy decision | ToolRuntime tests | Tool failed outcome / diagnostics | Tool message | `tool_runtime.py` |

## Propagation Audit

- Compaction input:
  - Producer: `compact_material.py` builds trace/evidence/answer/current input material.
  - Projection: `conversation_compact_input_vnext_from_material_pack()` now emits `trace_kind=user_visible_progress` for user-visible progress material.
  - Prompt: `conversation_compaction_user.md` documents only business-readable trace categories.
  - Validation: `tests/host/test_compact_material.py` checks the new trace kind.

- Compaction output:
  - Producer: LLM outputs claim text and labels only.
  - Parser: `llm_compaction.py` derives `FactEvidenceKindVNext.ACCEPTED_EVIDENCE_MATERIAL`.
  - Durable typed value: `EvidenceBackedFactCandidateVNext.to_json()` still includes internal `evidence_kind` for Host-owned accepted candidate JSON.
  - LLM-facing reuse: previous compacted view, memory snapshot, and RunInput semantic lines no longer render `evidence_kind=...`.
  - Validation: `tests/host/test_llm_compaction.py`, `tests/host/test_compact_material.py`, and `tests/host/test_run_input_builder.py`.

- Accepted result projection:
  - P1-A source remains `dayu.host.accepted_result_projection`.
  - `compact_material.py` still imports `project_accepted_tool_result`.
  - `run_input.py` still imports accepted result projection helpers.
  - `memory.py` still lazy-imports accepted result projection helpers.
  - No query/status/source/result semantics were rederived in P1-C.

- Tool cancellation:
  - Business tools now explicitly provide message/hint at call sites.
  - Runtime validates non-empty text and constructs `ToolCancelledOutcome(reason=host_cancelled)` without Host-governance default wording.
  - Fins / Doc / Web cancellation text is consistent: current call stopped; retry only after user confirmation if still needed.
  - Validation: runtime, Fins, Doc, and Web tool tests.

- ToolRuntime governed failures:
  - `reason_code` remains machine-readable governance.
  - LLM-facing `message` no longer says `awaiting adapter`, `poll awaiting`, or `tool execution cancelled before completion`.

## README And Design Decisions

- `dayu/host/README.md`: read. No update. Current README already states Host owns memory/context governance and accepted result projection. P1-C changed prompt/tool wording and design detail, not developer-facing Host package architecture.
- `dayu/fins/README.md`: read. No update. Current README already states Fins tools expose business semantic results and Host/ToolRuntime own wait/cancel governance.
- `dayu/config/README.md`: read. No update. It documents config/prompts directory responsibilities, not individual compaction prompt field schema.
- `tests/README.md`: read. No update. Existing test layer descriptions remain accurate.
- `docs/host/design.md`: updated because it explicitly documented the old compaction LLM-facing schema. It now records `user_visible_progress` and Host-derived internal evidence kind.

## Residual Scan Classification

- The final first required scan still reports many `poll`, `adapter`, and `wait id` hits in Host wait/poller/runtime implementation, runtime cancellation helpers, and tests. These are internal runtime / Host governance code and not LLM-facing prompt/schema/tool outcome text.
- The final first required scan no longer reports `未进入等待状态`, `后续调度`, `宿主取消`, `不要把本次取消视为业务失败`, `awaiting adapter`, `poll awaiting`, or `tool execution cancelled before completion` in the cleaned tool/runtime outcome paths.
- The focused compaction scan still reports internal `evidence_kind` typed fields and test dataclass construction. These are classified as Host typed contract / test fixture, not LLM output requirements or SystemMessage rendering.
- The final second required scan reports duplicate/governance terms broadly across Host/runtime/tests. `base/tools.md` `等待工具结果` remains business-readable allowed wording. Duplicate policy default messages are model-action guidance or internal diagnostics, not Host wait/poll/adapter leakage.

## Validation

Commands run:

```bash
source .venv/bin/activate && pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/runtime tests/fins tests/tools
```

Result: `1119 passed, 2 skipped, 3 warnings`.

```bash
source .venv/bin/activate && pytest tests/host/test_tooling_options.py tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_executor.py
```

Result: `116 passed`.

```bash
source .venv/bin/activate && rg -n "等待状态|未进入等待状态|后续调度|wait id|poll|adapter|user_visible_run_state|tool_source_text|accepted_evidence_material|宿主取消|不要把本次取消视为业务失败" dayu/config dayu/fins dayu/host dayu/runtime tests --glob '!**/*.html' --glob '!**/*.htm' --glob '!**/workspace/**'
```

Result: ran; remaining hits are internal Host/runtime wait/poll/adapter implementation, tests, or internal typed compact enums.

```bash
source .venv/bin/activate && rg -n "duplicate|governance|等待工具结果|等待结果" dayu/config dayu/fins dayu/host dayu/runtime tests --glob '!**/*.html' --glob '!**/*.htm' --glob '!**/workspace/**'
```

Result: ran; remaining hits are duplicate/governance implementation/tests plus allowed business-readable `等待工具结果` prompt text.

```bash
source .venv/bin/activate && rg -n "accepted_result_projection|AcceptedEvidenceEnvelope|AcceptedEvidenceToolQuery" dayu/host/run_input.py dayu/host/compact_material.py dayu/host/memory.py
```

Result: confirms P1-A projection source remains referenced by `run_input.py`, `compact_material.py`, and `memory.py`.

```bash
source .venv/bin/activate && pyright
```

Result: `0 errors, 0 warnings, 0 informations`.

```bash
git diff --check
```

Result: passed.

## Residual Risk

- Residual `poll` / `adapter` / `wait id` scan noise is expected in internal Host wait/poller/runtime code and tests. No P1-C LLM-facing prompt/schema/tool outcome owner remains unclassified.
- `ToolCancelledOutcome.reason` remains the public typed reason `host_cancelled`; P1-C only removes Host-governance prose defaults from LLM-facing message/hint and does not change P1-B durable cancellation truth.
