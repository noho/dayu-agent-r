# WU-SEMANTIC-OWNERSHIP-01 P2-A Plan

## 1. Goal / Motivation / Success Signal

Work unit：`WU-SEMANTIC-OWNERSHIP-01 P2-A CLI/service boundary consistency`。

目标：修正 CLI / Service 边界上仍存在的三类语义所有权漂移：

- `dayu-cli session resume` 通过导入 `prompt.py` / `interactive.py` 私有函数复用执行路径，绕过稳定 public command contract。
- Fins direct CLI 在 Service 已保证 RESULT contract 后仍保留本地缺失 RESULT 伪终态；这应是 hard contract violation，不应在下游消费者补业务 RESULT。
- `HostApiError` 在 `prompt` / `interactive` / `session` 命令中的展示文本和退出码映射不一致。

第一性原理判断：P2-A 动机成立，严重性为 P2 合理。它不是 Host durable truth 或 LLM-facing fact 的 P0/P1 问题，但会导致 CLI 入口在同一 Service / Host 事实下出现不同用户可见语义、不同退出码，且让 `session resume` 依赖其它 command 模块私有实现，增加后续 prompt / interactive 演进时的边界漂移风险。

成功信号：

- `session.py` 不再从 `dayu.cli.commands.prompt` / `dayu.cli.commands.interactive` 导入下划线私有函数。
- prompt / interactive / session 的已有 Session 执行复用同一个 public CLI command execution source-of-truth；该 helper 直接调用 Service public entrypoint runtime，不成为仅透传私有函数的兼容 wrapper。
- Fins direct CLI 不再构造 `_missing_result_event()`；Service stream 正常结束但没有 terminal result 时，CLI fail fast 为 contract violation，不投影为业务 failure RESULT。
- prompt / interactive / session 对 `HostApiError` 使用同一 CLI presentation / exit-code helper；selector-aware 差异只通过显式上下文参数表达。
- 受影响 CLI / Service tests、pyright、`git diff --check` 通过。

## 2. Direct Evidence And Current Finding Judgment

控制文档证据：

- `docs/host/issues-implementation-control.md:172-177` 记录当前 active work unit 为 `WU-SEMANTIC-OWNERSHIP-01`，next entry point 是 P2-A plan generation，并要求重新确认 DS 03 / DS 10 / DS 11。
- `docs/host/issues-implementation-control.md:127-152` 要求小型跨模块 cleanup 默认 1-3 个 implementation slices，超过 3 个 slices 必须说明。
- `docs/reviews/fullrepo-semantic-ownership-controller-adjudication.md:130-145` 接受 P2 CLI/service boundary consistency：DS 03、DS 10、DS 11；期望修复形态是公共 session execution helper，以及 missing direct RESULT 在 Service 外成为 hard contract violation。

设计真源证据：

- `docs/host/design.md:1189-1193` 定义普通 prompt 统一通过 `submit_followup`，Service / UI 观察主路径是 session-level `watch_session_events`，内部 run-scoped EventLog 不是普通 Service-facing 聊天入口。
- `docs/host/design.md:1218-1237` 冻结普通 Service-facing Host public API，包括 `ensure_session`、`create_session`、`get_session`、`list_sessions`、`watch_session_events`、`submit_followup`；`HostEvent` 是 Service-facing typed event。
- `docs/host/design.md:1824-1841` 定义 Service / channel adapter 拥有 Outbox 补读和 live watch attach/reconnect 协议，Host 不负责 deliver to UI。

### DS 03: accepted

当前仍成立。

直接代码证据：

- `dayu/cli/commands/session.py:36-45` 从 `dayu.cli.commands.interactive` / `dayu.cli.commands.prompt` 导入 `_execute_interactive_on_existing_session`、`_prepare_interactive_existing_session_execution`、`_execute_prompt_on_existing_session`、`_prepare_prompt_existing_session_execution`。
- `dayu/cli/commands/session.py:251-267` 在 prompt mode 调用 prompt 模块私有 prepare/execute。
- `dayu/cli/commands/session.py:275-289` 在 interactive mode 调用 interactive 模块私有 prepare/execute。
- `dayu/cli/commands/prompt.py:196-260` 与 `dayu/cli/commands/interactive.py:253-300` 的 prepare helper 虽然封装了 CLI runtime assembly，但仍是 command 模块私有实现。

