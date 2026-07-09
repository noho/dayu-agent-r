# WU-SEMANTIC-OWNERSHIP-01 P2-A Plan Review — AgentMiMo

## Scope

- Plan artifact: `docs/host/wu-semantic-ownership-01-p2-a-plan.md`
- AgentCodex delivery: `docs/reviews/wu-semantic-ownership-01-p2-a-plan-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p2-a-plan-controller-validation.md`
- Source adjudication: `docs/reviews/fullrepo-semantic-ownership-controller-adjudication.md`
- Control doc: `docs/host/issues-implementation-control.md`
- Design truth: `docs/host/design.md`, `docs/engine/design.md`
- Review mode: adversarial plan review per task file challenge areas.

## Verdict

**pass-with-findings**。0 个 blocking finding，3 个 non-blocking findings。

Plan 整体质量良好：三类语义所有权漂移的 root-cause 判断有直接代码证据支撑，owner boundary 划分合理，slice 切分符合控制文档小型跨模块 cleanup 的 1-3 slice 原则，stop conditions 明确。以下 findings 均为实现阶段可修复的 clarity / precision 问题，不阻塞 plan acceptance。

## Challenge Area 1: DS 03 / DS 10 / DS 11 Root-Cause Evidence

### DS 03: accepted — 证据充分

直接代码证据全部核对通过：

- `dayu/cli/commands/session.py:36-45` 确实从 `dayu.cli.commands.interactive` 导入 `_execute_interactive_on_existing_session`、`_prepare_interactive_existing_session_execution`，从 `dayu.cli.commands.prompt` 导入 `_execute_prompt_on_existing_session`、`_prepare_prompt_existing_session_execution`。
- `session.py:251-267` 在 prompt mode 调用 `_prepare_prompt_existing_session_execution` 和 `_execute_prompt_on_existing_session`。
- `session.py:275-289` 在 interactive mode 调用 `_prepare_interactive_existing_session_execution` 和 `_execute_interactive_on_existing_session`。

Root cause 判断正确：共享语义没有 public owner，`session resume` 只能依赖其它 command module 的 private helper。

### DS 10: partially accepted / updated — 改判合理

直接代码证据核对通过：

- `dayu/service/fins_direct.py:477-510` 的 `_ensure_result_event` 确实在正常结束且未见 RESULT 时产出 `_missing_result_event(...)`，且对重复 RESULT 抛 `FinsDirectUsageError`。Service tests `tests/service/test_fins_direct.py:499-515` 已覆盖。
- `dayu/cli/commands/fins.py:703-731` 的 `_consume_fins_direct_events` 在 async iterator 结束后调用 `_missing_result_event()` (line 726)。
- `dayu/cli/commands/fins.py:899-923` 构造另一个独立的 failure RESULT 事件。

改判合理：Service 已是 producer 正常结束缺 RESULT 的 fallback 真源；CLI 保留 `_missing_result_event()` 构成 contract violation 被伪装成业务 failure result 的问题。这不是"CLI 重复 Service 逻辑"的原始判断，而是更精确的"CLI 在 Service contract 已保证的前提下仍构造伪终态"。

### DS 11: accepted — 证据充分

直接代码证据核对通过：

- `session.py:150-154` 单独捕获 `HostApiError`，渲染 `host_code=... host_message=...`，调用 `_exit_code_for_host_error(...)`。
- `session.py:621-647` 拥有 `_host_error_context` 和 `_exit_code_for_host_error`，exit-code policy 为 `NOT_FOUND` + `not resolved_from_label` → `EXIT_USAGE_ERROR`，其余 → `EXIT_FAILURE`。
- `prompt.py:150-162` 未单独捕获 `HostApiError`，落入 generic `Exception` → `dayu-cli prompt: {exc}` + `EXIT_FAILURE`。
- `interactive.py:194-210` 同样落入 generic `Exception` → `dayu-cli interactive: {exc}` + `EXIT_FAILURE`。

Root cause 判断正确：Host structured error 的 CLI presentation/exit-code owner 未统一。

## Challenge Area 2: S1 Glue Facade Risk

**Non-blocking finding F-01**。

Plan Section 5 S1 提议将 prompt/interactive existing-session prepare/execute 的"真实实现"移到新 `dayu.cli.session_execution` 模块，并要求 "prompt / interactive command modules 调用新 helper"。

