# A1-A12 Accepted Fixes — Focused Re-Review

## Scope

- Mode: current changes (focused re-review of A1-A12 accepted fixes)
- Branch: phaseflow/wu-cm-01
- Base: HEAD (workspace uncommitted diff)
- Output file: docs/reviews/repo-review-20260604-fix-review-ds.md
- Design source of truth: docs/engine/design.md, docs/host/design.md
- Adjudication source: docs/reviews/repo-review-20260604-controller-adjudication.md
- Implementation record: docs/reviews/repo-review-20260604-fix-codex.md
- Included scope: all workspace diff files implementing A1-A12, related tests, README/docs sync
- Excluded scope: God module governance (M1), schema migration (R1), engine root exports (R2, R3), host importing engine (R4), _PublicHostHandle.close() lock concern (R5), cancellation token caching (R6), watch-session poll interval (R7), missing-owner orphan classification (R8), lane cancellation helper extraction (R9)

## Verification Baseline

- `pytest` (affected tests): 206 passed
- `pyright dayu/ tests/ utils/`: 0 errors, 0 warnings, 0 informations
- `git diff --check`: clean

## Findings

未发现实质性问题。

### 逐项审查摘要

**A1 — AsyncRunner.call() design sync**
- `docs/engine/design.md` §7: `request_identity` 已作为 keyword-only 参数加入 AsyncRunner.call() 签名，默认值 `None`，与实现一致。
- `tests/engine/runners/openai/test_protocol_surface.py`: 签名断言更新为 tuple 顺序检查，验证 KEYWORD_ONLY 和默认值 `None`。
- 无 contract 越界，与 design.md 一致。

**A2 — HTTP-date Retry-After**
- `dayu/engine/runners/openai/retry_policy.py`: `parse_retry_after` 新增 keyword-only `now` 参数（默认 `None`），HTTP-date 解析委托给 `_parse_retry_after_http_date`，使用标准库 `email.utils.parsedate_to_datetime`。
- 正确区分 delay-seconds 和 HTTP-date 两种形态；过去/非未来时间返回 `None`。
- `_parse_retry_after_http_date` 对无时区 HTTP-date 假定 UTC，有时区时转换到 UTC；`now` 参数同样转换到 UTC，与 design doc 无冲突。
- 测试覆盖：非法日期字符串、过去 HTTP-date、未来 HTTP-date（精确 7 秒）。pyright 通过。
- 审查确认：`now` 参数为 naive datetime 时 `astimezone(UTC)` 会抛 `ValueError`。但这是测试专用参数，生产路径始终使用 `datetime.now(UTC)`，不构成实际风险。

**A3 — 移除不可达 ServerTimeoutError 分支**
- `aiohttp.ServerTimeoutError` 继承自 `asyncio.TimeoutError`（Python 3.11 验证通过），第二个 `isinstance` 检查确实不可达。
- `dayu/engine/runners/openai/error_classifier.py`: 移除死分支，保留 `asyncio.TimeoutError → TIMEOUT` 归类。docstring 同步更新说明子类覆盖关系。
- 无行为变化，测试验证 ServerTimeoutError 仍归类为 TIMEOUT。

**A4 — 新增 durable 查询索引**
- 新增索引：`host_instances(status, heartbeat_at)` 和 `event_log(session_id, event_sequence)`。
- Schema version: 15 → 16。
- 索引正确加入 `HOST_DURABLE_INDEXES`（validation 真源）、`FOUNDATION_INDEX_DDL`（creation 真源）。
- Schema validation 覆盖：
  - `_read_user_version` → 版本校验
  - `_missing_required_indexes` → 名称存在性
  - `_validate_required_object_definitions` → SQL 定义精确匹配
  - 三者组成一条完整的 validation 链路
- 测试验证：索引存在性、列顺序（`status, heartbeat_at` 和 `session_id, event_sequence`）。
- 遵循 fresh schema 约束：`bootstrap_host_durable_store` 对 v0 执行 fresh bootstrap，对 v16 只做校验，其它版本结构化失败。

