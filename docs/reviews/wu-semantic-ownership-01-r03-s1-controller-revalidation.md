# WU-SEMANTIC-OWNERSHIP-01 / R03-S1 Controller Re-validation

## 1. Final verdict

- Prior validation：`docs/reviews/wu-semantic-ownership-01-r03-s1-controller-validation.md`。
- Accepted finding：`R03-S1-CV-F01`。
- Agent fix evidence：更新后的
  `docs/reviews/wu-semantic-ownership-01-r03-s1-implementation-codex.md` 与当前未提交 test diff。
- Controller verdict：**PASS / READY_FOR_DUAL_CODE_REVIEW**。

本裁决仍属于既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的同一 R03-S1，不创建新 WU、新 slice，
也不授权 accepted commit、S2/S3 或 aggregate。

## 2. Finding closure

`R03-S1-CV-F01` 已关闭。AgentCodex 只在
`tests/host/test_resolve_wait_command.py` 新增两个 direct durable owner case：

1. resume transition 的目标 Run 不存在时返回 `NOT_FOUND`；
2. terminal transition 的 WaitRecord 不存在时返回 `NOT_FOUND`。

两例都使用真实 SQLite durable store、production `EventLogStore`、完整 typed transition input 和
五张表的稳定快照；均断言所有返回 event/dispatch 字段为空且 EventLog、Run、Attempt、WaitRecord、
dispatch record 完全不变。测试覆盖 shared waiting-resolution 写前 precondition 的真实 NOT_FOUND
语义，不是 coverage-only assertion，也没有 production/test seam、mock policy、pragma 或阈值调整。

Controller 独立重跑 accepted plan §6.5 精确命令，得到：

- `77 passed`；
- `run_transition.py: 1375 statements / 281 missing / 80%`；
- finding 前基线为 `75 passed / 283 missing / 79%`。

因此 accepted `>=80%` owner-suite gate 已按原计划闭合。

## 3. Independent re-validation

| 验证 | Controller 结果 |
|---|---|
| exact transition owner suite coverage | `77 passed`，`run_transition.py 80%` |
| corrected 9-file matrix | `389 passed` |
| full Host | `1952 passed, 2 skipped, 5 deselected` |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| ruff changed owner test | PASS |
| `git diff --check` | PASS |

Agent 的完整 8-file coverage 原样重跑结果为 `1936 passed, 2 skipped, 21 deselected`，八个 production
文件均达标（`86%`–`98%`）。首轮 coverage 插桩下曾观察到一个无本 slice diff 的 dispatch close
时序失败；同一用例在无插桩 full Host 与原命令重跑均通过，期间无代码改动。Controller 此前已
独立取得同一 8-file coverage 的绿色结果，故该未复现观察不构成产品 finding。

## 4. Scope and retained contracts

- fix 只修改 owner test 与 implementation artifact；production、README、accepted plan、Controller
  validation/control 和 MiMo/DS artifacts 未被 Agent 修改。
- resume/terminal execution mismatch 的 `INVALID_STATE` + 五表 no-mutation、public
  completed/failed/lost source identity、governance-only `TOOL_AWAITING`、descriptor 冷热互斥、
  strict request/result execution equality 与四 consumer no-publication 全部保留。
- 未进入 S2 source/blacklist、S3 opaque provenance、Issue 177/178 或统一 authorization framework。

## 5. Next gate

下一 gate 是 AgentMiMo / AgentDS 对 `6e11d916..working tree` 的完整 R03-S1 implementation diff
并发 code review。review 必须覆盖 production、tests、README、implementation/Controller artifacts
及 plan-correction closure；任一路 accepted finding 都必须交 AgentCodex 修复并双路 re-review，
通过前不得创建 accepted local commit。
