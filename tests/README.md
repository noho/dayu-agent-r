# 测试手册

本文件只记录当前 `tests/` 下已经存在的测试分层、运行方式与维护约定。测试事实以当前代码和测试目录为准；新增测试层级后，应同步更新本文件。

## 默认环境

项目默认测试环境为 Python 3.11。运行测试或类型检查前，先激活仓库内虚拟环境：

```bash
source .venv/bin/activate
```

当前类型检查配置覆盖 `dayu/`、`tests/`、`utils/`，并排除 `workspace/`、缓存目录、隐藏目录与 `.venv/`。

`tests/conftest.py` 提供全局测试隔离夹具：每个测试结束后恢复 `dayu` namespace logger 的 handler、level、
propagate 与 disabled 状态，并关闭本测试新增的 logger handler，避免 CLI 入口日志装配把 pytest 捕获流泄漏给后续测试。

## 常用命令

运行当前契约、CLI、Documents、Fins、Tools、Host、Runtime、Service 与 Engine 测试：

```bash
pytest tests/contracts tests/cli tests/documents tests/fins tests/tools tests/host tests/runtime tests/service tests/engine -q
```

运行类型检查：

```bash
python -m pyright dayu/ tests/ utils/
```

默认 pytest 配置会排除 `stress` marker，因此常规命令不会运行 Host production stress suite。显式运行 stress suite 时需要覆盖默认 `addopts`：

```bash
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
```

也可以按目录或文件收窄测试范围：

```bash
pytest tests/contracts -q
pytest tests/cli -q
pytest tests/documents -q
pytest tests/fins -q
pytest tests/tools -q
pytest tests/host -q
pytest tests/host/test_tooling_options.py tests/host/test_package_exports.py tests/host/test_import_boundary.py -q
pytest tests/host/test_durable_schema.py tests/host/test_event_log_store.py -q
pytest tests/host/test_durable_connection.py tests/host/test_durable_transaction.py -q
pytest tests/host/test_durable_concurrency_matrix.py tests/host/test_idempotency_store.py tests/host/test_projection_checkpoint.py tests/host/test_memory_projection.py -q
pytest tests/host/test_event_log_multiprocess.py tests/host/test_admission_multiprocess.py tests/host/test_host_instance_liveness.py -q
pytest tests/host/test_durable_schema.py tests/host/test_projection_checkpoint.py tests/host/test_projection_runner.py tests/host/test_projection_read_model.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_admission_queue.py tests/host/test_dispatch_scheduler.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_resolve_wait_command.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
pytest tests/host/test_payload_store.py tests/host/test_artifact_store.py tests/host/test_host_instance_liveness.py -q
pytest tests/host/test_session_lifecycle.py tests/host/test_run_attempt_transitions.py -q
pytest tests/host/test_admission_queue.py tests/host/test_run_attempt_transitions.py -q
pytest tests/host/test_command_handle.py tests/host/test_public_session_api.py tests/host/test_session_lifecycle.py -q
pytest tests/host/test_recovery_multiprocess.py tests/host/test_admission_multiprocess.py tests/runtime/test_lane.py -q
pytest tests/host/test_admission_multiprocess.py tests/host -q
pytest tests/host/test_dispatch_scheduler.py tests/host/test_local_proxy_engine_ingest.py tests/host/test_command_handle.py tests/runtime/test_lane.py -q
pytest tests/host/test_phase5_local_execution_integration.py -q
pytest tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_effective_bundle.py tests/host/test_phase6_toolruntime_integration.py -q
pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_tool_trace_projection.py tests/host/test_dispatch_scheduler.py tests/host/test_tooling_options.py -q
pytest tests/host/test_toolruntime_executor.py tests/host/test_phase6_toolruntime_integration.py -q
pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_engine_ingest_mapping.py -q
pytest tests/host/test_resolve_wait_command.py tests/host/test_run_attempt_transitions.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_phase7_waiting_integration.py -q
pytest tests/host/test_wait_cancel_late_result.py tests/host/test_wait_adapter_polling.py tests/host/test_engine_ingest_mapping.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_run_api.py -q
pytest tests/host/test_submit_followup_public_contract.py tests/host/test_per_run_tool_selection.py tests/host/test_effective_execution_config.py -q
pytest tests/host/test_watch_session_events.py tests/host/test_public_host_event.py -q
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
pytest tests/host/test_context_budget.py tests/host/test_compaction_contract.py tests/host/test_compact_artifact_store.py -q
pytest tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q
pytest tests/host/test_context_compact_events.py -q
pytest tests/runtime -q
pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q
pytest tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py -q
pytest tests/service -q
pytest tests/engine -q
pytest tests/engine/contracts -q
pytest tests/engine/runners/openai/test_event_flow_ordering.py -q
pytest tests/engine/test_smoke_async_agent_providers.py -q
```

## 当前测试分层

### `tests/cli/`

