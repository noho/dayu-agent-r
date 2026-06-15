# WU-CLI-01 / CLI-01-S1 Implementation Re-Review (AgentMiMo)

## Scope

- Mode: current changes
- Branch: `phase/host-ui-implementation`
- Base: `main`
- Gate: implementation re-review（fix 后验证）
- Review target: fix 后 workspace changes，验证 accepted findings 关闭状态
- Output file: `docs/reviews/wu-cli-01-s1-implementation-rereview-mimo.md`
- Included scope:
  - `dayu/cli/arg_parsing.py`（S1-IMPL-F01 fix 验证）
  - `dayu/cli/main.py`（S1-IMPL-F02 fix 验证）
  - `tests/cli/test_arg_parsing.py`（新增测试验证）
- Excluded scope: none
- Parallel review coverage: 无

## Accepted Findings 验证

### S1-IMPL-F01：argparse 私有类型签名收敛 — PASS

**Controller 要求**：应收敛为本模块内部公共描述，避免在多个签名散落依赖 stdlib 私有类型名。

**Fix 实现**：
- `dayu/cli/arg_parsing.py:59-84`：新增 `CommandSubparserRegistry` Protocol，只描述 `add_parser(...)` 能力。
- `dayu/cli/arg_parsing.py:113-114`：`build_parser` 用 `cast(CommandSubparserRegistry, parser.add_subparsers(...))` 将 argparse 返回值收敛为 Protocol。
- 所有 10 个命令注册函数（`_register_init_command` 等）的 `subparsers` 参数均改为 `CommandSubparserRegistry` 类型。

**验证**：
- `grep -rn "_SubParsersAction" dayu/ tests/` — 零命中，私有类型已从所有签名中消除。
- `CommandSubparserRegistry` 是本模块内部 Protocol，不依赖 argparse 私有类型名。
- 未使用 `Any` 或 `object` 逃避类型；Protocol 只描述实际需要的 `add_parser` 能力，符合编码约束。
- pyright 0 errors。

**结论**：S1-IMPL-F01 已关闭。修复方法正确，Protocol 设计合理，无新问题引入。

### S1-IMPL-F02：runner 缺失时输出 stderr 诊断 — PASS

**Controller 要求**：应输出清晰内部 dispatch 诊断，并补测试。

**Fix 实现**：
- `dayu/cli/main.py:21-23`：新增 `MISSING_RUNNER_DIAGNOSTIC_TEMPLATE` 常量。
- `dayu/cli/main.py:41-48`：`runner is None` 分支先 `print(MISSING_RUNNER_DIAGNOSTIC_TEMPLATE.format(...), file=sys.stderr)`，再 `return EXIT_FAILURE`。
- `tests/cli/test_arg_parsing.py:202-221`：新增 `test_main_reports_missing_command_runner`，通过 `monkeypatch.delitem` 删除 `prompt` runner，验证退出码 `EXIT_FAILURE`、stderr 包含 `内部错误`、`缺少注册 runner`、`prompt`。

**验证**：
- 测试断言覆盖完整：退出码 + 三个 stderr 关键片段。
- 诊断模板使用 `format(command_name=...)` 插入实际命令名，排查价值明确。
- 诊断输出在 `return EXIT_FAILURE` 之前，确保即使后续有人修改退出码，诊断仍会输出。
- 测试通过 monkeypatch 删除 runner 模拟真实缺失场景，非硬编码路径。

**结论**：S1-IMPL-F02 已关闭。诊断信息清晰，测试覆盖完整，无新问题引入。

## Fix 引入新问题检查

**未发现新问题。**

逐项检查：

1. **类型安全**：`CommandSubparserRegistry` Protocol 是结构化子类型，`cast` 在 `build_parser` 唯一调用点将 argparse 返回值转为 Protocol。运行时 `add_subparsers()` 返回的对象确实有 `add_parser` 方法，`cast` 不会引入运行时类型不匹配。pyright 对 Protocol 使用 0 errors。

2. **运行时行为不变**：`_SubParsersAction` 消除只影响类型标注，不影响运行时 argparse 行为。`cast` 是 typing-only 操作，零运行时开销。

3. **诊断输出副作用**：`MISSING_RUNNER_DIAGNOSTIC_TEMPLATE` 的 `print(..., file=sys.stderr)` 只在 `runner is None` 时触发，当前正常路径（所有 CLI_COMMAND_NAMES 都有 runner）不会触发。未来新增命令忘记注册 runner 时，诊断输出是有价值的副作用。

4. **测试隔离**：`test_main_reports_missing_command_runner` 使用 `monkeypatch.delitem` 修改 `COMMAND_RUNNERS`，pytest 的 monkeypatch 机制保证测试结束后自动恢复，不影响其它测试。

5. **S1 scope 未扩大**：
   - `dayu/cli/` 文件结构未变：`__init__.py`、`__main__.py`、`arg_parsing.py`、`main.py`、`exit_codes.py`、`commands/__init__.py`。
   - 无新增文件，无新增 import。
   - `grep "import dayu\.\(engine\|host\|service\|fins\|ui\)" dayu/cli/ tests/cli/` — 零命中。
   - 未实现 S2-S7 中任何业务逻辑。
   - 未触达 Host/Fins business execution。
   - 未复制旧 dayu-agent 实现。

## S1 Scope 边界确认

**PASS** — scope 未扩大。

- CLI package 文件集与 fix 前完全一致。
- `CommandSubparserRegistry` Protocol 是 `arg_parsing.py` 内部类型收敛，不新增公共 API。
- `MISSING_RUNNER_DIAGNOSTIC_TEMPLATE` 是 `main.py` 内部常量，不新增公共 API。
- `__all__` 导出集未变。
- 无 S2-S7 语义渗入。

## 验证结果

| 验证项 | 结果 |
|---|---|
| `pytest tests/cli -q` | 25 passed in 0.10s |
| `pytest tests/cli --cov=dayu.cli --cov-report=term-missing -q` | 25 passed, total 99%（`arg_parsing.py` 100%, `main.py` 93%） |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | clean |
| `_SubParsersAction` grep | 零命中 |
| 禁止 import grep | 零命中 |

## Residual Risk

无。两个 accepted findings 均已关闭，fix 未引入新问题，S1 scope 未扩大。

`main.py` 覆盖率 93%，未覆盖行 66（`code is None`）和 69（`code` 非 int 非 None）为 `_normalize_system_exit_code` 防御路径，不影响 S1 正确性。

## Conclusion

**Pass.** S1-IMPL-F01 和 S1-IMPL-F02 均已按 controller adjudication 要求修复并验证通过。`CommandSubparserRegistry` Protocol 正确收敛了 argparse 私有类型依赖，`MISSING_RUNNER_DIAGNOSTIC_TEMPLATE` 提供了清晰的 stderr 诊断。fix 未引入新问题，S1 scope 未扩大。25 个测试全部通过，pyright 零报错，覆盖率 99%。
