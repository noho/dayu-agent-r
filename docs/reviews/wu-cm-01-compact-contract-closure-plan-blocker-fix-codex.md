# WU-CM-01 Compact Contract Closure Plan Blocker Fix

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | compact contract closure plan blocker fix |
| agent | AgentCodex |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| plan doc | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| implementation blocker artifact | `docs/reviews/wu-cm-01-compact-contract-closure-implementation-codex.md` |
| controller adjudication | `docs/reviews/wu-cm-01-compact-contract-closure-blocker-controller-adjudication.md` |
| blocker commit | `c6ed521e` |
| artifact path | `docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-fix-codex.md` |
| status | fixed-needs-re-review |

## Scope Judgment

blocker 动机成立，严重性评估正确。设计真源要求 Host Context Governance 只接受 vNext compact input / output，并由 Host compact closeout 写 canonical compact facts；当前 plan 却要求删除旧 compact public symbols，同时没有纳入旧 artifact writer 和仍依赖旧 symbols 的 production owner。继续 implementation 会把 agent 推向三条不合格路径：保留旧 public contract、越过 allowed files，或新增兼容桥。

本次选择扩大 Pre-Slice C，但只扩到能形成 pyright-clean compact contract closure 的最小 owner 集：

- `dayu/host/compact_artifact.py` 是 compact artifact writer 真源；既然 `tests/host/test_compact_artifact_store.py` 属于本 gate 必跑测试，production writer 必须同 gate 迁移。
- `dayu/host/memory.py` 与 `dayu/host/run_input.py` 只作为旧 compact public symbol deletion 的直接依赖 owner 纳入；允许范围仅限断开旧 compact symbol import / annotation / construction，不允许迁移 durable memory snapshot、projection algorithm、RunInputBuilder vNext memory section、Service assembly 或 Runtime config schema。
- 不降低旧 compact public symbol 删除退出信号。保留旧 symbols 会让 `dayu.host.compaction` 继续暴露旧 compact contract，无法证明不是 compatibility public contract。

该选择比把 artifact store 测试移出本 gate更合理，因为 artifact writer 与 compact event / payload / artifact closeout 是同一 compact governance 闭环；把测试移走会让 closure 名义通过，但 artifact production path 仍写旧 candidate。

## Accepted Findings Handling

| Controller accepted finding | 处理结论 | plan fix |
|---|---|---|
| `dayu/host/compact_artifact.py` owner 缺失 | accepted-fixed | Pre-Slice C allowed production files 明确加入 `dayu/host/compact_artifact.py`，并要求 `CompactArtifactWriteRequest`、artifact canonical JSON 和 descriptor metadata 从旧 candidate / quality result 迁移到 vNext output / vNext quality result。`tests/host/test_compact_artifact_store.py` 保留为必跑测试。 |
| 删除旧 public compact symbols 牵连 `memory.py` / `run_input.py` | accepted-fixed | Pre-Slice C allowed files 明确加入 `dayu/host/memory.py` 与 `dayu/host/run_input.py`，但只允许旧 compact symbol dependency severance。退出信号要求二者不再从 `dayu.host.compaction` 导入或引用旧 compact public symbols；完整 memory durable/projection、prompt assembly、config-service 仍由 Slice C 承接。 |
| `ContextCompactor` 双 public method closeout 受旧 callers 牵制 | accepted-fixed | Pre-Slice C implementation boundary 新增仓库内 production implementor / caller owner 清单，并要求同 gate 收敛到单一 public `compact()` vNext contract；`compact_request_vnext()` / `compact_vnext()` 不得作为 public protocol / production method 保留。 |

## New Allowed Owner List

Pre-Slice C 新增或明确的 owner：

- compact artifact writer：`dayu/host/compact_artifact.py`。
- old compact symbol dependency severance：`dayu/host/memory.py`、`dayu/host/run_input.py`。
- affected tests：`tests/host/test_memory_projection.py`、`tests/host/test_run_input_builder.py`、必要时 `tests/host/test_package_exports.py`。
- `ContextCompactor` production owner 清单：`dayu/host/compaction.py`、`dayu/host/llm_compaction.py`、`dayu/host/open_host.py`、`dayu/host/api.py`、`dayu/host/dispatch.py`、`dayu/host/engine_ingest.py`、`dayu/host/compaction_operation.py`。

Pre-Slice C 保留的核心 compact closure owner 不变：

