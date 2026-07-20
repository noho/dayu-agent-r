# WU-SEMANTIC-OWNERSHIP-01 R05-S1 Validation Plan Correction — AgentDS 第二路独立完整 Final Re-Review

## 1. Review 身份与 scope

- reviewer：AgentDS（第二路独立完整 final re-review）。
- 这不是新 WU、feature、issue，也不是重新打开独立 sub-WU。
- 本轮 re-review 覆盖：
  - 修订后的 R05 plan 全文：`docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md`
  - 当前七路径 S1 product/test/design diff 全文
  - 完整 correction/review evidence chain（9 个 artifacts，从 plan-drift Controller adjudication 到 zero-change fix Controller validation）
  - 初次 DS review：`docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-review-ds.md`
  - 初次 MiMo review：`docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-review-mimo.md`
  - Controller review adjudication：`docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-review-controller-adjudication.md`
  - AgentCodex zero-change fix：`docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-review-fix-codex.md`
  - Controller fix validation：`docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-review-fix-controller-validation.md`
  - 独立 source/digest/status/scan 验证（本轮全新执行）
- review timestamp：`20260715`。
- 唯一 write allowlist：`docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-rereview-ds.md`（本 artifact）。

## 2. 独立验证结果

本轮全部独立重新执行，未依赖任何既有 artifact 的缓存结论。

### 2.1 Protected seven-path digest

```text
git diff --binary -- \
  dayu/host/durable/state.py \
  dayu/host/wait_adapter.py \
  docs/host/design.md \
  tests/host/test_phase7_waiting_integration.py \
  tests/host/test_wait_adapter_polling.py \
  tests/host/test_wait_observation_runner.py \
  tests/host/test_wait_record_state.py \
  | shasum -a 256
```

结果：`3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2`

与 correction 前、correction 后、初次 DS review、MiMo review、zero-change fix 前后全部一致。**PASS / 无漂移。**

### 2.2 Invalid timeout-only symbol scan

```text
rg -n 'mark_wait_record_poll_abandon_timeout|_MarkWaitRecordAbandonTimeoutOperation' dayu tests
```

结果：零命中（rg exit 1）。production 与 tests 中均无定义、无调用、无 deprecated wrapper、无 compat re-export、无 dead helper 残留。**PASS。**

### 2.3 Scheduler test R05 owner symbol source scan

```text
rg -c 'wait_adapter|WaitPoller|WaitObservation|WaitRecord|mark_wait_record_poll_abandon_timeout|_MarkWaitRecordAbandonTimeoutOperation|release_wait_record_poll_claim|wait_observation_timeout|wait_abandon_timeout' tests/host/test_dispatch_scheduler.py
```

结果：零命中。`test_dispatch_scheduler.py` 与 R05 wait observation owner symbol 无任何 source/propagation 交集。**PASS。**

### 2.4 Scheduler/Engine/Waiting/Observation/Schema no-diff 确认

```text
git diff --name-only -- \
  dayu/host/dispatch.py \
  dayu/host/engine_ingest.py \
  dayu/host/_execution_health.py \
  tests/host/test_dispatch_scheduler.py \
  dayu/engine/agent.py \
  dayu/host/waiting.py \
  dayu/host/_wait_observation.py \
  dayu/host/durable/schema.py
```

结果：零输出（所有文件均无 diff）。**PASS。**

### 2.5 Deferred scope scan

```text
git diff --unified=0 -- dayu | rg -n 'authorization|permission|callback.transport|process.isolation|process_backed|subprocess|Issue.175'
```

结果：零命中（rg exit 1）。**PASS。**

### 2.6 Whitespace check

```text
git diff --check
```

结果：PASS（exit 0，无输出）。**PASS。**

### 2.7 Worktree status 一致性

当前 worktree status（`git status --porcelain=v1 --untracked-files=all`）：

- 9 个 modified (M) 文件：七个 protected S1 路径 + `issues-implementation-control.md` + plan
- 9 个 untracked (??) 文件（全部在 `docs/reviews/` 下）

