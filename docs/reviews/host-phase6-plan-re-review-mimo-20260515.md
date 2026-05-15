# Host Phase 6 Plan Re-Review - MIMO - 2026-05-15

- **reviewer**: AgentMiMo (role-scoped plan re-review)
- **reviewed target**: `docs/host/phase6-toolruntime-truncation-fetch-more-plan.md` (after plan fix)
- **controller adjudication**: `docs/reviews/host-phase6-plan-review-controller-adjudication-20260515.md`
- **current gate**: Phase 6 plan re-review after plan fix
- **verdict**: PASS

## Accepted Findings 复核

### DS-F1 - PolicySnapshot 与 no-tool 硬约束未拆解

**状态**: FIXED

Plan fix 覆盖点：
- §3.3.1 明确 `PolicySnapshot.__post_init__` 只校验 policy reference consistency 和 typed field coherence，不得无条件拒绝 `allow_tool_calls=True`。
- §3.3.1 明确 no-tool validation 只在 `NO_TOOL_REPLAY` / `NO_TOOL_DISABLED` 下执行；tool-enabled 有独立校验路径。
- §6 P6-S1 exact changes 包含：Split `PolicySnapshot.__post_init__`；split or conditionalize `_validate_no_tool_snapshot`。
- §7 unit tests 包含：`PolicySnapshot(allow_tool_calls=True)` is valid for `ToolExecutionMode.TOOL_ENABLED`。

### DS-F2 - DefaultSceneParameterProvider 硬编码 tools=disabled

**状态**: FIXED

Plan fix 覆盖点：
- §3.3.1 明确 `DefaultSceneParameterProvider` must derive system-message tool status from `ToolExecutionMode` plus policy / tool snapshot；must not output `tools=disabled` for `TOOL_ENABLED`。
- §6 P6-S1 exact changes 包含：Update `DefaultSceneParameterProvider` so system messages reflect mode/policy。
- §7 unit tests 包含：tool-enabled scene/system messages do not contain `tools=disabled`；replay/no-tool scene/system messages still express no-tool。

### DS-F3 - RunInputBuilder 工具启用/禁用决策机制缺失

**状态**: FIXED

Plan fix 覆盖点：
- §3.3.1 新增完整的 `ToolExecutionMode` section，定义三种 typed enum mode：`TOOL_ENABLED`、`NO_TOOL_REPLAY`、`NO_TOOL_DISABLED`。
- §3.3.1 明确 RunInputBuilder 通过显式 `ToolExecutionMode` 选择 provider，禁止反推。
- §3.3.1 明确 `AttemptDispatchSnapshot` 携带 mode 为 approved Host typed contract change。
- §3.9 replay guard 更新为引用 `ToolExecutionMode.NO_TOOL_REPLAY`，双层防线第一层触发条件明确。
- §6 P6-S1 exact changes 包含：Add `ToolExecutionMode`；pass it explicitly from Host dispatch / builder construction。

### DS-F4 - engine_ingest.py 工具事件映射变更未细化

**状态**: FIXED

Plan fix 覆盖点：
- §4.3.1 新增独立小节，明确列举 `TOOL_CALL_REQUESTED`、`TOOL_RESULT_ACCEPTED`、`TOOL_CALLS_BATCH_READY`、`TOOL_CALLS_BATCH_DONE`、`TOOL_CALL_DELTA` 等 EngineEvent 工具事件必须保持 `PREVIEW` / `DIAGNOSTIC`。
- §4.3.1 明确 `ToolRuntime -> HostToolFactAcceptPort` 是唯一 canonical owner。
- §6 P6-S2 exact changes 明确：Keep EngineEvent tool mappings diagnostic / preview only；if current mapping is canonical, downgrade it。
- §7 unit tests 包含：EngineEvent tool mappings remain preview / diagnostic and cannot append canonical tool facts。
- §7 integration tests 包含：EngineEvent ingest cannot bypass accept path to write tool result facts。

### MIMO-F1 - EventLog 工具事件类型假设未显式验证

**状态**: FIXED

Plan fix 覆盖点：
- §4.2 新增明确记录："Current EventLog `append_event` does not perform global closed-set validation for `event_type`；P6 normally does not need a schema version bump just to append new `TOOL_*` event types"。
- §4.2 限定 allowed schema/code changes 范围：adding tool canonical event payload types / codecs / payload validators。

### MIMO-F2 / DS-F9 - 批量 ToolExecutor 并发语义 / 批内 partial accept failure 测试覆盖

**状态**: FIXED

Plan fix 覆盖点：
- §3.4 步骤9 新增明确约束："批内一个 call 的 accept failure 不得让其它已 accepted call 的事实回滚"。
- §7 unit tests 新增："batch execution with one accept failure does not roll back other already accepted calls in the same batch"。
- §7 integration tests 新增："mixed batch accept outcomes return accepted call results and governed errors for failed accepts without EventLog rollback"。
- §6 P6-S3 tests 新增："batch with mixed accept outcomes keeps already accepted call outcomes visible to Engine and returns governed error only for rejected/timed-out calls"。

