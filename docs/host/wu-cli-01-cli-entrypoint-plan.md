# WU-CLI-01 CLI entrypoint integration plan

## Gate 状态

- 当前 gate：plan gate only。
- 本 artifact 只产出可直接用于代码生成的实现计划，不进入 implementation、review、fix、commit、push、PR 或其它 gate。
- 允许写入文件：`docs/host/wu-cli-01-cli-entrypoint-plan.md`。
- 设计真源：`docs/host/design.md`、`docs/engine/design.md`。
- 总控文档：`docs/host/ui-implementation-control.md`。
- 外部跟踪：GitHub Issue 83，仓库 `noho/dayu-agent-r`。
- 旧 CLI 对照源：`/Users/leo/workspace/dayu-agent/dayu/cli/` 与 `/Users/leo/workspace/dayu-agent/dayu/fins/cli_support.py`。

## Goal

实现 `dayu-agent-r` 的 CLI entrypoint，使当前 `pyproject.toml` 已声明的 `dayu-cli = "dayu.cli.main:main"` 有真实入口，并与旧 `dayu-agent` CLI 的用户可见命令面在本 WU scope 内对齐。

CLI 在架构上是当前 UI adapter，不是 Service 真源。`prompt` 与 `interactive` 必须通过 `ConfigLoader -> ScenePrepare -> ToolsDiscovery -> Service assembly -> Host public API` 触达 Host；Fins 直接数据命令必须通过 approved Service / Fins boundary 触达 Fins runtime 与 `dayu.fins.storage`，不能伪装成 Host run，也不能散落直接读取财报仓储。

本 WU 的迁移对象是旧 `dayu-agent` CLI / Fins 命令的业务语义、用户可见行为、参数面和 cancel 语义；实现方式必须适配当前新的 Service boundary、Fins runtime 与 Host public contracts / API。它不是迁移旧代码实现，也不能把旧实现目录结构、label registry、dependency setup、interactive UI 或旧 contracts 机械搬进当前仓库。

## Motivation

第一性原理判断：问题真实存在，且不是“补一个 main.py”就能解决。

- 当前 `pyproject.toml` 的 console script 指向 `dayu.cli.main:main`，但当前仓库缺少 `dayu/cli` 包；CLI entrypoint 直接不可用。
- 总控文档把 WU-CLI-01 定义为 CLI 通过 Service assembly 与 Host public API 接入，并与旧 `dayu-agent` CLI 对齐。
- Host 设计把生命周期、admission、cancel、wait-resume、event observation 作为 Host 真源；CLI 不能绕过 Service/Host 直接拼 Engine 请求。
- Engine 设计把 Engine 定位为单次 `AgentRunRequest` 执行边界；CLI 不应构造或持有 Engine contract。
- 当前 `dayu.service.host_assembly` 已经提供 config、scene、tool discovery 到 Host opener / submit request 的 typed assembly，但还缺复用型“会话打开、follow-up、终态观察、取消、错误映射”Service 边界。
- 当前 Fins runtime 已有 `DefaultFinsRuntime`、`FinsIngestionRuntime`、durable job store、wait adapter 和 `request_cancel(job_id)`；Fins direct CLI 应使用这些能力，而不是新建 CLI 专用长事务状态机。

问题严重性判断：缺口会导致用户无法通过当前声明的 `dayu-cli` 使用系统；如果把 orchestration 写进 CLI，会把未来 WeChat / GUI 所需的同一会话语义复制到多个 UI adapter，破坏 `UI -> Service -> Host -> Engine`。

## Success Signal

- `dayu-cli --help` 展示本 WU scope 内命令：`init`、`prompt`、`interactive`、`download`、`upload_filing`、`upload_material`、`upload_filings_from`、`process`、`process_filing`、`process_material`。
- `dayu-cli prompt ...` 通过 Service assembly 打开 Host，创建或复用 Session，提交 follow-up，观察 Host terminal event 并输出 final answer。
- `dayu-cli interactive ...` 使用同一 Service 会话语义支持 label / new-session、逐轮 follow-up、运行中取消与终端错误映射。
- Prompt / interactive 的 terminal observation 对快速完成 Run race-free：Service 在 `submit_followup(...)` 之前 attach live watcher，并用 public `get_run(...)` / `read_outbox_terminal_items(...)` 做补读兜底；禁止 submit 后才开始 watch。
- Fins direct commands 通过 Service / Fins boundary 调用 `DefaultFinsRuntime.get_ingestion_runtime()`，start job 后用 `read_job(job_id)` 观察终态；用户 SIGINT 必须映射为 `request_cancel(job_id)`，而不是只取消本地 asyncio task。
- 旧 CLI command surface audit 完成，每个不对齐点都有 intentional deviation 说明。
- 受影响测试、help snapshot / smoke、Host open-follow-up mocked path、Fins cancel path 覆盖完成；pyright 无新增或扩散报错。
- README 只按 AGENTS.md 触发规则更新，不把本计划或未来路线图写进 README。

## Non-goals / Scope Boundary

纳入 scope：

- `init`。
- `prompt`。
- `interactive`。
- Fins 直接数据命令：`download`、`upload_filing`、`upload_material`、`upload_filings_from`、`process`、`process_filing`、`process_material`。

不纳入 scope：

- write workflow。
- 差异化 Host 管理命令：`host`、`sessions`、`runs`、`cancel`、`conv` 等。这些命令需要按当前 Host public API 重新裁决管理面，不在 WU-CLI-01 里移植旧实现。
- Web / GUI / WeChat / render entrypoint。
- 旧 `llm_models.json` / `run.json` schema 兼容读取、旧库迁移、旧 workspace migrations。
- 任何 Host / Engine public API 大改。若实现时发现必须改 Host / Engine 设计真源，应停止并回到 design gate。

## Design Document Alignment

### Host design alignment

- CLI 只作为 UI adapter，不能成为 Host 状态或业务编排真源。
- Prompt / interactive 的入口路径固定为：解析 CLI 参数 -> 解析 workspace / config location -> `ConfigLoader` -> `ScenePrepare` -> `ToolsDiscovery` -> `compose_open_host_options(...)` -> `open_host(...)` -> Host public `ensure_session` / `create_session` -> submit 前 attach `watch_session_events` -> `submit_followup` -> `get_run` / `read_outbox_terminal_items` 兜底 -> `cancel_run`。
- CLI 不传 raw config fragment、manifest patch、profile id 字符串 payload 给 Host；Service 层负责把用户可见 override 映射为 Host public typed inputs。
- `close_session` 不承担用户取消语义。运行中 Ctrl-C 必须显式调用 `cancel_run(...)` 或当前 Session 的 active run cancel helper。
- `watch_session_events(...)` 是 live subscription，不是历史补读 API；计划禁止在 `submit_followup(...)` 完成后才 attach watcher，否则快速 terminal event 可能已经落在 attach cursor 之前。
- Fins direct command 不创建 Host Run，不写 Host EventLog，不使用 Host wait record；只有 LLM 工具触发的 Fins long job 才通过 Host wait adapter 接入 Host wait-resume。

### Engine design alignment

- CLI 不 import `dayu.engine` contract 来构造 `AgentRunRequest`。
- Engine 仍只通过 Host worker 被调用；CLI 看到的是 Host public event / terminal projection，不看到 Engine 内部 iteration 或 runner 状态机。
- Runner option / AgentPolicy override 只由 Service 合并成 `SubmitFollowupRequest.runner_options` / `agent_policy`，而不是由 CLI 拼 Engine request。
- Fins read / download / process / upload 位于 Engine 外部；财报存取只通过 `dayu.fins.storage` 仓储协议与 `DefaultFinsRuntime`。

## 直接代码证据

- `pyproject.toml` 已声明 `dayu-cli = "dayu.cli.main:main"`，当前 `rg --files dayu` 未发现 `dayu/cli`，entrypoint 缺失成立。
- `dayu/service/host_assembly.py` 当前提供：
  - `discover_service_tools(...)`。
  - `compose_open_host_options(...)`。
  - `compose_submit_followup_request(...)`。
  - `ServiceAssemblyOverrides(host_runtime_id, execution_profile_id, model_id, runner_option_hint_id)`。
