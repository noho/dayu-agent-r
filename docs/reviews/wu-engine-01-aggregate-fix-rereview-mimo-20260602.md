# WU-ENGINE-01 Aggregate Fix Re-Review

## Scope

- Mode: aggregate fix re-review（仅审查 AgentCodex 修复 diff 与对应 artifact）
- Branch: `refactor/wu-engine-01-runner-diagnostic-payload-audit`
- 未提交 diff 范围：
  - `dayu/engine/runners/openai/diagnostic_payload.py`（F-01 规范化 helper + F-02 scalar preview helper）
  - `tests/engine/runners/openai/test_diagnostic_payload.py`（4 个新测试 + 既有测试扩展）
- 角色：AgentMiMo 独立 re-review，不修改文件、不 commit、不 push。

## Review Method

1. 逐行走读 `_normalized_sensitive_key` / `_is_sensitive_key` 改动，验证破折号规范化是否正确覆盖 F-01 场景。
2. 逐行走读 `_provider_error_scalar_preview` / `_provider_error_summary` 改动，验证非字符串标量保留是否正确覆盖 F-02 场景。
3. 审查新增 helper 的 docstring / type / 命名是否符合 AGENTS.md。
4. 审查新增测试是否实质（非 vacuous）、是否能防止回归。
5. 检查是否引入新的 correctness / security / type / layering 问题。

## Findings

### F-01 关闭确认：破折号敏感 key normalization

**修复方案**: 新增 `_normalized_sensitive_key(key: str) -> str`，执行 `key.lower().replace("-", "_")`。`_is_sensitive_key` 改为基于规范化结果匹配 `_SENSITIVE_KEY_FRAGMENTS`。

**验证**:

| 输入 key | 规范化结果 | 匹配片段 | 脱敏 |
|---|---|---|---|
| `api_key` | `api_key` | `api_key` | 是 |
| `api-key` | `api_key` | `api_key` | 是 |
| `x-api-key` | `x_api_key` | `api_key` | 是 |
| `client-secret` | `client_secret` | `secret` | 是 |
| `access-token` | `access_token` | `token` | 是 |
| `Authorization` | `authorization` | `authorization` | 是 |

**结论**: F-01 已关闭。规范化方案优于硬编码分支，可扩展性好（未来新增分隔符只需改一处）。`_SENSITIVE_KEY_FRAGMENTS` 保持不变，避免碎片化。

### F-02 关闭确认：provider error 非字符串标量保留

**修复方案**: 新增 `_provider_error_scalar_preview(value: JsonValue) -> tuple[bool, JsonValue]`，集中表达保留规则：

- `str` → 非空则经 `_scalar_preview` 截断保留，空字符串丢弃
- `bool` / `int` / `float` → 原样保留
- `None` → 原样保留
- 容器（`dict` / `list`）→ 丢弃

**验证**:

| 输入 | 保留 | 值 |
|---|---|---|
| `"rate limited"` | 是 | `"rate limited"`（截断至 160 字符） |
| `429` | 是 | `429` |
| `True` | 是 | `True` |
| `None` | 是 | `None` |
| `""` | 否 | — |
| `"   "` | 否 | — |
| `{"name": "messages"}` | 否 | — |

**结论**: F-02 已关闭。`bool` 在 `int` 之前检查（Python 中 `bool` 是 `int` 子类），顺序正确。容器值显式返回 `False`，不依赖 fallthrough。

### 新增 helper / docstring / type 合规检查

| 检查项 | 状态 |
|---|---|
| 中文 docstring（参数、返回值、异常） | `_normalized_sensitive_key` / `_provider_error_scalar_preview` 均符合 |
| 类型标注完整 | `key: str -> str`、`value: JsonValue -> tuple[bool, JsonValue]`，无 `Any` / `object` |
| 模块级私有函数 | 两个新 helper 均为模块级 `_` 前缀，无嵌套 |
| 无 `hasattr` / `getattr` | 无 |
| 无魔法数字 / 魔法字符串 | 无 |
| 分层边界 | 无新依赖引入；仍仅依赖标准库 + `dayu.contracts.json_value` |

### 测试审查

| 测试 | 类型 | 结论 |
|---|---|---|
| `test_diagnostic_payload_redacts_sensitive_values`（扩展） | 回归防护 | 实质：覆盖 4 个破折号形态敏感 key，assert 值不在 leaf strings 中 |
| `test_provider_error_summary_preserves_json_scalar_values` | 新增 | 实质：覆盖 `code: 429`、`type: True`、`param: None`，assert `provider_error` dict 精确匹配 |
| `test_provider_error_summary_filters_empty_strings_and_containers` | 新增 | 实质：覆盖空字符串、纯空白字符串、容器值，assert `provider_error` 为 `{}` |

**vacuous pass 检查**: 所有新增 assert 均基于实际返回值做精确断言（`==` 比较或 `not in` 检查），非 `assert True` / `assert diagnostic is not None` 等 vacuous 形式。

### 新增 correctness / security / type / layering 问题

**未发现。**

逐项检查：

1. **Security**: `_normalized_sensitive_key` 的 `.replace("-", "_")` 仅作用于 key 名匹配，不影响值处理。不存在绕过风险。
2. **Type**: `_provider_error_scalar_preview` 返回 `tuple[bool, JsonValue]`，实际返回值类型（`str | int | float | bool | None`）均为 `JsonValue` 子类型，pyright 0 errors 确认。
3. **Correctness**: `bool` 在 `int` 之前检查，避免 `True` 被当作 `1` 保留。容器值 fallthrough 到 `return False, ""`，不泄漏结构。
4. **Layering**: 无新模块依赖。`_provider_error_scalar_preview` 复用既有 `_scalar_preview`，不引入跨层耦合。

## Validation Results

| 验证项 | 状态 |
|---|---|
| 目标测试（9 个） | 全部通过 |
| pyright（目标文件） | 0 errors, 0 warnings |
| pyright（全量） | 0 errors, 0 warnings |
| 公共 API `__all__` | 未变更 |
| README 同步需求 | 无需（不改变公共接口、CLI、配置入口、事件字段形状） |

## Conclusion

**PASS** — 无 blocking / high / medium / low finding。

F-01 / F-02 均已正确关闭：

- F-01：`_normalized_sensitive_key` 通过 `lower() + replace("-", "_")` 统一规范化，覆盖 `api-key` / `x-api-key` / `client-secret` / `access-token` 等破折号形态，方案可扩展、无脆弱分支。
- F-02：`_provider_error_scalar_preview` 集中表达保留规则，`int` / `float` / `bool` / `None` 原样保留，空字符串与容器值显式过滤，`bool`-before-`int` 检查顺序正确。

修复未引入新的 correctness / security / type / layering / test 问题。代码符合 AGENTS.md 全部编码硬约束。
