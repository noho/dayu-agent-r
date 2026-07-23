# WU-CTX-01 Slice 2 Implementation

## 1. 状态与边界

- 状态：implementation complete，未 commit、未 push、未创建 PR、未进入 review 或
  Slice 3。
- base：accepted Slice 1 protected commit `b6f297b4`。
- 设计与计划：`docs/host/design.md` §25；
  `docs/reviews/wu-ctx-01-plan-codex.md` §5.6、§5.7、§8.3。
- `docs/host/issues-implementation-control.md` 的既有 dirty 内容为 Controller-owned；
  本实现未修改或覆盖该文件。
- production、tests 与 README diff 均限制在 §8.3 allowlist；固定 implementation
  artifact 为本文件。
- 本 slice 的所有 producer 固定使用 `conservative_fallback`。没有引入 anchor
  resolver、usage pairing、anchored formula、usage selection，也没有从 raw
  `USAGE_REPORTED` 或 public 层重算。

## 2. 动机与语义 owner

动机成立：Slice 1 已能产生 conservative `ContextSizingResult`，但没有一个可重复读取、
可审计且与 driven transition 同事务的 canonical budget truth。若只在 dispatch
分支、日志或 public adapter 临时派生，startup replay、steer、wait resume 与 Engine
continuation 会各自拥有不同事实，且 rollback 后可能出现孤立展示。

唯一 owner 分工如下：

- `dayu/host/context_budget.py`：五 stage pressure/action matrix、conservative sizing
  result 与从冻结 atoms 重建 continuation result 的唯一计算 owner。
- `dayu/host/context_events.py`：`CONTEXT_BUDGET_EVALUATED` v1 schema、strict parser、
  deterministic identity、idempotent append、同 identity 冲突和 strict matching
  source load 的 canonical owner。
- `dayu/host/dispatch.py`、`engine_ingest.py`、`admission.py`、`recovery.py`、
  `waiting.py`：各状态机 producer 的 transaction-local ordering owner；只消费
  `ContextSizingResult` 或 strict source fact，不复制 canonical schema。
- `dayu/host/read_api.py` + `dayu/host/api.py`：canonical fact 到七字段
  `HostContextUsageView` 的唯一 public projection/contract owner。
- `dayu/service/entrypoint_runtime.py`：`HostContextUsageView` 到同形
  `EntrypointContextUsage` 的 exhaustive typed pass-through owner；既有 activity
  callback 继续交付该 DTO。
- `dayu/host/lifecycle_events.py` 与 `dayu/host/durable/schema.py`：event closed set
  与 fresh schema version owner。

直接调用点审计确认 canonical append 只位于上述 producer：
`dispatch.py:1893/2546/2777`、`engine_ingest.py:821/889/3804`、
`admission.py:3139`、`recovery.py:896`、`waiting.py:1365`；strict source load
位于 `engine_ingest.py:6341`、`recovery.py:1090`、`waiting.py:1268`。

## 3. Canonical fact 与 identity

`CONTEXT_BUDGET_EVALUATED` 使用 fresh `context_budget_evaluated.v1` strict schema。
identity 由 run、candidate cursor/digest、stage、policy snapshot digest 与 estimator
identity 组成；event id 和 decision id 均由 canonical digest 确定。相同 identity 与
相同 payload 是幂等 append；相同 identity 但结果不同会 fail closed。

fact 保存真实 pressure 与 stage-aware decision。basis points 使用整数计算且不
clamp；超过 context window 时允许大于 10000。当前 producer 的 method 始终为
`conservative_fallback`，`anchor_diagnostic` 始终为 `null`。v1 strict parser 中
计划冻结的 nullable anchor diagnostic 字段和 estimate-method closed enum 仅定义
schema 边界，不包含 Slice 3 resolver、pairing、公式或 usage 选择代码。

startup 不复用 source fact identity：它先 strict-load matching complete source
manifest 与 source fact，复用 estimate、threshold、policy 和 estimator atoms，再以
新 Attempt 的 manifest event sequence 和 `CONTINUATION` stage 派生新 identity。
complete source fact 缺失或 mismatch 会把 source 判为不可恢复并 fail closed，不
重新估算；unavailable source manifest 不写新 fact。

## 4. Producer ordering、幂等与 rollback

