# Repo Review Accepted Fix - AgentCodex

## 范围

本次只处理 `docs/reviews/repo-review-20260604-controller-adjudication.md` 中 `Accepted For Current Fix` 的 A1-A12，排除 God 模块治理项；未处理 rejected 项，未向 `dayu.engine` 包根新增 `RunnerRequestIdentity`、`build_runner_request_identity` 或 `ClientCorrelationPolicy` 导出。设计真源仅对照 `docs/engine/design.md` 与 `docs/host/design.md`。

## 处理结果

### A1 同步 `AsyncRunner.call` request identity 签名

- 结果：已完成。`docs/engine/design.md` 的 `AsyncRunner.call` 加入 keyword-only `request_identity: RunnerRequestIdentity | None = None`，协议表面测试同步断言参数存在、默认值为 `None`，且不通过 `**kwargs` 暴露。
- 改动文件：`docs/engine/design.md`、`tests/engine/runners/openai/test_protocol_surface.py`。
- 验证：受影响 pytest 与 pyright 已通过。
- 风险：未发现剩余风险。

### A2 `Retry-After` 支持 delay-seconds 与 HTTP-date

- 结果：已完成。`parse_retry_after` 同时解析正整数秒数与 HTTP-date；过去时间返回 `None`，未来时间返回剩余秒数。
- 改动文件：`dayu/engine/runners/openai/retry_policy.py`、`tests/engine/runners/openai/test_retry_backoff.py`。
- 验证：补充 HTTP-date 过去/未来测试，受影响 pytest 与 pyright 已通过。
- 风险：HTTP-date 解析依赖标准库 `email.utils.parsedate_to_datetime`；非标准日期继续按无效 header 处理。

### A3 删除不可达 `ServerTimeoutError` 分支

- 结果：已完成。移除 `classify_exception` 中被 `asyncio.TimeoutError` 覆盖后不可达的 `aiohttp.ServerTimeoutError` 分支，保留超时归类语义。
- 改动文件：`dayu/engine/runners/openai/error_classifier.py`、`tests/engine/runners/openai/test_http_error_classification.py`。
- 验证：相关分类测试与 pyright 已通过。
- 风险：未发现剩余风险。

### A4 增加 durable 查询索引并更新 schema validation

- 结果：已完成。新增 `host_instances(status, heartbeat_at)` 与 `event_log(session_id, event_sequence)` 索引，纳入 fresh schema 创建与 validation；`HOST_SCHEMA_VERSION` 提升到 16，按当前约束不做旧库兼容迁移。
- 改动文件：`dayu/host/durable/schema.py`、`tests/host/test_durable_schema.py`。
- 验证：新增索引存在性与列顺序测试，受影响 pytest 与 pyright 已通过。
- 风险：只覆盖 fresh schema；旧库迁移不在本任务允许范围内。

### A5 `dayu.runtime.__init__` 文档加入 `diagnostic_text`

- 结果：已完成。runtime 包文档补充 `diagnostic_text`，并说明文本/JSON digest helper。
- 改动文件：`dayu/runtime/__init__.py`。
- 验证：pyright 已通过。
- 风险：文档项，无额外运行时风险。

### A6 `cancel_session_runs` 对 WAITING/RECOVERING 不静默成功

- 结果：已完成。现有生产逻辑已会取消 `WAITING` 与 `RECOVERING` run；本次修正过期 docstring，并补强 WAITING session cancel 测试，确认会产生 `RUN_CANCELLED` 事实；RECOVERING durable cancel 已由现有测试覆盖。
- 改动文件：`dayu/host/admission.py`、`tests/host/test_wait_cancel_late_result.py`。
- 验证：`tests/host/test_wait_cancel_late_result.py` 与 `tests/host/test_public_cancel_session_runs.py` 已通过。
- 风险：未覆盖跨进程竞争中的所有 interleaving；当前测试覆盖公共 API 对 WAITING/RECOVERING 的结果语义。

### A7 `HostDispatchScheduler.close` cleanup 异常路径标记 done 且不吞异常

- 结果：已完成。普通 cleanup `Exception` 路径会设置 `_close_cleanup_done = True` 后重新抛出原异常；`asyncio.CancelledError` 保持可重试取消语义。
- 改动文件：`dayu/host/dispatch.py`、`tests/host/test_dispatch_scheduler.py`。
- 验证：新增 cleanup 抛错测试，并保留既有 close 取消重试语义测试；受影响 pytest 与 pyright 已通过。
- 风险：`CancelledError` 属于外部取消，不标记 cleanup done；这是为保持 close 生命周期可重试，不属于普通 cleanup 失败吞异常路径。

### A8 `ToolDisplayInfo.name` 非空校验

- 结果：已完成。`ToolDisplayInfo.__post_init__` 增加 name 非空校验。
- 改动文件：`dayu/contracts/tool_declaration.py`、`tests/contracts/test_tool_declaration.py`。
- 验证：新增空 name 拒绝测试，受影响 pytest 与 pyright 已通过。
- 风险：会拒绝此前可能被接受的空展示名；这是契约修正。

### A9 `tool()` 返回类型不暴露私有 `_ToolDecorator`

- 结果：已完成。`tool()` 返回类型改为公共 `Callable[[ToolCallable], ToolDefinition]`，运行时行为保持不变。
- 改动文件：`dayu/contracts/tool_declaration.py`。
- 验证：tool declaration 测试与 pyright 已通过。
- 风险：类型表面收窄为公共 callable 形状；未发现运行时风险。

### A10 runtime 文本 digest helper 与 `scene_prepare` 复用

