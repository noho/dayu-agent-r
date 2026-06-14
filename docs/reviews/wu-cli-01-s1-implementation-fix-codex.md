# WU-CLI-01 / CLI-01-S1 Implementation Fix (AgentCodex)

## Gate

- Work unit: WU-CLI-01
- Slice: CLI-01-S1
- Gate: implementation review fix
- Scope: 仅修复 controller accepted findings `S1-IMPL-F01` 与 `S1-IMPL-F02`
- Non-goals: 不实现 CLI-01-S2 到 CLI-01-S7；不触达 Host / Fins business execution；不提交、不 push、不开 PR

## 修复内容

### S1-IMPL-F01：收敛 argparse 私有类型签名

状态：已修复。

`dayu/cli/arg_parsing.py` 新增 `CommandSubparserRegistry` Protocol，只描述当前 parser 注册函数实际需要的 `add_parser(...)` 能力。所有命令注册函数的 `subparsers` 参数均改为使用该 Protocol，避免在多个函数签名中散落 `argparse._SubParsersAction[...]` 私有类型名。

`build_parser(...)` 在 `parser.add_subparsers(...)` 返回点将 argparse 返回值收敛为 `CommandSubparserRegistry`，私有 stdlib 类型不再出现在本模块函数签名中。

### S1-IMPL-F02：runner 缺失时输出 stderr 诊断

状态：已修复。

`dayu/cli/main.py` 新增 `MISSING_RUNNER_DIAGNOSTIC_TEMPLATE`，当已解析命令在 `COMMAND_RUNNERS` 中找不到 runner 时，先向 stderr 输出清晰内部 dispatch 诊断，再返回 `EXIT_FAILURE`。

`tests/cli/test_arg_parsing.py` 新增 `test_main_reports_missing_command_runner`，通过 monkeypatch 删除 `prompt` runner，验证退出码为 `EXIT_FAILURE`，stderr 包含 `内部错误`、`缺少注册 runner` 与命令名。

## README / 文档决策

- 已检查 `tests/README.md` 的测试分层说明；当前已覆盖 `tests/cli/` 的 parser、help、placeholder runner、退出码与全局参数位置。新增测试属于既有 CLI dispatch 失败契约，不需要再次扩写 README。
- 本次按要求新增本 fix report；未修改 `docs/host/ui-implementation-control.md`，避免扩大修复范围。

## 验证结果

- `source .venv/bin/activate && pytest tests/cli -q`
  - 结果：25 passed in 0.11s
- `source .venv/bin/activate && pytest tests/cli --cov=dayu.cli --cov-report=term-missing -q`
  - 结果：25 passed in 0.18s
  - 覆盖率：`dayu.cli` total 99%；`dayu/cli/arg_parsing.py` 100%；`dayu/cli/main.py` 93%
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：0 errors, 0 warnings, 0 informations
  - 备注：pyright 提示存在新版 `1.1.410`，当前环境版本检查通过
- `git diff --check`
  - 结果：clean

## 剩余风险 / 未覆盖项

- accepted findings 均已关闭，当前未发现需要在本 fix gate 继续处理的风险。
- `dayu/cli/main.py` 仍有 `SystemExit(None)` 与非整数 `SystemExit.code` 防御分支未被 CLI 测试覆盖；该缺口为既有防御路径，不影响本轮 accepted findings，且文件覆盖率仍高于 80%。
- S2-S7 仍未实现，这是当前 slice scope 的预期状态，不属于本 fix gate 风险。

## Completion Status

pass。S1-IMPL-F01 与 S1-IMPL-F02 已按 controller adjudication 修复并通过指定验证命令。
