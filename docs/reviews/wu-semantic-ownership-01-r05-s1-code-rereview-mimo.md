# WU-SEMANTIC-OWNERSHIP-01 R05-S1 Adversarial Code Re-Review — AgentMiMo (第一路)

## 1. Review scope 与 verdict

- review gate：`R05-S1 dual complete code re-review`；zero-change fix 后第一路 AgentMiMo adversarial re-review。
- 七路径 protected diff digest：`3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2`。
- implementation artifact：`docs/reviews/wu-semantic-ownership-01-r05-s1-implementation-codex.md`。
- validation continuation artifact：`docs/reviews/wu-semantic-ownership-01-r05-s1-validation-continuation-codex.md`。
- Controller validation artifact：`docs/reviews/wu-semantic-ownership-01-r05-s1-controller-validation.md`。
- AgentMiMo initial code review artifact：`docs/reviews/wu-semantic-ownership-01-r05-s1-code-review-mimo.md`。
- AgentDS initial code review artifact：`docs/reviews/wu-semantic-ownership-01-r05-s1-code-review-ds.md`。
- Controller code-review adjudication artifact：`docs/reviews/wu-semantic-ownership-01-r05-s1-code-review-controller-adjudication.md`。
- AgentCodex zero-change fix artifact：`docs/reviews/wu-semantic-ownership-01-r05-s1-code-review-fix-codex.md`。
- Controller zero-change fix validation artifact：`docs/reviews/wu-semantic-ownership-01-r05-s1-code-review-fix-controller-validation.md`。
- accepted plan base：`5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1`。
- current HEAD：`2c068869843837546e6c6bc0a5285918b01d8b29`。
- verdict：**PASS / 无 material finding**。

## 2. Re-review 方法与完整性说明

本次 re-review 不是只看 zero-change artifact，而是完整重审七路径 product/test/design diff 全文、accepted plan、全部 implementation/validation/review/adjudication/fix evidence chain、no-diff owner source、source/propagation/security scans 与测试验证。re-review 覆盖以下全部维度：

1. semantic owner 与 poll/abandon timeout non-terminal release/backoff transaction；
2. counts、claim CAS、attempt/next-observe、diagnostics、Wait/Run projection；
3. late publication 不污染下一轮；typed LOST、Ready/NotReady、explicit applied/unsupported/noop terminal preservation；
4. durable primitive 删除、dead caller/import/schema/public contract；
5. test owner contract、fake、时序、coverage gap；type/docstring/coupling/semantic drift；
6. retained safety、deferred scope、LLM-facing/no-unified-authorization boundary；
7. Controller 对两条 DS observation 的 disposition 是否合理、有无漏掉可达 defect；
8. protected seven-path digest 是否仍为 `3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2`；
9. zero-change proof 是否可信；scheduler close residual 是否仍未修、未掩盖、未 waive。

## 3. Finding ledger

### 3.1 零 finding 说明

经逐行 adversarial re-review 七路径 product/test/design diff 全文、全部 evidence chain、no-diff owner source、source/propagation/security scans、测试独立重跑与 protected target 复核，未发现任何 correctness、stability、semantic ownership drift、test contract、type/docstring、coupling、retained safety weakening 或 deferred scope leakage finding。

### 3.2 逐维度分析

#### 3.2.1 Root cause / semantic owner

**结论：正确，无 finding。**

直接代码证据链（本次 re-review 独立重读确认）：

1. `dayu/host/_wait_observation.py` — token identity、state、generation 管理发布权全在同一锁内（`_wait_observation.py:326-334`、`_wait_observation.py:348-361`）；timeout 先 invalidates token（`_wait_observation.py:210`），late result 只增加 dropped count（`_wait_observation.py:356`）。该 owner 正确，保持 no diff（`git diff --exit-code` PASS）。

