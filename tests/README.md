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

运行 workspace 初始化、模型家族、Service 装配与 provider matrix harness 的完整
focused 回归：

```bash
pytest tests/cli/test_arg_parsing.py \
  tests/cli/test_prompt_command.py \
  tests/cli/test_interactive_command.py \
  tests/cli/test_session_command.py \
  tests/cli/test_init_command.py \
  tests/cli/test_init_catalog.py \
  tests/cli/test_init_workspace.py \
  tests/cli/test_init_smoke.py \
  tests/runtime/test_assembly_helpers.py \
  tests/runtime/test_config_loader.py \
  tests/service/test_host_assembly.py \
  tests/cli/test_smoke_cli_init_provider_matrix.py -q
```

这些测试覆盖 `init` 参数面与退出码、resolved model family、单次模型 override 隔离、
target profile context minimum、交互重试、FIRST/PRESERVE/OVERWRITE/RESET、普通文件
repair、rollback、冻结 publication manifest、provider availability classifier、
脱敏与 no-fallback report contract。

对应单文件 coverage：

```bash
coverage erase
coverage run -m pytest tests/cli/test_arg_parsing.py \
  tests/cli/test_prompt_command.py \
  tests/cli/test_interactive_command.py \
  tests/cli/test_session_command.py \
  tests/cli/test_init_command.py \
  tests/cli/test_init_catalog.py \
  tests/cli/test_init_workspace.py \
  tests/cli/test_init_smoke.py \
  tests/runtime/test_assembly_helpers.py \
  tests/runtime/test_config_loader.py \
  tests/service/test_host_assembly.py \
  tests/cli/test_smoke_cli_init_provider_matrix.py
coverage report --include='dayu/cli/arg_parsing.py,dayu/cli/session_execution.py,dayu/cli/commands/init.py,dayu/cli/init_catalog.py,dayu/cli/init_workspace.py,dayu/runtime/assembly.py,dayu/service/host_assembly.py,utils/smoke_cli_init_provider_matrix.py'
```

`docs/cli_init_workspace_manifest_v1.json` 是冻结的 workspace publication 真值，精确
记录 5 个受管目录、43 个受管文件及 16 个 model pointer。普通 deterministic tests
只读取该文件，并独立枚举实际 publication tree；不会从实际树动态生成 expected，也不会
在 mismatch 时更新 manifest。

真实 15-choice provider matrix 不属于默认 pytest。显式运行：

```bash
python utils/smoke_cli_init_provider_matrix.py --oracle-version 1
```

该命令执行真实 `init`、`prompt` 与 Host evidence 取证，报告写入
`workspace/tmp/.../<run-id>/matrix-report.json`。外部 credential 缺失、
endpoint 未配置、transport failure、provider rejection 与 rate limit 按封闭分类记录；
内部 schema/profile/model/family/assembly/trace 错误、secret leak、fallback 或
requestable row 无真实 response 会使命令非零。报告只保留有界、脱敏的 response/diagnostic
摘要；Host SQLite/WAL 中 resolved credential 的 exact match 只记录为 accepted
observation，非 Host SQLite artifact 中的 credential value 与任意位置的 canary 都是
violation。

运行 Host Session Event Delivery 的 Service / CLI focused 回归：

```bash
pytest tests/service/test_entrypoint_runtime.py \
  tests/service/test_entrypoint_runtime_prompt_path.py \
  tests/service/test_entrypoint_runtime_interactive_path.py \
  tests/cli/test_transient_delivery_interruption_path.py \
  tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py \
  tests/cli/test_runtime_display.py tests/cli/test_activity_renderer.py \
  tests/cli/test_interactive_run_view.py tests/cli/test_thinking_renderer.py -q
```

运行 Session attachment、target recovery 与跨 opener cancel focused 回归：

```bash
pytest tests/runtime/test_native_mutex.py \
  tests/host/test_session_attachment_registry.py \
  tests/host/test_public_session_attachment.py \
  tests/host/test_active_cancel_dispatch.py \
  tests/host/test_run_attempt_transitions.py \
  tests/host/test_recovery_scan.py tests/host/test_recovery_multiprocess.py -q
```

批量上传 owner、脚本 renderer/publisher 与 public packaging 的 focused 验证：

```bash
pytest tests/fins/test_upload_batch.py tests/cli/test_upload_filings_from_command.py \
  tests/cli/test_fins_commands.py tests/cli/test_arg_parsing.py \
  tests/cli/test_public_package_entrypoints.py -q
```

运行 Tool Trace Analyzer、Service publication 与 CLI focused 回归：

```bash
pytest -q tests/host/test_tool_trace_analysis_input.py \
  tests/host/test_tool_trace_analysis_rules.py \
  tests/host/test_tool_trace_analysis.py \
  tests/service/test_tool_trace_analysis.py \
  tests/cli/test_tool_trace_command.py \
  tests/cli/test_arg_parsing.py \
  tests/cli/test_import_boundary.py
```

