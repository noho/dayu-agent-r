# WU-CM-01 Compact Contract Closure Plan Blocker Fix Re-Review Controller Adjudication

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | compact contract closure plan blocker fix re-review adjudication |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| plan blocker fix artifact | `docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-fix-codex.md` |
| re-review artifacts | `docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-fix-rereview-mimo.md`; `docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-fix-rereview-ds.md` |
| controller | AgentController |
| date | 2026-06-04 |

## Verdict

`plan-fix-required`。

AgentCodex 的 plan blocker fix 方向正确：`compact_artifact.py` 必须纳入 compact closure，`memory.py` / `run_input.py` 可以作为旧 compact symbol dependency severance owner 极窄纳入，且不应降低旧 public compact symbol 删除退出信号。

但 AgentMiMo 的 blocking finding 成立。Plan 已把 `dayu/host/open_host.py` 与 `dayu/host/api.py` 列为 `ContextCompactor` 同 gate owner，却没有把它们加入 Pre-Slice C allowed production files。若 implementation 改 `ContextCompactor.compact()` 为唯一 vNext public method，这两个文件是 typed construction / typed option 的直接 owner；不预留 allowed files 会再次触发 allowed-files blocker。

## Finding Adjudication

| finding | 来源 | 裁决 | 理由 | 修复要求 |
|---|---|---|---|---|
| `open_host.py` / `api.py` 被列为 ContextCompactor owner 但未纳入 allowed files | MiMo F1, DS F1 | accepted-blocking | `dayu/host/api.py` 直接持有 `ContextCompactor` typed option；`dayu/host/open_host.py` 直接构造 `LLMContextCompactor`。如果 protocol / constructor 因单一 vNext `compact()` contract 变更需要同步，这两个文件必须可改，否则 pyright-clean closure 不成立。 | Pre-Slice C allowed production files 必须增补 `dayu/host/open_host.py` 与 `dayu/host/api.py`，并将 scope 限定为 `ContextCompactor` / `LLMContextCompactor` construction、typed option 和 single public compact contract 对齐；不得混入 Service assembly、config-service 或 UI。 |
| `run_input.py` 对 `CompactMaterialBlockKind` 旧 enum members 的 dependency severance 边界有歧义 | MiMo F2 | accepted-non-blocking | 当前 plan 已允许 `run_input.py` 极窄断开旧 compact material enum 依赖，但应进一步说明旧 enum member 删除前必须替换为 vNext section 分类 helper 或本模块私有分类。 | 在 plan fix 中补一句边界澄清；不阻塞 fix 方向。 |
| `test_package_exports.py` 条件触发正确 | MiMo F3 | accepted-non-blocking | Pre-Slice C 会删除旧 `__all__` export，条件测试已覆盖。 | 无需额外 plan fix；implementation 触发 public export 变化时必须运行。 |
| `EvidenceBackedFactCandidate` 迁移策略未单独裁决 | DS F2 | accepted-non-blocking | 该符号同时处于当前旧导出和 vNext schema 语境，implementation closeout 必须裁决保留、重建或迁移，不能新旧定义并存。 | Plan fix 补充 implementation report 必须单独说明该符号的 closeout 策略；不要求 plan 穷举具体实现。 |

## Next Gate

进入 `WU-CM-01 compact contract closure plan blocker follow-up fix gate`。

AgentCodex 只应修改 plan / control doc / follow-up artifact，不进入 implementation。修复完成后必须再次 re-review。
