# WU-TOOLS-01-F01-02 Aggregate Deepreview — AgentDS

## Metadata

| 项目 | 内容 |
|---|---|
| Work unit | WU-TOOLS-01-F01-02 Migrated Tools Cancellation Propagation And Response |
| Review type | aggregate deepreview |
| Review agent | AgentDS |
| Review range | Accepted plan commit `af3ac6b8` → Slice 5 accepted commit `68f5fd40` |
| Design sources | `docs/host/design.md`, `docs/engine/design.md` |
| Plan | `docs/host/wu-tools-01-f01-02-cancellation-plan.md` |
| Control doc | `docs/host/issues-implementation-control.md`（当前未提交 bookkeeping diff 已核对） |
| Date | 2026-06-08 |
| Verdict | **PASS** — 无 blocking finding |

## Scope

本次 aggregate deepreview 覆盖 Slice 1–5 全部 accepted commits（`872a809e`, `f7cd11a9`, `6cc2ffca`, `bc919866`, `68f5fd40`）的累积生产代码与测试变更。审查范围包括全部 54 个变更文件，并核对各切片 review/re-review/controller adjudication artifact 的裁决链一致性。

控制文档未提交改动（`docs/host/issues-implementation-control.md`）已核对：该 diff 仅做 gate/status/next-entry 的 bookkeeping 字段更新，不涉及生产代码漂移。

## Validation

以下验证基于直接文件阅读和 git diff 证据完成。

### 1. Fins Download / Preprocess Awaiting Tools Token Bridge（Slice 1）

**证据链**：

- `dayu/fins/tools/download_tools.py:80-81`：`FinsDownloadToolCallable.__call__` 读取 `context.cancellation_token`，不再 `del context`。第 81 行 `cancellation_token.is_cancelled()` start 前 checkpoint，命中后调用 `_cancelled_outcome`（第 117-140 行）返回 `ToolCancelledOutcome(reason=TOOL_CANCELLED_REASON_HOST_CANCELLED)`，不创建 durable job。
- `dayu/fins/tools/preprocess_tools.py:79-81`：`FinsPreprocessToolCallable.__call__` 同模式。
- 第 84-88 行（download），第 84-88 行（preprocess）：`start_download/start_preprocess` 返回后检查 `start.status in {CANCELLING, CANCELLED}`，命中返回 cancelled outcome。`FinsIngestionStartCancelledError` 异常分支（第 88-89 行）同样返回 cancelled outcome。
- `dayu/fins/ingestion_runtime.py:1013-1068`（`start_download`），`1070-1124`（`start_preprocess`）：
  - 第 1049 行/第 1106 行：`_raise_if_start_cancelled(cancellation_token)` — 在 durable record 创建前做同步 checkpoint，命中抛 `FinsIngestionStartCancelledError`（第 126 行定义，`RuntimeError` 子类）。
  - 第 1050-1068 行：`_start_lock` 范围内依次执行：create queued record → `_is_start_cancelled` checkpoint → 若取消则 `_save_cancelled(record)` → 返回 cancelled job start → 不 submit 后台 job。
  - 若未取消：`executor.submit(job_id, lambda: self._run_download_job(...))` → 返回正常 start。
- `dayu/fins/ingestion_runtime.py:2639-2669`：`_is_start_cancelled` 和 `_raise_if_start_cancelled` 模块级私有 helper，类型签名清晰，无 magic value。
- `dayu/fins/ingestion_runtime.py:1841-1863`：`_save_cancelled` 直接持久化 CANCELLED 终态，`cancellation_requested=True`。

**invariant 验证**：

| Invariant | 状态 | 证据 |
|---|---|---|
| token cancelled before start must not create a job | PASS | `_raise_if_start_cancelled` 在 `_create_queued_record_with_start_lock` 之前执行；tool callable 在调用 runtime 前也做 pre-checkpoint |
| token cancelled between create and submit must leave job durable cancelling/cancelled and not submit | PASS | `_start_lock` 内同步 checkpoint → `_save_cancelled` → 返回 cancelled start → 不执行 `executor.submit` |
| durable job create 后、后台 submit 前取消检查是同步 checkpoint | PASS | 检查在 `_start_lock` 持有期间执行 |
| token not cancelled preserves existing awaiting outcome behavior | PASS | 正常路径未修改，`executor.submit` + `_awaiting_outcome_from_job_start` 保持不变 |
| Host cancel truth remains Host token; Fins job truth remains job store | PASS | token 仅在 start 边界观察；submit 后不再用 token 做 job cancel 真源；后台 job 继续通过 `_mark_job_running_or_cancelled`/`cancellation_requested` 检查做 durable cancel |