与 zero-change fix artifact §4.2 的期望一致（fix artifact 创建后 17 条 → Controller fix validation artifact 新增后 18 条）。staged path 为零。**PASS / 无意外漂移。**

### 2.8 Stale gate text scan

```text
rg -n 'second.plan.fix|second-plan-fix|R05 remediation second plan fix|WAITING_FOR_CONTROLLER_VALIDATION_AFTER_SECOND_PLAN_FIX' <plan>
```

结果：零命中（rg exit 1）。Controller follow-up `R05-S1-VAL-CV-F01` 的三处 stale gate 文本修复确认生效。**PASS。**

## 3. 初次 review findings 复核

### 3.1 DS 初次 review：ZERO MATERIAL FINDINGS — 仍成立

DS 初次 review 的 10 项 assumptions (A1–A10) 本轮全部独立重新验证：

| # | Assumption | 本轮重验结果 |
|---|-----------|------------|
| A1 | scheduler 失败与 R05 无 source/propagation 交集 | ✅ 独立 source scan 零命中 |
| A2 | `test_toolruntime_executor.py` 无 R05 交集 | ✅ 确认，且该文件有既有独立排除 |
| A3 | scheduler 失败是独立 lifecycle owner 缺口 | ✅ 确定性 probe 独立证明 |
| A4 | S1 diff 精确为 non-terminal release/backoff | ✅ 逐文件 diff 全文核对 |
| A5 | invalid timeout symbol 已彻底删除 | ✅ 独立 scan 零命中 |
| A6 | 七路径 protected digest 未漂移 | ✅ `3439b542...` 一致 |
| A7 | §7 功能矩阵未被替代或删减 | ✅ plan diff 无 §7 hunk |
| A8 | 未偷带 scheduler fix/Issue 175/callback/authorization/R05-S2/R06+ | ✅ deferred scope scan 零命中 |
| A9 | 保留全部 safety mechanisms | ✅ no-diff 文件 + retained test nodes 确认 |
| A10 | R04 config ownership 未修改 | ✅ 12-field policy + typed modes 无 diff |

全部 10 项 assumptions 仍成立。**DS 初次 ZERO MATERIAL FINDINGS 保持有效。**

### 3.2 MiMo F01–F13：仍为 challenge pass，非 defect

| MiMo 标签 | challenge 内容 | 本轮重验 |
|-----------|---------------|---------|
| F01 | 排除 `test_dispatch_scheduler.py` 不隐藏 R05 regression | ✅ 独立 source scan 零 R05 命中 |
| F02 | 排除不构成一般失败豁免 | ✅ plan §8 只允许两个 `--ignore`，§13 stop condition 12 禁止第三个豁免 |
| F03 | §7 未被 coverage 替代 | ✅ plan diff 无 §7 hunk；§8 明确声明"不是完整 Host regression acceptance" |
| F04 | measurement 可执行且不被 aggregate 掩盖 | ✅ 两个独立 `--fail-under=80`；Controller 候选 session 已验证 |
| F05 | scheduler root cause 未被误标 | ✅ plan §12 明确："不是 flake、不是 inherited pass、不是已修复" |
| F06 | residual owner/destination 足够 | ✅ plan §15 登记 owner boundary + "只能由 Controller/用户另行裁决" |
| F07 | gate/stop conditions/baseline/handoff 自洽 | ✅ §13 12 条 stop conditions；§12 完整六元组；§14 completion handoff |
| F08 | S1 diff 只实现 non-terminal release/backoff | ✅ 逐文件 diff 全文核对 |
| F09 | retained safety 全部保留 | ✅ no-diff 文件确认 + retained test nodes |
| F10 | R04 config ownership 保留 | ✅ 12-field policy + typed modes 无 diff |
| F11 | 未偷带 deferred scope | ✅ deferred scope scan 零命中 |
| F12 | protected digest 一致 | ✅ `3439b542...` |
| F13 | `git diff --check` 通过 | ✅ exit 0 |

