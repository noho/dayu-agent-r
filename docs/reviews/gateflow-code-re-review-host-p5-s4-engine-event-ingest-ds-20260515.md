# Gateflow Code Re-Review: Host P5-S4 EngineEvent Ingest B1 Fix

- **Gate**: Host Phase 5 P5-S4 EngineEvent Ingest B1 blocking fix re-review
- **Reviewer**: AgentDS
- **Artifact**: `docs/reviews/gateflow-code-re-review-host-p5-s4-engine-event-ingest-ds-20260515.md`
- **Date**: 2026-05-15
- **Original review**: `docs/reviews/gateflow-code-review-host-p5-s4-engine-event-ingest-ds-20260515.md`
- **Source finding**: MiMo B1 blocking (`docs/reviews/gateflow-code-review-host-p5-s4-engine-event-ingest-mimo-20260515.md`)
- **Fix artifact**: `docs/reviews/gateflow-fix-host-p5-s4-engine-event-ingest-20260515.md`
- **Implementation artifact**: `docs/reviews/gateflow-implementation-host-p5-s4-engine-event-ingest-20260515.md`

## Scope

- 仅验证 B1 fix：`terminal_closeout=True` 且 `status` 为 `ACCEPTED` 或 `DUPLICATE` 时，`ingest` 和 `_close_worker_lifecycle` 均触发 `wake_queue_promotion` 并返回 `promotion_triggered=True`。
- 检查回归测试是否覆盖 duplicate final_answer 与 duplicate clean EOF promotion retry。
- 检查 fix 是否引入新 blocking 问题。
- 不重审全部 P5-S4。

## B1 Fix 审查

### Fix 机制

引入共享方法 `EngineEventIngestor._with_terminal_promotion_retry()`（`engine_ingest.py:798-820`）：

```python
def _with_terminal_promotion_retry(
    self, result: EngineIngestResult, *, session_id: str
) -> EngineIngestResult:
    if result.terminal_closeout and result.status in (
        EngineIngestStatus.ACCEPTED,
        EngineIngestStatus.DUPLICATE,
    ):
        self._wakeup_port.wake_queue_promotion(session_id)
        return EngineIngestResult(
            status=result.status,
            events=result.events,
            terminal_closeout=True,
            promotion_triggered=True,
            reason=result.reason,
        )
    return result
```

该方法在两处被调用，覆盖所有 terminal closeout 返回路径：

| 调用点 | 文件:行 | 覆盖场景 |
| --- | --- | --- |
| `ingest()` return | `engine_ingest.py:268` | 所有 EngineEvent terminal ingest（final_answer、run_failed、run_cancelled、context_compaction 等） |
| `_close_worker_lifecycle()` return | `engine_ingest.py:793` | clean EOF (`close_clean_eof`) 与 worker lost (`close_worker_lost`) |

### 裁决：Fix 正确

1. **条件正确**：`terminal_closeout=True` 且 `status in (ACCEPTED, DUPLICATE)` — 只有实际完成 terminal closeout（包括幂等重放）才触发 promotion。REJECTED（stale、late、precondition failed）不触发，semantically 正确。

2. **覆盖完整**：所有 terminal closeout 返回路径（normal ingest、worker lifecycle closeout）均经过同一共享方法，不会漏掉任何路径。

3. **Active cancel 路径也覆盖**：`_close_active_cancel` 在 `_ingest_validated` → `_dispatch_terminal_by_event` 中被调用，其返回值流经 `_operation` lambda → `ingest()` → `_with_terminal_promotion_retry`。内部 `promotion_triggered=False` 是哑值，由外层覆写，不构成 bug。

4. **`_wakeup_port` 非空**：`__init__` 中 `_wakeup_port` 默认为 `NoopAdmissionWakeupPort()`（line 232-234），不存在 None 调用风险。

## 回归测试覆盖检查

### 覆盖项

| 测试 | 文件:行 | 覆盖场景 | 验证点 |
| --- | --- | --- | --- |
| `test_duplicate_candidate_returns_existing_result` | `test_engine_ingest_mapping.py:306` | duplicate final_answer promotion retry | `first.promotion_triggered is True`，`second.promotion_triggered is True`，`wakeup.promoted_session_ids == [sid, sid]`，canonical event 仅 1 条 |
| `test_clean_eof_without_terminal_closes_failed` | `test_phase5_local_execution_integration.py:135` | duplicate clean EOF promotion retry | `duplicate.status == DUPLICATE`，`duplicate.promotion_triggered is True`，`wakeup.promoted_session_ids == [sid, sid]` |

两个回归测试均验证：
- 首次调用 promotion_triggered=True
- 重放调用 promotion_triggered=True
- wakeup spy 记录了两次 promotion（证明重放触发重试）

### 未覆盖但无风险项

- **Active cancel DUPLICATE promotion retry**：`_close_active_cancel` 的 DUPLICATE 分支（line 643-649）未单独测试 promotion retry。但该路径与 normal ingest 共享 `_with_terminal_promotion_retry`，且 active cancel 的首次 ACCEPTED case 已在 `test_run_cancelled_after_active_cancel_closes_cancelled` 中测试。风险极低，可在后续补齐。

## 新 Blocking 问题检查

| 检查项 | 结果 |
| --- | --- |
| `_with_terminal_promotion_retry` 条件分支逻辑 | Pass — 只对 ACCEPTED/DUPLICATE + terminal_closeout 触发，语义正确 |
| 所有 terminal 路径均经过该方法 | Pass — ingest() 和 _close_worker_lifecycle() 均调用 |
| REJECTED + terminal_closeout=True 不触发 promotion | Pass — CAS-lost 场景不应触发 promotion |
| 非 terminal 事件不触发 promotion | Pass — preview/projection_signal/diagnostic 的 terminal_closeout=False |
| 引入新的依赖/架构违规 | 无 — 仅添加一个私有方法，无新 import |
| 引入类型问题 | 无 — pyright 0 errors |
| 引入测试回归 | 无 — 10 passed |
| trailing whitespace | 无 — git diff --check pass |

## 验证结果

| 验证项 | 结果 |
| --- | --- |
| `pytest tests/host/test_engine_ingest_mapping.py tests/host/test_phase5_local_execution_integration.py -q` | **10 passed** (0.18s) |
| `python -m pyright dayu/host tests/host` | **0 errors, 0 warnings, 0 informations** |
| `git diff --check` | **passed** |

## 总结

| 类别 | 结果 |
| --- | --- |
| B1 fix 正确性 | **已修复** — `_with_terminal_promotion_retry` 对所有 ACCEPTED/DUPLICATE terminal closeout 触发 promotion retry，覆盖 ingest 和 worker lifecycle 两条路径 |
| 回归测试覆盖 | **充分** — duplicate final_answer（engine_ingest_mapping）和 duplicate clean EOF（integration）均覆盖 |
| 新 blocking 问题 | **0** |
| 新 non-blocking 问题 | **1** (minor): `_close_active_cancel` 内部 DUPLICATE/ACCEPTED 返回值中 `promotion_triggered=False` 是哑值（被外层覆写），可清理但不影响正确性 |
| 验证通过 | **全部** — pytest、pyright、git diff --check |

**Re-review 结论**: B1 已修复，修复正确无副作用，可合入。
