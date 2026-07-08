# Code Re-Review

## Scope

- Mode: re-review of DS F-1 / F-3 / F-5 fix
- Branch: phase/host-issues-control
- Base: previous DS review artifact `docs/reviews/wu-cli-smoke-01-fins-cancel-memory-review-ds.md`
- Output file: docs/reviews/wu-cli-smoke-01-fins-cancel-memory-rereview-ds.md
- Included scope: 3 production files + 3 test files covering DS F-1/F-3/F-5 fixes
- Excluded scope: DS F-2/F-4 (低严重度, not accepted for fix); unchanged files from previous review

## Findings

未发现新问题。

## Accepted Finding Status

### DS F-1 — 已关闭 ✅

**原问题**：`_refresh_owned_client_for_current_loop()` 用 `id(asyncio.get_running_loop())` 作为 loop identity，`id()` 可能碰撞。

**修复内容** (`dayu/fins/downloaders/sec_downloader.py`):
- 字段 `_client_loop_identity: int | None` → `_client_event_loop: asyncio.AbstractEventLoop | None`（行 860）
- 比较方式 `id(asyncio.get_running_loop())` → `asyncio.get_running_loop()` + `is` object identity（行 1644-1648）
- `close()` 清空 `_client_event_loop = None`（行 890）
- 对测试注入的非 `httpx.AsyncClient` fake client 保持不刷新（行 1643 `isinstance` 检查）

**验证**:
- `is` 操作符比较 Python 对象 identity，不依赖内存地址。新 `asyncio.run()` 创建的 event loop 是全新对象，`is` 比较不可能碰撞。
- `_client_event_loop` 只持有最新绑定的 loop 引用；刷新时旧引用被覆盖，不造成引用泄漏。`close()` 显式清空。
- 测试 `test_owned_client_refreshes_across_asyncio_run_boundaries`（`tests/fins/test_sec_downloader.py:926`）从断言 `id()` 变化改为断言 `is` 对象 identity 变化（`assert downloader._client_event_loop is not first_event_loop`），更准确反映修复意图。测试通过。

**结论**: 修复充分，无残留风险。

### DS F-3 — 已关闭 ✅

**原问题**：`run_download_stream_impl` (SEC) 终态 `status="cancelled"` 在收尾阶段二次调用 `cancel_checker()`，存在 TOCTOU。

**修复内容** (`dayu/fins/pipelines/sec_download_workflow.py`):
- 引入本地 monotonic `cancelled: bool = False`（行 435）
- 两处设置 `cancelled = True`：
  - 行 438：filing 循环边界 `cancel_checker()` 返回 `True` → break
  - 行 474：单 filing 流静默结束（无 terminal event）且 `cancel_checker()` 返回 `True` → break
- 行 549：`status="cancelled" if cancelled else "ok"`，只读本地标志

**验证**:
- `cancelled` 是 monotonic 标志：一旦从 `False` 变为 `True` 就不再回退。
- 新增测试 `test_download_stream_final_status_does_not_recheck_cancel_token`（`tests/fins/test_sec_pipeline_download_stream.py:309`）：
  - 使用一个 `_cancel_on_second_call` checker：第一次返回 `False`，第二次返回 `True`
  - 由于 filing 循环只调用一次 checker（返回 `False`），filing 正常完成，`cancelled` 保持 `False`
  - 最终 `final_result["status"] == "ok"` 且 `call_count == 1`
  - 证明 final status 行不再二次调用 `cancel_checker`。测试通过。

**结论**: 修复充分，本地标志语义透明，无残留风险。

### DS F-5 — 已关闭 ✅

**原问题**：`_is_cancel_requested()` 捕获 `CnDownloadCancelledError` 后返回 `True`，再由调用方构造新异常，丢失原始异常对象和 traceback。

**修复内容** (`dayu/fins/pipelines/cn_download_workflow.py`):
- `_is_cancel_requested()` 行 417-420：`except Exception as exc: if isinstance(exc, CnDownloadCancelledError): raise`
  - 对 `CnDownloadCancelledError` 使用 bare `raise`，原样传播原始异常对象和 traceback
  - 对其它异常仍 `raise RuntimeError(...) from exc`，保留 cause chain
