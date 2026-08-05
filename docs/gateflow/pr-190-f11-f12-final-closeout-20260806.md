# PR 190 F11/F12 Final Closeout

## Completion status

- Work unit: 关闭 PR 190 上 F11 public compactor response identity 与 F12 minimal fresh compaction v3 contract。
- Design docs: `docs/host/design.md`、`docs/engine/design.md`。
- Draft PR: https://github.com/noho/dayu-agent-r/pull/190
- Closeout basis head: `3d813ebd693740cf22305b89cbe8b27ed390376d`（accepted validation + draft-PR-pass 已 push）。
- Final closeout date: 2026-08-06。
- Gateflow status: **FINAL CLOSEOUT PASS**；本 artifact commit/push 后只剩 Oracle-controller adjudication。

## Finding status and final owner contract

### F11 / observed behavior 59 — fixed

Status: **已修复**。

- Canonical identity owner: Host compaction accepted/rejected terminal payload 持有同源 `SuccessfulRunnerResponseIdentity`。
- Public resolver owner: Host durable Tool Trace 在 manifest/input identity 验证通过后，投影一个 typed `ResolvedCompactorResponseIdentity`。
- Public analysis owner: Tool Trace typed report 与 JSON/Markdown renderer 只消费 resolver projection。
- Public fields: terminating runner request identity、actual effective provider/model、provider-request-id availability/value。
- Successful compact 与 successful response 后被 Context Governance reject 的 attempt 均可查；no-success rejection 使用显式 nullable identity。
- 不从 config、相邻 event、时间顺序、provider name 推断；manifest/ref/digest mismatch 继续 fail closed；不暴露 endpoint、credential、headers 或 raw provider request/response。
- PR-review 补充 test 用冲突邻近 payload 验证 rejected typed/JSON/Markdown 输出仍只来自 canonical successful response identity。

### F12 / observed behavior 62 — fixed

Status: **已修复**。

Final minimal contract:

- LLM 只生成五类业务可读 Semantic Memory 与 retained content 必需 provenance：`session_summary`、`evidence_facts`、`answer_anchors`、`forward_intents`、`reference_continuity`。
- mandatory explicit-drop ledger 及四类 model-authored drop reason 从 fresh v3 schema 删除；无 alias、compat reader、wrapper、shim 或下游补偿。
- Host 从 immutable source boundary 与 accepted provenance 派生 represented set、exact omitted complement、真实 caps/usage audit。
- 一个 immutable structure descriptor 机械派生 concrete template、concise prompt rules、provider-native JSON Schema、strict parser 和 owner tests。
- Initial request 首次即包含实际 caps；repair request 自足、同一 immutable request/source boundary、bounded whole-candidate replay。
- `session_summary` required + nullable；`null` 是完整 replacement，清空旧 summary，不清其它四类 Memory。
- Context Governance 是唯一 accept barrier；invalid candidate 不写 accepted artifact、success terminal 或 Memory，repair exhaustion 进入既有 deterministic fallback。
- Accepted artifact、EventLog、Memory、RunInput、Tool Trace 从同一 accepted truth 派生。
- PR-review 最终修正把 parser failure 的 `code/json_path/message` 交给 `compact_structure.py` typed exception owner，移除 downstream string inference；同时删除无语义的 parser request 参数。

该方案相对 Goal Confirmation **无 contract 或 scope drift**。它保留 strict parser、duplicate/unknown/missing/type/enum/cap rejection、immutable binding、bounded repair、single terminal、fallback 与 Memory safety；没有增加自然语言 heuristic、第二 LLM judge、provider 特例、unbounded retry 或第二 accepted truth。

## Design, code, tests, README and registry changes

### Design and code

