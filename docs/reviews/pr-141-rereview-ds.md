# PR 141 targeted re-review

## Scope

- Mode: targeted re-review（只复核 controller accepted findings 的 fix 是否关闭）
- PR: [#141](https://github.com/noho/dayu-agent-r/pull/141)
- Controller adjudication: `docs/reviews/pr-141-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/pr-141-fix-codex.md`
- Output file: `docs/reviews/pr-141-rereview-ds.md`
- Review timestamp: 2026-06-14 18:51 CST
- Reviewed files:
  - `dayu/cli/agent_entrypoint.py`（新增）
  - `dayu/cli/commands/prompt.py`
  - `dayu/cli/commands/interactive.py`
  - `dayu/cli/main.py`
  - `tests/cli/test_prompt_command.py`
  - `tests/cli/test_interactive_command.py`
- Excluded: PR-RV-F02（controller 裁决 deferred-with-owner，本轮不重新打开）

## Findings

### PR-RV-F01 — 已修复

**Finding 原文**：`prompt.py` / `interactive.py` 存在大量重复私有函数（workspace 解析、config 校验、文本裁剪、execution override 映射、unsupported flag 检测、SIGINT monitor）。

**Fix 验证**：

- 新增 `dayu/cli/agent_entrypoint.py`（305 行），抽取 8 个共享组件：
  - `CliSigintMonitor` — 统一 SIGINT 观察器（install / close / notify / wait_next）
  - `resolve_workspace_root` — workspace root 解析
  - `resolve_explicit_config_dir` — 显式 config 目录解析与 containment 校验
  - `optional_stripped_text` — 可选 CLI 文本校验
  - `require_cli_text` — 必填 CLI 文本校验
  - `unsupported_execution_option_names` — 旧执行参数检测
  - `service_run_overrides_from_args` — 参数到 ServiceRunOverrides 映射
  - `package_config_root` — 包内默认配置根目录

- `prompt.py` 与 `interactive.py` 中原 7 个重复私有函数（`_resolve_workspace_root`、`_resolve_explicit_config_dir`、`_optional_stripped_text`、`_require_cli_text`、`_package_config_root`、`_service_run_overrides_from_args`、`_unsupported_execution_option_names`）已全部移除，改为从 `agent_entrypoint` import。grep 确认零残留。

- 原 `_PromptSigintMonitor` 与 `_InteractiveSigintMonitor` 已移除，统一为 `CliSigintMonitor`。

**边界检查**：

- `agent_entrypoint.py` 仅 import 标准库 + `dayu.cli.arg_parsing` + `dayu.service.host_assembly.ServiceRunOverrides`。零 `dayu.host` / `dayu.engine` / `dayu.fins` import。保持在 CLI UI adapter 层内。
- 共享模块不承载 Service 语义、不调用 Host API、不访问 Fins storage。
- `ServiceRunOverrides` import 与原 prompt.py / interactive.py 已有依赖一致，不构成新增跨层依赖。

**行为保持检查**：

- prompt SIGINT 控制流不变：`_submit_prompt_turn_handling_sigint` 仍为单 SIGINT → cancel 或 return None；finally 块仍保证 monitor.close()。
- interactive 双 SIGINT 控制流不变：`_submit_interactive_turn_handling_sigint` → `_cancel_interactive_turn_after_first_sigint` → `_wait_for_run_id_or_local_exit` / `_cancel_run_waiting_for_terminal_or_second_sigint`。finally 块仍保证 monitor.close()。
- unsupported flag fail-fast 不变：`prompt.py` 和 `interactive.py` 各自保留 `_raise_for_unsupported_execution_options` wrapper，使用命令专属 `UsageError` 类型，核心检测逻辑共享 `unsupported_execution_option_names`。
- error_factory 模式保持错误类型命令专属：`CliCommandUsageError` vs `CliInteractiveUsageError`，在各自 `run_*_command` 的 except 块正确捕获。
- 测试更新：`test_prompt_command.py` 与 `test_interactive_command.py` 的测试 monitor 子类均继承共享 `CliSigintMonitor`，测试覆盖 SIGINT before/after run_id、cancel request 构造、second SIGINT local exit、unsupported flag rejection、config containment。62 passed（targeted）+ 94 passed（full CLI）。

**结论**：PR-RV-F01 已正确修复。重复逻辑已抽取到 CLI 层内共享模块，边界清晰，用户可见行为、exit code、cancel 语义、unsupported flag fail-fast 均保持不变。

---

### PR-RV-F03 — 已修复

**Finding 原文**：`_normalize_system_exit_code` docstring 写 `:raises ValueError:` 但代码无任何 raise 路径。

**Fix 验证**：

- `dayu/cli/main.py:88-89` docstring 已修改：
  - 旧：`:raises ValueError: 本函数不主动抛出；异常输入按失败退出码处理`
  - 新：`:raises Exception: 本函数不主动抛出异常；非整数载荷按失败退出码处理。`
- 函数体未变（lines 92-97）：`code is None → EXIT_SUCCESS`、`isinstance(code, int) → code`、`else → EXIT_FAILURE`。零 raise 路径。
- grep 确认 `main.py` 中不再出现 `ValueError`。

**结论**：PR-RV-F03 已正确修复。docstring 不再声称可能抛出 `ValueError`，行为未变。

---

### 新问题检查

沿以下维度对 fix 做 adversarial pass，未发现新问题：

1. **prompt/interactive 用户可见行为**：`_run_prompt_command_async` / `_run_interactive_command_async` 入口参数解析、runtime assembly、session 管理、submit、cancel、terminal rendering 路径未变。共享函数行为与抽取前一致（逐一对比 `resolve_workspace_root`、`resolve_explicit_config_dir`、`require_cli_text`、`optional_stripped_text`、`service_run_overrides_from_args`、`unsupported_execution_option_names` 的实现）。

2. **cancel 语义**：prompt 单 SIGINT cancel、interactive 双 SIGINT（第一次 cancel + 第二次 local exit）语义不变。`CliSigintMonitor` 的 install/close/notify/wait_next 与原 `_PromptSigintMonitor` / `_InteractiveSigintMonitor` 实现一致。

3. **unsupported flag fail-fast**：各命令的 `_raise_for_unsupported_execution_options` wrapper 保留，错误消息格式不变，exit code 不变（EXIT_USAGE_ERROR）。

4. **Host public API path**：prompt.py / interactive.py 的 Host API 调用（`open_host`、`ensure_session`/`create_session`、`submit_followup`、`cancel_run`、`watch_session_events`、`read_outbox_terminal_items`）均经 `entrypoint_runtime.py` Service helper，fix 未触碰这些路径。

5. **Service/reuse boundary**：`agent_entrypoint.py` 是 CLI 层内模块，不向 Service 暴露；Service helper（`entrypoint_runtime.py`）不依赖 CLI 层。fix 未改变分层。

6. **`package_config_root()` 使用 `__file__`**：`Path(__file__).resolve().parents[1] / "config"` — 与原实现一致，依赖 `agent_entrypoint.py` 位于 `dayu/cli/` 下。若未来移动此文件需同步更新，但这是 package-relative path 的标准用法，风险低。

7. **`error_factory` 模式**：共享函数通过 `Callable[[str], ValueError]` 参数化错误类型，调用方传入命令专属 `UsageError`。`ValueError` 子类在 `except CliCommandUsageError` / `except CliInteractiveUsageError` 中被正确捕获，不会泄漏到外层 `except Exception`。

8. **测试覆盖**：targeted 测试（62 passed）覆盖 SIGINT before/after run_id、cancel request 构造、second SIGINT local exit、unsupported flag rejection、config containment；full CLI 测试（94 passed）覆盖所有 CLI 命令。pyright 0 errors。未观察到测试因抽取而弱化。

## Open Questions

无。

## Residual Risk

- PR-RV-F02（SigintMonitor.install() 平台降级时无诊断）保持 deferred-with-owner，归入 `WU-CLI-01-RR-06` 后续 signal/cancel adapter work。本轮未处理，也不应在本 gate 处理。
- `WU-CLI-01-RR-01` 至 `WU-CLI-01-RR-10` 均保持已有 owner/destination，fix 未引入新 residual risk。