- `compose_submit_followup_request(...)` 当前把 `runner_spec`、`runner_options`、`agent_policy` 固定为 `None`，因此旧 CLI 中可映射的 per-run override 需要新增 Service helper 合并，而不是让 CLI 自己拼 Host request。
- `dayu/host/api.py` 已提供 public `EnsureSessionRequest`、`CreateSessionRequest`、`SubmitFollowupRequest`、`CancelRunRequest`、`CancelSessionRunsRequest` 与 Host Protocol 方法。
- `dayu/host/api.py` 当前真实 `HostCallContext` 字段为 `actor: str`、`source: str`、`request_id: str`、`authorization_claims: tuple[AuthorizationClaim, ...]`、`operation_context: OperationContext`；`OperationContext` 字段为 `operation_name`、`operation_kind`、`business_domain`、`business_object_type`、`business_object_id`、`scenario`、`correlation_id`。本计划不得使用 review artifact 中旧表述的 `caller` / `service` / `metadata` 字段名。
- `dayu/host/api.py` 当前真实 `CancelRunRequest` 字段为 `context`、`client_request_id`、`reason`、`mode`；`CancelMode` 当前唯一 public 值是 `CancelMode.GRACEFUL`。任何实现不得写成 `cancel_run(reason=...)`。
- `dayu/host/open_host.py` 提供 async-only `open_host(options)`；同步 CLI 只能在 CLI / Service adapter 边界用 `asyncio.run` 包装，Host 不增加同步 wrapper。
- `dayu/host/open_host.py` 的 `watch_session_events(session_id)` 是普通 public method，调用时先取 `_session_live_event_start_cursor(...)`，再返回 `_watch_session_events_after(session_id, cursor)`；其 docstring 明确是 “Session live HostEvent 订阅”，内部 `_watch_session_events_after(...)` 只读取该 attach cursor 之后的事件。
- `dayu/host/api.py` 的 `FollowupSnapshot.command_watermark` docstring 明确说明它是 command commit 后的 durable read watermark，“不是 `watch_session_events` 的 watch cursor”；不能把 submit 返回的 watermark 当成 watch 起点。
- `dayu/host/api.py` / `dayu/host/open_host.py` 已提供 public `get_run(run_id)`，`RunSnapshot.status` 包含 `SUCCEEDED`、`FAILED`、`CANCELLED`、`LOST` 终态，可作为 run 是否已终态的 public snapshot 判断。
- `dayu/host/api.py` / `dayu/host/open_host.py` 已提供 public `read_outbox_terminal_items(session_id, ReadOutboxTerminalItemsRequest)`；请求字段为 `after: OutboxTerminalCursor`、`seen_terminal_event_ids: tuple[str, ...]`、`limit: int`；返回 `OutboxTerminalItemsBatch` 包含 `items`、`next_cursor`、`scanned_watermark`、`projection_checkpoint`、`projection_status`、`projection_error_code`、`projection_error_message`、`has_more`。`OutboxProjectionStatus` 只有 `CAUGHT_UP`、`LAGGED`、`FAILED`。
- `OutboxTerminalItem` 包含 `terminal_event_id`、`event_sequence`、`run_id`、`terminal_status`、`dedupe_key`、`final_answer`、`error_message`、`cancel_reason`；`dedupe_key` 必须等于 `terminal_event_id`。`HostEvent` 同样暴露 `event_id`、`event_sequence`、`run_id`、`dedupe_key`、`terminal_status`，Service 只能用这些 public 字段做去重和补读游标。
- `dayu/runtime/config_loader.py` 只读取新 schema：`models.json`、`execution_profiles.json`、`host_runtime.json`、`runtime_lanes.json`、`tool_discovery.json`，且显式拒绝 legacy `llm_models.json` / `run.json`。
- `dayu/runtime/location.py` 当前默认解析 `workspace/config` overlay；旧 CLI 的 `--config` 需要一个层中立 location 扩展，而不是在 CLI 里复制路径推导。
- `dayu/config/prompts/manifests/prompt.json` 与 `interactive.json` 当前真实 `context_slots` 均为 required string：`fins_default_subject` 与 `base_user`；没有旧独立 `prompt_mt` 场景。
- `dayu/fins/service_runtime.py` 提供 `DefaultFinsRuntime.create(workspace_root).get_ingestion_runtime()`。
- `dayu/fins/ingestion_runtime.py` 提供 `start_download(FinsDownloadRequest)`、`start_preprocess(FinsPreprocessRequest)`、`start_upload(FinsUploadRequest)`、`read_job`、`request_cancel` 和 job status：`QUEUED`、`RUNNING`、`CANCELLING`、`SUCCEEDED`、`FAILED`、`CANCELLED`。`FinsUploadRequest` 是 `FinsUploadFilingRequest | FinsUploadMaterialRequest` 联合类型，runtime 没有 `start_upload_filing(...)` 或 `start_upload_material(...)` 方法。
- `dayu/fins/ingestion/wait_adapter.py` 的 `abandon_wait(...)` 已把 Host wait abandon 映射到 `runtime.request_cancel(job_id)`，说明 Fins job cancel 真源是 ingestion job store。
- 旧 CLI 的 `command_names.py` 中 Fins commands 为 `download`、`upload_filing`、`upload_filings_from`、`upload_material`、`process`、`process_filing`、`process_material`；Host management commands 为 `sessions`、`runs`、`cancel`、`host`，本 WU 不纳入。
- 旧 CLI 的 SIGINT 标准退出码为 130。

## 旧 CLI Command Surface Audit

### 全局参数

旧 CLI 对多数命令支持：

- `--base` / `-b` / `--workspace`：工作区根目录，默认 `./workspace`。
- `--config`：配置目录，默认 `workspace/config`。
- 日志等级：`--log-level {debug,verbose,info,warn,error}`、`--debug`、`--verbose`、`--info`、`--quiet`。

计划对齐：

- 保留参数名、别名和用法错误 exit code 2。
- `--base` / `--workspace` 映射为 project workspace root。
- `--config` 通过 runtime location resolver 的中立扩展映射为 explicit config overlay；默认仍为 `workspace/config`。
- `--config` 行为必须显式：
  - 未传 `--config` 且默认 `workspace/config` 不存在：不是错误，`resolve_runtime_locations(...)` 返回 `config_overlay_dir=None`，使用 package 默认 config / prompt assets / manifests。
  - 传入 `--config`：相对路径先按 project workspace root 解析，再 `expanduser().resolve(strict=False)`；绝对路径直接 resolve。
  - 显式路径不存在、存在但不是目录、或 resolve 后不在 project workspace root 内：fail fast，CLI exit 2，不得静默 fallback 到 package 默认配置。
  - 显式目录存在但缺少 `prompts/` 或 `prompts/manifests/`：仍作为 config overlay 传给 `ConfigLoader`；prompt asset / manifest root 可按现有 resolver 规则 fallback 到 package 默认资产。
- 日志参数只配置 CLI / runtime logging，不进入 Host payload。

### 旧执行覆盖参数

旧 `prompt` / `interactive` 执行参数包括：

- `--model-name` / `-m`。
- `--thinking` / `--no-thinking`。
- `--web-provider`。
- `--temperature`。
- `--debug-sse`、`--debug-tool-delta`、`--debug-sse-sample-rate`、`--debug-sse-throttle-sec`。
- `--tool-timeout-seconds`。
- `--enable-tool-trace`、`--tool-trace-dir`。
- `--max-iterations`。
- `--fallback-mode`、`--fallback-prompt`。
- `--max-consecutive-failed-tool-batches`。
- `--max-duplicate-tool-calls`、`--duplicate-tool-hint-prompt`。
- `--doc-limits-json`、`--fins-limits-json`。

计划对齐：

- `--model-name` 映射为 `ServiceAssemblyOverrides.model_id`。
- `--temperature` 映射为本 turn 的 `RunnerCallOptions.temperature` override。
- `--tool-timeout-seconds`、`--max-iterations`、`--fallback-mode`、`--fallback-prompt`、`--max-consecutive-failed-tool-batches` 映射为本 turn 的 `AgentPolicy` override。
- `--thinking` / `--no-thinking` 只有在当前 `models.json` / provider extension 存在明确可选模型或 runner hint 时才映射；否则解析保留但执行时报 unsupported，避免把旧模型目录语义硬编码进 CLI。
- `--web-provider`、`--doc-limits-json`、`--fins-limits-json` 只有在当前 `tool_discovery.json` provider config 有 typed override helper 时才实现；WU-CLI-01 不允许把这些 JSON 作为 raw payload 塞进 Host。若无 helper，则解析保留、执行时报 unsupported。
- `--debug-sse`、`--debug-tool-delta`、`--debug-sse-sample-rate`、`--debug-sse-throttle-sec`、`--enable-tool-trace`、`--tool-trace-dir`、`--max-duplicate-tool-calls`、`--duplicate-tool-hint-prompt` 当前无 Host public per-run typed contract，作为 intentional deviation：parser 保留这些旧参数以便给出稳定错误；命令执行前统一 fail fast，输出 unsupported option，exit 2；不得警告后继续、静默忽略或 forward 到 Host raw payload。

### 命令审计

| 命令 | 旧参数 / 行为 | WU-CLI-01 对齐策略 |
| --- | --- | --- |
| `init` | `--base/-b`、`--reset`、`--overwrite`；复制 config/assets，选择 provider，写旧 config，跑旧 workspace migrations。 | 保留命令名和参数。实现当前 schema bootstrap：创建 workspace、复制当前 `dayu/config` 到 `workspace/config`，按 `--reset` / `--overwrite` 控制覆盖。不得生成旧 `llm_models.json` / `run.json`，不得跑旧 migrations。provider interactive 只可修改当前 `models.json` / `execution_profiles.json` 的 typed fields。 |
| `prompt` | positional `prompt`；`--ticker`；`--label`；`--model-name/-m`；`--thinking/--no-thinking`；执行覆盖参数；旧 `--label` 走 `prompt_mt`。 | 保留用户可见参数。使用当前 `prompt` scene；`--ticker` 映射为 `context_slot_values["fins_default_subject"]`，缺省为 `未指定具体公司`；`base_user` 映射为 `本地 CLI 用户` 或后续 auth display name；`--label` 映射为 Host session slot key，不使用旧 `prompt_mt`，这是 intentional deviation。 |
| `interactive` | `--label` 与 `--new-session` 互斥；`--model-name/-m`；`--thinking/--no-thinking`；执行覆盖参数；REPL 支持逐轮输入和中断。 | 保留旧参数，并新增 optional `--ticker` 作为当前 `interactive.json` required context slot 的用户可见填充值；`--label` 映射为 Host scoped slot；`--new-session` 创建新 session 并绑定 slot；`--ticker` 映射为 `context_slot_values["fins_default_subject"]`，缺省为 `未指定具体公司`；`base_user` 映射为 `本地 CLI 用户` 或后续 auth display name；运行中 Ctrl-C 调用 Host cancel，非运行输入态 Ctrl-D 退出。 |
| `download` | `--ticker` required，CSV alias；`--forms`；`--start`；`--end`；`--overwrite`；`--rebuild`；`--infer`。 | 映射为 `FinsDownloadRequest(ticker, form_types, filed_after, filed_before, overwrite_existing, rebuild_processed)`。`--infer` 当前无 approved Fins alias inference boundary，解析保留但执行时报 unsupported。download 的 CSV alias 不静默持久化，超过一个 ticker token 时提示当前只使用 canonical 或要求用户拆命令。 |
| `upload_filing` | `--ticker`；`--action {create,update,delete}`；`--files`；`--fiscal-year`；`--fiscal-period`；`--amended`；`--filing-date`；`--report-date`；`--company-name`；`--infer`；`--overwrite`。 | CLI 参数传给 `FinsDirectCommandService.start_upload_filing(...)`，由该 wrapper 构造 `FinsUploadFilingRequest` 并调用 `FinsIngestionRuntime.start_upload(...)`。CSV alias 和 `--company-name` 可传入当前 upload request 的 typed fields；`--infer` unsupported。delete 只有当前 upload runtime 支持时放行，否则执行时报 unsupported。 |
| `upload_material` | `--ticker`；`--action`；`--forms`；`--material-name`；`--files`；`--document-id`；`--internal-document-id`；period/date/company；`--infer`；`--overwrite`。 | CLI 参数传给 `FinsDirectCommandService.start_upload_material(...)`，由该 wrapper 构造 `FinsUploadMaterialRequest` 并调用 `FinsIngestionRuntime.start_upload(...)`。保留同名参数；`--infer` unsupported。参数组合必须在 CLI / Service 边界校验，业务存取仍由 Fins runtime 完成。 |
| `upload_filings_from` | `--ticker`；`--from`；`--action {create,update}`；`--output`；`--recursive`；metadata flags；`--material-forms`；生成批量 upload 脚本。 | 保留命令名和主要参数。新增 Fins boundary helper 负责扫描目录、识别 filing/material、生成结构化计划；CLI 只负责把计划格式化为 `dayu-cli upload_*` 命令。该命令不启动 ingestion job。 |
| `process` | `--ticker`；repeatable / comma `--document-id`；`--overwrite`；`--ci`。 | 映射为 `FinsPreprocessRequest(source_kind=FILING, document_ids=..., rebuild_processed=overwrite)`。`--ci` 当前无公共 CI snapshot contract，解析保留但执行时报 unsupported。 |
| `process_filing` | `--ticker`；`--document-id`；`--overwrite`；`--ci`。 | 映射为 `FinsPreprocessRequest(source_kind=FILING, document_ids=(document_id,), rebuild_processed=overwrite)`。`--ci` unsupported。 |
| `process_material` | `--ticker`；`--document-id`；`--overwrite`；`--ci`。 | 映射为 `FinsPreprocessRequest(source_kind=MATERIAL, document_ids=(document_id,), rebuild_processed=overwrite)`。`--ci` unsupported。 |
| `write` | 旧写作 workflow。 | 不注册。运行 `dayu-cli write` 走 argparse invalid choice，exit code 2。 |
| `host` / `sessions` / `runs` / `cancel` / `conv` | 旧 Host 管理面与 label registry。 | 不注册。后续按当前 Host public API 单独设计。 |
| Web / GUI / WeChat / render | 旧或其它入口。 | 不纳入本 WU。 |