Root cause：共享语义“在既有 Session 上执行 prompt turn / interactive REPL”没有 public owner；`session resume` 作为第三个消费者只能依赖其它 command module 的 private helper。直接在 `session.py` 特判不是修复；正确 owner 应是一个 CLI public command execution helper，复用 Service public entrypoint runtime。

### DS 10: partially accepted / updated

原 finding “CLI duplicates Service `_ensure_result_event` missing-result fallback”按当前代码需要改判：Service 已经拥有 producer 正常结束缺 RESULT 的 fallback，CLI 不再需要也不应重复业务 RESULT 语义；但 CLI 当前仍保留下游 `_missing_result_event()`，这构成 contract violation 被伪装成业务 failure result 的问题。

直接代码证据：

- `dayu/service/fins_direct.py:207-213`、`:355-361`、`:423-429`、`:468-474` 所有 direct stream 均经 `_ensure_result_event(...)` 返回。
- `dayu/service/fins_direct.py:477-510` 的 `_ensure_result_event` 在正常结束且未见 RESULT 时产出 `_missing_result_event(...)`；重复 RESULT 时 `FinsDirectUsageError` fail fast。
- `tests/service/test_fins_direct.py:499-515` 已覆盖 Service 缺 RESULT 正常结束合成 failure RESULT。
- `dayu/cli/commands/fins.py:703-731` 的 `_consume_fins_direct_events` 在消费结束仍会调用 CLI 本地 `_missing_result_event()`。
- `dayu/cli/commands/fins.py:899-923` 本地构造另一个 failure RESULT，且 `tests/cli/test_fins_commands.py:879-899` 当前断言 CLI fallback 文案。

Root cause：Service 与 CLI 同时拥有“缺失 RESULT 时如何投影 terminal semantics”。当前 Service 已是真源；CLI 的职责只是在 Service contract 被破坏时 fail fast，不能生成业务 RESULT 掩盖上游 contract violation。

### DS 11: accepted

当前仍成立。

直接代码证据：

- `dayu/host/api.py:1168-1180` 定义 Host public structured error code，`dayu/host/api.py:3212-3245` 定义 `HostApiError(code, message, retryable, detail)`。
- `dayu/cli/commands/session.py:150-154` 顶层单独捕获 `HostApiError`，渲染 `dayu-cli session {action}: host_code=... host_message=...`，并调用 `_exit_code_for_host_error(...)`。
- `dayu/cli/commands/session.py:268-273`、`:290-295`、`:331-336` 对 resume/purge 内联捕获 `HostApiError`，带 selector context 显示并计算 exit code。
- `dayu/cli/commands/session.py:621-647` 拥有 session 私有 `_host_error_context` 与 `_exit_code_for_host_error`。
- `dayu/cli/commands/prompt.py:150-162` 未单独捕获 `HostApiError`，会落入通用 `Exception`，文本是 `dayu-cli prompt: {exc}`，退出码固定 1。
- `dayu/cli/commands/interactive.py:194-210` 同样未单独捕获 `HostApiError`，文本是 `dayu-cli interactive: {exc}`，退出码固定 1。
- `tests/cli/test_session_command.py:631-660`、`:678-719` 覆盖 session selector-aware HostApiError 文案；prompt / interactive 测试目前只覆盖 terminal failure，如 `tests/cli/test_prompt_command.py:1904-1925`、`tests/cli/test_interactive_command.py:1361-1386`，没有同等级 HostApiError presentation contract。

Root cause：Host API structured error 的 CLI presentation/exit-code owner 未统一。Session command 因近期引入 list/resume/purge 语义先做了私有实现；prompt / interactive 保持通用 Exception catch，导致相同 Host structured error 在不同入口中失去 code/message 格式一致性。

## 3. Owner Boundary

