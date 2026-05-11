# P8.5 Slice 1 Code Review

- review gate name: code review
- reviewed target: current workspace uncommitted P8.5 Slice 1 production / tests / docs / implementation report
- reviewer conclusion: fail
- artifact path: `docs/host/phase8.5-s1-code-review.md`

## Conclusion

fail

Slice 1 的主方向成立：专用 ToolRuntime RunEventType、Host public fetch_more / cursor contracts、serializer mapping 与 caller-facing schema helper 已基本删除；`RuntimeTruncateManager` 与 Host 私有 framework `fetch_more` tool 也已落到 Host 内部边界。

但当前实现仍有阻塞问题：plan 要求的 credential-only payload policy 没有落地，普通 tool arguments / result payload 会原样进入 EventLog / trace；同时 durable `HostToolRuntime` 的 owner scope 执行保护已经变成未被生产路径调用的死 guard，测试只覆盖私有 helper 而没有覆盖真实 `execute_tool_call()` 路径。

## Findings

### 01-未修复-[高]-普通工具 payload 的 explicit credential scrub 未落地

- **入口/函数**: `translate_engine_event()` / `serialize_run_event_data()` / `ToolTraceObserver._emit_tool_call()`
- **文件(行号)**: `dayu/host/_event_translation.py:91`, `dayu/host/_run_event_serializer.py:247`, `dayu/host/_run_event_serializer.py:256`, `dayu/host/_tool_trace_projection.py:262`
- **输入场景**: Engine 产生普通 `TOOL_CALL_REQUESTED(arguments={"API_KEY": "sk", "cursor": "...", "scope_token": "..."})`，或普通 `TOOL_RESULT_ACCEPTED` 的 result value / failure message 中包含 `api_key` / explicit credential 字段。
- **实际分支**: `translate_engine_event()` 只过滤 `FinalAnswerData`，对 `ToolCallRequestedData` / `ToolResultAcceptedData` 原样写入 `RunEventDraft`；serializer 在 `arguments=dict(data.arguments)` 和 `outcome=_encode_outcome(data.outcome)` 处原样编码；trace projection 又把 `requested_data.arguments` 原样写入 `arguments_json`。
- **预期行为**: 按 `docs/host/phase8.5-plan.md:420` 与 `docs/host/phase8.5-plan.md:428`，EventLog / trace 应保留 cursor、`scope_token`、普通 tool args/result，但仍必须 scrub `API_KEY` / explicit credentials。
- **实际行为**: 旧的 cursor/scope redaction 被删除是正确方向，但没有补上 credential-only scrub；目前 ordinary tool payload 中的 explicit credentials 会原样进入 durable EventLog 与 trace JSONL。
- **直接证据**: `dayu/host/_event_translation.py:91-104` 没有 tool payload scrub 分支；`dayu/host/_run_event_serializer.py:247-263` 原样序列化 arguments / outcome；`dayu/host/_tool_trace_projection.py:262-268` 原样落 `arguments_json` / `result_value_json`。测试搜索只看到 provider protocol raw payload secret scrub，未看到 ordinary tool payload API key / credential scrub 断言。
- **影响**: credential 泄漏到 EventLog / trace / 后续 projection；同时 implementation report 声称“只 scrub 显式 API key / credential”与代码事实不一致。
- **建议改法和验证点**: 增加共享的 credential-only scrub helper，作用于普通 tool call arguments 与 accepted result payload / failure payload；规则必须精确到 explicit credential keys，不能因字段名为 `cursor`、`scope_token` 或普通 `token` 就遮蔽。补测试：同一 payload 中 `API_KEY` 被替换，`cursor` / `scope_token` 保留；trace record 与 serializer roundtrip 都覆盖。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 高

### 02-未修复-[高]-durable ToolRuntime owner scope guard 未保护真实执行路径