2. `dayu/host/wait_adapter.py` — poll timeout 分支（`wait_adapter.py:1072-1085`）不再构造 `WaitPollLost(ResolveWaitLostOutcome(...))`，改为 `_release_with_backoff(...)` 写 `ADAPTER_ERROR / wait_observation_timeout`；abandon timeout 分支（`wait_adapter.py:1320-1334`）不再调用 `_MarkWaitRecordAbandonTimeoutOperation`，改为同一 `_release_with_backoff(...)` 写 `ABANDON_ERROR / wait_abandon_timeout`。`WaitPoller` 作为 observation 结果解释与 claim release/backoff policy owner 正确。

3. `dayu/host/durable/state.py` — `mark_wait_record_poll_abandon_timeout(...)` 完整删除（原 `state.py:2725-2801` 共 78 行），`_MarkWaitRecordAbandonTimeoutOperation` wrapper 及其 import 一并删除。保留的 `release_wait_record_poll_claim(...)` 继续拥有原子 claim release、next-observe、attempt 与 diagnostic projection（`state.py:2589-2659`）。`mark_wait_record_poll_abandoned(...)` 继续服务 explicit applied/unsupported/noop lifecycle outcome 的 terminal `poll_abandoned_at` 写入（`state.py:2662-2724`）。`TERMINAL_RUN_STATUS_VALUES` unused import 已删除（原 `state.py:40`）。删除无误。

4. `docs/host/design.md` — 只改写 accepted plan 指定的精确句子（原 2429-2430 行改为 2429-2432 行）：从 "cancelled wait 的 abandon 超时只写 `wait_abandon_timeout` diagnostic/close marker" 改为 "cancelled wait 的 abandon observation timeout 只写 poll-local transient `wait_abandon_timeout` diagnostic、释放 claim 并按 policy backoff，durable status 保持 `CANCELLED` 且不写 terminal `poll_abandoned_at`；只有 provider 显式返回 applied/unsupported/noop lifecycle outcome 才写 terminal marker"。改动精确，未扩写 policy/schema/future terminal evidence contract。

#### 3.2.2 Poll/abandon 返回计数、CAS 冲突、backoff attempt/next-observe、diagnostic、Wait/Run projection

**结论：正确，无 finding。**

本次 re-review 独立重读代码并验证：

| 维度 | poll timeout 实际行为 | abandon timeout 实际行为 |
|---|---|---|
| `lost` 计数 | `lost == 0`（不调用 resolve_wait） | N/A |
| `abandoned` 计数 | N/A | `abandoned == 0`（不写 terminal marker） |
| `adapter_errors` 计数 | `adapter_errors == 1` | `adapter_errors == 1` |
| claim 清理 | `poll_claim_id is None`、`poll_claim_owner_id is None`、`poll_claimed_at is None`、`poll_claim_expires_at is None` | 同左 |
| backoff attempt | `poll_backoff_attempt == 1`（base `0 + 1`） | `poll_backoff_attempt == 1` |
| next_observe_at | 按 `_backoff_delay_seconds(1, policy)` 计算 | 同左 |
| poll_last_outcome | `WaitPollLastOutcome.ADAPTER_ERROR` | `WaitPollLastOutcome.ABANDON_ERROR` |
| poll_last_error_code | `"wait_observation_timeout"` | `"wait_abandon_timeout"` |
| poll_abandoned_at | `None`（不写入） | `None`（不写入） |
| Wait 状态 | `WAITING`（不变） | `CANCELLED`（不变） |
| Run 状态 | `WAITING`（不变） | N/A |
| resolver 调用 | 零调用 | 零调用 |

`_release_with_backoff` 唯一调用 `_backoff_delay_seconds(next_attempt, policy)`，其中 `next_attempt = record.poll_backoff_attempt + 1`（`wait_adapter.py:1475`），公式 `policy.backoff_initial_delay_seconds * (policy.backoff_multiplier ** (backoff_attempt - 1))` 封顶 `policy.backoff_max_delay_seconds`（`wait_adapter.py:1886-1889`）。没有 timeout-local 时间公式或第二 backoff 算法。

#### 3.2.3 Late publication token/generation fence 与下一轮 observation 污染

**结论：正确，无 finding。**

