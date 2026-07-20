# WU-SEMANTIC-OWNERSHIP-01 PR 179 Deepreview — AgentDS

## Scope

- **Mode**: PR Review
- **PR**: 179 (draft)
- **Title**: WU-SEMANTIC-OWNERSHIP-01 umbrella remediation continuation
- **Author**: Leo Liu (noho)
- **Head**: `86174133b51f2e34cac5d93c4128d9b40a8c48b8`
- **Base**: `main`
- **Branch**: `phaseflow/host-issues-control`
- **Repository**: `noho/dayu-agent-r`
- **Output file**: `docs/reviews/wu-semantic-ownership-01-pr179-deepreview-ds.md`
- **Reviewer**: AgentDS
- **Date**: 2026-07-20

### Included scope

全部 2281 changed files（219 production Python files, ~2062 test/smoke/doc/config/CI files），含 GitHub Actions workflow YAML。

Production 模块覆盖：`dayu/host/`（~55 files）、`dayu/engine/`（~20 files）、`dayu/fins/`（~80 files）、`dayu/runtime/`（~19 files）、`dayu/service/`（~10 files）、`dayu/cli/`（~16 files）、`dayu/contracts/`（~4 files）、`dayu/tools/`（~22 files）、`dayu/documents/`（~4 files）、`dayu/config/`（prompts/manifests）。

### Excluded scope

