# P9.5 S12 ToolRuntime Truncation / Duplicate Defensive Hardening — Code Review (AgentDS)

## Gate

- Work unit: P9.5 Pre-P10 Cross-Repository Hardening
- Slice: S12 ToolRuntime Truncation / Duplicate Defensive Hardening
- Approved plan: `docs/host/p9-5-pre-p10-hardening-plan.md` S12
- Implementation artifact: `docs/reviews/p9-5-s12-toolruntime-truncation-duplicate-hardening-implementation-20260517.md`
- Role: review agent only (AgentDS). 不改代码，不 commit/push/PR，不进入其它 gate。
- Review scope: `dayu/host/tool_runtime.py`, `tests/host/test_toolruntime_truncation_fetch_more.py`, `tests/host/test_toolruntime_duplicate_governance.py`, `tests/host/test_toolruntime_accept_barrier.py`, `dayu/host/README.md`, `tests/README.md`, implementation artifact.

## Review Methodology

1. 逐行审查 diff 中新增/修改的全部生产代码与测试代码。
2. 对每个新增校验，回溯全部 production call site，模拟输入场景并验证是否产生误拒。
3. 对每个新增 truncation test，验证是否经过真实 `TruncationManager` / `DefaultToolRuntimeFactory` 路径。
4. 对每个新增 duplicate validation test，验证 candidate 构造与 `_policy_decision_from_duplicate` 的一致性。
5. 检查 README 变更是否只描述当前事实、不包含未来设计。
6. 检查是否符合 S12 的 Non-Goals（无 durable cursor table、duplicate ledger、Tool Trace projection、policy default change、Host/Engine special fetch_more branch、public API/error taxonomy change、business-specific rules）。

## Finding Summary

**Blocking: 0**
**Non-blocking observation: 1**
**Residual risks: 3**

---

## Detailed Findings

### Non-Blocking Observation N1: ToolPolicyDecisionKind 与 DuplicateDecisionKind 隐式值耦合

- **入口/函数**: `_validate_duplicate_governed_candidate` → `candidate.policy_decision.kind.value != decision.value` (tool_runtime.py:3750)
- **输入场景**: 两个独立 `StrEnum` 的比较依赖相同的 `.value` 字符串（如 `"hint"`, `"hard_stop"`）
- **实际行为**: `ToolPolicyDecisionKind.HINT.value == "hint"`, `DuplicateDecisionKind.HINT.value == "hint"` — 当前定义一致
- **预期**: 当前实现正确，两者定义在同一模块、共享 `"hint"` / `"require_justification"` / `"hard_stop"` 值
- **直接证据**: `tool_runtime.py:205-216` (ToolPolicyDecisionKind) 与 `tool_runtime.py:219-226` (DuplicateDecisionKind) 定义一致
- **影响**: 低。若未来一方独立变更枚举值而另一方未同步，此校验会在构造期 fails closed，不会静默接受错误候选。当前两枚举均在同一文件由同一 owner 维护，耦合可接受。
- **建议验证点**: Contract Ownership audit (S16) 时可留意两个枚举是否应显式声明"共享语义值集合"的约束关系。
- **严重程度**: observation（非缺陷）

---

## 逐项审查

### 1. `_validate_policy_decision_fields` (新增, tool_runtime.py:3667-3688)

**审查问题**: 是否误拒合法 ALLOW / governed 决策？

**验证路径**:

| 生产路径 | policy_decision 构造 | 校验结果 |
|---------|---------------------|---------|
| 普通 allow (line 1237) | `kind=ALLOW, reason_code=None, message=None` | ALLOW 无 reason/message → pass |
| Timeout (line 4978) | `kind=GOVERNED_ERROR, reason_code=_TOOL_RUNTIME_TIMEOUT_REASON, message="tool execution timed out after..."` | governed 有 reason+message → pass |
| Cancel (line 4964) | `kind=GOVERNED_ERROR, reason_code=_TOOL_RUNTIME_CANCELLED_REASON, message="tool execution cancelled..."` | governed 有 reason+message → pass |
| No-tool (line 1222) | `kind=GOVERNED_ERROR, reason_code=_TOOL_RUNTIME_NO_TOOL_REASON, message="tool calls are disabled..."` | governed 有 reason+message → pass |
| Duplicate HINT (line 4334-4348) | `kind=HINT, reason_code="duplicate_hint", message="duplicate tool call should use..."` | governed 有 reason+message → pass |
| Duplicate HARD_STOP (line 4334-4348) | `kind=HARD_STOP, reason_code="duplicate_hard_stop", message="duplicate tool call hard-stopped..."` | governed 有 reason+message → pass |
| Duplicate REQUIRE_JUSTIFICATION (line 4334-4348) | `kind=REQUIRE_JUSTIFICATION, reason_code="duplicate_requires_justification", message="duplicate tool call requires..."` | governed 有 reason+message → pass |
| Duplicate REUSE (line 4334-4348) | `kind=REUSE, reason_code="duplicate_reuse", message="reuse prior accepted tool result"` | governed 有 reason+message → pass |