### MIMO-F3 - ToolAwaitingOutcome 受治理结果类型未指定

**状态**: FIXED

Plan fix 覆盖点：
- §3.4 步骤5 明确：Phase 6 maps `ToolAwaitingOutcome` to `ToolFailedOutcome` with governed error message。
- §3.9 Awaiting section 明确：policy decision uses `governed_error`；canonical fact kind is `governed_error`；`unsupported_awaiting` is only a policy reason / diagnostic reason and must not become a canonical `ToolFactKind`。
- §3.5 `ToolFactKind` 表格明确 `governed_error` 行的必填字段与 `unsupported_awaiting` 约束。
- §7 unit tests 新增：P6 awaiting unsupported guard 覆盖完整映射路径。

### DS-F5 - 测试文件迁移范围未量化

**状态**: FIXED

Plan fix 覆盖点：
- §5.2 P6-S3 test files 明确："Prefer no change to `tests/host/test_phase5_local_execution_integration.py`；only touch it if an assertion explicitly names Phase 5 no-tool internals that P6 removes. Add new Phase 6 integration tests instead of migrating broad Phase 5 coverage"。
- 新增独立的 `tests/host/test_phase6_toolruntime_integration.py` 覆盖 Phase 6 integration 测试。

### DS-F6 - TruncationManager 与 business ToolTruncateSpec 的 wiring 未指定

**状态**: FIXED

Plan fix 覆盖点：
- §3.6 新增明确约束："`TruncationManager` construction must receive `truncate_specs_by_name: Mapping[str, ToolTruncateSpec]` from the same `EffectiveToolBundle.truncate_specs_by_name` used by schema projection and dispatcher"。
- §6 P6-S4 exact changes 新增："Initialize `TruncationManager` from `EffectiveToolBundle.truncate_specs_by_name`；business `ToolTruncateSpec` must not be recomputed from another source"。
- §7 unit tests 新增："`TruncationManager` uses `EffectiveToolBundle.truncate_specs_by_name` for business `ToolTruncateSpec`"。

### DS-F7 - P6-S3 执行流步骤3隐含依赖 P6-S5 的 duplicate pass-through

**状态**: FIXED

Plan fix 覆盖点：
- §6 P6-S3 exact changes 新增："Inject `PassThroughDuplicateGovernance` always-allow stub for P6-S3；P6-S5 replaces it with the full duplicate matrix"。
- §6 P6-S3 non-goals 更新为："no duplicate governance beyond pass-through `allow`"。

### DS-F8 - ToolFactAcceptCandidate 字段构造时机与校验规则未指定

**状态**: FIXED

Plan fix 覆盖点：
- §3.5 新增完整的 `ToolFactAcceptCandidate.__post_init__` 校验规则表，按 `ToolFactKind` 列出必填字段与受限字段。
- §3.5 新增 `accept_idempotency_key` / `semantic_input_digest` 非空格式校验要求。
- §3.5 新增 `duplicate_decision` 与 `duplicate_key` 联动校验规则。
- §7 unit tests 新增："`ToolFactAcceptCandidate.__post_init__` enforces required fields for `completed` / `failed` / `cancelled` / `reuse` / `governed_error`"。

### DS-F10 - duplicate key 是否包含 index_in_iteration 未明确

**状态**: FIXED

Plan fix 覆盖点：
- §3.7 新增明确声明："`index_in_iteration` is explicitly excluded from the duplicate key. Two calls in the same iteration with the same tool identity and same normalized arguments must still enter duplicate governance"。
- §6 P6-S5 exact changes 新增："Compute duplicate key without `index_in_iteration`"。
- §7 unit tests 新增："duplicate key excludes `index_in_iteration`；two same-iteration calls with different indexes and same normalized args still enter duplicate governance"。

## New Blocking Findings

无。

## Finding 统计

- accepted finding count: 12
- fixed count: 12
- still open count: 0
- new blocking count: 0

## 验证结果

```bash
cd /Users/leo/workspace/dayu-agent-r && git diff --check docs/host/phase6-toolruntime-truncation-fetch-more-plan.md
```

- 无 whitespace 错误。

## 结论

所有 12 个 controller accepted findings（DS-F1~F4 为 blocking，DS-F5~F10 + MIMO-F1~F3 为 non-blocking）均已修复。Plan fix 通过在 §3.3.1 新增 `ToolExecutionMode` 完整定义、§4.3.1 新增 EngineEvent 工具事件 preview 限制、§3.4/§3.5/§3.6/§3.7/§3.9 细化校验规则与 wiring 约束、§6 各 slice exact changes 显式列出变更项、§7 测试矩阵补充覆盖缺口等方式，系统性地收敛了所有 accepted findings。MIMO-F4 未修复符合 controller 裁决（no-fix）。

---

- **artifact path**: `docs/reviews/host-phase6-plan-re-review-mimo-20260515.md`
- **verdict**: PASS
- **blocking count**: 0
- **finding count**: 12 (all fixed)
