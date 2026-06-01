# WU-STRESS-01 Discussion / Code Inspection

## 总控结论

WU-STRESS-01 的动机成立。Host 设计真源要求 Host 对 Run / Attempt lifecycle、recovery、watch、scheduler、liveness 与 durable truth 保持强约束；当前测试已经覆盖大量单点和短路径集成，但缺少与总控文档验收信号一致的独立 production hardening stress suite。

## 直接证据

- `pyproject.toml` 仅配置基础 `pytest`，未声明 `stress` 或等价 marker。
- `tests/README.md` 记录了常规 Host、Runtime、Service、Engine 测试入口，但没有独立 stress suite 命令、marker、超时预算或结构化压测摘要约定。
- `tests/host/test_recovery_multiprocess.py` 与 `tests/host/recovery_support.py` 已覆盖 owner 进程退出后的 recovery public stream 路径，可复用其多进程和 stale owner 测试支撑思想。
- `tests/host/test_watch_session_events.py` 已覆盖单 session watcher、双 watcher、terminal event、consumer cancel 与错误边界，但不是 sustained watch lag / reconnect stress。
- `tests/host/test_dispatch_scheduler.py` 已覆盖 scheduler drain、lane、worker startup、close、active task cleanup 等窗口，但不是 queued / active / terminal / cancel / recovery 长时间混合流转 stress。
- `tests/host/test_event_log_multiprocess.py` 中存在局部 event id conflict stress，但它不是 Host crash / recovery / watch / scheduler 组合 suite。

## Scope Boundary

当前 work unit 应只建立可重复运行、默认排除的 Host stress suite，并用 deterministic fake worker / fake clock / fault injection 组合现有 Host public path 或稳定测试支撑边界。它不应改 Host public contract、durable schema、EventLog 语义、recovery 状态机或 scheduler 生产行为，除非 planning 通过代码核对发现直接阻塞 stress suite 的真实缺口。

## Non-goals

- 不把 stress tests 放入默认快速 pytest 入口。
- 不用不可控睡眠或外部服务制造偶然压力。
- 不重复外部慢盘 / Docker Linux / 高延迟文件系统 SQLite 压力跟踪项。
- 不把缺少 stress suite 扩大成新的测试框架、平台化 runner 或生产诊断系统。

## Planning Handoff 要求

planning agent 必须形成 code-generation-ready plan，至少覆盖：

- pytest marker / 命令 / 默认排除策略。
- stress helper 与测试文件 ownership。
- repeated startup / recovery / crash E2E stress。
- sustained watch stress，包括慢消费、断开重连、terminal 不丢失和 cursor / lag 诊断。
- scheduler / liveness long-run stress，包括 queued / active / terminal / cancel / recovery 混合流转和 close 后 active task 清理。
- mixed Host stress 的 deterministic fault injection 范围。
- 结构化摘要字段：session / run 数、crash 次数、recovery 次数、watch lag、scheduler drain 状态、liveness stale 判断、terminal 去重结果。
- 受影响测试、pyright 与 README 同步命令。

## Blocking Questions

无。当前设计真源和总控文档足以进入 planning gate；若 planning agent 发现必须修改 public contract、durable schema、状态机或生产行为，必须停止并返回 controller 裁决。
