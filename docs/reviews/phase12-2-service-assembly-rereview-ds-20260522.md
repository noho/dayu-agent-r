# Code Review — Phase 12.2 Service Assembly DS Finding 1 Re-review

## Scope

- **Mode**: scoped re-review of DS Finding 1 fix only.
- **Source review artifact**: `docs/reviews/phase12-2-service-assembly-code-review-ds-20260522.md`
- **Output file**: `docs/reviews/phase12-2-service-assembly-rereview-ds-20260522.md`
- **Included scope**:
  - `dayu/service/host_assembly.py` — `_agent_fallback_mode_from_config`（line 807–815）
  - `tests/service/test_host_assembly.py` — 新增 `test_agent_fallback_mode_from_config_uses_engine_enum_values`（line 153–170）
  - `docs/reviews/phase12-2-service-assembly-implementation-codex-20260522.md` — Fix Addendum 段（line 79–103）
- **Excluded scope**:
  - DS Finding 2（README 死链）— 本轮 out-of-scope/deferred
  - `docs/reviews/repo-review-20260522-070034.md`、`docs/reviews/repo-review-20260522-070045.md` — controller 指令忽略

## Fix Verification

### DS Finding 1: `_agent_fallback_mode_from_config` 手工 if/elif → `AgentFallbackMode(value)`

**原状态**（host_assembly.py:815–818）：
```python
if value == "force_answer":
    return AgentFallbackMode.FORCE_ANSWER
if value == "raise_error":
    return AgentFallbackMode.RAISE_ERROR
raise ValueError(f"unsupported fallback_mode: {value}")
```

**修复后**（host_assembly.py:815）：
```python
return AgentFallbackMode(value)
```

**验证**：
- `AgentFallbackMode` 是 `StrEnum`（`dayu/engine/contracts/agent_policy.py:15`），成员 `FORCE_ANSWER = "force_answer"`、`RAISE_ERROR = "raise_error"`。
- `StrEnum(value)` 对合法字符串值返回对应枚举成员；对非法值 `raise ValueError`。
- 修复后对合法输入的行为与原 if/elif 链完全等价：`AgentFallbackMode("force_answer")` 返回 `AgentFallbackMode.FORCE_ANSWER`，`AgentFallbackMode("raise_error")` 返回 `AgentFallbackMode.RAISE_ERROR`。
- 修复后对非法输入的行为与原代码一致：`AgentFallbackMode("unsupported")` 抛出 `ValueError`。
- 若 `AgentFallbackMode` 新增成员（如 `FALLBACK_TO_DEFAULT = "fallback_to_default"`），`AgentFallbackMode(value)` 自动支持新值，不再需要同步修改此函数。**原 finding 的 maintainability 问题已收口**。

### 新增测试验证

`test_host_assembly.py:153–170` `test_agent_fallback_mode_from_config_uses_engine_enum_values`：

- Line 161–164：验证 `"force_answer"` → `AgentFallbackMode.FORCE_ANSWER`（`is` identity check）。
- Line 165–168：验证 `"raise_error"` → `AgentFallbackMode.RAISE_ERROR`（`is` identity check）。
- Line 169–170：验证 `"unsupported"` → `ValueError`（`pytest.raises`）。

三个路径全部覆盖，断言精确（`is` 而非 `==`，保证返回的是枚举单例而非碰巧相等的字符串）。

### 新增问题检查

- **函数签名**：`(value: str) -> AgentFallbackMode` 不变，调用方无影响。
- **返回类型**：`AgentFallbackMode(value)` 返回 `AgentFallbackMode`，与原函数返回类型一致。
- **异常语义**：`ValueError` 保持不变，调用方异常处理路径不受影响。
- **导入**：`test_host_assembly.py:24` 新增 `from dayu.service.host_assembly import _agent_fallback_mode_from_config`。这是对私有函数的 focused 测试导入，实现 artifact 的 validation 确认 pyright 0 errors。
- **架构**：修改仅在 Service 层内部（`host_assembly.py` + 对应测试），不涉及 `dayu.runtime` 层，无跨层影响。

### Controller Validation Report

根据实现 artifact 的 Fix Addendum (line 98–101)：
- `pytest tests/service -q`：3 passed（修复前 2 passed，新增 1 个 focused test）
- `pyright dayu/service tests/service`：0 errors, 0 warnings, 0 informations

## Findings

未发现实质性问题。DS Finding 1 已收口，无新增 blocker。

## Open Questions

无。

## Residual Risk

无。修复范围极小且精确：一行生产代码改动（if/elif 链替换为 `AgentFallbackMode(value)`），一个 focused 测试（覆盖两个合法值 + 一个非法值），零新增依赖，零跨层修改。

## Conclusion

**PASS**

DS Finding 1 已收口：`_agent_fallback_mode_from_config` 从手工 if/elif 映射改为 `AgentFallbackMode(value)` 直接构造，行为完全等价，新增 `AgentFallbackMode` 成员时自动获得支持。配套 focused 测试覆盖两个合法值和非法值路径。blocking finding count = 0。无新增问题。
