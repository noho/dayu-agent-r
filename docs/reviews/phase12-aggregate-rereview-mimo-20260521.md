# Phase 12 Aggregate Re-Review — MiMo

- **Reviewer**: AgentMiMo
- **Date**: 2026-05-21
- **Branch**: `docs/phase12-design-discussion`
- **Gate**: Phase 12 aggregate re-review
- **Fix artifact**: `docs/reviews/phase12-aggregate-fix-digest-codex-20260521.md`

## Verdict: PASS

P12-AGG-F1 已修复。duplicated canonical JSON digest / normalization 逻辑已正确抽取到
`dayu/runtime/_digest.py` 私有 helper 模块，行为不变，无新增 blocker。

---

## P12-AGG-F1 Status: FIXED

### 修复验证

| 检查项 | 结果 |
|--------|------|
| `tools_discovery.py` 删除本地 `_canonical_json_digest` / `_normalize_json_value` | 已确认：grep 无 `^def _canonical_json_digest` / `^def _normalize_json_value` |
| `scene_prepare.py` 删除本地 `_canonical_json_digest` / `_normalize_json_value` | 已确认：仅保留 `_text_digest`（非本次重复目标） |
| `tools_discovery.py` 改为 `from dayu.runtime._digest import canonical_json_digest, normalize_json_value` | 已确认 |
| `scene_prepare.py` 改为 `from dayu.runtime._digest import canonical_json_digest` | 已确认 |
| `_digest.py` 不导出到 `dayu.runtime.__init__` | 已确认：私有模块，不在 `__all__` |

### 行为不变性

- `canonical_json_digest` 参数保持：`sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`, `allow_nan=False`，前缀 `sha256:`
- `normalize_json_value` 递归规范化逻辑与原实现一致
- 现有 digest stability / sensitivity 测试全部通过（48 focused + 174 full runtime）

### Runtime Import Boundary

`_digest.py` 仅依赖：
- 标准库：`hashlib`, `json`, `collections.abc`, `typing`
- `dayu.contracts.JsonValue`

未导入 `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。
import boundary 测试自动覆盖 `_digest.py`（`_iter_python_files()` 递归扫描）。

### 弱类型守卫

`_digest.py` 所有函数签名使用具体类型（`JsonValue`, `str`, `Mapping`），
弱类型 guard 测试自动覆盖。pyright 0 errors。

---

## Validation Run

```text
$ source .venv/bin/activate && pytest tests/runtime/test_tools_discovery_digest.py tests/runtime/test_tools_discovery.py tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py tests/runtime/test_scene_assets_migration.py -q
48 passed in 0.31s

$ source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q
9 passed in 0.77s

$ source .venv/bin/activate && pytest tests/runtime -q
174 passed in 3.88s

$ source .venv/bin/activate && pyright dayu/runtime tests/runtime
0 errors, 0 warnings, 0 informations

$ git diff --check
clean
```

---

## New Blockers

无。

---

## Residual Observations

1. **`_digest.py` 无直测**：controller fix digest 已说明原因 — 现有 digest stability/sensitivity
   测试 + runtime import boundary + weak typing guard 已覆盖行为不变要求。
   可接受，不阻塞。

2. **`scene_prepare.py` 仅导入 `canonical_json_digest`，未导入 `normalize_json_value`**：
   符合预期 — `scene_prepare` 只用 canonical digest，不需要独立 normalization。
   `tools_discovery` 需要 `normalize_json_value`（用于 schema properties 规范化）。
   两个模块按需导入，无多余依赖。

---

## Scope Confirmation

- P12-AGG-F1：FIXED
- Host public interface：未修改
- Engine / Service / UI / Fins：未触碰
- digest 输出：行为不变
- 新增 blocker：0
