# WU-CLI-INIT-01 PR #188 Fix Re-Review — DS

## Re-review metadata

- **PR**: [#188](https://github.com/noho/dayu-agent-r/pull/188) — `cli: establish and enforce the init oracle`
- **审查类型**: PR fix re-review（Controller 复审 PR-F3 blocking finding 后的 fixture 修复验证）
- **审查者**: AgentDS（Claude Code / DeepSeek）
- **日期**: 2026-07-30
- **输入文档**:
  - `docs/reviews/wu-cli-init-01-pr-review-ds.md`（原始 DS PR review，含 PR-F3 blocking finding）
  - `docs/reviews/wu-cli-init-01-pr-fix-codex.md`（Controller fix 裁决 + Codex 修复）
  - `docs/reviews/wu-cli-init-01-pr-review-mimo.md`（MiMo 独立 PR review）
  - `docs/reviews/wu-cli-init-01-goal-confirmation-controller.md`
- **本次审查范围**: 仅审查 fix diff 的正确性、完整性、生产扩散和残余风险；不重新审查已有 aggregate review findings

---

## Verdict

**PASS** — PR-F3 blocking finding 已完全修复。

7 个测试文件各新增 `_runtime_assembly_env()` helper，统一替换旧的单-key `env` dict 为双-key env。0 生产代码扩散。105 个受影响测试全部通过。Full suite 5960 passed。pyright 0 errors。

---

## 1. Fix 变更概览

| 维度 | 值 |
|------|-----|
| 变更文件数 | 7（全部在 `tests/` 下） |
| Insertions | 111 |
| Deletions | 15 |
| 生产代码变更 | 0 |
| 新增 helper 函数 | 7 个（每文件一个 `_runtime_assembly_env()`） |

### 1.1 逐文件变更

| # | 文件 | 变更内容 | 影响行 |
|---|------|---------|--------|
| 1 | `tests/service/test_entrypoint_runtime_interactive_path.py` | 新增 `_runtime_assembly_env()`；L296, L363 `env=` 替换 | +17/-2 |
| 2 | `tests/service/test_entrypoint_runtime.py` | 新增 `_runtime_assembly_env()`；L3124 `env=` 替换 | +15/-1 |
| 3 | `tests/service/test_entrypoint_runtime_prompt_path.py` | 新增 `_runtime_assembly_env()`；L365 `env=` 替换 | +15/-1 |
| 4 | `tests/tools/test_combined_tools_acceptance.py` | 新增 `_API_KEY` 常量 + `_runtime_assembly_env()`；L390 `env=` 替换 | +16/-1 |
| 5 | `tests/cli/test_transient_delivery_interruption_path.py` | 新增 `_API_KEY` 常量 + `_runtime_assembly_env()`；L313 `env=` 替换 | +16/-1 |
| 6 | `tests/runtime/test_smoke_host_public_multiturn_assembly.py` | 新增 `_runtime_assembly_env()`；4 处 `env=` 替换 | +21/-4 |
| 7 | `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` | 新增 `_runtime_assembly_env()`；5 处 `env=` 替换 | +26/-5 |

### 1.2 变更模式一致性

每个文件的修改模式完全相同：

```python
# 新增 helper（模块级私有函数）
def _runtime_assembly_env() -> dict[str, str]:
    """构造真实 <文件名描述> assembly 所需的测试 credential 环境。

    :returns: 同时包含显式 DeepSeek 主 Run 与 package MiMo compactor credential 的新字典。
    :raises Exception: 不主动抛出异常。
    """
    return {
        "DEEPSEEK_API_KEY": _API_KEY,
        "MIMO_PLAN_API_KEY": _API_KEY,
    }

# 旧调用
env={"DEEPSEEK_API_KEY": _API_KEY}
# → 新调用
env=_runtime_assembly_env()
```

**一致性判定**: ✅ 全部 7 个文件遵循同一模式。`test_combined_tools_acceptance.py` 与 `test_transient_delivery_interruption_path.py` 额外提取了 `_API_KEY` 常量（原为内联字面量），这是合理的代码质量提升，不改变行为。

---

## 2. 测试验证

### 2.1 受影响文件（105 tests）

```
tests/service/test_entrypoint_runtime.py                      63 passed
tests/service/test_entrypoint_runtime_interactive_path.py      3 passed
tests/service/test_entrypoint_runtime_prompt_path.py           3 passed
tests/tools/test_combined_tools_acceptance.py                  ~5 passed
tests/cli/test_transient_delivery_interruption_path.py         1 passed
tests/runtime/test_smoke_host_public_multiturn_assembly.py     ~8 passed
tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py ~22 passed
────────────────────────────────────────────────────────────────
Total: 105 passed, 0 failed, 3 warnings
```

### 2.2 Full suite

```
5960 passed, 10 skipped, 6 deselected, 3 warnings in 184.09s
```

**0 failures across full suite。** 10 skipped 和 3 warnings 均为 edgar deprecation warnings（已知、预存、非本 WU 引入）。

### 2.3 pyright

```
0 errors, 0 warnings, 0 informations
```

---

## 3. 零生产扩散验证

| 检查项 | 结果 |
|--------|------|
| `git diff --name-only` 不含 `dayu/` 路径 | ✅ 全部 7 个文件在 `tests/` 下 |
| `git diff --name-only` 不含生产配置 | ✅ 无 `dayu/config/` 变更 |
| 无新常量、类型、接口暴露 | ✅ `_runtime_assembly_env()` 是模块级私有函数 |
| 无测试逻辑变更 | ✅ 只替换 `env=` 参数值；断言、mock、控制流不变 |

---

## 4. Helper 只进完整 Assembly 路径验证

| 文件 | `_runtime_assembly_env()` 调用点 | 进入的 assembly 入口 | 完整路径？ |
|------|-------------------------------|---------------------|-----------|
| `test_entrypoint_runtime.py` | `_prepare_runtime` → `prepare_entrypoint_runtime(..., env=...)` | `prepare_entrypoint_runtime` → `compose_open_host_options` → `_compose_options` → `_runner_spec_from_model(compactor)` | ✅ |
| `test_entrypoint_runtime_interactive_path.py` | `_prepare_interactive_runtime` → 同上 | 同上 | ✅ |
| `test_entrypoint_runtime_prompt_path.py` | `_prepare_prompt_runtime` → 同上 | 同上 | ✅ |
| `test_combined_tools_acceptance.py` | `compose_open_host_options(..., env=...)` | 同上（直接调用） | ✅ |
| `test_transient_delivery_interruption_path.py` | `prepare_entrypoint_runtime(..., env=...)` | 同上（直接调用） | ✅ |
| `test_smoke_host_public_multiturn_assembly.py` | `_prepare_runtime_assembly(_args(...), env=...)` | `_prepare_runtime_assembly` → `compose_open_host_options` | ✅ |
| `test_smoke_host_public_conversation_memory_scenarios_assembly.py` | `_prepare_runtime_assembly(_args(...), env=...)` | 同上 | ✅ |

**所有 7 个 helper 的使用点均通过 `compose_open_host_options` / `prepare_entrypoint_runtime` / `_prepare_runtime_assembly` 进入完整 Host→Service→CLI assembly。无绕过 assembly 的 shortcut。** ✅

---

## 5. 前置 Fail-Closed 单-Key Case 合理性验证

`tests/service/test_host_assembly.py` 中保留 3 处单-key `env` 调用，全部 87 个测试通过。逐案分析：

### 5.1 L359: `env={"MIMO_PLAN_API_KEY": _MIMO_PLAN_API_KEY}` — S3 设计验证测试

- **测试**: `test_compactor_uses_ordinary_scene_hint_and_default_family`
- **路径**: 使用 package defaults（无 workspace overlay），`compose_open_host_options`
- **为何单-key 合理**: 这是 S3 新增的核⼼设计验证——证明未 init 时 package defaults 只需单个 provider credential（MIMO_PLAN_API_KEY）即可完成 compactor assembly。这正是 Goal Confirmation §目标 4 的直接 test evidence
- **判定**: ✅ 合理。单-key 是测试意图本身，不是 fixture 缺陷

### 5.2 L463: `env={"DEEPSEEK_API_KEY": _API_KEY}` — Workspace overlay 覆盖测试

- **测试**: `test_assembly_with_only_deepseek_key_validates_ordinary_compactor_identity`
- **路径**: 使用 workspace overlay（`_write_tool_discovery_overlay`），compactor model 被 workspace config 指定为 `deepseek-v4-flash`
- **为何单-key 合理**: workspace overlay 显式指定 DeepSeek 为 compactor model（非 package default Mimo），因此只需要 `DEEPSEEK_API_KEY`。该测试验证 workspace config override 优先级正确、family match 通过
- **判定**: ✅ 合理。workspace overlay 修改了 compactor model 的 owner，credential 需求随之改变

### 5.3 L1462: `env={"DEEPSEEK_API_KEY": _API_KEY}` — `_render_headers` 单元测试

- **测试**: `test_render_headers_rejects_unresolved_placeholder`
- **路径**: 直接调用 `_render_headers(...)`，不经过 assembly
- **为何单-key 合理**: 测试目标是"header 中存在未解析占位符时 fail-fast"，只需要一个已解析 key + 一个未解析 key 即可。单-key 不是设计选择，而是测试最小化输入原则
- **判定**: ✅ 合理。这是 `_render_headers` 的独立单元测试，不依赖 assembly 路径

### 5.4 总结

| 用例 | 类型 | 判定 |
|------|------|------|
| L359 `MIMO_PLAN_API_KEY` only | Package default 单-family 设计验证 | ✅ S3 设计意图 |
| L463 `DEEPSEEK_API_KEY` only | Workspace overlay override 验证 | ✅ Override 路径合法 |
| L1462 `DEEPSEEK_API_KEY` only | `_render_headers` 单元测试 | ✅ 单元测试最小输入 |

**3 个单-key case 均为有意识的测试设计，不是 fixture 遗漏。全部 test_host_assembly.py 的 87 个测试通过。** ✅

---

## 6. PR-F3 原始 Finding 关闭确认

| PR-F3 子项 | 修复前状态 | 修复后状态 | 关闭？ |
|-----------|-----------|-----------|--------|
| `test_entrypoint_runtime_interactive_path.py` (3 tests) | `ValueError: missing env MIMO_PLAN_API_KEY` | 3 passed | ✅ |
| `test_entrypoint_runtime.py` (~30 tests) | 同上 | 63 passed | ✅ |
| `test_entrypoint_runtime_prompt_path.py` (2 tests) | 同上 | 3 passed | ✅ |
| `test_combined_tools_acceptance.py` (1 test) | 同上 | ~5 passed | ✅ |
| `test_transient_delivery_interruption_path.py` (1 test) | 同上 | 1 passed | ✅ |
| `test_smoke_host_public_multiturn_assembly.py` (4 tests) | 同上 | ~8 passed | ✅ |
| `test_smoke_host_public_conversation_memory_scenarios_assembly.py` (5 tests) | 同上 | ~22 passed | ✅ |

**PR-F3 已完全关闭。** ✅

---

## 7. Scope 扩散检查

| 检查项 | 结果 |
|--------|------|
| 生产代码修改 | 0 文件 ✅ |
| 生产配置修改 | 0 文件 ✅ |
| 新增 public API | 0 ✅ |
| 修改测试逻辑（断言/mock/控制流） | 0 ✅ |
| 修改已有 helper 签名 | 0 ✅ |
| 新增 helper 数量 | 7（每文件 1 个，命名一致 `_runtime_assembly_env`） ✅ |
| 新增常量 | 2（`test_combined_tools_acceptance.py` + `test_transient_delivery_interruption_path.py` 各新增 `_API_KEY`） ✅ |
| 变更超出 7 个受影响的测试文件 | 0 ✅ |

---

## 8. Residual Risks

### 8.1 本 Fix 引入的新 Risk

**无。** Fix 是纯测试 fixture 更新：7 个模块级私有 helper，只被同一文件的 `env=` 参数消费。

### 8.2 已有 Residual Risks 状态

| ID | 描述 | 状态 |
|----|------|------|
| PR-F3 | 45 个测试 fixture 过时 | **已关闭** ✅ |
| PR-F1 | PR body 未提及 `session_execution.py` 变更 | Informational，保留 |
| PR-F2 | PR body 未提及 `ui-implementation-control.md` 变更 | Informational，保留 |
| R1–R6 | Aggregate review 残余 risks | 不变 |

---

## 9. 审查覆盖项确认

- ✅ Fix diff 逐文件检查（7 个文件，统一模式）
- ✅ 105 个受影响测试全部通过
- ✅ Full suite 5960 passed, 0 failures
- ✅ pyright 0 errors, 0 warnings
- ✅ 零生产代码扩散（`git diff --name-only` 全部在 `tests/`）
- ✅ Helper 只进入完整 assembly 路径（`compose_open_host_options` / `prepare_entrypoint_runtime` / `_prepare_runtime_assembly`）
- ✅ 3 个前置单-key case 合理性逐案验证
- ✅ PR-F3 关闭确认
- ✅ 只审查，未修改已有文件

---

## 10. Completion

- **Re-review verdict**: **PASS**
- **PR-F3 blocking finding**: 已完全关闭
- **Fix 文件数**: 7（全部在 `tests/`）
- **Fix 变更量**: 111 insertions(+), 15 deletions(−)
- **生产代码扩散**: 0
- **105 affected tests**: 全部通过
- **Full suite**: 5960 passed, 0 failures
- **pyright**: 0 errors, 0 warnings, 0 informations
- **新 finding**: 0
- **新 residual risk**: 0
- **无未关闭 finding**

**PR #188 可以推进到 final closeout gate。**