### Help text 与 exit code

- `dayu-cli --help` 的 `prog` 使用当前 console script 名 `dayu-cli`，不是旧 `python -m dayu.cli`。`python -m dayu.cli` 通过 `__main__.py` 支持，但 help 主显示仍用 `dayu-cli`。这是 intentional deviation。
- help 文案使用中文，保留旧 CLI 的命令名和核心参数名。
- exit code：
  - 成功：0。
  - 业务 / 运行失败：1。
  - argparse 用法错误：2。
  - 用户 SIGINT / 本地取消成功发起：130。
- Fins job terminal `FAILED` 映射 1，`CANCELLED` 映射 130，`SUCCEEDED` 映射 0。

## 影响文件和模块边界

### UI adapter

新增 `dayu/cli/`：

- `dayu/cli/__init__.py`：包概览与 public exports，不能承载业务逻辑。
- `dayu/cli/__main__.py`：调用 `main()`。
- `dayu/cli/main.py`：解析参数、设置日志、分发命令、兜底 SIGINT exit code。
- `dayu/cli/arg_parsing.py`：构建 parser、命令参数和 help text。
- `dayu/cli/exit_codes.py`：CLI exit code 常量。
- `dayu/cli/host_context.py`：CLI-local `HostCallContext` / `OperationContext` / Host mutating `client_request_id` 构造 helper；只使用 Host public DTO，不调用 Host method。
- `dayu/cli/output.py`：CLI 输出格式化，只处理终端展示，不处理业务状态真源。
- `dayu/cli/commands/init.py`。
- `dayu/cli/commands/prompt.py`。
- `dayu/cli/commands/interactive.py`。
- `dayu/cli/commands/fins.py`。

CLI 模块允许导入 `dayu.service`、`dayu.runtime` 的基础错误类型、`dayu.fins` 的枚举 / request 类型和只读 domain value；不得导入 `dayu.engine` 内部，不得直接读写 Fins storage 路径。

### 可复用 Service boundary

新增 / 扩展：

- `dayu/runtime/location.py`：给 `resolve_runtime_locations(...)` 增加 optional explicit config overlay 参数，默认行为不变。
- `dayu/service/entrypoint_runtime.py`：新增可复用 Agent entrypoint service helper。
- `dayu/service/host_assembly.py`：保留现有 `compose_submit_followup_request(...)` 行为不变；新增 `ServiceRunOverrides` 与具体 sibling helper `compose_submit_followup_request_with_overrides(...)` 支持 typed per-run `RunnerCallOptions` / `AgentPolicy` override。
- `dayu/service/fins_direct.py`：新增可复用 Fins direct job helper，封装 start / poll / cancel / terminal mapping。
- `dayu/service/README.md`：若新增 Service public helper，更新当前已实现的 Service 边界说明。

Service helper 是公共入口语义，不是 CLI 专用胶水，理由：

- prompt / interactive 所需的 session open、follow-up、terminal observation、cancel、错误映射是所有 UI adapter 共享语义。
- Fins direct job 的 start / poll / cancel 语义可被 CLI、未来 GUI、内部任务面板复用。
- 这些 helper 不持有 CLI argparse、终端渲染或 stdout/stderr 概念。

### Fins boundary

可能新增：

- `dayu/fins/upload_batch.py`：若当前 Fins 没有等价 helper，新增 typed batch upload plan generator。它只负责业务识别与结构化计划，不输出 shell text。

必须保持：

- Fins document storage 只通过 `dayu.fins.storage` 仓储协议与 `DefaultFinsRuntime` 间接触达。
- CLI 不直接读取 `workspace/fins` 下文件结构。

### Host public API 调用点

只能通过：

- `dayu.host.open_host.open_host`。
- `Host.ensure_session(...)`。
- `Host.create_session(...)`。
- `Host.submit_followup(...)`。
- `Host.watch_session_events(...)`。
- `Host.get_run(...)`。
- `Host.read_outbox_terminal_items(...)`。
- `Host.cancel_run(...)` 或 `Host.cancel_session_runs(...)`。

不得导入 Host store、scheduler、command/read internal API。

## Public Contract / Schema / State Machine 判断

### 需要新增或扩展的 public contract

- CLI command surface 是新的用户可见 public contract。
- `dayu.runtime.location.resolve_runtime_locations(...)` 增加 optional explicit config overlay 参数；默认行为不变，属于层中立 runtime 能力。
- `dayu.service.host_assembly.compose_submit_followup_request(...)` 保持无 override 的既有调用方稳定；同模块新增 `ServiceRunOverrides`：
  - `temperature: float | None`
  - `tool_execution_timeout_seconds: float | None`
  - `max_iterations: int | None`
  - `fallback_mode: str | None`
  - `fallback_prompt: str | None`
  - `max_consecutive_failed_tool_batches: int | None`
- 同模块新增 `compose_submit_followup_request_with_overrides(...)`：
  - 参数包含 `context`、`session_id`、`client_request_id`、`scene_inputs`、`user_prompt`、`tool_names`、`behavior`、`target_run_id`、`host_assembly: ServiceOpenHostAssemblyResult`、`run_overrides: ServiceRunOverrides`。
  - 内部先调用既有 `compose_submit_followup_request(...)` 生成 base request，再用 host assembly 的 `ordinary_selection` 与 `agent_policy_config` 生成完整 typed `RunnerCallOptions` / `AgentPolicy`，最后 `dataclasses.replace(...)` 到 `runner_options` / `agent_policy`。
  - `temperature` 只覆盖完整 `RunnerCallOptions.temperature`；`tool_execution_timeout_seconds`、`max_iterations`、`fallback_mode`、`fallback_prompt`、`max_consecutive_failed_tool_batches` 只覆盖完整 `AgentPolicy` 对应字段；未覆盖字段来自 current assembly baseline，不得传 patch dict。
  - 不在本 helper 中处理 unsupported 旧 flags；unsupported 必须在 CLI 参数转换阶段 exit 2。
- `dayu.service.entrypoint_runtime` 新增 public dataclass / helper：
  - `EntrypointRuntimeRequest`。
  - `EntrypointRuntimeResult`。
  - `EntrypointTurnRequest`。
  - `EntrypointRunTerminalResult`。
  - `EntrypointCancelRequest`。
  - `prepare_entrypoint_runtime(...)`。
  - `ensure_or_create_entrypoint_session(...)`。
  - `submit_entrypoint_turn_and_wait(...)`。
  - `cancel_entrypoint_run_and_wait(...)`。
- `dayu.service.fins_direct` 新增 public dataclass / helper：
  - `FinsDirectRuntimeRequest`。
  - `FinsDirectStartRequest`。
  - `FinsDirectJobHandle`。
  - `FinsDirectTerminalResult`。
  - `FinsDirectCommandService`。

这些 contract 只表达当前 UI entrypoint 必须共享的 Service 语义，不新增 Host / Engine 状态。

### 不做的 schema / state change

- 不修改 Host EventLog schema。
- 不修改 Host session / run / attempt 状态机。
- 不修改 Engine `AgentRunRequest`。
- 不修改 Fins ingestion job store schema。
- 不新增旧 workspace schema migration。

### Host call context 与幂等 id 策略

当前 `dayu.host.api` 的 `HostCallContext` 字段必须按真实 public contract 构造：`actor`、`source`、`request_id`、`authorization_claims`、`operation_context`。职责划分如下：

