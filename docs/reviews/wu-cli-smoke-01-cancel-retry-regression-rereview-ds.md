# WU-CLI-SMOKE-01 cancel retry regression 复核 — AgentDS

## 审查结论：PASS

2026-07-09 复核。DS review (2026-07-08) 的 5 条 findings 中 **4 条已闭环，1 条保持 LOW 且不影响正确性**。新增 2 条 LOW finding（docstring 遗漏、测试 artifact），均不阻塞合入。

---

## 1. 已闭环 findings 复核

### Finding 1.1 (LOW) — dead code 残留 — **已解决**

| 检查项 | 状态 | 证据 |
|--------|------|------|
| `_EVENT_TYPE_TOOL_AWAITING` 常量 | 已删除 | `grep -n "TOOL_AWAITING" dayu/host/memory.py` → 无结果 |
| `elif event.event_type == _EVENT_TYPE_TOOL_AWAITING:` 分支 | 已删除 | diff 显示整段移除，不再有 `pass` 或投影逻辑 |
| `_selected_awaiting_item` / `_selected_awaiting_text` / `_accepted_arguments_mapping` | 已删除 | diff 显示三函数完全移除 |
| 四个 payload field 常量 | 已删除 | diff 显示 `_PAYLOAD_FIELD_ACCEPTED_ARGUMENTS` 等常量移除 |
| `_EVENT_TYPE_TOOL_AWAITING` 常量在 `dayu/host/durable/memory.py` | 已删除 | `grep -n "TOOL_AWAITING" dayu/host/durable/memory.py` → 无结果 |

**结论**：TOOL_AWAITING 已从两处（memory.py 与 durable/memory.py）完全消失，不再是残留的 dead code。

### Finding 2.1 (LOW) — `_resolve_company_via_browse_edgar_ticker` docstring — **已解决**

`dayu/fins/downloaders/sec_downloader.py:1009-1010`：
```
Raises:
    SecDownloadCancelledError: 取消检查点观察到取消请求时抛出。
```

### Finding 2.2 (LOW) — 公开方法 docstring 遗漏 `SecDownloadCancelledError` — **已解决**

| 方法 | 状态 |
|------|------|
| `resolve_company` | HAS SecDownloadCancelledError |
| `fetch_submissions` | HAS SecDownloadCancelledError |
| `fetch_json` | HAS SecDownloadCancelledError |
| `fetch_browse_edgar_filenum` | HAS SecDownloadCancelledError |
| `resolve_primary_document` | HAS SecDownloadCancelledError |
| `fetch_sc13_party_roles` | HAS SecDownloadCancelledError |
| `fetch_file_bytes` | HAS SecDownloadCancelledError |
| `classify_6k_remote_candidates` | HAS SecDownloadCancelledError |

**全部 8 处已补充。**

### Finding 2.3 (LOW) — 内层 catch + 外层 re-check 冗余 — **未变**

`dayu/fins/pipelines/sec_download_filing_workflow.py:358-359`：
```python
except SecDownloadCancelledError:
    return
```
`dayu/fins/pipelines/sec_download_workflow.py:493-494`（外层循环）：
```python
if cancel_checker is not None and cancel_checker():
    cancelled = True
    break
```

**功能正确。** 内层 catch 后 return 不抛异常，外层在下一轮迭代通过 `cancel_checker()` 检测取消。多余一次循环迭代，无风险。保持 LOW，不阻塞。

### Finding 3.1 (LOW) — 测试 stub 的 `del cancellation_checker` — **未变**

`tests/fins/test_sec_pipeline_download.py:170` 等处。功能正确，不阻塞。

---

## 2. 新增等价性测试复核（核心验收项）

### 2.1 测试结构

`tests/host/test_memory_projection.py:411-472` — `test_tool_awaiting_presence_does_not_change_llm_facing_memory_semantics`:

**事件序列 A（无 awaiting）**：
```
USER_INPUT_ACCEPTED → TOOL_RESULT_ACCEPTED → RUN_SUCCEEDED
```

**事件序列 B（有 awaiting）**：
```
USER_INPUT_ACCEPTED → TOOL_AWAITING → TOOL_RESULT_ACCEPTED → RUN_SUCCEEDED
```

**断言**：
1. `_llm_facing_memory_text_view(snapshot_B) == _llm_facing_memory_text_view(snapshot_A)` — **严格相等**
2. `memory_text` 不含 `"TOOL_AWAITING"`, `"start_fins_download"`, `"CRCL"`

### 2.2 `_llm_facing_memory_text_view` helper

`tests/host/test_memory_projection.py:207-227` — 提取 `(role, text)` 元组的稳定视图，覆盖 `selected_recent_window` 与 `recent_evidence_items`。

### 2.3 等价性覆盖评估 — **PASS**

| 验收准则 | 覆盖 | 证据 |
|----------|------|------|
| 有无 TOOL_AWAITING 的 selected_recent_window role/text 完全一致 | YES | `==` 断言比较两快照的全部 item |
| 有无 TOOL_AWAITING 的 recent_evidence role/text 完全一致 | YES | helper 同时提取 evidence |
| memory 不投影"等待/awaited/取消/poll/abandoned" | YES | `forbidden_fragments` 断言（第一个测试） |
| memory 不包含工具名/参数 | YES | `"start_fins_download" not in memory_text` 与 `"CRCL" not in memory_text` |

