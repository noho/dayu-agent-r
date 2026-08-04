# Interactive Conversation Memory Closure F08–F10：final closeout

## Gate identity

- Gate：Gateflow final closeout。
- Work unit：修复 Interactive Conversation Memory closure 的 F08–F10。
- Branch：`codex/interactive-oracle`。
- PR：PR 190，`https://github.com/noho/dayu-agent-r/pull/190`。
- Draft-pass head：`3d51fb221ff2533705115ecac55439f9409bd3aa`。
- Decision：**final closeout PASS**。F08、F09、F10 均已修复；所有固定 Gateflow gates 和两路 review chain 完整；
  没有 blocking open question 或 unclassified residual risk。
- 本 summary 是最后一个 docs-only Gateflow artifact；其 commit/hash 与 push 后最新 PR head 在 external final closeout 中报告。

## Findings and semantic owners

### F08：meaningful session summary / null

- 最终状态：**已修复**。
- LLM-facing owner：`dayu/config/prompts/scenes/conversation_compaction_user.md`。
- Typed accept owner：Host Context Governance 的 schema/shape/cap/coverage barrier。
- Durable projection owner：accepted compact → Conversation Memory projector。
- 修复：prompt 自足要求 summary 至少是一条完整、可独立理解的业务陈述；明确禁止单字符/占位文本；当前明确 cap 无法
  容纳有意义摘要时输出 JSON `null`。Accepted `null` 保持完整 replacement 语义：清除 prior session summary，但不影响
  同一 candidate 的其它四类 Semantic Memory。
- 边界：Host 不发明字符阈值、关键词黑名单或自然语言 semantic verifier；真实 model 是否稳定遵从由后续 real-provider
  scenario 观察。
- 同源更新：workspace publication manifest/hash consumer 与 smoke hash test 同步；Memory owner test 锁定 null clear。

### F09：Compactor Tool Trace canonical/hot identity

- 最终状态：**已修复**。
- Canonical identity owner：Host compactor runner-call manifest/EventLog append boundary。
- Hot projection owner：Host Tool Trace projector。
- Consistency owner：formal Tool Trace public resolver。
- 修复：`DurableCompactorProposalManifestRecorder` 把同一 manifest descriptor 的 `payload_ref` 和 digest 写入 canonical
  EventLog row，同时从同一 descriptor 派生 hot projection/returned manifest reference；resolver 的 identity mismatch 继续
  fail closed，没有 compactor 特例或 private-SQLite 旁路。
- Owner E2E：真实 scheduler path 覆盖 recorder → catch-up → reconstruction query → formal resolver 的 success、repair 后
  success、exhausted fallback；另有 mismatch fail-closed test。

### F10：turn-group atomicity / feedback-request binding / root accept completeness

- 最终状态：**已修复**。
- Material/group owner：Host compact material builder/selector。
- Frozen source/provenance owner：Host compact pipeline。
- Feedback routing owner：Host proactive scheduler/dispatcher。
- Durable accept owner：Host compaction operation/Context Governance accept barrier。
- 修复：
  - 以完整 `host_run_id` turn group 为不可分割 atomic unit；collective exclusion 后按 strict-prefix item/char policy 选取，
    oversized group 不拆分、不越 cap、不跳过后续 unit；
  - root selection 保存稳定 `TurnGroupMembership` 与 per-block provenance；reactive transient pass 绑定 root digest，并要求
    exact non-overlapping partition；
  - repair feedback 携带 request digest 与 source-boundary digest；只在同一 immutable root request/boundary 复用，tier 或
    boundary 变化即清空；
  - operation 在 provider 前和 durable accept 前验证完整 root input、selected pack、pass partition、feedback binding 和 single
    terminal permit；late/stale result 不产生第二 canonical terminal。
- 没有增大 cap 掩盖问题，没有 Memory/UI/CLI/test fixture 下游补偿。

## PR review finding