- `docs/host/design.md`: frozen F11 canonical/public Tool Trace identity、F12 fresh v3 structure/acceptance/coverage/audit/repair/durable ownership。
- `docs/engine/design.md`: frozen provider-neutral structured-output request/capability transport；Engine 不拥有 business schema acceptance。
- Host Tool Trace resolver/analysis contracts expose canonical response identity。
- Engine gains typed `StructuredOutputCapability` / request union and required runner-call transport。
- Host compactor gains fresh v3 structure owner、strict parser、prompt/schema projection、Host-derived coverage/audit and typed parse failure。
- Production fallback material replay and accepted terminal payload were corrected from real-observation findings before evidence acceptance。

### Prompt / publication

- System prompt: 2,510 → 822 bytes。
- User prompt: 13,919 → 4,301 bytes。
- Final hashes:
  - system: `97479acc0cc686cb9a72d18b310aff58cabba4d4b223c6773a12249b5ed333e5`；
  - user: `59b50e13ea636c434fcabe26adf6d9ed22665dfcba03533ebcf5e9b524b87b76`；
  - prompt manifest: `a3ad3ec2b30bc9037b5a4aa7b288d8a2462870d5bac77217a6aa708d58aa52db`；
  - init publication manifest: `d95de68e69b0aacc712ec6bf468c8604a91460a17f3e2497f397182517a6a9f8`。

### README

- Updated: `dayu/host/README.md`、`dayu/config/README.md`、`dayu/engine/README.md`、`dayu/README.md`、`tests/README.md`。
- Not updated: root `README.md`，because no user-visible CLI/install/workspace workflow changed。

### Oracle / scenario registry

- User-confirmed replacement contract was applied；不是为了迁就实现删除场景。
- Historical oracle/scenario records remain preserved with explicit supersession provenance。
- `cli.interactive.core-execution@2` is the accepted current owner for stable replacement predicates。
- Three replacement scenarios remain `unadjudicated`；both registries remain `calibration`。
- Final SHA-256:
  - `docs/cli_ci_oracles.json`: `3404e241dbd71c6244da24b0dbb080022d4c57b36f040ac3456e7a18dbc97acf`；
  - `docs/cli_ci_scenarios.json`: `f4363fc5e7026ad075f4b7f855342cae493a4852d21bd72ef6e53b3f2d588e37`。

## Verification

### Implementation and deterministic validation

- Final full pytest: **6727 passed, 11 skipped, 6 deselected**。
- Final clean coverage union: **389 passed, 1 skipped**；`compact_structure.py` 89%、`llm_compaction.py` 86%，both >=80%。
- PR-review focused: 53 compaction owner tests + 32 Tool Trace analysis tests PASS。
- Full-repository pyright: **0 errors, 0 warnings, 0 informations**。
- All Python files changed since F11/F12 base pass Ruff。
- Compileall、both registry JSON parses、`git diff --check`: PASS。
- Full-repository Ruff was also run and reported 89 historical/out-of-work-unit findings；current changed-file set has zero。
- Coverage instrumentation/order diagnostic failures were isolated: ToolRuntime file 68 passed and cancel case 1 passed without coverage；full suite remained green。Detailed classification: `docs/gateflow/pr-190-f11-f12-final-validation-20260806.md`。

### Real-provider observation

Real observation is **complete as implementation evidence**, but does not substitute for Oracle adjudication。

- Mimo plan used first；DeepSeek covered provider-independent paths where applicable。
- Covered first-pass compact、invalid JSON repair/exhaust/fallback、cap-constrained compact、rolling correction、prompt-injection-style material、accepted evidence fact、failed compact no-Memory-pollution、reconnect continuity、F11 successful/rejected public identity。
- Public/canonical identity comparison: 0 mismatch。
- Immutable evidence root: `/Users/leo/workspace/.dayu-cli-ci/interactive-memory-v3-20260805T-s4-restart-uOZytY`。
- `digest.json` SHA-256: `38f0b01f12c2ab55ce1af3c16080b71013d1a19512d65051f5532b747f71da0d`。
- Human report SHA-256: `bbaa52a04100932c09e0a8e20d19c81ed6d865378db502bc6d4f1936c9694411`。
- Secret scan: 0 findings；four credential-bearing `dayu_host.sqlite3` files remain quarantined outside public root；four non-secret `runtime_lanes.sqlite3` remain published。

