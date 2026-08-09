# `WU-CLI-DOWNLOAD-01` Slice 3 — AgentDS Independent Code Review

## 1. Review 状态

- **Reviewer**: AgentDS（独立，未读取 MiMo 结论）
- **Date**: 2026-08-10
- **Verdict**: **PASS** — 零 correctness/stability finding
- **Baseline HEAD**: `54309c597b71ca0f7ce581500e6272970588dec2`（plan amendment accepted commit）
- **Reviewed diff**: 12 changed files, +1069/-344 lines（全部位于基础计划与 amendment allowlist）
- **Scope**: Slice 3 — DL-F09 canonical cancellation、DL-F11 conversion completion、Docling child process boundary

## 2. 审查方法

按用户指令严格执行：

1. 读取 AGENTS.md、基础计划 §5.5 / Slice 3 / §9、amendment、implementation artifact
2. 审查全部未提交 diff（逐文件、逐 hunk）
3. 运行 owner tests（245 passed）、5 次重复 deterministic set（5/5）、full affected union（1367 passed）、read-only `test_interruptible_process.py`（37 passed）
4. 运行 pyright、ruff check、ruff format --check、compileall、git diff --check
5. 运行 10 项 AST/static gate（constructor scan、runner await scan、process start/spawn scan、CLI cancel scan、storage isolation、runtime isolation、hasattr/getattr scan、production sleep scan、conversion checkpoint scan）
6. 逐文件覆盖率检查（全部 ≥ 80%）
7. Adversarial 验证所有 plan 要求的 invariant、stop condition 与 forbidden boundary

## 3. Adversarial 验证结果

### 3.1 CLI SIGINT request-and-wait 与 late SIGINT race

**验证路径**：

- `_wait_for_terminal_handling_sigint`：0 个 `event_task.cancel()`（AST 精确扫描仅在函数体内），0 个 `_CliDirectLocalExit` 引用（rg 全仓库 0 hit）。首次 SIGINT 幂等 request token/渲染 cancelling，重复 SIGINT 不重复 request，始终 await 同一 event consumer。
- Late SIGINT race：若 event_task 先完成（terminal 已提交），`finally` 内 `sigint_task.cancel()` 为 noop（task 已 done 或 SIGINT 恰好在 event_task 完成后到达），`gather(return_exceptions=True)` 立即返回。CLI 返回 canonical terminal（SUCCESS/FAILURE），不被 late SIGINT 改写。
- CLI 退出码仅取自 canonical terminal summary：`_CliFinsCancellationToken` 的 `request_count` 测试证明重复 SIGINT 不重复 request token，terminal 释放前 wait task 未完成。

**裁决**: 通过。CLI 不再拥有 terminal/timeout/kill/130 合成的任何 owner-level 能力。

### 3.2 Runtime operation task、shield/join/queue clean exhaustion

**验证路径**：

- Operation task 是 `_run_direct_stream_operation`，唯一拥有 `daemon=False` producer thread 与有界 sync queue pump。
- 正常完成：pump 读到 `_DirectStreamProducerDone` → break → `finally`: `thread.join()` → `output_queue.put(_DirectStreamProducerDone())`。
- Consumer abort（`aclose()`）: `finally` 内 `request_consumer_abort()` → `asyncio.shield(operation_task)` → task 内 producer 观察到 checker 停止 → thread join → output queue marker。
- Consumer task cancellation: 同 consumer abort 路径，`CancelledError` 向上传播前 `finally` 等待 cleanup。
- 测试证据：`_ConsumerAbortDownloadAdapter` 保存真实 `Thread` 对象，close/cancel 后直接断言 `is_alive() is False`。`_ConsumerTaskCancelledDownloadAdapter` 在有界轮询中观察 checker，断言 task 只在 producer thread exit 后返回。

**裁决**: 通过。所有路径验证 thread join + clean exhaustion marker + no alive thread。

### 3.3 Terminal precedence、consumer abort no RESULT

**验证路径**：

- `claim_terminal()` 原子 gate：`_lock` 保护，先检查 `_consumer_aborted`（True → return None，不写 `_terminal_status`），再检查 `_terminal_status`（非 None → return None），最后 `_cancellation_requested` 优先 → 写入并返回。
- 单元测试 `test_direct_terminal_state_is_atomic_and_ignores_late_cancel_or_result`：SUCCESS 提交后 cancel 返回 False，第二 terminal 返回 None；cancel 先生效时 terminal 强制为 CANCELLED；consumer abort 后 claim_terminal 返回 None 且 `_terminal_status is None`。
- Consumer abort 测试：`_record_direct_cancellation_states` 通过 monkeypatch `create` 捕获真实 state 对象，close/cancel 后直接断言 `is_consumer_aborted() == True` 与 `_terminal_status is None`。

**裁决**: 通过。business cancel 压过迟到 provider failure（`_CancellationThenFailureDownloadAdapter` 测试：barrier 先 cancel 再释放 provider 异常 → RESULT 为 CANCELLED），consumer abort 不创造 RESULT。

