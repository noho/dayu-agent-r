# Plan Review: WU-DUR-P01-S2-R2 runner-call event link hardening

- **Reviewed target**: `docs/host/wu-dur-p01-s2-r2-runner-call-event-link-plan.md`
- **Reviewer**: mimo
- **Timestamp**: 20260605-190326
- **Scope**: 全量 plan review，重点审查 root cause 同源性、新增 event 最小性、fail-closed 语义、continuation reset 误匹配防护、Tool Trace 集成克制性、schema/diagnostic/测试/文档 code-generation-ready 程度、stop conditions 完整性。

## Assumptions Tested

1. Root cause 是 `iteration_index == 0` 间接猜测，不是缺少 Engine 事件。
2. 新增 `RUNNER_CALL_INPUT_ITERATION_LINKED` 不越层、不改变 Engine contract。
3. Missing first manifest 应 rejected 而非 limited-signal。
4. Continuation reset `iteration_index == 0` 不会误匹配旧 ordinary manifest。
5. Tool Trace 集成范围克制，不扩张现有 projection 语义。
6. Event schema、diagnostic reason、测试切片、README/control doc 触发 code-generation-ready。
7. Stop conditions 覆盖所有关键失败模式。

## Findings

### 01-未修复-高-`ENGINE_EVENT_REJECTED` 未进入设计真源 event type 表

- **位置**: Slice 0 Design sync; 设计真源 `docs/host/design.md` 13.2 Event Type List (L1485-1499)
- **问题类型**: 契约缺失
- **当前写法**: plan 在 Slice 1 fail-closed 路径中大量使用 `ENGINE_EVENT_REJECTED` + `stop_worker_stream=True`，但设计真源 event type list 不包含 `ENGINE_EVENT_REJECTED`。代码中 `engine_ingest.py:213` 已定义 `_EVENT_TYPE_ENGINE_EVENT_REJECTED = "ENGINE_EVENT_REJECTED"` 并在多处使用，但设计文档从未登记该 event type。
- **反例/失败场景**: 实施 Agent 读设计真源时发现 event type 表没有 `ENGINE_EVENT_REJECTED`，可能认为这是未定义 event type 而停止实施，或自行决定不写文档直接编码，导致设计真源继续漂移。
- **为什么有问题**: 设计真源是 Host EventLog 语义的 single source of truth。plan 的 Slice 0 要求"在 EventLog event type 表中加入 `RUNNER_CALL_INPUT_ITERATION_LINKED`"，但漏掉了同样需要补录的 `ENGINE_EVENT_REJECTED`。这是一个 pre-existing gap，但本 plan 是第一次在 fail-closed 主路径上依赖该 event type，必须同步关闭。
- **直接证据**: `docs/host/design.md` L1485-1499 event type list 无 `ENGINE_EVENT_REJECTED`；`dayu/host/engine_ingest.py` L213 定义并多处使用。
- **影响**: 设计真源与代码继续漂移；实施 Agent 可能因设计缺定义而阻塞或绕过。
- **建议改法和验证点**: Slice 0 增加动作：在 `docs/host/design.md` event type list 和 canonical event contract matrix 中补录 `ENGINE_EVENT_REJECTED`，明确其 scope (`session_id`、`run_id`、`attempt_id`、`execution_id`)、payload (`reason`、`stop_worker_stream`)、无 Run/Attempt 状态副作用、resume/memory 不消费、audit 消费。验证：grep 设计真源确认 `ENGINE_EVENT_REJECTED` 出现在 event type list 和 matrix 中。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 高

### 02-未修复-高-新增 diagnostic reasons 未写入设计真源闭集定义

