# WU-SEMANTIC-OWNERSHIP-01 R05-S1 Validation Plan Correction Review — AgentDS

## 1. Review 身份与 scope

- reviewer：AgentDS（第二路独立完整 adversarial plan review）。
- 这不是新 WU、feature、issue，也不是重新打开独立 sub-WU。
- reviewed target：修订后的 `docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md` **全文**，不是只看 correction diff。
- 同时覆盖：
  - Controller drift adjudication：`docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-drift-controller-adjudication.md`
  - AgentCodex correction artifact：`docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-codex.md`
  - Controller validation：`docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-controller-validation.md`
  - 原 accepted plan review/fix/re-review final artifacts：`docs/reviews/wu-semantic-ownership-01-r05-plan-second-rereview-controller-adjudication.md` 及其引用的两路 final review
  - R05-S1 implementation artifact：`docs/reviews/wu-semantic-ownership-01-r05-s1-implementation-codex.md`
  - 当前七路径 S1 产品/test/design diff 全文
  - scheduler direct source/test：`dayu/host/dispatch.py` close/wake/worker closeout、`dayu/host/engine_ingest.py` terminal promotion、`dayu/host/_execution_health.py` forced gate、`tests/host/test_dispatch_scheduler.py` 失败节点、`workspace/tmp/test_r05_scheduler_close_probe.py`
  - control doc 当前 R05 状态：`docs/host/issues-implementation-control.md`
- review timestamp：`20260715-224459`。
- 唯一 write allowlist：`docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-review-ds.md`（本 artifact）。

## 2. Assumptions tested

| # | Assumption | 验证方式 | 结论 |
|---|---|---|---|
| A1 | scheduler 失败与 R05 wait observation 无 source/propagation 交集 | 对 `test_dispatch_scheduler.py` 做完整 source scan：`wait_adapter`、`WaitPoller`、`WaitObservation`、`WaitRecord`、`mark_wait_record_poll_abandon_timeout`、`_MarkWaitRecordAbandonTimeoutOperation`、`release_wait_record_poll_claim` 均为零命中 | **成立** |
| A2 | `test_toolruntime_executor.py` 同样无 R05 交集 | 同上 source scan，零命中 | **成立** |
| A3 | scheduler 失败是独立 lifecycle owner 缺口，不是 R05 timeout transaction 错误 | 确定性 probe `workspace/tmp/test_r05_scheduler_close_probe.py` 独立复现顺序：close gate 先提交 → promotion task 取消时让出 event loop → active worker clean EOF → terminal promotion 同步 wake → force health gate 拒绝 | **成立** |
| A4 | 当前 S1 diff 精确为 non-terminal release/backoff | 完整 diff 逐文件核对：poll timeout → `_release_with_backoff(ADAPTER_ERROR/wait_observation_timeout)`、abandon timeout → `_release_with_backoff(ABANDON_ERROR/wait_abandon_timeout)`、删除 invalid primitive + unused import | **成立** |
| A5 | invalid timeout symbol 已从 production/tests 彻底删除 | `rg 'mark_wait_record_poll_abandon_timeout\|_MarkWaitRecordAbandonTimeoutOperation' dayu tests` 零命中（exit 1） | **成立** |
| A6 | 七路径 protected digest 未漂移 | 独立运行 `git diff --binary -- <seven paths> \| shasum -a 256`，结果 `3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2` | **成立** |
| A7 | §7 功能矩阵未被 coverage session 替代或删减 | plan diff 无 §7 hunk；§7.1 exact owner/focused/aggregate nodes 原样保留 | **成立** |
| A8 | 未偷带 scheduler fix、Issue 175、callback、authorization、R05-S2、R06+ | `git diff --unified=0 -- dayu \| rg 'authorization\|permission\|callback.transport\|process.isolation\|process_backed\|subprocess\|Issue.175'` 零命中；`_wait_observation.py`/`waiting.py`/`engine/agent.py`/`durable/schema.py` 均无 diff；scheduler source files（`dispatch.py`/`engine_ingest.py`/`_execution_health.py`）与 `test_dispatch_scheduler.py` 均无 diff | **成立** |
| A9 | 保留 late-publication fence、claim CAS、capacity、shared close deadline、authoritative typed lost、explicit lifecycle terminal | focused matrix 覆盖全部节点；diff 中 authoritative lost test 仅增加了 idempotency key + error_code 断言（强化而非削弱）；runner token/fence 保持 no diff | **成立** |
| A10 | R04 config ownership 未被修改 | `awaiting_resolution_mode`、12-field policy、packaged provider modes 均无 diff | **成立** |

