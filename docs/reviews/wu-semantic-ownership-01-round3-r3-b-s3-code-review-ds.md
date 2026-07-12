# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-B S3 Code Review — AgentDS

## Scope

- **Review target**: S3 working tree changes（7 files, +527/−27 lines）
- **Plan**: `docs/host/wu-semantic-ownership-01-round3-r3-b-engine-provider-protocol-plan.md`
- **Implementation artifact**: `docs/reviews/wu-semantic-ownership-01-round3-r3-b-s3-implementation-codex.md`
- **Controller validation**: `docs/reviews/wu-semantic-ownership-01-round3-r3-b-s3-controller-validation.md`
- **Design truth**: `docs/engine/design.md`
- **Reviewed docs**: `dayu/engine/README.md`, `tests/README.md`
- **Agent instructions**: `AGENTS.md`
- **Date**: 2026-07-12

---

## Focus 1: ToolParametersSchema Construction-Time Count-Bound Validation

### `_validate_count_bounds()` (tool_schema.py)

```python
_COUNT_BOUND_KEYS: tuple[str, ...] = ("minLength", "maxLength", "minItems", "maxItems")

for bound_name in _COUNT_BOUND_KEYS:
    if bound_name not in field_schema: continue
    bound = field_schema[bound_name]
    if isinstance(bound, bool) or not isinstance(bound, int):
        raise TypeError(f"ToolParametersSchema {path}.{bound_name} must be int")
    if bound < 0:
        raise ValueError(f"ToolParametersSchema {path}.{bound_name} must be non-negative")
```

- 四个 bound keys 精确限定 ✅
- bool → TypeError ✅
- float / string / None → `not isinstance(bound, int)` → TypeError ✅
- 负数 → ValueError ✅
- `0` → passes both checks (isinstance(0, int) True, not bool True, 0 >= 0 True) ✅

### Array items recursion

```python
items_schema = field_schema.get("items")
if isinstance(items_schema, Mapping):
    _validate_count_bounds(items_schema, path=f"{path}.items")
```

- Only recurses when `items` is a Mapping ✅
- Depth: one level (property fields → their `items`) ✅
- No deeper object nesting expansion ✅

### `__post_init__` integration

```python
field_schema = self.properties[property_name]
if isinstance(field_schema, Mapping):
    _validate_count_bounds(field_schema, path=f"properties.{property_name}")
```

- Only validates if field schema is a Mapping （non-Mapping fields like `"string"` skip validation per plan scope）✅

### Not expanded to full JSON Schema engine

- `rg -n 'oneOf|pattern|additionalProperties.*schema|definitions|dependencies|allOf|anyOf|not|format|\$ref' dayu/contracts/tool_schema.py` → **无命中** ✅
- No third-party JSON Schema dependency imported ✅

### Direct verification

```
minLength=0        → PASS (合法)
minLength=-1       → ValueError: "must be non-negative"
minLength=True     → TypeError: "must be int"
minLength=1.5      → TypeError: "must be int"
items.minLength=-1 → ValueError: "must be non-negative"
items.minItems=-1  → ValueError: "must be non-negative"
no bounds          → PASS (无 bound key 正常通过)
non-mapping field  → PASS (非 Mapping field 不校验, 符合 scope)
```

**判定**: ✅ Pass — 四个 bounds 全覆盖，0 合法，未扩展为完整 JSON Schema engine。

---

## Focus 2: Runtime Projection Defense

### `_is_valid_count_bound()` (tool_call_projection.py)

```python
def _is_valid_count_bound(value: JsonValue) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
```

- 与 `ToolParametersSchema` 的校验逻辑一致：非 bool int + 非负 ✅

### `_first_invalid_count_bound()`

```python
for bound_name in _COUNT_BOUND_KEYS:
    if bound_name not in field_schema: continue
    if not _is_valid_count_bound(field_schema[bound_name]):
        return f"{path}{bound_name}"
items_schema = field_schema.get("items")
if isinstance(items_schema, Mapping):
    return _first_invalid_count_bound(items_schema, path=f"{path}items.")
return None
```

