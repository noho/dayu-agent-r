# WU-TOOL-02 Extra Full Repository Review — AgentMiMo

## Review Context

- Work unit: `WU-TOOL-02 Accept Candidate Structure Cleanup`
- Gate: ready-to-open-draft-PR 前置全仓 review
- Review mode: full repository review
- Branch: `refactor/wu-tool-02-accept-candidate-cleanup`
- Handoff: `docs/reviews/wu-tool-02-extra-full-repo-review-handoff-20260602.md`
- Design source: `docs/host/design.md`
- Control source: `docs/host/host-core-followup-implementation-control.md`
- Approved plan: `docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`
- Aggregate deepreview adjudication: `docs/reviews/wu-tool-02-aggregate-deepreview-controller-adjudication-20260602.md`

## Repository Map

### Package Structure

```
dayu/
├── contracts/          # 公共契约层（tool_call, tool_result, tool_outcome, etc.）
├── engine/             # Engine 层（agent, runners, contracts）
│   ├── contracts/
│   └── runners/openai/
├── host/               # Host 层（tool_runtime, dispatch, recovery, etc.）
│   └── durable/        # Host durable 存储层
├── runtime/            # 运行时基础设施（cancellation, lane, filelock, config_loader）
├── service/            # Service 层（host_assembly）
└── config/             # 配置（prompts, execution profiles）
```

### Test Structure

```
tests/
├── contracts/          # 契约测试（14 files）
├── engine/             # Engine 测试（40+ files）
│   ├── contracts/
│   └── runners/openai/
├── host/               # Host 测试（80+ files，最大测试套件）
├── runtime/            # Runtime 测试（16 files）
└── service/            # Service 测试（3 files）
```

### Key Files for WU-TOOL-02

| 文件 | 角色 |
|---|---|
| `dayu/host/tool_runtime.py` | 主要变更文件：ToolFactAcceptCandidate 结构拆分 |
| `dayu/host/tool_trace.py` | Tool Trace projection consumer（EventLog payload 消费） |
| `dayu/host/evidence.py` | Accepted evidence envelope（EventLog payload 消费） |
| `dayu/host/projection.py` | Projection runner 框架 |
| `dayu/host/memory.py` | Memory projection consumer |
| `dayu/host/compaction_evidence.py` | Compaction evidence extraction（EventLog payload 消费） |
| `dayu/host/waiting.py` | ToolAwaitingAcceptCandidate（独立类型，未纳入本次重构） |
| `dayu/host/tool_duplicate_governance.py` | Duplicate governance（attempt-scoped） |

## 实际覆盖区域

本次全仓 review 按风险优先级覆盖以下区域：

### 1. ToolFactAcceptCandidate 结构拆分完整性

**Producer 路径**：`tool_runtime.py` 中两个 producer 函数：
- `_tool_fact_result_accept_candidate()`（line 5002）：构造 COMPLETED/FAILED/CANCELLED/GOVERNED_ERROR candidate
- `_tool_fact_reuse_accept_candidate()`（line 5105）：构造 REUSE candidate

两者均使用新子结构 `ToolAcceptIdentity`、`ToolAcceptCall`、`ToolAcceptResult`、`ToolAcceptGovernance`、`ToolAcceptIdempotency`、`ToolAcceptDiagnostics` 组合构造 `ToolFactAcceptCandidate`。无旧 flat field 构造残留。

**Validation 路径**：`ToolFactAcceptCandidate.__post_init__()` 按 fact kind 分派校验：
- `_validate_common_candidate_fields()`：校验子结构类型
- `_validate_duplicate_fields()`：校验 duplicate governance 字段组合
- `_validate_result_fact_policy()` / `_validate_governed_error_candidate()` / `_validate_reuse_candidate()`：按 fact kind 校验跨结构约束

每个子结构有独立 validator：`_validate_tool_accept_identity()`、`_validate_tool_accept_call()`、`_validate_tool_accept_result()`、`_validate_tool_accept_duplicate_governance()`、`_validate_tool_accept_governance()`、`_validate_tool_accept_idempotency()`、`_validate_tool_accept_diagnostics()`。

**Consumer 路径**：EventLog payload 构造（`_tool_result_payload()`，line 3450）通过 `_candidate_result()` 和 `candidate.governance.duplicate` 等 accessor 读取新子结构。所有 payload field name 与旧实现一致。

### 2. EventLog Payload 一致性

Producer 写入的 EventLog payload field names 与所有 consumer 一致：
- `tool_trace.py` 通过 `_FIELD_TOOL_CALL_ID = "tool_call_id"` 等常量读取
- `compaction_evidence.py` 通过 `_PAYLOAD_FIELD_ACCEPTED_EVIDENCE_ENVELOPE = "accepted_evidence_envelope"` 读取
- `memory.py` 对 `TOOL_RESULT_ACCEPTED` 只做 `pass`（evidence-backed facts 通过 compaction path 物化）

### 3. 分层边界

