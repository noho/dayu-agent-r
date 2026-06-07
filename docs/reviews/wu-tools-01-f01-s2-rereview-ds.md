# WU-TOOLS-01-F01 Slice S2 Re-Review

## Gate Metadata

- Gate: re-review gate (fix verification only).
- Work unit: `WU-TOOLS-01-F01`.
- Slice: `S2 - Preprocess / Process Runtime Pipeline`.
- Branch: `host-wu-tools-01-f01`.
- Scope guard: 只复核 controller accepted findings 的修复，禁止改 production/test/README/control doc，禁止 fix，禁止 commit/push/PR，禁止进入后续 gate。
- Inputs:
  - `docs/reviews/wu-tools-01-f01-s2-code-review-controller-adjudication.md` — accepted findings
  - `docs/reviews/wu-tools-01-f01-s2-fix-codex.md` — fix artifact
  - `docs/reviews/wu-tools-01-f01-s2-code-review-ds.md` — previous review
  - `dayu/fins/ingestion_runtime.py`
  - `tests/fins/test_fins_ingestion_runtime.py`

## Validation Executed

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py -q`
  - 结果: **31 passed**, 3 warnings (edgartools deprecation, 非本 slice 引入)。
- `source .venv/bin/activate && python -m pyright dayu/fins/ingestion_runtime.py dayu/fins/service_runtime.py tests/fins/test_fins_ingestion_runtime.py`
  - 结果: **0 errors, 0 warnings, 0 informations**。

## Accepted Findings Verification

### F01-S2-001 — fixed

- **Controller requirement**: `_MAX_PREPROCESS_DOCUMENTS` 检查必须移到 deleted/ingest_complete/form_types 过滤后的实际工作集；补充 regression test。
- **Evidence (production code)**: `dayu/fins/ingestion_runtime.py:1047`
  - 过滤循环（lines 1034-1044）先对 `selected_ids` 逐项调用 `get_source_meta`，按 `is_deleted`、`ingest_complete`、`form_types` 过滤到 `filtered_ids`。
  - 上限检查 `if len(filtered_ids) > _MAX_PREPROCESS_DOCUMENTS` 在 line 1047，位于过滤循环之后、`return tuple(filtered_ids)` 之前。
  - 旧位置（过滤前的 `len(selected_ids)` 检查）已移除，确认不再存在。
- **Evidence (test)**: `tests/fins/test_fins_ingestion_runtime.py:367-389` — `test_start_preprocess_whole_ticker_applies_limit_after_form_filter`
  - Fixture 创建 1 个 10-K 文档 + 51 个 10-Q 文档（总数 52 > `_MAX_PREPROCESS_DOCUMENTS`）。
  - 请求使用 whole-ticker + `form_types=("10-K",)`。
  - 断言 job `SUCCEEDED`、`selected_count == 1`、`processed_count == 1`、`processed_document_ids == ["aapl-2024-10k"]`。
  - 证明上限作用于过滤后集合，不再错误拒绝合法请求。
- **Status**: fixed。

### F01-S2-002 — fixed

- **Controller requirement**: `_save_failed_from_exception` 在二次 job-store 失败时必须写 bounded diagnostic log，保持 non-throwing，补充 focused test。
- **Evidence (production code)**: `dayu/fins/ingestion_runtime.py:1247-1256`
  - 外层 `try` 块仍尝试 `read_job` + `_save_failed`（lines 1242-1246）。
  - `except Exception as terminal_exc:` 捕获二次失败后，通过 `_LOGGER.warning` 输出结构化 diagnostic（lines 1248-1255）：
    - event name: `fins.ingestion.failed_terminalization_failed`
    - `job_id=%s` — job ID
    - `error_type=%s` — 二次异常类型
    - `original_error_type=%s` — 原始异常类型
    - `exc_info=True` — traceback via logger exception info，不进入 job record payload
  - `return` 后方法退出，不抛出（line 1256）。
- **Evidence (test)**: `tests/fins/test_fins_ingestion_runtime.py:485-525` — `test_save_failed_from_exception_logs_secondary_job_store_failure`
  - Monkeypatch `FsFinsIngestionJobStore.save_job` 抛出 `OSError`。
  - 直接调用 `_save_failed_from_exception` 传入 `RuntimeError("primary failure")` 作为原始异常。
  - 断言 log 包含 `fins.ingestion.failed_terminalization_failed`、`job_id=`、`error_type=OSError`、`original_error_type=RuntimeError`。
  - 二次异常不传播（调用不 crash）——隐式验证。
- **Status**: fixed。

## New Findings

None.

## README Sync

按 CLAUDE.md 触发规则检查 `dayu/fins/README.md` 和 `tests/README.md`：
- `dayu/fins/ingestion_runtime.py` 变更：上限检查位置调整（内部 correctness fix）、diagnostic logging 追加（内部 observability 增强）。均不改变 Fins README 中已记录的 stable runtime interface、preprocess pipeline 路径、job store 位置或 download 状态说明。
- `tests/fins/test_fins_ingestion_runtime.py` 变更：新增 2 个 focused test。`tests/README.md` 的测试分层和运行方式说明无需更新。
- 确认无需 README 更新。

## Residual Risk

- **get_source_meta N+1 调用**: `_MAX_PREPROCESS_DOCUMENTS` 的上限检查现在位于过滤循环之后，意味着超限场景下需要先对全集（可能数百文档）调用 `get_source_meta` 才会触发拒绝。这是 F01-S2-001 原始 review 已识别的 I/O 成本 trade-off——当前 `_MAX_PREPROCESS_DOCUMENTS=50` 且 plan S2 边界为 bounded selection，实际冲击有限。若后续上限放宽或超大规模 ticker 场景出现，可考虑 early bail-out（如先做廉价过滤再逐项 `get_source_meta`）。
- **`_save_failed_from_exception` 仍为 best-effort**: 若 `read_job` 本身就失败（job store 完全不可用），diagnostic log 仍会输出，但终态 record 无法写入。这是 by-design risk，controller adjudication 已确认保持 best-effort 不重试。

## Blocking Open Questions

None.

## Verdict

**pass**

Both controller-accepted findings are fixed with production code and focused regression tests. No new correctness, stability, or testing issues introduced. 31 tests pass, pyright 0 errors. Ready for the next gate per controller's gate order.
