# WU-SEMANTIC-OWNERSHIP-01 P1-C Implementation Review — AgentMiMo

## 结论

**pass-with-findings**

无阻断 finding。3 个 non-blocking findings，2 个 residual risk items。

## 1. 动机 / 严重性判断

P1-C 动机仍成立，未被过度修复。

直接证据确认：(a) compaction prompt 旧 schema 要求 LLM 输出 `evidence_kind=tool_result|tool_source_text|accepted_evidence_material`，是 Host internal pipeline enum 的 LLM-facing 暴露；(b) `run_input.py` 的 `_memory_evidence_fact_message()` 和 fallback codec 将 `evidence_kind={fact.evidence_kind.value}` 渲染进 `SystemMessage`，确定性治理泄漏；(c) Fins download/upload/preprocess 启动失败含"未进入等待状态"，Fins/Doc/Web 取消含"宿主取消"/"后续调度"，runtime `host_cancelled_outcome()` 提供 Host-governance 默认文案；(d) `ToolBusinessCancelled` 的 optional message/hint + fallback 默认文案模式允许调用方不提供业务可读文本。

修复边界合理：只清理 LLM-facing schema/prompt/tool outcome 文案，不改变 P1-A accepted-result projection contract，不改变 P1-B lifecycle/cancel durable truth。

## 2. Owner Boundary 审计

| 语义族 | 事实 owner | 修复位置 | 评语 |
|---|---|---|---|
| Compaction trace kind | Host compact material builder | `compact_material.py:3180-3183`, `compaction.py:78`, `conversation_compaction_user.md` | ✅ 内部 `CompactMaterialBlockKind.USER_VISIBLE_RUN_STATE` → 投影为 `TraceReadableKindVNext.USER_VISIBLE_PROGRESS`，prompt 只暴露业务可读值 |
| Compaction evidence kind | Host parser from evidence labels | `llm_compaction.py:661-664`, prompt output schema | ✅ LLM 不再输出 `evidence_kind`；Host 在 parser 阶段固定派生 `ACCEPTED_EVIDENCE_MATERIAL` |
| Memory/fallback fact rendering | Host RunInput projection | `run_input.py:2347-2348`, `run_input.py:3441-3447` | ✅ `_memory_evidence_fact_message()` 和 `_accepted_compact_fact_lines()` 均不再渲染 `evidence_kind=...` |
| Fins startup failure | Fins tool callable | `download_tools.py`, `upload_tools.py`, `preprocess_tools.py` | ✅ 改为业务可读"任务未能启动"，去除"未进入等待状态" |
| Cancellation text | Business tool callable | Fins/Doc/Web call sites, `tool_call_projection.py` | ✅ `host_cancelled_outcome()` 和 `ToolBusinessCancelled` 改为必填非空 message/hint，移除 runtime 默认 Host 文案 |
| Duplicate governance | Host duplicate policy | `tool_duplicate_governance.py:108-110` | ✅ `awaiting_fanout` 改为业务可读"相同工具请求已有进行中的工具结果" |
| ToolRuntime governed failure | ToolRuntime policy decision | `tool_runtime.py` | ✅ LLM-facing message 改为业务可读"后台任务启动能力未配置"/"任务未返回可跟踪引用"/"工具调用在完成前已停止" |

## 3. Findings

### F-01 (INFO) — `FactEvidenceKindVNext.TOOL_SOURCE_TEXT` 枚举成员未清理

- **文件**: `dayu/host/compaction.py:87`
- **证据**: `TOOL_SOURCE_TEXT = "tool_source_text"` 仍在 `FactEvidenceKindVNext` 枚举中定义，但无任何活跃代码路径使用该值（`rg` 只命中定义行和测试 fixture 构造中的 `ACCEPTED_EVIDENCE_MATERIAL`）。
- **Owner boundary**: Host compaction typed enum，internal。
- **阻断判断**: 非阻断。implementation artifact 已将其分类为 `internal typed contract`。`ACCEPTED_EVIDENCE_MATERIAL` 仍被 Host derivation 使用，`TOOL_SOURCE_TEXT` 是未使用的枚举成员但不影响 LLM-facing 行为。
- **建议**: 未来 P2-B 或 cleanup WU 中移除死枚举成员以减少 scan noise。当前不阻塞。

### F-02 (INFO) — `CompactMaterialBlockKind.USER_VISIBLE_RUN_STATE` 内部命名保留

- **文件**: `dayu/host/compact_material.py:152`, `dayu/host/compact_material.py:3178`, `dayu/host/compaction.py:60`
- **证据**: `CompactMaterialBlockKind.USER_VISIBLE_RUN_STATE` 仍作为内部 block kind 使用，在 `_trace_material_vnext()` 中投影为 LLM-facing `user_visible_progress`。内部命名与 LLM-facing 值之间的映射在此处完成。
- **Owner boundary**: Host compact material builder，internal。
- **阻断判断**: 非阻断。这是正确的 owner boundary 设计：内部 block kind 可保留精确术语，投影边界负责 LLM-facing 语义改写。test fixture 使用该枚举值是测试正确行为。
- **建议**: 无。设计正确。

