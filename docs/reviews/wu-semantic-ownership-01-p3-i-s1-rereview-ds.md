# S1 Re-Review (AgentDS)

## Scope

- Gate: S1 re-review
- Work unit: WU-SEMANTIC-OWNERSHIP-01 P3-I
- Original review: `docs/reviews/wu-semantic-ownership-01-p3-i-s1-code-review-ds.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-i-s1-code-review-controller-adjudication.md`
- Fix report: `docs/reviews/wu-semantic-ownership-01-p3-i-s1-fix-codex.md`
- Re-review target: DS F1 only
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-i-s1-rereview-ds.md`

## Verification Summary

```
pytest tests/cli/test_public_package_entrypoints.py -q → 12 passed
pyright dayu/runtime/argparse_exit.py dayu/runtime/__init__.py dayu/web/ dayu/wechat/ dayu/render/ tests/cli/ → 0 errors, 0 warnings, 0 informations
python -m dayu.web --help → exit 0
python -m dayu.wechat.main --help → exit 0
python -m dayu.render.render --help → exit 0
python -m dayu.web (no args) → exit 1, correct diagnostic to stderr
python -m dayu.wechat.main (no args) → exit 1, correct diagnostic to stderr
python -m dayu.render.render input.md output.pdf → exit 1, correct diagnostic to stderr
git diff --check → clean
```

## DS F1 Fix Verification

### 1. 共享 helper 已抽取到层中立位置

`dayu/runtime/argparse_exit.py` 提供 `normalize_argparse_system_exit_code(exc: SystemExit) -> int`：

- **层中立**: 只依赖 `__future__.annotations` 和 `typing.Final`，无任何 `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins` 依赖。✅
- **完整类型**: 参数 `exc: SystemExit`，返回值 `-> int`，常量 `Final[int]`。✅
- **标准库 only**: 无第三方依赖。✅
- **中文 docstring**: 模块、函数均有中文 docstring，参数/返回值/异常说明完整。✅

### 2. 三个入口模块不再重复定义

| 文件 | 旧状态 | 新状态 |
| --- | --- | --- |
| `dayu/web/__main__.py` | 本地 `_normalize_system_exit_code` + `EXIT_USAGE_ERROR` 常量 | 删除本地定义，改为 `from dayu.runtime.argparse_exit import normalize_argparse_system_exit_code` |
| `dayu/wechat/main.py` | 同上 | 同上 |
| `dayu/render/render.py` | 同上 | 同上 |

通过 `rg "_normalize_system_exit_code\|normalize_argparse_system_exit_code" dayu/` 确认：三个入口模块不再包含本地 `_normalize_system_exit_code` 定义。✅

### 3. 行为不变

原始三份 `_normalize_system_exit_code` 的逻辑：

```python
if isinstance(exc.code, int):
    return exc.code
return EXIT_USAGE_ERROR  # 2
```

新共享 helper 逻辑（`dayu/runtime/argparse_exit.py:17-20`）：

```python
if isinstance(exc.code, int):
    return exc.code
return ARGPARSE_USAGE_ERROR_EXIT_CODE  # 2
```

语义完全一致。三个入口的 help 路径（`SystemExit(0)` → 返回 `0`）和 argparse 参数错误路径（`SystemExit(2)` → 返回 `2`）行为不变。✅

### 4. `dayu/runtime/__init__.py` 已登记

包 docstring 中已加入"层中立 argparse 退出码规范化"描述，符合 runtime 包不 re-export 的策略。✅

### 5. `dayu/cli/main.py` 不是未关闭的重复

`dayu/cli/main.py:180-193` 保留了独立的 `_normalize_system_exit_code`，但语义与 runtime helper **本质不同**：

| 维度 | runtime `normalize_argparse_system_exit_code` | CLI `_normalize_system_exit_code` |
| --- | --- | --- |
| `code is None` | 不处理（落入 `else` → 返回 `2`） | 返回 `EXIT_SUCCESS` (0) |
| `isinstance(code, int)` | 原样返回 `code` | 原样返回 `code` |
| 其他类型 | 返回 `ARGPARSE_USAGE_ERROR_EXIT_CODE` (2) | 返回 `EXIT_FAILURE` (1) |

差异根因：
- Runtime helper 专为 argparse 设计——argparse 的 `SystemExit.code` 要么是 `int`（包括 `0`），不会出现 `None`。
- CLI helper 处理任意来源的 `SystemExit`（包括 `sys.exit()` 无参数时 `code=None`），因此需要 `None → 0` 映射，且非整数 code 按通用失败处理（1）而非 argparse usage error（2）。

CLI 的 `_normalize_system_exit_code` 有独立语义，不是 DS F1 范围内的未关闭重复。✅

### 6. 现有测试保持有效

`tests/cli/test_public_package_entrypoints.py` 12 个测试全部通过。测试覆盖：
- `test_pyproject_public_script_targets_import_and_help`：每个入口 `("--help",)` → `EXIT_SUCCESS`，经过 runtime helper 的 `isinstance(int)` 分支。
- `test_public_modules_execute_help`：subprocess 执行 `python -m <module> --help`，验证 stdout 含命令名、stderr 为空、退出码 0。
- `test_public_entrypoint_import_does_not_load_optional_heavy_dependencies`：确认入口 import 不加载可选重依赖。
- `test_non_help_execution_returns_controlled_diagnostics`：无参数/带参数非 help 路径返回 `EXIT_UNAVAILABLE`（不经过 runtime helper）。
- `test_wechat_subcommand_help_is_controlled`：子命令 help 返回 `EXIT_SUCCESS`，经过 runtime helper。

测试未修改，断言未削弱，公开行为未变化。✅

### 7. Propagation audit 复核

按 controller 要求的 propagation path 逐项复核：

| 路径 | 产生者 | 校验/规范化 owner | 投影 | 一致性 |
| --- | --- | --- | --- | --- |
| `dayu.web.__main__` | argparse `SystemExit` | `dayu.runtime.argparse_exit` | `main() -> int` → `raise SystemExit(main())` | ✅ |
| `dayu.wechat.main` | argparse `SystemExit` | 同上 | 同上 | ✅ |
| `dayu.render.render` | argparse `SystemExit` | 同上 | 同上 | ✅ |

三个入口的 LLM/user-visible help 与诊断语义未变化；无 durable state、trace、memory 或 audit 输出需要同步迁移。✅

## Findings

未发现实质性问题。DS F1 已正确关闭。

## Open Questions

无。

## Residual Risk

- `dayu/cli/main.py` 的 `_normalize_system_exit_code` 仍在本地定义，未使用 runtime helper。当前 CLI 语义与 argparse 专用 helper 不同（`None → 0`、非 int → 1），因此不算重复。但如果后续 CLI 也需要 argparse 专用规范化（例如 CLI 子命令也使用 argparse），应考虑分层组合而非复制逻辑。当前风险低，不属于本次 S1 范围。
- 本次未检查 S2 terminal cursor 文件及更大范围的 `dayu/` 目录，按 re-review scope 限定在 DS F1 及相关文件。
