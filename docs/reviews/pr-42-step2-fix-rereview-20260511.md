# PR #42 Step 2 Fix Re-review

## Scope

- Mode: current workspace Step 2 re-review
- Branch: `migration/host-p8-5-stabilization`
- Base: `dd9dd4a` (`fix: address host p8.5 review findings step 1`)
- Review gate: PR #42 Step 2 independent re-review
- Conclusion: pass
- Output file: `docs/reviews/pr-42-step2-fix-rereview-20260511.md`
- Included scope: Step 2 schema boundary changes in `dayu/host/_worker.py`, `dayu/host/_proxy.py`, `dayu/host/_run_harness.py`, `dayu/host/_durable_harness.py`; touched tests, smoke scripts, `docs/host/design.md`, `dayu/host/README.md`, `tests/README.md`.
- Excluded scope: raw payload retention / #43, P8.6 recovery model, P10 full ToolRegistry, P15 hard-gate / watchdog, P16 public/internal freeze, full PR #42 correctness review.
- Parallel review coverage: 无。

## Findings

未发现实质性问题。

## Evidence

- 旧 callback-style provider 入口已从生产路径删除：
  - `dayu/host/_engine_tool_schema_provider.py` 在当前 Step 2 diff 中删除。
  - `dayu/host/_worker.py:20-69` 的 `EngineWorker` 只持有 `tool_executor`，`run_agent_messages()` 必须接收显式 `tool_schemas: tuple[ToolSchema, ...]`，并把该 tuple 写入 `AgentRunRequest.tool_schemas`。
  - `dayu/host/_proxy.py:21-68` 的 `WorkerProxy` / `LocalProxy` 同样只透传显式 `tool_schemas`，没有 callback 回 Runtime / Harness 取 schema。
- `LocalRunHarness` 不再把 Host framework schema 写回 caller request：
  - `dayu/host/_run_harness.py:613-616` 在写 `USER_INPUT_ACCEPTED` 前解析当前 Engine-visible schema。
  - `dayu/host/_run_harness.py:640-655` 只 `replace(request, input=build_result.run_input)`，没有替换 `request.options.tool_schemas`；增强后的 schema 作为单独参数传入 `_run_to_store()`。
  - `dayu/host/_run_harness.py:819-824` 把显式 `tool_schemas` 传给 `WorkerProxy.stream_engine_events()`。
  - `dayu/host/_run_harness.py:1119-1131` compact retry 的 context snapshot fact 复用同一显式 schema tuple，不从 retry request options 二次增强。
- `fetch_more` 冲突 admission 时序正确：
  - `dayu/host/_run_harness.py:613-617` 先 `_resolve_engine_tool_schemas()`，后 append `USER_INPUT_ACCEPTED`。
  - `dayu/host/_tool_runtime.py:253-273` 通过 framework tool name set 拒绝 caller-provided `fetch_more` schema。
  - `tests/host/test_phase2_tool_runtime_boundary.py:530-545` 断言同名 schema 在 `USER_INPUT_ACCEPTED` 前抛错且 EventLog 为空。
- OpenAI schema serialization 仍在 Engine / Runner adapter：
  - `dayu/engine/runners/openai/payload.py:160` 保留 `_serialize_tool_schema()`，`dayu/engine/runners/openai/payload.py:339-340` 在 OpenAI payload 边界序列化 `ToolSchema`。
  - Step 2 没有新增 Anthropic / provider redesign 代码。
- 测试覆盖 Step 2 关键回归面：
  - `tests/host/test_phase2_tool_runtime_boundary.py:451-474` 覆盖 Harness 显式传 schema 且不污染 request options。
  - `tests/host/test_phase2_tool_runtime_boundary.py:478-526` 覆盖 EngineWorker 只使用显式 schema 参数。
  - `tests/host/test_phase2_tool_runtime_boundary.py:426-433` 覆盖 caller-provided framework schema conflict。
  - `tests/README.md:114-117` 同步描述当前测试边界。
- 残留扫描：
  - `rg "schema_provider|engine_tool_schema_provider|_engine_visible_request|_engine_tool_schema_provider" dayu tests utils docs/host/design.md dayu/host/README.md tests/README.md` 只命中 `docs/host/design.md:1096` 的反模式说明；`dayu/`、`tests/`、`utils/`、README 中未发现旧可调用入口。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_phase2_tool_runtime_boundary.py tests/host/test_phase8_5_framework_tools.py tests/host/test_host_public_api_surface.py tests/host/test_phase1_public_boundary.py -q`
  - 21 passed
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 0 errors, 0 warnings, 0 informations
- `git diff --check dd9dd4a --`
  - passed

## Open Questions

无。

## Residual Risk

- 本次 re-review 只按用户指定 scope 运行焦点测试与 pyright，未重新运行完整 `tests/host -q`；修复报告记录其已运行且通过。
- `LocalRunHarness` 仍是当前 run orchestration 集中点，但 Step 2 只要求移除 schema 双重增强入口；P9 / P16 的结构收口仍按既有迁移计划跟踪。

## Commit Readiness

Step 2 可以 commit。