- 递归检查 field + items schema ✅
- 返回非法 bound 路径名 ✅

### `_project_field()` 防御集成

```python
invalid_count_bound = _first_invalid_count_bound(field_schema)
if invalid_count_bound is not None:
    return _schema_bound_failure(field_name=field_name, bound_name=invalid_count_bound)
```

- 在字段投影前检查，在 `_project_string` / `_project_array` 的 per-bound 检查之前 ✅
- 返回 `_schema_bound_failure` — 错误归类为 schema bound failure，不伪装成用户参数 error（`_range_failure`）✅
- 路径示例: `minLength` → bound failure；`items.minLength` → 同上 ✅

### Old per-bound 检查同步升级

`_project_string` 和 `_project_array` 的旧检查从:
```python
if isinstance(min_length, bool) or not isinstance(min_length, int):
```
改为:
```python
if not _is_valid_count_bound(min_length):
```
- 覆盖 bool、非 int、负数 — 与 construction-time 一致 ✅
- `_is_valid_count_bound` 是唯一真源 ✅

**判定**: ✅ Pass — mutable defense 完整，不把 schema bug 伪装成用户参数错。

---

## Focus 3: JSON Typed Enum Equality

### `_json_values_equal()` 直接验证（22 cases, all pass）

| Category | Test | Expected | Result |
|----------|------|----------|--------|
| **bool != number** | `True == 1` | False | ✅ |
| | `False == 0.0` | False | ✅ |
| | `True == 0` | False | ✅ |
| **number equivalence** | `1 == 1.0` | True | ✅ |
| | `1.0 == 1` | True | ✅ |
| **nested list** | `[1.0, 'a'] == [1, 'a']` | True | ✅ |
| | `[1] == [1, 2]` | False | ✅ |
| **nested object** | `{'a': 1.0} == {'a': 1}` | True | ✅ |
| | `{'a': 1} == {'b': 1}` | False | ✅ |
| **null** | `None == None` | True | ✅ |
| | `None == 0` | False | ✅ |
| | `None == False` | False | ✅ |
| **string** | `'a' == 'a'` | True | ✅ |
| **bool-bool** | `True == True` | True | ✅ |
| | `True == False` | False | ✅ |
| **NaN/inf** | `NaN == NaN` | False | ✅ |
| | `inf == inf` | False | ✅ |

### Algorithm correctness

```python
if left is None or right is None:
    return left is None and right is None                  # null only == null
if isinstance(left, bool) or isinstance(right, bool):
    return isinstance(left, bool) and isinstance(right, bool) and left is right  # bool ≠ any other type
if isinstance(left, (int, float)) or isinstance(right, (int, float)):
    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        return False                                        # number ≠ non-number
    if isinstance(left, float) and not math.isfinite(left): return False  # NaN/inf never equal
    if isinstance(right, float) and not math.isfinite(right): return False
    return left == right                                    # mathematical equality: 1 == 1.0
```

- bool 分支在 number 分支之前 — 关键：`isinstance(True, int)` 为 True，但 bool check 先执行 ✅
- `math.isfinite()` 拒绝 NaN/inf ✅

### No Python membership

- `rg -n 'value not in enum_value|value in enum_value' dayu/runtime/tool_call_projection.py` → **无命中** ✅
- New code: `any(_json_values_equal(value, candidate) for candidate in enum_value)` ✅

### No string serialization comparison

- `_json_values_equal` 使用类型判断 + 数学值比较，不使用 `str(value)` 或 `json.dumps()` ✅

**判定**: ✅ Pass — JSON type semantics correct, bool/num separation, 1==1.0 equivalence, no serialization/string comparison.

---

## Focus 4: Default 与 Explicit Argument 同一 Enum Path

### `_project_field()` 流程

```python
# 1. _first_invalid_count_bound (defense)
# 2. type check
# 3. _project_string / _project_array / etc
#    → inside: _validate_enum(value, field_schema, field_name)
# 4. default: if value is None and field_schema has "default"
#    → value = default
#    → rerun _project_field(...)  ← 递归回到同一路径
```

