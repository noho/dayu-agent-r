# WU-SEMANTIC-OWNERSHIP-01 R05-S1 Validation Plan Correction — AgentMiMo Final Re-Review

## 1. Review 身份与 verdict

- reviewer：AgentMiMo（第一路完整 final re-review）。
- 这不是新 WU、feature、issue，也不是重新打开独立 sub-WU。
- review 范围：修订后的 R05 plan **全文**、当前七路径 S1 产品/test/design diff、implementation artifact，以及从 plan-drift Controller adjudication 到 zero-change fix Controller validation 的完整 correction/review evidence chain。
- review timestamp：`20260715-231500`。
- 唯一 write allowlist：`docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-rereview-mimo.md`（本 artifact）。

**verdict：PASS / zero material finding。**

本 re-review 完整覆盖：修订后 plan 全文（§0-§15）、plan-drift Controller adjudication（`R05-S1-VAL-PD-F01`）、AgentCodex correction artifact、Controller validation（PASS）、初次 MiMo review（F01-F13 全部 CHALLENGE_PASS）、初次 DS review（ZERO MATERIAL FINDINGS）、Controller review adjudication（PASS_WITH_ZERO_ACCEPTED_FINDING）、AgentCodex zero-change fix record、Controller zero-change fix validation（PASS），以及当前七路径 S1 diff 与 implementation artifact。

## 2. Finding ledger

**Zero material findings.**

经完整 re-review，所有维度均未发现 material defect：

| # | 复核维度 | 结论 | 证据 |
|---|---------|------|------|
| F01 | 初次 MiMo review 的 zero finding 是否仍成立 | **成立** | MiMo F01-F13 全部为 challenge-pass 标签，不是 defect；Controller 已裁决不把正向验证标签转换成 findings |
| F02 | zero-change gate 是否确实没有遗漏 accepted finding 或内容漂移 | **无遗漏无漂移** | zero-change fix 只新增一个 artifact；七路径 digest `3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2` 前后一致；worktree status 16→17 只增 zero-change artifact；staged paths 为零 |
| F03 | 排除 `test_dispatch_scheduler.py` 是否隐藏 R05 regression | **不隐藏** | 该文件对 R05 owner symbol 全集 source scan 为零命中；scheduler source files 相对 R05 plan base 无 diff；确定性 probe 独立证明 root cause 是 scheduler close gate 与 terminal promotion 线性化缺口 |
| F04 | §7 functional matrices 是否被 coverage measurement 替代 | **未替代** | plan diff 无 §7 hunk；§8 明确声明"本节 session 只测量 R05 两个实际 changed production owner 的覆盖率，不是完整 Host regression acceptance，也不能替代、删减或放宽 §7.1 的任何功能节点" |
| F05 | measurement 整体绿色与逐文件 ≥80% 是否可执行且不被 aggregate 掩盖 | **可执行且不被掩盖** | Controller 独立候选 session：`1830 passed, 2 skipped, 5 deselected`；`durable/state.py=83%`、`wait_adapter.py=86%`；两个 `coverage report --fail-under=80` 均通过 |
| F06 | scheduler root cause 是否被错误标为 flake/inherited/已修复 | **未被错误标记** | plan §12 完整记录六元组、失败 session、确定性 probe 五步事件顺序、同源 root cause 与明确 disposition："这不是 flake、不是 inherited pass、不是已修复问题" |
| F07 | residual owner/destination 是否足够 | **足够** | plan §15 登记为"Host scheduler close / terminal promotion coordination"；"当前 umbrella 不修复、不创建 issue、不归入 Issue 175；后续 destination 只能由 Controller / 用户另行裁决" |
| F08 | gate、stop conditions、baseline registry、completion handoff 是否自洽 | **自洽** | §13 共 12 条 stop conditions 完备；§12 baseline registry 包含完整六元组与 disposition；§14 completion handoff 与 control doc 和 Controller artifacts 一致 |
| F09 | S1 diff 是否只实现 non-terminal release/backoff | **是** | `wait_adapter.py`：poll timeout → `_release_with_backoff(ADAPTER_ERROR/wait_observation_timeout)`，保持 WAITING；abandon timeout → `_release_with_backoff(ABANDON_ERROR/wait_abandon_timeout)`，保持 CANCELLED，不写 `poll_abandoned_at`；删除 `_MarkWaitRecordAbandonTimeoutOperation` 与 import。`durable/state.py`：删除 `mark_wait_record_poll_abandon_timeout(...)` 定义与 unused `TERMINAL_RUN_STATUS_VALUES` import |
| F10 | 是否保留 late-publication fence、claim CAS、capacity、shared close deadline、authoritative typed lost、explicit lifecycle terminal | **全部保留** | `_wait_observation.py`、`waiting.py` 无 diff；authoritative lost test 保留并增加 idempotency key + error_code 断言（强化）；explicit terminal parameterized tests 保留；capacity / close deadline tests 保留 |
| F11 | R04 config ownership 是否保留 | **保留** | 12-field policy、typed modes、provider config 均无 diff；plan §1.2 完整列出；§13 stop condition 8 禁止 R04 变化 |
| F12 | 是否偷带 scheduler fix、Issue 175、callback、统一 authorization、R05-S2 或 R06+ | **未偷带** | deferred scope scan 零命中；scheduler source/test 无 diff；plan §1.3 明确非目标清单；§6 closed allowlist 精确 |
| F13 | 受保护七路径 digest 是否一致 | **一致** | 独立运行 `git diff --binary -- <7 paths> | shasum -a 256`，结果 `3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2` |
| F14 | `git diff --check` 是否通过 | **通过** | 无 whitespace error |
| F15 | invalid timeout symbol 是否零定义零调用 | **零** | `rg 'mark_wait_record_poll_abandon_timeout|_MarkWaitRecordAbandonTimeoutOperation' dayu tests` exit 1（零命中） |

