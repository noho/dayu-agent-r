# WU-CM-01 Compact Contract Closure Plan Re-Review

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | compact contract closure plan re-review gate |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| plan doc | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| plan artifact | `docs/reviews/wu-cm-01-compact-contract-closure-plan-codex.md` |
| original review artifacts | `docs/reviews/wu-cm-01-compact-contract-closure-plan-review-mimo.md`; `docs/reviews/wu-cm-01-compact-contract-closure-plan-review-ds.md` |
| controller adjudication | `docs/reviews/wu-cm-01-compact-contract-closure-plan-review-controller-adjudication.md` |
| fix artifact | `docs/reviews/wu-cm-01-compact-contract-closure-plan-fix-codex.md` |
| reviewer | mimo |
| date | 2026-06-04 |
| review scope | 只判断 fix 是否完整处理 Controller accepted findings，以及 Pre-Slice C 是否足以进入 implementation；不修改 production code / tests / README / plan |
| conclusion | **pass** |

## Accepted Findings 处理逐项核对

### DS B1：`tests/host/test_compact_artifact_store.py` 纳入 Pre-Slice C

**Controller 裁决：** accepted。Fix 要求：加入 Pre-Slice C allowed tests、测试命令、退出信号，限定为 artifact store 的 vNext candidate / quality check / material JSON 迁移。

**fix 处理验证：**

| 位置 | Plan 行号 | 内容 | 状态 |
|---|---|---|---|
| allowed files | 250 | `tests/host/test_compact_artifact_store.py`，仅限 artifact store 的 vNext candidate / quality check / material JSON 迁移 | ✓ |
| 测试命令 | 282 | `pytest tests/host/test_compaction_contract.py ... tests/host/test_compact_artifact_store.py -q` | ✓ |
| 退出信号 must-pass tests | 301 | 显式列出 5 个 must-pass 测试，包含 `test_compact_artifact_store.py` | ✓ |
| Test Matrix | 551 | `pytest tests/host/test_compact_artifact_store.py -q` | ✓ |
| 最终验证命令 | 589 | 包含 `tests/host/test_compact_artifact_store.py` | ✓ |

**scope 限定验证：** allowed files 限定为"仅限 artifact store 的 vNext candidate / quality check / material JSON 迁移"。该文件当前 import `CompactionCandidate`、`CompactMaterialBlockKind`、`check_compaction_candidate()`（review DS B1 直接证据），迁移 scope 自然收敛到这些旧 contract 的 vNext 替换，不会扩大到 artifact store 的 I/O 语义本身。

**结论：** 完整处理。

---

### DS B2：`dayu/host/compaction_evidence.py` 纳入 Pre-Slice C

**Controller 裁决：** accepted。Fix 要求：加入 Pre-Slice C allowed files，限定为 compact evidence material section label / vNext material contract 迁移。

**fix 处理验证：**

| 位置 | Plan 行号 | 内容 | 状态 |
|---|---|---|---|
| allowed files | 240 | `dayu/host/compaction_evidence.py`，仅限 compact evidence material section label / vNext material contract 迁移 | ✓ |
| implementation boundary | 262 | `compaction_evidence.py` 如仍生产 compact evidence material，必须同步使用 vNext material section label，不得继续依赖旧 `CompactMaterialBlockKind` 或旧 material JSON field | ✓ |

**scope 限定验证：** 该文件当前使用 `CompactMaterialBlockKind.RAW_ASSISTANT_TURN`（review DS B2 直接证据）。若 Pre-Slice C 重构 `CompactMaterialBlockKind` 枚举（删除旧 `PINNED_STATE` / `WORKING_ASSUMPTION` / `OPEN_QUESTION` / `EPISODE_SUMMARY`），`RAW_ASSISTANT_TURN` 作为非删除目标可能需要同步迁移到 vNext section label。Plan 的 scope 限定确保此迁移被 gate 控制。

**结论：** 完整处理。

---

### DS B3：退出信号重写

**Controller 裁决：** accepted。Fix 要求：重写退出信号——旧 candidate/type/helper 在 production closeout files 中不得有 class definition、public export 或 production reference；历史 docs/implementation report 可命中；若保留旧 symbol，必须是私有、不可导出、非 production path，并由 report 给直接证据。

**fix 处理验证：**

Plan 第 296 行退出信号原文：

