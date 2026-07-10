# WU-SEMANTIC-OWNERSHIP-01 P3-H S2 Code Review — AgentDS

## Scope

- **Mode**: current changes (unstaged + staged diff vs HEAD)
- **Branch**: `phaseflow/host-issues-control`
- **Base for review context**: `main` (verified no additional S2 changes on branch beyond workspace)
- **Output file**: `docs/reviews/wu-semantic-ownership-01-p3-h-s2-code-review-ds.md`
- **Included scope**:
  - `dayu/fins/direct_event_text.py` (new)
  - `dayu/fins/ingestion_runtime.py` (modified — direct/wait text projection call sites)
  - `dayu/fins/ingestion/wait_adapter.py` (modified — wait outcome text, `_wait_boundary_lost`)
  - `tests/fins/test_fins_ingestion_runtime.py` (modified)
  - `tests/fins/test_fins_ingestion_tools.py` (modified)
  - `docs/reviews/wu-semantic-ownership-01-p3-h-s2-implementation-codex.md` (implementation self-report)
  - `docs/reviews/wu-semantic-ownership-01-p3-h-s2-controller-validation.md` (controller validation report)
- **Excluded scope**: `docs/cli_ci*`, `docs/reviews/code-review-20260710-*`, and any files not in the S2 review instruction list.
- **Parallel review coverage**: 无。单 Agent 逐路走读完成。

---

## Findings

### 1-未修复-中-`_failure_message` 对 `snapshot.message` 的回退路径是观测诊断文本泄漏的潜在通道

- **入口/函数**: `_failure_message()` → `_failed_outcome()` → `_poll_snapshot_result()` → `FinsIngestionWaitPollAdapter.poll_wait()`
- **文件(行号)**: `dayu/fins/ingestion/wait_adapter.py:556-574`
- **输入场景**: 未来任意代码路径构造了 `FinsResultSummary` 且 `error_message` 为 `None` 或空字符串的 FAILED 或 CANCELLED 终态，经由 observation snapshot 进入 `_failure_message`。
- **实际分支**: `_failure_message` 在 `result.error_message is not None and result.error_message.strip() != ""` 条件为 `False` 时，落到 `snapshot.message.strip() != ""` 回退分支（line 570-571），将 observation snapshot 的诊断短消息作为 LLM 可见的失败说明返回。
- **预期行为**: LLM 可见的失败说明应始终来自 `direct_event_text` helper（`direct_failure_message` 或特定业务失败函数），不应暴露 process-local observation 的内部诊断术语（如 `"Observation was cancelled before activation."`、`"Observation activation failed."` 等）。
- **实际行为**: 当前所有已知 FAILED/CANCELLED 路径（`_observation_failure_result` line 5094-5120、`_observation_cancelled_result` line 5123-5152、`_mark_observation_failed` line 5155-5190、direct stream `_emit_direct_result` 路径）均已使用 `direct_failure_message()` 设置非空 `error_message`，因此当前实测不会触发回退。但 `_failure_message` 的回退逻辑本身未移除或未加 `assert` 保护，属于防御性代码的语义真源游离——真实真源应在 result 构造处，回退分支的存在使未来代码可能绕过 owner boundary 而不被察觉。
- **直接证据**: `wait_adapter.py:570-571`：`if snapshot.message.strip() != "": return snapshot.message.strip()`；当前 `snapshot.message` 在 FAILED/CANCELLED 终态可能包含的值（由 `ingestion_runtime.py:2437`、`ingestion_runtime.py:2503`、`ingestion_runtime.py:2639` 写入）均以 `"Observation"` 开头，属于 process-local 诊断文本。
- **影响**: 静默泄漏——不会在正常流程触发，但一旦有代码在终态构造时遗漏 `error_message` 填入，observation 内部诊断文本就会直接出现在 LLM 可见的失败原因中，且现有测试不会捕获此回归。
- **建议改法和验证点**: 在 `_failure_message` 加 `assert` 或至少加 WARN 日志，确保 `result.error_message` 在 FAILED/CANCELLED 状态下非空。或者直接删除 `snapshot.message` 回退分支，在终态路径上强制要求 `result.error_message` 存在。修改后需验证：构造 `FinsResultSummary(error_message=None)` 的 FAILED snapshot → `_failure_message` 应触发明确错误而非静默回退。
- **修复风险（低）**: 若删除回退分支，需确保所有 FAILED/CANCELLED 构造点确实提供了 `error_message`——当前控制流已覆盖，主要风险是未来新增路径遗漏。
- **严重程度（中）**:

