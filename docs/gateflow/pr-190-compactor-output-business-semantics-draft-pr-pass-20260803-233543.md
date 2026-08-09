# PR 190 Compactor 输出业务语义 Draft PR Pass

## Gate metadata

- Gate：`draft-PR-pass`
- Work unit：补齐 Compactor LLM-facing 输出 schema 的核心字段与显式丢弃原因业务语义
- Existing PR：[PR 190](https://github.com/noho/dayu-agent-r/pull/190)
- Branch：`codex/interactive-oracle`
- Acceptance time：2026-08-03 23:35:43 +08:00
- Decision：`DRAFT-PR-PASS`
- Completion status：`draft-PR-pass`
- Current gate after this artifact：`final closeout`
- Next entry point：`final closeout`
- Blocking open questions：无
- Artifact path：`docs/gateflow/pr-190-compactor-output-business-semantics-draft-pr-pass-20260803-233543.md`

本 gate 只确认 supplementary work unit 已满足进入 final closeout 的精确条件，不宣告 PR 可合并，不宣告 CI pass，也不宣告真实 provider conformance pass。

## Accepted gate chain

| Gate | Accepted commit | Decision |
|---|---|---|
| Plan | `21b602c1feea555d5ab1241ca96ece073221d648` | accepted plan；单一 S1、owner、scope 与验证边界冻结 |
| Implementation S1 | `11b63911d61bd80b8e69ec3e2c32a3fd260f4e33` | accepted slice；prompt owner、tests 与 publication hash 闭环 |
| Aggregate deepreview | `b819309c654b9db8e3f02280687bdb3291442a89` | 两路 aggregate deepreview pass；finding 与 residual owner 已裁决 |
| Accepted PR review | `8e88f0538787456d5a2905d679c508c3da89d797` | 两路 no-code re-review pass；accepted PR-review artifact 已提交并完成 final push |

Accepted PR-review artifact `docs/gateflow/pr-190-pr-review-acceptance-20260803-232949.md` 存在于 commit `8e88f053`，其 next gate 明确为 `draft-PR-pass`。四个 accepted commits 均存在且都是当前 HEAD 的祖先；`b819309c..8e88f053` 只有 accepted PR-review checkpoint commit。

## Exact entry state

入口检查在创建本 artifact 前执行，结果如下：

- 当前 branch：`codex/interactive-oracle`，不是 `main` 或其它 protected trunk。
- Worktree / index：clean；`git status --short --branch` 只有 branch/upstream 行，无 staged、unstaged 或 untracked path。
- Local HEAD：`8e88f0538787456d5a2905d679c508c3da89d797`。
- Upstream tracking head：`8e88f0538787456d5a2905d679c508c3da89d797`。
- Fetched remote-tracking head：`8e88f0538787456d5a2905d679c508c3da89d797`。
- `git ls-remote github refs/heads/codex/interactive-oracle`：`8e88f0538787456d5a2905d679c508c3da89d797`。
- GitHub PR head OID：`8e88f0538787456d5a2905d679c508c3da89d797`。
- 因而 local HEAD = upstream = fetched remote-tracking head = remote branch head = PR head；accepted PR-review 后的 final push 已完成。
- PR state：`OPEN`。
- Draft：`true`。
- Base/head：`main` ← `codex/interactive-oracle`。
- Mergeability：`MERGEABLE`。
- Merge state：`CLEAN`。
- GitHub `statusCheckRollup`：空，即当前无 reported checks；这不等同于 CI pass，本 gate 不作 CI pass 声明。

## Frozen files and current hashes

Supplementary work unit 的固定起点为 `62b7d4a235f6b8a715fd6bbb518e98b352a64ac8`。`git diff --exit-code 62b7d4a2 HEAD -- <frozen files>` 通过且 `git diff --name-status` 无输出，证明以下三份冻结文件在整个 supplementary work unit 中未变：

- `docs/cli_ci_oracles.json`：`sha256:f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`。
- `docs/cli_ci_scenarios.json`：`sha256:7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`。
- `docs/cli_ci.md`：`sha256:a241182d4d09e8843ea647947777bc7f6f71c5532fa148e2abb87ede3e748b82`。

当前 publication truth：

- Prompt owner `dayu/config/prompts/scenes/conversation_compaction_user.md`：`sha256:a2f5711c84f6fdd51f921e5d266d05cdb3f6a34a6c8321ffc42f0c5dc75a0dce`。
- Manifest `docs/cli_init_workspace_manifest_v1.json`：`sha256:fb6d0ba8fbf01b093419d178daf09c145bc8643e03b900703a91f2a3ff005f6c`。
- Manifest 中 `config/prompts/scenes/conversation_compaction_user.md` 的 `content_sha256` 与 prompt 当前 raw bytes digest 完全一致。
- `tests/cli/test_smoke_cli_init_provider_matrix.py::FROZEN_MANIFEST_SHA256` 与 manifest 当前 raw bytes digest 完全一致。

## Validation

| Check | Result |
|---|---|
| `python -m json.tool docs/cli_init_workspace_manifest_v1.json` | pass |
| `python -m json.tool docs/cli_ci_oracles.json` | pass |
| `python -m json.tool docs/cli_ci_scenarios.json` | pass |
| `git diff --check` | pass，无输出 |
| Accepted commits / ancestry | pass；`21b602c1`、`11b63911`、`b819309c`、`8e88f053` 均存在且属于当前 chain |
| Accepted PR-review artifact | pass；精确 artifact 存在于 `8e88f053` |
| Remote / PR exact state | pass；local/upstream/remote/PR head 同一，PR OPEN + draft + `MERGEABLE/CLEAN` |

本 gate 只新增 Markdown artifact，没有 production、test 或 LLM-facing 行为变化，因此不重跑 pytest/pyright；接受同一 exact PR head 上已经过 accepted review 的验证证据。

## Immutable real-evidence truth

- 本 supplementary work unit 没有新增真实 provider run。
- 既有 immutable bundle 保持为 `/Users/leo/workspace/.dayu-cli-ci/pr190-compactor-llm-facing-20260803-182956/`。
- `SHA256SUMS` index digest：`dc7836bd631dc59a6665953fa988bce43228560c48a28a9ba6df9f419726d9a2`。
- `shasum -a 256 -c SHA256SUMS`：13/13 OK。
- Final exact real-provider truth：Mimo `network_unavailable`，DeepSeek `network_unavailable`，没有取得非空 candidate。
- Behavior truth：`not_observed`；真实 strict parse、governance accept、cap compliance、injection resistance 与 whole-candidate repair 均不得写成 pass。

因此 deterministic prompt/parser/publication validation 只证明 owner contract 与发布真值，不能替代真实 provider conformance。

## Docs decision

本 gate 只记录流程状态，不修改 production、tests、prompt、manifest、README、design、oracle、scenario 或 `docs/cli_ci.md`。README/design 均为 `no-change`。

## Residual risks and owners

1. 真实 provider 对字段分类、drop reason、repair cap 与 prompt-injection boundary 的行为仍为 `not_observed`。
   - Classification：`assigned to later work unit / requiring explicit user decision at final-validation boundary`。
   - Owner：real Compactor conformance evidence owner / user / Oracle controller。
2. Frozen oracle/scenario 的 current-head inventory/readiness proof 尚未刷新；冻结定义未变不等于 readiness 已重新验证。
   - Classification：`assigned to later work unit`。
   - Owner：独立 readiness refresh work unit。
3. `forward_intents.status` 与 `reference_continuity.reason` 的 LLM-facing 业务语义不在本 supplementary scope。
   - Classification：`assigned to later work unit`。
   - Owner：后续独立 LLM-facing schema work unit。
4. Readable-view / `vNext` naming debt。
   - Classification：`assigned to later work unit`。
   - Owner：Host compaction/readable-view naming-cleanup work unit。
5. GitHub 当前无 reported checks。
   - Classification：`requiring explicit user decision at merge boundary`。
   - Owner：repository CI/config owner 与 PR merge operator / user。
6. 大 PR 的固有遗漏风险。
   - Classification：`requiring explicit user decision at merge boundary`。
   - Owner：PR merge operator / user；两路 review 只能缓解，不能消除该风险。

所有 residual risks 均已分类并有 owner；没有未分类 residual risk或 blocking open question。

## Gate decision and protected actions

`DRAFT-PR-PASS`

下一未完成 gate 是 `final closeout`。本 gate 不创建新 PR，不 mark ready，不 approve，不 merge，不 comment，不 request reviewers，不 rebase，不 force-push，不删除 branch，也不修改任何 production、tests、reviews、design、README、oracle 或 scenario 文件。
