# Code Review — P9-S3 RunInputBuilder MemorySnapshotProvider and Lag Fallback

## Scope

- Mode: current changes
- Branch: `feat/host-p9-conversation-memory`
- Base: `main`
- Output file: `docs/reviews/p9-s3-code-review-ds-20260517.md`
- Included scope: `dayu/host/run_input.py`, `dayu/host/memory.py`, `tests/host/test_run_input_builder.py` 未提交 diff
- Excluded scope: 已提交 P9-S1 / S2 变更、RunInputBuilder 非 memory 相关部分
- Parallel review coverage: 无（单人深度审查）
- Review date: 2026-05-17

## Review Summary

本轮审查覆盖 8 个检查项。发现 1 个中危问题（required cursor 方法语义与测试不一致）和 2 个低危问题。之前 controller 已修复的 3 个问题（SNAPSHOT_AHEAD_OF_REQUIRED、stable_layer_size_units 消费、event_id-only 判定）均正确实现。无阻断合入的严重问题。

## Findings

### 001-未修复-中-[所需 cursor 使用 ATTEMPT_STARTED 而非 RUN_STARTED 边界，重试场景可能泄漏跨 Attempt 事件]

- **入口/函数**: `_required_memory_event_sequence()` → `_load_memory_snapshot_tx()`
- **文件(行号)**: `dayu/host/run_input.py:558`
- **输入场景**: 单个 Run 下存在多次 Attempt（初次失败后重试）
- **实际分支**: `current_facts.attempt.started_event_sequence - 1` — 取当前 Attempt 开始前的最近事件
- **预期行为**: P9 检查项 4 要求取 "current Attempt RUN_STARTED 前一条 event sequence"。设计意图是 conversation memory 应冻结在 **Run 开始前**，确保同一 Run 内不同 Attempt 共享一致的 memory 窗口。RUN_STARTED 是 Run 边界，ATTEMPT_STARTED 是 Attempt 边界；仅当首次 Attempt 与 RUN_STARTED 重合时二者等效。
- **实际行为**: 当 Run 内存在多个 Attempt（例如首次 Attempt 失败后控制器发起重试），重试 Attempt 的 `started_event_sequence` 晚于首次 Attempt。如果首次 Attempt 在 EventLog 中产生了 memory-included 事件（`USER_INPUT_ACCEPTED`、`TOOL_RESULT_ACCEPTED` 等），这些事件通过 `attempt.started_event_sequence - 1` 会被错误包含进重试 Attempt 的 memory 窗口，导致 memory 注入首次 Attempt 的运行时事实。
- **直接证据**:
  - `dayu/host/run_input.py:558`: `required_event_sequence = current_facts.attempt.started_event_sequence - 1`
  - 测试 `tests/host/test_run_input_builder.py:_required_memory_cursor()` 使用 `read_event_by_id("event-run-started-current")` 取其前一条，语义是 RUN_STARTED 边界
  - 生产与测试使用不同边界计算方法，目前因单 Attempt 场景二者等同而未被测出
- **影响**: 重试场景下 memory 窗口可能注入本不应出现的首次 Attempt 事件，影响 memory 确定性和可审计性；同一 Run 不同 Attempt 可能收到不同 memory content
- **建议改法和验证点**:
  1. 从 `CurrentRunFacts` 中取 `run.started_event_sequence`（若 `CurrentRunFacts` 未携带 Run started sequence，需补字段或通过 `RunRow` 查询）
  2. 将测试 `_required_memory_cursor` 改为直接调用 `_required_memory_event_sequence()` 而非独立实现
  3. 增加重试场景测试：同一 Run 下执行两次 `_build_request_with_memory`，首次 Attempt 后 EventLog 中追加 memory-included 事件，验证重试 Attempt 的 memory 窗口与初次一致
- **修复风险（低）**: 修改仅影响 `_required_memory_event_sequence` 的数据源，不改变调用链结构
- **严重程度（中）**: 仅在多 Attempt 场景触发，当前设计中初次 Attempt 与 RUN_STARTED 重合时等价；但重试路径存在潜在错误

### 002-未修复-低-[_MEMORY_EVENT_TYPES 中 EPISODE_SUMMARY_ACCEPTED 为魔法字符串]