CLI UI adapter 测试，当前覆盖 `dayu.cli` 的 parser factory、scoped command help、未纳入旧命令的 unknown command
用法错误、尚未实现命令的 not-implemented 退出、`KeyboardInterrupt` 到 130 的映射、全局参数位置，以及 `init`
对 current schema workspace config / prompts 的 bootstrap、existing file / overwrite、reset 硬编码白名单、symlink
escape fail-fast、旧配置文件不生成、生成配置可由 `ConfigLoader` 加载和复制阶段 SIGINT 130；
`python -m dayu.cli --help` 入口，并覆盖 CLI main 把默认 log level、`--debug` / `--verbose` / `--quiet` / `--log-level`
解析结果和 stderr 诊断流交给 `dayu.runtime.log.set_level_from_flags(...)` 装配日志。`prompt` 命令测试覆盖 CLI 参数到 Service entrypoint request 的转换、stable
Host slot key、unsupported 旧执行参数 fail fast、真实 `prompt.json` required context slots、mock Host public
open/follow-up terminal path、fast terminal、outbox fallback、FAILED terminal 输出和 SIGINT 后 Host public cancel request；
`interactive` 命令测试覆盖默认 fresh anonymous Session、label session binding、`--new-session` 用法错误、真实
`interactive.json` required context slots、两轮同 Session、每轮独立 watcher attach/close、fast terminal、FAILED / CANCELLED 继续输入、LOST fatal、运行态 SIGINT cancel、
第二次 SIGINT 本地 130、显式 config 错误、unsupported 旧执行参数 fail fast，以及 `--verbose` / `--debug` 诊断不污染 stdout 用户结果通道。Session command 测试覆盖 CLI label kind 到 Host public slot ref 的映射、anonymous / prompt / interactive / other slot 展示身份反解、含点号 label 不拆分、`session list` public Host 调用与 open / closed 输出、`session purge` 的 `--yes` 门禁、按 session id 清理、按 label 先 list 解析 slot 再 purge、Host `INVALID_STATE` 前置条件错误、label purge TOCTOU 错误上下文、成功输出、resume parser shape 与 S4 not-implemented 执行边界，并确认 Session list / purge 输出不展示删除计数 digest 或内部治理字段。Fins direct command 测试覆盖
`download`、`upload_filing`、`upload_material`、`process`、`process_filing`、`process_material` 的 CLI 参数到
`FinsDirectCommandService` 显式方法参数转换、Service event stream 消费、progress / terminal summary
stdout/stderr 投影、CLI 输出中绝对路径可见但受长度控制、upload file 存在性与 allowlist 前置校验、`--infer` / `--ci` fail fast、
默认日志不污染 progress 输出、`--verbose` 执行骨架日志与 `--debug` event detail 诊断写入 stderr 且 stdout 保持用户 UI、
Service stream / cancel failure 向上传播且 CLI 不重复记录同一 ERROR、
`upload_filings_from` 的本地目录扫描、filing / material 识别、脚本 quoting、`--output` 写入、错误码、扫描期
SIGINT 130、确认不启动 live event stream、terminal exit mapping、SIGINT 到 operation-scoped async cancellation、
cancel race 收口、第二次 SIGINT 本地 130，以及 CLI 不直接 import `dayu.fins.storage`。
CLI 测试不得启动真实 Host / Fins 业务路径；涉及 Host 状态机时使用 Service helper 与 mocked Host public API。

### `tests/runtime/`

运行时基础设施测试，覆盖 `dayu.runtime` 的层中立边界、取消 helper、diagnostic 文本 helper、digest helper 与日志装配：

- import boundary：阻止 runtime 反向依赖 Engine、Host、Service、UI、Fins 或引入运行期 HTTP 客户端，并显式确认
  `config_loader.py`、`location.py`、`scene_prepare.py`、`tools_discovery.py`、`assembly.py` 与 `tool_truncation.py` 被边界扫描覆盖。
- cancellation：覆盖取消等待 helper 的完成、取消与异常传播语义。
- lane：覆盖 cross-process named semaphore / capacity guard 的配置校验、独立 SQLite runtime lane DB schema、acquire /
  heartbeat / release、timeout、协作式 cancellation、`Task.cancel()` 透传、controller close、跨进程 capacity invariant、
  close/acquire 并发下 pending acquire 唤醒、新 claim 拒绝、active claim count invariant、shielded claim / refresh / release
  遇到外层取消时的收口一致性、外层取消 cleanup 有界等待与 late result 观测、TTL 时间真源不受 monotonic elapsed 前跳影响、release 后其它进程 acquire，以及 crash 后 TTL stale cleanup eventual acquire；测试不断言
  FIFO、公平性或 Host dispatch 集成。
- filelock：覆盖同步 file lock wrapper 的 parent directory 创建策略、禁用创建时的结构化错误、context manager 正常与异常路径 release、release 幂等、non-blocking timeout 包装，以及第三方 `filelock` import 只能出现在 `dayu.runtime.filelock` 的边界。
- diagnostic text：覆盖层中立 diagnostic 文本中的 Bearer / API key / authorization / password / secret / token 敏感值检测、局部 value 脱敏、marker 字面替换、有界截断、空字符串 no-op、普通 token/header 诊断不误判，以及先脱敏再截断不泄漏原值。
- digest：覆盖层中立 UTF-8 文本 digest 的稳定 `sha256:<hex>` 输出形态。
- logging：验证 `dayu.runtime.log` 的 logger 装配、默认 stderr 诊断流、显式 stream override、CLI 风格级别解析、层中立 verbose / bounded payload key helper、`VERBOSE` / `CRITICAL` 级别契约，并验证 `dayu.runtime.log_levels` 只提供公共日志级别常量、不注册 stdlib logging level。
- config loader：覆盖 `models.json`、`execution_profiles.json`、`host_runtime.json`、`runtime_lanes.json`、`tool_discovery.json` 的 typed view 加载、workspace 同 id 整条替换、合法单继承链、missing / self / circular / multi / invalid `extends` 错误路径、catalog record 内重复 id 字段 fail fast、execution profile 上下文窗口分档校验、工具重复治理 decision allowlist、旧 execution profile 字段与旧 runner hint `max_tokens` fail fast、host runtime lane 引用校验和旧配置文件不读取。
- runtime location：覆盖 `workspace/config` 存在与不存在时的 `config_overlay_dir`，显式 config overlay 目录存在 / 缺失 / 非目录边界，workspace prompt assets 优先级，以及包内 prompt / manifest 默认资产缺失时 fail fast。
- tool call projection：覆盖 current `ToolCallable` 共享参数投影与 outcome 构造 helper，包括 schema default、类型收窄、unknown / missing / enum / range / array item 参数失败、固定 `invalid_argument` failure、completed / failed outcome metadata，以及 Host cancellation token 对应的 `ToolCancelledOutcome(host_cancelled)`。
- scene prepare：覆盖单 scene 装配、system prompt 输出、fragment refs / source refs / digest、required context slot、未知 / 非字符串 placeholder、双花括号字面量保留、单继承、可选或继承的 model hints、旧 `conversation` / 泛化 `runtime` / 旧 model 字段 fail fast、typed agent policy override、fragment id / order 冲突、fragment path containment、missing required fragment fail-closed，以及 `all` / `none` / `select` 工具选择的 names、tags、并集、未知工具和空匹配语义。
- tools discovery：覆盖显式 import path / package entry point provider 解析、禁用 provider 跳过、provider identity / source refs / 空工具输出 fail-fast、重复 provider / 工具名、reserved framework tool name 防线，以及 source refs 内容摘要规范化。
- assembly helpers：覆盖 runtime-neutral 模型 / runner option hint 选择、typed allowlist override 解析、Agent policy 字段级优先级合并、工具截断 policy 默认值补齐，以及 helper 返回值不构造 Host / Engine typed object；弱类型守卫显式确认这些 Phase 12 runtime helper 文件被扫描；`test_smoke_host_public_multiturn_assembly.py` 覆盖 Host public multiturn smoke 通过正式 Service assembly helper、内置 `manual-smoke` provider、workspace overlay provider、默认 fresh session slot、duplicate governance diagnostics 和 compact pressure 估算的成功路径；`test_smoke_host_public_conversation_memory_scenarios_assembly.py` 覆盖 Host public conversation memory 场景 smoke 的 CLI suite 解析、mock finance tool 装配、tool selection、pressure 文本和 slot key 语义。
- scene asset migration：覆盖迁移后的真实 scene manifest 可被 `ScenePrepare` 装配，直接 fragment 引用可加载，旧
  `max_iterations` 落入新 `agent_policy` 且不迁移工具超时，base prompt 不混入未裁决占位段，并确认未迁移
  tasks、contract 文件、workflow 产物与未引用模板。

