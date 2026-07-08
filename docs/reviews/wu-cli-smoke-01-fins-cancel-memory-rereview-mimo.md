# Re-Review — WU-CLI-SMOKE-01 Fins Cancel / Memory

## Scope

- Mode: re-review of accepted findings DS F-1, DS F-3, DS F-5
- Branch: `phase/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-cli-smoke-01-fins-cancel-memory-rereview-mimo.md`
- Included scope: fix artifact `docs/reviews/wu-cli-smoke-01-fins-cancel-memory-review-fix-codex.md`，`dayu/fins/downloaders/sec_downloader.py`，`dayu/fins/pipelines/sec_download_workflow.py`，`dayu/fins/pipelines/cn_download_workflow.py`，`tests/fins/test_sec_downloader.py`，`tests/fins/test_sec_pipeline_download_stream.py`，`tests/fins/test_cn_download_workflow.py`

## Accepted Finding Status

### DS F-1: SEC downloader loop identity 不应只保存 `id(loop)` — **已关闭**

**修复内容**: `_client_loop_identity: int | None` 替换为 `_client_event_loop: asyncio.AbstractEventLoop | None`。比较方式从 `id()` 改为 `is`（object identity）。

**验证**:

- `_refresh_owned_client_for_current_loop()` 保存 `current_loop = asyncio.get_running_loop()` 并用 `self._client_event_loop is current_loop` 比较。`is` 是正确的 object identity 比较，event loop 在其生命周期内是单例，`is` 比 `id()` 更 Pythonic 且语义等价。
- `close()` 正确地将 `_client_event_loop = None`，释放 loop 引用。不存在 loop 引用泄漏：downloader 持有的是 loop 引用而非 loop 内部资源；当 downloader 被 close 或 GC 时引用自然释放。
- 旧 loop 关闭后 `is` 比较仍安全：新 `asyncio.run()` 创建新 loop 对象，`is` 比较为 `False`，触发 client 刷新。旧 loop 关闭不会导致误用，因为 `_refresh_owned_client_for_current_loop` 总是获取当前 running loop。
- 测试 `test_owned_client_refreshes_across_asyncio_run_boundaries` 断言 `downloader._client_event_loop is not first_event_loop`，验证 object identity 变化而非 `id()` 变化。

**结论**: 修复充分，无新 blocker。

### DS F-3: SEC final status 不应在收尾阶段二次调用 `cancel_checker` — **已关闭**

**修复内容**: 新增本地 monotonic `cancelled` 标记。仅在实际命中取消边界并 break，或单 filing 因取消静默停止且没有 terminal filing event 时设置 `cancelled=True`。final result status 使用 `status="cancelled" if cancelled else "ok"`，不再收尾阶段二次读取 `cancel_checker`。

**验证**:

- `run_download_stream_impl` 中 `cancelled = False` 在循环前初始化（行 ~434）。filing 边界检查 `cancel_checker()` 返回 `True` 时设置 `cancelled = True` 并 break（行 ~437）。单 filing 流结束后若 `filing_terminal_seen` 为 `False` 且 `cancel_checker()` 返回 `True`，也设置 `cancelled = True` 并 break（行 ~470）。final result 使用本地 `cancelled`（行 ~549）。
- 测试 `test_download_stream_final_status_does_not_recheck_cancel_token` 使用 `_cancel_on_second_call`：第一次调用返回 `False`（filing 边界），第二次调用返回 `True`（模拟收尾阶段 token 翻转）。由于 `cancelled` 仅在第一次边界检查时设置，而第一次返回 `False`，所以 `cancelled` 保持 `False`，final status 为 `"ok"`。这正确证明了收尾阶段 token 翻转不会误报 cancelled。

**结论**: 修复充分，无新 blocker。

### DS F-5: CN/HK cancel checker 主动抛出的 `CnDownloadCancelledError` 不应被吞掉 — **已关闭**

**修复内容**: `_is_cancel_requested()` 不再 catch `CnDownloadCancelledError` 并返回 `True`。改为在 except block 中用 `isinstance(exc, CnDownloadCancelledError)` 检查后 `raise`，保留原始异常对象与 traceback。

**验证**:

- `_is_cancel_requested()` 的 except block 结构：`except Exception as exc:` → `if isinstance(exc, CnDownloadCancelledError): raise` → `raise RuntimeError(...) from exc`。`CnDownloadCancelledError` 是 `Exception` 子类，进入 except block 后被 `isinstance` 识别并原样 re-raise。
- `_raise_if_cancelled()` 先调用 `_is_cancel_requested(cancel_checker)`，若 checker 主动抛出 `CnDownloadCancelledError`，该异常直接传播到 `_raise_if_cancelled` 的调用方。
- 测试 `test_cn_cancel_checker_preserves_cancel_exception_object` 预构造 `expected = CnDownloadCancelledError("caller cancelled")`，在 cancel checker 中 `raise expected`，调用 `_is_cancel_requested(_raise_cancelled)` 后 `assert exc is expected`。这证明异常对象是同一个，不是被吞掉后重新构造的。

**结论**: 修复充分，无新 blocker。

## Findings

未发现新 blocker。

## Tests Reviewed

- `tests/fins/test_sec_downloader.py::test_owned_client_refreshes_across_asyncio_run_boundaries` — 验证 loop object identity 变化（DS F-1）
- `tests/fins/test_sec_pipeline_download_stream.py::test_download_stream_final_status_does_not_recheck_cancel_token` — 验证 final status 不因收尾阶段 token 翻转误报 cancelled（DS F-3）
- `tests/fins/test_cn_download_workflow.py::test_cn_cancel_checker_preserves_cancel_exception_object` — 验证主动抛出的 CnDownloadCancelledError 是同一个异常对象（DS F-5）
- broader affected tests: `318 passed`
- pyright: `0 errors, 0 warnings, 0 informations`

## Verdict

**PASS**。三个 accepted findings 均已充分修复，无新 blocker 引入。上轮 review 的 PASS 结论（SEC client loop refresh、Fins observation 隔理、SEC/CN/HK 取消检查点、Docling convert 边界、Memory 投影、类型/docstring/README/测试覆盖）仍成立。
