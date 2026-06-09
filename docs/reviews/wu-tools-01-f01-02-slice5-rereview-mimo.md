# WU-TOOLS-01-F01-02 Slice 5 S5-F1 Re-Review

## Metadata

- Work unit: `WU-TOOLS-01-F01-02`
- Gate: Slice 5 S5-F1 re-review (narrow fix gate)
- Reviewer: AgentMiMo
- Reviewed artifacts:
  - `docs/reviews/wu-tools-01-f01-02-slice5-closeout-review-controller-adjudication.md`
  - `docs/reviews/wu-tools-01-f01-02-slice5-fix-codex.md`
  - `tests/fins/test_fins_ingestion_tools.py` (current diff)
- Date: 2026-06-08

## Validation

### S5-F1 修复正确性

`test_ingestion_tool_schemas_hide_host_internal_fields`（第 485-519 行）在 `for definition in definitions:` 循环内，于既有 `schema_text` 全文检查之前新增了以下显式断言：

```python
properties = definition.schema.function.parameters.properties
required = definition.schema.function.parameters.required
assert "execution_context" not in properties
assert "cancellation_token" not in properties
assert "execution_context" not in required
assert "cancellation_token" not in required
```

- 4 条断言分别锁定 `parameters.properties` 和 `parameters.required` 两个 LLM-facing JSON Schema 入口。
- 覆盖 download 和 preprocess 两个 awaiting tool definition（循环遍历两者）。
- 既有的 `schema_text` 全文检查（`tool_call_id`、`digest`、`cursor`、`raw job record`、`Host`）保留不变，继续覆盖其它 Host 内部治理字段。

结论：S5-F1 已正确修复，符合 controller adjudication 要求。

### 测试验证

- `pytest tests/fins/test_fins_ingestion_tools.py::test_ingestion_tool_schemas_hide_host_internal_fields` -> PASS（1 passed）。

### Scope 检查

- `git diff --name-only` 中非 `tests/` 和 `docs/` 的文件：无。
- 未修改生产代码、未修改其它测试文件。
- S5-F2 `_is_runtime_start_call` TypeGuard 仍存在（controller 判定 rejected-with-reason），未被移除或修改，符合 adjudication 决策。

### LLM-facing schema 语义约束

新增断言直接验证 `execution_context` 和 `cancellation_token` 两个 Host 内部治理字段不暴露于 LLM-facing schema 的 `properties` 和 `required`，符合 CLAUDE.md Agent 语义约束："不得把系统状态、调度状态、Host / Engine 内部治理信息伪装成财报事实、业务事实或用户可见结论"。

### AgentCodex fix artifact 验证

`docs/reviews/wu-tools-01-f01-02-slice5-fix-codex.md` 记录了：
- Scope 仅限 `tests/fins/test_fins_ingestion_tools.py` 和 fix artifact 自身。
- Motivation 正确阐述了显式 `properties` / `required` guard 的必要性。
- Validation 包含全部 4 条要求命令，均为 PASS。
- README decision 合理：不更新 `tests/README.md`（在已有职责内补充）。
- Remaining risks 如实记录。

## Findings

| # | Severity | Finding | 决策 |
|---|---|---|---|
| F1 | info | 修复新增了 `_assert_context_token_bridge` / `_find_class` / `_find_method` / `_is_runtime_start_call` 四个 AST helper 和 `test_awaiting_tool_callables_consume_context_and_bridge_token_to_runtime` 测试，超出 controller 要求的"仅 properties/required 断言"。但这些属于 Slice 5 audit matrix 的既有实现内容（验证 callable 不丢弃 context 且桥接 token），不引入 scope 漂移。 | accepted — 属于同一 test file 内的 audit matrix 覆盖，与 S5-F1 修复同属 Slice 5 职责。 |
| F2 | info | `_is_runtime_start_call` 使用 `TypeGuard[ast.Call]`，predicate 语义比 TypeGuard 更宽（controller S5-F2 rejected-with-reason）。该函数在 re-review 期间未被修改，决策维持。 | accepted — 无变化，维持原 adjudication。 |

无 blocking finding。

## Conclusion

**PASS**

S5-F1 已被 AgentCodex 正确窄修复：`test_ingestion_tool_schemas_hide_host_internal_fields` 显式断言 `execution_context` 和 `cancellation_token` 不在 `definition.schema.function.parameters.properties` 和 `definition.schema.function.parameters.required` 中，同时保留原有 `schema_text` 全文检查。修复仅限测试文件，无生产代码漂移，符合 LLM-facing schema 语义约束。