### `tests/service/`

Service composition 测试，覆盖 `dayu.service` 在 Host 外部把 runtime typed config、locations、工具发现、prepared scene、显式 override 与 env/secret mapping 映射为 Host public typed inputs：

- host assembly：覆盖 `host_runtime.json` 的 SQLite write retry、payload inline threshold、worker startup timeout 等 construction tuning 被映射进 `OpenHostOptions`，execution profile 的工具重复治理 policy 被映射进 `HostToolingOptions`，provider secret 占位符在 Service helper 中解析，prompt asset path / 工具发现 source refs / provider location 边界 fail-fast，compactor scene 必填 AgentPolicy 字段校验，per-run helper 直接使用 `PreparedSceneInputs.system_prompt` 生成 `SubmitFollowupRequest`，以及 `ServiceRunOverrides` 到完整 `RunnerCallOptions` / `AgentPolicy` 的 typed override 合并。
- entrypoint runtime：覆盖 reusable Agent entrypoint Service boundary 的 runtime 准备、Session ensure/create、session helper 参数校验、submit 前 watcher attach、fast terminal race、无关 terminal 过滤、watcher failure 诊断后 outbox fallback、`get_run` + outbox fallback、`OutboxTerminalCursor` / `seen_terminal_event_ids` / `limit=50`、`CAUGHT_UP` 分页、`LAGGED` 重试、`FAILED` 与 caught-up-without-match 错误、watcher close、cancel 已终态跳过 `cancel_run(...)`、cancel 与终态竞争失败后继续 public terminal fallback，以及 `CancelRunRequest(context, client_request_id, reason, mode)` 构造；interactive path 覆盖真实 `interactive.json` required slots 和连续两轮独立 terminal wait state。
- Fins direct：覆盖 reusable Fins direct Service boundary 的 download / preprocess typed request 构造、upload wrapper 到 `FinsIngestionRuntime.upload(...)` union API、runtime `AsyncIterator[FinsEvent]` pass-through、progress / result contract、failure result pass-through、runtime stream exception 透传、stream 正常结束但缺少 result 时合成 failure result、重复 result fail fast、task cancellation 关闭 runtime stream、Service 不暴露 job handle / job event / `request_cancel` direct API，以及 direct event leakage guard。
- Fins awaiting assembly：覆盖 Service 基于启用 provider 的显式 provider id、import path、source id 与 provider config 识别 Fins download / preprocess / upload awaiting providers，为 `HostToolingOptions` 绑定 wait adapter registry，并在 workspace root 不一致或重复 wait binding 时于 `open_host` 前 fail fast。
- import boundary / weak typing guard：阻止 Service 导入 Config、UI 或 Fins 非 assembly 边界；当前只允许 Service composition helper 导入 `dayu.fins.ingestion` 装配 Fins wait adapter，以及 `dayu.service.fins_direct` 导入 Fins runtime / request / enum / direct event public boundary，并通过 AST 扫描禁止 `Any`、`object`、无类型签名与裸容器注解进入 Service 源码。

### `tests/contracts/`

公共协作契约测试，覆盖 `dayu.contracts` 的稳定边界：

- package exports：锁定包根 `__all__` 白名单，阻止未承诺符号泄漏。
- import boundary：阻止公共契约层反向依赖 Engine、Host、runtime implementation、Service、UI、Fins 或运行期 HTTP 客户端，
  并显式确认公共 source ref 契约模块被边界扫描覆盖。
- weak typing guard：通过 AST 扫描阻止 `Any`、`object`、无类型签名与裸容器注解进入公共契约源码。
- ToolExecutionOutcome / ToolResult / ToolCall 等契约测试：覆盖工具调用 provider state、工具结果信封、工具执行 outcome 封闭联合与穷尽匹配、工具等待时间字段时区边界、工具参数 schema key 边界和截断策略 limit key 映射穷尽性。
- tool declaration：覆盖最小 `@tool(..., truncate=ToolTruncateSpec(...))` 声明能力，确认 `ToolDefinition` / `ToolBundle` 只投影 `ToolSchema` 给 Engine，校验展示名非空，默认拒绝调用方直接构造空 `ToolBundle`，并覆盖框架 no-tool 路径使用的类型真实空 bundle。

### `tests/documents/`

共享文档基础测试，覆盖 `dayu.documents` 的层中立边界与轻量处理器 fixture：

- import boundary：阻止 `dayu.documents` 反向依赖 Engine、Host、Service、UI、Fins 或具体工具实现，并确认 Docling runtime 与 processors 子包被边界扫描覆盖。
- processors：使用确定性 fixture 覆盖 Markdown、HTML 与 Docling JSON 处理器的章节提取、表格读取与搜索片段输出。