- **入口/函数**: `HostToolRuntime.execute_tool_call()`
- **文件(行号)**: `dayu/host/_tool_runtime.py:214`, `dayu/host/_tool_runtime.py:264`, `tests/host/test_phase8_tool_runtime_fencing.py:178`
- **输入场景**: durable runtime 在没有 `ToolRuntimeOwnerScope` 的上下文中被直接通过 `ToolRuntimeToolExecutor.execute()` 或 `HostToolRuntime.execute_tool_call()` 调用，执行会创建 / 消费 manager cursor，尤其是 `fetch_more`。
- **实际分支**: `execute_tool_call()` 从 `dayu/host/_tool_runtime.py:276` 开始按普通 name dispatch；framework 分支直接调用 `self._framework_tools.fetch_more_definition().executor.execute(request)`，业务分支直接调用底层 executor 并 `apply_truncation()`。全函数没有调用 `_resolve_appender()`。
- **预期行为**: durable ToolRuntime 的执行治理应由 active attempt owner scope 约束；P8 owner fencing 语义不能只保护 EventLog append，还应避免 stale / out-of-scope runtime execution mutation 消费 cursor store。
- **实际行为**: `_resolve_appender()` 仍会在 durable + 无 scope 时抛 `RuntimeError`，但它在 production 执行路径中没有调用点；唯一测试只是直接调用私有 `_resolve_appender()`，没有验证 `execute_tool_call()` 在 durable + no scope 下 fail fast。
- **直接证据**: `rg "_resolve_appender\\(" dayu tests` 只有定义和 `tests/host/test_phase8_tool_runtime_fencing.py:191` 的直接私有调用；`dayu/host/_tool_runtime.py:264-343` 的真实执行路径没有 owner scope 校验。
- **影响**: durable runtime 的 cursor issue / consume 可在 owner scope 外发生，造成 stale worker 或错误装配路径下的 Host 私有 runtime state mutation；现有测试给出“durable runtime requires owner scope”的假阳性信号，但没有覆盖真实入口。
- **建议改法和验证点**: 要么在 `execute_tool_call()` 开头引入明确的 durable execution scope 校验，并保持不向 Engine 暴露 manager / appender；要么如果设计裁决 tool execution 不再需要 owner scope，就删除 `_resolve_appender()` 和对应测试/README 说法，并为 owner-lost + in-flight fetch_more 增加直接回归测试，证明 stale execution 不会污染后续 run/attempt。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 高

### 03-未修复-[中]-Slice 1 必跑 validation 命令仍引用不存在测试文件

- **入口/函数**: Slice 1 validation gate
- **文件(行号)**: `docs/host/phase8.5-plan.md:449`, `docs/host/phase8.5-s1-implementation-report.md:98`
- **输入场景**: review / controller 按 approved plan 直接运行 `pytest tests/contracts/test_tool_declaration.py tests/contracts/test_tool_result.py tests/contracts/test_package_exports.py -q`。
- **实际分支**: pytest 在 collection 前失败：`tests/contracts/test_tool_result.py` 不存在。仓库当前存在的是 `tests/contracts/test_tool_result_envelope.py`。
- **预期行为**: plan validation 命令可复制运行；若测试文件已重命名，plan / report / tests README 应收敛到当前真实路径。
- **实际行为**: implementation report 记录了失败并补跑 equivalent command，但没有修正 approved plan 中的必跑命令，也没有新增/重命名对应测试文件。
- **直接证据**: `docs/host/phase8.5-plan.md:449` 写不存在路径；`docs/host/phase8.5-s1-implementation-report.md:101` 也确认该命令 collection 前失败。
- **影响**: review gate 的 required validation 不可复现，后续 controller / worker 容易把失败命令当成环境问题跳过。
- **建议改法和验证点**: 将 approved validation path 修正为 `tests/contracts/test_tool_result_envelope.py`，或新增真实 `tests/contracts/test_tool_result.py` 并把相关 contract coverage 移入该文件；重新跑原 plan 命令应不再 collection-fail。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

## Open Questions

