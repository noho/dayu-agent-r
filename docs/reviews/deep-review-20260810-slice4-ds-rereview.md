# AgentDS Slice 4 Code-Review Rereview

- **Reviewer**: AgentDS（原 DS-F01/F02/F03 提出者）
- **Date**: 2026-08-10
- **Baseline**: `afde13dfeeb50f18bb35364ee15d8dcd23a7bcc2`
- **Fix artifact**: `docs/gateflow/wu-cli-download-01-slice4-review-fix-20260810-092330.md`
- **Scope**: 最新未提交 delta（20 files, +3509/-1197）
- **Verdict**: **PASS** — 三项原 finding 全部已裁决；修复正确、有据；无新增 blocking finding

## 1. DS-F01 重裁决：`(False, failure_reason)` 路径确可达

### 1.1 原 finding

断言 `_publish_sec_post_repair_mutations` 中 `artifact_saved=False` 对 `Sc13DirectionRejectedWithArtifact` 不可达——因为 `persist_rejected_filing_artifact` 所有失败都 raise。

### 1.2 反驳证据（已核实）

**证据 1 — `(False, failure_reason)` 是正常可达返回路径**：

`dayu/fins/pipelines/sec_download_persistence.py:257-299`：
```python
failed_files = [item for item in file_results if item.get("status") == "failed"]
failure_reason = summarize_failed_download_file_reasons(failed_files) if failed_files else None
if failure_reason is None:
    ... upsert artifact + registry ...
    batching_repository.commit_batch(batch)
    return True, None        # ← 成功路径
# failure_reason is not None:
batching_repository.rollback_batch(batch)
return False, failure_reason  # ← 可达！typed transport failure 走此处
```

- `_PrefetchFailed` → materializer 投影为 `file_failed` DownloaderEvent
- `build_file_result_from_downloader_event` → `DownloadFileResult(status="failed")`
- `summarize_failed_download_file_reasons` → 非空 `failure_reason`
- 函数 rollback batch 并返回 `(False, failure_reason)`

**证据 2 — SC13 registry-only fallback 是规范行为**：

`dayu/fins/pipelines/sec_download_workflow.py:843-877`：
- `artifact_saved == True` → artifact+registry 已同批发布 → `continue`
- `artifact_saved == False` → 进入独立 registry-only durable unit（`:863-877`）

这与 v2 plan amendment §5.4（`:295-297`）规定的 SC13 registry-only policy 完全一致。

**证据 3 — 新增顶层回归测试**：

`tests/fins/test_sec_pipeline_download.py::test_sec_pipeline_sc13_transport_failure_publishes_registry_only`：
- 通过 `StubDownloader` 产生 `_PrefetchFailed(provider_unavailable)`
- 经真实 `SecPipeline.download` 顶层调用链
- 断言 `registry_payload[document_id]["reason"] == "sc13_direction_rejected"`
- 断言 `not _rejected_meta_path(...).exists()`（artifact 不存在）
- 该测试在未修改 production fallback 的情况下通过 → 动态可达性证明

**证据 4 — 原 review 内部矛盾**：

原 DS review §2.5 将 `sec_download_workflow.py:863-877` 判为"SC13 listing/transport 失败 → registry-only PASS"——与 DS-F01 的不可达结论自相矛盾。

### 1.3 裁决

**DS-F01 撤回**。`(False, failure_reason)` 路径通过 typed `_PrefetchFailed` → materializer → failure_reason 正常可达。SC13 registry-only fallback 是 v2 plan 明文规定的 provider-specific policy，不是 dead compatibility code。

---

## 2. DS-F02 重裁决：三路 company-id 确由同一 owner 产生

### 2.1 原 finding

建议 `company_info["company_id"]`（event payload）可能与 `upsert_company_meta_for_cn_download` 的内部 company_id 不一致。

### 2.2 反驳证据（已核实）

**证据 1 — 三路调用同一 public function**：

| 路径 | 文件:行号 | 调用 |
|---|---|---|
| event COMPANY_RESOLVED | `cn_download_workflow.py:200` | `ticker_to_company_id(normalized)` |
| durable company meta | `cn_download_company_meta.py:48` | `ticker_to_company_id(normalized)` |
| durable source meta | `cn_download_source_upsert.py:244` | `ticker_to_company_id(normalize_ticker(ticker))` |

全部 import 自 `dayu.fins.ticker_normalization`；对同一有效 ticker，`try_normalize_ticker` 与 `normalize_ticker` 产生相同 `NormalizedTicker`，`ticker_to_company_id` 是纯函数 → 三路结果必然一致。

