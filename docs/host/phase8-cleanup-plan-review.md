# Plan Review — Host P8 Legacy Cleanup + Code-Review Fix

## Reviewed Target

- Plan artifact: `docs/host/phase8-cleanup-plan.md`
- Surrounding context:
  - `docs/host/phase8-plan.md`（P8 设计真源）
  - `docs/reviews/code-review-20260510-{0825,0830,0831}.md`（三轮 review accepted findings）
  - `dayu/host/_run_harness.py`、`_attempt_supervisor.py`、`_attempt_lease.py`、`_run_state_store.py`、`_conversation_memory_durable.py`、`_tool_runtime.py`、`__init__.py`
  - 测试集 `tests/host/test_phase8_*.py`、`tests/host/test_phase1_public_boundary.py`、`tests/host/test_phase2_tool_runtime_*.py`、`tests/host/test_phase5_multiturn_no_governance_smoke.py`、`utils/smoke_host_*.py`

## Assumptions Tested

1. `AttemptSupervisor.append_terminal_and_close` 已经满足 `_handle_owner_lost` 的全部需求 —— 包含 lease_exit_stack 退出、stream signal、CAS miss 不抛断流。
2. 删除 package-level `start_run` / `stream_run_events` / `get_run_result` / `fetch_more_tool_result` 后，仅有「测试 + utils smoke」消费方，无 production / dayu-cli 调用。
3. 删除 `_default_harness_for_running_loop` / `_build_default_harness` 后，所有依赖默认装配的单元测试都能改为显式构造 `LocalRunHarness`（test-only deps）或 `build_durable_harness`。
4. `LocalRunHarness.fetch_more_tool_result` 删除后，框架 `fetch_more` 工具仅经 Engine → ToolRuntimeToolExecutor → `InMemoryToolRuntime.execute_tool_call`，调用方无需直接补读入口。
5. `mark_recovering_and_create_attempt` 仅供 supervisor 使用，可在 supervisor 不再调用后整体下线（或保留方法但 supervisor 不调用）。
6. `_finish_attempt_if_durable` 的 legacy（无 supervisor）durable fallback 没有非测试调用方。
7. 删除 P6 legacy fallback 后，`AttemptStateStore` 仅在显式 non-durable 测试场景使用，`PlainRunEventAppender` 仅服务这种场景。

逐项压测后的判断详见 findings。

## Findings

### F01-未修复-[严重]-Plan 未消除三处旧测试断言「attempt_lease_lost terminal RunEvent 必须写入」，与 D1 同事务 CAS-miss 不写直接矛盾

- **位置**: Slice S3 「测试」与 `tests/host/test_phase8_attempt_supervisor.py:1151,1318,1324,1342`
- **问题类型**: 测试缺口 / 不可直接实施
- **当前写法**: S3 仅在 bullet 中要求「修正旧测试中把 owner-lost 后写 attempt_lease_lost terminal 当成期望行为的断言（参考 0831 residual risk 提示）」，但没有列出具体测试与断言要改成什么。
- **反例/失败场景**: `test_phase8_attempt_supervisor.py:1318` 显式 `assert host_data.error_code == "attempt_lease_lost"`、`:1342` 断言 `summary.startswith("attempt_lease_lost:")`。D1 改造后，CAS miss 路径不再写 RUN_FAILED，这些 assert 立刻失败；但 owner 仍有效（fenced + lease 未过期）的 owner-lost 场景下，原子路径会写入 terminal RunEvent 并把 attempt 推到 `LOST`，仍然能保留诊断可见性。Plan 没有切分这两种场景，implementation agent 极可能直接「期望反转」断言，或退回旧路径以「保住测试」。
- **为什么有问题**: AGENTS.md「测试必须跟着实现边界迁移，不得为了保住旧测试而在生产代码里堆兼容逻辑」的硬约束需要 plan 明确切分语义；CAS hit 与 CAS miss 的可观测对比是 D1 的核心契约，必须显式写进 slice 验证点。
- **直接证据**: `dayu/host/_run_harness.py:1060` 当前裸 append；`tests/host/test_phase8_attempt_supervisor.py:1318/1324/1342` 现有断言；plan §Slice S3 测试只字未提具体行号或断言改写规则。
- **影响**: implementation agent 在 S3 落地时，要么放弃 D1 原子化（保住旧断言）→ 0830-F1 仍未消除；要么粗暴反转断言 → 失去 owner-lost 诊断信号 → 真实回归无法 review 验收。
- **建议改法和验证点**:
  - S3 plan 增加显式分类测试矩阵：
    - **Case A (CAS hit, owner 仍有效但 loss_reason 触发)**: 走 `append_terminal_and_close` 原子路径 → EventLog 出现 1 条 `RUN_FAILED(error_code=attempt_lease_lost)`、`host_attempts.state=LOST`、`terminal_event_position` 非空。
    - **Case B (CAS miss, recovery 已替换 owner)**: 不写任何 RunEvent，`host_attempts.state` 保持 recovery 推进后的值，旧 owner harness 返回不抛断流但记 typed log。
  - S3 plan 列出必须改写的具体测试位置：`test_phase8_attempt_supervisor.py:1151-1342` 改为对 Case A 验证；新增 Case B 用例。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 严重

