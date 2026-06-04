# WU-CM-01 Slice B Plan Fix Re-Review (DS)

日期：2026-06-04

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| review target | Slice B plan fix artifact `docs/reviews/wu-cm-01-slice-b-plan-fix-codex.md` |
| reviewed plan | `docs/host/wu-cm-01-conversation-memory-plan.md` (post-fix state) |
| design source | `docs/host/design.md` §24-25 |
| control doc | `docs/host/issues-implementation-control.md` |
| blocker artifact | `docs/reviews/wu-cm-01-slice-b-implementation-codex.md` |
| controller adjudication | `docs/reviews/wu-cm-01-slice-b-blocker-controller-adjudication.md` |
| prior accepted plan | `docs/host/wu-cm-01-conversation-memory-plan.md` (commit `a92416ec`) |
| review scope | plan/control/artifact 修正 only; 不审 dirty partial implementation code |
| reviewer | AgentDS (planreview skill) |
| artifact path | `docs/reviews/wu-cm-01-slice-b-plan-fix-rereview-ds.md` |

## Reviewed Target And Scope

本 re-review 的审查对象是 WU-CM-01 Slice B plan fix artifact (`docs/reviews/wu-cm-01-slice-b-plan-fix-codex.md`) 及其对 accepted plan (`docs/host/wu-cm-01-conversation-memory-plan.md`) 的修改。审查范围按用户指定：

1. `engine_ingest.py` 加入 Slice B 是否必要且 scope 足够窄
2. proactive subsequent run input / memory projection / RunInputBuilder consumption 是否正确归还 Slice C/D
3. 测试边界是否还能验证 operation/event/proactive/reactive closeout
4. 是否仍禁止旧 payload compatibility fields、projection shim、old candidate adapter、lazy import、extra payload、untyped event payload
5. 是否有新的 pyright-clean slice 风险

不审查：
- 当前 workspace 中未验收的 partial implementation code diff
- Slice A / C / D / E 的 plan 内容（除非与 Slice B 边界交叉）
- design.md 本身的正确性

## Assumptions Tested

1. **A1**: reactive accepted closeout 的生产 owner 确实是 `engine_ingest.py`，且 Slice B 没有其他遗漏的 production owner。
2. **A2**: plan fix 对 `engine_ingest.py` 的 scope 限制（仅限 reactive accepted event/artifact closeout）足够窄，不会引入 scope creep。
3. **A3**: subsequent run input / memory projection / RunInputBuilder 消费明确归属 Slice C/D，Slice B 测试不会通过这些路径的断言。
4. **A4**: 所有旧兼容路径禁止项在 plan fix 后仍保持。
5. **A5**: plan fix 没有引入新的类型错误或 pyright 风险。

## Findings

### 1-未修复-中-compact_artifact.py 写路径迁移未在 plan 中显式处理

- **位置**: Slice B 实现边界 "reactive accepted closeout" 段；`engine_ingest.py` `_append_reactive_compacted_event` 方法
- **问题类型**: 不可直接实施 / 契约缺失
- **当前写法**: plan fix 将 `engine_ingest.py` 加入 Slice B allowed files，scope 为 "仅限 reactive accepted compaction event / artifact closeout"。但 `_append_reactive_compacted_event` (line 1719-1738) 当前通过 `CompactArtifactStore(...).write_compact_artifact(CompactArtifactWriteRequest(...))` 写 artifact，而 `CompactArtifactWriteRequest` (compact_artifact.py:40-74) 在 `__post_init__` 中强制校验 `isinstance(self.accepted_candidate, CompactionCandidate)`。plan 和 plan fix 均未提及 `compact_artifact.py` 或说明 engine_ingest.py 如何绕过此类型校验。

- **反例/失败场景**: implementation agent 进入 engine_ingest.py 修改 `_append_reactive_compacted_event` 时，将 `candidate: CompactionCandidate` 改为 `candidate: ConversationCompactOutputVNext`，但若继续调用 `CompactArtifactWriteRequest(accepted_candidate=candidate)`，会在 `__post_init__` 触发 `TypeError: CompactArtifactWriteRequest.accepted_candidate must be CompactionCandidate`——这正是 blocker artifact 中已观测到的错误。

