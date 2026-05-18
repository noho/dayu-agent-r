# Post-P10 Codex Challenge Review

- **Reviewer**: AgentCodex independent challenge reviewer
- **Review timestamp**: 20260518-152704
- **Gate**: Post-P10 / P10.5 discussion
- **Reviewed target**: `docs/host/post-p10.md`
- **Source of truth**: `docs/host/design.md`, `docs/host/implementation-control.md`
- **Existing artifacts reviewed**:
  - `docs/reviews/post-p10-public-contract-challenge-mimo-20260518.md`
  - `docs/reviews/post-p10-wiring-smoke-challenge-ds-20260518.md`
- **Proposition challenged**: P10.5 实施完后，后续 Service 只调用 Host public interface / contract 即可完成普通本地多轮会话闭环。
- **Conclusion**: fail for direct implementation; fail for implementation-ready plan until the blocking public-contract questions below are discussed and written back.

## Scope

本次只审查 P10.5 discussion 是否足以进入 code-generation-ready implementation plan，不实现源码、不修改计划文档、不提交、不推送。代码事实仅从授权范围读取：`dayu/host`、`tests/host`、`dayu/host/README.md`、`tests/README.md`。

## Assumptions Tested

- 普通本地多轮闭环至少需要：打开/关闭本地 Host runtime、提交首轮、提交 follow-up、提交后自动调度、等待 terminal、读取 final answer、关闭 runtime。
- “只调用 Host public interface / contract”意味着 Service 不导入 `dayu.host.dispatch`、durable store、scheduler internals，不直接查 SQLite 内部表，不读内部 payload descriptor。
- P10.5 可以排除 Recovery、真实 Service/CLI/WeChat/GUI 接入、真实业务工具发现、动态 ScenePrepare 和 web tools 迁移。
- P10.5 若需要新增或改变 `dayu.host` public API，必须先和用户讨论，不能由 planning / implementation agent 自行决定。

## Blocking Findings

### B1-未修复-高-P10.5 仍停留在 public API discussion brief，不能直接交给 implementation-ready plan

- **位置**: `docs/host/post-p10.md` Public API 变更护栏；`docs/host/implementation-control.md` Phase 10.5 关键设计问题。
- **问题类型**: open question 未收敛 / 公共契约缺失 / 不可直接实施
- **当前写法**: 文档已经正确识别 runtime、wakeup、terminal wait、answer read 都需要冻结，但仍以“必须确认”描述 public shape、生命周期、关闭语义、错误语义和 read contract。
- **反例/失败场景**: planning agent 被要求写 implementation-ready plan 时，必须自行选择 `HostLocalRuntime` 命名、sync/async open/close、暴露 command facet 还是 wrapper methods、wait API 形状、answer payload decoder、错误码和取消语义。不同 agent 可生成互不兼容的 public contract，implementation review 时也无法判断哪一个是用户确认过的契约。
- **为什么有问题**: 本项目总控要求 material open question 必须先和用户讨论；P10.5 自身也声明 public API 变更不能由 implementation 直接改。当前文档列出了要讨论的问题，但没有记录决策，因此还不是 code-generation-ready plan 输入。
- **直接证据**:
  - `docs/host/post-p10.md:31` 要求 P10.5 如需新增、删除或改变 `dayu.host` public API，必须先和用户讨论。
  - `docs/host/post-p10.md:37` 到 `docs/host/post-p10.md:40` 把 `dayu.host.__all__`、runtime 入口和 final answer read path 明确列为 public API 范围。
  - `docs/host/post-p10.md:42` 说明只要普通 Service 依赖新的稳定入口，就必须先完成 public API discussion。
  - `docs/host/implementation-control.md:216` 到 `docs/host/implementation-control.md:217` 要求 material open question 出现时停下来和用户讨论，不得让 planning / implementation agent 自行选择 public contract。
  - `docs/host/implementation-control.md:1210` 到 `docs/host/implementation-control.md:1215` 连续使用“必须确认”列出 runtime shape、wakeup、Run 状态语义、terminal wait / answer read contract 与 API 变更写回要求。
  - `docs/host/design.md:818` 到 `docs/host/design.md:824` 规定 Host 公共接口是稳定命名空间，内部 durable / dispatch / policy 类型不得暴露。
  - `dayu/host/command.py:242` 到 `dayu/host/command.py:246` 显示当前 `create_host_command_handle` 明确拒绝 `local_execution`，要求显式打开 scheduler。
  - `dayu/host/__init__.py:101` 到 `dayu/host/__init__.py:188` 当前包根导出没有 local runtime、terminal wait 或 answer read facade。