| producer | 同事务顺序与决策 | 幂等/rollback contract |
| --- | --- | --- |
| ordinary allow | manifest → fact → `RUN_STARTED` → `ATTEMPT_STARTED` | 单套 start identity；transition precondition miss 抛 private rollback；low-level CAS error 传播，manifest/fact/payload/Attempt/dispatch 全部回滚 |
| ordinary soft | fact → `CONTEXT_COMPACTION_REQUESTED` | 不创建 manifest/Attempt；重复 governance 使用 deterministic fact |
| ordinary hard | fact → terminal failure | 不创建 Attempt/dispatch |
| proactive post-compact allow | manifest → `POST_COMPACT` fact → start | stage 保持真实；与 start 同事务 |
| proactive post-compact hard | fact → terminal failure | 不进行第二次 proactive request |
| tier fallback allow | manifest → `DISPATCH_FALLBACK` fact → start | stage 保持真实；与 start 同事务 |
| tier fallback hard | fact → terminal failure | 不 silent accept |
| reactive accepted post-compact | 已提交 compact 后，新事务 manifest → `REACTIVE_POST_COMPACT` fact → recovery start | normal/soft/hard 均 `ALLOW_DISPATCH`；start precondition miss 回滚新 candidate manifest/fact/payload/Attempt/dispatch，已接受 compact 保留 |
| startup replay | source strict validation → new manifest → new `CONTINUATION` fact → recovery start | 新 identity；source missing/mismatch 零重估并 fail closed；start precondition/CAS 失败回滚全部 candidate 写 |
| running/waiting steer | steer owner 冻结 candidate；manifest → `CONTINUATION` fact → start | hard pressure 仍 `ALLOW_DISPATCH`；同 transaction 创建新 Attempt |
| wait completed/cancelled | resolution owner 内 manifest → `CONTINUATION` fact → resume/start transition | hard pressure仍 allow；resolution/result 的既有内部顺序不改变 |
| wait failed/lost | terminal owner only | 零新 manifest、fact、Attempt、dispatch |
| Engine `iteration_index > 0` | limited/complete continuation manifest → 可用时 fact → link/preview | source complete 时写 `CONTINUATION` fact；任一 frozen source unavailable 时写 limited manifest、零 fact |
| policy missing | existing no-budget manifest/start path | 零 sizing、fact、`CONTEXT_USAGE` activity |
| internal compactor / historical usage | 不进入 dispatch-relevant producer | 零 budget fact；raw usage 仍只是 observation |

producer-level tests 直接断言了上述顺序与零事实契约，而非仅依赖 canonical append
unit test或生产代码 inspection：

- `test_dispatch_scheduler.py` 覆盖 ordinary allow/soft/hard、post-compact
  allow/hard、fallback allow/hard、policy missing、precondition/CAS rollback。
- `test_engine_ingest_mapping.py` 覆盖 reactive rollback、iteration>0 complete
  manifest→fact→preview 与 unavailable source 零 fact。
- `test_public_steer.py` 覆盖真实 hard continuation 仍 allow 且 fact-before-start。
- `test_resolve_wait_command.py` 覆盖 completed/cancelled wait resume 的
  manifest→fact→start，以及 failed/lost 零 candidate state。
- `test_recovery_scan.py` 覆盖 startup source atom 复用、新 identity、ordering，
  以及 source fact missing/mismatch 零新 candidate state。

## 5. Public secrecy 与 Service pass-through

Host public `HostContextUsageView` 和 Service
`EntrypointContextUsage` 都只包含：

1. `predicted_input_tokens`
2. `context_window_size`
3. `utilization_basis_points`
4. `soft_threshold_tokens`
5. `hard_threshold_tokens`
6. `estimate_method`
7. `pressure_level`

Host read projector 只 strict-parse `CONTEXT_BUDGET_EVALUATED`；raw
`USAGE_REPORTED` 继续 `activity=None`。public contract 不含 usage event/ref、
anchor diagnostic、delta、policy ref、stage 或 budget decision。Service mapper
逐字段复制数值并 exhaustive 映射两个 enum，不计算 percentage、pressure 或 action；
测试使用彼此不满足算术关系的合法 DTO 值证明没有重算。既有 activity callback 收到
typed `CONTEXT_USAGE`；CLI 只安全消费 activity，不自行格式化百分比。

## 6. `context_events` local durable import 证据

`context_events.py` 保留 `TYPE_CHECKING` 类型导入和两个函数内
`dayu.host.durable.event_log` runtime import。直接 import graph 为：

