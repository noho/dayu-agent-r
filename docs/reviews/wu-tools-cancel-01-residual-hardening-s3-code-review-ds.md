# Code Review — WU-TOOLS-CANCEL-01 S3

## Scope

- **Mode**: current changes (against HEAD since commit `4f9df113`)
- **Branch**: `phase/wu-tools-cancel-01`
- **Base**: `4f9df113` (WU-TOOLS-CANCEL-01: accept residual hardening S2B)
- **Output file**: `docs/reviews/wu-tools-cancel-01-residual-hardening-s3-code-review-ds.md`
- **Included scope**:
  - `dayu/fins/tools/fins_tools.py`
  - `dayu/tools/doc_tools.py`
  - `dayu/tools/web/web_tools.py`
  - `tests/fins/test_fins_storage_provider.py`
  - `tests/tools/test_doc_tools_provider.py`
  - `tests/tools/web/test_web_tools_provider.py`
  - `tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/` (new)
- **Excluded scope**: S1/S2A/S2B 已提交变更；`dayu/contracts/tool_execution.py` / `dayu/host/tool_runtime.py` 的 S1-S2 已落地部分（仅验证 S3 引用正确性）
- **Parallel review coverage**: 无

## Findings

### 1-未修复-低-`_DocProcessTarget` 通用 Exception 处理器未携带结构化 hint

- **入口/函数**: `_DocProcessTarget.__call__`
- **文件(行号)**: `dayu/tools/doc_tools.py:381-383`
- **输入场景**: 子进程工具目标在执行过程中抛出非业务异常（如内存错误、第三方库 bug）。
- **实际分支**: `except Exception` 分支。
- **预期行为**: Doc 工具应该和 Fins 工具一致，在通用异常路径上提供恢复提示。
- **实际行为**: `process_tool_failed_envelope(error_type="execution_error", message=f"Tool {self.tool_name!r} execution failed.")` —— 没有传递 `hint` 参数。对比 Fins 工具对应路径（`fins_tools.py:281-285`）提供了 `hint=_UNEXPECTED_FAILURE_HINT`。
- **直接证据**: `fins_tools.py:284` 传入了 `hint=_UNEXPECTED_FAILURE_HINT`，`doc_tools.py:383` 未传 `hint`。该不对称在 S3 之前已存在（旧代码 Doc 通用异常消息不含 hint 文本，Fins 含），S3 将 hint 提升为一级字段后，Doc 侧的空 hint 不再被隐式隐藏，对 LLM 恢复的影响更直接。
- **影响**: 微小的用户体验差异——Doc 工具通用异常发生后 LLM 收到的 `ToolResultFailure` 没有恢复提示，可能降低自动恢复概率。
- **建议改法和验证点**: 为 `doc_tools.py:381-383` 增加 `hint=_UNEXPECTED_FAILURE_HINT` 或 Doc 专用的通用异常提示常量，与 Fins 对齐。随后确认 `test_doc_process_target_argument_validation_failure_separates_hint` 和现有 Doc 失败 envelope 测试仍然通过。
- **修复风险（低）**: hint 是附加字段，不影响 `error_type` / `message` 的既有断言。
- **严重程度（低）**: 预存行为偏差，S3 未引入；但 S3 实施窗口是修复该偏差的自然时机。

### 2-未修复-低-`_build_fins_aapl_xbrl_workspace` 中 company_meta 写入在批事务外

- **入口/函数**: `_build_fins_aapl_xbrl_workspace`
- **文件(行号)**: `tests/fins/test_fins_storage_provider.py:1652`
- **输入场景**: 后续 `batching_repository` 批内文件写入失败（如磁盘满、blob 存储异常）。
- **实际分支**: `except Exception` 分支仅对 `batching_repository` 执行 `rollback_batch(token)`，但 `company_repository.upsert_company_meta(...)` 已在第 1652 行先于 `begin_batch` 调用。
- **预期行为**: 如果批事务包含公司元数据 upsert 与文档/文件写入，两者应在同一事务边界内，失败时统一回滚。
- **实际行为**: 批内操作失败回滚后，`CompanyMeta` 记录已持久化在临时 workspace 中。由于测试使用 `tmp_path`，整个 workspace 在测试结束时被 pytest 清理，不影响后续测试；但在本地调试或 fixture 复用场景下可能残留。
- **直接证据**: `company_repository.upsert_company_meta(...)` 在第 1652 行执行；`begin_batch` 在第 1661 行执行；`rollback_batch` 在第 1699 行只回滚 batch 内操作。
- **影响**: 测试隔离轻微降级——仅影响 `tmp_path` 范围内的局部状态，不影响生产代码或跨测试数据。
- **建议改法和验证点**: 将 `company_repository.upsert_company_meta(...)` 移入批事务内；或将 company meta upsert 移到 try/except 中并捕获后清理。也可在测试 teardown 中显式清理，但不如直接修正写入顺序简单。
- **修复风险（低）**: 只涉及测试 helper 内部顺序调整。
- **严重程度（低）**: 测试辅助函数内部不一致，不影响生产代码。

### 3-未修复-低-`_web_process_failed_envelope` 中 `cast(WebPayload, ...)` 绕过类型检查

