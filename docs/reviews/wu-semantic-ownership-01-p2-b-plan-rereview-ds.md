# WU-SEMANTIC-OWNERSHIP-01 P2-B Plan Re-Review — AgentDS

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P2-B Host memory/test contract hardening`
- Gate: plan re-review（adversarial，不改代码）
- Plan artifact: `docs/host/wu-semantic-ownership-01-p2-b-plan.md`
- Initial reviews:
  - `docs/reviews/wu-semantic-ownership-01-p2-b-plan-review-mimo.md` (pass-with-findings)
  - `docs/reviews/wu-semantic-ownership-01-p2-b-plan-review-ds.md` (pass-with-findings)
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p2-b-plan-review-controller-adjudication.md`
- Delivery artifact: `docs/reviews/wu-semantic-ownership-01-p2-b-plan-rereview-ds.md`

## Verdict

**pass**

所有 controller 接受的 plan-review findings 均已关闭。Plan 修复准确落实了 adjudication 决定，未引入新的 underspecification 或 scope 问题。Plan 已具备进入 implementation gate 的条件。

---

## Closure Check

| # | Closure item | Source | Plan location | Status |
|---|---|---|---|---|
| 1 | typed field 落点明确，不混淆 read model field / durable schema | MiMo F1, DS F1 | S2 lines 197-200：typed field 落点优先为 `_MemoryProjectionPayloadView` 或 RunInputBuilder internal event view；明确排除 `ConversationMemorySnapshotVNext` 和 `SelectedRecentWindowItem`；`TOOL_RESULT_ACCEPTED` 分支 owner boundary 保持不变 | ✅ Closed |
| 2 | relative import resolution algorithm 明确，含 unresolvable failure | MiMo F2, DS F2 | S1 lines 138-143：五步确定性算法（文件路径+package root → 当前 package path → node.level 回溯 → 拼接 node.module → 不可解析时报明确错误）；测试覆盖 absolute / same-package / parent-package / no-module / unresolvable | ✅ Closed |
| 3 | source scan 覆盖 `test_memory_projection.py` | MiMo F3 | S1 lines 154 和 S2 line 215：`test_memory_projection.py` 加入 sentinel source scan 和 S2 negative scan 目标文件列表 | ✅ Closed |
| 4 | cross-path equivalence test 断言 exact answer text equality + no refs/digests | MiMo F4, DS F6 | S2 lines 203-208：两条路径产出文本必须完全相同；不得包含 `terminal_summary_ref`、`terminal_summary_digest`、payload ref、artifact ref、event id、digest、cursor 或 Host governance label；至少包含一个真实 durable store case（inline final_answer 为空 + terminal artifact descriptor） | ✅ Closed |
| 5 | plan 从 one-slice 改为 two-slice，避免 MiMo08 stop 阻塞 MiMo09/12 | DS F4 | §5 line 118："本 work unit 建议 2 个 implementation slices"；S1=import-boundary+snapshot fixture hardening，S2=terminal answer continuity projection contract；lines 119-121 给出拆分理由和 S1→S2 的 factory 复用依赖 | ✅ Closed |
| 6 | `dayu/host/terminal_payload.py` allowed file 条件明确 | DS F5 | S2 line 179：允许修改 `terminal_payload.py`，"仅在 terminal answer continuity resolver contract 需要同步 helper 返回类型或 typed material 时修改" | ✅ Closed |
| 7 | business test body vs digest invariant / factory sentinel 边界明确 | DS F3 | S1 line 146："factory 内部可以使用一个私有 sentinel 常量或空 digest 占位来完成 digest 计算，但业务测试体不得直接写 `snapshot_digest=\"pending\"`"；line 149：digest invariant test 集中在 factory 测试或明确命名的 invariant test；rollback `rg` 命令只扫描三个业务测试文件，factory 文件不在扫描范围内 | ✅ Closed |

---

## New Findings

无。

Plan 修复忠实反映了 controller adjudication 的七项决定，没有引入新的 underspecification、scope creep 或语义所有权漂移。两 slice 的拆分边界清晰、依赖关系明确（S1 factory → S2 cross-path equivalence test），stop condition 各自的触发范围和升级路径保持不变。

---

## Residual Risks

以下风险在原 DS review 中已识别，plan 修复后仍然存在，implementation gate 需持续关注：

### R1. `_terminal_answer.py` 与 `docs/host/design.md` 对齐后仍可能暴露 design truth gap

**状态**：不变。Plan S2 的 stop condition 正确覆盖此风险——implementation agent 必须在第一步 design truth sync 后立即判断是否触发 stop condition，不能先写 production code 再回头补 design。

**Owner**：implementation agent + gate review。

### R2. Relative import scanner 可能与现有 `_matches_prefix()` 逻辑产生交互

**状态**：不变。相对 import 解析为绝对模块名后，同一 `_matches_prefix()` 逻辑自然适用；但若解析结果与手动绝对 import 形式不一致，已有 test 的 expected list 可能需要更新。Implementation 后必须运行完整 `tests/host/test_import_boundary.py`。

**Owner**：implementation agent。

### R3. Shared memory snapshot factory 可能被后续修改绕过

**状态**：不变。CI 中的 `rg` source scan assertion 作为被动 gate 可捕获回归，但无编译期 enforce。当前 P2 级别 test hardening 不需要编译期 enforce。

**Owner**：后续 gate review + CI maintainer。

### R4. Cross-path equivalence test 可能暴露未知 semantic conflict

**状态**：不变。Plan stop condition 已列出此风险。Implementation 应优先写 equivalence test（在 production change 之前），以尽早发现冲突。

**Owner**：implementation agent。

### R5 (new, low). S1 factory 设计可能与 S2 cross-path equivalence test 需求不完全匹配

**风险**：S1 的 shared snapshot factory 在 S2 cross-path equivalence test 中首次被用于构造 durable store-backed 的 EventLog → projection → RunInputBuilder 完整链路。若 S1 的 factory 设计（如 snapshot digest 构造方式、cursor 初始化方式）与 S2 的真实 durable store case 需求不完全匹配，S2 implementation 可能需要对 factory 做轻量扩展。

**缓解**：factory 的设计范围（empty/rich snapshot、cursor、policy_digest）已是 memory snapshot 的基本构造要素，覆盖 S2 cross-path equivalence test 所需的 snapshot input 概率很高。即使需要扩展，属于同一 work unit 内的合理迭代，不需要升级为 design gate。

**Owner**：implementation agent（S2）。

---

## Review Artifact

- 本 artifact: `docs/reviews/wu-semantic-ownership-01-p2-b-plan-rereview-ds.md`
- 产出日期: 2026-07-09
- Reviewer: AgentDS (Claude Code Agent)
- 未修改任何生产代码、测试或 README。