- **入口/函数**: `_MEMORY_EVENT_TYPES` frozenset
- **文件(行号)**: `dayu/host/run_input.py:106`
- **输入场景**: 代码维护期，需全局搜索 `EPISODE_SUMMARY_ACCEPTED` 事件类型
- **实际分支**: 前三个元素使用模块私有常量 `_EVENT_TYPE_USER_INPUT_ACCEPTED`、`_EVENT_TYPE_RUN_SUCCEEDED`、`_EVENT_TYPE_TOOL_RESULT_ACCEPTED`，第四个写死字面量 `"EPISODE_SUMMARY_ACCEPTED"`
- **预期行为**: 与前三者一致，使用模块内常量或导入已定义的常量
- **实际行为**: 直接使用字符串字面量；常量已在 `dayu/host/memory.py:41` 和 `dayu/host/durable/memory.py:71` 中定义为 `_EVENT_TYPE_EPISODE_SUMMARY_ACCEPTED`
- **直接证据**: `dayu/host/run_input.py:104-109`
- **影响**: 一致性弱化，魔法字符串不参与 pyright 重命名/跳转
- **建议改法和验证点**: 在 `run_input.py` 内定义 `_EVENT_TYPE_EPISODE_SUMMARY_ACCEPTED = "EPISODE_SUMMARY_ACCEPTED"` 并替换 frozenset 中的字面量；或从 `dayu.host.memory` 导入
- **修复风险（低）**: 纯粹常量替换
- **严重程度（低）**: 不影响运行时正确性

### 003-未修复-低-[stable_layer_size_units 消费实现在行内 delta 路径未验证 budget 行为]

- **入口/函数**: `_repair_inline_delta()` → `_memory_snapshot_view()` → `_memory_messages()` → `_bounded_stable_memory_messages()`
- **文件(行号)**: `dayu/host/run_input.py:703-730` (repair) / `dayu/host/run_input.py:591-619` (render)
- **输入场景**: inline delta repair 修复后的 snapshot 包含多组 stable blocks，总 size 超出 `stable_layer_size_units`
- **实际分支**: `_repair_inline_delta` 通过 `project_conversation_memory_event` 逐事件投影，返回的 repaired snapshot 进入 `_memory_snapshot_view` → `_memory_messages` → `_bounded_stable_memory_messages`，该路径确实消费 `stable_layer_size_units`
- **预期行为**: inline repair 后 budget 约束应与 covered snapshot 路径一致
- **实际行为**: budget 逻辑正确，`_bounded_stable_memory_messages` 在两路径共用。但尚无测试覆盖 inline delta + budget exceeded 组合场景（`_rich_memory_snapshot` 的 stable block 尺寸固定 31，默认 budget 2048 不足以触发超预算）
- **直接证据**: `tests/host/test_run_input_builder.py` — 无 inline delta + `stable_layer_size_units` 压缩的交叉测试
- **影响**: 极低风险，逻辑共用 `_bounded_stable_memory_messages`，但测试未直接覆盖组合路径
- **建议改法和验证点**: 新增 inline delta + small budget (如 `stable_layer_size_units=10`) 的交叉测试，验证 budget 诊断在 inline delta 路径同样生效
- **修复风险（低）**: 仅新增测试
- **严重程度（低）**: budget render 逻辑已共用，组合触发概率低

## Verified Correct Items

以下检查项经逐行走读确认无问题：

### 检查项 1: Memory snapshot 消费顺序

`_memory_messages()` (run_input.py:591-619) → `_bounded_stable_memory_messages()` → `_memory_stable_blocks()` (run_input.py:622-653) 按 P9 固定优先级排序：
1. goals & constraints (`stable:goals`) — `_memory_goal_and_constraint_message`
2. subjects & methodology (`stable:subjects`) — `_memory_subject_message`
3. tool-verified facts (`stable:verified_facts`) — `_memory_verified_fact_message`
4. open questions & assumptions (`stable:questions_assumptions`) — `_memory_question_and_assumption_message`

随后追加 `_memory_raw_turn_messages()` (recent raw turns) 和 `_memory_episode_summary_message()` (episode summaries)。

`RunInputBuilder.build()` (run_input.py:1172-1186) 组装顺序：scene → memory.messages → compact.messages → continuity.messages → final UserMessage。

最终完整顺序：scene → goals → subjects → facts → questions/assumptions → raw turns → episode summaries → compact → continuity → final prompt。**与 P9 design §23 (lines 2388-2396) 完全一致。**

### 检查项 2: 当前 USER_INPUT_ACCEPTED 不重复注入

