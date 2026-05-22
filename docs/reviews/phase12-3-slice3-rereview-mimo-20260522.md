# Phase 12.3 Slice 3 Re-Review - AgentMiMo - 2026-05-22

## Verdict

**PASS** — 所有 Accepted Findings 已正确修复，无新增 blocking findings。

## 审查范围

- Controller adjudication：`docs/reviews/phase12-3-slice3-code-review-controller-adjudication-20260522.md`
- Implementation artifact Fix Addendum：`docs/reviews/phase12-3-slice3-implementation-codex-20260522.md`
- 当前 diff 中相关修改（10 个文件，+740/-42 行）

## 检查清单

### F1: Smoke assembly test 迁移 ✅ PASS

**检查项**：smoke assembly test 已从 `standard` 迁移到 `standard-256k`，且测试通过；没有新增 `standard` alias。

**证据**：
- `tests/runtime/test_smoke_host_public_multiturn_assembly.py:127`：`execution_profile_id="standard-256k"`
- `tests/runtime/test_smoke_host_public_multiturn_assembly.py:62`：`assert assembly.diagnostics.execution_profile_id == "standard-256k"`
- 测试通过：`56 passed in 0.99s`

**验证**：未新增 `standard` 兼容 alias。`rg -n '"standard"' tests/runtime/test_smoke_host_public_multiturn_assembly.py` 无输出（除注释外）。

### F2: __all__ 导出 ✅ PASS

**检查项**：`ExecutionProfileCompatibilityDiagnostic` 与 `validate_execution_profile_context_window` 已加入 `__all__`。

**证据**：
- `dayu/runtime/assembly.py:950-969`：`__all__` 列表包含：
  - `"ExecutionProfileCompatibilityDiagnostic"`（第953行）
  - `"validate_execution_profile_context_window"`（第968行）

### F3: 交叉校验 ✅ PASS

**检查项**：ConfigLoader 已交叉校验 `context_window_class` 与 `min_context_window_tokens`，256k 精确 262144，1m 精确 1000000，并有 focused tests。

**证据**：

1. **映射定义**（`dayu/runtime/config_loader.py:58-61`）：
```python
_EXECUTION_PROFILE_MIN_CONTEXT_WINDOW_TOKENS_BY_CLASS: Final[Mapping[str, int]] = {
    "256k": 262_144,
    "1m": 1_000_000,
}
```

2. **交叉校验函数**（`dayu/runtime/config_loader.py:1320-1345`）：
```python
def _validate_execution_profile_context_window_pair(
    *,
    context_window_class: str,
    min_context_window_tokens: int,
    context: str,
) -> None:
    expected_tokens = _EXECUTION_PROFILE_MIN_CONTEXT_WINDOW_TOKENS_BY_CLASS[
        context_window_class
    ]
    if min_context_window_tokens != expected_tokens:
        raise ConfigFieldError(
            f"{context}.min_context_window_tokens must be {expected_tokens} "
            f"when context_window_class is {context_window_class}"
        )
```

3. **调用点**（`dayu/runtime/config_loader.py:1238-1242`）：
```python
_validate_execution_profile_context_window_pair(
    context_window_class=context_window_class,
    min_context_window_tokens=min_context_window_tokens,
    context=context,
)
```

4. **测试覆盖**（`tests/runtime/test_config_loader.py:661-682`）：
- `test_execution_profile_context_window_pair_must_be_consistent` 覆盖两个矛盾组合：
  - `("1m", 262144)`：1m class 配 256k tokens
  - `("256k", 1000000)`：256k class 配 1m tokens
- 断言 `ConfigFieldError, match="min_context_window_tokens must be"`

### 无自动 profile 切换 ✅ PASS

**检查项**：未新增 Host public API、Engine code 或自动 profile 切换。

**证据**：
- `dayu/service/host_assembly.py` 的 `_select_execution_profile_id`（:516-531）只根据 `explicit_profile_id` 或 `config.execution_profiles.default_execution_profile_id` 选择
- `validate_execution_profile_context_window` 只做 fail-fast 校验和诊断，不改变 profile 选择
- `rg -n "auto.*switch|auto.*select|auto.*profile" dayu/runtime dayu/service` 无输出

## 验证结果

| 验证项 | 结果 |
|--------|------|
| `pytest tests/runtime/test_config_loader.py tests/runtime/test_assembly_helpers.py tests/service/test_host_assembly.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q` | 56 passed |
| `pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q` | 13 passed |
| `pyright dayu/runtime dayu/service tests/runtime tests/service` | 0 errors |
| `git diff --check` | clean |

## 非阻塞观察

### Observation #1：交叉校验使用精确值而非范围

`_validate_execution_profile_context_window_pair` 要求 `min_context_window_tokens` 精确等于映射表中的值，而非 `>=` 范围检查。

**评估**：这是正确的设计选择。`min_context_window_tokens` 是机器可读的兼容性元数据，精确值确保配置一致性，避免歧义。未来新增分档时只需扩展映射表。

### Observation #2：测试覆盖了所有矛盾组合

`test_execution_profile_context_window_pair_must_be_consistent` 使用 `@pytest.mark.parametrize` 覆盖了 `("1m", 262144)` 和 `("256k", 1000000)` 两种矛盾组合，完整覆盖了当前两个分档的交叉校验。

## 结论

Controller 接受的三个 findings（F1/F2/F3）均已正确修复：
- F1：smoke test 迁移到 `standard-256k`，测试通过
- F2：新符号已加入 `__all__`
- F3：交叉校验实现完整，测试覆盖充分

无新增 blocking findings。Slice 3 可标记为 PASS。
