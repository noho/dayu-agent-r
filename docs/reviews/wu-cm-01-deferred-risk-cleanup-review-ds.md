# WU-CM-01 Deferred Risk Cleanup — AgentDS Review

## Gate

- Work unit: WU-CM-01 PR deferred risk cleanup
- Review agent: AgentDS
- Scope: D1 / D2 / D4 / D5 实现审查
- Base artifacts:
  - `AGENTS.md`
  - `docs/host/design.md`  §24 Conversation Memory / §25 Context Governance
  - `docs/host/issues-implementation-control.md` residual risk 表
  - `docs/reviews/wu-cm-01-pr-deferred-risk-controller-adjudication.md`
  - `docs/host/wu-cm-01-deferred-risk-cleanup-plan.md`
  - `docs/reviews/wu-cm-01-deferred-risk-cleanup-implementation-codex.md`

## 结论

**PASS** — D1 / D2 / D4 / D5 实现满足 adjudication 全部要求。无 correctness、stability、maintainability 级别的 blocking finding。以下 findings 按严重度排序，均为非阻塞观察点。

---

## Findings

### F1 [INFO] `memory.py` `__all__` 规模大且测试白名单需持续维护

**证据**：`dayu/host/memory.py:3195-3267` — `__all__` 包含 75 个符号；`tests/host/test_package_exports.py:900-974` — `EXPECTED_MEMORY_MODULE_EXPORTS` frozenset 硬编码全部 75 个符号名。

**分析**：`memory.py` 是 Conversation Memory vNext 的 typed contract 集中模块，导出了 29 个 dataclass/Enum/Protocol 类型、16 个公共函数、22 个常量及 4 个 TypeAlias。模块级 `__all__` 白名单是 adjudication 明确要求的审计机制，但 75 条入口加硬编码 frozenset 测试意味着每次新增 public symbol 都必须同步更新两处。这不是实现错误，而是该审计机制固有的维护成本。

**建议**：接受当前设计。若后续 `memory.py` public surface 继续膨胀，可考虑按语义拆分为 `memory.contracts`（纯类型/常量）和 `memory.helpers`（构造/序列化函数），降低单模块 `__all__` 规模。不在本轮处理。

---

### F2 [INFO] `test_memory_repair.py` 测试耦合到内部模块属性名

**证据**：`tests/host/test_memory_repair.py:384`：
```python
monkeypatch.setattr(memory_repair, "ProjectionRunner", RealProjectionRunner)
```

**分析**：测试通过 `monkeypatch.setattr` 将 `memory_repair` 模块的 `ProjectionRunner` 替换为 `RealProjectionRunner`。这是 adjudication D5 要求的"真实 durable store 上的 memory projection catch-up / rebuild 测试"的最小侵入实现方式。但该写法耦合到 `memory_repair.py` 内部的 import 属性名——若 `memory_repair.py` 重构 import（例如 `from dayu.host.projection import ProjectionRunner as _ProjectionRunner`），测试会在属性名层面失败而非行为层面失败。当前 `memory_repair.py` 的 import 是 `from dayu.host.projection import ProjectionRunner`（无别名），风险低。

**建议**：接受当前实现。若后续 `memory_repair.py` 的 import 方式变更，同步更新测试即可。不在本轮处理。

---

### F3 [INFO] `tests/README.md` 包含非 D1-D5 scope 的文档修正

**证据**：`tests/README.md:127,136` — `start_run` → `_start_run` 修正及"内部 admission primitive / 低层测试路径的"新增描述。

**分析**：`test_phase5_local_execution_integration.py` 实际上使用的是 `_start_run`（内部 admission primitive）而非 `start_run`（public facade）。原 README 描述为 `start_run` 是既有不准确描述。本轮 README diff 顺带修正了该不准确描述，属于文档精度改进，不是 scope creep。但严格来说该修正确实超出了 D1-D5 的计划范围。

**建议**：无负面影响，接受。后续 README 更新应尽量在 commit message 中标注 incidental 修正。

---

### F4 [INFO] D4 `slice1` 清理彻底

