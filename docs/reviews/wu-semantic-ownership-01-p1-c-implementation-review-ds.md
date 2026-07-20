# WU-SEMANTIC-OWNERSHIP-01 P1-C Implementation Review — AgentDS

## Conclusion

**pass-with-findings**

F-1 是阻断级 finding：Web 工具取消 hint 中 6 处 "host cancelled" 治理词泄漏到 LLM-facing tool outcome，P1-C plan S2 明确要求清理但未执行。其余实现质量良好：compaction prompt/parser、RunInput memory/fallback 投影、Fins/Doc 取消文案、runtime helper fail-fast、P1-A/P1-B 保护、design.md 更新、README 决策均正确。

---

## F-1 (HIGH — 阻断): Web 工具取消 hint 泄漏 "host cancelled" 治理术语到 LLM

### 直接证据

`dayu/tools/web/` 中 6 处取消 hint 包含 `"The host cancelled this web search/fetch"`，经 `_host_cancelled_from_token()` / `host_cancelled_outcome()` → `ToolCancelledOutcome.hint` 进入 LLM-facing tool result：

| # | 文件:行号 | 路径 | hint 文本 |
|---|---|---|---|
| 1 | `dayu/tools/web/web_tools.py:1343-1346` | `SearchWebToolCallable._execute_search` → `_host_cancelled_from_token`（pre-lock cancel check） | `"[continue_without_web] The host cancelled this web search; continue without this web search unless the user asks to retry."` |
| 2 | `dayu/tools/web/web_tools.py:1365-1368` | `SearchWebToolCallable._execute_search` → `_host_cancelled_from_token`（post-lock cancel check） | 同上 |
| 3 | `dayu/tools/web/web_tools.py:1448-1451` | `FetchWebPageToolCallable._execute` → `_host_cancelled_from_token`（pre-lock cancel check） | `"[continue_without_web] The host cancelled this web fetch; continue without this page unless the user asks to retry."` |
| 4 | `dayu/tools/web/web_tools.py:1462-1465` | `FetchWebPageToolCallable._execute` → `_host_cancelled_from_token`（post-lock cancel check） | 同上 |
| 5 | `dayu/tools/web/web_tools.py:744-746` | `_raise_fetch_cancelled()` → `WebToolCancelledError.hint` → `host_cancelled_outcome()` at line 1479 | `"[continue_without_web] The host cancelled this web fetch; continue without this page unless the user asks to retry."` |
| 6 | `dayu/tools/web/web_search_providers.py:323-325` | `_cancel_if_requested()` → `WebSearchCancelledError.hint` → `host_cancelled_outcome()` at line 1386 | `"[continue_without_web] The host cancelled this web search; continue without this web search unless the user asks to retry."` |

所有 6 处 hint 均经 `host_cancelled_outcome(message=..., hint=...)` 直接进入 `ToolCancelledOutcome.hint`，成为 LLM 可读 tool result 的一部分。

### Owner boundary

- **首次产生**: Web tool callable（`SearchWebToolCallable._execute_search` / `FetchWebPageToolCallable._execute`）与 `web_search_providers._cancel_if_requested()` 是取消 hint 文本的 owner
- **校验**: 无。P1-C plan S2 明确要求对 `dayu/tools/web/web_tools.py` 做显式 message/hint 审计并清理 "宿主取消"，但 Web cancellation messages 被清理后（`_WEB_SEARCH_CANCELLED_MESSAGE` / `_WEB_FETCH_CANCELLED_MESSAGE` 改为 `"网页搜索/抓取工具调用已停止。"`），对应的 hints 未被清理
- **持久化 / 诊断**: `ToolCancelledOutcome` → EventLog `raw_tool_outcome` → accepted result / memory / trace
- **LLM-facing 投影**: `ToolCancelledOutcome.hint` → tool message → LLM context

### 为什么是阻断

