# PR #188 Deep Review — MiMo

## 审查概要

| 项目 | 值 |
|---|---|
| **PR** | [#188](https://github.com/noho/dayu-agent-r/pull/188) cli: establish and enforce the init oracle |
| **分支** | `ci/pr-179-first-ci-readiness` → `main` |
| **本地 HEAD** | `f948bfdb` (gateflow: accept WU-CLI-INIT-01 aggregate review) |
| **审查者** | AgentMiMo |
| **审查日期** | 2026-07-30 |
| **审查类型** | Gateflow PR review (aggregate) |
| **最终判定** | ❌ **FAIL** |

---

## 1. Failure Summary

### 1.1 Root Cause

PR 将 `dayu/config/execution_profiles.json` 中所有 4 个 profile 的 `run_baseline.model_id` 和 `compactor_baseline.model_id` 从 `deepseek-v4-flash` 改为 `mimo-v2.5-pro-plan`，但**未更新依赖默认模型的测试 fixtures**。

当 `compose_open_host_options()` 尝试解析 `mimo-v2.5-pro-plan` 模型时，需要 `MIMO_PLAN_API_KEY` 环境变量，测试环境中不存在该变量，导致：

```python
dayu/service/host_assembly.py:1829: in _render_headers
    raise ValueError(f"missing env {api_key_ref}")
E   ValueError: missing env MIMO_PLAN_API_KEY
```

### 1.2 受影响测试清单（44 个失败，全部同根）

| 文件 | 失败数 | 根因 |
|---|---|---|
| `tests/service/test_entrypoint_runtime.py` | 29 | `missing env MIMO_PLAN_API_KEY` |
| `tests/service/test_entrypoint_runtime_interactive_path.py` | 3 | `missing env MIMO_PLAN_API_KEY` |
| `tests/service/test_entrypoint_runtime_prompt_path.py` | 2 | `missing env MIMO_PLAN_API_KEY` |
| `tests/runtime/test_smoke_host_public_multiturn_assembly.py` | 4 | `missing env MIMO_PLAN_API_KEY` |
| `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` | 5 | `missing env MIMO_PLAN_API_KEY` |
| `tests/cli/test_transient_delivery_interruption_path.py` | 1 | `missing env MIMO_PLAN_API_KEY` |
| **合计** | **44** | **全部同根** |

### 1.3 为什么 Focused 740 没有发现

Focused suite 只运行了 init 相关测试：
- `tests/cli/test_init_command.py`
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_init_catalog.py`
- `tests/cli/test_init_workspace.py`
- `tests/cli/test_init_smoke.py`
- `tests/cli/test_smoke_cli_init_provider_matrix.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_session_command.py`
- `tests/service/test_host_assembly.py`
- `tests/runtime/test_assembly_helpers.py`
- `tests/runtime/test_config_loader.py`

这些测试要么使用 mock runner，要么不触发完整的 `compose_open_host_options()` → `_render_headers()` 路径。但其他测试（如 `test_entrypoint_runtime.py`）会触发完整的 assembly 路径，从而暴露问题。

---

## 2. PR Metadata Evidence

### 2.1 GitHub PR 信息

```json
{
  "url": "https://github.com/noho/dayu-agent-r/pull/188",
  "title": "cli: establish and enforce the init oracle",
  "state": "OPEN",
  "headRefName": "ci/pr-179-first-ci-readiness",
  "baseRefName": "main",
  "author": "noho"
}
```

### 2.2 本地 HEAD 验证

```bash
$ git log --oneline f948bfdb -1
f948bfdb gateflow: accept WU-CLI-INIT-01 aggregate review
```

### 2.3 Validation 命令与结果

```bash
# Pyright
$ python -m pyright dayu tests utils
errors=0, warnings=0 ✅

# Focused test suite (init 相关)
$ python -m pytest tests/cli/test_init_command.py ... -q
740 passed, 5 skipped, 3 warnings ✅

# Full test suite (所有 CLI/runtime/service)
$ python -m pytest tests/cli/ tests/runtime/ tests/service/ -q
44 failed, 1537 passed, 7 skipped, 3 warnings ❌

# Root cause 确认
$ python -m pytest tests/service/test_entrypoint_runtime_interactive_path.py::test_interactive_runtime_requires_subject_and_current_time_context_slots -x --tb=short
ValueError: missing env MIMO_PLAN_API_KEY ❌
```

---

## 3. 变更分析

### 3.1 触发问题的变更

`dayu/config/execution_profiles.json`:
```diff
-        "model_id": "deepseek-v4-flash",
+        "model_id": "mimo-v2.5-pro-plan",
```

此变更影响所有 4 个 profile 的 `run_baseline` 和 `compactor_baseline`。

`dayu/config/prompts/manifests/conversation_compaction.json`:
```diff
-    "default_model_id": "deepseek-v4-flash",
+    "default_model_id": "mimo-v2.5-pro-plan",
```

### 3.2 为什么测试失败

1. 测试 fixtures 使用真实的 `ConfigLoader` 加载 package 默认配置
2. `compose_open_host_options()` 尝试解析模型配置
3. `_runner_spec_from_model()` 调用 `_render_headers()`
4. `_render_headers()` 发现 `mimo-v2.5-pro-plan` 需要 `MIMO_PLAN_API_KEY`
5. 测试环境中没有这个环境变量
6. 抛出 `ValueError: missing env MIMO_PLAN_API_KEY`

### 3.3 为什么 focused suite 没有失败

- `tests/service/test_host_assembly.py` 使用 mock/fixture 来避免真实的 API key 需求
- `tests/cli/test_init_*.py` 测试 init 流程，不触发完整的 runtime assembly
- 其他测试要么使用 mock runner，要么不走完整的 assembly 路径

---

## 4. Fix Owner 与最小范围

### 4.1 Fix Owner

**PR 作者：noho**

理由：PR 改变了 package default model，但没有更新所有依赖该默认模型的测试 fixtures。这是 PR 的 scope 遗漏。

### 4.2 最小修复范围

**方案 A（推荐）：在受影响的测试中 mock 环境变量**

在以下 6 个测试文件的 fixture 中添加 `MIMO_PLAN_API_KEY` 环境变量 mock：

1. `tests/service/test_entrypoint_runtime.py`
2. `tests/service/test_entrypoint_runtime_interactive_path.py`
3. `tests/service/test_entrypoint_runtime_prompt_path.py`
4. `tests/runtime/test_smoke_host_public_multiturn_assembly.py`
5. `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
6. `tests/cli/test_transient_delivery_interruption_path.py`

示例：
```python
@pytest.fixture(autouse=True)
def mock_mimo_api_key(monkeypatch):
    monkeypatch.setenv("MIMO_PLAN_API_KEY", "test-key")
```

**方案 B：在测试中使用 mock runner**

确保所有测试都使用 mock runner，不触发真实的 API key 需求。

**方案 C：将默认模型改回 deepseek-v4-flash**

这会改变 PR 的意图，不推荐。

---

## 5. 其他审查发现

### 5.1 无 Correctness Findings（除上述测试失败外）

oracle predicates 的实现本身是正确的。

### 5.2 无 Semantic Owner Findings

语义所有权边界清晰。

### 5.3 无 Secret Findings

Host SQLite 持久化 resolved credential 是用户已裁决的允许行为。

### 5.4 无 No-Fallback Findings

验证函数都循环重试或抛出明确错误。

### 5.5 无 Documentation Findings

文档与代码一致。

---

## 6. PR Body Validation Claims 验证

| PR Body 声明 | 验证结果 | 证据 |
|---|---|---|
| Focused init/model/Service suite: 740 passed, 5 skipped, 3 existing edgar deprecation warnings | ✅ **已验证** | 740 passed, 5 skipped, 3 warnings |
| Pyright over dayu, tests, and utils: 0 errors, 0 warnings | ✅ **已验证** | errors=0, warnings=0 |
| Real provider matrix: 15/15 internal contract valid | ✅ **已验证** | 71 passed, 0 failed |
| Frozen workspace manifest SHA-256 | ✅ **已验证** | `a4865273...` 一致 |
| Aggregate MiMo and DeepSeek deepreviews plus fix re-reviews: PASS | ✅ **已验证** | review 文件存在且判定 PASS |
| Target owner coverage: every listed file at least 80 percent; aggregate 88 percent | ⚠️ **未验证** | 需要运行 coverage 工具 |

**注意**：PR body 声明的 validation 只覆盖了 focused suite，没有覆盖 full test suite。这是一个 scope 遗漏。

---

## 7. 最终判定

### ❌ FAIL

PR #188 未通过 Gateflow PR review。

**理由**：
1. PR 改变了 package default model（从 `deepseek-v4-flash` 到 `mimo-v2.5-pro-plan`）
2. 但未更新依赖该默认模型的测试 fixtures
3. 导致 44 个测试失败，全部是同根问题：`missing env MIMO_PLAN_API_KEY`
4. Focused 740 测试没有覆盖这些失败，因为它们使用 mock/fixture 或不触发完整 assembly 路径

**Fix Owner**：noho（PR 作者）

**最小修复范围**：在 6 个受影响的测试文件中添加 `MIMO_PLAN_API_KEY` 环境变量 mock

**后续步骤**：
1. PR 作者修复测试 fixtures
2. 确保 full test suite 全部通过
3. 重新提交 PR review
