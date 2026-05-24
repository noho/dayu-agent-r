# Code Review

**结论: BLOCKED**

Slice 1 的实现质量本身是好的：material pack typed contract 清晰，旧字段完整删除，LLM-facing / internal provenance 分离正确，prompt-local label helper 集中在 `compact_material.py`，tests 全部通过 (260 passed)，pyright 0 errors。但存在两个高严重度的 slice boundary 违反：(1) `run_input.py` 和 `memory.py` 被修改但 plan 明确归属 Slice 6；(2) 18 个 plan 未授权的测试文件被修改，其中 `test_public_compact_smoke.py` 的 +106 行 ConfigLoader/ScenePrepare 集成变更属于 Slice 7 范围。需要 Controller 裁决：要么接受提前合并并更新 plan boundary，要么要求剥离超范围变更。

## Scope

- Mode: current changes
- Branch: feat/phase-12-5-conversation-memory-optimize
- Base: main
- Output file: docs/reviews/p12-6-slice1-code-review-mimo-20260524.md
- Included scope: Phase 12.6 Slice 1 workspace diff — Material Pack contract deletion boundary and direct consumers migration
- Excluded scope: Engine, Fins, Service, UI, Host public API, files outside plan §7/§8.0 allowed list
- Parallel review coverage: 无

## Findings

### 1-未修复-高-Slice 1 修改了 plan 明确归属 Slice 6 的生产文件

- **入口/函数**: Slice 1 plan §8.0 允许修改文件清单
- **文件(行号)**: `dayu/host/run_input.py` (+91/-19), `dayu/host/memory.py` (大量修改)
- **输入场景**: 任何遵循 plan slice boundary 的实现或 review
- **实际分支**: `run_input.py` 被修改: `VerifiedFactView` -> `EvidenceBackedFactView`, `tool_fact_refs` -> `accepted_evidence_refs`/`evidence_backed_fact_refs`, 新增 `_memory_minimum_preserve_message` 渲染, `_preserved_tool_fact_refs_text` -> `_preserved_fact_refs_text`。`memory.py` 被修改: 新增 `EvidenceBackedFactCandidate`/`MinimumPreserveItemCandidate` import, `VerifiedFactView` -> `EvidenceBackedFactView`, projection 逻辑变更
- **预期行为**: plan §8.0 Slice 1 允许文件列表不包含 `dayu/host/run_input.py` 和 `dayu/host/memory.py`；这两个文件明确归属 Slice 6 (Memory Projection Consolidation / RunInputBuilder Rendering)
- **实际行为**: 实现者在 Slice 1 中一并修改了这两个文件，跨越了 plan 明确规定的 slice boundary
- **直接证据**: `git diff main --stat` 显示 `dayu/host/run_input.py` +91/-19, `dayu/host/memory.py` 大量修改；plan §8.0 Slice 1 允许文件列表无这两个文件
- **影响**: 违反 slice boundary 约定；Slice 1 和 Slice 6 的变更混在一起，后续 Slice 6 的 review 无法独立验证这些变更是否正确
- **建议改法和验证点**: 将 `run_input.py` 和 `memory.py` 的变更从 Slice 1 commit 中剥离，保留到 Slice 6 实施时一并提交；或由 Controller 显式裁决提前合并的合理性
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 高

### 2-未修复-高-18 个 plan 未授权的测试文件被修改

