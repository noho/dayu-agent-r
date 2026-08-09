# PR-190 F13 S1 实现记录（2026-08-06）

## 状态与边界

- 当前基线：`62445b59c7a644133b15ca29d34c6e678aa2c047`。
- gate status：`accepted`；C1/C2/C3 checkpoint 与 S1 full-slice 均获两路 review 接受，无 unresolved blocking/high/medium finding。
- 本记录只描述 S1 步骤 1-6 的 atomic worktree 实现与验证，不包含 review、checkpoint 或 gate 裁决。
- 当前仍是未提交 worktree；未 stage、未 commit、未 push。
- 未提前实现 S2 的 public Tool Trace 新投影、README 或 integration 文案。

## C1：fresh v4 domain、structure 与 prompt

Production/config：

- `dayu/host/compaction.py`
  - 定义 `CompactInputV4`、七字段且 selector 无默认值的 `CompactCandidateV4`。
  - 定义 `CompactAcceptedEvidenceFactV4`、`CompactAcceptedReplacementV4`；`CompactAcceptedTruthV4` 显式分离 audit-only `proposal` 与 consumer truth `replacement`，并绑定 immutable boundary、coverage、policy audit 与 current input ref。
  - `PromptLocalProvenanceEntry` 为 frozen/slots、全字段无默认值；以 `canonical_evidence_refs` 替换旧 singular material-pack provenance 字段。
  - 删除 Python v3 compact contract、candidate-based policy/coverage audit 真源及兼容入口。
- `dayu/host/compact_structure.py`
  - 七字段 descriptor 是 template、prompt rules、formal JSON Schema 与 strict duplicate-key parser 的唯一结构 owner。
- `dayu/host/llm_compaction.py`
  - initial/repair 共用完整 v4 输入、七字段结构、计量规则与 whole-object repair；repair feedback 只投影有界 typed issue。
- `dayu/config/prompts/scenes/conversation_compaction_user.md`
  - 自足说明七字段、类型、必填性、允许 kind、retain/omit、combined item/char caps 数值例与最小 JSON。
  - LLM-facing 内容不暴露 canonical refs、source refs、request/boundary digest 或 Host 治理术语。

Owner tests：

- `tests/host/test_compaction_contract.py`
- `tests/host/test_llm_compaction.py`

覆盖 exact fields/defaults、frozen/slots、结构同源、strict parser、initial/repair prompt 自足与脱敏。

## C2：material、boundary、governance、replacement 与 schema-5 durable binding

Production：

- `dayu/host/compact_material.py`
  - current evidence 与 previous fact provenance 机械进入 boundary；previous replacement 逐 atom 保留 claim/refs。
- `dayu/host/context_governance.py`
  - acceptance 复用唯一 proposal-boundary validator；label existence、duplicate、kind 与 tuple canonical order 在 owner 边界 fail closed。
  - retain selector 原子复制 previous fact；new fact 只允许 current evidence support，并按 boundary 内 support entry 顺序合并 refs。
  - information、duplicate、caps 与 policy audit 全部基于 combined accepted replacement，retain-only 合法。
- `dayu/host/compact_payload.py`
  - schema-5 strict payload 自包含 `accepted_proposal`、`accepted_replacement`、internal source boundary、coverage、audit 与 aggregate refs。
  - parser 复用 proposal↔boundary↔replacement 唯一 binding validator，严格重验 retained/new fact 与其它四区 exact binding。
  - aggregate 必须精确等于 replacement 的 fact/entry ordered unique union；boundary 侧只校验 unique membership/subset，不施加跨 fact ordinal 单调约束。
- `dayu/host/compact_artifact.py`、`dayu/host/context_events.py`
  - artifact/EventLog 持久化 proposal digest 与完整 replacement；coverage/audit 只读 replacement。
  - `source_boundary_refs` 只由 `current_input_ref + covered boundary source_refs` 派生；evidence aggregate 直接来自 replacement。

Owner tests：

- `tests/host/test_compact_material.py`
- `tests/host/test_compact_artifact_store.py`
- `tests/host/test_compact_pipeline.py`
- `tests/host/test_compaction_terminal.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_compaction_contract.py`

覆盖 retain-only、previous support typed reject、combined duplicate/caps、无 evidence material 禁止 new fact、previous/current 空 refs fail closed、two-source union、retained+two-source-new 手工复算、durable claim/selection/context/refs exact tamper，以及 normal/reverse/three-fact shared dedup/retained+new/empty/out-of-bound/duplicate/mismatch aggregate。

手工复算用例：

- retained `P1` refs：`(previous-a, previous-b)`。
- new fact support `E1,E2` refs：`E1=(current-a, shared)`，`E2=(shared, current-b)`，逐 fact union 为 `(current-a, shared, current-b)`。
- replacement aggregate：`(previous-a, previous-b, current-a, shared, current-b)`。

## C3：rolling、multi-pass、Memory、reconnect、RunInput 与 call sites

Production：

- `dayu/host/compact_pipeline.py`
  - `CompactPipelineAcceptedPayloadInput.accepted_evidence_mapping_refs` 改为只读 property，从 `accepted_truth.replacement` 派生，删除显式 aggregate 双字段。
- `dayu/host/compaction_operation.py`
  - pass accepted truth 与 root revalidation 全部使用 replacement；retained selectors 按 root boundary ordered unique union。
- `dayu/host/memory.py`
  - Memory 逐 fact 读取 `accepted_replacement` atom 自己的 refs，不把 aggregate union 赋给每个事实。
