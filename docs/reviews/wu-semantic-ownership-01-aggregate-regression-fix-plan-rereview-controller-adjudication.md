# WU-SEMANTIC-OWNERSHIP-01 aggregate regression fixed-plan re-review Controller adjudication

## 1. Gate identity and evidence lock

- 时间：`2026-07-18 17:05:55 +0800`。
- Work unit：`WU-SEMANTIC-OWNERSHIP-01`，既有 umbrella overdesign remediation continuation；不是新 WU。
- Reviewed plan：`docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`，640 行 / 50,784 bytes / SHA-256 `7e91421b8bc8c442dcf72e94c20eb84d4f27f2b9878b427481448d6f2f4ea714`。
- AgentMiMo final artifact：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-rereview-mimo.md`，378 行 / 26,457 bytes / SHA-256 `35f84bc5330e6b5017451a08fb1fe523941cbef2359f700ccccb0d2ccc4ae33d`。
- AgentDS final artifact：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-rereview-ds.md`，431 行 / 31,069 bytes / SHA-256 `766e439c8ef1ed1ff3ed1c236af7a1adb0b93ca14a5541cdca50740d9a8d185b`。
- 结论：`PLAN_ACCEPTED / CODE_GENERATION_READY / NEW_ACCEPTED_FINDINGS 0 / READY_FOR_EXACT_SCOPE_LOCAL_PLAN_COMMIT`。

## 2. Review routing and evidence validity

- AgentMiMo 未启动 subagent / Explore / Task，明确没有读取 routing-invalid 的初始 MiMo artifact；AgentDS 未读取 AgentMiMo review。两路独立性有效。
- 两路初稿都只部分读取 Host design，Controller 因此拒绝初稿证据并在同一任务内要求补齐；这不是新 gate，也没有 `/clear`。最终两份 artifact 均用精确 metrics/hash 证明完整读取 `AGENTS.md`、controller discussion、五份 design 真源和本 gate artifacts，其中 Host design 为 3,696 行 / 388,584 bytes / SHA-256 `276d35e15edfbf3efb1b9bff8ff4abbb38de48e075050379218fd19df90f43e9`。
- AgentDS 初次把 Controller control-doc gate update 误判为 protected hash drift；Controller提供 current gate entry hash后，DS 在同一任务内将其正确重分类为授权 gate-transition evidence。该过程没有改变 plan 或其它 protected artifact。
- Review 期间 plan、Codex fix、Controller validation及所有 pre-existing non-control protected hashes保持不变；`git diff --check`通过，staged tree为空。

## 3. Accepted finding closure

| Finding | MiMo | DS | Controller disposition |
| --- | --- | --- | --- |
| `AR-PLAN-PF01` — omitted CLI direct-stream test consumer | CLOSED | CLOSED | `CLOSED`：CLI test在Slice 2 mutable test allowlist、focused tests与`dayu tests utils` owner/stale scans中闭环 |
| `AR-PLAN-PF02` — omitted public-awaiting validation utility | CLOSED | CLOSED | `CLOSED`：独立one-path utility allowlist、仅import迁移、九处typed uses零diff、post-migration fresh smoke与stale-private scans完整 |

两路都确认 rejected/no-fix建议没有偷带，三 slices仍分别关闭 current-schema/test-oracle、Fins public owner migration和九路径owner-test coverage；AR-F06/AR-F07与security/deferred/no-code状态没有改变。

## 4. New findings and observations

- 新 material finding：`0`。
- Blocking question：`0`。DS 对Slice 3 SEC/Docling fixture可行性的提问是 implementation risk；计划已用production-zero-diff和production-defect stop condition正确覆盖，不需要plan fix。
- MiMo `OBS-01`：`tests/fins/test_fins_ingestion_runtime.py` 只作为 regression focused test，当前不import `direct_stream`，故不进入mutable allowlist；维持 `NO_FIX / CORRECT_AS_WRITTEN`。
- MiMo `OBS-02` / 先前 DS logging candidates：Python logging registry恢复需要implementation contract test证明；计划已精确要求finally恢复与清理，不授权production logging变更，维持 `NO_PLAN_FIX / IMPLEMENTATION_EVIDENCE_REQUIRED`。
- MiMo `OBS-03`：`dayu/fins/ingestion/__init__.py` 已存在且应保持protected zero-diff；维持 `NO_FIX`。
- DS artifact中沿用的 `accepted-candidate` / `needs-evidence` 只是先前reviewer术语，不能覆盖既有Controller裁决。Logger、compactor parent、coverage feasibility、validation cost、external provider、AR-F06 future removal、Ruff和module-width候选继续保持 `REJECTED_WITH_REASON`、`COVERED_AS_WRITTEN` 或显式residual，不是current accepted finding。

Final ledger：accepted/open `0`，rejected-with-reason `0`（本轮无新候选），observation `3`，local blocker `0`，design contradiction `0`。

## 5. Plan acceptance

Controller接受final plan为code-generation-ready：

- Motivation由aggregate current-tree failures直接支持，不是重复修复。
- 三 slices顺序固定为 Slice 1 test-owner closure → Slice 2 Fins public-owner migration → Slice 3 test-only coverage closure；每个slice不超过三组语义闭环且有独立review/fix/re-review/commit边界。
- Owner、allowlist、protected paths、stop conditions、canonical/coverage/pyright/Ruff/build/scans/smokes和README/security/deferred/no-code gates完整。
- Topic 8与Topic 9仍为no-code；没有统一tool authorization framework；Issue 142、151、175、177、178及Web/WeChat/render trackers没有被偷带。
- AR-F06保持 `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`；AR-F07保持 `PENDING_RELEASE_BLOCKER`。

## 6. Exact-scope accepted local plan commit authorization

下一 gate只授权Controller把本轮plan/control/evidence的精确15路径做accepted local commit，message为 `docs: accept aggregate regression fix plan`：

```text
docs/host/issues-implementation-control.md
docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md
docs/reviews/wu-semantic-ownership-01-r12-accepted-implementation-commit-controller-validation.md
docs/reviews/wu-semantic-ownership-01-aggregate-regression-codex.md
docs/reviews/wu-semantic-ownership-01-aggregate-regression-controller-adjudication.md
docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-controller-validation.md
docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-ds.md
docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-mimo-cleanroom.md
docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-mimo.md
docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-controller-adjudication.md
docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-fix-codex.md
docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-fix-controller-validation.md
docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-rereview-mimo.md
docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-rereview-ds.md
docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-rereview-controller-adjudication.md
```

必须先精确验证 staged path/status、staged diff-check、plan/review hashes与没有product/test/README/workflow delta。该commit不授权implementation、push、PR、aggregate deepreview或closeout；commit后由Controller独立建立Slice 1 implementation entry locks和授权。