1. P1-C plan S2 明确要求："清理 Doc/Web cancellation messages 中的'宿主取消'以及 Doc/Web/Fins cancellation hints 中的'后续调度'"。Web hints 中的 "host cancelled" 是同一语义族的治理泄漏，未被清理是 scope 遗漏。
2. "host cancelled" 是英文 Host 治理术语，与 P1-C 清理的所有其他工具（Fins download/upload/preprocess/read、Doc）已改为中文业务可读文案不一致。
3. `[continue_without_web]` 前缀是内部代码风格标注混入 LLM-facing 文本。
4. 实现 artifact 的 residual scan 命令未覆盖 `dayu/tools/` 目录，也未搜索英文 "host cancelled"，导致此泄漏未被发现。

### 建议修复位置

修复应在 hint 的 owner boundary（Web tool callable 和 `web_search_providers`）执行：

- `dayu/tools/web/web_tools.py:1343-1346`、`:1365-1368` — 将 search 取消 hint 改为业务可读中文，如 `"当前工具调用已停止；如仍需要该结果，请等待用户确认后再重新发起。"`（与 Fins/Doc 一致）
- `dayu/tools/web/web_tools.py:1448-1451`、`:1462-1465` — 同上
- `dayu/tools/web/web_tools.py:744-746` — `_raise_fetch_cancelled()` 的 hint 改为业务可读中文
- `dayu/tools/web/web_search_providers.py:323-325` — `_cancel_if_requested()` 的 hint 改为业务可读中文
- 建议抽取一个共享常量（如 `_WEB_CANCELLED_HINT`）放在 `web_tools.py` 中复用，避免 6 处独立文案不一致

---

## F-2 (MEDIUM — 非阻断): `_PAYLOAD_FIELD_EVIDENCE_KIND` 死代码

### 直接证据

- `dayu/host/compact_material.py:120`: `_PAYLOAD_FIELD_EVIDENCE_KIND = "evidence_kind"` — 定义后在文件中仅此 1 次出现，无任何实际引用
- `dayu/host/run_input.py:196`: `_PAYLOAD_FIELD_EVIDENCE_KIND = "evidence_kind"` — 同上

P1-C 从 `_candidate_facts_texts()`、`_snapshot_fact_texts()` 和 `_accepted_compact_fact_lines()` 移除了 `evidence_kind` 渲染后，这两个常量成为死代码。

### Owner boundary

- **首次产生**: compact material / run input 模块各自定义
- **校验**: 无消费者，无法触发校验
- **影响**: 无行为影响，但违反 CLAUDE.md "禁止兼容性代码" 规则

### 建议修复位置

- `dayu/host/compact_material.py:120` — 移除 `_PAYLOAD_FIELD_EVIDENCE_KIND`
- `dayu/host/run_input.py:196` — 移除 `_PAYLOAD_FIELD_EVIDENCE_KIND`
- 注意：`dayu/host/compaction.py` 中 `EvidenceBackedFactCandidateVNext.evidence_kind` 字段仍保留为 Host-owned typed value，这与 dead constant 是不同的概念，不应删除

---

## F-3 (LOW — 非阻断): `FactEvidenceKindVNext.TOOL_RESULT` 与 `TOOL_SOURCE_TEXT` 枚举值不再被赋值

### 直接证据

`FactEvidenceKindVNext` 枚举定义于 `dayu/host/compaction.py:217-220`，包含三个值：

```python
TOOL_RESULT = "tool_result"
TOOL_SOURCE_TEXT = "tool_source_text"
ACCEPTED_EVIDENCE_MATERIAL = "accepted_evidence_material"
```

P1-C 后，`llm_compaction.py:110` 将所有 fact candidate 的 evidence kind 固定为 `_HOST_DERIVED_FACT_EVIDENCE_KIND = FactEvidenceKindVNext.ACCEPTED_EVIDENCE_MATERIAL`。`TOOL_RESULT` 和 `TOOL_SOURCE_TEXT` 在整个 codebase 中不再被赋值。