### F02-未修复-[高]-Plan 未列出删除 package-level convenience 后必须迁移的具体测试与 utils smoke，存在明确反例

- **位置**: Slice S1 / S9 与 `tests/host/test_phase1_run_harness.py`、`test_phase1_public_boundary.py`、`test_phase2_tool_runtime_eventlog.py`、`test_phase2_tool_runtime_truncation.py`、`test_phase2_tool_runtime_boundary.py`、`test_phase5_multiturn_no_governance_smoke.py`、`utils/smoke_host_tool_runtime.py`、`utils/smoke_host_multiturn_no_governance.py`、`utils/smoke_engine_worker.py`
- **问题类型**: 切片过粗 / 不可直接实施
- **当前写法**: S1「迁移 `tests/host/test_run_harness*.py` 等任何依赖 `dayu.host.start_run` 等 API 的测试」（不存在 `test_run_harness*.py` 文件名）；S9「替换 `from dayu.host import start_run` 等导入为显式 `LocalRunHarness` / `build_durable_harness`」也只是抽象描述。
- **反例/失败场景**: `grep` 显示实际依赖入口的文件包含 `test_phase1_public_boundary.py:57-59` 直接断言 `__all__` 含 `"fetch_more_tool_result"` / `"get_tool_fetch_more_handle"`，删除即整测试失败；`test_phase2_tool_runtime_*.py` 共 14 处直接调用 `runtime.get_tool_fetch_more_handle(...)`，这是 `InMemoryToolRuntime` 的方法不是 `LocalRunHarness` 的，与 S1 删除范围（harness method + 模块级转发）有交叉但不同；`utils/smoke_host_tool_runtime.py:246-285` 也调用 `harness.fetch_more_tool_result`。
- **为什么有问题**: plan 没有把「`InMemoryToolRuntime.get_tool_fetch_more_handle` 是否一并删除」纳入 D6 决策。如果保留 ToolRuntime 入口但删 Harness 透传，等于把绕过点下移；如果一并删除，则需要把 `test_phase2_tool_runtime_*.py` 的 14 处全部迁移到 `execute_tool_call` 路径——这是非平凡的测试改写，必须列入 plan，否则实施时无从判断「是改测试还是停下来问」。
- **直接证据**: `dayu/host/_tool_runtime.py:695` 的 `async def get_tool_fetch_more_handle`；`tests/host/test_phase2_tool_runtime_eventlog.py:194..434` 直接调用；`utils/smoke_host_tool_runtime.py:246-285` 直接调用。
- **影响**: implementation agent 必然停下问 controller，或自行做架构裁决（fetch_more 工具入口是否仍存在），plan 无法直接生成代码。
- **建议改法和验证点**:
  - 在 D6 显式决定 `InMemoryToolRuntime.get_tool_fetch_more_handle` 与 `fetch_more` 是否保留为 ToolRuntime 接口（用户原话「framework fetch_more 仅作普通 tool call 经 ToolRuntimeToolExecutor → InMemoryToolRuntime.execute_tool_call」语义上倾向删除独立入口）。
  - 在 S1 文件清单加入：`test_phase1_public_boundary.py`、`test_phase2_tool_runtime_eventlog.py`、`test_phase2_tool_runtime_truncation.py`、`test_phase2_tool_runtime_boundary.py`、`test_phase5_multiturn_no_governance_smoke.py`、`utils/smoke_host_tool_runtime.py`。逐文件给出迁移目标（用 `execute_tool_call` 还是删除整测）。
  - 添加验证：`grep -RIn "fetch_more_tool_result\|get_tool_fetch_more_handle" dayu tests utils` 结果应为空。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 高