**测试覆盖**：

- `test_download_tool_cancelled_before_start_returns_cancelled_without_job`（`tests/fins/test_fins_ingestion_tools.py:354`）：验证 pre-cancel 返回 `ToolCancelledOutcome` 且不创建 job 文件。
- `test_preprocess_tool_cancelled_before_start_returns_cancelled_without_job`（第 372 行）：同上。
- `test_awaiting_tool_callables_consume_context_and_bridge_token_to_runtime`（第 390 行）：AST 级 source guard 验证 `del context` 已删除，`start_download/start_preprocess` 调用包含 `cancellation_token` keyword。
- 已有 awaiting outcome 测试（第 273、301 行）保持通过。

### 2. Web Search Token Propagation And Fetch Coverage（Slice 2）

**证据链**：

- `dayu/tools/web/web_tools.py:1070-1071`：`search_web` 装饰器声明 `execution_context_param_name="execution_context"`。
- 第 1076 行：函数签名增加 `execution_context: BatchToolExecutionContext | None = None`。
- 第 1095-1096 行：`_resolve_execution_cancellation_token(execution_context)` + `_raise_if_tool_cancelled`。
- 第 1112 行：`cancellation_token` 传入 `search_public_web`。
- `dayu/tools/web/web_search_providers.py:137-258`（`search_public_web`）：
  - 第 152 行：`cancellation_token: CancellationToken | None = None` 参数新增。
  - 第 187 行：`_raise_if_search_cancelled` — query/domain 归一化后 checkpoint。
  - 第 189-226 行：provider 候选循环内每轮入口 `_raise_if_search_cancelled`（第 190 行），每次 provider 尝试前 `_raise_if_search_cancelled`（第 192 行），结果返回后 `_raise_if_search_cancelled`（第 226 行）。
  - 第 227-229 行：异常处理中 `_is_search_cancelled_error(exc)` 判取消错误透传，不吞掉。
- 第 263-282 行：`_raise_if_search_cancelled` 通过 `ToolBusinessError(code="tool_cancelled")` 抛出，与 legacy adapter 兼容。
- `dayu/tools/web/web_tools.py:1149-1309`（`fetch_web_page`）：已有 token 传递路径保留，warmup/probe/fetch 三个阶段均传递 token 并做 checkpoint。

**invariant 验证**：

| Invariant | 状态 | 证据 |
|---|---|---|
| `execution_context` is not part of LLM-facing schema | PASS | 装饰器 metadata，不进入 schema properties |
| Cancelled search must not try later fallback providers | PASS | `_raise_if_search_cancelled` 在循环入口和每次候选尝试前执行；取消异常透传 |
| Provider fallback loop checks token before every attempt | PASS | 第 190、192 行两个 checkpoint 确保取消优先于 provider 尝试 |
| Existing fetch safety policy unchanged | PASS | no plan-modification of `_is_safe_public_url` 等 |

**测试覆盖**：

- `test_search_web_cancelled_before_provider_returns_tool_cancelled`（`tests/tools/web/test_web_tools_provider.py:310`）
- `test_search_web_cancelled_between_provider_attempts_stops_fallback`（第 399 行）
- `test_fetch_playwright_cancel_projects_to_cancelled_failure`（第 571 行）— 已有测试保持通过

### 3. Doc Tools Context Injection And Checkpoints（Slice 3）

**证据链**：

- `dayu/tools/doc_tools.py:115-174`：模块级私有 helper：
  - `_resolve_doc_cancellation_token`：从 context 解析 token。
  - `_raise_if_doc_cancelled`：token 已取消时抛 `ToolBusinessError(code="tool_cancelled")`。
  - `_raise_doc_cancelled`：构造稳定取消错误，消息包含 `cancel_reason()`。