## Gateflow commits

1. `8d8d3883c473c9774e212cc24a2aacd9fe6d7925` — accepted plan。
2. `427b1c858d5e926f309935fa206963deb1618436` — plan checkpoint digest correction。
3. `19a6d6257504876e01da3067bbc4cf33ae99525d` — design truth。
4. `c8be3e5184b8b797c59458027e991f0284cbb3b5` — F11 public Tool Trace。
5. `1943904eea9e30357805c9f1d2b6f6e815b37c86` — Engine structured output。
6. `321893e423beeb20acf2768c03b2be3477c92903` — fresh compaction v3。
7. `c824ea9038ecb4084621117c6806764cd63e9a20` — real evidence harness。
8. `f7957b6343f4647ce0c6058a08e9ae84ab629f30` — fallback material replay fix。
9. `d9f044f944dd44e0d369f9d93e0533d2b725e413` — accepted terminal payload fix。
10. `1a79ff1859117027340910152c0ce208a7f37b5d` — accepted real evidence。
11. `8b3d6cf6688f83373839b903c8fef89c640147fd` — registry supersession/update。
12. `2cf1b4acf290f128c18544c48995b29bbbe625b5` — PR body checkpoint artifact。
13. `9fa3ff799506e66f995b4156dbb960c98c2f737e` — aggregate deepreview fix/acceptance。
14. `d51a87135ba07d98b6a3d20296152495c9ececb9` — PR review fix/acceptance。
15. `5824baffc544914adb727365b80be4e90c510e14` — final validation。
16. `3d813ebd693740cf22305b89cbe8b27ed390376d` — draft-PR-pass。

本 final closeout artifact 的 commit 将成为 PR 190 的最终 implementation closeout head；最终 exact SHA 由 push/readback 后在用户 closeout 与 PR body 报告。

## PR and prohibited actions

Closeout basis readback:

- URL: https://github.com/noho/dayu-agent-r/pull/190
- state: OPEN；draft: true；base/head: `main` / `codex/interactive-oracle`。
- mergeable: MERGEABLE；merge state: CLEAN。
- GitHub checks: no checks reported；不伪称 CI PASS。

Explicitly not performed:

- no new PR；
- no merge；
- no mark ready；
- no approve；
- no reviewer request；
- no rebase / force-push；
- no branch deletion。

## Remaining risks and owners

1. **Oracle controller / pending:** adjudicate the three replacement scenarios on final head and regenerate init/prompt/interactive readiness proof。
2. **Existing module owners / historical debt:** 89 repository-wide Ruff findings outside F11/F12 changed-file scope。
3. **Runtime/ToolRuntime test owner / test infrastructure:** coverage instrumentation/order can interfere with multiprocessing fixtures；isolated and full non-coverage suites pass。
4. **Deployment/session owner / accepted constraint:** fresh v3 schema intentionally has no v2 artifact compatibility reader or migration shim。
5. **Oracle + real-provider owner / epistemic boundary:** deterministic Host checks cannot prove arbitrary natural-language quality；use immutable observation plus human adjudication。

All residual risks are classified；none blocks implementation closeout。

## Three-state conclusion and next entry point

- **Implementation PASS:** F11/F12 design, code, owner tests, full tests, type checks, review gates and draft PR chain pass。
- **Real observation PASS as evidence:** immutable Mimo/DeepSeek observations cover the required matrix and show no public/canonical F11 mismatch or Memory safety failure。
- **Oracle decision pending:** replacement scenarios are deliberately still unadjudicated；implementation agents have not frozen readiness。

Next entry point: **Oracle controller 在 PR 190 final head 上审阅 immutable observation，裁决三条 replacement scenarios，并重新生成 init/prompt/interactive readiness proof。**