### Owner boundary

- **首次产生**: `dayu/host/compaction.py` 定义
- **赋值**: 仅 `llm_compaction.py:110` 引用 `ACCEPTED_EVIDENCE_MATERIAL`
- **影响**: 非阻断。Host-derived strategy 选择单一值是正确的——当前所有 evidence facts 来自 evidence material section。如果未来需要多 section 区分，再扩展 parser

### 建议

- 在 P2-B 或后续 cleanup 中评估是否保留另外两个枚举值，或在 design.md 中记录当前单一值策略

---

## F-4 (LOW — 非阻断): Process-path 取消 envelope 含内部治理文案

### 直接证据

`dayu/tools/web/web_tools.py:505-509`:

```python
except (WebToolCancelledError, WebSearchCancelledError):
    return _web_process_failed_envelope(
        error_type="execution_error",
        message=f"Tool {self.tool_name!r} execution was interrupted inside child process.",
        hint="Parent ToolRuntime owns cancellation and timeout closeout.",
    )
```

`message` 含 `"child process"` 实现细节，`hint` 含 `"Parent ToolRuntime owns cancellation and timeout closeout."` 治理术语。该 path 通过 `ProcessToolEnvelope` 返回给父进程 `ToolRuntime`。

### Owner boundary

当前 `ProcessToolEnvelope` 仅定义在 `dayu/contracts/tool_execution.py`，未被 `dayu/host/` 消费——父进程 ToolRuntime 的实际 envelop 处理逻辑未在本次搜索中找到。如果未来 ToolRuntime 将 envelop 的 message/hint 直接投影到 `ToolFailedOutcome`，则此文案将泄漏到 LLM。

### 影响

非阻断。process path 当前可能未在生产中使用（`ProcessToolEnvelope` 未被 Host 消费），且父进程 ToolRuntime 应有自己的 LLM-facing 文案生成逻辑。但文案本身是治理泄漏，应在 Web tool process 重构时一并修复。

---

## P1-A / P1-B 保护确认（通过）

### P1-A accepted_result_projection 保护

三个 consumer 文件仍通过直接 import 引用 P1-A projection helper：

| 文件 | 行号 | 引用方式 |
|---|---|---|
| `dayu/host/compact_material.py` | 48, 2272 | `from dayu.host.accepted_result_projection import project_accepted_tool_result` |
| `dayu/host/run_input.py` | 126, 3829 | 同上 |
| `dayu/host/memory.py` | 1712, 1717 | lazy import from `dayu.host.accepted_result_projection` |

P1-C 未修改这些 import、未重新推导 query/status/source/result、未用 LLM-facing 文案替代 typed projection contract。

### P1-B lifecycle / cancel durable truth 保护

- `TOOL_CANCELLED_REASON_HOST_CANCELLED` 语义未改变
- `host_cancelled_outcome()` 仍固定 `reason=TOOL_CANCELLED_REASON_HOST_CANCELLED`
- 取消 durable schema（EventLog、`host_runs.cancel_request_event_id`）未被 P1-C 触及
- P1-C 只修改了 LLM-facing `message`/`hint` 文本，不改 typed reason 或 durable truth

---

## 逐项 Review 重点判定

### 1. 第一性原理判断 P1-C 动机是否仍成立，是否被过度修复

**成立，未被过度修复。** Compaction prompt 不再要求 LLM 输出 Host evidence pipeline enum，RunInput 不再渲染 `evidence_kind=...` 到 SystemMessage，Fins/Doc 取消文案已改为业务可读。Web 工具 hints 是唯一未被清理的治理泄漏（见 F-1）。

### 2. Owner boundary 修复位置