**A5 — runtime 文档加入 diagnostic_text**
- `dayu/runtime/__init__.py` 文档补充 `diagnostic_text` 和 `_digest` 说明。纯文档变更。

**A6 — cancel_session_runs WAITING/RECOVERING 语义**
- 代码事实确认（`dayu/host/admission.py`）：
  - `_session_cancel_target_for_run` 已对 WAITING（行 4278）和 RECOVERING（行 4305）正确分类。
  - WAITING 路径额外要求 `attempt.status == AttemptStatus.SUSPENDED`（行 4295），否则返回 `None` → 上层抛 `UNSUPPORTED_OPERATION`（fail-closed）。
  - RECOVERING 路径无额外 attempt 状态约束，允许 `attempt`/`dispatch_record` 为 `None`。
  - `_cancel_target` 正确分发到 `_cancel_waiting_target`（行 2206）和 `_cancel_recovering_target`（行 2239）。
- Docstring 从"由后续 phase 负责"更新为实际行为描述，与代码实现对齐。
- 测试：`test_cancel_session_runs_cancels_waiting_run` 验证 `WaitRecordStatus.CANCELLED` 和 `RUN_CANCELLED` event；RECOVERING cancel 已由既有测试覆盖。
- 审查确认：`host/design.md` 行 1009/1182/2416 仍标注 WAITING/RECOVERING cancel 为 "deferred"，但这些是 Phase tracking 标注（Phase 7/11），不是设计约束。代码实现已超前于 Phase 计划，docstring 更新是正确的。

**A7 — dispatch close cleanup 异常路径标记 done**
- `dayu/host/dispatch.py` `close()`（行 2028-2054）：cleanup 体包裹在 `try/except Exception` 中。
  - `except Exception` 块设置 `_close_cleanup_done = True` 后 re-raise。
  - `asyncio.CancelledError`（Python 3.11 继承自 `BaseException`）不被 `except Exception` 捕获，因此 CancelledError 路径不标记 cleanup done，支持重试。
  - 正常路径在 try 块结束后设置 `_close_cleanup_done = True`（行 2054）。
- `_closed` 在 cleanup 前设置（行 2020），早期返回 guard 为 `self._closed and self._close_cleanup_done`（行 2018），因此 CancelledError 后可重试。
- 测试 `test_scheduler_close_marks_cleanup_done_when_cleanup_raises`：注入 `_FailingLaneClose` 验证 RuntimeError 穿透后 `_close_cleanup_done is True`、`_closed is True`、`failing_close.calls == 1`。
- 审查确认：无竞态引入。CancelledError retry 路径清理操作（cancel task、discard handle）是幂等的。

**A8 — ToolDisplayInfo.name 非空校验**
- `dayu/contracts/tool_declaration.py` `ToolDisplayInfo.__post_init__`（行 76-83）：调用 `_require_non_empty_text(self.name, field_name="ToolDisplayInfo.name")`。
- 与 ToolDefinition 使用同一 helper，错误消息格式一致（`"{field_name} must be non-empty"`）。
- 测试 `test_tool_display_info_rejects_empty_name` 覆盖空白 name 拒绝。
- 类型安全：frozen dataclass，`__post_init__` 始终在构造时调用。

**A9 — tool() 返回类型不暴露私有 _ToolDecorator**
- `dayu/contracts/tool_declaration.py` `tool()` 返回类型从 `_ToolDecorator` 改为 `Callable[[ToolCallable], ToolDefinition]`。
- 纯类型层面变更，运行时行为不变。`_ToolDecorator` 仍存在且可正常工作，只是不再通过公开 API 签名暴露。
- pyright 验证通过（0 errors）。
- `Callable[[ToolCallable], ToolDefinition]` 精确描述了装饰器的公共语义：输入 ToolCallable，输出 ToolDefinition。

**A10 — runtime text_digest helper 复用**
- `dayu/runtime/_digest.py` 新增 `text_digest(value: str) -> str`，输出 `sha256:<hex>`，与 `canonical_json_digest` 同前缀。
- `dayu/runtime/scene_prepare.py`：`_text_digest` 私有函数已移除，改用 `text_digest`。
  - 两处调用点（fragment ref digest 和 source ref digest）均使用 `text_digest(content)`。
  - digest 输出格式不变（`sha256:<hex>`），与旧实现一致。