- `PR-BODY-01`：**已修复**。PR body 曾把 prior F01–F07 exact-head/evidence 表述为当前状态；现已保留历史 evidence，同时
  分开记录 F08–F10 reviewed implementation、accepted PR review checkpoint、owner tests、no-checks 和五条未运行 scenarios。
- DS-OQ-1..4、DS-A/B/C：均 `rejected-with-reason`，两路 re-review final status 为`证据失效`；没有 deferred code finding。

## Gateflow commits

| Gate | Commit |
|---|---|
| accepted plan | `68ba403811fe98835ea93f8c715ca8ed7ba26164` |
| accepted F08 | `47b6a2af938dfd473572664f8c7da069533d97a0` |
| accepted F09 | `d04f7531f3a7bfef2de004afbb94b2d607704b36` |
| accepted F10 | `fd15b6601a985c538cdbe6a529af99d07c281a05` |
| accepted aggregate deepreview | `0c6410420f9d702b1b7b189f0c4e4a8b575c614c` |
| draft readiness | `bba998fbff5be8d843a6dbd3b90f7f014a5c87a1` |
| existing PR 190 reuse | `72b7f14515d58ee3f1cc6ad9a7a48a108d165c21` |
| accepted PR review | `da9a2d463dab5742ff3e853b63f0e71f50ee1733` |
| draft-PR-pass | `3d51fb221ff2533705115ecac55439f9409bd3aa` |

本 final closeout summary 的 commit 在提交后由 external closeout 追加报告，不重写上述历史。

## Validation

### Owner and integration tests

- F08–F10 focused owner suite（11 files）：`489 passed, 1 skipped`；skip 为 opt-in real-provider smoke。
- Host compaction/Tool Trace/Memory/RunInput/proactive owner suite：`2385 passed, 1 skipped, 6 deselected`。
- Aggregate coverage suite：`418 passed, 1 skipped`。
- PR re-review：MiMo `443 passed`；AgentCodex `489 passed, 1 skipped`；DS 独立走读四条 F09 formal-resolver paths。

### Full pytest and flaky classification

- 首轮：`6638 passed, 10 skipped, 6 deselected, 1 failed`；唯一失败为
  `test_open_host_active_cancel_watchdog_public_watch_observes_cancelled` 的非确定性 cancel/watchdog 时序。
- 该 node 独立/循环 6/6 通过；第二轮完整全仓：`6639 passed, 10 skipped, 6 deselected`，绿色。
- DS 独立 review 另观察同一 active-cancel 区域时序失败；相关 nodes 隔离 8/8 通过，且测试/owner 不在 F08–F10 diff。
- 分类：work-unit 外 timing observation；没有以 workaround、skip 或 assertion 放宽掩盖。

### Coverage and static checks

| File | Coverage |
|---|---:|
| `dayu/host/compact_material.py` | 86% |
| `dayu/host/compact_pipeline.py` | 92% |
| `dayu/host/compaction.py` | 84% |
| `dayu/host/compaction_operation.py` | 86% |
| `dayu/host/context_governance.py` | 89% |
| `dayu/host/dispatch.py` | 83% |
| aggregate | 85% |

- Full pyright（724 files）：`0 errors, 0 warnings, 0 informations`。
- Changed Python Ruff：通过。
- `python -m compileall -q dayu tests utils`：通过。
- `python -m json.tool`：oracle、scenario、workspace manifest 全部通过。
- `git diff --check`：通过。
- GitHub checks：zero/no checks；未声明 CI pass。

## Formal real-CLI evidence boundary

本 work unit 按用户明确 non-goal **没有**运行、补写或裁决以下五条正式 scenarios：

- `interactive.interactive.g06.summary-null`
- `interactive.interactive.g06.tool-trace-formal`
- `interactive.interactive.g06.turn-group-atomicity`
- `interactive.interactive.g06.drop-superseded`
- `interactive.interactive.g06.drop-policy-limit`

因此：

