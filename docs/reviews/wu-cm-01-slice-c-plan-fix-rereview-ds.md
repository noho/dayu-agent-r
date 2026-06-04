# WU-CM-01 Slice C Plan Fix/Reslice Re-Review

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | Slice C plan fix/reslice re-review |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| plan artifact | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| plan fix artifact | `docs/reviews/wu-cm-01-slice-c-plan-fix-codex.md` |
| blocker artifact | `docs/reviews/wu-cm-01-slice-c-implementation-codex.md` |
| controller adjudication | `docs/reviews/wu-cm-01-slice-c-blocker-controller-adjudication.md` |
| reviewer | AgentDS |
| date | 2026-06-04 |

## 结论

**pass-with-findings** — 0 条 blocking finding，4 条 non-blocking finding。

## 动机判断

动机成立。以下从第一性原理逐条验证：

### 1. 扩大 Slice C 的必要性与充分性

**必要**。直接代码证据确认旧 `ConversationMemorySnapshot` / `MemoryProjectionPolicy` 的 production consumer 图跨越以下模块：

| Consumer | 文件 | 消费旧字段的证据 |
|---|---|---|
| RunInputBuilder | `dayu/host/run_input.py:94` | `from dayu.host.memory import ...`，读取 snapshot 渲染旧 stable block header |
| Compact material | `dayu/host/compact_material.py` | 从旧 snapshot 构造 `stable_input` / `history_input` / `evidence_input` |
| Dispatch precondition | `dayu/host/dispatch.py` | 读取 `snapshot.evidence_backed_facts` |
| Service assembly | `dayu/service/host_assembly.py:984-1013` | `_memory_projection_policy_from_config()` 映射旧 `max_pinned_items`、`max_evidence_backed_facts`、`max_working_assumptions` 等 |
| Runtime config | `dayu/runtime/config_loader.py:236-270` | `MemoryProjectionConfig` 含 14 个旧字段 |
| Tests | 多份 host/service/runtime 测试 | 构造或断言旧 snapshot/policy shape |

Controller adjudication 接受的两条路径中，路径 1（扩大 Slice C 为 pyright-clean vertical slice）是正确的选择。路径 2（双轨子 slice）会在中间状态留下旧 shape 与新 contract 并存的窗口，容易诱导 compatibility wrapper、旧字段 alias 或旧 snapshot → vNext bridge helper——这正是 plan 和 AGENTS 约束明确禁止的。

**足够**。新 Slice C allowed files 覆盖了所有 blocker evidence 中列出的 direct production consumers：
- `dayu/host/memory.py` + `durable/memory.py` — contract 定义端
- `dayu/host/run_input.py` + `compact_material.py` + `dispatch.py` + `context_fallback.py` — Host 内部 consumer 端
- `dayu/service/host_assembly.py` + `dayu/runtime/config_loader.py` — 跨层 config/assembly 端
- 所有受影响 tests — 验证端

**不过大**。plan 明确承认 "Slice C 范围大于原计划，implementation / review 复杂度上升" 并给出了接受理由。在 gated review 流程（implementation → code review → fix → re-review → controller adjudication）下，该复杂度可控。这不是一个"不可审"的 slice，而是一个"需要审得仔细"的 slice。

### 2. 是否真正解决 pyright-clean blocker

**是**。Blocker 的直接证据是：若在 allowed files 内删除旧 snapshot/policy 字段，全量 pyright 会在禁止修改的 consumers 上失败。plan fix 将所有 production consumers 和 tests 纳入同 slice allowed files，消除了"禁止修改"与"必须修改"之间的矛盾。plan 同时明确禁止 compat wrapper/re-export/old-field alias/旧 snapshot bridge/旧库兼容读取/hasattr/getattr/untyped dict/Any/lazy import/extra payload，确保不会通过旁路绕过。

### 3. dayu/runtime/config_loader.py 层中立性

**保持**。当前 `config_loader.py` 的 imports 来自 `dayu.contracts`（`JsonValue`, `ToolBundleSourceKind`）和 `dayu.runtime._agent_policy_constants`，无任何 Host/Service/Engine/UI/Fins import。

