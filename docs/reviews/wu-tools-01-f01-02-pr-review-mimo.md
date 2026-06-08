# WU-TOOLS-01-F01-02 PR Review — AgentMiMo

## Metadata

| 字段 | 值 |
|---|---|
| PR | [#128](https://github.com/noho/dayu-agent-r/pull/128) |
| Work Unit | WU-TOOLS-01-F01-02 Migrated Tools Cancellation Propagation And Response |
| Reviewer | AgentMiMo (mimo-v2.5-pro) |
| Review Date | 2026-06-08 |
| Design Sources | `docs/host/design.md`; `docs/engine/design.md` |
| Plan | `docs/host/wu-tools-01-f01-02-cancellation-plan.md` |
| Control Doc | `docs/host/issues-implementation-control.md` |

## Validation

### 1. PR 远端 diff 与本地 accepted commits / artifacts 一致性

**PASS。**

- PR head SHA: `5f220c4ed7cbd6290fb0eefaa8e46128e544a3cc`
- 本地 HEAD SHA: `5f220c4ed7cbd6290fb0eefaa8e46128e544a3cc`
- SHA 完全一致，本地与远端无差异。

### 2. PR 范围检查

**PASS。**

PR 涉及的生产代码文件均在 WU 范围内：

| 文件 | 职责 |
|---|---|
| `dayu/fins/ingestion_runtime.py` | Fins ingestion runtime，添加 cancellation_token 参数到 start_download/start_preprocess |
| `dayu/fins/tools/download_tools.py` | Fins 下载 awaiting tool，消费 context.cancellation_token |
| `dayu/fins/tools/preprocess_tools.py` | Fins 预处理 awaiting tool，消费 context.cancellation_token |
| `dayu/fins/tools/fins_tools.py` | Fins read tools，添加 execution_context 注入 |
| `dayu/fins/tools/read_runtime.py` | Fins read runtime，添加 cancellation_token 参数 |
| `dayu/fins/tools/search_engine.py` | Fins search engine，添加 cancellation_token checkpoint |
| `dayu/tools/web/web_tools.py` | Web tools，search_web 添加 execution_context 注入 |
| `dayu/tools/web/web_search_providers.py` | Web search providers，search_public_web 添加 cancellation_token |
| `dayu/tools/doc_tools.py` | Doc tools，全部 5 个工具添加 execution_context 注入 |

测试文件均在 WU 范围内：

| 文件 | 职责 |
|---|---|
| `tests/fins/test_fins_ingestion_tools.py` | Fins awaiting tools 测试 |
| `tests/fins/test_fins_ingestion_runtime.py` | Fins ingestion runtime 测试 |
| `tests/fins/test_fins_storage_provider.py` | Fins storage provider 测试 |
| `tests/tools/web/test_web_tools_provider.py` | Web tools provider 测试 |
| `tests/tools/test_doc_tools_provider.py` | Doc tools provider 测试 |
| `tests/tools/test_combined_tools_acceptance.py` | Combined tools acceptance 测试 |

README 文件更新：

| 文件 | 更新内容 |
|---|---|
| `dayu/fins/README.md` | 更新 ingestion runtime cancellation token 签名、FinsIngestionStartCancelledError 契约说明 |
| `tests/README.md` | 更新 Fins awaiting callable 启动前 cancellation 和 runtime create 后 submit 前 cancellation 覆盖描述 |

**未发现 WU 范围外改动。**

### 3. CancellationToken 传递和取消响应

**PASS。**

#### Fins Awaiting Tools (Slice 1)

- `FinsDownloadToolCallable.__call__` (download_tools.py:59-114):
  - 从 `context.cancellation_token` 获取 token ✅
  - start 前检查 `cancellation_token.is_cancelled()` ✅
  - 调用 `runtime.start_download(request, cancellation_token=cancellation_token)` ✅
  - 检查返回的 job status 是否为 CANCELLING/CANCELLED ✅
  - 捕获 `FinsIngestionStartCancelledError` ✅
  - 不再 `del context` ✅

- `FinsPreprocessToolCallable.__call__` (preprocess_tools.py:58-113):
  - 同 download tools 的实现 ✅

- `FinsIngestionRuntime.start_download` (ingestion_runtime.py:1013-1068):
  - 接受 `cancellation_token: CancellationToken | None = None` 参数 ✅
  - normalize/request_summary 后 `_raise_if_start_cancelled(cancellation_token)` ✅
  - 在 `_start_lock` 内创建 durable job 后检查 `_is_start_cancelled(cancellation_token)` ✅
  - 若取消，调用 `_save_cancelled(start.record)` 返回 cancelled job ✅
  - 若未取消，提交 `executor.submit` ✅

- `FinsIngestionRuntime.start_preprocess` (ingestion_runtime.py:1070-1124):
  - 同 start_download 的实现 ✅

#### Web Tools (Slice 2)

- `search_web` (web_tools.py:1071-1113):
  - 声明 `execution_context_param_name="execution_context"` ✅
  - 从 `execution_context` 解析 `cancellation_token` ✅
  - 调用 `_raise_if_tool_cancelled(cancellation_token)` ✅
  - 传递 `cancellation_token` 给 `search_public_web` ✅

- `search_public_web` (web_search_providers.py:137-261):
  - 接受 `cancellation_token: CancellationToken | None = None` 参数 ✅
  - 入口处 `_raise_if_search_cancelled(cancellation_token)` ✅
  - provider fallback 循环开始前 `_raise_if_search_cancelled(cancellation_token)` ✅
  - 每个 provider 尝试前 `_raise_if_search_cancelled(cancellation_token)` ✅
  - provider 结果返回后 `_raise_if_search_cancelled(cancellation_token)` ✅

- `fetch_web_page` 已有 execution_context 注入和 cancellation checkpoint ✅

#### Doc Tools (Slice 3)

- 全部 5 个 Doc tools 均声明 `execution_context_param_name="execution_context"` ✅
- 模块级 helper:
  - `_resolve_doc_cancellation_token(execution_context)` ✅
  - `_raise_if_doc_cancelled(cancellation_token)` ✅
  - `_raise_doc_cancelled(cancellation_token)` ✅
- checkpoint 位置:
  - `list_files`: before glob, inside file iteration, before return ✅
  - `get_file_sections`: before processor creation, after processor list, before fallback ✅
  - `search_files`: before rglob, inside file iteration, before processor search, before return ✅
  - `read_file`: before encoding attempts, after readlines, before range extraction ✅
  - `read_file_section`: before processor creation, before processor.read_section, before child traversal ✅

#### Fins Read Tools (Slice 4)

- 全部 9 个 Fins read tools 均声明 `execution_context_param_name="execution_context"` ✅
- 模块级 helper:
  - `_resolve_fins_cancellation_token(execution_context)` ✅
  - `_raise_if_fins_cancelled(cancellation_token)` ✅
  - `_raise_fins_cancelled(cancellation_token)` ✅
- `FinsReadRuntime` 方法均接受 `cancellation_token: CancellationToken | None = None` ✅
- checkpoint 位置按风险分级:
  - 入口 checkpoint ✅
  - repository list/meta/blob reads 前后 ✅
  - processor creation/section/table reads 前后 ✅
  - search engine query loops 内部 ✅
  - XBRL fact query/filtering loops 内部 ✅
  - large table/statement result assembly loops 内部 ✅

### 4. Host cancel 真源是否未被替代

**PASS。**

- Fins ingestion job cancel 真源仍是 `job_store.request_cancel` / `claim_running_or_cancelled` / `save_succeeded_or_cancelled` ✅
- 工具只观察 `CancellationToken`，不创建私有 cancel 状态 ✅
- Fins awaiting job 只通过已有 Fins job store cancel 字段表达 job cancel ✅
- Host wait adapter abandon wait 仍调用 `runtime.request_cancel(job_id)` ✅

### 5. 两阶段启动是否未被擅自实现

**PASS。**

- 未发现 `prepare durable job -> Host awaiting accept 成功 -> activate/submit background job` 实现 ✅
- PR residual risks 明确声明 "Awaiting accept two-stage startup remains deferred to WU-WAIT-03 or a dedicated design follow-up" ✅
- 当前 mitigation:
  - Fins tool start 前观察 token，若已取消则不创建 job ✅
  - Fins tool start 后、返回 awaiting outcome 前再次观察 token；若已取消，立即 `runtime.request_cancel(job_id)` 并返回取消 outcome ✅
  - Fins runtime 执行前、循环中、终态前已有 durable cancel check ✅

### 6. LLM-facing schema 是否不泄漏 execution_context / cancellation_token / Host 内部治理字段

**PASS。**

- `search_web` 的 parameters 只包含 `query`, `domains`, `recency_days`, `max_results`，不含 `execution_context` ✅
- `fetch_web_page` 的 parameters 只包含 `url`, `extract_mode`, `max_chars`，不含 `execution_context` ✅
- Doc tools 的 parameters 不含 `execution_context` ✅
- Fins read tools 的 parameters 不含 `execution_context` ✅
- Fins download/preprocess tools 的 parameters 不含 `cancellation_token` ✅
- `test_combined_tools_acceptance.py` 中有断言:
  - `assert "execution_context" not in properties` (line 207) ✅
  - `assert "cancellation_token" not in properties` (line 208) ✅
  - `assert "execution_context" not in definition.schema.function.parameters.required` (line 209) ✅
  - `assert "cancellation_token" not in definition.schema.function.parameters.required` (line 210) ✅

### 7. README、tests、pyright、residual risk owner/destination

**PASS。**

#### README 更新

- `dayu/fins/README.md`: 已更新 ingestion runtime cancellation token 签名、`FinsIngestionStartCancelledError` 契约说明、awaiting 流程中 token checkpoint 描述。属于该 README 的"当前代码已实现的能力"职责范围 ✅
- `tests/README.md`: 已更新 Fins awaiting callable 启动前 cancellation 和 runtime create 后 submit 前 cancellation 覆盖描述 ✅
- 其它 README 按触发规则检查后无需更新 ✅

#### Tests

- Fins ingestion tools: 11 个测试（含 pre-cancel、create-submit gap cancel、source guard） ✅
- Fins storage provider: 50+ 测试（含每个 Fins read tool 的 pre-cancel、搜索中取消、降级不吞取消、XBRL 过滤取消） ✅
- Web tools provider: 30+ 测试（含 search/fetch pre-cancel、provider 间取消停止 fallback） ✅
- Doc tools provider: 15+ 测试（含全部 5 个工具 pre-cancel、search_files 迭代取消、read_file 编码降级取消） ✅
- Combined tools acceptance: audit matrix 测试确认 schema 不泄漏 ✅

#### pyright

```
$ source .venv/bin/activate && pyright dayu/fins dayu/tools tests/fins tests/tools
0 errors, 0 warnings, 0 informations
```

PASS ✅

#### Residual Risks Owner/Destination

| ID | Risk | Decision | Owner / Destination |
|---|---|---|---|
| R1 | Awaiting accept 前 orphan job 窗口 | Deferred | WU-WAIT-03 或新 WU-TOOLS-01-F01-02A |
| R2 | Synchronous blocking I/O 无法被 token 强制中断 | Accepted residual limitation | provider/runtime follow-up |
| R3 | Legacy adapter 把 tool_cancelled 投影为 failed outcome | Deferred | adapter contract WU |

均有明确 owner/destination ✅

### 8. Control doc PR URL bookkeeping

**注意：** 本地 `docs/host/issues-implementation-control.md` 有未提交的 PR URL bookkeeping 修改（将 WU-TOOLS-01-F01-02 状态从 `ready-to-open-draft-PR-blocked` 更新为 `PR-review`，添加 draft PR URL `https://github.com/noho/dayu-agent-r/pull/128`）。这是 controller bookkeeping，不是生产代码问题。

## Findings

**未发现 blocking finding。**

### F1 (Minor) — Control doc bookkeeping 未提交

- **Severity**: Informational
- **Location**: `docs/host/issues-implementation-control.md`
- **Description**: 本地有 PR URL bookkeeping 修改未提交，但这不是生产代码问题，是 controller 职责。
- **Impact**: 无。controller 会在后续 gate 处理。

## Conclusion

**PASS。**

PR 128 满足 WU-TOOLS-01-F01-02 PR review gate 的全部验收标准：

1. ✅ PR 远端 diff 与本地 accepted commits / artifacts 一致，无 WU 范围外改动。
2. ✅ 已迁移 Fins / Web / Doc tools 的 CancellationToken 传递和取消响应满足 aggregate deepreview 结论。
3. ✅ Host cancel 真源未被替代；两阶段启动未被擅自实现（deferred to WU-WAIT-03）。
4. ✅ LLM-facing schema 不泄漏 execution_context / cancellation_token / Host 内部治理字段。
5. ✅ README 已按触发规则更新；tests 全部通过；pyright 0 errors；residual risks 均有 owner/destination。
6. ✅ 本地 control doc 的 PR URL bookkeeping 是 controller 职责，不是生产代码问题。

**建议：进入 draft-PR-pass gate。**