- `WaitObservationRunner.observe(...)` 在 `adapter_call_timeout_seconds` 后调用 `_invalidate_token(token)`（`_wait_observation.py:210`），token state 变为 `INVALIDATED`。
- `_publish(...)` 同时检查 token identity、state（must be `ACTIVE`）、closed 与 generation（`_wait_observation.py:348-361`）；late result 进入 `dropped_count`。
- 下一轮 `poll_once()` 创建全新 claim、新 observation、新 token；旧 token 已 invalid 且其 result_queue maxsize=1，不存在跨轮污染路径。
- 测试断言 `runner.diagnostics_snapshot().dropped_count == 1` 和 `runner.diagnostics_snapshot().invalidated_count == 1` 直接验证。

#### 3.2.4 Authoritative typed lost、Ready/NotReady、explicit applied/unsupported/noop terminal

**结论：正确，无 finding。**

- `test_poll_adapter_lost_result_closes_run`（`test_wait_adapter_polling.py:886-903`）使用 `_RecordingPublicCommandResolver` 与 idempotency key 断言，确认 authoritative typed `WaitPollLost` 仍走 `_resolve_claimed_wait(...)` 路径、`lost == 1`、`WaitRecordStatus.LOST`、`RunStatus.LOST`。timeout code 不出现在该 branch。
- `test_poll_adapter_ready_result_resolves_wait`、`test_poll_adapter_not_ready_leaves_wait_active` 保持原 owner 断言。
- `test_cancelled_poll_wait_is_abandoned_once_without_resolve`、`test_failed_cancelled_wait_abandon_is_retried_next_poll` 保持 explicit lifecycle terminal outcome 的 `mark_wait_record_poll_abandoned(...)` 路径断言。
- `test_poll_abandon_success_marks_row_and_clears_claim` 参数化覆盖 `ABANDONED`/`ABANDON_UNSUPPORTED`/`ABANDON_NOOP` 三种 explicit terminal outcome，均写 `poll_abandoned_at`。
- `test_cancelled_poll_timeout_release_preserves_claimability_after_due` 证明 timeout release 后 `poll_abandoned_at is None`、到期可再次 claim。

#### 3.2.5 删除 durable primitive 的 dead import/caller/schema drift/public contract

**结论：正确，无 finding。**

- `mark_wait_record_poll_abandon_timeout` 在 production/tests 中零定义、零调用（`rg` exit 1，无匹配）。
- `_MarkWaitRecordAbandonTimeoutOperation` 在 production/tests 中零定义、零调用。
- `mark_wait_record_poll_abandon_timeout` 的 import 已从 `wait_adapter.py` 删除。
- `TERMINAL_RUN_STATUS_VALUES` unused import 已从 `state.py` 删除（原 `state.py:40`）。
- `datetime.UTC` unused import 已从 `test_phase7_waiting_integration.py` 删除（原 `test_phase7_waiting_integration.py:8`）。
- `dayu/host/durable/schema.py` no diff；`poll_abandoned_at` schema 字段保留。
- `mark_wait_record_poll_abandoned(...)` 继续存在并服务 explicit terminal outcome。

#### 3.2.6 Tests 是否真正断言 owner contract、self-implementation fake、时序脆弱、test helper 误用、覆盖缺口

**结论：正确，无 finding。**

- **Owner contract 断言**：新 timeout tests 断言完整 claim 清理（四个 fields）、backoff attempt/next-observe、diagnostic code/outcome、Wait/Run 状态、resolver 零调用；不是只断言计数或日志。
- **`_BlockingAdapter` 改造**：从 `WaitPollNotReady()` 改为 `WaitPollReady(ResolveWaitCompletedOutcome(...))` 是正确的——late result 必须是 Ready 才能验证 token fence 阻止了 resolution。若保持 NotReady，late result 不会进入 resolve path，无法验证 fence 有效性。
- **时序确定性**：使用 `_MutableClock` 显式推进时间，不依赖 `time.sleep()`；`advance(0.01)` 匹配 `backoff_initial_delay_seconds=0.01` 的 test override。无时序脆弱。
- **Test helper 使用**：`_RecordingPublicCommandResolver` 记录 idempotency keys 但不实际 resolve；`_NoResolveResolver` 在 abandon test 中阻止 resolve。两者都是正确的测试替身，不 self-implement production behavior。
- **覆盖缺口**：四个 focused test files 全部 69 passed。focused branch matrix 19 passed 覆盖 Ready、NotReady、authoritative typed LOST、poll/abandon timeout、snapshot failure、explicit lifecycle terminal、retry、claim CAS、expired claim、invalid deadline、token invalidation、capacity/shared close deadline 与真实 durable resume。coverage 测量 `state.py=83%`、`wait_adapter.py=86%`，均 >=80%。

