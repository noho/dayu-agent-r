# WU-TOOL-02 Draft PR Review — AgentMiMo

## Scope 与 Reviewed Inputs

- **PR**: `https://github.com/noho/dayu-agent-r/pull/108`
- **Branch**: `refactor/wu-tool-02-accept-candidate-cleanup` vs `main`
- **Work unit**: WU-TOOL-02 Accept Candidate Structure Cleanup
- **Reviewed inputs**:
  - PR diff (`gh pr diff 108`, 7545 lines)
  - PR metadata (state, mergeable, checks, body)
  - Aggregate deepreview controller adjudication: `docs/reviews/wu-tool-02-aggregate-deepreview-controller-adjudication-20260602.md`
  - Extra full-repo review controller adjudication: `docs/reviews/wu-tool-02-extra-full-repo-review-controller-adjudication-20260602.md`
  - Approved plan: `docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`
  - 控制文档: `docs/host/host-core-followup-implementation-control.md`
- **Production file**: `dayu/host/tool_runtime.py` (+665/-302)
- **Test files**: 5 个受影响测试文件
- **验证**: 206 affected tests passed, full pyright 0 errors (独立重新验证)

## Review Method

聚焦 draft PR gate 要求：是否仍存在会阻塞 `draft-PR-pass` 的 actionable finding。不重复已裁决的 nonblocking style notes。

执行步骤：
1. 核对 PR diff 与本地分支状态一致性
2. 独立运行受影响测试与 pyright 验证
3. 从 PR diff 中识别可能的新 blocking issue
4. 核对已裁决 findings 是否在 PR 中正确处理
5. 检查 CI/checks 状态

## Finding 1: No blocking findings

**Severity**: 无

经过独立验证，PR diff 中不存在会阻塞 `draft-PR-pass` 的 actionable finding。

### 验证依据

**代码正确性**:
- `ToolFactAcceptCandidate` 已收敛为 7 字段 typed composition root（`identity`, `call`, `tool_fact_kind`, `result`, `governance`, `idempotency`, `diagnostics`）
- 所有旧扁平字段访问已迁移至子结构路径（生产代码 grep 确认 0 残留）
- 子结构 `__post_init__` 校验内部 invariant，组合根校验跨结构 fact-kind 约束，分层正确

**EventLog durable truth 稳定性**:
- `TOOL_CALL_REQUESTED`、`TOOL_CALL_GOVERNED`、`TOOL_RESULT_ACCEPTED` 的 payload key 完全不变
- event id 派生输入 (`_tool_accept_event_plan`) 的 digest_input key/value 不变
- accepted evidence envelope shape 不变
- idempotency scope 格式不变：`f"{candidate.identity.attempt_id}:{candidate.call.tool_call_id}"`

**Duplicate governance 语义不变**:
- reuse 路径：`result=None`，governed event 只写 requested + governed
- duplicate governed error：policy reason/message 校验不变
- ALLOW duplicate：跳过 governed event 的逻辑不变

**Projection consumers 隔离**:
- `dayu/host/tool_trace.py`, `memory.py`, `compaction_evidence.py`, `compact_material.py` 零 diff
- 121 个 projection consumer 测试通过（独立验证中包含）

**类型安全**:
- pyright 0 errors（独立重新验证）
- 无 `Any`、`object`、无类型签名

**测试覆盖**:
- 206 affected tests passed（独立重新验证）
- 覆盖普通 result、failed/cancelled、plain governed error、duplicate governed error、reuse、diagnostics、truncation、payload consumers

**AGENTS.md 合规**:
- 分层边界：仅 `dayu/host/tool_runtime.py` 生产代码改动
- `dayu.runtime` 边界：未引入新 import
- 无兼容 wrapper/facade/re-export
- 无 extra payload
- 无 god dataclass（已拆分为 7 个职责清晰子结构）
- 中文 docstring：所有新增 dataclass 与 validation helper 均有完整中文 docstring
- README 触发规则：内部 dataclass 拆分不触发 README 更新

## Finding 2 (non-blocking, 已裁决): `_tool_result_payload` 中 `else None` 缩进

**Severity**: 非阻塞，已在 aggregate deepreview 和 extra full-repo review 中裁决为 style note。

**Evidence**: `dayu/host/tool_runtime.py` `_tool_result_payload` 函数中 `else None` 缩进偏移。

**Controller 裁决**: 不改变 Python 语义，不影响 EventLog payload 或 consumer 行为。当前 gate 不为纯格式化问题开启 fix loop。

**结论**: 不重复此 finding，不阻塞 PR。

## Finding 3 (non-blocking, 已裁决): ALLOW duplicate governance validation

**Severity**: 非阻塞，已在 aggregate deepreview 和 extra full-repo review 中裁决。

**Evidence**: `_validate_tool_accept_duplicate_governance` 对 ALLOW 决策要求 `duplicate_scope` 和 `duplicate_decision_message` 非空。

**Controller 裁决**: 旧 validator 一旦 `duplicate_decision` 存在同样要求 scope/message；当前行为符合 "duplicate governance record 必须可审计" 的设计目标。

**结论**: 不重复此 finding，不阻塞 PR。

## Finding 4 (non-blocking, 已裁决): `ToolFactKind.LOST` 无显式测试

**Severity**: 非阻塞（pre-existing），已在 aggregate deepreview 中裁决为 deferred-with-owner (RR-TOOL-03)。

**结论**: 不重复此 finding，不阻塞 PR。

## CI / Checks 状态

- **GitHub statusCheckRollup**: 空数组（no checks reported）
- **PR state**: OPEN
- **Mergeable**: MERGEABLE

PR 当前无 CI checks。这不影响 draft PR review 结论，因为：
- 本地独立验证已确认 206 tests passed + pyright 0 errors
- PR 是 draft 状态，CI 可能尚未配置或未触发

## Validation / Coverage Judgment

| 验证项 | 状态 |
|--------|------|
| 206 affected tests | ✅ passed (独立重新验证) |
| pyright 全量 | ✅ 0 errors (独立重新验证) |
| EventLog payload key 稳定 | ✅ diff 确认不变 |
| Projection consumers 零 diff | ✅ diff 确认不变 |
| 旧扁平字段残留 (生产代码) | ✅ 0 hits |
| `ToolAwaitingAcceptCandidate` 隔离 | ✅ 独立类型，未被误改 |
| AGENTS.md 合规 | ✅ 无违反 |

### 已裁决 residual risks (不阻塞 PR)

| ID | 描述 | Owner | 裁决 |
|----|------|-------|------|
| RR-TOOL-03 | `ToolFactKind.LOST` accept candidate fail-fast 显式测试缺口 | future ToolRuntime fact-kind expansion | deferred |
| RR-TOOL-04 | 子结构直接单元测试与测试 helper 进一步收敛 | WU-LAYER-02 / future test organization cleanup | deferred |

## Final Verdict

**pass**

理由：
- PR diff 中无新 blocking finding
- 已裁决的 nonblocking findings 均不要求当前 gate 修复
- 206 affected tests passed + pyright 0 errors（独立重新验证）
- EventLog payload、accepted evidence envelope、idempotency scope、duplicate governance、reuse、projection consumers 语义均不变
- AGENTS.md 全部硬约束满足
- PR mergeable，无冲突
- CI 状态：no checks reported（不影响 draft PR pass 判定）
