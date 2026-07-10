# WU-SEMANTIC-OWNERSHIP-01 / P3-D / S3 Re-Review (AgentDS)

## Scope

- Mode: re-review gate — 复核 P3-D-S3-CR-F01 fix 是否关闭。
- Work unit: WU-SEMANTIC-OWNERSHIP-01 / P3-D - Engine provider protocol normalization
- Slice: S3 - Typed Engine error codes and propagation audit
- Finding under review: P3-D-S3-CR-F01
- Output file: docs/reviews/wu-semantic-ownership-01-p3-d-s3-rereview-ds.md
- Re-reviewer: AgentDS
- Date: 2026-07-11

### Sources

- Controller adjudication: docs/reviews/wu-semantic-ownership-01-p3-d-s3-code-review-controller-adjudication.md
- Fix artifact: docs/reviews/wu-semantic-ownership-01-p3-d-s3-fix-codex.md
- Controller fix validation: docs/reviews/wu-semantic-ownership-01-p3-d-s3-fix-controller-validation.md
- Original MiMo review: docs/reviews/wu-semantic-ownership-01-p3-d-s3-code-review-mimo.md
- Original DS review: docs/reviews/wu-semantic-ownership-01-p3-d-s3-code-review-ds.md

### Excluded scope

- 不重新裁決已接受的 residual risks（S3 intentional string-only constructor break、provider-specific wrapper source 不在 Host 暴露）。
- 不 review S3 原始实现变更（production files、new test coverage、README/doc 更新），这些已由原始 DS review 覆盖并确认为无实质性问题。

## Re-Review Checklist

### 1. Agent tests no longer compare typed error_code directly to string literals

**通过。** 

- `rg -n '\.error_code\s*==\s*"' tests/engine/test_agent_phase2.py` — **零命中**。
- `rg -n '\.error_code\s*!=\s*"' tests/engine/test_agent_phase2.py` — **零命中**。
- 全部 9 处原 MiMo finding 001 指出的断言点均已替换为 `_assert_engine_run_error_code(...)` 或 `_assert_runner_specific_error_code(...)` 调用。

直接证据：`tests/engine/test_agent_phase2.py:765,864,917,1030,1054,1070,1524,1655,1884`。

### 2. EngineRunErrorCode assertions prove enum identity and serialized value

**通过。**

`_assert_engine_run_error_code` helper（`tests/engine/test_agent_phase2.py:105-117`）：

```python
assert actual is expected                                        # enum identity
assert serialize_engine_error_code(actual) == expected.value     # serialized value
```

- `is` 操作符确保 `actual` 是同一个 enum member 对象，而非等值裸字符串 — 这区分了 `EngineRunErrorCode.CONTEXT_COMPACTION_REQUIRED`（enum member）与 `"context_compaction_required"`（裸字符串）。
- `serialize_engine_error_code(actual) == expected.value` 额外校验 durable text 序列化结果与 enum 成员的 canonical value 一致。

全部 7 处 EngineRunErrorCode 断言均使用此 helper：`test_agent_phase2.py:917,1030,1054,1070,1524,1655`（6 处 `RunFailedData.error_code`）及隐式覆盖。

### 3. RunnerSpecificErrorCode assertions prove wrapper type, source, and serialized value

**通过。**

`_assert_runner_specific_error_code` helper（`tests/engine/test_agent_phase2.py:120-137`）：

```python
assert isinstance(actual, RunnerSpecificErrorCode)               # wrapper type
assert actual.source is expected_source                          # source discriminator
assert serialize_engine_error_code(actual) == expected_value     # serialized value
```

- `isinstance(actual, RunnerSpecificErrorCode)` 确保字段未退化为裸 `str`。
- `actual.source is expected_source` 确保 wrapper 的闭集 source discriminator 未被丢失。
- `serialize_engine_error_code(actual) == expected_value` 确保 durable text 序列化符合预期。

全部 3 处 RunnerSpecificErrorCode 断言均使用此 helper：`test_agent_phase2.py:765,864,1884`。

### 4. Weak-typing guard precisely prevents direct `.error_code == "..."` or `.error_code != "..."` regressions

**通过。**

Guard 测试 `test_agent_tests_do_not_compare_typed_error_codes_to_literal_strings`（`tests/engine/test_weak_typing_guard.py:344-370`）：

