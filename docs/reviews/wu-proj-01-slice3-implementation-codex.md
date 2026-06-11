# WU-PROJ-01 Slice 3 Implementation - AgentCodex

## 范围

- Work unit：`WU-PROJ-01`
- Slice：`Slice 3 - Bounded memory projection catch-up / rebuild`
- Gate：implementation
- Agent：AgentCodex
- 日期：2026-06-11

## 已实现

- 新增 Host 内部 `MemoryProjectionCatchupBudget`，字段为 `max_batches`、`max_scanned_events` 和 `purpose`。
- 新增 bounded repair stop reason，并扩展 `ConversationMemoryProjectionRepairResult`，携带 stop reason、target coverage、budget exhausted、target cursor 与 budget 字段。
- 将 memory repair 的无界循环替换为 bounded loop；failure、idle、target reached、覆盖 max target cursor、batch budget exhausted、scanned-event budget exhausted 都有明确停止原因。
- 保持 budget exhausted 与 projection failure 分离：预算耗尽只记录为 `budget_exhausted`，不写 projection failure row。
- dispatch worker accept 前的 required memory catch-up 改为使用 required budget；required cursor 未覆盖时阻断 `worker.accept`。
- dispatch lag rebuild 改为只重建到 required cursor，并使用 rebuild budget；重建后仍未覆盖目标时按 memory projection repair closeout 收口。
- `open_host` after-commit memory projection catch-up 改为 bounded best-effort budget。
- 补充测试覆盖 catch-up target stop、catch-up budget exhausted、rebuild budget exhausted、真实 durable partial checkpoint advance、open_host budget 注入、dispatch budget exhausted 阻断 worker accept，以及 bounded result 日志字段。

## 修改文件

- `dayu/host/memory_repair.py`
- `dayu/host/dispatch.py`
- `dayu/host/open_host.py`
- `tests/host/test_memory_repair.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_logging.py`
- `docs/reviews/wu-proj-01-slice3-implementation-codex.md`

## 验证

已通过：

```bash
source .venv/bin/activate && python -m pytest tests/host/test_memory_repair.py
source .venv/bin/activate && python -m pytest tests/host/test_open_host_runtime.py
source .venv/bin/activate && python -m pytest tests/host/test_logging.py
source .venv/bin/activate && pyright
```

结果：

- `tests/host/test_memory_repair.py`: 9 passed
- `tests/host/test_open_host_runtime.py`: 12 passed
- `tests/host/test_logging.py`: 4 passed
- `pyright`: 0 errors, 0 warnings

## README 决策

- 已检查 `dayu/host/README.md` 更新约束。
- 已检查 `tests/README.md` 更新约束。
- 未修改 README。本 slice 增加的是 Host 内部 bounded repair 执行与对应测试，没有新增 public Host API、新测试层级或新测试命令类别；现有 README 对 Conversation Memory projection/read model 与 repair/catch-up 路径的说明仍准确。

## 阻塞问题

- 无。

## 剩余风险

- 当前预算常量是 Host 内部第一版取值，不是 public configuration。若后续 production profiling 证明 ordinary dispatch 需要部署级调参，应进入后续设计/API 决策，而不是在本 slice 扩展隐藏配置。
- 现有 reactive ingest catch-up 调用不在本 slice allowed files 内；它们不属于 ordinary dispatch command/admission hot path，本 slice 未修改。
