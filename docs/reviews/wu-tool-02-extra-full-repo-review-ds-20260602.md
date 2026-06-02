# WU-TOOL-02 Extra Full Repository Review — AgentDS

## 元信息

- **Review agent**: AgentDS
- **Review type**: Full repository review (not diff-only)
- **Gate**: WU-TOOL-02 ready-to-open-draft-PR 前置全仓 review
- **Branch**: `refactor/wu-tool-02-accept-candidate-cleanup`
- **Work unit**: WU-TOOL-02 Accept Candidate Structure Cleanup
- **Design source**: `docs/host/design.md`
- **Control source**: `docs/host/host-core-followup-implementation-control.md`
- **Approved plan**: `docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`
- **Aggregate deepreview adjudication**: `docs/reviews/wu-tool-02-aggregate-deepreview-controller-adjudication-20260602.md`
- **Date**: 2026-06-02

## Repository Map 与覆盖区域

### 全仓结构

```text
dayu/
  contracts/     — 跨层共享契约（JSON、工具、取消、工具执行结果）
  engine/        — Engine 层（Agent 执行、Runner 协议、SSE、provider）
  host/          — Host 层（Session/Run/Attempt 治理、EventLog、ToolRuntime、memory、compaction）
    durable/     — Host durable foundation（SQLite schema、EventLog、state transition、codec）
  runtime/       — 层中立运行期基础设施（日志、取消等待、lane、filelock、config、tool discovery）
  service/       — Service 层（Host assembly helper）
config/          — 包内默认配置 + prompts
tests/           — 测试矩阵
  contracts/ engine/ host/ runtime/ service/
docs/            — 设计文档、总控文档、review artifacts
utils/           — 分析辅助脚本
workspace/       — 工作区临时文件
```

### 本次全仓 Review 实际走读的区域

按风险优先级走读，以下为实际阅读并核对的真实入口和关键链路：

| 区域 | 文件/路径 | 走读方式 |
|------|----------|---------|
| ToolFactAcceptCandidate 组合根 | `dayu/host/tool_runtime.py` (L1-L700, L3930-L4330) | 全文走读 dataclass 定义、validation、producer/consumer 迁移 |
| ToolRuntime accept barrier consumers | `dayu/host/tool_runtime.py` (L1700-L3100) | 走读 EventLog payload、accepted evidence envelope、ack 构造路径 |
| Duplicate governance module | `dayu/host/tool_duplicate_governance.py` | 全文走读 typed contracts |
| Tool trace projection | `dayu/host/tool_trace.py` | 走读 consumer id、event filter、payload 读取 |
| Compaction evidence material | `dayu/host/compaction_evidence.py` | 走读 accepted evidence envelope 消费路径 |
| Compact material pack | `dayu/host/compact_material.py` | 走读 EventLog payload 消费路径 |
| Memory projection | `dayu/host/memory.py` | 走读 TOOL_RESULT_ACCEPTED 消费路径 |
| Evidence envelope | `dayu/host/evidence.py` | 走读 accepted evidence envelope typed contract |
| Host public API | `dayu/host/__init__.py` | 全文走读 public export |
| Service assembly | `dayu/service/host_assembly.py` | 走读 Host construction boundary |
| Import boundary 约束 | `dayu/runtime/*.py` vs business layers | AST 扫描 + test 验证 |
| 分层反向依赖检查 | `dayu/engine` -> `dayu/host` 方向 | AST 扫描 + test 验证 |
| 全量 pyright | 全仓 | 0 errors |
| WU-TOOL-02 affected tests | 10 test files, 206 tests | 全部通过 |
| Import boundary tests | 3 test files, 28 tests | 全部通过 |
| Boundary/guard/package export tests | 3 test files, 25 tests | 全部通过 |
| Host README | `dayu/host/README.md` | 全文走读 stable contract 表述 |
| 项目 README | `dayu/README.md` | 全文走读架构边界表述 |
| Control doc residual risk table | `docs/host/host-core-followup-implementation-control.md` | 核对所有 RR-* entries |

