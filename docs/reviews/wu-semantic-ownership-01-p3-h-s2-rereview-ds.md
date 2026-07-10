# WU-SEMANTIC-OWNERSHIP-01 P3-H S2 code re-review (AgentDS)

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-H - LLM-facing and UI-copy boundary cleanup`
- Slice: `S2 - Fins direct stream and wait visible-language owner`
- Review type: code-review fix 复审，不扩大 scope
- Inputs:
  - `docs/reviews/wu-semantic-ownership-01-p3-h-s2-code-review-controller-adjudication.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-h-s2-fix-codex.md`
  - 当前 diff 中 S2 相关文件（`wait_adapter.py`, `ingestion_runtime.py`, 对应测试文件）
- Accepted findings to verify: `P3-H-S2-CR-F01`, `P3-H-S2-CR-F02`

## Verification: P3-H-S2-CR-F01 — 已关闭

**要求**: `_failure_message` 不得 fallback 到 `snapshot.message`；failed observation result 缺少 `error_message` 时应 fail fast。

**证据**:

1. `dayu/fins/ingestion/wait_adapter.py:556-566` — `_failure_message` 函数签名改为仅接受 `FinsResultSummary`，不再接受或读取 `FinsObservationSnapshot`。函数体只检查 `result.error_message` 是否为非空字符串，为空或 None 时抛出 `ValueError("failed Fins observation result must contain error_message")`。已不存在任何对 `snapshot.message` 的引用。

2. `dayu/fins/ingestion/wait_adapter.py:564` — 条件 `result.error_message is not None and result.error_message.strip() != ""` 确保空白字符串也被拒绝，防止空白 `error_message` 绕过 fail-fast。

3. `dayu/fins/ingestion/wait_adapter.py:488` — 调用点 `_failed_outcome` 传入 `_failure_message(result)`，其中 `result` 来自 `_required_result(snapshot)`（line 540-541），该函数在 `snapshot.result is None` 时独立抛出 `ValueError`。

4. 上游 `error_message` 真源确认：`ingestion_runtime.py:4937-4966` 的 `_safe_direct_error_message` 在检测到路径、job id、cursor、raw payload、或包含 `"Observation"` 等内部诊断文本时，调用 `direct_failure_message(error_kind=..., fallback_message=None)` 返回业务可读文案；否则用清洗后的 message 作为 fallback。`ingestion_runtime.py:4470-4473` 的 `_emit_direct_cancelled_result` 同样走 `direct_failure_message` 路径。

5. 测试 `test_fins_wait_poll_adapter_rejects_failed_result_without_message`（`test_fins_ingestion_tools.py:1626`）构造 FAILED snapshot，其 `result.error_message=None` 但 `snapshot.message="Observation activation failed."`（包含内部诊断文本），断言 `poll_wait` 抛出 `ValueError("must contain error_message")` — 证明不会 fallback 到 `snapshot.message`。

**结论**: F01 已完全关闭。fail-fast 路径从 `_failure_message` → `_failed_outcome` → `_poll_snapshot_result` → `poll_wait` 逐层传播，最终由 Host poller 按 adapter error 处理，不会静默吞掉缺失 `error_message` 的失败结果。

## Verification: P3-H-S2-CR-F02 — 已关闭

**要求**: 测试必须覆盖 observation terminal `error_message` 不泄漏内部 Observation 诊断文本，包括 cancel before activation、activation failed、producer without result，以及 malformed failed snapshot。

**证据**:

| 场景 | 测试函数 | 文件:行号 | 关键断言 |
|---|---|---|---|
| Cancel before activation | `test_cancel_prepared_observation_prevents_later_activation_submit` | `test_fins_ingestion_runtime.py:2444` | `cancelled.result.error_message == direct_failure_message(error_kind=CANCELLED, fallback_message=None)` + `"Observation" not in cancelled_error_message` |
| Activation failed | `test_unexpected_activation_exception_terminalizes_prepared_observation` | `test_fins_ingestion_runtime.py:2666` | `snapshot.result.error_message == direct_failure_message(error_kind=EXECUTION, fallback_message=None)` + `"Observation" not in activation_error_message` |
| Producer without result | `test_observed_producer_without_result_uses_helper_failure_message` | `test_fins_ingestion_runtime.py:2696` | `snapshot.result.error_message == direct_failure_message(error_kind=EXECUTION, fallback_message=None)` + `"Observation" not in missing_result_error_message` |
| Malformed failed snapshot | `test_fins_wait_poll_adapter_rejects_failed_result_without_message` | `test_fins_ingestion_tools.py:1626` | `pytest.raises(ValueError, match="must contain error_message")` — snapshot.message 含 `"Observation activation failed."` 但 adapter 拒绝 fallback |

四个场景的测试均：
- 直接断言 `error_message` 来源于 `direct_failure_message(...)` helper（`direct_event_text.py:84-120`），确认文本从统一真源派生；
- 显式断言 `"Observation" not in ...` 确保 process-local 诊断文本不进入 LLM 可见的 `error_message`；
- malformed failed snapshot 测试额外覆盖了 wait adapter 侧的 fail-fast 行为。

**结论**: F02 已完全关闭。四个场景覆盖了 PENDING→CANCELLED（cancel before activation）、PENDING→FAILED（activation exception）、stream producer 静默结束（无 RESULT）、以及 wait adapter 收到缺少 `error_message` 的 FAILED snapshot 四条路径，每条路径都验证了内部诊断文本不泄漏到 `error_message`。

## Additional Observations

以下变更出现在当前 diff 中但不在 controller adjudication 的 fix 范围内。按"不扩大 scope"的约束，仅记录观察，不做 full review。

### OBS-01: `_wait_boundary_lost` 变更未在 fix-codex 中记录

- **文件**: `dayu/fins/ingestion/wait_adapter.py:609-627`
- **变更**: `_transient_pending_expired`（硬编码 300s 窗口，基于 `created_at`）→ `_wait_boundary_lost`（基于 Host `deadline_at`/`expires_at` 边界）
- **观察**: 此变更不在 F01/F02 fix 范围内，fix-codex 未提及。新函数在 `deadline_at` 和 `expires_at` 均为 `None` 时返回 `False`（NOT_READY 永不过期），与旧行为（`created_at` 超过 300s 后必定 LOST）语义不同。LOST vs NOT_READY 的判定影响 LLM 可见的 wait outcome message（`_MESSAGE_FINS_OBSERVATION_LOST`），属于 S2 可见语言范围。
- **风险**: 若 Host 对 transient polling 场景未设置 `deadline_at`/`expires_at`，transient unavailable 将永久停留在 NOT_READY 而不收口为 LOST，导致 LLM 无限等待。
- **建议**: 确认 Host wait record 在进入 poll 循环时是否总会设置这两个边界字段中的至少一个；或者在 `_wait_boundary_lost` 中添加对 `poll_claim_expires_at` 的回退，或在两者均为 None 时保留一个有界 fallback。

### OBS-02: `FinsDirectStreamProtocolError` 变更了 direct stream 公共契约

- **文件**: `dayu/fins/ingestion_runtime.py:2699-2732`（`_run_direct_stream`）
- **变更**: 原 `_direct_missing_result_event` 静默生成 FAILURE RESULT → 现抛出 `FinsDirectStreamProtocolError(MISSING_RESULT)` / `FinsDirectStreamProtocolError(DUPLICATE_RESULT)`
- **观察**: 此变更是 public API contract 变更——`_run_direct_stream` 的调用方原本会收到一个合成失败事件，现在会收到异常。虽然异常更精确地表达了 protocol violation，但需确认所有调用方已更新异常处理。此变更不在 F01/F02 fix 范围内。
- **风险**: 低。测试 `test_direct_stream_missing_result_raises_protocol_error` 和 `test_direct_stream_duplicate_result_raises_protocol_error` 已验证新行为。`_run_direct_stream` 是 runtime 内部方法，上游 `run_observed_stream` 等调用方在 `ingestion_runtime.py` 内部，变更已覆盖。

## Findings

未发现实质性问题。

**PASS** — 两个 accepted findings（P3-H-S2-CR-F01、P3-H-S2-CR-F02）已完全关闭。fix 实现了 controller adjudication 的所有四项要求，propagation audit 路径完整，测试覆盖了要求的四个场景。

## Open Questions

- 无。

## Residual Risk

- `_wait_boundary_lost` 变更（OBS-01）未经 controller adjudication，不在本次 fix scope 内。若 Host 对 transient polling 未设置 `deadline_at`/`expires_at`，可能导致 transient unavailable 无限停留 NOT_READY，建议在后续 S2 或独立 work unit 中审查。
- diff 中包含多项超出 F01/F02 fix 范围的 S2 变更（`FinsPreprocessResultStatus`、`FinsUploadPipelineResult`、`not_supported_count` 分离、`DownloadRejectionEntry` 使用等），这些变更未经过 controller adjudication 或独立 code review，存在未被发现的 material finding 风险。建议在后续 work unit 或独立 deepreview 中覆盖。
