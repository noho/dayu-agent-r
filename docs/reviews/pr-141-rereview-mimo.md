# PR 141 targeted re-review — PR-RV-F01 / PR-RV-F03 fix verification

## Scope

- Mode: targeted re-review（只复核 controller accepted findings 的 fix）
- PR: #141
- Base: main
- Head: phase/host-ui-implementation
- Output file: `docs/reviews/pr-141-rereview-mimo.md`
- Included scope:
  - `dayu/cli/agent_entrypoint.py`（新增共享 helper）
  - `dayu/cli/commands/prompt.py`（复用 helper）
  - `dayu/cli/commands/interactive.py`（复用 helper）
  - `dayu/cli/main.py`（docstring 修正）
  - `tests/cli/test_prompt_command.py`（测试引用迁移）
  - `tests/cli/test_interactive_command.py`（测试引用迁移）
  - `docs/reviews/pr-141-fix-codex.md`（fix artifact）
- Excluded scope: PR-RV-F02（controller 裁决 deferred-with-owner，本轮不复核）

## Findings

未发现实质性问题。

### PR-RV-F01 fix 验证：`prompt.py` / `interactive.py` 重复逻辑已抽取 ✅

- **原始问题**: `prompt.py` 与 `interactive.py` 各自独立实现了 7 个实质相同的私有函数（`_resolve_workspace_root`、`_resolve_explicit_config_dir`、`_optional_stripped_text`、`_require_cli_text`、`_package_config_root`、`_service_run_overrides_from_args`、`_unsupported_execution_option_names`）及 `_PromptSigintMonitor` / `_InteractiveSigintMonitor`，违反"重复逻辑必须抽取"约束。
- **Fix 实现**: 新增 `dayu/cli/agent_entrypoint.py`，将上述 7 个函数和 `CliSigintMonitor` 抽取到 CLI UI adapter 层内共享模块。`prompt.py`（line 16-24）和 `interactive.py`（line 18-26）改为从 `agent_entrypoint` 导入，保留各自 Session/turn/REPL/cancel 控制流。
- **直接证据**:
  - `grep` 确认 `prompt.py` 和 `interactive.py` 中不存在旧的 `_resolve_workspace_root`、`_resolve_explicit_config_dir`、`_optional_stripped_text`、`_require_cli_text`、`_package_config_root`、`_service_run_overrides_from_args`、`_unsupported_execution_option_names`、`_PromptSigintMonitor`、`_InteractiveSigintMonitor` 定义。
  - `agent_entrypoint.py` 导出的 8 个符号（`CliSigintMonitor`、`package_config_root`、`optional_stripped_text`、`resolve_explicit_config_dir`、`resolve_workspace_root`、`service_run_overrides_from_args`、`unsupported_execution_option_names`）均被 `prompt.py` 和 `interactive.py` 导入使用。
  - 测试文件 `test_prompt_command.py`（line 17）和 `test_interactive_command.py`（line 17）已更新为从 `dayu.cli.agent_entrypoint` 导入 `CliSigintMonitor` 和 `package_config_root`。
- **Fix 是否关闭原始问题**: 已关闭。7 个重复函数和 2 个重复 SIGINT monitor 类均已抽取到共享模块。

### PR-RV-F03 fix 验证：`_normalize_system_exit_code` docstring 已修正 ✅

- **原始问题**: docstring 写 `:raises ValueError:`，但函数无 `ValueError` 抛出路径，误导调用方。
- **Fix 实现**: `main.py` line 89 改为 `:raises Exception: 本函数不主动抛出异常；非整数载荷按失败退出码处理。`
- **直接证据**: 函数体（lines 92-97）只有三条路径——`code is None` → `EXIT_SUCCESS`、`isinstance(code, int)` → `code`、其它 → `EXIT_FAILURE`——均为 return，无 raise。修正后的 docstring 准确描述了函数行为。
- **Fix 是否关闭原始问题**: 已关闭。

## 用户可见行为、cancel 语义、flag fail-fast、API 路径、Service 边界检查 ✅

- **用户可见行为**: `prompt.py` 和 `interactive.py` 保留各自 Session 构建、turn 提交、cancel 触发、终端渲染和退出码逻辑，未改变。
- **cancel 语义**: `CliSigintMonitor`（`agent_entrypoint.py:28-110`）的 `install`/`close`/`notify`/`wait_next` 实现与原 `_PromptSigintMonitor`/`_InteractiveSigintMonitor` 行为一致——count-based event 等待，调用方决定 cancel 语义。
- **unsupported flag fail-fast**: `unsupported_execution_option_names`（`agent_entrypoint.py:214-247`）检测逻辑不变，`prompt.py` 和 `interactive.py` 仍各自调用该函数并在发现 unsupported options 时 fail-fast。
- **Host public API path**: 未引入 `agent_entrypoint.py` 对 Host API 的直接调用；`prompt.py`/`interactive.py` 仍通过 `ServiceRunOverrides` + `open_host` 走 Service/Host 路径。
- **Service/reuse boundary**: `agent_entrypoint.py` 只 import `dayu.cli.arg_parsing` 和 `dayu.service.host_assembly.ServiceRunOverrides`，不 import `dayu.host`/`dayu.engine`/`dayu.fins`/`dayu.runtime`，未越界。

## 新问题检查 ✅

Fix 未引入新问题：
- `agent_entrypoint.py` 模块 docstring 明确声明"不承载 Service 语义，不调用 Host API，也不访问 Fins storage"（line 3-6），与实际实现一致。
- `__all__` 导出 8 个符号，均被实际使用，无死导出。
- `UsageErrorFactory` 类型别名（line 20）为 `Callable[[str], ValueError]`，与 `prompt.py`/`interactive.py` 的 `UsageError` 工厂一致。
- Validation evidence（用户提供）：62 passed（3 文件）、94 passed（全 cli）、pyright 0 errors、git diff --check clean。

## Open Questions

无。

## Residual Risk

- PR-RV-F02 保持 deferred-with-owner（`WU-CLI-01-RR-06`），不属本轮 scope。
- `WU-CLI-01-RR-01` 至 `WU-CLI-01-RR-10` 均保持 controller adjudication 的 owner/destination。
