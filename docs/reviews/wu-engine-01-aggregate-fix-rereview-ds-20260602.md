# WU-ENGINE-01 Aggregate Fix Re-review

## Scope

- 角色：AgentDS re-review。
- 输入 artifact：
  - `docs/reviews/wu-engine-01-aggregate-deepreview-ds-20260602.md`（原始 DS low findings F-01, F-02）
  - `docs/reviews/wu-engine-01-aggregate-fix-codex-20260602.md`（AgentCodex 修复记录）
  - `git diff -- dayu/engine/runners/openai/diagnostic_payload.py tests/engine/runners/openai/test_diagnostic_payload.py`
- 输出 artifact：本文件。
- 审查重点：F-01/F-02 是否关闭，是否引入新的 correctness/security/type/layering/test 问题。

## Review Method

1. 逐行审查 diff 中每个新增/修改的函数与测试。
2. 对 F-01 手动验证所有 claimed key pattern 的规范化匹配结果。
3. 对 F-02 手动验证所有 claimed scalar type 的保留/过滤行为，含 bool/int 子类顺序。
4. 对 `_is_sensitive_key` / `_provider_error_summary` 调用路径做端到端推演。
5. 运行受影响测试与 pyright 验证。
6. Adversarial failure pass：破折号规范化边界、容器泄漏、脆弱分支、vacuous test 风险。

## Finding-by-Finding Assessment

### F-01: 破折号形态敏感 key 未被 `_is_sensitive_key` 覆盖

**修复方案回顾**：

- 新增 `_normalized_sensitive_key(key: str) -> str`，在匹配前统一做 `key.lower().replace("-", "_")`。
- `_is_sensitive_key` 改为基于规范化 key 做既有片段子串匹配。
- 不新增 `_SENSITIVE_KEY_FRAGMENTS` 条目，不新增分支。

**验证结果**：

| Key | 规范化结果 | 命中片段 | 是否脱敏 |
|---|---|---|---|
| `api-key` | `api_key` | `api_key` | ✅ |
| `x-api-key` | `x_api_key` | `api_key` (子串) | ✅ |
| `client-secret` | `client_secret` | `secret` | ✅ |
| `access-token` | `access_token` | `token` | ✅ |
| `api_key` | `api_key` | `api_key` | ✅ (不退化) |
| `Authorization` | `authorization` | `authorization` | ✅ (不退化) |
| `normal-field` | `normal_field` | 无 | ✅ (无误伤) |
| `code` / `type` / `param` | `code` / `type` / `param` | 无 | ✅ (不影响 provider error 路径) |

**脆弱分支检查**：`_normalized_sensitive_key` 只有一行 `key.lower().replace("-", "_")`，无 if/else 分支。`_is_sensitive_key` 调用该规范化后走既有子串匹配。整体结构为 `normalize → match`，未引入冗余分支。✅

**Adversarial 边界**：

- `api---key` → `api___key` → `"api_key" not in "api___key"` → 不匹配。此场景极度边缘（连续多个破折号在 API key 命名中不存在），属于 known limitation，在 AgentCodex 修复记录中已声明可继续在 `_normalized_sensitive_key` 扩展规范规则。
- `api-key_secret` → `api_key_secret` → 同时命中 `api_key` 和 `secret` → 正确脱敏。✅
- 空字符串 key `""` → `""` → 不命中 → 正确不脱敏（空 key 不会承载机密）。✅

**F-01 关闭判断**: **CLOSED**。修复覆盖了所有 claimed key pattern（`api-key` / `x-api-key` / `client-secret` / `access-token`），未引入脆弱分支，未退化既有下划线形态覆盖。

---

### F-02: `_provider_error_summary` 静默丢弃非字符串 `code`/`type`/`param`

**修复方案回顾**：

- 新增 `_provider_error_scalar_preview(value: JsonValue) -> tuple[bool, JsonValue]`：
  - 非空字符串：保留并按 `_DIAGNOSTIC_SCALAR_MAX_CHARS` 截断。
  - `int` / `float` / `bool` / `None`：保留为 JSON 标量。
  - 空字符串、仅空白字符串、容器值：不保留。
- `_provider_error_summary` 改为调用该 helper，不再只接受字符串。

**验证结果**：

| 输入值 | 类型 | 保留? | 预览值 | 正确? |
|---|---|---|---|---|
| `429` | `int` | ✅ | `429` | ✅ |
| `True` | `bool` | ✅ | `True` | ✅ |
| `None` | `NoneType` | ✅ | `None` | ✅ |
| `3.14` | `float` | ✅ | `3.14` | ✅ |
| `"rate_limited"` | `str` | ✅ | `"rate_limited"` | ✅ |
| `""` | `str` | ❌ | — | ✅ |
| `"   "` | `str` | ❌ | — | ✅ |
| `{"name": "msg"}` | `dict` | ❌ | — | ✅ |
| `[1, 2, 3]` | `list` | ❌ | — | ✅ |

