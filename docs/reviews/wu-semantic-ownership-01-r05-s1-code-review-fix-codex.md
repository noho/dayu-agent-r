# WU-SEMANTIC-OWNERSHIP-01 R05-S1 Code Review Fix — AgentCodex Zero-Change Record

## 1. Gate identity、第一性原理与结论

| 项目 | 值 |
|---|---|
| umbrella | `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation |
| sub-WU | 既有 `R05-S1`；不是新 WU、feature 或 issue |
| gate | `R05-S1 code-review zero-change fix record` |
| fixed plan base | `5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1` |
| validation-resume HEAD | `2c068869843837546e6c6bc0a5285918b01d8b29` |
| Controller verdict | `PASS_WITH_ZERO_ACCEPTED_FINDING / ZERO_CHANGE_FIX_RECORD_REQUIRED` |
| accepted current finding | `0` |
| rejected-as-finding observation | `1` |
| retained residual | `1` |
| blocker | `0` |
| 唯一 write allowlist | `docs/reviews/wu-semantic-ownership-01-r05-s1-code-review-fix-codex.md` |
| completion status | `STOPPED_FOR_CONTROLLER_VALIDATION` |

本 gate 的流程动机成立，但不存在产品或测试 defect 可修。两路完整 code review 均为 PASS / zero material finding，Controller 的最终 ledger 也明确 accepted current finding 为零。若修改 product、test、design、README、plan、control 或既有 artifact，就会把 observation 或 residual 擅自升级成当前业务事实，越过 `WaitPoller`、durable state、future Host durable evidence policy 与 Host scheduler lifecycle 各自的 owner boundary。

因此正确 fix 是零产品变更：只持久化两路 review 与 Controller disposition，并用创建前后 digest、路径集合和 status 证明受保护 transaction 未漂移。本轮未 stage、commit、push；未进入 R05-S2、scheduler fix、Issue 175、callback transport、统一 authorization、R06-R12、aggregate 或 PR gate。

## 2. 完整读取与证据范围

本记录完整读取并交叉核对：

1. `AGENTS.md`；
2. `docs/host/issues-implementation-control.md`；
3. `docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md`；
4. `docs/reviews/wu-semantic-ownership-01-r05-s1-implementation-codex.md`；
5. `docs/reviews/wu-semantic-ownership-01-r05-s1-validation-continuation-codex.md`；
6. `docs/reviews/wu-semantic-ownership-01-r05-s1-controller-validation.md`；
7. `docs/reviews/wu-semantic-ownership-01-r05-s1-code-review-mimo.md`；
8. `docs/reviews/wu-semantic-ownership-01-r05-s1-code-review-ds.md`；
9. `docs/reviews/wu-semantic-ownership-01-r05-s1-code-review-controller-adjudication.md`；
10. 当前七路径 product/test/design transaction、no-diff owners 与 retained-safety source anchors。

直接证据继续支持同一 owner 判定：`WaitPoller` 拥有 observation timeout 的 transient diagnostic 与 release/backoff 解释，`release_wait_record_poll_claim(...)` 拥有 durable 原子 projection，`WaitObservationRunner` 独占 late-publication authority，typed LOST 与 explicit lifecycle terminal outcome 保留各自 owner。没有要求当前 gate 修改任一 owner 的新证据。

## 3. 两路 review 与 Controller finding ledger

### 3.1 AgentMiMo

AgentMiMo verdict 为 `PASS / 无 material finding`。其完整 review 覆盖七路径 diff、root cause、两条 timeout transition、计数、claim CAS、backoff、late publication、authoritative typed LOST、explicit lifecycle terminal、durable primitive 删除、owner tests、类型/docstring、coupling、retained safety、deferred scope、scheduler residual 与既有验证证据；未提出需要修改 product、test、design 或 README 的 finding。

### 3.2 AgentDS

AgentDS verdict 为 `PASS — zero material finding, two observations`。两条 observation 的 Controller disposition 如实保留：

| observation | Controller disposition | 本 gate 动作 |
|---|---|---|
| `CANCELLED` wait 在 provider 永不返回 explicit lifecycle terminal outcome 时按 capped backoff 长期重试，deadline expiry 不进入非-CANCELLED boundary handler | `RETAINED_RESIDUAL / NO_R05-S1_FIX`；owner 是 future Host durable evidence policy | 不创造 terminal evidence，不在 R05-S1、R05-S2 或 scheduler residual 中旁路实现 |
| poll observation timeout 复用 `WaitPollLastOutcome.ADAPTER_ERROR`，supervisor `adapter_errors` 未拆分 timeout | `NO_CURRENT_DEFECT / NO_FIX`；durable `poll_last_error_code=wait_observation_timeout` 已区分根因，当前 contract 未承诺该聚合只统计 provider exception | 作为 `rejected-as-finding observation` 留痕；不新增 enum/schema/default |

DS 对 shared-close wall-clock test 的 CI timing 备注，以及第二轮 abandon error backoff 缺少专门独立测试的备注，均未提供当前可达 correctness defect；Controller 将其保留为 review notes，不进入 accepted/deferred finding ledger。

### 3.3 Controller final ledger

| 分类 | 数量 | 状态 |
|---|---:|---|
| accepted current finding | `0` | `CLOSED` |
| rejected-as-finding observation | `1` | `ADAPTER_ERROR` aggregation 没有当前 defect |
| retained residual | `1` | future Host durable evidence policy |
| blocker | `0` | `NONE` |

历史 `R05-PF-01..04`、`R05-PRR-F01`、`R05-S1-VAL-PD-F01` 与 `R05-S1-VAL-CV-F01` 保持关闭。Scheduler close / terminal promotion coordination 是上述 ledger 之外的独立 Host scheduler lifecycle residual；未修、未 waive、未建 issue、未归 Issue 175。

## 4. 创建前冻结

### 4.1 Identity 与七路径 protected digest

创建前 branch 为 `phaseflow/host-issues-control`，HEAD 为 `2c068869843837546e6c6bc0a5285918b01d8b29`，本 artifact 不存在。

七个受保护路径精确为：

1. `dayu/host/durable/state.py`
2. `dayu/host/wait_adapter.py`
3. `docs/host/design.md`
4. `tests/host/test_phase7_waiting_integration.py`
5. `tests/host/test_wait_adapter_polling.py`
6. `tests/host/test_wait_observation_runner.py`
7. `tests/host/test_wait_record_state.py`

执行 `git diff --binary -- <seven paths> | shasum -a 256`，创建前 digest 为：

```text
3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2
```

`git diff --name-only -- dayu tests docs/host/design.md` 与相对 fixed plan base 的同范围命令均精确返回上述七路径；path-set digest 为：

```text
5a4e4782db79c7d1e3ea41261cae42d246760f9b6e61efd9583d485e71faecf9
```

### 4.2 Review evidence chain

创建前 evidence chain SHA-256：

| artifact | SHA-256 |
|---|---|
| R05 plan | `5683ecca22c7af75c9ba9743eeee98748dcffafbe3fb1e8199e265d4f8b2146c` |
| implementation | `b8ec89aafc6008587791958cb356f0124cec76199959f2ea3b62272ee3496732` |
| validation continuation | `baaea96ac51c1e3cf44047372bbf43403cb3d7d4030c0c06a362f49dafda2758` |
| Controller validation | `fc391e13017e4e8a93e0ae670e830e85c3afbf541427823a55cee3ff28c45fe1` |
| AgentMiMo code review | `2be67f6313bcff32ce7608e6432569019618f30d9f7ac3889303091007f653e8` |
| AgentDS code review | `1049918158f1be2260f145aa0e030c76ee926c5107dc5f67795001154eda4e20` |
| Controller code-review adjudication | `1a4e9787bc5cbce51719b8efec6bcac3e778ea30e193cc36061a8f9312c576ad` |

上述有序 `shasum` manifest 自身 digest 为：

```text
cc065f20a816f679ae885e8ed110a1bf3e3786c6785c0c2a675be6added35542
```

### 4.3 Working-tree status

创建前 `git status --short` 精确为 `14` 条：

```text
 M dayu/host/durable/state.py
 M dayu/host/wait_adapter.py
 M docs/host/design.md
 M docs/host/issues-implementation-control.md
 M tests/host/test_phase7_waiting_integration.py
 M tests/host/test_wait_adapter_polling.py
 M tests/host/test_wait_observation_runner.py
 M tests/host/test_wait_record_state.py