- **位置**: Slice 0 Design sync; 设计真源 `docs/host/design.md` L1672-1678 diagnostic reason 闭集
- **问题类型**: 契约缺失
- **当前写法**: plan 在 Slice 1 link resolution 中使用 `ambiguous_runner_call_manifest`、`runner_call_iteration_link_conflict`、`runner_call_manifest_mismatch` 三个新 diagnostic reason，但只在 plan 的 L104 和 Slice 0 中提到"先在设计真源补充 `ambiguous_runner_call_manifest` reason"和"若需要新增 diagnostic reason...先在设计真源写闭集定义"。plan 没有给出这三个 reason 的语义定义、使用边界和与现有 reason 的区分规则。
- **反例/失败场景**: 实施 Agent 在 Slice 0 时可能只添加 reason name 而不写语义定义，导致后续 consumer 无法区分 `ambiguous_runner_call_manifest`（多个候选 manifest）与 `runner_call_iteration_link_conflict`（同一 iteration 已有 link 指向不同 manifest）的含义差异。或实施 Agent 在 Slice 1 编码时用魔法字符串临时写入，违反编码硬约束。
- **为什么有问题**: 设计真源 diagnostic reason 闭集是 typed diagnostic contract 的一部分。新增 reason 必须有完整语义定义，否则 consumer（Tool Trace、analyzer、audit）无法正确解读。
- **直接证据**: `docs/host/design.md` L1678 列出当前 reason 闭集，不包含上述三个新 reason；plan L104 只说"先在设计真源补充"但未给出定义。
- **影响**: 实施 Agent 可能用不完整的 reason 定义编码，或用魔法字符串绕过 typed diagnostic contract。
- **建议改法和验证点**: Slice 0 增加动作：为 `ambiguous_runner_call_manifest`、`runner_call_iteration_link_conflict`、`runner_call_manifest_mismatch` 写完整语义定义，包括：(1) 使用场景；(2) 与相邻 reason 的区分规则；(3) 是否允许 `ENGINE_EVENT_REJECTED` 和 `RUNNER_CALL_INPUT_ITERATION_LINKED` 共用；(4) `consumer_boundary` 允许值。验证：设计真源 diagnostic reason 闭集包含新增 reason 且有语义定义。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 高

### 03-未修复-中-`_has_prior_iteration_observation` 范围未规格化

- **位置**: Slice 1 Link resolution contract 步骤 3 候选数为 0 分支
- **问题类型**: 不可直接实施
- **当前写法**: plan 提出 `_has_prior_iteration_observation(...)` helper，但未指定其查询范围：是检查当前 attempt/execution 下所有 iteration observations，还是只检查当前 run 下所有 execution？是否包含 compactor proposal call 的 iteration？是否包含已 rejected 的 iteration？
- **反例/失败场景**: 如果 `_has_prior_iteration_observation` 只检查当前 execution，而 compactor proposal 在不同 execution 下运行，则 compactor proposal 的 iteration 不会干扰 ordinary dispatch 的 link resolution，这是正确行为。但如果实现错误地检查所有 execution，compactor proposal 的 iteration 可能被误判为 "prior observation"，导致 ordinary missing manifest 场景从 rejected 降级为 continuation limited-signal。
- **为什么有问题**: 实施 Agent 需要明确的查询边界才能写出正确的 SQL 或 EventLog 查询。plan 只说"已有 earlier accepted iteration link 或 earlier accepted iteration preview"，但没有指定 scope。
- **直接证据**: plan L120 "候选数为 0 且当前 attempt/execution 已有 earlier accepted iteration link 或 earlier accepted iteration preview"——未指定是否跨 execution。
- **影响**: 实施 Agent 可能写出范围过宽或过窄的查询，导致误匹配或漏匹配。
- **建议改法和验证点**: 在 plan 中明确：`_has_prior_iteration_observation` 查询范围为当前 `attempt_id` + `execution_id` 下所有 `RUNNER_CALL_INPUT_ITERATION_LINKED` (accepted) 和 `ITERATION_STARTED` preview events。不跨 execution，不包含 rejected link。验证：测试覆盖 compactor proposal iteration 存在时 ordinary missing manifest 仍 rejected。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 04-未修复-中-现有 `iteration_index=1` continuation 测试可能因新逻辑行为变化