- **为什么有问题**: plan fix 的 scope 描述足够覆盖所需变更（artifact closeout 是 scope 内），但 plan 未给出从旧 `CompactArtifactStore`/`CompactArtifactWriteRequest` 迁移到 vNext artifact 写入路径的明确指引。implementation agent 需要自行判断是复制 dispatch.py 的 vNext artifact 写入方式还是提取共享 helper，这可能引入实现不一致。

- **直接证据**:
  - `dayu/host/compact_artifact.py:40-56`: `CompactArtifactWriteRequest.accepted_candidate` 类型为 `CompactionCandidate`
  - `dayu/host/compact_artifact.py:71-74`: `__post_init__` 强校验 `isinstance(self.accepted_candidate, CompactionCandidate)`
  - `dayu/host/engine_ingest.py:1719-1738`: `_append_reactive_compacted_event` 使用 `CompactArtifactStore(...).write_compact_artifact(CompactArtifactWriteRequest(...))`
  - `dayu/host/dispatch.py:1570-1596`: proactive path 已绕过 `CompactArtifactWriteRequest`，直接用 `LocalArtifactStore` + `_compact_artifact_json_vnext` 写 vNext artifact
  - plan fix 全文和 plan Slice B 节均未搜索到 `compact_artifact` 或 `CompactArtifact` 字样

- **影响**: implementation agent 在实现时可能： (a) 复制 dispatch.py 的 vNext artifact 写入逻辑到 engine_ingest.py（DRY 违规）；(b) 尝试修改 `compact_artifact.py`（scope 外）；(c) 停滞并要求 plan 澄清。不会导致数据损坏或状态不一致，但可能产生实现返工。

- **建议改法和验证点**:
  1. 在 plan 中明确：engine_ingest.py 的 vNext artifact 写入应采用与 dispatch.py 一致的 `LocalArtifactStore` 直写方式，不使用 `CompactArtifactWriteRequest`。
  2. 若 vNext artifact JSON 构造需要跨 dispatch.py 和 engine_ingest.py 共享，应将 `_compact_artifact_json_vnext`、`_compact_artifact_payload_ref`、`_compact_artifact_descriptor_metadata_vnext` 提取到已在 Slice B allowed files 中的 `compact_payload.py`（或新建共享模块并加入 allowed files）。
  3. 验证：engine_ingest.py 中 `_append_reactive_compacted_event` 不再通过 `CompactArtifactStore`/`CompactArtifactWriteRequest` 写 artifact。

- **修复风险**: 低。plan 文字修正，不涉及代码变更。
- **严重程度**: 中。不阻止 implementation 启动，但 implementation agent 首次遇到此问题时需要停下判断，可能产生一次 round-trip。

### 2-未修复-低-test_engine_ingest_mapping.py 不在 Slice B 测试范围内

- **位置**: Slice B 测试命令
- **问题类型**: 测试缺口
- **当前写法**: Slice B 测试命令包含 `test_dispatch_scheduler.py` 和 `test_recovery_dispatch.py`，但不包含 `tests/host/test_engine_ingest_mapping.py`。该文件包含直接测试 `EngineEventIngestor` reactive compaction 路径的用例，其 fake compactor helper（line 164、196、214）返回 `CompactionCandidate`。若 `engine_ingest.py` 的 `_append_reactive_compacted_event` 签名切换到 vNext，但该测试文件的 fake compactor 仍返回旧 `CompactionCandidate` 类型，在全量 `pytest tests/host -q` 时会暴露类型不匹配。

- **反例/失败场景**: Slice B focused tests 通过（因为不包含 `test_engine_ingest_mapping.py`），但全量 Host 测试中该文件的 fake compactor 返回类型与 `run_compaction_operation` → `_append_reactive_compacted_event` 的 vNext 类型链不兼容。

- **为什么有问题**: plan 的测试命令未覆盖直接测试 `engine_ingest.py` reactive path 的测试文件。Slace B focused tests 可能 green，但全量 `pytest tests/host -q` 会 red。这不阻塞 Slice B 验证（Slice B 测试命令本身可以 pass），但会留下已知 breakage 到 Slice C/D，增加了后续 slice 的清理负担。

