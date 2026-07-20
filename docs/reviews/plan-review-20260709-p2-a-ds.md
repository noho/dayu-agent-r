# WU-SEMANTIC-OWNERSHIP-01 P2-A Plan Review — AgentDS

## Verdict

**pass-with-findings**（4 个 accepted finding，0 个 blocking）

## Review Scope

- Plan: `docs/host/wu-semantic-ownership-01-p2-a-plan.md`
- AgentCodex delivery: `docs/reviews/wu-semantic-ownership-01-p2-a-plan-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p2-a-plan-controller-validation.md`
- Source adjudication: `docs/reviews/fullrepo-semantic-ownership-controller-adjudication.md`
- Control doc: `docs/host/issues-implementation-control.md`
- Design truth: `docs/host/design.md`, `docs/engine/design.md`
- Current code: `dayu/cli/commands/session.py`, `dayu/cli/commands/prompt.py`, `dayu/cli/commands/interactive.py`, `dayu/cli/commands/fins.py`, `dayu/service/fins_direct.py`

## 1. DS 03 / DS 10 / DS 11 Current-Code Root-Cause Evidence

### DS 03: accepted — evidence sufficient

Plan 中 DS 03 的判断经独立代码核对后确认为充分。

直接证据链：

- `dayu/cli/commands/session.py:36-45`：`from dayu.cli.commands.interactive import _execute_interactive_on_existing_session, _prepare_interactive_existing_session_execution` 和 `from dayu.cli.commands.prompt import _execute_prompt_on_existing_session, _prepare_prompt_existing_session_execution`，四个导入均为下划线私有符号。
- `dayu/cli/commands/session.py:251-267`：prompt mode resume 调用 `_prepare_prompt_existing_session_execution(...)` 和 `_execute_prompt_on_existing_session(...)`。
- `dayu/cli/commands/session.py:275-289`：interactive mode resume 调用 `_prepare_interactive_existing_session_execution(...)` 和 `_execute_interactive_on_existing_session(...)`。

Root cause 成立：共享语义"在既有 Session 上执行 prompt turn / interactive REPL"的 owner 缺失，`session resume` 作为第三个消费者只能依赖其它 command module 的 private helper。

但有一个细节 plan 未充分处理：prompt prepare（`prompt.py:236-239`）调用 `_prompt_context_slot_values(ticker=..., fmp_api_key=...)` 构造 context slot values，而 interactive prepare（`interactive.py:296`）调用 `_interactive_context_slot_values()`——两者的 context slot 构造逻辑不同，且当前都位于各自 command module 内。S1 将 prepare/execute 移到新 helper 时，context slot values 的构造策略必须在 plan 中明确：是新 helper 接受已构造的 slot values 作为参数（保持命令差异在 command module），还是新 helper 自己根据 scenario 分发。当前 plan 未对此说明。（→ DS-F01）

### DS 10: partially accepted / updated — evidence sufficient，改判合理

Plan 对 DS 10 的改判合理。原 finding "CLI duplicates Service `_ensure_result_event` missing-result fallback" 在当前代码下需要更新，因为 Service 已经拥有正常缺失 RESULT 的 fallback。

直接证据链：

- `dayu/service/fins_direct.py:477-510`：`_ensure_result_event` 在正常 stream 结束且未见 RESULT 时合成 failure RESULT；重复 RESULT 时 `FinsDirectUsageError` fail fast。
- `tests/service/test_fins_direct.py:499-515`：已覆盖 Service 缺失 RESULT 正常结束合成 failure RESULT。
- `dayu/cli/commands/fins.py:703-731`：`_consume_fins_direct_events` 在消费完 stream 后调用 `_missing_result_event()`（line 726）。
- `dayu/cli/commands/fins.py:899-923`：CLI 本地构造完整的 `FinsEvent` + `FinsResultSummary(FinsResultStatus.FAILURE)`，伪装为业务 failure RESULT。

Root cause 改判正确：Service 现在是正常缺 RESULT 的 fallback owner；CLI 的 `_missing_result_event()` 不是 duplicate fallback，而是更危险的 contract violation 被下游业务 RESULT 掩盖。CLI 应该在 Service contract 被破坏时 fail hard，不生成业务 RESULT。