- **影响**: implementation-ready plan 会被迫承担 public API 设计裁决；后续 Service contract 可能由实现便利驱动，而不是由用户确认的 Host public contract 驱动。
- **建议改法和验证点**:
  - 先做一次 P10.5 public API decision pass，并写回 `docs/host/post-p10.md` 或 P10.5 phase plan。
  - 至少冻结：runtime public 名称、构造 options、sync/async lifecycle、command facet 暴露方式、关闭语义、scheduler wakeup ownership、terminal wait API 或轮询 contract、answer read 返回类型和错误语义。
  - 决策写回后再生成 implementation-ready plan；plan 应引用这些已确认决策，而不是重新设计。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 高

### B2-未修复-高-follow-up execution target / scene-policy continuity 被降级过早，仍是 plan 前 public contract question

- **位置**: `docs/host/post-p10.md` Challenge Review 裁决；`dayu.host` follow-up public API。
- **问题类型**: 公共契约缺失 / open question 未收敛 / 目标过窄
- **当前写法**: 总控裁决把 follow-up execution target 默认值、per-run scene / policy 输入列为 non-blocking / discussion，并说明 scene / policy 在 P10.5 可先写死。
- **反例/失败场景**: 首轮通过 `StartRunRequest.execution_target` 指向某个 runner/profile，但第二轮 `SubmitFollowupRequest` 没有 execution target。实现 agent 可能继续使用内部硬编码默认值，导致第二轮不保证沿用首轮 runner、tool profile、scene policy 或 runtime profile。smoke 如果只配置单一 fake runner 会通过，但后续 Service 仍不知道 ordinary follow-up 的目标选择 contract。
- **为什么有问题**: “普通本地多轮”不是只拿到第二个字符串，还要求同一会话的后续输入在稳定 Host contract 下选择可解释的执行目标与 policy。当前代码把该选择隐藏在 command facade 内部常量中；如果 P10.5 要冻结 Service contract，至少必须先让用户确认 P10.5 的选择边界。
- **直接证据**:
  - `docs/host/post-p10.md:292` 将 follow-up execution target 默认值、per-run scene / policy 输入列为 non-blocking / discussion。
  - `docs/host/post-p10.md:269` 允许 mock / 写死输入提供 scene inputs、RunnerSpec、AgentPolicy 等装配，但没有定义 follow-up 如何继承或选择这些装配。
  - `dayu/host/api.py:1416` 到 `dayu/host/api.py:1435` 显示 `StartRunRequest` 有显式 `execution_target`。
  - `dayu/host/api.py:1528` 到 `dayu/host/api.py:1548` 显示 `SubmitFollowupRequest` 没有 `execution_target`、scene profile 或 policy profile 字段。
  - `dayu/host/command.py:108` 定义 `_PUBLIC_FOLLOWUP_DEFAULT_EXECUTION_TARGET = "host-public-followup-default"`。
  - `dayu/host/command.py:469` 到 `dayu/host/command.py:474` 在 `submit_followup` 中把 follow-up resolved target 写成该内部默认值。
  - `docs/host/design.md:1818` 说明若未来支持多 scene tool profile，Service 可以通过 typed `tool_profile_ref` 或独立 Host handle 选择工具集合，且该扩展必须冻结到 Attempt snapshot，不能塞进 metadata。
  - `docs/host/design.md:2450` 说明 context window / reserved output tokens 是 Service / composition root 显式 typed input，不能从 per-run metadata 或 extra payload 读取。
