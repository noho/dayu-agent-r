# WU-CM-01 Compact Contract Closure Plan Blocker Follow-Up Fix

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | compact contract closure plan blocker follow-up fix |
| agent | AgentCodex |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| plan doc | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| plan blocker fix artifact | `docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-fix-codex.md` |
| plan blocker fix re-review artifacts | `docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-fix-rereview-mimo.md`; `docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-fix-rereview-ds.md` |
| controller adjudication | `docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-fix-rereview-controller-adjudication.md` |
| current commit | `464bfa1c` |
| artifact path | `docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-followup-fix-codex.md` |
| status | fixed-needs-re-review |

## Scope Judgment

本次 follow-up blocker 动机成立，严重性评估正确。上一轮 fix 已把 `dayu/host/open_host.py` 与 `dayu/host/api.py` 列为 `ContextCompactor` owner，但没有纳入 Pre-Slice C allowed production files；如果 implementation 将 `ContextCompactor.compact()` 收敛为唯一 vNext public contract，这两个文件分别承担 `LLMContextCompactor` construction 与 typed option owner，不预留 allowed file 会再次导致 pyright-clean closure 不可执行。

本次修复只更新 plan / control doc / 本 artifact，不进入 implementation。修复范围严格限定为 compact contract closure plan 的可执行边界，不修改 production code、tests、README、schema、config，不 commit / push / PR。

## Accepted Findings Handling

| Controller accepted finding | 处理结论 | follow-up fix |
|---|---|---|
| Blocking：Pre-Slice C allowed production files 必须增补 `dayu/host/open_host.py` 与 `dayu/host/api.py` | accepted-fixed | Plan 的 Pre-Slice C allowed files 增补 `dayu/host/open_host.py` 与 `dayu/host/api.py`。`open_host.py` 仅限 `LLMContextCompactor` construction 与 single public `ContextCompactor.compact()` vNext contract 类型对齐；`api.py` 仅限 `HostLocalExecutionOptions.context_compactor` typed option 与 single public compact contract 类型对齐。Allowed Files / Modules Summary 同步补齐这两个文件。 |
| Scope 必须严格限定，不得混入 Service assembly、config-service、UI 或 OpenHost 行为重构 | accepted-fixed | Plan 的 implementation boundary 与 exit signal 明确禁止在 `open_host.py` / `api.py` 修改中混入 `dayu/service/host_assembly.py`、`dayu/runtime/config_loader.py`、`dayu/config/execution_profiles.json`、`dayu.ui`、OpenHost lifecycle、scheduler wiring、runtime behavior 或 public behavior 重构。 |
| Non-blocking clarification：`run_input.py` 对旧 `CompactMaterialBlockKind` enum members 的 dependency severance 边界有歧义 | accepted-fixed | Plan 明确要求删除旧 enum members 前，`run_input.py` 必须先把对 `PINNED_STATE`、`WORKING_ASSUMPTION`、`OPEN_QUESTION`、`EPISODE_SUMMARY` 等旧 members 的引用替换为 vNext section 分类 helper 或本模块私有分类；不得提前迁移 full vNext memory prompt assembly、固定 prompt section 顺序或 fallback prompt 语义。 |
| Non-blocking clarification：`EvidenceBackedFactCandidate` 处于旧导出和 vNext schema 双重语境 | accepted-fixed | Plan 新增 implementation closeout 要求：必须单独说明 `EvidenceBackedFactCandidate` 的处置策略。若当前定义完全对齐 design 24.3，可保留为 vNext shape；若不一致，必须重建或迁移到 vNext shape。禁止新旧定义并存、alias、compatibility re-export 或旧 candidate wrapper。 |

## Plan Changes

已更新 `docs/host/wu-cm-01-conversation-memory-plan.md`：

- Pre-Slice C allowed files/modules 增补 `dayu/host/open_host.py` 与 `dayu/host/api.py`，并同步到 Allowed Files / Modules Summary。
- Pre-Slice C implementation boundary 增补 `open_host.py` / `api.py` 的极窄修改范围：只允许 compactor construction、typed option 和 single public compact contract 类型对齐。
- Pre-Slice C 禁止越界范围明确包含 Service assembly、config-service、UI、OpenHost lifecycle、scheduler wiring、runtime behavior 与 public behavior 重构。
- `run_input.py` dependency severance 边界明确为旧 enum member 删除前替换到 vNext section 分类 helper 或本模块私有分类，且不得提前迁移 full vNext memory prompt assembly。
- `EvidenceBackedFactCandidate` 处置策略被纳入 implementation closeout 与退出信号。
- 条件测试说明补充：若 `api.py` typed option 或 `open_host.py` compactor construction 因 single public compact contract 需要测试同步，追加 `tests/host/test_public_open_host_options.py` 与 `tests/host/test_open_host_runtime.py`，并运行全量 pyright。

## Control Doc Changes

已更新 `docs/host/issues-implementation-control.md`：

- `implementation status` 更新为 `compact-contract-closure-plan-blocker-followup-fix-complete-needs-rereview`。
- `next entry point` 更新为 `WU-CM-01 compact contract closure plan blocker follow-up fix re-review gate`。
- 新增 `compact contract closure plan blocker follow-up fix artifacts` 记录本 artifact 路径。

## Validation

未运行 production tests 或 pyright。本 gate 的停止条件是只修 plan / control doc / follow-up artifact，不进入 implementation。

已执行的验证：

- preflight：当前分支为 `phaseflow/wu-cm-01`，修改前工作区干净。
- 文档证据核对：读取 plan、control doc、上一轮 blocker fix artifact、MiMo / DS re-review artifact 与 Controller adjudication。
- 范围核对：本次只修改允许的三个文件：`docs/host/wu-cm-01-conversation-memory-plan.md`、`docs/host/issues-implementation-control.md`、`docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-followup-fix-codex.md`。

## Residual Risks

| 风险 | 分类 | Owner / Destination |
|---|---|---|
| 本 follow-up fix 仍需 re-review 确认 allowed files、implementation boundary、exit signal 与条件测试说明足够严格 | requiring re-review | WU-CM-01 compact contract closure plan blocker follow-up fix re-review gate |
| Pre-Slice C implementation 仍可能误把 `open_host.py` / `api.py` 类型对齐扩大为 OpenHost 行为或 Service/config assembly 变更 | requiring re-review | re-review 与 implementation gate 必须按本 plan 的 allowed changes 执行 |
| full memory contract、durable schema、RunInputBuilder vNext prompt assembly、config-service 和 README 尚未迁移 | covered by later approved slice | Slice C / Slice D |

## Conclusion

本 follow-up fix 已处理 Controller accepted findings。下一入口是 `WU-CM-01 compact contract closure plan blocker follow-up fix re-review gate`。本轮按停止条件到此停止，不进入 implementation、review、commit、push 或 PR。