- 新增独立函数 `_raise_if_cancelled()`（行 425-454），为 ticker 级阶段（discovery、company meta、candidate list、overwrite clear）提供统一的取消检查和异常抛出，避免各调用点散落 `_is_cancel_requested` + `raise CnDownloadCancelledError` 模式。

**验证**:
- `except Exception as exc: if isinstance(exc, CnDownloadCancelledError): raise` 与 `except CnDownloadCancelledError: raise` 语义等价。`isinstance` 检查正确识别子类。
- 新增测试 `test_cn_cancel_checker_preserves_cancel_exception_object`（`tests/fins/test_cn_download_workflow.py:544`）：
  - 构造预置 `CnDownloadCancelledError("caller cancelled")` 对象
  - `_raise_cancelled` checker 抛出该对象
  - 捕获后 `assert exc is expected` — 同一个 Python 对象
  - 测试通过。

**结论**: 修复充分，异常传播正确，无残留风险。

## Tests Reviewed

| 测试 | 文件 | 覆盖目标 | 结论 |
|---|---|---|---|
| `test_owned_client_refreshes_across_asyncio_run_boundaries` | `tests/fins/test_sec_downloader.py:926` | F-1: loop object identity `is` 判断 | 通过 |
| `test_download_files_stream_cancel_stops_without_failed_event` | `tests/fins/test_sec_downloader.py:733` | SEC 文件循环取消检查 | 通过（上轮已有，本回合回归） |
| `test_download_stream_final_status_does_not_recheck_cancel_token` | `tests/fins/test_sec_pipeline_download_stream.py:309` | F-3: final status 不重读 token | 通过 |
| `test_cn_cancel_checker_preserves_cancel_exception_object` | `tests/fins/test_cn_download_workflow.py:544` | F-5: 异常对象原样传播 | 通过 |
| `test_cn_download_cancel_after_pdf_download_does_not_start_docling` | `tests/fins/test_cn_download_workflow.py:545` | CN/HK PDF 后取消检查 | 通过（上轮已有，本回合回归） |
| `test_cn_download_cancel_after_docling_convert_skips_source_commit` | `tests/fins/test_cn_download_workflow.py:595` | CN/HK Docling 后取消检查 | 通过（上轮已有，本回合回归） |
| `test_abandoned_observation_does_not_pollute_repeat_download_observation` | `tests/fins/test_fins_ingestion_runtime.py:2241` | Fins observation 隔离 | 通过（上轮已有，本回合回归） |
| `test_tool_awaiting_accepted_arguments_project_to_recent_evidence` | `tests/host/test_memory_projection.py:337` | Memory TOOL_AWAITING | 通过（上轮已有，本回合回归） |
| 既有 SEC / CN / Host memory 测试矩阵 | 多个文件 | 回归保护 | 199 passed |

**全部测试**: `199 passed, 3 warnings`（edgar deprecation 仅）。Pyright: `0 errors, 0 warnings, 0 informations`。

## Verdict

**PASS** — DS F-1 / F-3 / F-5 全部关闭，无新 blocker。

### 上轮其它 PASS 结论复核

- **SEC owned AsyncClient 按 event loop 刷新**: 本次修复用 `is` 替换 `id()`，消除了理论碰撞窗口。安全性与上轮结论一致，且更稳健。
- **Fins observation cancel/abandon 第二轮隔离**: 无变更。上轮结论成立。
- **SEC/CN/HK 单 filing 取消检查点**: CN/HK 新增 ticker 级 `_raise_if_cancelled`（discovery → company meta → candidate list → overwrite clear），检查点更密集。上轮结论成立且进一步增强。
- **Docling convert cancel 边界**: 无变更。上轮结论（cooperative checkpoint，文档化 residual risk）成立。
- **Memory TOOL_AWAITING LLM-facing 投影**: 无变更。上轮结论成立。
- **类型/docstring/README/测试**: 本次新增代码有完整中文 docstring，新参数 `cancellation_checker` 类型统一为 `Callable[[], bool] | None`，pyright 零错误。上轮结论成立。

## Residual Risk

与上轮一致，无新增风险：
- CN/HK Docling convert 同步线程内不可强中断（产品级 residual，已文档化）
- SEC `_filter_filings` / SC13 补齐阶段无取消检查（已知限制，非本次修复范围）
- Fins awaiting 长事务仍是 cooperative cancellation（架构设计决策）