- 所有 5 个 Doc tools 均声明 `execution_context_param_name="execution_context"`：
  - `list_files`（第 278 行）
  - `get_file_sections`（第 391 行）
  - `search_files`（第 713 行）
  - `read_file`（第 937 行）
  - `read_file_section`（第 1071 行）

**checkpoint 密度**：

| 工具 | 入口 | 阻塞I/O前 | 循环内 | 处理前 | 返回前 | 证据行号 |
|---|---|---|---|---|---|---|
| `list_files` | ✅ | — | ✅（文件迭代） | — | ✅ | 317, 325, 346 |
| `get_file_sections` | ✅ | ✅（processor创建前） | ✅（processor list后） | ✅（降级路径） | — | 423, 429, 438 |
| `search_files` | ✅ | ✅（每个文件迭代） | ✅（rglob循环） | ✅（processor搜索前后） | ✅ | 754, 756, 770, 783, 797 |
| `read_file` | ✅ | ✅（每个编码尝试） | — | ✅（readlines后） | — | 983, 986, 1000 |
| `read_file_section` | ✅ | ✅（processor创建前） | — | ✅（read_section前后） | ✅ | 1115, 1129, 1140 |

**invariant 验证**：

| Invariant | 状态 |
|---|---|
| No write capability added | PASS — 所有工具为只读 |
| No LLM-facing schema changes | PASS — `execution_context_param_name` 是 adapter metadata |
| Directory/file traversal stops promptly after cancel | PASS — 循环内 checkpoint 抛出 `ToolBusinessError` |

**测试覆盖**：

- `test_doc_tools_cancelled_before_work_return_tool_cancelled`（`tests/tools/test_doc_tools_provider.py:233`）：参数化覆盖全部 5 个工具的 pre-cancel 场景。
- `test_search_files_cancelled_during_iteration_stops_before_later_scan`（第 488 行）：验证搜索迭代中取消停止后续文件扫描。
- `test_read_file_cancelled_after_first_failed_encoding_stops_fallback`（第 551 行）：验证编码降级中取消停止后续尝试。

### 4. Fins Read Tools Context Injection And Checkpoints（Slice 4）

**证据链**：

- `dayu/fins/tools/fins_tools.py:37-54`：`_resolve_fins_cancellation_token` 模块级私有 helper，从 context 解析 token。
- 所有 9 个 Fins read tools 均声明 `execution_context_param_name="execution_context"`：
  - 第 197 行（`list_documents`）、第 281 行（`get_document_sections`）、第 362 行（`read_section`）
  - 第 460 行（`search_document`）、第 563 行（`list_tables`）、第 650 行（`get_table`）
  - 第 732 行（`get_page_content`）、第 820 行（`get_financial_statement`）、第 913 行（`query_xbrl_facts`）
- 每个工具函数均将 `cancellation_token` 传入 `read_runtime` 对应方法。

- `dayu/fins/tools/read_runtime.py`：
  - 第 122-161 行：`_raise_if_fins_cancelled` / `_raise_fins_cancelled` 模块级 helper，错误码 `tool_cancelled`。
  - 第 164 行：`cancellation_token` 在 `read_runtime.py` 中出现 164 次，所有公开 read 方法均携带 token 参数并在关键边界执行 checkpoint。
  - `list_documents`（第 213-320 行）：入口 + ticker 解析后 + 仓储读取后 + 循环内（每文档迭代）checkpoint。
  - `get_document_sections`（第 322-379 行）：入口 + normalize 后 + processor 创建后 + `list_sections` 后 + 语义增强循环内 checkpoint。
  - `read_section`（第 381-526 行）：入口 + normalize 后 + processor 创建后 + processor read 前后 + 父标题查询前后 checkpoint。第 471-473 行：`except ToolBusinessError` 中检查 `code == _TOOL_CANCELLED_ERROR_CODE` 后透传，不吞掉取消错误。
  - `search_document`（第 528-629 行）：入口 + normalize 后 + processor 创建后 + `list_sections` 后 + 语义增强循环内（每章节）checkpoint。第 625-627 行：`except ToolBusinessError` 中检查取消错误码后透传。

