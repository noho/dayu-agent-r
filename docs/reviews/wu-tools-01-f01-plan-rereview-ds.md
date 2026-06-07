# WU-TOOLS-01-F01 Plan Re-Review Artifact

## Gate Metadata

- **Gate**: plan re-review
- **Work unit**: `WU-TOOLS-01-F01 Shared Fins Ingestion Runtime And Download / Preprocess Awaiting Tools`
- **Re-reviewed artifact**: `docs/host/wu-tools-01-f01-shared-fins-ingestion-runtime-plan.md`（修复后）
- **Re-review artifact**: `docs/reviews/wu-tools-01-f01-plan-rereview-ds.md`
- **Re-reviewer**: planreview skill (deepseek-v4-pro)
- **原 review artifacts**:
  - `docs/reviews/wu-tools-01-f01-plan-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-plan-review-ds.md`
- **Controller adjudication**: `docs/reviews/wu-tools-01-f01-plan-review-controller-adjudication.md`
- **Plan fix summary**: `docs/reviews/wu-tools-01-f01-plan-fix-controller-summary.md`
- **Scope guard**: 只复核已接受 finding 的修复状态，不扩大到新的完整 plan review。不修改任何文件，不 commit/push/PR。

## Re-Review Scope

本次 re-review 仅复核以下 6 个已接受 finding 在修复后 plan 中的修复状态：

1. S3 download scope（Mimo F01 / DS F02）
2. Provider/runtime sharing（DS F01）
3. S5 provider detection（DS F03 / Mimo F02）
4. Job store path（DS F04 / Mimo F03）
5. `include_ingestion_tools` transition（DS F05 / Mimo F05）
6. LLM-facing schema self-containment + processor/storage boundary（Mimo F04 / Mimo F06）

## Validation Run（只读）

```text
$ git branch --show-current
host-wu-tools-01-f01

$ ls dayu/fins/ingestion* 2>&1
No such file or directory
→ 确认：ingestion_runtime.py 尚未实现，plan S1-S3 为全新实现路径。

$ ls dayu/cli 2>&1
ls: dayu/cli: No such file or directory
→ 确认：CLI boundary 决策仍然有效。

$ ls dayu/fins/tools/download_provider.py dayu/fins/tools/preprocess_provider.py \
      dayu/fins/tools/download_tools.py dayu/fins/tools/preprocess_tools.py 2>&1
均不存在
→ 确认：download/preprocess provider 文件尚未创建，plan S4 为全新实现。

$ grep "include_ingestion_tools" dayu/fins/tools/provider.py
_CONFIG_INCLUDE_INGESTION_TOOLS_FIELD: Final[str] = "include_ingestion_tools"
    include_ingestion_tools = _parse_bool_default(...)
    if include_ingestion_tools:
→ 确认：fail-closed include_ingestion_tools 代码仍在，plan S4/S6 移除目标有效。

$ grep -n "wait_adapter_registry=None" dayu/service/host_assembly.py
1046:        wait_adapter_registry=None,
→ 确认：host_assembly 仍硬编码 wait_adapter_registry=None，plan S5 wiring 变更点准确。
```

所有原始 review 的代码证据断言仍然成立，plan 修复未引入与代码现状的矛盾。

---

## Finding-by-Finding Re-Review

### Finding 1 — S3 Download Scope（Mimo F01 / DS F02）

**Controller 要求**：S3 实现 typed download runtime + source adapter protocol + deterministic no-network fake adapter test path + storage write path + unsupported-source failure；F01 不实现真实 SEC/CN/HK network download adapters。

**修复后 plan 证据**：

- S3 Non-goals（第 411 行）：`"No real SEC/CN/HK network download adapter implementation in F01."` — 精确排除真实网络 adapter。
- S3 Completion signal（第 430-432 行）：`"Download runtime has a production-owned typed entry point, adapter protocol, deterministic no-network fake adapter test path, storage write path and explicit unsupported-source failure. Real SEC/CN/HK network adapter breadth is deferred to a later owner or explicit user-approved scope expansion."` — 五个验收维度逐一列明，与 Controller 要求完全一致。
- Download adapter scope 专区（第 184-188 行）：`"F01 implements the typed download runtime, the source adapter protocol, deterministic no-network fake adapter test path, storage write path and explicit unsupported-source failure. F01 does not implement real SEC/CN/HK network download adapters."` — 在 §Implementation Decisions 中作为独立专区明确边界。
- S3 Exact allowed changes（第 384-392 行）：逐项列出 adapter protocol、fake adapter、normalize_ticker、storage write、unsupported-source failure。
- S3 Stop condition（第 434-436 行）：`"Stop and request user decision before adding real SEC/CN/HK network download adapters"` — stop condition 精确到具体动作。

**状态：已修复**

---

### Finding 2 — Provider/Runtime Sharing（DS F01）

**Controller 要求**："Shared runtime" = shared Fins business code + workspace-scoped durable state，不是 Python singleton；禁止 module-level singleton；same workspace 必须 atomic/locked writes。