## 3. 旧 findings closure 复核

| 旧 Finding | 最终状态 | MiMo re-review |
|---|---|---|
| `R05-PF-01` cancelled abandon 长期 capped retry residual | CLOSED | plan §2.1/§4/§15 保持同源；不发明 terminal evidence。**保持关闭** |
| `R05-PF-02` smoke timing 可执行性 | CLOSED | event/condition/state-poll、monotonic deadline、named margins 完整。**保持关闭** |
| `R05-PF-03` Host design close marker 真源纠错 | CLOSED | S1 精确 writeback，保留 explicit lifecycle terminal。**保持关闭** |
| `R05-PF-04` invalid timeout-only durable primitive | CLOSED | storage owner deletion + owner test + zero-symbol scan 完整。**保持关闭** |
| `R05-PRR-F01` touched-file Ruff registry | CLOSED | 两条 F401 已在 changed files 清除。**保持关闭** |
| `R05-S1-VAL-CV-F01` 三处 stale gate 文本 | CLOSED | AgentCodex follow-up 已精确修复；stale 字符串扫描零命中。**保持关闭** |
| `R05-S1-VAL-PD-F01` coverage gate 与 scheduler owner 耦合 | CLOSED via correction | plan §8/§12-§15 已完整反映；correction 通过双路 review + zero-change fix + re-review。**保持关闭** |

所有旧 findings 保持关闭。本次 re-review 不重新打开任何已关闭 finding。

## 4. 独立验证结果

| 验证项 | 命令 | 结果 |
|--------|------|------|
| 受保护七路径 digest | `git diff --binary -- <7 paths> | shasum -a 256` | `3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2` |
| `git diff --check` | `git diff --check HEAD` | PASS |
| invalid timeout symbol scan | `rg 'mark_wait_record_poll_abandon_timeout\|_MarkWaitRecordAbandonTimeoutOperation' dayu tests` | 零命中（exit 1） |
| scheduler test R05 symbol scan | `rg -c <R05 symbols> test_dispatch_scheduler.py` | 零命中（exit 1） |
| deferred scope scan | `git diff --unified=0 HEAD -- dayu | rg <deferred keywords>` | 零命中（exit 1） |
| plan §7 hunk check | `git diff HEAD -- plan.md | grep §7` | 无 §7 功能矩阵 hunk（只有引用 §7 的文本） |
| worktree status | `git status --short` | 预期 18 条（9 modified + 9 untracked） |

## 5. Retained safety

修订后的 plan 与 S1 diff 完整保留：