- `dayu/fins/tools/search_engine.py:59-82`：`_raise_if_search_cancelled` 模块级 helper，供搜索引擎内部循环使用。错误码同为 `tool_cancelled`。

**invariant 验证**：

| Invariant | 状态 |
|---|---|
| Fins read tools remain read-only | PASS |
| Financial document access remains through `dayu.fins.storage` protocols | PASS — 所有仓储访问通过 `FinsReadRuntime` 的仓储引用 |
| No read runtime private cancel state is stored between calls | PASS — `cancellation_token` 作为方法参数传递，不在实例存储 |

**测试覆盖**：

- `test_list_documents_pre_cancel_returns_tool_cancelled`（`tests/fins/test_fins_storage_provider.py:647`）
- `test_search_document_cancellation_during_search_stops_before_all_candidates`（第 666 行）
- `test_search_document_semantic_enrichment_cancelled_error_is_not_swallowed`（第 699 行）：验证降级块不吞掉取消错误。
- `test_read_section_cancelled_before_processor_read_returns_tool_cancelled`（第 737 行）
- `test_read_section_parent_title_lookup_cancelled_error_is_not_swallowed`（第 774 行）：验证父标题查询降级不吞取消。
- `test_query_xbrl_facts_cancellation_during_filtering_stops_promptly`（第 806 行）

### 5. Audit Matrix, Combined Assembly, And LLM-Facing Schema Cleanliness（Slice 5）

**证据链**：

- `tests/tools/test_combined_tools_acceptance.py:205-210`：
  ```python
  for definition in discovered_tools.tool_bundle.definitions:
      properties = definition.schema.function.parameters.properties
      assert "execution_context" not in properties
      assert "cancellation_token" not in properties
      assert "execution_context" not in definition.schema.function.parameters.required
      assert "cancellation_token" not in definition.schema.function.parameters.required
  ```
  硬断言所有工具 LLM-facing schema 均不泄露 `execution_context` 或 `cancellation_token` 字段。

- Source-level guard `_assert_context_token_bridge`（`tests/fins/test_fins_ingestion_tools.py:1171`）：通过 AST 分析验证 download/preprocess callable 不包含 `del context`，且 `start_download/start_preprocess` 调用包含 `cancellation_token=` keyword。该 guard 覆盖的行为（context 传递路径）是行为测试难以直接观察的边界，符合 plan 约束。

## Core Questions 裁决

### Q1: 已迁移 Fins/Web/Doc tools 是否完成 CancellationToken 传递审计

**PASS**。审计结论如下：

| 工具族 | 工具数 | token 进入业务入口 | 不丢弃 context | 证据文件:行号 |
|---|---|---|---|---|
| Fins download/preprocess | 2 | ✅ | ✅（不再 `del context`） | `download_tools.py:80`, `preprocess_tools.py:79` |
| Web search/fetch | 2 | ✅ | ✅ | `web_tools.py:1076,1178` |
| Doc tools | 5 | ✅ | ✅ | `doc_tools.py:278,391,713,937,1071` |
| Fins read | 9 | ✅ | ✅ | `fins_tools.py:197,281,362,460,563,650,732,820,913` |

### Q2: 长事务工具是否在本 WU 实现取消响应

**PASS**。

- Fins download/preprocess awaiting：start 前 checkpoint、create-submit 间 `_start_lock` 同步 checkpoint、submit 后不再用 token 做 truth（交给 job store durable cancel）。wait adapter `request_cancel` 语义未被替换。
- Web search/fetch：provider 循环每轮入口 checkpoint，取消停止 fallback。fetch 阶段间 checkpoint 保留。
- Doc/Fins read 风险路径：均补充 checkpoint，循环内命中取消停止后续处理。

### Q3: 其它工具是否至少把 token 传入业务入口

**PASS**。所有 Doc tools（5 个）和 Fins read tools（9 个）均将 token 传入业务入口，并按阻塞 I/O（文件读取、仓储访问）、循环（rglob、文档迭代、section 增强）、外部资源（processor 操作、搜索引擎）风险补充 checkpoint。

