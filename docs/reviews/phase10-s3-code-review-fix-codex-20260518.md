# Phase 10 Slice 3 Code Review Fix — Codex

## Accepted Findings

- AgentDS M1：`validate_context_compacted_payload` 未校验 `episode_summary_candidate.proposed_verified_fact_refs` 为空。已接受并修复。
- AgentDS residual risk：replace patch value 的非法结构只会在 memory projection 阶段失败，validator 未提前拒绝。已作为同类防御深度补强一并修复。

## Fixes

- `dayu.host.context_events.validate_context_compacted_payload`：
  - 新增 `proposed_verified_fact_refs` optional text list 校验；非空时 fail closed，避免 accepted compact summary 在 payload 层携带“新建 verified fact”提议。
  - `_validate_patch_evidence` 在 `replace` 操作下调用 `_validate_replace_patch_value`，提前校验 `current_goal` 为非空文本、tuple 字段为文本数组、`confirmed_subjects` 为 Host-neutral opaque refs。
- `tests/host/test_context_compact_events.py`：
  - 新增 `test_compacted_payload_rejects_summary_proposed_verified_fact_refs`。
  - 新增 `test_compacted_payload_rejects_replace_patch_without_value`。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_context_compact_events.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q`
  - `79 passed`
- `source .venv/bin/activate && pyright`
  - `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - passed

## Residual

- Low severity maintainability notes remain: context event validator keeps an explicit Host-neutral ref kind set, while memory projection uses `HostNeutralRefKind`; current values are aligned. Avoided changing enum ownership in Slice 3 to keep dependency direction clean and avoid importing memory from context event helpers.