**证据 2 — 新增三路同源断言**：

`tests/fins/test_cn_download_workflow.py:1004-1009`（`test_cn_download_workflow_commits_pdf_and_docling` 内）：
```python
company_event = next(event for event in events if event.event_type is DownloadEventType.COMPANY_RESOLVED)
company_meta = pipeline._company_repository.get_company_meta("600519")
assert company_event.payload["company_id"] == source_meta["company_id"] == company_meta.company_id == "600519_SSE"
```

该断言直接证明 event/source/company 三路投影为同一值。production 未修改。

### 2.3 裁决

**DS-F02 撤回**。三路 company-id 共享同一 `ticker_to_company_id` owner，不存在多源漂移风险。

---

## 3. DS-F03 重裁决：cancel contract 已自足，checkpoint 已收口

### 3.1 原 finding

`prefetch_files_stream` cancel 使用裸 `return`，依赖 convention-based safety；调用方可能遗漏 post-consumption checkpoint。

### 3.2 修复内容（已核实）

**修复 1 — Docstring 自足 contract**：

`dayu/fins/downloaders/sec_downloader.py:1558-1567`（`prefetch_files_stream` docstring 新增取消语义段）：
- 任一协作式取消检查点命中 → stream 正常停止，不伪造 `failed`
- 首 descriptor 前取消 → 空 stream
- 中途取消 → 可能保留已 yield 前缀
- 调用方**必须**在完全消费后立即再次执行同一 `cancellation_checker`
- 迭代结束 ≠ 操作成功

**修复 2 — Conditional post-transport checkpoint 收口**：

`dayu/fins/downloaders/sec_downloader.py:1615-1618`（conditional 路径内）：
```python
# 原代码：
_raise_if_download_cancelled(cancellation_checker)

# 修复后：
try:
    _raise_if_download_cancelled(cancellation_checker)
except SecDownloadCancelledError:
    return
```

关闭了 conditional transport 返回 payload 后、yield `_PrefetchedFile` 前的极窄 cancel 窗口。

**修复 3 — 消费者 inventory 完整**：

| 消费者 | 文件:行号 | Post-consumption checkpoint |
|---|---|---|
| SEC single filing | `sec_download_filing_workflow.py:489-490` | `cancel_checker is not None and cancel_checker()` |
| SEC rejected persistence | `sec_download_persistence.py:235` | `_raise_if_cancelled(cancellation_checker)` |
| Public wrapper | `sec_downloader.py:1784` | 组合 prefetch + materialize，checkpoint 在调用方 |

**修复 4 — 新增确定性回归**：

`tests/fins/test_sec_downloader.py::test_download_files_stream_conditional_cancel_after_transport_stops_without_failure`：
- Fake transport 在返回 payload 前设置 `cancelled = True`
- 断言只产生 `file_download_started` 前缀
- `store_stub.calls == []`（无 payload 落盘）
- 无 `file_failed` 事件伪造
- 无异常外泄

### 3.3 裁决

**DS-F03 已修复**。Cancel contract 现已在 docstring 中自足；conditional checkpoint gap 已收口；所有消费者 inventory 完整；新增确定性回归覆盖精确窗口。

---

## 4. 其他验证项

| 检查项 | 结果 |
|---|---|
| fix artifact 未修改 production 的 SC13 fallback（仅改 docstring + checkpoint） | ✓ |
| fix artifact 未修改 production 的 CN company-id 路径（仅改 test assertion） | ✓ |
| 新增 3 项 test 均通过 targeted run（16 passed, 204 deselected） | ✓ |
| pyright `0 errors, 0 warnings, 0 informations` | ✓ |
| Ruff check + format check 通过 | ✓ |
| `git diff --check` exit 0 | ✓ |
| fix artifact 未修改 README / plan / Oracle / registry / Host / Engine / PR190 | ✓ |
| 未 commit / push / PR | ✓ |

---

## 5. 判决

**PASS**

- DS-F01：**撤回** — `(False, failure_reason)` 路径通过 typed `_PrefetchFailed` 正常可达；SC13 registry-only fallback 是 v2 plan 规定的 provider-specific policy。
- DS-F02：**撤回** — 三路 company-id 共享同一 `ticker_to_company_id` owner，新增 test 证明 event/source/company 三路同源。
- DS-F03：**已修复** — docstring cancel contract 自足；conditional post-transport checkpoint gap 收口；消费者 inventory 完整；确定性回归覆盖。

无新增 finding。无 blocking issue。原 DS review 其余 PASS 项继续有效。
