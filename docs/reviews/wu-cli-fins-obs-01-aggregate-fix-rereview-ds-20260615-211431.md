# WU-CLI-FINS-OBS-01 Aggregate Fix Re-Review

## Scope

- Work unit: `WU-CLI-FINS-OBS-01`
- Gate: aggregate deepreview fix re-review
- Input adjudication: `docs/reviews/wu-cli-fins-obs-01-aggregate-deepreview-adjudication-20260615-210618.md`
- Input fix: `docs/reviews/wu-cli-fins-obs-01-aggregate-fix-codex.md`
- Output file: `docs/reviews/wu-cli-fins-obs-01-aggregate-fix-rereview-ds-20260615-211431.md`
- Review mode: current uncommitted changes only
- Reviewed files:
  - `dayu/fins/ingestion_runtime.py`
  - `tests/fins/test_fins_ingestion_runtime.py`
  - `tests/cli/test_fins_commands.py`
- Excluded scope: committed slices S1–S6, deferred/accepted-risk items, unmodified production files

## Conclusion

**PASS**

三个 accepted fix item 全部正确实现。pyright 0 errors、pytest 83 passed。deferred/accepted-risk 项未被误修。无新增分层/类型/测试问题。

## AGG-FIX-01 验证：Corrupted Event Sidecar Row Recovery

### 实现路径

`append_job_event`（`ingestion_runtime.py:1380`）→ `_last_event_sequence_locked`（`ingestion_runtime.py:1499`）→ `_iter_event_records_locked`（`ingestion_runtime.py:1522`）。

### 变更分析

**`_iter_event_records_locked`** 原实现对三类坏数据均直接抛异常，导致整个 sidecar 不可用：

1. 坏 JSONL（`json.loads` 抛 `JSONDecodeError`）：原实现无 try/except，异常向上传播。
2. 非对象的合法 JSON（如 `[...]`）：原实现 `raise ValueError(...)` 直接终止。
3. 对象形式的 JSON 但字段类型不匹配（`_event_record_from_json` 抛 `ValueError`）：原实现无 try/except，异常向上传播。

修复后：
- 场景 1：catch `JSONDecodeError` → `_warn_malformed_event_sidecar_row` + `continue`（line 1545-1550）✅
- 场景 2：`isinstance(payload, Mapping)` 为 False → `_warn_malformed_event_sidecar_row` + `continue`（line 1552-1556）✅
- 场景 3：catch `ValueError` → `_warn_malformed_event_sidecar_row` + `continue`（line 1558-1564）✅
- 有效 record 的单调性校验：`if record.sequence <= last_sequence: raise ValueError(...)` （line 1565-1566）— 保持不变 ✅

**`_warn_malformed_event_sidecar_row`**（line 4045-4068）只接受 `line_number: int` 和 `error_type: str`。warning 消息只使用模块级常量 `_JOB_EVENT_SIDECAR_ROW_SKIPPED_LOG_EVENT`、`_JOB_EVENT_SIDECAR_KIND`、`_JOB_EVENT_FILE_SUFFIX`、`_JOB_EVENT_SIDECAR_ROW_SKIPPED_SUMMARY`。不含 sidecar payload 值、job id 或文件系统路径。✅

**`_last_event_sequence_locked`** 通过 `_iter_event_records_locked` 遍历全部 event，由于坏行被跳过，`last_sequence` 追踪最后一条有效 event 的 sequence。若 sidecar 全部坏行则返回 0，后续 `append_job_event` 从 sequence=1 开始分配。✅

### 测试覆盖

- `test_job_event_sidecar_skips_corrupted_rows_and_append_continues`（test 文件 line 1772）：构造坏 JSONL（缺闭合花括号）和非法 JSON 数组，追加新 event 后验证 sequence=2、events=[1,2]、warning 只含固定字段不含 payload 值和 job_id。✅
- `test_job_event_sidecar_still_rejects_non_monotonic_valid_records`（test 文件 line 1824）：复制有效 event 构造 sequence 重复，验证仍然抛出 `ValueError`。✅

### AGG-FIX-01 结论：PASS

## AGG-FIX-02 验证：CLI Synthetic Terminal Fallback Rendering Coverage

