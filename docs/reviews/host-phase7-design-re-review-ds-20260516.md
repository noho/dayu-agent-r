# Host Phase 7 Design Re-review — 2026-05-16

## Review Target

- **Primary artifact**: `docs/reviews/host-phase7-design-discussion-codex-20260516.md`
- **Diff context**: `docs/host/design.md` (§20–22, §3 Run API 补充) 和 `docs/host/implementation-control.md` (Phase 7) 当前 uncommitted diff
- **Design truth**: `docs/host/design.md` §20 Tool Awaiting / Wait Record, §21 Suspend / Resume / Retry / Replay, §22 Cancel
- **Control truth**: `docs/host/implementation-control.md` Phase 7

## Review Scope

独立复核 accepted design decisions 是否充分、最小、与 Host 架构一致。聚焦六项：

1. `ResolveWaitRequest` typed outcome envelope 替代弱 `outcome_ref`
2. wait record durable typed fields
3. callback 限于 adapter contract
4. `WAITING` cancel 与 late result diagnostic-only 行为
5. Engine / RemoteStub 不拥有 wait truth
6. 无过度设计

## Assumptions Tested

| # | Assumption | Evidence Check |
|---|---|---|
| A1 | Phase 6 `ToolAwaitingOutcome` 仍被降级为 governed error，Phase 7 必须补齐 accept path | 代码事实：`dayu/host/tool_runtime.py:2440-2452` 确认 `UNSUPPORTED_AWAITING_REASON` governed error |
| A2 | `resolve_wait` 当前是 stable unsupported，不打开事务 | 代码事实：`dayu/host/command.py:487-501` 确认 `_raise_unsupported_operation` |
| A3 | `ResolveWaitRequest.outcome_ref` 当前是弱类型 `str` | 代码事实：`dayu/host/api.py:1248` 确认 `outcome_ref: str`，无类型区分 |
| A4 | `WaitResolutionSource` 枚举已包含 POLL / CALLBACK / MANUAL | 代码事实：`dayu/host/api.py:220-228` 确认三成员完整 |
| A5 | `ToolAwaitSpec` 在 Engine 契约层定义且 Engine 只透传 `resume_token` | 代码事实：`dayu/contracts/tool_await.py:35-46` 确认，docstring 明确 Engine 不解析 |
| A6 | 设计真源 §20 已明确 Engine `tool_awaiting` / `run_suspended` 不能创建 wait record | `docs/host/design.md:2019` 确认 |

## Architecture Boundary Review

逐层检查：

- **Engine → Host**: Engine `tool_awaiting` / `run_suspended` 只能携带 accepted refs 作为 diagnostic / idempotent confirmation，不能创建 wait record、不能推进 Run 状态、不能关闭 Attempt。**PASS**
- **Host → Engine**: `resolve_wait` 是 Host command path，不穿透到 Engine；resume 时 Host 通过 RunInputBuilder 重建完整 messages 后走正常 dispatch pipeline。**PASS**
- **RemoteStub**: 讨论 non-goals 明确不实现 RemoteProxy 自治 resume；RemoteStub 不拥有 wait truth。**PASS**
- **Adapter → Host durable state**: wait poller 不持有 EventLog appender，只能通过 `resolve_wait` command path 提交结果。adapter key 存为 string ref，不存进程内 adapter 对象。**PASS**
- **Wait record vs EventLog**: wait record 是 active wait 查询索引，EventLog 是 canonical fact 真源；wait record 不替代 EventLog。**PASS**

## Findings

### F1-未修复-低-`observed_at` 字段类型未指定