- `tests/runtime/test_digest.py` 验证输出形态；`tests/runtime/test_scene_prepare.py` 新增具体 fragment digest 精确断言。
- 审查确认：复用路径不影响 digest 稳定性。

**A11 — 安全合并重复 _require_non_empty_text**
- `dayu/contracts/_validation.py`：层中立基础校验模块，只依赖 `from __future__ import annotations`，无其它依赖。
- 合并范围（语义完全一致，错误类型 `ValueError`，返回 `None`）：
  - `dayu/contracts/tool_source.py`（移除私有 `_require_non_empty_text`/`_require_optional_non_empty_text`）
  - `dayu/runtime/tools_discovery.py`（同上）
- 新接入（从内联校验迁移）：
  - `dayu/contracts/tool_declaration.py`：`ToolDefinition.__post_init__` 和 `ToolDisplayInfo.__post_init__`
- 正确保留未合并的本地 validator：
  - `dayu/runtime/scene_prepare.py`：抛 `ScenePrepareError` 且返回 strip 后文本，语义不同
  - `dayu/host/durable/`：抛 `HostDurableError`，语义不同
- 审查确认：
  - `dayu.runtime.tools_discovery.py` 从 `dayu.contracts._validation` 导入不违反分层约束（runtime 可依赖 contracts 层）。
  - 错误类型（`ValueError`）、返回语义（`None`）、错误消息格式（`"{field_name} must be non-empty"`）在合并范围内完全一致。
  - 测试 `test_tools_discovery_digest.py` 的 `test_schema_mapping_with_non_string_key_is_rejected` 正确地从 digest 层校验迁移到 schema 构造边界校验（`ToolParametersSchema.__post_init__`），`normalize_json_value` 中的冗余校验仍保留作为防御。

**A12 — 移除 dispatch CAS 后 sleep(0)**
- `dayu/host/dispatch.py` `_dispatch_one`（原行 2328）：`await asyncio.sleep(0)` 已移除。
- `_mark_dispatching_after_recheck` 和 `_dispatch_record_still_pre_accept` 均为同步方法（通过 `transaction_runner.run_write` 执行），无内部 await 点。
- 移除 sleep(0) 消除了 CAS accept 和 pre-accept recheck 之间的自愿 yield 窗口，减小了 inconsistent read 的可能窗口。
- 取消安全：`except asyncio.CancelledError` handler 仍在外层包裹 `_start_worker` 和 lane token release。
- 既有取消竞态测试（`test_dispatch_scheduler.py`）继续通过，验证 recheck 前取消仍释放 lane 且不启动 worker。

### 分层与依赖边界审查

- `dayu.contracts._validation`：零外部依赖（仅 `from __future__ import annotations`），位于最底层公共契约。
- `dayu.runtime._digest`：依赖 `dayu.contracts`（`JsonValue`），符合 runtime 依赖 contracts 的分层约束。
- `dayu.runtime.tools_discovery`：新增 `from dayu.contracts._validation import`，符合 runtime 可依赖 contracts 的约束。
- `dayu.runtime.scene_prepare`：从 `dayu.runtime._digest` 导入（包内依赖），无跨层穿透。
- Engine runner 模块（`retry_policy.py`, `error_classifier.py`）：仅依赖 stdlib，无向上依赖。
- Host 模块（`admission.py`, `dispatch.py`, `durable/schema.py`）：仅依赖同层模块和下层 contracts，无反向依赖。
- 未发现分层违规。

### README/docs 同步审查

