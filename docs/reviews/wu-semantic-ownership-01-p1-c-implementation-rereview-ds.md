# WU-SEMANTIC-OWNERSHIP-01 P1-C Implementation Re-Review — AgentDS

## 结论

**pass**

F-1（Web 取消 hint 泄漏 "host cancelled"）已完全修复。F-2（`_PAYLOAD_FIELD_EVIDENCE_KIND` 死常量）已完全移除。控制器裁决的 fix 范围正确、落在 owner boundary、无新增阻断问题。P1-C F-1/F-2 已关闭。

---

## Re-Review 重点逐项判定

### 1. F-1 是否完全修复：Web cancellation hint 不再包含 Host 治理词

**已完全修复。**

#### 1.1 Source-of-truth

新增 `dayu/tools/web/web_cancellation_text.py` 作为 Web 工具取消 hint 的唯一真源：

```python
WEB_CANCELLED_HINT: Final[str] = "当前工具调用已停止；如仍需要该结果，请等待用户确认后再重新发起。"
```

文本不含 "host cancelled"、"Host cancelled"、"The host cancelled"、"[continue_without_web]" 或任何 Host 治理词。与 Fins/Doc 取消文案语义一致。

#### 1.2 调用点覆盖审计（全部 8 处使用共享常量）

| # | 文件:行号 | 路径 | 修复后 hint | 状态 |
|---|---:|---|---|---|
| 1 | `web_tools.py:1341` | search pre-lock cancel → `host_cancelled_outcome()` | `WEB_CANCELLED_HINT` | ✅ |
| 2 | `web_tools.py:1360` | search post-lock cancel → `host_cancelled_outcome()` | `WEB_CANCELLED_HINT` | ✅ |
| 3 | `web_tools.py:1378` | search `WebSearchCancelledError` handler → `host_cancelled_outcome()` | `WEB_CANCELLED_HINT`（替代 `exc.hint`） | ✅ |
| 4 | `web_tools.py:1440` | fetch pre-lock cancel → `host_cancelled_outcome()` | `WEB_CANCELLED_HINT` | ✅ |
| 5 | `web_tools.py:1451` | fetch post-lock cancel → `host_cancelled_outcome()` | `WEB_CANCELLED_HINT` | ✅ |
| 6 | `web_tools.py:1466` | fetch `WebToolCancelledError` handler → `host_cancelled_outcome()` | `WEB_CANCELLED_HINT`（替代 `exc.hint`） | ✅ |
| 7 | `web_tools.py:745` | `_raise_fetch_cancelled()` → `WebToolCancelledError` | `WEB_CANCELLED_HINT` | ✅ |
| 8 | `web_search_providers.py:325` | `_raise_if_search_cancelled()` → `WebSearchCancelledError` | `WEB_CANCELLED_HINT` | ✅ |

#### 1.3 Exception handler 投影边界修复

关键修复：search 和 fetch 的 exception handler 不再信任 `exc.hint`（异常内部携带的 hint 可能来自 cancel_reason 或未清理的遗留文本），而是统一投影为共享常量 `WEB_CANCELLED_HINT`：

- `_call_search_web`: `hint=WEB_CANCELLED_HINT`（替代 `hint=exc.hint`）
- `_call_fetch_web_page`: `hint=WEB_CANCELLED_HINT`（替代 `hint=exc.hint`）

这是 owner boundary 正确修复模式：Web callable 作为 LLM-facing 投影 owner，在 `host_cancelled_outcome()` 边界统一替换异常内部 hint 为业务可读文本。

#### 1.4 Message 文本同步清理

- `_WEB_SEARCH_CANCELLED_MESSAGE`: `"网页搜索工具调用已被宿主取消。"` → `"网页搜索工具调用已停止。"`（移除"宿主"）✅
- `_WEB_FETCH_CANCELLED_MESSAGE`: `"网页抓取工具调用已被宿主取消。"` → `"网页抓取工具调用已停止。"`（移除"宿主"）✅

#### 1.5 扫描验证

```
rg -n "host cancelled|Host cancelled|The host cancelled|continue_without_web" dayu/tools/web/
```

**零命中**（仅 `web_recovery.py:15` 的 `NEXT_ACTION_CONTINUE_WITHOUT_WEB = "continue_without_web"` 为内部 action code，不进入 LLM-facing 文本；对应的 LLM-facing `_REASON_HINTS` 为业务可读中文）。

```
rg -n "宿主取消|不要把本次取消视为业务失败|后续调度|未进入等待状态|awaiting adapter|poll awaiting|tool execution cancelled before completion"
```

**全量零命中**。

#### 1.6 测试守卫

