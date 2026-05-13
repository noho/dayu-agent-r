# Gateflow Code Review — Host P0 S1 Engine Context Compaction

- Work gate: `code review`
- Work unit: Host Phase 0 / P0 - Engine Context Compaction Event 语义前置
- Assigned slice: `P0-S1 engine-contract-unknown-budget`
- Approved plan path: `docs/host/phase0-engine-context-compaction-plan.md`
- Implementation artifact: `docs/reviews/gateflow-implementation-host-p0-s1-engine-context-compaction-20260513.md`
- Accepted plan commit: `866f6f5`
- Review artifact path: `docs/reviews/gateflow-code-review-host-p0-s1-engine-context-compaction-ds-20260513.md`
- Reviewer: AgentDS

## Review Scope

Target files reviewed:

- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/contracts/agent_run.py`
- `dayu/engine/agent.py`
- `tests/engine/test_engine_event_contract.py`
- `tests/engine/test_agent_phase2.py`
- `tests/engine/runners/openai/test_http_error_event.py`
- `docs/reviews/gateflow-implementation-host-p0-s1-engine-context-compaction-20260513.md`

## Review Method

1. 逐文件对比 approved plan §4 合约变更、§6 P0-S1 exact allowed changes、expected assertions 与 stop conditions。
2. 逐文件对比 hard constraints：Engine 不实现 proactive governance；`budget_state` 为 `ContextBudgetSnapshot | None` 且无默认值；`None` 为唯一 unknown 表达；不要求 dataclass 类型级零值禁止。
3. 验证 provider_request_id 全链路透传、event ordering、recoverable semantics、reason 保留。
4. 验证 `0/0/0` sentinel 已从生产代码与当前 tests 中清除。
5. 运行全量 Engine 回归测试与 pyright 类型检查。
6. 运行旧 sentinel 多行搜索并对命中逐条分类。

## Per-File Contract Verification

### dayu/engine/contracts/engine_events.py

- `ContextCompactionRequestedData.budget_state: ContextBudgetSnapshot | None` —— 与 plan §4.1 一致 ✅
- 字段无默认值，调用方必须显式面对该字段 ✅
- 中文 docstring 写明 `None` 表示 provider overflow 边界预算未知 / 未上报 ✅
- `reason: str` 保留字符串类型（plan 明确 P0 不引入 reason enum）✅
- `provider_request_id: str | None` 保留 ✅
- `__all__` 导出未变更 ✅

### dayu/engine/contracts/agent_run.py

- `ContextBudgetSnapshot` 中文 docstring 已删除 `0/0/0` 占位语义 ✅
- 明确 "不含计算逻辑、不消费阈值、不承载 unknown marker" ✅
- 明确 "预算未知时，使用方必须在持有本类型的字段上显式表达缺失语义" ✅
- `prompt_tokens: int / completion_tokens: int / total_tokens: int` 无校验逻辑，零值合法（plan 明确不要求类型级零值禁止）✅
- 公共导出 (`__all__`) 未变更 ✅

### dayu/engine/agent.py

- `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED` 分支（L1237-L1253）✅
  - `budget_state=None` ✅
  - `reason=_ERROR_CONTEXT_COMPACTION_REQUIRED` 保留 ✅
  - `provider_request_id=data.provider_request_id` 保留 ✅
  - `RunFailedData(recoverable=True)` 保留 ✅
  - `_CONTEXT_COMPACTION_REQUIRED_MESSAGE` 保留 ✅
- 非 context overflow 的 HTTP error 路径未被修改（仍为 `recoverable=False`）✅
- Engine 不实现 compact / retry / tokenizer / Host state transition ✅

### tests/engine/test_engine_event_contract.py

- `test_provider_request_id_fields_are_locked` (L158-L179) 锁定 `ContextCompactionRequestedData` 四字段为 `iteration_id, budget_state, reason, provider_request_id` ✅
- `test_context_compaction_budget_state_accepts_unknown_and_snapshot` (L182-L213) ✅
  - `budget_state=None` 构造合法 ✅
  - `budget_state=ContextBudgetSnapshot(1000, 500, 1500)` 构造合法 ✅
  - `budget_state` 字段无默认值 ✅
- 无 `ContextBudgetSnapshot(0, 0, 0)` 断言或构造 ✅

### tests/engine/test_agent_phase2.py

- `test_context_overflow_http_error_maps_to_compaction_required_fact` (L543-L587) ✅
  - event ordering: `ITERATION_STARTED → CONTEXT_COMPACTION_REQUESTED → ITERATION_COMPLETED → RUN_FAILED` ✅
  - `compact_event.data.budget_state is None` ✅
  - `compact_event.data.provider_request_id == "req_context"` ✅
  - `IterationCompletedData.provider_request_id == "req_context"` ✅
  - `RunFailedData.error_code == "context_compaction_required"` ✅
  - `RunFailedData.provider_request_id == "req_context"` ✅
  - `RunFailedData.recoverable is True` ✅
- 无 `ContextBudgetSnapshot(0, 0, 0)` 断言或构造 ✅

### tests/engine/runners/openai/test_http_error_event.py

- `test_http_context_overflow_maps_to_context_length_exceeded` (L262-L293) ✅
  - HTTP 400 + `context_length_exceeded` body → `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED` ✅
  - `provider_request_id == "req_context"` (HTTP error + DoneData 双端验证) ✅
  - `RunnerDoneData.finish_reason is FinishReason.ERROR` ✅
  - `attempt=1, retried=False`（context overflow 不可重试）✅

### docs/reviews/gateflow-implementation-host-p0-s1-engine-context-compaction-20260513.md

- Implementation report 对 sentinel 搜索的 6 类命中逐条分类准确，无遗漏或误判 ✅
- 未实现项明确标注 P0-S2 deferred ✅
- Residual risk 分类正确：fixed current slice / later slice / later phase / deferred capability ✅
- Stop condition 状态正确：无 hit ✅

## Hard Constraint Verification

| 约束 | 状态 | 证据 |
|-------|--------|--------|
| Engine 不实现 proactive context governance | ✅ | `agent.py` 仅在 `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED` 分支触发 reactive event |
| Engine 不 compact / retry / 调 tokenizer | ✅ | 无 compact/retry/tokenizer 代码 |
| Engine 不执行 Host state transition | ✅ | 无 Host Run/Attempt 状态迁移逻辑 |
| `budget_state: ContextBudgetSnapshot \| None`, 无默认值 | ✅ | `engine_events.py:268` |
| `None` 是唯一 unknown 表达 | ✅ | docstring + 代码一致 |
| `ContextBudgetSnapshot(0,0,0)` 不作为 unknown sentinel | ✅ | sentinel 搜索在 dayu/ 和 tests/ 中无命中 |
| 不要求 dataclass 零值禁止 | ✅ | `ContextBudgetSnapshot` 无 `__post_init__` 校验 |
| `reason` 保留 str 类型 | ✅ | `engine_events.py:269` |
| `provider_request_id` 全链路透传 | ✅ | HTTP Error → Compaction → RunFailed + Done → IterationCompleted, 测试中均为 `"req_context"` |
| recoverable semantics 保留 | ✅ | `RunFailedData.recoverable=True` |
| 不修改 Host 代码 | ✅ | 无 Host 文件变更 |
| 不新增 UnknownBudget dataclass/enum/wrapper | ✅ | 未新增任何类型 |
| 不把事实放入 metadata | ✅ | 所有诊断事实在显式字段 |

## Event Ordering Verification

Context overflow 完整事件序列（`test_agent_phase2.py:571-576`）：

```
ITERATION_STARTED → CONTEXT_COMPACTION_REQUESTED → ITERATION_COMPLETED → RUN_FAILED
```

- `iteration_completed` 在 `context_compaction_requested` 之后、`run_failed` 之前 ✅
- `context_compaction_requested` 不是 terminal ✅
- `run_failed(context_compaction_required, recoverable=True)` 是 terminal ✅

## provider_request_id End-to-End Trace

```
RunnerHTTPErrorData.provider_request_id = "req_context"
  ├── ContextCompactionRequestedData.provider_request_id = "req_context" ✅
  └── RunFailedData.provider_request_id = "req_context" ✅
