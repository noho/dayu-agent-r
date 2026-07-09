# WU-SEMANTIC-OWNERSHIP-01 P1-A Plan Re-Review — AgentDS

## Metadata

- Review type: narrow plan re-review (controller accepted findings closure check)
- Plan artifact: `docs/host/wu-semantic-ownership-01-p1-a-plan.md`
- Plan fix artifact: `docs/reviews/wu-semantic-ownership-01-p1-a-plan-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p1-a-plan-review-controller-adjudication.md`
- Primary review artifacts:
  - `docs/reviews/plan-review-20260709-p1-a-mimo.md`
  - `docs/reviews/plan-review-20260709-p1-a-ds.md`
- Review date: 2026-07-09
- Reviewer: AgentDS (re-review)

## Scope

本次为 narrow re-review，仅检查 controller accepted findings P1A-PLAN-F01 至 P1A-PLAN-F07 是否在 plan artifact 中闭合，以及 fix 是否引入新的 blocker。不改代码，不改文档，不提交。

## Conclusion

**`pass`**

全部 7 个 controller-accepted findings 已在 plan artifact 中闭合。未发现 fix 引入的新 blocker。

---

## Finding-by-Finding Closure Verification

### P1A-PLAN-F01: Tool Trace request summary 替代策略 — CLOSED

| Required fix (controller) | Plan 证据 |
|---|---|
| 明确选择窄方案：projection 拥有 query/status/source/result truth；Tool Trace 保留 display-only 参数渲染 | §4 明确选择窄方案 |
| Tool Trace 不能重新拥有 accepted query/status/source 语义 | §6 S2："不再直接回读 request atom 决定 query/status/source" |
| Checklist 区分 projection truth 与 trace 参数摘要 | §8 item 1："trace 参数摘要只保留 display-only 有界渲染/脱敏" |
| Propagation audit 确认 Tool Trace 参数摘要只是 display-only | §12 item 4 已补 |

验证通过。Tool Trace 的 `_tool_request_summary_from_tool_result()` 在 plan 中已有明确替代策略：projection helper 提供 query/status/source/result truth，Tool Trace 只保留 display-only 参数有界渲染/脱敏，不再直接回读 request atom。

---

### P1A-PLAN-F02: Read API PREVIEW vs CANONICAL_FACT 边界 — CLOSED

| Required fix (controller) | Plan 证据 |
|---|---|
| 明确 Read API 是否迁移到 canonical projection helper | §4 明确迁移到 canonical `TOOL_RESULT_ACCEPTED` projection helper |
| `_activity_from_row()` 新增 CANONICAL_FACT 显式分发 | §4："PREVIEW event class 仍按 preview payload 处理既有 activity，CANONICAL_FACT `TOOL_RESULT_ACCEPTED` 通过 projection helper 产生 activity status / summary，二者不得在同一 row 上互相 fallback" |
| `AcceptedToolResultStatus` → `HostActivityStatus` 映射 | §4 已补完整映射：`completed→COMPLETED`; `failed/governed_error/lost/unknown→FAILED`; `cancelled→CANCELLED`。`unknown` fail closed |
| Checklist 和 propagation audit | §8 item 2 / §12 item 5 已补 |

验证通过。Read API 的 event class 分发边界已明确：PREVIEW path 保持现有行为，CANONICAL_FACT path 通过 projection helper 产生 activity。两者不互相 fallback。

---

### P1A-PLAN-F03: `_readable_source_text_from_refs()` 处理 — CLOSED

| Required fix (controller) | Plan 证据 |
|---|---|
| S1/S2 显式处理该函数 | §6 S1："`compact_material._readable_source_text_from_refs()` 对 accepted result 的使用必须被 helper 输出替代" |
| 明确迁移/替代/保留边界 | §6 S2："accepted-result source 不再经 `_readable_source_text_from_refs()` 生产 `source_note`" |
| Validation grep 增加 `_readable_source_text_from_refs` 和 `source_note` | §9 grep 已增加；预期结果区分了允许命中（non-accepted initial material 边界）与禁止命中（accepted-result 调用） |
| Checklist | §8 item 6 已补 |

验证通过。`_readable_source_text_from_refs()` 对 accepted result 的使用被 helper 输出替代；non-accepted initial material 边界保留且有文档说明。Grep 预期结果对允许/禁止命中区分清楚。

---

### P1A-PLAN-F04: Conversation Memory unavailable-query fallback owner — CLOSED

| Required fix (controller) | Plan 证据 |
|---|---|
| 常量迁移到 projection helper | §4："`ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` 的 owner 迁移到 `accepted_result_projection.py`，作为 query typed limited-signal 的唯一定义" |
| Conversation Memory 不自行决定 fallback | §4："Conversation Memory 只能消费 projection `query_text` / `query_state`，不得根据 `event.evidence_query_text is None` 自行决定 fallback 条件" |
| 旧模块导入规则 | §4："旧模块若仍需要该文案只能从 projection owner 导入" |
| Checklist | §8 item 4 已补 |