- **入口/函数**: `_web_process_failed_envelope`
- **文件(行号)**: `dayu/tools/web/web_tools.py:1648-1655`
- **输入场景**: 任意调用 `_web_process_failed_envelope` 的路径。
- **实际分支**: 函数体最后一行。
- **预期行为**: 类型安全——如果 `process_tool_failed_envelope` 返回类型改变，pyright 应在调用处报错。
- **实际行为**: `cast(WebPayload, process_tool_failed_envelope(...))` 将 `JsonValue` 强制转换为 `WebPayload`（即 `dict[str, JsonValue]`）。当前 `process_tool_failed_envelope` 总是返回 `dict[str, JsonValue]`，运行时安全；但如果合约函数签名未来调整（如增加嵌套结构），该 `cast` 会让 pyright 静默。
- **直接证据**: `process_tool_failed_envelope` 的返回类型是 `JsonValue`（联合类型），`WebPayload` 是 `dict[str, JsonValue]`。`cast` 在此处绕过了 `JsonValue` 到 `dict[str, JsonValue]` 的 narrowing 检查。
- **影响**: 远期维护风险——合约返回值变化时本地 type check 不会告警。
- **建议改法和验证点**: 方案 A：在 `_web_process_failed_envelope` 调用处加运行时 `assert isinstance(result, dict)` 后再 cast；方案 B：在 `contracts.tool_execution` 中提供类型更窄的变体（如 `process_tool_failed_envelope_dict`）。方案 A 成本最低且不改变公共契约。
- **修复风险（低）**: runtime assert 不影响正常路径。
- **严重程度（低）**: 当前运行时安全，远期维护提示。

## Positive Observations

以下验证项均通过，无问题：

1. **Envelope 迁移完整性**：Doc/Fins/Web 三个工具包均已移除本地 `_DOC_PROCESS_*`、`_FINS_PROCESS_*`、`_WEB_PROCESS_*` 常量，统一使用 `dayu.contracts` 的 `process_tool_completed_envelope` / `process_tool_failed_envelope`。grep 确认零残留。

2. **Hint 结构化分离**：所有 failed envelope 构造路径均将 `hint` 作为独立字段传入 `process_tool_failed_envelope`，不再拼接到 `message`。`_process_failure_message` helper（Doc/Fins 中把 hint 拼入 message 的函数）已完全移除。Host `_tool_outcome_from_process_envelope` 正确将 `ProcessToolFailedEnvelope.hint` 映射至 `ToolResultFailure.hint`。

3. **架构边界**：
   - Host 层 (`dayu/host/`) 未 import 任何 concrete tool 包（`dayu.tools`、`dayu.fins`）。
   - `dayu.runtime` 未 import `dayu.engine`、`dayu.host`、`dayu.service`、`dayu.ui` 或 `dayu.fins`。
   - Tool schema (`dayu/contracts/tool_schema.py`) 未暴露任何 process envelope field。

4. **AAPL XBRL Fixture**：
   - 所有文件来自已下载的 `workspace/portfolio/AAPL/filings/fil_0000320193-24-000123`，包含真实 SEC EDGAR XBRL 数据（`meta.json`、`.htm`、`.xsd`、`_cal.xml`、`_def.xml`、`_htm.xml`、`_lab.xml`、`_pre.xml`）。
   - `_build_fins_aapl_xbrl_workspace` 通过 `FsCompanyMetaRepository`、`FsSourceDocumentRepository`、`FsDocumentBlobRepository`、`FsBatchingRepository` 构造符合仓储协议的临时 workspace。
   - 无网络 taxonomy 依赖；XBRL 处理器仅消费本地 fixture 文件。
   - `test_fins_read_aapl_xbrl_query_runs_in_spawned_child` 通过 `ProcessBackedToolExecutionCapsule` 运行真实 spawned child，断言 `NetIncomeLoss` concept 出现于查询结果中。concept 名来自 fixture 实现期发现，未在生产代码中硬编码。

5. **测试覆盖**：
   - 三个工具包各有一个 `test_*_do_not_redeclare_process_envelope_constants` 测试，直接读取源文件文本断言 `_DOC_PROCESS_` / `_FINS_PROCESS_` / `_WEB_PROCESS_` 未出现——有效防回潮。
   - Doc/Fins/Web 均修改了失败 envelope 测试，断言 `"Hint:" not in str(envelope["message"])` 且独立断言 `envelope["hint"]` 值。
   - 新增 `test_fins_read_aapl_xbrl_query_runs_in_spawned_child` 覆盖 XBRL spawned child 路径。
   - 全量 `114 passed, 1 skipped`，`pyright 0 errors`，`git diff --check` 通过。

## Open Questions

- 无。

## Residual Risk

- XBRL fixture 元数据 `source_meta` 包含与 `SourceDocumentUpsertRequest` 显式字段重复的键（`ticker`、`document_id` 等），当前仓储实现容忍该重复；若未来仓储增加 meta 字段唯一性校验，该 fixture 构造逻辑可能需要调整。
- Web `cast(WebPayload, ...)` 在 `process_tool_failed_envelope` 返回值类型变更时不会触发 pyright 告警，属于远期维护风险，当前无实际影响。
- 预存的 Doc/Fins 通用异常 hint 不对称在 S3 后更显眼但非回归——若后续 tool hardening 工作涉及 Doc 工具，应一并处理。

## 结论

**PASS_WITH_FINDINGS**

三个 finding 均为低严重度：一个预存行为偏差（Doc 通用异常缺少 hint），一个测试 helper 批事务边界不一致，一个远期类型安全提示。均不阻塞 merge，不影响 S3 核心迁移目标的正确性。Envelope 合约统一、hint 结构化分离、架构边界、fixture 合规性和测试防回潮均验证通过。
