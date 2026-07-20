# WU-SEMANTIC-OWNERSHIP-01 / R11-I2 validation plan-drift fix — AgentCodex

## 1. Gate 结论

本轮是同一 umbrella `WU-SEMANTIC-OWNERSHIP-01` 内 R11-I2 的 validation plan-drift
plan-only fix，不是新 WU、sub-WU、implementation slice、test fix 或 scope expansion。

Controller 接受的唯一 finding `R11-I2-VAL-PD-F01` 已写入 accepted plan：

- §4 将根 README public-contract test 的唯一函数节点加入 I2 allocation；
- §7.1 将 I2 exact allowlist 从 `14` paths 修正为 `15` paths；
- 旧的全局 `--infer` 禁止、JSON argv 必须存在与“不生成 shell”必须存在的 assertions 已明确改为
  batch-only `--infer`、no JSON argv、executable `.sh` / `.cmd` current contract；
- §7.2、§7.3、§8、§9.1 与 §10 已同步 cumulative/I1/I2 path count、protected-I1 exception、
  checkpoint 与 validation scan wording。

本轮只修改 accepted plan 并新增本 artifact。未修改 stopped code、tests、README、packaging、workflow、
Controller control/artifacts；未运行 implementation test、coverage、pyright、Ruff、wheel 或 Windows workflow；
未 stage、commit、push、创建 PR 或进入 R12。

## 2. 第一性原理与 semantic owner

修复动机成立，且 HIGH 严重度准确。直接 owner-side 证据是：

1. accepted I2 root README contract 已要求 `upload_filings_from --infer` + `FMP_API_KEY`、删除 JSON argv
   `schema_version=1` / `commands`，并说明可执行 `.sh` / `.cmd`；
2. stopped cumulative validation 唯一失败
   `tests/cli/test_arg_parsing.py::test_root_readme_matches_current_cli_public_contract` 仍冻结三组相反旧语义；
3. 同文件 parser owner tests 已证明 `--infer` 只属于 batch command，故 README、parser production、renderer、
   packaging 或 workflow 都不是根因；
4. 正确 semantic owner 是这个根 README public-contract test node。它应投影当前最终用户契约，而不是让 README
   恢复已删除协议或隐藏已实现能力。

因此最佳最小修复不是兼容文案、下游 fallback、恢复 JSON schema、移除 `--infer` 或回改 I1 producer/consumer，
而是把唯一 stale test node 重新分配给 I2，并保持同文件其它 parser/help nodes 及另外七个 I1 paths受保护。

## 3. Authority 与 scope

完整读取并遵守：

- `AGENTS.md`；
- accepted plan `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`；
- corrected Controller adjudication
  `docs/reviews/wu-semantic-ownership-01-r11-i2-validation-plan-drift-controller-adjudication.md`；
- `docs/host/issues-implementation-control.md` 的完整 `## 当前状态`。

Corrected adjudication 为 `63` lines / `4,585` bytes / SHA-256
`f77412837d5222420f36459dad9069f870f909651383f70d0e21d23edcc94c69`。实时 gate 仍为
`R11-I2 validation plan-drift fix for root README public-contract test ownership`，implementation 继续暂停。

本 turn authored paths 精确为：

1. `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`
2. `docs/reviews/wu-semantic-ownership-01-r11-i2-validation-plan-drift-fix-codex.md`

## 4. Before / after plan diff

| Plan owner | Before | After | Finding closure |
|---|---|---|---|
| §4 slice allocation | `tests/cli/test_arg_parsing.py` 只列在 I1；I2 泛指 §7 paths | cumulative unique path count 固定为 `22`；I1 固定 `8` paths；I2 从 `14` 修正为 `15` paths；唯一共享 path 只开放 `test_root_readme_matches_current_cli_public_contract` | 关闭 slice allocation omission，不重开其它 parser tests |
| §4 protected I1 | I2 authorization 把整个 `test_arg_parsing.py` hash视为不可变 | mutation 前仍必须匹配 protected before-lock `7cdc4c1d...ece6`；mutation 后只有指定函数可产生 I2 delta，另七个 I1 paths与同文件其它 nodes不变 | 区分 before-lock 与 post-mutation node exception |
| §7.1 exact allowlist | 14 paths：packaging/CI、六个 deletion、public packaging test、四个 README | 15 paths：原 14 paths 加共享 `tests/cli/test_arg_parsing.py`，严格限一个函数 | 精确授权 owner test，不扩大 production/README/workflow scope |
| §7.1 test contract | 计划只要求 README 删除 JSON，未分配 stale test correction | 明确删除旧全局 `--infer` 禁止、`"schema_version": 1` / `"commands"` 必须存在和“不生成 shell”必须存在 assertions；改为 current 正/负 contract | 关闭三组相反旧 contract |
| §7.2 workflow count | 文字列 cumulative allowlist，但未与 I2 path count区分 | 明确 workflow trigger 是 `22` 个 cumulative unique paths；I2 是 `15` paths；共享 test 已计入五个 cumulative test files且不重复计数 | 消除 22/15/shared-path 计数歧义 |
| §7.3 checkpoint | packaging focused command已包含整个 test file，但未说明该函数的 I2 ownership | 要求先匹配 before-lock、只改指定函数、记录 15-path allowlist并做 node-level diff review | 让 checkpoint 可执行且 fail closed |
| §8 validation/scans | final cumulative validation包含 test file与 README关键词 scan，但未明确 node exception | 增加 exact 15-path、current positive/negative contract、protected-I1 nodes验证；scan 纳入 test file并要求 owner review，不允许裸关键词冒充通过 | 同步 validation truth，不放宽完整 gates |
| §9.1 state machine | I2 仅写 packaging/README/Windows，所有 I1 hashes笼统 protected | I2 state 明确 15 paths、唯一共享 node；mutation 前八个 I1 locks全匹配，之后七个非共享 paths hash不变且共享文件只改该 node | 不创建第三 slice/checkpoint/commit |
| §10 checklist | 无 plan-drift closure项 | 增加 22/8/15 count、single-node allocation与新 README test contract验收项 | 为双路完整 review提供明确 oracle |