- **直接证据**:
  - `tests/host/test_engine_ingest_mapping.py:164,196,214`: fake compactor helper 签名 `-> CompactionCandidate`
  - `tests/host/test_engine_ingest_mapping.py:446`: `CONTEXT_COMPACTED` event type 断言
  - plan Slice B 测试命令不含 `test_engine_ingest_mapping.py`
  - plan fix 未提及该文件

- **影响**: Slice C/D implementation agent 在后续 slice 需要额外修复该测试文件的 fake compactor 类型，属于 residual risk。不会阻塞 Slice B 本身的退出信号。

- **建议改法和验证点**:
  1. 在 plan 中标注 `test_engine_ingest_mapping.py` 为 Slice B residual risk：该文件的 fake compactor 类型迁移随 `engine_ingest.py` 变更自然需要更新，但不在 Slice B focused test 命令中强制验证。
  2. 或在 Slice B allowed test files 中加入该文件，并明确其 fake compactor 需要切换到 vNext 返回类型。

- **修复风险**: 低。
- **严重程度**: 低。非阻塞，属于 deferred cleanup 性质。

### 3-未修复-低-dispatch.py 与 engine_ingest.py 之间 vNext artifact 写入逻辑重复风险

- **位置**: Slice B 实现边界 / allowed files
- **问题类型**: 过度耦合 / 最佳实践偏离
- **当前写法**: dispatch.py 的 proactive accepted closeout 已实现完整的 vNext artifact 写入链路（`_compact_artifact_json_vnext`、`_compact_artifact_payload_ref`、`_compact_artifact_descriptor_metadata_vnext`，均为模块私有函数）。engine_ingest.py 的 reactive accepted closeout 需要相同的逻辑。plan fix 没有指定共享方式，implementation agent 可能选择在 engine_ingest.py 中复制这些函数。

- **反例/失败场景**: implementation agent 在 engine_ingest.py 中复制 dispatch.py 的 vNext artifact 构造逻辑（约 100 行），导致两份相同逻辑分散在两个模块中。后续若 vNext artifact schema 需要调整（例如新增字段），需要同时修改两处，容易遗漏。

- **为什么有问题**: CLAUDE.md 要求"重复逻辑必须抽取"。若 implementation agent 选择复制，会在后续 slice 或 maintenance 中产生 drift 风险。

- **直接证据**:
  - `dayu/host/dispatch.py:3684-3755`: `_compact_artifact_json_vnext`、`_compact_artifact_payload_ref`、`_compact_artifact_descriptor_metadata_vnext` 为模块私有
  - `dayu/host/compact_payload.py`: 已在 Slice B allowed files 中，是合理的共享提取目标
  - plan fix 未提及 artifact JSON 构造逻辑的共享策略

- **影响**: 代码重复和潜在的 artifact schema drift。不影响功能正确性。

- **建议改法和验证点**:
  1. plan 中建议将 vNext artifact JSON 构造的共享逻辑提取到 `compact_payload.py`（已在 Slice B allowed files），dispatch.py 和 engine_ingest.py 均从该处 import。
  2. 或明确允许 engine_ingest.py 中有限的局部复制，并在 plan 中记录为 accepted duplication（有意识的技术债务）。

- **修复风险**: 低。
- **严重程度**: 低。不影响 Slice B 功能完整性。

## Focus Area 详细审查

### Focus 1: engine_ingest.py 加入 Slice B 是否必要且 scope 足够窄

**必要性：确认成立。**

直接代码证据：
- `dayu/host/engine_ingest.py:1666-1672`: reactive accepted 分支将 `operation_result.accepted_candidate` (类型 `ConversationCompactOutputVNext | None`) 传给 `_append_reactive_compacted_event(candidate=...)`，该参数当前声明为 `candidate: CompactionCandidate`
- `dayu/host/engine_ingest.py:1696-1705`: `_append_reactive_compacted_event` 签名仍使用旧 `CompactionCandidate` 和 `CompactQualityCheckResult`
- `dayu/host/engine_ingest.py:1719-1738`: 方法体通过 `CompactArtifactStore` → `CompactArtifactWriteRequest` 写 artifact，后者在 `compact_artifact.py:71-74` 强制校验 `CompactionCandidate` 类型
- `dayu/host/dispatch.py` 的 proactive path 不负责 reactive accepted closeout；reactive path 的唯一 production owner 是 `engine_ingest.py`