- **影响**: P10.5 可能冻结一个只对单 runner mock smoke 成立的接口；后续 Service 一旦需要稳定选择或继承 runner / policy / tool profile，就不能只依赖已冻结 Host public contract。
- **建议改法和验证点**:
  - plan 前请用户确认 P10.5 ordinary scope 采用哪一种 contract：
    1. 单 runtime profile：follow-up 始终使用 Host local runtime construction-time profile，`StartRunRequest.execution_target` 在 P10.5 smoke 中只作为诊断 target；
    2. 继承语义：follow-up 自动继承同 Session / source Run 的 execution target 与 policy snapshot；
    3. 显式字段：给 follow-up 增加 typed target/profile 字段；
    4. 独立 Host handle：不同 scene/tool profile 通过不同 runtime handle 表达。
  - 该决策必须写入 P10.5 plan，并用 smoke 断言第二轮请求实际使用的 runner/policy/tool profile 来源。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 高

## Non-Blocking Findings

### N1-未修复-中-S3 real-runner smoke 的 skip 语义需要在 plan 中写清，否则会制造验收歧义

- **位置**: Smoke coverage matrix 与 P10.5 退出条件。
- **问题类型**: 测试缺口 / 验收边界不清
- **当前写法**: 文档同时要求 no-tool、mock-tool、real-runner 多轮 smoke 都走同一路径，也允许真实 provider 环境不可用时 skip。
- **反例/失败场景**: implementation plan 把 S3 作为必须实际通过的本地测试，CI 无 API key / 网络时 P10.5 无法验收；或者相反，review agent 看到 skip 就认为 real-runner path 未覆盖，误报 blocker。
- **为什么有问题**: 真实 runner smoke 只证明 provider 链路可跑，确定性 correctness 已由 mock smoke 承担。skip 语义需要在 plan 的 validation section 变成明确规则。
- **直接证据**:
  - `docs/host/post-p10.md:98` 到 `docs/host/post-p10.md:104` 说明 S3 不替代 S1/S2，且 provider key / 网络不可用时测试必须明确 skip。
  - `docs/host/implementation-control.md:1228` 允许 real-runner smoke 环境不可用时明确 skip。
  - `docs/host/implementation-control.md:1239` 又把 no-tool、mock-tool、real-runner smoke 均使用同一路径写为退出条件，未在退出条件本身重复 skip 规则。
- **影响**: 可能造成 plan/review 对 S3 的 blocking 边界不一致。
- **建议改法和验证点**: P10.5 plan 明确：S3 测试文件必须存在并使用同一 runtime/public path；缺 provider 环境时以明确 skip 计入 `not covered but accepted`，validation 报告必须列出 skip 条件和未执行原因。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### N2-未修复-中-现有 tests README 对 Phase 5 / 10 集成测试的描述不能作为 P10.5 coverage 证据

