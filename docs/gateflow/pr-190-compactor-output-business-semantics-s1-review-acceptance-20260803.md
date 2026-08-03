# PR 190 Compactor 输出业务语义 S1 review acceptance

## Gate metadata

- Gate：`code review -> fix -> re-review acceptance`
- Work unit：补齐 Compactor LLM-facing 输出 schema 的核心字段与显式丢弃原因业务语义
- Slice：`S1 — Compactor output business semantics`
- Branch：`codex/interactive-oracle`
- Decision：`pass`
- Completion status：`code-review-pass`
- Current gate after this artifact：`accepted slice commit`
- Next entry point：创建 accepted slice commit；checkpoint 完成后进入 `aggregate deepreview`
- Blocking open questions：无
- Artifact path：`docs/gateflow/pr-190-compactor-output-business-semantics-s1-review-acceptance-20260803.md`

本 artifact 收口 S1 的 code review/fix/re-review loop。本次只新增该 acceptance artifact，未修改任何实现、测试、prompt、manifest、hash、README、design 或 review evidence，也未执行 stage、commit、push。

## Scope and reviewed target

Review loop 覆盖单一 S1 的完整 intended implementation：

- `dayu/config/prompts/scenes/conversation_compaction_user.md`：LLM-facing 业务语义 owner；
- `tests/host/test_llm_compaction.py`：packaged prompt owner test，含 code-review fix；
- `tests/host/test_public_compact_smoke.py`：默认真实装配路径 smoke；
- `docs/cli_init_workspace_manifest_v1.json`：prompt bytes publication digest；
- `tests/cli/test_smoke_cli_init_provider_matrix.py`：冻结 manifest digest；
- implementation、fix、两路 code review 与两路 re-review durable artifacts。

明确未修改 Host typed contract、strict parser、Context Governance、Memory projection、system prompt、scene manifest、execution profile、README、design、frozen oracle/scenario 或 `docs/cli_ci.md`。Deferred `forward_intents.status` / `reference_continuity.reason` 不在本 slice。

## Code review and re-review artifacts

| Stage | Artifact | SHA-256 | Result |
|---|---|---|---|
| Code review — AgentMiMo | `docs/reviews/code-review-20260803-220950.md` | `3d1547d292af0b5a64fb55c63211e35949273d1e6cc1dbf1a18d36f1156832aa` | `pass`，无 finding |
| Code review — AgentDS | `docs/reviews/code-review-20260803-221641.md` | `d62942a55ecd0740ec84d879b561b3cd78ad9ccd899e72aa5b0819aa609b83c9` | `pass-with-findings`，F01/F02/F03 |
| Re-review route 1 | `docs/reviews/code-review-20260803-222315.md` | `46b673938ddeb857271b809f297c714634c1c13e5afd05d694afa7bb6abc7fe2` | `pass` |
| Re-review route 2 | `docs/reviews/code-review-20260803-222626.md` | `78a9c85f12c39e70ac644ab249d6d2ca2b006b4b194c524f971c289552f96458` | `pass` |

Supporting gate artifacts：

- `docs/gateflow/pr-190-compactor-output-business-semantics-s1-implementation-20260803.md`：`sha256:fd60e6b7469fbd246c2e6f6b7746599f5a3bd23b47ce2b21e1c2c2e16aede68a`；
- `docs/gateflow/pr-190-compactor-output-business-semantics-s1-code-review-fix-20260803.md`：`sha256:193e12d0054493d843e4fc1d804fa82b7e4f712f878eda8af5a2ce761075ab10`。

全部 review/re-review artifacts 已读取并纳入本 acceptance；内容与 hash 均保持不变。

## Controller adjudication and final finding status

### AgentMiMo

- 无 finding；code review `pass`。

### AgentDS F01 — `accepted` -> `已修复`

Owner test 已补齐七项 frozen semantic fragments：不得发明新结论；`superseded` 的过时/冲突/误导与 replacement 保留当前内容；`redundant` 丢弃不损失独立信息；session summary 不得加入材料没有的事实、结论或任务；claim 不得把 `trace_material` / `answer_material` 当事实依据；answer anchors 不得把工具证据、未来动作或新推断伪装成既有结论。

两路 re-review 均逐项确认七个 fragment 在 prompt 与 owner test 中闭环，每个独立判断都有独立 assertion；最终状态 `已修复`。

### AgentDS F02 — `accepted` -> `已修复`

Static forbidden-term guard 已覆盖大小写敏感的 `Compact` 类型前缀、`compaction.py`、`context_governance`、`memory.py`、`MemoryProjectionPolicy`、`SessionSummaryMemoryView`、`event_id` 与 `payload_ref`。既有 schema/source-kind 正向存在断言保留，`Compact` 不误禁业务所需的小写 schema labels。

两路 re-review 均确认当前活跃内部术语覆盖完整、prompt 无命中、业务 schema labels 无误禁；最终状态 `已修复`。

### AgentDS F03 — `rejected-with-reason`

