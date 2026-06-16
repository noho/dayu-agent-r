# WU-CLI-FINS-OBS-01 Slice E Review (AgentDS)

## Gate

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: E, README / design-adjacent docs / tests synchronization
- Reviewer: AgentDS
- Date: 2026-06-16
- Plan source: `docs/host/wu-cli-fins-obs-01-replacement-plan.md` Slice E
- Design sources: `docs/host/design.md`; `docs/engine/design.md`
- Control source: `docs/host/issues-implementation-control.md`
- Implementation: `docs/reviews/wu-cli-fins-obs-01-slice-e-implementation-codex.md`

## Scope

当前未提交 diff 中四个 README-only 改动：

- `dayu/README.md`
- `dayu/service/README.md`
- `dayu/fins/README.md`
- `tests/README.md`

不审查 `docs/reviews/wu-cli-fins-obs-01-slice-e-implementation-codex.md` 的正确性（那是 implementation report 的角色）；本文只审查四个 README 改动是否与当前代码一致、是否清理了被否决的 durable job 描述、是否暴露实现细节或写 future plan、tests README 是否准确描述测试覆盖、验证命令是否充分。

## 验证

```text
source .venv/bin/activate && pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_arg_parsing.py -q
281 passed, 3 warnings

source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations

git diff --check
clean
```

所有验证通过，与 implementation codex 报告一致。

## 逐项核对

### 1. dayu/README.md 与当前代码一致性

**代码事实确认：**

- `dayu/service/fins_direct.py` 的 `FinsDirectCommandService` 对 direct commands 暴露 `AsyncIterator[FinsEvent]`（每个命令方法 6 个均为 `-> AsyncIterator[FinsEvent]`），不暴露 `FinsDirectJobHandle`、`stream_job_events_until_terminal`、`wait_for_terminal` 或 `request_cancel(job_id)`。
- `dayu/fins/tools/_ingestion_tool_helpers.py` 的工具调用使用 `ToolAwaitingOutcome(await_kind=EXTERNAL_JOB)` 并调用 `start_observed_*` API，不暴露 durable job id 作为 `resume_token`。
- `dayu/cli/commands/fins.py` 的 CLI 消费 `AsyncIterator[FinsEvent]`，通过 `_wait_for_terminal_handling_sigint` 消费 direct stream，取消走 `cancellation_token.request_cancel("keyboard_interrupt")`（operation-scoped cancellation），不是 `service.request_cancel(job_id)`。
- Legacy `start_*` / `read_job` / `read_job_events` / `request_cancel(job_id)` 仍存在于 `dayu/fins/ingestion_runtime.py` 中，但 `dayu/service/fins_direct.py` 不消费它们（grep 确认为 0 命中）。

**README 对照：**

| README 语句 | 代码事实 | 一致 |
|---|---|---|
| "Fins direct 命令入口通过 `dayu.service.fins_direct` 暴露 `AsyncIterator[FinsEvent]`，不伪装成 Host Run，也不把 CLI 操作建模为 durable job。" (L72) | Service 暴露 6 个 `-> AsyncIterator[FinsEvent]` 方法，无 job handle/cancel | ✅ |
| "`dayu.service.fins_direct`：从 product entrypoint 显式参数构造... 并把 Fins direct runtime events 以 `AsyncIterator[FinsEvent]` 形式交给调用方消费。" (L88) | `FinsDirectCommandService` 调用 `runtime.download()/preprocess()/upload()` 并透传事件 | ✅ |
| "`dayu.fins`：... download / preprocess / process / upload direct stream 与 awaiting observation foundation" (L92) | 代码有 `AsyncIterator[FinsEvent]` direct stream 入口和 `start_observed_*` observation 入口 | ✅ |
| "工具触发的 download、preprocess 与 upload 长事务通过 lightweight observation handle 接入 Host wait-resume。CLI 等 direct 数据命令... 在 Service/Fins boundary 内消费普通 `AsyncIterator[FinsEvent]`，... 取消走当前 operation-scoped cancellation。" (L111) | Tools 返回 `ToolAwaitingOutcome(EXTERNAL_JOB)`，CLI 使用 token-based cancel | ✅ |

**dayu/README.md 结论：PASS。** 与所有已验证代码事实一致。

### 2. dayu/service/README.md 与当前代码一致性

**代码事实确认：**
- `FinsDirectCommandService` 不 import 也不暴露出 `FinsDirectJobHandle`、`stream_job_events_until_terminal` 等旧的 durable job API。
- `FinsDirectCommandService` 通过 `_ensure_result_event` helper 在 stream 正常结束但缺少 RESULT 时合成 failure result。
- Service 方法通过 `cancellation_token` 传播取消。
- 所有 6 个 command 方法返回 `AsyncIterator[FinsEvent]`。