**全部 13 项仍为 challenge pass，不是 defect。不得转换为 finding。**

### 3.3 Controller adjudication final ledger — 仍成立

Controller 裁决的 final ledger：

| 分类 | 数量 | 本轮重验 |
|---|---|---:|---|
| accepted current finding | 0 | ✅ 仍为零 |
| rejected finding | 0 | ✅ 仍为零 |
| observation / retained residual | 4 | ✅ 均有 owner/disposition |
| blocker | 0 | ✅ 仍为零 |

四个 retained residual 本轮复核：

1. **scheduler close/terminal promotion coordination**：仍定位到 `HostDispatchScheduler.close()` / `EngineEventIngestor._with_terminal_promotion_retry`；未修复、未 waive、未建 issue、未归 Issue 175；plan §12/§15 完整登记。✅
2. **cancelled abandon capped retry**：仍归 future Host durable evidence policy；plan §15 明确记录。✅
3. **plan §0 历史 transition 状态**：plan artifact 不承担 live gate tracker 职责；control doc 正确反映当前 gate。非 material finding。✅
4. **R05-S2 未执行**：在本 correction 范围内正确 deferred；S1 completion 不依赖 S2。✅

**Controller final ledger 仍成立。无新 finding 需要加入。**

## 4. Zero-change gate 完整性审计

### 4.1 Zero-change fix artifact 内容复核

AgentCodex zero-change fix artifact（`...review-fix-codex.md`）正确记录了：

- accepted/rejected/blocker 均为 `0 / 0 / 0`
- MiMo F01–F13 全部 disposition 为 `CHALLENGE_PASS / NOT_A_DEFECT / NO_FIX`
- DS 与 Controller 均为零 material finding
- MiMo coverage harness mistake 已在 review 内纠正，不是产品/计划 finding
- protected seven-path digest 创建前后均为 `3439b542...`
- worktree status 创建前 16 条 → 创建后 17 条（只增加 fix artifact）
- 没有修改 plan、产品、测试、设计、control 或既有 artifacts

### 4.2 是否遗漏 accepted finding

逐项核对：

- Controller review adjudication 明确 accepted finding = 0
- MiMo F01–F13 全部判定为 `CHALLENGE_PASS / NOT_A_DEFECT`
- DS 明确 ZERO MATERIAL FINDINGS
- 历史 findings（R05-PF-01..04、R05-PRR-F01、R05-S1-VAL-CV-F01）保持关闭

**确认：无遗漏 accepted finding。**

### 4.3 是否发生内容漂移

- protected seven-path digest：`3439b542...` 全程不变 ✅
- worktree status：与 zero-change fix 记录的期望一致（+Controller fix validation artifact） ✅
- staged paths：零 ✅
- plan/product/test/design/control/既有 artifacts：zero-change gate 内未修改 ✅

**确认：无内容漂移。**

### 4.4 Controller fix validation 复核

Controller fix validation（`...review-fix-controller-validation.md`）独立验证了：

- seven-path digest 一致
- worktree status 一致
- staged path 为零
- `git diff --check` PASS
- plan/product/tests/design/control 无漂移
- scheduler residual 未修/未 waive/未建 issue/未归 Issue 175
- MiMo harness mistake 已纠正

**Controller fix validation 的 verdict `PASS / READY_FOR_DUAL_COMPLETE_PLAN_CORRECTION_RE_REVIEW` 经独立复核成立。**

## 5. S1 semantics 与 retained safety 逐项复核

### 5.1 wait_adapter.py diff