- CLI / UI adapter 负责构造 `HostCallContext`，因为 actor、source、auth claims、用户可见 command / scene / ticker 都来自入口层；reusable `dayu.service.entrypoint_runtime` 只接收并透传 context，不在 Service helper 内硬编码 CLI 身份。
- 本 WU 的本地 CLI 默认值：
  - `actor="cli-user"`，未来若 CLI 增加登录 / profile，可替换为已解析的人类用户或 service principal。
  - `source="dayu-cli"`。
  - `request_id="dayu-cli:<command>:<uuid4hex>:<operation>"`，每次 Host API 调用生成一个新的追踪 id；它不是幂等键，不参与重放判定。
  - `authorization_claims=()`；本地 CLI 当前无认证声明，不伪造 role。未来 auth 层若提供声明，必须显式构造成 `AuthorizationClaim(name=..., value=...)`。
  - `operation_context=OperationContext(...)`：
    - `operation_name` 使用 `dayu_cli.<command>.<operation>`，例如 `dayu_cli.prompt.submit_followup`、`dayu_cli.interactive.cancel_run`、`dayu_cli.prompt.create_session`。
    - `operation_kind` 使用 `cli_prompt`、`cli_interactive` 或 `cli_init` / `cli_fins_direct`。
    - `business_domain` 对 prompt / interactive / Fins direct 使用 `fins`，对纯 Host session 操作仍按入口业务归入 `fins`，不写 `host` 来伪装成管理面。
    - `business_object_type="ticker"` 且 `business_object_id=<ticker>` 仅在用户提供 `--ticker` 时设置；否则二者为 `None`。
    - `scenario` 使用当前 scene id：`prompt` 或 `interactive`；Fins direct 使用命令名。
    - `correlation_id` 使用本次 CLI invocation id，所有同一命令进程内的 session/create/submit/cancel context 共享该 id。
- CLI adapter 生成并持有 `cli_invocation_id = uuid4().hex`，interactive 每轮生成递增 `turn_index`。Service helper 不生成这些入口身份 id，只校验传入字段非空并传给 Host request。
- `client_request_id` 与 `HostCallContext.request_id` 必须分开：
  - `CreateSessionRequest.client_request_id = "dayu-cli:<command>:<cli_invocation_id>:session:create"`。
  - `SubmitFollowupRequest.client_request_id = "dayu-cli:<command>:<cli_invocation_id>:turn-<n>:submit"`。
  - 同一 turn 对同一 `run_id` 的 cancel 必须复用同一个 `CancelRunRequest.client_request_id = "dayu-cli:<command>:<cli_invocation_id>:turn-<n>:run-<run_id>:cancel:cli_sigint"`，重复 Ctrl-C 不得生成新 cancel 幂等键。
  - `EnsureSessionRequest` 当前 public contract 没有 context / client_request_id，只传 `scope`、`slot_key`、`metadata`；若 helper 选择 create path，必须使用上面的 create context 与 create client_request_id。

### Agent prompt / interactive state machine

1. Resolve workspace / config / scene / tools。
2. Compose `OpenHostOptions`。
3. `open_host(options)`。
4. `ensure_session` 或 `create_session`：
   - 无 label：为当前 command 创建 session。
   - 有 label：用 stable slot key 复用 session。
   - `--new-session`：创建新 session 并绑定同一 slot key。
5. 在提交 follow-up 前调用 `watch_session_events(session_id)`，立即创建 live watcher，并启动 Service 内部 event-drain task，把 HostEvent 写入本地 typed queue。调用点必须早于 `submit_followup(...)`。
6. `submit_followup(behavior=QUEUE)`，记录 `FollowupSnapshot.accepted_run_id`。`command_watermark` 只用于诊断，不作为 watch cursor。
7. 等待 terminal：
   - 优先消费 live watcher queue 中 `event.run_id == accepted_run_id` 且 `terminal_status is not None` 的 HostEvent。
   - watcher queue 可以先收到 terminal，再等 `submit_followup(...)` 返回；Service 在知道 `accepted_run_id` 后再按 run id 过滤。
   - Service 在本 turn 内维护 `last_observed_event_sequence: int`、`seen_event_ids: set[str]`、`seen_terminal_event_ids: set[str]`、`seen_dedupe_keys: set[str]`；每个 watcher event 无论是否属于当前 run，都先用 `event_id` / `dedupe_key` / `event_sequence` 去重，再推进 `last_observed_event_sequence=max(...)`。terminal event 的 `event_id` 加入 `seen_terminal_event_ids`。
   - 若 live watcher 暂未给出 terminal，按 Agent terminal poll interval 调用 public `get_run(accepted_run_id)`；若 `RunSnapshot.status` 已是 `SUCCEEDED` / `FAILED` / `CANCELLED` / `LOST`，再用 public `read_outbox_terminal_items(...)` 查找同一 `run_id` 的 terminal item 作为展示 payload 补读。
   - Outbox fallback 初始 cursor 为 `OutboxTerminalCursor(event_sequence=last_observed_event_sequence)`；如果 watcher 还没有产出任何事件，则使用 `OutboxTerminalCursor(event_sequence=0)`。请求固定使用 `ReadOutboxTerminalItemsRequest(after=cursor, seen_terminal_event_ids=tuple(sorted(seen_terminal_event_ids)), limit=50)`。
   - 每次 outbox read 后先扫描 `batch.items` 中 `item.run_id == accepted_run_id` 的 terminal item；找到即返回 `source="outbox_read"`，并用 `item.dedupe_key` 去重。未找到时把 cursor 推进到 `batch.next_cursor`，记录 `batch.scanned_watermark` 仅用于诊断。
   - `batch.has_more=True` 表示当前 cursor 后仍有同 Session item，必须继续分页读取，不能睡眠后重头读，也不能把未匹配视为丢失。
   - `batch.projection_status == OutboxProjectionStatus.LAGGED` 时，空结果或未匹配都不能视为完整；按同一 poll interval 重试 `get_run(...)` + outbox read，直到 caught up、failed、找到目标 item 或外层 timeout / cancel。
   - `batch.projection_status == OutboxProjectionStatus.FAILED` 时，立即升级为 Service terminal observation error，错误中包含 `projection_error_code` / `projection_error_message`，CLI prompt 映射 exit 1，interactive 按 fatal service error 退出。
   - `batch.projection_status == OutboxProjectionStatus.CAUGHT_UP` 且已经分页到 `has_more=False` 仍找不到同一 `run_id` 的 terminal item，同时 `get_run(...)` 已确认该 run 终态：按 Host public projection contract violation 处理为 Service error；不得读取 Host durable internals，也不新增第三种成功 terminal source。
8. 返回 `EntrypointRunTerminalResult`，包含 terminal 来源：`live_event` 或 `outbox_read`，以及 dedupe key。
9. 运行中 SIGINT：
   - 已拿到 `run_id`：构造 `CancelRunRequest(context=<cancel HostCallContext>, client_request_id=<本 turn 本 run 稳定 cancel id>, reason="cli_sigint", mode=CancelMode.GRACEFUL)`，再调用 `Host.cancel_run(run_id, request)`。
   - 未拿到 `run_id`：停止本地等待并关闭 Host handle，不写取消事实。
   - 取消命令 accepted 后继续观察到 terminal 或输出 run id 供用户后续管理面处理；exit code 130。

Race-free 逻辑：

- `watch_session_events(...)` 的 attach cursor 在 submit 前取得，因此本 turn 的 input accepted、run accepted、terminal event 都在 cursor 之后。
- event-drain task 即使在 `submit_followup(...)` 返回前收到 terminal，也只缓存在本地 queue；不会因尚未知 `accepted_run_id` 而丢弃。
- `accepted_run_id` 是 submit 的 public return；Service 只按该 id 选择 terminal，避免 label session 中其它 run 的 terminal 混入。
- `get_run(...)` / `read_outbox_terminal_items(...)` 只作为 public 补读兜底，不替代 submit 前 watcher；它们用于处理本地 watcher task 调度、消费异常或恢复路径，不引入 Host internals。
- 每次 `submit_entrypoint_turn_and_wait(...)` 调用创建新的 watcher、队列和去重集合；terminal、错误、cancel 或 timeout 后必须取消 drain task 并关闭 watcher。当前 `open_host.py` 返回 async generator，支持 `aclose()`；实现应定义窄 `ClosableHostEventIterator` Protocol 表达 `aclose()`，fake Host watcher 也实现它，避免把 watcher 生命周期留给 GC。
- interactive 多轮不得复用上一轮 watcher、queue、cursor 或 `seen_*` 集合；只可在 CLI 输出层保存已展示 terminal 的高水位用于用户界面去重，不可影响下一轮 Host terminal wait 的 run_id 过滤。

### Fins direct job state machine

1. CLI 参数校验。
2. 构造 typed request：download / preprocess 直接构造 `FinsDownloadRequest` / `FinsPreprocessRequest`；upload 由 `FinsDirectCommandService.start_upload_filing(...)` / `start_upload_material(...)` wrapper 构造 `FinsUploadFilingRequest` / `FinsUploadMaterialRequest`。
3. `DefaultFinsRuntime.create(workspace_root).get_ingestion_runtime()`。
4. `start_*` 返回 job id。
5. 循环 `read_job(job_id)`，默认 poll interval 为 1.0 秒：
   - `QUEUED` / `RUNNING` / `CANCELLING`：继续等待并输出进度。
   - `SUCCEEDED`：exit 0。
   - `FAILED`：stderr 输出失败原因，exit 1。
   - `CANCELLED`：exit 130。
6. 运行中 SIGINT：
   - 第一次 SIGINT：调用 `request_cancel(job_id)`，输出取消已请求和 job id，继续等待 terminal。
   - 第二次 SIGINT：本地立即 exit 130，但必须已完成第一次 `request_cancel(job_id)`。

Fins direct polling 策略：

