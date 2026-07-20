# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-F Code Review Fix（AgentCodex）

## 修复结论

总控裁决唯一 accepted finding `R3-F-CR-01` 已修复。`dayu-cli init` 的 staging 安装事务仍由 `dayu/cli/commands/init.py` 的 `_install_staged_config_tree(...)` 唯一负责回滚，但异常边界已从所有 `BaseException` 收窄为安装事务明确处理的 `OSError` 与 `KeyboardInterrupt`。

## 第一性原理核对

finding 当前真实存在：旧 `config` 已经通过 `os.replace(...)` 移至私有 backup 后，staging 安装使用 `except BaseException` 触发回滚。事务确实需要覆盖文件系统失败与用户中断，但不应把 `SystemExit`、`GeneratorExit` 等非安装失败语义纳入本地事务 contract。因此正确修复点是安装事务 owner 的异常边界，而不是 CLI 顶层或测试夹具中的下游补偿。

## 实现改动

- `dayu/cli/commands/init.py`
  - 将 `_install_staged_config_tree(...)` 的捕获边界改为 `except (OSError, KeyboardInterrupt):`。
  - 保留 `existing_moved` 且目标目录不存在时把 backup 原子移回旧 `config` 的语义，并继续重新抛出原始安装异常。
  - 在函数异常 contract 中明确记录安装阶段 `KeyboardInterrupt` 会在回滚后重新抛出。
- `tests/cli/test_init_command.py`
  - 新增 `test_init_staged_install_keyboard_interrupt_restores_existing_config`。
  - 测试仅在 `os.replace(staging_dir, config_dir)` 时注入 `KeyboardInterrupt`，直接断言旧配置恢复、新配置未进入最终 `config`、staging 保留且 backup 无残留。

## README decision

不修改 README。本次没有改变用户可见的安装、初始化、参数、输出或工作流 contract，只精确化内部事务捕获边界并补齐同一 `tests/cli` 测试分层中的异常分支；`tests/README.md` 已覆盖 whole-tree staging 安装与 SIGINT 测试范围，未新增测试层级。

## 验证

- `source .venv/bin/activate && pytest tests/cli/test_init_command.py -q`
  - 通过：`17 passed, 3 warnings in 1.02s`。
  - warning 均来自已安装 `edgar` 包的 deprecated import，不是本次变更引入。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 通过：`0 errors, 0 warnings, 0 informations`。
- `rg -n "except BaseException" dayu/cli dayu/runtime dayu/service tests`
  - `dayu/cli`、`dayu/runtime`、`dayu/service` 无匹配；剩余匹配位于 R3-A Host stress support 与不在本 finding 范围内的 Fins 测试代码。
- `git diff --check`
  - 通过：无 whitespace error。

## Finding 状态与残余风险

- `R3-F-CR-01`：fixed。
- 剩余 accepted finding：无。
- 残余风险：若底层文件系统连 backup 回移本身也抛出 `OSError`，事务会按既有 contract fail-visible，且可能保留 backup 供诊断；要在此类双重文件系统失败下保证恢复需要 durable journal，不属于本次唯一 accepted finding。此次收窄没有新增该风险。