**修复后 plan 证据**：

- Shared runtime ownership（第 141-142 行）：`""Shared runtime" means shared Fins business code plus workspace-scoped durable state. It does not require one Python object instance shared by every provider."` — 定义精确。
- 第 143 行：`"Do not introduce a module-level singleton or hidden memoized global runtime factory."` — 明确禁止 singleton。
- 第 144 行：`"Tool providers may each call DefaultFinsRuntime.create(workspace_root=...), but every runtime instance for the same workspace_root must derive the same Fins job store path and use cross-instance-safe writes."` — 允许多实例但约束一致性。
- Storage boundary（第 181-182 行）：`"The Fins job store must save only job governance records and must use atomic replacement plus a lock, or an equivalent transactional filesystem-safe mechanism, so separate runtime instances for the same workspace cannot corrupt job state."` — 并发安全机制明确。
- S1 Expected assertions（第 280-281 行）：`"Two DefaultFinsRuntime.create(workspace_root=same_root) instances read/write the same workspace-derived job store safely without sharing a Python object singleton."` — 可测试断言。

**状态：已修复**

---

### Finding 3 — S5 Provider Detection Mechanism（DS F03 / Mimo F02）

**Controller 要求**：Service assembly 从 configured provider ids/import paths/binding specs 检测 Fins awaiting providers；校验 workspace_root；不改 `ToolsDiscoveryProviderOutput`；不依赖 diagnostics strings。

**修复后 plan 证据**：

- S5 Exact allowed changes（第 544-549 行）：
  - `"Detect Fins awaiting providers from explicit configured provider ids, import paths and binding specs already visible to Service assembly."` ✓
  - `"Validate that all enabled Fins awaiting provider configs participating in one assembly have the same absolute workspace_root; fail before open_host on mismatch."` ✓
  - `"Do not change ToolsDiscoveryProviderOutput shape and do not depend on provider diagnostics strings."` ✓
- Service/composition-root adapter 专区（第 202-205 行）：`"Service assembly detects Fins awaiting providers from explicit configured provider ids, import paths and binding specs already visible in tool_discovery.json / provider config. It must not inspect diagnostic strings."` + `"Service assembly must validate that enabled Fins awaiting providers for one Host assembly use a matching absolute workspace_root"` + `"Do not change ToolsDiscoveryProviderOutput shape"` — 三约束在专属决策段重申。
- S5 Error handling（第 578-579 行）：`"Service assembly fails before open_host if Fins awaiting provider config cannot construct a wait adapter registry."` + `"Service assembly fails before open_host if enabled Fins awaiting providers have different workspace roots."` — fail-fast 行为明确。

**状态：已修复**

---

### Finding 4 — Job Store Path（DS F04 / Mimo F03）

**Controller 要求**：workspace-derived path，只保存 job governance records。

**修复后 plan 证据**：

- S1 Exact allowed changes（第 235 行）：`"Derive the job store path from workspace_root, for example <workspace_root>/.dayu/fins_ingestion/jobs, or from an equivalent explicit Fins runtime directory under the workspace."` — 具体路径示例，workspace-derived。
- Storage boundary 专区（第 181 行）：`"The Fins job store path must be deterministic from workspace_root, such as <workspace_root>/.dayu/fins_ingestion/jobs or an equivalent explicit Fins runtime directory."` — 与 S1 一致。
- 第 182 行：`"The Fins job store must save only job governance records"` — 内容约束明确。
- S1 Data flow invariants（第 258 行）：`"Job store records contain governance state only ... They must not contain source document正文, processed payloads, provider raw payloads or raw filesystem document paths exposed to tools."` — 反面排除完整。

**状态：已修复**

---

### Finding 5 — `include_ingestion_tools` Transition（DS F05 / Mimo F05）

**Controller 要求**：split providers 后删除 read-provider ingestion parsing/fail-closed test；`include_ingestion_tools` 不是 supported target config。

**修复后 plan 证据**：

- Provider split 专区（第 192 行）：`"Read provider remains read-only and must remove include_ingestion_tools parsing from the target implementation after download/preprocess providers exist."` — 移除范围明确。
- 第 193 行：`"include_ingestion_tools is not a supported target config. Workspace overlays must enable download/preprocess capability through independent download and preprocess providers."` — 目标架构声明。
- S4 Exact allowed changes（第 461 行）：`"Remove read-provider include_ingestion_tools parsing after split providers exist; after implementation, the old fail-closed test must be replaced with independent provider discovery tests."` — 代码+测试移除。
- S4 Error handling（第 490 行）：`"include_ingestion_tools is not accepted as a target enablement switch; download/preprocess enablement must come from independent providers in workspace overlay config."` — provider 层 fail-fast 语义。
- S6 Exact allowed changes（第 627 行）：`"Delete or rewrite tests that assert read-provider include_ingestion_tools fail-closed behavior; target coverage must prove independent download/preprocess provider enablement through workspace overlay config."` — 测试迁移路径。
- S6 Expected assertions（第 643 行）：`"Workspace overlay does not use include_ingestion_tools as a supported target config."` — 验收 assertion。

