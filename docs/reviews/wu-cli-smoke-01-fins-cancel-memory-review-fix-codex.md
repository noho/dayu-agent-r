# WU-CLI-SMOKE-01 Fins Cancel / Memory Review Fix

## Accepted Findings

- DS F-1: SEC downloader owned HTTP client 的 loop identity 不应只保存 `id(asyncio.get_running_loop())`。
- DS F-3: SEC download workflow final status 不应在收尾阶段二次读取 `cancel_checker`。
- DS F-5: CN/HK cancel checker 主动抛出的 `CnDownloadCancelledError` 不应被吞掉后重新构造。

## Fixes

- `dayu/fins/downloaders/sec_downloader.py`
  - 将 `_client_loop_identity: int | None` 改为 `_client_event_loop: asyncio.AbstractEventLoop | None`。
  - `_refresh_owned_client_for_current_loop()` 保存当前 event loop 对象，并用 `is` 做 object identity 比较；跨 loop 时刷新 owned `httpx.AsyncClient`，`close()` 清空 loop 引用。
  - 对测试注入的非 `httpx.AsyncClient` fake client 仍保持不刷新，避免测试桩被误替换。

- `dayu/fins/pipelines/sec_download_workflow.py`
  - 新增本地 monotonic `cancelled` 标记。
  - 仅在实际命中取消边界并 break，或单 filing 因取消静默停止且没有 terminal filing event 时设置 `cancelled=True`。
  - final result status 使用本地 `cancelled`，不再收尾阶段二次读取 `cancel_checker`。

- `dayu/fins/pipelines/cn_download_workflow.py`
  - `_is_cancel_requested()` 对 `CnDownloadCancelledError` 原样 `raise`，保留原始异常对象与 traceback。
  - 普通非取消异常仍 `raise RuntimeError(...) from exc`，保留 cause。

## Tests

- 新增/更新：
  - `tests/fins/test_sec_downloader.py::test_owned_client_refreshes_across_asyncio_run_boundaries`：断言 loop 对象 identity 变化，不再只证明 id 变化。
  - `tests/fins/test_sec_pipeline_download_stream.py::test_download_stream_final_status_does_not_recheck_cancel_token`：证明 final status 不会因收尾阶段 token 翻转误报 cancelled。
  - `tests/fins/test_cn_download_workflow.py::test_cn_cancel_checker_preserves_cancel_exception_object`：证明主动抛出的 `CnDownloadCancelledError` 是同一个异常对象。

- Validation:
  - focused pytest: `source .venv/bin/activate && pytest tests/fins/test_sec_downloader.py::test_owned_client_refreshes_across_asyncio_run_boundaries tests/fins/test_sec_pipeline_download_stream.py::test_download_stream_final_status_does_not_recheck_cancel_token tests/fins/test_cn_download_workflow.py::test_cn_cancel_checker_preserves_cancel_exception_object -q`，`3 passed`。
  - affected pytest: `source .venv/bin/activate && pytest tests/fins/test_sec_downloader.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_sec_pipeline_download.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_pipeline.py tests/fins/test_cn_download_runtime.py tests/fins/test_fins_ingestion_runtime.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q`，`318 passed`。
  - pyright: `source .venv/bin/activate && pyright`，`0 errors, 0 warnings, 0 informations`。
  - `git diff --check`: passed。

## Remaining Risk

本次 fix 不改变上一轮 artifact 记录的 residual risk：Fins awaiting 长事务仍是 cooperative cancellation；CN/HK Docling 同步转换在线程运行期间仍不能被强中断。若产品要求转换过程中 hard interrupt，需要后续 controller 决策 process/subprocess isolation + timeout。