**类型安全**：`isinstance(value, bool)` 在 `isinstance(value, int)` 之前检查，避免 `bool` 被错误提升为 `int`。手动验证确认 `issubclass(bool, int)` 为 `True`，先检查 `bool` 是正确的。✅

**有界性**：字符串经过 `_scalar_preview(value, max_chars=160)` 截断。`int`/`float`/`bool`/`None` 为 JSON 原生标量，在 JSON 序列化下自然有界（即使极端大整数也在 Python JSON parser 可表示范围内，且远小于 4096 字节上限）。✅

**容器拦截**：`dict` / `list` 落入最后的 `return False, ""` 分支，不会被保留。✅

**空字符串语义**：`value.strip() == ""` 同时覆盖 `""` 和 `"   "`（仅空白字符），语义与 `_provider_error_summary` 的"有意义的诊断信息"意图一致。✅

**F-02 关闭判断**: **CLOSED**。修复正确覆盖了 `int` / `float` / `bool` / `None` 的保留、空字符串与容器的过滤。类型检查顺序正确，有界性有保证。

---

## 新增代码审查

### `_normalized_sensitive_key`（diagnostic_payload.py:451-459）

- **docstring**: 完整中文，参数/返回值/异常说明齐全。✅
- **类型**: `str -> str`，无 `Any`/`object`。✅
- **位置**: 模块级私有函数，符合 CLAUDE.md "优先使用模块级私有辅助函数"。✅
- **无副作用**: 纯函数。✅

### `_provider_error_scalar_preview`（diagnostic_payload.py:332-351）

- **docstring**: 完整中文，参数/返回值/异常说明齐全。✅
- **类型**: `JsonValue -> tuple[bool, JsonValue]`，无 `Any`/`object`。✅
- **位置**: 模块级私有函数。✅
- **`isinstance` 使用**: 用于 JSON value type narrowing，属于充分理由。✅
- **`bool` 检查顺序**: 在 `int` 之前，避免子类误判。✅

### 测试扩展

- `test_diagnostic_payload_redacts_sensitive_values`: 新增 4 个破折号 key + 4 个对应 forbidden value。断言使用 `_leaf_strings` 递归遍历所有字符串叶子，能捕获任何泄漏。非 vacuous。✅
- `test_provider_error_summary_preserves_json_scalar_values`: 覆盖 `int(429)` / `bool(True)` / `None(null)` 三种标量，断言 exact equality。能防止回归到纯字符串过滤。非 vacuous。✅
- `test_provider_error_summary_filters_empty_strings_and_containers`: 覆盖空字符串、仅空白字符串、dict 容器。虽然有部分行为在旧实现中也成立（空字符串/容器过滤），但测试了新增 helper 的完整过滤语义——包括旧实现不存在的 `"   "` 空白字符串分支。非 vacuous。✅

### 未覆盖的边界

- `float` 类型的 provider error 字段：`_provider_error_scalar_preview` 代码路径覆盖了 `float`（与 `int` 共用 `isinstance` 分支），但测试中无显式 `float` 用例。由于 `float` 与 `int` 走相同分支且 Python 中 `float` 不是 `int` 的子类，实际风险极低。不作为 finding。
- 嵌套对象中的破折号敏感 key：`_top_level_preview` 对嵌套对象使用 `_container_summary`（仅返回结构摘要），不递归脱敏。这是设计意图（诊断载荷只做一层预览），非本次修复范围。

## Validation Results

| 验证项 | 状态 |
|---|---|
| 受影响测试 (9 个) | 全部通过 |
| pyright (目标文件) | 0 errors, 0 warnings |
| F-01 claimed key patterns 手动验证 | 全部通过 |
| F-02 claimed scalar types 手动验证 | 全部通过 |
| `bool`/`int` 检查顺序 | 正确 |
| 容器泄漏检查 | 无泄漏 |
| 分层边界 | 无违反（仅 `diagnostic_payload.py` + 测试） |
| 魔法数字/字符串 | 无新增 |
| 兼容性代码 | 无新增 |
| 嵌套函数/类 | 无新增 |
| `Any`/`object`/`getattr`/`hasattr` | 无使用 |
| vacuous test 风险 | 无 |

## Conclusion

**PASS** — 无 blocking、high、medium、low finding。

- F-01（破折号敏感 key）已通过 `_normalized_sensitive_key` 的 `-` → `_` 统一规范化关闭，未引入脆弱分支。
- F-02（非字符串 provider error 字段丢弃）已通过 `_provider_error_scalar_preview` 的扩展类型保留关闭，有界、类型正确、不保留容器。
- 新增 helper 符合 CLAUDE.md：完整中文 docstring、模块级私有、显式类型、无魔法值。
- 测试覆盖了所有 claimed 修复场景，能防止回归，非 vacuous。
- 无新增 correctness、security、type、layering 或 test 问题。
- Ready-to-commit（当前未提交状态可提交）。
