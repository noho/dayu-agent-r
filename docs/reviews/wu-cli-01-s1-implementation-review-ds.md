# WU-CLI-01 / CLI-01-S1 Implementation Review (AgentDS)

## Scope

- Mode: current changes (workspace changes relative to `phase/host-ui-implementation`)
- Base: main
- Review target: CLI-01-S1 uncommitted workspace changes
- Output file: `docs/reviews/wu-cli-01-s1-implementation-review-ds.md`
- Accepted plan: `docs/host/wu-cli-01-cli-entrypoint-plan.md`，slice CLI-01-S1
- Implementation report: `docs/reviews/wu-cli-01-s1-implementation-codex.md`
- Included files:
  - `dayu/cli/__init__.py`
  - `dayu/cli/__main__.py`
  - `dayu/cli/main.py`
  - `dayu/cli/arg_parsing.py`
  - `dayu/cli/exit_codes.py`
  - `dayu/cli/commands/__init__.py`
  - `tests/cli/test_arg_parsing.py`
  - `tests/README.md` (partial diff)
  - `docs/host/ui-implementation-control.md` (partial diff)
- Excluded: pycache 目录、旧 CLI 对照源、plan 文档正文
- Parallel review coverage: 无（scope 集中，单 reviewer 逐行走读已覆盖）

## Findings

### 1-Low-`argparse._SubParsersAction` 私有类型暴露在多个函数签名中

- **入口/函数**: `_add_command_parser`、`_register_init_command`、`_register_prompt_command` 等全部 10 个命令注册函数
- **文件(行号)**: `dayu/cli/arg_parsing.py:194, 221, 243, 267, 370, 397, 423, 453, 480, 508, 532`
- **输入场景**: 类型检查器对上述函数签名求值
- **实际分支**: 参数 `subparsers` 的类型标注为 `argparse._SubParsersAction[argparse.ArgumentParser]`
- **预期行为**: 使用公共 API 类型或 Protocol 描述 subparsers 注册器
- **实际行为**: 使用 typeshed 为 `add_subparsers()` 定义的返回类型 `_SubParsersAction`，该类型名下划线前缀表明它是 argparse 内部实现细节
- **直接证据**: 所有命令注册函数签名中 `subparsers` 参数的类型标注均为 `argparse._SubParsersAction[argparse.ArgumentParser]`；typeshed 虽然将此类型作为 `add_subparsers()` 的返回类型暴露，但它不是 argparse 文档化公共 API
- **影响**: 若 CPython 或 typeshed 在未来版本中重命名或重构此内部类型，所有签名需同步更新；当前行为无运行时影响
- **建议改法和验证点**: 可考虑提取 `SubparserRegistry = argparse._SubParsersAction[argparse.ArgumentParser]` 模块级类型别名到一处，减少未来修改面；或在模块级用 `assert argparse._SubParsersAction is not None` 做编译期锚定。不改也不影响 S1 正确性
- **修复风险（低）**: 纯类型标注调整，不影响运行时行为
- **严重程度（低）**: 无运行时影响，typeshed 当前稳定暴露该类型；仅作为未来兼容性风险记录

### 2-Low-`COMMAND_RUNNERS` 缺失 runner 时静默返回 `EXIT_FAILURE`

- **入口/函数**: `main`
- **文件(行号)**: `dayu/cli/main.py:37-38`
- **输入场景**: 某个已通过 argparse 子命令校验的命令在 `COMMAND_RUNNERS` 中查不到对应 runner
- **实际分支**: `runner is None` → `return EXIT_FAILURE`（退出码 1）
- **预期行为**: 返回失败退出码；可附加 stderr 诊断信息便于排查内部不一致
- **实际行为**: 静默返回 1，无 stderr 输出说明是 dispatch 缺失而非命令执行失败
- **直接证据**: 第 37 行 `if runner is None:` → 第 38 行 `return EXIT_FAILURE`，中间无任何 `print(..., file=sys.stderr)` 或日志输出
- **影响**: 当前无法触发（所有 `CLI_COMMAND_NAMES` 均在 `COMMAND_RUNNERS` 中有对应条目）；仅当未来 slice 新增命令但忘记更新 `COMMAND_RUNNERS` 时暴露。届时表现与 `EXIT_NOT_IMPLEMENTED` 相同（退出码都是 1），但缺少 "尚未实现" 诊断文本，增加排查成本
- **建议改法和验证点**: 在 `return EXIT_FAILURE` 前加 `print(f"dayu-cli: 内部错误：命令 '{args.command_name}' 缺少注册 runner", file=sys.stderr)`。增加测试用 monkeypatch 将 `COMMAND_RUNNERS` 清空后验证 stderr 包含诊断信息
- **修复风险（低）**: 仅增加诊断输出
- **严重程度（低）**: 当前无法触发，仅作为未来 slice 的防御性改进