验证通过。Conversation Memory 的 fallback 决策权已从消费者收回 projection helper。

---

### P1A-PLAN-F05: `AcceptedToolResultStatus` 映射与 `_tool_result_status()` — CLOSED

| Required fix (controller) | Plan 证据 |
|---|---|
| 映射表定义 ordinary/wait-resolution status field precedence | §4 已补完整 6 行映射表，覆盖 `completed`/`failed`/`cancelled`/`governed_error`/`lost`/`unknown` |
| 字段优先级 | §4："先读 canonical accepted status fields（wait-resolution 的 `resolution_kind` 高于 ordinary `tool_fact_kind`），再读 raw outcome 的 kind/result.ok 作为同一 helper 内的降级依据" |
| `_tool_result_status()` 处理 | §4："在 S2 中删除，或重构为只把 projection status 格式化为 Tool Trace 展示文本的 adapter；它不得继续读取 payload 字段推断 status" |
| S1 测试要求 | §6 S1/S3 已补 status mapping 测试要求 |

验证通过。Status 映射规则完整、优先级明确、`_tool_result_status()` 的去向已裁决。

---

### P1A-PLAN-F06: `InitialEvidenceMaterial` / `_evidence_blocks()` 边界 — CLOSED

| Required fix (controller) | Plan 证据 |
|---|---|
| 分类为 in-scope 或 non-goal | §5 明确 non-goal："不是 accepted-result projection owner，本轮不把它们改造成 EventLog accepted result 读取路径" |
| fixture 约束 | §5："若 S3 测试需要用 accepted tool result 构造 initial material，测试输入必须先经 projection helper 派生，不能在 fixture 内手写另一套 accepted query/source 语义" |
| S3 审计 | §6 S3："增加 grep / fixture 审计" |
| Checklist | §8 item 8 已补 |

验证通过。Initial material 边界已明确：不是 accepted-result projection owner，但 fixture 中的 accepted tool result 输入必须经 projection helper 派生。

---

### P1A-PLAN-F07: validation scans — CLOSED

| Required fix (controller) | Plan 证据 |
|---|---|
| grep 增加 `_readable_source_text_from_refs`、`source_note`、`tool_call_request_atoms` | §9 grep 已增加全部三个关键词 |
| 声明允许命中 | §9 预期结果："只允许新共享 helper 内部命中 `tool_call_request_atoms`、status/query/source projection 私有函数或 non-accepted initial material 边界命中" |
| 声明禁止命中 | §9 预期结果："消费者禁止命中旧私有 query/status/source helper、accepted-result `source_note` 生产、`_readable_source_text_from_refs` accepted-result 调用和 request atom back-query" |

验证通过。Validation grep 已扩展覆盖上游 source producer 和 request atom back-query 调用点，允许/禁止命中边界清晰。

---

## New Blocker Scan

对 fix 引入的新增内容做一致性检查，未发现新的 plan 级矛盾或缺口：

1. **窄方案一致性**：§4 窄方案（Tool Trace 保留 display-only 渲染）与 §6 S2 迁移要求一致，无矛盾。
2. **Status 映射完整性**：6 个状态值的映射规则已覆盖全部场景。Read API `unknown → FAILED`（fail closed）与 §4 的"不隐藏 accepted result"原则一致。
3. **Source 边界一致性**：`_readable_source_text_from_refs()` 允许在 non-accepted initial material 边界保留，与 §5 non-goal 和 §9 grep 预期三者一致。
4. **无 schema 变更依赖**：plan 仍选择不改 durable schema；stop condition §11.1 覆盖 implementation 发现必须改变时的处置路径。
5. **AgentCodex 注明的 residual risks**（governed_error 具体 durable 字段名待落实、source refs 丰富度不足、Tool Trace bounded rendering 分界）均为 implementation-stage risks，不构成 plan 级 blocker。

---

## Summary

| Finding | Status |
|---|---|
| P1A-PLAN-F01: Tool Trace request summary 替代策略 | CLOSED |
| P1A-PLAN-F02: Read API PREVIEW vs CANONICAL_FACT 边界 | CLOSED |
| P1A-PLAN-F03: `_readable_source_text_from_refs()` 处理 | CLOSED |
| P1A-PLAN-F04: Conversation Memory unavailable-query fallback owner | CLOSED |
| P1A-PLAN-F05: `AcceptedToolResultStatus` 映射与 `_tool_result_status()` | CLOSED |
| P1A-PLAN-F06: `InitialEvidenceMaterial` / `_evidence_blocks()` 边界 | CLOSED |
| P1A-PLAN-F07: validation scans | CLOSED |
| New blockers introduced by fix | NONE |

**Final verdict: `pass`**

Plan artifact 已 code-generation-ready。全部 7 个 controller-accepted findings 已闭合，无新增 blocker。
