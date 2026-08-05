# PR 190 F11/F12 Accepted Plan Checkpoint

## Checkpoint identity

- PR: <https://github.com/noho/dayu-agent-r/pull/190>
- Gate: plan gate accepted checkpoint
- Checkpoint date: `2026-08-05`
- Branch: `codex/interactive-oracle`
- PR base: `main@113ea34d47b95812d79aa31705949bbb46bc6061`
- PR head: `codex/interactive-oracle@3087b1b983a97ce5012d54e818795f4755434a98`
- Local HEAD: `3087b1b983a97ce5012d54e818795f4755434a98`
- Reviewed plan base: `3087b1b983a97ce5012d54e818795f4755434a98`
- Checkpoint verdict: **PASS — accepted plan**
- Still-open findings: **0**
- New blockers: **0**

本 checkpoint 只冻结 plan gate 的接受状态与下一入口，不修改已经 review 的 plan、controller adjudication、两份 original review、两份 re-review、finding baseline、生产代码、设计真源或 registry。未执行 stage、commit 或 push。

## Accepted plan artifact bundle

下列 SHA-256 固定本次 accepted plan 的完整审查链；implementation 必须以这些精确内容为输入。任何 artifact 内容变化都会使本 checkpoint 失效并要求重新 plan review。

| Role | Artifact | SHA-256 |
|---|---|---|
| Code-generation-ready implementation plan | `docs/gateflow/pr-190-f11-f12-interactive-memory-plan-20260805.md` | `e869201c77f8a7275d4865c4d211056ebe26dcc8e7437350681578e3d740ae0f` |
| Controller adjudication/fix record | `docs/gateflow/pr-190-f11-f12-plan-review-adjudication-20260805.md` | `ff3e27c73952d3aa8743547530975b572b12ec1259ed594ec28a0d9278b826e4` |
| Original independent review A | `docs/reviews/plan-review-20260805-144305.md` | `d9358fe2621e70ffc1790af2ad71678ccaccb2105df4cfc9833336b6005fcfd6` |
| Original independent review B | `docs/reviews/plan-review-20260805-144405.md` | `e2bb882149f5e0de0528e99d6ee96f30fd6073a4ad2d64b214e99a7d968bace4` |
| Independent re-review A / MiMo | `docs/reviews/plan-rereview-20260805-150612.md` | `6b0d7e1052d72609a6d75d095488df5855396555e332d7f29bb664bda1898a74` |
| Independent re-review B / Claude | `docs/reviews/plan-rereview-20260805-ds.md` | `538ff5193b45a70623c4c2bba881e03ceca89a9657f7e76424153bfcdcdc8d64` |

Finding baseline 保持只读：

- `docs/reviews/wu-interactive-memory-postfix-readiness.md`
- SHA-256: `39cd2d7e28c951791e540afa5d7db63b8ede312b7d3c5d59cffff85527bf0abb`

## Two-path re-review result

| Review path | Coverage | Result | Still open | New blocker |
|---|---|---|---:|---:|
| MiMo re-review | Review A F01-F10、Review B B-01-B-07、6 个原 open questions及新 blocker scan | **PASS** | 0 | 0 |
| Claude re-review | Review B B-01-B-07、3 个原 open questions、8 个重点 contract area 及新 blocker scan | **PASS** | 0 | 0 |

两路 re-review 均确认 controller 裁决有直接证据支撑，修订后的 plan 已达到 code-generation-ready；不存在需要再次修改 plan 才能进入 implementation 的 finding 或 blocker。

## Original finding closure ledger

### Review A: F01-F10

