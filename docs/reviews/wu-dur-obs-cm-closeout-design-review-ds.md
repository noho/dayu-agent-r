# WU-DUR-P01 / WU-OBS-P00 / WU-CM-01-F02 / WU-CM-01-F01 — Slice 0.5 Design Review

## Gate Identity

- **review gate**: Slice 0.5 design review
- **reviewer**: AgentDS
- **review target**: `docs/host/design.md` current working-tree diff vs HEAD (`c1e9de3f`)
- **plan artifact**: `docs/host/wu-dur-obs-cm-closeout-plan.md`
- **slice 0 implementation artifact**: `docs/reviews/wu-dur-obs-cm-closeout-slice0-implementation-codex.md`
- **control doc**: `docs/host/issues-implementation-control.md`
- **review stance**: adversarial design review — 判断 Slice 0 写回是否足够成为 Slice 1-7 的设计真源

## Scope

本 review 只审 actual `design.md` diff 是否等价或更严格地实现 accepted plan appendix。不重新审 plan；不实现、fix、commit、push、PR；不进入 Slice 1-7。

## Acceptance Criteria Check

### AC1: Contract Completeness

| contract | field name | type | required | semantics | digest/ref boundary | validation rule |
|---|---|---|---|---|---|---|
| `RunnerCallInputAssemblyManifest` | 19 fields | ✓ typed | ✓ per-field | ✓ | ✓ | ✓ |
| `RunnerCallMessageEntry` | 11 fields | ✓ typed | ✓ per-field | ✓ | ✓ | ✓ |
| `ProjectorMetadata` | 6 fields | ✓ typed | ✓ per-field | ✓ | ✓ | ✓ |
| `ToolCallArgumentsAtom` | 14 fields | ✓ typed | ✓ per-field | ✓ | ✓ | ✓ |
| Tool Trace signal | 11 fields | ✓ typed | ✓ per-field | ✓ | ✓ | ✓ |
| `RunnerCallReconstructionDiagnostic` | 10 fields | ✓ via enumeration | ✓ narrative | ✓ | ✓ | ⚠ narrative form (see F-001) |
| `CompactorRunnerCallIdentity` | 9 fields | ✓ typed | ✓ per-field | ✓ | ✓ | ✓ |

**Result**: PASS — all seven contracts present with equivalent or stricter field definitions.

### AC2: Inline/Ref Boundary And Descriptor Kinds

- `payload_inline_threshold_bytes` 复用: ✓ 已在 design.md §13.1 定义为 construction root 注入值；diff 中 `ToolCallArgumentsAtom.arguments_storage_kind` 和 manifest 存储形态均引用该阈值。
- Descriptor kinds: ✓ `runner_call_input_manifest`、`runner_call_projection_artifact`、`tool_call_arguments_json`、`tool_call_semantic_query_text`、`compactor_input_projection` 五种均已明确。

**Result**: PASS.

### AC3: `RUNNER_CALL_INPUT_ASSEMBLED` State Side Effect

- 矩阵行: "无 Run / Attempt 状态副作用；不参与 terminal decision、recovery scan、memory projection、dispatch decision 或 lifecycle transition" ✓
- §23.1: "该 event 没有 Run / Attempt 状态副作用，不驱动 recovery、memory、lifecycle、terminal decision 或 dispatch decision" ✓
- Hot payload: 仅 scope + identity + manifest ref/digest + validation_status ✓

**Result**: PASS.

### AC4: RunnerCallKind / RunnerCallTriggerReason Non-overlapping Coverage

- `RunnerCallKind` (5 values): `initial_user_dispatch`, `followup_user_dispatch`, `tool_result_continuation`, `post_compaction_dispatch`, `compactor_proposal` — 互不重叠 ✓
- `RunnerCallTriggerReason` (11 values): `initial_user_input`, `followup_user_input`, `tool_results_available`, `force_answer_after_tool_limit`, `finish_reason_length_continuation`, `host_retry`, `host_replay`, `host_resume`, `context_compaction_completed`, `context_compaction_repair_attempt`, `context_compaction_retry_attempt` — 互不重叠 ✓
- Design rule: "forced answer、length continuation、retry/replay/resume 只作为 trigger reason，不挤入 kind" ✓
- Coverage assertion: "该分类必须覆盖 ordinary initial / follow-up、tool result continuation、post compaction dispatch、compactor proposal、retry / replay / resume、forced answer 与 length continuation" ✓
- ⚠ retry/replay/resume 到 kind 的映射未给出显式示例（见 F-002）

**Result**: PASS.

### AC5: Engine vs Host Ownership