### F03-未修复-[高]-`AttemptRecoveryDecision` 字段重构会破坏现有 phase8 recovery 测试与 typed log 字段，plan 未给出兼容/迁移指令

- **位置**: §Implementation Decisions D2、Slice S5 / S10；现状 `dayu/host/_attempt_lease.py:283-305`、`_attempt_supervisor.py:765-774`
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: D2 写「删除 `recovery_attempt_id` / `recovery_attempt_index`，保留 `action` / `source` / `reason`」并改 docstring；S5 验证只说「scan 后旧 attempt 进入 LOST，无新 RUNNING attempt；EventLog 不被 recovery scan 直接写入」。
- **反例/失败场景**:
  - `_attempt_supervisor.py:765` 的 `_LOGGER.info("...recovery_attempt_id=%s reason=%s", ..., decision.recovery_attempt_id, decision.reason)` 会因字段消失而 AttributeError；
  - `tests/host/test_phase8_attempt_recovery.py` 极可能 assert `decision.recovery_attempt_id is not None`（typed 决策语义就是为了让 caller 拿到新 attempt id）；
  - `AttemptRecoveryAction.MARK_RECOVERING_AND_CREATE_ATTEMPT` 枚举值如果删除，会破坏所有引用该值的字符串/枚举消费方；如果保留，与 D2「不再创建 RUNNING recovery attempt」语义矛盾（死代码 enum）。
- **为什么有问题**: plan 没有处理枚举层面的 contract 变更：
  - 应该明确 `AttemptRecoveryAction` 的新枚举集合（例如保留 `MARK_LOST` / `NOOP_TERMINAL`，删除 `MARK_RECOVERING_AND_CREATE_ATTEMPT`）；
  - 应该明确 `recover_stale_attempts` 的返回元素是否仍叫 `AttemptRecoveryDecision` 或改名；
  - 应该给出 typed log 字段调整。
- **直接证据**: `dayu/host/_attempt_lease.py:283-305`（枚举 + dataclass 定义）；`dayu/host/_attempt_supervisor.py:765-774`（log 引用 `recovery_attempt_id`）；plan §D2 仅写字段层面调整。
- **影响**: implementation agent 必须自行裁决枚举集与 log 字段，等于在实施期做架构选择。
- **建议改法和验证点**:
  - D2 增加：「`AttemptRecoveryAction` 枚举仅保留 `MARK_LOST`、`NOOP_TERMINAL`；删除 `MARK_RECOVERING_AND_CREATE_ATTEMPT` 整套引用」。
  - D2 显式列出 typed log 字段：`source_attempt_id`、`action`、`reason`、`source='recovery_scan'`。
  - S5 测试验证矩阵补：调 `recover_stale_attempts` 后没有任何新 attempt 行；`AttemptRecoveryDecision.action` ∈ {`MARK_LOST`, `NOOP_TERMINAL`}；幂等（连续两次扫描旧 attempt 已 LOST → 第二次空决策）。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 高

### F04-未修复-[高]-D5「durable harness 必须有 supervisor」契约改造会让 build_durable_harness 装配链做隐式架构选择，但 plan 没说装配链怎么改

