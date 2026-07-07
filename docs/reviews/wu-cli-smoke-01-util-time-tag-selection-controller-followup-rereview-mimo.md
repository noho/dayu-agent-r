# Controller-found follow-up re-review

## Scope

- Mode: current changes (narrow re-review)
- Branch: `phase/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-cli-smoke-01-util-time-tag-selection-controller-followup-rereview-mimo.md`
- Included scope: `dayu/tools/utils/provider.py`, `tests/tools/test_utils_tools_provider.py`
- Excluded scope: 仅复核 controller-found follow-up fix，不涉及 infer.json tag-only 迁移或非字符串 timezone 修复

## Controller-found issue

`started_at` 之前依赖 `ZoneInfo(DEFAULT_TIMEZONE)` 构造，在 IANA timezone 数据缺失时会在元信息构造阶段抛出 `ZoneInfoNotFoundError`，而非返回 `ToolFailedOutcome(error=timezone_load_failed)`。

## Verification

### 1. `get_current_time` 在业务时区加载前使用 UTC 元信息时间戳

**通过。**

- `provider.py:124` — `started_at = _utc_now()` 在函数入口处、任何 `ZoneInfo` 调用之前执行。
- `provider.py:265-278` — `_utc_now()` 使用 `datetime.now(timezone.utc)`，依赖标准库 `timezone.utc`，不依赖 IANA timezone 数据。
- `provider.py:294-298` — `_meta()` 中 `finished_at` 同样通过 `_utc_now()` 获取，全链路不经过 `ZoneInfo`。

### 2. `ZoneInfo(timezone)` 失败返回 `ToolFailedOutcome(error=timezone_load_failed)`，无未捕获异常

**通过。**

- `provider.py:140-148` — `ZoneInfo(timezone)` 调用包裹在 `try/except ZoneInfoNotFoundError` 中。
- 捕获后返回 `ToolFailedOutcome(result=ToolResultFailure(error="timezone_load_failed", ...))`。
- 参数校验（类型检查 → 支持范围检查）在 `ZoneInfo` 调用之前完成（`provider.py:126-139`），非法参数不会到达时区加载路径。

### 3. 成功路径、unsupported timezone、非字符串 timezone 行为未回归

**通过。**

- 成功路径（`provider.py:149-156`）：`datetime.now(tzinfo)` 使用已加载的 `ZoneInfo` 对象，返回 `ToolCompletedOutcome`，行为不变。
- unsupported timezone（`provider.py:133-139`）：在 `_SUPPORTED_TIMEZONES` 检查阶段即返回 `ToolFailedOutcome(error="invalid_argument")`，不触达 `ZoneInfo` 调用。
- non-string timezone（`provider.py:126-132`）：`_timezone_argument` 返回 `None`，立即返回 `ToolFailedOutcome(error="invalid_argument")`。

### 4. 测试覆盖 `ZoneInfoNotFoundError` 经由 ToolCallable 路径

**通过。**

- `test_utils_tools_provider.py:142-171` — `test_get_current_time_returns_failed_outcome_when_timezone_data_missing`：
  - 通过 `monkeypatch.setattr(utils_provider, "ZoneInfo", _raise_zoneinfo_not_found)` 替换 provider 内 `ZoneInfo`。
  - 调用 `definition.callable(_call({}), _context())`，走完整 ToolCallable 路径。
  - 断言返回 `ToolFailedOutcome`，`error == "timezone_load_failed"`，message 包含 `"无法加载时区"`，`meta is not None`。
- 测试运行：`5 passed`，pyright：`0 errors`。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

无。本次 follow-up fix 只解决元信息时间戳对 `ZoneInfo` 的隐式依赖，修复范围精确，测试覆盖完整。