| 语义 | 首次产生 | 校验 | 持久化 / 真源 | 投影 / 用户可见 | P2-A 修复边界 |
|---|---|---|---|---|---|
| Session、Run、Host public error | Host public API | Host request / state machine | Host durable EventLog / read model | Service / CLI 捕获并展示 | 不改 Host；只统一 CLI presentation helper |
| prompt / interactive turn execution | CLI command 输入解析；Service entrypoint runtime 执行 Host 协议 | CLI args validation；Service helper typed request | Host owns Session/Run facts | CLI renders terminal/activity/thinking | Service 继续拥有 Host submit/watch/cancel；CLI public helper 拥有 command execution composition 和展示差异 |
| `session resume` selector resolution | CLI session command | CLI selector validation；Host `get_session/list_sessions` | Host Session snapshot/list truth | CLI error includes selector context | 保留在 session command 或 CLI session helper；不得放入 prompt/interactive 私有函数 |
| Fins direct RESULT contract | Fins runtime producer；Service `_ensure_result_event` | Service duplicate/missing RESULT invariant | Fins event stream contract | CLI render event stream | Service owns normal missing RESULT fallback；CLI only asserts contract and fails hard if violated |
| `HostApiError` message / exit code | Host raises structured error | HostApiError dataclass invariant | Host error code/message/detail | CLI stderr + process exit code | CLI presentation helper owns formatting and exit mapping；Service 不拥有 process exit code |

为什么公共 helper 不是 glue seam：

- P2-A 需要移动真实 shared behavior，而不是保留旧 private helper 再包一层。新的 CLI helper 必须直接承载 prepare/execute 数据流、HostApiError presentation 或 Fins contract assertion；prompt / interactive / session 都调用它。
- Service helper 继续只做 product entrypoint runtime 和 Host public API 协议，不解析 `ParsedCliArgs`、不写 stdout/stderr、不安装 signal handler。CLI helper 可以依赖 Service，但 Service 不反向依赖 CLI。
- 如为 `HostApiError` 抽取 helper，它不是纯格式化别名；它冻结 selector-aware exit-code policy、command/operation context 和 `host_code/host_message` 文本契约。
- 新的 existing-session execution helper 与既有 `RuntimeDisplayController` 职责不重叠：`RuntimeDisplayController` 继续拥有 thinking guard、final-before-terminal cleanup、cancel cleanup 与 display lifecycle close；P2-A 新 helper 只拥有 existing-session runtime prepare / Host submit-watch execution composition / command execution identity。两者可以被同一 command 调用，但不得互相包裹成 facade。

## 4. Non-goals / Scope Boundary

- 不实施本 plan；当前任务只产出 plan 与 delivery artifacts。
- 不触碰 P2-B memory/test hardening。
- 不触碰 P2-C fallback prompt source-of-truth。
- 不修改 P1-A accepted-result projection contract。
- 不修改 P1-B lifecycle/cancel durable truth。
- 不修改 P1-C LLM-facing semantic cleanup 已接受 contract。
- 不改变 Host public API、Host durable schema、Engine runner、Fins storage 仓储协议或 Fins ingestion runtime 行为。
- 不添加兼容性 wrapper/facade，不保留旧私有 import 路径 re-export。
- 不为测试夹具保留下游 fallback；测试必须跟随新 owner boundary 迁移。

Stop conditions：

- implementation 发现 shared prompt / interactive execution 不能在不复制 REPL / terminal rendering 语义的情况下抽取到 CLI public helper，应停止并重新裁决是否拆分 prompt / interactive owner。
- implementation 发现 Fins direct Service contract 并未覆盖某个真实 command path，应先修 Service owner，而不是让 CLI继续 fallback。
- implementation 发现 prompt / interactive 的 `HostApiError` exit-code policy 需要改变用户可见 CLI contract，且 README 已公开描述不同语义，应停止并让 controller 裁决文档/行为变更。

## 5. Implementation Slices

本 work unit 是小型跨模块 cleanup，按控制文档 slice 原则保持 3 个 implementation slices，分别对应依赖顺序和独立验证闭环。

### S1. CLI Existing-session Execution Public Helper

Objective：移除 `session.py` 对 prompt / interactive 私有函数的依赖，建立 CLI-owned public execution helper，保持 prompt / interactive / session resume 行为一致。

Allowed files：

- `dayu/cli/session_execution.py` 或语义等价的新 CLI helper 模块。
- `dayu/cli/commands/prompt.py`
- `dayu/cli/commands/interactive.py`
- `dayu/cli/commands/session.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_session_command.py`
- `tests/cli/test_import_boundary.py` 或现有 CLI import boundary 测试文件，如存在。

Exact allowed changes：

- 新增 CLI helper 模块，命名建议 `dayu.cli.session_execution`。模块概览 docstring 必须说明：它是 CLI command execution owner，只复用 `dayu.service.entrypoint_runtime`，不读 Host durable internals，不读取 Fins storage，不实现 Service runtime assembly 之外的业务状态机。
- 将 prompt existing-session prepare/execute 的真实实现从 `prompt.py` 私有 helper 移到新 helper，暴露非下划线 typed API，例如：
  - `prepare_prompt_session_execution(...) -> PreparedPromptSessionExecution`
  - `execute_prompt_on_session(...) -> int`