- blocking: durable ToolRuntime 是否仍必须在真实 `execute_tool_call()` 入口校验 active attempt owner scope？当前测试名和 P8 fencing语义暗示“必须”，但 Slice 1 实现把唯一 guard 留成死代码。controller 需要裁决是恢复执行 guard，还是正式改变 P8-S5 owner boundary 并补充 owner-lost / stale execution 证据。
- non-blocking: `fetch_more` 业务 schema name collision 当前允许“与私有 schema 完全相等”的 caller-provided schema 通过。这可解释为 idempotent internal enhancement，但也接近兼容旧手工注入路径；若 controller 要求 caller 只传业务 schema，应在后续 ToolRegistry/P10 前明确是否改为统一拒绝外部 `fetch_more` schema。

## Validation Notes

- 已读取并对照：`AGENTS.md`、`CLAUDE.md`、`docs/host/phase8.5-plan.md`、`docs/host/design.md`、`docs/host/migration-plan.md`、`docs/host/phase8.5-s1-implementation-report.md`、`dayu/host/README.md`、`tests/README.md`。
- 未启动 `$gateflow`，未修改 production / tests / README，未 commit。
- 本次 review 实际运行：
  - `python -m pyright dayu/host/ dayu/contracts/ tests/host/ tests/contracts/` -> `0 errors, 0 warnings, 0 informations`
  - `pytest tests/contracts/test_tool_declaration.py tests/contracts/test_tool_result.py tests/contracts/test_package_exports.py -q` -> failed before collection，`tests/contracts/test_tool_result.py` 不存在
  - `pytest tests/contracts/test_tool_declaration.py tests/contracts/test_tool_result_envelope.py tests/contracts/test_package_exports.py -q` -> `9 passed`
  - `pytest tests/host/test_phase1_public_boundary.py tests/host/test_host_public_api_surface.py -q` -> `7 passed`
  - `pytest tests/host/test_phase2_tool_runtime_boundary.py tests/host/test_phase2_tool_runtime_truncation.py tests/host/test_phase2_tool_runtime_eventlog.py -q` -> `28 passed`
  - `pytest tests/host/test_phase3_conversation_memory_projection.py tests/host/test_phase5_multiturn_no_governance_smoke.py tests/host/test_phase8_tool_runtime_fencing.py -q` -> `29 passed`
- 删除项核查：production `dayu/contracts` / `dayu/host` 未再命中 `TOOL_FETCH_MORE`、`TOOL_CURSOR_`、`TOOL_RESULT_TRUNCATED`、`ToolFetchMore*`、`ToolCursor*Data`、`ToolResultTruncatedData`、`framework_fetch_more`；测试中的旧名主要用于负向 public-surface assertion。
- Host 私有边界核查：`RuntimeTruncateManager` 位于 `dayu/host/_runtime_truncate_manager.py`，没有进入 `dayu.host.__all__` / `dayu.host.contracts`；`FRAMEWORK_FETCH_MORE_NAME` 位于私有 `dayu.host._framework_tools`。
- Engine boundary 核查：Engine 仍只通过 `ToolSchema` / `ToolExecutionRequest` / `ToolExecutionOutcome` 接触工具；未发现 Engine import Host / ToolRuntime / manager / cursor type。`_run_harness.py` 会构造 enhanced request，`RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 使用 enhanced schemas。
- Memory / RunInput ingestion 核查：当前 memory 从普通 `ToolResultAcceptedData` 摘要化摄取，`truncation` 只写 `truncated=true`、`has_more`、`limit`、`ttl_seconds`、`scope_hash`，未写 raw cursor / raw scope token；P5 smoke 覆盖下一轮 input 不含 `scope_token` / `fetch_more_args`。
- Unexpected out-of-scope 核查：`dayu/host/_attempt_supervisor.py` 仅清理旧专用 fact 文档词；phase4 tests 是跟随删除旧 RunEventType 的必要迁移，未单独标 finding。
