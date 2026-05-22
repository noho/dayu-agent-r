# Re-Review — P12-S2-F1

## Scope

- Mode: current changes (fix-only re-review)
- Branch: `docs/phase12-design-discussion`
- Base: `main`
- Accepted finding: P12-S2-F1 — Mapping keys in digest canonicalization must fail fast unless strings
- Controller adjudication: `docs/reviews/phase12-slice2-code-review-controller-adjudication-20260521.md`
- Output file: `docs/reviews/phase12-slice2-rereview-mimo-20260521.md`

## Verdict

PASS.

## P12-S2-F1 Fixed

已修复。

**Production code change** (`dayu/runtime/tools_discovery.py:568`):

`_normalize_json_value` 的 `Mapping` 分支新增运行时 key 类型校验：

```python
for key, item in value.items():
    if not isinstance(key, str):
        raise TypeError("JsonValue object key must be str")
    result[key] = _normalize_json_value(item)
```

在递归规范化阶段、`json.dumps` 之前拦截非字符串 key，避免 canonical digest 序列化静默转义 malformed JSON object key。

**Test change** (`tests/runtime/test_tools_discovery_digest.py:306-335`):

新增 `test_schema_mapping_with_non_string_key_is_rejected`，通过 `cast(Mapping[str, JsonValue], {1: {"type": "string"}})` 注入带整数 key 的 malformed `properties`，断言 `TypeError` 在 digest 生成路径上快速失败，匹配消息 `"JsonValue object key must be str"`。

## New Blocking Findings

无。

Fix 范围精确：只在 digest canonicalization 的 Mapping 消费边界添加 key 类型校验，未扩大 scope 到完整 JSON Schema runtime validator，与 controller 裁决一致。原有 35 个 tests 全部通过，新增 1 个 focused test，总 36 passed。

## Validation Commands & Results

```text
source .venv/bin/activate && pytest tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py tests/host/test_tooling_options.py tests/host/test_package_exports.py -q
....................................                                     [100%]
36 passed in 0.71s
```

```text
source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q
......                                                                   [100%]
6 passed in 0.60s
```

```text
source .venv/bin/activate && python -m pyright dayu/contracts dayu/runtime dayu/host tests/runtime tests/host
0 errors, 0 warnings, 0 informations
```

```text
source .venv/bin/activate && git diff --check
(clean)
```

## Final Blocking Findings Count

0
