# WU-SEMANTIC-OWNERSHIP-01 / R12 S2 code review Controller adjudication

## Gate 与结论

- Gate：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 R12 S2 cumulative complete code review，不是新 WU。
- AgentMiMo artifact：`docs/reviews/wu-semantic-ownership-01-r12-s2-code-review-mimo.md`，236 行 / 18,784 bytes / SHA-256 `c983c2341785406846e491abd0099b8ba1d2c80be30c4898dc1cd30e8d7eb623`，verdict `PASS_WITH_OBSERVATIONS`。
- AgentDS artifact：`docs/reviews/wu-semantic-ownership-01-r12-s2-code-review-ds.md`，304 行 / 22,081 bytes / SHA-256 `25c545f79a01a6654ac4dfa13bea55112729d256d6639e51d68e8160eeeb763a`，verdict `PASS`。
- Controller verdict：`FIX_REQUIRED`。两路 reviewer 对 staging/publication transaction、Service Fins override、S3 scope 与 stale caller 的主体结论成立，但其“所有 KeyboardInterrupt 路径正确”的结论遗漏了 environment persistence boundary，被 Controller 直接代码证据与可重复探针推翻。
- accepted/open：`3`；rejected/no-fix：`4`；S3 mandatory residual：`2`；design contradiction：`0`；external blocker：`0`。

## Accepted current findings

### R12-S2-CR-F01 — HIGH — POSIX persistence interrupt 遗留含 secret 的 private temp

- Owner：`dayu.cli.init_environment`，具体是 `_write_profile_atomically` / POSIX persistence typed outcome。
- 直接代码：`_write_profile_atomically` 只捕获 `(OSError, UnicodeError)`；`KeyboardInterrupt` 在 file write、file `fsync` 或 `os.replace` 边界绕过 private-temp cleanup。
- Controller probe：对 `dayu.cli.init_environment.os.replace` 注入 `KeyboardInterrupt` 后，public profile 保持 absent，但 home 下仍存在 `.dayu-init-env-*`。该文件包含刚写入的 secret material，虽为 `0600`，仍违反 private staging cleanup 与 fixed-plan interrupt fault matrix。
- 必须修复：environment owner 必须在 interrupt 的调用前/调用后两种边界清理仍由本次 owner 持有的 private temp，不跟随 symlink、不删除未知 identity；若 profile replace 已实际生效，必须通过 typed/redacted truth 表达，不能把 durable store 状态猜成未写。测试必须覆盖 write/fsync/replace 的普通失败与 interrupt，且断言无 secret temp 遗留、无 secret 输出。

### R12-S2-CR-F02 — HIGH — Windows partial `setx` interrupt 丢失 written-names durable truth

- Owner：`dayu.cli.init_environment` 的 Windows batch persistence state machine 与 redacted result/interrupt contract。
- 直接代码：`_persist_windows_environment` 只捕获 `OSError`；第二个或后续 `subprocess.run` 抛 `KeyboardInterrupt` 时，先前成功的 `written_names` list 随 stack unwind 丢失，调用方只得到裸 interrupt。
- Controller probe：mock 第一次 `setx` 为 returncode 0、第二次抛 `KeyboardInterrupt`，观察到 `successful_calls_before_interrupt=1`，但 `persist_environment` 只传播 `KeyboardInterrupt-without-typed-result`。
- 必须修复：以最小 typed/redacted interrupt contract 保存并投影 `written_names` / `unwritten_names`，不含 values/captured output；CLI 仍保持 keyboard-interrupt exit semantics，不得把 interrupt 降格成普通 failure，也不得伪造回滚。还须覆盖 durable store 已完成后、进程内 env injection/verification 期间的 interrupt truth。

### R12-S2-CR-F03 — MEDIUM — persistence interrupt 未 abort prepared workspace transaction