## 逐项审查结论

### 1. S1 scope 边界

**结论: 通过。**

- `dayu/cli/` 只包含 package skeleton、parser factory、help contract、exit code mapping、placeholder command runner
- `dayu/cli/main.py:21-23` — `COMMAND_RUNNERS` 将所有命令映射到 `run_not_implemented_command`
- `dayu/cli/commands/__init__.py:15-27` — `run_not_implemented_command` 只输出 "尚未实现" 并返回退出码
- 无 `import dayu.engine`、`import dayu.host`、`import dayu.service`、`import dayu.fins`
- 无任何 Host/Fins 业务执行代码或 S2-S7 语义

### 2. 旧 CLI 业务语义迁移 vs 代码复制

**结论: 通过。**

- 迁移的是用户可见命令面（command names、参数名、help 文本），不是旧实现代码
- `EXCLUDED_COMMAND_NAMES`（`arg_parsing.py:47-54`）明确记录有意不迁移的命令
- 命令参数面与旧 CLI 一致（如 `prompt` 的 `--ticker`、`--label`、`--model-name` 等），均由 parser 以当前仓库风格重新定义
- 零 import 旧 `dayu-agent` 仓库路径

### 3. 命令注册范围

**结论: 通过。**

已注册（`CLI_COMMAND_NAMES`, `arg_parsing.py:35-46`）：
`init`, `prompt`, `interactive`, `download`, `upload_filing`, `upload_material`, `upload_filings_from`, `process`, `process_filing`, `process_material` — 共 10 个

未注册（`EXCLUDED_COMMAND_NAMES`, `arg_parsing.py:47-54`）：
`write`, `host`, `sessions`, `runs`, `cancel`, `conv` — 共 6 个

验证数据点：
- `test_top_level_help_registers_scoped_commands`（`test_arg_parsing.py:107-122`）— 验证包含/排除
- `test_excluded_commands_exit_with_usage_error`（`test_arg_parsing.py:171-180`）— 6 个排除命令均返回退出码 2
- `dayu-cli --help` 实际输出确认只展示 10 个命令

### 4. `interactive --help` 包含 optional `--ticker`

**结论: 通过。**

- `arg_parsing.py:284` — `parser.add_argument("--ticker", help="可选公司代码或财报主体。")` 无 `required=True`
- `test_interactive_help_contains_optional_ticker`（`test_arg_parsing.py:146-158`）— 独立验证
- 实际 `python -m dayu.cli interactive --help` 输出确认 `--ticker TICKER` 出现在 options 区域且未标注 required

### 5. `main(argv)` parse/dispatch/exit mapping

**结论: 通过。**

出口映射逐路径追踪（`main.py:26-43`）：
| 触发条件 | 机制 | 退出码 | 验证 |
|---|---|---|---|
| `--help` | argparse → `SystemExit(0)` → `_normalize_system_exit_code` | `0` | `test_module_run_function_uses_cli_main` |
| usage error / unknown command | argparse → `SystemExit(2)` → `_normalize_system_exit_code` | `2` | `test_missing_command_exits_with_usage_error`、`test_excluded_commands_exit_with_usage_error` |
| `KeyboardInterrupt` | `except KeyboardInterrupt` → `EXIT_KEYBOARD_INTERRUPT` | `130` | `test_main_maps_keyboard_interrupt` |
| placeholder runner | `run_not_implemented_command` → `EXIT_NOT_IMPLEMENTED` | `1` | `test_placeholder_runner_returns_not_implemented` |
| `SystemExit(None)` | `_normalize_system_exit_code` | `0` | 覆盖率 missing line 56（防御路径） |
| `SystemExit(string)` | `_normalize_system_exit_code` | `1` | 覆盖率 missing line 59（防御路径） |

`_normalize_system_exit_code`（`main.py:46-59`）正确处理三个分支：`code is None` → 0，`isinstance(code, int)` → code 直传，其他 → 1。

`SystemExit` 捕获在 `KeyboardInterrupt` 之后（`main.py:42`），不会意外吞掉中断信号。

### 6. AGENTS.md 合规

**结论: 通过。**

