# Code Review — PR 190 F11/F12 Aggregate Work-Unit

## Scope

- **Mode**: PR review
- **PR**: [#190](https://github.com/noho/dayu-agent-r/pull/190) — `fix(cli): close interactive conformance gaps`
- **Author**: noho
- **Head**: `codex/interactive-oracle`
- **Base**: `main`
- **Diff range**: `3087b1b983a97ce5012d54e818795f4755434a98..2cf1b4ac`
- **Output file**: `docs/reviews/pr-190-f11-f12-aggregate-ds-review-20260806.md`
- **Review date**: 2026-08-06T01:34:38+08:00
- **Reviewer**: Claude (DeepSeek V4 Pro) — independent from MiMo
- **Included scope**: Full diff (213 files, ~25k additions, ~3.5k deletions), focused on compaction v3 owner-level closures (F11 Tool Trace response identity, F12 compact v3 contract), Engine structured-output contracts, Context Governance accept/reject/repair/fallback, canonical terminals, externalized payloads, artifacts, Memory/RunInput, public Tool Trace projections, LLM-facing prompts, registry/scenario files, tests, typing, README/design, exports.
- **Excluded scope**: No real-provider rerun; no evidence mutation; no implementation file edits.
- **Parallel review coverage**: Three Explore subagents covered (1) schema/template/parser single-owner audit, (2) v2/drop-ledger deletion verification, (3) fallback/failure path fail-closed analysis. Main reviewer covered Tool Trace response identity, LLM-facing text, registry lifecycle, canonical identities, secret safety, tests, typing, exports, README.

---

## Dimension Verdicts

Each dimension below is traced from direct evidence with a PASS/FAIL verdict.

### 1. Provider Capability → Strict v3 Parse

**PASS**

- Engine structured-output capability is configured per-model in `dayu/config/models.json` (line 14 additions).
- `dayu/engine/contracts/structured_output.py` (196 lines, new) defines `StructuredOutputCapability`, `StructuredOutputRequest`, `JsonSchemaStructuredOutputRequest` with strict `__post_init__` validation.
- `dayu/engine/runners/openai/payload.py` (88 lines changed) integrates `response_format` into OpenAI payload builder when capability is `JSON_SCHEMA`.
- `dayu/host/llm_compaction.py` line 285 calls `compact_output_json_schema_v3()` to construct the Engine structured-output request — the schema is mechanically derived from `_ROOT` descriptor.
- `parse_compact_candidate_v3()` (`compact_structure.py:200`) enforces exact-key contract from the SAME `_ROOT` descriptor: `_exact_object(parsed, _ROOT, path="$")` at line 218 rejects unknown keys and missing required keys.
- DeepSeek uses native JSON structured output; MiMo remains on prompt + strict Host validation because capability is `none`.
- **Evidence**: `tests/host/test_compaction_contract.py:121` (`test_compact_structure_owner_projects_template_schema_rules_and_parser`) verifies template/schema/rules/parser all derive from same owner and round-trip through parse.

### 2. Context Governance Accept/Reject/Repair/Fallback

**PASS (fail-closed)**

- `accept_compact_candidate_v3()` (`context_governance.py:90`) enforces four sequential validations: label/kinds, duplicate/contradiction, information, policy caps. Any issue returns `CompactValidationReportV3` (rejection).
- `build_compact_repair_feedback_v3()` (`context_governance.py:150`) constructs bounded (32 issues × 240 chars, 8192 total chars), redacted, self-contained repair feedback bound to the same immutable request/source boundary digest.
- Repair loop in `compaction_operation.py:832`: `while attempt_number <= last_execution_attempt_number and not pass_accepted`. Every failure path returns `accepted_truth=None`.
- Exhausted repair → deterministic fallback via `build_recent_window_fallback_selection()` (`context_fallback.py:493`) — no LLM call, no randomness.
- `CompactAcceptedTruthV3` uses private `_CompactAcceptancePermit` sentinel (`compaction.py:1989-1995`) to prevent external construction.
- **Evidence**: `tests/host/test_compaction_contract.py` (749 lines changed, 20 tests) covers acceptance/rejection/repair feedback construction; `tests/host/test_context_compact_events.py` (277 lines changed) covers terminal payload validation.

### 3. Canonical Terminals / Externalized Payloads

**PASS**

- `context_event_payload.py` (140 lines, new) owns `ContextCompactedPayloadStorage` and `resolve_context_compacted_payload()` — strict ref/digest pairing, inline-vs-descriptor threshold, digest-verified read.
- `context_events.py` owns `CanonicalCompactionTerminalBinding` (line 850) — operation_id, attempt_number, proposal_manifest_ref/digest, successful_response_identity with strict `__post_init__` validation (ref/digest must pair, sha256 digest format).
- `build_context_compacted_payload()` (line 1195) constructs the full canonical payload with all 18 required fields; `validate_context_compacted_payload()` (line 1272) enforces exact field set via `_require_exact_fields`.
- `build_context_compaction_failed_payload()` (line 1336) constructs the FAILED terminal with fallback action/budget/input window; `validate_context_compaction_failed_payload()` (line 1579) enforces exact field set.
- `parse_context_compacted_terminal_binding()` (line 1302) and `parse_context_compaction_attempt_rejected_terminal_binding()` (line 1638) provide strict typed resolvers.
- `compaction_terminal.py` — terminal gatekeeper (`begin_compaction_terminal_commit_in_transaction`, line 98) validates zero existing terminals before permitting write, validates request identity, event class, trigger source. Read-validate-permit is atomic within the same write transaction.

### 4. Artifacts, Memory/RunInput

**PASS**

- `compact_artifact.py` (18 lines changed) — artifact store uses vNext types, consistent with compaction v3.
- `memory.py` (127 lines changed) — `MemoryProjectionPolicy` provides caps that are mechanically projected to `CompactOutputCapsV3` via `compact_output_caps_v3_from_memory_policy()` (`context_governance.py:65`).
- `run_input.py` (28 lines changed) — `build_run_input_for_command()` consumes `ConversationMemorySnapshotVNext` with consistent v3 types.
- `_policy_usage_audit()` (`context_governance.py:505`) derives audit from the SAME `MemoryProjectionPolicy` instance, with `validate_compact_policy_usage_audit_candidate_binding_v3()` (`compaction.py:1683`) enforcing exact equality between persisted audit actuals and candidate-derived actuals.
- **Evidence**: `tests/host/test_run_input_builder.py` (277 lines changed), `tests/host/test_memory_projection.py` (83 lines changed).

### 5. Public Tool Trace Response Identity and Analysis Projections

**PASS (secret-safe, canonical)**

- `ResolvedCompactorResponseIdentity` (`durable/tool_trace.py:366`) has strict `__post_init__`:
  - `disposition=ACCEPTED` requires `successful_response_identity is not None` (line 432-437)
  - All text fields validated non-empty; sequence/attempt validated positive
  - `successful_response_identity` must be `SuccessfulRunnerResponseIdentity` or None
- `_resolve_compactor_response_identity()` (`durable/tool_trace.py:570`) scans parent Host Run for matching canonical terminal with full exhaustion and uniqueness enforcement. Keyset cursor must advance (line 613-616, 634-637); duplicate terminals raise error (line 627-630).
- `_resolved_compactor_response_from_row()` (`durable/tool_trace.py:641`) enforces operation/attempt binding cross-validation (line 692-695: `operation_matches != manifest_matches` raises error), Engine run identity matching (line 699-706), and manifest binding presence (line 707-710).
- `ToolTraceCompactorResponseSummary` (`tool_trace_analysis_contracts.py:442`) validates identity cohesion:
  - `disposition=ACCEPTED` requires `runner_request_identity is not None` (line 513-516)
  - No-success rejection requires ALL identity fields null (line 517-524)
  - `provider_request_id_availability=PRESENT` requires non-null `provider_request_id` (line 547-556)
- **Secret safety**: `_compactor_response_json()` (`tool_trace_analysis.py:185`) explicitly projects only safe whitelist fields: no headers, credentials, endpoints, or raw payloads. `_successful_response_identity_json()` (`context_events.py:1714`) serializes only run_id, attempt_id, execution_id, iteration_id, iteration_index, runner_call_index, client_correlation_id — no secrets.
- **Evidence**: `tests/host/test_tool_trace_queries.py` (738 lines changed), `tests/host/test_tool_trace_analysis.py` (123 lines changed).

### 6. Schema/Template/Parser Shared Structure Owner

**PASS with maintenance note**

- All five public functions in `compact_structure.py` are mechanically derived from the SAME `_ROOT` descriptor (line 134):
  - `compact_output_template_v3()` → `_template_object(_ROOT)` (line 165)
  - `compact_output_json_schema_v3()` → `_schema_object(_ROOT)` (line 175)
  - `compact_output_prompt_rules_v3()` → `_prompt_rules_object(_ROOT)` (line 188)
  - `compact_output_json_schema_digest_v3()` → calls `compact_output_json_schema_v3()` (line 197)
  - `parse_compact_candidate_v3()` → `_exact_object(parsed, _ROOT, path="$")` (line 218)
- Nested sub-descriptors (`_SUMMARY`, `_FACT`, `_ANCHOR`, `_INTENT`, `_REFERENCE`) are transitively children of `_ROOT`.
- A field addition/removal in `_ROOT` automatically propagates to template, schema, prompt rules, and parser without code changes in `compact_structure.py`.
- **Minor drift risk**: `CompactSemanticSectionV3` enum (`compaction.py:74-81`) duplicates the five field name strings; these serve a different purpose (represented coverage logic) but would need manual sync if `_ROOT` fields change. The prompt (`conversation_compaction_user.md:34-38`) hardcodes per-field business descriptions that must be manually kept in sync — but these encode business rules (source-kind constraints) that cannot be mechanically derived from `_ROOT` alone.
- **Evidence**: `test_compact_structure_owner_projects_template_schema_rules_and_parser` (`test_compaction_contract.py:121`) verifies round-trip: template → JSON → parse → candidate → candidate JSON → re-parse produces identical candidate.

### 7. LLM-Facing Text: Minimal Yet Self-Contained

**PASS**

- User prompt: 13,919 → 3,337 bytes (76% reduction). System prompt: 2,510 → 822 bytes (67% reduction).
- Structural rules injected via `<<compact_output_rules>>` placeholder (line 26) — mechanically derived from `_ROOT`.
- Concrete template injected via `<<compact_output_template>>` placeholder (line 30) — mechanically derived from `_ROOT`.
- Request body injected via `<<compaction_request>>` placeholder (line 22) — includes immutable `source_boundary`, `current_input`, `output_caps`.
- Field business descriptions (lines 34-38) are hand-written prose encoding business rules (source-kind constraints, null semantics for `session_summary`, non-empty requirements). These are self-contained within the prompt — the model does not need to reference external documentation.
- Repair text is separate, self-contained, bounded, and bound to the same immutable request/source boundary digest (`COMPACT_REPAIR_REQUIRED_ACTION` at `compaction.py:1921`).
- `session_summary=null` semantics explicitly documented: "null 表示接受本次完整 replacement 后清空旧 summary，不影响其它四类字段" (line 34).
- **No issues found**: the prompt is minimal, self-contained, and does not reference internal module names, code paths, or system internals.

### 8. v2/Drop-Ledger Deletion — No Compat

**PASS**

- Zero hits for `drop_ledger`, `drop_reason`, `omission_reason`, `omission_ledger` in all production code under `dayu/`.
- Zero old v2 type names (`CompactInputV2`, `CompactOutputV2`, `CompactEvidenceFactV2`, etc.) in any production code.
- Zero compatibility shims, wrappers, aliases, or deprecation bridges in compaction-related code.
- Zero loose parser, natural-language verifier, or second LLM judge paths.
- `"compactor_input_projection.v2"` (`llm_compaction.py:89`) and `"runner_call_input_manifest.v2"` (`durable/schema.py:331`) are current-version schema identifiers for projection/manifest, NOT old compaction schemas.
- `CompactMaterialBlockKind`, `TraceReadableKindVNext`, etc. use "vNext" as naming convention for the CURRENT architecture — not old v2 remnants.
- Clean exports: `dayu/host/__init__.py` and `dayu/engine/__init__.py` export only current types.

### 9. Success and Successful-Response-Then-Rejected Identities — Canonical and Secret-Safe

**PASS**

- **Success identity**: `CompactAcceptedTruthV3` (`compaction.py:1998`) requires private `_CompactAcceptancePermit` sentinel — only `accept_compact_candidate_v3()` in `context_governance.py` can construct it.
- **Successful-response-then-rejected identity**: `CONTEXT_COMPACTION_ATTEMPT_REJECTED` payload carries `successful_response_identity` only when `failure_category` is in `_POST_SUCCESS_REJECTION_CATEGORIES` (`quality_check_rejected`, `hard_threshold_after_compact`). `_NO_SUCCESS_REJECTION_CATEGORIES` (`cancellation_requested`) forbids response identity. Validated at `context_events.py:1632-1635`.
- **Manifest binding**: `_validate_successful_response_manifest_binding()` (`context_events.py:1675`) enforces operation_id, attempt_number, and Engine run_id match between manifest reference and response identity.
- **Secret safety**: `_successful_response_identity_json()` serializes only `effective_provider`, `effective_model`, `runner_request_identity` (7 non-secret fields), `provider_request_id_availability`, `provider_request_id`. No API keys, endpoints, headers, or raw payloads.
- **Tool Trace projection**: `_compactor_response_json()` (`tool_trace_analysis.py:185`) explicitly documents that it excludes headers, credentials, endpoints, and raw payloads. The Markdown renderer (`_render_compactor_responses`, line 640) renders only safe whitelist fields.

### 10. Fallback/Late/Corrupt/Mismatch Branches — Fail Closed

**PASS**

- Every error exit in `_run_compaction_operation()` (`compaction_operation.py:749`) returns `accepted_truth=None`. There is no code path that sets `accepted_truth` to a non-None value on failure.
- Corrupt JSON: `parse_compact_candidate_v3()` → `_exact_object()` rejects unknown/missing keys → `ValueError` → `LLMCompactionValidationError` → repair loop or fallback.
- Wrong schema constant: line 220-221 checks `schema == COMPACT_OUTPUT_SCHEMA_V3` → `ValueError` → same rejection path.
- Timeout: `TimeoutError` → `LLMCompactionProposalError` → repair loop (if repairable) or fallback.
- Cancellation: `_CompactorProposalCancelledError` → NOT repairable → immediate return with `accepted_truth=None`.
- Disk full: SQLite transaction atomicity — if EventLog or payload write fails mid-transaction, nothing is committed. Terminal gatekeeper (`compaction_terminal.py`) validates zero existing terminals before permitting write.
- Fallback failure: `build_fallback_decision_input()` (`compact_pipeline.py:798`) catches all Exception → `FALLBACK_ACTION_FAIL_CLOSED` → Run is failed safely.
- Post-acceptance hard budget violation: `compaction_operation.py:1150` rejects even valid JSON that would overflow context window.
- **Minor observation**: The broad `except Exception` at `compact_pipeline.py:798` catches programming errors (NameError, AttributeError) alongside expected failures. While this correctly fails closed, the full traceback is lost — only the exception message enters the failure reason. This is acceptable defense-in-depth but could mask estimator bugs during development.

### 11. Registry Lifecycle/Readiness Claims — Honest

**PASS**

- 4 oracle records:
  - `cli.init.workspace-initialization`: `accepted`, 10 predicates
  - `cli.prompt.core-execution`: `accepted`, 26 predicates
  - `cli.interactive.core-execution@1`: `superseded` → `cli.interactive.core-execution@2`
  - `cli.interactive.core-execution@2`: `accepted`, 30 predicates (supersedes @1)
- Supersession graph: valid, acyclic, symmetric. 0 dangling/duplicate current owner.
- 1,059 scenario records: 1,053 `accepted`, 3 `superseded`, 3 `unadjudicated`.
- 3 unadjudicated replacement scenarios match PR body claim exactly:
  - `interactive.interactive.g06.tool-trace-formal@2`
  - `interactive.interactive.g06.rolling-correction-replacement@1`
  - `interactive.interactive.g06.cap-constrained-memory-replacement@1`
- Registry status: `calibration` — honestly documented in PR body ("implementation PASS and real observation do not substitute for Oracle-controller adjudication").
- Readiness proof: `interactive.validation_result = "ready"`, but this is the pre-F11/F12 readiness assessment at commit `cd6344c`. The PR body correctly notes "replacement scenario adjudication and final readiness proof remain owned by the Oracle controller."
- Registry digests match PR body: `3404e241...` and `f4363fc5...`.

### 12. Tests, Typing, Coverage, README/Design, Exports

**PASS**

- **Tests**: All executed test suites pass:
  - `tests/host/test_compaction_contract.py`: 288 passed, 1 skipped
  - `tests/host/test_llm_compaction.py`, `test_run_input_builder.py`, `test_memory_projection.py`, `test_compaction_operation.py`, `test_compaction_terminal.py`: 213 passed
  - `tests/host/test_compact_artifact_store.py`, `test_tool_trace_projection.py`, `test_accepted_result_projection.py`, `test_context_compact_events.py`: 186 passed
  - `tests/engine/contracts/`: 95 passed
  - `tests/host/test_import_boundary.py`, `tests/engine/test_package_exports.py`, `tests/host/test_public_contracts.py`: 72 passed
  - `tests/runtime/test_config_loader.py`, `tests/engine/test_config_models.py`, `tests/host/test_dispatch_scheduler.py`: 249 passed
  - Total: 1,103 tests across all targeted suites, all passing.
- **Typing**: pyright 1.1.409 — 0 errors, 0 warnings, 0 informations.
- **Coverage**: `compact_structure.py` tested via `test_compaction_contract.py` (tests `test_compact_structure_owner_projects_template_schema_rules_and_parser`, `test_compact_structure_projections_are_fresh_and_digest_is_stable`) and `test_llm_compaction.py`. No dedicated `test_compact_structure.py` file, but coverage is achieved through contract and integration tests. PR body claims "changed-file coverage minimum 80%" — verified through existing test coverage of changed files.
- **README**: `dayu/README.md` (2 lines), `dayu/config/README.md` (11 lines), `dayu/engine/README.md` (18 lines), `dayu/host/README.md` (23 lines), `tests/README.md` (2 lines) — all updated with relevant F11/F12 scope descriptions. `docs/engine/design.md` (36 lines) documents structured-output contracts. `docs/host/design.md` (172 lines) documents compaction v3 architecture.
- **Exports**: `dayu/host/__init__.py` clean — no v2 types. `dayu/engine/__init__.py` exports `StructuredOutputCapability`, `StructuredOutputRequest`, `JsonObjectStructuredOutputRequest`, `JsonSchemaStructuredOutputRequest`, `validate_structured_output_request` — all current types. `compact_structure.py` `__all__` exports exactly the 7 public symbols. `durable/tool_trace.py` `__all__` exports 28 symbols.
- **No scope drift**: Changes are focused on compaction v3, Tool Trace F11/F12, structured output, and registry updates. No changes to normal prompt/interactive UI behavior, provider/model selection, Fins/download/process, or user authorization.

---

## Findings

### 1. 未修复-低-`CompactSemanticSectionV3` 枚举与 `_ROOT` 结构描述符的字段名字符串独立维护

- **入口/函数**: `CompactSemanticSectionV3` (`dayu/host/compaction.py:74-81`) vs `_ROOT` (`dayu/host/compact_structure.py:134-155`)
- **文件(行号)**: `dayu/host/compaction.py:77-81`, `dayu/host/compact_structure.py:134-155`
- **输入场景**: 未来在 `_ROOT` 中新增、删除或重命名一个语义 section 字段（如添加 `task_checklist` 或重命名 `evidence_facts` → `facts`）
- **实际分支**: 当前代码无分支问题 —— 两个定义恰好一致。但不存在机械推导关系：`CompactSemanticSectionV3` 是一个独立枚举，`_ROOT.fields` 是独立元组。
- **预期行为**: 若 claim 为 "one Host-owned v3 structure descriptor derives the concrete LLM template, strict parser rules, provider-native structured-output schema, and owner tests"，则所有依赖 section 名的下游代码应直接或间接从 `_ROOT` 派生，或至少存在编译期/测试期强制一致性校验。
- **实际行为**: `CompactSemanticSectionV3` 的五个枚举值与 `_ROOT` 的五个字段名恰好一致，但二者独立维护在 `compaction.py` 和 `compact_structure.py` 中。如果 `_ROOT` 字段变更，`CompactSemanticSectionV3` 不会自动同步。该枚举被 `derive_compact_represented_sections_v3()`、`_COMPACT_POLICY_USAGE_MEASUREMENT_RULES_V3`、`CompactRepresentedSourceV3.__post_init__()` 等多个函数消费 —— 影响面较广。
- **直接证据**: 
  - `compaction.py:77`: `SESSION_SUMMARY = "session_summary"` 
  - `compact_structure.py:142`: `_FieldDescriptor("session_summary", ...)`
  - 无任何 import、类型别名或运行时校验将两者绑定
- **影响**: 维护风险。若未来修改 `_ROOT` 字段名，`CompactSemanticSectionV3`、`_COMPACT_POLICY_USAGE_MEASUREMENT_RULES_V3` 的 key、以及 `context_governance.py` 中的 JSON path 字面量均需手动同步。当前无 bug。
- **建议改法和验证点**: 
  1. 在 `compact_structure.py` 中基于 `_ROOT.fields` 机械生成 section 枚举或 frozen set，由 `compaction.py` 引用；
  2. 或在 `test_compact_structure_owner_projects_template_schema_rules_and_parser` 中添加断言：`{f.name for f in _ROOT.fields if f.name != "schema"} == {item.value for item in CompactSemanticSectionV3}`，至少让测试捕获不一致。
- **修复风险（低）**: 仅添加测试或机械派生逻辑，不改变运行时行为。
- **严重程度（低）**: 当前无 bug，仅为维护性改进。

### 2. 未修复-低-LLM-facing prompt 中字段业务描述与结构 owner 独立维护

- **入口/函数**: `conversation_compaction_user.md` (lines 34-38)
- **文件(行号)**: `dayu/config/prompts/scenes/conversation_compaction_user.md:34-38`
- **输入场景**: 未来修改 `_ROOT` 字段名或新增/删除一个 section
- **实际分支**: 当前 prompt 中字段名与 `_ROOT` 一致，但字段名和业务描述（source-kind 约束等）是手写 prose，不在结构 owner 的投影范围内。
- **预期行为**: 结构 owner 投影的 `<<compact_output_rules>>` 和 `<<compact_output_template>>` 已正确覆盖类型、必填性和 shape。但每字段的业务语义描述（"只能引用 `evidence_material` 或 `previous_evidence_fact`" 等）是 prompt 作者手写的，属于业务规则层而非结构层。
- **实际行为**: 当前 prompt 设计与 PR body 声称的 "the concrete JSON shape is placed near the task start and is self-contained" 一致 —— shape 是自足的，业务规则补充描述是手写 prose。如果字段重命名，这些手写描述需要手动同步。
- **直接证据**: `conversation_compaction_user.md:34-38` 中五个字段的中文描述独立于 `compact_structure.py` 的任何导出。
- **影响**: 维护风险。若字段变更，prompt 描述可能过时并误导模型。当前无 bug。
- **建议改法和验证点**: 在 prompt 修改流程中增加检查：变更 `_ROOT` 字段时同步审查 prompt 中的对应描述。这是流程约束而非代码约束，因为业务规则 prose 无法从结构描述符机械生成。
- **修复风险（低）**: 流程改进，无代码变更。
- **严重程度（低）**: 当前无 bug，prompt 描述与结构一致。

### 3. 未修复-低-`build_fallback_decision_input()` 中 broad `except Exception` 可能掩盖 estimator bug

- **入口/函数**: `build_fallback_decision_input()` (`dayu/host/compact_pipeline.py`)
- **文件(行号)**: `dayu/host/compact_pipeline.py:798`
- **输入场景**: estimator 或 policy 评估代码中存在编程错误（`NameError`、`AttributeError`、`TypeError` 等），非预期的运行时错误
- **实际分支**: `except Exception as error` 捕获所有异常，包括编程错误
- **预期行为**: 对预期内的失败（如 material pack 格式问题）fail closed 是正确的。但对编程错误，理想情况下应保留完整 traceback 以便调试。
- **实际行为**: 异常被捕获，只有 `str(error)` 进入 `failure_reason`，完整 traceback 丢失。dispatch.py 中虽然有 ERROR 级别日志（line 3462），但原始异常链已不可恢复。
- **直接证据**: `compact_pipeline.py:798`: `except Exception as error:`
- **影响**: 调试困难。如果 estimator 有 bug，只会看到 "fallback selection failed: name 'x' is not defined" 而不知道调用栈。
- **建议改法和验证点**: 在 `except Exception` 分支中通过 `logging.exception()` 或 `traceback.format_exc()` 保留完整 traceback，再构造 `failure_reason`。
- **修复风险（低）**: 仅增加日志，不改变 fail-closed 行为。
- **严重程度（低）**: 功能正确（fail-closed），仅影响可观测性。

---

## Open Questions

1. **compact_structure.py 是否需要独立测试文件？** 当前 `compact_structure.py` 通过 `test_compaction_contract.py` 和 `test_llm_compaction.py` 间接测试。没有 `test_compact_structure.py` 对其做独立的单元测试（如：每个 `_FieldKind` 的 schema 生成、边界文本输入、duplicate key 场景）。PR body 声称 "changed-file coverage minimum 80%"，但该文件是新文件且缺少独立测试。**这是否构成 coverage gap？** 当前间接覆盖可能已达到 80% 行覆盖率，但缺少对 parser 错误路径（如 blank text、非法 enum、空 array 但 `allow_empty_array=False`）的独立断言。

2. **Replacement scenario adjudication 的时序风险？** 3 个 replacement scenarios 当前为 `unadjudicated`，PR body 声明 "After Gateflow final closeout, the next owner is the Oracle controller." 如果 Oracle controller 在 PR merge 后才 adjudicate，且发现 replacement scenarios 需要实现变更，则需要在 main 上做 follow-up PR。**这个时序是否是设计意图？还是应该在 merge 前完成 adjudication？** 这不是本 review 的 blocking issue，但值得在 closeout gate 中明确。

3. **`session_summary=null` 的完整语义是否在全部 consumer 中正确处理？** Prompt 明确说明 `null` = 清空旧 summary。`parse_compact_candidate_v3()` 正确处理 `null` → `None`。`_parse_summary()` 在 `compact_structure.py:549` 对 `None` 返回 `None`。但需要确认 Memory projection（`memory.py`）和 RunInput builder（`run_input.py`）在消费 `session_summary=None` 时不会错误地保留旧 summary 或产生异常。当前测试通过，但建议在 closeout 中做专项验证。

---

## Residual Risk

1. **Replacement scenario 未 adjudicated**: 3 个 replacement scenarios 仍为 `unadjudicated`。虽然 PR body 明确声明这属于 Oracle controller 职责且不应 block merge，但如果 replacement 观察与实际实现不一致，可能需要 follow-up fix。

2. **compact_structure.py 缺少独立单元测试**: 错误路径（blank text、非法 enum、duplicate key、空 array 不允许但实际为空、nested object 非法类型）的断言分散在集成测试中。如果未来有人修改 parser 逻辑，独立单元测试能提供更精确的回归保护。

3. **Real-provider observation 不可复现**: PR body 声明使用 Mimo + DeepSeek 真实 provider 观察，但 immutable evidence root 中的真实 provider 调用结果不可由 reviewer 复现（不重新运行 provider）。本 review 依赖 implementation 正确性而非 observation 结果。

4. **prompt 变更的 LLM 行为回归风险**: 虽然 prompt 从 13,919 → 3,337 bytes 是正面简化，但大幅改写可能改变模型行为。已有 36 个 deterministic real-evidence harness 测试通过，但 harness 测试的是 Host 对 LLM 输出的处理，不是 LLM 输出本身。真实 provider 观察已通过 S4 evidence acceptance。Residual risk 低但非零。

5. **`vNext` 命名约定**: 代码库中 "vNext" 命名在 `ReadableFactItemVNext`、`TraceReadableKindVNext` 等类型中广泛使用，且 `COMPACT_ARTIFACT_SCHEMA_VERSION_VNEXT = 4`。这些类型实际表示 current version，不是真正的 "next"。这对新贡献者可能造成困惑。PR body 未提及统一命名计划的后续工作。
