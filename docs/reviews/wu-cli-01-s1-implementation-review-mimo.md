# Code Review

## Scope

- Mode: current changes
- Branch: `phase/host-ui-implementation`
- Base: `main`
- Output file: `docs/reviews/wu-cli-01-s1-implementation-review-mimo.md`
- Included scope:
  - `dayu/cli/__init__.py`
  - `dayu/cli/__main__.py`
  - `dayu/cli/arg_parsing.py`
  - `dayu/cli/main.py`
  - `dayu/cli/exit_codes.py`
  - `dayu/cli/commands/__init__.py`
  - `tests/cli/test_arg_parsing.py`
  - `tests/README.md`
  - `docs/host/ui-implementation-control.md`
  - `docs/reviews/wu-cli-01-s1-implementation-codex.md`
- Excluded scope: none
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## 审查结论

### 1. S1 范围边界

**PASS** — 严格限于 CLI package skeleton、parser、help、exit contract。

- `dayu/cli/commands/__init__.py:15-27`：`run_not_implemented_command` 只输出 stderr 提示并返回 `EXIT_NOT_IMPLEMENTED`，不启动 Host/Fins 业务执行。
- `dayu/cli/main.py:21-23`：`COMMAND_RUNNERS` 将所有 `CLI_COMMAND_NAMES` 映射到同一个 placeholder runner。
- 未实现 S2-S7 中任何业务逻辑。

### 2. 命令注册范围

**PASS** — 只注册计划要求的 10 个命令。

- `dayu/cli/arg_parsing.py:24-46`：`CLI_COMMAND_NAMES` 包含 `init`、`prompt`、`interactive`、`download`、`upload_filing`、`upload_material`、`upload_filings_from`、`process`、`process_filing`、`process_material`。
- `dayu/cli/arg_parsing.py:47-54`：`EXCLUDED_COMMAND_NAMES` 包含 `write`、`host`、`sessions`、`runs`、`cancel`、`conv`。
- 测试 `test_top_level_help_registers_scoped_commands` 验证只显示 `CLI_COMMAND_NAMES`，不显示 `EXCLUDED_COMMAND_NAMES`。

### 3. interactive --help 包含 optional --ticker

**PASS** — `dayu/cli/arg_parsing.py:284` 明确定义 `--ticker` 为 optional（无 `required=True`）。
- 测试 `test_interactive_help_contains_optional_ticker` 验证 help 输出包含 `--ticker`。

### 4. main(argv) 只做 parse/dispatch/exit mapping

**PASS** — `dayu/cli/main.py:26-43`：

- `parse_cli_args(argv)` 解析参数。
- `COMMAND_RUNNERS.get(args.command_name)` 查找 runner。
- `runner(args)` 分发执行。
- 异常处理：
  - `KeyboardInterrupt` -> `EXIT_KEYBOARD_INTERRUPT` (130)。
  - `SystemExit` -> `_normalize_system_exit_code(exc)`。
    - `code=None` -> `EXIT_SUCCESS` (0)（argparse help 场景）。
    - `code` 为 int -> 直接返回（argparse usage error 返回 2）。
    - 其它 -> `EXIT_FAILURE` (1)。

### 5. 退出码契约

**PASS** — 退出码映射正确。

- `dayu/cli/exit_codes.py:8-12`：
  - `EXIT_SUCCESS = 0`
  - `EXIT_FAILURE = 1`
  - `EXIT_USAGE_ERROR = 2`
  - `EXIT_KEYBOARD_INTERRUPT = 130`
  - `EXIT_NOT_IMPLEMENTED = EXIT_FAILURE = 1`
- argparse help -> SystemExit(0) -> `_normalize_system_exit_code` 返回 0。
- argparse usage error -> SystemExit(2) -> `_normalize_system_exit_code` 返回 2。
- KeyboardInterrupt -> 130。
- 验证通过：`main(['--help'])` -> 0，`main([])` -> 2，`main(['write'])` -> 2。

### 6. AGENTS.md 编码约束

**PASS** — 符合中文 docstring、严格类型签名要求。

- 所有模块、类、函数均有中文 docstring，包含参数、返回值、异常说明。
- 类型签名严格：`ParsedCliArgs` 明确声明字段类型；`build_parser`、`parse_cli_args`、`_add_command_parser` 等函数均有完整类型标注。
- 未使用 `Any`、`object`、`hasattr`、`getattr` 逃逸。
- 无兼容 wrapper，无反向依赖。

### 7. tests 覆盖 S1 success signal

**PASS** — 测试覆盖完整。

- `tests/cli/test_arg_parsing.py` 包含 12 个测试：
  - 顶层 help 命令注册验证。
  - 每个 scoped command 的 help 参数验证。
  - interactive optional --ticker 验证。
  - 缺少命令退出码 2 验证。
  - 排除命令退出码 2 验证。
  - placeholder runner not-implemented 验证。
  - KeyboardInterrupt -> 130 验证。
  - `python -m dayu.cli --help` 入口验证。
  - 模块入口函数复用验证。
  - 全局参数位置验证。
- 测试结果：24 passed。
- 覆盖率：98%（`arg_parsing.py` 100%，`main.py` 88%，`__main__.py` 83%）。

### 8. pyproject console script

**PASS** — `pyproject.toml` 声明 `dayu-cli = "dayu.cli.main:main"`，import 验证通过。

- `python -c "from dayu.cli.main import main; print('import OK')"` 成功。
- `python -m dayu.cli --help` 成功输出 help 文本。

### 9. README 更新

**PASS** — `tests/README.md` 更新符合触发规则。

- 新增 `tests/cli/` 测试层，README 新增 CLI 测试分层说明。
- 新增 `pytest tests/cli -q` 到常用命令列表。
- `dayu/README.md`、`dayu/host/README.md` 等未触发更新，符合触发规则。

### 10. pyright 类型检查

**PASS** — `dayu/cli/` 和 `tests/cli/` 范围内 0 errors。

## Open Questions

无。

## Residual Risk

- `main.py` 覆盖率 88%，`__main__.py` 覆盖率 83%。未覆盖路径为 `OSError` 异常分支和 `SystemExit` 非 int code 分支，属于防御性代码，风险低。
- `dayu-cli` console script 的 installed package wrapper 测试未执行，需在 packaging 或 smoke validation 阶段验证。
