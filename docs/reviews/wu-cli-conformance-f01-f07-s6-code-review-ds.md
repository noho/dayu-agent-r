# Code Review — S6/F06 typed trigger 无 alias 重命名

## Scope

- **Mode**: current changes (uncommitted)
- **Branch**: `codex/interactive-oracle`
- **Base**: `64c581f1`
- **Review target**: PR 190 S6/F06 — `context_compaction_completed` → `context_governance_resolved` fresh rename
- **Output file**: `docs/reviews/wu-cli-conformance-f01-f07-s6-code-review-ds.md`
- **Included scope**:
  - `dayu/host/run_input.py` — producer symbol 定义与两处 dispatch 生产点
  - `dayu/host/_runner_call_manifest.py` — strict closed allowlist 与 hot/manifest 双路径校验
  - `tests/host/test_engine_ingest_mapping.py` — success/fallback roundtrip、generic ingest link、strict rejection
  - `tests/host/test_run_input_builder.py` — producer 路径 hot/manifest 断言
  - `tests/host/test_tool_trace_projection.py` — public trace 透传与 outcome 不反推
  - `docs/host/design.md` — active trigger 表语义更新
- **Excluded scope**: Engine 生产代码（generic reader 无旧值分支，未修改）、frozen registry、归档 evidence、README
- **Parallel review coverage**: 无（单 reviewer 全链路走读）
- **Reference documents**:
  - `AGENTS.md`
  - Accepted plan: `docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md` §8
  - Plan-fix: `docs/reviews/wu-cli-conformance-f01-f07-plan-fix-codex.md` §3.3
  - Frozen F06: `F06-context-governance-trigger-name`
  - Implementation artifact: `docs/reviews/wu-cli-conformance-f01-f07-s6-implementation-codex.md`
  - Host design: `docs/host/design.md`

## Verification Results (pre-collected)

| Check | Result |
|---|---|
| Focused pytest (`test_engine_ingest_mapping.py` + `test_run_input_builder.py` + `test_tool_trace_projection.py`) | **275 passed** |
| Pyright (changed files) | **0 errors, 0 warnings, 0 informations** |
| Pyright (full `dayu/ tests/ utils/`) | **0 errors, 0 warnings, 0 informations** |
| Coverage `dayu/host/run_input.py` | **84%** (≥80% ✅) |
| Coverage `dayu/host/_runner_call_manifest.py` | **88%** (≥80% ✅) |
| `git diff --check` | **PASS** |
| Old symbol/literal scan (`context_compaction_completed` / `CONTEXT_COMPACTION_COMPLETED` / `_RUNNER_CALL_TRIGGER_CONTEXT_COMPACTION_COMPLETED`) in `dayu/host tests/host docs/host/design.md` | **0 hits** |
| New symbol/literal scan (`context_governance_resolved` / `CONTEXT_GOVERNANCE_RESOLVED`) in `dayu/host tests/host docs/host/design.md` | **18 hits** across 2 producer sites + strict allowlist + 5 test sites + design |
| Frozen registry SHA-256 (`docs/cli_ci_oracles.json` / `docs/cli_ci_scenarios.json`) | unchanged from plan baseline |
| Alias/re-export scan | **0 hits** |
| Staged files | **0** (未 stage) |

## Contract 闭合验证

### Producer → strict manifest persistence/read → generic ingest → public trace

```
producer:
  _prepared_candidate_kind_and_trigger (run_input.py:6672-6674)
    → POST_COMPACTION_DISPATCH + CONTEXT_GOVERNANCE_RESOLVED
    (covers: accepted compact via compact_artifact_refs, failed fallback via context_fallback_decision_ref)

  _runner_call_kind_and_trigger (run_input.py:7977-7979)
    → POST_COMPACTION_DISPATCH + CONTEXT_GOVERNANCE_RESOLVED
    (covers: RECOVERY start_reason, fallback is not None)

persistence + strict reader:
  _RUNNER_CALL_TRIGGER_REASONS (_runner_call_manifest.py:147-162)
    → frozenset 含 "context_governance_resolved"，不含旧 literal

  parse_runner_call_hot_payload (line 657)
    → _required_text (line 688) 只要求非空文本
    → _validate_hot_atoms (line 721) 调用 _require_closed_text (line 1711)
      校验 runner_call_trigger_reason ∈ _RUNNER_CALL_TRIGGER_REASONS

  parse_runner_call_manifest (line 914)
    → _parse_manifest_identity (line 1047-1054)
      同时做 _required_text + _require_closed_text 双重校验

  runner_call_hot_payload (line 600)
    → 先 _validate_hot_atoms (line 613) 再 parse_runner_call_manifest (line 614)
      确保所有 direct RunnerCallHotAtoms 构造路径均经 allowlist 校验

generic ingest (engine_ingest.py):
  → 只透传 manifest_payload.runner_call_trigger_reason (line 8096-8097)
  → 无旧值分支、无 outcome 推导

public trace (tool_trace.py / durable/tool_trace.py):
  → 只透传 hot_payload.runner_call_trigger_reason (line 724 / line 1009)
  → 不生成 context_compaction_outcome / compact_artifact_ref / fallback_action
```