### `tests/tools/`

业务工具与 provider 测试，当前覆盖原生 Doc tools provider、Web tools provider 与 combined tools acceptance：

- doc tools provider：覆盖 `dayu.tools.doc_provider` 通过当前 `ToolsDiscovery` 暴露五个原生 Doc tools、启用但缺少 `allowed_paths` 时 fail closed、显式路径白名单拒绝、路径参数投影为绝对路径、路径验证失败不进入业务函数体、current success / failure / cancellation outcome 投影、Markdown / Docling JSON 章节列表 / 搜索 / 章节读取、current `ToolTruncateSpec` 暴露、provider 级串行策略，以及 current ToolRuntime accept barrier 集成。
- web tools provider：覆盖 `dayu.tools.web` 通过当前 `ToolsDiscovery` 暴露原生 `search_web` 与 `fetch_web_page`、默认拒绝 private / local URL 且显式配置后才允许、搜索 optional 参数与 provider config 闭包投影、fetch truncate config 与 Playwright fallback channel / storage state config 投影、非法 URL 类型进入 Web 逻辑前失败、current success / failure / cancellation outcome 投影、current `ToolTruncateSpec` 暴露、provider 级串行策略，以及基于 AST import 解析确认未导入 OLD registry / truncation / `fetch_more` / UI。
- combined tools acceptance：使用确定性 workspace config 同时启用 Doc、Fins 与 Web providers，覆盖单一 `ToolBundle` 聚合、reserved `fetch_more` 防线、current `ToolTruncateSpec` 暴露、current ToolRuntime 注入并拥有 framework `fetch_more`、Service assembly 将 effective bundle 传入 Host、三类 provider 代表工具通过 ToolRuntime accept barrier 执行、代表性失败投影为 current outcome、ScenePrepare 可按 `doc` / `fins` / `web` tags 选择工具，以及 Web provider 串行策略在并发 callable 下生效。

`tests/tools/fixtures/documents/` 存放工具 provider 测试使用的确定性文档 fixture。当前包含 Markdown 与 Docling JSON 样本，测试应复制到临时目录后通过 provider 白名单访问，不直接把 fixture 根作为隐式生产路径。

`tests/tools/web/` 的 Web provider 测试必须保持 deterministic：搜索 provider、requests 主路径和 Playwright fallback 都通过 monkeypatch / fixture 替身控制，不做 live network 请求。
Web live smoke 位于 `utils/smoke_web_ci.py`，不在默认 pytest 中运行；直接运行该脚本会启动本地 fixture server，依次覆盖 HTML requests/fetch、PDF Docling conversion、client-rendered browser fallback 与 local assembly config hard gate；local assembly config case 通过完整 `ConfigLoader.load()`、`assemble_effective_tool_provider_configs()`、`discover_service_tools()` 与 `ToolDefinition.callable` 验证 Web overlay config 和 `truncate_max_chars`。默认还会从 `utils/web_ci_urls.jsonl` 采样 2 个 external URL 作为 diagnostic-only 输入，并运行 `auto` / `tavily` / `serper` / `duckduckgo` 四个 `search_web` provider diagnostic-only cases；运行时会打印 `SMOKE ...` UI 摘要行并按 `--log-level` 输出诊断日志，默认日志级别为 `debug`；传 `--external-limit 0` 可跳过外部 URL fetch，但 search provider diagnostics 仍默认运行。`tests/tools/web/test_smoke_web_ci.py` 只覆盖 smoke 判定、summary contract、默认 case matrix、UI/log 输出、typed `search_cases` 与 diagnostic-only 边界。

### `tests/fins/`

财报仓储、Fins read tools provider、Fins ingestion awaiting providers、ingestion runtime 与 SEC / CN / HK download/upload pipeline 测试，覆盖 `dayu.fins.storage` 文件系统仓储协议实现、确定性财报 fixture 的 list/read、`dayu.fins.tools.provider` 通过当前 `ToolsDiscovery` 暴露带 `fins` tag 的 read tools、`include_read_tools=false` 返回空工具集且不解析 workspace root、read provider 只暴露 read tools、`list_documents` 与 `search_document` 通过当前 ToolRuntime accept path 执行、数组 / 标量参数投影、current success / failure outcome 投影、current `ToolTruncateSpec` 暴露、workspace overlay 独立启用 read / download / preprocess / upload providers、download / preprocess / upload 独立 provider discovery、upload provider 空 `allowed_upload_roots` 返回空工具集且非法路径 fail-fast、awaiting callable 的 `EXTERNAL_JOB` outcome、awaiting callable 启动前观察 cancellation token 并返回 cancelled outcome、upload 路径越界、空文件与 delete 带 files 在 observation start 前失败、Fins wait adapter registry binding、poll adapter 的 observation terminal / corrupt token / missing handle / transient unavailable bounded retry 映射、abandon wait 请求 observation cancellation 与 cleanup、参数错误到 current failure outcome、SEC downloader 的无网络 HTTP/解析/限流 helper、SEC pipeline 的 skip / overwrite / cache / 6-K / SC13 / rejection artifact / stream 语义、CNInfo / HKEXNews downloader 的无网络 HTTP/解析/候选筛选/PDF 校验语义、CN/HK pipeline 的 source/blob commit、PDF gate、fast skip、独立季度缺失 skipped、runtime CN/HK auto adapter 语义、DoclingUploadService 的 create/update/delete/skip/overwrite、SEC/CN upload stream 的 filing/material id 与 source/blob 写入、DefaultFinsRuntime production upload runner 的 SEC/CN direct runtime stream 终态，以及基于 AST import 解析的 Fins / Engine / runtime import boundary。