### DS 11: accepted — evidence sufficient

Plan 中 DS 11 的判断经独立代码核对后确认为充分。

直接证据链：

- `dayu/cli/commands/session.py:92`：`_HOST_ERROR_TEMPLATE: Final[str] = "host_code={code} host_message={message}"`。
- `dayu/cli/commands/session.py:621-629`：`_host_error_context` 使用该模板格式化 HostApiError。
- `dayu/cli/commands/session.py:632-647`：`_exit_code_for_host_error` — NOT_FOUND + 非 label 解析 → `EXIT_USAGE_ERROR`，其余 → `EXIT_FAILURE`。
- `dayu/cli/commands/session.py:150-154`、`session.py:268-273`、`session.py:290-295`、`session.py:331-336`：四处独立捕获 `HostApiError`，使用同一私有 helper。
- `dayu/cli/commands/prompt.py:150-162`：**未**单独捕获 `HostApiError`，落入通用 `Exception` catch，渲染为 `dayu-cli prompt: {exc}`，退出码固定 1。
- `dayu/cli/commands/interactive.py:194-210`：**未**单独捕获 `HostApiError`，落入通用 `Exception` catch，渲染为 `dayu-cli interactive: {exc}`，退出码固定 1。

Root cause 成立：Host API structured error 的 CLI presentation/exit-code owner 未统一。session command 因 list/resume/purge 语义先做了私有实现；prompt / interactive 保持通用 Exception catch。

## 2. S1: `dayu.cli.session_execution` — Glue Facade Risk

### 评估：风险可控，但 plan 缺少关键设计细节

S1 的核心风险是：如果将 prepare/execute 函数从 `prompt.py` / `interactive.py` 移到 `session_execution.py`，但新模块只是原样转发旧私有实现（即新模块 import 旧 private helper 再 re-export），那就变成了 plan 明确禁止的"兼容性 wrapper/glue facade"。

当前 plan 的防护措施：

- Section 3 "Owner Boundary" 中明确："P2-A 需要移动真实 shared behavior，而不是保留旧 private helper 再包一层。新的 CLI helper 必须直接承载 prepare/execute 数据流"。
- S1 "Exact allowed changes" 中明确："不在 `prompt.py` / `interactive.py` 保留仅转发旧私有函数"。
- Stop condition：如果 shared execution 不能在"不复制 REPL / terminal rendering 语义"的情况下抽取到 CLI public helper，应停止并重新裁决。

这些防护措施正确但不够具体。缺少以下关键设计决策：

**DS-F01（accepted, MEDIUM）— context slot values 构造策略未明确**

`prompt.py:236-239` 调用 `_prompt_context_slot_values(ticker=..., fmp_api_key=...)` 而 `interactive.py:296` 调用 `_interactive_context_slot_values()`。S1 将 prepare/execute 移到新 helper 时，新 helper 的 prepare 函数签名有两种合理设计：

- 方案 A：新 helper 接受已构造的 `context_slot_values: dict[str, JsonValue]` 作为参数，context slot 构造差异保留在各自的 command module。
- 方案 B：新 helper 根据 scenario 参数内部分发 context slot 构造。

Plan 未裁决选择哪一种，也未说明 context slot values 的 owner 归属。建议 S1 采用方案 A（接受已构造的 slot values），保持 command-local context 差异在 command module，新 helper 只负责 runtime assembly 和 Session 执行。

**证据**：`docs/host/wu-semantic-ownership-01-p2-a-plan.md` Section 5 S1 "Exact allowed changes" 中未提及 context slot values 的处理方式。

**建议修复**：在 plan Section 5 S1 中补充说明：新 helper 的 prepare 函数接受已由 command module 构造的 `context_slot_values` 参数；`_prompt_context_slot_values` / `_interactive_context_slot_values` 保留在各自 command module（它们是 command-local 关注点，不是 shared execution 语义）。

**DS-F02（accepted, LOW）— 与 RuntimeDisplayController 的设计一致性未讨论**

