# WU-SEMANTIC-OWNERSHIP-01 P2-A Implementation - AgentCodex

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P2-A`
- Accepted plan commit: `38477f63`
- Implementation scope: S1 CLI existing-session execution helper, S2 Fins direct stream contract violation, S3 unified CLI `HostApiError` presentation.
- Artifact path: `docs/reviews/wu-semantic-ownership-01-p2-a-implementation-codex.md`

## 直接证据与动机确认

P2-A 动机成立。

- DS 03 直接证据：实现前 `dayu/cli/commands/session.py` 从 `dayu.cli.commands.prompt` / `dayu.cli.commands.interactive` 导入 `_prepare_*_existing_session_execution` 与 `_execute_*_on_existing_session` 私有 helper。`session resume` 依赖其它 command module 私有实现，shared existing-session execution 没有 CLI public owner。
- DS 10 直接证据：Service `dayu/service/fins_direct.py::_ensure_result_event` 已拥有 direct stream 正常结束但缺 RESULT 的业务 fallback；CLI `dayu/cli/commands/fins.py` 仍有本地 `_missing_result_event()` 并渲染 fake failure RESULT，属于下游伪造 terminal fact。
- DS 11 直接证据：`session.py` 有 command-local `_host_error_context` / `_exit_code_for_host_error`，prompt / interactive 则落入 generic `Exception` path，导致同一 `HostApiError` 在 CLI 入口的展示与退出码策略不一致。

严重性判断与 accepted plan 一致：这是 P2 CLI / Service 边界一致性问题，不改变 Host durable truth 或 LLM-facing fact，但会造成用户可见语义、退出码和 command module ownership 漂移。

## Owner Boundary 判定

- Existing-session execution：CLI public helper `dayu.cli.session_execution` 拥有 runtime prepare、CLI invocation identity、Host submit/watch/cancel execution composition；prompt / interactive command modules 只拥有各自参数、Session ensure/create 与 context slot 构造。
- Context slot：prompt 的 `fins_default_subject` / FMP fallback slot 仍由 `dayu/cli/commands/prompt.py` 的 `build_prompt_context_slot_values(...)` 构造；interactive 的 `current_time` slot 仍由 `dayu/cli/commands/interactive.py` 的 `build_interactive_context_slot_values()` 构造。`session_execution` 只接收已构造的 `context_slot_values`，不按 scenario 分发 slot 规则。
- Runtime display：`RuntimeDisplayController` 继续拥有 thinking guard、final-before-terminal cleanup、cancel cleanup、display lifecycle close。`session_execution` 只是调用它，不替代或包裹其职责。
- Fins direct missing RESULT：Service `_ensure_result_event` 继续拥有正常 missing-result 业务 fallback；CLI 只拥有“观察到 Service direct stream contract 被破坏”的 hard assertion。
- `HostApiError`：Host 继续拥有 structured error fact；CLI helper `dayu.cli.host_api_errors` 只拥有 stderr 展示文本和 process exit-code mapping。

## 具体改动

- 新增 `dayu/cli/session_execution.py`：
  - `prepare_prompt_session_execution(...)` / `execute_prompt_on_session(...)`
  - `prepare_interactive_session_execution(...)` / `execute_interactive_on_session(...)`
  - 搬迁 prompt / interactive existing-session runtime prepare、submit/watch/cancel、interactive startup reconnect / REPL 执行组合。
- 更新 `dayu/cli/commands/prompt.py` / `dayu/cli/commands/interactive.py`：
  - 删除旧 `_prepare_*_existing_session_execution` / `_execute_*_on_existing_session` 私有 helper，不保留同名转发 facade。
  - command 主路径改为调用 `dayu.cli.session_execution` public helper。
  - 保留 command-local ticker 校验、Session ensure/create 与 context slot 构造。
- 更新 `dayu/cli/commands/session.py`：
  - 不再导入 prompt / interactive 下划线私有符号。
  - `session resume` 调用 `session_execution` public helper。
  - `session resume` / `session purge` 使用统一 `HostApiError` 展示与退出码 helper。
- 新增 `dayu/cli/host_api_errors.py`：
  - `CliHostApiErrorTarget`
  - `format_host_api_error(...)`
  - `host_api_error_context(...)`
  - `exit_code_for_host_api_error(...)`
  - 策略：显式 `--session-id` selector 的 `NOT_FOUND` -> `EXIT_USAGE_ERROR`；label TOCTOU、prompt / interactive no explicit selector、generic Host error -> `EXIT_FAILURE`。
- 更新 `dayu/cli/commands/fins.py`：
  - 删除 CLI `_missing_result_event()`。
  - 新增 CLI-private `FinsDirectStreamContractViolation(RuntimeError)`。
  - `_consume_fins_direct_events(...)` 正常结束但无 RESULT 时抛 contract violation，由 generic failure path 渲染。
- 测试更新：
  - 新增 `tests/cli/test_import_boundary.py` AST-level import boundary test。
  - prompt / interactive / session 测试迁移到新 `session_execution` owner。
  - 新增 HostApiError pure function policy 覆盖。
  - 新增 prompt / interactive `HostApiError` structured presentation 覆盖。
  - Fins missing-result CLI 测试改为 contract violation。
- README：
  - 更新 `tests/README.md` 的 CLI 测试事实。

## Propagation Audit

- Session execution path:
  - `prompt` / `interactive` / `session resume`
  - -> command-local args + context slot construction
  - -> `dayu.cli.session_execution` public helper
  - -> `dayu.service.entrypoint_runtime`
  - -> Host public API
  - -> CLI terminal renderer / cursor store
  - Audit result: `session.py` 不再从 prompt / interactive 导入下划线私有符号；新增 AST test 固化该边界。
- Fins direct RESULT path:
  - Fins runtime producer
  - -> `FinsDirectCommandService._ensure_result_event`
  - -> CLI `_consume_fins_direct_events`
  - -> renderer 或 `FinsDirectStreamContractViolation`
  - Audit result: 缺 RESULT 的业务 fallback 只在 Service / upstream runtime 真源出现；CLI 不再构造业务 failure RESULT。
- HostApiError path:
  - Host public API raises `HostApiError`
  - -> `dayu.cli.host_api_errors` formats `host_code=... host_message=...`
  - -> prompt / interactive / session stderr and exit code
  - Audit result: command modules 不再各自重建 HostApiError core format / exit-code mapping。
- Durable / trace / memory / audit / LLM-facing:
  - P2-A 未修改 Host durable EventLog、trace、memory、audit、prompt/schema 或 LLM-facing material。

## 验证命令与结果

- `source .venv/bin/activate && pytest tests/cli/test_session_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py`
  - Result: `128 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/cli/test_import_boundary.py`
  - Result: `1 passed`
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed

## README 检查结果

- Root `README.md`: 已读取 Agent 更新约束。当前未新增 CLI 参数、工作流、日志位置或面向最终用户的排障步骤；错误格式统一属于内部 CLI consistency，不更新用户手册。
- `tests/README.md`: 已读取更新边界。因新增/迁移 CLI test facts，已更新 CLI 测试覆盖描述。
- `dayu/README.md`: P2-A 落实既有 CLI / Service / Host 边界，未改变分层关系或装配方式，未触发更新。
- `dayu/service/README.md`: 未修改 Service code 或 Service public contract，未触发更新。

## Residual Risks / 未覆盖项

- fixed in current slice: DS 03 / DS 10 / DS 11 当前 P2-A 范围内已按 accepted owner boundary 修复并由 focused tests / pyright 覆盖。
- assigned to later work unit: P2-B memory/test hardening 与 P2-C fallback prompt source-of-truth 未触碰，继续由后续 sub WU owner 处理。
- uncovered area: 未运行全仓 pytest；本任务按 accepted plan 运行了指定 CLI tests、import-boundary test、pyright 与 `git diff --check`。
- unrelated dirty state: `docs/host/issues-implementation-control.md` 在本轮开始前已有修改，内容为 P2-A implementation in progress；本实现未继续修改该文件。