- late-publication token/generation fence（`_wait_observation.py` 无 diff）
- claim CAS、release/backoff 唯一真源（`_release_with_backoff` 唯一调用点）
- outstanding capacity 与 shared close deadline
- authoritative typed `WaitPollLost` 经 common resolver terminalize（test 保留并强化）
- explicit applied / unsupported / noop lifecycle 写 terminal `poll_abandoned_at`（parameterized tests 保留）
- invalid timeout-only symbol production/tests 零定义零调用
- R04 config ownership：12 字段 policy、三个 typed modes、provider config owner
- `durable/schema.py` 无 diff；`poll_abandoned_at` 继续只承载 explicit lifecycle terminal
- Engine `agent.py` no-diff regression 固化

## 6. Residual owners 与 deferred scope

与原 accepted plan 和 correction 一致：

| residual | owner boundary | 当前 disposition |
|---|---|---|
| scheduler close / terminal promotion coordination 线性化缺口 | `HostDispatchScheduler.close()` / `EngineEventIngestor._with_terminal_promotion_retry(...)` | 未修复、未 waiver、未创建 issue、未归入 Issue 175；后续只能由 Controller / 用户另行裁决 |
| CANCELLED abandon 长期 capped retry | future Host cancel/abandon durable evidence policy | R05 不创造 terminal evidence；保留为 future owner residual |
| Issue 175 process isolation / process-backed containment | Issue 175 | 不由 R05 实现 |
| callback transport / authenticated callback ingress | 后续对应 WU/issue | R05 只保留 typed mode 与 fail-closed composition |
| unified authorization/permission schema、R06+ | 后续 WU | 不进入本 slice |
| future Host LOST durable evidence policy | future Host policy | R05 不预留 heuristic branch |

## 7. Evidence chain 完整性

本 re-review 覆盖的完整 evidence chain：

| # | artifact | 路径 |
|---|---------|------|
| 1 | plan-drift Controller adjudication | `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-drift-controller-adjudication.md` |
| 2 | AgentCodex correction artifact | `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-codex.md` |
| 3 | Controller validation | `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-controller-validation.md` |
| 4 | 初次 MiMo review | `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-review-mimo.md` |
| 5 | 初次 DS review | `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-review-ds.md` |
| 6 | Controller review adjudication | `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-review-controller-adjudication.md` |
| 7 | AgentCodex zero-change fix | `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-review-fix-codex.md` |
| 8 | Controller zero-change fix validation | `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-review-fix-controller-validation.md` |
| 9 | Implementation artifact | `docs/reviews/wu-semantic-ownership-01-r05-s1-implementation-codex.md` |
| 10 | 修订后 R05 plan 全文 | `docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md` |
| 11 | 当前七路径 S1 diff | `git diff HEAD` over seven protected paths |
| 12 | Control doc R05 状态 | `docs/host/issues-implementation-control.md` |
| 13 | phaseflow umbrella control | `docs/phaseflow-umbrella-optimization-control.md` |

## 8. 修正建议

无。本次 correction 的修订内容正确、完整、可执行。

## 9. 是否允许 accepted plan-correction commit

**允许。** 本次 re-review 确认：

1. 两路初次 review 均 PASS / zero material finding；
2. zero-change fix 正确持久化了 zero-change disposition；
3. 修订后的 plan 在 scheduler exclusion、§7 functional matrices、per-file coverage、root cause separation、stop conditions、current gate、completion handoff 等所有维度均完整可执行；
4. S1 semantics、protected digest、retained safety 与 deferred scope 未漂移；
5. scheduler residual 仍未修/未 waive/未建 issue/未归 Issue 175；
6. 七路径 protected digest 始终为 `3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2`。

Controller 可在完成 final adjudication 后创建 exact-scope accepted plan-correction commit，随后恢复 R05-S1 validation。

## 10. 与 AgentDS re-review 的独立性声明

本 re-review 在未读取 AgentDS re-review artifact（如存在）的情况下独立完成。所有证据来自：
- 修订后 plan 全文的直接读取
- 完整 correction/review evidence chain 的逐层复核
- 独立运行的 `git diff`、`shasum`、`rg` source scans
- 当前七路径 S1 diff 的直接核对

两路 reviewer 的 verdict 不独立授权 commit 或恢复 S1 validation；Controller 仍须完成 final adjudication。

## 11. 下一动作

Controller final adjudication。通过后创建 exact-scope accepted plan-correction commit，随后恢复 R05-S1 validation。

R05-S1 validation、R05-S2、scheduler 产品修复、code review、accepted product commit、aggregate gate、Issue 175、callback transport、统一 authorization、R06-R12、push 与 PR 均未授权。