- design.md L10 (pre-existing): "Engine 只执行单次 AgentRunRequest，不拥有 Session / Run 生命周期，不持久化 Host 状态" ✓
- design.md L40 (pre-existing): "Engine 不读取 Host durable store，不理解 Host policy，不管理 Session / Run / Attempt" ✓
- Manifest table: `runner_call_index` 标记 "Host-owned"；`iteration_id` / `iteration_index` 标记 "Engine-owned observation" ✓
- §23.1 明确 manifest refs/digests/source refs 为 Host 产出 ✓

**Result**: PASS.

### AC6: Compactor Parent/Self Identity

- `CompactorRunnerCallIdentity` 9 字段完整 ✓
- 关系声明: "补充 `CONTEXT_COMPACTED`，不替代 compact truth" ✓
- `CONTEXT_COMPACTED` 继续拥有 accepted compact artifact refs ✓
- accepted event 引用 accepted proposal manifest；rejected attempts 通过 typed diagnostics 引用各自 manifest ✓
- 明确 "任何 rejected proposal content、中间 transient artifact 或 compactor input projection 都不能进入 Conversation Memory" ✓

**Result**: PASS.

### AC7: Tool Trace Read Model

- §14.1 (pre-existing): "Tool trace 是 EventLog 派生 projection，不是 Host durable truth" ✓
- §14.1 diff: "Tool Trace 对 runner-call reconstruction 的消费边界固定为 read-only signal" ✓
- §14.1 diff: "这些字段只是 projection copy，不是 recovery、memory、dispatch 或 Run 状态真源" ✓

**Result**: PASS.

### AC8: LLM-facing Boundary

- §24.2 diff: "compact material / prompt / query_text 的 LLM-facing 语义必须自解释...不得暴露 tool_call_id、EventLog id、payload ref、artifact ref、digest、cursor、projection checkpoint、policy 名称..." ✓
- §23.1 diff: "LLM-facing compact material 或 prompt 不得暴露 projector id、schema version、digest 或 source contract refs" ✓
- Scalar aliases: "HostInternalRef...永远不进入 LLM-facing material" ✓
- §14.1 diff: "compact LLM-facing text 只能得到业务中性的 unavailable wording，不能得到 refs、digests、event ids、cursors 或 diagnostic ledger details" ✓
- F02 root cause statement explicit ✓

**Result**: PASS.

### AC9: Hidden Risks

- Messages dump 风险: manifest "不内联 full messages、完整 prompt、完整 compact material、完整 memory snapshot" ✓
- Untyped bag 风险: "不得以 raw provider dict、untyped payload bag 或 Python object 进入 Host manifest" ✓
- 兼容旧 schema 风险: plan 已明确 fresh schema only；design.md 为 forward-looking contract 定义，无兼容语言 ✓
- 工具参数伪装风险: §13.3 "没有 semantic query 是合法但可诊断状态" ✓

**Result**: PASS.

## Findings

### Blocking Findings

无。

### Non-blocking Findings

#### F-001 (non-blocking): `RunnerCallReconstructionDiagnostic` 字段契约使用叙事形式而非结构化表格

- **位置**: §14.1 diff, L92-98
- **观察**: Plan appendix 对 RunnerCallReconstructionDiagnostic 给出了独立的结构化字段表（10 rows, 5 columns）。design.md 使用叙事段落描述字段名、允许值、条件必填性。内容等价 — 所有 10 个字段均列出，status/reason/missing_atom_kind/missing_ref_kind/consumer_boundary 的枚举值均已闭合。
- **偏差**: `observed_count`、`expected_count`、`observed_digest`、`expected_digest` 的条件必填性（"required for count mismatch"、"required for digest mismatch"）在叙事形式中未逐字段显式标注，需从语义推导。Slate 1-7 实现者需自行推断：status=mismatch + reason=message_count_mismatch 时 observed_count/expected_count 必填。
- **建议**: Slice 4（Tool Trace signal projection）实现前，确认 `RunnerCallReconstructionDiagnostic` 的实现 dataclass 包含显式的 conditional required validation，并在 focused test 中验证。
- **裁决**: accepted — 内容等价，叙事形式不阻塞实现。

#### F-002 (non-blocking): Retry/replay/resume 到 `RunnerCallKind` 的映射缺少显式示例

