# WU-CLI-01 / CLI-01-S7 implementation re-review

## Scope

- Mode: targeted re-review（只复核 accepted finding S7-RV-F02 的 fix）
- Branch: `phase/host-ui-implementation`
- Base: `main`
- Output file: `docs/reviews/wu-cli-01-s7-implementation-rereview-mimo.md`
- Included scope:
  - `dayu/cli/arg_parsing.py`（ParsedCliArgs + _new_default_namespace）
  - `tests/cli/test_arg_parsing.py`（test_default_namespace_initializes_reset_false）
  - `docs/reviews/wu-cli-01-s7-implementation-fix-codex.md`（fix report）
  - `dayu/cli/commands/init.py`（args.reset 消费路径核对）
- Excluded scope: S7-RV-F01 / S7-RV-F03（controller rejected，fix 未引入新直接证据证明其变为当前阻塞问题）

## S7-RV-F02 fix 状态

**状态：已修复。**

### Controller 要求

1. `ParsedCliArgs` 补 `reset: bool`。
2. `_new_default_namespace()` 设置 `namespace.reset = False`。
3. 有测试证明 default namespace / parser path 下 `reset` 存在且默认为 `False`。

### 逐项验证

**要求 1：`ParsedCliArgs` 补 `reset: bool`**

- `dayu/cli/arg_parsing.py:124`：`reset: bool` 已声明在 `ParsedCliArgs` 类体中，位于 `overwrite: bool`（行 125）之前。
- 类型声明正确，与 `overwrite: bool`、`rebuild: bool`、`infer: bool` 等同级布尔字段一致。
- ✅ 已满足。

**要求 2：`_new_default_namespace()` 设置 `namespace.reset = False`**

- `dayu/cli/arg_parsing.py:230`：`namespace.reset = False` 已设置。
- 位于 `namespace.overwrite = False`（行 231）之前，与 `ParsedCliArgs` 字段顺序一致。
- ✅ 已满足。

**要求 3：测试证明 default namespace / parser path 下 `reset` 存在且默认为 `False`**

- `tests/cli/test_arg_parsing.py:307-319`：`test_default_namespace_initializes_reset_false` 测试。
- 覆盖两条路径：
  - `parse_cli_args(("init",))` → `init_args.reset is False`（init 命令，`--reset` 由 `store_true` 注册，默认 `False`；default namespace 也提供 `False`，一致）。
  - `parse_cli_args(("prompt", "hello"))` → `prompt_args.reset is False`（prompt 命令不注册 `--reset`，namespace 默认值 `False` 直接生效）。
- 额外断言 `init_args.overwrite is False` 确认同级布尔字段一致性。
- ✅ 已满足。

### 消费路径核对

- `dayu/cli/commands/init.py:87`：`if args.reset:` 直接读取 `args.reset`。
- 修复前：`ParsedCliArgs` 无 `reset` 声明，`_new_default_namespace()` 无 `reset` 初始化；若 init 命令以外的 runner 碰巧读取 `args.reset`（理论上不应发生，但 typed namespace contract 应自洽），会触发 `AttributeError`。
- 修复后：typed namespace 显式声明 `reset: bool`，default namespace 初始化为 `False`，消费路径安全。
- fix 未改动 `init.py` 的 `args.reset` 读取逻辑，只补齐了 namespace contract。

## Fix 引入的新问题检查

**未发现新问题。**

- `reset: bool` 声明与 `_new_default_namespace()` 初始化模式与 `overwrite`、`rebuild`、`infer` 等同级字段完全一致，无特殊风险。
- 测试 `test_default_namespace_initializes_reset_false` 覆盖了 init（有 `--reset` 注册）和 prompt（无 `--reset` 注册）两条路径，确认 default namespace 在两种场景下均提供 `reset=False`。
- argparse `store_true` 在用户传 `--reset` 时写入 `True`，不传时保持 namespace 默认值 `False`；default namespace 与 parser 行为一致，无冲突。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- 无新增残余风险。
- 既有残余风险（reset 过程中 SIGINT 部分删除、config copy 非目录级事务）保持不变，已在 controller adjudication 和原始 review 中 classified as accepted low residual risk。

## Validation evidence

- `pytest tests/cli/test_arg_parsing.py tests/cli/test_init_command.py -q`：35 passed，3 warnings（既有 edgar 弃用警告）。
- `pytest tests/cli -q`：94 passed，3 warnings。
- `python -m pyright dayu/ tests/ utils/`：0 errors，0 warnings，0 informations。
- `git diff --check`：clean。

## Conclusion

S7-RV-F02 已修复。`ParsedCliArgs.reset: bool` 声明、`_new_default_namespace()` 初始化、测试覆盖三项要求均已满足。fix 未引入新问题。S7-RV-F01 / S7-RV-F03 未重新打开（controller rejected，fix 未提供新直接证据）。