?? docs/reviews/wu-semantic-ownership-01-r05-s1-code-review-controller-adjudication.md
?? docs/reviews/wu-semantic-ownership-01-r05-s1-code-review-ds.md
?? docs/reviews/wu-semantic-ownership-01-r05-s1-code-review-mimo.md
?? docs/reviews/wu-semantic-ownership-01-r05-s1-controller-validation.md
?? docs/reviews/wu-semantic-ownership-01-r05-s1-implementation-codex.md
?? docs/reviews/wu-semantic-ownership-01-r05-s1-validation-continuation-codex.md
```

其 canonical status digest 为：

```text
b2bf75c047291516e045612b386869b312e8db0b3e89182959d3ab7688a8c256
```

创建前 staged path count 为 `0`。

## 5. 创建后 zero-change 证明

创建本 artifact 后立即复算，结果如下：

| protected target | 创建前 | 创建后 | 结论 |
|---|---|---|---|
| seven-path binary diff digest | `3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2` | `3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2` | identical / PASS |
| product/test/design path-set digest | `5a4e4782db79c7d1e3ea41261cae42d246760f9b6e61efd9583d485e71faecf9` | `5a4e4782db79c7d1e3ea41261cae42d246760f9b6e61efd9583d485e71faecf9` | identical / PASS |
| review evidence manifest digest | `cc065f20a816f679ae885e8ed110a1bf3e3786c6785c0c2a675be6added35542` | `cc065f20a816f679ae885e8ed110a1bf3e3786c6785c0c2a675be6added35542` | identical / PASS |
| status 排除本 artifact | `14` 条；`b2bf75c047291516e045612b386869b312e8db0b3e89182959d3ab7688a8c256` | `14` 条；`b2bf75c047291516e045612b386869b312e8db0b3e89182959d3ab7688a8c256` | identical / PASS |
| staged paths | `0` | `0` | identical / PASS |

创建后 full `git status --short` 为 `15` 条，full status digest 为：

```text
b8933e1f89a55fa89bee304f4a576247213bb47f5b80f0657892bc01dab7d732
```

相对 §4.3 的 `14` 条状态只新增：

```text
?? docs/reviews/wu-semantic-ownership-01-r05-s1-code-review-fix-codex.md
```

七份 evidence chain 的逐文件 SHA-256 也逐项与 §4.2 相同；不是仅靠 manifest 总值推断。`git diff --check` 创建后 exit `0`。由于普通 `git diff --check` 不检查 untracked file，另执行：

```bash
git diff --no-index --check /dev/null \
  docs/reviews/wu-semantic-ownership-01-r05-s1-code-review-fix-codex.md