| Finding | Controller disposition | Re-review closure |
|---|---|---|
| A-F01 Registry lifecycle、supersession 与 stable predicate resolution | accepted | **CLOSED / FIXED**：旧 accepted owner 按 lifecycle supersede，fresh owner 与 611 records/768 refs 的唯一 current accepted 解析及校验均已写入 plan。 |
| A-F02 `AsyncRunner.call` breaking signature change | accepted | **CLOSED / FIXED**：S2 同一 slice 更新 Protocol、唯一实现和全部 call sites；参数 required 且无 default。 |
| A-F03 `CompactCandidateV3` 与 structure owner | accepted | **CLOSED / FIXED**：typed domain contract 唯一归 `compaction.py`，structure projection 单向消费，不定义第二组 dataclass。 |
| A-F04 Caps DTO 与 policy owner | rejected-with-reason | **CLOSED / FIXED**：DTO 仅为 immutable mechanical projection；`MemoryProjectionPolicy` 仍唯一拥有数值、default、validation 与 digest。 |
| A-F05 Tool Trace analysis v1→fresh v2 | accepted | **CLOSED / FIXED**：删除 v1 reader/validation，不保兼容，producer/renderers/consumers/tests 同切。 |
| A-F06 Structured-output capability evidence | accepted | **CLOSED / FIXED**：DeepSeek 有官方 capability 依据；Mimo `none` 明确为 unknown 的保守值；真实装配归 S4 observation。 |
| A-F07 Rolling-correction replacement evidence | accepted | **CLOSED / FIXED**：以 retained current provenance、Host-derived omitted old labels 与下游无旧结论作为 required evidence。 |
| A-F08 S3 atomic migration review/rollback risk | rejected-with-reason | **CLOSED / FIXED**：保持单一 accepted vertical migration，并冻结 worktree 内部顺序与未提交 slice rollback。 |
| A-F09 Initial/repair template ownership | accepted | **CLOSED / FIXED**：共享 system contract 和同一 structure source，Host 分别渲染 initial/repair user body。 |
| A-F10 `session_summary` required/nullable semantics | accepted | **CLOSED / FIXED**：全部 root keys required；`session_summary` required 且 object-or-null。 |

### Review B: B-01-B-07

| Finding | Controller disposition | Re-review closure |
|---|---|---|
| B-01 S3 原子迁移切片过粗 | rejected-with-reason | **CLOSED / evidence-invalid**：拆 accepted checkpoint 会制造双 contract 或半迁移状态；固定内部序列与 rollback 控制该工程风险。 |
| B-02 Repair digest 可能泄漏至 LLM | accepted | **CLOSED / fixed**：digest 只属于 Host binding/audit/serialization；captured runner input 必须验证 value 与字段名均零泄漏。 |
| B-03 S0 design update 粒度不足 | accepted | **CLOSED / fixed**：Host/Engine 精确章节及 v2 normative semantics 删除/替换清单已经冻结。 |
| B-04 F11 pagination 任意总页数 cap | rejected-with-reason | **CLOSED / evidence-invalid**：采用每页有界、cursor 单调、short-page exhaustion 的完整 keyset scan；损坏或不推进 fail closed。 |
| B-05 DeepSeek capability 缺官方依据 | accepted | **CLOSED / fixed**：官方 JSON Output/API reference 已纳入证据边界，S4 仍验证实际装配。 |
| B-06 恢复 model-produced superseded/omission kind | rejected-with-reason | **CLOSED / evidence-invalid**：用户裁决排除不可严格验证 ledger；不得恢复主观关系或 Host 自然语言推断。 |
| B-07 Repair prompt structure 未冻结 | accepted | **CLOSED / fixed**：repair 自足且与 initial 共享 system contract、template/schema source。 |

原 Review A 的 3 个 open questions 与原 Review B 的 3 个 open questions也已全部关闭；它们不构成 implementation 前置问题。

## Gate state and next entry point

- Plan gate: **PASS / accepted**。
- Implementation: **尚未开始**；本 checkpoint 不代表任何 S0-S5 实现、设计、代码、registry 或 evidence delta 已发生。
- 下一唯一 entry point: **S0 — design truth**。先按 accepted plan 的精确章节清单更新并 review Host/Engine 设计真源，设计接受后才可进入后续 implementation slice。
- 任何实现工作必须继续遵守 accepted plan 中每 slice 的两路独立 review/fix/re-review/accepted commit，以及 aggregate deepreview、PR review 和 final closeout gates。

## Oracle status boundary

下列 replacement scenarios 的 Oracle controller 裁决仍是未来事项：

- `interactive.interactive.g06.tool-trace-formal@2`
- `interactive.interactive.g06.rolling-correction-replacement@1`
- `interactive.interactive.g06.cap-constrained-memory-replacement@1`

它们在真实 observation 后仍应保持 `unadjudicated` 或 `needs-more-evidence`，不得由本 checkpoint 预判为 accepted。该 **Oracle pending** 不阻塞本 work unit 未来完成 implementation/evidence final closeout；closeout 必须分别报告 `implementation`、`real_observation` 与 `oracle=pending`，不得合并宣称 oracle ready。

## Checkpoint readiness

**PASS**：两路 re-review 均通过，原 17 个 findings 逐项 closed，原 6 个 open questions 全部 resolved，`0 still-open / 0 new blocker`。Accepted plan bundle 与 finding baseline 已用 SHA-256 固定，可以从 S0 design truth 开始后续 implementation gate。