**验证**：
- `dayu/host/compact_material.py` — `grep -i "slice1\|Slice 1"` 无匹配。
- 6 个 module-private 常量从 `slice1-*` / `slice1_*` 改为语义命名：`initial-compact-material-policy`、`initial_current_anchor`、`initial_trace_material`、`initial_evidence_material`、`initial_previous_compacted_view`、`initial_answer_material`。
- 8 处 docstring 中 "Slice 1" / "Slice 1 初始" 清理为语义描述。
- 测试 `test_initial_segment_selection_diagnostics_do_not_expose_slice_name` (`tests/host/test_compaction_contract.py:198-211`) 断言 `policy_digest` 与 `deterministic_reason_codes` 均不含 `"slice1"`，验证方式为 `not any(...)` 而非固定字符串断言，避免过度绑定为外部 contract。

**结论**：D4 实现完整且未扩 scope 到真实 policy digest 派生。

---

### F5 [INFO] D2 enum 化类型正确且 EventLog contract 保持稳定

**验证**：

| 检查项 | 证据 | 状态 |
|---|---|---|
| `CompactionFailureCategory` 为 `StrEnum` | `dayu/host/compaction_operation.py:44-51` | ✓ |
| `CompactionNextPolicyDecision` 为 `StrEnum` | `dayu/host/compaction_operation.py:54-58` | ✓ |
| `CompactionAttemptRejected` 字段类型收紧 | `dayu/host/compaction_operation.py:86,90` | ✓ |
| EventLog payload 边界使用 `.value` | `dispatch.py:1966-1974`、`engine_ingest.py:1938-1949` | ✓ |
| `_log_rejected_attempt` 使用 `.value` | `compaction_operation.py:500,506` | ✓ |
| `_attempt_rejected` diagnostic_refs 使用 `.value` | `compaction_operation.py:427` | ✓ |
| `context_events.py` contract 未变更 | diff 不包含 `context_events.py` | ✓ |
| `CompactionOperationResult.failure_reason` 使用 `.value` | `compaction_operation.py:163,178,188,197,206,215` | ✓ |
| 两个 enum 纳入 `__all__` | `compaction_operation.py:553-554` | ✓ |
| 测试断言 enum instance 类型 | `test_compaction_operation.py:537-544` | ✓ |
| 测试断言 payload 仍为字符串 | `test_compaction_operation.py:564-565` | ✓ |

**结论**：D2 完整满足 adjudication 要求——字段类型收紧为 `StrEnum`，EventLog payload 继续输出既有字符串值，`context_events.py` 未误改。

---

### F6 [INFO] D1 `__all__` 不改变 `dayu.host` 包根 public contract

**验证**：
- `dayu/host/__init__.py:108-201` — `__all__` 与变更前完全一致，未新增 memory / fallback 符号。
- `dayu/host/memory.py:3195-3267` — `__all__` 不含任何 `_` 前缀私有符号（`_MemoryItemWithId`、`_MIN_SEQUENCE` 等均排除）。
- `dayu/host/context_fallback.py:751-770` — `__all__` 只含 8 个 public 常量、5 个 public 类、5 个 public 函数；`_NO_EVENT_SEQUENCE`、`_FIELD_*` 等私有常量排除。
- 所有 exported dataclass 字段类型所需 enum / TypeAlias 均已纳入 `__all__`：
  - `memory.py`: `MemoryClaimStatus`, `MemoryProducerKind`, `HostNeutralRefKind`, `MemoryIncludedReason`, `MemoryExcludedReason`, `SelectedRecentWindowRole`, `MemoryEvidenceBackedFactKind`, `MemoryDiagnosticReason`, `MemoryRepairReason`, `MemorySizeUnits`, `MemorySnapshotCursor`, `MemoryPolicyDigest`, `MemoryDigestRef`, `HostEventRef`, `HostPayloadRef` 均在 `__all__` 中。
  - `context_fallback.py`: `RecentWindowFallbackAction` (`StrEnum`) 在 `__all__` 中。
- 测试 `test_memory_module_all_matches_typed_contract_boundary` 和 `test_context_fallback_module_all_matches_helper_boundary` 通过 exact frozenset 断言和 `_` 前缀排除断言。

**结论**：D1 完整满足 adjudication 要求——模块级 `__all__` 只收口稳定 typed contracts，不向上泄漏到 `dayu.host` 包根 namespace。

---

