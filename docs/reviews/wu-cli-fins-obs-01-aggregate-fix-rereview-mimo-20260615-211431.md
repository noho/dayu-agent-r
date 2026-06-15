# Code Review

## 结论：PASS

## Scope

- **Mode**: current changes
- **Branch**: `phaseflow/host-issues-implementation`
- **Base**: `main`
- **Output file**: `docs/reviews/wu-cli-fins-obs-01-aggregate-fix-rereview-mimo-20260615-211431.md`
- **Work unit**: WU-CLI-FINS-OBS-01 aggregate fix re-review
- **Input adjudication**: `docs/reviews/wu-cli-fins-obs-01-aggregate-deepreview-adjudication-20260615-210618.md`
- **Fix artifact**: `docs/reviews/wu-cli-fins-obs-01-aggregate-fix-codex.md`
- **Included scope**:
  - `dayu/fins/ingestion_runtime.py` — AGG-FIX-01（坏 JSONL/invalid row 跳过 + 有界 warning + sequence 单调校验保留）和 AGG-FIX-03（`_LOGGER` Final 注解）
  - `tests/fins/test_fins_ingestion_runtime.py` — AGG-FIX-01 新增两个测试
  - `tests/cli/test_fins_commands.py` — AGG-FIX-02 新增 synthetic terminal fallback CLI 渲染测试
  - `docs/reviews/wu-cli-fins-obs-01-aggregate-fix-codex.md` — fix 记录
  - `docs/host/issues-implementation-control.md` — 控制文档状态更新
  - aggregate review artifacts（`docs/reviews/wu-cli-fins-obs-01-aggregate-deepreview-ds-20260615-205638.md`、`docs/reviews/wu-cli-fins-obs-01-aggregate-deepreview-mimo-20260615-205916.md`）
- **Excluded scope**: S1–S6 历次 review artifact（已作为参考）；deferred/accepted-risk 项（按 adjudication 不在本次 fix 范围内）
- **Parallel review coverage**: 无

## Findings

未发现实质性问题。

## 逐项验证

### AGG-FIX-01：坏 JSONL/invalid row 跳过且 warning 有界不泄 payload/job id/path；valid sequence 仍单调校验；后续 append 能继续

**要求回顾**（adjudication）：
- malformed JSONL lines 或 invalid event rows 不得使该 job 的所有 future `read_job_events(...)` 和 `append_job_event(...)` 调用永久失败
- 跳过无效行并记录有界 warning，包含 job-independent file context 和 line number，不包含 payload values
- 对 valid records 保留 strict monotonic validation
- 新增 Fins runtime 测试证明 corrupted sidecar row 被跳过且后续 append 能分配 next valid sequence

**代码走读**：

1. `_iter_event_records_locked`（`ingestion_runtime.py:1522–1569`）：
   - `json.loads` 失败 → `json.JSONDecodeError` → `_warn_malformed_event_sidecar_row` + `continue` ✅
   - `isinstance(payload, Mapping)` 失败 → `_warn_malformed_event_sidecar_row` + `continue` ✅
   - `_event_record_from_json` 抛 `ValueError`（字段缺失/类型非法/enum 非法）→ `_warn_malformed_event_sidecar_row` + `continue` ✅
   - `record.sequence <= last_sequence` → `raise ValueError("Fins ingestion job event sequence 未递增")` ✅ 严格单调校验保留
   - 正常 record → `records.append(record)` + `last_sequence = record.sequence` ✅

2. `_warn_malformed_event_sidecar_row`（`ingestion_runtime.py:4045–4068`）：
   - 参数只有 `line_number: int` 和 `error_type: str`，均为 job-independent ✅
   - 日志格式：`_JOB_EVENT_SIDECAR_ROW_SKIPPED_LOG_EVENT` + `sidecar_kind=` + `sidecar_suffix=` + `line_number=` + `error_type=` + `error_summary=` ✅
   - 不包含 payload 值、job id、file path ✅
   - `error_summary` 使用固定常量 `_JOB_EVENT_SIDECAR_ROW_SKIPPED_SUMMARY = "malformed_or_invalid_event_row"` ✅

