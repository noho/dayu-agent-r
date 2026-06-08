# WU-TOOLS-01-F01-02 Slice 4 Code Review - AgentMiMo

## Metadata

- **Review target**: WU-TOOLS-01-F01-02 Slice 4 - Fins Read Tools Context Injection And Checkpoints
- **Reviewer**: AgentMiMo (independent code review)
- **Date**: 2026-06-08
- **Design source**: `docs/host/design.md`, `docs/engine/design.md`
- **Plan source**: `docs/host/wu-tools-01-f01-02-cancellation-plan.md` Slice 4
- **Implementation artifact**: `docs/reviews/wu-tools-01-f01-02-slice4-implementation-codex.md`
- **Control doc**: `docs/host/issues-implementation-control.md` (controller state update, not correctness focus)

## Reviewed Scope

### Production Files

| File | Lines changed | Role |
|---|---|---|
| `dayu/fins/tools/fins_tools.py` | +108 | 九工具 execution_context 注入 + token 解析 helper |
| `dayu/fins/tools/read_runtime.py` | +331/-42 | 九方法 cancellation_token 参数 + checkpoint + cancel helper |
| `dayu/fins/tools/search_engine.py` | +37 | `_execute_query_search` cancellation_token + search 内部 checkpoint |

### Test Files

| File | Lines changed | Role |
|---|---|---|
| `tests/fins/test_fins_storage_provider.py` | +548 | 声明注入断言、pre-cancel、search 取消、read_section 取消、XBRL 取消 |
| `tests/tools/test_combined_tools_acceptance.py` | +6 | schema 污染断言 |

### Excluded From Review

- `docs/host/issues-implementation-control.md` — controller 状态更新，非 correctness 重点
- `docs/reviews/wu-tools-01-f01-02-slice4-implementation-codex.md` — implementation artifact，非生产代码

## Validation

| Command | Result |
|---|---|
| `pytest tests/fins/test_fins_storage_provider.py tests/tools/test_combined_tools_acceptance.py -q` | **25 passed, 3 warnings** (warnings 来自第三方 edgar deprecation) |
| `pyright dayu/fins/tools/ tests/fins/test_fins_storage_provider.py tests/tools/test_combined_tools_acceptance.py` | **0 errors, 0 warnings, 0 informations** |

## Findings

### Blocking

无。

### Non-Blocking

#### N1: search_engine.py 与 read_runtime.py 取消 helper 逻辑重复

- **Severity**: Minor (style / maintainability)
- **Location**: `dayu/fins/tools/search_engine.py:59-83` vs `dayu/fins/tools/read_runtime.py:139-160`
- **Evidence**: `search_engine.py` 的 `_raise_if_search_cancelled` 完整内联了 `_raise_fins_cancelled` 的逻辑——相同的 `ToolBusinessError(code="tool_cancelled")`、相同的 message 模板、相同的 hint。两个 helper 都是模块级私有函数。
- **Plan requirement**: Plan 7.1 要求"为每个工具族提供模块级私有 helper"。当前实现遵守了字面要求（两个模块各有一个），但语义上是同一取消逻辑的重复。
- **Impact**: 不影响正确性。`ToolBusinessError` 的 code/message/hint 一致，adapter 投影结果一致。
- **建议**: 若后续统一，可让 `search_engine.py` import `read_runtime._raise_fins_cancelled` 或抽取到共享的 `_cancel_contract` 模块。当前不阻塞。

#### N2: search_document 既有 try/except Exception: pass 可能延迟取消传播

- **Severity**: Low (pre-existing, not introduced by this slice)
- **Location**: `dayu/fins/tools/read_runtime.py:602-621`
- **Evidence**: `search_document` 的 `try` 块覆盖 `list_sections` → `_enrich_sections_with_semantic` → `build_section_bm25f_index` → `_build_section_semantic_profiles` → section 遍历。`except Exception: pass` 会吞掉期间抛出的 `ToolBusinessError(code="tool_cancelled")`。取消信号不会丢失——后续 `_execute_query_search` 入口的 checkpoint 会再次检测——但取消响应会被延迟到 search 阶段才生效。
- **Impact**: 不影响最终正确性（取消最终会被观察到），但取消响应不够及时。这是既有代码行为，本 slice 未引入也未恶化。
- **建议**: 后续可考虑 `except Exception:` 改为 `except (OSError, ValueError):` 或在 except 块中 re-raise `ToolBusinessError`。不阻塞本 slice。

