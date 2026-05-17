# P9.5 Pre-P10 Cross-Repository Hardening Plan Review — AgentDS

## Gate

- **Work unit**: P9.5 Pre-P10 Cross-Repository Hardening PR plan review.
- **Review role**: AgentDS, review-only.
- **Reviewed artifact**: `docs/host/p9-5-pre-p10-hardening-plan.md`.
- **Design truth**: `docs/host/design.md`.
- **Control truth**: `docs/host/implementation-control.md`.
- **Additional truths**: `dayu/README.md` logging and Contract Ownership, `docs/design.md` tool boundary, `dayu/engine/README.md` Runner interface.
- **Date**: 2026-05-17.

## Summary

该 plan 整体质量高，覆盖了 `docs/host/implementation-control.md:1486-1521` 列出的全部 P9.5 追踪项（共 22 项），切片按 semantic ownership 划分且依赖顺序合理。每个 slice 都有明确的 non-goals、stop conditions、targeted tests 和 validation commands。未发现会导致整体阻塞的架构级缺陷。

以下为按严重性排序的 findings。

---

## Findings

### F1 [MEDIUM] S14 "current_goal first-write-wins" 规格不足

**Evidence**:

- Plan line 317: `Enforce current_goal first-write-wins if current code does not.`
- Plan 全文未定义 `current_goal` 是什么、位于哪个模块、写路径是什么、first-write-wins 在技术上如何验证。

**Why it matters**:

实施 agent 拿到这条指令后无法直接落地——必须先自行发现 `current_goal` 的当前实现位置、写路径以及 first-write-wins 在现有代码中的含义，然后推断 enforcement 方式。这增加了实施偏差的风险：不同 agent 可能对 first-write-wins 有不同理解（CAS？唯一约束？应用层检查？）。

**Required fix**:

在 plan 中补充：
1. `current_goal` 的类型定义位置（当前代码中哪个模块/类）。
2. 写 `current_goal` 的路径（通过哪些 production code path）。
3. first-write-wins 的具体 enforcement 方式（例如唯一约束、应用层 CAS、或事务内条件插入）。
4. 如何验证 enforcement（测试策略）。

**Blocks implementation**: 仅阻断 S14（Memory Cleanup），不阻断 S1-S13 及 S15+。

---

### F2 [MEDIUM] S14 "legacy SessionContinuityProvider parameters" 操作不明确

**Evidence**:

- Plan line 318: `Remove or tighten legacy SessionContinuityProvider parameters so it cannot bypass memory history pool budget.`
- Plan 未解释 `SessionContinuityProvider` 在哪里、哪些 parameters 被视为 legacy、bypass memory history pool budget 的机制是什么、'tighten' 的具体方向（添加校验？修改签名？限制参数范围？）。

**Why it matters**:

"Remove or tighten" 给了实施 agent 两个方向截然不同的选择（删除 vs 收紧），但 plan 没有提供选择标准。如果实施 agent 选择了 tighten 但实际应该 remove，会留下不必要的代码；反之可能破坏仍在工作的功能。此外，"bypass memory history pool budget" 的 bypass 机制未被描述，实施 agent 可能只修表面而未消除真正的 bypass 路径。

**Required fix**:

在 plan 中明确：
1. `SessionContinuityProvider` 的模块路径。
2. 哪些参数/行为需要变更。
3. bypass 的具体机制（例如通过某个参数跳过 pool budget 检查）。
4. 倾向的处理方向（remove 还是 tighten），以及选择标准。

**Blocks implementation**: 仅阻断 S14，不阻断其他 slice。

---

### F3 [LOW] S10/S14 对 `tests/host/test_resolve_wait_command.py` 的共享修改权

**Evidence**:

- Plan line 252 (S10): `tests/host/test_resolve_wait_command.py` 在 allowed files 中。
- Plan line 314 (S14): 同样列出 `tests/host/test_resolve_wait_command.py`。

S10 处理 late `resolve_wait` rejection redundant catch-up cleanup，S14 处理 memory catch-up end-to-end tests。两者通过同一测试文件施加不同关注点。

**Why it matters**:

虽然 S10 在 S14 之前执行（按 slice number 排序），但 S14 可能无意中破坏或弱化 S10 添加的测试断言。Plan 未提供跨 slice 的测试文件修改协调规则。

**Required fix**:

在 plan 的 "Implementation Decisions" 或 S10/S14 各自的 stop conditions 中增加一条规则：S14 修改 `test_resolve_wait_command.py` 时，不得删除、弱化或绕过 S10 添加的测试断言；如需要重构共享 fixture，必须在 slice report 中说明。

**Blocks implementation**: 否。可接受的 sequencing risk，但建议在 controller 派发 S14 时明确提醒。

---

### F4 [LOW] S15 缺少"先审计现有日志"步骤

**Evidence**:

- Plan lines 329-343 (S15): "add only necessary logs for P1-P9 implemented paths according to documented level semantics."
- S15 的 Exact changes 直接进入"Add VERBOSE/DEBUG/WARN/ERROR/CRITICAL logs"但未要求实施 agent 先审计当前已有日志。