### 2-未修复-低-缺少"observation 诊断文本不泄漏到 error_message"的程序化不变式测试

- **入口/函数**: 测试套件 `tests/fins/test_fins_ingestion_runtime.py` 和 `tests/fins/test_fins_ingestion_tools.py`
- **文件(行号)**: `tests/fins/test_fins_ingestion_runtime.py:112-178`（文案 helper 测试）、`tests/fins/test_fins_ingestion_tools.py:1564-1624`（wait poll adapter 状态映射测试）
- **输入场景**: 未来开发者新增 observation 终态收口路径（如新的 producer 异常分类、新的 activation 失败原因），在构造 `FinsResultSummary` 时忘记通过 `direct_failure_message()` 设置 `error_message`，或直接硬编码了 observation 诊断文本。
- **实际分支**: 现有测试验证了文案 helper 输出的业务可读性（`test_direct_event_text_helper_owns_progress_and_wait_copy` 验证 wait 文案不含 Host/Engine 等术语），也验证了 wait adapter 使用的 hint/message 与 helper 一致，但没有任何测试断言"当 observation 在 cancel/activation-failed/finished-without-result 路径上产生终态时，`FinsResultSummary.error_message` 的值不是原始的 observation 诊断文本"。
- **预期行为**: 应有参数化或场景化测试，构造 observation 诊断收口场景（如 `cancel_observation` before activation、`activate_observation` 提交失败、producer 静默结束），并断言结果中的 `error_message`、wait outcome 中的 `message`/`hint` 来自 helper 且不含 `"Observation"` 前缀。
- **实际行为**: controller validation 通过 `rg` 文本扫描确认了当前代码中不存在 `error_message=.*Observation` 模式（`docs/reviews/wu-semantic-ownership-01-p3-h-s2-controller-validation.md:44-45`），但这是快照检查而非回归测试。
- **直接证据**: 测试 `test_direct_event_text_helper_owns_progress_and_wait_copy`（line 163-178）只验证了 wait 文案不含禁止术语，不验证 observation 终态构造链路上的 `error_message` 值。没有测试覆盖 `cancel_observation`（非 submitted 分支）→ `_observation_cancelled_result` 的 `error_message` 字段值断言。
- **影响**: 回归风险——当前正确，但缺少自动捕获未来回归的安全网。
- **建议改法和验证点**: 新增测试：对 `cancel_observation` before activation 路径、`activate_observation` 提交失败路径、producer 静默结束路径，分别断言 observation snapshot 的 `result.error_message` 来自 `direct_event_text` helper 且不含 `"Observation"` 等内部诊断术语。
- **修复风险（低）**: 新增测试不改变生产代码行为。
- **严重程度（低）**:

---

## Evidence Summary

### S2 Owner Boundary 成立性验证

1. **`direct_event_text.py` 隔离性**：仅 import `FinsErrorKind`、`FinsOperationKind`、`FinsResultStatus` 三个 typed enum（`direct_event_text.py:12`）。扫描确认不 import `FinsEvent`、`FinsResultSummary`、`FinsProgress`、`FinsIngestionRuntime`、Host 类型、storage、wait adapter/runtime。

