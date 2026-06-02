# WU-TOOL-02 Slice 2 Code Review — AgentMiMo

## Review Target

- Branch: `refactor/wu-tool-02-accept-candidate-cleanup`
- Gate: code review
- Scope: uncommitted workspace diff for Slice 2
- Allowed files: `dayu/host/tool_runtime.py`, `tests/host/test_toolruntime_accept_barrier.py`, `tests/host/test_toolruntime_executor.py`, `tests/host/test_toolruntime_truncation_fetch_more.py`
- Plan: `docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`
- Handoff: `docs/reviews/wu-tool-02-slice2-implementation-handoff-20260602.md`
- Implementation report: `docs/reviews/wu-tool-02-slice2-implementation-report-20260602.md`

## Review Method

1. 逐行审读 `dayu/host/tool_runtime.py` 的 workspace diff，覆盖子结构定义、组合根 `__post_init__`、producer、consumer、validation helper、logging、EventLog payload、accepted evidence envelope、accepted ack、reject helper。
2. 逐行审读三个测试文件的 workspace diff，覆盖 candidate 构造 helper、assertion 读取路径、negative validation tests。
3. 对照 plan 的 Hard Boundaries、Fact Kind 字段归属与校验规则、Producer/Consumer 迁移路径、Non-goals 逐项验证。
4. 辅助验证：`rg` 检查旧顶层字段残留、`pyright` 类型检查、focused tests 通过状态。

## Verification

```bash
source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py
# 53 passed in 0.34s

source .venv/bin/activate && pyright dayu/host/tool_runtime.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py
# 0 errors, 0 warnings, 0 informations
```

## Findings

### 01-unfixed-medium-validation-ALLOW-duplicate-governance-过度严格

**位置**: `dayu/host/tool_runtime.py:4034-4037` (`_validate_tool_accept_duplicate_governance`)

**问题**: `_validate_tool_accept_duplicate_governance` 对 `duplicate_scope` 和 `duplicate_decision_message` 做无条件非空校验（line 4034-4037）。这意味着即使是 `duplicate_decision=ALLOW` 且 `duplicate_key=None` 的 "无实际 duplicate governance" 场景，也必须提供 `scope` 和 `message`。

对照旧代码 `_validate_duplicate_fields`，旧实现通过 `if candidate.duplicate_decision is None: return` 提前退出，对无 duplicate governance 的 candidate 不做后续校验。新代码通过 `_tool_accept_duplicate_governance_from_decision` 对所有 candidate 都构造 `ToolAcceptDuplicateGovernance`（ALLOW 时 `duplicate_key=None`），导致 validation 覆盖面比旧代码更宽。

**实际影响**: 当前 producer 和 tests 总是为 ALLOW decision 提供 scope 和 message，因此该过度严格校验不会阻塞当前运行。但若未来 producer 或测试 helper 为 plain candidate 构造 `ToolAcceptDuplicateGovernance(duplicate_key=None, duplicate_decision=ALLOW, duplicate_scope=None, ...)` 会意外触发 ValueError。

**建议**: 在 `_validate_tool_accept_duplicate_governance` 中，对 `duplicate_scope is None` 和 `duplicate_decision_message is None` 的检查应排除 `ALLOW` decision，或改为仅在 `duplicate_key is not None` 时要求 scope/message。这是与旧 validation 的语义对齐，不是新增校验。

**严重程度**: medium — 当前行为正确，但 validation 边界不一致，后续维护风险。

### 02-unfixed-trivial-缩进风格不一致

**位置**: `dayu/host/tool_runtime.py:3518-3522`

**问题**: `_tool_result_payload` 中 `tool_call_governed_event_ref` 的条件表达式：
```python
        "tool_call_governed_event_ref": (
            _event_ref_json(_event_ref_from_row(governed))
            if governed is not None
                else None
        ),
```
`else None` 相对 `if` 多了一级缩进（column 20 vs column 16），与同文件其它条件表达式风格不一致。

**实际影响**: 无功能影响，Python 语法正确。

**严重程度**: trivial — 纯风格。

## Checklist Verification