#### 3.2.7 Type/docstring/maintainability/coupling/semantic ownership drift、LLM-facing 文本和 design 真源

**结论：正确，无 finding。**

- 所有新增/修改函数保持完整类型签名和中文 docstring。
- `_MutableClock` 类型实现 `WaitPollClock` protocol，`now()` 返回 `datetime`。
- `docs/host/design.md` 精确真源句与 R05 plan §5.1 一致，不扩写 policy/schema/future contract。
- production diff 只涉及 `wait_adapter.py` 与 `state.py` 两个 owner 文件，无 coupling 增加。
- LLM-facing 文本不受影响（R05 不修改 tool schema、prompt、memory projection）。

#### 3.2.8 Retained safety 是否被弱化、deferred scope 是否偷带

**结论：正确，无 finding。**

retained safety（本次 re-review 独立重跑确认）：

| 安全机制 | 状态 | 验证方式 |
|---|---|---|
| late publication token/generation fence | 保留 | `_wait_observation.py` no diff + `test_timeout_invalidates_token_and_late_result_cannot_publish` 通过 |
| outstanding capacity / shared close deadline | 保留 | `test_supervisor_close_uses_one_shared_deadline_and_stays_closing` 通过 |
| claim token CAS / release backoff / next-due claimability | 保留 | `test_active_poll_claim_suppresses_second_poller_adapter_call` + `test_expired_poll_claim_allows_retry` 通过 |
| authoritative typed lost via common resolver | 保留 | `test_poll_adapter_lost_result_closes_run` 通过 + idempotency key 断言新增 |
| explicit applied/unsupported/noop terminal marker | 保留 | `test_cancelled_poll_wait_is_abandoned_once_without_resolve` + `test_poll_abandon_success_marks_row_and_clears_claim` 通过 |
| invalid timeout-only symbol 零残留 | 确认 | `rg` 零匹配 |
| R04 config ownership / 12-field snapshot | 保留 | R04 preservation tests 通过 |
| cancellation / close-drain / capacity | 保留 | focused matrix 通过 |

deferred scope scan（`git diff --unified=0` added lines）：authorization、permission、callback transport、process isolation、process_backed、subprocess、Issue 175 均零命中。

#### 3.2.9 Scheduler residual 是否被当前代码误修、掩盖或引入新传播

**结论：正确，无 finding。**

- `tests/host/test_dispatch_scheduler.py` 对 `wait_adapter`、`WaitPoller`、`WaitObservation`、`WaitRecord`、`mark_wait_record_poll_abandon_timeout`、`release_wait_record_poll_claim` 零命中（`rg` exit 1）。
- `dispatch.py`、`engine_ingest.py`、`test_dispatch_scheduler.py` 相对 plan base 均 no diff。
- 确定性 scheduler close probe `workspace/tmp/test_r05_scheduler_close_probe.py` 仍 `1 passed in 0.31s`，证明 close gate → clean EOF terminal closeout → promotion wake rejection 缺口仍可确定性复现。
- R05-S1 只在 coverage measurement 中额外排除 `test_dispatch_scheduler.py`，不宣称修复、不创建 issue、不归入 Issue 175。
- coverage session 中无第三个 ignore、xfail、retry 或 failure exemption。

#### 3.2.10 Controller 对两条 DS observation 的 disposition 复核

**结论：合理，无 finding。**

