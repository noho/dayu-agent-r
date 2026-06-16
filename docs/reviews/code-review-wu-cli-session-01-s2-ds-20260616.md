# Code Review — WU-CLI-SESSION-01 S2

## Scope

- Mode: current changes
- Branch: wu-cli-session-01
- Base: 653c9966 (accepted plan commit)
- Output file: docs/reviews/code-review-wu-cli-session-01-s2-ds-20260616.md
- Included scope:
  - `dayu/cli/arg_parsing.py` — `ParsedCliArgs`、`_new_default_namespace()`、`_register_interactive_command()`
  - `dayu/cli/commands/interactive.py` — `_ensure_interactive_session()`
  - `dayu/cli/host_context.py` — `interactive_process_slot_key` 删除与 `__all__` 清理
  - `tests/cli/test_arg_parsing.py` — help expectation 更新、`--new-session` 用法错误测试
  - `tests/cli/test_interactive_command.py` — 旧测试删除、默认 anonymous 断言加强
  - `tests/README.md` — interactive 测试覆盖描述同步
  - `docs/reviews/wu-cli-session-01-s2-implementation-codex.md` — implementation report
- Excluded scope:
  - `docs/host/issues-implementation-control.md`（controller bookkeeping）
  - S1/S3/S4/S5/S6 slice 文件（不在 S2 scope）
  - MiMo review artifacts（不属于 DS reviewer scope）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### 逐项确认

**1. `--new-session` 彻底删除，无兼容 flag**

- `ParsedCliArgs` 中 `new_session: bool` 字段已删除（`dayu/cli/arg_parsing.py:98` 原位置，已移除）
- `_new_default_namespace()` 中 `namespace.new_session = False` 赋值已删除（`dayu/cli/arg_parsing.py:204` 原位置，已移除）
- `_register_interactive_command()` 中 `add_mutually_exclusive_group()` + `--new-session` 注册已删除，改为直接 `parser.add_argument("--label", ...)`（`dayu/cli/arg_parsing.py:405-406`）
- `_ensure_interactive_session()` 中 `if args.new_session:` 分支已删除（`dayu/cli/commands/interactive.py:278-292` 原位置，已移除）
- `grep -rn 'new_session' dayu/ --include='*.py'` 无任何匹配

**2. 默认 fresh anonymous Session 行为保持**

- `_ensure_interactive_session()` 无 `--label` 时仍走 `create_new=True, bind_slot=False, scope=None, slot_key=None`（`dayu/cli/commands/interactive.py:278-293`）
- 测试 `test_interactive_two_turns_use_same_session_and_independent_watchers` 新增断言 `bind_slot is False`、`scope is None`、`slot_key is None`（`tests/cli/test_interactive_command.py:699-702`）

**3. `--label` ensure-by-label 行为保持**

- `_ensure_interactive_session()` 有 `--label` 时仍走 `create_new=False, bind_slot=True, scope=INTERACTIVE_SESSION_SCOPE, slot_key=slot_key`（`dayu/cli/commands/interactive.py:264-277`）
- 空 label 校验、`interactive_slot_key` 映射、`CliInteractiveUsageError` 错误包装均未修改

**4. `interactive_process_slot_key` 删除无 dangling reference**

- 函数定义已从 `dayu/cli/host_context.py` 删除（原行 107-118）
- 已从 `host_context.__all__` 移除（`dayu/cli/host_context.py:361` 原条目已移除）
- 已从 `dayu/cli/commands/interactive.py` import 列表移除（`dayu/cli/commands/interactive.py:42` 原条目已移除）
- `grep -rn 'interactive_process_slot_key' --include='*.py'` 全仓零匹配

**5. 未越界实现 S3/S4/S5**

- diff 范围严格限于 S2 plan 允许的文件列表
- 未引入 `dayu/cli/commands/session.py`、`session list/resume/purge` 或任何新命令注册

**6. 测试覆盖完成信号**

- `test_interactive_help_omits_removed_new_session_flag`（`tests/cli/test_arg_parsing.py:188-200`）：验证 help 不含 `--new-session`
- `test_interactive_new_session_flag_exits_with_usage_error`（`tests/cli/test_arg_parsing.py:203-213`）：验证 `parse_cli_args(("interactive", "--new-session"))` 抛出 `SystemExit(2)`
- `COMMAND_HELP_EXPECTATIONS["interactive"]` 不再包含 `"--new-session"`（`tests/cli/test_arg_parsing.py:43-48`）
- 旧 `test_interactive_new_session_creates_bound_process_session` 已删除

**7. README 更新**

- `tests/README.md` interactive 测试覆盖描述已从 "label / new-session session binding" 更新为 "默认 fresh anonymous Session、label session binding、`--new-session` 用法错误"（`tests/README.md:95-96`），与 S2 后测试事实一致

**8. pyright / docstring / AGENTS**

- pyright：0 errors（implementation report 记录）
- 新增测试均有中文 docstring
- 本次为纯删除 + 测试补强，无新增类型签名、无 `Any`/`object`、无反向依赖、无兼容 wrapper

## Open Questions

无。

## Residual Risk

- 仅运行了 S2 指定 CLI 测试（`tests/cli/test_arg_parsing.py` + `tests/cli/test_interactive_command.py`），未运行全量 pytest。旧用户脚本若硬编码 `interactive --new-session` 将收到 argparse usage error（exit 2），这是 plan 明确接受的破坏性变更。