`dayu/cli/runtime_display.py` 是近期引入的 CLI-owned shared helper 先例，它集中了 thinking guard、final-before-terminal cleanup、cancel cleanup 和 display lifecycle close。S1 的新 helper 应该在 docstring 和边界说明中与 `RuntimeDisplayController` 保持一致的 ownership 语言，避免 CLI 下出现两个"shared execution helper"但职责边界不同的混淆。

**证据**：`dayu/cli/runtime_display.py` 存在且被 prompt.py / interactive.py / session.py 共同使用；plan 中未提及与现有 shared CLI helper 的职责关系。

**建议修复**：在 plan Section 5 S1 或 Section 3 Owner Boundary 中说明新 helper 与 `RuntimeDisplayController` 的职责分工——后者拥有 display/thinking/cancel cleanup lifecycle，前者拥有 session 执行准备/提交/错误处理 lifecycle；两者不重叠，不互相依赖。

## 3. S2: RuntimeError vs Specific CLI Contract Error

### 评估：RuntimeError 在当前错误处理架构下是正确选择

Plan S2 提议：当 `_consume_fins_direct_events(...)` 在 async iterator 结束且未返回 terminal result 时，抛出 `RuntimeError("Fins direct Service stream ended without RESULT")`。该错误由 `run_fins_direct_command` 的通用 `Exception` catch 渲染为 CLI failure。

分析：

- **为什么不应该是更具体的 CLI contract error 类型？** 因为这个错误表示 Service contract 被违反——Service 的 `_ensure_result_event` 已经保证正常 stream 结束必有一个 RESULT。如果 CLI 收到一个没有 RESULT 的 stream，要么是 Service 被绕过（broken test double），要么是 Service 有 bug。这属于 invariant violation，`RuntimeError` 语义匹配。
- **Service owner 会被错误绕过吗？** 不会。通用 `Exception` catch 在 `run_fins_direct_command` 中渲染错误文本并返回 `EXIT_FAILURE`，不会把 contract violation 伪装为 usage error 或业务 failure RESULT。这与 plan 的目标一致。
- **一个潜在问题**：如果未来有更多调用方使用 `_consume_fins_direct_events`，它们也会遇到同一个 `RuntimeError`，但可能期望不同的错误处理。不过当前该函数是 CLI 私有函数（下划线前缀），只有 CLI 一个消费者，这种风险在当前 scope 不成立。

结论：S2 的 `RuntimeError` 选择在当前的错误处理架构和 ownership boundary 下是正确的，不需要更具体的异常类型。

## 4. S3: HostApiError Exit-Code Policy

### 评估：策略正确，但存在一个未覆盖的边缘情况

Plan S3 的 exit-code policy：

- `NOT_FOUND` + 用户显式 session id selector → `EXIT_USAGE_ERROR`（用户给了不存在的 id）
- label 解析后的 TOCTOU、purge/resume submit、prompt/interactive ensure/create/submit/cancel HostApiError → `EXIT_FAILURE`

这个策略整体正确。逐一检验：

**explicit session id NOT_FOUND → EXIT_USAGE_ERROR**：正确。用户显式指定了一个不存在的 session id，这是用户输入错误，应返回 usage error。

**label resolved TOCTOU → EXIT_FAILURE**：正确。用户通过 label 指定目标 session，label 解析时该 session 存在且 OPEN；但到实际操作时（如 submit）session 已不存在。这不是用户输入错误——label 在解析时是有效的——而是运行时状态变化导致的失败，应返回 `EXIT_FAILURE`。

**prompt/interactive ensure/create/submit/cancel HostApiError → EXIT_FAILURE**：正确。这些是正常操作路径上的 Host 状态机拒绝（如 CONFLICT、INVALID_STATE），不是用户 CLI 参数错误，应返回 `EXIT_FAILURE`。

**DS-F03（accepted, LOW）— prompt/interactive 首次调用时的 NOT_FOUND 场景未明确**

