# WU-SEMANTIC-OWNERSHIP-01 P1-C Implementation Re-Review — AgentMiMo

## 结论

**pass**

F-1、F-2 已完全修复，无新增阻断问题。剩余均为 non-blocking residual risks。

## 1. Re-Review Scope

- 总控裁决修复：controller adjudication accepted F-1 (HIGH) 和 F-2 (MEDIUM)，deferred F-3/F-4/F-5
- 修复内容：
  - 新增 `dayu/tools/web/web_cancellation_text.py` 作为 Web 取消 hint 的 single source-of-truth
  - 更新 `web_tools.py` 7 处 hint 和 `web_search_providers.py` 1 处 hint 使用共享常量
  - 更新 `test_web_tools_provider.py` 断言共享 hint 并新增 forbidden pattern 检查
  - 移除 `compact_material.py` 和 `run_input.py` 中的 `_PAYLOAD_FIELD_EVIDENCE_KIND` 死常量
- Re-review 验证重点：F-1 完整性、F-2 完整性、新模块合规性、scan residual 可信度

## 2. F-1 验证：Web Cancellation Hint 泄漏是否完全修复

### 2.1 六处原始泄漏点逐一验证

| # | 原始位置 | 修复方式 | 验证 |
|---|---|---|---|
| 1 | `web_tools.py` search pre-lock cancel (`_call_search_web`) | `hint=WEB_CANCELLED_HINT` | ✅ diff 确认 line 1341 |
| 2 | `web_tools.py` search post-lock cancel (`_call_search_web`) | `hint=WEB_CANCELLED_HINT` | ✅ diff 确认 line 1360 |
| 3 | `web_tools.py` fetch pre-lock cancel (`_call_fetch_web_page`) | `hint=WEB_CANCELLED_HINT` | ✅ diff 确认 line 1440 |
| 4 | `web_tools.py` fetch post-lock cancel (`_call_fetch_web_page`) | `hint=WEB_CANCELLED_HINT` | ✅ diff 确认 line 1451 |
| 5 | `web_tools.py` `_raise_fetch_cancelled()` → `WebToolCancelledError.hint` | `hint=WEB_CANCELLED_HINT` | ✅ diff 确认 line 745 |
| 6 | `web_search_providers.py` `_raise_if_search_cancelled()` → `WebSearchCancelledError.hint` | `hint=WEB_CANCELLED_HINT` | ✅ diff 确认 line 325 |

### 2.2 Exception path 覆盖验证

`web_tools.py` 中两处 `except WebSearchCancelledError` / `except WebToolCancelledError` handler 原先透传 `exc.hint`，现在改为显式使用 `WEB_CANCELLED_HINT`：

- `web_tools.py:1378` search provider cancel handler: `hint=WEB_CANCELLED_HINT`（不再用 `exc.hint`）✅
- `web_tools.py:1466` fetch cancel handler: `hint=WEB_CANCELLED_HINT`（不再用 `exc.hint`）✅

即使 exception 对象携带旧 hint 文案，handler 也已覆盖为共享常量。DS review 中提到的 adversarial test fixture (`hint="[continue_without_web] Host cancelled."` at test line 1081) 正是验证此覆盖行为。

### 2.3 残余 scan 验证

controller 裁决后 scan 命令已扩展至 `dayu/tools` 并加入英文治理词 pattern：

```
rg -n "host cancelled|Host cancelled|The host cancelled|continue_without_web" dayu/ tests/
```

Re-review 独立 scan 结果（仅列 `dayu/tools/` 和 `tests/` 中相关命中）：

| 文件:行号 | 内容 | 分类 |
|---|---|---|
| `dayu/tools/doc_tools.py:2103` | docstring: `"把内部取消语义投影为 Host cancelled outcome。"` | internal docstring，非 LLM-facing |
| `dayu/tools/web/web_recovery.py:15` | `NEXT_ACTION_CONTINUE_WITHOUT_WEB = "continue_without_web"` | internal action code 常量，非 hint 文案 |
| `dayu/tools/web/web_tools.py:1098` | docstring: `"下一步动作（retry/change_source/continue_without_web）。"` | internal docstring |
| `tests/tools/web/test_web_tools_provider.py:83-85` | `_FORBIDDEN_CANCEL_MESSAGE_PARTS` 含 `"host cancelled"`, `"Host cancelled"`, `"continue_without_web"` | test 断言 enforcing fix |
| `tests/tools/web/test_web_tools_provider.py:1081` | `hint="[continue_without_web] Host cancelled."` | adversarial test fixture，验证 handler 覆盖 |
| `tests/fins/test_fins_storage_provider.py:986,1957` | docstring 含 `"Host cancelled outcome"` | internal docstring |

**无 LLM-facing 残留。** 所有命中均为 docstring、test fixture、或 internal constant。

### 2.4 F-1 结论

**完全修复。** 6 处原始泄漏 + 2 处 exception path 透传均已替换为 `WEB_CANCELLED_HINT` 共享常量。scan 范围已扩展至 `dayu/tools/` 并覆盖英文治理词。

## 3. F-2 验证：`_PAYLOAD_FIELD_EVIDENCE_KIND` 死常量是否移除