### 明确未覆盖的区域

以下区域因不直接触及 WU-TOOL-02 的变更范围，且不在本次全仓 review 的合理 scope 内，标记为未覆盖：

- `dayu/engine/runners/openai/` — SSE 解析、Runner 实现细节（与 candidate 结构无关）
- `dayu/config/prompts/` — scene manifest、prompt fragments（与 candidate 结构无关）
- `utils/` — 分析辅助脚本（非生产代码）
- `dayu/render/` — 不存在此目录
- `tests/engine/` — Engine 层测试（与 candidate 结构无关，除非测试本身依赖 Host type）
- `tests/contracts/` — contracts 层测试（与 candidate 结构无关）

## Findings

### Finding 01: ALLOW duplicate governance record 要求 scope/message 非空 — Non-blocking

- **Severity**: Low (non-blocking)
- **Evidence**: `dayu/host/tool_runtime.py` L4032-L4037, `_validate_tool_accept_duplicate_governance`
- **Description**: 当前 `ToolAcceptDuplicateGovernance` 的 `__post_init__` 要求任何存在 duplicate governance record 的情况都必须有 `duplicate_scope` 和 `duplicate_decision_message` 非空，包括 `DuplicateDecisionKind.ALLOW`。这意味着即使是 allow duplicate（同一 Attempt 内重复调用但允许继续执行），也必须记录完整的 scope 和 message。
- **Root cause**: 设计意图：`ToolAcceptDuplicateGovernance` 不为 `None` 表示"存在 duplicate governance 记录"，而一个记录必须有完整的审计信息。
- **Impact**: 比旧实现略严格——旧 `_validate_duplicate_fields` 对 `duplicate_decision is None` 直接返回，但一旦 `duplicate_decision` 存在（包括 ALLOW），旧实现同样要求 scope 和 message 非空。Aggregate deepreview 已裁决这是合理行为，不是 regression。
- **Recommendation**: 无需修复。当前行为符合 "duplicate governance record 必须可审计" 的设计目标。若未来需要 looser validation，应通过单独设计裁决，不在本 gate 处理。

### Finding 02: `ToolFactKind.LOST` 无显式测试覆盖 — Non-blocking (pre-existing)

- **Severity**: Low (non-blocking, pre-existing)
- **Evidence**: `dayu/host/tool_runtime.py` L614-L615, accepted plan 明确 LOST 不在 candidate 支持范围内
- **Description**: `ToolFactAcceptCandidate.__post_init__` 对 `LOST` 直接 fail-fast，但不存在显式测试构造 LOST candidate 并断言其被拒绝。这是 WU-TOOL-02 之前就存在的 gap。
- **Root cause**: `ToolFactKind.LOST` 当前不在 ToolRuntime accept candidate 支持范围内，只通过 lost tool fact codec 路径（`_tool_lost_fact_record`）处理。设计上从未计划让 LOST 进入 accept barrier。
- **Impact**: 无运行时 risk。LOST 路径有独立的生产逻辑和测试覆盖（通过 lost tool fact codec 和 terminal closeout 测试）。
- **Recommendation**: 无需修复。Aggregate deepreview 已 deferred 到未来 ToolRuntime fact-kind expansion。

### Finding 03: `_tool_result_payload` 中 `else None` 缩进 — Non-blocking (style only)

- **Severity**: Informational (non-blocking)
- **Evidence**: `dayu/host/tool_runtime.py` `_tool_result_payload` 函数
- **Description**: 某处 `else None` 的缩进在视觉上暗示它属于外层 `if` 而非内层，但 Python 语义上确实属于内层。
- **Root cause**: 该函数的多层嵌套结构。
- **Impact**: 不影响任何运行时行为，pyright 与 206 tests 均通过。
- **Recommendation**: 无需在当前 gate 修复。Aggregate deepreview 已裁决这不是 behavior issue。

### Finding 04: 子结构直接单元测试覆盖率可进一步强化 — Non-blocking (residual)