### 2.4 测试路径诊断 artifact — 观察

`build_conversation_memory_snapshot_from_events`（测试专用函数）不对 event 做 consumer filter 过滤。因此 TOOL_AWAITING 事件进入 `project_conversation_memory_event` 后落入 `else` 分支（`dayu/host/memory.py:1272-1275`），生成 `_unsupported_event_type_diagnostic`。

该 diagnostic 不影响 `_llm_facing_memory_text_view` 的比较结果（helper 不提取 diagnostics），也不影响 production 路径（durable consumer filter 排除 TOOL_AWAITING）。此为测试 artifact，归入 Finding R2。

---

## 3. 分层与架构边界复核

### 3.1 Memory 边界 — **PASS**

| 检查项 | 状态 |
|--------|------|
| durable consumer `_EVENT_TYPE_FILTER` 不含 TOOL_AWAITING | `dayu/host/durable/memory.py:96-100` |
| `conversation_memory_projection_event_filter()` 不订阅 TOOL_AWAITING | 代码确认 + 测试断言 `"TOOL_AWAITING" not in event_types` |
| `project_conversation_memory_event` 不处理 TOOL_AWAITING | 分支已完全删除 |
| TOOL_AWAITING 在 Host activity/tool_trace/waiting/engine 中的使用不进入 LLM-facing memory | 已在上次 DS review 确认，本次无回归 |

### 3.2 SEC cancel 边界 — **PASS**

| 检查项 | 状态 |
|--------|------|
| 全部公开 downloader 方法接受 `cancellation_checker` | 7/7 方法，docstring 已补充 |
| 全部内部 helper 传递 `cancellation_checker` | `_try_fetch_index_items` / `_try_fetch_index_header_documents` / `_try_fetch_primary_linked_html_files` |
| HTTP 核心链路检查取消 | `_execute_sec_request` per-attempt check + `_rate_limit` pre/post check + `_sleep_with_cancel_check` slice check |
| collection 阶段取消 yield PIPELINE_COMPLETED(cancelled) | `sec_download_workflow.py:371-398, 466-490` |
| SC13 filtering 传播取消 | `sec_sc13_filtering.py` all paths, explicit re-raise 保留 |
| `SecDownloadCancelledError(Exception)` 不被 `except RuntimeError` 误吞 | 继承层次正确，全链路验证通过 |

### 3.3 分层依赖 — **PASS**

无反向依赖、无跨层泄漏。`SecDownloadCancelledError` 定义在 downloader 层，被 pipeline 层消费，方向正确。

---

## 4. 验证结果

```
123 passed, 3 warnings in 6.74s
pyright: errors=0 warnings=0
```

---

## 5. 新增 findings

### Finding R1 (NEW, LOW) — `persist_rejected_filing_artifact` Raises 遗漏 `SecDownloadCancelledError`

- **文件/行号**：`dayu/fins/pipelines/sec_download_persistence.py:202-207`（参数签名）及 docstring Raises 段
- **证据**：函数接受 `cancellation_checker` 并通过 `_raise_if_cancelled` 抛出 `SecDownloadCancelledError`，但 Raises 段未声明。扫描确认其他 8 处公开方法均已补充。
- **建议**：在 Raises 段增加 `SecDownloadCancelledError: 取消检查点命中时抛出。`

### Finding R2 (NEW, LOW) — 测试路径 TOOL_AWAITING 产生 unsupported event type diagnostic

- **文件/行号**：`dayu/host/memory.py:1272-1275`（else 分支），`tests/host/test_memory_projection.py:427-442`（测试 event 序列）
- **证据**：`build_conversation_memory_snapshot_from_events` 不做 consumer filter 过滤，TOOL_AWAITING 落入 `project_conversation_memory_event` 的 else 分支，生成 diagnostic。`_llm_facing_memory_text_view` 忽略 diagnostics，等价性断言通过。Production 路径无此问题（durable filter 过滤）。
- **影响**：仅在测试路径中产生多余 diagnostic。若未来有人测试 `snapshot.diagnostics` 的严格内容，可能需要调整。
- **建议**：可接受现状（testing artifact），或考虑在 `build_conversation_memory_snapshot_from_events` 中做与 production 一致的 event filter。

---

## 附录：findings 闭环矩阵

| DS Review Finding | 当前状态 | 备注 |
|-------------------|----------|------|
| 1.1 (dead code 残留) | **已解决** | 常量、分支、辅助函数全部删除 |
| 2.1 (docstring `_resolve_company_via_browse_edgar_ticker`) | **已解决** | Raises 已补充 |
| 2.2 (docstring 公开方法) | **已解决** | 全部 8 处已补充 |
| 2.3 (inner catch 冗余) | 未变 | LOW，功能正确 |
| 3.1 (test stub del) | 未变 | LOW，功能正确 |
| — | R1 (NEW) | `persist_rejected_filing_artifact` docstring |
| — | R2 (NEW) | 测试路径 diagnostic artifact |
