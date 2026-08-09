# PR 190 Compactor 输出业务语义 aggregate deepreview acceptance

## Gate metadata

- Gate：`aggregate deepreview acceptance`
- Work unit：补齐 Compactor LLM-facing 输出 schema 的核心字段与显式丢弃原因业务语义
- Branch：`codex/interactive-oracle`
- Reviewed scope：`62b7d4a2..11b63911`
- Decision：`pass`
- Completion status：`aggregate-deepreview-pass`
- Current gate after this artifact：`accepted deepreview commit`
- Next entry point：完成 accepted deepreview checkpoint 后，回到 PR 190 的 existing draft PR chain，进入 `PR review`
- Blocking open questions：无
- Artifact path：`docs/gateflow/pr-190-compactor-output-business-semantics-aggregate-deepreview-acceptance-20260803-224144.md`

本 artifact 只收口当前补充 work unit 的 aggregate deepreview gate，固化两路独立 review evidence、历史 finding 最终裁决、验证状态与 checkpoint 边界。Acceptance artifact 创建阶段只新增本 artifact；不修改两份 aggregate review、代码、测试、prompt、manifest、README、design、oracle/scenario 或其它既有文件，也未执行 stage、commit、push 或任何 PR 外部操作。

## Scope and reviewed target

固定 scope 为 `62b7d4a2..11b63911`，不使用会随工作树或分支推进而漂移的 `HEAD`：

- Base：`62b7d4a235f6b8a715fd6bbb518e98b352a64ac8`；
- Accepted plan commit：`21b602c1`，`gateflow: accept plan for compactor output business semantics`；
- Accepted slice commit / reviewed tip：`11b63911d61bd80b8e69ec3e2c32a3fd260f4e33`，`gateflow: accept compactor output business semantics S1`；
- Committed diff：20 files changed，2387 insertions，11 deletions；
- Shipped implementation boundary：1 个 LLM-facing prompt owner、3 个测试文件、1 个 publication manifest；其余变更均为当前 work unit 的 Gateflow/review artifacts；
- Excluded：两份 aggregate review 与本 acceptance 尚未进入上述 committed scope，它们只作为本 gate 的 intended evidence/checkpoint 文件。

## Aggregate deepreview evidence

| Route | Artifact | SHA-256 | Result |
|---|---|---|---|
| Route 1 | `docs/reviews/aggregate-deepreview-20260803-223339.md` | `f7c39db8b5e501fe4f4ec3c98139e03b9465d6b6441816151e45ad6056156411` | `pass`；未发现实质性问题，无 finding |
| Route 2（独立） | `docs/reviews/aggregate-deepreview-20260803-223901.md` | `b16f972d5db46570e9eec4a09dd06f92a054e380e77d52c5c31c8603ab195b00` | `pass`；未发现实质性问题，无 finding |

两路均覆盖同一 committed scope，核验最终 shipped semantics、owner boundary、跨 artifact 一致性、测试与 hash evidence、frozen files、docs/oracle 状态、过度耦合和 semantic ownership drift。第二路明确未读取第一路，独立从 committed diff、owner 代码、摘要与测试证据得出结论。两路均未产生 accepted、deferred、needs-more-evidence 或其它新增 finding。

## Historical finding final adjudication