- **位置**: `tests/README.md` Host 测试说明；`tests/host/test_phase5_local_execution_integration.py` helper。
- **问题类型**: 测试缺口 / 文档与测试证据不一致
- **当前写法**: `tests/README.md` 描述 Phase 5 / 10 本地执行集成使用 public `start_run`、真实 scheduler、runtime lane 与 fake worker 覆盖 no-tool Engine 闭环，且“不绕过 scheduler 直接改生产状态”。
- **反例/失败场景**: P10.5 plan 或 review 直接引用既有集成测试作为 S1 public runtime smoke 证据。但该测试手工导入 scheduler、手工 wake/drain，并通过 SQLite 查询内部表；它可以证明内部组件工作，不能证明 Service 只调 public runtime/read path。
- **为什么有问题**: `post-p10.md` 已规定绕过 Host local runtime、操作 scheduler internals、直接查询 durable 内部表的 smoke 不计入 coverage。README 当前描述容易让 plan 误用旧测试。
- **直接证据**:
  - `tests/README.md:97` 说 `test_phase5_local_execution_integration.py` 覆盖 no-tool Engine 闭环且不绕过 scheduler 直接改生产状态。
  - `tests/host/test_phase5_local_execution_integration.py:55` 直接 import `HostDispatchScheduler`。
  - `tests/host/test_phase5_local_execution_integration.py:410` 到 `tests/host/test_phase5_local_execution_integration.py:412` 手工调用 `scheduler.wake_queue_promotion(...)` 和 `scheduler.drain_once()`。
  - `tests/host/test_phase5_local_execution_integration.py:1242` 到 `tests/host/test_phase5_local_execution_integration.py:1261` 直接查询 `host_runs`、`host_attempts`、`host_attempt_dispatch_records`。
  - `tests/host/test_phase5_local_execution_integration.py:1289` 到 `tests/host/test_phase5_local_execution_integration.py:1295` 直接查询 `host_runs` 状态。
  - `docs/host/post-p10.md:124` 明确此类 smoke 不能计入 coverage。
- **影响**: 可能低估 P10.5 新 smoke 的必要性，或让 implementation-ready plan 只修旧测试而没有新增真正 public-path smoke。
- **建议改法和验证点**: P10.5 plan 明确既有 Phase 5 / 10 集成测试只作为内部 wiring 回归；S1/S2/S3 coverage 必须新增或重写为只经 P10.5 Host local runtime / public command / public read path。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

## Accepted-As-Is Findings

### A1-已接受-严重-缺 Host local runtime / composition root 的 blocking 裁决充分

- **位置**: MiMo B2、DS B1、总控 accepted blocking。
- **问题类型**: accepted-as-is / 架构边界 / 公共契约缺失
- **当前写法**: MiMo 与 DS 均裁定 Service 缺少稳定 Host runtime / composition root，无法只调 public API 跑起来；总控已接受。
- **直接证据**:
  - `docs/reviews/post-p10-public-contract-challenge-mimo-20260518.md:30` 到 `docs/reviews/post-p10-public-contract-challenge-mimo-20260518.md:41` 将缺 composition root 标为 critical blocker。
  - `docs/reviews/post-p10-wiring-smoke-challenge-ds-20260518.md:15` 到 `docs/reviews/post-p10-wiring-smoke-challenge-ds-20260518.md:24` 将缺 Host runtime / composition root 标为 blocking。
  - `docs/host/post-p10.md:287` 接受该 blocking。
  - `dayu/host/command.py:242` 到 `dayu/host/command.py:246` 显示 command handle 拒绝本地执行配置。
  - `dayu/host/dispatch.py:386` 到 `dayu/host/dispatch.py:399` 显示 scheduler 构造依赖 transaction runner、event log、local execution、lane controller、registry 等内部依赖。
- **判断**: 裁决充分，无误判。它是 P10.5 的核心 root cause 之一。

### A2-已接受-严重-public command facade 与 scheduler wakeup 无公共接线的 blocking 裁决充分