#### N3: XBRL raw facts checkpoint 与 normalized facts checkpoint 覆盖了两轮遍历

- **Severity**: Observation (correctness OK)
- **Location**: `dayu/fins/tools/read_runtime.py:1351-1362`
- **Evidence**: `query_xbrl_facts` 在 `payload.get("facts")` 上做第一轮 checkpoint（raw facts），然后在 `normalized_payload.get("facts")` 上做第二轮 checkpoint（normalized facts）。两轮遍历的 checkpoint 是保守做法，确保 normalize 前后都能观察取消。
- **Impact**: 正确。checkpoint 频率略高但 XBRL facts 数量通常有限。

## Checklist Verification

### 1. Nine tools execution_context injection, schema pollution guard

**PASS**

- `fins_tools.py` 九个工具全部声明 `execution_context_param_name="execution_context"`：
  - `list_documents` (line 197)
  - `get_document_sections` (line 281)
  - `read_section` (line 362)
  - `search_document` (line 460)
  - `list_tables` (line 563)
  - `get_table` (line 650)
  - `get_page_content` (line 732)
  - `get_financial_statement` (line 820)
  - `query_xbrl_facts` (line 913)
- 九个工具函数均接收 `execution_context: BatchToolExecutionContext | None = None` 并通过 `_resolve_fins_cancellation_token` 传入 `FinsReadRuntime`。
- `execution_context` 和 `cancellation_token` 不在 `parameters` JSON Schema dict 中，不进入 LLM-facing schema。
- 测试 `test_fins_read_declarations_request_execution_context_injection` 断言九工具均有注入元数据。
- 测试 `test_combined_discovery_returns_single_bundle_without_reserved_names` 断言 schema 中无 `execution_context` / `cancellation_token`。

### 2. Token 从 BatchToolExecutionContext 读取，runtime 不保存私有 cancel 状态

**PASS**

- Token 仅从 `BatchToolExecutionContext.cancellation_token` 读取（`fins_tools.py:54`）。
- `FinsReadRuntime.__init__`（`read_runtime.py:174-210`）不存储任何 cancel 相关实例状态。
- 取消通过 per-call `cancellation_token` 参数 + module-level `_raise_if_fins_cancelled` 实现。
- Host cancel 真源未被改变。

### 3. Checkpoint 覆盖 Plan 要求的风险边界

**PASS**

| Plan 要求 | 实现位置 | 覆盖 |
|---|---|---|
| repository list/meta/blob reads | `list_documents`: lines 239-250, 259, 270; `_collect_source_documents`: 1603-1619; `_collect_source_documents_by_kind`: 1644-1672 | Yes |
| processor creation/read | `_get_or_create_processor`: 1993-2011; `_create_processor`: 2042-2057; `read_section`: 423-425; `get_table`: 1037-1039 | Yes |
| search loops | `_execute_query_search`: 584-642 (exact + expansion phases); `_search_document_multi`: 788-809 | Yes |
| XBRL fact query/filter loops | `query_xbrl_facts`: 1337-1362 (raw facts + normalized facts 两轮) | Yes |
| table/statement assembly loops | `list_tables`: 934-961; `get_financial_statement`: 1250-1251 | Yes |
| document identity alias scan | `_resolve_canonical_document_id`: 1518-1527 | Yes |
| section semantic enrich | `_enrich_sections_with_semantic`: 1788-1797 | Yes |
| multi-query aggregation | `_search_document_multi`: 788-809 | Yes |

### 4. Cancellation 通过 legacy adapter 投影为 stable tool_cancelled failure

**PASS**

