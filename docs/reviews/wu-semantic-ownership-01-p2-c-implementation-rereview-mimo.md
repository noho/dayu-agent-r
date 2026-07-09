# WU-SEMANTIC-OWNERSHIP-01 P2-C implementation re-review - AgentMiMo

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-C`
- Gate: implementation fix re-review
- Accepted finding: `P2C-IMPL-F01`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p2-c-implementation-fix-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p2-c-implementation-controller-validation.md`

## Re-review Checklist

### 1. P2C-IMPL-F01 是否已关闭

**验证结果：已关闭。**

`tests/engine/test_agent_phase3_tool_call.py::test_agent_policy_rejects_invalid_values` 中：

- `continuation_prompt` 空白值覆盖（第 866-875 行）：循环 `("", "   ", "\n\t")`。
- `fallback_prompt` 空白值覆盖（第 898-907 行）：循环 `("", "   ", "\n\t")`。

两组值完全一致，覆盖对称。原始 finding 报告的单值 `continuation_prompt=" "` 已被替换为完整三值循环。

### 2. Fix 是否只落在测试 owner boundary

**验证结果：是。**

`git diff tests/engine/test_agent_phase3_tool_call.py` 确认变更仅涉及：

- 新增模块常量 `_TEST_FALLBACK_PROMPT` / `_TEST_CONTINUATION_PROMPT`（第 93-95 行）。
- 重命名 `test_contract_fields_are_explicit` → `test_agent_policy_accepts_explicit_prompt_fields`，断言从 `assert policy.fallback_prompt` 改为显式值比较。
- 新增 `test_agent_policy_prompt_fields_are_required` 测试。
- `test_agent_policy_rejects_invalid_values` 中：单值 `continuation_prompt=" "` 替换为三值循环；所有 `AgentPolicy(...)` 负例补齐显式 `fallback_prompt` / `continuation_prompt` 参数。

Production code 变更（`dayu/engine/contracts/agent_policy.py`、`dayu/runtime/assembly.py`、`dayu/service/host_assembly.py`、`dayu/engine/README.md`）属于 P2-C implementation 主体，不属于本次 fix gate。

### 3. 是否引入新问题

**验证结果：未引入。**

- **测试异味**：模块常量 `_TEST_FALLBACK_PROMPT` / `_TEST_CONTINUATION_PROMPT` 是 test-scoped fixture 级常量，不跨测试文件共享，不构成跨测试默认真源。
- **LLM-facing 默认迁回 Engine**：`AgentPolicy` 仍为 required fields，无 default value。测试常量仅用于构造合法 policy 实例。
- **runtime 旧名回归**：测试使用当前 `AgentPolicy` 签名，无旧字段名或旧默认值引用。

### 4. Controller 验证结果复核

**独立验证通过：**

| 检查项 | Controller 报告 | 独立复核 |
|--------|----------------|----------|
| `pytest tests/engine/test_agent_phase3_tool_call.py` | 45 passed | 45 passed in 0.20s ✓ |
| `pyright` | 0 errors | 0 errors, 0 warnings, 0 informations ✓ |
| `git diff --check` | pass | 无输出 ✓ |

## Conclusion

**pass**

P2C-IMPL-F01 已关闭：`continuation_prompt` 与 `fallback_prompt` 的空白值覆盖现在对称，均使用 `("", "   ", "\n\t")` 三值循环。Fix 仅落在测试 owner boundary，未触及 production code。未引入新的测试异味、跨测试默认真源、LLM-facing 默认迁回 Engine 或 runtime 旧名回归。