- **精确范围**：仅扫描 `tests/engine/test_agent_phase2.py`，不扫描 Host durable text（`engine_ingest.py` 含 44 处 `error_code` 引用，均不在 guard 扫描范围内）。
- **精确模式**：AST 级别的 `ast.Compare` 节点，仅当同时满足以下条件时触发：
  - 运算符为 `ast.Eq` 或 `ast.NotEq`
  - 表达式一侧包含 `.error_code` 属性读取（`_contains_error_code_attribute` 辅助函数通过 `ast.Attribute` 检测，排除裸变量名 `error_code`、字典下标 `data["error_code"]`、序列化函数调用 `serialize_engine_error_code(...)` 等误报）
  - 表达式另一侧为字符串字面量 `ast.Constant`
- **对抗验证**：手动构造 `.error_code == "bad_sse"` 输入，guard 正确检出；裸变量名 `error_code` 和字典下标 `data["error_code"]` 均不触发误报。

直接证据：`tests/engine/test_weak_typing_guard.py:233-243`（`_contains_error_code_attribute`）、`344-370`（guard 测试）。

### 5. No production behavior, README/doc, LLM-facing path, or Host projection was unnecessarily changed

**通过。**

Fix gate 仅修改两个文件：
- `tests/engine/test_agent_phase2.py`：新增两个测试 helper、替换 9 处断言
- `tests/engine/test_weak_typing_guard.py`：新增一个 guard 测试

未修改任何 `dayu/engine/`、`dayu/host/`、`dayu/config/` 下的生产代码、README、设计文档、LLM-facing prompt 或 Host projection。S3 分支中的生产文件变更为 S3 原始实现内容，已由原始 DS review 确认为无实质性问题。

## Verification

```
# 受影响测试
source .venv/bin/activate && pytest tests/engine/test_agent_phase2.py tests/engine/test_weak_typing_guard.py -q
# → 72 passed in 0.31s

# 扩展 Engine 测试矩阵
source .venv/bin/activate && pytest tests/engine/contracts tests/engine/test_engine_event_contract.py tests/engine/test_package_exports.py tests/engine/test_agent_phase2.py -q
# → 149 passed in 0.18s

# pyright
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
# → 0 errors, 0 warnings, 0 informations

# git diff --check
# → 通过，无输出。
```

## Findings

### P3-D-S3-CR-F01 关闭判定：已修复

全部 5 项 checklist 均有直接证据支撑：

| Checklist | 状态 | 关键证据 |
|---|---|---|
| 1. 无字符串字面量直接比较 | 通过 | `rg` 零命中，全部 9 处替换为 typed helper |
| 2. EngineRunErrorCode enum identity + serialized value | 通过 | `actual is expected` + `serialize_engine_error_code` |
| 3. RunnerSpecificErrorCode type + source + serialized value | 通过 | `isinstance` + `is` source + `serialize_engine_error_code` |
| 4. Weak-typing guard 精确防回归 | 通过 | AST 级 `.error_code` 属性检测，仅扫 `test_agent_phase2.py` |
| 5. 无生产行为/文档/LLM 路径变更 | 通过 | Fix gate 仅改两个测试文件 |

### 新 material findings：无

经过对 fix 变更的逐行走读和对抗验证，未发现新的实质性 defect。Fix 变更精准、最小化，落在正确的 owner boundary（Engine contract 测试证明边界和弱类型守卫），未触及 Host consumer、展示层、文档或 LLM-facing 路径。

## Open Questions

- 无。

## Residual Risk

- S3 intentional string-only constructor break 保持原 accepted residual risk，本次 fix 不改变。
- Provider-specific wrapper source 仍只在 Engine typed wrapper 内可见，Host durable/public projection 仍是 serialized text；如未来需要公开 source，需要新的 Engine/Host public contract。
- Guard 仅扫描 `tests/engine/test_agent_phase2.py`；若未来其他 Engine 测试文件（如 `tests/engine/contracts/`）出现 typed error_code 与字符串字面量直接比较，当前 guard 不会捕获。但此类文件当前不存在该模式（已验证），且若新增此类断言，应在此 guard 中扩展扫描范围。

---

S3 re-review complete.
