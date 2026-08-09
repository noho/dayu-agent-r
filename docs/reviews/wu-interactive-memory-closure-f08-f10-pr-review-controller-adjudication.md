# Interactive Conversation Memory Closure F08–F10：PR review 总控裁决

## Gate identity

- Gate：Gateflow PR review → fix → re-review → accepted PR review checkpoint。
- Work unit：修复 Interactive Conversation Memory closure 的 F08–F10。
- PR：PR 190，`https://github.com/noho/dayu-agent-r/pull/190`。
- Reviewed implementation/artifact head：`72b7f14515d58ee3f1cc6ad9a7a48a108d165c21`。
- Base：`main` @ `113ea34d47b95812d79aa31705949bbb46bc6061`。
- 总控裁决：**PASS**。唯一 accepted finding `PR-BODY-01` 已修复；production/test accepted findings 为零；
  没有 blocking open question、deferred finding 或 unclassified residual risk。
- Current next entry point：创建 accepted PR review commit，normal push，然后进入 `draft-PR-pass`。

## Durable PR review chain

- AgentMiMo 独立 PR review：
  `docs/reviews/wu-interactive-memory-closure-f08-f10-pr-review-mimo.md`
- AgentDS 独立 PR review：
  `docs/reviews/wu-interactive-memory-closure-f08-f10-pr-review-ds.md`
- AgentCodex deepreview artifact：
  `docs/reviews/pr-190-review-20260804-201303.md`
- AgentCodex fix/audit：
  `docs/reviews/wu-interactive-memory-closure-f08-f10-pr-review-fix-codex.md`
- AgentMiMo 独立 PR re-review：
  `docs/reviews/wu-interactive-memory-closure-f08-f10-pr-rereview-mimo.md`
- AgentDS 独立 PR re-review：
  `docs/reviews/wu-interactive-memory-closure-f08-f10-pr-rereview-ds.md`

总控逐项读取两路 review、Codex fix/audit、两路 re-review、当前 PR body/metadata 和相关 owner tests；以下裁决不以
reviewer 的 PASS 结论替代直接证据。

## Finding status

### PR-BODY-01：draft PR summary 与真实 head 漂移

- 原状态：accepted，中严重度。
- 根因：PR 190 body 的 exact-head、测试数字和 review status 仍指向 prior F01–F07 checkpoint `58aeb7b...`，没有准确
  呈现 remote head `72b7f145...` 已包含的 F08–F10、其 evidence boundary 和五条明确未运行 scenarios。
- Fix：AgentCodex 仅更新 PR body；保留 F01–F07 历史 bundle/evidence，单独记录 F08–F10 owner validation、frozen
  digests、no-checks 状态、out-of-scope active-cancel observation 和后续 Oracle obligations。
- External-state safety：未改变 title、OPEN/draft、base/head、reviewDecision、mergeability；未 comment、approve、request
  changes、mark ready、merge 或 request reviewers。
- 写后 body SHA-256：`ee97bf6818801fb5585d784a5273f0ed7afa3dae3f35df79faf6576ec32493c8`。
- MiMo re-review：**已修复**。
- DS re-review：**已修复**。
- 总控最终状态：**已修复**。

### DS-OQ-1：单标点 summary 仍可通过 deterministic Host shape validation

- 裁决：`rejected-with-reason`；最终状态：**证据失效**。
- 机械观察成立，但它不是当前 code contract gap。Frozen owner boundary 明确要求 prompt 以自足业务语言禁止 placeholder，
  同时禁止 Host 发明字符阈值、关键词黑名单或任意自然语言 semantic verifier。Host 只拥有 typed shape/cap/coverage；真实
  provider 的 meaningful/null 遵从性由后续 `interactive.interactive.g06.summary-null` evidence gate 观察。
- 把“`.` 是否有业务语义”硬编码为 deterministic accept/reject 会违反本 work unit 明确 non-goal，并产生另一个错误 owner。

### DS-OQ-2：F09 缺少 recorder → public resolver owner E2E

- 裁决：`rejected-with-reason`；最终状态：**证据失效**。
- 直接证据：`tests/host/test_dispatch_scheduler.py` 的 `_resolve_and_assert_compactor_calls` 明确执行
  `catch_up_tool_trace_projection` → `read_runner_call_reconstruction_signals_by_run` →
  `resolve_runner_call_projection_from_signal`，逐字段核对 canonical EventLog row、hot identity、manifest descriptor、
  input/output projection、provider/model/attempt/response identity。
- 路径覆盖：success、invalid repair 后 success、exhausted fallback；另由 Tool Trace query test 验证 event-row/hot identity
  mismatch fail closed。MiMo/DS re-review 均直接走读该链并确认。

### DS-OQ-3：`CompactRepairFeedbackV2.to_json()` 可能泄漏治理 digest 给 LLM

- 裁决：`rejected-with-reason`；最终状态：**证据失效**。
- `to_json()` 是 durable/internal serialization，进入 derived durable projection；唯一 LLM repair projection 使用
  `_repair_feedback_prompt_json_vnext`，只输出脱敏、自解释的 validation feedback，不包含 `request_digest` 或
  `source_boundary_digest`。当前没有误用调用路径；仅为未来可能误用重命名 public method 会扩大无需求变更。

### DS-OQ-4：provenance multiset / event-id collision 理论攻击面