无 `engine_ingest.py` 的修改，Slice B 无法完成 "accepted / rejected / failed compaction 都是 vNext 事件闭环" 的目标。

**Scope 足够窄：确认成立。**

plan fix 的 scope 限制：
- "仅限 reactive accepted compaction event / artifact closeout"
- "不得修改 Engine event ingest 的其它状态机、projection catch-up、RunInputBuilder 调用或旧 payload 兼容路径"

代码核对：
- `_append_reactive_compacted_event` 方法体（lines 1716-1770）只做两件事：写 artifact + append EventLog。无 memory projection、无 durable snapshot write、无 RunInputBuilder 调用。
- 调用方 `_execute_reactive_compaction` 的 `_operation` 闭包（lines 1547-1694）处理 stale check、attempt rejected events、accepted/failed 分支——这些都属于 "event closeout" 语义。
- `engine_ingest.py` 其余约 1800 行代码（Engine event type dispatch、RUN_STARTED/SUCCEEDED/FAILED ingest、ToolRuntime、Wait 等）不在此 scope 内，不受影响。

**有一个 scope 边界需要注意**：`_append_reactive_compaction_failed_event` (line 1772) 写入 `CONTEXT_COMPACTION_FAILED`——这不属于 "accepted closeout"，而是 "failed closeout"。plan fix 的 scope 描述只提到 "reactive accepted compaction event / artifact closeout"，未提及 failed closeout。但从代码看，`_append_reactive_compaction_failed_event` 的 payload 构造使用 `build_context_compaction_failed_payload`，该函数可能不需要 vNext 类型变更（failed 路径无 candidate）。此点不是 blocker，但值得在 implementation 时确认 failed path 是否需要同步变更。

### Focus 2: proactive subsequent run input / memory projection / RunInputBuilder consumption 是否正确归还 Slice C/D

**确认正确归还。**

plan fix 明确了以下归属：
- "proactive closeout 只验证 operation 编排、accepted / failed event payload、artifact descriptor 与 fallback 行为；不得要求 accepted compacted event 已被 subsequent RunInputBuilder 消费"
- "subsequent run input、memory projection、durable snapshot materialization、post-compact delta 和 RunInputBuilder 对 vNext payload 的消费断言属于 Slice C / D"
- "Slice B 测试不得通过旧 payload compatibility fields、projection shim、old candidate adapter 或额外 payload 字段让这些断言提前通过"

对应的失败测试 `test_multi_turn_proactive_compact_feeds_subsequent_run_input` (test_dispatch_scheduler.py:4105) 的 run-4 断言（lines 4175-4184+）确实检查了 subsequent run input 中的 memory section 渲染（`current_goal=`、`Memory episode summaries:`），这些属于 Slice D 的 RunInputBuilder 消费范围。plan fix 正确将其归入 Slice C/D。

三个 reactive 测试 (`test_reactive_overflow_recovers_and_dispatches_new_attempt`、`test_reactive_repeated_overflow_dispatch_loop_fails_closed_at_limit`、`test_reactive_recovery_uses_fresh_duplicate_governance_attempt`) 的 root cause 在 `engine_ingest.py`，plan fix 通过加入该文件到 Slice B 来覆盖。

### Focus 3: 测试边界是否还能验证 operation/event/proactive/reactive closeout

**可以验证。**

plan fix 更新后的 Slice B 退出信号：
- "accepted compact、attempt rejected、repair exhausted 与 fallback failure event 都使用 vNext payload 并通过 validator"
- "fact-only invalid 与 non-fact invalid 都触发同一 fail closed / whole-candidate repair 策略"
- "operation-level attempt number、candidate digest、quality issues 与 budget accounting 有测试断言"
- "proactive accepted / failed closeout 与 reactive accepted / failed / fallback closeout 都能形成 vNext event / artifact / state transition 闭环；测试断言停在 operation/event closeout，不断言 subsequent run input 已消费 compacted view"

