# Code Review: WU-CLI-SESSION-01 S2

## Scope

- Mode: current changes
- Branch: `wu-cli-session-01`
- Base: `653c9966` (accepted plan commit)
- Output file: `docs/reviews/code-review-wu-cli-session-01-s2-mimo-20260616.md`
- Included scope:
  - `dayu/cli/arg_parsing.py`
  - `dayu/cli/commands/interactive.py`
  - `dayu/cli/host_context.py`
  - `tests/cli/test_arg_parsing.py`
  - `tests/cli/test_interactive_command.py`
  - `tests/README.md`
  - `docs/reviews/wu-cli-session-01-s2-implementation-codex.md`
- Excluded scope: `docs/host/issues-implementation-control.md`（controller bookkeeping，仅检查是否与事实矛盾）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Review Detail

### 1. `--new-session` 是否从 parser/help/command path 彻底删除

- `ParsedCliArgs` dataclass 已删除 `new_session` 字段（`arg_parsing.py:100` 后无该字段）。
- `_new_default_namespace()` 已删除 `namespace.new_session = False`（diff 确认删除）。
- `_register_interactive_command()` 不再创建 mutually exclusive group，直接注册 `--label`（`arg_parsing.py:406`）。
- `_ensure_interactive_session()` 中 `args.new_session` 分支已完整删除（`interactive.py:275` 后无该分支）。
- 测试覆盖：`test_interactive_help_omits_removed_new_session_flag` 验证 help 不含 `--new-session`；`test_interactive_new_session_flag_exits_with_usage_error` 验证 parser 对 `--new-session` 返回 `EXIT_USAGE_ERROR`。
- **结论**：彻底删除，无兼容 flag。

### 2. 默认 interactive fresh anonymous Session 行为是否保持

- `_ensure_interactive_session()` 无 `--label` 时走 `create_new=True, bind_slot=False, scope=None, slot_key=None`（`interactive.py:278-293`），与 S2 前行为一致。
- `test_interactive_two_turns_use_same_session_and_independent_watchers` 已强化断言：`bind_slot is False`、`scope is None`、`slot_key is None`（`test_interactive_command.py:699-702`）。
- **结论**：行为保持。

### 3. `--label` ensure-by-label 行为是否保持

- `_ensure_interactive_session()` 有 `--label` 时走 `interactive_slot_key(args.label)` + `ensure_or_create_entrypoint_session(create_new=False, bind_slot=True, scope=INTERACTIVE_SESSION_SCOPE, ...)`（`interactive.py:264-277`），与 S2 前一致。
- `test_interactive_label_reuses_host_slot_and_fills_context_slots` 仍然存在且覆盖该路径。
- **结论**：行为保持。

### 4. `interactive_process_slot_key` 删除是否无 dangling reference

- `host_context.py` 已删除函数定义。
- `host_context.__all__` 已删除 `"interactive_process_slot_key"`。
- `interactive.py` import 已删除 `interactive_process_slot_key`。
- 全仓 grep `interactive_process_slot_key` 返回零结果（生产代码和测试均无残留）。
- **结论**：无 dangling reference。

### 5. 是否越界实现 session list/resume/purge

- diff 仅涉及删除 `--new-session` 相关代码和强化现有测试断言。
- 未新增 `list_sessions`、`resume`、`purge` 相关逻辑。
- control doc 记录 S2 范围为 "removed obsolete `interactive --new-session` only"，与实现一致。
- **结论**：未越界。

### 6. tests/README 更新是否符合边界

- README 更新仅修改 `interactive` 命令测试覆盖描述，从 "label / new-session session binding" 改为 "默认 fresh anonymous Session、label session binding、`--new-session` 用法错误"。
- 描述与实际测试事实一致：默认 anonymous 测试存在、label 测试存在、`--new-session` usage error 测试存在。
- 未触及 Host/engine/fins/config README，符合触发规则。
- **结论**：符合边界。

## Open Questions

无。

## Residual Risk

- 旧用户传入 `--new-session` 现在返回 usage error，这是预期的不兼容变更，无兼容 flag。implementation report 已记录。
- 仅运行 S2 指定 CLI 测试（54 passed）与全项目 pyright（0 errors），未运行全量 pytest。这是 S2 slice 的合理验证范围。
