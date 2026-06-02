# WU-TOOL-02 Slice 1 Code Review — AgentDS

## Review Metadata

- **Reviewer**: AgentDS
- **Date**: 2026-06-02
- **Gate**: code review
- **Branch**: `refactor/wu-tool-02-accept-candidate-cleanup`
- **Scope**: Slice 1 — 新增子结构与局部 validation helper
- **Plan**: `docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`
- **Handoff**: `docs/reviews/wu-tool-02-slice1-implementation-handoff-20260602.md`
- **Implementation Report**: `docs/reviews/wu-tool-02-slice1-implementation-report-20260602.md`

## Verdict

**Code review pass.** 无 blocking finding。

## Evidence

### 1. 独立验证

| 验证项 | 命令 | 结果 |
|---|---|---|
| Accept barrier tests | `pytest tests/host/test_toolruntime_accept_barrier.py` | 16 passed |
| Pyright | `pyright dayu/host/tool_runtime.py` | 0 errors, 0 warnings |

### 2. File Ownership

- 改动文件：`dayu/host/tool_runtime.py` 仅此一个 production 文件。✓
- 总控文档 `docs/host/host-core-followup-implementation-control.md` 仅有状态行更新（gate 变更 / 日志），不属于 review scope。✓
- 未修改 tests、README、配置、schema、其他 production 文件。✓

### 3. 新增 Dataclass（7 个）

| 类名 | 字段数 | slots | frozen | 中文 docstring | 严格类型 | 兼容 facade |
|---|---|---|---|---|---|---|
| `ToolAcceptIdentity` | 4 | ✓ | ✓ | ✓ | ✓ | 无 |
| `ToolAcceptCall` | 6 | ✓ | ✓ | ✓ | ✓ | 无 |
| `ToolAcceptResult` | 5 | ✓ | ✓ | ✓ | ✓ | 无 |
| `ToolAcceptDuplicateGovernance` | 5 | ✓ | ✓ | ✓ | ✓ | 无 |
| `ToolAcceptGovernance` | 3 | ✓ | ✓ | ✓ | ✓ | 无 |
| `ToolAcceptIdempotency` | 2 | ✓ | ✓ | ✓ | ✓ | 无 |
| `ToolAcceptDiagnostics` | 1 | ✓ | ✓ | ✓ | ✓ | 无 |

- 字段集合与 plan Proposed Typed Structure 一致。✓
- 所有类均未加入 `__all__`，保持 Host 内部类型。✓
- 无 `Any`、`object`、无类型签名、magic payload。✓
- 无旧字段 property 转发、兼容 re-export。✓

### 4. 新增 Validation Helper（7 个）

| 函数 | 校验对象 | 校验内容 |
|---|---|---|
| `_validate_tool_accept_identity` | identity | 4 文本非空 |
| `_validate_tool_accept_call` | call | 3 文本非空 + 3 sha256 digest |
| `_validate_tool_accept_result` | result | outcome sha256, optional payload sha256, payload_ref 一致性, truncation 类型 |
| `_validate_tool_accept_duplicate_governance` | duplicate | decision/key/scope/message/prior_refs 内部一致性 |
| `_validate_tool_accept_governance` | governance | policy decision 字段 + tool_idempotency_key + duplicate 类型 |
| `_validate_tool_accept_idempotency` | idempotency | key 非空 + semantic digest sha256 |
| `_validate_tool_accept_diagnostics` | diagnostics | 所有 ref 类型 |

- 所有 helper 均为模块级私有函数，中文 docstring 完整。✓
- 每个 helper 仅校验其对应子结构的内部 invariant，未涉及 fact kind 判别、跨子结构字段关系、policy/duplicate 跨结构等值约束。✓

### 5. 关键 Plan 约束逐条验证

#### 5.1 `ToolFactAcceptCandidate` 顶层字段未变

代码行 565 起 `ToolFactAcceptCandidate` 定义与 HEAD 完全一致，顶层字段未增删改。✓

#### 5.2 Producer 未迁移

`_tool_fact_accept_candidate()`（行 1889）、`_tool_fact_reuse_accept_candidate()`（行 2185）未改动。✓

#### 5.3 Accept barrier consumer 未迁移

`_accept_idempotency_scope()`、`_read_accept_context()`、`_tool_accept_event_plan()`、`_tool_result_payload()`、`_accepted_evidence_envelope()`、`_accepted_ack_from_rows()` 等均未改动。✓

#### 5.4 Tests 未迁移

所有 5 个 allowed test files 未改动。✓

#### 5.5 EventLog payload / accepted evidence / duplicate / wait / memory / compaction / tool trace 行为不变

仅新增 dataclass 和独立 helper，无任何 consumer 接入。✓

#### 5.6 未借结构拆分新增 payload digest 校验语义

`_validate_tool_accept_result` 中 `payload_digest == payload_ref.payload_digest` 检查（行 3999-4003）与现有 `_validate_common_candidate_fields` 行 4131-4135 语义一致，是对已有 candidate 内部 invariant 的子结构层级复现，未扩大为新的等值规则或持久化约束。✓

#### 5.7 未引入 `Any` / `object` / 无类型签名 / 兼容 facade

全文搜索确认。✓

#### 5.8 `ToolFactKind.LOST` 仍 unsupported

新 dataclass 和 validator 均无 LOST 构造语义。✓

#### 5.9 验证报告可信

独立运行 tests 和 pyright 结果与 implementation report 一致。✓

### 6. Adversarial Pass

以下场景逐一审查，均未发现新增风险：

- **误接入旧 producer**：新 dataclass 未被任何 producer 引用，不会改变 candidate 构造路径。
- **误改 EventLog payload key**：EventLog payload helper（`_tool_call_requested_event_request()` 等）全未修改。
- **validation helper 提前承担跨子结构约束**：逐个 helper 审查，均只校验各自结构内部字段类型/格式/组合，无 fact-kind 分支、无跨结构字段引用（`_validate_tool_accept_governance` 调用 `_validate_policy_decision_fields` 是 `ToolPolicyDecision` 自身内部 invariant 的既有校验，非跨结构约束）。
- **新 dataclass 意外公开为 public API**：`__all__` 未包含任何新类。✓
- **类型错误隐藏**：pyright 0 errors。✓

## Findings

无 blocking finding。无 non-blocking finding。

## Conclusion

Slice 1 实现严格遵循 approved plan：只新增 7 个 Host 内部 typed 子结构和 7 个局部 validation helper，未改变 `ToolFactAcceptCandidate` 顶层字段、producer、consumer、tests、EventLog payload 或任何运行时行为。中文 docstring 完整，类型严格，无兼容 facade。验证通过（16 tests passed，pyright clean）。Slice 1 code review pass，可进入 Slice 2。