**README 对照：**

| README 语句 | 代码事实 | 一致 |
|---|---|---|
| "`dayu.service.fins_direct`：为 product entrypoint 提供 reusable Fins direct stream helper... `AsyncIterator[FinsEvent]` 透传、terminal result 收口和 operation-scoped cancellation" (L13) | 所有方法返回 `AsyncIterator[FinsEvent]`，`_ensure_result_event` 负责收口 | ✅ |
| "调用方通过 `async for` 消费 `PROGRESS` 与唯一 terminal `RESULT`；若 runtime stream 正常结束但未产出 `RESULT`，Service 会合成清晰 failure result" (L25) | `_ensure_result_event` 实现此行为 | ✅ |
| "Service direct API 不暴露 job id、event sidecar、cursor 或 `request_cancel(job_id)`" (L25) | `fins_direct.py` grep 全部 0 命中，无旧 API 引用 | ✅ |
| "`fins_direct` 的 upload helper 只通过 `FinsIngestionRuntime.upload(...)` 提交" (L25) | Service 调用 `runtime.upload(...)` | ✅ |

**dayu/service/README.md 结论：PASS。** 与所有已验证代码事实一致。已彻底清理了旧 "启动 job / 轮询终态 / durable cancel" 描述。

### 3. dayu/fins/README.md 与当前代码一致性

**代码事实确认：**
- `FinsIngestionRuntime` 暴露三个 direct stream 方法：`async def download(...) -> AsyncIterator[FinsEvent]`、`async def preprocess(...) -> AsyncIterator[FinsEvent]`、`async def upload(...) -> AsyncIterator[FinsEvent]`。
- 暴露三个 observation handle 方法：`start_observed_download(...)`、`start_observed_preprocess(...)`、`start_observed_upload(...)`，都返回 `FinsObservationHandle`。
- 暴露 `poll_observation(handle) -> FinsObservationSnapshot`、`cancel_observation(handle) -> FinsObservationSnapshot`、`abandon_observation(handle) -> None`。
- Legacy helpers `start_download/start_preprocess/start_upload/read_job/read_job_events/request_cancel` 仍存在。
- `FinsEvent` / `FinsProgress` / `FinsResultSummary` 在代码中定义。
- `FinsObservationHandle` / `FinsObservationSnapshot` / `FinsObservationStatus` 在代码中定义。
- `FinsIngestionJobRecord` / `FinsIngestionJobStatus` / `FinsIngestionOperationKind` / `FinsIngestionJobStart` 仍为 legacy 契约。
- `FsFinsIngestionJobStore` 仍存在，服务 legacy job store。
- Wait adapter 调用 `poll_observation` / `cancel_observation` / `abandon_observation`，不调用 `read_job` / `request_cancel(job_id)`。

**README 对照：**

| README 语句 | 代码事实 | 一致 |
|---|---|---|
| "Fins direct stream 是 CLI / Service direct 调用的用户可见进度边界；Fins awaiting observation handle 是 Host wait adapter 的轻量观察引用；二者都不是 Host durable truth。" (L38) | Direct stream 暴露 `FinsEvent`；observation handle 域在 process-local registry | ✅ |
| 列出 `download/preprocess/upload -> AsyncIterator[FinsEvent]` 和 `start_observed_*/poll_observation/cancel_observation/abandon_observation` 为当前稳定入口 (L143-151) | 所有方法在代码中存在 | ✅ |
| "legacy helpers ... 仍保留在 runtime foundation 中服务 legacy job-store 覆盖；Service direct 和 Fins awaiting tools 不消费这些入口。" (L152) | `fins_direct.py` 不 import `start_download/start_preprocess/start_upload`；tools 调用 `start_observed_*` | ✅ |
| 状态机区分 direct result status (success/failure/cancelled)、observation status (pending/running/succeeded/failed/cancelled/lost)、legacy job status (queued/running/cancelling/succeeded/failed/cancelled) (L502-554) | 代码中有三个独立 enum 集合 | ✅ |
| Wait adapter 映射 pending/running -> not ready, succeeded -> completed, failed -> failed, cancelled -> cancelled, lost -> lost outcome (L427-432) | `FinsIngestionWaitPollAdapter` 实现此映射 | ✅ |
| "Direct event 不包含 job id、sequence、cursor、resume token、sidecar path、绝对路径、provider raw payload 或财报正文" (L415) | `FinsEvent` 无此类字段，泄漏测试存在 | ✅ |
| "Direct stream 不创建 durable job record" (L656) | `download()` 路径不创建 job record，通过 direct queue 和 event stream | ✅ |