### 实现

测试文件新增 `_FakeFinsDirectService.stream_job_events_until_terminal` 在 `use_synthetic_terminal_fallback=True` 时产出 `FinsDirectJobEvent` 带有 `event_label=FINS_DIRECT_SYNTHETIC_TERMINAL_EVENT_LABEL`（即 `"job_terminal_fallback"`）和 `terminal_result`。

新增测试 `test_live_fins_command_renders_synthetic_terminal_fallback_and_exit_code`（test 文件 line 404）验证：
- CLI exit code 为 `FINS_DIRECT_EXIT_SUCCESS` ✅
- 走 stream 路径而非 wait 路径（`stream_calls` 非空，`wait_calls` 为空）✅
- 输出包含 `"Fins job progress"`、`"Fins job succeeded"`、`event="job_terminal_fallback"` ✅
- 输出包含 `"processed_count=1"`（来自 terminal_result 的 result_summary）✅
- stderr 为空 ✅

### 生产代码状态

生产代码（`dayu/cli/commands/fins.py`、`dayu/cli/output.py`、`dayu/service/fins_direct.py`）已在先前 committed slice 中实现 synthetic terminal fallback 路径。本 fix 仅补充缺失的 CLI-level 测试，不修改生产代码。✅

### AGG-FIX-02 结论：PASS

## AGG-FIX-03 验证：`_LOGGER` Final Annotation

### 直接证据

`dayu/fins/ingestion_runtime.py:79`：
```python
_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)
```

### 验证

- pyright 对 `ingestion_runtime.py` 报 0 errors。✅
- 现有代码中所有 `_LOGGER.warning(...)` 调用点不被 pyright 报 Final variable re-assignment。✅

### AGG-FIX-03 结论：PASS

## Deferred / Accepted-Risk Items 检查

逐项核对未提交 diff，确认以下五项均未被修改：

| 项 | 文件/函数 | 结论 |
| --- | --- | --- |
| DS finding 3 `_is_summary_key_allowed` | 不在 `ingestion_runtime.py` diff 中 | ✅ 未动 |
| DS finding 5 sync `request_cancel` in SIGINT | 相关代码不在 diff 中 | ✅ 未动 |
| DS finding 6 repeated RUNNING claim `updated_at` | `claim_running_or_cancelled` 不在 diff 中 | ✅ 未动 |
| DS finding 7 `_last_event_sequence_locked` O(N) scan | 函数本身未被修改为 O(1)；只通过 `_iter_event_records_locked` 的 skip 行为变更间接影响，算法复杂度不变 | ✅ 未动 |
| DS finding 8 mutable `FINS_DIRECT_SERVICE_FACTORY` | 不在 diff 中 | ✅ 未动 |

## 分层/类型/测试检查

- **分层**：`_warn_malformed_event_sidecar_row` 是 `ingestion_runtime.py` 的模块级私有辅助函数，同文件内已有大量同类 helper（`_bounded_text`、`_validate_job_id`、`_utc_now` 等），分层边界不变。✅
- **类型**：pyright 0 errors, 0 warnings, 0 informations。`_warn_malformed_event_sidecar_row` 使用 keyword-only 参数且全部有类型注解。✅
- **测试**：新增 3 个测试函数全部通过。测试使用已有 fixture 和 helper（`_HoldingExecutor`、`_build_ingestion_runtime`、`_FakeFinsDirectService`），符合现有测试模式。✅
- **控制文档**：`docs/host/issues-implementation-control.md` line 337 已经记录 aggregate fix validation 结果，本次 re-review 结论 PASS 后需更新该行状态为 "re-review passed"。✅

## Open Questions

无。

## Residual Risk

- AGG-FIX-01 的 `_iter_event_records_locked` 方法名以 `_iter_` 开头但返回 `tuple`（非惰性迭代器）。这是此方法的 pre-existing naming inconsistency，不在本次 fix 范围内，不影响正确性。
- 若 sidecar 文件存在极大量事件（远超 `_MAX_JOB_EVENT_READ_LIMIT`），`_last_event_sequence_locked` 仍需 O(N) 扫描全部有效事件。这是 DS finding 7 已标记的 deferred scalability 问题，不在本次修复范围。