### F7 [INFO] D5 测试覆盖满足 adjudication "该有"缺口

**验证**：

| adjudication 要求 | 测试证据 | 状态 |
|---|---|---|
| 模块导出白名单 | `test_package_exports.py::test_memory_module_all_matches_typed_contract_boundary`、`test_context_fallback_module_all_matches_helper_boundary` | ✓ |
| 缺失 source label typed/schema 边界 | `test_compaction_contract.py::test_vnext_candidate_schema_rejects_missing_required_source_label` — 构造空 `source_labels=()` 的 `SessionSummaryCandidateVNext`，断言 `ValueError` | ✓ |
| 真实 durable repair integration | `test_memory_repair.py::test_catch_up_uses_real_durable_store_and_writes_snapshot` — 使用真实 `open_host_durable_store` + `RealProjectionRunner`，写入 EventLog → catch_up → 验证 snapshot / checkpoint | ✓ |
| memory catch-up 与 snapshot write 同事务 | `test_durable_concurrency_matrix.py::test_memory_snapshot_write_and_checkpoint_commit_together` — 写入 snapshot + checkpoint 后同事务内读取验证两者均可见且 cursor 一致 | ✓ |
| 初始 selection 诊断不含 `slice1` | `test_compaction_contract.py::test_initial_segment_selection_diagnostics_do_not_expose_slice_name` | ✓ |
| enum 字段类型 + payload 字符串 | `test_compaction_operation.py::test_run_compaction_operation_retries_quality_rejection` — 同时断言 `isinstance` enum 和 payload `str` 值 | ✓ |
| 不重复已有覆盖 | 未新增 large chunk / fallback path / CAS rollback 重复测试 | ✓ |
| 不伪造非法 typed object | `test_vnext_candidate_schema_rejects_missing_required_source_label` 通过合法的 typed 构造（空 tuple）触发边界，未绕过 dataclass `__post_init__` 构造非法对象 | ✓ |

**结论**：D5 实现满足 adjudication 要求。Codex review 中提到的 D5-F1（direct quality checker missing-source-label 不可达）已正确处理——改为 typed 边界测试而非私有 bypass。

---

## AGENTS.md 合规检查

| 规则 | 检查结果 |
|---|---|
| 中文 docstring | ✓ 所有新增类、函数、测试均有中文 docstring |
| 严格类型 | ✓ `StrEnum`、typed dataclass 字段、无 `Any`/`object`/无类型签名新增 |
| 禁止兼容 facade | ✓ `_FAILURE_*` 别名是 module-private 常量（`_` 前缀），不是 public facade |
| 禁止魔法字符串扩散 | ✓ 枚举化减少自由字符串；`_DIAGNOSTIC_SUFFIX_*` 是既有 module-private 常量，未新增扩散 |
| README 触发规则 | ✓ `tests/README.md` 已按触发规则同步（package exports、durable concurrency matrix 描述更新）；`dayu/host/README.md` 经检查无需更新 |
| pyright / test 验证 | ✓ Codex review 记录 `pytest` 104 tests passed，`pyright` 0 errors，`git diff --check` passed |
| 禁止扩 scope | ✓ 未修改 `dayu.host.__all__`、未扩展 policy digest 派生、未引入额外 public contract |

---

## 残余风险

1. `memory.py` `__all__` 与 `EXPECTED_MEMORY_MODULE_EXPORTS` frozenset 的手工同步维护负担——每次新增 public symbol 需同时更新两处。这是 D1 审计机制的固有成本，不属于实现缺陷。
2. `test_memory_repair.py:384` 的 `monkeypatch.setattr` 耦合到 `memory_repair.ProjectionRunner` 的 import 属性名——若上游重构 import 方式需同步更新。
3. 长期 Conversation Memory evaluation（GitHub Issue #80）仍在本轮 scope 之外。

---

## 裁决建议

- D1: **PASS** — 模块级 `__all__` 白名单完整，包根 namespace 未变更。
- D2: **PASS** — `StrEnum` 类型正确，EventLog payload 保持字符串兼容。
- D4: **PASS** — `slice1` 清理彻底，未扩 scope。
- D5: **PASS** — 补充测试覆盖 adjudication "该有"缺口，未重复已有覆盖。
