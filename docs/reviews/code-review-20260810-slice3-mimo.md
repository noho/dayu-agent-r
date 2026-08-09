# Slice 3 Code Review — AgentMiMo

## 1. Gate 状态

- Work unit：`WU-CLI-DOWNLOAD-01`。
- Slice：Slice 3，DL-F09 canonical cancellation + DL-F11 conversion。
- Review 时间：2026-08-10。
- 分支：`codex/download-oracle`。
- 基线 HEAD：`54309c59`（plan amendment accepted commit）。
- 实施 artifact：`docs/gateflow/wu-cli-download-01-slice3-implementation-20260810-053604.md`。
- 本 review 不修改产品代码、测试、计划或 implementation artifact。

## 2. 审查范围

### 2.1 修改文件清单

Production（8 files，全部在 Slice 3 allowlist 内）：

| 文件 | 变更类型 |
| --- | --- |
| `dayu/cli/commands/fins.py` | 修改 |
| `dayu/fins/ingestion_runtime.py` | 修改 |
| `dayu/fins/pipelines/download_events.py` | 修改 |
| `dayu/fins/pipelines/cn_docling_process.py` | 新增 |
| `dayu/fins/pipelines/cn_download_protocols.py` | 修改 |
| `dayu/fins/pipelines/cn_download_filing_workflow.py` | 修改 |
| `dayu/fins/pipelines/cn_download_workflow.py` | 修改 |
| `dayu/fins/pipelines/cn_pipeline.py` | 修改 |

Tests（7 files，全部在 base plan / amendment allowlist 内）：

| 文件 | 变更类型 |
| --- | --- |
| `tests/cli/test_fins_commands.py` | 修改 |
| `tests/fins/test_fins_ingestion_runtime.py` | 修改 |
| `tests/fins/test_cn_download_runtime.py` | 修改 |
| `tests/fins/test_cn_download_workflow.py` | 修改 |
| `tests/fins/test_cn_pipeline.py` | 修改 |
| `tests/fins/test_cn_docling_process.py` | 新增 |
| `tests/fins/test_fins_direct_stream.py` | 未修改（已有 baseline） |

未修改 forbidden boundary：`dayu/runtime/interruptible_process.py`、Host/Engine、README、Oracle。

### 2.2 验证执行

| 验证项 | 结果 |
| --- | --- |
| Slice 3 owner tests (245 passed) | PASS |
| 5x repeat deterministic owner set | PASS (5/5) |
| 10x late-provider-failure isolation | PASS (10/10) |
| 基础计划 §9 完整 21-file affected union (1367 passed) | PASS |
| `tests/runtime/test_interruptible_process.py` (37 passed, read-only) | PASS |
| `python -m pyright dayu/ tests/ utils/` | PASS, 0 errors |
| `ruff check <14 changed files>` | PASS |
| `compileall dayu tests` | PASS |
| `git diff --check` | PASS |
| `git diff --exit-code -- dayu/runtime/interruptible_process.py` | PASS |
| Amendment constructor AST gate (16 constructors, 0 legacy keyword) | PASS |
| Typed runner injection AST gate (10 injections) | PASS |
| Filing workflow AST gate (1 awaited runner, 0 to_thread) | PASS |
| Production process AST gate (1 start(), 0 spawn()) | PASS |
| CLI AST gate (0 event_task.cancel, 0 _CliDirectLocalExit) | PASS |

单文件 coverage（245-test data，各自 `--fail-under=80`）：

| Production file | Statement % | Gate |
| --- | ---: | --- |
| `dayu/cli/commands/fins.py` | 85% | PASS |
| `dayu/fins/ingestion_runtime.py` | 90% | PASS |
| `dayu/fins/pipelines/download_events.py` | 100% | PASS |
| `dayu/fins/pipelines/cn_docling_process.py` | 82% | PASS |
| `dayu/fins/pipelines/cn_download_protocols.py` | 100% | PASS |
| `dayu/fins/pipelines/cn_download_filing_workflow.py` | 89% | PASS |
| `dayu/fins/pipelines/cn_download_workflow.py` | 93% | PASS |
| `dayu/fins/pipelines/cn_pipeline.py` | 89% | PASS |

## 3. Adversarial 验证逐项

### 3.1 CLI SIGINT request-and-wait

**结论：PASS。**

`_wait_for_terminal_handling_sigint` 已删除 `_CliDirectLocalExit`、`event_task.cancel()`（SIGINT 路径）与 `render_fins_direct_local_exit_after_cancel`。首次 SIGINT 幂等请求 token 并渲染 cancelling；重复 SIGINT 不重复 request（`cancellation_requested` flag）；始终等待 validated consumer clean exhaustion。exit code 机械取自 canonical terminal `FinsResultSummary.exit_code`。

SIGINT 路径不再调用 `event_task.cancel()`。`_cancel_and_drain_fins_event_task` 中的 `event_task.cancel()`（line 826）仅用于非 SIGINT 异常 cleanup 路径，是正确行为。