2. **Runtime 只产生 typed facts**：所有 direct result 标题通过 `direct_result_title()` 选择（`ingestion_runtime.py:4428`），所有 runtime-owned progress 文案通过 `direct_progress_message()` 选择（`ingestion_runtime.py:2799, 2855, 2911, 2935, 2946, 3385, 3396, 3511, 3530, 3551, 3566, 3581, 3595, 3619, 3662, 3674, 3716`），所有 direct 失败消息通过 `direct_failure_message()` 或特定 helper（`direct_download_no_source_documents_message` 等）选择（`ingestion_runtime.py:2820, 2876, 2929, 2959, 3290, 3335, 4470, 4963, 4966, 5116, 5148, 5186`）。无残留硬编码中文 direct/wait 文案。

3. **Wait adapter 只消费 helper 文本**：`wait_adapter.py:489` 使用 `wait_failed_hint()`、`wait_adapter.py:510` 使用 `wait_cancelled_message()`、`wait_adapter.py:511` 使用 `wait_cancelled_hint()`。无残留直接中文字符串作为 failed/cancelled 的 hint/message。

4. **Observation 终态 result 均使用 helper 文本**：`_observation_failure_result`（line 5116）、`_observation_cancelled_result`（line 5148）、`_mark_observation_failed`（line 5186）均通过 `direct_failure_message()` 设置 `error_message`。原始 observation 诊断文本（`"Observation was cancelled before activation."`、`"Observation activation failed."`、`"Observation finished without a result."` 等）仅写入 `record.message`（observation snapshot 的 `message` 字段），不再进入 `FinsResultSummary.error_message`。controller 修正已生效。

5. **Contract 不变**：`dayu.fins.direct_events` 中的 `FinsEvent`、`FinsProgress`、`FinsResultSummary` 形状与校验逻辑未修改。

### 传播路径一致性验证

- **Direct progress**: Runtime → `direct_progress_message(stage=...)` → `_direct_progress_event()` → `FinsEvent(PROGRESS)` → Service/CLI consumer。唯一真源、无重复格式化。
- **Direct result**: Runtime → `direct_result_title()` + `direct_failure_message()` → `_emit_direct_result()` → `FinsResultSummary` → `FinsEvent(RESULT)`。标题和错误说明均由 helper 选择，存储于同一 `FinsResultSummary` 实例。
- **Observation/wait**: Observation snapshot 的 `result`（`FinsResultSummary`）→ `_completed_outcome` / `_failed_outcome` / `_cancelled_outcome` → Host resolve outcome。completed 使用 `result.title`，failed 使用 `_failure_message(snapshot, result)`（优先 `result.error_message`），cancelled 使用 `wait_cancelled_message()` + `wait_cancelled_hint()`。所有 LLM 可见文本均从同一 `FinsResultSummary` 或 helper 派生。
- **无下游特例分支**：搜索 `ingestion_runtime.py` 和 `wait_adapter.py`，没有发现对 `FinsResultSummary.error_message` / `title` 做二次格式化、替换、或根据 operation_kind 做特例分支的代码。
- **无兼容 wrapper/re-export**：`direct_event_text.py` 的每个 public 函数都是独立实现，体内不委托到 runtime/wait adapter。`ingestion_runtime.py` 和 `wait_adapter.py` 直接 import 具体 helper 函数，无 `__all__` re-export、无兼容别名。
- **无 schema/contract 非必要变更**：`FinsEvent`、`FinsProgress`、`FinsResultSummary` 的数据类定义未变；`direct_event_text.py` 是新增模块，不修改已有 contract。

### 测试覆盖验证