- 裁决：`rejected-with-reason`；最终状态：**证据失效**。
- selected proof 比较保留 cardinality、refs 和 packed-content digest；frozen block proof 要求 block id 唯一；EventLog
  `event_id` 有数据库 unique identity，identity conflict fail closed。没有当前 producer 或 caller 能构造“改变 durable truth
  又通过 provider 前 barrier”的可达反例。

### DS-A/B/C aggregate observations

| Item | 总控裁决 | Re-review final status | Direct owner reason |
|---|---|---|---|
| previous view 不在 selected raw proof | `rejected-with-reason` | 证据失效 | previous typed pair 与本轮 raw delta 是不同 owner；加入 selected proof 会使合法 request 假阳性 |
| budget acceptance helper 恒真 | `rejected-with-reason` | 证据失效 | 既有 proactive/reactive hard-threshold contract，早于本 WU，不是待实现 conditional |
| recorder 内建 `PayloadStore` | `rejected-with-reason` | 证据失效 | store 无实例状态且不拥有 identity；同 transaction 的 descriptor/ref/digest 是唯一真源 |

## F08–F10 PR verdict

| Finding | 唯一 owner | Final status |
|---|---|---|
| F08 meaningful summary/null | conversation compaction prompt；typed shape/cap/coverage 为 Host Context Governance；accepted null projection 为 Memory | **已修复**；prompt 自足禁止 placeholder，null 清除 prior summary 且不影响其它四类 memory，无 Host NL heuristic |
| F09 Tool Trace hot identity | Host compactor runner-call manifest/EventLog append boundary、Tool Trace projector、formal resolver | **已修复**；descriptor/EventLog/hot/resolver 同源，success/repair/exhaust/mismatch owner E2E 通过 |
| F10 turn-group atomicity / feedback binding | Host material selector、pipeline frozen snapshot、proactive scheduler、operation accept boundary | **已修复**；group 原子、strict-prefix bounded、root/transient exact partition、双 digest feedback binding、single terminal 均在 owner 生效 |

没有 downstream Memory/UI/CLI/test-fixture compensation，没有 compatibility alias/wrapper、loose parsing、old schema read、
public schema expansion 或新的 semantic owner。

## Validation adjudication

- AgentCodex focused owner suite（11 files）：`489 passed, 1 skipped, 3 warnings`。
- MiMo re-review focused owner suite：`443 passed`。
- DS re-review：直接走读 F09 四路径 E2E 和 PR external state；没有修改代码或运行被禁止 scenarios。
- Accepted aggregate full pytest：最终 `6639 passed, 10 skipped, 6 deselected`；首轮 active-cancel timing observation 已隔离
  并分类，后续完整 suite 绿色。
- Accepted Host owner suite：`2385 passed, 1 skipped, 6 deselected`。
- Accepted focused coverage：`418 passed, 1 skipped`；六个 changed Host files 均 ≥80%，合计 85%。
- Full pyright：`0 errors, 0 warnings, 0 informations`。
- Ruff、compileall、JSON validation、frozen hashes、`git diff --check`：通过。
- GitHub checks：zero/no checks；明确不表述为 GitHub CI pass。
- 五条正式 CLI scenarios：未运行；owner tests 不冒充正式 real-provider conformance evidence。

## Frozen baseline integrity

- `docs/cli_ci_oracles.json`：
  `da04923193a04c0e33eca9c60e0d8eb919b74963b2c2f4170954be2f07261201`
- `docs/cli_ci_scenarios.json`：
  `7c991d14ebc79f9f8e8c66d9eb94c10156c5a36eecd3bb11df24ed18cbca2093`
- `docs/reviews/wu-interactive-memory-closure-f08-f10.md`：
  `95a09543fc7f1a2a09f99dbe2c2c014e71ac22f2c386dc5364f6a1a2d14b1b08`

三份 digest 与 accepted-plan checkpoint 一致，PR review/fix/re-review 未改写 baseline。

## Residual risk disposition

- 五条正式 CLI scenarios/readiness proof：`covered by later approved evidence/readiness gate`，owner=Oracle 总控。
- F08 real-provider 对 meaningful/null prompt 的稳定遵从性：同上，由
  `interactive.interactive.g06.summary-null` 覆盖，不是 current code finding。
- active-cancel 非确定性时序：`assigned to later work unit if recurrence`，owner=`open_host` active-cancel runtime/test。
- Legacy compactor 若未来不实现 prepared-manifest protocol：conditional limitation；由选择该实现的 future work unit 拥有，
  当前 production 正式 path 无 gap。
- GitHub checks 为零：`requiring explicit user decision at later merge/readiness`；本 draft gate 只记录事实。
- DS-A/B/C/OQ-1..4：均已 `rejected-with-reason`，不登记 deferred correctness risk。

没有 unclassified residual risk；没有需要当前用户决策的 blocker。

## Docs and external-state decision

- Production/tests/design/README 不需再修改；PR body 是本 gate 唯一 accepted external-state fix。
- PR 190 当前仍 OPEN draft，title/base/head branch/reviewDecision 未被 review loop 改变。
- accepted PR review commit 仅包含七份 PR review/fix/re-review/controller artifacts；随后 normal push。

## Completion status

PR review loop **PASS**。`PR-BODY-01` 最终状态为已修复，其余 review observations 证据失效；F08–F10 均为已修复。
当前可创建 accepted PR review commit；尚未 push 该 checkpoint，尚未进入 `draft-PR-pass` 或 final closeout。
