# WU-SEMANTIC-OWNERSHIP-01 / R11-I2 validation plan-drift Controller adjudication

## 1. 结论

`PLAN FIX REQUIRED / IMPLEMENTATION PAUSED`。

Controller 接受一个 implementation-validation plan-drift finding：`R11-I2-VAL-PD-F01`。这不是新的产品问题、sub-WU 或 scope expansion，而是 accepted plan 对 cumulative test path 的 slice 分配遗漏。当前 I2 dirty implementation tree保留；在 plan-only correction完成完整双路 review并被接受前，不得继续修改 code/test/README/packaging/CI。

## 2. 直接证据

R11-I2 accepted contract 要求根 `README.md`：

- 说明 `upload_filings_from --infer` 与 `FMP_API_KEY`；
- 删除旧 JSON argv `schema_version=1` / `commands` 公共协议；
- 说明生成 POSIX `.sh` / Windows `.cmd` executable script，而不是“不生成 shell”。

I2 完成相应 README owner 更新后，focused cumulative test为 `1 failed, 152 passed, 2 skipped`。唯一失败 `tests/cli/test_arg_parsing.py::test_root_readme_matches_current_cli_public_contract` 仍冻结三组相反的旧 contract：

1. 将所有 `--infer` 列入根 README 禁止词；
2. 要求根 README 保留 `"schema_version": 1` 与 `"commands"`；
3. 要求根 README 保留“不生成 shell”。

同文件现有 parser owner tests 已明确 `upload_filings_from` 支持 `--infer`，因此失败不是 README 写错，也不能通过隐藏参数、恢复 JSON 或兼容文案修复。正确 semantic owner 是根 README public-contract test：它应继续拒绝 direct upload 已删除/未实现 contract，但正向断言 batch-only `--infer`、executable script 与 no-JSON current surface。

## 3. 为什么需要 plan correction

`tests/cli/test_arg_parsing.py` 在 R11 cumulative closed allowlist 内，但 amended plan §4 将其只分配给 I1，并在 §7.1 排除于 I2 exact allowlist；I2 authorization 又把 I1 hash设为 protected。故 AgentCodex 正确停止，Controller 不能用临时授权覆盖 accepted plan。

接受 finding 的最小 plan fix 是：

- 在 §4 slice allocation 和 §7.1 I2 exact allowlist 中加入 `tests/cli/test_arg_parsing.py`，范围只限 `test_root_readme_matches_current_cli_public_contract`；
- 明确删除其旧 `--infer`/JSON/no-shell assertions，改为 current root README contract 的正/负断言；
- 更新相关 path counts、protected-I1/I2 checkpoint wording与 validation scan，但不改变生产、README、workflow、wheel、review或 commit架构；
- 不允许修改 parser tests 的其它 owner contract，不重新打开已完成 I1 producer/consumer实现。

## 4. finding ledger

| id | severity | status | owner fix |
|---|---|---|---|
| `R11-I2-VAL-PD-F01` | HIGH | ACCEPTED / OPEN | accepted plan 的 slice allowlist 与 README contract test projection |

blocker question：`0`。设计真源与用户裁决无矛盾；不需要用户重新裁决。

## 5. protected stopped tree

- HEAD：`a527ec030215e5bfcf9c4fad2f4a6fda243f5d65`；staged set为空。
- accepted plan before-fix SHA-256：`55d35256f0f89f39f722438dc19d9ae65269b16810f96f1cd0129c6eba06d427`。
- stopped product/test/README/packaging tracked binary diff SHA-256：`718846cdd5ce3ad8d9d789b3b7b47e18df8943ac541f63a925dd696b06fe8332`，精确命令为 `git diff --binary HEAD -- README.md dayu tests pyproject.toml requirements.txt .github`；它有意排除随后由 Controller 更新的 control/plan/review artifacts，untracked workflow 由下方独立 hash 锁定。
- stopped `tests/cli/test_arg_parsing.py` SHA-256：`7cdc4c1d014bc7012aca28f05927b8afbbd04b86cc6d0aa2dfbf5f87af91ece6`，与 I1 protected lock一致。
- untracked renderer SHA-256：`dfe0508deb905ef9bc21204a75a8ec55abf87ec254517831556dc7a8ba7aea65`。
- untracked Windows workflow SHA-256：`4026da55c789c0f3f961887f3f19536c7817abad4665ffd78b493219f2560953`。
- stopped I2 path changes、六个 tracked deletions、四个 README、I1 tree 与 Controller artifacts均不得在 plan gate变化。

## 6. 唯一 plan-only authorization

AgentCodex 只可修改：

1. `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`
2. 新增 `docs/reviews/wu-semantic-ownership-01-r11-i2-validation-plan-drift-fix-codex.md`

必须完整修复 §3 的四项要求，逐条记录 before/after plan diff与 protected stopped-tree复核，以 `READY_FOR_DUAL_COMPLETE_PLAN_DRIFT_REVIEW` 结束。不得修改 code、tests、README、packaging、workflow、Controller control/artifacts，不得运行后续 implementation、stage、commit、push、PR或 R12。

AUTHORIZED_R11_I2_PLAN_DRIFT_FIX_ONLY
