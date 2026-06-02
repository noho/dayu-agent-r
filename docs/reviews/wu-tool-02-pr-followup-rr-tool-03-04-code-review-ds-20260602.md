# WU-TOOL-02 PR Follow-up RR-TOOL-03 / RR-TOOL-04 Code Review — AgentDS

## Scope

Review only this follow-up fix:

- `ToolFactKind.LOST` explicit fail-fast negative test 是否真实关闭 `RR-TOOL-03`。
- `ToolAccept*` 子结构直接 validator negative tests 是否真实关闭 `RR-TOOL-04` 的直接测试缺口。
- 是否违反 AGENTS.md：中文 docstring、禁止 `Any` / `object`、禁止逃避类型边界、测试不应为过度收敛引入跨文件共享 builder。
- README/doc sync 裁决复核。
- validation 是否充分。

## Evidence Sources

- 测试文件: `tests/host/test_toolruntime_accept_barrier.py`
- 生产 validator: `dayu/host/tool_runtime.py` (lines 3936–4105, 4120–4131, 4307–4317, 4335–4360)
- `ToolFactKind` enum: `dayu/host/tool_runtime.py` lines 268–276
- `ToolFactAcceptCandidate.__post_init__`: `dayu/host/tool_runtime.py` lines 588–615
- Implementation handoff: `docs/reviews/wu-tool-02-pr-followup-rr-tool-03-04-implementation-handoff-20260602.md`
- Implementation report: `docs/reviews/wu-tool-02-pr-followup-rr-tool-03-04-implementation-report-20260602.md`

## Findings

### RR-TOOL-03 Closure: `ToolFactKind.LOST` Explicit Negative Test

**Verdict: CLOSED**

测试 `test_lost_tool_fact_kind_fails_fast_as_unsupported` (lines 692–709) 正确验证了 LOST fail-fast 行为：

1. 使用 `_completed_candidate(seeded, ...)` 构造基线候选（COMPLETED kind）。
2. 通过 `dataclasses.replace(base, tool_fact_kind=ToolFactKind.LOST)` 创建新实例，触发 `__post_init__`。
3. `__post_init__` 执行路径分析（lines 588–615）:
   - `_validate_common_candidate_fields(self)` → 通过（所有子结构字段有效）。
   - `_validate_duplicate_fields(self)` → `governance.duplicate is None` → 立即返回（line 4130）。
   - `self.tool_fact_kind is ToolFactKind.LOST` — 不匹配 COMPLETED（line 597）、FAILED/CANCELLED（line 602）、GOVERNED_ERROR（line 609）、REUSE（line 612）。
   - 命中 `else: raise ValueError("unsupported tool_fact_kind")`（line 615）。
4. 断言 `pytest.raises(ValueError, match="unsupported tool_fact_kind")` 精确匹配。

该测试证明 LOST 不会被静默接受为 completed/result/reuse/governed fact。不需要 durable store — 纯 validator 测试性质正确。

### RR-TOOL-04 Closure: Sub-structure Direct Validator Tests

**Verdict: CLOSED**

7 个子结构 validator 均获得至少一个直接负例测试，与 production validator 逐项对齐：

| 子结构 | 测试 | Production Validator | 验证路径 |
|---|---|---|---|
| `ToolAcceptIdentity` | `test_tool_accept_identity_rejects_empty_fields` (lines 712–746) | `_validate_tool_accept_identity` (line 3936) | 4 个字段逐一空字符串 → `_require_non_empty_text` → ValueError |
| `ToolAcceptCall` | `test_tool_accept_call_rejects_invalid_digest` (lines 749–764) | `_validate_tool_accept_call` (line 3953) | `tool_schema_digest="not-a-sha256-digest"` → `_require_sha256_digest` → ValueError |
| `ToolAcceptResult` | `test_tool_accept_result_rejects_payload_ref_digest_mismatch` (lines 767–784) | `_validate_tool_accept_result` (line 3979) | `payload_digest ≠ payload_ref.payload_digest` → line 3995 ValueError |
| `ToolAcceptDuplicateGovernance` | `test_tool_accept_duplicate_governance_rejects_invalid_fields` (lines 787–819) | `_validate_tool_accept_duplicate_governance` (line 4002) | scope=None → line 4035; message=None → line 4037; bad ref → line 4039 |
| `ToolAcceptGovernance` | `test_tool_accept_governance_rejects_non_policy_decision` (lines 822–834) | `_validate_tool_accept_governance` (line 4043) | `cast(ToolPolicyDecision, "bad-...")` → line 4051 isinstance fail → ValueError |
| `ToolAcceptIdempotency` | `test_tool_accept_idempotency_rejects_invalid_semantic_digest` (lines 837–848) | `_validate_tool_accept_idempotency` (line 4063) | `semantic_input_digest="not-a-sha256-digest"` → `_require_sha256_digest` → ValueError |
| `ToolAcceptDiagnostics` | `test_tool_accept_diagnostics_rejects_non_diagnostic_ref` (lines 851–862) | `_validate_tool_accept_diagnostics` (line 4081) | `cast(ToolTraceDiagnosticRef, "bad-...")` → line 4090 isinstance fail → ValueError |

### Finding 01 (Nonblocking): `_validate_tool_accept_duplicate_governance` 部分分支无直接负例

**Severity**: 低（非阻塞）。