## 3. 逐项 challenge 结果

### 3.1 排除 `test_dispatch_scheduler.py` 是否有 source/propagation/coverage/security 漏洞

**直接证据：**

- `test_dispatch_scheduler.py` 对 R05 owner symbol 全集 source scan 为零命中（见 A1）。
- `dayu/host/dispatch.py`、`dayu/host/engine_ingest.py`、`dayu/host/_execution_health.py` 相对 R05 plan base 均无 diff。
- 确定性 probe 独立证明 root cause 是 scheduler close gate 与 terminal promotion 的线性化缺口，与 R05 timeout transaction 无关。
- R05 的 `wait_adapter.py` 变更只改变 poller 内 timeout decision branch 的 durable operations；不改变 scheduler-visible 的任何状态、schema 或 API。

**coverage 分析：** coverage 工具测量测试执行期间被覆盖的代码行。`test_dispatch_scheduler.py` 从未 import 或调用任何 `wait_adapter`/`durable/state.py` 的 wait-record 函数，因此排除该文件不会减少 R05 changed owners 的已测量覆盖率。Controller 候选 session 独立验证了两个 owner 分别为 83%/86%，且两个逐文件 `--fail-under=80` 均通过。

**security 分析：** 被排除的测试测试 queue promotion 的 compact 行为，不涉及 wait observation 的 token fence、claim CAS、capacity、close-drain 或任何 R05 security boundary。R05 security mechanisms 全部由 §7.1 focused owner nodes 覆盖。

**regression 隐藏风险：** 修订后的 coverage measurement 明确命名为 "R05 changed-owner coverage measurement"，不是 "Host regression acceptance"。R05 功能回归由 §7.1 的 exact owner/focused/aggregate 矩阵覆盖，不由 coverage session 替代。排除 scheduler test 不会隐藏任何 R05 regression，因为该 test 从不测试 R05 code paths。

**结论：无 source/propagation/coverage/security 漏洞，不会隐藏 R05 regression。**

### 3.2 §7 功能矩阵是否仍完整覆盖 R05 real propagation

**直接证据：**

- plan diff 无 §7 hunk。§7.1 的 test-first 三节点、durable preservation 节点、实现后 16-node focused matrix、4-file Host focused collection 均原样保留。
- §7.2 Engine nodes 与 §7.3 R04 preservation/aggregate regression 也未修改。
- §8 明确声明 coverage session "只测量 R05 两个实际 changed production owner 的覆盖率，不是完整 Host regression acceptance，也不能替代、删减或放宽 §7.1 的任何功能节点"。

**结论：§7 功能矩阵完整保留，coverage 是测量而非功能替代。**

### 3.3 Measurement 整体绿色 + 逐文件 ≥80% 是否可执行且不被 aggregate 掩盖

**直接证据：**

- Controller 独立候选 session：`1830 passed, 2 skipped, 5 deselected in 53.15s`，整体绿色。
- `dayu/host/durable/state.py=83%`，`dayu/host/wait_adapter.py=86%`。
- 两个独立 `coverage report --include='...' --fail-under=80` 均通过。
- 计划明确要求对每个 actual changed production file 单独执行 `--fail-under=80`，"禁止用总覆盖率代替逐文件门禁"（§8 末尾）。

**可执行性：** 命令已由 Controller 独立运行验证，code-generation-ready。

**结论：可执行，不被 aggregate 掩盖。**

### 3.4 Scheduler root cause 是否真与 R05 owner 分离，是否被错误标为 flake/inherited/已修复

**直接证据：**

- 确定性 probe `workspace/tmp/test_r05_scheduler_close_probe.py` 以事件顺序证明 root cause 是 scheduler close 与 terminal promotion 的独立协调缺口。
- plan §12 明确记录："该失败不得称为 flake、inherited pass 或已修复；其产品 owner 超出 R05-S1 closed allowlist，当前 umbrella 不修复、不创建 issue，也不归入 Issue 175"。
- plan §15 将 residual owner boundary 登记为："Host scheduler close / terminal promotion coordination"，并明确 "后续 destination 只能由 Controller / 用户另行裁决"。
- plan §13 stop condition #12 明确禁止为绕过该缺口而新增第三个 ignore/deselect/xfail/retry/failure exemption，或修改 scheduler 产品/测试。

**结论：root cause 正确分离，未被误标。Residual owner/destination 足够。**

### 3.5 Plan 当前 gate、stop conditions、baseline registry、completion handoff 是否自洽

**gate 一致性：**