- **位置**: MiMo B3、DS B2、总控 accepted blocking。
- **问题类型**: accepted-as-is / 接线缺失 / 生命周期漏洞
- **当前写法**: MiMo 与 DS 均指出 `start_run` / `submit_followup` 提交后默认 no-op wakeup，Run 会停在 accepted/queued。
- **直接证据**:
  - `docs/reviews/post-p10-public-contract-challenge-mimo-20260518.md:43` 到 `docs/reviews/post-p10-public-contract-challenge-mimo-20260518.md:55` 将 wakeup 接线缺失标为 critical blocker。
  - `docs/reviews/post-p10-wiring-smoke-challenge-ds-20260518.md:26` 到 `docs/reviews/post-p10-wiring-smoke-challenge-ds-20260518.md:39` 将 command facade 与 scheduler wakeup 缺失标为 blocking。
  - `docs/host/post-p10.md:288` 接受该 blocking。
  - `dayu/host/admission.py:456` 到 `dayu/host/admission.py:458` admission commit 后会调用 projection catch-up 和 wakeup。
  - `dayu/host/admission.py:683` 到 `dayu/host/admission.py:688` 默认注入 no-op wakeup / no-op projection catch-up port。
  - `dayu/host/command.py:253` 到 `dayu/host/command.py:255` 创建 command handle 时未传真实 wakeup port。
  - `dayu/host/dispatch.py:490` 到 `dayu/host/dispatch.py:504` scheduler 的真实 wakeup 是内部对象方法。
- **判断**: 裁决充分。它与 A1 相关但不重复；composition root 可以是修复载体，wakeup 是必须被 contract 覆盖的行为。

### A3-已接受-严重-final answer public read path 与 terminal wait contract 的 blocking 裁决充分

- **位置**: MiMo B1/B4、DS B3、总控 accepted blocking。
- **问题类型**: accepted-as-is / 公共读取契约缺失
- **当前写法**: MiMo 与 DS 均指出 Service 可以知道 Run succeeded，却没有 public 方法稳定等待 terminal 并读取回答正文；总控已接受 terminal wait 和 answer read。
- **直接证据**:
  - `docs/reviews/post-p10-public-contract-challenge-mimo-20260518.md:17` 到 `docs/reviews/post-p10-public-contract-challenge-mimo-20260518.md:29` 将 final answer 内容读取缺失标为 critical blocker。
  - `docs/reviews/post-p10-public-contract-challenge-mimo-20260518.md:56` 到 `docs/reviews/post-p10-public-contract-challenge-mimo-20260518.md:72` 要求冻结 terminal 等待 public pattern。
  - `docs/reviews/post-p10-wiring-smoke-challenge-ds-20260518.md:40` 到 `docs/reviews/post-p10-wiring-smoke-challenge-ds-20260518.md:52` 将 public final answer read path 缺失标为 blocking。
  - `docs/host/post-p10.md:289` 到 `docs/host/post-p10.md:290` 接受 final answer read path 与 terminal wait contract blocker。
  - `dayu/host/api.py:1696` 到 `dayu/host/api.py:1709` 的 `TerminalResultSummary` 只有 status/ref/digest。
  - `dayu/host/api.py:1977` 到 `dayu/host/api.py:1984` 的 `HostEventView` 只有 payload ref/digest，不含 payload 内容。
  - `dayu/host/read_api.py:37` 到 `dayu/host/read_api.py:87` public read API 只有 `get_session`、`get_run`、`stream_run_events`。
  - `dayu/host/engine_ingest.py:1968` 到 `dayu/host/engine_ingest.py:2005` 会写 terminal summary payload，但当前读取路径不在 public API 中。
- **判断**: 裁决充分。MiMo 对 terminal wait 的补充已经被总控吸收，不再遗漏。

### A4-已接受-高-S1/S2/S3 smoke 尚未落地应作为 P10.5 exit blocker，而不是当前代码 root cause blocker