`tests/fins/test_fins_ingestion_tools.py` 覆盖 `dayu.fins.tools.download_provider`、`dayu.fins.tools.preprocess_provider` 与 `dayu.fins.tools.upload_provider` 的独立 ToolsDiscovery provider report、独立 provider id / spec id / tool name、download / preprocess / upload 工具 schema 不暴露 Host 内部治理字段、工具调用注册 lightweight observation handle 后返回 `ToolAwaitingOutcome(EXTERNAL_JOB)`、启动前 cancellation token 已取消时返回 `ToolCancelledOutcome` 且不注册 observation、upload provider 缺少 `allowed_upload_roots` 时返回空工具集、非法 upload allowlist fail fast、upload 路径越界、空文件与 delete 带 files 在 observation start 前返回失败、Fins wait adapter registry 对稳定工具名的绑定与重复 binding fail fast、poll adapter 对 succeeded / failed / cancelled / pending / corrupt token / missing handle / transient unavailable 的 Host wait outcome 映射、abandon wait 请求 observation cancellation 与 cleanup，以及 provider 创建的不同 runtime 实例通过同一 workspace 派生 runtime 能力。本文件还覆盖 lightweight observation handle contract：resume token 只承载 opaque handle id、corrupt token / missing process-local observation source 分类为 LOST、observation status 到 wait resolution 的中立映射固定、snapshot terminal / retry-after 字段组合校验，以及禁止 handle / message 暴露 job、sequence、cursor 或 storage path。

`tests/fins/test_fins_ingestion_runtime.py` 覆盖 workspace-scoped ingestion runtime：cross-runtime shared workspace job store、legacy download / preprocess / upload queued job persistence、ticker normalization、DefaultFinsRuntime 为 US 的 `sec` / `auto`、CN 的 `cninfo` / `auto`、HK 的 `hkexnews` / `auto` 装配 production download adapter，并为 SEC/CN direct runtime upload stream 装配 production upload runner、legacy download / preprocess / upload 在 durable create 后、executor submit 前观察 cancellation token 并标记 job cancelled 且不提交后台操作、direct download / upload stream 产出 `PROGRESS` 与唯一 `RESULT`、direct stream 不创建 durable job record 或 sidecar、direct stream 使用 operation-scoped cancellation token/checker、direct 用户事件不暴露路径、job id、raw provider payload 或正文、stream producer 静默结束时收口 failure result、upload `SourceKind` filing/material 分流、upload 默认缺 runner 时的 unsupported terminal failure、upload request / result bounded summary、无网络 fake download adapter 写入 source/blob 仓储、unsupported source failed terminal、重复下载按 storage 语义跳过、rejected filing artifact 通过 maintenance 仓储保存、preprocess source -> processed pipeline、已有 processed 跳过 / 重建、missing document failed terminal、unsupported processor not_supported summary、cancel transition、record leakage boundary、legacy job store 原子写入失败清理、legacy ingestion job event sidecar 的 queued/running/terminal/status observation 序列、download / upload 同步调用边界与 preprocess 文档处理路径的粗粒度 `PROGRESS` event、`read_job_events(...)` 游标读取、bounded payload 与敏感内容不落 sidecar、并发 sequence 分配、非法 payload 拒绝、non-terminal、terminal 与 progress event append failure 的 WARN-and-continue 行为，以及新增 ingestion runtime 不破坏 read provider / `FinsReadRuntime` 懒加载行为。

Fins fixture 由测试通过仓储 public API 写入临时 workspace，不依赖隐式 cwd、环境变量或手工拼生产路径。

### `tests/host/`

Host 公共 API 类型、Session / Run public command facade、construction tooling options 与内部 durable foundation 测试，覆盖 `dayu.host` 的稳定边界：