- 没有生成新的 post-fix observed-behavior report 或 readiness proof；
- 没有把 deterministic fixture、owner tests 或 public-resolver E2E 冒充 real-provider conformance evidence；
- frozen observed report 保持只读：
  `/Users/leo/workspace/.dayu-cli-ci/interactive-memory-closure-20260804T5X59S8/evidence/observed-behavior.md`，
  SHA-256 `ad64315116c3940d9b0e7354c9e2a38aeff75fa179af723a82e696ff55658263`；
- 后续新 immutable evidence bundle/digest 由 Oracle 总控运行五条正式 scenarios 时产生，本 work unit 不伪造 bundle path。

## Frozen Oracle baseline

- `docs/cli_ci_oracles.json`：
  `da04923193a04c0e33eca9c60e0d8eb919b74963b2c2f4170954be2f07261201`
- `docs/cli_ci_scenarios.json`：
  `7c991d14ebc79f9f8e8c66d9eb94c10156c5a36eecd3bb11df24ed18cbca2093`
- `docs/reviews/wu-interactive-memory-closure-f08-f10.md`：
  `95a09543fc7f1a2a09f99dbe2c2c014e71ac22f2c386dc5364f6a1a2d14b1b08`

三份 digest 与用户提供 baseline 精确相同；implementation、tests、review 和 PR body 均未改写 frozen Oracle/scenario/finding。

## Docs, prompt and README decisions

- Prompt：更新 `conversation_compaction_user.md` 的 meaningful/null 自足规则，并同步 workspace publication manifest/hash
  consumer。
- Host design：更新 `docs/host/design.md`，冻结 F09 canonical runner-call identity 与 F10 atomic/binding/accept contract。
- Engine design：`docs/engine/design.md` 不修改；直接代码证据表明 F08–F10 owner 均在 prompt/Host，不在 Engine。
- README：按自身 Agent 更新约束更新 `dayu/host/README.md` 与 `tests/README.md`。
- `dayu/config/README.md`、根 `README.md`、`dayu/README.md`：不命中其读者/职责变化，保持不变。
- 所有新增 plan/implementation/review/closeout artifacts 均写入独立文件，没有覆盖 frozen finding 或旧 evidence。

## Remaining risks and owners

| Risk / uncovered area | Classification | Owner |
|---|---|---|
| 五条正式 interactive scenarios、new immutable evidence bundle、readiness proof | covered by later approved evidence/readiness gate | Oracle 总控 |
| F08 real-provider meaningful/null prompt compliance | covered by `interactive.interactive.g06.summary-null` | Oracle 总控 + accepted prompt contract |
| active-cancel 非确定性时序若再次稳定复现 | assigned to later work unit if recurrence | `open_host` active-cancel runtime/test |
| GitHub checks 为零 | requiring explicit user decision at later merge/readiness | 用户/PR owner |
| future legacy/non-prepared compactor implementation | conditional future limitation | 选择该实现的 future work unit；当前 production prepared path 无 gap |

没有 unclassified residual risk，没有当前必须创建的新 issue。

## Git and PR safety closeout

- 当前 branch 继承 `github/main`，本地 `main == github/main`，没有 rebase/reset/history rewrite。
- 复用 existing PR 190；没有创建新 PR。
- PR 190 保持 `OPEN` draft、base `main`、head `codex/interactive-oracle`、MERGEABLE/CLEAN。
- 没有 merge、approve、mark ready、request reviewers、review comment、delete branch 或 force-push。
- 所有 commits 均 normal push 到同一 PR 190。

## Next entry point

Oracle 总控在 PR 190 final repair head 上补跑五条真实 interactive scenarios，形成新的 immutable evidence bundle/digest；
完成 Agent-in-the-loop 裁决，并重新生成 init/prompt/interactive readiness proof。只有 Oracle 总控可以据此决定当前实现是否
获得 formal conformance pass。

## Completion status

Work unit `Interactive Conversation Memory closure F08–F10`：**completed / final closeout PASS**。
