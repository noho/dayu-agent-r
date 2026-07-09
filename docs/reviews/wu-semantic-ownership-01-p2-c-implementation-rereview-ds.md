# WU-SEMANTIC-OWNERSHIP-01 P2-C Implementation Re-Review — AgentDS

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-C`
- Gate: implementation fix re-review
- Unique accepted finding: `P2C-IMPL-F01`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p2-c-implementation-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p2-c-implementation-fix-codex.md`

本轮只做 re-review，不修改文件，不 commit，不 push。

## Re-Review Method

- 核查 `git diff` 确认 fix 只落在 `tests/engine/test_agent_phase3_tool_call.py`。
- 源码扫描旧名残留（`AgentPolicyDefaults|code_default|_SOURCE_CODE_DEFAULT|_agent_policy_defaults_from_config`）、Engine prompt 默认残留（`_DEFAULT_FALLBACK_PROMPT|_DEFAULT_CONTINUATION_PROMPT`）。
- 扫描跨测试默认真源（`_TEST_FALLBACK_PROMPT` / `_TEST_CONTINUATION_PROMPT` 是否被其他测试模块导入）。
- 复现 controller 验证：pytest 45 passed、pyright 0、git diff --check pass。

## Re-Review Findings

### 1. P2C-IMPL-F01 关闭验证

**结论：已关闭。** 直接证据：

fix diff 中 `tests/engine/test_agent_phase3_tool_call.py` 第 91-93 行：

```python
# continuation_prompt 为空 / 纯空白必须在构造期被拒。
for invalid_continuation_prompt in ("", "   ", "\n\t"):
```

与第 896-905 行 `fallback_prompt` 循环对称：

```python
# fallback_prompt 为空 / 纯空白必须在构造期被拒。
for invalid_fallback_prompt in ("", "   ", "\n\t"):
```

两者覆盖完全相同的三种空白输入（空字符串、多空格、换行+制表符），测试对称性已补齐。

未覆盖场景检查：`AgentPolicy.__post_init__` 的校验逻辑是 `if not self.continuation_prompt.strip()`（行 84），等价于 `strip() == ""`。三种空白输入 `""`（空）、`"   "`（纯空格）、`"\n\t"`（纯 whitespace）经 `strip()` 后均为 `""`，触发同一条 `ValueError` 路径。覆盖完整、无遗漏等价类。

### 2. Fix Owner Boundary 验证

**结论：fix 只落在 Engine contract test 边界内，production code 无变化。**

直接证据：

- `git diff --stat` 显示 44 个文件变更，全部为 P2-C original implementation 变更；fix 在已有实现基础上仅修改 `tests/engine/test_agent_phase3_tool_call.py`。
- 旧名残留扫描（`AgentPolicyDefaults|code_default|_SOURCE_CODE_DEFAULT|_agent_policy_defaults_from_config`）：`dayu/`、`tests/`、`utils/` 全部零命中。无 runtime 旧名回归。
- Engine prompt 默认残留扫描（`_DEFAULT_FALLBACK_PROMPT|_DEFAULT_CONTINUATION_PROMPT`）：Engine contract 零命中；唯一命中在 `dayu/runtime/config_loader.py`（配置层真源），符合预期。无 LLM-facing 默认迁回 Engine。
- Production 文件（`dayu/engine/contracts/agent_policy.py`、`dayu/runtime/assembly.py`、`dayu/service/host_assembly.py`）未在 fix 中有任何额外变更。

### 3. 新引入问题检查

**结论：无新引入的测试异味、跨测试默认真源、LLM-facing 默认迁回 Engine、或 runtime 旧名回归。**

逐项证据：

| 检查项 | 扫描命令 / 方法 | 结果 |
|---|---|---|
| 跨测试默认真源 | `rg "from tests.engine.test_agent_phase3_tool_call import" tests/` | 零命中。`_TEST_FALLBACK_PROMPT` 和 `_TEST_CONTINUATION_PROMPT` 仅在 `tests/engine/test_agent_phase3_tool_call.py` 文件内使用，为 module-private 常量（`_` 前缀），未被任何其他测试模块导入 |
| 跨测试 prompt 常量扩散 | `rg "_TEST_FALLBACK_PROMPT\|_TEST_CONTINUATION_PROMPT" tests/` | 全部 19 个命中均在 `tests/engine/test_agent_phase3_tool_call.py` 内；`tests/host/test_package_exports.py` 中的 `DEFAULT_FALLBACK_SELECTED_RECENT_WINDOW_*` 常量与 AgentPolicy prompt 无关 |
| LLM-facing 默认迁回 Engine | `rg "_DEFAULT_FALLBACK_PROMPT\|_DEFAULT_CONTINUATION_PROMPT" dayu/engine` | 零命中 |
| Runtime 旧名回归 | `rg "AgentPolicyDefaults\|code_default\|_SOURCE_CODE_DEFAULT\|_agent_policy_defaults_from_config" dayu/ tests/ utils/ --glob '*.py'` | 零命中 |
| 新增 production 变更 | `git diff -- dayu/` | 无 fix 引入的新增 production diff |

### 4. Controller 验证复核

**结论：controller 验证结果充分。** 逐项复现：

| 验证项 | 命令 | 复现结果 |
|---|---|---|
| 聚焦 Engine contract 测试 | `pytest tests/engine/test_agent_phase3_tool_call.py` | `45 passed in 0.19s` |
| 类型检查 | `pyright` | `0 errors, 0 warnings, 0 informations` |
| 空白检查 | `git diff --check` | 无输出（pass） |

三项验证均与 controller 验证结果和 fix artifact 报告一致。

## Propagation Audit

Fix 仅修改测试断言矩阵，业务语义传播路径完全未变：

```
Config Source (execution_profiles.json / compactor scene)
  → ConfigLoader.AgentPolicyConfig
    → merge_agent_policy_config(...)
      → AgentPolicy(fallback_prompt=..., continuation_prompt=...)
        → Host baseline / durable restore
          → AgentRunRequest.agent_policy
            → Engine fallback / continuation 状态机 → LLM user message
```

Engine `AgentPolicy.__post_init__` 的校验逻辑（`strip() == ""` → `ValueError`）未变；`continuation_prompt` 空白拒绝的测试覆盖从单 case 扩展为三 case 循环，与 `fallback_prompt` 对称。

## Conclusion

**pass**

唯一 accepted finding `P2C-IMPL-F01` 已关闭：

- `continuation_prompt` 与 `fallback_prompt` 的空白值覆盖现在对称：均为 `("", "   ", "\n\t")` 三 case 循环。
- Fix 只落在 Engine contract test boundary（`tests/engine/test_agent_phase3_tool_call.py`），production code 无新增变化。
- 未引入新的测试异味、跨测试默认真源、LLM-facing 默认迁回 Engine、或 runtime 旧名回归。
- 三项 controller 验证（pytest 45 passed、pyright 0、git diff --check pass）均已复现确认。

无新 material finding。

## Residual Notes

- Broad suite 8 个 failure 仍是 umbrella residual，本 fix 未涉及；需在 umbrella final closeout 前由对应 owner 处理。
- `_TEST_FALLBACK_PROMPT` 和 `_TEST_CONTINUATION_PROMPT` 是文件级 module-private 常量，若未来 Engine contract 测试拆分多个文件，建议通过 Engine contract test fixture（而非复制常量）共享测试输入值。

## Artifact Path

`docs/reviews/wu-semantic-ownership-01-p2-c-implementation-rereview-ds.md`
