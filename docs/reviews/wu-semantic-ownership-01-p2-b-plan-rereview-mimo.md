# WU-SEMANTIC-OWNERSHIP-01 P2-B Plan Re-Review — AgentMiMo

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P2-B Host memory/test contract hardening`
- Gate: re-review（确认 controller adjudication accepted findings 全部关闭）
- Plan artifact: `docs/host/wu-semantic-ownership-01-p2-b-plan.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p2-b-plan-review-controller-adjudication.md`
- Initial reviews:
  - `docs/reviews/wu-semantic-ownership-01-p2-b-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p2-b-plan-review-ds.md`

## Verdict

**pass**

全部 7 个 accepted plan-review findings 已关闭，plan 已正确应用 controller adjudication 的所有修正。无新增 blocking plan issue。

## Closure Check

| # | Accepted Finding | Source | Closure Evidence | Status |
|---|---|---|---|---|
| 1 | typed field 落点明确，不混淆 read model field / durable schema | MiMo F1 / DS F1 | Plan S2 L197-199 明确 typed field 优先落在 projection-internal view（`_MemoryProjectionPayloadView`）或 RunInputBuilder internal event view；L199 明确禁止落在 `ConversationMemorySnapshotVNext` / `SelectedRecentWindowItem`；L200 明确 `TOOL_RESULT_ACCEPTED` 分支保持当前 owner boundary。 | ✅ closed |
| 2 | relative import resolution algorithm 明确，含 unresolvable failure | MiMo F2 / DS F2 | Plan S1 L138-144 给出 5 步确定性算法：从文件路径和 package root 计算 package-relative position → `node.level` 回溯 → 拼接 `node.module` → `node.module is None` 时只返回 package prefix → 回溯超出 package root 或无法确定 prefix 时返回明确解析错误并使测试失败。L144 要求测试覆盖 absolute / same-package / parent-package / no-module / unresolvable 五种 case。 | ✅ closed |
| 3 | source scan 覆盖 `test_memory_projection.py` | MiMo F3 | Plan S1 L154 source scan assertion 覆盖 `test_compact_material.py`、`test_run_input_builder.py`、`test_memory_projection.py`；S1 L131 允许 `test_memory_projection.py` 接入 shared snapshot factory；S2 L215 明确 source scan 覆盖 `test_memory_projection.py` 防止新增 equivalence test 引入 sentinel。 | ✅ closed |
| 4 | cross-path equivalence test 断言 exact answer text equality + no refs/digests | MiMo F4 / DS F6 | Plan S2 L203-208 明确要求至少一个真实 durable store case：写入 `RUN_SUCCEEDED`（inline `final_answer` 为空）+ `terminal_summary_ref`/`terminal_summary_digest` 指向真实 terminal artifact payload → durable projection 与 RunInputBuilder 分别消费 → LLM-facing assistant answer text 字符串完全相同 → 不包含 `terminal_summary_ref`、`terminal_summary_digest`、payload ref、artifact ref、event id、digest、cursor 或 governance label。 | ✅ closed |
| 5 | plan 从 one-slice 改为 two-slice，避免 MiMo 08 stop 阻塞 MiMo 09/12 | DS F4 | Plan S1（L122-169）覆盖 MiMo 09 + MiMo 12 的 import-boundary 和 fixture hardening；S2（L171-234）覆盖 MiMo 08 的 terminal answer continuity projection contract。L120 明确 S1 独立于 S2，S1 的 snapshot fixture 供 S2 cross-path equivalence test 复用。 | ✅ closed |
| 6 | `dayu/host/terminal_payload.py` allowed file 条件明确 | DS F5 | Plan S2 L179 允许 `dayu/host/terminal_payload.py`，条件为"仅在 terminal answer continuity resolver contract 需要同步 helper 返回类型或 typed material 时修改"。 | ✅ closed |
| 7 | business test body vs digest invariant / factory sentinel 边界明确 | DS F3 | Plan S1 L146-149 明确：factory 内部可使用私有 sentinel 常量或空 digest 占位完成 digest 计算，但业务测试体不得直接写 `snapshot_digest="pending"`；`ConversationMemorySnapshotVNext(` 在 `test_compact_material.py` 与 `test_run_input_builder.py` 中只出现在 shared factory、factory test 或明确 digest invariant test 允许位置。 | ✅ closed |

## New Findings

无。

Plan 在应用 7 个修正后保持内部一致：
- S1 的 allowed files 与 S2 的 allowed files 无冲突。
- S1 的 source scan assertion 与 S2 的 negative scan 覆盖范围一致。
- S1 的 snapshot fixture factory 供 S2 的 cross-path equivalence test 复用的依赖关系明确。
- Stop conditions 未因 two-slice 拆分而减弱——每个 slice 的 stop condition 仍然独立可验证。

## Residual Risks

以下风险在 plan 中已有控制，不需要额外 plan 修正，但 implementation gate 需关注：

1. **S2 design truth sync 可能发现 design gap：** `docs/host/design.md` 当前没有显式描述 `RUN_SUCCEEDED` hot payload、terminal payload descriptor 与 assistant final-answer continuity resolver 三者的关系。Plan stop condition 覆盖了此风险。S1 可独立进行。

2. **relative import 解析与 `_matches_prefix()` 的交互：** 解析为绝对模块名后，已有的 allowed/forbidden 列表可能需要微调。Plan S1 validation 覆盖了完整 `test_import_boundary.py` 运行。

3. **cross-path equivalence test 可能暴露 semantic conflict：** RunInputBuilder 可能对 answer text 做额外截断或 wrapper。Plan stop condition 已覆盖。

## Review Artifact

- 本 artifact: `docs/reviews/wu-semantic-ownership-01-p2-b-plan-rereview-mimo.md`
- 产出日期: 2026-07-09
- Reviewer: AgentMiMo (Claude Code Agent)
- 未修改任何生产代码、测试或 README。