- **位置**: DS B4/B5、总控 accepted blocking、Smoke Coverage Matrix。
- **问题类型**: accepted-as-is / 测试缺口 / 严重度校正
- **当前写法**: DS 将 smoke 不存在、现有测试绕过 public API 标为 blocking；总控接受为 S1/S2/S3 smoke 尚未落地，现有测试不能证明命题。
- **直接证据**:
  - `docs/reviews/post-p10-wiring-smoke-challenge-ds-20260518.md:54` 到 `docs/reviews/post-p10-wiring-smoke-challenge-ds-20260518.md:65` 指出不存在通过 public API 的多轮 smoke。
  - `docs/reviews/post-p10-wiring-smoke-challenge-ds-20260518.md:67` 到 `docs/reviews/post-p10-wiring-smoke-challenge-ds-20260518.md:79` 指出现有测试直接查询内部表。
  - `docs/host/post-p10.md:62` 到 `docs/host/post-p10.md:83` 定义 S1 必须覆盖 runtime、public command、wakeup、memory continuity 和 public read path。
  - `docs/host/post-p10.md:85` 到 `docs/host/post-p10.md:95` 定义 S2 mock-tool multi-turn 覆盖 ToolRuntime schema/executor/accept barrier/memory。
  - `docs/host/post-p10.md:96` 到 `docs/host/post-p10.md:104` 定义 S3 real-runner smoke。
  - `docs/host/post-p10.md:124` 规定绕过 Host local runtime、scheduler internals 或 durable 内部表的 smoke 不计入矩阵。
  - `docs/host/post-p10.md:291` 接受 S1/S2/S3 smoke 尚未落地为 blocking。
- **判断**: 裁决方向正确，但严重度应解释为 P10.5 exit / verification blocker，不是独立于 A1-A3 的当前代码 root cause。DS B5 与 coverage matrix 重复，作为证据接受即可。

## MiMo / DS 裁决总评

- **充分**: A1、A2、A3 覆盖了 Service 最小闭环的核心 public contract 缺口；A4 覆盖了验证缺口。
- **严重度校正**: “smoke 尚未落地”应作为 P10.5 exit blocker；“现有测试绕过 public API”是为什么旧测试不能计入 coverage 的证据，不必作为独立 root blocker 反复计数。
- **遗漏**: B2 中的 follow-up execution target / scene-policy continuity 被降级为 non-blocking 过早。它不一定要求新增字段，但必须在 plan 前由用户确认 contract。
- **重复**: composition root 与 wakeup 有实现依赖关系但不是重复；前者是入口/lifecycle，后者是提交后执行语义。

## Open Questions Requiring User Discussion Before P10.5 Plan

1. Host local runtime / composition root 的 public 名称、构造 options、暴露 facet、sync/async open/close、关闭时是否 cancel active workers、关闭后 command/read API 错误语义。
2. terminal wait / answer read contract：是 runtime helper、独立 public function，还是官方轮询 pattern；返回 `str`、typed JSON summary 还是 payload view；digest 校验、missing payload、timeout、cancel、Run failed/lost/cancelled 的错误语义。
3. follow-up execution target / scene-policy continuity：P10.5 是单 runtime profile、follow-up 继承首轮 target/profile、follow-up 增加 typed target/profile 字段，还是通过独立 Host runtime handle 表达 profile。
4. S3 real-runner smoke 的验收规则：provider 环境不可用时如何在 coverage checklist 中记录 skip，不让 skip 变成 blocker 或假覆盖。

## Residual Risks

- 本 review 未检查 Recovery、RemoteProxy、真实 web tools、ConfigLoader、真实业务工具 discovery、真实 Service/CLI/WeChat/GUI 接入，因为 P10.5 明确排除这些范围。
- 未运行测试；本任务是 challenge review 与 artifact，不做源码实现或验证。
- P10.5 plan 若在未解决 B1/B2 的情况下生成，最大风险是 public API 被 implementation agent 设计成测试友好但 Service 不稳定的临时接口。

## Final Plan Review Conclusion

- **Conclusion**: fail
- **Can `docs/host/post-p10.md` be handed to an Agent for P10.5 implementation-ready plan?** No, not yet. It is a good discussion input, but B1/B2 的 public contract decisions must be discussed and written back first.
- **Can P10.5 go directly to implementation?** No.
- **Blocking findings**: 2
- **Non-blocking findings**: 2
- **Accepted-as-is findings**: 4