- package exports：锁定 `dayu.host.__all__`、`dayu.host.api.__all__` 与 Host 内部 typed contract 模块级 `__all__` 白名单，确认 command facade / tooling 类型可从包根导入但不进入 `dayu.host.api`，并阻止 memory / context fallback 私有 helper 泄漏。
- public contracts：验证 status / error 枚举字符串值、frozen slots dataclass、结构化 `HostApiError`、request validation failure paths，以及 `HostCommandHandleOptions` 必填 context window / reserved output budget 输入与 command-to-local execution composition wiring。
- command handle / public session API：覆盖 Host command handle factory fresh DB、稳定 public handle id、默认 active registry 不跨 handle 共享、内部依赖不暴露、close 幂等、关闭后 facade 稳定失败，以及 `ensure_session` / `create_session` / `get_session` / `close_session` 的 snapshot、幂等、冲突、NOT_FOUND 与保留 durable truth 语义；覆盖 `purge_session` 对已关闭且全部 Run 终态 Session 的 tombstone result、幂等重放、同 key 不同语义冲突、不同请求访问已 purge Session 冲突、append-only audit JSONL 的 `purge_started` / `purge_completed` / best-effort `purge_failed` 语义和 purge 后 read path `NOT_FOUND`；`test_storage_usage_report.py` 覆盖只读 `report_storage_usage` 的 fresh DB 零计数、Session / Run / payload descriptor / SQLite payload row count、logical bytes、orphan SQLite payload 诊断计数、DB/WAL 文件大小、async `open_host` handle 入口、closed handle 错误语义与 `json_value()` 键集合；`test_storage_orphan_proof.py` 覆盖 artifact descriptor 引用证明、shared descriptor 去重、projection lag 下 descriptor truth、`sha256/` namespace 安全、grace 过滤、稳定排序与物理 artifact size；`test_storage_maintenance.py` 覆盖 dry-run maintenance 不删除文件或 SQLite row、orphan 候选、物理 artifact bytes、WAL checkpoint on/off、EventLog/Session/Run 状态不变、async `open_host` handle 入口、closed handle 错误语义，以及 opt-in orphan artifact reclaim 的删除成功、共享引用保留、删除前 recheck 跳过、单文件错误诊断与幂等。
- public run / wait / event API：覆盖 `_start_run` 内部 admission primitive / 低层测试路径的 accepted pre-start / attach active conflict / 幂等重放 / 幂等冲突、`submit_followup(queue)` active 与 no-active 分支、`submit_followup(steer)` active RUNNING 新 Attempt / 幂等重放 / `SteerConflictDetail` 负面详情、typed prompt request contract、per-run `tool_names` 全量 / 禁用 / 子集 / unknown 拒绝、per-run runner config field-level partial merge、effective config / tool set freeze、重复 `(session_id, client_request_id)` 返回同一 accepted Run、`watch_session_events(session_id)` 两个 watcher 观察同一 terminal HostEvent、terminal event 不结束 iterator、consumer early cancel 不取消 Run / 不写 EventLog、final answer 只能从 terminal HostEvent typed view 取得、FAILED / CANCELLED / LOST terminal typed display fields、`open_host` startup recovery 后通过 watch 观察 final answer、handle closed / missing Session / Session CLOSED watch 语义、`HostEventView` 与 run-level `stream_run_events` 不在包根 public namespace、ordinary local `retry_run` FAILED 源关联新 Run / 缺失源 NOT_FOUND / 幂等冲突、`replay_run` SUCCEEDED 源关联 no-tool 新 Run / 缺失源 NOT_FOUND、`cancel_run` accepted / queued / pre-dispatch STARTING / injected active worker registry / WAITING / RECOVERING、`cancel_session_runs` 的 accepted / queued / pre-dispatch STARTING / injected active worker registry / WAITING / RECOVERING 子集、幂等重放、不影响其它 Session，以及 `resolve_wait` completed resume / tool-cancelled resume / failed closeout / lost closeout / late diagnostic / 同 outcome 不受 `observed_at` 变化影响的幂等重放 / 不同 outcome 幂等冲突。
- provider request identity / runner-call manifest / Tool Trace correlation：覆盖 Host effective execution config freeze / restore 保留 `RunnerSpec.client_correlation_policy`，RunInputBuilder 把 Attempt `attempt_id` / `execution_id` 投影到 `AgentRunRequest`，reactive compactor request 传递 Attempt / execution 而 proactive compactor request 保持二者为空；compactor proposal manifest 区分首次 proposal trigger reason 与 retry trigger reason；Engine iteration started 覆盖由真实 messages 角色顺序计算的 role sequence digest 与 serializer schema version；Engine ingest 覆盖 failed terminal、recoverable failure diagnostic、context compaction request / recovery closeout、provider protocol diagnostic、iteration completed preview 中的 `provider_request_id` / `client_correlation_id` payload、ordinary prepared manifest 到 `RUNNER_CALL_INPUT_ITERATION_LINKED` 的显式关联、runner-call manifest signal validation、missing / ambiguous / mismatch / link conflict fail closed、continuation reset limited-signal durable scope，以及 tool-call requested preview 的 normalized arguments digest；Tool Trace projection 覆盖 hot `trace_summary_json` 与 cold JSONL `trace_summary` 暴露 `client_correlation_id`、复制 runner-call manifest read-model signal 与 non-complete typed diagnostic、缺失 typed diagnostic fail closed、mismatch diagnostic、按 Run 查询 complete / limited_signal / mismatch typed reconstruction signal、context pressure / tool timing / failure metadata 结构化 signal、provider request id 查询结果的 trace summary 保留客户端关联字段，以及大工具参数 descriptor 不被展开进 cold JSONL。
- public-path smoke：`test_public_open_host_multiturn_smoke.py` 覆盖 real-runner no-tool 两轮、deterministic 两轮 final answer continuity、multi-client watch 与 queue idempotency；`test_public_tool_wiring_smoke.py` 覆盖 mock business tool wiring、accepted tool fact 到下一轮输入、`tool_names` 子集 / 空集合冻结，并对记录到的 runner call messages 校验最多一条 system message 且唯一 system 位于首位；`test_public_steer.py` 与 `test_public_resolve_wait_resume.py` 通过 `open_host(options)`、mock awaiting tool 和 public command 覆盖 WAITING Run 的 steer / resolve_wait；`test_public_cancel_smoke.py` 覆盖 pre-dispatch / active / RECOVERING / session-scoped cancel 与 close 边界；`test_public_compact_smoke.py` 覆盖 no-compaction recent raw continuity、deterministic public opener proactive compact、proactive material JSON 中 raw accepted tool evidence 进入 `evidence_material` 并由 fake compactor 生成后续可复用 vNext fact、vNext reference continuity 后续解析、多次 compact 后 memory / compactor input bounded、重复长 prompt 不因 compactor material 重复超窗失败、compactor proposal runner-call manifest bounded 且不内联重复长正文、manifest 的 message_count / message_entries / role sequence digest 同源、默认 compactor prompt 和 material 不暴露内部实现术语且自足说明输入输出，并保留 material-label fake proposal 对 raw accepted evidence block 到 fact candidate 的 helper-level 提取边界；`test_public_real_runner_matrix_smoke.py` 覆盖 mimo、deepseek、gemini、qwen 的 real runner public path。public smoke 需要等待非展示型调度事件时，只能通过 `public_smoke_support.py` 的集中 helper 作为测试同步 primitive，结果断言仍使用 public snapshot / HostEvent。real runner smoke 只允许按 provider 缺少 secret、endpoint / 网络不可用、临时不可用或 quota / rate-limit 给出精确 skip；real compactor smoke 默认跳过，只有设置 `DAYU_RUN_REAL_COMPACTOR_SMOKE=1` 才运行；测试专用 deterministic compactor 位于 `tests/host/fake_compaction.py`，测试专用可控 cancellation token 位于 `tests/host/fake_cancellation.py`，生产代码不得导入。
- Engine ingest / watch regression：覆盖空白 final answer 按 `empty_final_answer` 收口为 `FAILED`，并通过 public `watch_session_events` 投影为 typed failed HostEvent，防止 `RUN_SUCCEEDED` 写入不可展示 final answer 后导致 watch 读取崩溃。
- tooling options：验证 `FrameworkToolName` 为 `StrEnum`、默认 reserved framework tool policy、`HostToolingOptions` 接受 contracts source refs 且要求 source refs 非空、业务 `ToolBundle` 不得占用 `fetch_more` 等 reserved framework tool name、duplicate governance messages 显式覆盖所有决策类别，以及 default policy view 不共享可变状态。
- durable foundation / projection core / Context Governance / Conversation Memory / RunInputBuilder / dispatch scheduler / ToolRuntime accept barrier / executor / truncation / fetch_more / duplicate governance / diagnostics / EngineEvent ingest / internal admission：覆盖 SQLite fresh bootstrap、schema version / table constraint、transaction runner commit / rollback / after-commit、EventLog / payload / idempotency / projection checkpoint 基础路径、Context Budget、vNext compaction operation / artifact / typed contract、compact outcome payload 反向引用 proposal manifest ref / digest、Conversation Memory vNext policy 与 snapshot contract、selected recent window、accepted compact materialization、no fallback facts、durable snapshot / item / diagnostic round-trip、memory snapshot 与 projection checkpoint 同事务、memory snapshot integrity classification（invalid JSON、schema mismatch、digest mismatch、unsupported item kind、storage read failure）及 storage maintenance operator-facing report、repair / rebuild / catch-up、RunInputBuilder vNext memory 渲染 / inline delta / repair-required、ordinary one-system-message envelope、ordinary runner-call input manifest 有界且不内联大 user input / message content、Session lifecycle、Run / Attempt transition、dispatch / wait / resolve_wait / scheduler / ToolRuntime accepted tool-call request atoms（inline arguments、arguments descriptor、semantic query absent / inline / descriptor、digest mismatch fail-closed）/ duplicate governance / Engine ingest / public admission 与多进程 durable invariant。
- durable concurrency matrix：`test_durable_concurrency_matrix.py` 覆盖 idempotency 同 key 多进程 same / different digest、projection checkpoint lost CAS，以及 memory snapshot + checkpoint 同事务提交和 CAS rollback；EventLog append、ensure_session 与 liveness 仍由既有测试闭环，不在该矩阵文件重复覆盖。
- P12.6 memory semantic smoke：`test_toolruntime_accept_barrier.py` 覆盖 ToolRuntime accept barrier；`test_compaction_contract.py` / `test_context_compact_events.py` / `test_llm_compaction.py` / `test_compaction_operation.py` 覆盖 compact material pack、prompt-local label 到 canonical provenance 映射、compaction-gated vNext fact candidate、accepted evidence material 注入、accepted evidence query_text 消费 durable tool-call request atoms、LLM compactor prepared proposal input 与真实 runner messages 同源、vNext accepted / rejected / failed operation payload、proposal manifest ref 传递和 whole-candidate repair 边界；`test_compact_material.py` 覆盖 deterministic segment selection、protected current / selected recent-window floor、reactive frozen overflow material list、already represented block 排除、current input anchor 去重、vNext material 对 user turn / assistant turn / evidence / previous fact view / current anchor non-citable 的直接映射边界、EventLog-backed pre-dispatch compact material source、explicit previous compacted view pack path，以及 snapshot cursor lag repair-required 语义；`test_memory_projection.py` 覆盖 vNext policy / snapshot contract、compact 前 selected recent window、accepted compact materialization、accepted evidence without fact diagnostic、failed compaction 不物化 memory、JSON / durable round-trip、projection consumer checkpoint 与 durable memory snapshot integrity classification；`test_storage_maintenance.py` 覆盖 operator-facing maintenance result 暴露 memory snapshot integrity issues 且不执行 snapshot repair / overwrite；`test_run_input_builder.py` 覆盖 RunInputBuilder 对 vNext evidence fact、session summary、answer anchor、forward intent、reference continuity、selected recent window、post-compaction facts、no-compaction continuity、memory snapshot repair、shared ordinary material block source、ordinary runner-call input manifest，以及 fallback selected recent window rendering；`test_dispatch_scheduler.py` 覆盖 memory projection lag repair 不关闭 Run / Attempt 为失败终态，并覆盖 proactive / reactive compaction vNext closeout、compaction failure 后 recent-window fallback dispatch / hard-budget fail closed 不写 `CONTEXT_COMPACTED` 且不写 `RUN_LOST`。
- runtime：覆盖取消 / 超时 race helper、日志装配、file lock、lane controller、config loader 与 runtime import / weak typing guard。
- Phase 5 / 10 本地执行集成：`test_phase5_local_execution_integration.py` 使用 `_start_run` 内部 admission primitive / 低层测试路径、真实 `HostDispatchScheduler`、runtime lane 与 fake local worker 覆盖 no-tool Engine 闭环。fake worker 必须只通过 `LocalEngineWorkerFactory` / `LocalWorkerHandle` 边界产出 Engine public `EngineEvent`、响应 `on_cancel(reason)` hook 或模拟 clean EOF / stream crash；测试断言 Host durable Run / Attempt 终态、active cancel 传播、terminal / cancel 后 queue promotion 继续唤醒 pre-start governance / dispatch，不绕过 scheduler 直接改生产状态。
- import boundary：允许 Host 在 LocalProxy、Host-owned LLM compaction 与 compaction operation 边界沿依赖方向调用 Engine public entry / contracts，阻止 Host 导入 Config、Fins、Service 或 UI，阻止 Host 使用动态模块扫描能力扫描业务工具模块，确认 business `ToolBundle` 不进入 per-run request dataclass 字段，并确认 `fetch_more` 只留在 ToolRuntime / tooling owner 中且不迁移 OLD fetch-more projection；显式覆盖 `dayu.host.durable.purge` 不依赖上层、runtime、public command owner 或 audit / dispatch owner。
- weak typing guard：通过 AST 扫描阻止 `Any`、`object`、无类型签名与裸容器注解进入 Host 公共类型源码，并显式确认 `dayu.host.durable.purge` 被纳入扫描。
- production stress：`test_host_production_stress.py` 使用 `stress` marker，默认 pytest 排除，需通过
  `pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q` 显式运行。stress summary
  JSON 固定包含 `scenario_name`、`session_count`、`run_count`、`crash_count`、`recovery_count`、
  `watch_lag_max`、`watch_lag_samples`、`scheduler_drained`、`liveness_stale_detected`、
  `terminal_duplicate_count`、`terminal_dedupe_ok` 与 `failure_boundary`；`failure_boundary` 只允许使用
  stress helper 定义的封闭失败边界或 `None`。