| Finding / source | Final adjudication | Final status / owner |
|---|---|---|
| PR 190 follow-up F01：核心输出字段与四种 drop reason 缺少自足业务语义 | `accepted` | 已由当前 work unit 的 prompt owner、owner tests 与 publication chain 完整修复；两路 aggregate deepreview 确认关闭 |
| 初始 plan review F01：`session_summary: null` proposed 语义与 Memory replacement owner 相反 | `accepted` | 已修复；accepted candidate 的 `null` 明确清空既有摘要，并由 Memory regression 锁定 |
| 初始 plan review F02：previous evidence support 与 `policy_limit` cap 可见来源未同源 | `accepted` | 已修复；claim 双来源与 repair feedback 明示具体 cap 的前提已进入 prompt owner 和 tests |
| AgentDS plan F01：`forward_intents.status` / `reference_continuity.reason` 业务语义缺口 | `deferred-with-owner` | `assigned to later work unit`；owner 为后续独立 LLM-facing schema work unit，不在当前 scope 下游补偿 |
| AgentDS plan F02：hash encoding concern | `rejected-with-reason` | raw bytes 由 `sha256sum` 与 publication test exact 校验，byte drift fail closed；不是 residual risk |
| AgentDS code F01：7 项 frozen semantic fragment 缺失 | `accepted` | `已修复`；owner test 已为 7 项分别增加独立 assertion，两路 re-review 与 aggregate deepreview 均确认 |
| AgentDS code F02：forbidden-term guard 不完整 | `accepted` | `已修复`；guard 扩展至 13 项，prompt 零命中且不误禁业务 schema labels |
| AgentDS code F03：substring 前缀匹配漏检 | `rejected-with-reason` | 与 code F01 同 root cause、同 owner、同 fix；F01 修复后独立证据失效，不重复计为 finding |

其它 plan review、code review 与 re-review route 均为 `pass / 无 finding`。不存在 `未修复`、`部分修复`、`needs-more-evidence` 或 deferred code-review finding；唯一 deferred plan finding已有明确 later-work-unit owner。

## Validation status

本 acceptance 接受既有 implementation、re-review 与两路 aggregate deepreview 中记录的实际验证，不把未运行的真实 provider 行为冒充 deterministic pass：

| Validation | Accepted status |
|---|---|
| Packaged prompt owner tests | `24 passed`；修复后的 focused owner test `1 passed`；36 项 frozen business semantics 与 13 项 forbidden-term guard 均有直接证据 |
| Default assembled public smoke | focused run `1 passed`；完整示例继续通过 production parser 与 Context Governance accept barrier |
| Memory replacement regression | `1 passed`；锁定 accepted `session_summary: null` 清空既有摘要 |
| Publication/config assembly | implementation evidence 为 `287 passed, 3 warnings`；第二路 aggregate 独立 evidence 为 `267 passed, 3 warnings`；warnings 均为第三方 `edgar` deprecation |
| Re-review combined host tests | `54 passed, 1 skipped`；skip 是未启用的 opt-in real-provider smoke，不宣称真实模型 behavior pass |
| Pyright | 完整验证 `0 errors, 0 warnings, 0 informations`；第二路对 changed files 独立验证同样为 0 |
| Diff integrity | `git diff --check` pass |

本轮只新增 Markdown acceptance artifact，没有代码或测试行为变化，因此未重复运行 pytest/pyright；上述状态来自已通过并被两路 aggregate deepreview 复核的 durable evidence。

## Hash and publication status

- Prompt owner：`sha256:a2f5711c84f6fdd51f921e5d266d05cdb3f6a34a6c8321ffc42f0c5dc75a0dce`；
- Owner test：`sha256:4d77165a473467c8fd57964e06c3b07cc5679e05917c093d98d637af6974eac0`；
- Public smoke：`sha256:64ade7605786c2308e16e087e37ee4fa5f519886113cbe33923144a526c33e31`；
- Publication manifest：`sha256:fb6d0ba8fbf01b093419d178daf09c145bc8643e03b900703a91f2a3ff005f6c`；
- CLI manifest hash test：`sha256:c86520e50941e25c5451b36669c74ad874a1da52c0145cda3ecc6fd6e7a65faa`。

Publication chain 已闭合：prompt raw bytes digest 与 manifest 中唯一对应 entry 一致；manifest raw bytes digest 与 `FROZEN_MANIFEST_SHA256` 一致。两路 review hash 已按当前 raw bytes 独立计算并记录；本 acceptance 未回写 review evidence。

## Frozen files, docs and oracle status

`62b7d4a2..11b63911` 对以下 frozen owners / registry files均为零 diff：

