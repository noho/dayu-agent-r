# PR 190 Final PR Review Controller Adjudication

## Scope

- Gate：existing draft PR review → fix → re-review。
- Reviewed remote/code head：`0f7dc59168aca6e5f5b5bb30c059711465347bf2`。
- PR：190，`codex/interactive-oracle` → `main`，OPEN / draft。
- MiMo review：`docs/reviews/pr-190-final-pr-mimo-review-20260803.md`。
- DeepSeek review：`docs/reviews/pr-190-final-pr-ds-review-20260803.md`。
- Codex fix：`docs/reviews/pr-190-final-pr-review-fix-codex-20260803.md`。
- MiMo re-review：`docs/reviews/pr-190-final-pr-rereview-mimo-20260803.md`。
- DeepSeek re-review：`docs/reviews/pr-190-final-pr-rereview-ds-20260803.md`。

Controller 逐项读取两路 review、fix、re-review，并回到 frozen design、代码、Git/PR metadata 与 evidence 核验；不以两路结论一致代替证据。

## Review finding adjudication

### 两路新增 production findings

- MiMo：没有 correctness、stability、maintainability、semantic ownership、LLM-facing 或 overcoupling finding。
- DeepSeek：没有新增 production finding；其 final artifact 的“无新增 Critical / High”之后所列 F-001—F-004 均是此前 aggregate review 已裁决观察的重述。
- Decision：`pass/no-code-fix`。没有 owner-level production failure、可达反例或新设计冲突需要修改代码、测试、prompt、design、README 或 registry。

### DeepSeek 重列 F-001：`intent_type` / `reason` 开放字符串

- Decision：`rejected-with-reason；remain closed`。
- Direct evidence：frozen v2 design、typed contract、Memory projection 与自足 prompt 均明确定义为非空业务字符串；闭集只属于 status、source kind 和 explicit-drop reason。此前 controller D-001 已拒绝从旧 vNext enum 反推新 schema。
- PR review 没有提供下游按该字符串分支、持久化不一致或违反 frozen oracle 的新证据，不能恢复 enum 或新增 pattern accept rule。

### DeepSeek 重列 F-002：multi-pass summary 换行拼接

- Decision：`rejected-with-reason；remain closed`。
- Direct evidence：pass material disjoint、顺序 frozen，aggregate 后由 root input 对 coverage、duplicate、contradiction 与 caps 全量重验。review 没有 coherence predicate 或失败 sample；增加 LLM rewrite 会扩大 provider 调用与产品语义。

### DeepSeek 重列 F-003：VT100 reader broad catch

- Decision：`rejected-with-reason；remain closed`。
- Direct evidence：reader 已处理 terminal/select/read/strict UTF-8 的预期失败；PromptToolkit parser resolution 是同步 invariant。`except Exception: break` 会掩盖 programming failure，又不会向 waiter 投递 typed failure。review 没有可复现 parser exception 或新的 failure-channel contract。

### DeepSeek 重列 F-004：submit handoff 竞态

- Decision：`rejected-with-reason；remain closed`。
- Direct evidence：ambiguity sleep 后的 `is_done`、`flush_keys`、`feed_multiple`、`process_keys` 之间没有 `await`，同一 event-loop task 内不存在 reviewer 假设的调度窗口。没有新调度点或失败数据。

### MiMo previous-* source kinds 未逐个 injection 参数化

- Decision：`rejected-with-reason；not a contract gap`。
- Direct evidence：完整 `CompactInputV2` JSON 由同一 marker 包围；renderer 不按 `source_kind` 分支、过滤或重写。current/trace/evidence/answer 四位置 canary 覆盖共同 production path，逐个穷举 previous-* 不会增加 marker owner contract 证明。完整自然语言 evaluation 仍归 Issue 80。

### Provider selector 与旧 scenario compatibility observations

- Decision：`out-of-scope / no-fix`。
- Mimo-first / DeepSeek-only 是真实 smoke 的 test selector，不是 production provider-selection contract；用户明确禁止修改 provider/model 语义。
- P25→P27R 是前序已冻结 registry baseline，任务禁止旧 alias/compatibility；本 follow-up `7cf1027c..0f7dc591` 对 oracle、scenario、handbook 为零 diff。

### Review metadata corrections

- DeepSeek artifact 写 `45 commits`；直接命令 `git rev-list --count main..0f7dc591` 为 `43`。Decision：`artifact metadata error only`，不影响 reviewed tree/diff/code verdict；Codex fix 与两路 re-review 已记录纠正。
- MiMo 初稿曾把前序 F01-F07 Mimo full-real bundle 与本 follow-up evidence 并列得不够清楚；同一 reviewer 已原地纠正 durable artifact：前序 bundle只证明 F01-F07，本 follow-up 两路真实 provider 均 `network_unavailable`，行为是 `not_observed`。两路 re-review 已核验 corrected bytes 与语义。

## Fix and re-review adjudication

- Accepted production findings：`0`。
- Fix：`PR-REVIEW-FIX-PASS — NO-CODE-FIX`；只新增 durable reconciliation artifact，没有修改任何运行时代码、测试、LLM-facing prompt、design、README 或 frozen registry。
- MiMo re-review：`PR-REREVIEW-PASS`；no-code-fix accepted。
- DeepSeek re-review：`PR-REREVIEW-PASS`；no-code-fix accepted。
- Controller correction：reviewer 只能给出独立 review 结论，最终 adjudication 由本 artifact 的 controller 承担；MiMo rereview artifact 的角色标题/footer 已由 reviewer 自行纠正。

## Validation and exact-state evidence

- Local/remote/PR reviewed head：`0f7dc59168aca6e5f5b5bb30c059711465347bf2`。
- `main..0f7dc591`：43 commits；`7cf1027c..0f7dc591`：6 commits。
- PR metadata：number 190，OPEN，draft，base `main`，head `codex/interactive-oracle`，`MERGEABLE`。
- Frozen truth：`git diff --exit-code 7cf1027c..0f7dc591 -- docs/cli_ci_oracles.json docs/cli_ci_scenarios.json docs/cli_ci.md` pass。
- GitHub checks：未报告 checks；不得写成 CI pass。
- 已接受 deterministic evidence：S4 aggregate `365 passed, 1 skipped`；full pyright `0 errors, 0 warnings`；aggregate DeepSeek Host suite `2362 passed, 8 deselected`；prompt evidence bundle checksum `13/13 OK`。

## Residuals and owner

1. 本 follow-up 的真实 provider behavior：`not_observed`。
   - 事实：Mimo 与 DeepSeek 均为 `network_unavailable`，没有非空 candidate。
   - 未观测：真实 strict parse、governance accept、cap compliance、injection resistance 与 whole-candidate repair。
   - Owner：user / Oracle controller。该事实阻止宣告真实 behavior/formal conformance pass，但不是 production code failure，也不阻止 Gateflow 记录 final closeout。
2. F01-F07 既有 Host public-cancel test-order flake、overall registry calibration、renderer target pin 与 durable resolved Authorization projection：保持既有 owner/后续 work unit，不因本 review 重开。
3. GitHub 当前无 checks：外部 CI owner；本 closeout 只报告本地验证与 immutable evidence。

## Gate verdict

`PR-REVIEW-PASS — NO-CODE-FIX — REREVIEW-PASS`

允许提交并推送本 gate 的 intended review artifacts，随后执行 draft-PR-pass 与 final closeout。该 verdict 不 mark ready、不 approve、不 merge，也不替 user / Oracle controller 宣告 formal conformance pass。
