# WU-OBS-SIGNALS-01 / OBS-SIG-01 Fix Re-Review — AgentDS

## Scope

- Work unit: `WU-OBS-SIGNALS-01`
- Slice: `OBS-SIG-01` / P01 context pressure signal
- Gate: re-review (post-fix)
- Predecessor artifacts:
  - Implementation: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-01-implementation-codex.md`
  - MiMo code review: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-01-code-review-mimo.md`
  - DS code review: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-01-code-review-ds.md`
  - Controller adjudication: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-01-code-review-controller-adjudication.md`
  - Fix: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-01-fix-codex.md`
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Control doc: `docs/host/issues-implementation-control.md`

## Accepted Findings Recheck

### MIMO-F1: Missing `transaction` parameter documentation

- **Finding**: `EngineEventIngestor._duplicate_terminal_result` 与 `_ingest_validated` 的 docstring 缺少 `:param transaction: 当前 Host transaction。`
- **Adjudication**: accepted; restore docstring line.
- **Current state**: ✅ **FIXED**
  - `_duplicate_terminal_result` (`engine_ingest.py:809`): `:param transaction: 当前 Host transaction。` 已存在
  - `_ingest_validated` (`engine_ingest.py:913`): `:param transaction: 当前 Host transaction。` 已存在
- **Evidence**: 直接读取文件确认两处 docstring 均已包含 transaction 参数说明；git diff 中这两个函数没有变更（net zero — 实现阶段移除后 fix 阶段恢复）

### DS-F1: Stale `transaction` parameter documentation

- **Finding**: `EngineEventIngestor._usage_observation_diagnostic` 函数签名已移除 `transaction` 参数，但 docstring 仍保留 `:param transaction: 当前 Host transaction。`
- **Adjudication**: accepted; remove stale line.
- **Current state**: ✅ **FIXED**
  - 函数签名 (`engine_ingest.py:2711-2716`): `self, *, context, data, estimate` — 无 `transaction`
  - docstring (`engine_ingest.py:2718-2723`): 仅列出 `:param context:`、`:param data:`、`:param estimate:`、`:returns:` — 无 stale `:param transaction:`
- **Evidence**: 直接读取文件确认 stale 行已删除，docstring 与函数签名完全一致

## Scope Creep Recheck

| 检查项 | 结论 | 证据 |
|---|---|---|
| Fix 是否只改动 docstring，未改变行为逻辑 | ✅ PASS | 三处修改均为纯文档：两处恢复缺失的参数文档，一处删除残留参数文档。无函数签名、逻辑路径、常量或类型变更归因于 fix |
| Fix 是否未扩大 scope | ✅ PASS | fix 仅触及 `engine_ingest.py` 的三处 docstring；未修改 `tool_trace.py`、测试文件或 control doc |
| 整体 OBS-SIG-01 diff 是否仍满足 P01 范围 | ✅ PASS | diff 仅涉及 `context_pressure` 信号字段；`tool_timing` / `failure_metadata` / `partial_tool_call_signal` 在 `_TraceSummarySignals` 中仅为 placeholder copy，无 P02/P03/P04 producer 实现 |
| 是否提前实现 P02/P03/P04 | ✅ PASS | 无 tool_timing、failure_metadata producer 逻辑或 partial_tool_call_signal 新字段 |
| 是否修改 Engine public contract | ✅ PASS | `dayu/engine/` 无修改；`decide_context_budget` 仅在 Host 层 (`engine_ingest.py`) 调用 |
| 是否修改 SQLite schema 或 ToolRuntime | ✅ PASS | 无 schema migration、无 ToolRuntime 执行语义或状态机变更 |
| Architecture 分层是否保持 | ✅ PASS | Engine 不理解 Host budget；Tool Trace 仍是 projection 不是 durable truth；compaction 压力派生仅读取现有 payload 字段 |

## New Findings

无。fix 正确、完整地解决了 controller 接受的全部两项 finding（MIMO-F1、DS-F1），未引入新问题。

## Residual Risk

- **P02/P03/P04 信号字段**：`tool_timing`、`failure_metadata`、`partial_tool_call_signal` 仍由后续 slice 填充。当前 OBS-SIG-01 未引入相关 producer 代码，scope 隔离清晰。
- **compaction failed 缺少 request fact 时的降级路径**：`_context_compaction_request_payload` 找不到 request event 时 `policy_ref`、`estimator_digest`、`trigger_source`、`budget_reason` 全部返回 `None`。此为 non-failing projection signal 约束下的预期降级行为，无专门测试覆盖。已在 DS 初版 review 中标记，不属于 OBS-SIG-01 blocking。
- **`_required_bool` 缺失字段时的异常路径**：当前测试 fixture 均提供合法 bool，未测试字段缺失时 `HostDurableError` 的抛出路径。生产 payload builder (`context_events.py` validator) 已保证必填字段存在，风险低。已在 DS 初版 review 中标记。

以上三项 residual risk 均为 approved plan 内的已知项或已在初版 review 中记录的非 blocking 项；fix 未改变这些风险的状态或严重程度。

## Validation

独立本地重跑验证：

- **pytest**: `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_context_compact_events.py`
  - Result: **116 passed in 0.89s**
- **pyright**: `source .venv/bin/activate && pyright`
  - Result: **0 errors, 0 warnings, 0 informations**

两组验证均与 fix-codex 报告一致，验证结果可信。

## Verdict

**PASS**

Fix 完整、准确地解决了 controller 接受的 MIMO-F1 与 DS-F1 两项 docstring 一致性 finding，未引入新问题，未改变行为逻辑，未扩大 scope。测试与类型检查均通过。整体 OBS-SIG-01 diff 仍严格限定在 P01 范围。无 blocking open questions。

---

等待 controller 下一步指令。