- plan §0 gate 文本："当前 gate：同一 R05-S1 validation plan correction 已由 AgentCodex 完成，当前等待 Controller validation" — 反映 correction 完成时的状态。
- Controller validation artifact 已给出 `PASS / READY_FOR_DUAL_COMPLETE_PLAN_CORRECTION_REVIEW`。
- control doc 当前 gate 已更新为 "R05-S1 validation plan-correction dual review"。
- plan §14 明确 correction 完成后 "下一步只回 Controller validation"，与实际流程一致（Controller validation 已执行并通过）。
- 三处历史 stale gate 文本（曾冒充 current gate）已由 Controller follow-up `R05-S1-VAL-CV-F01` 精确关闭；独立 stale 字符串扫描确认零命中。

**plan §0 状态字符串的微小时间差：** plan §0 的 `WAITING_FOR_CONTROLLER_VALIDATION_AFTER_R05_S1_VALIDATION_PLAN_CORRECTION` 在 Controller validation 已通过的当前时刻严格来说是过去状态。但 plan artifact 不承担 live gate tracker 职责（那是 control doc 的职责），且 plan §0 正文已完整描述 transition 路径。这不是 material finding。

**stop conditions：** §13 的 12 条 stop conditions 覆盖：durable state 扩域、新增 policy/scheduler/runner/fence、runner token regression、Engine regression、adapter decision 越界修复、timeout 仍调 resolve/LOST/terminal、authoritative lost 误改、R04 漂移、security 放宽、修订后 measurement 非绿/覆盖率不足/diff 越界、scheduler 豁免。全部 conditions 精确且可执行。

**baseline registry：** §12 完整登记了失败六元组（exact command、node、error、first stable frame、normalized fingerprint、validation HEAD）、失败 session 结果（`1 failed, 1917 passed, 1 skipped, 5 deselected`）、确定性 probe 证据（`1 passed`）、同源 root cause、Controller 候选 session 证据（`1830 passed, 2 skipped, 5 deselected` / 83% / 86%）。登记完整且正确。

**completion handoff：** §14 明确 correction 完成后只回 Controller validation，不得自行进入 R05-S1 剩余 validation、R05-S2、code review、commit、aggregate gate、push 或 PR。与 Controller validation artifact 和 control doc 一致。

**结论：gate、stop conditions、registry、handoff 自洽。无 material finding。**

### 3.6 当前 S1 diff 是否确实只实现 non-terminal release/backoff，保留所有指定 contract

**逐文件 diff 核对：**

| 文件 | diff 内容 | 判定 |
|---|---|---|
| `dayu/host/wait_adapter.py` | poll timeout：删除 `WaitPollLost(ResolveWaitLostOutcome(...))` 构造 + `_resolve_claimed_wait` 调用，改为 `_release_with_backoff(ADAPTER_ERROR/wait_observation_timeout)`；abandon timeout：删除 `_MarkWaitRecordAbandonTimeoutOperation` 调用，改为 `_release_with_backoff(ABANDON_ERROR/wait_abandon_timeout)`；删除 invalid import/wrapper | ✅ 符合 |
| `dayu/host/durable/state.py` | 删除 `mark_wait_record_poll_abandon_timeout(...)` 完整定义（~50行）；删除 `TERMINAL_RUN_STATUS_VALUES` unused import；保留 `release_wait_record_poll_claim` 和 `mark_wait_record_poll_abandoned` | ✅ 符合 |
| `docs/host/design.md` | 精确改写 cancelled abandon timeout 句：timeout → transient diagnostic + release/backoff + keep CANCELLED + no `poll_abandoned_at`；保留 explicit lifecycle terminal 描述 | ✅ 符合 |
| `tests/host/test_wait_observation_runner.py` | 替换两条旧错误测试为 R05 owner contract；保留 token invalidation、close deadline；强化 late Ready drop 与下一轮恢复断言 | ✅ 符合 |
| `tests/host/test_wait_adapter_polling.py` | 仅对 authoritative lost test 增加 resolver idempotency key 与 `poll_last_error_code is None` 断言（强化 typed lost 同源验证） | ✅ 符合 |
| `tests/host/test_phase7_waiting_integration.py` | 增加 poll timeout → WAITING → 下一轮 Ready 恢复的 owner integration test；删除 unused `UTC` import | ✅ 符合 |
| `tests/host/test_wait_record_state.py` | 增加 durable owner boundary test：CANCELLED release 后到期可再次 claim，并断言 `poll_abandoned_at is None` | ✅ 符合 |

**保留 contract 逐项核对：**