```

命令 exit `1` 只表示新文件相对 `/dev/null` 存在内容差异，且无 whitespace diagnostic；本 artifact whitespace check PASS。

因此创建前后受保护 content、product/test/design path 集合、review evidence chain 与既有 working-tree status 均未变化；唯一 delta 是新增本 zero-change artifact。

## 6. Source、allowlist、安全与 deferred-scope 复核

| 检查 | 结果 |
|---|---|
| `git diff --check` | 创建前 exit `0`；创建后结果见 §5 |
| 七路径 allowlist | current product/test/design path set 精确为 §4.1 七路径 |
| invalid timeout-only symbols | `mark_wait_record_poll_abandon_timeout` / `_MarkWaitRecordAbandonTimeoutOperation` 对 `dayu tests` 零命中，`rg` exit `1` / PASS |
| no-diff owners | `_wait_observation.py`、`waiting.py`、`agent.py`、durable schema、`dispatch.py`、`engine_ingest.py`、scheduler owner test 相对 fixed base 全部 empty diff / PASS |
| publication fence | token state、generation、single-slot result queue、`_invalidate_token` 与 `_publish` anchors 均仍由 `_wait_observation.py` 拥有；owner test anchor 保留 |
| claim/backoff 真源 | 两条 timeout branch 仍复用 `_release_with_backoff`；该 helper 唯一调用 `_backoff_delay_seconds`，durable projection 仍复用 `release_wait_record_poll_claim` |
| terminal preservation | `WaitPollLost(ResolveWaitLostOutcome)` 与 `mark_wait_record_poll_abandoned`、applied/unsupported/noop lifecycle types 及 owner tests 均保留 |
| retained safety tests | token invalidation、shared close deadline、active/expired claim、invalid deadline、typed LOST、explicit abandon terminal 的 test symbols 均存在；本 gate不重跑测试 |
| scheduler R05 symbol scan | `test_dispatch_scheduler.py` 对 R05 owner symbols 零命中，`rg` exit `1` / PASS |
| scheduler owner paths | `dispatch.py`、`engine_ingest.py` 与 scheduler owner test 相对 fixed base empty diff / PASS |
| scheduler deterministic probe | probe SHA-256 仍为 `e267d059419259b28a71e9b37643853a53e4b43d4b8d6ca80339b2c58ead42e8`；只引用 continuation / Controller / reviewer 已通过的 `1 passed` 证据，本 gate未重跑 |
| deferred added-lines scan | production diff 对 authorization、permission、callback transport、process isolation、process-backed/subprocess、Issue 175 零命中，`rg` exit `1` / PASS |
| R05-S2 / README / config / Service / Fins | accepted deferred paths相对 fixed base empty diff / PASS |
| staged paths | 创建前为 `0`；创建后结果见 §5 |

这些 source-level 复核没有把 scheduler residual 解释为修复、waiver、flake 或 inherited pass，也没有把 future durable-evidence residual 投影为当前 terminal business fact。

## 7. 既有 validation evidence 与 README decision

本 gate没有重跑 product tests、coverage、pyright 或 Ruff，也不声称新的 full Host coverage。以下只引用受七路径 protected digest 保护、已由 Agent 与 Controller 独立通过的既有 evidence：

- owner nodes `3 passed`，durable preservation `4 passed`，focused branch matrix `19 passed`，四个 Host files `69 passed`；
- R04 config/composition preservation `35 passed, 3 warnings`；aggregate functional matrix `359 passed, 3 warnings`，Controller 独立重跑同为 `359 passed, 3 warnings`；
- corrected changed-owner coverage session `1830 passed, 2 skipped, 5 deselected`，只排除 plan 允许的两个独立 owner test files；`state.py=83%`、`wait_adapter.py=86%`，两个逐文件 `--fail-under=80` 均通过；
- Agent 与 Controller full pyright 均为 `0 errors, 0 warnings, 0 informations`；changed-file Ruff 均 `All checks passed!`；
- full Ruff registry 从 fixed base `167` 精确变为 `165`，`added=[]`，removed 只有两个 planned touched-file F401。

README decision 保持不变：本 gate 没有产品、测试 contract、用户入口、分层或装配变化，且唯一 write allowlist 禁止 README 修改；R05-S1 不更新 README，Host/tests README final acceptance 仍属于 later approved R05-S2。本记录不进入 R05-S2。

## 8. Residual risks 与 owner boundary

| residual | owner / destination | 当前 disposition |
|---|---|---|
| CANCELLED abandon 永久缺少 authoritative terminal evidence | future Host durable evidence policy | retained；当前 claim CAS、finite timeout、capacity、late-result fence 与 capped backoff 只限制资源，不创造终止证据 |
| scheduler close / terminal promotion coordination | 独立 Host scheduler lifecycle owner | retained outside DS observation ledger；未修、未 waive、未建 issue、未归 Issue 175；destination 只能由 Controller / 用户另行裁决 |
| R05-S2 Engine regression/public smoke 与 Host/tests README final acceptance | accepted later R05-S2 gate | pending；本 gate零实现 |
| Issue 175 process-backed containment | existing Issue 175 | 与 scheduler residual、future durable evidence policy 都是不同 owner；本 gate零实现 |
| callback transport、统一 authorization、R06+ | 各自 later WU / issue | 本 gate零实现 |

没有 unclassified R05-S1 current finding，没有 blocker，也没有授权本 gate修复的产品风险。

## 9. 下一 gate 与 stop status

本 zero-change record 完成后，下一步只能是 **Controller validation**。Controller 必须复核创建前后 protected digest、path/status proof、完整 review ledger、两条 observation disposition、retained safety、scheduler residual 与 deferred boundaries。

只有 Controller validation PASS 后，才进入 AgentMiMo / AgentDS **双路完整 R05-S1 code re-review**。两路必须重新审查七路径完整 transaction、完整 evidence chain、Controller observation disposition、protected target 不变、安全/deferred boundary 未漂移，以及 scheduler residual 未被修复或掩盖。Reviewer verdict 不独立授权 commit；re-review 后仍须 Controller 最终裁决。

本轮停止于 `STOPPED_FOR_CONTROLLER_VALIDATION`。不得直接 commit，不得进入 R05-S2、aggregate、scheduler fix、Issue 175、callback、统一 authorization、R06-R12、push 或 PR。

Artifact path：`docs/reviews/wu-semantic-ownership-01-r05-s1-code-review-fix-codex.md`