> 旧 candidate / type / helper 在 production closeout files 中不得再有 class definition、public export 或 production reference；production closeout files 包括 `dayu/host/compaction.py`、`dayu/host/llm_compaction.py`、`dayu/host/context_governance.py`、`dayu/host/compaction_operation.py`、`dayu/host/context_events.py`、`dayu/host/compact_payload.py`、`dayu/host/compact_material.py`、`dayu/host/compaction_evidence.py`。历史 docs、review artifact、implementation report 可命中旧 symbol。若 implementation 因未切换后续非 production path 而保留任何旧 symbol，必须是私有、不可导出、非 production path，并在 implementation report 中给出直接代码证据和 owner。

**改进点：**

1. 不再依赖盲 grep 作为唯一标准——消除了原 review B3 指出的 grep 命中 class 定义与"unused 删除候选"的张力。
2. 逐文件列出 production closeout files（8 个文件），消除歧义。
3. 明确了保留旧 symbol 的三个条件：私有、不可导出、非 production path。
4. 要求 implementation report 给直接代码证据和 owner，保证可审计。

**结论：** 完整处理。

---

### MiMo Finding 1：显式列出 must-pass tests

**Controller 裁决：** accepted。Fix 要求：显式列出 `test_compaction_contract.py`、`test_llm_compaction.py`、`test_compaction_operation.py`、`test_compact_material.py`、`test_compact_artifact_store.py`。

**fix 处理验证：**

Plan 第 301 行：

> 必须通过的 tests 明确包括：`tests/host/test_compaction_contract.py`、`tests/host/test_llm_compaction.py`、`tests/host/test_compaction_operation.py`、`tests/host/test_compact_material.py`、`tests/host/test_compact_artifact_store.py`。触发 fake/public smoke 条件时，必须追加对应 `tests/host/fake_compaction.py` consumer 测试和 `tests/host/test_public_compact_smoke.py`。

**结论：** 完整处理。5 个 must-pass tests 全部显式列出，fake/public smoke 追加条件也已写明。

---

### MiMo Finding 2：vNext positive adoption exit signals

**Controller 裁决：** accepted。Fix 要求：增加 positive signals——`context_governance.py` production accept barrier 使用 vNext checker；operation closeout/repair/fallback 使用 vNext candidate。

**fix 处理验证：**

Plan 第 299 行：

> `context_governance.py` 的 production accept barrier 使用 vNext checker；operation accepted / rejected / repair exhausted / fallback closeout、whole-candidate repair 和 failed fallback 均使用 vNext candidate、vNext quality issue 与 vNext payload / artifact helper。

**结论：** 完整处理。exit signals 现在同时包含 negative（旧符号删除）和 positive（vNext 入口确认）验证。

---

### DS N1/N2/N4/residual：contract clarifications

**Controller 裁决：** accepted。Fix 要求：明确 `compact()` / `compact_request_vnext()` 收敛策略、`run_compaction_operation()` compactor 参数类型、旧 payload constants 清理、外部 `ContextCompactor` implementor residual risk。

**fix 处理验证：**

| Finding | Plan 行号 | 内容 | 状态 |
|---|---|---|---|
| N1: `compact()` / `compact_request_vnext()` 策略 | 256 | `compact_request_vnext()` 只能作为未导出的内部拆分 helper，由 public `compact()` 调用；slice closeout 时不得形成双 public method | ✓ |
| N2: `run_compaction_operation()` compactor 参数类型 | 257 | 必须是返回 vNext output 的 `ContextCompactor` protocol；不得继续以旧 `CompactionCandidate` compactor annotation | ✓ |
| N4: `context_events.py` 旧 payload cleanup | 265 | 旧 compact payload constants、旧 field allowlist、旧 payload reader/writer helper 必须同步清理 | ✓ |
| residual: 外部 ContextCompactor implementor | 307 | 当前 slice owner 必须通过 package exports/tests/pyright 识别仓库内 implementor，仓库外 implementor 风险作为 public contract breakage 在 implementation report 中列明 | ✓ |

**结论：** 完整处理。

---

## Pre-Slice C Implementation Readiness 检查

### Owner 缺口检查

| allowed file | owner scope | 无缺口 |
|---|---|---|
| `dayu/host/compaction.py` | 核心 compact contract 定义 | ✓ |
| `dayu/host/llm_compaction.py` | LLM parser | ✓ |
| `dayu/host/context_governance.py` | quality checker | ✓ |
| `dayu/host/compact_material.py` | material pack 构造 | ✓ |
| `dayu/host/compaction_evidence.py` | compact evidence material section label | ✓ |
| `dayu/host/compaction_operation.py` | operation closeout | ✓ |
| `dayu/host/context_events.py` | 条件：payload reader/writer | ✓ |
| `dayu/host/compact_payload.py` | 条件：artifact JSON helper | ✓ |
| `dayu/host/dispatch.py` | 条件：proactive closeout | ✓ |
| `dayu/host/engine_ingest.py` | 条件：reactive closeout | ✓ |
| 7 个测试文件 | 各有明确 scope 限定 | ✓ |