F03 只是 F01 substring-fragment 缺口的产生机制，与 F01 同 root cause、同 owner、同修复动作，没有独立 finding。F01 的七项独立 assertion 补齐后，F03 证据不再成立；两路 re-review 均确认 duplicate 裁决合理。

不存在未修复、部分修复、needs-more-evidence 或 deferred code-review finding。

## Validation accepted

Review loop 接受以下实际验证证据：

| Validation | Result |
|---|---|
| Initial owner test file | `24 passed` |
| Initial assembled public smoke | `1 passed` |
| Memory replacement regression | `1 passed` |
| Publication/config assembly suite | `287 passed, 3 third-party deprecation warnings` |
| Fix-focused owner test | `1 passed` |
| Fix-focused public smoke | `1 passed` |
| Re-review combined host tests | `54 passed, 1 skipped`；skip 为未启用的 opt-in real provider smoke |
| Re-review Memory replacement regression | `1 passed` |
| Full pyright | `0 errors, 0 warnings, 0 informations` |
| `git diff --check` | pass，无输出 |

Deterministic tests 证明 prompt contract、production parser/governance example、replacement regression 与 publication truth；未把未运行的 real-provider smoke 冒充模型行为证据。

## Hash and publication acceptance

- Prompt owner：`sha256:a2f5711c84f6fdd51f921e5d266d05cdb3f6a34a6c8321ffc42f0c5dc75a0dce`；
- Owner test：`sha256:4d77165a473467c8fd57964e06c3b07cc5679e05917c093d98d637af6974eac0`；
- Public smoke：`sha256:64ade7605786c2308e16e087e37ee4fa5f519886113cbe33923144a526c33e31`；
- Publication manifest：`sha256:fb6d0ba8fbf01b093419d178daf09c145bc8643e03b900703a91f2a3ff005f6c`；
- CLI manifest hash test：`sha256:c86520e50941e25c5451b36669c74ad874a1da52c0145cda3ecc6fd6e7a65faa`。

Prompt digest 与 manifest 中唯一对应 entry 一致；manifest digest 与 `FROZEN_MANIFEST_SHA256` 一致。Code-review fix 未改变 prompt、manifest、CLI hash test 或 public smoke bytes；两路 re-review 均确认无 hash/scope drift。

## Docs decision

- `dayu/config/README.md`：本 slice 只兑现既有 LLM-facing prompt 自足职责，不改变 prompts 目录职责、装配、配置 schema 或用户工作流；`no-change`。
- `tests/README.md`：只强化既有 Compactor conformance tests，不新增测试层级、运行方式或维护规则；`no-change`。
- Host/design、根 README、`dayu/README.md` 与其它 design：typed contract、状态机、分层、装配和用户工作流未变；`no-change`。

## Residual risks and open questions

- `assigned to later work unit`：真实 provider 对字段分类、drop reason 与 repair cap 的稳定遵循度；owner 为 real Compactor conformance evidence work unit。
- `assigned to later work unit`：frozen oracle/scenario 的 current-head readiness refresh；owner 为独立 readiness refresh work unit。
- `assigned to later work unit`：`forward_intents.status` 与 `reference_continuity.reason` 的 LLM-facing 业务语义；owner 为后续独立 LLM-facing schema work unit。
- `fixed in current slice`：F01/F02 owner-test regression blind spots；F03 duplicate finding 随 F01 修复关闭。

所有 residual risks 均已分类并有 owner。无 blocking open question，无未分类 residual risk。

## Accepted slice checkpoint

Accepted slice commit 只允许包含以下 intended files：

1. `dayu/config/prompts/scenes/conversation_compaction_user.md`
2. `tests/host/test_llm_compaction.py`
3. `tests/host/test_public_compact_smoke.py`
4. `docs/cli_init_workspace_manifest_v1.json`
5. `tests/cli/test_smoke_cli_init_provider_matrix.py`
6. `docs/gateflow/pr-190-compactor-output-business-semantics-s1-implementation-20260803.md`
7. `docs/gateflow/pr-190-compactor-output-business-semantics-s1-code-review-fix-20260803.md`
8. `docs/reviews/code-review-20260803-220950.md`
9. `docs/reviews/code-review-20260803-221641.md`
10. `docs/reviews/code-review-20260803-222315.md`
11. `docs/reviews/code-review-20260803-222626.md`
12. `docs/gateflow/pr-190-compactor-output-business-semantics-s1-review-acceptance-20260803.md`

Commit message：

```text
gateflow: accept compactor output business semantics S1
```

Checkpoint 前必须重新检查 branch/status，只 stage 上述显式路径并核对 staged diff；不得包含 unrelated files。Accepted slice commit 完成后，Gateflow 下一入口为 `aggregate deepreview`。

## Acceptance decision

`pass`

两路初始 code review、fix artifact 与两路 re-review evidence 完整；F01/F02 已修复并独立复核，F03 duplicate 裁决成立；测试、pyright、hash、docs、scope 与 residual-risk ownership 全部闭环。S1 code-review loop 已关闭，当前 gate 为 `accepted slice commit`，checkpoint 后进入 `aggregate deepreview`。