vNext `MemoryProjectionConfig` 将定义 per-semantic bounded policy 字段（`context_window_size`、selected recent window 的 item/char cap/floor、evidence fact 的 item/char cap/floor、session summary char cap、answer anchor item/char cap、forward intent item/char cap、reference continuity item/char cap/floor、inline delta repair limits、`policy_ref`）。这些是纯数据字段（int/float/str），与现有 `ContextBudgetConfig`、`ToolTruncationPolicyConfig` 等同质，不引入任何业务层依赖。

plan 的约束 "typed config view 必须按 design source 第 3 章 / 第 24 章读取同一 vNext `memory_projection_policy` 字段集合" 和 "不接受旧字段" 是正确且充分的。

**Non-blocking finding NF-1**：plan 对 vNext config JSON 字段名未给出完整 inventory。design source 24.6 描述了 policy 的语义维度（caps、floors），但没有给出 JSON 字段名映射表。implementation agent 需要从 design source + plan 描述推导实际字段名，如 `selected_recent_window_item_cap`、`evidence_fact_char_cap` 等。建议在 implementation gate 开始前先固定字段名清单并与 design source 核对，避免实现中途发现字段名歧义。

### 4. dayu/service/host_assembly.py 映射纯度

**保持**。当前 `_memory_projection_policy_from_config()`（host_assembly.py:984-1013）已是显式字段映射模式：

```python
return MemoryProjectionPolicy(
    context_window_size=context_window_size,
    max_pinned_items=policy.max_pinned_items,
    max_evidence_backed_facts=policy.max_evidence_backed_facts,
    ...
)
```

plan 要求 vNext 迁移后 "只做 config typed view 到 Host `MemoryProjectionPolicy` 的显式字段映射；不得根据 model window 或 profile id 隐式选择 policy，不得用 raw dict patch、profile lookup 或 extra payload 兜底"。这与当前模式一致，无反向依赖或 raw dict 逃逸风险。

### 5. 测试矩阵覆盖

plan 的 Slice C 测试命令覆盖以下维度：

| 维度 | 覆盖测试 |
|---|---|
| Direct consumer (projection/durable) | `test_memory_projection.py`, `test_durable_schema.py`, `test_projection_checkpoint.py`, `test_durable_concurrency_matrix.py`, `test_memory_repair.py` |
| Compact material / RunInputBuilder | `test_compact_material.py`, `test_run_input_builder.py` |
| Dispatch / recovery | `test_dispatch_scheduler.py`, `test_recovery_dispatch.py` |
| Fail-fast config | `test_config_loader.py` (vNext field accept, old field reject) |
| Service assembly | `test_host_assembly.py` |
| Admission / tool barrier | `test_admission_queue.py`, `test_toolruntime_accept_barrier.py`, `test_resolve_wait_command.py` |
| Public smoke | `test_public_open_host_multiturn_smoke.py`, `test_public_compact_smoke.py` |
| Optional: public contracts | `test_public_contracts.py`（仅当 public options policy assertions 受字段迁移影响） |
| Optional: tool wiring smoke | `test_public_tool_wiring_smoke.py`（仅当 accepted evidence material prompt 行为变化） |

覆盖充分。exit signals 中列出的断言（empty/non-empty compacted view, post-compact delta, compact boundary, fallback no high-order memory, checkpoint atomicity, old config fail fast, pyright clean）与测试矩阵一一对应。

**Non-blocking finding NF-2**：`test_memory_repair.py` 的存在性在 plan 中标注为 "如果不存在，则以 `test_memory_projection.py` 中 repair / rebuild cases 覆盖"。建议 implementation agent 在开始前先确认该文件是否存在，若不存在则在 implementation report 中明确记录替代覆盖路径。

### 6. 旧 alias / compat wrapper / facade / re-export 禁止

**严格禁止**。plan 中以下位置明确禁止：

- Slice C 实现边界："不得引入旧库兼容读取、旧字段 fallback codec、旧 item kind alias、compatibility wrapper / facade / re-export"
- Slice C 实现边界："旧 `MemoryProjectionPolicy` 字段 alias、旧 config field alias、旧 snapshot -> vNext 或 vNext -> 旧 snapshot bridge helper"
- Slice C 实现边界："通过 `hasattr` / `getattr`、无类型 dict、`Any`、lazy import 或 extra payload 跨越旧 / 新 contract"
- 旧路径保留/删除边界：多处 "不得保留" 声明

