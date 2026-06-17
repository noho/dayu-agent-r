# Code Review — Slice C Re-review (Dedupe/Sequence Guard Fix)

## Scope

- Mode: current changes (Slice C fix)
- Branch: `wu-cli-activity-01`
- Output file: `docs/reviews/wu-cli-output-channels-slice-c-rereview-ds-20260617.md`
- Included scope:
  - `dayu/cli/run_view.py` — `record_activity` 去重/乱序防护 + `Final[str]` 常量
  - `tests/cli/test_interactive_run_view.py` — 新增 dedup/乱序过滤测试
- Reference: `docs/reviews/wu-cli-output-channels-slice-c-code-review-ds-20260617.md` 的 Finding 1
- Fix doc: `docs/reviews/wu-cli-output-channels-slice-c-fix-20260617.md`

## Fix verification

### Finding 1 修复: `record_activity` 缺少 dedupe 防护 — 已修复

**变更** (`run_view.py:139-140,166-167,216-228`):

```python
# 新增字段
_seen_activity_dedupe_keys: set[str]
_last_activity_event_sequence: int | None

# __init__ 初始化
self._seen_activity_dedupe_keys = set()
self._last_activity_event_sequence = None

# record_activity 入口防护
if activity.dedupe_key in self._seen_activity_dedupe_keys:
    return
if (
    activity.event_sequence is not None
    and self._last_activity_event_sequence is not None
    and activity.event_sequence < self._last_activity_event_sequence
):
    return
self._seen_activity_dedupe_keys.add(activity.dedupe_key)
if activity.event_sequence is not None:
    self._last_activity_event_sequence = activity.event_sequence
```

逻辑与 `CliActivityRenderer.record` (`activity.py:100-112`) 一致：
1. `dedupe_key` 已见过 → 跳过
2. `event_sequence` 小于已观察最大值 → 跳过（乱序）
3. 通过后记录 `dedupe_key` 并更新 `event_sequence` 上界

**测试** (`test_interactive_run_view.py:46-65`):

```
输入序列:
  1. dedupe_key="activity-1", event_sequence=2  → 接受 (首次)
  2. dedupe_key="activity-1", event_sequence=3  → 拒绝 (重复 dedupe_key)
  3. dedupe_key="activity-0", event_sequence=1  → 拒绝 (乱序, 1 < last_seq=2)
  4. dedupe_key="activity-3", event_sequence=3  → 接受 (新 key, seq=3 >= last_seq=2)
结果: len(view.activity_lines) == 2
```

覆盖了重复 dedupe_key 拒绝和乱序 event_sequence 拒绝两种场景。✅

### `Final[str]` 常量 — 已修复

`run_view.py:21-25` 所有模块级字符串常量从 `str` 改为 `Final[str]`，与 `activity.py` 风格一致。✅

## AGENTS 约束

| 约束 | 状态 |
|---|---|
| 新增字段有类型注解 | ✅ `set[str]`、`int \| None` |
| 新增测试有中文 docstring | ✅ |
| pyright | ✅ `0 errors` |

## Verification

```
source .venv/bin/activate && pytest tests/cli/test_interactive_run_view.py tests/cli/test_interactive_command.py tests/cli/test_run_keys.py -q
→ 37 passed, 3 warnings

source .venv/bin/activate && python -m pyright dayu/cli/run_view.py tests/cli/test_interactive_run_view.py
→ 0 errors, 0 warnings, 0 informations
```

## Residual Risk

- 前次 review 标记的 buffer 无界增长、非 full-screen 限制不变——这些是 plan 已接受的设计限制。
- `_seen_activity_dedupe_keys` set 在整个 session 生命周期累积所有 activity dedupe keys，对长 session 内存有微增。与 `CliActivityRenderer._seen_dedupe_keys` 行为一致。

## Conclusion

Finding 1 已精确修复，`record_activity` 的 dedupe 和乱序过滤逻辑与 `CliActivityRenderer.record` 对齐。无新增问题。