**结论**: 全部 production call site 通过校验。ALLOW 的 `reason_code=None, message=None` 约定被所有 call site 遵守（line 1237-1240）。非 ALLOW 的 `reason_code` 与 `message` 必填约定同样被所有 call site 遵守。无误拒风险。

---

### 2. `_validate_governed_error_candidate` (新增, tool_runtime.py:3691-3709)

**审查问题**: 是否会误拒 timeout / cancellation / plain governed_error？

**数据流分析**:

- **Timeout**: `_dispatch_tool_call_with_bounds` (line 2485-2489) → `_runtime_timeout_policy_decision` → `kind=GOVERNED_ERROR` → `_tool_fact_accept_candidate` → `_tool_fact_kind` returns `GOVERNED_ERROR` (因为 `kind is not ALLOW`) → `duplicate_governed=False` (因为 line 2367 在 dispatch 前求值) → `reuse_prior_event_refs=()` → `__post_init__` → `_validate_governed_error_candidate` → `kind is GOVERNED_ERROR` → check `reuse_prior_event_refs` is empty → **pass** ✅

- **Cancel**: 同上，`_runtime_cancelled_policy_decision` → `kind=GOVERNED_ERROR` → same flow → **pass** ✅

- **No-tool / scope mismatch**: `kind=GOVERNED_ERROR`, `reuse_prior_event_refs=()` → **pass** ✅

- **Duplicate HINT**: `_policy_decision_from_duplicate` → `kind=HINT` → `duplicate_governed=True` → `reuse_prior_event_refs=duplicate_decision.prior_event_refs` (非空) → `_validate_governed_error_candidate` → `kind is HINT` (非 ALLOW/REUSE) → 进入 `_validate_duplicate_governed_candidate` → **pass** ✅ (详见下节)

- **ALLOW + GOVERNED_ERROR 非法组合**: `kind=ALLOW` → `_validate_governed_error_candidate` raises "governed_error requires governed policy decision" → correctly rejected ✅

**结论**: 无误拒。三种合法路径 (plain governed_error, duplicate governed, REUSE-governed) 各自进入正确的校验分支。

---

### 3. `_validate_duplicate_governed_candidate` (新增, tool_runtime.py:3712-3738)

**审查问题**: policy kind / reason / message 严格匹配是否与生产构造函数一致？

**一致性验证**:

生产唯一构造函数 `_policy_decision_from_duplicate` (line 4334-4348):
```python
kind=ToolPolicyDecisionKind(decision.kind.value),     # "hint"/"hard_stop"/"require_justification"
reason_code=_duplicate_reason_code(decision.kind),    # 同一函数
message=_duplicate_message(decision.kind),             # 同一函数
```

校验函数:
```python
candidate.policy_decision.kind.value != decision.value       # 字符串值相等
candidate.policy_decision.reason_code != _duplicate_reason_code(decision)  # 同一函数
candidate.policy_decision.message != _duplicate_message(decision)          # 同一函数
```

**结论**: 校验使用与构造函数完全相同的 `_duplicate_reason_code` / `_duplicate_message`。不存在因两处独立维护导致 false positive 的风险。严格匹配设计正确——若未来新增 duplicate decision 类型但忘记更新构造函数，校验会在构造期 fails closed。

---

### 4. `_validate_result_fact_policy` (新增, tool_runtime.py:3741-3752)

**审查问题**: 普通 COMPLETED / FAILED / CANCELLED 要求 ALLOW policy 是否正确？

**数据流分析** (`_tool_fact_kind`, line 4657-4678):
```python
if policy_decision.kind is not ToolPolicyDecisionKind.ALLOW:
    return ToolFactKind.GOVERNED_ERROR
```

所以 COMPLETED / FAILED / CANCELLED 只能在 `policy_decision.kind is ALLOW` 时出现。`_validate_result_fact_policy` 只是把这个不变式显式编码为校验——若 bug 导致非 ALLOW policy 的 outcome 被错误映射到 COMPLETED/FAILED/CANCELLED，会在构造期 fails closed。

**结论**: 检验是正确的 defensive invariant，不会误拒任何合法路径。

---

### 5. `_validate_reuse_candidate` 扩展 (修改, tool_runtime.py:3767-3775)

**审查问题**: reuse 的 policy kind / reason / message 严格匹配是否与生产构造函数一致？

**一致性验证**: 与 `_validate_duplicate_governed_candidate` 同理，校验使用与 `_policy_decision_from_duplicate` 完全相同的 `_duplicate_reason_code(DuplicateDecisionKind.REUSE)` / `_duplicate_message(DuplicateDecisionKind.REUSE)`。

