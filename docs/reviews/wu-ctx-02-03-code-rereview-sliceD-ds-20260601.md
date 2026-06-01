# WU-CTX-02 + WU-CTX-03 Slice D focused re-review artifact

## 审查范围

Focused re-review，仅覆盖以下三项：

1. 确认 accepted finding（docstring 缩进）已修复。
2. 确认 fix 未改变 Slice D 行为、状态机、payload、测试或 README。
3. 确认 INFO finding（`_FALLBACK_ACTION_NOT_APPLICABLE` 私有常量重复）按 controller 裁决 deferred。

**前置 artifacts**:
- implementation: `docs/reviews/wu-ctx-02-03-implementation-sliceD-codex-20260601.md`
- MiMo prior review: `docs/reviews/wu-ctx-02-03-code-review-sliceD-mimo-20260601.md`
- DS prior review: `docs/reviews/wu-ctx-02-03-code-review-sliceD-ds-20260601.md`
- fix artifact: `docs/reviews/wu-ctx-02-03-fix-sliceD-codex-20260601.md`

## 验证命令及结果

### 测试

```bash
source .venv/bin/activate
pytest tests/host/test_engine_ingest_mapping.py tests/host/test_dispatch_scheduler.py -q
```

结果: `100 passed in 1.23s`

### 类型检查

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

结果: `0 errors, 0 warnings, 0 informations`

## 逐项确认

### 1. Finding 1 (LOW) — `_fallback_selection_failure_reason` docstring 缩进已修复

**确认通过。**

- **文件**: `dayu/host/engine_ingest.py`
- **位置**: 行 3300-3313，函数 `_fallback_selection_failure_reason`
- **验证**: `:param error:` (行 3305)、`:param compact_failure_reason:` (行 3306)、`:returns:` (行 3307) 现在均使用 **4 空格缩进**，与同模块其他 module-level helper（如 `_single_block_segment_selection` 行 3316）一致。
- **diff 确认**: fix artifact 声明的唯一变更是 docstring `:param` / `:returns` 行从 8 空格缩进调整为 4 空格。当前工作区 diff 中该函数 docstring 与此描述完全吻合。

### 2. Fix 隔离性 — 未改变 Slice D 行为、状态机、payload、测试或 README

**确认通过。**

- **行为**: `_fallback_selection_failure_reason` 的函数体（行 3310-3313）未做任何修改；`_reactive_fallback_decision`（行 3235-3298）中调用该函数的方式未变；fallback 决策逻辑（`build_recent_window_fallback_selection` → `estimate_recent_window_fallback_budget` → `hard_budget_passed` 分支）未变。
- **状态机**: 未触及 `run_transition.py`、状态推进路径或 transition precondition。reactive fallback dispatch（`RECOVERING -> COMPACTION_FAILED -> RUN_STARTED -> ATTEMPT_STARTED`）与 fail closed（`RECOVERING -> COMPACTION_FAILED -> RUN_FAILED`）语义不变。
- **payload**: `CONTEXT_COMPACTION_FAILED` 的 `fallback_action` / `fallback_policy_decision` / `fallback_input_window` / `fallback_input_digest` / `fallback_budget_result` 字段结构和写入路径不变。
- **测试**: `test_engine_ingest_mapping.py` 与 `test_dispatch_scheduler.py` 无修改（diff 仅包含原始 Slice D 实现的测试变更，fix 未追加测试改动）。
- **README**: `dayu/host/README.md` 与 `tests/README.md` 的 diff 仍为原始 Slice D 实现的文档同步，fix 未产生新的 README diff。

### 3. Finding 2 (INFO) — `_FALLBACK_ACTION_NOT_APPLICABLE` 私有常量重复，deferred

**确认 deferred，不要求本 Slice 修复。**

- **现状**: 该常量在 3 个模块各自独立定义：
  - `dayu/host/context_events.py:196`（Slice B/C 既有）
  - `dayu/host/dispatch.py:231`（Slice B/C 既有）
  - `dayu/host/engine_ingest.py:230`（Slice D 新增）
- **评估**: 三者值相同（`"not_applicable"`），互不影响。这是 Slice B/C 即已存在的模式，Slice D 沿用了同一模式。不构成逻辑错误或类型错误。controller 裁决 deferred，本次 re-review 确认该裁决仍然成立。

## 结论

**Passed.**

- Finding 1 已修复（docstring 缩进调整为 4 空格）。
- Fix 未改变 Slice D 行为、状态机、payload、测试或 README。
- Finding 2（`_FALLBACK_ACTION_NOT_APPLICABLE`）按 controller 裁决 deferred。
- 100 tests pass，pyright 0 errors。
- **无新 findings**。
