# WU-CTX-02 + WU-CTX-03 discussion / code inspection

## 1. Work unit goal 与 success signal 摘要

依据 `docs/host/design.md`：

- 第 1 节设计目标要求 Host 是 Session / Run / Attempt / EventLog / admission / cancel / resume / retry / steer / replay / memory / tool governance 的治理真源，Engine 只执行单次 `AgentRunRequest`，durable facts 必须可恢复，远端执行环境不能拥有 Host 状态。
- 第 25 节要求 Context Governance 属于 Host，Engine 不做 Host-side compact retry；compact repair / retry 必须 bounded；retry budget 耗尽后只能写一个最终 `CONTEXT_COMPACTION_FAILED`，不得 Service replay、Engine retry Host governance 或无限 compact。
- `max_compaction_attempts_per_operation` 默认 packaged policy 必须为 5，且代码 fallback 默认值与 execution profile 默认值一致。
- deterministic recent-window fallback 不是 compact 成功：不得写 `CONTEXT_COMPACTED`、不得写 memory projection、不得伪造 stable facts；必须通过 `CONTEXT_COMPACTION_FAILED` 或等价 diagnostic 记录 fallback policy decision、fallback input window / digest、重新估算结果。
- reactive overflow 必须走 `RECOVERING` + 新 Attempt 路径；超过 `max_reactive_compactions_per_run` 后 fail closed，Run 进入 `FAILED`，不得进入 `LOST`，不得无限 retry。

依据 `docs/host/host-core-followup-implementation-control.md`：

- WU-CTX-02 目标：建立 compact failure 策略矩阵；明确 retry / partial materialize / fail closed / diagnostic；补齐 proactive / reactive compact failure E2E；默认 retry budget 提升到 5；默认 compact 模型使用 flash-tier；清理 compactor model 默认来源不一致；实现 deterministic recent-window fallback 诊断与预算重估。
- WU-CTX-02 success signal：每类 compact failure 都有用户可见或 diagnostic 结果；默认 retry budget 为 5；测试覆盖首轮失败、repair 成功、repair 耗尽与 fallback 收口；默认 compact model 与 scene / execution profile 配置一致；post-compact budget estimate 失败不 silent overflow；failure 不留下 orphan Attempt、重复 terminal、partial compacted event 或 memory projection 半物化。
- WU-CTX-03 目标：建立 reactive overflow 从 RunInputBuilder、compaction、retry 到 terminal / diagnostic 的端到端测试；确认循环上限与失败收敛路径；验证 fallback 不能放下输入或 policy 不允许继续时仍由 reactive 上限兜底。
- WU-CTX-03 success signal：连续 overflow 不会无限循环；terminal / diagnostic 能说明 compact 次数、最后失败原因和 fail closed；E2E 可观察 Attempt 数、`CONTEXT_COMPACTION_REQUESTED` / `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` 事件数与最终 Run terminal 状态。

## 2. 动机是否成立

结论：WU-CTX-02 与 WU-CTX-03 的动机仍成立，但需要收窄为“补齐已设计但未落地的 failure policy / fallback / E2E 缺口”，不能扩大为重写 Context Governance。

仍真实存在的风险：