- 将 interactive existing-session prepare/execute 的真实实现从 `interactive.py` 私有 helper 移到新 helper，暴露非下划线 typed API，例如：
  - `prepare_interactive_session_execution(...) -> PreparedInteractiveSessionExecution`
  - `execute_interactive_on_session(...) -> int`
- prompt / interactive command modules 的 `_run_prompt_command_async` / `_run_interactive_command_async` 内部也必须调用新 public helper；`session.py` 也调用同一 helper。原 private `_prepare_*` / `_execute_*` 函数从 prompt / interactive command modules 删除，不保留同名转发。
- 不在 `prompt.py` / `interactive.py` 保留仅转发旧私有函数；测试引用旧私有 helper 的地方必须迁移到新 public helper，或改用 command main path。
- 若 dataclass 当前只服务新 helper，应移动到新 helper；若只服务 command-local REPL/display，可留在原模块，但不得让 `session.py` 依赖 private symbol。
- `session.py` 的 selector resolution 继续由 session command owner 负责；新 helper只接受已解析出的 `session_id`，不猜 label。
- prompt / interactive 的 context slot 构造仍由各自 command module 拥有：prompt 继续由 prompt command 计算 ticker / FMP 相关 `context_slot_values`，interactive 继续由 interactive command 计算 interactive slots。新 helper 的 prepare API 接受已构造的 `context_slot_values`，不得根据 scenario 字符串自行分发 slot 构造规则。

Tests / assertions：

- `tests/cli/test_session_command.py`：保留 `session resume --mode prompt` / `interactive` by session id / label 的断言，新增或更新断言确认执行路径不调用 create/ensure，不依赖 prompt/interactive private helper。
- `tests/cli/test_prompt_command.py`：已有 prompt command 行为不变；如测试直接调用旧 `_execute_prompt_on_existing_session`，改为新 public helper。
- `tests/cli/test_interactive_command.py`：已有 interactive command 行为不变；如测试直接调用旧 `_execute_interactive_on_existing_session`，改为新 public helper。
- 添加 import boundary / source scan 断言：`dayu/cli/commands/session.py` 不包含 `from dayu.cli.commands.prompt import _` 或 `from dayu.cli.commands.interactive import _`。
- 新建 `tests/cli/test_import_boundary.py` 或在等价 CLI boundary 测试文件中加入 AST-level 断言，禁止 `dayu/cli/commands/session.py` 从 `dayu.cli.commands.prompt` / `dayu.cli.commands.interactive` 导入下划线私有符号。该断言是必做自动化测试，不得只依赖人工 `rg`。

Validation:

```bash
source .venv/bin/activate && pytest tests/cli/test_session_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py
source .venv/bin/activate && pyright
git diff --check
```

Rollback / verification point：S1 完成后，`rg -n "commands\\.(prompt|interactive) import .*_" dayu/cli/commands/session.py tests/cli` 无命中或只有测试注释中的禁止断言。

### S2. Fins Direct RESULT Contract Assertion

Objective：删除 CLI 本地 missing RESULT 业务 fallback；Service 继续拥有正常 missing-result fallback，CLI 对违反 Service contract 的 stream fail hard。

Allowed files：

- `dayu/cli/commands/fins.py`
- `tests/cli/test_fins_commands.py`
- `tests/service/test_fins_direct.py`，仅在需要补强 Service contract 断言时修改。
- `tests/README.md`，仅在测试职责描述变化时按 README 触发规则检查后更新。

Exact allowed changes：