- **位置**: §D5 / §D7、Slice S4
- **问题类型**: 架构边界 / 契约缺失
- **当前写法**: 「durable harness 必须有 supervisor，这是 `build_durable_harness` 的契约前提；如果 `LocalRunHarness` 在 durable 模式下没有 supervisor，构造时即应 fail fast」。
- **反例/失败场景**: 当前 `LocalRunHarness.__init__` 没有 `is_durable` flag，supervisor 是可选注入；`build_durable_harness` 总是注入 supervisor；但 `LocalRunHarness` 也接受「durable 但没 supervisor」的混合配置（旧测试 / 半 durable 路径）。直接 fail fast 要求构造 invariant 重定义，影响哪些 fixture 不明。
- **为什么有问题**: plan 没说：
  - `LocalRunHarness` 是否新增 `is_durable: bool` 构造参数（D7 暗示需要），与 supervisor / event_store / attempt_state_store 三者的合法组合矩阵是什么；
  - 还是改为「以 `event_store is DurableRunEventStore` 推断 durable」（违反 AGENTS.md「禁止 hasattr/isinstance 当类型逃避」）；
  - 还是「以 `attempt_supervisor is not None` 推断 durable」（语义不严格）。
- **直接证据**: `dayu/host/_run_harness.py:1784-1808` 当前用 `attempt_supervisor / attempt_state_store / storage` 三个字段三态判断；plan §D5/D7 未规定单一真源字段。
- **影响**: implementation agent 必须自行选 invariant；选错会让其它路径（如 conversation memory 装配、pause / resume 入口）出现 fail-fast 误报。
- **建议改法和验证点**:
  - D7 加入：「`LocalRunHarness` 新增 `is_durable: bool` 显式构造参数；`build_durable_harness` 传 `True`；test-only 装配传 `False`。`is_durable=True` 时 supervisor / event_store(DurableRunEventStore) / attempt_state_store=None 是 invariant；构造时按 invariant 校验，违反 raise `RuntimeError`。」
  - 同步 `InMemoryToolRuntime` 的 `is_durable` flag 来自该 harness 的 flag（避免双源真实）。
  - S4 验证：构造 `LocalRunHarness(is_durable=True, attempt_supervisor=None)` 应 raise；构造 `LocalRunHarness(is_durable=True, attempt_state_store=non_none)` 也应 raise。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 高

### F05-未修复-[中]-Slice 顺序：S1 删除 `_default_harness_for_running_loop` 但 S2 才落 `_resolve_attempt_appender` fail-fast，存在 S1 后跑测试时 PlainRunEventAppender 仍在 durable 路径被使用

- **位置**: Slice S1、S2 排序
- **问题类型**: 不安全 sequencing
- **当前写法**: S1 先删入口 + 改测试；S2 再加 durable fail-fast。
- **反例/失败场景**: S1 完成后跑全量 phase8 测试，若 `tests/host/test_phase8_tool_runtime_fencing.py` 之外的测试构造的 harness 仍能在 durable 路径走 plain appender，0831-F003 不被消除；此时 controller 可能误判 S1 已通过。
- **为什么有问题**: plan 把入口删除与边界 fail-fast 拆成两 slice，留出 plain fallback 仍可被触达的窗口；review gate 容易把这种「测试通过但漏洞仍在」的状态错判为 ready。
- **直接证据**: 当前 `dayu/host/_run_harness.py:482-...` `_resolve_attempt_appender` 与 `dayu/host/_tool_runtime.py:378-381` `_resolve_appender` 的 plain fallback；plan §S1/S2 顺序。
- **影响**: 中——窗口仅存在于 slice 之间，但 review artifact 状态会与实际不变量不一致。
- **建议改法和验证点**:
  - 调整顺序：S1 → S2（durable fail-fast）→ S3（owner-lost 原子化）→ ...；或合并 S1+S2 为单 slice，但要求 file ownership 仍然清晰。
  - 增加 S2 验证：`grep -n "PlainRunEventAppender" dayu/host` 必须只在 test-only 路径出现，并且其使用方都标记 `is_durable=False`。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### F06-未修复-[中]-`mark_recovering_and_create_attempt` 删除决策被定义为「grep 后决定」，但 grep 应在 plan 阶段完成，否则 S5 是非确定 slice