Plan S3 exit-code policy 中"prompt/interactive ensure/create/submit/cancel HostApiError 默认为 EXIT_FAILURE"覆盖了大部分场景。但有一个边缘情况：`dayu-cli prompt`（不带 session selector）首次运行时，`ensure_session` 可能在极端的 Host 内部错误下抛出 `NOT_FOUND`（例如 slot 配置指向的默认 session 模板不存在）。当前策略将其归为 `EXIT_FAILURE`，这在语义上是合理的——用户没有指定 session id，所以不是用户输入错误——但 plan 应该明确说明这个判断依据。

**证据**：`docs/host/wu-semantic-ownership-01-p2-a-plan.md` Section 5 S3 exit-code policy bullet 中，prompt/interactive ensure 场景未显式说明为什么 NOT_FOUND 不应映射为 usage error。

**建议修复**：在 S3 exit-code policy 中补充一句：prompt/interactive 的 `NOT_FOUND`（如 slot 模板不存在）是 Host 配置/运行时错误，不是用户 CLI 参数错误，因此默认为 `EXIT_FAILURE`。

**关于 `HostApiErrorCode` 全量映射**：当前 `HostApiErrorCode` 包括 `not_found`、`invalid_state`、`conflict`、`idempotency_conflict`、`permission_denied`、`unsupported_operation`、`internal_error`（`docs/host/design.md:1241-1247`）。S3 helper 当前只显式区分了 `NOT_FOUND` + explicit selector → usage，其余 → failure。这是充分的最小策略——其他 code（如 `permission_denied`、`internal_error`）明显不是用户输入错误，不需要额外的条件判断。

## 5. 分层违规检查

### 评估：无分层违规

逐一检查 plan 的 ownership boundary 定义（Section 3）：

- **Service 不被要求承担 CLI stdout/stderr/exit code**：S3 明确"不把 HostApiError presentation 放入 Service；Service 没有 stdout/stderr 或 process exit code ownership"。
- **CLI 不构造 Service/Fins 业务事实**：S2 删除 CLI 本地 `_missing_result_event()`，CLI 不再构造 Fins business RESULT。
- **Service helper 继续只做 product entrypoint runtime**：Section 3 Owner Boundary 表格中明确"Service helper 继续拥有 Host submit/watch/cancel"，"不解析 ParsedCliArgs、不写 stdout/stderr、不安装 signal handler"。
- **CLI helper 可以依赖 Service，但 Service 不反向依赖 CLI**：Section 3 明确此约束。
- **Host public API 不改**：Section 4 Non-goals 明确"不改变 Host public API、Host durable schema"。

无分层违规。plan 的 owner boundary 与设计真源 `docs/host/design.md:1218-1227`（Service-facing public API 边界）和 `docs/host/design.md:1824-1841`（Service / channel adapter 拥有 Outbox 补读和 live watch）一致。

## 6. README / Test / Design 触发检查

### 评估：触发判断基本充分，但缺少 import-boundary test 的明确要求

**DS-F04（accepted, LOW）— import-boundary test 未被列为 S1/S3 的必做验证**

Plan Section 7 Validation Matrix 的建议补充中提到了 `tests/cli/test_import_boundary.py`，但：

- 该文件当前不存在（`ls tests/cli/test_import_boundary.py` → not found）。
- S1 rollback/verification point 中要求 `rg -n "commands\\.(prompt|interactive) import .*_" dayu/cli/commands/session.py` 无命中，这是 source scan 而非 import-boundary test。
- Plan 未说明是否应该在 S1 中创建 `tests/cli/test_import_boundary.py` 或在现有测试中新增 AST-level import boundary 断言。

鉴于 `dayu/cli/commands/session.py` 当前有四条跨 command module 私有 import，而 S1 的目标就是消除它们，应该有自动化测试锁定"session.py 不 import prompt/interactive 私有符号"。纯 source scan / grep 容易在后续改动中被绕过。

**证据**：`docs/host/wu-semantic-ownership-01-p2-a-plan.md` Section 5 S1 Tests/assertions 中提到"添加 import boundary / source scan 断言"，但未明确是测试文件中的断言还是手动 grep。

**建议修复**：在 S1 Tests/assertions 中将 import boundary 断言升级为明确的测试要求——例如在 `tests/cli/test_session_command.py` 或新文件 `tests/cli/test_import_boundary.py` 中添加 AST 扫描测试，断言 `dayu/cli/commands/session.py` 不包含对 `dayu.cli.commands.prompt` 或 `dayu.cli.commands.interactive` 的私有符号 import。

