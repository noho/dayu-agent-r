# WU-SEMANTIC-OWNERSHIP-01 R08 Test-Only Code-Review Fix Controller Authorization

## 1. Gate

Final corrected plan 已由双路完整 re-review 与 Controller adjudication 接受；accepted local plan commit 为 `0dc85654bb29612a547e7976f3eeb4801171f786`。本次授权仍是既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` / R08 的 cumulative code-review fix continuation，不是新 WU、feature、issue 或独立 sub-WU。

## 2. Re-entry lock

AgentCodex 开始任何测试修改前必须独立匹配：

| 项 | expected |
|---|---|
| branch | `phaseflow/host-issues-control` |
| accepted plan commit | `0dc85654bb29612a547e7976f3eeb4801171f786` |
| final plan SHA-256 | `a79268ea8d45f6af8854859269ce3592506f753272c32ecffab76d765cad7a02` |
| protected `git diff --binary -- dayu/fins tests` SHA-256 | `7a7ebf939b758ce8fdd92413210743e5a90b65272df62e466bf70332eb771d6d` |
| `tests/fins/test_fins_read_runtime.py` SHA-256 | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` |
| guards correction-entry SHA-256 | `4a076ca6c6efb5df986104833d9816e5bdfdda53ac0c292081a9be49223bc1ff` |
| staged paths | empty |

任一不匹配立即停止回 Controller，不得重建、恢复或猜测 drift。

## 3. Exact implementation authorization

- 唯一可新增产品/测试 delta：既有 allowlisted `tests/fins/test_read_runtime_semantic_ownership_guards.py`。
- 只能按 final plan §6.1 candidate 1→5 的顺序形成连续最短前缀，一次实现一个 exact node。
- 每个 node 必须是单一 stable owner family，使用计划指定 public seam；只有 candidate 5 可直接使用唯一 module helper。
- candidate 2/3 的 unknown ref path 必须由 typed fixture 产生 `KeyError`，通过 public runtime 观察精确 `FinsReadArgumentError`，不得直接断言 fixture。
- 每个 node 后执行同一完整 incremental coverage set，记录 `covered/statements/percent/decision`；`read_runtime_helpers.py` 首次 whole-file exact-key `>=80.00%` 立即停止，不实现后续候选。
- 五项全部完成仍低于 80% 时停止回 Controller；不得扩 path/production allowlist、恢复/搬运原四节点、加入 compatibility/private/fake/empty/skip/xfail/pragma/omit padding。

## 4. Required closeout before code re-review

达到首次阈值后，AgentCodex 必须清空 coverage 并从零完成 final plan §6.6/§6.7：受影响/focused/aggregate/full Fins tests、15-file exact-key whole-file coverage、full pyright zero、changed Python scoped Ruff zero、`git diff --check`、README trigger check、source/propagation/security/no-touch/correction scans、AAPL/HTML/no-statement 与 Host forced-truncation chain。

Implementation artifact 必须记录：逐步 ledger、最终新增节点的连续最短前缀、未实现候选、完整命令/结果、final changed-path manifest、每个 changed path SHA-256、final cumulative binary diff SHA-256、staged empty 与所有 stop/no-drift 证明。

完成前不得派发 code re-review；完成后也不得 commit product/test tree，必须先由 Controller 验证并锁定新 immutable cumulative tree，再进入 AgentMiMo/AgentDS 双路完整 code re-review。

## 5. Still unauthorized

其它 product/test/README path、S1/S2 historical artifact 修改、R09-R12、Issues 142/151/175/177/178、统一 tool authorization、Host/Engine/Service/UI、push 与 PR 均未授权。