- **位置**: Slice 2 Focused tests; 现有测试 `test_iteration_started_writes_limited_runner_call_manifest_for_continuation`
- **问题类型**: 测试缺口
- **当前写法**: plan 在 Slice 2 列出新增测试，但没有明确说明现有 `test_iteration_started_writes_limited_runner_call_manifest_for_continuation` (L2199) 是否需要更新。该测试当前使用 `iteration_index=1`，在新逻辑下应走 "候选数为 0 且已有 prior iteration observation → continuation limited-signal" 路径。但新逻辑不再调用 `_runner_call_manifest_matches_iteration`，而是先查 link event 再查 unlinked prepared manifest。如果测试 fixture 中没有 seed prior iteration observation（如 link event 或 preview），新逻辑可能走 "候选数为 0 且没有 prior iteration → missing initial manifest rejected" 路径，导致测试失败。
- **反例/失败场景**: 实施 Agent 删除 `iteration_index == 0` fallback 后，现有 continuation 测试因 fixture 中没有 prior iteration observation 而失败。实施 Agent 可能为了保住测试而添加 hack，或需要更新 fixture。
- **为什么有问题**: plan 的验收标准要求"RunInputBuilder existing manifest boundedness、message_count、role digest、one-system-message tests 继续通过"，但没有提到 engine_ingest 现有测试是否需要 fixture 更新。
- **直接证据**: `tests/host/test_engine_ingest_mapping.py` L2199 测试使用 `iteration_index=1` 但 fixture 中没有 seed prior iteration observation。
- **影响**: 实施 Agent 可能在删除旧逻辑后发现现有测试失败，需要额外修复工作。
- **建议改法和验证点**: Slice 2 增加动作：更新 `test_iteration_started_writes_limited_runner_call_manifest_for_continuation` fixture，确保在调用 `iteration_index=1` 前已有 prior iteration observation（如 seed 一个 accepted link event 或 preview）。验证：测试在新逻辑下通过。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 05-未修复-低-`_find_runner_call_manifest_event` 可能成为 dead code

- **位置**: Slice 1 实施范围; `engine_ingest.py` L4914-4964
- **问题类型**: 最佳实践偏离
- **当前写法**: plan 提出新增 `_find_runner_call_iteration_link_event`、`_find_unlinked_prepared_runner_call_manifest_events` 等 helper，但没有说明现有的 `_find_runner_call_manifest_event` 函数（使用 `iteration_index == 0` fallback）在新逻辑下是否仍被使用。
- **反例/失败场景**: 如果 `_find_runner_call_manifest_event` 不再被调用，它成为 dead code，违反编码硬约束（禁止兼容性代码）。如果仍被调用，则 `iteration_index == 0` fallback 仍在代码中，与 plan 目标矛盾。
- **为什么有问题**: plan 的 Slice 1 说"删除或停止使用 `_runner_call_manifest_matches_iteration` 的 `payload_iteration_id is None and iteration_index == 0` fallback"，但 `_find_runner_call_manifest_event` 是该 fallback 的调用者。如果整个函数被替换，应明确删除。
- **直接证据**: `engine_ingest.py` L4914 `_find_runner_call_manifest_event` 调用 `_runner_call_manifest_matches_iteration`；plan L181 说"删除或停止使用"该 fallback。
- **影响**: dead code 残留；或实施 Agent 不确定是否应删除该函数。
- **建议改法和验证点**: Slice 1 明确：`_find_runner_call_manifest_event` 在新逻辑下不再被调用，应在实施时删除。验证：grep 确认无调用点。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 06-未修复-低-`validation_status` 复用 `mismatch` 语义过载

