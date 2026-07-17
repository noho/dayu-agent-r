# WU-SEMANTIC-OWNERSHIP-01 / R08 prefix-six exact-drift implementation continuation Controller authorization

## 1. Authorization

`AUTHORIZED / SAME_R08_IMPLEMENTATION_CONTINUATION / VALIDATION_ONLY_NO_PRODUCT_DELTA`。

这是现有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 内部 remediation sub-WU R08 的同一 implementation continuation，不是新 WU、不是新 slice，也不是重开旧 sub-WU。

Authoritative entry：

- accepted plan commit：`c723de5907b834f05b2701d23c1067cb3eb960ce`（`docs: accept R08 prefix-six exact-drift plan`）
- fixed plan：`docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`
- fixed plan SHA-256：`0253e626d81aa46b3b987f8acf93487e03a7b031530ad10a9402537d91c64521`
- plan re-review Controller adjudication：`docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-rereview-controller-adjudication.md`

本 authorization 只允许 AgentCodex 在当前 protected stopped tree 上完成 plan §6.2 item 8、§6.6、§6.7 与 §6.9 implementation self-check；不得进入 code review、aggregate deepreview、commit、push 或 PR。

## 2. Entry locks

AgentCodex 必须先独立复核全部 locks，任一不匹配即停止，不得修复、回退或重建 tree：

| Lock | Required value |
|---|---|
| cumulative `dayu/fins + tests` binary diff | `e40de2a03ad1240ef78bf9d36e28195f54a9166f344dd03c73bf1d0e6f63f33f` |
| S1+S2 cumulative `read_runtime_helpers.py` content state | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` |
| actual-owner `read_runtime.py` | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` |
| candidate 6 guards | `cc4c5267241093e55d80e648f8d1013f7b71f52ace1f244447869d3afced9274` |
| shared runtime test | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` |
| S1 implementation artifact | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` |
| S2 cumulative implementation artifact | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` |
| prefix-five predecessor JSON | `43986a2d9aca926a26396d420feea966be1526bc98da1c2fd1620335282b59fb` |
| stopped prefix-six JSON | `b4c103423956543069ef89434cb7190d3e32b2847cff9f6320dc0a6c6f7b4dee` |
| staged tree | empty |

## 3. Exact authorized work

顺序不可改变：

1. 匹配 §2 全部 locks、current changed-path manifest、candidate 6 唯一 public-owner import/test 与三条 assertions，并确认原五个 stable-owner tests 保留。
2. 立即执行 plan §6.7.G 完整 source/AST proof：dead duplicate helper definition/caller/import 全零，actual typed/sorted owner 保留，shared-test 四节点/九 imports 仍删除，R07 owners no-touch。
3. 保留同一 implementation task mutation 前的 prefix-five predecessor JSON；不得回退 candidate 6、不得重跑 prefix-five。
4. Fresh `coverage erase` 后按 plan §6.6 相同八文件、零 deselect 重跑 prefix-six；必须精确得到 `392 passed`、`391/485 = 80.61855670% >= 80.00%`，并记录新 JSON SHA 与 `[344,346,348,442]` evidence。
5. Prefix-six 精确通过后，从零、完整、按 plan 原命令执行 §6.6/§6.7：focused owner/public tests、forced-truncation 三段组合、真实 AAPL/HTML/no-statement smokes、aggregate/full Fins regression、15-file exact-key per-file coverage、full pyright、全部实际 changed Python scoped Ruff、双向/source/AST/LLM/README/security/no-touch/no-deferred scans 与 `git diff --check`。
6. 完成后记录 immutable changed-path manifest、每个 reviewed path content SHA-256、累计 binary diff SHA-256、staged 状态、全部命令与 exact results。

## 4. Allowed artifact 与 no-touch boundary

唯一允许新增的 durable artifact：

```text
docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-implementation-continuation-codex.md
```

`workspace/tmp/` 下可以产生 plan 指定的 coverage/smoke 临时证据。除该新 artifact 与临时证据外：

- 不得修改 production、任何 tests、README、design、control、plan、prior review/controller/implementation artifacts；
- candidate 6、原五个 stable-owner tests、dead-helper deletion、actual owner 与 shared test 必须 no-touch；
- 不得新增第七项 coverage test、skip/xfail、pragma/omit、compatibility、fallback、fake/empty execution 或 loosened checker；
- 不得实施 R09-R12、Issues 142/151/175/177/178、统一 tool authorization framework 或任何 deferred 能力；
- Topic 8-9 no-code 与既有安全机制保持不变。

## 5. Stop conditions

任一 entry lock、source/AST proof、exact `392` count、`391/485` numerator/denominator、15-file `>=80.00%`、focused/smoke/regression、pyright、Ruff、scan、README/no-touch 或 `git diff --check` 失败，必须保留证据并停止回 Controller。不得自行修改 protected tree 处理 validation failure。

## 6. Completion report

Artifact 必须给出：

- entry/exit locks 与完整 changed-path/content manifest；
- prefix-five predecessor 与 fresh prefix-six exact evidence；
- §6.6/§6.7 每项命令、退出状态与 exact result；
- 15-file coverage ledger、full pyright、scoped Ruff、smokes/scans/diff check；
- no-touch、security、Topic 8-9、deferred boundary 结论；
- changed files（应只有本 artifact）、residual risks/uncovered areas、明确 completion 或 stop 状态。

完成后停止，等待 Controller validation 与双路完整 code review；不得 stage、commit、push、PR 或进入 aggregate deepreview。