- 非人工维护 artifacts（constraints/*.txt, lock files）。

### Review dimensions covered

1. 全量 production diff 逐文件走读（AgentDS 直接走读 + 6 subagent 并行深挖）
2. Engine contracts：finish_reason authority、usage identity、AgentPolicy prompt ownership、error_code typing
3. Host durable truth：EventLog、state machine、cancel linkage、terminal events、schema
4. Host projections：tool trace、evidence、memory、run input、compact material、outbox、read model
5. Fins contracts：preprocess/upload typed results、ingest_method、storage、tools
6. CLI/Service boundary：session resume、Fins direct missing RESULT、HostApiError
7. LLM-facing text：prompts、tool schemas、compaction、cancelled outcome
8. Runtime/config：config loader、assembly、tool_call_projection、AgentPolicy
9. Security：API key/headers exposure in tool trace/audit/public/log/LLM/review evidence
10. Semantic ownership drift：back-query、fallback、heuristic chain、loose parsing、blacklist
11. Test coverage：import boundaries、state machine、fixture patterns
12. Web tools：provider、egress、diagnostics

### Parallel review coverage

| Subagent | Scope | Status |
|----------|-------|--------|
| Engine + Runtime contracts | finish_reason, usage, AgentPolicy, config_loader, tool_call_projection | ✅ Completed |
| Fins contracts + tools | preprocess/upload typed results, ingest_method, storage, tools, domain | ✅ Completed |
| Host durable state machine | EventLog, state, run_transition, cancellation, admission, recovery, waiting | ✅ Completed |
| Host projection + LLM-facing | evidence, tool_trace, memory, run_input, compact_material, compaction, outbox | ✅ Completed |
| CLI/Service + Web tools | session, fins, host_assembly, web_tools, web_egress | ✅ Completed |
| Tests + config + prompts | import_boundary, state machine tests, fixtures, compaction prompt | ✅ Completed |

AgentDS 直接走读了全部关键 diff 并独立验证了以下区域：Engine runner_events/engine_events/agent_policy、Host engine_ingest/durable/state/run_transition/schema/event_log/lifecycle_events、Host tool_trace/evidence/accepted_result_projection/outbox/read_model、Runtime tool_call_projection/config_loader、Fins ingestion_runtime/document_models、CLI session/fins/host_api_errors、Compaction prompt/compact_material、Queue policy、Runner call manifest。

---

## Pre-review Context Verification

### Umbrella plan alignment

本 PR 是 WU-SEMANTIC-OWNERSHIP-01 umbrella remediation continuation。历史 umbrella plan（`docs/host/wu-semantic-ownership-01-umbrella-plan.md`）定义 P0-A 到 P2-C 共 8 个基线 sub-WU。Umbrella Section 8 要求在 P0-A 到 P2-C 完成后继续 full-repository deepreview 轮次（R01-R12），直至至少连续两轮无新增 accepted current-umbrella finding。R01-R12 全部已完成并签入本 PR。

经逐条核实，以下 umbrella 目标已在本 PR 中实现：

| Sub WU | 目标 | 状态 |
|--------|------|------|
| P0-A | Engine finish_reason authority + usage identity | **PASS** — `RunnerContentCompletedData.finish_reason` 已移除，`ContentCompleteData.finish_reason` 已移除，`RunnerUsageRecordedData.provider_request_id` 已添加 |
| P0-B | Fins preprocess/upload typed result contracts | **PASS** — `FinsIngestMethod` enum，typed preprocess summary，upload pipeline typed result |
| P1-A | Host accepted evidence/query/status typed projection | **PASS** — `accepted_result_projection.py` 新模块，`project_accepted_tool_result()` 单一入口 |
| P1-B | Host event type + cancellation durable contract | **PASS** — `lifecycle_events.py` 新模块，`RunRow.cancel_request_event_id` typed field，`RunQueuePolicy` enum |
| P1-C | LLM-facing governance leakage cleanup | **PASS** — compaction prompt 删除 `evidence_kind`，`trace_kind` 改为 `user_visible_progress`，Fins 工具文案清理 |
| P2-A | CLI/service boundary consistency | **PASS** — session.py 不再导入私有函数，HostApiError 集中化，CLI `_missing_result_event` 已删除 |
| P2-B | Memory/test contract hardening | **PASS** — import boundary tests 更新，memory projection 使用 typed `AcceptedToolEvidenceLLMMaterial` |
| P2-C | Config fallback prompt source of truth | **PASS** — `AgentPolicy.fallback_prompt`/`continuation_prompt` 改为必填，`AgentFallbackMode` 移至 `dayu.contracts` |

### R-series remediation additions (R01-R12, umbrella Section 8 后续 deepreview 轮次)

以下 R-series 新增能力已确认来自后续 full-repository deepreview 轮次，且正确 owner：

| Addition | Owner | Status |
|----------|-------|--------|
| `ProviderDiagnosticData` (Runner + Engine) | Runner/Engine event contracts | Properly owned |
| `ContextOverflowDetection` typed struct | Runner event contracts | Properly owned |
| `RunnerDiagnosticSeverity`/`RunnerDiagnosticSource` enums | Runner event contracts | Properly owned |
| `error_code` `str`→typed enum hardening | Engine/contracts | Properly owned |
| Schema CHECK constraint on `event_type` | Host durable schema | Properly owned |
| `PayloadDescriptorKind` enum | Host durable schema | Properly owned |
| `_runner_call_manifest.py` shared owner | Host internal | Properly owned |
| `compact_payload.py` typed compact semantic parsing | Host internal | Properly owned |
| `queue_policy.py` typed queue policy | Host admission | Properly owned |
| EventLog `parse_host_event_type()` validation | Host durable event_log | Properly owned |
| Schema version 20→23 | Host durable schema | Three rounds of schema hardening, properly owned |

### User 裁决锁定验证

- **Config/Host internal SQLite/EventLog API key**: 经审计全部关键路径，确认 API key/headers 未泄漏到 Tool Trace/audit/public/log/LLM/review evidence。Config 与 Host internal SQLite/EventLog 中存在的 API key/headers 属于 trusted-local domain，符合用户裁决。**PASS**
- **Gemini low-budget**: 在 diff 和测试文件中未发现 Gemini-specific quota 处理代码路径。按用户裁决归类为 `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`。**PASS**
- **R11/R12**:
  - R11 29713519099（explicit dispatch）与 R12 29713522620（explicit dispatch）已由 Controller 按 same-run contract 接受并 closed
  - 当前 PR head `86174133` 的自动 R11 run `29714042683` 和 R12 run `29714042672` 均为 **success**
  - 本 review 不重算、读取或回显 R12 canary 实际值；裁决链自洽。**PASS**
- **私网/端口默认策略**（Topic 2，用户指令）：私网与自定义端口由 `tool_discovery.json` 控制；默认 allow；DNS pin/peer proof 默认关闭。`True` 是产品裁决。**PASS**

### Topic closure status

| Topic | Closure | Evidence |
|-------|---------|----------|
| Topic 1-7 (P0-A to P2-C) | **Closed** — 全部 sub-WU 目标已实现 | 见上表 |
| Topic 8 | **No-code decision** — PR body | PR body Boundaries section |
| Topic 9 | **No-code decision** — PR body | PR body Boundaries section |
| Unified authorization framework | **Explicitly not implemented** — no-code boundary | PR body Boundaries section |
| Issue 142, 151, 175, 177, 178 | **Deferred** — owned by respective issue | PR body Boundaries section |
| Web/WeChat/render trackers | **Deferred** — owned by respective trackers | PR body Boundaries section |

---

## Findings

### 016-未修复-中-_governed_failure_outcome fallback 将 Host 治理错误码泄漏到 LLM-facing 文本

- **入口/函数**: `_governed_failure_outcome()`，`dayu/host/tool_runtime.py` 第 7206-7219 行
- **输入场景**: 非 `ALLOW` 的 `ToolPolicyDecision` 的 `message` 为 `None` 或空字符串时（当前所有 call site 均显式提供 message，但 fallback 仍作为 code path 存在）
- **实际分支**: `message=policy_decision.message or _TOOL_RUNTIME_GOVERNED_ERROR` → `"host_tool_governed_error"` 被写入 `ToolFailedOutcome.message`
- **预期行为**: LLM-facing 工具结果文本中不应出现 Host 内部治理术语。Owner 应 fail closed（`ValueError`），而非静默 fallback 到 Host governance 术语
- **实际行为**: 若 fallback 触发，`"host_tool_governed_error"` 会通过以下完整链路进入 LLM 上下文：`_governed_failure_outcome` → `ToolFailedOutcome(message="host_tool_governed_error")` → `accepted_tool_outcome_json` → EventLog → `project_accepted_tool_result` → `AcceptedToolEvidenceLLMMaterial.result_text` → `render_accepted_tool_evidence_for_llm()` → LLM 上下文 visible 文本
- **直接证据**: `dayu/host/tool_runtime.py:240` 定义 `_TOOL_RUNTIME_GOVERNED_ERROR = "host_tool_governed_error"`，第 7217 行 `message=policy_decision.message or _TOOL_RUNTIME_GOVERNED_ERROR`
- **影响**: Host 内部错误码会作为 LLM-facing 文本暴露给模型
- **唯一 owner**: `_governed_failure_outcome()` 是 `ToolFailedOutcome.message` 的 owner
- **建议改法和验证点**: 非 `ALLOW` decision 的 `message` 为 `None`/空时应 `raise ValueError`（fail closed），不允许进入 LLM-facing fallback。验证点：`ToolPolicyDecision` message=None + 非 ALLOW 的测试
- **修复风险**: 低 — 当前所有 call site 均显式提供 message，fail closed 不改变正常路径行为
- **严重程度**: 中

### 001-已裁决-已关闭-FinsReadProcessTarget finally 块 runtime.close() 覆盖业务成功结果是 accepted bounded failure contract

- **原 Finding 001**，经 Controller 裁决 **rejected-with-reason / closed**
- **直接证据**: `tests/fins/test_fins_storage_provider.py::test_fins_read_process_target_closes_runtime_on_success_and_failure` 明确冻结以下 bounded failure contract：
  - 首次 cleanup failure 在业务成功路径转换为 `execution_error`
  - 已有业务/异常失败保持 primary
  - close 两次
- **裁决来源**: `docs/reviews/wu-semantic-ownership-01-r07-s3-code-review-fix-codex.md` 与对应 Controller adjudication 已接受此 contract
- **分类**: rejected-with-reason / closed — 不得引入 metadata/log fallback

### 002-已裁决-已关闭-FinsPreprocessResultSummary.result_status catch-all SUCCEEDED 是 cancellation-safe partial summary

- **原 Finding 002**，经 Controller 裁决 **rejected-with-reason / closed**
- **直接证据**: `_bounded_preprocess_summary` 允许 `categorized_count < selected_count` 是 cancellation-safe partial summary 行为
- **裁决来源**: `docs/reviews/wu-semantic-ownership-01-p0-b-fix-codex.md` 及 P0-B Controller adjudication 已明确接受 `selected > categorized` 和 skipped-only success
- **分类**: rejected-with-reason / closed — 不得增加 equality check

### 017-已裁决-已关闭-dispatch drain loop HostTransactionRetryExhaustedError 是 transient backoff，不是 permanent failure

- **原 Finding 017**，经 Controller 裁决 **rejected-with-reason / closed**
- **直接证据**: R3-A plan DR-009 和 S3 Controller adjudication 冻结 `HostTransactionRetryExhaustedError` 为 transient：backoff/reconcile，不得 self-close/terminalize/cancel
- **裁决来源**: Topic 5 禁止无 authoritative typed lost outcome 时 LOST
- **分类**: rejected-with-reason / closed — 不得添加 circuit breaker/阈值/terminal closeout

### 019-已裁决-已关闭-Web egress 默认 allow 是产品裁决，非安全回退

- **原 Finding 019**，经 Controller 裁决 **rejected-with-reason / closed**
- **直接证据**: Controller discussion Topic 2 和用户指令明确：私网与自定义端口由 `tool_discovery.json` 控制，默认 allow；DNS pin/peer proof 默认关闭
- **裁决来源**: `True` 是产品裁决，不得改回 deny
- **分类**: rejected-with-reason / closed

### 003-已确认-无问题-non_stream_parser tool_call arguments 收紧为 str（协议正确性变更）

- **入口/函数**: `_coerce_final_tool_call()`，`dayu/engine/runners/openai/non_stream_parser.py`
- **分析**: OpenAI API 明确规定 `function.arguments` 必须是 JSON string。旧代码接受 `Mapping` 是过度宽松。新行为是正确的协议规范收紧。
- **分类**: nonfinding / closed

### 004-已确认-无问题-engine_ingest.py 规模观察（maintainability observation，no current action）

- **分析**: `engine_ingest.py` 7118 行，`EngineEventIngestor` 承担 Engine 事件摄入 + Host worker lifecycle closeout 双重职责。这是 P3-A/P3-B 计划将相关职责收敛到同一 ingest boundary 的架构选择结果。不创建 future WU，不引入新 scope。
- **分类**: nonfinding / maintainability observation / no current action

### 005-已确认-无问题-RejectedFilingArtifact.from_meta_dict ingest_method KeyError（producer 全部已迁移）

- **分类**: nonfinding / closed

### 006-已确认-无问题-CLI fins _missing_result_event fallback 已正确移除

- **分类**: nonfinding / closed

### 007-已确认-无问题-既有列举路径的 LLM-facing 治理文本已按 accepted remediation 清理

- **验证项**: Fins preprocess/download/upload 工具文案（"未进入等待状态"→"未能启动"）、`_FINS_CANCELLED_HINT`（"后续调度"→"等待用户确认"）、compaction prompt（`evidence_kind` 删除、`trace_kind`→`user_visible_progress`）、`host_cancelled_outcome`/`ToolBusinessCancelled`（message/hint 必填）、`_DEFAULT_HOST_CANCELLED_MESSAGE`/`_DEFAULT_HOST_CANCELLED_HINT` 移除、`fetch_more` description 中文业务语义
- **边界**: 本 nonfinding 仅覆盖上述已列举的 accepted remediation 路径，不覆盖本轮新候选 Finding 016（`_governed_failure_outcome` fallback）
- **分类**: nonfinding / closed

### 008-已确认-无问题-Host terminal event 三类语义已正确区分（lifecycle_events.py 单一 owner）

- **分类**: nonfinding / closed

### 009-已确认-无问题-cancel_request_event_id 已迁移到 typed durable state

- **分类**: nonfinding / closed

### 010-已确认-无问题-API key/headers 安全审计通过

- **分类**: nonfinding / closed

### 011-已确认-无问题-tool_trace 多级 fallback 已迁移为 typed projection

- **分类**: nonfinding / closed

### 012-已确认-无问题-run_input compact artifact 语义所有权已修复

- **分类**: nonfinding / closed

### 013-已确认-无问题-durable/memory MemoryProjectionEvent 迁移为 typed material

- **分类**: nonfinding / closed

### 014-已确认-无问题-ForwardIntent/ReferenceContinuityItem 迁移为 typed enum

- **分类**: nonfinding / closed

### 015-已确认-无问题-Schema version 20→23 三版本跳跃（有意的 schema 演进；fresh schema by Issue 142）

- **分类**: nonfinding / closed

### 018-已确认-无问题-_cancelled_eof_candidate 从 transient token 迁移到 durable typed read（语义所有权正确迁移）

- **分类**: nonfinding / closed

---

## Security Ledger

| # | Item | Status |
|---|------|--------|
| S1 | API key/headers in Tool Trace/audit/public/log/LLM/review evidence | **PASS** — 无泄漏 |
| S2 | API key/headers in Config + Host internal SQLite/EventLog | **PASS** — trusted-local domain |
| S3 | Provider credential in runner-call manifest | **PASS** — manifest hot atoms 不含 API key |
| S4 | Secret in EventLog payload | **PASS** — usage tokens only |
| S5 | Cancellation token exposure to LLM | **PASS** — typed durable state, not LLM-facing |
| S6 | Unified authorization framework | **PASS** — explicitly not implemented |
| S7 | Gemini low-budget quota | **PASS** — EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING |
| S8 | Web egress default allow policy | **PASS** — product decision, controlled by `tool_discovery.json` |

---

## No-code / Explicit Boundary Ledger

| # | Item | Disposition |
|---|------|-------------|
| N1 | Topic 8 | No-code decision |
| N2 | Topic 9 | No-code decision |
| N3 | Unified authorization framework | Explicitly not implemented |

## Deferred Ledger

| # | Item | Owner/Destination |
|---|------|-------------------|
| D1 | Issue 142 (migration) | Issue 142 |
| D2 | Issue 151 | Issue 151 |
| D3 | Issue 175 | Issue 175 |
| D4 | Issue 177 | Issue 177 |
| D5 | Issue 178 | Issue 178 |
| D6 | Web/WeChat/render trackers | Respective trackers |

---

## Residual Risk

1. **Finding 016 — `_governed_failure_outcome` fallback**: 中风险 — 当前所有 call site 均显式提供 message，fallback 不会被触发；但 code path 存在，若未来新增非 ALLOW decision call site 未提供 message，`"host_tool_governed_error"` 会进入 LLM context。修复风险低（fail closed 改为 `ValueError`）。

2. **Large file maintainability**: `engine_ingest.py` (7118 lines) 和 `test_web_tools_provider.py` 的单文件规模是长期维护观察点。当前不创建 action/future WU。

3. **Test coverage for new R-series additions**: `ProviderDiagnosticData`、`ContextOverflowDetection`、`RunnerDiagnosticSeverity` 等新增类型的 round-trip 测试覆盖率属于既有 design/review controlled 范围，无直接缺陷。

---

## Ledger Summary

### PASS/FAIL

**PASS** — PR 179 在以下维度通过审查：

- P0-A 到 P2-C 全部 8 个基线 sub-WU + R01-R12 全部 full-repository deepreview 轮次目标已正确实现
- 既有 accepted remediation 目标已关闭（back-query、fallback、heuristic chain、blacklist、loose parsing 已修复）
- LLM-facing 文本中既有 accepted Host 治理泄漏项已清理；本轮新增 Finding 016 仍待 Controller adjudication/fix
- API key/headers 安全控制已确认
- Terminal event 三类语义已正确区分
- Cancel linkage 已迁移到 typed durable state
- AgentPolicy prompt 双真源已消除
- R11/R12 Windows CI 均 success（29714042683、29714042672）
- Topic 8/9 no-code decisions 已确认
- Unified authorization framework explicitly not implemented

### Finding Ledger

| ID | Severity | Reviewer classification / Candidate | Status |
|----|----------|-------------------------------------|--------|
| 016 | 中 | Candidate (open pending Controller adjudication) | **Open** — 唯一 actionable finding |
| 001 | — | Rejected-with-reason | **Closed** — bounded failure contract accepted |
| 002 | — | Rejected-with-reason | **Closed** — cancellation-safe partial summary |
| 003 | — | Nonfinding | **Closed** — 协议正确性变更 |
| 004 | — | Nonfinding (maintainability observation, no action) | **Closed** |
| 005-015 | — | Nonfinding | **Closed** — 正确实现已确认 |
| 017 | — | Rejected-with-reason | **Closed** — transient backoff, no self-close |
| 018 | — | Nonfinding | **Closed** — 语义所有权正确迁移 |
| 019 | — | Rejected-with-reason | **Closed** — 产品裁决 allow |

### Final Counts

| Category | Count |
|----------|-------|
| **New actionable candidate** | **1** (Finding 016, 中) |
| Rejected-with-reason / closed | 4 (001, 002, 017, 019) |
| Nonfinding / closed | 14 (003-015, 018) |
| **Blocker** | **0** |
| **Pending** | **0** |
| **Unclassified residual** | **0** |

### Correct Next Gate

**Controller adjudication**（对 Finding 016 的 accept/reject/defer 裁决）。

不得 merge、mark-ready 或 final closeout。

---

*Review by AgentDS. 全部 6/6 subagent 并行审查已完成。Controller adjudication 已整合。*
