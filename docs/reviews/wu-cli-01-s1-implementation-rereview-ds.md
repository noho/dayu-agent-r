# WU-CLI-01 / CLI-01-S1 Implementation Re-Review (AgentDS)

## Scope

- Mode: current changes (re-review of fix gate)
- Branch: `phase/host-ui-implementation`
- Base: `main`
- Output file: `docs/reviews/wu-cli-01-s1-implementation-rereview-ds.md`
- Review target: 当前未提交 workspace changes（fix 后状态）
- Controller adjudication: `docs/reviews/wu-cli-01-s1-implementation-review-controller-adjudication.md`
- Fix report: `docs/reviews/wu-cli-01-s1-implementation-fix-codex.md`
- Original reviews: `docs/reviews/wu-cli-01-s1-implementation-review-mimo.md`, `docs/reviews/wu-cli-01-s1-implementation-review-ds.md`
- Included files:
  - `dayu/cli/arg_parsing.py`
  - `dayu/cli/main.py`
  - `tests/cli/test_arg_parsing.py`
  - (unchanged from S1: `dayu/cli/__init__.py`, `dayu/cli/__main__.py`, `dayu/cli/commands/__init__.py`, `dayu/cli/exit_codes.py`)
- Excluded: review artifacts、plan/control docs
- Parallel review coverage: 无

## Re-Review Objective

只验证两项 accepted findings 是否关闭，检查 fix 是否引入新问题，并确认 S1 scope 未扩大。

---

## Accepted Findings 逐项验证

### S1-IMPL-F01：argparse 私有类型暴露 → **已关闭**

**原始 finding**：11 个命令注册函数签名直接使用 `argparse._SubParsersAction[argparse.ArgumentParser]` 私有类型名。

**修复方案**：新增 `CommandSubparserRegistry` Protocol（`arg_parsing.py:59-84`），只描述 `add_parser(name, *, help, description, parents) -> ArgumentParser` 能力。所有命令注册函数的 `subparsers` 参数改为 `CommandSubparserRegistry`，`build_parser` 在 `parser.add_subparsers(...)` 返回点用 `cast(CommandSubparserRegistry, ...)` 收敛。

**验证结果**：

| 检查项 | 状态 | 证据 |
|---|---|---|
| `_SubParsersAction` 零残留 | ✅ | `rg -n '_SubParsersAction' dayu/cli/ tests/cli/` 零命中 |
| 所有命令注册函数参数为 Protocol | ✅ | 共 12 处函数签名使用 `CommandSubparserRegistry`（含 `_add_command_parser` 和 11 个 `_register_*` 函数） |
| 未用 `Any`/`object` 逃逸类型 | ✅ | `rg -n '\bAny\b\|: object\b' dayu/cli/` 零命中 |
| `cast` 使用收敛在单点 | ✅ | 仅在 `build_parser:113` 一处使用 `cast(CommandSubparserRegistry, ...)` |
| Protocol 语义自足 | ✅ | Protocol 只描述本模块需要的 `add_parser` 能力，无多余方法；中文 docstring 说明意图 |
| pyright 通过 | ✅ | 0 errors, 0 warnings, 0 informations |

**结论**：S1-IMPL-F01 已关闭。`CommandSubparserRegistry` Protocol 正确隔离了 `argparse._SubParsersAction` 私有类型，所有函数签名使用 Protocol 类型，`cast` 收敛在 `build_parser` 单一赋值点。

---

### S1-IMPL-F02：runner 缺失缺少 stderr 诊断 → **已关闭**

**原始 finding**：`main.py` 在 `COMMAND_RUNNERS` 缺失 runner 时静默返回 `EXIT_FAILURE`，无 stderr 诊断。

**修复方案**：新增 `MISSING_RUNNER_DIAGNOSTIC_TEMPLATE` 常量（`main.py:21-23`），在 `runner is None` 分支先向 stderr 输出诊断再返回 `EXIT_FAILURE`（`main.py:41-48`）。新增测试 `test_main_reports_missing_command_runner`（`test_arg_parsing.py:202-221`）验证退出码和 stderr 内容。

**验证结果**：

| 检查项 | 状态 | 证据 |
|---|---|---|
| stderr 诊断存在 | ✅ | `print(MISSING_RUNNER_DIAGNOSTIC_TEMPLATE.format(...), file=sys.stderr)` 在 `return EXIT_FAILURE` 之前（`main.py:42-47`） |
| 诊断信息清晰 | ✅ | 模板输出 `dayu-cli: 内部错误：命令 '{command_name}' 缺少注册 runner。`，包含中文内部错误说明、关键术语 `缺少注册 runner`、具体命令名 |
| 测试覆盖退出码 | ✅ | `test_main_reports_missing_command_runner` 断言 `exit_code == EXIT_FAILURE` |
| 测试覆盖 stderr 内容 | ✅ | 断言 `"内部错误" in captured.err`、`"缺少注册 runner" in captured.err`、`"prompt" in captured.err` |
| 测试触发机制正确 | ✅ | 使用 `monkeypatch.delitem(cli_main.COMMAND_RUNNERS, "prompt")` 模拟缺失 runner |