- poll timeout：删除 `WaitPollLost(ResolveWaitLostOutcome(...))` + `_resolve_claimed_wait` → `_release_with_backoff(ADAPTER_ERROR/wait_observation_timeout)` ✅
- abandon timeout：删除 `_MarkWaitRecordAbandonTimeoutOperation` → `_release_with_backoff(ABANDON_ERROR/wait_abandon_timeout)` ✅
- 删除 `mark_wait_record_poll_abandon_timeout` import ✅
- 删除 `_MarkWaitRecordAbandonTimeoutOperation` 完整 dataclass 定义 ✅
- 无新增 token、fence、scheduler、runner、policy 字段 ✅
- authoritative `WaitPollLost`、Ready/NotReady、explicit lifecycle terminal types 均保留 ✅

### 5.2 durable/state.py diff

- 删除 `mark_wait_record_poll_abandon_timeout(...)` 完整定义（~75 行） ✅
- 删除 `TERMINAL_RUN_STATUS_VALUES` unused import ✅
- `release_wait_record_poll_claim(...)` 保留 ✅
- `mark_wait_record_poll_abandoned(...)` 保留 ✅
- schema、enum、codec、migration 均无修改 ✅
- 无 deprecated wrapper、compat re-export、dead helper 残留 ✅

### 5.3 design.md diff

- 精确改写 cancelled abandon timeout 句：timeout → poll-local transient diagnostic + release/backoff + keep CANCELLED + no `poll_abandoned_at` ✅
- 保留 explicit lifecycle terminal（applied/unsupported/noop）描述 ✅
- 无新增 policy/schema/contract 内容 ✅

### 5.4 Test diffs

| 文件 | 变更 | 判定 |
|-----|------|------|
| `test_wait_observation_runner.py` | 替换两条旧错误测试为 R05 owner contract；新增 `_MutableClock`；强化 late Ready drop + 下一轮恢复断言 | ✅ |
| `test_wait_adapter_polling.py` | authoritative lost test 增加 resolver idempotency key + `poll_last_error_code is None` 断言 | ✅ |
| `test_phase7_waiting_integration.py` | 新增 owner integration test；删除 unused `UTC` import | ✅ |
| `test_wait_record_state.py` | 新增 durable owner boundary test：CANCELLED release 后 claimability + `poll_abandoned_at is None` | ✅ |

### 5.5 Retained safety 逐项确认

| safety mechanism | 证据 | 状态 |
|---|---|---|
| late-publication token/generation fence | `_wait_observation.py` no diff；runner test 保留 `test_timeout_invalidates_token_and_late_result_cannot_publish` | ✅ |
| claim CAS | `release_wait_record_poll_claim` 原子 contract 保留；CAS conflict test 保留 | ✅ |
| outstanding capacity | capacity test 保留 | ✅ |
| shared close deadline | supervisor close test 保留 | ✅ |
| authoritative typed lost | `test_poll_adapter_lost_result_closes_run` 保留并强化 idempotency key + error_code 断言 | ✅ |
| explicit lifecycle terminal | parameterized applied/unsupported/noop tests 保留 | ✅ |
| backoff cap 与 claim 唯一真源 | `_release_with_backoff` 是唯一 release/backoff 入口 | ✅ |
| R04 config ownership | 12-field policy + typed modes + provider config 均无 diff | ✅ |

## 6. Deferred scope 确认

以下全部确认未进入当前 correction：

- scheduler close/terminal promotion 产品修复（plan §15 registered residual）
- Issue 175 process isolation / process-backed containment
- callback transport
- 统一 authorization/permission schema
- R05-S2（Engine no-diff regression + public smoke）
- R06+ semantic ownership remediation
- future Host LOST/cancelled-abandon durable evidence policy

## 7. Current gate、stop conditions、completion handoff 自洽性

### 7.1 Gate 一致性

| 真源 | 当前 gate |
|-----|----------|
| control doc | `R05-S1 validation plan-correction dual complete re-review` |
| plan §0 | 同一 R05-S1 validation plan correction 已完成，等待 Controller validation（transition 描述完整） |
| Controller fix validation | `READY_FOR_DUAL_COMPLETE_PLAN_CORRECTION_RE_REVIEW` |