| DS observation | Controller disposition | 本次 re-review 判定 |
|---|---|---|
| `CANCELLED` wait 在 provider 永不返回 explicit lifecycle terminal outcome 时按 capped backoff 长期重试 | `RETAINED_RESIDUAL / NO_R05-S1_FIX`；owner 是 future Host durable evidence policy | 合理。R05 不能从 observation timeout 猜测 durable terminal evidence。当前 claim CAS、finite timeout、capacity cap、late-result fence 与 backoff cap 只限制资源，不创造 terminal evidence。 |
| poll observation timeout 复用 `WaitPollLastOutcome.ADAPTER_ERROR`，supervisor `adapter_errors` 未拆分 timeout | `NO_CURRENT_DEFECT / NO_FIX`；durable `poll_last_error_code=wait_observation_timeout` 已区分根因 | 合理。R05 plan 明确禁止新增 schema/enum/default；当前 aggregation 没有对外承诺"只统计 provider exception"，也没有业务消费者要求新 enum。 |

DS 对 pre-existing shared-close wall-clock test 的 CI timing 备注，以及第二轮 abandon error backoff 缺少专门独立测试的备注，均未给出 R05-S1 可达 correctness defect。Controller 将其归为 review notes 不进入 accepted/deferred finding ledger，合理。

无漏掉可达 defect。

#### 3.2.11 Validation/coverage/Ruff/pyright/source evidence 是否可信

**结论：可信，无 finding。**

本次 re-review 独立重跑验证：

| 门禁 | 命令 | 结果 |
|---|---|---|
| owner nodes（7 个） | `pytest 3 new owner + 2 durable preservation + 2 more` | `7 passed in 0.40s` |
| focused branch matrix minus owner（12 个） | `pytest 12 nodes` | `12 passed in 0.45s` |
| four Host focused files | `pytest test_wait_observation_runner.py test_wait_adapter_polling.py test_phase7_waiting_integration.py test_wait_record_state.py` | `69 passed in 0.93s` |
| pyright changed production files | `pyright dayu/host/wait_adapter.py dayu/host/durable/state.py` | `0 errors, 0 warnings, 0 informations` |
| Ruff changed files | `ruff check 8 changed Python files` | `All checks passed!` |
| invalid symbol guard | `rg mark_wait_record_poll_abandon_timeout\|_MarkWaitRecordAbandonTimeoutOperation dayu tests` | PASS（exit 1，零匹配） |
| no-diff audit | `git diff --exit-code ... -- schema.py _wait_observation.py waiting.py agent.py dispatch.py engine_ingest.py` | PASS |
| security scan | `git diff --unified=0 ... \| rg authorization\|permission\|...` | PASS（exit 1，零命中） |
| git diff --check | `git diff --check` | PASS |
| scheduler close probe | `pytest workspace/tmp/test_r05_scheduler_close_probe.py` | `1 passed in 0.31s` |
| scheduler test R05 symbol scan | `rg wait_adapter\|WaitPoller\|... test_dispatch_scheduler.py` | PASS（exit 1，零命中） |
| R04 config ownership | `rg awaiting_resolution_mode\|wait_poller_policy ...` | 精确匹配预期路径 |
| prohibited heuristic | `rg WaitPollerRuntimePolicy\(\) dayu tests utils` | PASS（exit 1，零命中） |

#### 3.2.12 Protected seven-path digest 复核

**结论：PASS。**

本次 re-review 独立执行：