3. 新增常量（`ingestion_runtime.py:104–108`）：`_JOB_EVENT_SIDECAR_KIND`、`_JOB_EVENT_SIDECAR_ROW_SKIPPED_LOG_EVENT`、`_JOB_EVENT_SIDECAR_ROW_SKIPPED_SUMMARY` 均为 `Final[str]` ✅

4. `_last_event_sequence_locked`（`ingestion_runtime.py:1499–1520`）调用 `_iter_event_records_locked` 后对返回结果再做单调性校验——因 `_iter_event_records_locked` 已保证返回 tuple 单调递增，此校验为冗余但不影响正确性。非 blocking finding。

5. `append_job_event`（`ingestion_runtime.py:1380–1426`）通过 `_last_event_sequence_locked` 获取 last sequence 并 +1，跳过的坏行不参与 sequence 分配 ✅

**测试走读**：

- `test_job_event_sidecar_skips_corrupted_rows_and_append_continues`（`test_fins_ingestion_runtime.py`）：
  - 写入两个坏行：一个 malformed JSON（`{"payload":"SHOULD_NOT_APPEAR_IN_WARNING"` 缺闭合），一个 non-object JSON（`["SHOULD_NOT_APPEAR_IN_WARNING"]`）
  - 调用 `append_job_event` → 验证 `appended.sequence == 2`（跳过坏行后按有效事件分配）✅
  - 调用 `read_job_events` → 验证返回 `[1, 2]`（JOB_QUEUED + PROGRESS）✅
  - 断言 warning 包含 `fins.ingestion.job_event_sidecar_row_skipped`、`sidecar_kind=fins_ingestion_job_event`、`sidecar_suffix=.events.jsonl`、`line_number=2`、`line_number=3`、`error_summary=malformed_or_invalid_event_row` ✅
  - 断言 `leaked_payload_value not in caplog.text` ✅ 不泄 payload
  - 断言 `start.job_id not in caplog.text` ✅ 不泄 job id

- `test_job_event_sidecar_still_rejects_non_monotonic_valid_records`（`test_fins_ingestion_runtime.py`）：
  - 写入重复的有效事件行（相同 sequence）
  - 断言 `pytest.raises(ValueError, match="sequence 未递增")` ✅ 单调校验保留

**结论**：AGG-FIX-01 全部要求满足。

### AGG-FIX-02：CLI synthetic terminal fallback 渲染和 exit-code 覆盖有效

**要求回顾**（adjudication）：
- 新增 CLI-level coverage for Service-produced synthetic terminal fallback event
- 测试必须证明 CLI 渲染和 exit-code behavior 在 `event_label="job_terminal_fallback"` 和 `terminal_result` 从 terminal job record fallback path 产出时仍然正确

**代码走读**：

1. `_FakeFinsDirectService`（`test_fins_commands.py:60–90`）：
   - 新增 `use_synthetic_terminal_fallback: bool` 参数 ✅
   - `stream_job_events_until_terminal` 中当 `self.use_synthetic_terminal_fallback` 为 True 时，构造 `FinsDirectJobEvent(event_label=FINS_DIRECT_SYNTHETIC_TERMINAL_EVENT_LABEL, terminal_result=terminal_result)` 并 yield ✅
   - 使用 `_terminal()` helper 构造 `FinsDirectTerminalResult`，与 Service 层合成逻辑一致 ✅

2. `test_live_fins_command_renders_synthetic_terminal_fallback_and_exit_code`（`test_fins_commands.py`）：
   - 设置 `fake_service.use_synthetic_terminal_fallback = True` ✅
   - 断言 `exit_code == FINS_DIRECT_EXIT_SUCCESS` ✅
   - 断言 `"Fins job progress" in captured.out` ✅ progress 事件仍渲染
   - 断言 `"Fins job succeeded" in captured.out` ✅ terminal 渲染为 success
   - 断言 `'event="job_terminal_fallback"' in captured.out` ✅ fallback label 出现在输出中
   - 断言 `"processed_count=1" in captured.out` ✅ result_summary 正确渲染
   - 断言 `captured.err == ""` ✅ 无 stderr 输出