- `_FORBIDDEN_CANCEL_MESSAGE_PARTS` 新增 `"host cancelled"`、`"Host cancelled"`、`"continue_without_web"` — 任何 LLM-facing outcome 中出现这些词将触发测试失败。
- 3 处断言从 `assert "continue_without_web" in outcome.hint`（确认泄漏存在）改为 `assert outcome.hint == web_cancellation_text.WEB_CANCELLED_HINT`（确认使用共享常量）。
- `test_search_web_deep_cancelled_sanitizes_governance_hint`（line ~1079-1096）显式注入 `hint="[continue_without_web] Host cancelled."` 并断言 `_assert_no_governance_text` 通过——验证异常 handler 的投影边界正确替换了治理文本。

### 2. Web cancellation hint 的 source-of-truth 和 owner boundary

✅ **source-of-truth**: `web_cancellation_text.py:WEB_CANCELLED_HINT`，被 `web_tools.py` 和 `web_search_providers.py` 共同 import。

✅ **Owner boundary**: 修复落在 Web callable 的 LLM-facing 投影边界（`host_cancelled_outcome()` 调用点），不是下游测试掩盖。
- 异常 handler 显式替换 `exc.hint` 为共享常量——生产代码层面阻止泄漏。
- 测试只验证生产行为，不自己构造"正确" text。

### 3. F-2 是否完全修复：`_PAYLOAD_FIELD_EVIDENCE_KIND` 死常量

✅ **已完全移除**。

| 位置 | 状态 |
|---|---|
| `dayu/host/compact_material.py:120` | 常量定义已删除；`_candidate_facts_texts()` 和 `_snapshot_fact_texts()` 不再渲染 `evidence_kind=...` |
| `dayu/host/run_input.py:196` | 常量定义已删除；`_memory_evidence_fact_message()` 和 `_accepted_compact_fact_lines()` 不再渲染 `evidence_kind=...` |

`rg -n "_PAYLOAD_FIELD_EVIDENCE_KIND" dayu/ tests/` → **零命中**。

✅ **Host typed evidence_kind 未被误删**: `dayu/host/compaction.py` 中 `EvidenceBackedFactCandidateVNext.evidence_kind` 字段（Host-owned typed contract）保留，与删掉的 `_PAYLOAD_FIELD_EVIDENCE_KIND`（LLM-facing 渲染常量）是不同的语义族。

### 4. `web_cancellation_text.py` 合规性

| 检查项 | 状态 |
|---|---|
| 模块中文 docstring | ✅ `"""Web 工具取消文案常量。"""` |
| `from __future__ import annotations` | ✅ |
| `Final` 类型注解 | ✅ `WEB_CANCELLED_HINT: Final[str]` |
| 常量中文 docstring | ✅ `"""Web 工具取消后投影给 LLM 的业务可读恢复提示。"""` |
| 分层正确 | ✅ 位于 `dayu/tools/web/`（Web tool package），只依赖 `typing.Final`，无反向依赖 |
| 单一真源 | ✅ 被 `web_tools.py` 和 `web_search_providers.py` 共同 import |
| 无过度设计 | ✅ 单一常量文件，朴素接口 |

### 5. 控制器裁决和 scan residual 分类可信度

✅ **控制器裁决可信**。

- F-1 fix 范围完整：覆盖 pre-lock、post-lock、provider cancellation、fetch fallback、exception handler 全部 5 类路径。
- F-2 fix 精确：只删 LLM-facing 渲染常量，不触 Host typed contract。
- 扫描已扩展至 `dayu/tools/` 并加入英文治理词 pattern，弥补初审扫描盲区。
- Residual hit 分类：
  - `web_recovery.py:15` `continue_without_web` — 内部 action code → ✅ internal
  - Docstrings 中的 "Host cancelled" — 内部文档 → ✅ internal
  - `_FORBIDDEN_CANCEL_MESSAGE_PARTS` 中的 "host cancelled" — 测试守卫 → ✅ 正确使用
  - 测试中显式注入治理文本 — 对抗性测试 → ✅ 正确使用

✅ **无新增阻断问题**。

---

## 补充验证

### 测试结果

```
pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py \
  tests/host/test_compact_material.py tests/host/test_run_input_builder.py \
  tests/runtime tests/fins tests/tools
→ 1119 passed, 2 skipped, 3 warnings
```

```
pytest tests/tools/web/test_web_tools_provider.py tests/runtime/test_tool_call_projection.py \
  tests/host/test_llm_compaction.py tests/host/test_compact_material.py \
  tests/host/test_run_input_builder.py
→ 237 passed, 1 skipped
```

