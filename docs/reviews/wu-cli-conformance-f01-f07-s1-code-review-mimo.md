# Code Review

## Scope

- Mode: current changes
- Branch: `codex/interactive-oracle`
- Base: `4a3dca64`（accepted plan commit）
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-s1-code-review-mimo.md`
- Included scope: workspace diff 相对 HEAD 的 15 个生产/测试文件
- Excluded scope: frozen docs/registry、Host/Engine、`dayu.runtime`、README（延迟到 S8）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

以下逐项验证了计划 §3 的核心 contract，均符合预期：

### 1. `--config` action/help 彻底删除

- **入口**: `dayu/cli/arg_parsing.py` `_build_runtime_arguments_parent` 函数已整体删除（原 L482–L501）。
- **直接证据**: `build_parser()` 中 root/command/action 三种 parent 均直接使用 `_build_common_arguments_parent` 返回的 `common_parent`，不再经 `_build_runtime_arguments_parent` 包装。`_register_session_command` 签名从 `(command_parent, action_common_parent, action_runtime_parent)` 简化为 `(command_parent, action_parent)`，三个 session action 统一使用同一个 `action_parent`。
- **测试覆盖**: `test_every_parser_scope_omits_removed_config_action` 递归收集全部 17 个 parser scope，逐个断言 `_actions` 中无 `--config` option string。`test_every_parser_help_omits_removed_config` 参数化 17 个 command path 的 help 输出，断言不含 `--config`。
- **验证**: 运行 `build_parser()` 确认产出 17 个 parser（root + 12 command + 3 session action + tool_trace analyze），均无 `--config`。

### 2. 无 alias/wrapper/hidden path

- **入口**: `dayu/cli/agent_entrypoint.py`
- **直接证据**: `CONFIG_DIR_OPTION_NAME`、`resolve_explicit_config_dir(...)` 及 `__all__` 中的对应 export 已删除。`_reject_disallowed_explicit_config(...)` 及其在 `parse_cli_args` 中的调用已删除。`ParsedCliArgs.config_dir` 字段及 `_new_default_namespace` 中的默认值已删除。
- **rg 扫描**: `explicit_config_dir`、`config_overlay_dir`、`resolve_explicit_config_dir`、`CONFIG_DIR_OPTION_NAME`、`_build_runtime_arguments_parent`、`_reject_disallowed_explicit_config` 在 `dayu/cli` 和 `dayu/service` 的生产代码中零命中。`config_overlay_dir` 仅出现在 `dayu/runtime/location.py`（独立 runtime location contract）和 `dayu/service/host_assembly.py`（Service assembly 内部字段，非被删除的 request 字段）。

### 3. `--config` 在所有 parser scope 均被 argparse 拒绝

- **equal-sign 形式** (`--config=/tmp/x`): `test_removed_config_is_argparse_unknown_in_every_parser_scope` 覆盖 root、init、prompt、interactive、download、session list/command/action、session resume、session purge、tool_trace analyze 共 10 个位置，断言 `SystemExit(2)` + stderr 含 `"unrecognized arguments"` + `"--config"`。
- **split-value 形式** (`--config /tmp/x`): `test_removed_config_split_value_form_never_produces_namespace` 覆盖 root、prompt、interactive、session list/command/action 共 5 个位置，断言 `SystemExit(2)` + stderr 含 `"error:"`。
- **诊断差异符合预期**: split-value 在 root 位置时，argparse 将孤立的 `/tmp/x` 报为非法 command choice（`invalid choice: '/tmp/x'`）而非 `"unrecognized arguments"`。这是原生 argparse 行为，实现未添加预扫描兼容特例。两种形式都确保 exit 2、无有效 namespace、无 Service/Host 调用。

### 4. parse 失败在 Service/Host 副作用前

- **入口**: prompt、interactive、session 三个命令的 removed-option 测试
- **直接证据**:
  - `test_prompt_removed_config_fails_before_service_preparation`: monkeypatch `prepare_entrypoint_runtime` 为 "调用即失败" sentinel，执行 `--config=/tmp/x` 后断言 sentinel 未调用、`captured_requests == []`。
  - `test_interactive_removed_config_fails_before_service_preparation`: 同上模式。
  - `test_session_removed_config_fails_before_service_preparation`: monkeypatch `prepare_host_admin` 为 sentinel，断言 admin preparation 未执行。
- **验证**: 三个测试均通过，证明 argparse rejection 发生在任何 Service/Host 打开之前。

### 5. Service runtime/admin 使用 workspace config/package fallback

- **入口**: `dayu/service/host_admin.py` `prepare_host_admin`
- **直接证据**: 新增 `from dayu.runtime.location import resolve_runtime_locations`。`prepare_host_admin` 现在调用 `resolve_runtime_locations(workspace_root, package_config_root)` 获取 `locations`，再用 `locations.config_overlay_dir` 传给 `ConfigLoader.load_host_runtime`。与 `prepare_entrypoint_runtime` 使用相同的 runtime location owner。
- **测试覆盖**:
  - `test_service_host_admin_request_has_no_config_override_field`: 断言 `ServiceHostAdminRequest` dataclass fields 不含 `config_overlay_dir`。
  - `test_prepare_host_admin_uses_workspace_config_when_present`: 创建 package config 和 workspace config 两套配置，断言 workspace config 覆盖 package（runtime_id == "workspace-admin"）。
  - `test_entrypoint_runtime_request_has_no_explicit_config_field`: 断言 `EntrypointRuntimeRequest` dataclass fields 不含 `explicit_config_dir`。
  - `test_prepare_entrypoint_runtime_uses_package_fallback_without_workspace_config`: 无 workspace config 时断言 `config_overlay_dir is None`、prompt/manifest 使用 package 路径。
- **`RuntimeLocations.config_overlay_dir` 独立 owner**: `dayu.runtime.location.resolve_runtime_locations` 仍保留 `explicit_config_overlay_dir` 可选参数，但 S1 的调用方不再传入该参数。独立 runtime location 能力未被误删。

### 6. typed construction sites 完整

- **`EntrypointRuntimeRequest` 构造**: `dayu/cli/session_execution.py`、`tests/cli/test_prompt_command.py`、`tests/cli/test_interactive_command.py`、`tests/cli/test_transient_delivery_interruption_path.py`、`tests/service/test_entrypoint_runtime.py`、`tests/service/test_entrypoint_runtime_prompt_path.py`、`tests/service/test_entrypoint_runtime_interactive_path.py` 中所有构造 site 均已删除 `explicit_config_dir=None`。
- **`ServiceHostAdminRequest` 构造**: `dayu/cli/commands/session.py`、`tests/cli/test_session_command.py`、`tests/service/test_host_admin.py` 中所有构造 site 均已删除 `config_overlay_dir=...`。
- **tests 断言 owner 而非 fixture 偶然**: `test_entrypoint_runtime_request_has_no_explicit_config_field` 和 `test_service_host_admin_request_has_no_config_override_field` 使用 `dataclasses.fields()` 机械枚举 dataclass field names，断言旧字段不存在。这是 owner-level schema 断言，不依赖 fixture 偶然行为。

### 7. scope/分层/类型/docstring/coverage

- **scope**: 修改严格限于 plan §3.1 的 15 个文件，未触及 README、Host、Engine、`dayu.runtime` 或 frozen docs/registry。
- **分层**: CLI 不再提供配置覆盖入口；Service 通过 `dayu.runtime` location owner 解析 workspace/package config。`host_admin.py` 新增对 `dayu.runtime.location` 的 import 符合分层架构（Service 依赖 runtime 基础设施）。
- **类型**: pyright 对全部 15 个受影响文件报告 0 errors。
- **docstring**: 删除的函数/字段的 docstring 已一并清除；保留的函数 docstring 已更新（如 `_prepare_session_admin` 的 raises 说明从 "workspace 或 config 参数非法" 改为 "workspace 参数非法"）。
- **coverage**: implementation artifact 报告的单文件覆盖率均 >= 80%（arg_parsing 99%、agent_entrypoint 93%、session 85%、session_execution 86%、entrypoint_runtime 88%、host_admin 86%）。

### 8. 验证结果

- **focused pytest**: 692 passed, 3 warnings（edgar deprecation），与 implementation artifact 一致。
- **pyright**: 0 errors, 0 warnings, 0 informations。
- **registry SHA-256**: `f9972d...` 和 `7f283b...` 与 plan §0.1 一致。
- **staged set**: 为空。
- **git diff --check**: 通过。

## Open Questions

无。

## Residual Risk

- `session resume --config=/tmp/x`（equal-sign 形式）未出现在 `test_removed_config_is_argparse_unknown_in_every_parser_scope` 的参数化列表中，但行为已通过实际运行验证为 exit 2 + "unrecognized arguments"，且 `test_every_parser_scope_omits_removed_config_action` 已覆盖全部 17 个 parser scope 的 action inventory。风险极低。
- split-value 诊断在 root 位置报告 "invalid choice" 而非 "unrecognized arguments"，是原生 argparse 行为差异。实现正确选择不添加预扫描兼容特例。测试断言 `"error:" in captured.err` 而非精确匹配 "unrecognized arguments"，覆盖了两种诊断形式。
- 全仓 pytest、全仓 pyright、README 同步延迟到 S8。

## Verdict

**PASS**。S1/F01 实现完整、正确地删除了全局 `--config` 的 grammar、action、help、parsing、forwarding 与 request 字段。parse 失败发生在 Service/Host 副作用前。Service runtime/admin 通过 `dayu.runtime` location owner 正确使用 workspace config / package fallback。typed construction sites 完整更新，tests 断言 owner-level contract。scope、分层、类型、docstring、coverage 均符合计划。未发现实质性问题。