control doc 是 live gate 真源，与当前实际 gate 一致。plan §0 的状态字符串 `WAITING_FOR_CONTROLLER_VALIDATION_AFTER_R05_S1_VALIDATION_PLAN_CORRECTION` 是 transition 历史态（Controller validation 已通过），但 plan artifact 不承担 live gate tracker 职责，且 §0 正文完整描述 transition 路径。**非 material finding。**

### 7.2 Stop conditions

§13 的 12 条 stop conditions 覆盖：
1. durable state 扩域
2. 新增 policy/scheduler/runner/token/fence
3. runner regression
4. Engine regression
5. adapter decision 越界修复
6. timeout 仍调 resolve/LOST/terminal
7. authoritative lost 误改
8. R04 漂移
9. security 放宽
10. measurement 非绿/覆盖率不足/diff 越界
11. allowlist 外 diff / design.md 越界
12. scheduler 豁免

全部 12 条完整且可执行。**PASS。**

### 7.3 Completion handoff

§14 明确：correction 完成 → Controller validation → 双路 review → fix/re-review → Controller adjudication → exact-scope accepted plan-correction commit → 恢复 R05-S1 validation。

当前处于双路 complete re-review 阶段（本 artifact 为第二路）。handoff 序列与实际流程一致。**PASS。**

## 8. Finding ledger

### 8.1 New findings

**ZERO.**

经完整独立 re-review，修订后的 plan、当前七路径 S1 diff、完整 correction/review evidence chain 在所有维度均未发现 material defect。

### 8.2 旧 findings closure

| Finding | 最终状态 | 本轮复核 |
|---------|---------|---------|
| `R05-PF-01` cancelled abandon capped retry residual | CLOSED | 保持关闭 ✅ |
| `R05-PF-02` smoke timing 可执行性 | CLOSED | 保持关闭 ✅ |
| `R05-PF-03` Host design close marker 真源纠错 | CLOSED | 保持关闭 ✅ |
| `R05-PF-04` invalid timeout-only durable primitive | CLOSED | 保持关闭 ✅ |
| `R05-PRR-F01` touched-file Ruff registry | CLOSED | 保持关闭 ✅ |
| `R05-S1-VAL-PD-F01` plan drift | REFLECTED_IN_CORRECTION | correction 已反映；等待 accepted commit 后关闭 gate ✅ |
| `R05-S1-VAL-CV-F01` stale gate text | CLOSED | 独立 stale 字符串扫描零命中 ✅ |
| DS coverage transient risk | RESIDUAL_LOCATED | root cause 已定位到 scheduler owner ✅ |

### 8.3 MiMo F01–F13

全部保持 `CHALLENGE_PASS / NOT_A_DEFECT`。不得转换为 finding。

## 9. Retained safety

同 §5.5。修订后的 plan 完整保留所有 safety mechanisms。

## 10. Residual owners

| Residual | Owner boundary | Disposition |
|----------|---------------|-------------|
| scheduler close/terminal promotion coordination | `HostDispatchScheduler.close()` / `EngineEventIngestor._with_terminal_promotion_retry` | 未修复、未 waive、未建 issue、未归 Issue 175；后续只能由 Controller/用户裁决 |
| CANCELLED abandon 长期 capped retry | future Host durable evidence policy | R05 不创造 terminal evidence |
| plan §0 历史 transition 状态 | plan artifact（live gate 真源是 control doc） | 非 material |
| R05-S2 未执行 | 既有 R05-S2 gate | 保持 pending；不阻塞 S1 |

## 11. Deferred scope

同 §6。全部 deferred items 确认未进入当前 correction。

## 12. Reviewed evidence