测试覆盖矩阵：
- `test_compaction_operation.py` — operation 级别 accepted/rejected/repair exhausted/fact-only invalid → vNext
- `test_context_compact_events.py` — event payload validator → vNext
- `test_dispatch_scheduler.py` — proactive dispatch closeout (需调整 test 1 的 subsequent run input 断言) + reactive dispatch closeout (engine_ingest.py 修复后)
- `test_recovery_dispatch.py` — recovery dispatch + compact closeout

proactive closeout 可验证：`test_dispatch_scheduler.py` 中 proactive tests 的 event type 顺序断言 (`CONTEXT_COMPACTED` before `RUN_STARTED`) 和 artifact descriptor 断言不依赖 subsequent run input 消费。

reactive closeout 可验证：`_append_reactive_compacted_event` 修改后，`test_reactive_overflow_recovers_and_dispatches_new_attempt` 的断言 (`CONTEXT_COMPACTED` count=1, `RUN_RECOVERING` count=1, attempt count=2) 都是 event closeout 级别断言，不依赖 RunInputBuilder。

**需注意**：`test_multi_turn_proactive_compact_feeds_subsequent_run_input` 的 run-4 断言（line 4180-4184）包含 `current_goal=` 和 `Memory episode summaries:` 等旧 memory section header。这些断言既检查了 subsequent run input（Slice D 范围），也依赖旧 memory section（Slice C/D 范围）。plan fix 对此测试的处理策略是"调整断言停在 operation/event closeout"，但未给出具体调整方式。implementation agent 需要判断是：(a) 移除 run-4 的 subsequent run input 断言；(b) 将整个测试标记为 skip 并在 Slice D 恢复；(c) 保留 event closeout 部分断言并移除 RunInputBuilder 消费部分。这是 implementation 层面的判断，plan fix 的约束已足够清晰。

### Focus 4: 是否仍禁止旧 payload compatibility fields、projection shim、old candidate adapter、lazy import、extra payload、untyped event payload

**确认所有禁止项均保持。**

plan fix 明确保留的禁止项（Slice B 实现边界 - 不得引入）：
- "CONTEXT_COMPACTED 旧字段 re-export、旧 payload facade、旧 candidate 到 vNext 的双向 adapter"
- "为保持 pyright 通过而新增的 lazy import seam、字符串字段探测、extra payload 字段或 untyped event payload"

plan fix 新增的禁止项（Slice B 实现边界）：
- "不得新增旧 candidate 到 vNext / vNext 到旧 candidate 的 adapter"
- "不得在 CONTEXT_COMPACTED payload 中保留 evidence_backed_fact_candidates、pinned_state_patch_candidate、minimum_preserve_item_candidates、preserved_* 或其它旧字段来喂给未迁移 projection / RunInputBuilder"
- "subsequent run input、memory projection... 对 vNext payload 的消费断言属于 Slice C / D。Slice B 测试不得通过旧 payload compatibility fields、projection shim、old candidate adapter 或额外 payload 字段让这些断言提前通过"

禁止项覆盖完整：旧字段 re-export、旧 payload facade、双向 adapter、lazy import seam、字符串字段探测、extra payload、untyped event payload、projection shim、compatibility fields 全部在列。

代码侧验证：`context_events.py` 的 `build_context_compacted_payload` 已切换到 `accepted_candidate: ConversationCompactOutputVNext` 并在 line 345-346 做 `isinstance` 强校验，同时 `validate_context_compacted_payload` 在 line 380 调用 `_reject_old_compacted_fields(payload)`——旧字段入口已被封堵。

### Focus 5: 是否有新的 pyright-clean slice 风险

**未发现新的 pyright 风险。**

plan fix 未修改 production code 或 tests，只修改了 plan 和 control doc 的 allowed-files 列表与边界描述。因此不会引入新的代码类型错误。

engine_ingest.py 加入 Slice B 后的潜在 pyright 风险：
1. `_append_reactive_compacted_event` 签名从旧类型切换到 vNext 类型时，需同步更新 `build_context_compacted_payload` 调用参数（从 `compact_artifact_ref`/`compact_artifact_digest`/`accepted_candidate`/`quality_check_result` 旧式调用切换到带 `operation_id`/`accepted_attempt_number`/`prompt_local_label_mapping_refs` 等 vNext 参数的调用）
2. `CompactArtifactStore`/`CompactArtifactWriteRequest` 的 import 可能变为 unused（若切换到 `LocalArtifactStore` 直写），需清理
3. `CompactionCandidate` import 可能在 `_append_reactive_compacted_event` 范围内变为 unused

