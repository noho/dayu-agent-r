# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-B S3 Code Review — AgentMiMo

## Review Target

`dayu/contracts/tool_schema.py`、`dayu/runtime/tool_call_projection.py` 的 S3 实现改动；`docs/engine/design.md`、`dayu/engine/README.md`、`tests/README.md` 文档同步。

## Design / Control Context

- `docs/engine/design.md` §16 Tool Schema
- `AGENTS.md` 语义所有权与修复边界、编码硬约束

## Review Focus 验证

### 1. ToolParametersSchema construction-time count-bound validation ✅

- `_validate_count_bounds()` 递归检查 `minLength`/`maxLength`/`minItems`/`maxItems`。
- `isinstance(bound, bool) or not isinstance(bound, int)` → `TypeError`；`bound < 0` → `ValueError`；`0` 合法。
- 递归检查 `items` schema（`isinstance(items_schema, Mapping)` 时）。
- `ToolParametersSchema.__post_init__` 遍历 `self.properties`，对每个 Mapping field schema 调用 `_validate_count_bounds`。
- 未扩展为完整 JSON Schema engine：只处理四个 count bounds，不处理 `oneOf`/`pattern`/nested object properties。
- Tests 覆盖：4 bounds × 3 invalid types（bool/float/string）→ TypeError；4 bounds × negative → ValueError；array items string bounds 同矩阵；zero positive。

### 2. Runtime projection defense ✅

- `_first_invalid_count_bound()` 在 `_project_field` 中调用，检查 field schema 和 items schema 的四个 count bounds。
- `_is_valid_count_bound()` 使用 `isinstance(value, int) and not isinstance(value, bool) and value >= 0`。
- 非法 bound 返回 `_schema_bound_failure`（不是 `_range_failure`），不把 schema bug 伪装成用户参数错误。
- `_project_string` 和 `_project_array` 中也使用 `_is_valid_count_bound` 作为二次防御。
- Tests 覆盖：构造后 mutable mapping 篡改为 `-1` → `schema bound` failure；空 array 也不能绕过被篡改的 `items.minLength`。

### 3. JSON typed enum equality ✅

- `_json_values_equal()` 递归实现：
  - `None` → identity check
  - `bool` → 只与同类型同值相等，不与 number 相等
  - `int/float` → 非 bool 有限数按 `left == right` 数学值比较；非有限 float → `False`
  - `str` → 类型 + 值比较
  - `list` → 长度 + 递归元素比较
  - `Mapping` → key 集合 + 递归值比较
- `_validate_enum()` 使用 `any(_json_values_equal(value, candidate) for candidate in enum_value)`，删除 Python `not in`。
- 未使用序列化字符串比较。
- Tests 覆盖：`True` vs `1/1.0`、`False` vs `0/0.0` → rejected；`1` vs `1.0` 双向 → accepted；nested array/object number equivalence 和 boolean/number separation。

### 4. Default 与显式 argument 复用同一 enum path ✅

- `_project_field` 中 default 和显式参数都经过 `_validate_enum()` → `_json_values_equal()`。
- Test `test_default_and_explicit_arguments_share_json_enum_equality`：`enum=[1]` + `default=True`，显式 `True` 和 default `True` 产生相同 failure message。

### 5. Doc/Web/Fins schema 只读验证 ✅

- `tests/tools/test_doc_tools_provider.py`、`tests/tools/web/test_web_tools_provider.py`、`tests/fins/test_fins_ingestion_tools.py` 只作为 read-only validation target 运行。
- 未修改任何业务 schema 或工具实现。
- 全部通过新 construction contract（`225 passed, 1 skipped, 3 warnings`）。

### 6. Documentation sync ✅

**`docs/engine/design.md`**：
- §4：AgentMessage union membership 与固有 role 校验
- §7：stream/non-stream terminal shape、tool-call identity、string-only arguments
- §9：first-accepted failure candidate
- §13：RunnerDone typed commit
- §14：EngineEvent discriminator/data validation
- §16：ToolParametersSchema count bounds 与 runtime typed enum equality
- 删除重复的 final-answer commit bullet

**`dayu/engine/README.md`**：
- AgentMessage 固有 role 构造校验
- EngineEvent discriminator/data 配对
- ToolSchema count bounds 与 runtime enum equality
- Runner protocol normalization、RunnerDone commit、first failure candidate

**`tests/README.md`**：
- contracts/runtime：non-negative bounds、typed enum recursion、mutable defense
- Engine：EngineEvent/message contract、RunnerDone cancellation ordering
- OpenAI：identity-conflict matrix、strict terminal parity、string-only non-stream arguments

### 7. 无新增 compat shim / 旧 schema migration / 完整 JSON Schema draft / 反向依赖 ✅

- Diff 中无 `hasattr`/`getattr`/`Any` 新增（仅有文档文本中的引用）。
- 无 schema migration、provider discovery、完整 JSON Schema draft 或第三方依赖。
- 无反向依赖：`dayu.runtime` 只依赖标准库和 `dayu.contracts`。
- Coverage：`tool_schema.py` 91%、`tool_call_projection.py` 90%。

## Findings

未发现实质性问题。S3 实现正确落实 plan 的 construction-time bound validation、runtime mutable defense、JSON typed enum equality、default/explicit 同路径、Doc/Web/Fins 只读验证和文档同步。

## Open Questions

无。

## Residual Risks

| Risk | Classification | Owner |
| --- | --- | --- |
| `ToolParametersSchema` 不覆盖 `oneOf`/`pattern`/nested object properties | accepted design boundary | 未来如需扩展由独立 schema WU 处理 |
| `_json_values_equal` 对 dict key 顺序不敏感（使用 `set(left) != set(right)`） | 符合 JSON object 语义 | 无需修改 |

## Code Review Conclusion

**status: pass**

S3 实现正确落实 plan 的所有 implementation decisions。`ToolParametersSchema` construction-time count-bound validation 覆盖四个 bounds + array items；runtime projection defense 拦截 mutable mapping 篡改且不伪装为用户错误；JSON typed enum equality 满足 bool ≠ number、finite number equivalence、nested recursion；default/explicit 同路径；Doc/Web/Fins 只读验证通过；文档同步准确。无新增 compat shim、完整 JSON Schema draft 或反向依赖。

**artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-b-s3-code-review-mimo.md`
**findings**: 0
**blocking questions**: 0
