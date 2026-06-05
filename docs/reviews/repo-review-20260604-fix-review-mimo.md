# Code Review

## Scope

- Mode: current changes (uncommitted workspace diff)
- Branch: phaseflow/wu-cm-01
- Base: main
- Output file: `docs/reviews/repo-review-20260604-fix-review-mimo.md`
- Included scope: A1-A12 accepted fixes 实现与测试，以及相关 README/docs 同步
- Excluded scope: God 模块治理、`dayu.engine` 包根导出扩展、schema migration
- Parallel review coverage: 无

## Review Basis

- 设计真源：`docs/engine/design.md`、`docs/host/design.md`
- 裁决真源：`docs/reviews/repo-review-20260604-controller-adjudication.md`
- 实现记录：`docs/reviews/repo-review-20260604-fix-codex.md`

## Findings

未发现实质性问题。

## A-Item Verification Summary

### A1 同步 `AsyncRunner.call()` 设计与协议表面测试

- `docs/engine/design.md` 第 148-155 行：`AsyncRunner.call()` 签名已加入 keyword-only `request_identity: RunnerRequestIdentity | None = None`。
- `tests/engine/runners/openai/test_protocol_surface.py`：断言参数名顺序、`KEYWORD_ONLY` 边界、默认值 `None`。
- 与设计真源一致。PASS。

### A2 `Retry-After` 支持 HTTP-date

- `dayu/engine/runners/openai/retry_policy.py`：`parse_retry_after` 新增 `now` 参数，delay-seconds 失败时 fallback 到 `_parse_retry_after_http_date`；使用标准库 `email.utils.parsedate_to_datetime` 解析；过去时间返回 `None`。
- 测试覆盖：非法字符串、过去 HTTP-date、未来 HTTP-date。
- 与设计真源（Host design 要求 Engine Runner 处理 `Retry-After`）一致。PASS。

### A3 移除不可达 `ServerTimeoutError` 分支

- `dayu/engine/runners/openai/error_classifier.py`：移除 `isinstance(exc, aiohttp.ServerTimeoutError)` 分支；`asyncio.TimeoutError` 已覆盖（`ServerTimeoutError` 是其子类）。
- 测试 docstring 更新为经 asyncio timeout 分支归类。
- 超时分类语义不变。PASS。

### A4 增加 durable 查询索引

- `dayu/host/durable/schema.py`：新增 `host_instances(status, heartbeat_at)` 与 `event_log(session_id, event_sequence)` 索引；`HOST_SCHEMA_VERSION` 从 15 提升到 16；两个索引加入 `HOST_DURABLE_INDEXES` 与 `FOUNDATION_INDEX_DDL`。
- 测试验证索引存在性与列顺序。
- 遵循 fresh schema 约束，不做旧库迁移。PASS。

### A5 Runtime 包文档加入 `diagnostic_text` 与 `_digest`

- `dayu/runtime/__init__.py` docstring 更新，明确 `diagnostic_text` 与 `_digest` 为层中立 runtime 能力。
- `dayu/README.md` 同步更新 `_digest` 条目。
- 文档项，无运行时风险。PASS。

### A6 `cancel_session_runs` 对 WAITING/RECOVERING 取消语义

- `dayu/host/admission.py` docstring 更新：声明取消 queued、pre-dispatch `STARTING`、active worker、`WAITING` 与 `RECOVERING` Run。
- `tests/host/test_wait_cancel_late_result.py`：`test_cancel_session_runs_cancels_waiting_run` 新增 `RUN_CANCELLED` event 断言。
- 设计真源中 `cancel_run` on waiting 的转换表（`RUN_WAITING -> RUN_CANCELLED`，产出 `CANCEL_REQUESTED`、wait record cancelled fact、`RUN_CANCELLED`）与测试断言一致。
- RECOVERING durable cancel 由既有测试覆盖。PASS。

### A7 `HostDispatchScheduler.close()` cleanup 异常路径标记

- `dayu/host/dispatch.py`：close cleanup 区域包裹 `try/except Exception`；异常路径设置 `_close_cleanup_done = True` 后重新抛出原异常；`CancelledError` 不在 `except Exception` 捕获范围内（Python 3.11 中 `CancelledError` 继承自 `BaseException`），保持可重试取消语义。
- 测试 `_FailingLaneClose` 验证：异常被抛出、`_closed` 与 `_close_cleanup_done` 均为 `True`。
- PASS。

### A8 `ToolDisplayInfo.name` 非空校验

- `dayu/contracts/tool_declaration.py`：`ToolDisplayInfo.__post_init__` 调用 `_require_non_empty_text(self.name, field_name="ToolDisplayInfo.name")`。
- 测试 `test_tool_display_info_rejects_empty_name` 验证空白 name 抛出 `ValueError`。
- 与 `ToolDefinition.__post_init__` 校验风格一致。PASS。

### A9 `tool()` 返回类型不暴露私有 `_ToolDecorator`

- `dayu/contracts/tool_declaration.py`：`tool()` 返回类型从 `_ToolDecorator` 改为 `Callable[[ToolCallable], ToolDefinition]`。
- `_ToolDecorator` 仍是内部实现类，运行时行为不变。
- 公共类型表面收窄为 callable 形状，pyright 兼容。PASS。

### A10 Runtime 文本 digest helper 与 `scene_prepare` 复用