所有 allowed files 均有明确 owner 和 scope 限定，无遗漏。

### 跨层越界检查

- Plan 第 275 行禁止混入 Slice C 内容：`memory.py`、`durable/memory.py`、`run_input.py`、`host_assembly.py`、`config_loader.py`、`execution_profiles.json`、memory durable schema — **无越界**。
- `compaction_evidence.py` 仅限 compact evidence material section label 迁移，不涉及 memory projection — **无越界**。
- `dispatch.py` / `engine_ingest.py` 仅限 compact event/artifact closeout，不得引入 memory durable write 或 RunInputBuilder — **无越界**。

### 兼容 wrapper/alias 风险检查

禁止项覆盖（plan 第 271-276 行）：

| 禁止项 | 防止的风险 | 有效 |
|---|---|---|
| 旧 candidate wrapper/facade/re-export | 旧 `CompactionCandidate` 借壳保留 | ✓ |
| 旧 material field alias | `stable_input` 等字段借壳保留 | ✓ |
| 旧 block kind enum alias | 旧到新的运行时兼容桥 | ✓ |
| 旧 snapshot bridge | `ConversationMemorySnapshot` ↔ vNext 双向 helper | ✓ |
| `hasattr`/`getattr`/无类型 dict/`Any`/lazy import/extra payload | 类型逃逸 | ✓ |

### Implementation Scope 检查

Pre-Slice C scope 聚焦在 compact contract domain 的 4 个核心生产文件 + 1 个条件文件 + 3 个条件文件 + 7 个测试文件。不引入 memory/projection/config-service 迁移。不过大。

### 与 design.md 一致性检查

- compact I/O 收敛到 `ConversationCompactInputVNext` / `ConversationCompactOutputVNext`（design 24.3）— ✓
- vNext material section 对齐 design 24.3 section allowlist — ✓
- `context_governance.py` 使用 vNext checker 对齐 design 25 章 — ✓
- whole-candidate repair 不 partial materialize（design 25 章）— ✓
- `current_input_anchor` not citable（design 24.3）— ✓

无冲突。

---

## Non-blocking Observations

### O1：`test_llm_compaction.py` 迁移规模

该文件有 ~30+ 测试函数调用 `compactor.compact()`（旧方法，返回 `CompactionCandidate`），仅 2 个 vNext 测试。迁移到 vNext 需要重写断言，不是简单搜索替换。Plan 已包含此文件，但未估计迁移规模。分类为 implementation agent 需注意的工作量信号，不阻塞 plan。

### O2：`issues-implementation-control.md` 状态历史

WU-CM-01 条目（line 383）的状态历史未显式提及 compact contract closure plan review / fix / re-review gate 的完成。当前状态条目（line 144: `compact-contract-closure-plan-fix-complete`）、next entry point（line 147: `re-review gate`）和 artifact 记录（line 158-159）均已正确更新。状态历史是叙述性文本，不影响 gate 流程，但可能影响将来追溯。分类为文档清晰性改进。

### O3：compact contract closure 与 Slice C 的测试命令分离

Pre-Slice C 的测试命令（plan line 282）和 Slice C 的测试命令（plan line 400-406）是分离的。这在 slice 内是正确的最小化，但没有一个统一命令能同时覆盖 Pre-Slice C + Slice C 的测试。最终验证命令（plan line 587-596）已包含全量测试。Implementation agent 在 Pre-Slice C 完成后进入 Slice C 前，应参考最终验证命令做一次全量回归。

---

## 总结

| 类别 | 数量 | 关键项 |
|---|---|---|
| accepted findings 处理 | 6/6 | DS B1, DS B2, DS B3, MiMo 1, MiMo 2, DS N1/N2/N4/residual 全部完整处理 |
| blocking findings | 0 | — |
| non-blocking observations | 3 | O1: 迁移规模信号; O2: 状态历史清晰性; O3: 测试命令分离信号 |

**结论：pass。**

AgentCodex 的 plan fix 完整处理了 Controller 的全部 6 组 accepted findings。Pre-Slice C 的 allowed files、实现边界、禁止项、测试命令、退出信号和 residual risks 均已补齐，无 owner 缺口、无跨层越界、无兼容 wrapper 风险、无过大 scope、无与 design.md 的冲突。Pre-Slice C 可以进入 implementation gate。