- **入口/函数**: Slice 1 plan §8.0 允许修改测试文件清单
- **文件(行号)**: `tests/host/test_context_policy.py` (+7), `tests/host/test_local_proxy_engine_ingest.py` (+6), `tests/host/test_logging.py` (+4), `tests/host/test_open_host_runtime.py` (+10), `tests/host/test_phase5_local_execution_integration.py` (+4), `tests/host/test_phase6_toolruntime_integration.py` (+6), `tests/host/test_phase7_waiting_integration.py` (+4), `tests/host/test_public_compact_smoke.py` (+106), `tests/host/test_public_contracts.py` (+2), `tests/host/test_public_open_host_options.py` (+11), `tests/host/test_public_tool_wiring_smoke.py` (+11), `tests/host/test_recovery_dispatch.py` (+4), `tests/host/test_resolve_wait_command.py` (+26), `tests/host/test_toolruntime_accept_barrier.py` (+86), `tests/host/test_toolruntime_diagnostics.py` (+4), `tests/host/test_toolruntime_duplicate_governance.py` (+4), `tests/host/test_toolruntime_executor.py` (+20), `tests/host/test_toolruntime_truncation_fetch_more.py` (+4)
- **输入场景**: 实现 `ContextCompactor` 协议签名变更 (新增 `cancellation_token` 参数) 后，所有使用 `FakeContextCompactor` 的测试需要同步更新
- **实际分支**: `ContextCompactor` 协议新增 `cancellation_token` 参数，导致 18 个不在 Slice 1 允许列表中的测试文件需要修改
- **预期行为**: plan §8.0 Slice 1 允许的测试文件列表明确列出 10 个文件；超出列表的修改应停下报告 Controller
- **实际行为**: 实现者修改了 28 个测试文件 (10 个允许 + 18 个未授权)，未报告 Controller
- **直接证据**: `git diff main --stat -- tests/host/` 显示 29 个文件修改，plan §8.0 只允许 10 个
- **影响**: slice boundary 约定被破坏；部分修改 (如 `test_public_compact_smoke.py` +106 行) 本身属于 Slice 7 范围
- **建议改法和验证点**: (1) 将 `ContextCompactor` 协议签名变更与 Slice 1 合并是合理的，但应由 Controller 裁决；(2) `test_public_compact_smoke.py` 的 ConfigLoader/ScenePrepare 集成变更应剥离到 Slice 7
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 高

### 3-未修复-低-测试 docstring 残留旧字段名

- **入口/函数**: `test_compaction_request_evidence_inputs_deduplicate_accepted_evidence_ids`
- **文件(行号)**: `tests/host/test_compaction_operation.py:708`
- **输入场景**: 阅读测试代码
- **实际分支**: docstring 写 `accepted_evidence_envelopes 按 evidence_id 去重并保留首个`
- **预期行为**: Slice 1 已删除 `accepted_evidence_envelopes` 作为 request 字段；docstring 应使用当前语义描述
- **实际行为**: docstring 仍使用旧字段名 `accepted_evidence_envelopes`
- **直接证据**: `rg -n "accepted_evidence_envelopes" tests/host/test_compaction_operation.py:708`
- **影响**: 仅 docstring 误导，不影响正确性；测试函数体已迁移为新语义
- **建议改法和验证点**: 将 docstring 改为当前语义描述，如 `evidence material 按 accepted_evidence_id 去重并保留首个`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- `run_input.py` 和 `memory.py` 的提前修改是否由 Controller 显式授权？若是，应更新 plan 或在 completion report 中说明裁决依据；若否，需按 slice boundary 剥离
- `ContextCompactor` 协议签名变更 (新增 `cancellation_token` 参数) 是否可作为 Slice 1 的 implicit dependency 合并？该变更导致 18 个额外测试文件需要同步修改

## Residual Risk

- Slice 1 初始 material pack construction 是 intentionally initial 的；完整 deterministic segment selection、already-represented 判断和 snapshot cursor repair 仍在 Slice 2
- Evidence material collector 仍依赖当前 accepted evidence envelope 做 canonical mapping；raw evidence path hardening 在 Slice 3
- dispatch.py 和 engine_ingest.py 的 proactive/reactive request 仍使用 `start_event_sequence=1` 读取 Session 起点 EventLog range；这是 Slice 2 的修复范围，不是 Slice 1 的 finding
- `context_events.py` 保留旧字段名常量 (`_FIELD_OLD_TOOL_FACT_REFS` 等) 和旧字段拒绝逻辑，用于 payload 兼容性校验 — 这是正确做法，确保旧 payload 写入的事件仍能被校验拒绝
