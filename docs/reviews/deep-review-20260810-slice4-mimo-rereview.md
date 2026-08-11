# WU-CLI-DOWNLOAD-01 Slice 4 Rereview — AgentMiMo

- 基线：`afde13dfeeb50f18bb35364ee15d8dcd23a7bcc2`
- 审查对象：`docs/gateflow/wu-cli-download-01-slice4-review-fix-20260810-092330.md` + 当前未提交 delta
- 审查范围：DS-F01 可达性回归、DS-F02 company-id 同源断言、DS-F03 cancellation contract/conditional checkpoint、MiMo `create_source=True` 观察
- 结论：**PASS**

---

## 1. DS-F01：SC13 registry-only fallback 可达性

### Review fix 裁决：`rejected-with-direct-evidence`

DS review 声称 `_persist_rejected_filing_artifact` 返回 `(False, ...)` 不可达，因为"所有失败都 raise"。review fix 反驳该前提并提供完整调用链证据。

### 独立复核

我独立展开 `sec_download_persistence.py` 的完整执行路径：

1. `:226-233`：`downloader.prefetch_files_stream(...)` 完整消费 private typed events。transport safe failure 投影为 `_PrefetchFailed` 值，**不是异常**。
2. `:247-258`：唯一 materializer `materialize_prefetched_event` 将 `_PrefetchFailed` 投影为 `DownloaderEvent(event_type="file_failed")`。
3. `:260-263`：`failed_files` 非空 → `failure_reason = summarize_failed_download_file_reasons(failed_files)` 非 None。
4. `:294-301`：`failure_reason is not None` 分支跳过 artifact upsert，进入 `:297` rollback 并返回 `(False, failure_reason)`。
5. `sec_download_workflow.py:843-877`：`_publish_sec_post_repair_mutations` 对 `artifact_saved = False` 的 `Sc13DirectionRejectedWithArtifact` 进入独立 registry-only batch（`:863-877`）。

**直接反例验证**：测试 `test_sec_pipeline_sc13_transport_failure_publishes_registry_only` 通过真实 `SecPipeline.download` 产生 `_PrefetchFailed(provider_unavailable)`，断言 registry entry durable 存在且 rejected artifact 不存在。该测试在未修改的 fallback 生产调用链上通过。

**与 DS review 内部一致性**：DS review `§2.5` 已将 `sec_download_workflow.py:863-877` 判为 "SC13 listing/transport 失败 → registry-only PASS"，与 DS-F01 的不可达结论自相矛盾。

**判定**：DS-F01 `rejected-with-direct-evidence` 成立。fallback 不是 dead code；删除它会破坏 v2 amendment §5.4 已接受的 SC13 registry-only policy。**PASS**。

---

## 2. DS-F02：CN event company ID 同源

### Review fix 裁决：`rejected-with-direct-evidence`

DS review 声称 `cn_download_workflow.py:199` 使用 `ticker_to_company_id(normalized)` 而 `cn_download_company_meta.py` 使用 `normalize_ticker` 后的 `ticker_to_company_id`，可能产生不一致。

### 独立复核

三处 company_id 事实均由 `dayu.fins.ticker_normalization` 的同一 public owner 产生：

- **observable event**：`cn_download_workflow.py:199` 调 `ticker_to_company_id(normalized)`，其中 `normalized` 来自 `:92-96` 的 `try_normalize_ticker` → `NormalizedTicker`。
- **durable company meta**：`cn_download_company_meta.py:44-48` 调 `normalize_ticker` → `ticker_to_company_id`。
- **durable source meta**：`cn_download_source_upsert.py:244-252` 调 `ticker_to_company_id(normalize_ticker(ticker))`。

三处输入都是同一个 canonical ticker string，调用同一个 `ticker_to_company_id` 函数。不存在两个 company-ID owner。

**测试验证**：`tests/fins/test_cn_download_workflow.py:1009` 直接断言：
```python
assert company_event.payload["company_id"] == source_meta["company_id"] == company_meta.company_id == "600519_SSE"
```
四路等值（event payload、source meta、company meta、expected literal）覆盖所有投影路径。

**判定**：DS-F02 `rejected-with-direct-evidence` 成立。production 不应修改。**PASS**。

---

## 3. DS-F03：cancellation contract / conditional checkpoint

### Review fix 裁决：`accepted`

DS review 指出 `prefetch_files_stream` 的取消契约未自足，且 conditional transport 返回 payload 后的 checkpoint 位置有缺陷。

### 独立复核

#### 3.1 Docstring 修复

`sec_downloader.py:1573-1578` 新增取消语义段：