- 在 `dayu/service/fins_direct.py` 定义 `DEFAULT_FINS_DIRECT_POLL_INTERVAL_SECONDS = 1.0`。
- `FinsDirectCommandService` constructor 接收 `poll_interval_seconds: float = DEFAULT_FINS_DIRECT_POLL_INTERVAL_SECONDS` 与可注入 `sleep` coroutine，便于测试；CLI 本 WU 不新增用户可见 `--poll-interval`，避免扩大旧 CLI 参数面。
- `poll_interval_seconds` 必须为有限正数，建议上限 60 秒；非法值在 Service 构造或命令参数转换阶段 fail fast，CLI exit 2。
- 测试必须断言默认值为 1.0 秒，`QUEUED` / `RUNNING` / `CANCELLING` 路径会调用注入 sleep，terminal status 不再 sleep。

## Implementation Slices

### CLI-01-S1: CLI package skeleton, parser, help and exit contract

Objective：

建立 `dayu/cli` 包、console entrypoint、parser 与命令分发骨架，确保 `dayu-cli --help` 和 scoped subcommand help 可运行，但不执行 Host / Fins 业务。

Allowed files / modules：

- `dayu/cli/__init__.py`
- `dayu/cli/__main__.py`
- `dayu/cli/main.py`
- `dayu/cli/arg_parsing.py`
- `dayu/cli/exit_codes.py`
- `dayu/cli/commands/__init__.py`
- `tests/cli/test_arg_parsing.py`

Exact allowed changes：

- 新增 parser factory，注册 scoped commands。
- 实现 global args、prompt / interactive args、Fins args、init args。
- `interactive --help` 必须包含 optional `--ticker`，用于填充当前 `interactive.json` required `fins_default_subject` context slot；这是对旧参数面的 additive compatibility，不改变无 ticker 时的交互行为。
- 不注册 `write`、`host`、`sessions`、`runs`、`cancel`、`conv`。
- `main(argv: Sequence[str] | None = None) -> int` 只负责 parse、dispatch 和 exit code mapping。
- 所有函数完整中文 docstring，严格类型签名，不使用 `Any` / `object` / 无类型参数。

Data flow：

`main(argv)` -> `build_parser()` -> parse args -> command dispatch table -> placeholder command runner。

State transitions：

无 durable state；只处理 CLI process exit state。

Error handling：

- argparse usage error -> exit 2。
- unknown command -> exit 2。
- placeholder runner 不应被用户路径触发；测试中可验证 dispatch table 完整性。
- `KeyboardInterrupt` -> exit 130。

Cancel behavior：

S1 只设置顶层 SIGINT exit code，尚无 Host / Fins job cancel。

Tests / validation：

- `dayu-cli --help` 包含 scoped commands，不包含 excluded commands。
- 每个 scoped command `--help` 包含核心参数。
- missing command exit 2。
- `python -m dayu.cli --help` 可运行。

Completion signal：

CLI help contract 通过单元测试，`dayu-cli` entrypoint import 不再失败。

Stop condition：

若 parser 需要旧 command 的内部业务类型才能完成，停止并拆分，不能把旧 contracts 移植进 CLI。

### CLI-01-S2: Runtime location and reusable Agent entrypoint Service boundary

Objective：

把 prompt / interactive 共享的配置解析、scene 准备、工具发现、Host open、session ensure/create、follow-up、terminal observation、cancel 和错误映射沉淀到 Service 边界。

Allowed files / modules：

- `dayu/runtime/location.py`
- `dayu/service/entrypoint_runtime.py`
- `dayu/service/host_assembly.py`
- `dayu/service/__init__.py`
- `tests/runtime/test_location.py`
- `tests/service/test_host_assembly.py`
- `tests/service/test_entrypoint_runtime.py`

Exact allowed changes：

- 给 `resolve_runtime_locations(...)` 增加 keyword-only `explicit_config_overlay_dir: Path | None = None`；为 `None` 时保持当前 `workspace/config` 行为。
  - `explicit_config_overlay_dir is None`：现有默认行为不变；默认 `workspace/config` 不存在时返回 `config_overlay_dir=None`，不报错。
  - `explicit_config_overlay_dir is not None`：调用方已完成 `--config` path 解析和 containment 校验；resolver 仍必须校验该路径存在且是目录，否则抛 `RuntimeLocationError`。
- 新增 `EntrypointRuntimeRequest`：
  - `workspace_root: Path`
  - `package_config_root: Path`
  - `explicit_config_dir: Path | None`
  - `scene_id: str`
  - `context_slot_values: Mapping[str, JsonValue]`
  - `assembly_overrides: ServiceAssemblyOverrides`
  - `env: Mapping[str, str]`
- 新增 `EntrypointRuntimeResult`：
  - `locations: RuntimeLocations`
  - `runtime_config: RuntimeConfig`
  - `scene_inputs: PreparedSceneInputs`
  - `discovered_tools: ServiceDiscoveredTools`
  - `host_assembly: ServiceOpenHostAssemblyResult`
- 从 `dayu.service.host_assembly` 复用 `ServiceRunOverrides`，不在 entrypoint runtime 里重复定义 override dataclass。字段为：
  - `temperature: float | None`
  - `tool_execution_timeout_seconds: float | None`
  - `max_iterations: int | None`
  - `fallback_mode: str | None`
  - `fallback_prompt: str | None`
  - `max_consecutive_failed_tool_batches: int | None`
- 新增 `EntrypointTurnRequest`：
  - `context: HostCallContext`
  - `session_id: str`
  - `client_request_id: str`
  - `user_prompt: str`
  - `tool_names: frozenset[str] | None`
  - `behavior: FollowupBehavior`
  - `target_run_id: str | None`
  - `run_overrides: ServiceRunOverrides`
- 新增 `EntrypointCancelRequest`：
  - `context: HostCallContext`
  - `run_id: str`
  - `client_request_id: str`
  - `reason: str`
  - `mode: CancelMode`
- 新增 / 使用 helper 合并 runner options / agent policy：
  - 固定使用 `dayu.service.host_assembly.compose_submit_followup_request_with_overrides(...)`，不得在 `entrypoint_runtime.py` 里另写第二套 override merge。
  - 合并逻辑基于 `ServiceOpenHostAssemblyResult.ordinary_selection` 和 `agent_policy_config`。
  - 只把可映射字段写入完整 typed `SubmitFollowupRequest.runner_options` / `agent_policy`。
  - unsupported execution args 在 CLI 参数转换阶段报错，不进入 Service。
- 新增 async helpers：
  - `prepare_entrypoint_runtime(...)`。
  - `ensure_or_create_entrypoint_session(...)`。
  - `submit_entrypoint_turn_and_wait(...)`。
  - `cancel_entrypoint_run_and_wait(...)`。
- `submit_entrypoint_turn_and_wait(...)` 必须实现 submit 前 watcher attach：
  - 参数接收 `Host` public Protocol，不接收 Host internal handle。
  - 在调用 `Host.submit_followup(...)` 前先调用 `Host.watch_session_events(session_id)` 并启动 drain task。
  - submit 返回后用 `FollowupSnapshot.accepted_run_id` 过滤 terminal event。
  - 等待循环同时消费 watcher queue，并按 poll interval 调用 `Host.get_run(accepted_run_id)` 检查 terminal snapshot。
  - 当 `get_run(...)` 显示已终态但 watcher queue 尚未给出 terminal 时，调用 `Host.read_outbox_terminal_items(...)` 补读同一 run 的 terminal payload。
  - outbox read 必须使用 `OutboxTerminalCursor`、`seen_terminal_event_ids`、`limit=50`，处理 `projection_status` 的 `CAUGHT_UP` / `LAGGED` / `FAILED`，并按 `has_more` 分页推进；不得调用 Host durable/read internal API。
  - 以 `HostEvent.dedupe_key` / `OutboxTerminalItem.dedupe_key` 去重，返回 `EntrypointRunTerminalResult(source=...)`。
- `cancel_entrypoint_run_and_wait(...)` 接收 `EntrypointCancelRequest`，并构造 Host public request：
  - `CancelRunRequest(context=request.context, client_request_id=request.client_request_id, reason=request.reason, mode=request.mode)`。
  - CLI SIGINT 固定 `reason="cli_sigint"`、`mode=CancelMode.GRACEFUL`。
  - 必须复用当前 turn 已 attach 的 watcher；若是独立 cancel wait helper，也必须在 `Host.cancel_run(...)` 前 attach watcher。
  - 重复 cancel 同一 run 必须复用同一 `client_request_id`，利用 Host `(run_id, client_request_id)` 幂等，不得为第二次 Ctrl-C 创建第二个 durable cancel request。

Data flow：

`EntrypointRuntimeRequest` -> runtime locations -> `ConfigLoader.load()` -> `ToolsDiscovery` -> `ScenePrepare` -> `compose_open_host_options()` -> `open_host()` -> session helper -> attach live watcher -> submit turn -> live event / get_run / outbox read terminal wait。

State transitions：

Service 不持久化状态，只调用 Host public state machine；session / run state 真源仍在 Host。

Error handling：

- Config / scene / tool discovery / assembly errors 映射为 Service entrypoint error，CLI 映射 exit 1。
- invalid user override 映射为 value error with field name，CLI 映射 exit 2。
- explicit `--config` 不存在、不是目录或路径逃逸映射为 `RuntimeLocationError` / CLI exit 2；默认 `workspace/config` 不存在不报错。
- Host terminal `FAILED` / error terminal 映射 exit 1。
- Host terminal `CANCELLED` 在 one-shot prompt 中映射 exit 130；interactive 的 cancelled / failed / lost 策略以 S4 固定分类为准。

Cancel behavior：

- `submit_entrypoint_turn_and_wait(...)` 在拿到 run id 后允许外部触发 cancel。
- `cancel_entrypoint_run_and_wait(...)` 调用 `Host.cancel_run(...)` 前必须已经有 watcher；然后等待同一 session event stream 或 outbox read 终态。
- Service helper 不安装 signal handler；signal 属于 UI adapter。

Tests / validation：