**发现 DS-E01（非阻断）：调用者装配示例仍使用 legacy API**

fins/README.md 的 "调用者装配示例" → "Download / preprocess / upload caller" 节 (L199-257) 中的 Python 代码示例仍然展示 `ingestion.start_download(...)`、`ingestion.start_preprocess(...)`、`ingestion.start_upload(...)` 三个 legacy 方法调用。该示例未更新为展示 declared stable entry 的 `download(...) -> AsyncIterator[FinsEvent]`、`preprocess(...) -> AsyncIterator[FinsEvent]`、`upload(...) -> AsyncIterator[FinsEvent]` direct stream API。

具体代码（L231-254）：
```python
download_start = ingestion.start_download(FinsDownloadRequest(...))
preprocess_start = ingestion.start_preprocess(FinsPreprocessRequest(...))
upload_start = ingestion.start_upload(FinsUploadFilingRequest(...))
```

这段示例与 L143-145 声明的 stable entry 不一致。读者在看到 "当前稳定入口分为 direct stream、awaiting observation 和 legacy durable job helpers" 后向下滚动到代码示例，看到的是 legacy API 调用，会产生困惑。

严重度评估：非阻断。legacy API 仍存在，示例本身不是错误的。但它在 Slice E（README 同步）的上下文中是一个遗漏——应该同时展示 direct stream `async for event in ingestion.download(...)` 方式作为推荐入口，或将现有示例明确标注为 "legacy 调用者示例"。

建议后续在 `$phaseflow` 的 casual cleanup 轮次中补充 direct stream 调用示例。

**dayu/fins/README.md 结论：PASS。** 核心描述（架构边界、接口、状态机、事件流、关键机制）与当前代码一致。DS-E01 为非阻断一致性问题。

### 4. tests/README.md 与当前测试覆盖一致性

**代码事实确认：**

- `tests/fins/test_fins_ingestion_runtime.py` 覆盖：direct download/upload stream 的 `PROGRESS` 与 `RESULT`、direct stream 不创建 durable job record 或 sidecar、direct stream 使用 operation-scoped cancellation、direct 用户事件不暴露泄漏字段、stream producer 静默结束时收口 failure result、legacy download/preprocess/upload queued job persistence、legacy job event sidecar 的游标读取与序列分配等。
- `tests/fins/test_fins_ingestion_tools.py` 覆盖：工具调用注册 lightweight observation handle 后返回 `ToolAwaitingOutcome(EXTERNAL_JOB)`、启动前 cancellation token 已取消时返回 `ToolCancelledOutcome` 且不注册 observation、wait adapter 的 observation terminal / corrupt token / missing handle / transient unavailable bounded retry 映射、abandon wait 请求 observation cancellation 与 cleanup、lightweight observation handle contract 的 resume token opaque handle id / corrupt token -> LOST / 禁止 job/sequence/cursor 暴露等。
- `tests/service/test_fins_direct.py` 覆盖：runtime `AsyncIterator[FinsEvent]` pass-through、progress/result contract、stream 正常结束但缺少 result 时合成 failure result、task cancellation 关闭 runtime stream、Service 不暴露 job handle / job event / `request_cancel` direct API、direct event leakage guard。

**README 对照：**

| README 语句 | 测试代码事实 | 一致 |
|---|---|---|
| "direct download / upload stream 产出 `PROGRESS` 与唯一 `RESULT`、direct stream 不创建 durable job record 或 sidecar" (L181) | `test_fins_ingestion_runtime.py` 覆盖 | ✅ |
| "工具调用注册 lightweight observation handle 后返回 `ToolAwaitingOutcome(EXTERNAL_JOB)`" (L179) | `test_fins_ingestion_tools.py` 覆盖 | ✅ |
| "poll adapter 对 succeeded / failed / cancelled / pending / corrupt token / missing handle / transient unavailable 的 Host wait outcome 映射" (L179) | `test_fins_ingestion_tools.py` 覆盖 | ✅ |
| "legacy download / preprocess / upload queued job persistence" (L181) | `test_fins_ingestion_runtime.py` 覆盖 | ✅ |
| "cross-runtime shared workspace job store" (L181) | 明确标注为 legacy | ✅ |

**tests/README.md 结论：PASS。** 准确描述了当前 direct stream / lightweight observation handle / legacy job-store 三层测试覆盖。

### 5. 误导性描述检查

逐个 README 搜索以下字符串：

**`dayu/README.md`：**
- CLI direct durable job：无。L72 明确 "不把 CLI 操作建模为 durable job"。
- job event sidecar：无。
- terminal fallback（指 Fins job terminal fallback）：无。出现的 "terminal fallback" 指 Host outbox fallback，是正确语义。
- `request_cancel(job_id)`：无。出现的是 Host `cancel_run(...)`，属于 Host governance。