| File | SHA-256 / status |
|---|---|
| `dayu/host/compaction.py` | `9c14b0294e1177f38e96cfa85d8c57a7a0aef31d7f338ed3f58b97ac6d7a7868`；preserved |
| `dayu/host/context_governance.py` | `ffbd24282737e316a70102229cbf9628f33b80154394c45b1404aedb77b6df3e`；preserved |
| `dayu/host/memory.py` | `42a56de0c2af9fb07fcaea2667a216d854d7225f4766f91902b289fc987026f8`；preserved |
| `dayu/config/prompts/scenes/conversation_compaction.md` | `4bd476db45f17bebaa7eb951c8354d10189df1faadb9c1c530619d9f3352f60a`；preserved |
| `dayu/config/prompts/manifests/conversation_compaction.json` | `a3ad3ec2b30bc9037b5a4aa7b288d8a2462870d5bac77217a6aa708d58aa52db`；preserved |
| `dayu/config/execution_profiles.json` | `3fd7e6940e337f0668bbac315f6b99254e3eb3309473a2161efc91cfc1b2e1f5`；preserved |
| `docs/cli_ci_oracles.json` | `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`；frozen definitions preserved |
| `docs/cli_ci_scenarios.json` | `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`；frozen definitions preserved |
| `docs/cli_ci.md` | `a241182d4d09e8843ea647947777bc7f6f71c5532fa148e2abb87ede3e748b82`；preserved |

全部 README 与 design 文档在固定 scope 内均为零 diff。Docs decision 为 `no-change`：当前 work unit 只兑现既有 prompt 自足职责并强化既有测试，没有改变目录职责、Host contract、schema、状态机、分层、装配、用户工作流或测试运行方式。

Oracle/scenario 的已裁决定义保持冻结且未被实现迁就；current-head inventory/readiness proof refresh 尚未完成，不在本 gate 冒充 ready。该 refresh 已分类到后续独立 readiness refresh work unit。

## Residual risks and owners

- `assigned to later work unit`：真实 provider 对字段分类、drop reason、repair cap 与 prompt-injection boundary 的稳定遵循度；owner 为 real Compactor conformance evidence work unit。Deterministic prompt/parser tests 不能替代真实模型行为观察。
- `assigned to later work unit`：frozen oracle/scenario 的 current-head inventory/readiness proof refresh；owner 为独立 readiness refresh work unit。冻结定义 preserved 不等于 current-head readiness 已验证。
- `assigned to later work unit`：`forward_intents.status`（`open` / `blocked` / `superseded`）与 `reference_continuity.reason` 的 LLM-facing 业务语义；owner 为后续独立 LLM-facing schema work unit。

所有 residual risk 均已分类并有 owner/destination。无未分类 residual risk，无 blocking open question。

## Accepted deepreview checkpoint

未来 accepted deepreview checkpoint 的 intended files 严格为：

1. `docs/reviews/aggregate-deepreview-20260803-223339.md`
2. `docs/reviews/aggregate-deepreview-20260803-223901.md`
3. `docs/gateflow/pr-190-compactor-output-business-semantics-aggregate-deepreview-acceptance-20260803-224144.md`

Commit message：

```text
gateflow: accept deepreview for compactor output business semantics
```

Acceptance artifact 创建阶段未 stage、commit 或 push。Acceptance pass 后，accepted deepreview checkpoint 立即重新检查 branch/status，只 stage 上述三个显式路径并核对 staged diff，使用上述 commit message 创建 commit 并 push；不得包含 unrelated files。Push 完成后不创建重复 PR，直接回到 PR 190 的 existing draft PR chain，下一 gate 为 `PR review`。

## Acceptance decision

`pass`

两路 aggregate deepreview 均为 `pass / 无 finding`；历史 finding 的 accepted/rejected/deferred 裁决与 fix/re-review 最终状态完整；测试、pyright、publication hash、frozen files、docs/oracle decision 与 residual-risk ownership 均闭环。Aggregate deepreview loop 已关闭，下一未完成 gate 是 `accepted deepreview commit`；完成该 checkpoint 后，进入 PR 190 existing draft PR chain 的 `PR review`。