```text
dayu.host.api:47
  -> dayu.host.memory:23
  -> dayu.host.context_events

dayu.host.context_events
  -> dayu.host.durable.event_log:41
  -> dayu.host.durable.schema:18,27
  -> dayu.host.durable._row_rules:10
  -> dayu.host.api
```

把 `EventClass` / append request 的 runtime import 提升为模块级会在 `api` 尚未完成
初始化时反向进入 `api`，形成真实 circular import；此前直接模块 import collection
已证明会命中 partial initialization。`TYPE_CHECKING` 已用于 row/store/transaction
签名，不能消除运行时构造 `EventClass` 和 `EventLogAppendRequest` 的需求。allowed
scope 内没有一个既不反向依赖 Host API、又拥有 canonical business semantics 的
durable-neutral module；把 owner 迁到 generic EventLog/schema 会造成 semantic
ownership drift。因而本 slice 保留局部 import 是最小且清晰的边界，消除它需要一个
out-of-scope durable dependency refactor。

## 7. README audit

- 已按 `dayu/host/README.md` 自身 Agent 更新约束同步 canonical fact、
  producer ordering、startup strict replay 与七字段 public secrecy。
- 已完整读取 `dayu/service/README.md` 并同步 typed pass-through 和 callback contract。
- 已读取 `tests/README.md` 的更新约束；本 slice 没有改变测试目录层级、运行入口或
  维护规则，因此没有机械修改该文件。
- 根 README 与 `dayu/README.md` 的职责触发未命中：没有用户安装/CLI workflow
  变化，也没有改变 UI → Service → Host → Engine 分层或装配方向。

## 8. 验证记录

- §8.3 exact focused：
  `732 passed`。
- full Host 最终 clean gate：
  `2228 passed, 2 skipped, 6 deselected`。
- full Host 首轮曾有一个未修改 watchdog 时序用例观察到同线程两次 cancel；该用例
  单独复跑通过，随后 full Host clean 复跑通过。
- affected Service/CLI：
  `71 passed`。
- branch coverage run（full Host + affected Service/CLI）：
  `2299 passed, 2 skipped, 6 deselected`。
- `python -m pyright dayu/ tests/ utils/`：
  `0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- 新增签名静态审计：
  对 slice added diff 与 `tests/host/test_context_budget_evaluated.py` 运行 `rg`，
  零 `Any` / `object` 参数或返回签名；该文件 `_sizing(...) ->
  ContextSizingResult` 且保留完整中文 docstring。
- Slice 3 越界审计：零 resolver、pairing 实现、anchored formula 或 usage
  selection；关键词命中仅限 strict nullable diagnostic schema、closed enum 和明确
  禁止重算的文档/docstring。
- raw usage public leakage 审计：`api.py`、`read_api.py`、
  `entrypoint_runtime.py` 的 public projection 零 `USAGE_REPORTED`、usage refs、
  anchor values、policy ref、stage/action 字段。

changed production file branch coverage：

| file | branch coverage |
| --- | ---: |
| `dayu/host/__init__.py` | 100.00% |
| `dayu/host/admission.py` | 85.63% |
| `dayu/host/api.py` | 89.50% |
| `dayu/host/context_budget.py` | 86.87% |
| `dayu/host/context_events.py` | 80.39% |
| `dayu/host/dispatch.py` | 85.07% |
| `dayu/host/durable/schema.py` | 94.76% |
| `dayu/host/engine_ingest.py` | 85.13% |
| `dayu/host/lifecycle_events.py` | 95.60% |
| `dayu/host/read_api.py` | 89.59% |
| `dayu/host/recovery.py` | 84.00% |
| `dayu/host/waiting.py` | 83.27% |
| `dayu/service/entrypoint_runtime.py` | 82.21% |

## 9. Residual risk

- 没有已知 correctness blocker。
- `context_events` 的局部 durable import 是现有 Host API/schema import graph 的
  明确循环隔离点；未来若重构 durable 公共类型边界，应以独立 work unit 处理，不能在
  consumer 层加 fallback。
- 本 slice 只交付 conservative fallback。nullable anchor diagnostic 与
  `usage_anchored` enum 只是已冻结 schema/typed contract 的未使用分支；真正的
  anchor resolver、pairing、公式和 usage selection 仍属于 Slice 3，当前 producer
  不可到达这些语义。
