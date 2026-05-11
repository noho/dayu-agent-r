# PR #42 Step 2 修复报告：EngineWorker/schema projection boundary

## 变更

- 删除 callback-style schema provider 入口：
  - 删除 `dayu.host._engine_tool_schema_provider`。
  - 移除 `EngineWorker(schema_provider=...)`。
  - 移除 `LocalRunHarness(engine_tool_schema_provider=...)` 与 `_engine_visible_request()`。
- 固定新的显式 schema 边界：
  - `WorkerProxy.stream_engine_events(...)` 新增显式 `tool_schemas: tuple[ToolSchema, ...]`。
  - `EngineWorker.run_agent_messages(...)` 接收显式 schema 集合并装配 `AgentRunRequest.tool_schemas`。
  - `LocalRunHarness.start_run()` 保留 `StartRunRequest.options.tool_schemas` 为调用方业务 schema，只把 Host ToolRuntime 投影出的当前 Engine-visible schema 作为单独参数传给 WorkerProxy / EngineWorker。
- 保持 P8.5 工具边界：
  - `fetch_more` 仍是 Host 私有 framework built-in tool，对 Engine 只是普通 tool schema / tool call / tool outcome。
  - 任意 caller-provided `fetch_more` schema 仍在 `USER_INPUT_ACCEPTED` 前 fail fast，不污染 EventLog。
  - OpenAI provider schema 翻译仍留在 Engine runner adapter。
- 同步测试与 smoke：
  - 更新 fake `WorkerProxy` / smoke proxy 签名。
  - `utils/smoke_engine_worker.py` 直接传入显式 schema。
  - `utils/smoke_host_tool_runtime.py` 与 `utils/smoke_host_multiturn_no_governance.py` 清理旧 provider 参数。
- 同步文档：
  - 更新 `docs/host/design.md` EngineWorker 接口示意。
  - 更新 `dayu/host/README.md` 与 `tests/README.md` 的当前事实描述。

## 验证

- `source .venv/bin/activate && pytest tests/host/test_phase2_tool_runtime_boundary.py tests/host/test_phase8_5_framework_tools.py tests/host/test_host_public_api_surface.py tests/host/test_phase1_public_boundary.py -q`
  - 21 passed
- `source .venv/bin/activate && pytest tests/contracts tests/engine -q`
  - 328 passed
- `source .venv/bin/activate && pytest tests/host -q`
  - 420 passed
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 0 errors, 0 warnings
- `git diff --check`
  - passed

## 残余风险

- `LocalRunHarness` 仍是当前 run orchestration 的集中点；本 Step 只移除 schema provider 双入口，不提前做 P9 RunSupervisor 拆分。
- P10 ToolRegistry、P15 schema bootstrap hard-gate、P16 public/internal bundle freeze 未进入本 Step。
- `dayu/README.md` 当前不存在；本 Step 未新增该总览文档，只更新了实际存在且命中职责范围的 README。