- **位置**: 设计契约变更 §2 新增追加式 link event; `validation_status` 定义
- **问题类型**: 契约缺失
- **当前写法**: plan 将 `mismatch` 定义为"找到 prepared manifest，但 `message_count` 或 `role_sequence_digest` 与 Engine observation 不一致，或 link identity 与既有 link 冲突"。这把数据不一致和 identity 冲突两种不同语义合为一个 status。
- **反例/失败场景**: consumer 看到 `mismatch` 时无法区分是数据校验失败还是 link 冲突。虽然 `diagnostic.reason` 可以区分，但 `validation_status` 本身的语义变得模糊。
- **为什么有问题**: 现有 diagnostic 状态集合中 `mismatch` 只用于数据不一致（`message_count_mismatch`、`role_sequence_digest_mismatch`）。plan 把 link conflict 也归入 `mismatch`，扩大了该 status 的语义范围。
- **直接证据**: plan L95-96 定义 `mismatch` 包含 "link identity 与既有 link 冲突"；`docs/host/design.md` L1676 定义 `mismatch` 为 "observed data 与 expected data 冲突"。
- **影响**: 轻微语义模糊，但 `diagnostic.reason` 可以弥补。不阻断实施。
- **建议改法和验证点**: 考虑将 link conflict 单独设为 `conflict` status，或在 plan 中明确 `mismatch` 的扩展语义并更新设计真源。验证：`validation_status` 语义定义与 `diagnostic.reason` 闭集一致。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

1. **`RUNNER_CALL_INPUT_ITERATION_LINKED` 是否需要进入 Tool Trace event type list？** plan 说"若实现把该事件纳入 Tool Trace，必须作为独立 read-only signal 投影"，但没有明确是否应该纳入。当前 `read_runner_call_reconstruction_signals_by_run` 只查询 `RUNNER_CALL_INPUT_ASSEMBLED`。如果 link event 不进入 Tool Trace，analyzer 如何消费它？
2. **`ENGINE_EVENT_REJECTED` 的 `stop_worker_stream` 字段是否需要在设计真源中定义为显式 payload 字段？** 当前代码中 `stop_worker_stream` 是 `EngineIngestResult` 的字段，不是 `ENGINE_EVENT_REJECTED` event payload 的字段。plan 没有区分这两者。
3. **link event 的 `manifest_schema_version` 字段的语义是什么？** 是 manifest body 的 schema version，还是 link event 自身的 schema version？如果是前者，它已在 manifest hot payload 中，link event 中重复记录的目的是什么？

## Residual Risks

| ID | 风险 | 缓解 | 建议追踪 |
|---|---|---|---|
| RR-01 | 新增 link event 过度扩张 EventLog contract | plan 限制为 Host-owned reconstruction fact，无状态副作用 | 本 WU 关闭后由 WU-OBS-P00 analyzer consumption 验证 |
| RR-02 | Tool Trace consumer 误把 prepared manifest `complete` 当作 Engine validated | README/design 明确 complete 是 assembly completeness | 本 WU Slice 3 README sync 关闭 |
| RR-03 | `ENGINE_EVENT_REJECTED` 设计真源缺定义 | 本 review Finding 01 要求 Slice 0 补录 | 本 WU Slice 0 关闭 |
| RR-04 | 新增 diagnostic reason 语义不完整 | 本 review Finding 02 要求 Slice 0 写完整定义 | 本 WU Slice 0 关闭 |

## Conclusion

**revise**

plan 的 root cause 分析同源且充分，新增 `RUNNER_CALL_INPUT_ITERATION_LINKED` 事件最小且不越层，fail-closed 语义正确，continuation reset 防护逻辑合理。但有 2 个高严重度 finding 阻断 code-generation-ready：

1. **`ENGINE_EVENT_REJECTED` 未进入设计真源 event type 表**（Finding 01）：plan 在 fail-closed 主路径依赖该 event type，但设计文档从未登记。Slice 0 必须补录。
2. **新增 diagnostic reasons 未写入设计真源闭集定义**（Finding 02）：`ambiguous_runner_call_manifest`、`runner_call_iteration_link_conflict`、`runner_call_manifest_mismatch` 三个新 reason 缺少语义定义。Slice 0 必须写完整定义。

非阻断建议：明确 `_has_prior_iteration_observation` 查询范围（Finding 03）、更新现有 continuation 测试 fixture（Finding 04）、清理可能的 dead code（Finding 05）、考虑 `validation_status` 语义细化（Finding 06）。

修复 Finding 01 和 02 后，plan 可进入 implementation。