当前代码结构是：
- `prompt.py` 内部：`run_prompt_command` → `_run_prompt_command_async` → `_prepare_prompt_existing_session_execution` → `_execute_prompt_on_existing_session`。
- `session.py` 导入并调用同一组 `_prepare_*` / `_execute_*` private helpers。

Plan 说"将真实实现从 prompt.py / interactive.py 私有 helper 移到新 helper"，但未明确区分两种迁移模式：

**模式 A（完全迁移）**：把 `_prepare_prompt_existing_session_execution` 和 `_execute_prompt_on_existing_session` 的函数体移到 `session_execution.py`，prompt.py 内部也改为调用新 public helper。这样 prompt.py 的内部调用链变成 `run_prompt_command` → `_run_prompt_command_async` → `session_execution.prepare_prompt_session_execution(...)` → `session_execution.execute_prompt_on_session(...)`。Private helpers 从 prompt.py 删除。

**模式 B（仅暴露 public API）**：private helpers 保留在 prompt.py 内部作为实现细节，新 `session_execution.py` 只是 import 并 re-export 为 public API。这会变成 glue facade。

Plan 当前措辞偏向模式 A（"不在 prompt.py / interactive.py 保留仅转发旧私有函数"），但 `prompt.py` 自身的 `_run_prompt_command_async` 也需要调用 prepare/execute。如果 private helpers 移走了，prompt.py 内部必须改用新 public helper。Plan 应显式说明这一点，否则 implementation agent 可能选择模式 B。

建议：在 S1 Exact allowed changes 中补充一句："prompt.py 的 `_run_prompt_command_async` 和 interactive.py 的 `_run_interactive_command_async` 内部也改用新 public helper；原 private `_prepare_*` / `_execute_*` 函数从 prompt.py / interactive.py 删除。"

**Severity**: low
**阻断判断**: 不阻断。Plan 意图明确（模式 A），只是措辞可更精确。

## Challenge Area 3: S2 RuntimeError vs Specific Error

**Non-blocking finding F-02**。

Plan Section 5 S2 提议用 `RuntimeError("Fins direct Service stream ended without RESULT")` 作为 contract violation error type。

问题：
1. `RuntimeError` 是 Python 通用 runtime 异常，语义过于宽泛。它不区分"Service contract 被违反"和"其它 runtime 故障"。
2. `_consume_fins_direct_events` 的当前 docstring 已标注 `:raises RuntimeError:`，说明当前代码就用 RuntimeError 做其它用途（line 730: `raise RuntimeError("missing-result event did not contain result")`）。新增的 contract violation RuntimeError 会与已有的 RuntimeError 混淆。
3. 测试断言需要区分 contract violation 和普通 runtime error。如果用 `RuntimeError`，测试只能靠 stderr 文本匹配，无法用异常类型断言。

建议：使用自定义异常 `FinsDirectStreamContractViolation(RuntimeError)`，放在 `dayu/cli/commands/fins.py` 或 `dayu/cli/contracts.py`。它继承 `RuntimeError` 保持向后兼容，但有明确语义。`run_fins_direct_command` 的 generic `Exception` catch 仍能捕获它。

**Severity**: low
**阻断判断**: 不阻断。当前方案功能正确，只是类型精度可改进。

## Challenge Area 4: S3 HostApiError Exit-Code Policy

Plan Section 5 S3 的 exit-code policy 核对通过：

- `HostApiErrorCode.NOT_FOUND` + 用户显式 session id selector（`resolved_from_label=False`）→ `EXIT_USAGE_ERROR`：当前 `session.py:645` 实现一致。用户输入不存在的 session id 是 usage error，正确。
- label 解析后的 TOCTOU NOT_FOUND → `EXIT_FAILURE`：当前 `session.py:645` 实现一致。用户输入了合法 label，label 解析成功，但 session 在 Host API 调用时已被删除，这是系统 race condition 而非用户输入错误，正确。
- prompt/interactive 的 HostApiError 默认 → `EXIT_FAILURE`：与当前 generic Exception catch 行为一致，但升级为 structured format，正确。

Policy 通过 helper 参数显式表达（`target: CliHostApiErrorTarget | None`），不在各 command 硬编码。设计合理。

无 finding。

## Challenge Area 5: Layering Violations

Plan owner boundary table确认：
- Service 不拥有 process exit code 或 stdout/stderr。
- CLI helper 拥有 command execution composition、stderr formatting、exit code mapping。
- Host owns `HostApiError` facts 但不拥有 CLI presentation。