### Q4: 是否保持 Host cancel 真源

**PASS**。

- 工具只观察 `CancellationToken`，不创建、不存储、不修改 token 状态。
- Fins awaiting callable 直接返回 `ToolCancelledOutcome`（`download_tools.py:131`, `preprocess_tools.py:131`），不经过 job store 私有 cancel 状态。
- Fins job cancel 仍以 job store `request_cancel` / `claim_running_or_cancelled` / `save_cancelled` 为真源。`_save_cancelled`（`ingestion_runtime.py:1841`）是已有模式的直接扩展，不引入第二套状态机。
- Legacy Web/Doc/Fins read tools 通过 `ToolBusinessError(code="tool_cancelled")` 投影，adapter 将之转为 `ToolFailedOutcome`。此路径不改变 adapter contract，也不创建工具私有 cancel 状态。

### Q5: Awaiting accept 前 orphan job 两阶段启动

**PASS（deferred with owner/destination）**。

- 两阶段启动（prepare → Host accept → activate）未被实现，符合 plan 裁决。
- 当前 mitigation（start 前/后 checkpoint + durable cancel bridge）已实现。
- Plan 裁决的 residual risk 已记录 owner/destination：WU-WAIT-03 或独立 WU-TOOLS-01-F01-02-follow-up。
- 无擅自扩大 Host wait adapter / Fins runtime contract 的迹象。

### Q6: LLM-facing schema 是否不泄漏内部治理字段

**PASS**。

- `test_combined_tools_acceptance.py:207-210`：直接断言所有工具的 LLM-facing schema `properties` 和 `required` 中不包含 `execution_context` 或 `cancellation_token`。
- `execution_context_param_name` 是 adapter 注入 metadata（`@tool` 装饰器参数），adapter 在调用时将 `BatchToolExecutionContext` 注入函数参数但不在 schema 中暴露。
- Tool schema description 中不含 `execution_context`、`cancellation_token`、Host run/attempt id 或其它治理字段。

### Q7: README 触发判断、测试覆盖、pyright 和 residual risk

**PASS**。

- README：`dayu/fins/README.md` 更新了 cancellation 语义说明，属于该 README 的"当前代码已实现的能力"职责范围。`tests/README.md` 无需更新（本文档未新增测试基础设施变更）。
- 测试覆盖：
  - Fins ingestion tools：11 个测试（含 pre-cancel、create-submit gap cancel、source guard）。
  - Fins storage provider：50+ 测试（含每个 Fins read tool 的 pre-cancel、搜索中取消、降级不吞取消、XBRL 过滤取消）。
  - Web tools provider：30+ 测试（含 search/fetch pre-cancel、provider 间取消停止 fallback）。
  - Doc tools provider：15+ 测试（含全部 5 个工具 pre-cancel、search_files 迭代取消、read_file 编码降级取消）。
  - Combined acceptance：schema 污染断言。
- pyright：Slice 5 closeout review 和 re-review controller adjudication 确认 full-repo pyright 无新增报错。当前工作树仅有 control doc bookkeeping 未提交，不影响 pyright。

## Findings

### F-DS-01: `_save_cancelled` 在 create-submit gap 直接标记 CANCELLED 而非通过 CANCELLING 中间态（Non-blocking）

- **位置**：`dayu/fins/ingestion_runtime.py:1841-1863`
- **事实**：`_save_cancelled` 直接设置 `status=FinsIngestionJobStatus.CANCELLED`，不经过 `request_cancel` → `CANCELLING` 过渡。
- **分析**：Create-submit gap 场景中 job 未进入 RUNNING，直接 CANCELLED 终态语义正确。后台 job 的 `_run_download_job`/`_run_preprocess_job` 中对已 cancellation_requested 的 job 在 `_mark_job_running_or_cancelled`（通过 `claim_running_or_cancelled`）后检查 `cancellation_requested | CANCELLING`，然后调用 `_save_cancelled`，语义同样正确。不阻塞本次 aggregate 通过。
- **Severity**：Non-blocking
- **建议**：无。当前两条到 CANCELLED 的路径（`request_cancel` → `claim_running_or_cancelled` 和 `_save_cancelled` 直接写）均服务于不同场景且语义正确。