**Why it matters**:

不审计现有日志可能导致：
- 在已有日志的地方重复添加日志。
- 遗漏缺少日志但未被注意的路径。
- 无法区分"已有但 level 不对"和"完全缺失"两种情况。

**Required fix**:

在 S15 Exact changes 最前面增加一步：`Audit existing Engine/Host log calls against documented level semantics; identify gaps, mis-leveled logs, and unlogged P1-P9 paths before adding new logs.`

**Blocks implementation**: 否。实施 agent 可以在 S15 开始时自行审计，但 plan 应显式要求这一步以降低遗漏风险。

---

### F5 [LOW] S11 ToolRuntime 机械拆分可能暴露测试中的私有类型依赖

**Evidence**:

- Plan lines 270-272: "If `tool_runtime.py` remains too large for targeted changes, mechanically extract private helpers by owner... If moving types used by tests, update tests to import from true owner or public documented entry."
- Plan line 273: "Existing ToolRuntime tests must remain behavior-identical."

**Why it matters**:

机械拆分把私有类型移到 `tool_runtime_*.py` 时，已有测试可能通过相对导入或模块内部路径访问这些类型。Plan 的处理策略是"update tests to import from true owner"，但如果 true owner 是 private module（`_*.py`），测试直接 import private module 会引入新的 import boundary 问题——测试依赖了不应对测试暴露的内部模块。

**Required fix**:

在 S11 stop conditions 中补充：如果类型移动后测试需要 import private module，优先考虑是否应通过 public documented entry 暴露该类型，或该测试是否应改为 behavior test（通过 public API 间接验证）。不得为测试保留 private module 的 re-export。

**Blocks implementation**: 否。S11 的 stop condition 已覆盖"extraction requires public compatibility wrappers"的情况。

---

### F6 [Observation] Plan 整体架构边界保持良好，无 blocking findings

以下方面经逐 slice 检查，确认符合设计真源：

- **无 P10+ 语义泄漏**：每个 slice 的 non-goals 和 stop conditions 明确禁止 Context Governance、RECOVERING、RemoteProxy、ToolsDiscovery、Audit/Tool Trace/Outbox sinks、purge/retention 等 P10+ 能力。
- **无 runner factory/registry**：S1 明确"不引入 runner factory / registry / provider selection contract"，helper 是 private、current-default-only。
- **无 compat re-export/wrapper**：所有 slice 的 stop conditions 均禁止 compatibility wrapper/re-export。
- **无 extra payload bag**：Forbidden changes 明确禁止 untyped metadata 作为显式参数传递方式。
- **无 Any/object 签名**：Non-goals 明确禁止。
- **日志非真源**：S15 明确"logs never include full prompts, tool args/results..."，S15 stop condition 禁止"exposing logs as public API"。
- **Engine 不理解 Host 治理**：S2 stop condition 明确"making Engine understand Host governance"为停止条件；S16 的 import boundary tests 覆盖此项。
- **状态机不变**：Forbidden changes 明确"No new Host/Engine state-machine states or transitions except fail-closed validation"。
- **Schema 只做 fresh**：S5 明确"fresh schema only; no old DB compatibility migration"。
- **文档更新触发规则对齐 CLAUDE.md**：S17 和 Documentation Decision 章节明确按 README 职责范围触发更新。

---

## Residual Risks

以下 risk 已在 plan 中识别，确认处置合理：

1. **Message/tool result size governance 可能无现有 typed detail 表达超限错误**（Plan lines 456-457）— plan 要求在 S13 遇到此情况时 stop for controller，处置正确。
2. **Contract Ownership audit 可能发现 misplaced public exports**（Plan lines 457-458）— plan 要求 stop for controller，处置正确。
3. **Schema CHECK hardening 可能需要 bump HOST_SCHEMA_VERSION**（Plan lines 458-459）— plan 允许 fresh-schema-only bump，处置正确。
4. **ToolRuntime 模块拆分可能过宽**（Plan line 459）— plan 要求 stop and re-slice，处置正确。
5. **Production memory catch-up wiring 可能暴露 snapshot history coupling**（Plan lines 460-461）— plan 要求 reassign to snapshot history PR，处置正确。

以下 risk plan 未显式列出，建议关注：

6. **S14 的两个 underspecification（F1, F2）可能导致 S14 实施停滞**— 需在 controller dispatch S14 前补充规格。
7. **S18 aggregate validation 的 `pytest -q` 可能耗时过长**— plan 已承认此风险（line 466）并允许 slice agent 先跑 targeted tests，处置合理。

---

## Conclusion

- **Blocking findings**: 0（无阻断整个 plan 推进的 finding）。
- **Medium findings requiring fix before S14 dispatch**: 2（F1, F2）。
- **Low findings**: 3（F3, F4, F5）。
- **Plan 可进入 controller adjudication**：S1-S13 及 S15-S18 的 slice 规格足够支撑实施；S14 需要在 controller 派发前根据 F1/F2 补充 current_goal 和 SessionContinuityProvider 的规格细节。