- **位置**: §A1 working assumption + Slice S5
- **问题类型**: open question 未收敛
- **当前写法**: 「该 store 方法是否完全删除依据其它使用方判断（grep 后决定）」、「stop condition」。
- **反例/失败场景**: plan-review 时已可 grep；把决策推到实施期等于把 architecture 选择留给 implementation agent，是 Gateflow 明确禁止的。
- **直接证据**: AGENTS plan 必须 handoff-ready；plan 段落 §Open Questions 标记为 non-blocking。
- **影响**: 中——实施期会被 stop condition 卡住。
- **建议改法和验证点**:
  - controller 在 plan-fix 阶段直接 grep 项目，给出确定的删除/保留决策并写入 D2；
  - 若 grep 结果显示无其它使用方，明确写「S5 同时下线 `mark_recovering_and_create_attempt` + `lease_store.create_recovery_attempt` 等关联 helper」。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### F07-未修复-[中]-S3「RunStream owner-lost 信号 / 订阅方 stop」描述不具体，可能让 implementation agent 自行设计新的 close 信号

- **位置**: §D1、Slice S3、§Risks R2
- **问题类型**: 不可直接实施
- **当前写法**: 「保证 RunStream 订阅方在 owner-lost 场景下能从 `RunStream.closed` 信号收到 stop（如有需要，另行处理 stream close 信号，不写 EventLog）」、Risk R2「如果发现需要新增 stream close 信号，纳入 S3 实施而非新增公开入口」。
- **反例/失败场景**: 「如有需要」是含糊条件；implementation agent 在 D1 改造后跑测试，若发现订阅方挂起，可能（a）新增一种 typed close 信号；（b）保留写 RUN_FAILED 的退路；两条路径都 plan 没明确选哪条。
- **为什么有问题**: AGENTS.md「设计下层组件接口时，必须假设上层组件不存在，只考虑上层调用需求，不向上泄漏实现细节」；RunStream 的 close 语义是上层契约，需要 plan 明确。
- **直接证据**: plan §S3、`docs/host/design.md` 应为 RunStream close 真源。
- **影响**: 中。
- **建议改法和验证点**:
  - D1 加入：「owner-lost CAS-miss 时 harness 关闭 stream 通过现有 `RunStream.aclose()` / 当前 `_run_to_store` 的退出路径完成；不新增 owner-lost typed close 事件。CAS hit 路径已经写 terminal RunEvent，订阅方按事件流自然 stop。」
  - 若现有 `RunStream` 没有可用 close 通道，plan 必须显式列出最小调整（不开新公开入口）。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 中

### F08-未修复-[低]-`InMemoryToolRuntime._resolve_appender` 引入「is_durable」flag 与 ContextVar owner-scope 双源真值未指定优先级

- **位置**: §D7、Slice S2
- **问题类型**: 契约缺失
- **当前写法**: 「durable 模式下 ContextVar 缺 owner scope → fail fast」。
- **反例/失败场景**: ContextVar 已设但 `is_durable=False`、或 ContextVar 未设但 `is_durable=True`，plan 未明确两个真值之间的关系。如果 implementation agent 把 ContextVar 当唯一入口，就保留了 0831-F003 风险；如果只看 flag，又会让 owner-aware execute_tool_call 没法在测试场景模拟。
- **直接证据**: `dayu/host/_tool_runtime.py:138-145, 378-381`。
- **影响**: 低（边界对，主要是文档严谨度）。
- **建议改法和验证点**:
  - D7 加入：「`is_durable=True` 时, ContextVar 必须存在 `ToolRuntimeOwnerScope`，缺失 → `RuntimeError`；ContextVar 存在但 `is_durable=False` 仍允许 plain（test-only 显式构造）。`PlainRunEventAppender` 使用方必须断言 `is_durable=False`。」
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### F09-未修复-[低]-S10 文档同步未提 `dayu/README.md` 总览中关于 host 公开入口的描述