**`dayu/service/README.md`：**
- CLI direct durable job：无。
- job event sidecar：无。
- terminal fallback（指 Fins job terminal fallback）：无。
- `request_cancel(job_id)`：无。L25 明确 "Service direct API 不暴露 job id、event sidecar、cursor 或 `request_cancel(job_id)`"。

**`dayu/fins/README.md`：**
- `request_cancel(job_id)`：在 L534 和 L656 出现，但每次都明确标注为 legacy 路径的行为。例如 L656："Legacy `start_*` job helpers 仍可创建 durable `queued` job record 并通过 `request_cancel(job_id)` 合作式取消，**但 Service direct 和 awaiting tools 不消费该路径**。"
- job event sidecar：在 L190 和 L416-417 出现，正确标注为 legacy。例如 L190："该路径是 legacy runtime foundation，不是 Service direct 或 awaiting tool 的公共观察边界。"

**结论：PASS。** 四个 README 均无将 CLI direct 描述为 durable job、job event sidecar、`request_cancel(job_id)` 或 terminal fallback 的误导性描述。所有保留的 durable/legacy 描述都显式标注为 legacy 且限定范围。

### 6. 实现细节过度暴露 / future plan 检查

**实现细节暴露：**
- `dayu/fins/README.md` L379 暴露了 legacy job store 的具体文件系统路径 `<workspace_root>/.dayu/fins_ingestion/jobs`。但该路径是 Fins workspace 规则的一部分，属于开发者需要知道的 workspace 布局事实，不是内部实现细节。且标注为 legacy。可接受。
- 各 README 均未暴露 EventLog 内部结构、durable store 表结构、dispatch scheduler 内部状态、Engine provider payload 格式或 runner 实现细节。✅

**Future plan：**
- `dayu/fins/README.md` L678："只有明确需要跨进程或跨重启恢复未完成 ingestion 时，才应单独设计最小 durable operation ledger；不得用 CLI direct 或"以后可能"作为 durable 需求。" 这是扩展 guardrail，不是 future plan。它告诉开发者扩展前必须满足的前置条件。✅
- 其他 README 均无 "将来"、"计划"、"下一步"、"roadmap" 等未来时表述。✅

**结论：PASS。** 无实现细节过度暴露，无 uncommitted future plan。

### 7. 验证命令充分性

Implementation codex 验证了：

1. `pytest` 覆盖所有 Slices A-D 的受影响测试文件，281 passed, 3 warnings。
2. `pyright dayu/ tests/ utils/` —— 0 errors。
3. `git diff --check` —— clean。

以上验证命令覆盖了：
- `tests/service/test_fins_direct.py`：Service direct stream contract
- `tests/cli/test_fins_commands.py`：CLI direct stream consumption + cancel
- `tests/fins/test_fins_ingestion_runtime.py`：Direct stream + legacy job-store coverage
- `tests/fins/test_fins_ingestion_tools.py`：Observation handle + await tools + wait adapter mapping
- `tests/service/test_host_assembly.py`：Wait adapter registry assembly
- `tests/cli/test_upload_filings_from_command.py`、`tests/cli/test_init_command.py`、`tests/cli/test_prompt_command.py`、`tests/cli/test_interactive_command.py`、`tests/cli/test_arg_parsing.py`：Non-Fins CLI command output regression guards

独立复现全部通过。

**结论：PASS。** 验证命令充分覆盖 Slice E 范围。

## 裁决

**整体结论：PASS。**

四份 README 改动与当前代码事实一致：
- Direct commands = `AsyncIterator[FinsEvent]`，PROGRESS + 唯一 terminal RESULT
- Awaiting tools = `ToolAwaitingOutcome(EXTERNAL_JOB)` + lightweight observation handle（process-local registry）
- Legacy job-store 已正确标注为 legacy，不作为 Service direct 或 awaiting tool 的公共观察真源

已清理的误导性描述：
- CLI direct durable job → 已移除
- Job event sidecar 作为 CLI direct truth → 已移除
- Terminal fallback synthetic event → 已移除
- `request_cancel(job_id)` 作为 CLI direct cancel → 已移除

所有三个 warning 为第三方依赖 edgartools 的 DeprecationWarning，与本次改动无关。

阻断发现：**0 blocking findings**。

非阻断发现：**DS-E01** —— fins/README.md 的 "调用者装配示例" 中 Download/preprocess/upload 代码示例仍展示 legacy `start_download/start_preprocess/start_upload` API，未更新为 declared stable entry 的 `download/preprocess/upload -> AsyncIterator[FinsEvent]` direct stream API。建议后续 casual cleanup 轮次补齐。
