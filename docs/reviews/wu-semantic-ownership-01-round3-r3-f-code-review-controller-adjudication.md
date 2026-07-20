# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-F Code Review Controller Adjudication

## 结论

本轮 R3-F implementation code review 输入：

- `docs/reviews/wu-semantic-ownership-01-round3-r3-f-code-review-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-round3-r3-f-code-review-ds.md`
- Controller 本地差异审查

MiMo 与 DS 均结论为 PASS / 0 material findings。Controller 复核后接受其大部分 PASS 结论，但新增并接受 1 个 material finding：`init` staging install rollback 使用 `except BaseException`，异常边界过宽。

## Accepted Finding R3-F-CR-01: init staging install rollback 捕获 BaseException，异常 owner 边界过宽

### Semantic fact / contract

`dayu-cli init` 的 config tree 安装事务 owner 是 `dayu/cli/commands/init.py`。该 owner 需要承诺：

- 安装失败时恢复已移动到 backup 的旧 `config` tree。
- 用户 SIGINT 时保持工作区 config 不处于半安装状态。
- 只捕获安装事务明确需要处理的失败语义，不把非本地安装失败的 `BaseException` 子类纳入 CLI rollback contract。

### Correct owner

`dayu/cli/commands/init.py` 的 `_install_staged_config_tree(...)`。

### Ownership drift

当前实现用 `except BaseException` 表达 rollback 边界：

- `dayu/cli/commands/init.py:336-344`

这把 rollback owner 从“安装阶段 OSError / KeyboardInterrupt”扩大到所有 Python 基础异常，包括 `SystemExit`、`GeneratorExit` 和其它非本地事务失败。该写法不是语义 owner 的精确 contract，也违反 AGENTS.md 对异常/边界设计的约束。

### Direct evidence

```text
dayu/cli/commands/init.py:336-344
try:
    if workspace_config_dir.exists():
        os.replace(workspace_config_dir, backup_dir)
        existing_moved = True
    os.replace(staging_dir, workspace_config_dir)
except BaseException:
    if existing_moved and not workspace_config_dir.exists():
        os.replace(backup_dir, workspace_config_dir)
    raise
```

现有 tests 只覆盖了 staging install `OSError` 回滚：

- `tests/cli/test_init_command.py:192-235`

现有 SIGINT 测试覆盖复制阶段 `_copy_asset_to_staging` 抛 `KeyboardInterrupt`，没有覆盖旧 config 已移动到 backup 后、安装 staging 时收到 `KeyboardInterrupt` 的回滚路径：

- `tests/cli/test_init_command.py:483-509`

### Failure / cost

当前实现行为多数情况下能恢复旧 config，但 contract 过宽：

- 它会捕获非安装失败语义，形成不可审计的异常边界。
- 后续维护者难以判断哪些异常被有意支持为 rollback trigger。
- 测试未锁住“安装阶段 SIGINT 也恢复旧 config”这个真实需求，未来把 `except BaseException` 简化为普通 `Exception` 时可能漏掉 SIGINT 回滚。

### Required correction

- 将 `except BaseException` 改为精确捕获安装事务需要处理的异常，例如 `except (OSError, KeyboardInterrupt):`。
- 保留旧 config 已移动后安装失败的 rollback 语义。
- 新增 owner 级测试：模拟 `os.replace(staging_dir, config_dir)` 抛 `KeyboardInterrupt`，断言旧 config 恢复、staging 保留给外层 finally 清理或保持可诊断、backup 不残留。

### Verification points

- `pytest tests/cli/test_init_command.py -q`
- `python -m pyright dayu/ tests/ utils/`
- `rg -n "except BaseException" dayu/cli dayu/runtime dayu/service tests`

## Rejected / Deferred

MiMo 与 DS 没有提出 material findings。Controller 本地审查未接受其它候选项：

- `shlex` import residual：仍被 `_quoted_diagnostic_text(...)` 使用，不属于 upload batch public contract residual。
- `README.md` 大幅收敛：符合根 README 当前用户手册约束，并有 parser/public contract tests 锁定已删除 flag 与 JSON argv 描述。
- 并发 init 缺少跨进程锁：已在 plan 和 implementation artifact 中声明为 out of scope，不是本轮 R3-F 必修。
- fresh-lock install 验证：属于 release/packaging pipeline 环境验证，本轮已通过 metadata/constraints 同源测试与本地 installed metadata 交叉检查。

## Gate Decision

R3-F 不可 close。需派 AgentCodex 修复 R3-F-CR-01，完成后重新运行验证并做复审。
