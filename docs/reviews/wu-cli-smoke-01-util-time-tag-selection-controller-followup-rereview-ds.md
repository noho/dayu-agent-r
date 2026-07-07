# Controller Follow-up Re-review — WU-CLI-SMOKE-01 util time + tag-only selection

## Scope

- Mode: current changes (narrow re-review, controller-found follow-up fix only)
- Branch: phase/host-issues-control
- Base: main
- Output file: docs/reviews/wu-cli-smoke-01-util-time-tag-selection-controller-followup-rereview-ds.md
- Included scope:
  - `dayu/tools/utils/provider.py` — `started_at` 改用 `_utc_now()`，`ZoneInfo` 异常转 `ToolFailedOutcome`
  - `tests/tools/test_utils_tools_provider.py` — 新增 `test_get_current_time_returns_failed_outcome_when_timezone_data_missing`
- Excluded scope:
  - `infer.json` tag-only 修复（已在上一轮 fix review 中通过，本轮不重复审查）
  - `test_scene_assets_migration.py` 迁移测试（同上）
- Parallel review coverage: 无（scope 极窄，单 reviewer 逐行走读）

## Verification Results

按 controller 给定的四项验证点逐条走读：

### V1: `get_current_time` 在业务时区加载前使用非 ZoneInfo 时间戳

- **入口**: `build_get_current_time_tool_definition` 内的 `get_current_time` 闭包（`provider.py:105-156`）
- **直接证据**:
  - 第 124 行 `started_at = _utc_now()` 是函数体内第一条可执行语句，早于任何 ZoneInfo 调用。
  - `_utc_now()`（第 265-278 行）实现为 `datetime.now(timezone.utc)`，纯 stdlib `datetime.timezone.utc`，零 IANA 依赖。
  - `_meta()`（第 281-298 行）的 `finished_at` 同样调用 `_utc_now()`，同样不依赖 IANA。
  - 业务时区 `ZoneInfo(timezone)` 在第 141 行才首次出现，此时 `started_at` 已安全捕获。
- **结论**: ✅ 通过。`started_at` 和 `finished_at` 均使用 stdlib UTC，在 ZoneInfo 调用前完成，不受 IANA 数据缺失影响。

### V2: `ZoneInfo(timezone)` 失败返回 `ToolFailedOutcome(error=timezone_load_failed)`，无未捕获异常

- **入口**: `get_current_time` 闭包第 140-148 行
- **直接证据**:
  - 第 140-141 行: `try: tzinfo = ZoneInfo(timezone)`
  - 第 142-148 行: `except ZoneInfoNotFoundError: return _failed_outcome(started_at=started_at, error=_ERROR_TIMEZONE_LOAD_FAILED, ...)`
  - `_ERROR_TIMEZONE_LOAD_FAILED` 在第 48 行定义为 `"timezone_load_failed"`。
  - `except` 子句精确捕获 `ZoneInfoNotFoundError`，不做宽泛 `except Exception`，不吞掉不相关异常。
  - 该 `except` 块以 `return` 结束，不走后续 `datetime.now(tzinfo)` 路径。
- **结论**: ✅ 通过。ZoneInfoNotFoundError 被精确捕获并转为 ToolFailedOutcome，不存在未捕获异常路径。

### V3: 成功路径、unsupported timezone、non-string timezone 行为无回归

- **成功路径**（第 149-156 行）:
  - `_timezone_argument` 返回 `DEFAULT_TIMEZONE` → 通过 `_SUPPORTED_TIMEZONES` 检查 → `ZoneInfo("Asia/Shanghai")` 成功 → `datetime.now(tzinfo)` → `ToolCompletedOutcome`。
  - 与修复前唯一的差异是 `started_at` 来源从 `ZoneInfo` 构造改为 `_utc_now()`，但两者均为 `datetime` 对象且语义一致（工具调用开始时刻），不影响 LLM-facing 行为。
- **Unsupported timezone**（第 133-139 行）:
  - `timezone not in _SUPPORTED_TIMEZONES` → `ToolFailedOutcome(error="invalid_argument")`。
  - 此分支在 ZoneInfo 调用之前，`started_at` 已安全捕获。行为与修复前一致。
- **Non-string timezone**（第 126-132 行）:
  - `_timezone_argument` 返回 `None` → 触发 `timezone is None` 分支 → `ToolFailedOutcome(error="invalid_argument")`。
  - 此分支同样在 ZoneInfo 调用之前。行为与修复前一致。
- **结论**: ✅ 通过。三条路径行为与修复前一致，无回归。

### V4: 测试通过 ToolCallable 路径覆盖 ZoneInfoNotFoundError

- **入口**: `test_get_current_time_returns_failed_outcome_when_timezone_data_missing`（`test_utils_tools_provider.py:142-171`）
- **直接证据**:
  - 第 157 行: `definition = discover_tools(_spec()).definitions[0]` — 通过完整的 provider discovery 路径获取 ToolCallable。
  - 第 159 行: `monkeypatch.setattr(utils_provider, "ZoneInfo", _raise_zoneinfo_not_found)` — 替换 provider 模块内的 `ZoneInfo` 符号。
  - 第 161-166 行: `definition.callable(_call({}), _context())` — 通过 ToolCallable 接口调用，而非直接调用内部函数。
  - 第 168-171 行: 断言 `isinstance(outcome, ToolFailedOutcome)`、`error == "timezone_load_failed"`、message 包含 "无法加载时区"、meta 不为 None。
  - `_raise_zoneinfo_not_found`（第 174-187 行）抛出 `ZoneInfoNotFoundError(key)`，精确模拟 IANA 数据缺失场景。
  - `_call({})` 传入空参数，`_timezone_argument` 返回 `DEFAULT_TIMEZONE`，通过 supported check，在 `ZoneInfo("Asia/Shanghai")` 处触发 monkeypatched 异常——恰好复现 controller 发现的原始问题场景。
- **结论**: ✅ 通过。测试覆盖了完整的 ToolCallable → ZoneInfo 异常 → ToolFailedOutcome 链路，且复现了原始根因场景（缺省时区 + IANA 数据缺失）。

## Findings

未发现实质性问题。四项验证点全部通过。

## Open Questions

无。

## Residual Risk

- 低: `_utc_now()` 依赖系统时钟，极端情况下系统时钟异常可能导致 `started_at` 不准确，但这非本工具职责范围，且不影响功能正确性。
- 低: `_meta()` 的 `finished_at` 和 `get_current_time` 的 `started_at` 分别调用 `_utc_now()`，两者之间存在亚毫秒级时差，但对 LLM-facing 语义无影响。
- 已记录但不在本轮 scope: `get_current_time` 仅支持 `Asia/Shanghai`，如需扩展多时区支持需单独设计。