| 风险 | 判断 | 直接证据 |
|---|---|---|
| 默认 retry budget 未对齐设计的 5 | 真实存在 | `dayu/host/context_policy.py:22` 为 `DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION = 2`；`dayu/config/execution_profiles.json:23/91/159/227` 均为 `3`；设计要求默认 packaged policy 为 5 且代码 fallback 与 profile 一致。 |
| compactor model 默认来源不一致 | 真实存在 | 默认 execution profile 的 compactor model 是 `deepseek-v4-flash`，见 `dayu/config/execution_profiles.json:11-16`；`conversation_compaction` scene manifest 的 `model.default_model_id` 是 `mimo-v2.5-pro-thinking-plan`，见 `dayu/config/prompts/manifests/conversation_compaction.json:10-12`；设计第 3 节要求 packaged default 不得互相矛盾。 |
| deterministic recent-window fallback 未实现 | 真实存在 | 代码搜索只命中设计文档和无关 `fallback_policy_snapshot`；proactive failure 在 `dayu/host/dispatch.py:1113-1128` 直接 append failed 并 `RUN_FAILED`；reactive failure 在 `dayu/host/engine_ingest.py:1530-1564` 直接 failed + `RUN_FAILED`。没有 fallback input window / digest / budget result 字段或重估路径。 |
| `CONTEXT_COMPACTION_FAILED` payload 不足以解释 attempt count / budget exhausted / fallback decision | 真实存在 | builder 只写 `failure_reason`、`policy_decision`、`retryable`、`diagnostic_refs`、`budget_after_attempted_compact`，见 `dayu/host/context_events.py:382-415`；validator 也只要求这些字段，见 `dayu/host/context_events.py:418-431`。设计要求至少包含 operation id、attempt count、retry / repair budget exhausted；fallback 时还要 fallback window / digest / budget result。 |
| reactive 连续 overflow 的 dispatch-loop E2E 不足 | 真实存在 | ingest 层已有计数测试，但 scheduler 层只有单次 overflow recovery 成功，见 `tests/host/test_dispatch_scheduler.py:3587-3618`；未见“worker 连续 overflow -> 多次 recovery Attempt -> 达到上限 -> final `RUN_FAILED`”的端到端测试。 |
| post-compact budget estimate failure silent overflow | 部分真实 | proactive path 能把 compact 后仍超 hard threshold 作为 retry / failure，见 `dayu/host/compaction_operation.py:209-235`；但当前 `CONTEXT_COMPACTION_FAILED` payload 未携带 attempt count / exhausted，且未看到独立 estimator failure / fallback 收口测试。 |

已被当前代码覆盖、风险不应重复放大的部分：

| 已覆盖项 | 直接证据 |
|---|---|
| Host-owned semantic repair bounded loop | `run_compaction_operation` 用 `max_attempts` 控制循环，见 `dayu/host/compaction_operation.py:118-151`；失败和 reject 会返回 `CompactionOperationResult`，见 `dayu/host/compaction_operation.py:171-247`。 |
| 首轮 proposal failure、quality rejection、hard-threshold-after-compact 后可 repair | 测试见 `tests/host/test_compaction_operation.py:376-477`。 |
| reactive compact 后不使用估算 hard threshold 阻断 recovery dispatch | 代码见 `dayu/host/compaction_operation.py:589-600`；测试见 `tests/host/test_compaction_operation.py:437-457`。 |
| reactive overflow 校验 attempt / execution identity | payload validator 要求 reactive attempt_id + execution_id，见 `dayu/host/context_events.py:260-264`；ingest stale identity 测试见 `tests/host/test_engine_ingest_mapping.py:569-608`。 |
| reactive compact failure 不进入 LOST | 代码通过 `_fail_recovering_run` 写 `RUN_FAILED`，见 `dayu/host/engine_ingest.py:1787-1826`；测试见 `tests/host/test_engine_ingest_mapping.py:611-635`。 |
| reactive compact count limit 的 ingest-level fail closed | 代码见 `dayu/host/engine_ingest.py:1157-1177`；测试见 `tests/host/test_engine_ingest_mapping.py:715-848`。 |
| reactive multi-pass 中间失败不提交 partial compacted event | `run_compaction_operation` 所有 pass 成功后才 merge candidate，见 `dayu/host/compaction_operation.py:237-260`；测试见 `tests/host/test_compaction_operation.py:685-724`。 |
| proactive compact failure 不创建 Attempt、不进 RECOVERING | 代码见 `dayu/host/dispatch.py:1113-1128`；测试见 `tests/host/test_dispatch_scheduler.py:3385-3414`。 |

被高估或不应纳入当前 work unit 的部分：

- 不应把 provider tokenizer adapter 纳入当前 WU。设计明确第一版不实现 provider-specific token counting / tokenizer adapter，见 `docs/host/design.md:2676`。
- 不应把 Engine overflow 处理迁入 Engine。控制文档 WU-CTX-03 非目标明确“不把 overflow 处理放进 Engine”。
- 不应重做 memory projection / evidence-backed fact 物化。当前风险是 fallback 不得伪造 stable facts；已有 memory 边界测试和 README 说明覆盖 no fallback facts / compaction-gated facts。
- 不应把 reactive ingest 层单点计数测试重复成同构单元测试；WU-CTX-03 明确只补 dispatch-loop 组合路径。