- Owner：`dayu.cli.commands.init.run_init_command` 的 transaction orchestration。
- 直接代码：`_persist_environment_if_needed(...)` 周围只捕获 `(EnvironmentPersistenceError, OSError)`；裸或 typed `KeyboardInterrupt` 直接落入最外层 exit mapping，没有调用 `abort_prepared_workspace_transaction(prepared)`，也无法投影 F02 的 written names。
- Controller real-owner probe：真实完成 staging/discovery 后，仅把 `persist_environment` 注入为 `KeyboardInterrupt`。结果为 exit code `130`、public config absent，但 workspace 下残留一个 `.dayu-init-transaction-*`。
- 必须修复：在 persistence boundary 上无论 plain 还是 owner-typed interrupt，都必须 identity-safe abort prepared transaction；typed interrupt 还要先/后按 owner contract 报告 durable written names，保留 exit code 130。若 abort 本身失败，必须保留现有 truthful retained-path error，而不是伪装已清理。

## Reviewer findings 裁决

- MiMo 01 / DS F-01（模块/函数长度）：`rejected-no-fix`。1,618 行模块只有一个 transaction 语义域，公共 API 与 typed state chain 清晰；当前提取新 result dataclass 会增加无业务语义的局部结构，不能仅按行数触发重构。
- DS F-02（`exists() or is_symlink()`）：`rejected-no-fix`。这是明确覆盖 dangling symlink 的 no-follow existence intent，不是 defect。
- DS open question 1（`_cleanup_private_path` 名称）：`rejected-no-fix`。函数以 owner identity + parent containment 为真实契约；增加只透传 wrapper 或兼容式 rename 无当前收益。
- DS open question 2（post-publication warning path）：`rejected-no-fix`。warning 同时显式带 `path_exists=False`，字段表示操作 target 而非 retained-only path，当前真值不矛盾。
- MiMo/DS 对四态、rename-after-effect、rollback、cleanup、symlink/reparse、durability、portfolio、Service override、ordinary `None`、非 Fins/Web isolation、无统一 authorization 的其余验证：接受。

## S3 mandatory residual 与 full CLI evidence

- `tests/cli/test_prompt_command.py::test_prompt_command_uses_init_generated_workspace_config` 是唯一非 init-test 的 stale caller，必须在 S3 通过显式交互输入/真实 workflow 迁移；禁止 production implicit default、compatibility fallback 或 test shim。
- Controller 已运行完整 `pytest tests/cli -q`：`469 passed, 1 failed, 2 skipped, 3 warnings`；唯一失败就是上述 stale caller。该结果是 S3 entry evidence，不将 failure 隐藏为 S2 pass，也不扩大 S2 production scope。
- prewarm、真实 POSIX subprocess smoke、真实 Windows normal/junction/rollback、Windows workflow、root/config/tests README 与最终 full CLI pass 仍由 S3 拥有。

## Fix 授权与退出条件

只授权 AgentCodex 修复 `R12-S2-CR-F01..F03`，更新 owner-level tests 与 fix artifact。允许修改：

- `dayu/cli/init_environment.py`
- `dayu/cli/commands/init.py`
- `tests/cli/test_init_environment.py`
- `tests/cli/test_init_command.py`
- 新增唯一 fix artifact `docs/reviews/wu-semantic-ownership-01-r12-s2-code-review-fix-codex.md`

如严格 owner contract 需要同步调整同模块既有 typed exception/result export，可在上述 production file 内完成；不得扩张为通用 cancellation framework、callback/factory/profile、兼容分支或 test seam。其余 10 个 fixed target 路径保持 immutable；S3、aggregate、commit、push、PR 仍未授权。

验证至少包括：owner tests；真实 staging 后 persistence interrupt cleanup；POSIX write/fsync/replace interrupt fault matrix；Windows first/middle/last interrupt written/unwritten names；secret non-disclosure；focused cumulative regression；逐文件 coverage；pyright；changed/full Ruff fingerprint；`git diff --check`；immutable hash/scope scans。所有 3 项 accepted findings 修复后进入双路 complete re-review。