这些是正常的类型迁移风险，不是结构性 pyright 风险。Slice B 的验证命令包含 `python -m pyright dayu/ tests/ utils/`，会在实现后捕获。

## Open Questions

1. **engine_ingest.py 中 `_append_reactive_compaction_failed_event` 是否需要同步切换到 vNext？** plan fix scope 为 "仅限 reactive accepted compaction event / artifact closeout"。failed path 的 payload 通过 `build_context_compaction_failed_payload` 构造，该函数可能不需要 vNext candidate 类型。但若 failed path 的 `_append_reactive_compaction_failed_event` 的签名也使用了旧类型参数，implementation agent 可能在实现时发现需要同步变更。建议在 implementation 时先核对 `_append_reactive_compaction_failed_event` 的完整签名和调用链。

2. **`test_engine_ingest_mapping.py` 的 fake compactor 返回类型迁移由哪个 slice 负责？** 该文件不在任何 slice 的 allowed files 中（Slice B 不含，Slice C/D 的 allowed files 主要是 memory/projection/RunInputBuilder 测试）。建议在 plan 中标注其 owner slice 或作为 Slice E (public smoke & docs) 的清理项。

## Residual Risks

| 风险 | 严重程度 | Owner | 说明 |
|---|---|---|---|
| `compact_artifact.py` 写路径迁移 | 低 | Slice B implementation | engine_ingest.py 可绕过 `CompactArtifactWriteRequest`，直接用 `LocalArtifactStore` + `PayloadStore` 写 vNext artifact（与 dispatch.py 一致），无需修改 `compact_artifact.py` |
| `test_engine_ingest_mapping.py` fake compactor 类型迁移 | 低 | Slice C/D 或 E | 该文件不在 Slice B focused tests 中，不影响 Slice B 退出信号。但全量 `pytest tests/host -q` 会暴露 |
| vNext artifact JSON 构造逻辑在 dispatch.py 与 engine_ingest.py 间重复 | 低 | Slice B implementation | 可通过提取到 `compact_payload.py` 或在 plan 中记录为 accepted duplication 解决 |
| `test_multi_turn_proactive_compact_feeds_subsequent_run_input` 的 run-4 subsequent run input 断言调整 | 低 | Slice B implementation | plan fix 已有明确约束，implementation agent 自行判断调整方式 |
| Slice C 的 memory durable/projection 消费 vNext compact event | — | Slice C | 正常 residual，已由 plan 明确 owner |
| Slice D 的 RunInputBuilder / subsequent run input 消费 | — | Slice D | 正常 residual，已由 plan 明确 owner |

## Final Plan Review Conclusion

**Verdict: `pass-with-findings`**

plan fix 正确识别并修复了原 Slice B 的两个核心问题：
1. `engine_ingest.py` 作为 reactive accepted closeout 的 production owner 被遗漏 → 已加入 allowed files，scope 严格限制
2. proactive subsequent run input 断言属于 Slice C/D → 已明确归还，并强化了禁止通过兼容字段提前通过的约束

三项 findings 均为非阻塞：
- Finding 1 (中): `compact_artifact.py` 写路径迁移策略未显式说明，但 feasible workaround 存在（`LocalArtifactStore` 直写），不阻止 implementation 启动
- Finding 2 (低): `test_engine_ingest_mapping.py` 未纳入 Slice B 测试范围，属于 deferred cleanup
- Finding 3 (低): vNext artifact 写入逻辑潜在重复，属于实现质量建议

五项 focus area 审查结论：
1. engine_ingest.py 加入 Slice B 必要且 scope 足够窄 ✓
2. proactive subsequent run input / memory projection / RunInputBuilder 正确归还 Slice C/D ✓
3. 测试边界可验证 operation/event/proactive/reactive closeout ✓
4. 所有旧兼容路径禁止项保持 ✓
5. 未发现新的 pyright-clean slice 风险 ✓

**建议**：controller 接受此 plan fix，进入 Slice B re-implementation gate。implementation agent 应在启动时注意 Finding 1 的 artifact 写路径选择，并在 implementation report 中记录实际采用的方案。