仓库当前不配置 GitHub Actions workflow；跨平台 CI 重建由
[GitHub Issue #184](https://github.com/noho/dayu-agent-r/issues/184) 跟踪。以下真实 Windows nodes 保留为
后续 CI 的验收资产：

```bash
python -m pytest tests/cli/test_run_keys.py::test_new_running_key_monitor_uses_noop_for_non_posix_tty tests/cli/test_upload_filings_from_command.py::test_windows_cmd_script_round_trips_adversarial_argv_with_real_cmd tests/cli/test_upload_filings_from_command.py::test_windows_generated_script_runs_real_cli_into_temp_storage tests/cli/test_arg_parsing.py::test_upload_actions_default_to_auto_and_batch_rejects_delete -q
```

其中两个 upload nodes 必须实际经过 `cmd.exe /d /c`，分别验证对抗参数逐元素恢复和
`python -m dayu.cli -> Service -> Fins -> temp storage` 闭环；非 Windows 本地环境只会明确 skip，不能替代真实
Windows runner 证据。
CLI process owner 会在解析参数和输出前，把真实 stdout/stderr `TextIOWrapper` 明确配置为 strict UTF-8，保证 redirected
init/upload 中文输出仍可编码；直接消费 Dayu CLI 或生成脚本所转发输出的测试 subprocess 同样显式使用
`encoding="utf-8", errors="strict"` 解码，不依赖 Windows ambient code page。内存 capture 等非 OS wrapper 保持调用方自己的
语义，纯 recorder、`reg.exe` 与 junction native 命令继续使用各自的平台输出契约。产品 `setx` persistence 调用的 native
output 没有消费者，因此不由产品捕获。真实 init Windows tests 继续覆盖 FIRST→PRESERVE→OVERWRITE→
RESET No→RESET Yes、`ConfigLoader`/scene 重载、junction/reparse、rollback/race、`setx` round-trip、
redirected stdin 与非 POSIX TTY owner boundary；新 CI 必须在 Windows runner 上调度这些现有测试。

默认 pytest 配置会排除 `stress` marker，因此常规命令不会运行 Host production stress suite 或 transient delta stress。显式运行时需要覆盖默认 `addopts`：

```bash
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
pytest -o addopts="" -m stress tests/host/test_transient_delta_stress.py -q
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
pytest tests/host/test_accepted_result_projection.py tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_tool_trace_projection.py tests/host/test_dispatch_scheduler.py tests/host/test_tooling_options.py -q
pytest tests/host/test_toolruntime_executor.py tests/host/test_phase6_toolruntime_integration.py -q
pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_engine_ingest_mapping.py -q
pytest tests/host/test_resolve_wait_command.py tests/host/test_run_attempt_transitions.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_phase7_waiting_integration.py -q
pytest tests/host/test_wait_callback.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py tests/host/test_package_exports.py tests/host/test_import_boundary.py -q
pytest tests/host/test_wait_cancel_late_result.py tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/host/test_engine_ingest_mapping.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_run_api.py -q
pytest tests/host/test_submit_followup_public_contract.py tests/host/test_per_run_tool_selection.py tests/host/test_effective_execution_config.py -q
pytest tests/host/test_watch_session_events.py tests/host/test_public_host_event.py -q
pytest tests/host/test_transient_delta.py tests/host/test_watch_session_events.py -q
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
pytest -o addopts="" -m stress tests/host/test_transient_delta_stress.py -q
pytest tests/host/test_context_budget.py tests/host/test_compaction_contract.py tests/host/test_compact_artifact_store.py -q
pytest tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q
pytest tests/host/test_context_compact_events.py -q
pytest -q tests/host/test_context_anchor.py tests/host/test_context_budget.py tests/host/test_context_compact_events.py tests/host/test_memory_projection.py tests/host/test_memory_repair.py tests/host/test_run_input_builder.py tests/host/test_accepted_result_projection.py tests/host/test_runner_call_hot_payload_contract.py tests/host/test_engine_ingest_mapping.py tests/host/test_compaction_operation.py tests/host/test_dispatch_scheduler.py tests/host/test_admission_queue.py tests/host/test_admission_multiprocess.py tests/host/test_public_steer.py tests/host/test_public_resolve_wait_resume.py tests/host/test_resolve_wait_command.py tests/host/test_phase7_waiting_integration.py tests/host/test_recovery_dispatch.py tests/host/test_public_session_attachment.py tests/host/test_open_host_runtime.py tests/host/test_command_handle.py tests/host/test_durable_schema.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_watch_session_events.py tests/host/test_projection_runner.py tests/host/test_recovery_scan.py tests/host/test_run_attempt_transitions.py tests/host/test_state_schema.py tests/host/test_outbox_projection.py
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

CLI UI adapter 测试当前覆盖 pyproject 只发布真实 `dayu-cli`、wheel metadata / entrypoints / archive 不包含已删除的 placeholder scripts、packages、Web extra 或 Streamlit requirement；也覆盖 `dayu.cli` 的 parser factory、scoped command help、未纳入旧命令的 unknown command
用法错误、尚未实现命令的 not-implemented 退出、`KeyboardInterrupt` 到 130 的映射、全局参数位置、`init` 拒绝
`--config`、Agent surfaces 使用 `--model/-m` 且拒绝旧 `--model-name`，以及 `init`
的 typed model catalog、OS environment owner、`.dayu`/`config` 单一 managed-root transaction、
FIRST/PRESERVE/OVERWRITE/RESET 四态、fresh-root/lock/identity/containment、真实 ConfigLoader/Service discovery/
13-scene validation、PRESERVE 根配置/prompt 补缺、ordinary-root repair、publication/rollback/cleanup fault
matrix、target effective profile context minimum、可恢复输入原步骤 retry、EOF/confirmation exit、secret
names-only diagnostic 与 SIGINT 130。`test_init_smoke.py` 进一步用隔离 subprocess 证明 FIRST/RESET-only exact-two-root
import prewarm 的 transitive graph、连续稳定、零网络/零 workspace/env mutation，并在真实 POSIX 上覆盖完整四态、
profile 0600/单 marker block/脱敏、user manifest 与缺失 prompt、portfolio/assets sentinel、RESET No 整树 hash、
公开 waiting notification、真实 file_lock 单 waiter 与双 queued publisher 串行成功；
`test_smoke_cli_init_provider_matrix.py` 覆盖冻结 manifest 的精确 publication tree、15-choice
classifier、endpoint/response 脱敏、persisted secret classification、canonical no-fallback
与 retained-report reconciliation；deterministic 路径不调用 provider。
`python -m dayu.cli --help` 入口，并覆盖 CLI main 把默认 log level、`--debug` / `--debug-stream` / `--verbose` / `--quiet` / `--log-level`
解析结果和进程结束自动删除的默认临时日志流或全局 `--log-file` 诊断流交给 `dayu.runtime.log.set_level_from_flags(...)` 装配日志，且覆盖临时流工厂、日志文件打开失败、连续调用恢复 stderr、恢复 stderr 失败仍关闭日志流，以及异常 / `KeyboardInterrupt` 路径恢复 stderr handler 后再关闭文件。`prompt` 命令测试覆盖 CLI 参数到 Service entrypoint request 的转换、`--ticker` 到 LLM-facing `fins_default_subject` Markdown slot 的生成、非法 `--ticker` usage error、FMP 公司名增强与缺 key fallback、stable
Host slot key、已移除执行参数走 argparse unknown、已删除旧 debug 参数走 argparse unknown、`--thinking` / `--no-thinking` 展示参数解析、thinking event 存在时 `--thinking` 与 `--no-thinking` 输出不同、真实 `prompt.json` required context slots、入口身份不进入 LLM context slots、mock Host public
open/follow-up terminal path、fast terminal、outbox fallback、默认 detail 输出 activity、显式 `--no-detail` 不注册 activity 输出、activity 不进入 `--log-file`、TTY 下 thinking/activity 交错输出前收尾与 final 前运行态清理、HostApiError 结构化展示、FAILED terminal 输出、非成功 terminal 渲染后 cursor 前进、cursor 写失败传播和 SIGINT 后 Host public cancel request；
`interactive` 命令测试覆盖默认 fresh anonymous Session、label session binding、existing-session startup reconnect 在首条输入前执行、startup terminal 渲染后 cursor 前进、`--new-session` 用法错误、真实
`interactive.json` 要求入口提供共享 `fins_default_subject` 与 `current_time` context slots、`interactive --ticker` 进入模型可读研究主体、两轮同 Session、每轮独立 watcher subscription open/close、fast terminal、FAILED / CANCELLED 继续输入、LOST fatal、输入态空 prompt 首次 Ctrl+C 重绘提示符、连续第二次 Ctrl+C 本地 130、正常输入重置输入态退出待确认状态、运行态 SIGINT cancel、
第二次运行态 SIGINT 本地 130 且没有 terminal 时不推进 cursor、interactive run view activity/transcript buffer、默认 detail 与显式 `--no-detail` 展示语义、Ctrl+T 切换 view 且不触发 cancel、显式 config 错误、HostApiError 结构化展示、已移除执行参数走 argparse unknown、已删除旧 debug 参数走 argparse unknown、`--thinking` / `--no-thinking` 展示参数解析、thinking event 存在时 `--thinking` 与 `--no-thinking` 输出不同，以及 `--verbose` / `--debug` / `--debug-stream` 诊断不污染 stdout 用户结果通道；CLI terminal cursor store 测试覆盖 workspace-local JSON cursor、async executor 包裹同步 file lock / JSON 读写、腐坏与非法字段 fail fast、只前进 watermark、seen ids 有界裁剪和 atomic replace 临时文件清理；CLI existing-session cursor 测试覆盖 startup reconnect 与 interactive turn 非成功 terminal 渲染后 cursor 前进，以及 prompt / startup reconnect / interactive turn cursor 写失败作为本地投递持久化错误传播；CLI activity renderer 独立测试覆盖 TTY policy、dedupe、sequence、hidden、visible 后隐藏状态、cancel 提示、TTY terminal 前清理和非 TTY 可读降级；CLI thinking renderer 独立测试覆盖输出、后续 delta 同行追加、delta 边界空格保留、terminal 前收尾、dedupe、乱序过滤和 disabled；interactive run view 独立测试覆盖 activity buffer、terminal transcript、activity/transcript view toggle、activity view 下 terminal result 输出并回到 transcript、不输出旧 `Activity hidden` 文本、可初始进入 activity view、TTY terminal 前清理和非 TTY 可读降级；运行态按键监听测试覆盖 Ctrl+T / Esc 映射、非 TTY no-op policy、TTY reader 恢复、thread start 失败恢复、prompt Ctrl+T 可见性切换、prompt / interactive Esc cancel 集成、prompt 第二次 Ctrl+C 本地退出和 cancel terminal 竞争优先级；interactive composer 独立测试覆盖非 TTY input reader adapter、Ctrl+J 换行、Ctrl+R 历史搜索、Ctrl+C 清空 / 退出和 Ctrl+X Ctrl+E 外部编辑器诊断，并覆盖 prompt / interactive existing-session 执行入口不会 create / ensure。Session command 测试覆盖 CLI label kind 到 Host public slot ref 的映射、anonymous / prompt / interactive / other slot 展示身份反解、含点号 label 不拆分、`session list` public Host 调用与 open / closed 输出、`session resume` 按 session id 或 label 解析已有 OPEN Session 后路由到 prompt / interactive existing-session 执行并传递 detail / thinking 展示参数、CLOSED / missing label fail fast、resume label TOCTOU 错误上下文、HostApiError 退出码纯函数策略、`session purge` 的 `--yes` 门禁、按 session id 清理、按 label 先 list 解析 slot 再 purge、Host `INVALID_STATE` 前置条件错误、purge label TOCTOU 错误上下文和成功输出，并确认 Session list / purge 输出不展示删除计数 digest 或内部治理字段。Fins direct command 测试覆盖
`download`、`upload_filing`、`upload_material`、`process`、`process_filing`、`process_material` 的 CLI 参数到
`FinsDirectCommandService` 显式方法参数转换、Service event stream 消费、progress / terminal summary
stdout/stderr 投影、CLI 输出中绝对路径可见但受长度控制、upload file 存在性 / 普通文件 / 非空前置校验、已删除 `--infer` / `--ci` 由 argparse 拒绝、
默认日志不污染 progress 输出、`--verbose` 执行骨架日志与 `--debug` event detail 诊断写入默认临时日志文件，`--log-file` 只迁移诊断日志且 stdout/stderr 用户 UI 保持原通道、
Fins owner stream / cancel failure 向上传播且 CLI 不重复记录同一 ERROR、stream 创建者在 success / protocol error / log-render error / 外部取消 / SIGINT 本地退出全部路径确定性关闭 raw source、既存 consumer primary 与 cleanup cause 保持、
`upload_filings_from` 的 typed 本地目录扫描、filing / material / skipped 三分、POSIX `.sh` 与 Windows `.cmd` renderer、default / explicit output、
ticker CSV、single FMP infer、human summary、调用者追加参数、atomic publisher、真实 POSIX recorder 与真实 CLI/temp-storage smoke、Windows 对抗参数与真实 CLI nodes、错误码、扫描期
SIGINT 130、确认生成阶段不启动 live event stream、terminal exit mapping、Fins-owned missing / duplicate protocol error 保持既有 CLI prefix/message/exit 1、typed error object 与 runtime `PREPROCESS` provenance 经 Service/CLI identity 传播、SIGINT 到 operation-scoped async cancellation、
cancel race 收口、第二次 SIGINT 本地 130，以及 CLI 不直接 import `dayu.fins.storage`。
CLI runtime display controller 独立测试覆盖每个 prompt / interactive display lifecycle 私有的单线程 executor 与 async serial gate、activity / thinking typed callback、toggle / finish / cancel / local-exit / terminal renderer 的同线程串行执行、thinking guard、blocking callback 与 close barrier、callback / renderer / executor failure identity、closing 后拒绝新 job，以及 `callback_started -> close_requested -> callback_released -> callback_finished -> renderer close -> executor shutdown -> caller-local release` 顺序；renderer 与 executor 在重复关闭和异常路径都恰好关闭一次，不使用 event-loop default executor 或 UI event queue。除本节明确列出的真实 POSIX / Windows CLI 到 Fins 临时仓储 smoke 外，CLI 单元测试不启动真实 Host / Fins 业务路径；涉及 Host 状态机时使用 Service helper 与 mocked Host public API。
CLI import boundary 测试通过 AST 阻止 `session` command 从 `prompt` / `interactive` command 导入下划线私有符号，并阻止 `tool_trace` command 越过 Service public boundary 导入 Host、Engine、Fins 或 Runtime。
`tool_trace analyze` 测试覆盖 parser help/required/unknown action、真实 module entry、成功报告与退出码、usage/analysis/publication failure 映射，以及 partial publication 同时展示已发布路径与失败路径。

### `tests/runtime/`

运行时基础设施测试，覆盖 `dayu.runtime` 的层中立边界、取消 helper、diagnostic 文本 helper、digest helper 与日志装配：

- import boundary：阻止 runtime 反向依赖 Engine、Host、Service、UI、Fins 或引入运行期 HTTP 客户端，并显式确认
  `config_loader.py`、`numeric.py`、`location.py`、`scene_prepare.py`、`tools_discovery.py`、`assembly.py` 与 `tool_truncation.py` 被边界扫描覆盖。
- native mutex：覆盖 strict-native per-key 互斥的同进程与多进程竞争、busy 与 unavailable 封闭分类、handle 释放和层中立 import boundary；真实 Windows syscall 路径由对应 Windows CI 环境验证。
- numeric / cancellation：覆盖有限数值公共判断，以及取消等待 helper 的完成、取消、timeout/poll interval 非有限值拒绝与异常传播语义。
- interruptible process：覆盖 process-backed 子进程完成、terminate / kill、cleanup grace 校验、POSIX 安全进程组
  cleanup 清理嵌套子进程，以及 unsupported、PID / pgid 不可用、pgid unsafe、group signal 失败与 direct signal 失败时的
  direct-child fallback 诊断；partial start / post-spawn failure、process / queue cleanup checkpoint 首错、caller cancellation、
  concurrent close single-flight 与 retry-only-incomplete-step 使用 deterministic fake / barrier 覆盖，同一 failed handle 不恢复 start 权限。
- lane：覆盖 cross-process named semaphore / capacity guard 的配置校验、独立 SQLite runtime lane DB schema、acquire /
  heartbeat / release、timeout、协作式 cancellation、`Task.cancel()` 透传、controller close、跨进程 capacity invariant、
  close/acquire 并发下 pending acquire 唤醒、新 claim 拒绝、active claim count invariant、shielded claim / refresh / release
  遇到外层取消时的收口一致性、外层取消 cleanup 有界等待与 late result 观测、partial token release 后 remaining-token retry、
  concurrent close / caller cancellation single-flight、首次 close reason 与 heartbeat stop completion、TTL 时间真源不受 monotonic elapsed 前跳影响、release 后其它进程 acquire，以及 crash 后 TTL stale cleanup eventual acquire；测试不断言
  FIFO、公平性或 Host dispatch 集成。
- filelock：覆盖同步 file lock wrapper 的 parent directory 创建策略、禁用创建时的结构化错误、context manager 正常与异常路径 release、release 幂等、non-blocking timeout 包装、非有限 timeout 拒绝，以及第三方 `filelock` import 只能出现在 `dayu.runtime.filelock` 的边界。
- diagnostic text：覆盖层中立 diagnostic 文本中的 Bearer / API key / authorization / password / secret / token 敏感值检测、局部 value 脱敏、marker 字面替换、有界截断、空字符串 no-op、普通 token/header 诊断不误判，以及先脱敏再截断不泄漏原值。
- digest：覆盖层中立 UTF-8 文本 digest 的稳定 `sha256:<hex>` 输出形态。
- logging：验证 `dayu.runtime.log` 的 logger 装配、默认 stderr 诊断流、显式 stream override、CLI 风格级别解析、层中立 verbose / stream-debug / bounded payload key helper、`VERBOSE` / `STREAM_DEBUG` / `CRITICAL` 级别契约，确认普通 `DEBUG` 抑制 stream-debug 记录而 `STREAM_DEBUG` 同时输出普通 debug 与 stream 诊断，并验证 `dayu.runtime.log_levels` 只提供公共日志级别常量、不注册 stdlib logging level。
- config loader：覆盖 `models.json`、`execution_profiles.json`、`host_runtime.json`、`runtime_lanes.json`、`tool_discovery.json` 的 typed view 加载、workspace 同 id 整条替换、非 map 字段完整替换、严格 JSON 拒绝 NaN / Infinity / 浮点溢出、合法单继承链、missing / self / circular / multi / invalid `extends` 错误路径、catalog record 内重复 id 字段 fail fast、execution profile 上下文窗口分档校验、工具重复治理 decision allowlist、process capsule cleanup grace 有限非负数校验、完整 required wait poller policy snapshot 的十二字段投影、missing/extra/zero/negative/non-finite/type 错误与整数位 Python bool 显式拒绝、旧 execution profile 字段与旧 runner hint `max_tokens` fail fast、host runtime lane 引用校验、旧配置文件不读取，以及 packaged tool discovery 中 Fins raw config 不写 `workspace_root`、三个 awaiting provider 显式 `poll` mode、显式 Doc / Fins limits、`doc-tools.enabled=false` 和旧 provider-level `allow_empty` 字段拒绝。
- workspace paths / runtime location：覆盖 workspace root 下公共路径派生、相对配置路径 containment、`config/` 存在与不存在时的 `config_overlay_dir`，显式 config overlay 目录存在 / 缺失 / 非目录边界，workspace prompt assets 优先级，以及包内 prompt / manifest 默认资产缺失时 fail fast。
- tool call projection：覆盖 current `ToolCallable` 共享参数投影与 outcome 构造 helper，包括 schema default、类型收窄、unknown / missing / range / array item 参数失败、JSON typed enum equality（boolean/number 分离、有限 number 数学等价、array/object 递归）、default/显式参数同路径、构造后 mutable schema 负 count bound 防御、固定 `invalid_argument` failure、completed / failed outcome metadata，以及 Host cancellation token 对应的 `ToolCancelledOutcome(host_cancelled)`。
- scene prepare：覆盖单 scene 装配、system prompt 输出、fragment refs / source refs / digest、required context slot、未知 / 非字符串 placeholder、双花括号字面量保留、单继承、可选或继承的 model hints、旧 `conversation` / 泛化 `runtime` / 旧 model 字段 fail fast、typed agent policy override、fragment id / order 冲突、fragment path containment、missing required fragment fail-closed，以及 `all` / `none` / `select` 工具选择的 names、tags、并集、未知工具、空匹配和 `<when_tag>` / `<when_tool>` 条件块过滤语义；真实 prompt assets 测试确认条件块 marker 不进入最终 system prompt。
- tools discovery：覆盖显式 import path / package entry point provider 解析、禁用 provider 跳过、provider identity / source refs / 启用 provider 空工具输出 fail-fast、重复 provider / 工具名、reserved framework tool name 防线，以及 source refs 内容摘要规范化。
- assembly helpers：覆盖 runtime-neutral 四字段 model family identity、模型 / runner option hint 选择、typed allowlist override 解析、Agent policy 字段级优先级合并、工具截断 policy 默认值补齐、Fins packaged 缺省 workspace root 到 Service effective absolute `workspace_root` 的注入、Web storage state 目录按 workspace root 解析、raw provider config 不变性，以及 helper 返回值不构造 Host / Engine typed object；弱类型守卫显式确认这些 Phase 12 runtime helper 文件被扫描；`test_smoke_host_public_multiturn_assembly.py` 覆盖 Host public multiturn smoke 通过正式 Service assembly helper、内置 `manual-smoke` provider、workspace overlay provider、默认 fresh session slot、duplicate governance diagnostics 和 compact pressure 估算的成功路径；`test_smoke_host_public_conversation_memory_scenarios_assembly.py` 覆盖 Host public conversation memory 场景 smoke 的 `memory-core` / `memory-compact` / `memory-reactive-compact` / `memory-compact-fallback` suite 解析、pressure mode 参数、reactive deterministic recovery dispatch oracle、compact failure fallback selected window oracle、compact EventLog audit 摘要验收、compact operation timeline / rejected histogram / manifest missing stage 诊断、`CONTEXT_COMPACTION_FAILED` hard fail 语义、mock finance tool 装配、tool selection、pressure 文本和 slot key 语义；`test_smoke_host_public_r03_semantic_ownership_assembly.py` 覆盖窄 R03 smoke 的真实 Config / Scene / Service 装配、public `open_host -> ensure_session -> submit_followup` 命令链、固定真实工具轮次、durable projection 仅作显式 internal diagnostic read，以及异常输出的 secret 脱敏与长度上限 guard。
- scene asset migration：覆盖迁移后的真实 scene manifest 可被 `ScenePrepare` 装配，直接 fragment 引用可加载，`current_time` 与 `fins_default_subject` 的 source placement 和展开后 system prompt 顺序不打断 scene 执行契约，`current_time` 展开文本说明静态时间边界且不暴露内部实现术语，`get_current_time` 只在 interactive / wechat 场景暴露且工具描述说明实时刷新调用边界，旧
  `max_iterations` 落入新 `agent_policy` 且不迁移工具超时，base prompt 不混入未裁决占位段，并确认未迁移
  tasks、contract 文件、workflow 产物与未引用模板。

### `tests/service/`

Service composition 测试，覆盖 `dayu.service` 在 Host 外部把 runtime typed config、locations、工具发现、prepared scene、显式 override 与 env/secret mapping 映射为 Host public typed inputs：

- host assembly：覆盖 `host_runtime.json` 的 SQLite write retry、payload inline threshold、worker startup timeout、process capsule cleanup interrupt policy 与完整 wait poller policy 等 construction tuning 被映射进 `OpenHostOptions` / `HostToolingOptions`；wait policy 不再接受 Service override 或 scene authority，prompt / interactive 与 scene all/select/none 对相同 provider/runtime inputs 得到相同 opener 决策；execution profile 的工具重复治理 policy 被映射进 `HostToolingOptions`，primary default、ordinary invocation override 与 compactor selection 各自独立求值，primary/compactor resolved family mismatch 在 Host 打开前 fail closed，单次跨 family ordinary override 不改变 compactor，ordinary / compactor baseline 默认启用 OpenAI-compatible client correlation policy，静态 `X-Client-Request-Id` header 冲突 fail fast，provider secret 占位符在 Service helper 中解析，prompt asset path / 工具发现 source refs / provider location 边界 fail-fast，compactor scene 必填 AgentPolicy 字段校验，per-run helper 直接使用 `PreparedSceneInputs.system_prompt` 生成 `SubmitFollowupRequest`，以及 `ServiceRunOverrides` 到完整 `RunnerCallOptions` / `AgentPolicy` 的 typed override 合并。
- wait callback endpoint：覆盖 framework-neutral callback completion mapper 的 method / content-type / path-body wait id transport rejection、malformed outcome shape、裸字符串 `provider_status_ref` 拒绝、headers/body 到 Host callback envelope 的 typed 映射、completed / failed / cancelled / lost outcome dataclass 转换、Host adapter status 到 HTTP-like code/body 的映射、AUTH_FAILED 401/403 reason code 分类、缺失认证字段交给 adapter 分类，以及 response body 不回显 outcome result payload。
- entrypoint runtime：覆盖 reusable Agent entrypoint Service boundary 的 runtime 准备、Session ensure/create、session helper 参数校验、submit 前 async watcher subscription open 与 accepted target binding 时序、sole consumer、capacity-one generation slot、fast terminal race、无关 terminal 过滤、activity / thinking typed callback execution port、callback shield 与 consumer 串行读取、exact-five disposition、old-generation / stop late commit 拒绝、terminal identity 去重、`DELIVERY_INTERRUPTED/TRANSIENT_MAILBOX_OVERFLOW` 专属 durable recovery、其它 EOF / public / non-public iterator failure 不 recovery，以及 callback、EOF、iterator、terminal、delivery recovery、slot-empty、caller cancellation分别与 watcher close failure 的异常优先级；durable read 继续覆盖 `get_run`、`OutboxTerminalCursor` / `seen_terminal_event_ids` / `limit=50`、`CAUGHT_UP` 分页、`LAGGED` 重试、`FAILED` 与 caught-up-without-match 错误；interactive startup 覆盖 watcher-first session-scoped backfill、无 target 不预读、target generation ack/rebind、idle snapshot 后 tail outbox closure、active Run observation与 queued-only bounded promotion wait / failure；cancel 覆盖已终态跳过 `cancel_run(...)`、非终态 subscription-before-cancel、terminal race recovery以及完整 `CancelRunRequest` 构造。scene context slot builder 覆盖 `fins_default_subject`、`current_time` 中文格式、FMP 成功增强、缺 key 时跳过 timeout 校验和失败 fallback；interactive path 覆盖真实 `interactive.json` 的 subject/current-time slots、Fins awaiting poller assembly 和连续两轮 terminal wait state。
- Fins direct：覆盖 reusable Fins direct Service boundary 的 download / preprocess typed request 构造、upload wrapper 到 `FinsIngestionRuntime.upload(...)` union API、同一个 `ValidatedFinsEventStream` identity pass-through、progress / result contract、failure result pass-through、runtime stream exception 透传、Fins-owned typed protocol error object 与 runtime `PREPROCESS` provenance 不被 Service alias 重建、task cancellation 关闭 runtime stream、Service 不暴露 job handle / job event / `request_cancel` direct API，以及 direct event leakage guard。
- Fins awaiting assembly：覆盖 Service 在 active filtering 前按显式 provider id、import path、source id 识别 Fins download / preprocess / upload awaiting providers，把 raw config 只交给 Fins 唯一 parser，并以 required parallel typed state 复用 mode/workspace/source/version；覆盖派生 discovery 直接替换 tool bundle 后仍保留相同 Host binding、activation registry、poll registry 与 policy composition，以及 disabled illegal fail-fast、disabled legal 不 active、recognized non-awaiting 字段存在性 misuse、未知第三方 opaque config、available tool 缺失过滤、poll/callback/manual 精确 binding、activation 全量、poll registry 只含 poll、callback pre-open failure、manual/no-provider/provider-disabled/runtime-disabled 与 enabled missing-registry matrix。`test_fins_wait_adapter.py` 还覆盖 Service-owned adapter 的 operation-kind 稳定映射、activation runtime 复用、corrupt token fail-fast、Host `WaitAdapterSnapshot` 到 Fins observation status / transient unavailable / lost / failed / cancelled / abandon lifecycle 的映射，以及 adapter 不读取 Host durable row deadline / expiry 字段。
- Tool Trace analysis：覆盖四种显式 path discovery、ambiguous/unsupported layout、hot-only/cold-only/artifact-root-missing、Host public analyzer 调用与同一 report JSON/Markdown rendering、UTF-8 output，以及 JSON 第一次 replace 和 Markdown 第二次 replace 的 old-file 有/无矩阵；两个 replace 位置都覆盖 cleanup secondary failure，断言 primary `failed_path`、`published_paths` 与 cleanup detail 不漂移。
- import boundary / weak typing guard：阻止 Service 导入 Config、UI 或 Fins 非 assembly 边界；当前只允许 Service composition helper 与 `dayu.service.fins_wait_adapter` 导入 `dayu.fins.ingestion` lightweight observation boundary、`dayu.service.fins_direct` 导入 Fins runtime / request / enum / direct event public boundary，以及 `dayu.service.scene_context` 导入 `dayu.fins.resolver` / `dayu.fins.ticker_normalization` 生成 entrypoint slot 文本；并通过 AST 扫描禁止 `Any`、`object`、无类型签名与裸容器注解进入 Service 源码。

### `tests/contracts/`

公共协作契约测试，覆盖 `dayu.contracts` 的稳定边界：

- package exports：锁定包根 `__all__` 白名单，阻止未承诺符号泄漏。
- import boundary：阻止公共契约层反向依赖 Engine、Host、runtime implementation、Service、UI、Fins 或运行期 HTTP 客户端，
  并显式确认公共 source ref 契约模块被边界扫描覆盖。
- weak typing guard：通过 AST 扫描阻止 `Any`、`object`、无类型签名与裸容器注解进入公共契约源码。
- ToolExecutionOutcome / ToolResult / ToolCall 等契约测试：覆盖工具调用 provider state、工具结果信封、工具执行 outcome 封闭联合与穷尽匹配、工具等待时间字段时区边界、工具参数 schema key 边界、property/array-items 的 count bounds 构造期非 bool 非负整数校验和截断策略 limit key 映射穷尽性。
- tool declaration：覆盖最小 `@tool(..., truncate=ToolTruncateSpec(...))` 声明能力，确认 `ToolDefinition` / `ToolBundle` 只投影 `ToolSchema` 给 Engine，校验展示名非空，默认拒绝调用方直接构造空 `ToolBundle`，覆盖 execution capability 默认 async direct、thread-backed guard、process-backed context / target / JSON 信封 pickle round-trip，并覆盖框架 no-tool 路径使用的类型真实空 bundle。

### `tests/documents/`

共享文档基础测试，覆盖 `dayu.documents` 的层中立边界与轻量处理器 fixture：

- import boundary：阻止 `dayu.documents` 反向依赖 Engine、Host、Service、UI、Fins 或具体工具实现，并确认 Docling runtime、processors 子包与完整 source snapshot helper 被边界扫描覆盖。
- processors：使用确定性 fixture 覆盖 Markdown、HTML 与 Docling JSON 处理器的章节提取、表格读取与搜索片段输出；完整 source snapshot 测试覆盖声明长度不参与拒绝、实际来源复制到 EOF、独立 cursor、processor snapshot 接入、正常/异常/取消/resource failure cleanup、系统临时物化文件清理、单 snapshot 单物化路径复用和关闭状态约束。

### `tests/tools/`

业务工具与 provider 测试，当前覆盖原生 Doc tools provider、Web tools provider 与 combined tools acceptance：

- doc tools provider：覆盖 `dayu.tools.doc_provider` 通过当前 `ToolsDiscovery` 暴露五个原生 Doc tools、启用但缺失或空 `allowed_paths` 时以 Doc-specific `ValueError` fail fast、显式 limits 到参数上限和截断声明的投影、显式路径白名单拒绝、路径参数投影为绝对路径、路径验证失败不进入业务函数体、list/search 共用的稳定可取消 depth-first 目录遍历、创建顺序反转稳定性、目录 symlink 可见但不递归、file symlink 作为 list entry、`search_files` 对 allowed root 内 symlink 逃逸目标不读取、`read_file` 单行长文本/多编码/range/完整 source/cancellation、`list_files` 完整 `total` / `scanned_entries` 与有界返回、`search_files` 仅保留 result limit partial、late query chunk scan、processor snapshot 和 bounded excerpt、默认运行的真实 10,001 小文件与 33 MiB 以上尾部 marker smoke、LLM-facing 输出字段说明、current success / failure / cancellation outcome 投影、Markdown / Docling JSON 章节列表 / 搜索 / 章节读取、current `ToolTruncateSpec` 暴露、五个 Doc tools 的 process-backed execution 声明、process target 可序列化与子进程内路径校验，以及 current ToolRuntime accept barrier / cancel 后 late result 不接受集成。
- web tools provider：覆盖 `dayu.tools.web` 通过当前 `ToolsDiscovery` 暴露原生 `search_web` 与 `fetch_web_page`、`fetch_web_page.url` schema 自足说明完整 `http/https` URL 及优先复用 `search_web` 结果、packaged Web 五个独立 bool 与 HTTP/browser/diagnostics 三组 typed budget defaults、合法 final partial record 的逐字段/group default、顶层 typo 与 nested unknown/invalid 的精确路径拒绝、private/custom-port 同源 `WebEgressPolicy`、显式 deny、HTTP redirect / meta refresh / Playwright request 继续导航前复用 safety owner、fetch body wire / decompressed 上限的结构化失败投影、ordinary fetch failure 消费本次 config snapshot 的非默认 diagnostic error cap、diagnostic error cap 为 `1` / `14` / `15` 时的有界可观察截断和未超限无误报、probe 无 budget、browser worker 只接 browser budget 且 process wrapper 独立接 diagnostic budget、diagnostic utility HTTP/Browser 常量直接复用 typed owner defaults，以及 diagnostic Playwright response body 的 HTTP child exact/declared-over/actual-over direct node。HTTP transport owner 测试覆盖每 attempt 只 prepare 一次、同一次 merged settings 原样进入 proxy selection 与 send、proxy allow/deny、numeric peer match/mismatch、proof + active proxy typed incompatibility、redirect 每跳重授权，以及 Tavily/Serper/DuckDuckGo 通过同一 plain sender 接收 egress/transport policy并保留 challenge/result 语义；browser 测试覆盖 capability/private permission 双向解耦、private subrequest route 拒绝、browser disabled 零启动、proof incompatibility 在 process 前失败、安全 LLM-facing 投影，以及 worker proxy 环境的继承/清理。diagnostic utility 不再拥有 credential lifecycle、输出/TTL CLI、private CLI overlay或本地 diagnostic 默认：未提供 `--max-network` 时直接消费 typed `DiagnosticResourceBudget.events`，显式正值形成单次 typed override，错误文本上限同源于 `DiagnosticResourceBudget.error_chars`；raw Playwright 只读显式 `--storage-state-in` 常规 JSON object 文件，`--storage-state-dir` 只交给 production resolver，artifact 只投影 `input_used` 且普通 writer/schema v2 保持。其余覆盖包括 Web diagnostic schema v2 对正文/HTML/stdio 只保留 length + digest、safe URL 删除 userinfo/query/fragment、响应头只保留存在性与受限语义、显式 storage input 的可读/缺失/非法矩阵、搜索 optional 参数与 provider config 闭包投影、fetch truncate config 与 Playwright fallback channel / storage state config 投影、非法 URL 类型进入 Web 逻辑前失败、current success / failure / cancellation outcome 投影、current `ToolTruncateSpec` 暴露、provider 级串行策略，以及基于 AST import 解析确认未导入 OLD registry / truncation / `fetch_more` / UI。
- combined tools acceptance：使用确定性 workspace config 同时启用 Doc、Fins 与 Web providers，覆盖单一 `ToolBundle` 聚合、reserved `fetch_more` 防线、current `ToolTruncateSpec` 暴露、current ToolRuntime 注入并拥有 framework `fetch_more`、Service assembly 将 effective bundle 传入 Host、三类 provider 代表工具通过 ToolRuntime accept barrier 执行、代表性失败投影为 current outcome、ScenePrepare 可按 `doc` / `fins` / `web` tags 选择工具，以及 Web provider 串行策略在并发 callable 下生效。

`tests/tools/fixtures/documents/` 存放工具 provider 测试使用的确定性文档 fixture。当前包含 Markdown 与 Docling JSON 样本，测试应复制到临时目录后通过 provider 白名单访问，不直接把 fixture 根作为隐式生产路径。

`tests/tools/web/` 的 Web provider 测试必须保持 deterministic：搜索 provider、requests 主路径和 Playwright fallback 默认都通过 monkeypatch / fixture 替身控制，不做 live network 请求；Playwright raw worker cleanup 默认覆盖使用 synthetic nested child 验证进程组清理边界，不依赖真实浏览器 binary。显式设置 `DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1` 时，才运行 optional/manual live browser cleanup smoke，并按环境能力 skip。
Web live smoke 位于 `utils/smoke_web_ci.py`，不在默认 pytest 中运行；直接运行该脚本会启动与父进程内存 ledger 共生的本地 fixture server，为 HTML requests/tool、PDF requests/tool、Playwright、challenge control、版本化 AAPL filing HTTP/Playwright 与 local assembly config 各生成唯一 256-bit query sentinel。版本化 fixture 由模块级私有常量直接指向 `tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928.htm`，缺失或不是常规文件即 hard fail；filing artifact 写入 `diagnostics/filing/`，真实 Playwright 读取本 run 的空 storage-state JSON 显式输入并记录 bytes、DOM/text、network events 与 `input_used`，不生成 credential output。handler 只追加 token digest、method、normalized path、response kind/digest 与 accepted/rejected；server 停止后先 freeze ledger 再分类，PASS 同时要求唯一 accepted request、父进程 expected bytes 与 artifact length/digest 相等、必需 backend execution evidence，以及 missing/wrong/HEAD-method/replay/unknown-path 负控全部被拒绝。local assembly config case 通过完整 `ConfigLoader.load()`、`assemble_effective_tool_provider_configs()`、`discover_service_tools()` 与 `ToolDefinition.callable` 验证 Web overlay config 和 `truncate_max_chars`；private deny 与 custom-port deny 以两个独立 typed provider overlay 进入同一链并要求 `permission_denied`，packaged default local cases不传旧 private CLI。默认还会从 `utils/web_ci_urls.jsonl` 采样 2 个 external URL 作为 diagnostic-only 输入，并运行 `auto` / `tavily` / `serper` / `duckduckgo` 四个 `search_web` provider diagnostic-only cases；运行时会打印 `SMOKE ...` UI 摘要行并按 `--log-level` 输出诊断日志，默认日志级别为 `debug`，但会压低与 Web smoke 判断无关的装配、抽取库和工具内部 debug 噪音；传 `--external-limit 0` 可跳过外部 URL fetch，但 search provider diagnostics 仍默认运行。`tests/tools/web/test_smoke_web_ci.py` 确定性覆盖 ledger lifecycle/freeze、每 case 唯一 sentinel、负控、schema v2/no-fallback、版本化 fixture 常规文件/执行、显式输入、独立 deny、synthetic success 不得自签 PASS、summary contract、typed `search_cases` 与 external diagnostic-only 边界。

### `tests/fins/`

财报仓储、Fins read tools provider、Fins ingestion awaiting providers、ingestion runtime 与 SEC / CN / HK download/upload pipeline 测试，覆盖 `dayu.fins.storage` 文件系统仓储协议实现、external ticker/document ID 在 source/processed/blob/rejected/registry namespace 的 exact opaque mapping round-trip 与 descriptor fail-closed、filename/primary/object key/local URI 的单路径组件及 containment/symlink 安全边界、显式 `BatchToken` authority、batching-only lifecycle、全部 mutation required `batch=`、跨 task/thread 显式 token 与跨 core/关闭 token 拒绝、同 ticker writer mutex、source/blob/processed/company/maintenance shared core、blob-first 且 published source 在 commit 前缺席、一次 complete-source commit 后 meta/files/blob/primary/provenance/manifest 与 persisted opaque revision 同时可见、source mutation 换 token而 rollback/non-source batch 保留 token、light/full snapshot 的 identity/meta/provenance/revision/files/primary 同版、显式 source kind 与另一 namespace 同 document ID 共存、真实双文件 A/B publication、transient recovery、持续变化耗尽 storage 内部预算后的 typed failure、symlink/meta mismatch/silent inode mutation 分类、full snapshot 临时资源和 FD cleanup、processor cache 初始 miss 并发单构建、replacement/eviction/clear/runtime close 的 borrow-retire cleanup、processor/result/citation 同 snapshot provenance、acquire/release/copy/marker/cleanup 双失败的 primary preservation 与完整 path-free exception graph、commit validator 对不完整 source/false completion/symlink/escape 的拒绝、commit 前失败或取消 exactly-once rollback、commit 开始后 caller 不二次 rollback、在线长 staging/validator 不阻塞 published reader、两次 rename 窗口 publication guard 只允许完整 old/new、fresh filesystem 各 crash phase recovery 与未提交 staging 清理、download/upload overwrite 失败/取消/空结果保留旧文档、source document provenance 投影与 citation `source_type` / `source_provider` 输出、确定性财报 fixture 的 list/read、`dayu.fins.tools.provider` 通过当前 `ToolsDiscovery` 暴露带 `fins` tag 的九个 read tools、九个 definition 共用同一 ticker 语义，其中八个文档读取 definition 共用“只接受同 ticker 的 `list_documents.documents[].document_id`、切换 ticker 后重新选择”约束、四个 Fins provider 启用时要求 effective absolute workspace root、read provider 只暴露 read tools、九个 read tools 的 process-backed execution 声明、process target factory / target pickle round-trip、process target 子进程内通过 `DefaultFinsRuntime` 重建只读 runtime并在成功/失败后关闭、九个工具 completed/failed/cancelled nested 输出不暴露 revision/private key/local URI/temp path、fast / processor / table path、failed JSON 信封和 ToolRuntime 取消真实 Fins process target 后不接受 late result、显式 limits 到各工具截断声明的投影、`list_documents` 与 `search_document` 通过当前 ToolRuntime accept path 执行、数组 / 标量参数投影、current success / failure outcome 投影、current `ToolTruncateSpec` 暴露、workspace overlay 独立启用 read / download / preprocess / upload providers、download / preprocess / upload 独立 provider discovery、upload provider 启用时默认注册上传工具、awaiting callable 的 `EXTERNAL_JOB` outcome、awaiting callable 启动前观察 cancellation token 并返回 cancelled outcome、upload 缺失文件、目录、空文件与 delete 带 files 在 observation start 前失败、workspace 外本地文件可启动 upload observation 且启动记录仍落在 Fins workspace、Fins lightweight observation handle / snapshot / runtime contract、参数错误到 current failure outcome、SEC downloader 的无网络 HTTP/解析/限流 helper、SEC pipeline 的 skip / overwrite / cache / 6-K / SC13 / rejection artifact / stream 语义、SEC/CN/HK production persisted-summary adapter 消费 `rebuild_processed` 并标记既有 processed 需重处理、CNInfo / HKEXNews downloader 的无网络 HTTP/解析/PDF 校验语义、HKEXNews 官方 `hasNextRow/rowRange/loadedRecord/recordCnt/result` exact 类型、initial-100 cumulative 续取、latest-count 扩容、final snapshot replacement、矛盾/无进展 typed provider failure、HKEX GET 与 CNInfo 财期 POST 前后 checkpoint 顺序及取消后 partial 零发布、CN/HK report selection helper 的候选筛选 / 语言过滤 / 财期推断 / 去重语义、CN/HK pipeline 的 blob-first complete-source commit、PDF gate、fast skip、独立季度缺失 skipped、runtime CN/HK auto adapter 语义、DoclingUploadService 的 create/update/delete/skip/overwrite、SEC/CN upload stream 的 filing/material id 与 source/blob 写入、DefaultFinsRuntime production upload runner 的 SEC/CN direct runtime stream 终态，以及基于 AST import 解析的 Fins / Engine / runtime import boundary。

Financial/XBRL contract 测试还覆盖 producer exact keys 与可选 reason 矩阵、原始 payload/list/fact 深层不变、扁平 query params、稳定去重和唯一 `fact_count=len(facts)` 公共投影；真实 AAPL XBRL、HTML 财务表、无目标报表与截断续读场景同时验证 process-backed 输出，以及 processor 结果与 citation 始终来自同一 borrowed snapshot。

SEC pipeline 测试还覆盖取消检查器贯穿 submissions history、Browse EDGAR、index/header/candidate collection 与单 filing 文件处理；collection 阶段命中取消时必须停止后续 filing 请求并产出 cancelled stream 终态。

`tests/fins/test_fmp_company_info_resolver.py` 覆盖 FMP 公司信息 resolver public contract：显式 API key / timeout、`search-symbol` 到 `search-name` 两跳算法、严格同名过滤、alias 去重且 canonical ticker 位于首项、不可变 tuple result、HTTP / timeout 包装、`search-name` 第二跳失败包装、非法 JSON、非数组 payload 和空结果失败路径。S3 aggregate 验证还要求对配置、CLI、tests 与 utils 执行旧入口身份 slot 字面残留扫描。

`tests/fins/test_fins_ingestion_tools.py` 覆盖 `dayu.fins.tools.download_provider`、`dayu.fins.tools.preprocess_provider` 与 `dayu.fins.tools.upload_provider` 的独立 ToolsDiscovery provider report、独立 provider id / spec id / tool name、唯一 `poll/callback/manual` enum/parser 的精确值，以及缺失/null/错类型/空串/大小写/空白/未知 mode 拒绝；三个 direct provider 都在创建 runtime 前校验 mode。文件同时覆盖 download / preprocess / upload 工具 schema 不暴露 Host 内部治理字段、工具调用注册 lightweight observation handle 后返回 `ToolAwaitingOutcome(EXTERNAL_JOB)`、启动前 cancellation token 已取消时返回 `ToolCancelledOutcome` 且不注册 observation、upload provider 启用时注册上传工具、upload 缺失文件、目录、空文件与 delete 带 files 在 observation start 前返回失败、workspace 外本地文件可启动 upload observation 且启动记录仍落在 Fins workspace，以及 provider 创建的不同 runtime 实例通过同一 workspace 派生 runtime 能力。本文件还覆盖 lightweight observation handle contract：resume token 只承载 opaque handle id、corrupt token / missing process-local observation source 分类为 LOST、observation status 到 wait resolution 的中立映射固定、snapshot terminal / retry-after 字段组合校验，以及禁止 handle / message 暴露 job、sequence、cursor 或 storage path。

`tests/fins/test_fins_direct_stream.py` 以真实 `async def` generator 和独立 typed observation state 覆盖唯一 Fins validator owner：progress 顺序、RESULT 缓存至 clean exhaustion、missing / duplicate / event-after-result typed reason、result-then-error 不泄漏 success、upstream exception/cancellation object identity、`GeneratorExit` / `finally`、primary 与 cleanup close failure chaining、显式/repeated close 至多一次，以及 `terminal_result` 在 OPEN / RESULT_BUFFERED / abortive / clean 四类状态的 availability 与同一结果实例。`tests/fins/test_fins_ingestion_runtime.py` 覆盖 workspace-scoped ingestion runtime：cross-runtime shared workspace job store、legacy download / preprocess / upload queued job persistence、ticker normalization、DefaultFinsRuntime 为 US 的 `sec` / `auto`、CN 的 `cninfo` / `auto`、HK 的 `hkexnews` / `auto` 装配 production download adapter，并为 SEC/CN direct runtime upload stream 装配 production upload runner、legacy download / preprocess / upload 在 durable create 后、executor submit 前观察 cancellation token 并标记 job cancelled 且不提交后台操作、direct download / upload stream 产出 `PROGRESS` 与唯一 `RESULT`、consumer abort 经真实 raw bridge `finally` 请求 operation cancellation 且 late progress 不再可见、download adapter progress sink 到 direct event 的投影、download summary 展示避免 skipped/rejected 重复表达同一批拒绝项、direct stream 不创建 durable job record 或 sidecar、direct stream 使用 operation-scoped cancellation token/checker、direct 用户事件不暴露路径、job id、raw provider payload 或正文、runtime raw bridge 只转发 producer 事件并由 public plain-def API 接入唯一 validator、upload `SourceKind` filing/material 分流、upload 默认缺 runner 时的 unsupported terminal failure、upload request / result bounded summary、upload pipeline typed result 必须显式提供状态、无网络 fake download adapter 写入 source/blob 仓储、unsupported source failed terminal、重复下载按 storage 语义跳过、rejected filing artifact 通过 maintenance 仓储保存、preprocess source -> processed pipeline、已有 processed 跳过 / 重建、missing document failed terminal、preprocess typed status helper、unsupported processor not_supported summary 与 skipped 计数分离、cancel transition、prepared observation cancel 后 abandon 不提交后台操作且释放 handle、submitted observation abandon 触发协作取消并保留已写入仓储产物、record leakage boundary、legacy job store 原子写入失败清理、legacy ingestion job event sidecar 的 queued/running/terminal/status observation 序列、download / upload 同步调用边界与 preprocess 文档处理路径的粗粒度 `PROGRESS` event、`read_job_events(...)` 游标读取、bounded payload 与敏感内容不落 sidecar、并发 sequence 分配、非法 payload 拒绝、non-terminal、terminal 与 progress event append failure 的 WARN-and-continue 行为，以及新增 ingestion runtime 不破坏 read provider / `FinsReadRuntime` 懒加载行为，并验证 DefaultFinsRuntime close 幂等、不会为清理触发 read runtime 惰性创建且关闭后拒绝新 read runtime。

Fins fixture 由测试通过仓储 public API 写入临时 workspace，不依赖隐式 cwd、环境变量或手工拼生产路径。

### `tests/host/`

Host 公共 API 类型、Session / Run public command facade、construction tooling options 与内部 durable foundation 测试，覆盖 `dayu.host` 的稳定边界：

- Session attachment 与恢复：registry 单元测试覆盖同一 handle 重复 attach、read-write / read-only mode 冻结、mutation / new-work lease drain 和 close；public / multiprocess 测试覆盖相同与不同 Session 的跨 opener 竞争、read-only mutation 在任何 durable write / wake 前 typed reject、target-only fixed-watermark recovery、incomplete proactive operation 恢复，以及旧 owner detach 后由 fresh read-write opener 继续目标治理。active cancel / transition / public attachment 联合测试覆盖 fresh opener 接受 cancel 后原 execution owner 按 required Session id 与 exact Attempt / execution / dispatch identity 传播 token / hook，即使 durable watchdog 已先终结 Run 也不丢 cancel link；stale identity 与非法 linked event 均 fail closed，且不存在 workspace-wide tick / wake。
- wait resolution identity：public completed / failed / lost 路径断言 `TOOL_RESULT_ACCEPTED` 归属挂起 source Attempt / execution；direct resume / terminal transition 覆盖 WaitRecord / source Attempt execution mismatch 返回 `INVALID_STATE`，且 EventLog、Run、Attempt、WaitRecord、dispatch record 五张 durable 表完全不变。
- package exports：锁定 `dayu.host.__all__`、`dayu.host.api.__all__` 与 Host 内部 typed contract 模块级 `__all__` 白名单，确认 command facade / tooling 类型与 `HostUnavailableDetail` 的公共导出边界，并阻止 memory / context fallback 私有 helper 泄漏。
- public contracts：验证 status / error 枚举字符串值、frozen slots dataclass、结构化 `HostApiError`、request validation failure paths、`HostCommandHandleOptions` 必填 context window / reserved output budget 输入与 command-to-local execution composition wiring，以及 Host construction storage 字段通过 durable owner 的唯一 typed helper 精确投影为 payload / SQLite policy。
- memory projection：覆盖 Conversation Memory 只消费 LLM-facing 普通对话、自解释工具证据与 compact 事实，`TOOL_RESULT_ACCEPTED` evidence item 通过 Host accepted result projection 取得同源 exact request / query、状态、结果摘要与业务 source 语义，并确认缺少 semantic query 时合法 `file_path` / `scope_token` / password-like 业务字段仍按 canonical arguments 机械展示；缺少 projection 字段时 fail closed 而不从 payload 重建，ambiguous raw result 不丢查询意图；`TOOL_AWAITING` 不产生独有 memory 语义，不把 waiting lifecycle、取消、poller 或 abandon 治理文本投影给模型，并确认 durable memory consumer 不订阅 awaiting 事件。
- command handle / public session API：覆盖 Host command handle factory fresh DB、稳定 public handle id、默认 active registry 不跨 handle 共享、内部依赖不暴露、close 幂等、关闭后 facade 稳定失败，以及 `ensure_session` / `create_session` / `get_session` / `list_sessions` / `close_session` 的 snapshot、列表摘要、空库边界、slot row 解码 fail-closed、幂等、冲突、NOT_FOUND 与保留 durable truth 语义；覆盖 `purge_session` 对已关闭且全部 Run 终态 Session 的 tombstone result、幂等重放、同 key 不同语义冲突、不同请求访问已 purge Session 冲突、append-only audit JSONL 的 `purge_started` / `purge_completed` / best-effort `purge_failed` 语义和 purge 后 read path `NOT_FOUND`；`test_storage_usage_report.py` 覆盖只读 `report_storage_usage` 的 fresh DB 零计数、Session / Run / payload descriptor / SQLite payload row count、logical bytes、orphan SQLite payload 诊断计数、DB/WAL 文件大小、async `open_host` handle 入口、closed handle 错误语义与 `json_value()` 键集合；`test_storage_orphan_proof.py` 覆盖 artifact descriptor 引用证明、shared descriptor 去重、projection lag 下 descriptor truth、`sha256/` namespace 安全、grace 过滤、稳定排序与物理 artifact size；`test_storage_maintenance.py` 覆盖 dry-run maintenance 不删除文件或 SQLite row、orphan 候选、物理 artifact bytes、WAL checkpoint on/off、EventLog/Session/Run 状态不变、async `open_host` handle 入口、closed handle 错误语义，以及 opt-in orphan artifact reclaim 的删除成功、共享引用保留、删除前 recheck 跳过、单文件错误诊断与幂等。
- public durable actor / HostAdmin / execution health：`test_durable_actor.py` 覆盖 command handle、真实 SQLite store / connection 的单 worker thread ownership、scheduler / actor connection identity 与 PRAGMA 同源、caller cancellation 后底层 future 继续、FIFO 与 bridge exception 透传；`test_public_host_admin.py` / `test_host_admin.py` 覆盖 execution/admin Protocol 分离、admin graph 无 scheduler / recovery / lane / worker / scene / tool / model secret、accepted / queued / recovering durable facts 不变和幂等 close；`test_scheduler_health.py` 与 `test_open_host_runtime.py` 以 Event / actor barrier 覆盖 STARTING/READY/UNAVAILABLE/CLOSING/CLOSED、admission-first、fatal-first、caller cancellation、public command/read/cancel 分流和 commit+wake-before-fatal，并继续覆盖 `BEGIN IMMEDIATE` 下 opener loop 前进、scheduler wake / active cancel loop bridge、startup recovery actor/READY handoff，以及 actor wake barrier 后的 scheduler -> projection -> actor handle -> executor -> scheduler store close order；`test_active_cancel_dispatch.py`、`test_dispatch_scheduler.py` 与 `test_admission_multiprocess.py` 覆盖 watchdog level Event 的 clear/set、tick 内 second wake、并发 wake 合并、unexpected fatal、真实 actor 到 opener-loop event/token/hook bridge、single-write cancel 分类、多进程 write-snapshot race和 promotion wake 幂等；`test_recovery_scan.py` 覆盖 fixed policy time / upper watermark、`(accepted_event_sequence, run_id)` keyset、bounded page transaction、commit 后 wake、第 2 批 rollback 与 durable 全量重跑，以及 ACCEPTED / QUEUED / WAITING / accepted-cancel 分类不漂移；CLI session list/purge 覆盖全部模型 API key 缺失时的真实 admin 路径。
- public run / wait / event API：覆盖 `_start_run` 内部 admission primitive / 低层测试路径的 accepted pre-start / attachment active conflict / 幂等重放 / 幂等冲突、`submit_followup(queue)` active 与 no-active 分支、`submit_followup(steer)` active RUNNING 新 Attempt / 幂等重放 / `SteerConflictDetail` 负面详情、typed prompt request contract、per-run `tool_names` 全量 / 禁用 / 子集 / unknown 拒绝、per-run runner config field-level partial merge、effective config / tool set freeze、effective tool display snapshot、重复 `(session_id, client_request_id)` 返回同一 accepted Run、`watch_session_events(session_id)` 的 async subscription 与 public closable iterator、durable `HostEvent` / live-only `HostTransientDelta` 联合流、successful return 前完成 cursor transaction 与 subscription reservation、subscription 建立前不 replay、三类 delta typed projection 与 EventLog 零 row、双 watcher terminal、retained item prospective check、唯一 in-flight 计数、慢 watcher typed delivery interruption 与快 watcher/terminal/Run 隔离、per-Session reservation cap 并发线性化与 subscription close 后 readmission、factory cancellation / Host close / iterator allocation failure释放、terminal fence、never-started / missing / 取消 / close、durable read failure public 映射、terminal 后下一 Run、consumer early cancel 不取消 Run / 不写 EventLog、final answer 只能从 terminal HostEvent typed view 取得、FAILED / CANCELLED / LOST terminal typed display fields 与 public event identity、Host activity event projection 的 tool call / tool result / tool batch / provider diagnostic / unknown / delta 边界、target recovery 后通过 watch 观察 final answer、production wait poller 全十二字段显式 policy / poll registry construction wiring、无 policy/disabled 不启动、enabled missing registry fail-closed、background poll resolve、wait poller 正常 observe / resolve / summary 状态链日志、not-ready 短间隔复查且不增加错误 backoff、纯 poll 无 wakeup 仍按 policy cadence 观察 ready、新 wait wakeup 打断 idle、空轮询不逐轮刷 summary 日志、poll observation timeout 只撤销发布权并释放 claim/backoff、迟到 Ready 不可 resolve、cancelled abandon timeout 保持可重试且不写 terminal marker、cancelled WAITING wait external lifecycle applied / unsupported / noop / error / missing-adapter / CAS / late-result 处理、wait lifecycle outcome schema、poller-before-scheduler close 与 open failure cleanup、handle closed / missing Session / Session CLOSED watch 语义、`HostEventView` 与 run-level `stream_run_events` 不在包根 public namespace、ordinary local `retry_run` FAILED 源关联新 Run / 缺失源 NOT_FOUND / 幂等冲突、`replay_run` SUCCEEDED 源关联 no-tool 新 Run / 缺失源 NOT_FOUND、`cancel_run` accepted / queued / pre-dispatch STARTING / injected active worker registry / WAITING / RECOVERING、`cancel_session_runs` 的 accepted / queued / pre-dispatch STARTING / injected active worker registry / WAITING / RECOVERING 子集、幂等重放、不影响其它 Session，以及 `resolve_wait` completed resume / tool-cancelled resume / failed closeout / lost closeout / late diagnostic / 等待时间边界 owner 判定 / 同 outcome 不受 `observed_at` 变化影响的幂等重放 / 不同 outcome 幂等冲突；`test_transient_delta.py` 用 deterministic barrier 覆盖 publish-before-wait、wait-before-publish、单项 pop/clear 与 publish 交界、overflow / close wakeup、accepted prefix、快慢 watcher 隔离、reservation cap 和低基数日志；`test_wait_callback.py` 覆盖 framework-independent callback adapter 的 auth-first、payload digest、unknown wait、等待时间边界委托给 resolve owner、late cancelled / lost、idempotent replay、same-key conflict、dispatch wakeup、EventLog 不变性，以及 callback digest 与 direct resolve digest 的共享 material 对齐；`test_wait_expiry_closeout.py` 直接覆盖 common expiry helper、FAILED terminal facts、commit 后 projection/promotion 与 result/cancel/expiry 多进程 first-committer race；`test_wait_observation_runner.py` 以 Event/barrier 覆盖 observation timeout 后 `WAITING` retry、token invalidation 后迟到发布丢弃、outstanding cap、cancelled abandon timeout retry，以及 poller loop 与两个 provider 共用单一 close deadline且最后线程结束前保持 `CLOSING`；`test_wait_poller_runtime.py` 覆盖全部 policy 字段构造时必填、finite/positive/type validation、drain_once、background backoff、idle 空轮询间隔、可取消 sleep、close 幂等、shutdown-skipped retry、有界 close drain timeout 诊断、可恢复 round error diagnostics 与 fatal self-close diagnostics。
- provider request identity / runner-call manifest / Tool Trace correlation：覆盖 Host effective execution config freeze / restore 保留 `RunnerSpec.client_correlation_policy`，并在恢复 typed config 前校验 config digest、policy snapshot digest 与 ref；RunInputBuilder 把 Attempt `attempt_id` / `execution_id` 投影到 `AgentRunRequest`，reactive compactor request 传递 Attempt / execution 而 proactive compactor request 保持二者为空；compactor proposal manifest 区分首次 proposal trigger reason 与 retry trigger reason；ordinary、Engine continuation 与 compactor 的 runner-call hot owner contract 覆盖 0 / 1 / 12 / 300 messages 下固定 key、无数组、有界 bytes、显式 complete diagnostic 与完整六字段 projector metadata，shared hot parser 对缺失/空/畸形 diagnostic、旧 metadata array、status/count/digest 冲突全部 fail closed；Engine iteration started 覆盖由真实 messages 角色顺序计算的 role sequence digest、serializer schema version 与中性 input projection，并断言 continuation message metadata ref 在 manifest 内闭合；Engine ingest 覆盖 failed terminal、recoverable failure diagnostic、context compaction request / recovery closeout、provider protocol diagnostic、iteration completed preview 中的 `provider_request_id` / `client_correlation_id` payload、ordinary prepared manifest 到 `RUNNER_CALL_INPUT_ITERATION_LINKED` 的显式关联、runner-call manifest signal validation、missing / ambiguous / mismatch / link conflict fail closed、continuation reset limited-signal durable scope、携带 observed projection 的 continuation-owned limited-signal manifest（projection 完整时 diagnostic 可为 complete），以及 tool-call requested preview 的 normalized arguments digest；accepted result projection 使用真实 outcome codec fixture，覆盖 accepted 工具结果的 query / status / result typed projection、精确 `result.value.citation` object 的全量 canonical 渲染、未知 citation member 保留、无 citation / 拼错 / 非 object 的统一中性 unavailable 文案、opaque envelope provenance round-trip 及四消费者不可见，以及 Tool Trace、Memory、RunInputBuilder、CompactMaterial 的 canonical text equivalence；四个消费者还覆盖 canonical request envelope / link / row / identity / digest 或 typed LLM material 缺失、损坏或漂移时统一抛出 `HostDurableError`，且不继续发布 snapshot、compact 或 trace；Tool Trace projection 覆盖 `TOOL_CALL_REQUESTED` 通过真实 EventLog row 和 strict request atom 解析 inline / descriptor canonical arguments，并对 missing row、wrong event type、storage conflict 与 digest mismatch fail closed，hot `trace_summary_json` 与 cold JSONL `trace_summary` 暴露 `client_correlation_id`、缺少 provider request id 时保留 client correlation fallback 且 provider id 查询不误命中、复制 runner-call manifest read-model signal 与 typed complete / non-complete diagnostic、缺失 typed diagnostic fail closed、mismatch diagnostic、按 Run 查询 complete / limited_signal / mismatch typed reconstruction signal、resolver 恢复 runner input projection / artifact projection payload / selected tool schema snapshot / tool args / tool result payload / terminal final answer、resolver 对调用方 / descriptor / SQLite row / artifact bytes 的 ref / digest / size、canonical JSON object 与 artifact containment 完整 fail-closed 矩阵、真实 300-message producer manifest 的 metadata summary 重建，以及 incomplete manifest、悬空 metadata id、未知 projector/purpose/schema 与 hot/manifest identity mismatch 的 full-graph fail-closed 矩阵；同时覆盖 context pressure / tool timing / failure metadata 结构化 signal、provider request id 查询结果的 trace summary 保留客户端关联字段，以及 Tool Trace readable request / result 保留 exact arguments、不执行字段名脱敏、大工具参数 descriptor ref / digest 只留内部 row 且不进入 readable summary。
- public-path smoke：`test_public_open_host_multiturn_smoke.py` 覆盖 real-runner no-tool 两轮、deterministic 两轮 final answer continuity、multi-client watch 与 queue idempotency；`test_public_tool_wiring_smoke.py` 覆盖 mock business tool wiring、accepted tool fact 到下一轮输入、`tool_names` 子集 / 空集合冻结，并对记录到的 runner call messages 校验最多一条 system message 且唯一 system 位于首位；`test_public_steer.py` 与 `test_public_resolve_wait_resume.py` 通过 `open_host(options)`、mock awaiting tool 和 public command 覆盖 WAITING Run 的 steer / resolve_wait；`test_public_cancel_smoke.py` 覆盖 pre-dispatch / active / RECOVERING / session-scoped cancel 与 close 边界；`test_public_compact_smoke.py` 覆盖 no-compaction recent raw continuity、deterministic public opener proactive compact、reactive compact recovery attempt、compact failure 后 deterministic recent-window fallback dispatch、proactive material JSON 中 raw accepted tool evidence 进入 `evidence_material` 并由 fake compactor 生成后续可复用 vNext fact、vNext reference continuity 后续解析、多次 compact 后 memory / compactor input bounded、重复长 prompt 不因 compactor material 重复超窗失败、compactor proposal runner-call manifest bounded 且不内联重复长正文、manifest 的 message_count / message_entries / role sequence digest 同源、默认 compactor prompt 和 material 不暴露内部实现术语且自足说明输入输出，并保留 material-label fake proposal 对 raw accepted evidence block 到 fact candidate 的 helper-level 提取边界；`test_public_real_runner_matrix_smoke.py` 覆盖 mimo、deepseek、gemini、qwen 的 real runner public path。public smoke 需要等待非展示型调度事件时，只能通过 `public_smoke_support.py` 的集中 helper 作为测试同步 primitive，结果断言仍使用 public snapshot / HostEvent。real runner smoke 只允许按 provider 缺少 secret、endpoint / 网络不可用、临时不可用或 quota / rate-limit 给出精确 skip；real compactor smoke 默认跳过，只有设置 `DAYU_RUN_REAL_COMPACTOR_SMOKE=1` 才运行；测试专用 deterministic compactor 位于 `tests/host/fake_compaction.py`，测试专用可控 cancellation token 位于 `tests/host/fake_cancellation.py`，生产代码不得导入。
- public awaiting entrypoint smoke：`utils/smoke_host_public_awaiting_entrypoint.py` 通过 packaged ConfigLoader、provider discovery、Service composition、`open_host` 与 public submit/wait/outbox 路径，校验三种 typed awaiting mode、packaged 十二字段 policy、单次 Run 的命名握手预算、外部 operation 越过握手与 observation timeout、timeout 后 `WAITING` retry state、首轮迟到 Ready 返回后在第二轮 observation 尚未返回的受控边界保持 public Run / durable Wait 等待态且无 terminal outbox、真实 backoff due 后第二轮恢复及最终 `SUCCEEDED`；脚本只用 Event/owner state 驱动 phase，并用单一 overall deadline 输出失败诊断。
- Engine ingest / watch regression：覆盖 Engine-owned 空白 final answer 判定以 `run_failed(runner_empty_final_content)` 收口，并通过 public `watch_session_events` 投影为 typed failed HostEvent；Host ingest 不用另一套空白谓词修补 final answer。
- transient Host→Service→CLI regression：`tests/cli/test_transient_delivery_interruption_path.py` 通过真实 Host publisher、两个 subscription、queued Run promotion、Service sole consumer、CLI 私有串行 display executor 与可释放 blocking renderer barrier，证明慢 callback 只减速当前 consumer 并使该 subscription 按 Host item cap 产生 non-retryable `DELIVERY_INTERRUPTED/TRANSIENT_MAILBOX_OVERFLOW`；Host terminal commit、第二个 Run promotion 与独立 watcher 继续完成。释放 barrier 后 Service 关闭 watcher并恰好进入一次 durable recovery，terminal / Outbox identity 保持一致且 CLI 最终结果只展示一次；测试不依赖 Service relay、byte quota 或 availability 映射。
- logging：覆盖 Host EngineEvent ingest 日志分层，确认 `content_delta` / `reasoning_delta` / `tool_call_delta` 的逐 delta ingest 诊断使用 stream-debug 级别并受普通 `DEBUG` 抑制，非 delta ingest 骨架保持 `VERBOSE`。
- tooling options：验证 `FrameworkToolName` 为 `StrEnum`、默认 reserved framework tool policy、`HostToolingOptions` 接受 contracts source refs 且要求 source refs 非空、业务 `ToolBundle` 不得占用 `fetch_more` 等 reserved framework tool name、duplicate governance messages 显式覆盖所有决策类别，以及 default policy view 不共享可变状态。
- durable foundation / projection core / Context Governance / Conversation Memory / RunInputBuilder / dispatch scheduler / ToolRuntime accept barrier / executor / truncation / fetch_more / duplicate governance / diagnostics / EngineEvent ingest / internal admission：覆盖 SQLite fresh bootstrap、schema version / table constraint、transaction runner commit / rollback / after-commit、EventLog / payload / idempotency / projection checkpoint 基础路径、Context Budget 的五阶段 action matrix、signed-delta positive / negative formula、strict anchor conjunction、compatibility、keyset 跨页、compact boundary、missing-usage 穿越与 invalid / ambiguous / lineage barrier、完整 conservative fallback、startup anchored exact replay 和 Host-private diagnostic / public 七字段隔离，vNext compaction operation / artifact / typed contract、compact outcome payload 反向引用 proposal manifest ref / digest、Conversation Memory vNext policy 与 snapshot contract、selected recent window、accepted compact materialization、no fallback facts、durable snapshot / item / diagnostic round-trip、memory snapshot 与 projection checkpoint 同事务、memory snapshot integrity classification（invalid JSON、schema mismatch、digest mismatch、unsupported item kind、storage read failure）及 storage maintenance operator-facing report、repair / rebuild / catch-up、RunInputBuilder vNext memory 渲染 / inline delta / repair-required、ordinary one-system-message envelope、wait resume 只从 canonical request row 恢复 exact replay identity 与参数，并对缺失、错链或 digest 漂移 fail closed、ordinary runner-call input manifest 有界且不内联大 user input / message content、runner-call projection payload 可恢复完整 LLM-facing messages、selected tool schema snapshot 可恢复 full JSON、Session lifecycle、Run / Attempt transition、dispatch / wait / resolve_wait / scheduler / ToolRuntime ordinary/awaiting 共用 accepted tool-call request writer（inline arguments、arguments descriptor、semantic query absent / inline / descriptor、真实 EventLog sequence、digest mismatch fail-closed），且 `TOOL_AWAITING` 只保留治理字段与显式 request link；同时覆盖 duplicate governance / Engine ingest / public admission 与多进程 durable invariant。
- durable concurrency matrix：`test_durable_concurrency_matrix.py` 覆盖 idempotency 同 key 多进程 same / different digest、projection checkpoint lost CAS，以及 memory snapshot + checkpoint 同事务提交和 CAS rollback；EventLog append、ensure_session 与 liveness 仍由既有测试闭环，不在该矩阵文件重复覆盖。
- P12.6 memory semantic smoke：`test_toolruntime_accept_barrier.py` 覆盖 ToolRuntime accept barrier；`test_compaction_contract.py` / `test_context_compact_events.py` / `test_llm_compaction.py` / `test_compaction_operation.py` / `test_compaction_cancellation_scope.py` 覆盖 compact material pack、prompt-local label 到 canonical provenance 映射、compaction-gated vNext fact candidate、accepted evidence material 注入、accepted evidence query_text 消费 durable tool-call request atoms、LLM compactor prepared proposal input 与真实 runner messages 同源、vNext accepted / rejected / failed operation payload、accepted compact 后预算只统计业务文本且 diagnostics 不计入、proposal manifest ref 传递、whole-candidate repair、attempt timeout child 隔离、parent cancellation 优先、caller task cancellation 透传与 manifest 后 pre-call recheck；`test_compact_pipeline.py` 覆盖 compact pipeline thin helper 的 source snapshot、normal request、tier recovery request、reactive pass queue、accepted / failed payload input、fallback decision handoff 与 ordinary protected raw-tail selection；`test_compact_material.py` 覆盖 deterministic segment selection、protected current / selected recent-window floor、reactive frozen overflow material list、already represented block 排除、current input anchor 去重、vNext material 对 user turn / assistant turn / evidence / typed previous view / current anchor non-citable 的直接映射边界、previous blocks 与 typed readable view exact invariant、EventLog-backed pre-dispatch compact material source、explicit previous compacted pair pack path、accepted result descriptor/SQLite row/artifact/noncanonical JSON tamper 在 strict material 构造前 fail closed，以及 snapshot cursor lag repair-required 语义；`test_memory_projection.py` 覆盖 vNext policy / snapshot contract、compact 前 selected recent window、typed terminal answer continuity material、accepted compact materialization、accepted evidence without fact diagnostic、failed compaction 不物化 memory、JSON / durable round-trip、projection consumer checkpoint 与 durable memory snapshot integrity classification；`test_storage_maintenance.py` 覆盖 operator-facing maintenance result 暴露 memory snapshot integrity issues 且不执行 snapshot repair / overwrite；`test_run_input_builder.py` 覆盖 RunInputBuilder 对 vNext evidence fact、session summary、answer anchor、forward intent、reference continuity、selected recent window、descriptor-backed terminal answer 与 durable memory projection 的 LLM-facing 文本等价、post-compaction facts、no-compaction continuity、memory snapshot repair、compact event ref 与 memory latest compaction ref 的一致性矩阵、ordinary single-system-message envelope、shared ordinary material block source、ordinary runner-call input manifest，以及 fallback selected recent window rendering；`test_dispatch_scheduler.py` 覆盖 memory projection lag repair 不关闭 Run / Attempt 为失败终态，并覆盖 proactive / reactive compaction vNext closeout、manifest commit 后 durable Run 失效时 provider count 保持为零、compaction failure 后 recent-window fallback dispatch / hard-budget fail closed 不写 `CONTEXT_COMPACTED` 且不写 `RUN_LOST`。Conversation Memory snapshot 测试数据应优先通过 `tests/host/memory_snapshot_factories.py` 构造并回填 digest，避免业务测试直接散落 snapshot digest 中间态或重复手写 `ConversationMemorySnapshotVNext(...)`。
- context budget / anchor integration：`test_context_anchor.py` 直接覆盖 compactor manifest / usage 整体排除且不形成 orphan barrier；`test_public_tool_wiring_smoke.py` 通过 public Host 覆盖 scripted runner 不发 usage 时仍持久化 `usage_missing` conservative budget fact 并成功终态；`test_public_steer.py` 断言 steer 的同一 candidate 只执行一次 conservative estimate。
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
  当前 suite 固定为 5 个 stress scenarios；runner-call boundedness scenario 在进入后续 gap / reconnect 阶段前显式证明 12 个 scripted calls 已被 worker 接受。
- transient delta stress：`test_transient_delta_stress.py` 使用 `stress` marker，默认 pytest 排除，需通过
  `pytest -o addopts="" -m stress tests/host/test_transient_delta_stress.py -q` 显式运行。该用例经真实 `open_host` 路径各发布至少 1000 条 content、reasoning、tool-call delta，断言三类 EventLog row 严格为 0，同时验证 fast watcher 全量观察、Run / Attempt / terminal / final answer / Outbox durable facts 保持一致。

### `tests/engine/`

Engine 契约、包根导出、事件契约与架构边界测试，覆盖 `dayu.engine` 的稳定边界：

- package exports：锁定 `dayu.engine.__all__`，阻止未承诺入口、实现类或取消异常出现在包根。
- import boundary：阻止 Engine 反向依赖 Host（含 memory）、Service、UI、Fins、工具声明 owner、工具执行实现、处理器或 trace 私有模块；OpenAI runner 子树内允许当前实现所需的 `aiohttp`。
- weak typing guard：扫描 `dayu.engine` 源码，守住强类型签名、封闭联合与 metadata 类型边界，并阻止 Engine error-code contract 退化为裸 `str` 或关键 dataclass 构造点传入字符串字面量。
- 事件契约与消息契约：覆盖 EngineEvent/RunnerEvent discriminator-data 构造配对、AgentMessage 固有 role 与 AgentRunRequest message union 构造校验、metadata、provider protocol error `partial_tool_calls` 有界摘要、usage provider request id 显式字段、content-completed 不承载 finish reason、AgentMessage 大内容透传到 Runner、终态事件集合等结构约束。
- Agent 状态机：覆盖无工具 final / failed / cancelled、content filter 降级 final 诊断日志、普通 completed / failed tool calling、工具结果投影、max iteration force-answer、大工具消息进入 force-answer 路径、连续失败工具批次保护、awaiting 拒绝与取消优先级、accepted awaiting 握手返回后独立 operation 可越过工具握手预算且不被 Engine timer 取消、RunnerDone typed commit 后迟到取消不覆盖 ordinary/force-answer/error/tool candidate、first failure candidate 不被 runner exception 覆盖、close cancellation 资源释放、工具批执行前取消不登记 tool call id。
- provider smoke 轻量测试：覆盖 `utils/smoke_async_agent_providers.py` 的参数解析、缺 key 跳过、安全输出与 provider case 配置，不做真实联网。
- provider extension config adapter：覆盖默认模型目录中的 provider extension JSON DSL 到 `ProviderRequestExtension` 封闭联合的映射，并确认未知 type、未知字段、非法枚举和非法字段组合 fail closed。

### `tests/engine/contracts/`

Engine contract 的细粒度测试，当前覆盖：

- `messages`：四种 AgentMessage 固有 role 构造校验、AssistantMessage / AssistantToolCall 与 provider state roundtrip 契约。
- `runner_events`：RunnerEventData 联合、RunnerHTTPErrorCode、RunnerHTTPErrorData、HTTP error 与 context overflow 错误枚举、HTTP error 到 Done(ERROR) 的收口契约，以及 provider / runner-specific error-code wrapper 的 trim、空值、长度和序列化契约。
- `runner_spec`：RunnerSpec 字段集合、`ClientCorrelationPolicy` 枚举值、provider reasoning / thinking extension、stream usage 能力字段、免鉴权 provider 的 `api_key_ref=None`、timeout / retry 校验与构造路径。
- `runner_identity`：`RunnerRequestIdentity` 与 `build_runner_request_identity` 的稳定 lowercase SHA-256 `client_correlation_id`、ASCII 长度、iteration / call index 差异、direct Engine 无 Attempt 路径、attempt / execution 成对约束、空文本与非法序号拒绝。
- `agent_run`：`AgentRunRequest` 的非空 messages、message union membership 校验，以及 Attempt `attempt_id` / `execution_id` 成对出现或同时缺失的契约。
- import boundary：Engine contract 子包不得越过自身契约边界引入上层依赖。

### `tests/engine/runners/openai/`

OpenAI-compatible Runner 的 provider 协议测试，覆盖从 payload 构建、provider 响应解析到 RunnerEvent 事件流的行为：

- payload：消息、工具 schema、reasoning content、provider 扩展、stream usage gating、禁止额外 payload 袋。
- SSE：content delta、reasoning delta、tool call delta、tool call 聚合、native index 类型/非负约束、synthetic/native/id/position identity conflict fail-closed 且不合并 partial、usage、malformed usage 非终止诊断、`[DONE]`、多行 data、单行 / data 行数缓冲上限、跨 chunk UTF-8、非法 UTF-8、尾部无换行、空 choices + usage、单 chunk choice policy fail-closed、HTTP 200 `Content-Type` 白名单分流和缺失 `Content-Type` fallback。
- diagnostics：覆盖 Runner HTTP attempt / response 等普通 debug 诊断、stream idle heartbeat 与 SSE done-token 的 stream-debug gating，以及 stream-debug 不输出完整 prompt、headers、API key 或响应正文。
- non-stream：非流式响应、string-only `function.arguments`、response-level choice policy fail-closed、thought 标签处理、stream / non-stream strict terminal parity（显式 finish reason 且 tool calls presence 当且仅当 `TOOL_CALLS`），且 finish reason 只在 Runner done 边界断言。
- 错误与重试：协议错误、HTTP error 分类、context overflow classifier、未知状态码、retry backoff、重试耗尽后的事件收口。
- request identity header：覆盖 OpenAI-compatible Runner 在 `ClientCorrelationPolicy.OPENAI_X_CLIENT_REQUEST_ID` 且 `request_identity` 存在时发送 `X-Client-Request-Id`，policy disabled 或 identity 缺失时不发送，policy 开启时拒绝静态 `X-Client-Request-Id` header 冲突，并确认 transport retry 复用同一个客户端关联 header；provider request id 从 `x-request-id` 或 DeepSeek `x-ds-trace-id` 提取且优先标准 `x-request-id`，基础设施 tracing header 不映射为 provider id，既有 `runner.http.response` DEBUG 行只输出实际存在的 provider request id header，全部缺失时输出 `x-request-id=None`。
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