| 检查项 | 结果 | 说明 |
|---|---|---|
| `ToolFactAcceptCandidate` 已组合根迁移 | PASS | 顶层字段收敛为 `identity`、`call`、`tool_fact_kind`、`result`、`governance`、`idempotency`、`diagnostics` |
| 无旧顶层字段 facade/re-export/property | PASS | `rg` 在 production 和 allowed tests 中无残留旧字段访问（awaiting candidate 的 `tool_call_id` / `semantic_input_digest` 属于 `ToolAwaitingAcceptCandidate`，不在 scope 内） |
| producer 迁移 | PASS | `_tool_fact_accept_candidate()` 和 `_tool_fact_reuse_accept_candidate()` 均构造 typed 子结构 |
| accept barrier consumer 迁移 | PASS | logging、idempotency scope、accept context、payload descriptor check、event plan、EventLog payload、accepted evidence envelope、accepted ack、reject helper 均改读组合结构 |
| EventLog payload key/shape 不变 | PASS | `TOOL_CALL_REQUESTED`、`TOOL_CALL_GOVERNED`、`TOOL_RESULT_ACCEPTED` payload 的 JSON key 和 value 类型未变 |
| accepted evidence envelope 不变 | PASS | `_accepted_evidence_envelope` 的 `payload_ref` / `payload_digest` 选择逻辑、`outcome_digest`、`truncation_applied` 语义不变 |
| accepted ack 不变 | PASS | `_ack_result_digest` reuse 回退 `semantic_input_digest` 语义不变；`reuse_prior_event_refs` 来自 duplicate governance |
| duplicate governance attempt-local 语义不变 | PASS | `duplicate_scope` 仍写入 governed payload，attempt scope 未变 |
| reuse 语义不变 | PASS | reuse candidate `result=None`，只写 requested + governed，ack `result_digest` 回退 semantic input digest |
| payload durability 不变 | PASS | `_candidate_payload_descriptor_exists` 正确处理 `result=None`（reuse）和 `result.payload_ref` |
| wait/awaiting 不变 | PASS | `_tool_awaiting_accept_candidate()` 和 `ToolAwaitingAcceptCandidate` 未修改 |
| memory/compaction/tool trace production consumer 不变 | PASS | implementation report 确认且 diff 不涉及这些文件 |
| 无 `Any`/`object`/无类型签名 | PASS | pyright 0 errors |
| validation: ordinary result | PASS | COMPLETED 要求 `result` + `payload_digest` + allow policy；FAILED/CANCELLED 要求 `result` + allow policy + 无 reuse prior refs |
| validation: reuse | PASS | 要求 `result=None` + `duplicate_decision=REUSE` + `policy_decision=REUSE` + prior refs 非空 |
| validation: plain governed error | PASS | 要求 `result` + 非 ALLOW/REUSE policy + 无 reuse prior refs |
| validation: duplicate governed error | PASS | HINT/REQUIRE_JUSTIFICATION/HARD_STOP 要求 prior refs 非空 + policy kind/value 匹配；DURABLE_MISSING 要求无 prior refs |
| validation: unsupported LOST | PASS | `__post_init__` else 分支 `raise ValueError("unsupported tool_fact_kind")` |
| tests 迁移为组合 helper | PASS | `_completed_candidate`、`_reuse_candidate`、`_fact_kind_candidate` 均使用 `_candidate_identity`、`_candidate_call`、`_allow_governance`、`_candidate_idempotency` 等 helper |
| 无兼容分支保旧行为 | PASS | 旧字段不在 production 或 allowed tests 中访问 |
| 无额外 payload/extra payload | PASS | 所有显式字段均在 typed 子结构中 |

## Implementation Report 可信度

Implementation report 声明的变更范围、验证结果、semantic confirmation 与 diff 一致。53 passed 和 0 pyright errors 经独立复现确认。Residual risks 如实列出（未运行全仓测试、未迁移 duplicate/diagnostics 测试文件）。

## Conclusion

**Code review pass**，附一个 medium finding（`_validate_tool_accept_duplicate_governance` 对 ALLOW decision 的 scope/message 过度严格）和一个 trivial finding（缩进风格）。两个 finding 均不阻塞当前 Slice 2 行为，可在后续 slice 或 fix gate 中处理。