### pyright

```
0 errors, 0 warnings, 0 informations
```

### 全量扫描

| 扫描目标 | pattern | 命中 | 分类 |
|---|---|---|---|
| 英文治理词 | `host cancelled\|Host cancelled\|The host cancelled\|continue_without_web` | 仅内部/测试 | ✅ |
| 中文治理词 | `宿主取消\|不要把本次取消视为业务失败\|后续调度\|未进入等待状态` | 零 | ✅ |
| ToolRuntime 治理 | `awaiting adapter\|poll awaiting\|tool execution cancelled before completion` | 零 | ✅ |
| 死常量 | `_PAYLOAD_FIELD_EVIDENCE_KIND` | 零 | ✅ |
| 死 helper | `_blank_to_default_optional` | 零 | ✅ |
| 默认 Host 文案 | `_DEFAULT_HOST_CANCELLED_MESSAGE\|_DEFAULT_HOST_CANCELLED_HINT` | 零 | ✅ |

---

## Propagation Audit（变更后确认）

| 语义 | 产生 | 校验 | LLM-facing 投影 | 一致性 |
|---|---|---|---|---|
| Web 取消 hint | `web_cancellation_text.py` 定义，`web_tools.py` / `web_search_providers.py` 引用 | Web provider tests + `_FORBIDDEN_CANCEL_MESSAGE_PARTS` | `ToolCancelledOutcome.hint` → tool message → LLM | ✅ 8 处统一 |
| Web 取消 message | `web_tools.py` `_WEB_SEARCH_CANCELLED_MESSAGE` / `_WEB_FETCH_CANCELLED_MESSAGE` | Web provider tests | `ToolCancelledOutcome.message` → tool message → LLM | ✅ 不再含"宿主" |
| evidence_kind LLM 渲染 | `run_input.py` / `compact_material.py`（已移除） | builder tests 断言 `"evidence_kind=" not in system_content` | 不再进入 SystemMessage / compact view | ✅ |
| Host typed evidence_kind | `compaction.py` `EvidenceBackedFactCandidateVNext` | compaction contract tests | 仅 durable typed value，不投影 | ✅ 未改变 |
| Runtime 取消 helper | `tool_call_projection.py` `host_cancelled_outcome(message, hint)` 必填 | runtime tests fail-fast for blank | 调用方显式提供，无默认 Host 文案 | ✅ |
| P1-A projection | `accepted_result_projection.py` | existing projection tests | run_input / compact_material / memory 仍引用 | ✅ 未改变 |
| P1-B cancel durable | P1-B contract | existing lifecycle tests | reason 不变 | ✅ 未改变 |

---

## 剩余非阻断 Residual Risks

| ID | Severity | 描述 | Owner |
|---|---|---|---|
| P1-C-R1 | LOW | `FactEvidenceKindVNext.TOOL_RESULT` / `TOOL_SOURCE_TEXT` 枚举值不再被活跃代码赋值（当前 strategy 只派生 `ACCEPTED_EVIDENCE_MATERIAL`）。不进入 LLM-facing 文本，不阻塞 P1-C。 | P2-B cleanup |
| P1-C-R2 | LOW | Process-path cancellation envelope（`web_tools.py:506-510`）仍含 `"child process"` / `"Parent ToolRuntime owns cancellation"` 内部术语。当前 `ProcessToolEnvelope` 未被 Host 消费为 LLM-facing outcome，不进入 LLM context。若未来 ToolRuntime 直接投影 envelop message/hint，需额外审计。 | Web process 重构 |
| P1-C-R3 | LOW | 无端到端 LLM compaction smoke 测试。现有测试覆盖 parser/contract/material/run_input，但未用真实 LLM 验证 prompt 变更后 compactor 是否按预期不输出 `evidence_kind`。 | 后续 WU 或 manual smoke |
| P1-C-R4 | INFO | Web 取消 hint 与 Fins/Doc 取消 hint 文本相同（`"当前工具调用已停止；如仍需要该结果，请等待用户确认后再重新发起。"`），但分别定义在 `dayu/tools/web/web_cancellation_text.py` 和 `dayu/fins/tools/fins_tools.py`。语义上各工具独立拥有取消文案，当前不构成同一语义多源问题；若未来统一工具取消文案，可考虑抽取跨包共享常量。 | 后续 cleanup |
| P1-C-R5 | INFO | `FactEvidenceKindVNext` 中 `TOOL_SOURCE_TEXT`（MiMo F-01）和 `TOOL_RESULT`（DS F-3）枚举值死代码。已在初审中标记为非阻断，控制器裁决为 deferred。 | P2-B cleanup |