## 3. 直接证据索引

| 路径 | 函数 / 类 / 位置 | 关键行为 |
|---|---|---|
| `dayu/host/context_policy.py` | `DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION`、`default_context_budget_policy` | 默认 attempt budget 当前为 2，并流入默认 policy。 |
| `dayu/config/execution_profiles.json` | `context_budget_policy.max_compaction_attempts_per_operation` | packaged profiles 当前为 3。 |
| `dayu/config/prompts/manifests/conversation_compaction.json` | `model.default_model_id` | scene default 当前是 high-spec `mimo-v2.5-pro-thinking-plan`，与 profile default `deepseek-v4-flash` 不一致。 |
| `dayu/service/host_assembly.py` | `build_open_host_options` 附近 | Service assembly 从 execution profile 显式传入 `max_compaction_attempts_per_operation`，见 `dayu/service/host_assembly.py:459-470`。 |
| `dayu/host/compaction_operation.py` | `run_compaction_operation` | 执行事务外 proposal / repair loop；失败时生成 rejected attempts；reactive 不用 budget estimate 阻断。 |
| `dayu/host/dispatch.py` | `_execute_proactive_compaction` | proactive compact success 写 `CONTEXT_COMPACTED`；failure 写 `CONTEXT_COMPACTION_FAILED` 并 fail unstarted Run；当前没有 fallback 分支。 |
| `dayu/host/engine_ingest.py` | `_start_reactive_context_recovery` | reactive overflow 校验 policy、input、compact count，上限内写 request、关闭旧 Attempt、进入 `RECOVERING`。 |
| `dayu/host/engine_ingest.py` | `_execute_reactive_compaction` | reactive compact success 写 compacted 并启动 recovery Attempt；failure 写 failed 并 `RUN_FAILED`；当前没有 fallback 分支。 |
| `dayu/host/context_events.py` | `build_context_compaction_failed_payload` | failed payload 字段少于设计要求，缺 operation id、attempt count、budget exhausted、fallback detail。 |
| `tests/host/test_compaction_operation.py` | retry / multi-pass tests | 覆盖 bounded retry、quality rejection、hard threshold、reactive estimate overflow、multi-pass single failure。 |
| `tests/host/test_engine_ingest_mapping.py` | reactive tests | 覆盖 identity、missing compactor fail closed、不进 LOST、count limit、corrupt count fail closed。 |
| `tests/host/test_dispatch_scheduler.py` | proactive / reactive scheduler tests | 覆盖 proactive failure attempt-free、single reactive overflow recovery；缺连续 overflow E2E。 |
| `dayu/host/README.md` | Context Governance 说明 | 文档记录当前已实现 proactive / reactive 路径和 reactive 上限，但未说明 deterministic recent-window fallback 已实现。 |
| `tests/README.md` | 测试覆盖说明 | 记录现有 compact / reactive coverage；未宣称 fallback 收口或连续 overflow dispatch-loop E2E。 |

## 4. compact failure / retry / fallback / reactive overflow loop 状态矩阵