- 结果：已完成。新增 `dayu.runtime._digest.text_digest`，`scene_prepare` 复用该 helper，digest 输出格式保持 `sha256:<hex>`。
- 改动文件：`dayu/runtime/_digest.py`、`dayu/runtime/scene_prepare.py`、`tests/runtime/test_digest.py`、`tests/runtime/test_scene_prepare.py`。
- 验证：新增 digest helper 测试，并断言 fragment digest 仍按原始文本计算；受影响 pytest 与 pyright 已通过。
- 风险：未发现剩余风险。

### A11 安全合并重复 `_require_non_empty_text`

- 结果：已完成安全范围内合并。新增 `dayu.contracts._validation`，只承载错误类型、返回语义、领域含义一致的非空文本校验；`tool_source`、`tools_discovery` 与 tool declaration 相关 name 校验复用该 helper。
- 改动文件：`dayu/contracts/_validation.py`、`dayu/contracts/tool_declaration.py`、`dayu/contracts/tool_source.py`、`dayu/runtime/tools_discovery.py`、`dayu/contracts/tool_schema.py`、`tests/runtime/test_tools_discovery_digest.py`。
- 验证：相关 contracts/runtime 测试与 pyright 已通过。
- 保留原因：`dayu/runtime/scene_prepare.py` 的 validator 抛 `ScenePrepareError` 且返回 strip 后文本，语义不同；`dayu/host/durable/_validation.py` 与 durable 调用方抛 `HostDurableError` 并处理 SQLite scalar 边界，语义不同；host、service 等模块内 validator 涉及本层领域错误、参数名、返回值或存储边界，未强行合并。
- 风险：只合并了语义同源的基础契约校验；仍存在领域本地 validator，但保留是为了不改变错误类型与边界语义。

### A12 移除 dispatch CAS 后无保护 `sleep(0)`

- 结果：已完成。删除 `_dispatch_one` 在 CAS 成功后的无保护 `await asyncio.sleep(0)`，保留 durable pre-accept recheck。
- 改动文件：`dayu/host/dispatch.py`、`tests/host/test_dispatch_scheduler.py`。
- 验证：既有取消竞态测试覆盖 recheck 前取消仍释放 lane 且不启动 worker；pre-worker cancel skip 测试继续通过。
- 风险：未发现需要保留 sleep 的设计证据；取消窗口由显式 durable recheck 承担。

## 文档同步

- 已同步 `dayu/engine/README.md` 的 runner 示例。
- 已同步 `docs/host/design.md` 中 `cancel_session_runs` 对 `WAITING` / `RECOVERING` 当前可闭环状态的语义，保留外部 job physical cancel / recovery dispatch cancellation 仍由后续 owner 强化的边界。
- 已同步 `dayu/README.md` 的 runtime digest 能力说明。
- 已同步 `tests/README.md` 的 runtime digest 与 tool declaration 测试说明。
- 已检查 `dayu/host/README.md`：本次 host 变更未改变其稳定接口、状态机或开发手册职责范围，不做机械更新。

## Full Pytest Follow-up

- 回归点 1：`AsyncOpenAIRunner.call` 的公共设计允许 `request_identity=None`，但 `_call_impl` 是当前实现的私有 keyword-only helper，公共 `call` 已显式转发默认值；失败测试直接调用私有 helper，应显式传 `request_identity=None`，不扩大实现表面。
- 回归点 2：`IterationCompletedData`、`RunFailedData` 与 `ContextCompactionRequestedData` 的当前 contract docstring、Engine README 与 ingest/agent 测试均把 `client_correlation_id` 作为显式诊断字段；字段锁测试过期，已补齐这些 dataclass 的字段集合。
- 回归点 3：`_compact_pressure_padding` 设计包含 pressure prompt 与工具压力之外的 reserve token；测试只用 prompt + tool 估算，漏掉 `_compact_pressure_reserve_tokens`，导致低估当前 runtime policy 下的压力总量。已改为按 helper 同源语义计算，不硬编码阈值数字。
- 改动文件：`tests/engine/runners/openai/test_runner_b3_extra.py`、`tests/engine/test_engine_event_contract.py`、`tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`。

## 验证结果

- `source .venv/bin/activate && pytest tests/engine/runners/openai/test_protocol_surface.py tests/engine/runners/openai/test_retry_backoff.py tests/engine/runners/openai/test_http_error_classification.py tests/contracts/test_tool_declaration.py tests/contracts/test_tool_source.py tests/contracts/test_tool_schema.py tests/runtime/test_digest.py tests/runtime/test_scene_prepare.py tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py tests/host/test_durable_schema.py tests/host/test_public_cancel_session_runs.py tests/host/test_wait_cancel_late_result.py tests/host/test_dispatch_scheduler.py -q`：224 passed。
- `source .venv/bin/activate && pytest tests/engine/runners/openai/test_runner_b3_extra.py::test_sse_idle_aclose_does_not_leak_pending_task tests/engine/test_engine_event_contract.py::test_provider_request_id_fields_are_locked tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py::test_pressure_off_and_padding_helper_cover_runtime_pressure_bounds -q`：3 passed。
- `source .venv/bin/activate && pytest tests/ -q`：1995 passed, 1 skipped, 5 deselected。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors, 0 warnings, 0 informations。
- `git diff --check`：通过。

## 未覆盖风险

- A4 遵循 fresh schema 约束，未实现旧库迁移。
- A6 未枚举所有跨进程取消 interleaving；已覆盖公共 API 对 WAITING/RECOVERING 的取消结果。