### F-03 (LOW) — `_runtime_cancelled_policy_decision` 诊断消息仍含英文

- **文件**: `dayu/host/tool_runtime.py:7414`
- **证据**: `message = "工具调用在完成前已停止"` 已改为中文，但同文件的 `_awaiting_configuration_failure()` 中 `message="该工具当前无法启动后台任务；请改用已可用的工具或稍后重试。"` 和 `_awaiting_external_job_failure()` 中 `message="该工具后台任务未返回可跟踪的任务引用；请稍后重试或联系系统维护者。"` 均为中文，而同函数 `_awaiting_external_job_failure()` 的 diagnostic emitter `message="awaiting binding did not produce external job ref"` 仍为英文。
- **Owner boundary**: diagnostic emitter 是 internal-only，不进入 LLM context。
- **阻断判断**: 非阻断。diagnostic message 不是 LLM-facing text。
- **建议**: 若后续统一 diagnostic 语言风格，可一并处理。

## 4. Cancellation 调用点覆盖审计

`ToolBusinessCancelled` 和 `host_cancelled_outcome()` 现在要求 message 和 hint 均为非空。验证所有调用点：

| 调用点 | message 来源 | hint 来源 | 状态 |
|---|---|---|---|
| `doc_tools.py:2095` `_doc_cancelled()` | `"文档工具调用已停止。"` | `_DOC_CANCELLED_HINT` (非空) | ✅ |
| `doc_tools.py:2117` `_cancelled_outcome()` | 透传 `cancellation.message` | 透传 `cancellation.hint` | ✅ |
| `web_tools.py:1381` search cancelled | `_WEB_SEARCH_CANCELLED_MESSAGE` (非空) | `exc.hint` (WebCancelledError) | ✅ |
| `web_tools.py:1475` fetch cancelled | `exc.message` (WebCancelledError) | `exc.hint` (WebCancelledError) | ✅ |
| `web_tools.py:1723` generic cancelled | caller-provided `message` | caller-provided `hint` | ✅ |
| `fins_tools.py:1016` Fins read cancelled | `exc.message` (FinsReadCancelledError) | `exc.hint` (非空) | ✅ |
| `fins_tools.py:1387` Fins helper cancelled | `"财报读取工具调用已被取消。"` | `_FINS_CANCELLED_HINT` (非空) | ✅ |
| `download_tools.py` start failure | `"下载任务未能启动。"` | 显式 hint | ✅ (ToolFailedOutcome, 非 cancelled) |
| `upload_tools.py` start failure | `"上传任务未能启动。"` | 显式 hint | ✅ (ToolFailedOutcome, 非 cancelled) |
| `preprocess_tools.py` start failure | `"预处理任务未能启动。"` | 显式 hint | ✅ (ToolFailedOutcome, 非 cancelled) |

无遗留调用点依赖 runtime 默认 Host 文案。`_blank_to_default_optional()` 已完全删除（`rg` 零命中）。

`ToolBusinessCancelled.__post_init__` 中 `self.message.strip() == ""` 校验覆盖空字符串和纯空白。fail-fast contract 正确。

## 5. P1-A / P1-B Preservation

- **P1-A accepted-result projection**: `rg -n "accepted_result_projection|AcceptedEvidenceEnvelope|AcceptedEvidenceToolQuery"` 在 `run_input.py`、`compact_material.py`、`memory.py` 均有命中，确认 P1-A projection helper 仍为 shared source-of-truth。P1-C 未重新推导 query/status/source/result 语义。
- **P1-B lifecycle/cancel durable truth**: `ToolCancelledOutcome.reason` 仍为 `TOOL_CANCELLED_REASON_HOST_CANCELLED`。P1-C 只清理 message/hint 文案，不改变 durable schema 或 terminal/cancel truth。
- **验证**: implementation artifact 和 controller validation 均确认上述 preservation。

## 6. `evidence_kind` Host Derivation 充分性

选择策略：Host 在 parser 阶段根据 evidence labels 所属 material section 固定派生 `FactEvidenceKindVNext.ACCEPTED_EVIDENCE_MATERIAL`。

充分性判断：

- 当前 compact contract 中 `evidence_backed_facts[*].evidence_labels` 只允许引用 `evidence_material` section 的 labels（quality checker 已验证）。
- 因此所有 accepted fact 的 evidence 来源都是 evidence material section，Host 派生 `ACCEPTED_EVIDENCE_MATERIAL` 是唯一正确值。
- 派生发生在 `llm_compaction.py:661-664`，在 label 验证之后，逻辑正确。
- `EvidenceBackedFactCandidateVNext.to_json()` 仍输出内部 `evidence_kind` 用于 durable persisted typed value，不影响 LLM-facing schema。
- design truth (`docs/host/design.md:3023`) 已更新记录"LLM-facing candidate 不输出 `evidence_kind`；Host 根据 evidence labels 所属 material section 派生内部 evidence kind"。

无破坏 memory / durable typed contract 风险。