`sigint_task.cancel()` + `await asyncio.gather(sigint_task, return_exceptions=True)` 在 finally 中确保 sigint monitor 关闭后 task 被清理。

测试 `test_sigint_requests_token_and_waits_without_job_id` 证明两次 SIGINT 后 `token.request_count == 1`（幂等），最终 result 来自 validated cancelled summary。

### 3.2 Runtime operation-task / non-daemon thread / queue / terminal 原子竞态

**结论：PASS。**

架构：`_run_direct_stream` 创建 `_DirectStreamCancellationState` + `asyncio.Queue`（output_queue）+ `operation_task`。operation task 内创建 `Queue`（sync bounded）、non-daemon `Thread`（`daemon=False`）。operation task 的 finally 先 `thread.join()`，再 `output_queue.put(_DirectStreamProducerDone())`。consumer generator 的 finally 先 `request_consumer_abort()`（若 task 未完成），再 `await asyncio.shield(operation_task)`。

关键不变量：
- Producer thread 是 non-daemon，不会被遗弃。
- `thread.join()` 在 `output_queue.put(ProducerDone)` 之前，consumer 看到 ProducerDone 时 thread 已退出。
- `asyncio.shield(operation_task)` 确保 consumer generator 返回前 operation task 完成。
- Consumer abort 在 shield 前请求，operation task 在 thread join 后向 output_queue 投递 ProducerDone，consumer 的 `output_queue.get()` 收到后 break。

测试覆盖：
- `test_direct_download_very_early_cancel_skips_adapter_and_joins_thread`：pre-cancel 无 adapter 调用、唯一 cancelled RESULT、无遗留 thread。
- `test_direct_cancel_wins_late_provider_failure_and_exhausts_after_join`：token cancel 后 provider failure，唯一 cancelled RESULT，thread `is_alive() is False`。
- `test_direct_consumer_abort_closes_raw_bridge_and_requests_cancellation`：aclose 后 thread `is_alive() is False`，`_terminal_status is None`。
- `test_direct_consumer_task_cancel_waits_for_producer_cleanup_and_thread_join`：task cancel 后 thread `is_alive() is False`，`_terminal_status is None`。

### 3.3 Consumer abort 不创造 RESULT

**结论：PASS。**

`_DirectStreamCancellationState` 设计：
- `request_consumer_abort()` 设置 `_consumer_aborted = True`。
- `claim_terminal()` 在 `_consumer_aborted is True` 时返回 `None`（不写 `_terminal_status`）。
- `_put_direct_queue()` 检查 `is_consumer_aborted()` 而非 `is_cancelled()`，consumer abort 后丢弃所有后续事件。

因此 consumer abort 后：(1) producer 的 `_put_direct_queue` 丢弃事件；(2) 即使 producer 调用 `claim_terminal()`，也返回 None 不创建 RESULT。`_terminal_status` 保持 `None`。

测试 `test_direct_terminal_state_is_atomic_and_ignores_late_cancel_or_result` 直接断言：`aborted_state.claim_terminal(CANCELLED) is None` 且 `aborted_state._terminal_status is None`。

两个 consumer abort 测试（`test_direct_consumer_abort_closes_raw_bridge_and_requests_cancellation` 与 `test_direct_consumer_task_cancel_waits_for_producer_cleanup_and_thread_join`）均断言 `cancellation_states[0].is_consumer_aborted() is True` 且 `_terminal_status is None`。

### 3.4 Docling real start / terminate-kill-close / temp / digest / process-group cleanup

**结论：PASS。**

`ProcessCnDoclingConversionRunner.convert_pdf_to_docling_json` 生命周期：
1. `_validate_stream_name` 校验。
2. Pre-start cancel check。
3. `tempfile.mkdtemp(prefix="dayu-cn-docling-")` 创建 system-temp 唯一目录。
4. Parent 写 input.pdf。
5. `InterruptibleProcessHandle(_CnDoclingProcessTarget(...))` 创建 handle。
6. `handle.start()` 真实 spawn。
7. `_wait_for_conversion` 以 50ms poll 轮询，cancel 时 terminate(2.0s) → kill(1.0s) → close。
8. `handle.close(kill_grace_seconds=1.0)` 无条件执行。
9. `_read_and_validate_output` 校验 child exit status、descriptor type、size int、SHA-256 hex、physical size match、digest match。
10. Post-validation cancel check。
11. Finally：handle close（若未关闭）+ `shutil.rmtree(temp_root)`。
12. Cleanup failure 只记录 warning（不含 path/PDF/provider data），不改写 primary outcome。

`_CnDoclingProcessTarget` 是 frozen dataclass、module-level、可 pickle。Test `test_production_process_target_is_pickleable_and_exports_descriptor` 验证 round-trip。

Process-group cleanup：`test_process_runner_cancel_escalates_terminate_to_kill_and_removes_nested_group` 使用真实 `InterruptibleProcessHandle.start()`、SIGTERM-ignoring nested child、PID marker barrier，断言 `terminate → kill → close` 顺序，both PIDs exit，temp tree 清理。