| 文件 | 原行号 | 状态 |
|---|---|---|
| `dayu/host/compact_material.py` | 120 | ✅ 已移除（diff 确认） |
| `dayu/host/run_input.py` | 196 | ✅ 已移除（diff 确认） |

独立 scan：`rg -n "_PAYLOAD_FIELD_EVIDENCE_KIND" dayu/ tests/` → 零命中。✅

`EvidenceBackedFactCandidateVNext.evidence_kind` typed 字段保留为 Host-owned internal value，未被误删。`llm_compaction.py` 现在固定派生 `_HOST_DERIVED_FACT_EVIDENCE_KIND = FactEvidenceKindVNext.ACCEPTED_EVIDENCE_MATERIAL`，不再从 LLM 输出解析。✅

### F-2 结论

**完全修复。** 死常量已移除，Host typed `evidence_kind` 字段未被误删。

## 4. 新增 `web_cancellation_text.py` 合规性

| 检查项 | 结果 |
|---|---|
| 模块 docstring（中文） | ✅ `"""Web 工具取消文案常量。"""` |
| 常量 docstring（中文） | ✅ `"""Web 工具取消后投影给 LLM 的业务可读恢复提示。"""` |
| 类型标注 | ✅ `Final[str]` |
| 分层 | ✅ 位于 `dayu/tools/web/`，属于 Web 工具包内部模块 |
| 反向依赖 | ✅ 无。仅被同包 `web_tools.py` 和 `web_search_providers.py` 通过 relative import 引用 |
| Single source-of-truth | ✅ 8 处生产调用点 + 3 处测试断言均引用同一常量 |
| `__init__.py` 导出 | 未导出。内部模块，relative import 使用，符合项目惯例 |

## 5. 总控验证与 Scan Residual 可信度

### 5.1 测试验证

- 独立运行 targeted tests: `237 passed, 1 skipped` ✅
- 全量 suite: `1119 passed, 2 skipped, 3 warnings` ✅
- pyright: `0 errors, 0 warnings, 0 informations` ✅
- `git diff --check`: passed ✅

### 5.2 Scan residual 分类审计

controller 裁决后 scan 覆盖 `dayu/config dayu/fins dayu/host dayu/runtime dayu/tools tests`，pattern 包含英文治理词。Re-review 独立验证残余命中分类：

| 残余模式 | 分类 | 可信度 |
|---|---|---|
| `poll`/`adapter`/`wait id` in Host/runtime 实现和测试 | internal runtime governance | ✅ 可信 |
| `user_visible_run_state`/`tool_source_text`/`accepted_evidence_material` in enum 定义和测试 | internal typed contract | ✅ 可信 |
| `duplicate`/`governance` in Host policy 实现和测试 | internal governance | ✅ 可信 |
| `等待工具结果` in `base/tools.md` | business-readable allowed (litmus test 通过) | ✅ 可信 |
| `host cancelled`/`continue_without_web` in docstring 和 test fixture | internal docstring / test enforcing fix | ✅ 可信 |

无新增阻断问题。

## 6. Propagation Audit（F-1/F-2 修复后确认）

| 语义 | 产生 | 校验 | 持久化/诊断 | LLM-facing 投影 | 一致性 |
|---|---|---|---|---|---|
| Web cancellation hint | `web_cancellation_text.WEB_CANCELLED_HINT` | test assertions + forbidden pattern check | `ToolCancelledOutcome.hint` → EventLog | tool message → LLM | ✅ |
| Compaction evidence kind | `llm_compaction.py` Host derivation | parser/checker tests | typed `evidence_kind` in candidate JSON | 不进入 LLM | ✅ |
| Memory/fallback fact rendering | `run_input.py` projection | builder tests | memory snapshot | SystemMessage 无 `evidence_kind` | ✅ |
| 其他语义（P1-A/P1-B/Fins/Doc/Duplicate/ToolRuntime） | 未被 F-1/F-2 修复触及 | 既有测试覆盖 | 不变 | 不变 | ✅ |

## 7. Residual Risks

| ID | 风险 | 分类 | 建议 |
|---|---|---|---|
| P1-C-RR1 | `FactEvidenceKindVNext.TOOL_RESULT` / `TOOL_SOURCE_TEXT` 死枚举成员 | deferred cleanup | P2-B 或 cleanup WU 中移除 |
| P1-C-RR2 | LLM 在移除 `evidence_kind` 输出后的行为变化 | 需 real-env 验证 | 下次 real-env smoke 中观察 compaction 输出质量 |
| P1-C-RR3 | Process-path cancellation envelope (`web_tools.py:505-509`) 含 `"child process"` / `"Parent ToolRuntime"` 内部治理文案 | deferred (当前未被 Host 投影到 LLM) | Web process 执行 hardening 时修复 |
| P1-C-RR4 | `NEXT_ACTION_CONTINUE_WITHOUT_WEB` 作为 LLM-facing recovery action code 保留了 `continue_without_web` 字面量 | info — 这是 intentional recovery 语义，不是治理泄漏 | 无需修复；如未来 action code 命名规范变更可一并调整 |

## 8. 最终判定

**pass。** F-1 Web cancellation hint 泄漏已完全修复（6 处原始 + 2 处 exception path），F-2 死常量已移除，新模块符合分层/类型/docstring 要求，scan residual 分类可信，无新增阻断问题。P1-C implementation 可关闭。