- late-publication token/fence：`_wait_observation.py` no diff；runner test 保留 `test_timeout_invalidates_token_and_late_result_cannot_publish` ✅
- claim CAS：`release_wait_record_poll_claim` 保留其原子 update contract；CAS conflict test 保留 ✅
- capacity：`test_supervisor_close_uses_one_shared_deadline_and_stays_closing` 保留 ✅
- shared close deadline：同上 ✅
- authoritative typed lost：`test_poll_adapter_lost_result_closes_run` 保留并增加 idempotency key + error_code 断言（强化） ✅
- explicit lifecycle terminal：`test_poll_abandon_success_marks_row_and_clears_claim` 保留 parameterized applied/unsupported/noop ✅
- R04 config ownership：12-field policy、typed modes、provider config 均无 diff ✅

**结论：当前 S1 diff 精确只实现 non-terminal release/backoff，完整保留所有指定 contract。**

### 3.7 是否偷带 scheduler fix、Issue 175、callback、统一 authorization、R05-S2 或 R06+

**直接证据：**

- scheduler source：`dayu/host/dispatch.py`、`dayu/host/engine_ingest.py`、`dayu/host/_execution_health.py` — 零 diff
- scheduler test：`tests/host/test_dispatch_scheduler.py` — 零 diff
- Engine：`dayu/engine/agent.py` — 零 diff
- Smoke：`utils/smoke_host_public_awaiting_entrypoint.py` — 零 diff
- README：均无 diff
- Security/deferred scope scan：`git diff --unified=0 -- dayu | rg 'authorization|permission|callback.transport|process.isolation|process_backed|subprocess|Issue.175'` — 零命中
- `dayu/host/waiting.py`、`dayu/host/_wait_observation.py`、`dayu/host/durable/schema.py` — 零 diff

**结论：未偷带任何 scheduler fix、Issue 175、callback、统一 authorization、R05-S2 或 R06+ 内容。**

## 4. Finding ledger

**Zero material findings.**

经完整 adversarial review，修订后的 plan 在以下所有维度均未发现 material defect：

- 排除 `test_dispatch_scheduler.py` 不产生 source/propagation/coverage/security 漏洞
- §7 功能矩阵完整保留，coverage 是测量而非功能替代
- measurement 整体绿色 + 逐文件 ≥80% 可执行且不被 aggregate 掩盖
- scheduler root cause 正确与 R05 owner 分离，未被误标
- gate、stop conditions、baseline registry、completion handoff 自洽
- S1 diff 精确只实现 non-terminal release/backoff，保留所有指定 contract
- 未偷带任何 deferred scope

## 5. 旧 findings closure 复核

| 旧 Finding | 最终状态 | DS 复核 |
|---|---|---|
| `R05-PF-01` cancelled abandon capped retry residual | CLOSED | plan §2.1/§4/§15 与 call order 同源；不发明 terminal evidence。**保持关闭** |
| `R05-PF-02` smoke timing 可执行性 | CLOSED | event/condition/state-poll、monotonic deadline、named margins/CI cap/phase ledger 完整。**保持关闭** |
| `R05-PF-03` Host design close marker 真源纠错 | CLOSED | S1 精确 writeback，保留 explicit lifecycle terminal。**保持关闭** |
| `R05-PF-04` invalid timeout-only durable primitive | CLOSED | storage owner deletion + owner test + zero-symbol scan gates 完整。**保持关闭** |
| `R05-PRR-F01` touched-file Ruff registry | CLOSED | 两条 F401 六元组完整，S1 已在 changed files 清除。**保持关闭** |
| DS coverage transient risk（原 second re-review） | RESIDUAL_VALIDATION_RISK → 升级为已定位 residual | root cause 已由确定性 probe 定位到 scheduler close/terminal promotion owner；plan §12/§15 完整登记。**状态更新为已定位，不再 root-cause-undetermined** |

所有旧 findings 保持关闭。原 DS coverage transient risk 的 root cause 已从 "undetermined" 升级为 "已定位到独立 owner boundary"。

## 6. Retained safety

修订后的 plan 完整保留：

- late publication token/generation fence（`_wait_observation.py` no diff）
- claim CAS（`release_wait_record_poll_claim` 原子 contract 保留）
- outstanding observation capacity（capacity test 保留）
- shared close deadline（supervisor close test 保留）
- authoritative typed lost（test 保留并强化 idempotency key + error_code 断言）
- explicit lifecycle terminal（parameterized applied/unsupported/noop tests 保留）
- backoff cap 与 claim 唯一真源（`_release_with_backoff` 是唯一 release/backoff 入口）
- R04 12-field policy、typed modes、provider config ownership（均无 diff）