- **位置**: 讨论 D1 与 design.md §20 resolve_wait request envelope
- **问题类型**: 契约缺失
- **当前写法**: 当前 `ResolveWaitRequest.observed_at: str`（`dayu/host/api.py:1250`），讨论只要求新 request 携带 `observed_at`，未指定是否继续为 `str` 或改为 `datetime`
- **反例/失败场景**: 若保持 `str`，implementation agent 可能接受任意字符串格式，调用方传入不一致的时区/格式，后续 diagnostic / audit 时间比较不可靠
- **为什么有问题**: wait record 的 `deadline_at` / `expires_at` 已是 typed datetime；`observed_at` 作为 adapter 观测时间应同等待遇，否则类型系统存在缺口
- **直接证据**: `dayu/contracts/tool_await.py:45` 定义 `deadline: datetime | None`；`ToolAwaitSnapshot.captured_at: datetime`（`tool_await.py:73`）均为 typed datetime
- **影响**: 实施 Agent 可能复制当前 `str` 设计，留下类型不一致
- **建议改法和验证点**: implementation plan 应要求 `observed_at` 使用 `datetime` 或 typed time wrapper；若因序列化边界需要 string，至少提供 parse validation。plan review milestone 验证
- **修复风险**: 低
- **严重程度**: 低

### F2-未修复-低-`lost` outcome 语义在 envelope 与 wait record 之间存在歧义

- **位置**: 讨论 D1 第 43 行 vs design.md §20 wait record 状态
- **问题类型**: 契约缺失
- **当前写法**: D1 描述 envelope 的 `lost` 为 "lost / unable-to-confirm outcome"（adapter 报告无法确认）；§20 line 2056 描述 wait record `lost` 为 "Host 无法确认外部 job 状态，且 policy 放弃继续等待"（Host 自主判断）
- **反例/失败场景**: implementation agent 可能把二者混为一谈——adapter 报告 lost 是否等价于 Host 把 wait record 标记为 lost？还是 adapter lost 只触发 Host policy 决定 wait record 走向 failed/lost/cancelled？
- **为什么有问题**: 两个不同主体（adapter 报告 vs Host 决策）的语义压缩到同一个 `lost` 枚举值，可能削弱 Host 作为治理真源的自主判定权
- **直接证据**: design.md §20 line 2095 "如果 job 状态无法确认，应进入 structured failed / lost" —— 说明 Host 对 "unable to confirm" 有 failed 和 lost 两条路径，不是无条件等于 lost
- **影响**: 低——第一版 external_job 工具大概率只有一种路径；但若枚举压缩过度，后续 split 需要 schema 迁移
- **建议改法和验证点**: implementation plan 应明确 envelope `lost` 是 adapter 的最佳判断（"adapter observation yielded no confirmable result"），wait record terminal status 由 Host resolve_wait pipeline 根据 envelope + policy 决定。plan 中加一行区分即可
- **修复风险**: 低
- **严重程度**: 低

### F3-未修复-中-late result diagnostic 记录路径在 Phase 7 无落地机制

- **位置**: 讨论 D4 与 design.md §22 late result rule
- **问题类型**: 切片过粗 / 不可直接实施
- **当前写法**: 迟到结果"只能进入 diagnostic / tool trace"（§22 line 2223-2224），但 Phase 8 才是 Projection Core / Tool Trace，Phase 7 自身没有定义 diagnostic 记录的具体载体
- **反例/失败场景**: Phase 7 implementation agent 实现 cancel → wait record cancelled → late result 到达时，发现没有可调用的 diagnostic 记录入口。两个坏结果：(a) agent 自行发明一个临时存储，(b) 静默丢弃 late result 不留任何痕迹，导致 operator 无法审计被拒绝的结果
- **为什么有问题**: Phase 7 的 late result rejection 是 correctness-critical 路径；若无最小 diagnostic 记录，late result 的审计链断裂，且后续 Phase 8 不可能重建 Phase 7 未记录的 diagnostic 事实
- **直接证据**: implementation-control.md Phase 7 验证要求只列 "unit tests: late result rejection"，未要求测试 late result 是否可被 diagnostic 记录；Phase 8 (Projection Core) 文档未提及需要跨 phase 消费 Phase 7 的 diagnostic 记录
- **影响**: Phase 7 实施留下一个 correctness 闭合依赖 Phase 8 的缺口；late result 可能被丢弃后无法审计
- **建议改法和验证点**: Phase 7 implementation plan 应包含最小 diagnostic 记录机制——至少 append 一个 `LATE_RESULT_DIAGNOSTIC` EventLog event（non-canonical，不影响 Run terminal state）或在 wait record 添加 `diagnostic_payload` 字段。不要求完整 tool trace 投影。plan review 验证该机制是否足以支撑 Phase 8 后续消费
- **修复风险**: 低——最小 diagnostic event 不改变任何状态机语义
- **严重程度**: 中