- 删除 `dayu/cli/commands/fins.py` 的 `_missing_result_event()`，以及 `FinsErrorKind` / `FinsOperationKind` / `FinsResultStatus` 等只为本地 missing-result event 服务的 import。
- 定义 CLI 私有 contract violation 异常，例如 `FinsDirectStreamContractViolation(RuntimeError)`。它只表达 CLI 观察到 Service direct stream contract 被破坏，不承载 Fins 业务结果语义。
- 将 `_consume_fins_direct_events(...)` 在 async iterator 结束且未返回 terminal result 时改为抛出 `FinsDirectStreamContractViolation("Fins direct Service stream ended without RESULT")`。该错误由 `run_fins_direct_command` 的通用 `Exception` catch 渲染为 CLI failure，不作为 usage error。
- 不在 CLI 构造 `FinsEvent` / `FinsResultSummary` fallback；不调用 renderer 投影一个业务 failure result。
- `tests/cli/test_fins_commands.py::test_stream_without_result_returns_failure` 改为 contract violation 断言：退出码仍为 `EXIT_FAILURE`，stderr 包含 Service contract violation 文本，不包含 `Fins failure` 或 `ended without result` 业务 RESULT 渲染。
- 保留 `tests/service/test_fins_direct.py::test_stream_without_result_closes_as_failure_result`，证明正常 Service path 仍合成 failure RESULT；CLI fake service 如果绕过 Service helper，应被视为 broken test double / contract violation。

Tests / assertions：

```bash
source .venv/bin/activate && pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py
```

Rollback / verification point：S2 完成后，`rg -n "_missing_result_event|Fins direct stream ended without result" dayu/cli tests/cli` 不应再显示 CLI 构造业务 RESULT；Service 与 Service tests 可保留该业务 failure 文案。

### S3. Unified CLI HostApiError Presentation

Objective：统一 prompt / interactive / session 的 Host structured error 展示和退出码映射。

Allowed files：

- `dayu/cli/host_api_errors.py` 或语义等价的新 CLI helper 模块。
- `dayu/cli/commands/prompt.py`
- `dayu/cli/commands/interactive.py`
- `dayu/cli/commands/session.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_session_command.py`
- `README.md`，仅在用户可见 CLI 错误文本/退出码变化属于 README 职责时按 README 约束更新。
- `tests/README.md`，如新增 HostApiError presentation test scope。

Exact allowed changes：

- 新增 CLI helper，例如 `dayu.cli.host_api_errors`，定义：
  - `CliHostApiErrorTarget` dataclass：可选 `selector`、`session_id`、`resolved_from_label`、`operation` 等用户可见上下文。
  - `format_host_api_error(command_name: str, error: HostApiError, *, action: str | None = None, target: CliHostApiErrorTarget | None = None) -> str`
  - `exit_code_for_host_api_error(error: HostApiError, *, target: CliHostApiErrorTarget | None = None) -> int`
- helper 必须统一渲染结构化核心：`host_code={error.code.value} host_message={error.message}`。额外上下文如 selector/session id 可以在 session resume/purge 目标错误中添加，但不能改变 core format。
- exit-code policy：
  - `HostApiErrorCode.NOT_FOUND` 且错误来自用户显式 session id selector 时返回 `EXIT_USAGE_ERROR`。
  - label 解析后的 TOCTOU、purge/resume submit、prompt/interactive ensure/create/submit/cancel HostApiError 默认为 `EXIT_FAILURE`，除非已有明确 CLI usage owner 证明它是用户参数错误。
  - prompt / interactive 首次 ensure/create/submit 阶段即使收到 `NOT_FOUND`，也默认是 Host 配置、slot、Session lifecycle 或运行期状态错误；用户没有显式提供 session id selector，因此不得映射为 usage error。
  - 该策略必须由 helper 参数显式表达，不能在 prompt / interactive / session 各自硬编码。
- `session.py` 删除私有 `_HOST_ERROR_TEMPLATE`、`_host_error_context`、`_exit_code_for_host_error`，改用 public helper。保留 `_purge_host_error_message` / `_resume_host_error_message` 的 selector-specific 文案时，它们也必须调用统一 core formatter，或改成构造 target 交给 helper。
- `prompt.py` / `interactive.py` 在 `RuntimeLocationError` 和 usage error 之后、generic `Exception` 之前单独捕获 `HostApiError`，使用统一 helper 渲染并返回 helper exit code。
- 不把 HostApiError presentation 放入 Service；Service 没有 stdout/stderr 或 process exit code ownership。

Tests / assertions：

- `tests/cli/test_session_command.py`：现有 purge/resume HostApiError 测试继续通过，并断言 core format 为 `host_code=... host_message=...`。
- `tests/cli/test_prompt_command.py`：新增 fake Host 在 ensure/create/submit 抛 `HostApiError(code=CONFLICT/INVALID_STATE, message=...)`，断言 stderr 包含 `dayu-cli prompt`、`host_code=<code>`、`host_message=<message>`，exit code 为 `EXIT_FAILURE`。
- `tests/cli/test_interactive_command.py`：新增对应 HostApiError 测试，断言同一 core format 和 exit code。
- helper 的 pure functions 必须有轻量单元测试，覆盖 NOT_FOUND explicit selector -> usage、label TOCTOU -> failure、prompt/interactive NOT_FOUND -> failure、generic HostApiError -> failure。