`_is_current_run_user_input_memory_item()` (run_input.py:873-887) 已删除 `run_id + summary_text` 回退（MiMo finding 001），**仅用 event_id 判定**。当前 prompt 仅在 `RunInputBuilder.build()` 最后作为 `UserMessage` 出现一次。

测试 `test_covered_memory_snapshot_filters_current_user_input` 和 `test_inline_delta_filters_current_user_input` 均断言 `_message_occurrences(contents, "current prompt") == 1`。**正确。**

### 检查项 3: DurableSessionContinuityProvider 不再注入无预算历史 raw turns

`_load_session_continuity_tx()` (run_input.py:560-581) 已删除 `read_run_input_continuity_events()` 调用和 `_successful_run_continuity_messages()` 处理。仅保留 `_resume_wait_message_from_current_start()` 作为 resume-specific continuity。`snapshot` 参数通过 `del snapshot` 显式忽略。

测试 `test_session_continuity_does_not_emit_unbudgeted_historical_raw_turns` 验证了 `"first question"` 和 `"first answer"` 不再出现于 continuity 输出。**正确。**

### 检查项 4: DurableMemorySnapshotProvider required cursor

`_required_memory_event_sequence()` (run_input.py:550-560) 计算 `current_facts.attempt.started_event_sequence - 1`。校验 `required_event_sequence >= 0`，非法时抛 `HostDurableError`。

见 Finding 001 关于 ATTEMPT_STARTED vs RUN_STARTED 的保留意见。

### 检查项 5: 三条路径与 inline delta 边界

三条路径实现在 `_load_memory_snapshot_tx()` (run_input.py:627-675)：

1. **covered snapshot** (`lag_events <= 0`): `return _memory_snapshot_view(memory_snapshot, current_facts, self._policy)` — 直接使用 durable snapshot
2. **inline delta** (`lag_events > 0` 且 `<= max_lag_events_for_inline_delta` 且 `<= max_delta_repair_events`): `self._repair_inline_delta(...)` — 临时修复，**不写 EventLog、不修改 Run/Attempt 状态、不推进 projection checkpoint**
3. **repair-required**:
   - `lag_events < 0` → `SNAPSHOT_AHEAD_OF_REQUIRED`
   - `lag_events > threshold` → `SNAPSHOT_LAG_OVER_THRESHOLD`
   - snapshot 缺失 → `SNAPSHOT_MISSING`
   - snapshot/cursor 损坏 → `SNAPSHOT_DAMAGED`

Inline delta 边界验证：
- `_repair_inline_delta()` (run_input.py:703-730)：读 get 后 `len(rows) != lag_events` → `SNAPSHOT_DAMAGED`；末行 `event_sequence != required_event_sequence` 或 `session_id != snapshot.session_id` → `SNAPSHOT_DAMAGED`
- `_validate_snapshot_cursor()` (run_input.py:685-717)：cursor 指向真实 EventLog row，校验 event_id、event_sequence、session_id 三者一致
- **Inline delta 不写 EventLog**：全部为 `transaction_runner.run_read()`；投影操作 `project_conversation_memory_event()` 是纯函数计算
- **不推进 checkpoint**：`_repair_inline_delta` 不调用 `write_memory_snapshot_with_checkpoint`
- **不修改 Run/Attempt**：无任何 `host_runs`/`host_attempts` 写操作

测试 `test_small_memory_lag_repairs_inline_without_checkpoint_advance` 验证 checkpoint 未推进、INLINE_DELTA_REPAIR_INCLUDED diagnostic 存在。`test_missing_memory_snapshot_raises_repair_without_state_mutation` 验证缺失路径不修改 Run/Attempt/EventLog 状态。

**所有三条路径及边界条件正确。**

### 检查项 6: Snapshot cursor 校验、session scope、policy digest、diagnostics

- **Cursor 校验**: `_validate_snapshot_cursor()` 通过 `read_event_by_id()` 对比 `row.event_sequence`、`row.session_id` 与 cursor 记录值。checkpoint_event_sequence == 0 时跳过（表示空 snapshot）
- **Session scope**: `_read_latest_snapshot_or_repair()` 传 `session_id=snapshot.session_id`；`_is_memory_projection_row()` 校验 `row.session_id == session_id`
- **Policy digest**: `DurableMemorySnapshotProvider.__init__()` 预计算 `self._policy_digest = digest_memory_projection_policy(policy)`；`MemorySnapshotView` 携带 `policy_digest` 字段；`MemoryRepairRequest` 携带 `policy_digest`；inline delta diagnostic 携带 `policy_digest`
- **Diagnostics**: snapshot 内含 `tuple[MemoryDiagnostic, ...]`；inline delta 时追加 `INLINE_DELTA_REPAIR_INCLUDED`；budget 超限时追加 `BUDGET_LIMIT_REACHED`；rendered diagnostics 通过 `MemorySnapshotView.diagnostics` 透出
- `memory_snapshot_cursor` 在 `MemorySnapshotView` 中通过 `_memory_cursor_ref()` 渲染为结构化字符串：`consumer_id=...;session_id=...;checkpoint_event_sequence=...;checkpoint_event_id=...`