- `dayu/host/run_input.py`、`dayu/host/dispatch.py`、`dayu/host/engine_ingest.py`
  - reconnect、ordinary dispatch、engine ingest 与 accepted result call sites 切换到 schema-5 replacement/read model。
- `tests/host/fake_compaction.py`
  - fake 显式输出 required selector；typed duplicate repair 先经过真实 governance reject，再按 `duplicate_semantic_item` 与 `evidence_facts` path 省略 routed pass facts并触发 root 重验，不使用 claim heuristic 预判。
- smoke/runtime：
  - `utils/smoke_host_public_conversation_memory_scenarios.py`
  - `utils/smoke_host_public_r03_semantic_ownership.py`
  - `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
  - input/output、required selector 与 exact root keys 已机械迁移到 v4；未扩展 runtime 语义。

其余迁移测试/helpers：

- `tests/host/memory_snapshot_factories.py`
- `tests/host/test_accepted_result_projection.py`
- `tests/host/test_compaction_cancellation_scope.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_proactive_compaction_operation.py`
- `tests/host/test_public_compact_smoke.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_tool_trace_queries.py`

覆盖 rolling 逐 fact provenance、Memory 多 fact 独立 refs、multi-pass selector union、typed repair、repair exhaustion/fallback、stale/late terminal、reconnect 与 public/runtime smoke assembly。

## 验证命令与结果

全部命令在 `source .venv/bin/activate` 后运行。

1. C1 focused：

   `pytest -q tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py`

   结果：`64 passed`。

2. C2 focused：

   `pytest -q tests/host/test_compact_material.py tests/host/test_compact_artifact_store.py tests/host/test_compact_pipeline.py tests/host/test_compaction_terminal.py tests/host/test_context_compact_events.py`

   结果：`215 passed`。

3. C3 focused/integration：

   `pytest -q tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_compaction_operation.py tests/host/test_proactive_compaction_operation.py tests/host/test_compaction_cancellation_scope.py tests/host/test_accepted_result_projection.py tests/host/test_tool_trace_queries.py tests/host/test_public_compact_smoke.py tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`

   结果：`595 passed, 1 skipped`；另有 3 条第三方 `edgar` deprecation warnings。

4. 目标 Ruff：对全部 S1 修改的 Python production/tests/helpers/utils 文件运行 `ruff check`。

   结果：`All checks passed!`。

5. 完整 pyright：`pyright`。

   结果：`0 errors, 0 warnings, 0 informations`。工具另提示可从 `1.1.409` 升级到 `1.1.411`，不影响本次结果。

6. 编译与 whitespace：

   `python -m compileall -q dayu/host tests/host tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py utils/smoke_host_public_conversation_memory_scenarios.py utils/smoke_host_public_r03_semantic_ownership.py`

   `git diff --check`

   结果：均通过、无输出。

7. structure 校验：对 `compact_output_json_schema_v4()` 运行 `Draft202012Validator.check_schema`，并验证 template JSON 经 strict parser round-trip。

   结果：`schema/template/parser validation: passed`。

8. AST 构造点清点：扫描 `dayu/tests/utils`。

   结果：`CompactCandidateV4=24`、`CompactEvidenceFactV4=33`、`CompactSourceBoundaryEntryV4=28`、`PromptLocalProvenanceEntry=5`；所有 required keyword 齐全，无 positional/missing 构造。

9. residue：

   `rg -n -i 'accepted_candidate|candidate_binding_v4' dayu tests utils --glob '*.py'`

   结果：零命中。

   active Python v3 symbol/schema 扫描只命中 `tests/service/test_host_assembly.py` 两条明确断言 v3 字符串不应进入 prompt 的 negative tests；它们不构造或读取 v3 contract。

## 已知风险与未覆盖项

- C3 有 1 个既有 skip；本 gate 未改变其 skip 条件。
- 测试输出中的 3 条 `edgar` deprecation warnings 来自第三方依赖。
- 上游 raw accepted-evidence typed atom/`RunInputMaterialBlock` 仍合法携带 singular `accepted_evidence_id`，用于 current evidence admission；S1 已确保它不进入 `PromptLocalProvenanceEntry` 或 accepted replacement durable/read-model 双真源，下游 compact provenance 使用 `canonical_evidence_refs`。
- README 与 public Tool Trace 最终语义/全文 residue 归 S2，本 gate 未修改。
- 实现 Agent 交付时未 stage、未 commit、未 push；后续 stage/commit/push 仅由 Controller 在 gate accepted 后执行。

## Review closeout

- C1：`docs/gateflow/pr-190-f13-s1-c1-checkpoint-20260806-162858.md`；AgentMiMo / AgentDS 均 accepted。
- C2：`docs/gateflow/pr-190-f13-s1-c2-checkpoint-20260806-164043.md`；AgentMiMo / AgentDS 均 accepted。
- C3：`docs/gateflow/pr-190-f13-s1-c3-checkpoint-20260806-165756.md`；AgentMiMo / AgentDS 均 accepted。
- full-slice：`docs/reviews/pr-190-f13-s1-full-review-mimo-20260806.md` 与 `docs/reviews/pr-190-f13-s1-full-review-ds-20260806.md` 均 accepted。
- AgentDS 初始 medium finding 经原 reviewer 窄 re-review dismissed：上游 singular accepted evidence id → 单元素 canonical tuple 是 accepted plan 要求的 owner-boundary机械投影；previous fact multi-ref路径与其分离。最终无 unresolved medium。
- 本 slice 仍只形成 tests/Host integration/Host smoke 证据；未执行真实 provider 或 interactive CLI，不能声称真实行为通过。