### F4-未修复-低-cancel 路径 "active wait record" 单数措辞不精确

- **位置**: design.md §22 line 2212-2213（已写回 diff）
- **问题类型**: 状态机漏洞
- **当前写法**: "CAS 标记 active wait record cancelled"——单数。design.md §20 基本路径暗示每次 Attempt closed as SUSPENDED 时只有一个 active wait record
- **反例/失败场景**: implementation agent 按单数实现 cancel，若未来一个 Attempt 内批量工具调用同时进入 awaiting（虽然当前设计未描述该路径），cancel 只标记一个 wait record
- **为什么有问题**: 防御性正确性要求 cancel 路径遍历 Run 下所有 `status=waiting` 的 wait records；当前单数措辞埋下盲区
- **直接证据**: `cancel_session_runs` §22 line 2243 "WAITING Run 取消 wait record" 同样未明确单复数。`resolve_wait` §20 line 2106 明确幂等范围是 `(wait_id, idempotency_key)` —— 说明一个 Run 可能有多个 wait_id
- **影响**: 低——当前设计下一个 Run 同一时刻只有一个 active wait record；但文本歧义可能在审阅中被误解
- **建议改法和验证点**: 将 §22 cancel 规则改为 "CAS 标记 Run 下所有 active (status=waiting) wait record 为 cancelled" 或至少加注 "Phase 7 第一版同一 Run 同时仅一个 active wait record，cancel 标记该 record 为 cancelled"
- **修复风险**: 低
- **严重程度**: 低

### F5-未修复-低-测试矩阵缺少竞态覆盖与 poll adapter 停轮询验证

- **位置**: implementation-control.md Phase 7 验证要求
- **问题类型**: 测试缺口
- **当前写法**: "unit tests: wait record state machine、resolve_wait idempotency、late result rejection" + "integration tests: awaiting -> resolve -> resumed local run"
- **反例/失败场景**: cancel 与 resolve_wait 并发提交时 first-committer-wins 逻辑未测试；poll adapter 检测到 wait record cancelled 后停止轮询的行为未验证
- **为什么有问题**: 这些是设计讨论明确决策的语义（D4 first-committer-wins, adapter best-effort stop），缺少测试将导致 correctness regression 不可检测
- **直接证据**: 讨论第 132 行 "cancel vs resolve first-committer-wins"；design.md §20 line 2113 "adapter 观察到 wait record cancelled 后，可以 best-effort cancel / revoke / abandon 外部 job"
- **影响**: Phase 7 核心正确性语义缺乏回归保护
- **建议改法和验证点**: implementation plan 的 test matrix 显式添加：(a) cancel-vs-resolve CAS race unit test，(b) poll adapter stop-after-wait-cancelled unit test。plan review 验证
- **修复风险**: 低
- **严重程度**: 低

### F6-未修复-低-"受限 typed refs" 对 snapshot_ref / external_job_id 未具体化