| 类别 | 路径 |
|-----|------|
| 项目指令 | `AGENTS.md` |
| 修订后 plan | `docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md`（全文） |
| Control doc | `docs/host/issues-implementation-control.md`（R05 相关 section） |
| Plan-drift Controller | `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-drift-controller-adjudication.md` |
| Correction AgentCodex | `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-codex.md` |
| Correction Controller validation | `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-controller-validation.md` |
| Implementation AgentCodex | `docs/reviews/wu-semantic-ownership-01-r05-s1-implementation-codex.md` |
| 初次 DS review | `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-review-ds.md` |
| 初次 MiMo review | `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-review-mimo.md` |
| Controller review adjudication | `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-review-controller-adjudication.md` |
| Zero-change fix AgentCodex | `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-review-fix-codex.md` |
| Fix Controller validation | `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-review-fix-controller-validation.md` |
| 七路径 S1 diff | `dayu/host/durable/state.py`, `dayu/host/wait_adapter.py`, `docs/host/design.md`, `tests/host/test_phase7_waiting_integration.py`, `tests/host/test_wait_adapter_polling.py`, `tests/host/test_wait_observation_runner.py`, `tests/host/test_wait_record_state.py`（完整 diff） |
| 独立验证命令 | protected digest、invalid symbol scan、scheduler R05 symbol scan、scheduler/Engine/Waiting/Observation/Schema no-diff、deferred scope scan、`git diff --check`、worktree status、stale gate text scan |

## 13. Final verdict

**PASS / ZERO MATERIAL FINDINGS**

本轮第二路独立完整 final re-review 重新审查了修订后的 R05 plan 全文、当前七路径 S1 product/test/design diff、完整 correction/review evidence chain，并独立执行了全部关键验证扫描。结论：

1. **初次 DS review 的 ZERO MATERIAL FINDINGS 仍然成立。** 全部 10 项 assumptions (A1–A10) 经独立重验通过。
2. **MiMo F01–F13 正确保持 challenge pass，不是 defect。** 全部 13 项经独立重验通过。
3. **Zero-change gate 未遗漏 accepted finding，未发生内容漂移。** Protected digest `3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2` 全程不变；worktree status 与期望一致。
4. **Whole-file scheduler exclusion 安全。** 独立 source scan 确认 `test_dispatch_scheduler.py` 与 R05 owner symbol 零交集。
5. **§7 functional matrices 完整保留。** Plan diff 无 §7 hunk；§8 coverage 是测量而非功能替代。
6. **Per-file coverage 可执行且不被 aggregate 掩盖。** 两个实际 changed production files 各自 `--fail-under=80`。
7. **Root cause 正确分离。** Scheduler close/terminal promotion coordination 是独立 Host lifecycle owner。
8. **Stop conditions 完整可执行。** §13 的 12 条全部 intact。
9. **Current gate 自洽。** Control doc、plan §0、Controller fix validation 一致。
10. **Completion handoff 正确。** 下一步是 Controller final adjudication，随后 exact-scope accepted plan-correction commit，再恢复 R05-S1 validation。
11. **S1 semantics 精确为 non-terminal release/backoff。** 逐文件 diff 全文核对确认。
12. **Protected digest 未漂移。** `3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2`
13. **Retained safety 全部保留。** Late-publication fence、claim CAS、capacity、shared close deadline、typed lost、explicit lifecycle terminal、backoff cap、R04 config ownership 均 intact。
14. **Deferred scope 全部确认未进入。** Scheduler fix、Issue 175、callback、authorization、R05-S2、R06+ 均未偷带。
15. **Scheduler residual 仍未修、未 waive、未建 issue、未归 Issue 175。** Plan §12/§15 完整登记。

**允许进入 exact-scope accepted plan-correction commit，随后恢复 R05-S1 validation。**

本 artifact 完成后停止等待 Controller。

## 14. 与 AgentMiMo re-review 的独立性声明

本 re-review 在未读取 AgentMiMo re-review artifact（如存在）的情况下独立完成。所有证据来自：

- 原始 source code 与 test 文件的直接读取
- 独立执行的 `git diff`、`shasum`、`rg` source scans
- plan/artifact 全文的独立交叉核对
- 完整 evidence chain 的逐项复核

两个 reviewer 的 verdict 不独立授权恢复 S1 validation；Controller 仍须裁决全部 findings 并完成 exact-scope accepted plan-correction commit。