**结论**：S1-IMPL-F02 已关闭。runner 缺失时 stderr 输出清晰内部诊断，测试覆盖退出码和诊断文本验证。

---

## Fix 引入新问题检查

逐项检查 fix 变更是否引入新的 correctness、type safety 或 structural 问题：

### 1. `CommandSubparserRegistry` Protocol 与 argparse 运行时兼容性

- **入口/函数**: `build_parser` → `cast(CommandSubparserRegistry, parser.add_subparsers(...))`
- **文件(行号)**: `dayu/cli/arg_parsing.py:113-119`
- **分析**: Protocol 要求 `add_parser(name, *, help, description, parents)`。真实的 `_SubParsersAction.add_parser` 实际接受更多参数（如 `aliases`、`prog` 等 via `**kwargs`），但我们的 Protocol 是描述需求端而非完整实现端，所有调用点只传这四个参数，类型检查器只检查调用方是否符合 Protocol 声明。运行时 `add_parser` 由 argparse 提供，与类型标注无关。
- **直接证据**: 25 个测试全部通过，包含每个命令的 help 生成（间接验证 `add_parser` 正确注册）；`build_parser()` 在 `parse_cli_args()` 中的完整路径正常工作。
- **结论**: 无新问题。Protocol + `cast` 是 Python 中隔离 stdlib 私有类型的标准模式。

### 2. `monkeypatch.delitem` 对模块级 dict 的副作用

- **入口/函数**: `test_main_reports_missing_command_runner`
- **文件(行号)**: `tests/cli/test_arg_parsing.py:213`
- **分析**: `monkeypatch.delitem(cli_main.COMMAND_RUNNERS, "prompt")` 删除 dict 中的键。pytest `monkeypatch` 夹具在测试函数结束时自动恢复原始状态，不会污染后续测试。
- **直接证据**: 25 个测试全部通过；`test_placeholder_runner_returns_not_implemented`（同样依赖 "prompt" runner 存在）在第 184 行，早于 `test_main_reports_missing_command_runner`，且通过。若 monkeypatch 未正确恢复，依赖 `COMMAND_RUNNERS["prompt"]` 的后续测试会失败。
- **结论**: 无新问题。pytest monkeypatch 自动恢复语义正确。

### 3. 未引入新依赖、新模块、新抽象泄漏

| 检查项 | 状态 |
|---|---|
| `import dayu.engine|host|service|fins|ui` 零命中 | ✅ |
| 无新增模块 | ✅ |
| 无 `Any`/`object` 类型逃逸 | ✅ |
| 无 `hasattr`/`getattr` | ✅ |
| Protocol 不导出（不在 `__all__` 中） | ✅ |

---

## S1 Scope 边界确认

| 边界检查 | 状态 | 证据 |
|---|---|---|
| 未实现 S2-S7 | ✅ | `COMMAND_RUNNERS` 所有 10 个命令仍映射到 `run_not_implemented_command` |
| 未触达 Host/Fins | ✅ | `rg -n 'import dayu\.(engine\|host\|service\|fins\|ui)' dayu/cli/` 零命中 |
| 未复制旧 dayu-agent 实现 | ✅ | 无旧实现 import；命令参数面以当前仓库风格重新定义 |
| 命令注册范围不变 | ✅ | `CLI_COMMAND_NAMES` 仍为 10 个；`EXCLUDED_COMMAND_NAMES` 仍为 6 个 |
| 退出码契约不变 | ✅ | 5 个退出码常量未修改 |

---

## Verification Commands Re-Run

```
pytest tests/cli -q                        → 25 passed in 0.10s
pytest tests/cli --cov=dayu.cli -q         → 99% coverage (main.py 93%)
python -m pyright dayu/ tests/ utils/      → 0 errors, 0 warnings, 0 informations
git diff --check                           → clean
```

Uncovered lines in `main.py:66,69` 仍为原始的 `SystemExit(None)` 和 `SystemExit(code)` 非 int 防御路径，与本轮 fix 无关。

---

## Conclusion

**PASS。**

两项 accepted findings（S1-IMPL-F01、S1-IMPL-F02）均已关闭：私有类型 `_SubParsersAction` 已通过 `CommandSubparserRegistry` Protocol 隔离；runner 缺失路径已输出清晰 stderr 诊断并有测试覆盖。Fix 未引入新问题，S1 scope 未扩大。25 个测试全部通过，pyright 零报错，覆盖率 99%。