> 任一协作式取消检查点命中后，本 stream 正常停止枚举，不为取消伪造 `failed` variant；首个 descriptor 前取消会产生空 stream，中途取消可能保留已经 yield 的事件前缀。完整消费本 stream 的调用方必须在循环结束后立即再次执行同一个 `cancellation_checker` checkpoint；迭代结束本身只表示不再有 transport event，不表示操作成功。

**判定**：自足、准确、无歧义。

#### 3.2 Conditional post-transport checkpoint

`sec_downloader.py:1633-1636`：conditional transport (`_http_download_if_modified`) 返回 payload 后，在检查 empty content 前执行：
```python
try:
    _raise_if_download_cancelled(cancellation_checker)
except SecDownloadCancelledError:
    return
```

旧代码在此位置没有 checkpoint，payload 会被 materialize 即使取消已请求。修复后，取消命中时 stream 停止，不 yield `_PrefetchedFile`，不调用 store callback。

#### 3.3 Unconditional path consistency

`sec_downloader.py:1658`：unconditional transport (`_http_download`) 返回后同样有 `_raise_if_download_cancelled(cancellation_checker)` checkpoint。两条路径一致。

#### 3.4 Consumer-side checkpoints

production consumers 在完整消费 `prefetch_files_stream` 后立即执行 checkpoint：
- `sec_download_persistence.py:234-235`：`_raise_if_cancelled(cancellation_checker)`
- `sec_download_filing_workflow.py:489-490`：`if cancel_checker is not None and cancel_checker(): return`

与 docstring 的"迭代结束不等价于操作成功"一致。

#### 3.5 测试验证

`test_download_files_stream_conditional_cancel_after_transport_stops_without_failure`：fake conditional transport 返回 payload 时设置 `cancelled = True`。断言：
- `events == ["file_download_started"]`（只保留 started 前缀）
- `store_stub.calls == []`（无 callback，无 materialization）

**判定**：DS-F03 `accepted` 修复正确。conditional 和 unconditional 路径均有 post-transport checkpoint，docstring 自足，测试覆盖精确。**PASS**。

---

## 4. MiMo `create_source=True` 观察

### Review fix 裁决：`rejected-with-reason`（非 defect）

MiMo 原始 review 将该项标为"功能正确、轻微语义耦合、非 blocker"。review fix 提供了更详细的不变量证据。

### 独立复核

`sec_download_filing_workflow.py:550-556` 对非 MISSING target 调用 `reset_source_document(ticker, document_id, SourceKind.FILING, batch=token)`，清除旧 staging source。之后 `:703 create_source=True` 触发 `create_source_document` 而非 `update_source_document`。

两条进入 Phase B materialization 的路径：

1. **REPAIR_REQUIRED / COMPLETE+overwrite**：经过 `reset_source_document` → target 在 staging 中不存在 → `create_source=True` 正确。
2. **MISSING**：跳过 reset → target 在 staging 中不存在 → `create_source=True` 正确。

将 `create_source` 改为 `phase_b_integrity.status is SourceIntegrityStatus.MISSING` 会遗漏 REPAIR_REQUIRED 和 COMPLETE+overwrite 两条 reset 后的路径。将它改为 `not phase_b_integrity.status is SourceIntegrityStatus.COMPLETE or overwrite` 虽然语义更精确，但不增加有效正确性保障，且引入对 Phase B classification 的额外依赖。

**判定**：`create_source=True` 与 staging 真实状态一致，不存在 defect。review fix 的 `rejected-with-reason` 裁决成立。**PASS**。

---

## 5. 验证

```text
.venv/bin/pytest -q tests/fins/test_sec_downloader.py tests/fins/test_cn_download_workflow.py tests/fins/test_sec_pipeline_download.py -k 'cancel or top_level_success or rejected_prefetch or sc13_artifact_transport_failure' --disable-warnings
exit 0: 16 passed, 205 deselected

.venv/bin/pytest -q tests/fins/test_sec_downloader.py tests/fins/test_cn_download_workflow.py tests/fins/test_sec_pipeline_download.py --disable-warnings
exit 0: 221 passed
```

---

## 6. 结论

**PASS**。四项 review finding 的裁决均成立：

| Finding | 裁决 | 独立复核结论 |
|---|---|---|
| DS-F01 SC13 registry-only fallback | `rejected-with-direct-evidence` | fallback 可达且有业务含义；删除会破坏已接受 policy |
| DS-F02 CN company-ID 同源 | `rejected-with-direct-evidence` | 三处均由同一 owner 产生；四路等值测试覆盖 |
| DS-F03 cancellation contract | `accepted` | docstring 自足；conditional + unconditional 均有 post-transport checkpoint；consumer checkpoint 一致 |
| MiMo `create_source=True` | `rejected-with-reason` | 与 staging 真实状态一致；非 defect |

未发现新的 correctness、concurrency、atomicity 或 semantic ownership finding。