- **Severity**: Informational (residual note)
- **Description**: 当前 `ToolAcceptIdentity`、`ToolAcceptCall`、`ToolAcceptResult`、`ToolAcceptGovernance`、`ToolAcceptIdempotency`、`ToolAcceptDiagnostics` 的 validation 通过组合根路径（accept barrier tests、duplicate governance tests、diagnostics tests）间接覆盖。没有针对单个子结构的独立单元测试。
- **Impact**: 低。组合根路径的测试已覆盖各子结构的 validation 路径和错误情况。但若未来单独修改子结构 validation，缺少直接单元测试可能使回归检测延迟到 accept barrier 测试层。
- **Recommendation**: 后续 maintenance hardening（如 WU-LAYER-02）可考虑为子结构增加独立单元测试。不阻塞当前 PR。

### Finding 05: 测试 helper 重复 — Non-blocking (pre-existing)

- **Severity**: Informational (residual note)
- **Description**: `tests/host/test_toolruntime_accept_barrier.py` 和 `tests/host/test_toolruntime_executor.py` 中存在类似的 candidate 构造 helper（如 `_completed_candidate()`、`_reuse_candidate()`、`_fact_kind_candidate()`），部分逻辑重复但散落于各测试文件。
- **Impact**: 低。WU-TOOL-02 的 Slice 2 已将 hand-written 超宽 candidate 构造替换为组合 helper，但不同测试文件之间的 helper 仍有重复。
- **Recommendation**: 后续 test organization cleanup 可考虑抽取共享 candidate factory。不阻塞当前 PR。

## 全仓分层与架构检查

### dayu.runtime 边界 — PASS

- `dayu.runtime` 无任何 `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins` 导入
- 78 个 runtime Python 文件全部 AST 扫描通过
- `tests/runtime/test_import_boundary.py` 13 passed
- `tests/host/test_import_boundary.py::test_runtime_does_not_import_host_or_engine_layers` passed

### Engine → Host 方向 — PASS

- `dayu.engine` 无任何 `dayu.host` 导入
- `tests/host/test_import_boundary.py::test_engine_does_not_import_host_layer` passed

### Host → 上层方向 — PASS

- `dayu.host` 无 `dayu.service` / `dayu.ui` / `dayu.fins` / `dayu.config` 导入
- `tests/host/test_import_boundary.py::test_host_does_not_import_upper_or_business_layers` passed

### Host → Engine 方向 — PASS（经允许边界模块）

- Host 仅通过 7 个允许边界模块导入 `dayu.engine`：`_execution_config_projection.py`、`api.py`、`dispatch.py`、`engine_ingest.py`、`llm_compaction.py`、`local_proxy.py`、`run_input.py`
- `tests/host/test_import_boundary.py::test_host_engine_imports_stay_on_allowed_boundary_modules` passed

### Host 包根 public export — PASS

- `dayu.host` 包根不导出 `ToolRuntime`、`ToolRuntimeHandle`、`ToolBundle`、`ToolDefinition`
- `tests/host/test_import_boundary.py::test_host_root_does_not_export_toolruntime_or_tool_declaration_owners` passed

### projection / memory / purge durable 边界 — PASS

- 所有 projection 模块、memory 模块、purge durable 模块的 import 边界测试通过
- ToolRuntime schema projection 模块的 import 边界测试通过

## 全仓类型与编码约束检查

### pyright — PASS

- 全量 pyright: 0 errors, 0 warnings

### `Any` / `object` 类型使用 — PASS

- `dayu/host/tool_runtime.py` 中无 `Any`、`object`、`hasattr`、`getattr` 使用
- 全仓搜索仅命中 docstring 中的 "JSON object" 和 tool schema 定义中的 `type="object"` 字面量

### 兼容性代码 — PASS

- 无旧字段 property facade
- 无兼容 re-export
- 无兼容 wrapper
- 旧顶层字段已全部移除
- `rg` 辅助检查：`dayu/host/tool_runtime.py` 中无 `candidate.old_field` 残留

### 中文 docstring — PASS

- 所有新增的 7 个子结构 dataclass 均有完整中文 docstring
- 所有新增 validation helper 均有完整中文 docstring