**闭合结论**: 从 producer 到 public trace 形成完整、无断裂的 rename 链路。✅

### Success accepted compact 与 failed fallback 都只用 `context_governance_resolved`

- **success path** (`test_context_compaction_requested_none_budget_uses_host_estimator_and_dispatches_recovery`):
  `test_engine_ingest_mapping.py:1416` — hot payload trigger = `context_governance_resolved`
  `test_engine_ingest_mapping.py:1429-1431` — durable manifest identity trigger = `context_governance_resolved`
  同时保留 `CONTEXT_COMPACTED` payload 断言不变（terminal outcome ownership）。

- **fallback path** (`test_reactive_compactor_missing_fallback_dispatches_recovery_attempt`):
  `test_engine_ingest_mapping.py:2793` — hot payload trigger = `context_governance_resolved`
  `test_engine_ingest_mapping.py:2794-2795` — durable manifest identity trigger = `context_governance_resolved`
  同时保留 `CONTEXT_COMPACTION_FAILED` payload 断言不变。

**结论**: 两条路径统一使用新 trigger，且各自保持正确的 terminal outcome owner。✅

### 旧 symbol/literal 无 active 残留且旧/unknown 输入 strict 拒绝

- 全量 active code scan: `context_compaction_completed` / `CONTEXT_COMPACTION_COMPLETED` / `_RUNNER_CALL_TRIGGER_CONTEXT_COMPACTION_COMPLETED` 在 `dayu/host tests/host docs/host/design.md` 中 **0 hits**。
- `test_runner_call_manifest_rejects_stale_and_unknown_governance_trigger` (`test_engine_ingest_mapping.py:6129-6194`):
  - 先构造 `context_governance_resolved` manifest 并通过 hot + durable 双路径 roundtrip 断言
  - 对 `"context_compaction_" + "completed"`（旧值，字符串拼接避免 scan 误命中）: `parse_runner_call_hot_payload` → `HostDurableError`，`parse_runner_call_manifest` → `HostDurableError`
  - 对 `"unknown_context_governance_trigger"`（未知值）: 同上 fail closed
- 无 normalization（`_required_text` 返回原始字符串，`_require_closed_text` 做精确 `value not in allowed_values` 匹配）、无 alias、无 fallback reader。

**结论**: 旧值与未知值均 strict fail closed。✅

### 无 alias/re-export/normalize/migration

- 旧 `_RUNNER_CALL_TRIGGER_CONTEXT_COMPACTION_COMPLETED` 已删除，不保留 alias 或 re-export。
- 新 `_RUNNER_CALL_TRIGGER_CONTEXT_GOVERNANCE_RESOLVED` 只在 `run_input.py:338` 定义并由同一模块内两处 producer 消费，不跨模块导出。
- `_runner_call_manifest.py:157` 的 allowlist 直接使用字面量 `"context_governance_resolved"`，不从 `run_input.py` import（contract owner 独立定义 closed set）。
- 无 import alias、无兼容性常量 re-export、无迁移路径。

**结论**: 符合 fresh contract rename 无兼容残留要求。✅

### Trigger 不冒充 CONTEXT_COMPACTED/FAILED，artifact/fallback refs 精确 outcome owner

- Trigger = `context_governance_resolved`，语义为 "governance 已收口并允许下一次 dispatch"。
- Terminal outcome = `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED`，各自携带 artifact refs / fallback refs。
- 两个 namespace 互不重叠:
  - `context_governance_resolved` ≠ `CONTEXT_COMPACTED`
  - `context_governance_resolved` ≠ `CONTEXT_COMPACTION_FAILED`
- Tool trace 测试 (`test_tool_trace_projects_runner_call_manifest_signal`): 透传 trigger 值，同时 assert `context_compaction_outcome` / `compact_artifact_ref` / `fallback_action` **不存在**于 trace summary。
- Success/fallback 测试的原有 `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` 断言全部保留且不变。

**结论**: Trigger 没有夺取 terminal outcome 或 artifact/fallback refs 的所有权。✅

### 测试证明 roundtrip/hot link/trace 透传而非从 trigger 反推结果

- **Roundtrip** (`test_engine_ingest_mapping.py:1412-1431` 与 `2779-2795`):
  从真实 EventLog hot payload → `parse_runner_call_hot_payload` → 读 durable manifest payload → `parse_runner_call_manifest`，两条路径均 assert `runner_call_trigger_reason == "context_governance_resolved"`。