## 7. LLM-facing 文本残留扫描

最终 targeted scan 分类：

| 模式 | LLM-facing 残留 | 评语 |
|---|---|---|
| `等待状态` / `未进入等待状态` | 零 LLM-facing 命中 | ✅ |
| `后续调度` | 零 LLM-facing 命中 | ✅ |
| `宿主取消` / `不要把本次取消视为业务失败` | 零 LLM-facing 命中 | ✅ |
| `awaiting adapter` / `poll awaiting` | 零 LLM-facing 命中（仅 diagnostic/internal） | ✅ |
| `tool execution cancelled before completion` | 零 LLM-facing 命中 | ✅ |
| `user_visible_run_state` | 仅 `compaction.py` enum 定义 + internal block kind + test | ✅ internal |
| `tool_source_text` / `accepted_evidence_material` | 仅 `compaction.py` enum 定义 + test fixture | ✅ internal |
| `evidence_kind=` | 仅 `llm_compaction.py` (Host derivation), `memory.py` (internal typed), tests | ✅ 不在 prompt/run_input SystemMessage 中 |
| `等待工具结果` | `base/tools.md` 中"调用后等待工具结果；结果会说明..." | ✅ business-readable allowed (litmus test 通过) |
| `duplicate` / `governance` | Host policy implementation/tests | ✅ internal |

## 8. README 决策

- `dayu/host/README.md`: 不更新。当前 README 已描述 Host 拥有 memory/context governance 和 accepted-result projection。P1-C 只改 prompt/tool 文案和 design detail，不改 developer-facing Host 接口。**成立**。
- `dayu/fins/README.md`: 不更新。当前 README 已描述 Fins 暴露业务语义结果、Host/ToolRuntime 拥有 wait/cancel governance。**成立**。
- `dayu/config/README.md`: 不更新。描述 config/prompts 目录职责，不描述单个 compaction prompt 字段。**成立**。
- `tests/README.md`: 不更新。无测试层级或维护规则变化。**成立**。

## 9. 测试充分性

- implementation report: `1119 passed, 2 skipped, 3 warnings` + `116 passed` (duplicate governance)。
- controller validation: `1119 passed, 2 skipped, 3 warnings` + `20 passed` (tool_call_projection)。
- 新增测试 `test_compaction_prompt_does_not_expose_internal_evidence_or_run_state_terms` 断言 prompt 中不出现内部枚举名。✅
- `test_parse_conversation_compact_output_vnext_derives_fact_evidence_kind` 验证 Host 派生 evidence kind。✅
- `test_host_cancelled_outcome_requires_explicit_message_and_hint` 和 `test_tool_business_cancelled_requires_explicit_message_and_hint` 验证 fail-fast contract。✅
- `test_run_input_builder.py` 的 `assert "evidence_kind=" not in system_content` 确认 SystemMessage 不再渲染内部字段。✅
- pyright `0 errors, 0 warnings, 0 informations`。✅
- `git diff --check` pass。✅

## 10. Residual Risk

| ID | 风险 | 分类 | 建议 |
|---|---|---|---|
| P1-C-R1 | `FactEvidenceKindVNext.TOOL_SOURCE_TEXT` 死枚举成员增加 scan noise | deferred cleanup | P2-B 或 cleanup WU 中移除 |
| P1-C-R2 | LLM 在移除 `evidence_kind` 输出后的行为变化——compactor 不再被要求分类 evidence kind，可能改变 compaction 输出分布 | 需 real-env 验证 | 下次 real-env smoke 中观察 compaction 输出质量 |

## 11. Propagation Audit Summary

| 语义 | 产生 | 校验 | 持久化/诊断 | LLM-facing 投影 | 一致性 |
|---|---|---|---|---|---|
| Compaction trace category | `compact_material.py` block kind | material tests | compact material payload | prompt `user_visible_progress` | ✅ |
| Compaction evidence kind | `llm_compaction.py` parser | parser/checker tests | accepted compact candidate typed | 不进入 LLM | ✅ |
| Memory fact rendering | `run_input.py` projection | builder tests | memory snapshot | SystemMessage 无 `evidence_kind` | ✅ |
| Fins startup failure | Fins tool callable | Fins tests | ToolFailedOutcome | 业务可读"任务未能启动" | ✅ |
| Cancellation text | business tool caller | runtime + domain tests | ToolCancelledOutcome | 业务可读停止/重试文案 | ✅ |
| Runtime cancelled helper | `tool_call_projection.py` | runtime tests | ToolCancelledOutcome | 调用方显式提供，无 Host 默认文案 | ✅ |
| Duplicate governance | `tool_duplicate_governance.py` | duplicate tests | policy decision / possible outcome | "相同工具请求已有进行中的工具结果" | ✅ |
| P1-A accepted-result projection | `accepted_result_projection.py` | existing projection tests | EventLog/payload/memory | 未被 P1-C 改写 | ✅ |
| P1-B lifecycle/cancel | P1-B durable contract | existing lifecycle tests | EventLog/run row | reason 不变，message/hint 清理 | ✅ |
