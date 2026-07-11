# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `8515364a`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-k-s1-code-review-mimo.md`
- Included scope:
  - `tests/host/test_memory_projection.py`
  - `tests/contracts/test_tool_result_envelope.py`
  - `tests/host/test_run_input_builder.py`
  - `docs/reviews/wu-semantic-ownership-01-p3-k-s1-implementation-codex.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-k-s1-controller-validation.md`
- Excluded scope: AGENTS.md, CLAUDE.md, docs/cli_ci*, docs/reviews/code-review-20260710-*.md
- Parallel review coverage: 无

## Findings

未发现实质性问题。

逐项审查结论：

### 1. Memory 投影断言：exact field-set lock → owner-level subset + 行为断言

旧代码用 `tuple(field.name for field in fields(...)) == _POLICY_FIELDS` 做精确有序元组比较，测试充当完整字段 registry。新代码改为 `frozenset` + subset containment（`<=`），同时新增了 owner helper 行为断言：

- `default_memory_projection_policy()` 构造 → `memory_projection_policy_to_json_value()` JSON 投影 → required fields 在 JSON 中存在。
- `digest_memory_projection_policy()` 对 policy 变更的敏感性（window_size 变化、policy_ref 变化 → digest 不同）。
- `build_empty_conversation_memory_snapshot()` 构造 → 语义区段字段值断言 → `calculate_memory_snapshot_digest()` 一致性 → `conversation_memory_snapshot_to_json_value()` / `conversation_memory_snapshot_from_json_value()` JSON round-trip。

这些断言比旧的纯字段名比较更强：它们验证了 owner helper 的消费路径、digest 计算正确性、JSON durable round-trip 完整性。如果生产 owner 移除某个必需字段，subset 断言会失败；如果 digest 算法或 JSON 序列化回归，round-trip 断言会失败。

### 2. Tool result envelope：complete field-set equality → required fields + forbidden awaiting

旧代码用 `success_fields == {"ok", "value", "meta"}` 做精确集合相等。新代码改为 `required_success_fields <= success_fields` 和 `required_failure_fields <= failure_fields`，同时保留 `success_fields.isdisjoint(forbidden)` 和 `failure_fields.isdisjoint(forbidden)`。

公共判别值（`ok is True/False`）和禁止 `await_spec/await/awaiting` 的守卫不变。测试不再承诺完整闭合字段集合，但仍然阻止必需字段消失和 awaiting 字段回归。

### 3. Resume guidance helper：散落 prose 断言 → 集中语义 helper

旧代码在 3 个测试函数中各写 5-11 行 `assert "..." in message.content`。新代码抽出 `_assert_resume_guidance_semantics(...)` 文件私有 helper，区分两类断言：

- **production-owned 固定语义行**（`_RESUME_GUIDANCE_COMPLETED_INTRO`、`_RESUME_GUIDANCE_NO_REPEAT`）：用 `in lines` 做精确行匹配，不是 vague keyword substring。
- **动态投影事实**（tool_name、status、result_text）：用 f-string 精确匹配对应行。
- **内部泄漏负面断言**（`_RESUME_GUIDANCE_FORBIDDEN_INTERNAL_FRAGMENTS`）：保留全部 11 个 forbidden fragment。

helper docstring 明确声明了 ownership 关系和更新责任。3 个调用点参数一致（`fake_tool` / `completed` / `{"answer": 42}`），行为等价于旧代码但更集中、更可维护。

### 4. 范围边界

- 只修改了 S1 允许的 3 个测试文件。
- 未触及生产代码、S2 raw SQL helper、S3 cancellation/compaction fake、README。
- `_POLICY_FIELDS` / `_SNAPSHOT_FIELDS` 旧名已不存在，被语义更清晰的 `_REQUIRED_MEMORY_POLICY_FIELD_NAMES` / `_REQUIRED_MEMORY_SNAPSHOT_FIELD_NAMES`（`frozenset`）替代。
- 新增了 `memory_projection_policy_to_json_value` 导入用于 owner helper 行为断言，该符号已在 `dayu.host.memory` 中存在。

### 5. 测试与类型验证

- `pytest` 166 passed in 1.20s。
- `pyright` 0 errors, 0 warnings, 0 informations。
- `git diff --check` 无 whitespace 问题。
- Controller validation source scan 确认旧 tuple lock 模式和 vague keyword 模式均无残留。

## Open Questions

无。

## Residual Risk

- `_REQUIRED_MEMORY_POLICY_FIELD_NAMES` 包含 20 个字段名、`_REQUIRED_MEMORY_SNAPSHOT_FIELD_NAMES` 包含 13 个字段名。这些常量仍然显式列举字段，如果生产 owner 有意移除某个字段，测试会作为 coupling point 阻止变更。这是 intended behavior（测试保护 owner 承诺的必需字段），但如果 owner 的字段演进频繁，这些常量需要同步更新。
- Resume guidance 的固定语义行（`_RESUME_GUIDANCE_COMPLETED_INTRO`、`_RESUME_GUIDANCE_NO_REPEAT`）目前是测试中的精确中文文本镜像，不是从 production owner 导入的常量。implementation artifact 已记录这一现状，S1 范围内可接受。
