# Phase 12 Aggregate Re-Review — DS

**Date:** 2026-05-21
**Reviewer:** AgentDS (aggregate re-review worker)
**Gate:** Phase 12 aggregate re-review
**Verdict:** PASS

## Scope

Re-review of P12-AGG-F1 fix: duplicated canonical JSON digest / normalization logic extracted from
`tools_discovery.py` and `scene_prepare.py` into `dayu/runtime/_digest.py`.

## P12-AGG-F1 Status: FIXED

### What Was Changed

- **新增** `dayu/runtime/_digest.py`：私有层中立 helper，提供 `canonical_json_digest` 与 `normalize_json_value`。仅依赖标准库 (`hashlib`, `json`, `collections.abc`, `typing`) 与 `dayu.contracts.JsonValue`。
- **修改** `dayu/runtime/tools_discovery.py`：删除本地 `_canonical_json_digest` 与 `_normalize_json_value`（约 40 行），改为从 `dayu.runtime._digest` import。`hashlib`/`json` import 已随删除移除。
- **修改** `dayu/runtime/scene_prepare.py`：删除本地 `_canonical_json_digest` 与 `_normalize_json_value`（约 40 行），改为从 `dayu.runtime._digest` import `canonical_json_digest`。保留本地 `_text_digest`（fragment 文本摘要不是 canonical JSON helper 抽取目标）。

### Behavior Preservation Confirmed

digest 算法参数完全相同：`sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`, `allow_nan=False`，摘要前缀保持 `sha256:`。

两处旧 `_normalize_json_value` 的唯一语义差异是 `scene_prepare.py` 版本在函数内对 `value.keys()` 做了排序 — 该排序因 `json.dumps(sort_keys=True)` 已覆盖而冗余。统一版本采用 `tools_discovery.py` 的直接迭代模式，行为等价。

既有的 digest 稳定性与敏感性测试全部通过，确认输出不变。

### Runtime Import Boundary Verified

`_digest.py` 由 `test_import_boundary.py` 的 `rglob("*.py")` 自动发现并扫描，禁止层依赖列表 (`dayu.engine`, `dayu.host`, `dayu.service`, `dayu.ui`, `dayu.fins`, `aiohttp`, `requests`, `httpx`) 均未命中。

### Weak Typing Guard Verified

`_digest.py` 使用 `JsonValue` 和 `str` 作为类型注解，无 `Any`、`object`、bare builtin generic。由 `test_weak_typing_guard.py` 自动扫描确认。

## Validation Run (Independent Re-execution)

| Check | Result |
|---|---|
| `pytest tests/runtime/test_tools_discovery_digest.py tests/runtime/test_tools_discovery.py tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py tests/runtime/test_scene_assets_migration.py -q` | **48 passed** in 0.27s |
| `pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q` | **9 passed** in 0.73s |
| `pytest tests/runtime -q` | **174 passed** in 3.93s |
| `pyright dayu/runtime tests/runtime` | **0 errors, 0 warnings, 0 informations** |
| `git diff --check` | clean |

All results match controller-reported validation.

## New Findings

None. No new blockers, no regressions, no import boundary violations, no weak typing violations, no whitespace issues.

## Residual Risk Acknowledgment

`_digest.py` 无专用直测 — 其行为由 `test_tools_discovery_digest.py`（digest 稳定性与敏感性）和 `test_scene_prepare.py`（scene assembly digest）间接覆盖。controller adjudication 已接受此策略，合法 `JsonValue` 的 canonical digest 输出不变性已由 48 个既有测试保护。

## Conclusion

P12-AGG-F1 修复正确：重复的 canonical JSON digest 与 normalize 逻辑已抽取到 `dayu/runtime/_digest.py`，两个原调用点已改为共享该 helper。digest 行为未变（48 个稳定性/敏感性测试通过），runtime import boundary 与 weak typing 约束满足（9 个边界/守卫测试通过），全量 runtime 测试通过（174 passed），pyright 零错误。无新增 blocker。

**Verdict: PASS.** P12-AGG-F1 fixed.