- **位置**: §Documentation Update Decision、Slice S10
- **问题类型**: 范围漂移防御
- **当前写法**: 「不更新 `dayu/README.md`（分层未变）」。
- **反例/失败场景**: `dayu/README.md` 是 `UI / Service / Host / Engine` 总览，可能罗列 host 包稳定边界；删除 package-level convenience 后，若总览中残留 `dayu.host.start_run` 等示例，文档与代码不一致。
- **直接证据**: 需在 plan-fix 阶段 grep `dayu/README.md` 确认。
- **影响**: 低，可在 closeout 前发现。
- **建议改法和验证点**: S10 加入一步 `grep -n "start_run\|stream_run_events\|fetch_more_tool_result\|get_run_result\|get_tool_fetch_more_handle" dayu/README.md` 必须为空；命中则同步删除/改写。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### F10-未修复-[低]-S7 fail-fast 改造的「事务回滚」验证点未提 acquire / recovery 路径的影响范围

- **位置**: §D4、Slice S7
- **问题类型**: 测试缺口
- **当前写法**: 「单元测试模拟 `lastrowid=None`/`0` → 抛 RuntimeError，事务回滚」。
- **反例/失败场景**: `_allocate_fencing_token` 内部抛异常会让 caller (`acquire_new_attempt` / `mark_recovering_and_create_attempt`，后者在 S5 已下线) 整事务回滚；测试需要断言 host_attempts 行未插入 + host_fencing_tokens 行未插入 + supervisor 抛 typed error。
- **直接证据**: `dayu/host/_run_state_store.py:1186` 调用栈。
- **影响**: 低。
- **建议改法和验证点**: S7 验证矩阵补：`acquire_new_attempt` 触发 `_allocate_fencing_token` 失败 → 对应 `host_attempts` / `host_fencing_tokens` 行均不存在；调用方观测到 `RuntimeError("fencing token allocation returned invalid lastrowid")`。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

1. `LocalRunHarness.fetch_more_tool_result` 是 controller-accepted 删除目标；但 `InMemoryToolRuntime.get_tool_fetch_more_handle` / `fetch_more` 是否同时删除（仅保留 `execute_tool_call` 路径）？plan-fix 阶段需明确。
2. RunStream 在 owner-lost CAS-miss（不写终态）路径下的 stop 信号契约：是否复用现有 `aclose()` / 自然结束，还是引入 typed termination？plan-fix 阶段需明确。
3. `mark_recovering_and_create_attempt` / `lease_store.create_recovery_attempt` 是否完全下线（grep 项目得出）？plan-fix 阶段需明确。

## Residual Risks

- 三份 review artifact 状态更新规则在 plan §S10 已写明，但 review 中 5 个 「rejected/deferred」decision 的具体 rationale 文本未预先草拟，最终 closeout 才补写有遗漏风险 → owner: S10 实施时直接草拟 rationale 块，加入 controller state。
- `tests/host/_memory_store_fake` 等基础设施覆盖率断言被 plan §R5 推到「issue 推 P9」选项，但 issue 编号 / 跟踪入口未指定 → owner: 若不在 S9 内闭环，需在 closeout 报告中给出明确 issue id 或 follow-up phase。

## Plan Review Conclusion

**fail** — 必须修复 F01 / F02 / F03 / F04 / F05 / F06 / F07 后再 re-review。

主要不足集中在三类：

1. 测试矩阵未具体到行号 / 断言改写规则（F01 / F02），让 implementation agent 必然在「保住旧测试 / 反转断言 / 退回旧路径」三选一上做架构选择；
2. 契约层（F03 枚举集 / F04 invariant 真源 / F08 双源优先级）未在 plan 阶段收敛，违反 handoff-ready；
3. 顺序与决策延后（F05 / F06 / F07）会让实施期停下问 controller，违反 code-generation-ready。

修复后重点 re-review：是否所有「需要 implementation agent 自行选择架构 / 测试反转 / 契约定义」的隐式选择都被显式写入 plan。