- **位置**: 讨论 D2 与 design.md §20 wait record model
- **问题类型**: 不可直接实施
- **当前写法**: "`snapshot_ref`、`external_job_id` 与 `snapshot_ref` 必须是强类型字段或受限 typed refs"（design.md §20 line 2047-2048）
- **反例/失败场景**: implementation agent 不知道 "受限 typed refs" 具体指什么——是一个带 validation 的 wrapper type？还是一个 constrained string？若实现为 bare `str`，设计约束丧失；若实现为过重的 typed wrapper，增加维护成本
- **为什么有问题**: 设计语言给 implementation agent 留下了需要自行设计的自由度，违反 "plan must be code-generation-ready" 原则
- **直接证据**: design.md §20 line 2047-2048 使用 "受限 typed refs" 但未定义约束
- **影响**: implementation agent 可能选错抽象级别，后续 review 返工
- **建议改法和验证点**: implementation plan 应明确：(a) `snapshot_ref` 是 `str` 还是 typed wrapper，其约束是什么（长度上限？格式？）；(b) `external_job_id` 是 `str | None` 还是 typed ID。若决定在第一版用 constrained string，显式写出约束
- **修复风险**: 低
- **严重程度**: 低

## Open Questions

无 blocking open question。上列 findings 均可在 implementation plan 阶段通过具体化解决，不要求回退设计讨论。

## Residual Risks

| # | Risk | Tracking |
|---|---|---|
| R1 | Phase 7 late result diagnostic 记录机制依赖 Phase 8 projection，若 Phase 8 设计变更可能影响 diagnostic event schema | implementation plan 应定义最小 diagnostic event 的 schema，作为 Phase 8 消费该事件的 forward contract |
| R2 | callback adapter contract 在当前非产品化状态下没有具体 typed protocol，Phase 8+ 产品化 callback 时可能需要调整 contract shape | 在 wait record / resolve_wait pipeline plan 中标记 callback source 的 adapter protocol 为 "stable-forward-deferred"，避免 Phase 7 对 callback 做过多假设 |
| R3 | `cancel_session_runs` 对 WAITING Run 的 cancel 路径在 Phase 7 实现，但该函数尚有不少其他 deferred 路径 | 确认 Phase 7 的 `cancel_session_runs` 变更只涉及 WAITING Run 部分，不影响 QUEUED 和 pre-dispatch STARTING 的已有 Phase 4 实现 |

## Final Plan Review Conclusion

**PASS**

六个 focus areas 均通过检查：

1. **ResolveWaitRequest typed outcome envelope**: 设计充分且最小——completed/failed/cancelled/lost 四值覆盖所有 tool terminal 种类，替代弱 `outcome_ref: str`。`dayu/host/api.py:1248` 当前 `outcome_ref: str` 无类型区分，typed envelope 消除此缺口。

2. **Wait record typed durable fields**: 字段列表足够（wait_id 到 status 共 13+ 字段），职责边界清晰（active wait 索引，不替代 EventLog）。

3. **Callback 限于 adapter contract**: 讨论 D3 与 design.md §20 line 2100-2102 对齐——Phase 7 只保留 `WaitResolutionSource.CALLBACK` 枚举值与 common pipeline 入口，不实现 HTTP 服务、认证、重放防护。

4. **WAITING cancel / late result**: 语义明确——cancel CAS 标记 wait record cancelled，Run 进入 CANCELLED，不创建 resume Attempt；late result 不得成为 canonical fact。

5. **Engine / RemoteStub 不拥有 wait truth**: design.md §20 line 2019 明确约束，讨论 non-goals 第 140 行排除 RemoteProxy 自治 resume。

6. **无过度设计**: non-goals 明确排除 callback HTTP endpoint、external job physical cancel 保证、retry/replay、recovery dispatch beyond adapter restore。

六条 findings 均非阻塞：F3（late result diagnostic 记录路径）为中等严重度但可在 plan 阶段以最小 diagnostic event 解决；其余五条为低严重度，属于措辞精度或 plan 具体化层面的改进项。

上列 findings 和 residual risks 应由 Phase 7 handoff implementation-ready plan 覆盖或显式 deferred-tracking。