- **Hot link** (`_validate_manifest_hot_identity`, `_runner_call_manifest.py:1612-1685`):
  `identity.runner_call_trigger_reason`（来自 durable manifest）与 `hot_payload.runner_call_trigger_reason` 逐字段比对，任一分裂即 `HostDurableError("runner-call hot/manifest identity mismatch")`。测试通过 valid trigger 间接覆盖此路径。

- **Trace 透传** (`test_tool_trace_projects_runner_call_manifest_signal`):
  `row.trace_summary["runner_call_kind"] == "post_compaction_dispatch"`、`row.trace_summary["runner_call_trigger_reason"] == "context_governance_resolved"` 证明透传新值；`"context_compaction_outcome" not in row.trace_summary` 等三条负断言证明不从 trigger 反推 outcome。

- **不从 trigger 反推**: 无一测试从 `runner_call_trigger_reason == "context_governance_resolved"` 推断 compact success/failure；outcome 始终从 `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` event payload 断言。

**结论**: 测试设计符合 "证明行为而非从 trigger 反推" 的约束。✅

### 设计语义一致

`docs/host/design.md:3166`:
> `context_governance_resolved` | context governance 已收口并允许下一次 dispatch；精确 success / failure outcome 仍只由 `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` 及其 artifact / fallback refs 拥有

与代码实现语义完全一致。旧 literal 在设计文档中 0 hits。

**结论**: 设计、代码、测试三方语义一致。✅

## Findings

经过全链路逐行走读、adversarial failure pass、semantic ownership drift pass、contract boundary check、分支可达性分析、strict reader matrix 验证、所有直接构造 `RunnerCallHotAtoms` 的 bypass 路径审查、以及测试覆盖与断言方向验证：

**未发现实质性问题。**

S6/F06 实现是一个干净、完整、无副作用的 fresh contract rename：

- 旧 symbol/literal 从 active code 完全移除（0 hits）
- 新 symbol/literal 在 producer（2 处）、persistence allowlist（1 处）、generic ingest（透传）、public trace（透传）、owner tests（5 处 site × roundtrip + strict rejection + trace 透传）和 design（1 处）中一致使用
- 所有 `RunnerCallHotAtoms` 直接构造路径（`run_input.py:7447`、`engine_ingest.py:7443`、`compaction_operation.py:1538`）均经过 `runner_call_hot_payload()` → `_validate_hot_atoms()` → `_require_closed_text()` 的 allowlist 校验，无 bypass
- `parse_runner_call_hot_payload` 和 `parse_runner_call_manifest` 双路径均对旧/unknown 值 fail closed
- 无 alias、re-export、normalize、migration 或兼容路径
- 成功 compact 与失败 fallback 均使用同一 trigger，但各自通过 canonical `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` event 保留精确 outcome ownership
- 测试断言方向正确：从真实数据路径出发验证 roundtrip，而非从 trigger 值反推 outcome
- Pyright 0 errors、tests 275 passed、coverage 84%/88%、`git diff --check` clean

### 审查覆盖的 adversarial surface（均无发现）

| Attack surface | 审查结论 |
|---|---|
| 直接 `RunnerCallHotAtoms(...)` 构造绕过 allowlist | 三处构造均经 `runner_call_hot_payload()` → `_validate_hot_atoms()` 校验 |
| hot/manifest 身份分裂 | `_validate_manifest_hot_identity` 逐字段比对，trigger 在比对列表中 |
| Engine ingest / Tool Trace 从 trigger 推导 outcome | 代码均为纯透传，测试负断言确认不生成 outcome 字段 |
| 旧值被 loose parser 接受 | `_require_closed_text` 严格 `not in` 检查，无 normalization |
| 分支重叠导致错误 trigger 被分派 | 两处 producer 的条件互斥且完备；CONTINUATION > governance > initial 优先级正确 |
| Schema/contract 版本漂移 | `manifest_schema_version` 独立校验，trigger rename 不改变 schema version |
| 测试固化偶然行为 | 所有新增断言均为 typed contract 行为，非历史偶然 |
| 设计-代码不一致 | 设计表已同步，语义注释明确区分 trigger 与 outcome |

## Open Questions

无。

## Residual Risk

| 风险 | 评估 |
|---|---|
| 未来新增 producer 可能用 `context_governance_resolved` 搭配错误 kind | **LOW** — strict allowlist 不校验 kind × trigger 叉积，但 producer 是唯一入口且数量有限 |
| 旧 durable DB 中存在序列化的 `context_compaction_completed` 值 | **无风险** — S6 按 fresh schema 起库，不承诺旧 DB 可打开；strict reader fail closed 是预期行为 |
| S7 实施时需同步 `context_governance_resolved` 引用 | **LOW** — S7 计划已明确依赖 S6 新 trigger，且 S7 在同一分支上原子闭合 |
| Frozen real-provider CLI evidence 刷新 | **已委派 S8** — 不在 S6 scope |

## Verdict

**PASS** — S6/F06 implementation is complete, correct, and ready for the next gate. No defects found. All contract invariants verified. No blocking issues.