**状态：已修复**

---

### Finding 6 — LLM-Facing Schema Self-Containment + Processor/Storage Boundary（Mimo F04 / Mimo F06）

**Controller 裁决**：Mimo F04 "accepted as already sufficient — no additional fix required"；Mimo F06 "accepted as already sufficient — no additional fix required"。

**修复后 plan 证据**（验证原约束未被修复过程破坏）：

- S4 Tool schemas（第 465 行）：`"Tool schemas must be self-explanatory for LLMs and not expose Host internals, digest, cursor, raw job record paths or tool_call_id."` — LLM-facing 约束保留。
- S2 Storage boundary（第 336-337 行）：`"No direct writes to processed/ outside repository implementation."` — storage 边界保留。
- Storage boundary 专区（第 177-180 行）：`"Source documents, blob files, processed documents, rejected filing artifacts and batching must use dayu.fins.storage repository protocols/implementations. No direct Path(...) glob or raw JSON writes outside storage repository internals for financial document data."` — 存储边界保留。
- S2 Exact allowed changes（第 308-313 行）：preprocess 通过 `ProcessedDocumentRepositoryProtocol` 写入、processor registry 复用 — processor/storage 边界保留。
- S3 Storage write path（第 389-390 行）：download 通过 `SourceDocumentRepositoryProtocol`、blob repository、`FilingMaintenanceRepositoryProtocol` 写入 — 三 repos 路径保留。

**状态：已修复**（原约束完整保留，未被 plan 修复过程削弱）

---

## Overall Verdict

**PASS** — 全部 6 个已接受 finding 均已修复。修复后的 plan 满足 Controller adjudication 的全部要求，可以进入 implementation gate。

## Finding Status Table

| # | Finding | 原来源 | Controller 裁决 | 状态 | 关键证据行 |
|---|---------|--------|----------------|------|-----------|
| 1 | S3 download scope | Mimo F01 / DS F02 | accepted | **已修复** | Plan 第 184-188 行（Download adapter scope）、第 411 行（S3 Non-goals）、第 430-432 行（S3 Completion signal） |
| 2 | Provider/runtime sharing | DS F01 | accepted | **已修复** | Plan 第 141-144 行（Shared runtime ownership）、第 181-182 行（Storage boundary）、第 280-281 行（S1 Expected assertions） |
| 3 | S5 provider detection | DS F03 / Mimo F02 | accepted | **已修复** | Plan 第 544-549 行（S5 Exact allowed changes）、第 202-205 行（Service/composition-root adapter） |
| 4 | Job store path | DS F04 / Mimo F03 | accepted | **已修复** | Plan 第 235 行（S1）、第 181 行（Storage boundary）、第 258 行（S1 invariants） |
| 5 | `include_ingestion_tools` | DS F05 / Mimo F05 | accepted | **已修复** | Plan 第 192-193 行（Provider split）、第 461 行（S4）、第 490 行（S4 error handling）、第 627/643 行（S6） |
| 6 | LLM schema + processor/storage boundary | Mimo F04 / Mimo F06 | accepted（无需修改） | **已修复** | Plan 第 465 行（S4 schemas）、第 177-180 行（Storage boundary）、第 336-337 行（S2）、第 389-390 行（S3） |

## Remaining Blockers / Residual Risks

**无 blocker**。所有 residual risk 已正确分类：

| Risk | Classification | Owner |
|------|---------------|-------|
| Real SEC/CN/HK network download adapters | deferred-with-owner | Later Fins source-adapter owner or explicit user-approved F01 scope expansion |
| Upload ingestion | assigned to later WU | `WU-TOOLS-01-F09` |
| Future CLI download/process | assigned to later WU | Future CLI/package WU |
| SEC/Fins CI pipeline | assigned to later WU | `WU-TOOLS-01-F04/F05` |
| CN/HK Docling CI pipeline | assigned to later WU | `WU-TOOLS-01-F06/F07` |
| `WU-TOOLS-01-S1-R1` CI coverage | tracked by existing issue | F04-F07 owners |
| `WU-TOOLS-01-S1-R2` processor naming | tracked by existing issue | F08 owner |

## Completion Report

- **Artifact path**: `docs/reviews/wu-tools-01-f01-plan-rereview-ds.md`
- **Overall verdict**: PASS — 全部 6 个已接受 finding 已修复
- **Finding status**: 6/6 已修复，0 部分修复，0 未修复，0 证据失效
- **Remaining blockers**: 无
- **Residual risks**: 全部已正确分类（deferred / assigned to later WU / tracked by existing issue），无新增风险
- **Validation run**: 5 条只读核查命令全部通过，代码证据与 plan 断言一致
- **Next gate**: 可进入 implementation gate