Validation:

```bash
source .venv/bin/activate && pytest tests/cli/test_session_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py
source .venv/bin/activate && pyright
git diff --check
```

Rollback / verification point：S3 完成后，`rg -n "_host_error_context|_exit_code_for_host_error|host_code=\\{code\\}" dayu/cli/commands` 不应显示 command-local duplicate helpers。

## 6. README Trigger Judgment

当前 plan artifact 本身不需要 README 更新，因为未修改生产代码、测试职责或用户可见行为。

后续 implementation 的 README 判断：

- 修改 `dayu/cli/commands/*` 或新增 `dayu/cli/*.py`：没有专属 `dayu/cli/README.md`，但如果用户可见 CLI 命令参数、输出、退出码或工作流变化，必须先读取根 `README.md` 的 Agent 更新约束，并按其读者边界判断是否更新。
- 修改 `dayu/service/fins_direct.py` 或 Service public contract：必须读取 `dayu/service/README.md` 的 Agent 更新约束并判断是否更新。本 plan 倾向不修改 Service code；若只改 CLI hard assertion，Service README 通常不需要更新。
- 修改 `tests/cli` / `tests/service`：必须读取 `tests/README.md` 的 Agent 更新约束；若测试职责描述新增 HostApiError presentation 或 Fins contract violation，按职责范围更新。
- 涉及 `UI -> Service -> Host -> Engine` 边界说明变化：必须读取 `dayu/README.md` 并判断是否更新。P2-A 预期是落实既有边界，不预期修改 `dayu/README.md`。

## 7. Validation Matrix

Implementation 必跑：

```bash
source .venv/bin/activate && pytest tests/cli/test_session_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_fins_commands.py
source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_fins_direct.py
source .venv/bin/activate && pytest tests/cli/test_import_boundary.py
source .venv/bin/activate && pyright
git diff --check
```

建议补充：

```bash
source .venv/bin/activate && pytest tests/cli/test_arg_parsing.py tests/cli/test_runtime_display.py tests/cli/test_session_terminal_cursor.py
source .venv/bin/activate && pytest tests/service/test_import_boundary.py tests/cli/test_import_boundary.py
```

精确新增/更新断言：

- `tests/cli/test_session_command.py`：`session resume` 不依赖 prompt/interactive private import；HostApiError selector-aware core format 和 exit code 保持。
- `tests/cli/test_prompt_command.py`：HostApiError structured format 和 exit code。
- `tests/cli/test_interactive_command.py`：HostApiError structured format 和 exit code。
- `tests/cli/test_fins_commands.py`：Service stream without RESULT 是 contract violation，不再渲染 CLI-generated Fins failure event。
- `tests/service/test_fins_direct.py`：Service missing RESULT fallback 与 duplicate RESULT fail-fast 继续作为 Service contract 真源。

## 8. Propagation Audit Required After Implementation

implementation artifact 必须列出并确认：

- Session execution path：`prompt` / `interactive` / `session resume` -> CLI public session execution helper -> Service entrypoint runtime -> Host public API -> CLI renderer。确认没有 command-to-command private helper import。
- Fins direct RESULT path：Fins runtime producer -> `FinsDirectCommandService._ensure_result_event` -> CLI stream consumer -> renderer / contract violation。确认缺 RESULT 的业务 fallback 只在 Service 出现。
- HostApiError path：Host public API raises `HostApiError` -> CLI helper formats core code/message and computes exit code -> prompt / interactive / session stderr。确认 command modules 不各自重建映射。
- Durable / trace / memory / audit：P2-A 不改变 durable state、trace、memory、audit、LLM-facing prompt/schema；artifact 应明确 no-touch。

## 9. Completion Report Format

implementation Agent 完成后需报告：

- Completed slices：S1/S2/S3 状态。
- Changed files。
- Direct evidence that DS 03 / DS 10 / DS 11 are closed or reclassified.
- README decisions with target README paths and whether updated.
- Validation commands and results.
- Propagation audit result.
- Residual risks with owner/destination。