| 语义族 | Owner | 修复位置 | 判定 |
|---|---|---|---|
| Compaction trace kind | Host compact material builder | `compact_material.py` / prompt / `compaction.py` | ✅ 正确 |
| Compaction fact evidence kind | Host parser | `llm_compaction.py` / prompt | ✅ 正确（Host-derived strategy） |
| Conversation Memory fact rendering | Host RunInput projection | `run_input.py` | ✅ 正确 |
| Accepted compact fallback rendering | Host RunInput fallback codec | `run_input.py` | ✅ 正确 |
| Fins startup failure wording | Fins tool callable | `download_tools.py` / `upload_tools.py` / `preprocess_tools.py` | ✅ 正确 |
| Fins/read cancellation outcome text | Fins tool callable | `fins_tools.py` / `read_runtime_helpers.py` | ✅ 正确 |
| Doc cancellation outcome text | Doc tool callable | `doc_tools.py` | ✅ 正确 |
| Runtime host-cancelled default | Runtime helper → Caller-owned | `tool_call_projection.py` → 各 call site | ✅ 正确 |
| Web cancellation hint text | Web tool callable / search provider | `web_tools.py` / `web_search_providers.py` | ❌ 遗漏（见 F-1） |
| ToolRuntime governed failure text | ToolRuntime | `tool_runtime.py` | ✅ 正确 |
| Duplicate governance awaiting fanout | Host duplicate policy | `tool_duplicate_governance.py` | ✅ 正确 |

### 3. LLM-facing 文本：Host/wait/poll/adapter/governance 泄漏检查

- `base/tools.md` `等待工具结果` — 保留合理。Litmus test: 删除后模型更可能假设同步完成。✅
- `awaiting adapter binding is not configured` — 已改为 `"该工具当前无法启动后台任务；请改用已可用的工具或稍后重试。"` ✅
- `poll awaiting requires a durable external job ref` — message 已改为 `"该工具后台任务未返回可跟踪的任务引用；请稍后重试或联系系统维护者。"` ✅
- `tool execution cancelled before completion` — 已改为 `"工具调用在完成前已停止"` ✅
- Web "host cancelled" hints — ❌ 遗漏（见 F-1）

### 4. `evidence_kind` Host-derived strategy

- LLM 不再输出 `evidence_kind` 字段 ✅
- Parser 在 label quality check 通过后固定派生 `FactEvidenceKindVNext.ACCEPTED_EVIDENCE_MATERIAL` ✅
- Quality checker 已校验 evidence labels 只引用 evidence material section，派生安全 ✅
- Durable typed contract (`EvidenceBackedFactCandidateVNext.evidence_kind`) 保留为 Host-owned internal value ✅
- Memory (`MemoryEvidenceBackedFactKind.DERIVED_FROM_EVIDENCE`) 独立分类，未被破坏 ✅

### 5. Cancellation: `ToolBusinessCancelled` 与 `host_cancelled_outcome` message/hint 覆盖

- `host_cancelled_outcome()`: message/hint 改为必填非空，blank 值触发 `ValueError` ✅
- `ToolBusinessCancelled`: message/hint 改为必填非空，`__post_init__` 校验空白抛出 `ValueError` ✅
- `_DEFAULT_HOST_CANCELLED_MESSAGE` / `_DEFAULT_HOST_CANCELLED_HINT` 已删除 ✅
- `_blank_to_default_optional()` 已删除 ✅
- Fins download/upload/preprocess `_cancelled_outcome()`: 直接构造 `ToolCancelledOutcome`，使用 module 级 `_CANCELLED_MESSAGE` / `_CANCELLED_HINT`（非空常量）✅
- Fins read tools: `raise_fins_cancelled()` / `host_cancelled_outcome()` 使用显式非空文案 ✅
- Doc tools: `ToolBusinessCancelled(message=..., hint=...)` 显式非空 ✅
- Web tools: message 已更新（`_WEB_SEARCH_CANCELLED_MESSAGE` / `_WEB_FETCH_CANCELLED_MESSAGE`），hint 未更新 ❌（见 F-1）
- 无兼容 fallback、无空白默认、无测试掩盖 ✅