- `dayu.runtime` 不 import `dayu.host` / `dayu.engine` / `dayu.service` / `dayu.ui` / `dayu.fins`
- `dayu.contracts` 不 import 任何上层
- `dayu.engine` 不 import `dayu.host` / `dayu.service` / `dayu.ui`
- `dayu.host` 不 import `dayu.service` / `dayu.ui`

无反向依赖。

### 4. 旧术语/旧路径残留

- `tool_runtime.py` 中 "run-scoped" 出现 7 处，均为 truncation manager 语义（非 duplicate governance），属于正确用法
- `tool_duplicate_governance.py` 中无 "run-scope" / "run-scoped" 残留
- 测试文件中 `ToolAwaitingAcceptCandidate`（`waiting.py`）的 flat field 访问属于独立类型，不纳入 WU-TOOL-02 范围

### 5. 类型安全与测试

- 全量 pyright：0 errors
- Host 测试套件：1100 passed, 1 skipped, 5 deselected
- WU-TOOL-02 核心测试：96 passed（accept_barrier + executor + duplicate_governance + diagnostics + truncation_fetch_more + tool_trace_projection + effective_bundle）

### 6. Residual Risks

- `RR-TOOL-01`：awaiting fanout 更宽并发治理，deferred-with-owner，不阻塞当前 PR
- `RR-TOOL-02`：tool trace duplicate scope 透传，已 closed

## Findings

**No blocking findings.**

### Nonblocking Note 01: `_tool_result_payload` 中 `else None` 缩进

- Severity: Low / non-blocking
- 文件: `dayu/host/tool_runtime.py:3521`
- 直接证据: `"tool_call_governed_event_ref"` 的 `else None` 缩进与 `if governed is not None` 对齐而非与赋值语句对齐
- 影响: 不改变 Python 语义，pyright 与全部测试通过
- 建议: 无需在当前 gate 修复；aggregate deepreview controller adjudication 已记录为 style note

### Nonblocking Note 02: 控制文档 WU-TOOL-02 状态滞后

- Severity: Low / non-blocking
- 文件: `docs/host/host-core-followup-implementation-control.md`
- 直接证据: WU-TOOL-02 在工作单元表中仍标记为 `planning`，但实际已通过全部 slice、aggregate deepreview，当前处于 full-repository review gate
- 影响: 不影响代码正确性或 PR 质量；属于文档同步滞后
- 建议: ready-to-open-draft-PR gate 通过后由 controller 更新

## 未覆盖区域

以下区域未在本次全仓 review 中深入走读，不属于伪称已覆盖：

1. **Engine runner 内部实现**（`dayu/engine/runners/openai/`）：WU-TOOL-02 不涉及 Engine runner 变更，且 Engine 不 import Host
2. **Service host_assembly 细节**（`dayu/service/host_assembly.py`）：WU-TOOL-02 不涉及 Service 层变更
3. **Config prompts 内容**（`dayu/config/prompts/`）：配置内容不在 WU-TOOL-02 scope 内
4. **Host durable schema / connection / maintenance**：WU-TOOL-02 不涉及 durable schema 变更
5. **Host recovery / dispatch / admission 细节**：WU-TOOL-02 不涉及这些路径的逻辑变更
6. **多进程压力测试**（`tests/host/test_host_production_stress.py`）：由 WU-STRESS-01 覆盖，不在本次 review 深度走读范围内

## 与 WU-TOOL-02 ready-to-open-draft-PR 的阻塞性裁决

**不阻塞。** 本次全仓 review 未发现会阻塞 WU-TOOL-02 ready-to-open-draft-PR 的 correctness、stability、maintainability、layering、tool governance、EventLog durable truth、memory / compaction projection 或 testing risks。

具体确认：
- `ToolFactAcceptCandidate` 结构拆分完整，producer / validation / consumer 全链路一致
- EventLog payload field name 向后兼容，projection consumers（tool_trace、compaction_evidence）正确消费
- 分层边界未被违反，`dayu.runtime` 边界清洁
- 无旧术语 / 旧路径 / 旧字段依赖残留（`ToolAwaitingAcceptCandidate` 为独立类型，不在本次 scope）
- 全量 pyright 0 errors，Host 测试 1100 passed
- README 无需更新（WU-TOOL-02 不涉及用户可见行为变化或公共 API 变更）

## Residual Risks / Recommended Follow-up Owners

| 风险 | 状态 | Owner |
|---|---|---|
| RR-TOOL-01: awaiting fanout 更宽并发治理 | deferred-with-owner | future WU-TOOL awaiting hardening |
| `ToolAwaitingAcceptCandidate` 结构拆分 | not-in-scope | 若未来需要，单独 work unit |
| 控制文档 WU-TOOL-02 状态同步 | deferred-to-gate-closeout | controller |

## Final Verdict

**pass-with-nonblocking-notes**

无 blocking finding。两个 nonblocking notes 均不要求当前 gate 修复。WU-TOOL-02 ready-to-open-draft-PR 前置全仓 review 通过。