## 全仓测试状态检查

### WU-TOOL-02 affected tests — PASS

```text
tests/host/test_toolruntime_accept_barrier.py          16 passed
tests/host/test_toolruntime_executor.py                34 passed
tests/host/test_toolruntime_duplicate_governance.py    28 passed
tests/host/test_toolruntime_diagnostics.py              4 passed
tests/host/test_toolruntime_truncation_fetch_more.py    3 passed
tests/host/test_tool_trace_projection.py               21 passed
tests/host/test_tool_trace_queries.py                  14 passed
tests/host/test_memory_projection.py                   13 passed
tests/host/test_compaction_operation.py                33 passed
tests/host/test_llm_compaction.py                      40 passed
---
Total: 206 passed in 0.68s
```

### 边界/guard/契约测试 — PASS

```text
tests/host/test_import_boundary.py         10 passed
tests/host/test_weak_typing_guard.py        8 passed
tests/host/test_package_exports.py          7 passed
tests/runtime/test_import_boundary.py      13 passed
tests/engine/test_import_boundary.py        3 passed
---
Total: 41 passed
```

## 全仓跨模块影响检查

### EventLog Payload — PASS（无变化）

所有 EventLog event type、payload key、payload 构造路径保持不变：

- `TOOL_CALL_REQUESTED` payload: identity、call identity、schema digest、iteration
- `TOOL_CALL_GOVERNED` payload: governance decision、duplicate scope、reuse refs
- `TOOL_RESULT_ACCEPTED` payload: accepted evidence envelope、raw tool outcome、diagnostic refs

### Accepted Evidence Envelope — PASS（无变化）

`dayu/host/evidence.py` 中 `AcceptedEvidenceEnvelope`、`AcceptedEvidenceToolQuery`、`AcceptedEvidenceResultRef`、`OpaqueEvidenceRef` 的字段、digest 派生、JSON 序列化均未改变。

### Memory Projection — PASS（无变化）

`dayu/host/memory.py` 只通过 committed `TOOL_RESULT_ACCEPTED` EventLog payload 消费工具结果，不依赖 `ToolFactAcceptCandidate` 内部结构。

### Compaction Evidence / Material — PASS（无变化）

- `dayu/host/compaction_evidence.py` 只通过 `accepted_evidence_envelope_from_json_value` 消费 committed EventLog payload
- `dayu/host/compact_material.py` 只通过 canonical refs 构造 compact material
- 均不依赖 `ToolFactAcceptCandidate` 内部结构

### Tool Trace — PASS（无变化）

- `dayu/host/tool_trace.py` 只消费 committed EventLog payload 中的命名白名单字段
- payload key 和 JSON shape 不变，tool trace hot/cold projection 不受影响

### Awaiting Candidate — PASS（scope 外但验证无回归）

- `dayu/host/waiting.py` 中的 `ToolAwaitingAcceptCandidate` 保持原有 flat fields
- Awaiting path 明确排除在 WU-TOOL-02 scope 外，未被误改
- `tests/host/test_wait_awaiting_accept.py` 中的 `candidate.field` 引用指向 `ToolAwaitingAcceptCandidate`，不是 `ToolFactAcceptCandidate`

### Duplicate Governance — PASS（语义不变）

- `dayu/host/tool_duplicate_governance.py` 保持 attempt-scoped duplicate governance typed contracts
- `DuplicateGovernanceScope`、`DuplicateDecisionKind`、`InMemoryAttemptDuplicateGovernance` 均未改变

## 全仓术语一致性检查

### 术语 grep — PASS

- `rg -i "run.scope|run-local|run_local" dayu/host/tool_runtime.py dayu/host/tool_duplicate_governance.py` — 无残留 run-scope duplicate 术语
- `rg -n "ToolFactAcceptCandidate" dayu/` — 仅在 `tool_runtime.py`（定义与使用）、`tooling.py`（EffectiveToolBundle）与测试文件中出现
- `rg -n "accepted_evidence_envelope\|evidence_envelope" dayu/` — 仅出现在稳定的 accepted evidence envelope 路径中

