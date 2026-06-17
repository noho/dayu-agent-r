# Code Review (Re-Review)

## Scope

- Mode: current changes
- Branch: `wu-cli-activity-01`
- Base: `main`
- Output file: `docs/reviews/wu-cli-output-channels-slice-c-rereview-mimo-20260617.md`
- Included scope: Slice C fix - dedupe/event_sequence guard、constants Final
- Excluded scope: Slice A/B、Host/Engine 变更

## Reviewed Files

- `dayu/cli/run_view.py` - dedupe/event_sequence guard、constants Final
- `tests/cli/test_interactive_run_view.py` - dedupe/乱序测试

## Findings

未发现实质性问题。

DS code review 发现的 dedupe 缺口已正确修复：

### 1. dedupe/event_sequence guard

**修复正确**：
- `_seen_activity_dedupe_keys: set[str]` 用于去重（`run_view.py:138`）
- `_last_activity_event_sequence: int | None` 用于乱序过滤（`run_view.py:140`）
- `__init__` 中初始化为 `set()` 和 `None`（`run_view.py:166-167`）
- `record_activity()` 入口检查 `dedupe_key`（`run_view.py:218-219`）
- 检查 `event_sequence < _last_activity_event_sequence`（`run_view.py:220-225`）
- 通过后更新 `_seen_activity_dedupe_keys` 和 `_last_activity_event_sequence`（`run_view.py:226-228`）

**与 CliActivityRenderer 一致**：
- 逻辑与 `CliActivityRenderer.record()` 的 dedupe/sequence guard 完全对齐
- 避免 watch replay 或同一事件重复回调造成重复输出

**测试覆盖**：
- `test_run_view_deduplicates_and_filters_out_of_order_activity`（`test_interactive_run_view.py:46-64`）
  - `activity-1` sequence=2：通过
  - `activity-1` sequence=3：重复 dedupe key，过滤
  - `activity-0` sequence=1：乱序，过滤
  - `activity-3` sequence=3：通过
  - 断言 `len(view.activity_lines) == 2`

### 2. constants Final

**修复正确**：
- `_TRANSCRIPT_HEADER: Final[str] = "Interactive transcript"`（`run_view.py:21`）
- `_ACTIVITY_HEADER: Final[str] = "Interactive activity"`（`run_view.py:22`）
- `_EMPTY_VIEW_MESSAGE: Final[str] = "(empty)"`（`run_view.py:23`）
- `_CANCEL_REQUESTED_MESSAGE: Final[str] = "Interactive: cancel requested"`（`run_view.py:24`）
- `_LOCAL_EXIT_AFTER_CANCEL_MESSAGE: Final[str] = "Interactive: cancelling; local process exiting"`（`run_view.py:25`）

**与同类 CLI 模块风格对齐**：`activity.py`、`prompt.py`、`interactive.py` 均使用 `Final[str]`。

## Open Questions

无。

## Residual Risks

- run view buffer 仍按当前 plan 不做有界裁剪；长 session 大 buffer 属于非 full-screen run view 的已知限制。

## Validation

### 已运行（由 fix artifact 确认）

```bash
source .venv/bin/activate && pytest tests/cli/test_interactive_run_view.py tests/cli/test_interactive_command.py tests/cli/test_run_keys.py -q
# 37 passed, 3 warnings

source .venv/bin/activate && pyright dayu/cli/activity.py dayu/cli/run_view.py dayu/cli/commands/interactive.py tests/cli/test_interactive_run_view.py tests/cli/test_interactive_command.py tests/cli/test_run_keys.py
# 0 errors

git diff --check
# clean
```

### 未运行

无。本次 re-review 基于静态代码阅读和 fix artifact 验证记录。

---

Review timestamp: 2026-06-17T23:01:36+08:00
Reviewer: AgentMiMo