RunnerDoneData.provider_request_id = "req_context"
  └── IterationCompletedData.provider_request_id = "req_context" ✅
```

全部四端一致携带 `"req_context"`。

## Sentinel Search Classification

```bash
rg -n "ContextBudgetSnapshot\(|prompt_tokens=0|completion_tokens=0|total_tokens=0|0/0/0|占位快照" dayu tests docs README.md
```

命中分类（逐条人工核对）：

| 区域 | 命中 | 分类 | 结论 |
|------|------|--------|--------|
| `dayu/` (生产代码) | 0 | — | ✅ 无旧 sentinel |
| `tests/` (当前测试) | 2 | `test_engine_event_contract.py:199,209` | ✅ 均为 `ContextBudgetSnapshot(1000,500,1500)` 真实快照测试 |
| `docs/engine/design.md` | 1 | L415 `0/0/0` 旧文本 | ⚠️ P0-S2 清理范围，非本 slice |
| `docs/engine/phase5-plan-review.md` | 2 | L122, L126 历史 review 引用 | ✅ 历史 artifact |
| `docs/engine/phase0-plan.md` | 1 | L204 类型签名引用 | ✅ 非 sentinel 使用 |
| `docs/host/implementation-control.md` | 6 | 旧追踪文本 + 新 controller 状态 | ✅ 非 P0-S1 范围，implementation report 已声明未修改 |
| `docs/host/phase0-engine-context-compaction-plan.md` | 多 | 批准 plan 描述旧 sentinel 的证据/验证标准文本 | ✅ 自身即为 plan 真源 |

结论：生产代码和当前 tests 中无旧 unknown-budget sentinel 语义残留。

## Validation Results

| 命令 | 结果 |
|------|------|
| `pytest tests/engine/test_engine_event_contract.py tests/engine/test_agent_phase2.py::test_context_overflow_http_error_maps_to_compaction_required_fact tests/engine/runners/openai/test_http_error_event.py::test_http_context_overflow_maps_to_context_length_exceeded -q` | 13 passed |
| `pytest tests/engine tests/engine/runners/openai/test_context_overflow_classifier.py -q` | 323 passed |
| `pyright` | 0 errors, 0 warnings, 0 informations |
| sentinel 搜索 | 生产代码 + 当前 tests 无旧语义命中 |

## Findings

无。

本次 review 在以下维度未发现任何需要修复的问题：

- correctness（合约语义与代码一致）
- public contract drift（ `budget_state` 类型与 docstring 一致）
- type safety（pyright 零错误）
- Engine/Host boundary（Engine 无 proactive governance）
- event ordering（四个事件严格有序）
- provider_request_id preservation（四端一致）
- recoverable `run_failed` semantics（`recoverable=True`）
- test coverage（`None` + 真实 snapshot + Runner overflow event-path 均覆盖）
- old `0/0/0` unknown-budget sentinel 残留（生产代码与当前 tests 中已清除）

## Open Questions

无。

## Residual Risks

以下风险已由 plan §11 和 implementation report 明确归属，review 确认无需在本 slice 处理：

1. **`docs/engine/design.md` §15 仍含 `0/0/0` 旧文本**：归属 P0-S2 docs sync。当前不阻塞 P0-S1 closeout，但必须在 P0-S2 中清理。
2. **Host EngineEvent ingest validation 对 `budget_state=None` 的接受**：归属 Phase 5 dispatch / reactive failure closeout。
3. **Host Context Governance semantic interpretation / estimator / policy / compact decision**：归属 Phase 10 Context Governance / Compaction。
4. **`reason: str` 保持字符串而非 StrEnum**：plan §10.1 已评估为非阻塞风险，归属 Phase 5 / Phase 10 ingest mapping。
5. **`ContextBudgetSnapshot` 类型级不禁止零值**：plan §4.1 明确不要求零值禁止；语义负担在使用方，当前合约已通过 `None` 区分 unknown。

## Conclusion

**结论: PASS**

P0-S1 实现完整、正确，完全符合 approved plan 的所有合约变更、allowed changes、expected assertions 和 hard constraints。零 finding 需要修复。P0-S2 文档同步可以安全进入。

Controller decision status for all findings: pending-controller-decision（本次 review 零 finding，此项为形式保留）。