### 6. P1-A / P1-B preservation

✅ 通过（见上文详细确认）。

### 7. README 决策

- `dayu/host/README.md`: 不更新。当前 README 已描述 Host 拥有 memory/context governance 和 accepted-result projection，P1-C 未新增稳定 Host developer interface。✅
- `dayu/fins/README.md`: 不更新。当前 README 已描述 Fins 暴露业务语义工具结果，Host/ToolRuntime 拥有 wait/cancel governance。✅
- `dayu/config/README.md`: 不更新。它描述 config/prompts 目录职责，不描述单个 compact prompt 字段。✅
- `tests/README.md`: 不更新。测试层级、运行规则、维护规则未变。✅
- `docs/host/design.md`: 已更新。记录 `user_visible_progress` trace kind 和 Host-derived internal evidence kind。✅

### 8. 测试充分性、pyright、scan residual 分类

- 测试: `1119 passed, 2 skipped` — 覆盖 compaction prompt scan 断言、parser Host-derived evidence kind、RunInput memory/fallback 不再渲染 evidence_kind、`host_cancelled_outcome` / `ToolBusinessCancelled` fail-fast ✅
- pyright: `0 errors, 0 warnings, 0 informations` ✅
- `git diff --check`: 通过 ✅
- scan residual 分类:
  - `poll`/`adapter`/`wait id` 在 Host/runtime 实现和测试中保留为 internal — 正确 ✅
  - `evidence_kind` 在 typed contract / test fixture 中保留为 Host internal — 正确 ✅
  - `duplicate`/`governance` 在 Host 实现和配置中保留为 internal — 正确 ✅
  - **但是**: scan 命令未覆盖 `dayu/tools/` 目录且未搜索英文 "host cancelled"，导致 F-1 泄漏未被发现 ❌

---

## Residual Risks / Test Gaps

| ID | Severity | 描述 | Owner |
|---|---|---|---|
| R-1 | MEDIUM | **Web cancellation hint governance leakage scan 不完整。** Implementation artifact 的 scan 命令覆盖了 `dayu/config dayu/fins dayu/host dayu/runtime tests`，但未覆盖 `dayu/tools/`。英文 "host cancelled" 不在搜索 pattern 中。修复 F-1 后，应将 `dayu/tools/` 加入 scan scope 并在 pattern 中加入英文治理词。 | P1-C fix gate |
| R-2 | LOW | **`_PAYLOAD_FIELD_EVIDENCE_KIND` 死代码**（F-2）。两个常量定义无消费者。 | P2-B cleanup |
| R-3 | LOW | **`FactEvidenceKindVNext.TOOL_RESULT` / `TOOL_SOURCE_TEXT` 枚举值死代码**（F-3）。当前 strategy 只用 `ACCEPTED_EVIDENCE_MATERIAL`。 | P2-B cleanup |
| R-4 | LOW | **无端到端 compaction smoke 测试。** 现有测试覆盖 parser/contract/material/run_input，但没有真实 LLM 调用的 compaction 测试验证 prompt 变更后 LLM 是否按预期不输出 `evidence_kind`。P1-C 的核心理由是 LLM 不应输出内部枚举——这个假设应在真实 LLM 上验证。 | 后续 WU 或 manual smoke |
| R-5 | LOW | **Web 取消 hint 文案不一致。** Fins/Doc 使用共享常量，Web 在 6 处独立写 inline hint。修复 F-1 时应抽取共享常量。 | P1-C fix gate |
| R-6 | INFO | **Process-path cancellation envelope 文案含治理术语**（F-4）。当前 `ProcessToolEnvelope` 未被 Host 消费，但如果未来 ToolRuntime 直接投影 envelop message/hint 到 LLM，需额外审计。 | Web tool process 重构 |

---

## Propagation Audit（补充确认）