- `_raise_fins_cancelled`（`read_runtime.py:139-160`）抛出 `ToolBusinessError(code="tool_cancelled", ...)`。
- Legacy adapter `definition_adapter.py:374-382` 将 `ToolBusinessError` 投影为 `ToolFailedOutcome(error=error.code)`。
- `ToolBusinessError` 不会被 `read_runtime.py` 中的 `except KeyError` 或 `except FileNotFoundError` 捕获。
- `search_document` 的 `except Exception: pass`（line 620）理论上可吞掉取消，但后续 checkpoint 会再次检测（见 N2）。
- 已有 `ToolArgumentError` / not-supported 行为未被破坏。

### 5. 只通过 dayu.fins.storage 协议访问财报文档

**PASS**

- `read_runtime.py` 所有文档访问通过 `self._source_repository`、`self._company_repository`、`self._processed_repository`、`self._processor_registry`。
- 无 `pathlib.Path`、`os`、`open()` 等直接文件系统访问。
- `search_engine.py` 无文件系统 import，仅操作内存数据结构。

### 6. read_section 移除历史 **_kwargs 安全性

**PASS**

- Git 历史确认 `**_kwargs` 在 commit `688b9de0` 中移除，替换为显式 `execution_context` 参数。
- `**_kwargs` 原本用于吞掉 `within_section_ref` 等历史参数，这些参数已不在当前 schema 中。
- 移除后 `read_section` 签名 `(ticker, document_id, ref, execution_context=None)` 与 schema `required: [ticker, document_id, ref]` 一致。
- Schema validator 不会传入额外参数（adapter 只注入声明的 `execution_context`），因此移除 `**_kwargs` 不影响合法路径。

### 7. 测试覆盖

**PASS**

| Plan 要求的测试 | 实现测试 | 覆盖 |
|---|---|---|
| list_documents pre-cancel | `test_list_documents_pre_cancel_returns_tool_cancelled` | Yes |
| search_document 中途取消停止候选 | `test_search_document_cancellation_during_search_stops_before_all_candidates` | Yes |
| read_section processor read 前取消 | `test_read_section_cancelled_before_processor_read_returns_tool_cancelled` | Yes |
| query_xbrl_facts filtering 取消 | `test_query_xbrl_facts_cancellation_during_filtering_stops_promptly` | Yes |
| 九工具 declaration 注入 | `test_fins_read_declarations_request_execution_context_injection` | Yes |
| combined schema 污染 | `test_combined_discovery_returns_single_bundle_without_reserved_names` (新增 6 行断言) | Yes |

### 8. AGENTS.md 合规

**PASS**

- 中文 docstring: 所有新增函数/方法均有完整中文 docstring，含 Args/Returns/Raises。
- 类型签名: 无新增 `Any`、`object`、无类型参数或返回值。
- Pre-existing 类型债: `read_runtime.py` 大量使用 `dict[str, Any]`（如 `ListDocumentsResult`、`SearchDocumentResult`），但这是既有模式（TypedDict 定义在 `result_types.py`），本 slice 未扩散。
- 无新增 `hasattr`/`getattr`（`get_page_content` 的 `getattr(processor, "get_page_content", None)` 是既有逻辑）。
- 模块级私有 helper: `_resolve_fins_cancellation_token`（`fins_tools.py`）、`_raise_if_fins_cancelled` / `_raise_fins_cancelled`（`read_runtime.py`）、`_raise_if_search_cancelled`（`search_engine.py`）。

## Open Questions

无 blocking open questions。

## Residual Risks (from Plan)

| ID | Risk | Status |
|---|---|---|
| R1 | Awaiting accept 前 orphan job 窗口 | Deferred（本 slice scope 外） |
| R2 | 同步 I/O 无法被 token 强制中断 | Accepted residual limitation |
| R3 | Legacy adapter 投影为 failed outcome 而非 ToolCancelledOutcome | Accepted（本 WU 不改 adapter contract） |
| R4 | Processor 内部长阻塞需 processor owner 补 checkpoint | Implementation artifact 已记录 |

## Conclusion

**PASS**

Slice 4 实现完整覆盖了 Plan 要求的所有 checkpoint 边界、九工具 execution context 注入、schema 污染防护、cancellation token 传递链路和测试覆盖。无 blocking finding。两个 non-blocking 观察（N1 helper 重复、N2 既有 try/except 延迟取消传播）不影响正确性，可作为后续改进项。