| 场景 | 当前代码状态 | 当前测试状态 | 缺口 |
|---|---|---|---|
| default `max_compaction_attempts_per_operation` | Host fallback 2，execution profiles 3 | `test_context_policy` 只断言等于常量，不断言 5 | 改为 5 并加配置 / assembly / packaged default 对齐测试。 |
| compact proposal 抛异常 | bounded retry；耗尽后 failed | operation 层、scheduler proactive 层有覆盖 | failed payload 仍缺 attempt count / exhausted。 |
| quality check reject | bounded retry；可记录 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` | operation 层和 proactive scheduler 层有覆盖 | fallback 收口缺失。 |
| proactive compact 后仍超 hard threshold | operation 层作为 `hard_threshold_after_compact` retry/failure | operation 层有覆盖 | post-compact estimate failure / fallback budget 重估缺失。 |
| compactor 或 artifact store missing | proactive 直接 `RUN_FAILED`；reactive 关闭旧 Attempt 后 `RUN_FAILED` | proactive attempt-free、reactive no-LOST 有覆盖 | 设计要求可按 policy 尝试 deterministic recent-window fallback，目前没有。 |
| stale compaction result | proactive 失败收口；reactive 留在 `RECOVERING` 并写 failed diagnostic | 两侧均有测试 | 是否应 terminal 不是当前 WU 必修；若计划触碰需谨慎。 |
| deterministic recent-window fallback 成功 | 未实现 | 无测试 | WU-CTX-02 核心缺口。 |
| deterministic recent-window fallback 仍超预算 / policy 禁止 | 未实现；现状直接 fail closed | 无 fallback-specific 测试 | 需要 failed payload / diagnostic 说明 fallback decision 与预算结果。 |
| reactive first overflow success | request -> old Attempt failed -> `RUN_RECOVERING` -> compacted -> new Attempt | ingest 与 scheduler E2E 有覆盖 | 已覆盖，不应重复扩大。 |
| reactive repeated overflow 未达上限 | ingest 层按 committed reactive request count 允许第二次 | ingest 层有“允许第二条 operation”测试 | 缺真实 worker/scheduler 连续 overflow E2E。 |
| reactive repeated overflow 达上限 | ingest 层 fail closed，Run `FAILED`，不写 `RUN_LOST` | ingest 层有覆盖 | 缺 dispatch-loop E2E 验证 Attempt / event 数。 |
| reactive compact failure 后 `LOST` | 当前不进入 `LOST` | 有测试 | 已覆盖，不是主要实现风险。 |
| partial compacted event | multi-pass 全部成功后才 merge，失败只返回 failed | operation 层有覆盖 | 如果增加 fallback，需确保不引入 partial materialization。 |

## 5. 现有测试覆盖与缺口矩阵

| 验收信号 | 已有测试 | 缺口 |
|---|---|---|
| 每类 compact failure 有 diagnostic / user-visible result | `tests/host/test_context_compact_events.py:259-273` 覆盖 failed payload builder；`tests/host/test_dispatch_scheduler.py:3337-3381` 覆盖 rejected event；`tests/host/test_engine_ingest_mapping.py:611-635` 覆盖 reactive failure terminal | failed payload 不含 attempt count / exhausted / fallback details；fallback 类 failure 无测试。 |
| retry budget 默认 5 | 无；当前 `test_context_policy` 只断言等于常量 | 需要断言 Host fallback、packaged execution profiles、Service assembly 默认一致为 5。 |
| 首轮失败、repair 成功、repair 耗尽 | `tests/host/test_compaction_operation.py:376-477`；`tests/host/test_dispatch_scheduler.py:3288-3381` | 当前多用 max_attempts=2，需在默认 5 更新后覆盖默认路径和 attempts exhausted payload。 |
| fallback 收口 | 无 | 需要 proactive / reactive fallback 成功与 fallback 后仍超预算 fail closed。 |
| 默认 compact model 与 scene / execution profile 配置一致 | Service / runtime 测试覆盖读取与 assembly，但没有断言 scene default 与 profile default 一致 | 需要配置一致性测试；当前事实不一致。 |
| post-compact budget estimate 失败不会 silent overflow | operation 层覆盖 compact 后仍超 hard threshold | 缺 estimator failure / failed payload 诊断与 fallback 决策可观察。 |
| failure 不留下 orphan Attempt / duplicate terminal / partial compacted / memory 半物化 | proactive attempt-free、reactive no-LOST、multi-pass single failure 已覆盖 | fallback 引入后需补同类断言。 |
| 连续 overflow 不无限循环 | ingest 层 count limit 覆盖 | 缺 scheduler / worker dispatch-loop E2E。 |
| terminal / diagnostic 能说明 compact 次数、最后失败原因、fail closed | 当前 failure_reason 有；attempt rejected 有 attempt_number | 最终 `CONTEXT_COMPACTION_FAILED` 缺 attempt_count / exhausted；没有 fallback decision detail。 |
| E2E 可观察 Attempt 数和 compact event 数 | 单次 reactive recovery E2E 已覆盖 Attempt=2 | 缺连续 overflow 到上限的 E2E。 |

## 6. 是否需要先修改 design_doc

不需要先修改 `docs/host/design.md`。

理由：设计真源已经明确了当前 work unit 需要的核心行为，包括 default 5、deterministic recent-window fallback、fallback diagnostic、reactive `RECOVERING` 路径、不得进入 `LOST`、不得无限 retry。当前缺口是代码 / 配置 / 测试未完全实现设计，而不是设计目标缺失或互相矛盾。

唯一需要在 plan gate 中保持警惕的是 fallback policy 的具体参数形状。若实现需要新增 public `ContextBudgetPolicy` 字段来表达是否允许 fallback、recent window N/M、fallback budget detail 等，才需要先回到设计文档补充 public contract；若实现采用 Host 内部 packaged policy 常量或已有 memory projection floor 派生，不一定需要改设计真源。

## 7. 建议进入 plan gate 的 scope boundary、non-goals、stop conditions

建议 scope boundary：

- 只覆盖 WU-CTX-02 / WU-CTX-03 已由设计和控制文档支持的行为：default attempts 对齐、compactor default model 对齐、`CONTEXT_COMPACTION_FAILED` payload / diagnostic 补足、deterministic recent-window fallback、proactive / reactive failure E2E、连续 reactive overflow dispatch-loop E2E。
- 优先复用现有 `ContextBudgetPolicy`、`run_compaction_operation`、`dispatch`、`engine_ingest`、`RunInputBuilder` / material block 边界，不重写 compaction candidate / memory projection / durable store。
- fallback 必须只构造本次 dispatch input view，不提交 `CONTEXT_COMPACTED`，不写 memory projection，不生成 stable facts。
- reactive loop E2E 应通过 scheduler + fake worker 触发连续 provider overflow，观察 Attempt 数、compact request / compacted / failed 事件数、最终 Run 状态。

建议 non-goals：

- 不引入 provider tokenizer adapter。
- 不把 overflow retry 放进 Engine。
- 不改变 evidence-backed fact candidate-only 裁决。
- 不让 Service 提供 candidate builder、repair callback 或 Host governance retry 策略。
- 不重做 recovery / positive orphan proof。
- 不为旧 schema / 旧 profile 保留兼容路径。

建议 stop conditions：

- 若需要新增或改变 Host public contract / config schema 来表达 fallback policy，先停回 design discussion。
- 若 fallback 实现需要改写 memory projection 或 stable facts，停止。
- 若连续 overflow E2E 暴露 scheduler / worker lifecycle 非确定性，先收敛测试同步 primitive，不靠 sleep / race。
- 若实现会让 reactive compact failure 进入 `LOST` 或让 proactive failure 进入 `RECOVERING`，停止。
- 若发现 config default model 对齐会影响普通 scene manifest 全局默认策略，先单独裁决配置边界。

## 8. blocking open questions

none

## 9. residual risks 初步分类与 owner 建议

| residual risk | 分类 | owner 建议 |
|---|---|---|
| default attempts 与 profiles 不一致 | 当前 WU 必修 | WU-CTX-02 implementation owner |
| scene manifest compactor model 与 execution profile default 不一致 | 当前 WU 必修 | WU-CTX-02 implementation owner，涉及 `dayu/config` 与 config tests |
| fallback policy 具体参数是否 public | 可能需要 design decision，但当前不 blocking | plan gate owner；若新增 public field 则 controller 回 design_doc |
| failed payload schema 增补是否触发 schema migration | 当前 WU 必修；按新 schema 起库，不做旧库兼容 | WU-CTX-02 implementation owner |
| 连续 overflow E2E 可能 flaky | 当前 WU 测试风险 | WU-CTX-03 implementation owner，使用现有 fake worker / scheduler helper |
| post-compact estimator failure 是否有独立代码路径 | needs-more-evidence | plan gate 进一步核对 estimator / candidate budget 数据流 |
| fallback 不伪造 stable facts | 当前 WU 必修 invariant | WU-CTX-02 implementation owner + review owner |