**Non-blocking finding NF-3**：plan 在 Slice C 旧路径删除边界中声明删除旧 durable item kind（`raw_user_turn`、`raw_assistant_turn`、`assistant_conclusion`、`episode_summary`、`minimum_preserve_item`、`working_assumption`、`pinned_state`），并明确 "旧库 row 不做兼容读取"。这是正确的全新 schema 起库策略。但 durable schema migration 的 fail-fast 行为（旧库打开时是 clean error 还是自动重建）在 plan 中未显式说明。建议 implementation agent 确认 `dayu/host/durable/memory.py` 的 schema version check 机制能在旧 item kind 存在时给出明确错误而非静默失败。

### 7. Slice D/E 重映射、Issue #80 映射、Residual Risks 一致性

**一致**。验证如下：

- Slice 重映射：旧 Slice C (memory durable/projection only) → 新 Slice C (memory contract + projection + prompt assembly + dispatch + config assembly)；旧 Slice D (prompt/fallback) → 合并入新 Slice C；旧 Slice E (public smoke/docs) → 新 Slice D。plan 中的 Slice D 描述、allowed files、测试命令已同步更新。
- Issue #80 映射：plan 的 "Issue-80 / Design 24.7 Evaluation Mapping" 表列出 13 个评测维度，每个都有明确状态（current scope covered / deferred-with-owner / explicit non-goal）、归属 Slice（A/B/C/D）和测试入口。该表与 design source 24.7 的 "至少覆盖以下可断言场景" 列表一致。
- Control doc next entry point：`docs/host/issues-implementation-control.md` line 147 记录 `next entry point | WU-CM-01 Slice C implementation gate`，与 plan fix artifact 声明一致。
- Residual risks：plan 的 residual risks 表覆盖了完整 eval benchmark (WU-CM-10/#80)、User Profile Memory (WU-CM-11/#115)、deep recall (#39)、tokenizer adapter、Fins integration。均有明确 deferred owner。

**Non-blocking finding NF-4**：plan fix artifact (`wu-cm-01-slice-c-plan-fix-codex.md`) 中 "已更新 `docs/host/issues-implementation-control.md`" 声称 `implementation status` 改为 `slice-c-plan-fix-complete`，`next entry point` 改为 `WU-CM-01 Slice C implementation gate`。经核对 control doc line 144/147，这两处已正确更新。但 control doc 中 WU-CM-01 段落的 implementation commits 行（line 150）未包含 Slice C plan fix 完成后的新 commit——这是因为 plan fix gate 只修改文档，不创建 implementation commit。当前状态一致，但 implementation gate 完成后需要更新该行。

## Review Summary

| 审查维度 | 结论 |
|---|---|
| 动机成立性 | pass |
| Slice C 范围扩大必要性 | pass |
| pyright-clean blocker 解决方案正确性 | pass |
| runtime/config_loader.py 层中立性保持 | pass |
| service/host_assembly.py 映射纯度 | pass |
| 测试矩阵覆盖充分性 | pass |
| 旧 compat/bridge/alias 禁止完整性 | pass |
| Slice D/E 重映射一致性 | pass |
| Issue #80 映射一致性 | pass |
| Residual risks / control doc 一致性 | pass |

## Non-Blocking Findings Summary

| ID | 严重度 | 描述 | 修复建议 |
|---|---|---|---|
| NF-1 | 低 | vNext config JSON 字段名未给出完整 inventory，implementation agent 需从 design source + plan 推导 | implementation gate 开始前固定字段名清单，与 design source 核对后写入 implementation report |
| NF-2 | 低 | `test_memory_repair.py` 存在性待确认 | implementation agent 先确认文件存在，若不存在则在 report 中记录替代覆盖路径 |
| NF-3 | 低 | durable schema migration 的旧库 fail-fast 行为未显式说明 | implementation agent 确认旧 item kind 存在时 schema version check 给出明确错误 |
| NF-4 | 低 | control doc implementation commits 行在 plan fix gate 后未变化（预期行为） | implementation gate 完成后更新该行 |