- `dayu/runtime/_digest.py`：新增 `text_digest(value: str) -> str`，输出 `sha256:<hex>`。
- `dayu/runtime/scene_prepare.py`：删除 `_text_digest` 与 `_DIGEST_PREFIX`，改用 `text_digest`。
- 测试 `test_text_digest_matches_existing_sha256_prefix_shape` 验证输出形态。
- 测试 `test_single_scene_assembly_outputs_stable_refs_and_digest` 验证 fragment digest 仍按原始文本计算。
- 输出格式不变。PASS。

### A11 安全合并 `_require_non_empty_text`

- `dayu/contracts/_validation.py`：新模块，提供 `require_non_empty_text` 与 `require_optional_non_empty_text`；错误类型为 `ValueError`，返回语义一致。
- 消费方：`tool_declaration.py`、`tool_source.py`、`tools_discovery.py`。
- 保留原因（未合并）：`scene_prepare.py` 的 validator 抛 `ScenePrepareError`；host durable validation 抛 `HostDurableError`。
- `tool_schema.py` 新增 `isinstance(property_name, str)` 检查，将非字符串 key 的错误从 `normalize_json_value` 的 `TypeError("JsonValue object key must be str")` 前移到 schema 边界的 `TypeError("ToolParametersSchema.properties keys must be str")`。测试同步更新。
- PASS。

### A12 移除 dispatch CAS 后 `sleep(0)`

- `dayu/host/dispatch.py` `_dispatch_one`：删除 `_mark_dispatching_after_recheck` 与 `_dispatch_record_still_pre_accept` 之间的 `await asyncio.sleep(0)`。
- 设计真源要求 dispatch recheck durable state 后 dispatch；不要求 CAS 与 worker start 之间有无条件 yield。
- 既有取消竞态测试覆盖 recheck 前取消仍释放 lane 且不启动 worker。
- PASS。

## Open Questions

- 无。

## Residual Risk

- 本次未运行全量 pytest，只运行受影响测试集合。
- A4 遵循 fresh schema 约束，旧库迁移不在本任务范围内。
- A6 未枚举所有跨进程取消 interleaving；已覆盖公共 API 对 WAITING/RECOVERING 的取消结果语义。
- `dayu/contracts/_validation.py` 无独立单元测试；通过消费方（tool_declaration、tool_source、tools_discovery）间接覆盖。

## Final Follow-Up Review

### Scope

- follow-up 改动文件：`tests/engine/runners/openai/test_runner_b3_extra.py`、`tests/engine/test_engine_event_contract.py`、`tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`、`docs/host/design.md`、`docs/reviews/repo-review-20260604-fix-codex.md`
- 验证结果：`pytest tests/ -q` 1995 passed, 1 skipped, 5 deselected；pyright 0 errors；diff check clean。

### 1) 私有 `_call_impl` 测试显式传 `request_identity=None`

`test_runner_b3_extra.py:80-81` 直接调用 `runner._call_impl(msgs, ..., request_identity=None)`。设计真源（`docs/engine/design.md` 第 154 行）定义 `request_identity: RunnerRequestIdentity | None = None` 为 keyword-only 可选参数。测试显式传 `None` 等价于使用默认值，且同文件其它测试（`test_sse_idle_outer_cancel_does_not_leak_pending_task` 等）通过公共 `runner.call()` 覆盖了省略该参数的路径。PASS。

### 2) `client_correlation_id` 加入 EngineEvent 字段锁测试

`test_engine_event_contract.py:158-182` 的 `test_provider_request_id_fields_are_locked` 断言 `IterationCompletedData`、`RunFailedData`、`ContextCompactionRequestedData` 包含 `client_correlation_id` 字段。实际 dataclass（`dayu/engine/contracts/engine_events.py:332`）定义 `client_correlation_id: str | None = None`，与测试断言一致。PASS。

### 3) pressure bounds 测试纳入 `_compact_pressure_reserve_tokens`

`test_smoke_host_public_conversation_memory_scenarios_assembly.py:280-296` 使用 `_compact_pressure_reserve_tokens(context_window_size=policy.context_window_size)` 计算预留 token，断言总 pressure 落在 soft 与 hard 阈值之间。该 helper 来自 `utils/smoke_host_public_conversation_memory_scenarios.py:2372`，是 smoke 测试脚本中的常量估算（`160_000` tokens），不是生产代码。测试验证的是 smoke 场景中 pressure 估算的边界合理性，不是生产 budget policy 的精确值。PASS。

### 4) `docs/host/design.md` WAITING/RECOVERING cancel 语义更新

设计文档更新准确区分了两层：

- **当前可闭环**：`QUEUED`、pre-dispatch `STARTING`、`WAITING`（取消 wait record 收口）、未派发 `RECOVERING`（直接收口）。
- **后续强化**：active worker 物理传播（Phase 5）、外部 job physical cancel / abandon（Phase 7）、recovery dispatch cancellation（Phase 11）。

关键措辞从 "Phase 4 只实现子集" 更新为 "当前覆盖所有可闭环 non-terminal Run"，同时明确 "不能把当前逻辑收口解释为外部执行环境已经物理停止"。与实现一致。PASS。

### Final Follow-Up PASS

未发现实质性问题。follow-up 改动合理：测试补充覆盖了 Runner 边界场景与 EngineEvent 契约锁；设计文档准确反映了 WAITING/RECOVERING cancel 的当前能力与后续强化边界。