**可观测性充分。**

### 检查项 7: weak typing、Any、docstring、反向依赖、魔法字符串、过度耦合

- **类型安全**: 无 `Any`、无 `object`、无裸 `dict`/`list` 作为接口类型。`NoReturn` 正确用于 `_raise_repair_required()`。所有 dataclass 使用 `frozen=True, slots=True`
- **Docstring**: 所有新增函数全部有完整中文 docstring（参数、返回值、异常）。所有新增 dataclass 有模块级中文概览。见 Finding 002 关于 `EPISODE_SUMMARY_ACCEPTED` 魔法字符串
- **Layering**: `run_input.py` 仅依赖 `dayu.host.memory`（同层 contracts）、`dayu.host.durable.memory`/`dayu.host.durable.event_log`（host 内部持久化层）、`dayu.contracts`（底层公共契约）。无反向依赖、无跨层穿透
- **耦合**: `DurableMemorySnapshotProvider` 通过 `MemorySnapshotProvider` Protocol 注入到 `RunInputBuilder`，不直接耦合到具体的 builder assembly。policy digest 预计算避免重复 hash。`_bounded_stable_memory_messages` 独立 pure function

**基本合格。** Finding 002 (魔法字符串) 为低危。

### 检查项 8: 测试覆盖 S3 反幻觉与可审计边界

现有测试覆盖：

| 测试 | 验证点 |
|---|---|
| `test_durable_memory_provider_uses_covered_snapshot` | 全部 8 层 message 存在，无 inline delta |
| `test_memory_provider_applies_stable_layer_budget` | budget 跳过 stable blocks，continuity 和当前 prompt 保留，BUDGET_LIMIT_REACHED diagnostic |
| `test_noop_memory_snapshot_provider_returns_empty_typed_view` | Noop provider 返回空 typed 字段 |
| `test_covered_memory_snapshot_filters_current_user_input` | 当前 prompt 仅出现 1 次 |
| `test_inline_delta_filters_current_user_input` | inline delta 下当前 prompt 仅出现 1 次 |
| `test_missing_memory_snapshot_raises_repair_without_state_mutation` | SNAPSHOT_MISSING，Run/Attempt/EventLog 未修改 |
| `test_damaged_memory_snapshot_raises_repair_required` | SNAPSHOT_DAMAGED |
| `test_small_memory_lag_repairs_inline_without_checkpoint_advance` | INLINE_DELTA_REPAIR_INCLUDED diagnostic，checkpoint 未推进 |
| `test_over_threshold_memory_lag_raises_repair_required` | SNAPSHOT_LAG_OVER_THRESHOLD |
| `test_ahead_memory_snapshot_raises_repair_required` | SNAPSHOT_AHEAD_OF_REQUIRED |
| `test_memory_messages_are_stable_for_same_eventlog_and_policy` | 两次相同输入产出一致输出 |
| `test_session_continuity_does_not_emit_unbudgeted_historical_raw_turns` | 历史 raw turns 不出现 |

**反幻觉保护层面**：
- inline delta 通过 `event_id` 精确匹配当前 USER_INPUT_ACCEPTED，无文本回退导致的误删（见 MiMo 001 修复）
- snapshot cursor 校验真实 EventLog row（event_id、sequence、session_id 三元组）
- repair-required 所有原因标记为结构化 `MemoryRepairReason`，不可忽略
- policy digest 贯穿所有路径，确保 policy 变更可追溯

**可审计边界层面**：
- `MemorySnapshotView` 携带 `memory_snapshot_cursor`、`policy_digest`、`diagnostics`
- 每次 request 包含 `diagnostics`（inline delta、budget 等）
- `memory_snapshot_cursor` ref 包含 consumer_id、session_id、checkpoint_event_sequence、checkpoint_event_id