- **Helper 单元测试**: `test_direct_event_text_helper_owns_result_titles_and_failure_messages`（line 112-160）覆盖 result title（DOWNLOAD/FAILURE、PROCESS_MATERIAL/FAILURE、UPLOAD_FILING/CANCELLED）、failure message（STORAGE、PROVIDER with fallback）、以及四个特定 business 失败消息。
- **Helper progress/wait 测试**: `test_direct_event_text_helper_owns_progress_and_wait_copy`（line 163-178）覆盖 5 个 progress stage、未知 stage 回退、wait failed/cancelled hint/message，以及 wait 文案不暴露 Host/Engine 术语的不变式。
- **Wait adapter 测试**: `test_fins_wait_poll_adapter_maps_observation_statuses`（line 1564-1624）验证 failed outcome 的 hint 等于 `wait_failed_hint()`、cancelled outcome 的 message 等于 `wait_cancelled_message()`、hint 等于 `wait_cancelled_hint()`。
- **Boundary 测试**: `test_fins_wait_poll_adapter_transient_unavailable_uses_host_wait_boundaries`（line 1641-1703）覆盖 6 种 Host deadline/expires 边界场景，包括 future/past/invalid/无边界/仅旧 created_at。
- **Direct stream 测试**: `test_direct_download_stream_writes_storage_and_does_not_create_job_record`（line 1289）、`test_direct_download_projects_adapter_file_progress_events`（line 1326）、`test_direct_download_result_details_preserve_exclusive_skipped_count`（line 1368）等验证 direct stream 行为不变。
- **未覆盖项**: 参见 Finding 2——缺少对 observation 终态构造链路 `error_message` 值的程序化断言。

### Controller Validation 复核

Controller validation（`docs/reviews/wu-semantic-ownership-01-p3-h-s2-controller-validation.md`）报告的修正已逐点确认：

1. `_observation_failure_result`（line 5116）使用 `direct_failure_message(error_kind=FinsErrorKind.EXECUTION, fallback_message=None)` → 结果 `"财报处理执行失败"`。**确认通过**。
2. `_observation_cancelled_result`（line 5148）使用 `direct_failure_message(error_kind=FinsErrorKind.CANCELLED, fallback_message=None)` → 结果 `"操作已取消"`。**确认通过**。
3. `_mark_observation_failed`（line 5186）使用 `direct_failure_message(error_kind=error_kind, fallback_message=None)` → 按 error_kind 选择对应业务文案。**确认通过**。
4. `record.message` 写入的 `"Observation was cancelled before activation."`（line 2437）、`"Observation activation failed."`（line 2503）、`"Observation finished without a result."`（line 2639）均不进入 `FinsResultSummary.error_message`。**确认通过**。

---

## Open Questions

- 无。

---

## Residual Risk

1. **`_failure_message` snapshot.message 回退分支**（Finding 1）：当前路径安全，但防御性代码缺乏语义真源收束（应强制 result 处提供 error_message 而非在消费者处回退）。
2. **Observation 终态 error_message 不变式测试缺失**（Finding 2）：当前正确性依赖代码审查而非自动化回归测试。
3. **Legacy job sidecar `failure_summary.message`**（`ingestion_runtime.py:4161`、`ingestion_runtime.py:4231`）：`_save_failed_from_exception` 将 `str(exc)` 原始异常文本写入 durable job record 的 `failure_summary.message`。该文本可能通过 CLI 命令（如 `dayu fins job show`）暴露给用户，但此路径不属于 S2 direct stream / wait outcome scope，S2 设计文档已明确保留 legacy job sidecar 文本。若 CLI 会投影 `failure_summary` 给最终用户，建议在单独的 slice 中处理。
4. **Source-specific adapter progress messages**：adapter 提供的 `FinsDownloadProgressEvent.message` 直接透传至 direct stream `FinsEvent(PROGRESS).message`（`ingestion_runtime.py:4365-4390`），走 `_emit_download_adapter_progress` 而非 `direct_progress_message()`。这是 adapter 作为 fact producer 的合理边界，当前 S2 不改变此行为。若 adapter 提供了不合适的文本，修复应在 adapter 自身或 adapter→runtime 的输入校验处。
5. **`_save_failed` 对 legacy job 路径的文案尚未迁移到 helper**：`_run_preprocess_job`（line 3290）和 `_run_download_job`（line 3335）中的失败消息已使用 helper-derived `direct_preprocess_no_requested_documents_message()` 与 `direct_download_no_source_documents_message()`，但 `_save_failed_from_exception`（line 4231）仍使用 `str(exc)`。这不属于 S2 scope，但标记为已知残留。