- `dayu/host/compaction.py`
- `dayu/host/llm_compaction.py`
- `dayu/host/context_governance.py`
- `dayu/host/compact_material.py`
- `dayu/host/compaction_evidence.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/context_events.py`
- `dayu/host/compact_payload.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- compact contract / parser / operation / material / artifact tests and affected fake/public smoke tests.

## Deferred Owner List

仍归后续 Slice C，不进入 Pre-Slice C：

- `ConversationMemorySnapshot` vNext shape。
- durable memory rows、snapshot codec、projection checkpoint、repair path。
- full memory projection algorithm 与 `MemoryProjectionPolicy` vNext schema。
- RunInputBuilder vNext memory section rendering、fixed prompt assembly order、fallback prompt behavior。
- dispatch memory precondition and projection catch-up semantics。
- Service assembly、Runtime config loader、packaged `execution_profiles.json`。

仍归后续 Slice D 或后续 work unit：

- README / smoke closure：Slice D。
- complete Conversation Memory eval benchmark：WU-CM-10 / GitHub Issue #80。
- cross-session User Profile Memory：WU-CM-11 / GitHub Issue #115。
- deep historical recall / semantic search：GitHub Issue #39。

## Compatibility Risk Closure

本修复不引入 compatibility wrapper、alias、re-export 或旧 snapshot bridge，理由如下：

- Pre-Slice C 继续要求旧 compact candidate / material / quality helper 在 production closeout files 中不得有 class definition、public export 或 production reference。
- `compact_artifact.py` 必须直接写 vNext output / vNext quality result，不允许 vNext -> old candidate adapter。
- `memory.py` / `run_input.py` 只允许断开旧 compact public symbol 依赖；若为了保持旧 memory behavior 到 Slice C 需要临时类型，必须是 memory / run_input 自有 typed shape，且不得导出为 compact compatibility contract。
- `ContextCompactor` 必须收敛到单一 public `compact()` vNext method，不允许旧 `compact()` 与 vNext `compact_request_vnext()` / `compact_vnext()` 并存。
- Slice C 明确不再承担旧 compact public symbol deletion，只消费 Pre-Slice C 已闭合的 vNext compact event / artifact。

## Plan Changes

已更新 `docs/host/wu-cm-01-conversation-memory-plan.md`：

- Pre-Slice C allowed files/modules 增补 `compact_artifact.py`、`memory.py`、`run_input.py` 和对应测试。
- Pre-Slice C 实现边界补充 artifact writer、old compact symbol dependency severance、ContextCompactor owner closure。
- Pre-Slice C 禁止项补充：除 dependency severance 外不得混入 Slice C memory / prompt / config 内容。
- Pre-Slice C 测试命令补充 `tests/host/test_memory_projection.py`、`tests/host/test_run_input_builder.py`，public export 变化时追加 `tests/host/test_package_exports.py`。
- Pre-Slice C 退出信号补充 artifact writer closure、`memory.py` / `run_input.py` 不再引用旧 compact symbols、ContextCompactor 单 public method closure。
- Slice C 目标更新为不再承担 compact artifact writer、compact event payload closure 或旧 compact public symbol deletion。
- Allowed files summary 增补 `dayu/host/compact_artifact.py` 的 Pre-Slice C 限定。

已更新 `docs/host/issues-implementation-control.md`：

- 当前状态推进到 compact contract closure plan blocker fix complete / needs re-review。
- next entry point 改为 `WU-CM-01 compact contract closure plan blocker re-review gate`。
- 记录本 fix artifact。

## Validation

未运行 production tests 或 pyright。本 gate 按用户停止条件只修 plan / control doc / fix artifact，不进入 implementation。

已执行的验证类型：

- preflight：当前分支 `phaseflow/wu-cm-01`，工作区修改前干净。
- 文档 / 代码证据核对：读取 design、plan、control、implementation blocker、Controller adjudication，并用 `rg` 核对旧 compact symbols 在 `compact_artifact.py`、`memory.py`、`run_input.py`、`llm_compaction.py`、`context_governance.py`、`compaction_operation.py` 中的当前引用。

## Residual Risks

| 风险 | 分类 | Owner / Destination |
|---|---|---|
| Pre-Slice C 现在包含 `memory.py` / `run_input.py` dependency severance，implementation 可能误扩大到 memory durable/projection 或 prompt assembly | requiring re-review | Plan re-review 必须重点检查新增边界是否足够严格；implementation gate 必须按 allowed changes 执行 |
| 仓库外 `ContextCompactor` implementor 会因单一 public `compact()` vNext contract 发生 breaking change | assigned to later work unit | implementation report / public contract closeout 记录；本仓库内 owner 必须 pyright-clean |
| full memory contract、durable schema、config-service 和 README 尚未迁移 | covered by later approved slice | Slice C / Slice D |

## Re-Review Conclusion

需要 re-review。当前 plan fix 已处理 Controller accepted findings，但这是 compact closure owner 边界变更，必须由 re-review 明确接受后才能回到 implementation gate。