- explicit config overlay 位置解析：显式路径不存在、不是目录、resolve 后逃逸均 exit 2；未显式传入且默认 `workspace/config` 不存在时不报错并使用 package defaults。
- `prepare_entrypoint_runtime(...)` 不导入 Engine 内部，不扫描工具模块。
- mocked Host 验证 ensure/create、watch、submit、get_run、read_outbox、cancel 调用顺序；`watch_session_events` 必须早于 `submit_followup`。
- context/id 测试：CLI adapter 构造的 `HostCallContext` 字段必须为当前 `dayu.host.api` 真实字段；`HostCallContext.request_id` 与 mutating request `client_request_id` 必须不同；重复 cancel 复用同一 cancel client_request_id。
- per-run `temperature` 和 `AgentPolicy` override 只进入 Host public fields。
- fast terminal race test：fake Host 在 `submit_followup(...)` 返回前或返回瞬间把 terminal event 放入 watcher stream，Service 仍返回该 terminal。
- watcher fallback test：fake watcher 不产出 terminal，但 `get_run(...)` 返回 terminal 且 `read_outbox_terminal_items(...)` 返回同 run item，Service 返回 outbox terminal。
- outbox projection tests：覆盖 `CAUGHT_UP` 命中、`CAUGHT_UP` + `has_more=True` 分页后命中、`CAUGHT_UP` 且 caught-up-without-match 转 Service error、`LAGGED` 重试、`FAILED` 转 Service error。
- unrelated terminal filtering test：同一 session watcher 中出现其它 run terminal，不得结束当前 turn。
- watcher lifecycle tests：每次 turn 都创建新 watcher；terminal / error / cancel 后 drain task 被取消且 watcher `aclose()` 被调用；第二轮 fake watcher 不接收第一轮残留 event；重复 `event_sequence` / `dedupe_key` 不会重复返回 terminal。

Completion signal：

Prompt / interactive 可以只依赖 `dayu.service.entrypoint_runtime` 完成 Host orchestration，不需要在 CLI 中直接编排 Host 状态机。

Stop condition：

若需要新增 Host public method 才能完成本 slice，停止并回到 design gate。

### CLI-01-S3: Prompt command through Service assembly and Host public API

Objective：

实现 `dayu-cli prompt` 的 one-shot command，支持旧 CLI scoped 参数和当前 Host open/follow-up path。

Allowed files / modules：

- `dayu/cli/commands/prompt.py`
- `dayu/cli/host_context.py`
- `dayu/cli/output.py`
- `dayu/cli/arg_parsing.py`
- `dayu/service/entrypoint_runtime.py`，仅限 S2 helper 必要小修。
- `tests/cli/test_prompt_command.py`
- `tests/service/test_entrypoint_runtime_prompt_path.py`

Exact allowed changes：

- positional `prompt` 作为本轮 user prompt。
- 当前 `prompt.json` 的真实 required context slots 为 `fins_default_subject` 与 `base_user`：
  - `--ticker` 映射为 `context_slot_values["fins_default_subject"] = ticker_value.strip()`。
  - 未传 `--ticker` 时使用 `context_slot_values["fins_default_subject"] = "未指定具体公司"`，以保持旧 prompt 不强制 ticker 的用户可见行为。
  - `context_slot_values["base_user"]` 来自 CLI adapter 的 display user；本 WU 默认 `"本地 CLI 用户"`，未来 auth/profile 可提供人类可读显示名。不得把 `request_id`、event id、cursor 或其它 Host 内部治理 id 塞进 LLM-facing context slot。
- `--label` 生成 stable Host slot key，例如 `cli.prompt.<label>`；不得使用旧 label registry 文件。
- `--model-name` 映射为 `ServiceAssemblyOverrides.model_id`。
- 可映射执行覆盖项转换为 `ServiceRunOverrides`。
- unsupported 旧执行项报清晰错误并 exit 2。
- 输出 final answer；错误输出 Host terminal error message。
- CLI adapter 构造 `HostCallContext` 与 submit / cancel `client_request_id`，Service helper 只消费这些 public typed inputs。

Data flow：

CLI args -> `EntrypointRuntimeRequest(scene_id="prompt")` -> open Host -> ensure/create session -> Service pre-submit watcher terminal wait -> print final answer -> exit。

State transitions：

- 无 `--label`：创建或 ensure 当前 command session，turn 结束后 close Host handle。
- 有 `--label`：复用同一 slot session。
- prompt 不进入 interactive loop。

Error handling：

- prompt 为空 -> argparse exit 2。
- scene manifest 不再是实现期猜测；若未来 `prompt.json` 移除或重命名 `fins_default_subject` / `base_user`，S3 manifest 集成测试必须失败，implementation 应停止回到 plan/design，而不是注入隐式 prompt 文本。
- Host terminal failed -> exit 1。

Cancel behavior：

- Ctrl-C 在 run accepted 前：exit 130。
- Ctrl-C 在 run accepted 后：构造 `EntrypointCancelRequest`，其中 `CancelRunRequest` 最终字段为 `context=<cancel context>`、`client_request_id="dayu-cli:prompt:<cli_invocation_id>:turn-1:run-<run_id>:cancel:cli_sigint"`、`reason="cli_sigint"`、`mode=CancelMode.GRACEFUL`；调用 `Host.cancel_run(run_id, request)`，等待 terminal，exit 130。

Tests / validation：

- 参数到 Service request 的转换。
- `--label` stable slot key。
- unsupported old flags fail fast。
- mocked Host open-follow-up-terminal path，断言 watcher attach 发生在 submit 前。
- prompt fast terminal path：submit 返回前 terminal 已写入 watcher queue，命令仍输出 final answer。
- prompt outbox fallback path：watcher 无 terminal、`get_run` 已终态、outbox read 返回同 run terminal，命令仍输出 final answer。
- SIGINT after run id calls `Host.cancel_run(run_id, CancelRunRequest(...))`，断言 context、client_request_id、reason、mode 完整且重复 SIGINT 复用 cancel client_request_id。
- prompt manifest integration：使用真实 `prompt.json` 验证 `fins_default_subject` / `base_user` 均被填充。

Completion signal：

`dayu-cli prompt "..."` 在 mocked provider / mocked Host dependency 下可完整收口，并且没有 CLI 直接调用 Engine。

Stop condition：

若当前 `prompt` scene manifest 不再声明 `fins_default_subject` / `base_user`，停止并报告需要先改 scene manifest 或本计划；不得在 CLI 中注入隐式 prompt 文本绕过 `ScenePrepare`。

### CLI-01-S4: Interactive command using the same Service session semantics

Objective：

实现 `dayu-cli interactive`，复用 S2 的 Service helper 处理 session、turn、terminal observation 与 cancel。

Allowed files / modules：

- `dayu/cli/commands/interactive.py`
- `dayu/cli/host_context.py`
- `dayu/cli/output.py`
- `dayu/cli/arg_parsing.py`
- `tests/cli/test_interactive_command.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`

Exact allowed changes：

- 保留 `--label` 与 `--new-session` 互斥。
- 当前 `interactive.json` 的真实 required context slots 同样为 `fins_default_subject` 与 `base_user`：
  - S1 parser 必须为 interactive 注册 optional `--ticker`，映射为 `context_slot_values["fins_default_subject"] = ticker_value.strip()`。
  - 未传 ticker 时使用 `context_slot_values["fins_default_subject"] = "未指定具体公司"`。
  - `context_slot_values["base_user"]` 默认 `"本地 CLI 用户"`，未来可接 auth/profile display name；不得放 Host 内部 id。
- `--label` slot key 使用 `cli.interactive.<label>`。
- 无 label 时使用当前进程 session，不写旧 label registry。
- `--new-session` 调用 `create_session(bind_slot=True)`，不复用旧 session。
- 逐轮输入全部通过 `submit_entrypoint_turn_and_wait(...)`。
- 每轮 CLI adapter 都构造新的 `HostCallContext.request_id` 与 submit client_request_id；同一轮 cancel 复用该 run 的 cancel client_request_id。
- 终端 UI 只展示输入提示、assistant final answer、错误和取消状态；不复制旧 `interactive_ui.py` 的复杂渲染系统，除非当前 Host public events 已提供等价信息。

Data flow：

CLI args -> `EntrypointRuntimeRequest(scene_id="interactive")` -> open Host -> ensure/create session -> REPL -> per turn pre-submit watcher terminal wait -> print -> next turn。

State transitions：

- Idle input state。
- Run pending / running state。
- Cancel requested state。
- Terminal state returns to idle unless user exits。

Error handling：

- label 与 new-session 同时提供 -> argparse exit 2。
- Service assembly failure -> exit 1。
- 单轮 terminal fatal / non-fatal policy 固定如下：
  - `SUCCEEDED`：输出 final answer，回到输入态。
  - `FAILED`：输出 `error_message` 或 fallback 错误文案，回到输入态，exit code 暂不结束进程。
  - `CANCELLED`：输出取消状态，回到输入态；如果是用户 Ctrl-C 触发，当前 cancel 操作本身仍按 130 语义记录，但 interactive 进程继续运行。
  - `LOST`：fatal，输出 lost 诊断，退出 interactive，exit 1。
  - Host handle closed、Service assembly error、outbox projection `FAILED`、caught-up-without-match contract violation：fatal，退出 interactive，exit 1。

Cancel behavior：

- 输入态 Ctrl-D：退出 0。
- 输入态 Ctrl-C：清空当前输入或退出当前 command，按实现测试固定。
- 运行态第一次 Ctrl-C：构造 `EntrypointCancelRequest`，最终调用 `Host.cancel_run(run_id, CancelRunRequest(context=<cancel context>, client_request_id="dayu-cli:interactive:<cli_invocation_id>:turn-<n>:run-<run_id>:cancel:cli_sigint", reason="cli_sigint", mode=CancelMode.GRACEFUL))`，等待 terminal 并回到输入态。
- 运行态第二次 Ctrl-C：本地 exit 130；若已有 run id，必须已发出 cancel。

Tests / validation：