3. CLI 渲染路径验证：`render_fins_direct_event`（`output.py:143–200`）对 synthetic terminal event 走 `terminal_result.status is SUCCEEDED` 分支 → 输出 `Fins job succeeded` + result_summary，与真实 terminal event 路径一致 ✅

**结论**：AGG-FIX-02 全部要求满足。

### AGG-FIX-03：`_LOGGER` Final

**要求回顾**（adjudication）：
- 将 `_LOGGER` 注解改为 `Final[logging.Logger]`
- 运行 pyright

**代码走读**：

- `ingestion_runtime.py:79`：`_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)` ✅
- pyright 验证：`0 errors, 0 warnings, 0 informations` ✅

**结论**：AGG-FIX-03 全部要求满足。

## Deferred / Accepted-Risk 项误修检查

对照 adjudication 中的 deferred/accepted-risk 项，逐项确认未被本次 fix 触及：

| Source finding | Decision | 本次 fix 是否触及 | 证据 |
| --- | --- | --- | --- |
| DS finding 3 `_is_summary_key_allowed` conservative substring matching | accepted-risk | 否 | 无 `output.py` 改动 |
| DS finding 5 synchronous `request_cancel` in SIGINT coroutine | deferred | 否 | 无 `fins.py` 改动 |
| DS finding 6 `claim_running_or_cancelled` repeated RUNNING claim | deferred | 否 | 无 `claim_running_or_cancelled` 改动 |
| DS finding 7 `_last_event_sequence_locked` O(N) append scan | deferred | 否 | `_last_event_sequence_locked` 逻辑未变 |
| DS finding 8 mutable `FINS_DIRECT_SERVICE_FACTORY` test seam | accepted-risk | 否 | 无 `FINS_DIRECT_SERVICE_FACTORY` 改动 |

**结论**：未误修任何 deferred/accepted-risk 项。

## 控制文档一致性

`docs/host/issues-implementation-control.md` 更新：
- 当前状态表：implementation status 更新为 `aggregate accepted fixes implemented; re-review pending` ✅
- 当前状态表：next entry point 更新为 `aggregate fix re-review` ✅
- WU-CLI-FINS-OBS-01 条目：gate artifacts 新增 aggregate deepreview、adjudication、fix、validation 记录 ✅
- WU-CLI-FINS-OBS-01 work unit 表：状态保持 `review`，当前定位更新为 `aggregate accepted fixes implemented; re-review pending` ✅

## 分层/类型/测试检查

- pyright：`0 errors, 0 warnings, 0 informations` ✅
- pytest：`83 passed, 3 warnings`（均为 edgar 第三方 deprecation warning）✅
- `git diff --check`：clean ✅
- 新增代码无反向依赖、无跨层泄漏 ✅
- 新增常量均为 `Final[str]`，符合模块级常量约束 ✅
- 新增测试覆盖 happy path 和 failure path ✅
- 新增 `_warn_malformed_event_sidecar_row` 为模块级私有辅助函数，符合编码约束 ✅

## Open Questions

无。

## Residual Risk

- `_last_event_sequence_locked` 对 `_iter_event_records_locked` 返回结果的单调性校验为冗余（`_iter_event_records_locked` 内部已校验）。非 blocking，可在后续维护中简化。
- AGG-FIX-02 的 CLI test 仅覆盖 SUCCEEDED 终态的 synthetic fallback，未覆盖 FAILED/CANCELLED。但 Service 层已覆盖全部三类终态的合成逻辑，且 CLI 渲染对所有 `FinsDirectTerminalResult` 使用统一路径，风险极低。