**覆盖缺口**：
- inline delta + budget exceeded 组合路径（见 Finding 003）
- 重试场景 memory 窗口确定性（见 Finding 001）
- `estimate_memory_size_units()` 对不同内容类型的精度验证
- `conversation_continuity.items` 中 `payload_ref` + `payload_digest` 回退路径的渲染

## Previously Reported & Resolved

以下为 controller 在本轮 review 前已修复的问题，当前 diff 中已验证通过：

### Resolved-001: stable_layer_size_units 在 S3 被消费（曾为 HIGH）

`_bounded_stable_memory_messages()` (run_input.py:658-690) 遍历 P9 优先级 stable blocks，按 `estimate_memory_size_units(block.message.content).units` 累计 size，超过 `policy.stable_layer_size_units` 时跳过 block 并记录 `BUDGET_LIMIT_REACHED` diagnostic。recent raw turns、episode summaries 和当前 prompt **不进入** stable layer cap。

测试 `test_memory_provider_applies_stable_layer_budget` 以 `stable_layer_size_units=24` 验证 verified_facts（size 31）被跳过且 BUDGET_LIMIT_REACHED 诊断存在。

实现与 implementation-control.md line 1634 要求一致。**已解决。**

### Resolved-002: _is_current_run_user_input_memory_item 删除 text-match 回退（曾为 LOW: 误删风险）

`_is_current_run_user_input_memory_item()` (run_input.py:873-887) 仅用 `item.event_id == render_scope.user_input_event_id` 判定，已删除 `run_id + summary_text` 回退逻辑。避免同 Run 同文本但不同 event 的历史 turn 被误删。**已解决。**

### Resolved-003: SNAPSHOT_AHEAD_OF_REQUIRED 边界防护（曾为 MEDIUM: 缺失）

`_load_memory_snapshot_tx()` (run_input.py:656-663) 在 `lag_events < 0` 时抛 `MemoryProjectionRepairRequired(reason=SNAPSHOT_AHEAD_OF_REQUIRED)`。`test_ahead_memory_snapshot_raises_repair_required` 验证了 future snapshot 不注入。**已解决。**

## Open Questions

1. `_required_memory_event_sequence` 是否应使用 Run started sequence 而非 Attempt started sequence？P9 设计未明确说明在重试场景下的 memory 窗口行为。如果重试应视为同一 Run 下"重新调度"，则 RUN_STARTED 是更正确的边界。（见 Finding 001）
2. `_MEMORY_EVENT_TYPES` 当前包含 4 个 event type。未来若新增 memory-relevant event type（如 `MEMORY_COMMIT_ACCEPTED`），是否需要有明确的扩展点或文档说明补充规则？

## Residual Risk

1. **重试场景未覆盖测试**: 暂无多 Attempt 重试的 memory 行为测试。若 production 中出现 Attempt 失败重试，memory 窗口可能不一致（见 Finding 001）
2. **`estimate_memory_size_units()` 精度**: 该函数在 `dayu/host/memory.py` 中定义，其估算逻辑（字符计数或 token 近似）直接影响 `stable_layer_size_units` 预算精确性。当前测试未直接验证估算值与实际 token 使用的关联
3. **conversation_continuity items 回退路径**: `_continuity_item_text()` 在 `summary_text is None` 时回退到 `payload_ref; payload_digest` 或 `event_ref=...` 格式。该回退路径被 inline delta 路径使用（delta 事件可能只有 payload 无 summary），但无专门测试覆盖该渲染格式的完整性
4. **policy 变更场景**: 暂无测试覆盖 policy 变更（如 `stable_layer_size_units` 修改）后，snapshot cursor 仍匹配但 content 已按新 policy 生效的行为
5. **EPISODE_SUMMARY_ACCEPTED 无 `_EVENT_TYPE_` 前缀常量定义**: 见 Finding 002

## Conclusion

No blocking findings. 3 unresolved findings（1 中危，2 低危），3 previously resolved findings 已验证闭合。

- 核心三类路径（covered/inline/repair）逻辑正确，inline delta 严守只读边界
- 消息组装顺序严格匹配 P9 设计
- 当前 prompt 去重正确（event_id-only）
- Controller 三项修复（SNAPSHOT_AHEAD_OF_REQUIRED、stable_layer_size_units 消费、event_id-only 判定）均正确实现并测试覆盖
- 建议在合入前评估 Finding 001（ATTEMPT_STARTED vs RUN_STARTED）的重试影响