```bash
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

与 accepted protected value、initial code review、zero-change fix artifact 创建前/后值精确一致。

#### 3.2.13 Zero-change proof 复核

**结论：可信。**

zero-change fix artifact（`docs/reviews/wu-semantic-ownership-01-r05-s1-code-review-fix-codex.md`）记录了创建前/后 protected digest、path-set digest、review evidence manifest digest、status digest 与 staged path count 均未漂移。Controller 独立复核并确认。

本次 re-review 验证当前 working-tree 状态与 zero-change fix artifact 记录一致：

- actual changed production list 精确为 `dayu/host/durable/state.py`、`dayu/host/wait_adapter.py`。
- 七路径 protected digest 未变。
- `git diff --check` PASS。
- 全部 no-diff owners 未变化。

zero-change fix 没有修改任何 product、test、design、control、plan 或既有 artifact；只新增了 fix record artifact。

#### 3.2.14 Scheduler close residual 是否仍未修、未掩盖、未 waive

**结论：正确，无 finding。**

- `dispatch.py`、`engine_ingest.py`、`test_dispatch_scheduler.py` 相对 fixed plan base 均 no diff。
- R05 owner symbols 对 `test_dispatch_scheduler.py` 零命中。
- 确定性 probe `workspace/tmp/test_r05_scheduler_close_probe.py` 仍 `1 passed in 0.31s`，证明 close gate → clean EOF terminal closeout → promotion wake rejection 缺口仍可确定性复现。
- R05-S1 没有误修、掩盖或引入新的 scheduler 传播。
- 正确 classification 保持 RETAINED RESIDUAL：独立 Host scheduler lifecycle owner；未修、未 waive、未建 issue、未归 Issue 175；destination 需 Controller / 用户另行裁决。

## 4. Reviewed evidence 列表

1. `AGENTS.md` — 完整读取。
2. `docs/host/issues-implementation-control.md` — R05 gate 状态核对。
3. `docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md` — 完整读取。
4. `docs/reviews/wu-semantic-ownership-01-r05-s1-implementation-codex.md` — 完整读取。
5. `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-continuation-codex.md` — 完整读取。
6. `docs/reviews/wu-semantic-ownership-01-r05-s1-controller-validation.md` — 完整读取。
7. `docs/reviews/wu-semantic-ownership-01-r05-s1-code-review-mimo.md` — 完整读取。
8. `docs/reviews/wu-semantic-ownership-01-r05-s1-code-review-ds.md` — 完整读取。
9. `docs/reviews/wu-semantic-ownership-01-r05-s1-code-review-controller-adjudication.md` — 完整读取。
10. `docs/reviews/wu-semantic-ownership-01-r05-s1-code-review-fix-codex.md` — 完整读取。
11. `docs/reviews/wu-semantic-ownership-01-r05-s1-code-review-fix-controller-validation.md` — 完整读取。
12. `dayu/host/wait_adapter.py` — 完整 diff 与关键路径全文阅读（poll timeout 分支 `1072-1085`、abandon timeout 分支 `1320-1334`、`_release_with_backoff` `1455-1495`、`_backoff_delay_seconds` `1873-1889`、`_resolve_claimed_wait` `1406-1453`、`_abandon_cancelled_wait` `1233-1357`）。
13. `dayu/host/durable/state.py` — 完整 diff 与关键路径全文阅读（`release_wait_record_poll_claim` `2589-2659`、`mark_wait_record_poll_abandoned` `2662-2724`、已删除 `mark_wait_record_poll_abandon_timeout` 位置确认）。
14. `docs/host/design.md` — 精确 diff 核对（2429-2432 行）。
15. `tests/host/test_wait_observation_runner.py` — 完整 diff 与新测试全文阅读。
16. `tests/host/test_wait_adapter_polling.py` — 完整 diff 与修改测试全文阅读。
17. `tests/host/test_phase7_waiting_integration.py` — 完整 diff 与新测试全文阅读。
18. `tests/host/test_wait_record_state.py` — 完整 diff 与新测试全文阅读。
19. `dayu/host/_wait_observation.py` — no-diff 验证 + token/fence 机制全文阅读（`observe` `200-220`、`_invalidate_token` `319-334`、`_publish` `336-361`）。
20. `dayu/host/waiting.py` — no-diff 验证。
21. `dayu/host/durable/schema.py` — no-diff 验证。
22. `dayu/engine/agent.py` — no-diff 验证。
23. `tests/host/test_dispatch_scheduler.py` — R05 symbol 零命中验证。
24. `workspace/tmp/test_r05_scheduler_close_probe.py` — 确定性 probe 运行验证。

## 5. Retained safety 确认

| 安全机制 | 状态 | 验证方式 |
|---|---|---|
| late publication token/generation fence | 保留 | `_wait_observation.py` no diff + `test_timeout_invalidates_token_and_late_result_cannot_publish` 通过 |
| outstanding capacity / shared close deadline | 保留 | `test_supervisor_close_uses_one_shared_deadline_and_stays_closing` 通过 |
| claim token CAS / release backoff / next-due claimability | 保留 | `test_active_poll_claim_suppresses_second_poller_adapter_call` + `test_expired_poll_claim_allows_retry` 通过 |
| authoritative typed lost via common resolver | 保留 | `test_poll_adapter_lost_result_closes_run` 通过 + idempotency key 断言 |
| explicit applied/unsupported/noop terminal marker | 保留 | `test_cancelled_poll_wait_is_abandoned_once_without_resolve` + `test_poll_abandon_success_marks_row_and_clears_claim` 通过 |
| invalid timeout-only symbol 零残留 | 确认 | `rg` 零匹配 |
| R04 config ownership / 12-field snapshot | 保留 | R04 preservation tests 通过 |
| cancellation / close-drain / capacity | 保留 | focused matrix 通过 |

## 6. Deferred scope 确认

以下 scope 均未在本 S1 diff 中实现或偷带：

- Issue 175（process isolation / process-backed containment）
- callback transport
- unified authorization/permission schema
- future cancelled-abandon durable evidence policy
- future explicit Host LOST durable evidence policy
- R05-S2（Engine regression / public smoke / README acceptance）
- R06+ semantic ownership remediation

## 7. Residual owners

| Residual | Owner | 状态 |
|---|---|---|
| scheduler close / terminal promotion coordination | Host scheduler lifecycle owner（非 R05 timeout owner） | 已定位、未修、未 waive、未建 issue、未归 Issue 175；确定性 probe 可复现；corrected coverage 只与其解耦 |
| CANCELLED abandon 若 provider 永不返回 explicit terminal outcome | future Host durable evidence policy owner | 当前 claim CAS、finite timeout、capacity cap、late-result fence 与 backoff cap 只限制资源，不创造 terminal evidence |
| Issue 175 | 独立 GitHub Issue | 不由 R05 实现 |
| callback transport / unified authorization / R06+ | 各自独立 WU/issue | 零实现 |

## 8. Finding ledger 汇总

| 分类 | 数量 | 状态 |
|---|---:|---|
| accepted current finding | 0 | CLOSED |
| rejected-as-finding observation（从 DS 初始 review 继承） | 1 | `ADAPTER_ERROR` aggregation 没有当前 defect |
| retained residual（从 DS 初始 review 继承） | 1 | future Host durable evidence policy |
| blocker | 0 | NONE |

历史 `R05-PF-01..04`、`R05-PRR-F01`、`R05-S1-VAL-PD-F01`、`R05-S1-VAL-CV-F01` 保持关闭。Scheduler close / terminal promotion coordination 继续是 ledger 之外的独立 Host scheduler lifecycle residual。

## 9. 最终裁决

**PASS / 无 material finding / 无 required fix gate。**

R05-S1 的产品 transaction 精确落在 semantic owner boundary：`WaitPoller` 把 poll/cancelled-abandon observation timeout 解释为 poll-local transient diagnostic + claim release/backoff；durable state 删除 invalid timeout-only terminal primitive；Host design 真源同步纠正；owner tests 覆盖 late publication、retry、typed lost 与 explicit lifecycle terminal。没有 schema、Engine、scheduler、Service、config、README 或 deferred scope 修改。

两路 code review 均为 PASS / zero material finding。Controller 裁决 zero-change fix。本 re-review 确认全部 evidence chain 可信、protected target 未漂移、安全/deferred boundary 未漂移、scheduler residual 未被修复或掩盖。

本 review verdict 不独立授权 commit；Controller 必须裁决全部 findings（本路为零 finding），并决定是否需要第二路 AgentDS re-review 或可直接推进。

---

**Reviewer**: AgentMiMo
**Date**: 2026-07-15
**Review type**: zero-change fix 后第一路完整 adversarial re-review
**Reviewed digest**: `3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2`