### `tests/engine/`

Engine 契约、包根导出、事件契约与架构边界测试，覆盖 `dayu.engine` 的稳定边界：

- package exports：锁定 `dayu.engine.__all__`，阻止未承诺入口、实现类或取消异常出现在包根。
- import boundary：阻止 Engine 反向依赖 Host（含 memory）、Service、UI、Fins、工具声明 owner、工具执行实现、处理器或 trace 私有模块；OpenAI runner 子树内允许当前实现所需的 `aiohttp`。
- weak typing guard：扫描 `dayu.engine` 源码，守住强类型签名、封闭联合与 metadata 类型边界。
- 事件契约与消息契约：覆盖 EngineEvent、RunnerEvent、AgentMessage、metadata、provider protocol error `partial_tool_calls` 有界摘要、AgentMessage 大内容透传到 Runner、终态事件集合等结构约束。
- Agent 状态机：覆盖无工具 final / failed / cancelled、普通 completed / failed tool calling、工具结果投影、max iteration force-answer、大工具消息进入 force-answer 路径、连续失败工具批次保护、awaiting 拒绝与取消优先级、close cancellation 资源释放、工具批执行前取消不登记 tool call id。
- provider smoke 轻量测试：覆盖 `utils/smoke_async_agent_providers.py` 的参数解析、缺 key 跳过、安全输出与 provider case 配置，不做真实联网。
- provider extension config adapter：覆盖默认模型目录中的 provider extension JSON DSL 到 `ProviderRequestExtension` 封闭联合的映射，并确认未知 type、未知字段、非法枚举和非法字段组合 fail closed。