### F-DS-02: Legacy Web/Doc/Fins read 工具的取消仅通过 `ToolBusinessError` 投影，不通过 `ToolCancelledOutcome`（Known limitation，Non-blocking）

- **位置**：`dayu/tools/doc_tools.py:170-174`, `dayu/fins/tools/read_runtime.py:157-161`, `dayu/tools/web/web_search_providers.py:278-282`
- **事实**：Legacy tools 取消统一通过 `ToolBusinessError(code="tool_cancelled")` → adapter 投影为 `ToolFailedOutcome`，而非 `ToolCancelledOutcome`。
- **分析**：这与 plan R3 residual risk 一致。plan 明确"本 WU 不改 adapter-wide contract"。adapter 已将 `tool_cancelled` 投影为稳定的 `ToolFailedOutcome` error code，不影响下游 LLM 判断。
- **Severity**：Non-blocking
- **Owner/Destination**：若需统一 cancelled outcome，后续独立 tool adapter contract WU。

### F-DS-03: 同步阻塞 I/O（`requests`、文件系统、processor）调用无法被 token 物理中断（Known limitation）

- **位置**：所有 checkpoint 实现
- **事实**：所有 checkpoint 仅在做同步阻塞调用前/后检查 token。token 无法中断正在执行的 `requests.get`、`file.read()` 或 processor 操作。
- **分析**：与 plan R2 一致。当前通过 timeout budget + 前置/后置 checkpoint 覆盖，在可中断边界（调用前后、循环内）做协作式响应。不做伪抢占式取消。
- **Severity**：Non-blocking
- **Owner/Destination**：若需物理 abort，转 WU-WAIT-03/provider-specific runtime owner。

## Residual Risk Review

对照 plan Section 11：

| Risk ID | Plan 裁决 | 实现验证 | 状态 |
|---|---|---|---|
| R1 — Orphan job 窗口 | Deferred；两阶段启动延后 | Start 前/后 checkpoint + durable cancel bridge 已实现。无 Host wait adapter / Fins runtime contract 扩大 | Deferred，owner/destination 仍为 WU-WAIT-03 |
| R2 — 同步 I/O 不可物理中断 | Accepted residual limitation | Checkpoint 在调用前后/循环内补充。timeout budget 保持 | Accepted |
| R3 — Legacy adapter 降级 failed outcome | 本 WU 不改 adapter contract | 所有 legacy 取消统一 `ToolBusinessError(code="tool_cancelled")` | Deferred，后续独立 adapter contract WU |
| R4 — Fins read runtime 深层 checkpoint 需实现裁决 | Implementation 补 checkpoint；未完成项带 owner | 全部 Fins read runtime 方法有 checkpoint；search_engine 有 `_raise_if_search_cancelled` | Closed — 实现已完成 |

无新增 residual risk。

## Conclusion

**PASS** — 无 blocking finding。

WU-TOOLS-01-F01-02 的全部 5 个 slice 实现与 accepted plan 一致：

- Fins download/preprocess awaiting tools 的 token 桥接完整：start 前 checkpoint、create-submit 间 `_start_lock` 同步 checkpoint、submit 后 durable cancel bridge。
- Web search/fetch 和 Doc/Fins read tools 的 context 注入与 checkpoint 审计覆盖所有工具入口（18 个工具 100% context 注入）。
- LLM-facing schema 清洁：`test_combined_tools_acceptance` 硬断言无 `execution_context` / `cancellation_token` 泄漏。
- Host cancel 真源保留：工具只观察 token；Fins job cancel 仍以 job store 为真源；无工具私有 cancel 状态。
- 两阶段启动已按 plan 裁决 deferred，未擅自扩大 contract。
- 测试覆盖充分：预取消、循环中取消、降级块不吞取消、schema 清洁均有 behavior test。
- 3 个 non-blocking findings（F-DS-01, F-DS-02, F-DS-03）均为 plan 已知限制或实现正确性 nuance。
- 全部 4 个 plan residual risk 有明确 owner/destination。