| 语义 | 产生 | 校验 | 持久化 / 诊断 | LLM-facing 投影 | 一致性 |
|---|---|---|---|---|---|
| Compaction trace kind | `compact_material.py` → `TraceReadableKindVNext.USER_VISIBLE_PROGRESS` | `test_compact_material.py` 断言 `user_visible_progress` | compact material payload | prompt `trace_kind=user_visible_progress` | ✅ 一致 |
| Compaction fact evidence kind | `llm_compaction.py` → `_HOST_DERIVED_FACT_EVIDENCE_KIND` | quality checker label validation → parser fixed derive | `EvidenceBackedFactCandidateVNext.to_json()` | prompt 不再要求输出；RunInput 不再渲染 | ✅ 一致 |
| Fins start failure wording | `download_tools.py` / `upload_tools.py` / `preprocess_tools.py` → `"X任务未能启动。"` | Fins ingestion tool tests | `ToolFailedOutcome` → EventLog | tool message → LLM | ✅ 一致 |
| Fins cancellation hint | `fins_tools.py:_FINS_CANCELLED_HINT` / `read_runtime_helpers.py:raise_fins_cancelled` | Fins/Doc cancellation tests | `ToolCancelledOutcome` | tool message → LLM | ✅ 一致（3 处文案相同） |
| Doc cancellation | `doc_tools.py:ToolBusinessCancelled(message=..., hint=...)` | runtime + doc tool tests | `ToolCancelledOutcome` | tool message → LLM | ✅ 一致 |
| Runtime cancelled helper | `tool_call_projection.py:host_cancelled_outcome(message, hint)` required non-empty | runtime tests fail-fast for blank | `ToolCancelledOutcome` | tool message → LLM | ✅ 一致 |
| Web cancellation message | `web_tools.py:_WEB_SEARCH_CANCELLED_MESSAGE` / `_WEB_FETCH_CANCELLED_MESSAGE` | （message 正确） | `ToolCancelledOutcome` | tool message → LLM | ✅ message 一致 |
| Web cancellation hint | `web_tools.py` / `web_search_providers.py` inline hints | ❌ 无（含 "host cancelled"） | `ToolCancelledOutcome` | tool message → LLM | ❌ 不一致（见 F-1） |
| Duplicate awaiting fanout | `tool_duplicate_governance.py:DuplicateGovernanceMessages.awaiting_fanout` | duplicate tests | diagnostic JSON | 不进入 LLM context（S0 分类为 internal-diagnostic） | ✅ 一致 |
| ToolRuntime governed failure | `tool_runtime.py` governed messages | ToolRuntime tests | `ToolFailedOutcome` / diagnostic | tool message → LLM | ✅ 一致 |
| P1-A accepted-result projection | `accepted_result_projection.py` | existing projection tests | EventLog/payload/memory | trace/run input/compact | ✅ 未改变 |
| P1-B lifecycle/cancel durable | P1-B contract | existing lifecycle tests | EventLog / run row | public HostEvent | ✅ 未改变 |

---

## 验证命令复跑

Controller validation 已确认以下通过：

- `pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/runtime tests/fins tests/tools` → `1119 passed`
- `pytest tests/runtime/test_tool_call_projection.py` → `20 passed`
- `pyright` → `0 errors`
- `git diff --check` → passed

AgentDS 额外验证：
- `grep -rn "host cancelled" dayu/tools/web/` → 6 hits（F-1 证据）
- `grep -rn "project_accepted_tool_result" dayu/host/{compact_material,run_input,memory}.py dayu/host/durable/memory.py` → 4 处引用（P1-A 保护确认）
- `_DEFAULT_HOST_CANCELLED_MESSAGE` / `_DEFAULT_HOST_CANCELLED_HINT` / `_blank_to_default_optional` → 全量清除确认
- Governance scan `等待状态|未进入等待状态|后续调度|宿主取消|不要把本次取消视为业务失败|awaiting adapter|poll awaiting|tool execution cancelled before completion` → 0 hits（中文治理词全量清除确认）