### 3.4 Docling spawn/process-group/terminate-kill-close/temp/digest/pickle/cleanup

**验证路径**：

- Production `ProcessCnDoclingConversionRunner`：调用真实 `InterruptibleProcessHandle.start()`（AST 精确 1 个 `.start()` call，0 个 `.spawn()` call）。
- 取消升级：50ms poll → `terminate(2.0s)` → 必要时 `kill(1.0s)` → 无条件 `close(kill_grace_seconds=1.0s)`。嵌套 process group 测试：外层 target 启动 nested Python child，两者均 ignore SIGTERM；marker barrier 发布实际 PID；runner 返回后用 `os.kill(pid, 0)` 在 5s bounded deadline 内断言不存在。
- Temp：`tempfile.mkdtemp(prefix="dayu-cn-docling-")` 创建 per-run 唯一目录，所有路径（success/failure/cancel）均在 `finally` 内 `shutil.rmtree`；测试通过 monkeypatch 捕获路径并逐个断言 `Path.exists() is False`。Cleanup 异常仅记录 bounded warning（`stage` + `error_type.__name__`），不含路径、PDF 内容或 raw payload。
- Digest：production target `pickle.dumps/loads` round-trip 通过。Queue descriptor 仅含 `size`/`sha256`。
- Size/digest 验证仅在 handle close 后执行：测试 monkeypatch `_read_and_validate_output` 在真实验证入口断言 `calls[-1] == "close"`。

**裁决**: 通过。所有可控路径 child PID 结束、temp tree 清理、producer thread join、no late output。

### 3.5 Conversion completion publication fence

**验证路径**：

- 实际顺序：`child output → handle close → size/digest validation → cancel checkpoint → CONVERSION_COMPLETED → cancel checkpoint → publication eligibility → batch/publication`（AST 确认 `_raise_if_cancelled` 分别在 COMPLETED yield 前后各一次）。
- `test_cn_download_cancel_after_conversion_completed_skips_publication`：consumer 在 `CONVERSION_COMPLETED` yield boundary 后请求取消 → 下一个 cancel checkpoint 返回 cancelled → 无 `FILING_COMPLETED`、source meta/blob 未创建（`FileNotFoundError` 断言）。
- Workflow owner 与 `CnPipeline.download_stream` facade owner 均断言完整 success 事件序列含 `CONVERSION_COMPLETED`。

**裁决**: 通过。completed 后取消阻止 publication；已发布路径完整且与 owner/facade 断言一致。

### 3.6 Typed owner / 无 compatibility

**验证路径**：

- 16 个 `CnPipeline(...)`/子类 `super().__init__` constructor 中 0 个旧 `convert_pdf_to_docling_json=` keyword；精确 10 个 `docling_conversion_runner=` injection。
- `PdfToDoclingJsonBytes`：rg 全仓库 0 hit。
- `asyncio.to_thread(convert_pdf...)`：AST 精确 0 个。
- `convert_pdf_bytes_to_docling_json_bytes`：已从 `cn_pipeline.py` 删除并从 `__all__` 移除。
- 所有 test fake 均实现 `CnDoclingConversionRunner` Protocol 的 `async convert_pdf_to_docling_json`。
- `_TOKEN_TO_PERIOD`：`cn_form_utils.py` 内 0 hit。
- `_CliDirectLocalExit`：全仓库 0 hit。
- `dayu/runtime/interruptible_process.py`：`git diff --exit-code` exit 0。

**裁决**: 通过。无 compatibility shim、re-export、双参数、hasattr/getattr、production sleep/timing hook。

### 3.7 测试是否真实证明计划

**验证路径**：

- `test_process_runner_cancel_escalates_terminate_to_kill_and_removes_nested_group`：使用真实 spawned child + nested Python process + marker barrier + 实际 PID 存活性断言。terminate/kill grace 通过 monkeypatch module constant 缩短，production 代码不增加 timing hook。
- `test_direct_cancel_wins_late_provider_failure_and_exhausts_after_join`：Event barrier 控制 provider entry/release 顺序，保存真实 `Thread` 对象并断言 `is_alive()`。
- `test_direct_consumer_abort_closes_raw_bridge_and_requests_cancellation`：`_record_direct_cancellation_states` 捕获真实 state，`close_started` barrier 证明 `aclose()` 在 producer 未完成时阻塞，`allow_cancellation_check` 释放后 close 完成。
- 所有 process/cancellation 测试使用 deterministic Event/barrier + bounded deadline，无 `time.sleep`/`asyncio.sleep` 猜时序。5 次重复 deterministic set 全部 PASS，late-provider-failure test 10 次独立重复全部 PASS。

**裁决**: 通过。测试直接证明 plan invariant，无 fake 冒充 real、sleep 猜时序或 barrier 泄漏。

### 3.8 Allowlist、README gate、forbidden boundary

**验证路径**：

