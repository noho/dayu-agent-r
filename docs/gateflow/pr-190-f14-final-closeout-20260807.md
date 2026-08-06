# PR 190 / F14 final closeout

## Outcome

`PASS`：F14 已从 root cause 修复。Host 不再从 accepted compact terminal 的 EventLog sequence 反推 material consumption；protected/unselected raw turns 未被 replacement 覆盖时不会被消费，离开 recent floor 后会按 canonical order 与 atomic Run group 重新 eligible，并能进入后续 durable replacement。

## Single source of truth

唯一真源是 strict `ContextCompactedSemanticPayload.compacted_source_refs`。Host 从 accepted chain 累积该 coverage truth，并在既有 material/atomic owner boundary 上证明 consumed prefix 与 unconsumed suffix；material frontier 是该 truth 对 canonical material 的派生值。terminal event id/sequence 只用于 provenance。没有新增 schema/public contract、durable cursor、兼容分支、双 projector 或第二 source truth。

## Gate history

- Goal Confirmation：`docs/reviews/f14-goal-confirmation-20260806-221301.md`
- accepted plan commit：`b222b8b064f096d899a9de708e45cd1fb6e732e6`
- implementation commit：`6eb41ac1`（`fix(host): derive compact frontier from accepted coverage`）
- aggregate deepreview commit：`7dd84a4a`（Controller / MiMo / DeepSeek 三路 PASS）
- final validation/real observation：`docs/gateflow/pr-190-f14-final-validation-and-real-observation-20260807.md`

全部 accepted findings 已修复并由原 reviewers re-review；aggregate gate 无新增 finding。

## Validation state separation

- implementation/tests：owner regression、lifecycle、rolling monotonicity、restart/reconnect、evidence provenance 与投影同源均有 deterministic tests；测试中使用 deterministic fixtures/fake/mock。
- production observation：fresh workspace、production CLI POSIX PTY、真实 MiMo、production finance tools、真实 AAPL 10-K；未使用 fake/mock provider/tool。FY2025 correction 在离开 production recent window 后进入 latest durable replacement，新 facts 绑定新 production refs，21.7% 未成为 EvidenceFact，reconnect 由正式 Memory/RunInput 证明。
- Oracle readiness：仍为 `pending-user-adjudication`；本 work unit 不把 formal scenario 标为 accepted/ready。

## Full validation exceptions

- full Pyright、compileall、JSON、diff check 与 changed-files Ruff 通过。
- full pytest 的 4 个 frozen publication manifest failures 已在 implementation 前 `b222b8b0` 精确复现；不是 F14 回归。
- full Ruff 仍有 89 个未修改文件中的既有错误；没有隐藏、扩散或自动修改范围外代码。

## Evidence

- root：`/Users/leo/workspace/.dayu-cli-ci/f14-postfix-20260807-cAoxqy`
- distributable manifest SHA-256：`84c2b93e32a58cd1f89a2ef9c331e420d600ebbc5e850b7939d333022cc1f4b6`
- owner audit SHA-256：`402449c5681c33aa5600f89128863c2bb1faee398387ea91a4876fc542b8fbfa`
- exact-value secret scan：5 values / 104 files / 0 findings / 0 unreadable；SHA-256 `ff3ecdef4d453cfd8604aa2a5c1dfb60faf9a7e7187f962b326ec3cd71332da3`
- raw SQLite 仅本机原件保留，未进入 distributable evidence。

Oracle fresh rerun 入口：

```bash
source .venv/bin/activate
python workspace/tmp/f14_real_cli_observation.py \
  --run-root <fresh-empty-run-root> \
  --repo-root /Users/leo/workspace/dayu-agent-r \
  --cli /Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli
```

该 ignored harness 的 captured immutable copy 位于 evidence root 的 `evidence/harness-source.py`，SHA-256 `1de6956e6d1888387ea8fd75f37b35eb76a36849552edb9859d77f982153397c`。

## PR boundary and remaining risks

继续使用已有 draft PR 190；不新建 PR、不 merge、不 mark ready、不 approve/request reviewers、不 rebase/force-push、不删除分支。final closeout commit 与 push 后由 Controller 回读 PR head/state。

remaining risks：accepted-chain/material scan 的线性长 Session 成本；provider 非确定性；本次 real run 未触发非-accepted lifecycle；formal status 仍待 Oracle/用户裁决。
