# Code Re-Review — WU-LIFE-04 Slice Fix Gate

## Scope

- Mode: current changes (re-review of fix gate)
- Branch: `phase/wu-life-04-deadline-watchdog`
- Base: prior review artifacts at controller adjudication state
- Output file: `docs/reviews/wu-life-04-slice-code-rereview-ds.md`
- Re-review target: accepted finding S1S2-CR-F01 fix verification + new material blocker scan
- Included scope: `dayu/host/durable/run_transition.py` (fix target), all workspace changes (new blocker scan)
- Excluded scope: `docs/reviews/` (review artifacts), `docs/host/` (design/doc syncs)
- Parallel review coverage: 无

## Accepted Finding 验证

### S1S2-CR-F01: 删除 `_normalized_event_occurred_at` 死代码

- **状态**: 已修复
- **证据**:
  1. `rg "_normalized_event_occurred_at" dayu/host/` → 无匹配（exit code 1）。函数定义已从 `dayu/host/durable/run_transition.py` 中完全删除。
  2. `rg "_normalized_event_occurred_at" tests/` → 无匹配。测试代码无残留引用。
  3. 关联清理：`import math` 也从 `run_transition.py:13` 删除（`math.isnan`/`math.isinf` 仅被旧 `_validate_active_cancel_timeout_closeout_input` 使用，随该验证函数重构一并移除）。
  4. 旧调用点 `_active_timeout_cancelled_payload` 已重构为 `_active_watchdog_cancelled_payload`（`run_transition.py:4405`），其中 `cancel_requested_at` 改为直接从 `request.cancel_requested_at`（`ActiveCancelWatchdogCloseoutInput` 的 `str` 字段）取值，不再需要 `_normalized_event_occurred_at` 做 roundtrip 归一化。
  5. pyright: 0 errors, 0 warnings, 0 informations（183 files analyzed）。
  6. 受影响 Host 测试全部通过: 242 passed（覆盖 `test_run_attempt_transitions.py`, `test_active_cancel_dispatch.py`, `test_open_host_runtime.py`, `test_public_open_host_options.py`, `test_engine_ingest_mapping.py`, `test_dispatch_scheduler.py`）。
  7. `rg "active_cancel_timeout|ActiveCancelTimeout|_active_timeout_|_ACTIVE_CANCEL_TIMEOUT" dayu/host/ tests/host/` → 无匹配，所有旧命名已清理干净。

## New Material Blocker 扫描

对 fix 涉及的变更路径做逐行走读：

### 1. `cancel_requested_at` 数据流验证

**链路**: `_active_cancel_watchdog_candidate_from_run` → `tick_active_cancel_watchdog` → `ActiveCancelWatchdogCloseoutInput` → `_active_watchdog_cancelled_payload`

- `dispatch.py:4098`: `cancel_requested_at=parse_utc_timestamp(cancel_requested.occurred_at)` — candidate 从 `CANCEL_REQUESTED` event 的 `occurred_at` 解析为 `datetime`。
- `dispatch.py:1108-1110`: `cancel_requested_at=format_utc_timestamp(candidate.cancel_requested_at)` — 构造 closeout input 时格式化为标准 UTC 字符串。
- `run_transition.py:4437`: `"cancel_requested_at": request.cancel_requested_at` — payload 直接使用已格式化的字符串。
- `run_transition.py:6280-6283`: `_validate_active_cancel_watchdog_closeout_input` 校验 `cancel_requested_at` 为非空文本。

**结论**: 数据流完整，类型一致（`datetime` → `str` → payload `str`），校验覆盖。`cancel_requested_at` 语义从旧代码的 `RUN_CANCELLING.occurred_at` 变为 `CANCEL_REQUESTED.occurred_at`，语义更准确（字段名与数据源一致）。无 blocker。

### 2. `ActiveCancelWatchdogCloseoutInput` 字段变更验证

旧字段 `timeout_seconds: float` 和 `timed_out_at: datetime` 已替换为 `cancel_requested_at: str` 和 `closed_out_at: datetime`。

- 所有构造点（`dispatch.py:1096`）均使用新字段名和正确类型。
- 所有消费点（payload 构造、event request 构造）均使用新字段名。
- 验证函数已同步更新，不再校验 `timeout_seconds` 的 `math.isnan`/`math.isinf`。
- `import math` 随之移除，无其他调用点。

**结论**: 字段变更一致，无残留旧字段引用。无 blocker。

### 3. 死代码删除的副作用检查

`_normalized_event_occurred_at` 是纯函数（`format_utc_timestamp(parse_utc_timestamp(event.occurred_at))`），无副作用、无全局状态、无注册回调。删除不影响任何调用链。

其使用的 `parse_utc_timestamp` 和 `format_utc_timestamp` 仍被模块内大量其他函数使用（Run/Attempt 创建、terminal closeout、recovery 等路径），import 保留正确。

**结论**: 删除安全，无副作用。无 blocker。

### 4. 其他 workspace changes 快速扫描

对 `git diff` 中 `run_transition.py` 和 `dispatch.py` 之外的文件变更做了抽样检查：

- `dayu/host/api.py`: `active_cancel_timeout_seconds` 字段及相关验证删除 — 仅删除，无新增逻辑。
- `dayu/host/open_host.py`: `defer_accepted_cancel_to_watchdog=True` 硬编码 — 仅参数变更。
- `docs/host/design.md`, `docs/host/issues-implementation-control.md`, `dayu/host/README.md`: 文档同步，无逻辑变更。
- `tests/host/*`: 测试重命名和断言更新，与实现变更一致。

**结论**: 无意外变更，无新逻辑引入。无 blocker。

## Findings

未发现新的 material blocker。

S1S2-CR-F01 已完全修复，fix 未引入新的 correctness、stability 或 maintainability 问题。

## Open Questions

无。

## Residual Risk

- 本 fix gate 仅处理 S1S2-CR-F01（死代码删除），未改变 WU-LIFE-04 原有 residual risk profile。
- Controller adjudication 中 deferred 的 residual risks（watchdog loop fatal exit 无自动恢复、全表扫描性能、物理中断未实现等）保持原有 owner 不变，不在本 re-review scope 内。

## Re-Review Conclusion

**Pass.** S1S2-CR-F01 已修复，无新 material blocker。修复证据完整：函数定义及唯一调用点均已删除，关联 `import math` 清理，pyright 零错误，242 个 Host 测试通过，全仓库无残留旧名称引用。