- 修改文件全部位于基础计划 Slice 3 production/test allowlist 或 amendment 新增的 `tests/fins/test_cn_pipeline.py`。
- `tests/fins/test_cn_pipeline.py` 的 upload test 区域零 diff（rg 确认 upload `CONVERSION_STARTED` 引用为 `UploadFilingEventType`/`UploadMaterialEventType`，不是 `DownloadEventType`）。
- `dayu/runtime/interruptible_process.py`：未修改。
- CLI 未导入 `dayu.fins.storage`（AST 扫描 0 hit）。
- `dayu.runtime` 未导入 fins/host/engine/service/ui（AST 扫描 0 hit）。
- 未修改 README、Oracle、registry、Host、Engine、Service、upload contract。
- 无 commit、push、PR。

**裁决**: 通过。

## 4. Static Validation Summary

| Check | Result |
| --- | --- |
| Owner tests (7 files) | 245 passed, 3 edgar deprecation warnings |
| Deterministic repeat (5 runs) | 5/5 PASS, 170 passed each |
| Full affected union (21 files) | 1367 passed |
| `test_interruptible_process.py` (read-only) | 37 passed |
| pyright (`dayu/ tests/ utils/`) | 0 errors, 0 warnings, 0 informations |
| ruff check (14 changed files) | All checks passed |
| ruff format --check (14 changed files) | 14 files already formatted |
| compileall (`dayu tests`) | PASS |
| `git diff --check` | PASS |
| `git diff --exit-code -- dayu/runtime/interruptible_process.py` | exit 0 |

## 5. Coverage

同一 coverage data（245 owner tests），每个修改 production 文件单独执行 `--fail-under=80`：

| File | Stmts | Cover |
| --- | ---: | ---: |
| `dayu/cli/commands/fins.py` | 448 | 85% |
| `dayu/fins/ingestion_runtime.py` | 1760 | 90% |
| `dayu/fins/pipelines/download_events.py` | 25 | 100% |
| `dayu/fins/pipelines/cn_docling_process.py` | 125 | 82% |
| `dayu/fins/pipelines/cn_download_protocols.py` | 40 | 100% |
| `dayu/fins/pipelines/cn_download_filing_workflow.py` | 235 | 89% |
| `dayu/fins/pipelines/cn_download_workflow.py` | 216 | 93% |
| `dayu/fins/pipelines/cn_pipeline.py` | 381 | 89% |

全部 ≥ 80%。

## 6. AST / Static Gates

| Gate | Result |
| --- | --- |
| CnPipeline constructor scan (16 expected) | 16 constructors, 0 old injection keyword |
| Typed runner injection count | 10 `docling_conversion_runner=` |
| Filing workflow: await runner | 1 await, 0 `asyncio.to_thread(convert_pdf...)` |
| Process: `.start()` call | 1 production `.start()`, 0 `.spawn()` |
| CLI: `_wait_for_terminal_handling_sigint` cancel | 0 `event_task.cancel()` |
| CLI: `_CliDirectLocalExit` | 0 references |
| `cn_form_utils.py`: `_TOKEN_TO_PERIOD` | 0 hits |
| `PdfToDoclingJsonBytes` | 0 hits |
| `dayu.runtime` isolation | 0 upper-layer imports |
| CLI storage isolation | 0 `dayu.fins.storage` imports |
| `hasattr`/`getattr` in new code | 0 hits |
| Production `time.sleep`/`asyncio.sleep` | 0 hits |
| CONVERSION_COMPLETED cancel checkpoints | 2 checkpoints (before + after yield) |
| Logging contact canary | 0 absolute path / PDF content / raw payload |

全部 PASS。

## 7. Findings

**零 finding**。无 correctness、stability、maintainability、semantic ownership drift、过度设计、coverage gap 或 contract violation。

所有 plan §5.5 invariant 均被测试/static 证据直接证明：

- 一次 Ctrl+C → 唯一 canonical cancelled terminal + exit 130
- cancelled/failure/success 无活 child、无 late output
- provider/Docling/storage cleanup 完成 + thread join 在 terminal 放行前
- conversion_started 无 completed 时不得 publication
- completed 后 cancel checkpoint 阻止 publication
- commit 前 cancel → rollback
- consumer abort → no RESULT
- duplicate terminal → no claim
- late SIGINT → no terminal override

## 8. Residual Risks

未引入新 residual。既存 base-plan residual 保持：

- Parent SIGKILL → system-temp 可能残留（不在 workspace 增加 scavenger）
- 非 POSIX 平台 nested process-group 能力不同（capability skip + helper read-only baseline）
- 底层文件系统/网络 I/O 永久不返回（依赖 bounded timeout/checkpoint，CLI 不伪造 timeout terminal）

## 9. 结论

**PASS**。Slice 3 实现符合基础计划 §5.5 与 amendment 的全部 invariant、stop condition 与 forbidden boundary。所有 adversarial 路径（CLI SIGINT race、runtime terminal gate、Docling process escalation、CONVERSION_COMPLETED publication fence、consumer abort、typed injection migration）均有直接测试/static 证据证明正确性。下一合法入口：两路 code review 完成后 aggregate deepreview。