### `tests/engine/contracts/`

Engine contract 的细粒度测试，当前覆盖：

- `messages`：AssistantMessage / AssistantToolCall 与 provider state roundtrip 契约。
- `runner_events`：RunnerEventData 联合、RunnerHTTPErrorCode、RunnerHTTPErrorData、HTTP error 与 context overflow 错误枚举、HTTP error 到 Done(ERROR) 的收口契约。
- `runner_spec`：RunnerSpec 字段集合、`ClientCorrelationPolicy` 枚举值、provider reasoning / thinking extension、stream usage 能力字段、免鉴权 provider 的 `api_key_ref=None`、timeout / retry 校验与构造路径。
- `runner_identity`：`RunnerRequestIdentity` 与 `build_runner_request_identity` 的稳定 lowercase SHA-256 `client_correlation_id`、ASCII 长度、iteration / call index 差异、direct Engine 无 Attempt 路径、attempt / execution 成对约束、空文本与非法序号拒绝。
- `agent_run`：`AgentRunRequest` 的非空 messages 校验，以及 Attempt `attempt_id` / `execution_id` 成对出现或同时缺失的契约。
- import boundary：Engine contract 子包不得越过自身契约边界引入上层依赖。

### `tests/engine/runners/openai/`

OpenAI-compatible Runner 的 provider 协议测试，覆盖从 payload 构建、provider 响应解析到 RunnerEvent 事件流的行为：

- payload：消息、工具 schema、reasoning content、provider 扩展、stream usage gating、禁止额外 payload 袋。
- SSE：content delta、reasoning delta、tool call delta、tool call 聚合、usage、malformed usage 非终止诊断、`[DONE]`、多行 data、单行 / data 行数缓冲上限、跨 chunk UTF-8、非法 UTF-8、尾部无换行、空 choices + usage、HTTP 200 `Content-Type` 白名单分流和缺失 `Content-Type` fallback。
- non-stream：非流式响应、thought 标签处理、stream / non-stream 终态语义一致性。
- 错误与重试：协议错误、HTTP error 分类、context overflow classifier、未知状态码、retry backoff、重试耗尽后的事件收口。
- request identity header：覆盖 OpenAI-compatible Runner 在 `ClientCorrelationPolicy.OPENAI_X_CLIENT_REQUEST_ID` 且 `request_identity` 存在时发送 `X-Client-Request-Id`，policy disabled 或 identity 缺失时不发送，policy 开启时拒绝静态 `X-Client-Request-Id` header 冲突，并确认 transport retry 复用同一个客户端关联 header。
- 取消与资源：取消边界、取消后不补 done 事件、close 释放资源、已完成 read task 异常消费。
- 架构边界与协议表面：Runner 只产出 RunnerEvent，不依赖 ToolExecutor，不暴露任意 `**kwargs` 或 `set_tools`，事件流顺序保持单调并以唯一终态收口。

本目录内已有 `_fakes.py`、`_factories.py`、`_sse_helpers.py`、`_diagnostic_helpers.py` 作为局部测试 helper。

## 维护约定

- 新增公共契约必须补 package export、import boundary、weak typing guard 相关测试。
- 新增 Host 公共类型必须同步更新 `tests/host/test_package_exports.py`，并为新增 request / snapshot 或 construction options 校验补充对应测试。
- 新增 Runner 行为必须优先补协议事件流测试，确保下游 Engine loop 能无歧义消费。
- 状态机测试必须覆盖输入事实、状态分支、事件顺序、终态收口。
- 架构边界测试必须阻止反向依赖，尤其是下层导入上层实现或私有治理概念。
- 测试不得为了旧接口在生产代码中保留兼容逻辑；测试应跟随当前实现边界迁移。
- 测试 helper 可以放在对应测试子目录内，例如 `_fakes.py`、`_factories.py`、`_sse_helpers.py`。
- helper 不应成为生产代码替代品，也不应隐藏关键断言；协议事实和终态断言应保留在测试用例中。

## 类型与弱类型守护

测试必须配合 `pyright` 使用。公共契约、Runtime、Host、Service 和 Engine 的测试已经通过 AST 扫描守护弱类型边界，新增契约时应保持同等严格度。

- 禁止通过测试 helper 引入 `Any` / `object` / 裸 `dict` 的公共契约逃逸。
- 如果测试需要构造 JSON，应使用当前项目已有 `JsonValue` 类型或局部私有 helper，不得把弱类型 JSON 袋扩散到生产接口。
- 对封闭联合新增成员时，应同步更新穷尽匹配测试，避免新分支在类型检查中静默漏处理。

## README 更新边界

本文件只描述当前 `tests/` 已存在的事实，不写用户手册、Engine 设计文档、完整 review prompt、未落地测试体系或时间敏感记录。

如果之后新增测试层级、测试运行方式或测试维护规则发生变化，应在对应变更中同步更新本文件。