### 3.5 CONVERSION_COMPLETED 双 checkpoint 与无半发布

**结论：PASS。**

`cn_download_filing_workflow.py` 顺序：
```
_raise_if_cancelled()          # checkpoint 1
yield CONVERSION_COMPLETED
_raise_if_cancelled()          # checkpoint 2
→ publication eligibility → batch
```

Workflow owner 与 `CnPipeline.download_stream` facade owner 均断言 success 顺序：`CONVERSION_STARTED → CONVERSION_COMPLETED → FILING_COMPLETED`。

`test_cn_download_cancel_after_conversion_completed_skips_publication`：在 CONVERSION_COMPLETED yield boundary 设 `cancel_state.cancelled = True`，断言 cancelled terminal、无 FILING_COMPLETED、source meta 不存在（无半发布）。

### 3.6 10 处 typed injection、无 compat

**结论：PASS。**

AST constructor scan：16 个 `CnPipeline`/子类 `super().__init__` constructor，0 个旧 `convert_pdf_to_docling_json=` keyword。

Typed runner injection AST gate：精确 10 个 `docling_conversion_runner=` injection。

Production `cn_download_filing_workflow.py`：精确 1 个 awaited `runner.convert_pdf_to_docling_json(...)`，0 个 `asyncio.to_thread(convert_pdf...)`。

`PdfToDoclingJsonBytes` TypeAlias 已从 `cn_download_protocols.py` 删除，`__all__` 已更新。`convert_pdf_bytes_to_docling_json_bytes` 已从 `cn_pipeline.py` 删除。`cn_pipeline.py` 不再 import `DoclingRuntimeInitializationError` 或 `convert_pdf_bytes_with_docling`。

`rg` 穷举确认 production/test 仅剩 typed Protocol/runner/fake method 及直接 workflow await。

### 3.7 测试确定性 / coverage / allowlist / README gate

**结论：PASS。**

测试使用 `asyncio.Event`/`asyncio.Queue` barrier 和 bounded deadline（`asyncio.wait_for(..., timeout=1.0)`），不使用 `sleep` 猜时序。5x repeat deterministic owner set 与 10x isolation run 均 PASS。

所有修改 production 文件单文件 coverage >= 80%。Test 文件不承担 production 阈值。

所有修改文件在 base plan / amendment allowlist 内。未修改 forbidden boundary。README 未修改（implementation artifact §7 已说明理由）。

## 4. Findings

### F-01：`render_fins_direct_local_exit_after_cancel` 死代码

- Severity：low
- 文件：`dayu/cli/output.py:279, 589`
- Root cause：Slice 3 从 `fins.py` 删除了对 `render_fins_direct_local_exit_after_cancel` 的 import，但 `output.py` 不在 Slice 3 production allowlist 内，函数定义与 `__all__` 导出未同步删除。
- 影响：无功能影响。函数不再被任何 production/test 代码调用，是纯死代码。
- 修复建议：在 documentation closeout 或下一个涉及 `output.py` 的 slice 中删除该函数定义与 `__all__` 条目。不阻塞当前 slice。

### F-02：`_put_direct_queue` 使用 `is_consumer_aborted()` 语义精确但注释可补充

- Severity：informational
- 文件：`dayu/fins/ingestion_runtime.py:4877`
- Root cause：`_put_direct_queue` 检查 `is_consumer_aborted()` 而非 `is_cancelled()`。行为正确：business cancel（`_cancellation_requested`）允许 producer 继续投递直到自行观察 checker 停止；consumer abort（`_consumer_aborted`）立即丢弃事件避免 producer 卡在无人读取的队列。但 `is_cancelled()` 同时覆盖两者，当前检查选择更窄的 predicate，未来维护者可能疑惑为何不用 `is_cancelled()`。
- 影响：无功能影响。当前行为与 plan §5.5"consumer abort 不创造业务 RESULT"一致。
- 修复建议：可选在行内注释中补充"business cancel 允许 producer drain；consumer abort 需立即 fence"的区分理由。不阻塞。

## 5. 结论

**PASS。**

两个 low/informational findings 均不阻塞。实施满足 Slice 3 全部 invariants：
- CLI SIGINT request-and-wait，无 local synthetic terminal。
- Runtime operation task 拥有 non-daemon producer thread，join 后才投递 clean-exhaustion marker。
- Consumer abort 不创造 RESULT（`claim_terminal` 返回 None，`_terminal_status` 保持 None）。
- Docling 真实 `InterruptibleProcessHandle.start()`，terminate→kill→close 有界升级，system-temp cleanup。
- CONVERSION_COMPLETED 双 checkpoint，无半发布。
- 10 处 typed injection 迁移完成，无 compat shim。
- 测试确定性、coverage、allowlist、README gate 均通过。

下一 gate：两路独立 Slice 3 code review 通过后可进入 Slice 4 implementation。