## 5. 修正后的 root README owner-test contract

后续只有在本 plan fix 完成 Controller validation、双路 complete plan review、必要 fix/re-review、accepted plan
commit 与新 implementation authorization 后，才可修改该 test node。本轮没有执行以下 implementation。

后续 exact node 必须：

- 从旧 `removed_contract` 全局禁止集合中移除 `--infer`；
- 删除旧正向 assertions：`'"schema_version": 1' in readme`、`'"commands"' in readme`、
  `"不生成 shell" in readme`；
- 正向断言 `upload_filings_from` batch contract 包含 `--infer` 与 `FMP_API_KEY`；
- 正向断言 POSIX `.sh`、Windows `.cmd` 及 `/bin/sh`、`cmd.exe /d /c` executable usage；
- 负向断言 direct upload 未获得 `--infer`，旧 JSON argv `schema_version=1` / `commands` 公共协议和
  “不生成 shell”文案不存在；
- 保留原 test 对其它已删除/未实现 CLI contract 的负向断言；
- 不修改同文件其它 parser/help tests，不重算 parser、README 或 renderer 语义。

## 6. Protected stopped-tree locks

Controller correction 已废弃错误的 `c1bf52df...e858` lock；本 artifact 不再引用或追逐它。唯一稳定 tracked
product/test/README/packaging diff lock 使用 Controller 指定 exact command：

```bash
git diff --binary HEAD -- README.md dayu tests pyproject.toml requirements.txt .github
```

| Lock | Before fix | After plan fix | 结果 |
|---|---|---|---|
| HEAD | `a527ec030215e5bfcf9c4fad2f4a6fda243f5d65` | `a527ec030215e5bfcf9c4fad2f4a6fda243f5d65` | unchanged |
| accepted plan | `55d35256f0f89f39f722438dc19d9ae65269b16810f96f1cd0129c6eba06d427` | `20f35e55573321ddfa474f772742097bb55963165936195de73785c39bc031dd` | authorized plan-only delta |
| plan size | `889` lines / `75,526` bytes | `925` lines / `79,384` bytes | authorized |
| stopped tracked product diff | `718846cdd5ce3ad8d9d789b3b7b47e18df8943ac541f63a925dd696b06fe8332` | `718846cdd5ce3ad8d9d789b3b7b47e18df8943ac541f63a925dd696b06fe8332` | unchanged |
| stopped `tests/cli/test_arg_parsing.py` | `7cdc4c1d014bc7012aca28f05927b8afbbd04b86cc6d0aa2dfbf5f87af91ece6` | same | unchanged |
| untracked renderer | `dfe0508deb905ef9bc21204a75a8ec55abf87ec254517831556dc7a8ba7aea65` | same | unchanged |
| untracked Windows workflow | `4026da55c789c0f3f961887f3f19536c7817abad4665ffd78b493219f2560953` | same | unchanged |
| corrected adjudication | `f77412837d5222420f36459dad9069f870f909651383f70d0e21d23edcc94c69` | same | read-only / unchanged |
| staged set | empty | empty | unchanged |

Stopped I2 path changes、六个 tracked deletions、四个 README、全部 I1 implementation、renderer、workflow 与
Controller artifacts未被本 turn 修改。Controller control 的当前 SHA-256 为
`c1fdb39f24d315ee984d9a96bd0c960977bbf7c7367210d7714f0edb43e1e694`，只作 read-only current-state
复核；它有意不属于稳定 stopped product diff lock。

## 7. Validation 与 docs decision

- accepted plan 完整读取：PASS（before-fix 889/889 lines）。
- corrected adjudication 完整重读：PASS（63/63 lines，size/hash均匹配 Controller correction）。
- 总控 `## 当前状态` 完整读取：PASS；correction 后相关 gate/next-entry/R11-I2 rows已重读。
- `git diff --check -- docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`：PASS。
- plan contract/path-count/protected wording scan：PASS；§4、§7.1、§7.2、§7.3、§8、§9.1、§10均有明确命中。
- stopped tracked product diff exact command：PASS，`718846cd...8332`。
- test/renderer/workflow/adjudication hashes：PASS。
- `git diff --cached --name-only`：空。
- authored path count：`2`。
- tests / coverage / pyright / Ruff / wheel / Windows workflow：未运行；Controller plan-only authorization明确禁止继续
  implementation/test，本轮也没有代码变更需要执行这些 gate。
- README decision：不更新。当前只修 accepted plan 与 review artifact，没有改变已经 stopped 的用户可见 contract、
  测试实现、分层、装配或最终用户工作流。

## 8. Finding 与 residual risk

| ID | Gate status | 当前状态 |
|---|---|---|
| `R11-I2-VAL-PD-F01` | plan fix | `FIXED_IN_PLAN / PENDING_DUAL_COMPLETE_PLAN_DRIFT_REVIEW` |

- blocking open question：`0`。
- unclassified residual risk：`0`。
- Windows real-run release blocker：保持原 accepted plan 状态，本轮既未关闭也未改变。
- stopped focused `1 failed, 152 passed, 2 skipped`：保持历史 validation evidence；本轮未重跑、未冒充 green。
- next entry point：Controller validation 与双路 complete plan-drift review；在 plan acceptance 和新的 exact implementation
  authorization 前，R11-I2 implementation 继续暂停。

READY_FOR_DUAL_COMPLETE_PLAN_DRIFT_REVIEW