Plan Section 3 明确："Service helper 继续只做 product entrypoint runtime 和 Host public API 协议，不解析 ParsedCliArgs、不写 stdout/stderr、不安装 signal handler。CLI helper 可以依赖 Service，但 Service 不反向依赖 CLI。"

S3 Exact allowed changes 明确："不把 HostApiError presentation 放入 Service；Service 没有 stdout/stderr 或 process exit code ownership。"

无分层违反。无 finding。

## Challenge Area 6: README / Test / Design Triggers

Plan Section 6 的 README trigger 判断：

- 当前 plan artifact 不修改生产代码，不需要 README 更新。正确。
- Implementation 阶段的触发规则已列出：root README（CLI 用户可见输出/退出码/工作流变化）、`dayu/service/README.md`（Service public contract 变化）、`tests/README.md`（测试职责描述变化）、`dayu/README.md`（分层关系变化）。

这些触发规则具体且可操作。Implementation agent 可以在对应 slice 完成后按规则判断。

Design truth trigger：Plan 不修改 Host public API、Host durable schema、Engine runner，因此不需要更新 `docs/host/design.md` 或 `docs/engine/design.md`。正确。

**Non-blocking finding F-03**：Plan Section 5 S1 Allowed files 列出 `tests/cli/test_import_boundary.py` 或"现有 CLI import boundary 测试文件，如存在"。代码搜索确认 `tests/cli/test_import_boundary.py` 不存在（只有 `tests/host/`、`tests/service/`、`tests/engine/` 等目录下有 import boundary 测试）。Plan 应明确说明 S1 需要新建此文件，而非假设它已存在。

**Severity**: low
**阻断判断**: 不阻断。Implementation agent 会发现文件不存在并自行创建。

## Challenge Area 7: Validation Matrix Coverage

Plan Section 7 validation matrix：

**必跑测试**：
- `tests/cli/test_session_command.py` — 覆盖 session resume HostApiError 和 execution path。
- `tests/cli/test_prompt_command.py` — 覆盖 prompt command 行为。
- `tests/cli/test_interactive_command.py` — 覆盖 interactive command 行为。
- `tests/cli/test_fins_commands.py` — 覆盖 Fins direct contract violation。
- `tests/service/test_entrypoint_runtime.py` / `test_entrypoint_runtime_prompt_path.py` / `test_entrypoint_runtime_interactive_path.py` — 覆盖 Service entrypoint runtime。
- `tests/service/test_fins_direct.py` — 覆盖 Service missing RESULT fallback。
- `pyright` — 类型检查。
- `git diff --check` — whitespace 检查。

**建议补充**：
- `tests/cli/test_import_boundary.py`（新建后）。
- `tests/service/test_import_boundary.py`。
- `tests/cli/test_arg_parsing.py`、`test_runtime_display.py`、`test_session_terminal_cursor.py`。

覆盖足够。S1/S2/S3 的核心行为变更都有对应测试文件覆盖。Import boundary 测试在建议补充中已列出。

无 finding。

## Findings Summary

| ID | Severity | Plan Section | 描述 | 阻断 | 建议修复 |
|---|---|---|---|---|---|
| F-01 | low | Section 5 S1 | prompt/interactive 内部调用链是否也改用新 public helper 未显式说明 | 不阻断 | 在 S1 Exact allowed changes 中补充 prompt.py / interactive.py 内部也改用新 public helper，删除旧 private helpers |
| F-02 | low | Section 5 S2 | `RuntimeError` 语义过宽，与已有 RuntimeError 用途混淆 | 不阻断 | 改用 `FinsDirectStreamContractViolation(RuntimeError)` 自定义异常 |
| F-03 | low | Section 5 S1 | `tests/cli/test_import_boundary.py` 不存在但被列为 allowed file | 不阻断 | 明确说明 S1 需新建此文件 |

## Propagation Audit Note

本 review 不修改代码。Implementation 完成后需按 Plan Section 8 做 propagation audit：

- Session execution path：确认 prompt / interactive / session resume → CLI public helper → Service entrypoint runtime → Host public API → CLI renderer，无 command-to-command private import。
- Fins direct RESULT path：确认缺 RESULT 的业务 fallback 只在 Service 出现，CLI 只做 contract violation fail-fast。
- HostApiError path：确认 command modules 不各自重建映射。
- Durable / trace / memory / audit：确认 P2-A 不改变。