| 约束 | 状态 | 证据 |
|---|---|---|
| 中文 docstring | ✅ | 所有 7 个模块、全部 18 个函数/方法均有中文 docstring（含参数/返回值/异常） |
| 严格类型签名 | ✅ | 无 `Any`、无 `object`、无无类型参数/返回值；grep 确认零命中 |
| 禁止 `hasattr`/`getattr` | ✅ | grep 确认零命中 |
| 无兼容 wrapper/re-export | ✅ | 无转发函数、无别名导出 |
| 无反向依赖 | ✅ | `dayu/cli/` 只 import stdlib 与自身；grep `dayu\.\(engine\|host\|service\|fins\|ui\)` 零命中 |
| 私有类型使用 | ⚠️ | `argparse._SubParsersAction` 为 typeshed 暴露的内部类型（见 Finding 1） |

### 7. Tests 覆盖与 README 更新

**结论: 通过。**

Tests（`tests/cli/test_arg_parsing.py`，24 个用例全部通过）：
- `test_top_level_help_registers_scoped_commands` — S1 success signal：help 包含/排除正确命令
- `test_command_help_contains_core_arguments`（10 个 parametrized）— 每个命令 help 包含核心参数
- `test_interactive_help_contains_optional_ticker` — 独立验证 review 重点项
- `test_missing_command_exits_with_usage_error` — 缺少子命令 → 退出码 2
- `test_excluded_commands_exit_with_usage_error`（6 个 parametrized）— 排除命令 → 退出码 2
- `test_placeholder_runner_returns_not_implemented` — placeholder 退出 + stderr 诊断
- `test_main_maps_keyboard_interrupt` — `KeyboardInterrupt` → 130
- `test_python_module_help_runs` — 子进程验证 `python -m dayu.cli --help`
- `test_module_run_function_uses_cli_main` — 同进程验证模块入口
- `test_parse_args_accepts_global_options_before_and_after_command` — 全局参数位置无关性

覆盖率：98%（`arg_parsing.py` 100%、`main.py` 88%、`__main__.py` 83%），missing lines 均为防御代码路径。

README 更新（`tests/README.md` diff）：
- 在 "常用命令" 中加入 `tests/cli`
- 在 "各层独立运行" 中加入 `pytest tests/cli -q`
- 新增 `### tests/cli/` 段落说明测试层定位和边界
- 符合 AGENTS.md 触发规则：`tests/` 修改 → 更新 `tests/README.md`

### 8. Console script 与模块入口

**结论: 通过。**

- `pyproject.toml:98` — `dayu-cli = "dayu.cli.main:main"` ✅
- `python -c "import dayu.cli.main"` — 成功 ✅
- `python -m dayu.cli --help` — 正常输出 help，退出码 0 ✅
- `dayu/cli/__main__.py` — `run_module()` 调用 `main()`，`if __name__ == "__main__": raise SystemExit(run_module())` ✅

## Open Questions

无。

## Residual Risk

1. **`BrokenPipeError` 未处理**：当 CLI 输出通过管道传输（如 `dayu-cli --help | head`）且接收端提前关闭时，Python 默认会抛出 `BrokenPipeError` 并打印 traceback。这是 Python CLI 通用问题，非 S1 特有；建议在后续 slice 中按需在 `main()` 添加 `except BrokenPipeError` 处理（参考 Python 3.8+ `PYTHONUNBUFFERED` 行为）。

2. **S2-S7 切片依赖 S1 parser contract**：当前 `ParsedCliArgs` 字段固定为 `command_name`、`workspace_root`、`config_dir`、`log_level`。后续 slice 在 runner 中消费 args 时需注意 argparse 运行时动态属性与类型标注的一致性 — `ParsedCliArgs` 继承 `argparse.Namespace`，运行时属性集由各命令 parser 的 `add_argument` 决定，不受类注解约束。建议 S2 在 runner 入口做显式字段校验。

3. **Coverage missing lines**：`main.py:38`（runner 缺失静默返回）、`:56`（`SystemExit.code is None`）、`:59`（`SystemExit.code` 非 int 非 None）为防御路径未覆盖。当前均不影响正常路径行为，可在后续 slice 的集成测试中补覆盖。

## Conclusion

**Pass.** CLI-01-S1 实现严格限定在 S1 scope 内：CLI package skeleton、parser factory、help contract 和 exit code mapping。10 个 plan 要求命令全部注册，6 个排除命令均未注册。`interactive --help` 正确包含 optional `--ticker`。`main(argv)` 仅做 parse/dispatch/exit mapping，退出码 mapping（help=0、usage/unknown=2、KeyboardInterrupt=130）逐路径验证通过。AGENTS.md 合规：中文 docstring、严格类型、无 Any/object/hasattr/getattr、无兼容 wrapper、无反向依赖。24 个测试全部通过，覆盖率 98%，pyright 零报错。`pyproject.toml` console script 可正常 import，`python -m dayu.cli` 可正常运行。两个 low-severity findings 均不影响 S1 正确性，可在后续 slice 中按需处理。