- **位置**: §23.1 diff, L195
- **观察**: design.md 声明 "forced answer、length continuation、retry/replay/resume 只作为 trigger reason，不挤入 kind" 且在 coverage assertion 中列出 retry/replay/resume。映射关系可从规则逻辑推导：`host_retry` + original kind → 重放原 call type。但未给出类似 "host_retry of initial dispatch → kind=initial_user_dispatch, trigger_reason=host_retry" 的显式示例。
- **影响**: Slice 2 实现者可能对 retry/replay/resume 场景下 `runner_call_kind` 取值产生歧义。
- **建议**: Slice 2 implementation 前在 manifest 的 kind/trigger reason 组合注释中补一个 retry/replay/resume 映射示例，或在 Slice 2 implementation artifact 中裁判映射关系。
- **裁决**: accepted — 逻辑可推导，不阻塞。

#### F-003 (non-blocking): Event 矩阵列名 `run_id` 与 `RUNNER_CALL_INPUT_ASSEMBLED` 行内 `host_run_id` 不一致

- **位置**: §13.3 canonical event contract matrix
- **观察**: 矩阵表头 scope 列使用 `run_id`；`RUNNER_CALL_INPUT_ASSEMBLED` 行使用 `host_run_id`。语义差异有充分理由（compactor proposal 无 Host admitted user Run），但矩阵格式不一致。其他 control event 行（`RETRY_REQUESTED` 等）可能也有类似问题，不在本次 review scope。
- **建议**: 低优先级 — 不影响 contract 正确性。可单独做 matrix 格式治理。
- **裁决**: accepted — 格式问题，非 contract 缺口。

#### F-004 (non-blocking): `projector_id` / `purpose` 使用"至少覆盖"语言

- **位置**: §23.1 diff, L167
- **观察**: `projector_id` table 类型列为 "closed string enum"，但文字描述为 "第一版至少覆盖 [10 values]"；`purpose` 同理 "第一版至少覆盖 [7 values]"。Plan appendix 使用 "closed string enum" 且无 "至少覆盖" 修饰。差异细微：design.md 的语言承认未来可扩展，对当前 10/7 个值的闭合性无实质削弱。
- **建议**: Slice 2 实现时确认 projector_id/purpose 枚举在代码中以 closed enum 定义；新增值必须通过 design.md 更新。
- **裁决**: accepted — 当前枚举值闭合，可扩展表态不影响 Slice 1-7 实施。

#### F-005 (non-blocking): `manifest_schema_version` 具体版本字符串未指定

- **位置**: §23.1 diff, manifest table row 1
- **观察**: validation rule 为 "equals design-approved current version"，未指定具体字符串（如 `"1.0"` 或 `"2025-06"`）。Plan appendix 同样未指定。这是设计文档的正常行为 — 版本在实现时确定。
- **建议**: Slice 2 implementation 前定义 schema version，写入设计文档或 plan handoff note。
- **裁决**: accepted — deferred to implementation，不阻塞。

## Residual Risks / Open Questions

| risk | severity | owner | mitigation |
|---|---|---|---|
| `payload_inline_threshold_bytes` 具体阈值未在 design.md 硬编码 | low | Slice 1-2 implementer | 阈值由 construction root 注入；focused tests 需验证边界行为 |
| Provider tool_calls/reasoning_content deferred to WU-ENG | medium | WU-ENG owner | design.md 已通过 `provider_specific_atom_deferred` limited-signal 正确表达缺口，不引入 untyped bag |
| Compactor input projection artifact 的 durable write ordering 与 atomic rename 规则未在 diff 中显式重复 | low | Slice 3 implementer | §13.1 已有的 artifact 发布规则适用于所有 artifact kinds，compactor_input_projection 隐式继承 |
| 外部 Engine provider contract changes 可能影响 Slice 2 的 `provider_tool_calls_digest` / `reasoning_content_digest` | low | Slice 2 implementer | design.md 已允许两种路径（typed fields → digest；raw state → deferred），不阻塞 |

## Verdict

**PASS-WITH-FINDINGS**

- blocking findings: 0
- non-blocking findings: 5
- residual risks: 4 (all low/medium, all owned)

Slice 0 design.md diff 完整且等价于 accepted plan appendix 的 contract shape。所有 acceptance criteria 均已满足。5 个 non-blocking findings 均为格式完善性或文档粒度问题，不影响 Slice 1-7 以 design.md 为设计真源启动实现。

## Completion Report

- **artifact path**: `docs/reviews/wu-dur-obs-cm-closeout-design-review-ds.md`
- **verdict**: pass-with-findings
- **blocking findings**: 0
- **non-blocking findings**: 5
- **residual risks / open questions**: 4
- **next gate readiness**: Slice 1-7 may proceed with design.md as truth source; F-001/F-002 resolution by Slice 2/4 implementers is recommended but not gating