Default 路径通过递归调用 `_project_field()` 复用完整的 field projection，包括:
- `_first_invalid_count_bound` defense
- type check
- `_validate_enum` using `_json_values_equal`

显式参数和 default 经过完全相同的 `_validate_enum` → `_json_values_equal` 路径。✅

**判定**: ✅ Pass — default 与显式参数同路径。

---

## Focus 5: Doc/Web/Fins Schema Read-Only Validation

- Controller rerun: `225 passed, 1 skipped` (skip/warnings from existing Edgar deprecation, not from this diff) ✅
- Three consumer test files unmodified per diff ✅
- All existing production tool schemas pass the new `__post_init__` construction contract ✅
- Plan S3 stop condition (existing schema illegal → stop) not triggered ✅

**判定**: ✅ Pass — 只读验证通过，无业务 schema 修改。

---

## Focus 6: Documentation Sync Accuracy

### `docs/engine/design.md`

| Change | Source truth | Accurate |
|--------|-------------|----------|
| AgentRunRequest message union validation | S1 `agent_run.py:119-129` | ✅ |
| AgentMessage role construction validation | S1 `messages.py:46-67` | ✅ |
| EngineEvent discriminator/data mapping | S1 `engine_events.py:547-643` | ✅ |
| Stream/non-stream terminal shape requirement | S2 `_choice_policy.py:339-377` | ✅ |
| Tool-call identity conflict rules | S2 `tool_call_aggregator.py` | ✅ |
| Non-stream string-only arguments | S2 `non_stream_parser.py:528-579` | ✅ |
| First failure candidate | S1 `agent.py:551-565` | ✅ |
| RunnerDone typed commit | S1 `agent.py:543` (runner_done field) | ✅ |
| ToolParametersSchema bounds + enum equality | S3 production code | ✅ |
| Removed duplicate final-answer commit bullet | Previously duplicated entry in §13 | ✅ |

### `dayu/engine/README.md`

- 遵守 `Agent更新约束【必须遵守】`：只写已实现的代码事实 ✅
- 消息构造期 role 校验、EngineEvent discriminator 配对、ToolSchema bounds/enum、finish/tool shape、identity conflict、string-only arguments、first failure candidate — 全部对应已实现代码 ✅
- 未写测试清单（不违反约束）✅

### `tests/README.md`

- 遵守 "只记录当前 tests/ 下已经存在的测试" ✅
- Tool call projection 新增 JSON typed enum、mutable defense 描述 — 对应新增测试 ✅
- Engine contract 新增 discriminator/message union/RunnerDone ordering/identity conflict/terminal parity 描述 — 对应 S1/S2 新增测试 ✅
- OpenAI 新增 native index、identity conflict、string-only arguments、strict terminal parity 描述 — 对应 S2 新增测试 ✅

### Unmodified docs

- `docs/host/design.md`, `dayu/host/README.md` — 未修改 ✅
- 根 `README.md`, `dayu/README.md` — 未修改 ✅
- Fins/Config README — 未修改 ✅

**判定**: ✅ Pass — 三份文档同步准确，符合各自约束。

---

## Focus 7: Scope Violations

| Scan | Result |
|------|--------|
| `Any` / `object` in production code | 无新增 |
| `hasattr(` / `getattr(` in production code | **无命中** |
| `from dayu.host` / `import dayu.host` | **无命中** |
| `loose` / `compat` / `OLD` in production code | **无命中** |
| `oneOf` / `pattern` / `$ref` / full JSON Schema keywords | **无命中** |
| 旧 schema migration / compatibility | **无实现** |
| Doc/Web/Fins production schema modified | **无修改** |
| Host/Agent/Runner production files modified | **无修改** |
| provider capability flag / feature switch | **无新增** |

**判定**: ✅ Pass — 无 scope 违规。

---

## Findings

无。7 个 focus area 全部通过，未发现 material issue。

---

## Plan Review Conclusion

**Pass** — 0 findings, 0 blocking questions.

**Artifact**: `docs/reviews/wu-semantic-ownership-01-round3-r3-b-s3-code-review-ds.md`