- `dayu/README.md`：runtime 能力列表新增"文本 / JSON digest"描述，`_digest` 模块说明新增。与代码一致。
- `dayu/engine/README.md`：fallback Runner 调用路径示例补充 `request_identity=identity`。与 A1 设计同步一致。
- `tests/README.md`：runtime 测试说明补充 digest helper 覆盖；contracts 测试说明补充展示名非空校验。与实现一致。
- `docs/engine/design.md`：§7 AsyncRunner.call() 签名同步。与 A1 一致。
- `docs/host/maintainability-implementation-control.md`：source review artifact 引用更新、RR-MAINT-01 描述补充 20260604 review findings。
- `dayu/host/README.md`：按 AgentCodex 报告，本次 Host 变更未改变稳定接口，不做机械更新。审查确认本判断合理。

## Open Questions

无。

## Residual Risk

- 本次只运行受影响测试集合（206 passed），未运行全量 pytest。
- A6 WAITING cancel 要求 `attempt.status == SUSPENDED`；非 SUSPENDED 的 WAITING run 会导致 `cancel_session_runs` 以 `UNSUPPORTED_OPERATION` fail-closed。这是设计意图，但未在测试中显式覆盖该 fail-closed 路径。
- A7 CancelledError retry 路径未显式测试（需在 async 上下文中注入 CancelledError 到 lane_controller.close）。当前手工验证依赖 Python 3.11 `CancelledError` 继承自 `BaseException` 的行为保证。
- `host/design.md` 行 1009/1182/2416 仍标注 WAITING/RECOVERING cancel 为 Phase 7/11 deferred，与当前代码实现不一致。这不属于本次 A1-A12 fix scope，但建议后续 Phase tracking 刷新时同步更新。

## Verdict

**PASS** — A1-A12 accepted fixes 的实现、测试和文档同步均通过 focused re-review。未发现 correctness、stability、layering、public contract 或 schema validation 方面的实质性问题。

## Controller Follow-Up

- `docs/host/design.md` 中关于 `cancel_session_runs` 只覆盖 Phase 1-3 子集、`WAITING` / `RECOVERING` deferred 的旧标注已同步为当前实现事实。
- 同步后保留边界：`WAITING -> CANCELLED` 与未派发 `RECOVERING -> CANCELLED` 是当前可闭环逻辑收口；外部 job physical cancel / abandon 与 recovery dispatch cancellation 仍由后续 owner 强化。

## Final Follow-Up PASS

全量 pytest 通过（1995 passed, 1 skipped, 5 deselected）、pyright 0、diff check clean。对本次 follow-up 的五项变更逐项审查：

### 1. `_call_impl` 私有方法测试显式传 `request_identity=None`

- 文件：`tests/engine/runners/openai/test_runner_b3_extra.py:81`
- `AsyncOpenAIRunner._call_impl` 签名（`runner.py:327-334`）：`request_identity` 为 required keyword-only 参数（`request_identity: RunnerRequestIdentity | None`，无默认值）。
- 旧调用 `runner._call_impl(msgs, make_options(stream=True), [])` 缺少该必选参数。
- 新调用显式传递 `request_identity=None`，与测试目的一致（该测试验证 SSE idle close 不泄漏 pending task，不测试 request identity 行为）。
- **符合设计**：`AsyncRunner.call()` 的 keyword-only `request_identity` 默认值为 `None`，`_call_impl` 接收相同类型但作为 required kwarg；测试传 `None` 不改变被测行为。

### 2. `client_correlation_id` 加入 EngineEvent 字段锁测试

- 文件：`tests/engine/test_engine_event_contract.py:165-182`
- `client_correlation_id: str | None = None` 已存在于生产代码 `dayu/engine/contracts/engine_events.py` 的以下 dataclass：
  - `IterationCompletedData`（行 332）
  - `RunFailedData`（行 415）
  - `ContextCompactionRequestedData`（行 273）
- 测试 `test_provider_request_id_fields_are_locked` 之前断言这三个 dataclass 的完整字段集合但遗漏了 `client_correlation_id`。
- 本次修正将测试断言与生产 dataclass 字段集合对齐，不是新增字段。
- **符合当前 contract**：测试现在精确反映生产代码的字段契约。

### 3. pressure bounds 测试纳入 `_compact_pressure_reserve_tokens`

