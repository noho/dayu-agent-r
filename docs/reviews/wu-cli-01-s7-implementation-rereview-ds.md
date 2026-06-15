# WU-CLI-01 / CLI-01-S7 implementation re-review

## Gate

- gate: implementation re-review
- work unit: WU-CLI-01
- slice: CLI-01-S7 init current-schema workspace bootstrap
- review focus: S7-RV-F02 fix closure only
- artifact path: `docs/reviews/wu-cli-01-s7-implementation-rereview-ds.md`
- timestamp: 20260614-180439

## Scope

本轮只复核 controller accepted finding S7-RV-F02 的 fix 是否关闭，并检查 fix 是否引入新问题。不重新打开 rejected findings S7-RV-F01 / S7-RV-F03（除非 fix 引入了新的直接证据）。

## Re-review method

逐行走读了以下关键路径：

1. `ParsedCliArgs` 类型定义 → `reset: bool` 字段存在性与类型一致性（`arg_parsing.py:124`）
2. `_new_default_namespace()` → `namespace.reset = False` 初始化（`arg_parsing.py:230`）
3. `parse_cli_args` → `_new_default_namespace()` → argparse `parse_args(namespace=...)` 链路（`arg_parsing.py:181-191`）
4. `run_init_command` → `args.reset` 读取路径（`init.py:87`）
5. `test_default_namespace_initializes_reset_false` 测试覆盖（`test_arg_parsing.py:307-319`）
6. Fix 未触及的 rejected findings S7-RV-F01 / S7-RV-F03 对应代码区域，确认未引入新的直接证据

所有判断基于直接代码路径证据；root cause 与触发输入、实际分支、返回值或副作用在同一条逻辑/数据路径上。

## Fix verification: S7-RV-F02

Controller 要求三项修复：

### 要求 1：`ParsedCliArgs` 补充 `reset: bool`

- **位置**: `dayu/cli/arg_parsing.py:124`
- **实际代码**: `reset: bool`
- **验证**: 已补充。`reset` 现在与 `overwrite: bool`（第 125 行）同为 `ParsedCliArgs` 声明的布尔字段，typed CLI namespace contract 完整。

### 要求 2：`_new_default_namespace()` 设置 `namespace.reset = False`

- **位置**: `dayu/cli/arg_parsing.py:230`
- **实际代码**: `namespace.reset = False`
- **验证**: 已补充。`reset` 初始化紧随 `namespace.overwrite = False`（第 231 行），两条 `store_true` 布尔参数的初始化策略一致。`parse_cli_args` 在 `parser.parse_args(argv, namespace=_new_default_namespace())` 中将此 namespace 传入 argparse，argparse 在命令行提供 `--reset` 时覆盖为 `True`，行为正确。

### 要求 3：测试证明 default namespace / parser path 下 `reset` 存在且默认为 `False`

- **位置**: `tests/cli/test_arg_parsing.py:307-319`
- **测试函数**: `test_default_namespace_initializes_reset_false`
- **断言**:
  - `parse_cli_args(("init",))` → `init_args.reset is False`（init 命令 parser 路径）
  - `parse_cli_args(("init",))` → `init_args.overwrite is False`（一致性对照）
  - `parse_cli_args(("prompt", "hello"))` → `prompt_args.reset is False`（非 init 命令也从默认 namespace 获得 `reset=False`）
- **验证**: 测试覆盖了 default namespace 经 parser 路径后的 `reset` 默认值，以及非 init 命令的 `reset` 默认值。断言使用 `is False`（identity check for False singleton），严格验证布尔默认。

### `run_init_command` 读取 `args.reset` 一致性

- **位置**: `dayu/cli/commands/init.py:87`
- **实际代码**: `if args.reset:`
- **验证**: `args` 参数类型标注为 `ParsedCliArgs`（`init.py:76`），`reset` 现已在 `ParsedCliArgs` 中声明为 `bool`，在 `_new_default_namespace()` 中初始化为 `False`。`run_init_command` 生产路径始终经 `parse_cli_args` → `_new_default_namespace()` → argparse `store_true`，`reset` 属性始终存在，typed contract 与 runtime attribute 一致。无 `AttributeError` 风险。

## Fix status: S7-RV-F02

**已修复**。

三项 controller 要求均已实现，且实现方式与既有 `overwrite` 字段的模式一致：typed field → default namespace init → `store_true` argparse action。未引入胶水代码、兼容分支或 `getattr` 逃逸。

## New findings check

对 fix 触及的代码区域执行了 adversarial failure pass：

1. **`_new_default_namespace()` 字段顺序**: `namespace.reset = False`（第 230 行）位于 `namespace.overwrite = False`（第 231 行）之前。两个字段均为简单布尔赋值，无相互依赖，顺序不影响正确性。

2. **`ParsedCliArgs` 字段位置**: `reset: bool`（第 124 行）位于 `overwrite: bool`（第 125 行）之前，与其他 init 命令字段（`overwrite`、`rebuild`、`infer`）聚集在同一区域。类型声明位置不影响运行时行为。

3. **测试独立性**: `test_default_namespace_initializes_reset_false` 不依赖 fixture、mock 或外部状态，仅使用 `parse_cli_args` 公共 API。测试不会因其他测试修改全局状态而 flaky。

4. **Rejected findings 未受影响**:
   - S7-RV-F01（`_raise_if_legacy_asset_selected` 对 prompts 子目录同名文件误伤风险）：fix 未修改 `init.py:208-221`，该 guard 逻辑不变。当前 assets 无同名文件，误伤风险未实际触发，无新的直接证据证明它变成当前阻塞问题。
   - S7-RV-F03（`workspace/config` 为普通文件时错误消息精度）：fix 未修改 `init.py:224-265` 相关路径，错误处理行为不变。当前仍安全失败 exit 1，无新的直接证据证明错误消息精度变成当前阻塞问题。

5. **架构边界**: fix 仅修改 `dayu/cli/arg_parsing.py` 和 `tests/cli/test_arg_parsing.py`，均属 CLI adapter 层。未跨层穿透到 Service / Host / Engine / Fins。未新增 import、未修改 public exports。符合 `UI -> Service -> Host -> Engine` 分层约束。

6. **编码约束**: `reset: bool` 是显式类型标注，无 `Any` / `object` 逃逸。`namespace.reset = False` 是直接属性赋值，无 `hasattr` / `getattr` / `setattr` 动态访问。新增测试有完整中文 docstring。符合 AGENTS.md 编码硬约束。

**未发现新问题**。

## Open Questions

无。

## Residual Risk

- 当前 fix 仅在 S7-RV-F02 范围内关闭 typed namespace 与 runtime attribute 不一致。其他 `ParsedCliArgs` 字段如果也存在"仅靠 argparse 隐式默认、未在 `_new_default_namespace()` 显式初始化"的情况，不在本 re-review scope 内。从代码阅读来看，`overwrite` 和 `reset` 是 init 命令仅有的两个 `store_true` 布尔参数，二者现均已显式初始化；其他命令的 `store_true` 参数（如 `new_session`、`debug_sse` 等）也在 `_new_default_namespace()` 中有对应初始化行。未发现同类型遗漏。
- Fix 未引入新的 test gap、CI gap 或未检查区域。

## Validation evidence

- `tests/cli/test_arg_parsing.py tests/cli/test_init_command.py`: 35 passed（fix artifact 记录）
- `tests/cli`: 94 passed（fix artifact 记录）
- `pyright dayu/ tests/ utils/`: 0 errors（fix artifact 记录）
- `git diff --check`: clean（本 re-review 复核确认）