- `--label` / `--new-session` session binding。
- 两轮 follow-up 使用同一 Host session。
- 每一轮都在 submit 前 attach watcher；第二轮不得复用上一轮已关闭或已消费完的 terminal wait state。
- 每一轮 terminal / error / cancel 后 watcher `aclose()` 被调用；第二轮使用新的 queue、cursor 和去重集合。
- interactive fast terminal path：单轮 terminal 在 submit 返回前出现也能正确回到 idle。
- 运行中 SIGINT 调用完整 `CancelRunRequest`，重复 SIGINT 不重复 durable cancel。
- terminal failed / cancelled / lost 的展示与 fatal / non-fatal 策略。
- interactive manifest integration：使用真实 `interactive.json` 验证 `fins_default_subject` / `base_user` 均被填充。

Completion signal：

interactive 在 mocked Host 下完成两轮对话与运行中取消；session orchestration 没有 CLI 专用实现。

Stop condition：

若需要旧 `conv` / label registry 才能实现 label 复用，停止并改为 Host slot 方案；不得移植旧 registry。

### CLI-01-S5: Fins direct job Service boundary and direct commands

Objective：

实现 Fins direct job 的 start / poll / cancel / terminal mapping，并接入 `download`、`upload_filing`、`upload_material`、`process`、`process_filing`、`process_material`。

Allowed files / modules：

- `dayu/service/fins_direct.py`
- `dayu/cli/commands/fins.py`
- `dayu/cli/output.py`
- `dayu/cli/arg_parsing.py`
- `tests/service/test_fins_direct.py`
- `tests/cli/test_fins_commands.py`
- 现有 `tests/fins/test_fins_ingestion_runtime.py` 只可补充当前 direct command 所需 cancel cases。

Exact allowed changes：

- 新增 `FinsDirectCommandService`：
  - 构造时接收 `DefaultFinsRuntime` 或 `FinsIngestionRuntime`。
  - `start_download(...)`。
  - `start_preprocess(...)`。
  - `start_upload_filing(...)`：Service-facing convenience wrapper，不要求 runtime 有同名方法；它用显式参数构造 `FinsUploadFilingRequest(ticker=..., source_kind=SourceKind.FILING, action=..., files=..., fiscal_year=..., fiscal_period=..., amended=..., filing_date=..., report_date=..., company_name=..., ticker_aliases=..., overwrite=...)`，再调用 `FinsIngestionRuntime.start_upload(request, cancellation_token=...)`。
  - `start_upload_material(...)`：Service-facing convenience wrapper，不要求 runtime 有同名方法；它用显式参数构造 `FinsUploadMaterialRequest(ticker=..., source_kind=SourceKind.MATERIAL, action=..., files=..., form_type=..., material_name=..., document_id=..., internal_document_id=..., fiscal_year=..., fiscal_period=..., amended=..., filing_date=..., report_date=..., company_name=..., ticker_aliases=..., overwrite=...)`，再调用 `FinsIngestionRuntime.start_upload(request, cancellation_token=...)`。
  - `wait_for_terminal(job_id: str)`，按 `poll_interval_seconds` 轮询 `runtime.read_job(job_id)`。
  - `request_cancel(job_id: str)`。
- CLI 参数转换到 `FinsDirectCommandService` 的显式方法参数；下载 / 预处理可直接构造 typed request，upload typed request 必须由 `start_upload_filing(...)` / `start_upload_material(...)` wrapper 构造。转换层不直接读写 storage。
- `--infer`、`--ci` 等 unsupported flags fail fast。
- ticker CSV helper 必须产生 typed result：canonical ticker 与 aliases；aliases 只传给当前 request 支持的字段。
- `upload_*` file path 校验只做用户输入存在性和 allowlist 前置检查；业务 ingestion 仍由 Fins runtime 完成。

Data flow：

CLI args -> `FinsDirectCommandService` explicit method args -> typed Fins request -> `DefaultFinsRuntime.create(workspace_root)` / injected runtime -> ingestion runtime `start_*` or `start_upload` -> job id -> poll `read_job` -> terminal result -> CLI output。

Upload call path 固定为：

- `dayu-cli upload_filing ...` -> CLI 解析 / 文件路径前置校验 -> `FinsDirectCommandService.start_upload_filing(...)` -> `FinsUploadFilingRequest(...)` -> `runtime.start_upload(request)`。
- `dayu-cli upload_material ...` -> CLI 解析 / 文件路径前置校验 -> `FinsDirectCommandService.start_upload_material(...)` -> `FinsUploadMaterialRequest(...)` -> `runtime.start_upload(request)`。
- CLI 不直接调用 `runtime.start_upload(...)`，也不寻找不存在的 `runtime.start_upload_filing(...)` / `runtime.start_upload_material(...)`。

State transitions：

Fins job status 使用 existing status，不新增状态：

- `QUEUED` / `RUNNING` -> wait。
- `CANCELLING` -> wait terminal。
- `SUCCEEDED` -> exit 0。
- `FAILED` -> exit 1。
- `CANCELLED` -> exit 130。

Error handling：

- invalid command args -> exit 2。
- request construction failure -> exit 2 when user input invalid, exit 1 when runtime invariant fails。
- job start failure -> exit 1。
- job failed terminal -> exit 1 with job id and reason。

Cancel behavior：

- Start boundary cancellation token is not enough；CLI must keep job id and call `request_cancel(job_id)` on SIGINT。
- First SIGINT after job id：request cancel and continue polling。
- First SIGINT before job id：exit 130；no durable job to cancel。
- Second SIGINT after cancel request：exit 130 with job id printed。

Tests / validation：

- Each command maps args to correct typed request。
- upload wrapper tests assert `start_upload_filing(...)` passes a `FinsUploadFilingRequest` into `runtime.start_upload(...)` and `start_upload_material(...)` passes a `FinsUploadMaterialRequest` into `runtime.start_upload(...)`。
- Fins direct poll tests assert default `poll_interval_seconds == 1.0` and fake sleep is called only for nonterminal statuses。
- Fins direct service calls `request_cancel(job_id)` on SIGINT path。
- Terminal status exit code mapping。
- No CLI direct `dayu.fins.storage` import。
- Existing Fins ingestion runtime tests still pass。

Completion signal：

六个 direct job commands 可以在 fake ingestion runtime 下完成 start、progress、success、failure、cancel tests。

Stop condition：

若某个 command 需要当前 Fins runtime 不存在的业务 contract 才能真实执行，保留 parser 但执行时报 unsupported，并在 residual risk 里登记 owner。

### CLI-01-S6: upload_filings_from batch plan generation

Objective：

实现 `upload_filings_from` 的目录扫描与批量上传脚本生成，但不启动 ingestion job。

Allowed files / modules：

- `dayu/fins/upload_batch.py`
- `dayu/service/fins_direct.py`
- `dayu/cli/commands/fins.py`
- `tests/fins/test_upload_batch.py`
- `tests/cli/test_upload_filings_from_command.py`

Exact allowed changes：

- 在 Fins boundary 新增 typed batch plan：
  - `UploadBatchPlanRequest`
  - `UploadBatchPlanEntry`
  - `UploadBatchPlanResult`
- 支持 `--from`、`--recursive`、`--action {create,update}`、`--material-forms`、`--output` 和 metadata flags。
- Fins helper 返回结构化 command entries，不返回 shell text。
- CLI formatter 把 entries 输出为 `dayu-cli upload_filing ...` 或 `dayu-cli upload_material ...`。
- 默认输出 stdout；提供 `--output` 时写指定文件。

Data flow：

CLI args -> `UploadBatchPlanRequest` -> Fins batch helper scans local source dir -> structured entries -> CLI output formatter。

State transitions：

无 durable job state；只处理本地 plan generation。

Error handling：

- source dir 不存在 -> exit 2。
- 无可识别文件 -> exit 1，并输出原因。
- 写 output 失败 -> exit 1。

Cancel behavior：

- 目录扫描阶段响应 SIGINT，exit 130；无 Fins job 可 cancel。

Tests / validation：

- recursive / non-recursive 扫描。
- filing / material 识别。
- output script command quoting。
- 不导入 Host / Engine。
- 不直接读取 Fins storage。

Completion signal：

`upload_filings_from` 在临时目录 fixture 下生成稳定脚本，命令行与 old CLI command names 对齐，prefix 使用 `dayu-cli`。

Stop condition：

若旧识别规则无法从当前 Fins domain 自洽迁移，保留命令但降级为 explicit file list 生成，并登记 residual risk。

### CLI-01-S7: init current-schema workspace bootstrap and docs/tests closure

Objective：

实现 `dayu-cli init`，按当前 config schema 初始化 workspace，并完成 README / tests / pyright 闭环。

Allowed files / modules：

- `dayu/cli/commands/init.py`
- `dayu/cli/arg_parsing.py`
- `tests/cli/test_init_command.py`
- `dayu/config/README.md`，仅在实际修改 `dayu/config` 或 config init 行为属于该 README 当前职责时更新。
- `dayu/fins/README.md`，仅在新增 `dayu/fins/upload_batch.py` 时更新。
- `dayu/service/README.md`，若新增 Service helper，更新当前实现边界。
- `dayu/README.md`，若 implementation 触及跨包边界说明，按其约束更新。
- `tests/README.md`，若新增 CLI test 分类或测试命令需要记录，按其约束更新。

Exact allowed changes：

- `init --base/-b` 创建 workspace root。
- 创建 `workspace/config` 并复制当前 `dayu/config` 下的 required config files 与 prompts。
- `--overwrite` 允许覆盖已有 config files。
- `--reset` 使用硬编码删除白名单，禁止 glob / pattern 删除，禁止删除白名单外任何路径：
  - 允许删除 `<project_root>/workspace/config/`。
  - 允许删除当前默认 Host / UI runtime 目录：`<project_root>/workspace/.dayu/host/`、`<project_root>/workspace/.dayu/artifacts/`、`<project_root>/workspace/.dayu/web_tools_storage_states/`。
  - 不允许删除整个 `<project_root>/workspace/.dayu/`，因为其中可能包含本 WU 未拥有的 runtime 文件；尤其不删除 `<project_root>/workspace/.dayu/runtime/runtime_lanes.sqlite3`。
  - 不允许删除 `<project_root>/.dayu/`，其中可能包含 Fins ingestion jobs、SEC cache / throttle、Fins storage batch / backup / lock 状态。
  - 不允许删除 `<project_root>/workspace/fins/`、`<project_root>/fins/`、用户 upload 源目录、`upload_filings_from --from` 目录、用户输出目录或任何不在白名单内的普通文件。
  - 白名单路径 resolve 后必须仍位于 `<project_root>/workspace/` 下；若路径是 symlink 或 resolve 后逃逸，fail fast，exit 2，不递归删除。
  - 若白名单路径不存在，跳过该路径；不存在不算错误。
