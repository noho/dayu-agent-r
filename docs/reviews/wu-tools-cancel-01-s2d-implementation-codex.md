# WU-TOOLS-CANCEL-01 S2D Implementation Artifact

## 动机判断

S2D 动机成立，且严重性评估准确。直接证据是 `search_web` / `fetch_web_page` 的生产定义此前未声明 `ToolDefinition.execution`，Host production ToolRuntime 可能按默认 `async_direct` 调用 direct callable；direct callable 内部仍在 provider lock 中通过 `asyncio.to_thread(...)` 执行同步 `requests` 主路径。该形态只能取消 awaiter，不能抢占已经进入 OS thread 的同步 I/O，不满足 #87 interrupt closeout。

本 slice 选择 process-backed，而不是 request-abort-capable async_direct。原因是当前 Web 主路径基于同步 `requests.Session` 与 Playwright fallback；若选择 async_direct，必须重写或引入 async HTTP adapter，并证明 cancel 时 response / client / stream 被关闭。当前最小生产级 root-cause 修复是让 production execution 进入既有 `ProcessBackedToolExecutionCapability` / Host process capsule，父进程取消或超时时 terminate / kill 子进程，迟到结果不进入 accept barrier。

## 改动

- `dayu/tools/web/web_tools.py`
  - 新增 `_WebProcessTargetFactory` 与 `_WebProcessTarget`。
  - process target 只保存工具名、参数 JSON 副本、`WebToolsConfig` 和 timeout 标量；不捕获 `requests.Session`、provider lock、`CancellationToken`、Host / Run / Session 对象或 Playwright runtime / browser 对象。
  - 子进程内重新通过现有 Web 同步业务 helper 构造 requests / Playwright 所需 runtime；timeout budget 继续传入 search HTTP 与 fetch HTTP / browser 阶段。
  - `search_web` 与 `fetch_web_page` 的 `ToolDefinition.execution` 均声明为 `ProcessBackedToolExecutionCapability`。
  - direct callable fallback 保留，继续覆盖直接测试 / 非生产 fallback 的 cooperative cancellation 与 provider lock 串行语义。
  - process target 只返回 `completed` / `failed` JSON 信封；不返回 awaiting / cancelled / timeout / host_cancelled。

- `tests/tools/web/test_web_tools_provider.py`
  - 覆盖两个 Web definitions 声明 process-backed。
  - 覆盖 process factory / target pickle round-trip，并断言不携带 Session / lock / token / Host / Playwright runtime 语义。
  - 覆盖 process target fast success path、failed JSON envelope、timeout budget 标量传递。
  - 覆盖真实 `ProcessBackedToolExecutionCapsule` spawned child 成功路径。
  - 覆盖真实 Web process target 取消后 ToolRuntime 返回 governed cancel failure，且 accept barrier 只接受取消事实，不接受 late child result。
  - 保留 direct callable cancellation、timeout budget、Playwright cancellation 和 provider lock fallback 测试。

## 验证

- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py -q`
  - 31 passed
- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py -q`
  - 55 passed
- `source .venv/bin/activate && pyright`
  - 0 errors, 0 warnings, 0 informations
- `source .venv/bin/activate && git diff --check`
  - passed

README 触发检查：本 slice 修改了 `tests/`，已阅读 `tests/README.md`。本次是在既有 Web provider 测试文件内补覆盖点，没有新增测试层级、目录职责或运行方式，因此无需更新 `tests/README.md`。

## Stop Condition

- 未修改 Engine contract、durable schema、Host public contract 或 `dayu.runtime.interruptible_process` JsonValue envelope。
- Host 不按工具名分支选择执行形态；production 仍由 `ToolDefinition.execution` 进入 S2A2 declaration-backed factory。
- process target 可 pickle，且不依赖父进程 provider lock 或父进程全局 Session。
- Playwright fallback 没有回落到不可抢占同进程 production path；它在 Web process target 子进程内按现有 fail-closed worker 语义运行，父进程仍可 terminate / kill 整个 Web tool process。
- 取消后 late child result 未进入 accept barrier。

## Residual Risk

- Process-backed 会增加 Web tool 冷启动成本；当前 #87 closeout 优先保证取消可抢占与 late-result 隔离，worker pool 或复用优化应作为后续性能 work unit 评估。
- Host process envelope 当前只消费 `error_type` 与 `message`，没有独立 `hint` 字段；Web process target 为避免修改 runtime / Host envelope contract，把 hint 合入 message。错误码保持稳定，成功 payload 与 truncate spec 不变。
- 本 slice 使用本地 socket HTTP server 验证真实子进程成功与取消路径，不跑真实外网 provider；真实 provider 可用性和外网波动不作为 S2D correctness 前置。