`_duplicate_message(DuplicateDecisionKind.REUSE)` 返回 `"reuse prior accepted tool result"`，`_duplicate_reason_code(DuplicateDecisionKind.REUSE)` 返回 `"duplicate_reuse"`。

`test_toolruntime_accept_barrier.py:545` 的 `_reuse_candidate` fixture 已同步更新 `message="reuse prior accepted tool result"`（从旧的 `"reuse prior accepted result"` 改为与生产常量一致）。

**结论**: 生产构造函数与校验使用同一套常量。test fixture 同步正确。

---

### 6. Truncation 新测试

#### 6a. `test_text_lines_truncation_fetch_more_returns_remaining_lines` (新增, test_toolruntime_truncation_fetch_more.py:204-247)

- **覆盖策略**: `TEXT_LINES` + `max_lines=2`
- **输入**: `"line-1\nline-2\nline-3\nline-4"` → 可见部分 `"line-1\nline-2"`, fetch_more 返回 `"line-3\nline-4"`
- **路径**: `_handle` → `DefaultToolRuntimeFactory` + `enable_truncation_manager=True` → 真实 `TruncationManager._truncate_text_lines`
- **结论**: 覆盖真实路径 ✅

#### 6b. `test_list_items_truncation_fetch_more_returns_remaining_items` (新增, test_toolruntime_truncation_fetch_more.py:250-291)

- **覆盖策略**: `LIST_ITEMS` + `max_items=1`
- **输入**: `["first", {"second": True}, 3]` → 可见部分 `["first"]`, fetch_more 返回 `[{"second": True}, 3]`
- **路径**: 真实 `TruncationManager._truncate_list_items`
- **结论**: 覆盖真实路径 ✅

#### 6c. `test_binary_bytes_truncation_fetch_more_returns_base64_remainder` (新增, test_toolruntime_truncation_fetch_more.py:293-330)

- **覆盖策略**: `BINARY_BYTES` + `max_bytes=2`
- **输入**: `base64.b64encode(b"abcdef")` → 可见部分 `base64.b64encode(b"ab")`, fetch_more limit=2 返回 `base64.b64encode(b"cd")`
- **路径**: 真实 `TruncationManager._truncate_binary_bytes`
- **结论**: 覆盖真实路径 ✅

#### 6d. `test_fetch_more_rejects_used_cursor` (新增, test_toolruntime_truncation_fetch_more.py:360-376)

- **覆盖场景**: cursor 已标记 `used_at` 时 fetch_more 返回 `ToolFailedOutcome(hint="cursor_already_used")`
- **路径**: 通过 `_manager_from_handle` 直接修改 `TruncationManager._cursors` dict → 然后经过 `FetchMoreToolCallable` 读取 → 真实 cursor 校验路径
- **结论**: 覆盖真实 cursor 重用拒绝路径 ✅

#### 6e. `test_fetch_more_rejects_invalid_limit` (新增, test_toolruntime_truncation_fetch_more.py:379-391)

- **覆盖场景**: `limit=0` → fetch_more 返回 `ToolFailedOutcome(hint="invalid_fetch_more_request")`
- **路径**: `_fetch_more_call("fetch-call-1", cursor, scope_token, limit=0)` → `FetchMoreToolCallable` → 真实 limit 校验
- **结论**: 覆盖真实 invalid limit 拒绝路径 ✅

---

### 7. Duplicate 新测试

#### 7a. `test_governed_duplicate_candidate_validation_rejects_missing_prior_refs` (新增, test_toolruntime_duplicate_governance.py:316-322)

- **场景**: duplicate governed candidate 的 `reuse_prior_event_refs=()` → ValueError "requires prior event refs"
- **fixture**: `_governed_duplicate_candidate(DuplicateDecisionKind.HINT)` → 执行真实 duplicate governance → 获取真实 candidate → 用 `dataclasses.replace` 清空 prior refs → 验证构造期 reject
- **结论**: 正确覆盖 missing prior refs 防御 ✅

#### 7b. `test_governed_duplicate_candidate_validation_rejects_policy_mismatch` (新增, test_toolruntime_duplicate_governance.py:325-352)

- **场景**: HINT 决策 + HARD_STOP policy kind → ValueError "policy kind must match decision"
- **结论**: 正确覆盖 policy kind mismatch 防御 ✅

#### 7c. `test_governed_duplicate_candidate_validation_rejects_reason_mismatch` (新增, test_toolruntime_duplicate_governance.py:355-372)

- **场景**: HARD_STOP 决策 + `reason_code="duplicate_hint"` → ValueError "reason must match decision"
- **结论**: 正确覆盖 reason mismatch 防御 ✅