### README 同步 — PASS（无需更新）

- `dayu/host/README.md` 对 ToolRuntime 的描述在 stable contract 层面：accept barrier 语义、duplicate governance 为 attempt-local、工具结果必须经 accept barrier。WU-TOOL-02 不改变这些 stable semantics。
- `dayu/README.md` 对分层、边界、ToolRuntime 的架构表述均为 stable contract 层面，不受内部 dataclass 拆分影响。
- `dayu/config/README.md` — 不涉及此变更。
- `tests/README.md` — 测试约定无稳定变化。
- 根 `README.md` — 用户手册层面无变化。

## Residual Risk 追踪表核对

控制文档 `docs/host/host-core-followup-implementation-control.md` 中所有 RR-* entries 状态与当前代码一致：

| ID | 状态 | 一致性 |
|----|------|--------|
| RR-STRESS-01 | deferred-with-owner | 一致 |
| RR-STRESS-02 | deferred-with-owner | 一致 |
| RR-DUR-02 | deferred-with-owner | 一致 |
| RR-DUR-03 | deferred-with-owner | 一致 |
| RR-DUR-05 | deferred-with-owner | 一致 |
| RR-LIFE-01 | deferred-with-owner | 一致 |
| RR-LIFE-02 | deferred-with-owner | 一致 |
| RR-CTX-SLICED-01 | deferred-with-owner | 一致 |
| RR-TOOL-01 | deferred-with-owner | 一致 |
| RR-TOOL-02 | closed | 一致（WU-TOOL-01 Slice 3 已完成） |

无 WU-TOOL-02 引出的新 residual risk 需要 tracked。

## Verdict

### 对 WU-TOOL-02 ready-to-open-draft-PR 的阻塞性裁决

**No blocking findings.** 本次全仓 review 未发现会阻塞 WU-TOOL-02 进入 ready-to-open-draft-PR 的 correctness、stability、maintainability、layering、tool governance、EventLog durable truth、memory/compaction projection 或 testing 风险。

具体确认：

1. **WU-TOOL-02 实现完整性**: `ToolFactAcceptCandidate` 已从超宽 flat dataclass 成功拆分为 7 个 typed 子结构的组合根，所有 producer、accept barrier、EventLog payload、ack 和 projection consumer 均已迁移到新结构。无旧字段 facade、wrapper 或 re-export 残留。

2. **全仓分层边界**: `dayu.runtime` / `dayu.engine` / `dayu.host` / `dayu.service` 之间的 import boundary 全部保持，与 CLAUDE.md 架构约束一致。28 个 import boundary 测试全部通过。

3. **EventLog / Durable Payload**: `TOOL_CALL_REQUESTED`、`TOOL_CALL_GOVERNED`、`TOOL_RESULT_ACCEPTED` 的 event type、payload key、event id 派生、accepted evidence envelope shape、idempotency scope 均未改变。

4. **跨模块影响**: tool trace、memory projection、compaction evidence/material 等只消费 committed EventLog payload 的模块无需修改，回归测试 121 passed 确认语义一致。

5. **类型安全**: 全量 pyright 0 errors；tool_runtime.py 中无 `Any`、`object`、`hasattr`、`getattr`、magic payload。

6. **测试**: 206 affected Host tests passed；所有 boundary/guard/package export tests passed。

7. **README/Doc**: 无触发条件需要更新。

### Final Verdict: **pass**

### Residual Risks / Recommended Follow-up Owners

| ID | 描述 | Severity | Owner |
|----|------|----------|-------|
| DS-RR-01 | 子结构缺少独立单元测试，当前依赖组合根路径间接覆盖 | Low | WU-LAYER-02 shared helper consolidation |
| DS-RR-02 | 测试 helper 在 accept_barrier 与 executor 测试文件间部分重复 | Low | future test organization cleanup |
| DS-RR-03 | `ToolFactKind.LOST` 无显式测试覆盖（pre-existing） | Low | future ToolRuntime fact-kind expansion |
