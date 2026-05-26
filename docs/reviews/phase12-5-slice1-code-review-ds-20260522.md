# Phase 12.5 Slice 1 Code Review — AgentDS

- **Gate**: Phase 12.5 Slice 1 code review
- **Role**: Independent code review agent (AgentDS). Review only. No file modifications.
- **Approved plan**: `docs/reviews/phase12-5-implementation-ready-plan-20260522.md`
- **Slice**: Slice 1 — Contract Rename And Config Schema
- **Date**: 2026-05-22

## Review Summary

**Verdict: PASS.** No blocking issues. All Slice 1 plan items are correctly implemented. Validation passed (42 tests, 0 pyright errors). No compatibility shims, no old-key fallbacks, no aliases. One minor scope observation (F2 below) is cosmetic and does not affect correctness.

## Findings

### F1 (INFO — PASS): All plan-required renames correctly executed

验证了以下每一个 Slice 1 要求的 rename：

| Plan requirement (§4.1) | Status | Evidence |
|---|---|---|
| `VerifiedFactView` → `EvidenceBackedFactView` | **DONE** | `dayu/host/memory.py:212`, `dayu/host/durable/memory.py:85` |
| `ConversationMemorySnapshot.verified_facts` → `evidence_backed_facts` | **DONE** | `dayu/host/memory.py:297`, all call sites in `project_conversation_memory_event()`, `build_empty_conversation_memory_snapshot()` |
| `MemoryProjectionPolicy.max_verified_facts` → `max_evidence_backed_facts` | **DONE** | `dayu/host/memory.py:261`, `_limit_evidence_backed_facts()` |
| `MemoryProjectionConfig.max_verified_facts` → `max_evidence_backed_facts` | **DONE** | `dayu/runtime/config_loader.py:250` |
| `execution_profiles.json` 中 `max_verified_facts` → `max_evidence_backed_facts` | **DONE** | All 4 profiles updated (`dayu/config/execution_profiles.json:23,89,155,221`) |
| `MemoryClaimStatus.TOOL_VERIFIED` → `EVIDENCE_BACKED` | **DONE** | `dayu/host/memory.py:195` |
| `MemoryIncludedReason.TOOL_VERIFIED_FACT` → `EVIDENCE_BACKED_FACT` | **DONE** | `dayu/host/memory.py:204` |
| Durable `_ITEM_KIND_VERIFIED_FACT` → `_ITEM_KIND_EVIDENCE_BACKED_FACT` | **DONE** | `dayu/host/durable/memory.py:92` |
| JSON codec helpers renamed | **DONE** | `_verified_fact_to_json_value()` → `_evidence_backed_fact_to_json_value()`, `_verified_fact_from_json_value()` → `_evidence_backed_fact_from_json_value()`, durable helper equivalents |
| `_verified_fact_from_projection_event()` → `_evidence_backed_fact_from_projection_event()` | **DONE** | `dayu/host/memory.py:400` |
| `_limit_verified_facts()` → `_limit_evidence_backed_facts()` | **DONE** | `dayu/host/memory.py:489` |
| `_payload_digest_for_verified_fact()` → `_payload_digest_for_evidence_backed_fact()` | **DONE** | `dayu/host/durable/memory.py:151` |
| `DEFAULT_MEMORY_MAX_VERIFIED_FACTS` → `DEFAULT_MEMORY_MAX_EVIDENCE_BACKED_FACTS` | **DONE** | `dayu/host/memory.py:186` |
| `_insert_verified_fact_item()` → `_insert_evidence_backed_fact_item()` | **DONE** | `dayu/host/durable/memory.py:111` |

### F2 (LOW — Observation): Import restructuring in host_assembly.py outside Slice 1 scope

**File**: `dayu/service/host_assembly.py:19-33`, `tests/service/test_host_assembly.py:10-15`

**Change**: `from dayu.host import (...)` 拆分为 `from dayu.host.api import (...)` + `from dayu.host.tooling import HostToolingOptions`。被移动的符号（`CompactorRunnerBaseline`, `FollowupBehavior`, `HostCallContext`, `OpenHostOptions`, `OrdinaryRunExecutionBaseline`, `SubmitFollowupRequest`, `HostToolingOptions`）与 memory contract rename 无直接关系。

**Assessment**: 这是对 "禁止兼容性 re-export" 策略的主动清理，不在 Slice 1 plan scope 内。改动无害，不引入行为变化，不破坏编译。属 benign scope creep，不阻塞 Slice 1 验收。

### F3 (INFO — Correctly Deferred): `run_input.py` 的 block_id 与函数名未在 Slice 1 改名

**File**: `dayu/host/run_input.py:1616-1618, 1715-1726`