**README 触发**：Plan Section 6 的 README 判断框架正确。Implementation 前应先读取各目标 README 的 Agent 更新约束再决定是否更新。当前 plan-only gate 不需要 README 更新。

**Design 触发**：P2-A 不改变 Host public API、durable schema 或 Service entrypoint contract，不需要更新 `docs/host/design.md` 或 `docs/engine/design.md`。Plan Section 4 Non-goals 中已明确。

## 7. Validation Matrix Coverage

### 评估：覆盖基本充分，有两处遗漏

Plan Section 7 的必跑验证矩阵覆盖了受影响的核心测试文件。对照当前 `tests/cli/` 下实际存在的测试文件：

**已覆盖**：`test_session_command.py`、`test_prompt_command.py`、`test_interactive_command.py`、`test_fins_commands.py`、Service tests、pyright、`git diff --check`。

**建议补充已验证**：`test_arg_parsing.py`、`test_runtime_display.py`、`test_session_terminal_cursor.py`（在 plan 建议补充中已列出）。

**遗漏**：

1. **Import-boundary test**（见 DS-F04）：当前不存在，S1 需要创建或扩展现有测试。

2. **S3 HostApiError helper 单元测试**：Plan S3 Tests/assertions 中提到"如果 helper 暴露独立 pure function，可添加轻量单元测试"。鉴于 S3 的 helper 函数（`format_host_api_error`、`exit_code_for_host_api_error`）确实是独立 pure function，应将单元测试从"可添加"升级为"必做"——这些函数承载了 CLI exit-code policy，应该是项目中最容易测试、最不应该缺少覆盖的代码。

## Findings Summary

| ID | Severity | 文件/章节 | 阻断 | 描述 |
|---|---|---|---|---|
| DS-F01 | MEDIUM | Plan §5 S1 | No | context slot values 构造策略未明确——新 helper 接受已构造的 slot values 还是根据 scenario 内部分发 |
| DS-F02 | LOW | Plan §5 S1 / §3 | No | 与 RuntimeDisplayController 的设计一致性未讨论——两个 CLI shared helper 的职责分工未说明 |
| DS-F03 | LOW | Plan §5 S3 exit-code policy | No | prompt/interactive 首次 ensure 时的 NOT_FOUND 场景未明确说明为何不是 usage error |
| DS-F04 | LOW | Plan §5 S1 Tests / §7 | No | import-boundary test 未被列为 S1/S3 必做验证；建议从 source scan/grep 升级为 AST-level 自动化测试 |

## Propagation Audit Preview

基于当前 plan 的 owner boundary 定义，implementation 后的 propagation audit 应确认以下路径（预判无风险）：

| 路径 | 语义 | 预期结论 |
|---|---|---|
| prompt / interactive / session resume → CLI public helper → Service entrypoint runtime → Host public API → CLI renderer | Session execution | 无 command-to-command private import |
| Fins runtime producer → Service `_ensure_result_event` → CLI stream consumer → renderer / contract violation | Fins direct RESULT | 缺 RESULT 业务 fallback 只在 Service |
| Host public API → `HostApiError` → CLI helper format core → prompt / interactive / session stderr | HostApiError presentation | command modules 无各自映射 |
| Durable / trace / memory / audit / LLM-facing prompt/schema | P2-A scope | no-touch（plan 明确不改变） |

## Residual Risks

- S1 的 context slot values 构造策略若未在 implementation 前裁决，可能导致新 helper 签名反复修改或在 command module 和新 helper 之间产生隐式依赖。
- S3 HostApiError helper 的 exit-code policy 中 `NOT_FOUND` 在非 explicit-session-id 场景下的行为虽然正确，但缺乏显式测试覆盖可能导致后续维护时策略被无意修改。
- Plan 没有要求新增 `tests/cli/test_import_boundary.py`——如果实现时仅靠 grep/comment 做 import boundary 验证，后续重构可能重新引入跨 command private import。