- 文件：`tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py:280-286`
- `_compact_pressure_reserve_tokens` 在 `utils/smoke_host_public_conversation_memory_scenarios.py:2372-2382` 定义为语义函数：
  - 接受 `context_window_size` 参数
  - 基于 context window class 分支（`>= 1_000_000` vs 更小）
  - 两个分支当前返回同一常量 `_COMPACT_PRESSURE_RESERVE_TOKENS = 160_000`，但语义上属于"输出预留 + 系统开销估算"，不是无意义硬编码
- 旧 pressure 计算 `prompt_tokens + _tool_pressure_estimated_tokens()` 缺少 system reserve overhead。
- 新计算补全了 reserve tokens，使用与生产 pressure 辅助逻辑相同的 `_compact_pressure_reserve_tokens(context_window_size=policy.context_window_size)` 函数，`context_window_size` 从 policy 读取而非硬编码。
- **同源语义**：测试使用与 smoke pressure 辅助相同的函数和数据源，不引入独立硬编码值。

### 4. `docs/host/design.md` WAITING/RECOVERING cancel 语义边界更新

- 文件：`docs/host/design.md` 行 1009、1181-1182、2416、2427-2428
- 变更将三处 Phase tracking 标注从"deferred"更新为准确反映当前实现与后续强化边界：

| 位置 | 旧表述 | 新表述 | 审查 |
|---|---|---|---|
| Phase 4 behavior matrix (行 1009) | "WAITING、RECOVERING cancel deferred" | "完整覆盖当前可闭环状态；active worker 物理传播、外部 job physical cancel / abandon 与 recovery dispatch 中取消继续由对应后续 owner 强化" | "当前可闭环"与"physical"的区分准确 |
| `cancel_run` 语义 (行 1181) | "WAITING 与 RECOVERING cancel 分别由 Phase 7 / Phase 11 落地" | "WAITING Run 通过取消 wait record 直接 CANCELLED；未派发的 RECOVERING Run 直接 CANCELLED。外部 job physical cancel / abandon 与 recovery dispatch cancellation 分别由 Phase 7 / Phase 11 强化" | 区分了 logical cancel（已实现）与 physical/recovery cancel（deferred），边界清晰 |
| `cancel_session_runs` 语义 (行 1182) | "Phase 4 只实现 queued / pre-dispatch STARTING 子集" | "取消该 Session 下所有当前可闭环未终态 Run。queued / pre-dispatch STARTING、WAITING 与未派发 RECOVERING 会直接收口" | 准确反映已实现覆盖范围 |
| `cancel_session_runs` 详细 (行 2416) | "Phase 4 只实现... WAITING、RECOVERING... stable deferred" | "当前实现覆盖所有当前可闭环 non-terminal Run... 不能把当前逻辑收口解释为外部执行环境已经物理停止" | "逻辑收口"与"物理停止"的区分是关键的语义边界 |
| per-run cancel 路径 (行 2427-2428) | WAITING "Phase 7 owns 该路径"、RECOVERING "Phase 11 recovery owner 接入" | WAITING "Phase 7 继续拥有该强化路径"、RECOVERING "在新 recovery dispatch 尚未提交前直接取消；已进入 recovery dispatch 的取消强化由 Phase 11 recovery owner 接入" | 准确区分 pre-dispatch cancel（已实现）vs dispatch 后 cancel（deferred） |

- **语义准确性**：所有更新一致区分三个层次——
  1. **逻辑收口**（当前可闭环）：cancel wait record、Run → CANCELLED transition
  2. **物理传播**（deferred）：外部 job 实际停止、active worker 取消传播
  3. **Recovery dispatch 取消**（deferred）：已派发 recovery 的取消强化
- 不会让读者误以为外部执行环境已被物理停止，也不会让读者以为 WAITING/RECOVERING 仍完全无法取消。

### 综合判定

五项 follow-up 变更均合理：
- 测试变更（#1, #2, #3）修复了测试与生产代码之间的不一致，不改变任何生产行为
- 设计文档变更（#4）准确反映了当前实现事实并保留了后续强化边界
- 全量 pytest（1995 passed）和 pyright（0 errors）验证通过

**Final Follow-Up PASS** — 无新增 findings。