#### 7d. `test_governed_duplicate_candidate_validation_rejects_message_mismatch` (新增, test_toolruntime_duplicate_governance.py:375-391)

- **场景**: REQUIRE_JUSTIFICATION 决策 + `message="wrong duplicate governance message"` → ValueError "message must match decision"
- **结论**: 正确覆盖 message mismatch 防御 ✅

#### 7e. `test_governed_error_candidate_validation_rejects_allow_policy` (新增, test_toolruntime_duplicate_governance.py:394-411)

- **场景**: GOVERNED_ERROR fact + ALLOW policy → ValueError "governed_error requires governed policy decision"
- **fixture 注意事项**: 测试把 `duplicate_decision=None` 以绕过 `_validate_duplicate_fields` early return，使 candidate 能到达 `_validate_governed_error_candidate` 的 ALLOW 检查。这是一个 white-box 测试构造。
- **结论**: 正确覆盖 GOVERNED_ERROR 不允许 ALLOW policy 的防御 ✅

---

### 8. TruncationManager 初始化成本评估

**审查问题**: 生产规模问题是否需要 reassign 到 Phase 15？

**证据**:
- `DefaultToolRuntimeFactory.create_tool_runtime` (line 2902-2911): `TruncationManager.__init__` 仅保存 `session_id`, `run_id`, `attempt_id`, `truncate_specs_by_name`（只读视图），初始化空 `_cursors: dict[str, _CursorRecord]`
- 无文件 I/O、DB 访问、后台任务启动、网络调用、大内存分配
- 构造是 run-scoped（每次 Attempt 开始各构造一次），随 ToolRuntime handle 生命周期结束被 GC

**结论**: 当前无生产规模问题。实现 artifact 已添加中文注释记录此判断。无需 reassign 到 Phase 15。

---

### 9. README 变更审查

#### 9a. `dayu/host/README.md`

- Line 9-10: 截断策略描述从仅 `text_chars` 改为覆盖 `text_chars`、`text_lines`、`list_items` 与 `binary_bytes`；cursor 校验新增 `invalid limit`
- Line 13: 新增 "duplicate governed candidate 会校验 policy kind、prior refs、reason 与 message 均匹配当前 duplicate decision"
- **判定**: 全部描述当前已实现行为，无未来设计承诺 ✅

#### 9b. `tests/README.md`

- Line 179: 覆盖率描述新增 `` `text_chars` / `text_lines` / `list_items` / `binary_bytes` truncation ``、`` invalid limit `` 错误路径、`duplicate governed candidate 字段一致性`
- **判定**: 与新增 tests 一一对应，描述当前覆盖事实 ✅

---

### 10. S12 Non-Goals 合规检查

| Non-Goal | 状态 |
|----------|------|
| 不实现 durable cursor table | ✅ 未引入 |
| 不实现 durable duplicate ledger | ✅ 未引入 |
| 不实现 Tool Trace projection | ✅ 未引入 |
| 不改变 policy default | ✅ 未改变 |
| 不添加 Host/Engine special fetch_more branch | ✅ 未添加 |
| 不改变 public API/error taxonomy | ✅ 未改变 |
| 不添加 business-specific rules | ✅ 未添加 |

---

## 残余风险

### R1: Truncation cursor 内存范围限制（已有，非本轮引入）

cursor 是 TruncationManager 内存 dict，不支持 crash / restart / cross-run recovery。这是设计边界，实现 artifact 已记录。若未来需要持久化，应归入对应 phase owner。

### R2: Duplicate registry 进程内范围限制（已有，非本轮引入）

`InMemoryRunScopedDuplicateGovernanceRegistry` 是进程内 run-local 能力，不提供 durable duplicate ledger。crash / restart 后重复风险继续由 RunInputBuilder 回放 accepted facts 降低。这是设计边界。

### R3: ToolPolicyDecisionKind 与 DuplicateDecisionKind 隐式值耦合（observation N1）

两个独立 `StrEnum` 通过 `.value` 字符串比较校验。当前共享相同值集合 `"hint"`, `"require_justification"`, `"hard_stop"`，校验正确。若未来独立变更，校验 fails closed（构造期 ValueError），不会静默接受错误候选。

---

## 审查结论

**建议: 通过。** 0 blocking finding。

新增校验与全部 14 个 production call site 一致，无误拒风险。truncation 新测试覆盖真实 `DefaultToolRuntimeFactory` / `TruncationManager` / `FetchMoreToolCallable` 路径。duplicate validation 测试使用真实 candidate + `dataclasses.replace` 构造边缘输入。README 变更只描述当前事实。TruncationManager 初始化无 Phase 15 问题。S12 Non-Goals 全部遵守。

1 non-blocking observation（N1: 枚举隐式值耦合），3 residual risks（均为已记录的现有设计边界或 observation N1 的扩展阐述）。