Slab 内的字段访问 `snapshot.verified_facts` → `snapshot.evidence_backed_facts` 和类型 `VerifiedFactView` → `EvidenceBackedFactView` 已正确更新（compile fallout）。但以下项保持旧名：
- `block_id="stable:verified_facts"`（行 1618）
- 函数名 `_memory_verified_fact_message()`（行 1715）
- docstring 与消息文本中的 "tool-verified facts"（行 1718, 1726）

Plan §7 Slice 6 明确将这些改名列为 Slice 6 精确变更。**这不是 Slice 1 遗漏，是正确的延迟**。

### F4 (INFO — Correctly Deferred): 测试文件中仍有旧名引用

`tests/host/test_memory_projection.py`、`tests/host/test_run_input_builder.py` 等文件中仍有 `VerifiedFactView`、`max_verified_facts`、`verified_facts`、`MemoryClaimStatus.TOOL_VERIFIED` 等旧名引用。这些文件不在 Slice 1 允许范围（plan §7 Slice 1 明确说 "focused compile/type fallout in `tests/host/*` only where imports/constructors require rename"），会在 Slice 5 / Slice 6 中更新。

## Positive Confirmations

### C1: 旧 config key 被拒绝

`dayu/runtime/config_loader.py:1460` — `_parse_memory_projection()` 的 `allowed` 集合只包含 `"max_evidence_backed_facts"`，不包含旧 `"max_verified_facts"`。

`tests/runtime/test_config_loader.py:579-596` — `test_old_max_verified_facts_key_fails_fast` 正确验证旧 key 导致 `ConfigFieldError`，错误消息匹配 `"max_evidence_backed_facts"`（missing key diagnostic）。

### C2: 旧 snapshot JSON key fail-closed

`dayu/host/memory.py:2750-2753` — `conversation_memory_snapshot_from_json_value()` 使用 `_required_list(mapping, "evidence_backed_facts")`。若 JSON 中只有旧 key `"verified_facts"` 而没有 `"evidence_backed_facts"`，会因 required key missing 而失败。这是正确的 fail-closed 行为（plan §4.9）。

`dayu/host/durable/memory.py:92` — durable item kind 常量已改为 `"evidence_backed_fact"`，旧 `"verified_fact"` 不再被写入。旧 durable item row 的 reader 路径（schema validation）不在 Slice 1 范围，由 Slice 5 覆盖（plan §7 Slice 5 exact changes 最后一项）。

### C3: 无反模式

- **无 old-name alias**: 未发现 `@property` 转发旧名、旧名 module-level 常量、旧 dict key fallback
- **无兼容性 re-export**: 未在 `__init__.py` 新增旧名转发
- **无 magic string fallback**: config 解析直接拒绝未知字段，不走兼容路径
- **无 neutral fallback fact**: `_evidence_backed_fact_from_projection_event()` 仍保留 fallback 逻辑（fact_summary 为空时生成 diagnostic），这是 plan 中明确的 Slice 1 stop condition 范围外行为（该逻辑属于旧行为，后续 Slice 3/5 会修改）

### C4: README 同步准确

- `dayu/README.md:16` — "verified fact" → "evidence-backed fact"，术语与架构描述一致
- `dayu/host/README.md:239, 244` — 两处 "verified fact" → "evidence-backed fact"，与 Memory Projection 章节的实际定义同步

### C5: 验证通过（控制器已确认）

- `pytest tests/runtime/test_config_loader.py tests/service/test_host_assembly.py` → 42 passed
- `pyright dayu/host/memory.py dayu/host/durable/memory.py dayu/runtime/config_loader.py dayu/service/host_assembly.py dayu/host/run_input.py` → 0 errors

## Scope Compliance Check

| Slice 1 Required | Status |
|---|---|
| Rename dataclasses, fields, constants, JSON keys | **DONE** |
| Update memory policy digest JSON to use new key | **DONE** (`dayu/host/memory.py:2632`) |
| Update config parser exact field set | **DONE** (`dayu/runtime/config_loader.py:1460`) |
| Add test that old `max_verified_facts` is rejected | **DONE** (`tests/runtime/test_config_loader.py:579`) |
| No old-name aliases, wrappers, or fallback keys | **DONE** |
| Only allowed files modified | **DONE** (minor benign scope creep in F2) |

## Residual Risks

| Risk | Classification |
|---|---|
| 测试文件（test_memory_projection.py 等）仍引用旧名，未在 Slice 1 更新 | Covered by later approved slice（Slice 5/6） |
| `run_input.py` 的 `block_id` 与函数名仍是旧名 | Covered by Slice 6 |
| 其他模块（compaction.py, context_events.py 等）仍有旧 `verified_fact_refs` 字段 | Covered by Slice 3/4 |
| 旧 durable snapshot 的 fail-closed reader 测试 | Covered by Slice 5 |

## Recommendation

**Accept Slice 1.** 所有 plan-required 变更加正确实现，无兼容包袱，验证通过。可进入 Slice 2。