## 7. Deferred scope

以下内容确认未进入当前 correction 且 plan 边界完整：

- scheduler close/terminal promotion 产品修复（residual owner boundary 已登记，plan §15）
- Issue 175 process isolation / process-backed containment
- callback transport
- 统一 authorization/permission schema
- R05-S2（Engine no-diff regression + public smoke）
- R06+ semantic ownership remediation
- future Host LOST/cancelled-abandon durable evidence policy

## 8. Reviewed paths/commands

| 类别 | 路径/命令 |
|---|---|
| 计划 | `docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md`（全文） |
| Controller artifacts | `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-drift-controller-adjudication.md`、`docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-controller-validation.md` |
| AgentCodex artifacts | `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-plan-correction-codex.md`、`docs/reviews/wu-semantic-ownership-01-r05-s1-implementation-codex.md` |
| 历史 review | `docs/reviews/wu-semantic-ownership-01-r05-plan-second-rereview-controller-adjudication.md` |
| Control doc | `docs/host/issues-implementation-control.md`（R05 相关行） |
| 项目指令 | `AGENTS.md`、`docs/phaseflow-umbrella-optimization-control.md` |
| 生产代码 | `dayu/host/dispatch.py`（close/wake/worker closeout）、`dayu/host/engine_ingest.py`（terminal promotion）、`dayu/host/_execution_health.py`（forced gate）、`dayu/host/wait_adapter.py`（完整 diff）、`dayu/host/durable/state.py`（完整 diff） |
| 测试 | `tests/host/test_dispatch_scheduler.py`（失败节点 + source scan）、`workspace/tmp/test_r05_scheduler_close_probe.py`、四个 owner test 文件完整 diff |
| Design | `docs/host/design.md`（diff） |
| Digest | `git diff --binary -- <seven paths> \| shasum -a 256` → `3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2` |
| Source scans | invalid symbol scan（零命中）、deferred scope scan（零命中）、test_dispatch_scheduler R05 symbol scan（零命中）、test_toolruntime_executor R05 symbol scan（零命中）、no-diff files 确认 |
| planreview skill | 完整读取并应用 |

## 9. Residual risks

| Risk | Owner boundary | Disposition |
|---|---|---|
| scheduler close/terminal promotion 线性化缺口 | `HostDispatchScheduler.close()` / `EngineEventIngestor._with_terminal_promotion_retry` | 已由确定性 probe 定位；R05 coverage measurement 与其解耦；产品修复待 Controller/用户另行裁决；plan §12/§15 完整登记 |
| CANCELLED abandon 长期 capped retry（无 provider terminal outcome） | future Host durable evidence policy | R05 的 claim CAS/capacity cap/finite timeout/late-result fence/backoff cap 限制资源但不创造 terminal evidence；plan §15 明确记录 |
| plan §0 状态字符串 `WAITING_FOR_CONTROLLER_VALIDATION_AFTER_R05_S1_VALIDATION_PLAN_CORRECTION` | plan artifact（非 live gate tracker） | Controller validation 已通过；control doc 正确反映当前 gate；不影响 execution，非 material |
| R05-S2 未执行 | R05-S2（Engine no-diff + public smoke） | 在本 plan correction 范围内正确 deferred；S1 completion 不依赖 S2 |

## 10. Verdict

**PASS / ZERO MATERIAL FINDINGS**

修订后的 R05-S1 validation plan correction 是 accepted plan 的同一 R05 内的精确 validation contract 修复。它只把 R05 changed-owner coverage measurement 与无 source/propagation 交集的独立 scheduler lifecycle owner 解耦，同时完整保留所有 R05 功能矩阵、逐文件覆盖率、静态检查、source/propagation/security scans、README decision 与后续 aggregate gate。

所有七项 task-required challenge 均通过直接代码/数据证据验证。无 material finding。correction 可安全进入 Controller adjudication 与后续 R05-S1 validation 恢复。

**不需要 fix/re-review。** 本 artifact 完成后停止等待 Controller。

## 11. 与 AgentMiMo review 的独立性声明

本 review 在未读取 AgentMiMo review artifact（如存在）的情况下独立完成。所有证据来自：
- 原始 source code 与 test 文件的直接读取
- 独立执行的 `git diff`、`shasum`、`rg` source scans
- 确定性 probe 的代码级追踪
- plan/artifact 全文的独立交叉核对

两个 reviewer 的 verdict 不独立授权恢复 S1 validation；Controller 仍须裁决全部 findings。
