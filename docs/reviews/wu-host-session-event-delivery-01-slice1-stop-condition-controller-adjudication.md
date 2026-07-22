# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 1 Stop Condition Controller Adjudication

## 元数据

- Work Unit：`WU-HOST-SESSION-EVENT-DELIVERY-01`
- 原 gate：`implementation-slice-1`
- Trigger：AgentCodex 执行完整 pyright 时发现 accepted plan 未列明的真实 public watch callers
- Accepted plan commit：`8b29462c`
- Controller 决定：`return-to-plan-fix`

## 直接证据

AgentCodex 已按 S1 修改 `Host.watch_session_events(...)` 为 async factory，并完成 plan §5.2 已列 production/test/fake 调用点的机械传播。完整 `pyright` 仍报告 `18 errors`：

- 8 个 error 来自已授权 Service/CLI test fake 的 `__aiter__` 返回类型不够精确，属于既有 S1 allowed test scope，可直接修复。
- 10 个 error 来自 accepted plan §5.2 未列出的 4 个真实 public Host smoke callers：
  - `utils/smoke_host_public_r03_semantic_ownership.py`
  - `utils/smoke_host_public_conversation_memory.py`
  - `utils/smoke_host_public_conversation_memory_scenarios.py`
  - `utils/smoke_host_public_multiturn.py`

这 4 个文件当前直接执行 `watcher = host.watch_session_events(...)`，随后把 coroutine 当作 async iterator 传给 `_run_round(...)`。async factory contract 生效后，真实分支会把 coroutine 传入 iterator consumer，既导致 pyright error，也会在 smoke runtime 失败。

## 动机与 owner 裁决

动机成立。`Host.watch_session_events(...)` 的 async public contract 由 `dayu.host` 拥有；所有 direct callers 必须显式 `await`。这 4 个 `utils/` 脚本不是新的业务 owner，也不需要修改行为，只需消费已经冻结的 public activation contract。

Accepted plan §7 S1 已授权“5.2 列出的全部 Host direct watch call files”做 async/public iterator 机械传播，但 §5.2 的静态清单漏掉了上述 4 个当前代码 callsites。因此这是 plan manifest 不完整，而不是允许 implementation agent自行解释的隐含授权。

禁止用以下方案绕过：

- 同步 factory compatibility branch；
- lazy attach / pending future；
- 在 consumer 下游识别 coroutine；
- `cast`、`getattr` 或其它兼容 shim。

## Accepted plan amendment

AgentCodex 必须只修订 plan 与 plan-fix artifact：

1. 在 §5.2 的 public watch direct caller 闭集中加入上述 4 个 `utils/` 文件，要求每个调用显式 `await`。
2. 在 §7 S1 allowed scope 中明确授权这 4 个文件仅做 async factory/public iterator contract 的机械传播；不得修改 smoke 场景、断言、数据流、CLI/Service relay或其它行为。
3. 在 S1 validation/source propagation scan 中纳入 `utils/` direct caller 检查。
4. 说明 `utils/` 按仓库 AGENTS.md 默认无需新增测试或单文件 coverage，但仍纳入完整 pyright、py_compile/source scan；这不降低生产与测试文件的 coverage acceptance。

## Gate 与现有 workspace

- 当前 gate 返回 `plan-fix-after-slice1-stop`。
- 已有 S1 implementation changes 保留在 workspace，但不得继续实施、验证收口或生成 implementation artifact，直到 plan amendment 经原 AgentMiMo 与 AgentDS 独立 re-review 并由 Controller accepted。
- Controller bookkeeping 仍由 Controller 独占；implementation/plan agent不得修改 `docs/host/issues-implementation-control.md`。
- Blocking open question：`None`。所需 scope amendment 已由直接代码与 pyright evidence 精确确定。