**证据**: `_validate_tool_accept_duplicate_governance` (lines 4002–4040) 共有 7 个独立 raise 路径。新增测试覆盖其中 3 个：
- `duplicate_scope is None` → line 4035 ✓
- `duplicate_decision_message is None` → line 4037 ✓
- `reuse_prior_event_refs` contains non-HostEventRef → line 4039 ✓

未覆盖路径：
- `duplicate_decision` 非 `DuplicateDecisionKind` → line 4020
- `duplicate_scope` 非 `DuplicateGovernanceScope` → line 4024
- REUSE/HINT/REQUIRE_JUSTIFICATION/HARD_STOP/DURABLE_MISSING 时 `duplicate_key is None` → line 4033

**影响**: 这三条路径由 pyright 在构造期兜底（类型检查阻止传入错误类型），且 handoff 仅要求"缺 scope/message 或非法 prior ref 拒绝"。不为阻塞。

**建议**: 不需要当前 gate 修复。若后续组织 validator 测试矩阵，可考虑并入。

### Finding 02 (Nonblocking): `_validate_tool_accept_governance` `tool_idempotency_key` 与 `duplicate` 类型检查无直接负例

**Severity**: 低（非阻塞）。

**证据**: `_validate_tool_accept_governance` (lines 4043–4060) 有 4 条校验路径。新增测试仅覆盖 `policy_decision` 非 `ToolPolicyDecision` 路径（line 4052）。`tool_idempotency_key` optional 非空（line 4054–4056）与 `duplicate` 类型检查（line 4057–4060）未被直接负例覆盖。

**影响**: 同上，pyright 兜底 + handoff 明确范围。不为阻塞。

### Finding 03 (Nonblocking): `_validate_tool_accept_call` 仅覆盖单 digest 路径

**Severity**: 低（非阻塞）。

**证据**: `_validate_tool_accept_call` (lines 3953–3976) 校验 3 个 digest 字段 + 3 个文本字段。新增测试仅对 `tool_schema_digest` 做负例。所有 digest 字段使用同一 `_require_sha256_digest` 函数，所有文本字段使用同一 `_require_non_empty_text` 函数。覆盖代表性路径足以证明 validator 功能。

**影响**: 无。

## AGENTS.md Compliance Check

### 中文 docstring

全部 8 个新增测试函数均有完整中文 docstring，包含 `:returns:` 与 `:raises:` 子句。符合要求。✓

### 禁止 `Any` / `object`

新增代码未使用 `Any` 或 `object` 类型。`cast(ToolPolicyDecision, ...)` 等用法是显式类型转换，目标类型明确，不构成类型逃避。✓

### 禁止逃避类型边界

`cast` 用法用于向类型检查器声明"我故意传错类型以测试运行时 validator"，而非逃避设计约束。handoff 明确允许此模式："如果 pyright 对'故意传错类型'的测试不允许直接构造，请优先使用 `typing.cast`"。✓

### 测试耦合

未引入跨文件共享 test builder。`test_lost_tool_fact_kind_fails_fast_as_unsupported` 使用同文件已有 `_SeededRun` + `_completed_candidate` helper，其余测试直接构造子结构实例。无新增模块级 helper。✓

## README / Doc Sync Judgment

Implementation report 裁决为"不更新 README"，依据：
- 本次仅补测试覆盖，不修改 production 接口、CLI、配置、schema、架构边界或用户可见行为。
- 按 README 触发规则：`tests/` 修改触发 `tests/README.md` 检查，但本次新增测试不改变测试分层、运行方式或约定，不触发更新。

**复核结论**: 同意。测试新增为现有测试文件的增量补充，不改变测试目录结构、运行方式或维护规则。

## Validation Coverage

### 测试执行

- 单文件 `tests/host/test_toolruntime_accept_barrier.py`: 24 passed (16 existing + 8 new) ✓
- 组合 `accept_barrier + duplicate_governance + diagnostics`: 56 passed ✓
- pyright `tests/host/test_toolruntime_accept_barrier.py dayu/host/tool_runtime.py`: 0 errors, 0 warnings ✓

### 覆盖充分性

- RR-TOOL-03（LOST fail-fast）: 有直接测试，证明 LOST 在 `__post_init__` 被 fail-fast 拒绝 ✓
- RR-TOOL-04（子结构 validator）: 7 个子结构各至少 1 个直接负例 ✓
- 未引入跨文件耦合 ✓
- pyright 干净 ✓

## Final Verdict

**pass**

### Summary

- RR-TOOL-03: CLOSED — `ToolFactKind.LOST` explicit negative test 证明 LOST 在 candidate 构造期 fail-fast，不会被误当作 accepted result/reuse/governed fact。
- RR-TOOL-04: CLOSED — 7 个 accept candidate 子结构 validator 均获得直接负例测试，覆盖空字段、非法 digest、payload ref digest mismatch、duplicate governance 字段组合、policy 类型、idempotency digest 与 diagnostic ref 类型。
- Findings: 3 条 nonblocking（validator 分支覆盖率），均不要求当前 gate 修复。
- AGENTS.md 合规: 中文 docstring、无 Any/object、无类型逃避、无跨文件测试耦合，全部通过。
- README/doc sync: 无需更新。
- Validation: tests 24/56 passed, pyright 0 errors.