- 不生成旧 `llm_models.json` / `run.json`。
- 不执行旧 workspace migrations。
- 若 provider interactive 进入 scope，只修改当前 `models.json` typed model records 与 env 提示；不把 API key 写入 config 明文。

Data flow：

CLI args -> resolve package config root -> copy config assets -> optional current-schema model selection -> summary output。

State transitions：

Filesystem bootstrap only；不打开 Host，不创建 Fins job。

Error handling：

- workspace 路径非法 -> exit 2。
- 目标文件存在且未 `--overwrite` -> exit 1 with actionable message。
- reset 白名单外路径、symlink 逃逸或路径 containment 校验失败 -> exit 2，不执行任何删除。
- copy failure -> exit 1。

Cancel behavior：

- SIGINT 中断 init，exit 130。
- 为避免半初始化误判成功，copy 应使用 temp path + atomic replace；若中断，输出可能残留路径。

Tests / validation：

- 空 workspace init。
- existing files without overwrite。
- overwrite behavior。
- reset 只删除白名单路径；断言 `<project_root>/.dayu/fins_ingestion/jobs/`、`<project_root>/.dayu/sec_cache/`、`<project_root>/workspace/fins/`、`runtime_lanes.sqlite3` 和用户普通文件 fixture 均保留。
- generated workspace config passes `ConfigLoader.load(workspace_config_dir=...)`。

Completion signal：

`dayu-cli init --base <tmp>` 生成当前 schema workspace，随后 `ConfigLoader` 能加载该 overlay。

Stop condition：

若要提供旧 init 的 provider catalog 体验需要改当前 config schema，停止并回到 schema/design gate。

## Testing Plan

### 常规测试

- `source .venv/bin/activate && pytest tests/cli tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime.py tests/service/test_fins_direct.py -q`
- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/host/test_wait_adapter_polling.py -q`
- `source .venv/bin/activate && pyright`

### Contract / unit coverage

- Parser help contract：top-level help、每个 scoped command help、excluded command invalid choice。
- Service entrypoint contract：explicit config overlay fail-fast / default overlay missing fallback、scene prepare、tool discovery、Host open options、submit follow-up request fields、per-run overrides。
- Host context / cancel contract：`HostCallContext` exact fields、`OperationContext` fields、`CreateSessionRequest` / `SubmitFollowupRequest` / `CancelRunRequest` client_request_id、`CancelMode.GRACEFUL`、重复 cancel 幂等 key。
- Host open/follow-up path：使用 mocked Host public Protocol，验证 `watch_session_events` 早于 `submit_followup`、fast terminal 不丢、`get_run` / `read_outbox_terminal_items` 兜底、outbox cursor / `seen_terminal_event_ids` / `projection_status` / `has_more` 和 terminal mapping。
- Interactive path：two-turn same session、label slot、新 session绑定、每轮 pre-submit watcher、watcher close/aclose、多轮 event_sequence 去重、运行中 cancel、`FAILED` / `CANCELLED` / `LOST` fatal policy。
- Fins direct commands：每个 command typed request mapping、upload wrapper 到 `runtime.start_upload(...)` union API、terminal status exit code、默认 1.0 秒 poll interval、SIGINT to `request_cancel(job_id)`。
- `upload_filings_from`：目录扫描、脚本生成、quoting、无 job start。
- `init`：当前 schema workspace bootstrap，reset deletion whitelist，生成 config 可被 `ConfigLoader` 加载。

### Smoke / external dependency separation

不把网络、真实 SEC 下载、真实 LLM provider 放入常规测试。单独 smoke：

- `source .venv/bin/activate && dayu-cli --help`
- `source .venv/bin/activate && dayu-cli prompt --help`
- `source .venv/bin/activate && dayu-cli interactive --help`
- `source .venv/bin/activate && dayu-cli download --help`
- 使用 fake provider / fake Host 或现有 Host public smoke，验证 one-shot prompt path。
- 使用 fake Fins ingestion runtime，验证 long job cancel path。
- 真实 SEC / provider smoke 只作为手动或外部依赖 smoke，失败不得阻塞常规 unit suite，除非环境变量显式启用。

### Coverage target

- 新增或修改的非 `dayu/render/`、非 `utils/` 单文件目标覆盖率 >= 80%。
- 若某个文件主要是 argparse declaration，覆盖以 help snapshot / parse tests 计入。

## README / Doc Decision

本 plan gate 不修改 README。后续 implementation gate 按 AGENTS.md 触发：

- 修改 `dayu/host/`：检查 `dayu/host/README.md`；本计划不预期修改 Host 包。
- 修改 `dayu/engine/`：检查 `dayu/engine/README.md`；本计划不预期修改 Engine 包。
- 修改 `dayu/fins/`：若新增 `dayu/fins/upload_batch.py`，检查并按需更新 `dayu/fins/README.md`。
- 修改 `dayu/config/`：若 init 需要调整 config defaults，先读 `dayu/config/README.md` 约束并按需更新；本计划优先不改 config defaults。
- 修改 `tests/`：检查并按需更新 `tests/README.md`。
- 涉及 `UI / Service / Host / Engine` 边界变化：检查并按需更新 `dayu/README.md`。
- 新增 `dayu/service` public helper：虽然 AGENTS.md 没有单列 service trigger，也应按当前 `dayu/service/README.md` 的实际职责更新已实现边界，不能写未来计划。

本 WU 的工作计划 artifact 不属于用户手册，不应复制进 README。

## Risks / Open Questions / Residual Risks

### Blocking open questions

当前没有阻塞 plan 自洽的问题。若 implementation 发现需要改 Host / Engine public design 才能满足 prompt / interactive 取消或 terminal observation，必须停止并回到 design gate。

### Residual risks

| Risk | Impact | Owner / destination | Planned handling |
| --- | --- | --- | --- |
| 旧 `--infer` alias inference 当前无 approved Fins boundary。 | download / upload 与旧 CLI 行为不完全一致。 | Fins owner；GitHub Issue 83 的 intentional deviation，后续单独 Fins alias inference WU。 | WU-CLI-01 解析保留但执行时报 unsupported，不静默忽略。 |
| 旧 `--ci` process snapshot 当前无公共 contract。 | process 系列与旧 CLI 不完全一致。 | Fins / tooling owner；后续 CI snapshot contract WU。 | WU-CLI-01 解析保留但执行时报 unsupported。 |
| 旧 debug / trace / duplicate governance flags 无当前 Host public per-run contract。 | 部分 power-user flags 不可用。 | Host / Service owner；后续 observability / per-run governance WU。 | 不塞 raw payload；unsupported fail fast。 |
| `upload_filings_from` 的旧文件识别规则可能依赖旧 Fins helper。 | 批量脚本生成 parity 风险。 | Fins owner；CLI-01-S6。 | 在 Fins boundary 建 typed batch plan helper；若无法自洽，降级并登记 deviation。 |
| `--thinking/--no-thinking` 在当前模型 schema 中不是独立布尔开关。 | 旧 CLI 模型选择体验不完全一致。 | Config / Service owner；后续 model profile UX WU。 | 只在当前 model/hint 可明确映射时支持，否则 unsupported。 |
| `init --reset` 具有潜在数据破坏风险。 | 误删用户财报数据。 | CLI owner；CLI-01-S7。 | reset 只删除硬编码白名单：`workspace/config/`、`workspace/.dayu/host/`、`workspace/.dayu/artifacts/`、`workspace/.dayu/web_tools_storage_states/`；不删除 `workspace/.dayu/runtime/runtime_lanes.sqlite3`、`<project_root>/.dayu/`、Fins data 或用户文件。 |
| Fins job cancel 是协作式，部分长事务可能不及时检查 `request_cancel`。 | Ctrl-C 后 terminal 可能延迟。 | Fins runtime owner；现有 ingestion runtime tests 和后续 adapter hardening。 | CLI 第一次 SIGINT 发 durable cancel，第二次 SIGINT 允许本地退出并打印 job id。 |

## 为什么没有过度设计

- 没有引入新的 workflow engine、Host 管理面、UI framework 或跨入口 daemon。
- 没有改 Host / Engine 核心状态机；prompt / interactive 只使用现有 public API。
- 新增 Service helper 只覆盖本 WU 必须共享的会话和 Fins job语义，且不含 argparse、stdout/stderr、终端渲染。
- Fins direct command 复用现有 ingestion runtime、job store、wait adapter cancel 真源，不新建并行 job system。
- 旧 CLI 中无法映射到当前 typed contract 的参数 fail fast，不为表面兼容引入 raw extra payload 或旧 schema 兼容层。
- `upload_filings_from` 的脚本生成被限制在 Fins typed batch plan + CLI formatter，不与 ingestion job 执行耦合。

## Completion Report Format

后续 implementation gate 完成时，最终报告必须包含：

- Artifact / PR path。
- 修改了什么：按 CLI、Service、Fins、Runtime、Tests、Docs 分类。
- 旧 CLI command surface 对齐结果：新增命令、参数、help、exit code、intentional deviation。
- 验证了什么：列出 pytest、pyright、help smoke、Host open-follow-up smoke、Fins cancel smoke。
- 未验证什么：网络 / 真实 LLM / 真实 SEC 等外部依赖 smoke 是否跳过及原因。
- README 决策：检查了哪些 README，修改了哪些，没有修改的原因。
- Residual risks：每项 owner / destination。
- 是否修改了 scope 外文件。
