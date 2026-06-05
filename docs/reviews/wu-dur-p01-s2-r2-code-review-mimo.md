# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-dur-obs-cm-closeout`
- Base: `main`
- Output file: `docs/reviews/wu-dur-p01-s2-r2-code-review-mimo.md`
- Included scope: `dayu/host/engine_ingest.py`、`tests/host/test_engine_ingest_mapping.py`、`docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`、`docs/host/issues-implementation-control.md`，以及 plan artifact `docs/host/wu-dur-p01-s2-r2-runner-call-event-link-plan.md` 与 implementation report `docs/reviews/wu-dur-p01-s2-r2-implementation-codex.md`
- Excluded scope: Engine / Fins / Service / UI 层；Tool Trace durable projection 行为未变更（只更新 README 描述）
- Parallel review coverage: 无

## Findings

### 001-未修复-低-现有 mismatch link 重放时 rejected reason 语义偏差

- **入口/函数**: `_append_iteration_started_events`（engine_ingest.py:2404-2442）
- **文件(行号)**: engine_ingest.py:2411-2434
- **输入场景**: 首次 `ITERATION_STARTED` 导致 mismatch link + `ENGINE_EVENT_REJECTED(reason="runner_call_manifest_mismatch")`；随后相同 Engine observation 重放
- **实际分支**: `existing_link is not None` → `_runner_call_iteration_link_matches` 返回 True（engine 字段一致）→ `_resolution_from_link_event` 返回 status=mismatch → 进入 `resolution.status != COMPLETE` 分支 → `_append_rejected_diagnostic(reason=_REASON_RUNNER_CALL_MANIFEST_MISMATCH)`
- **预期行为**: plan Section 3 定义 `runner_call_iteration_link_conflict` 用于"既有 link 的 validation_status 不是 complete 时，即使 Engine observation 字段与 link 一致，重放也继续返回 rejected"。重放场景应返回 `runner_call_iteration_link_conflict`，而非 `runner_call_manifest_mismatch`。后者应保留给"首次发现 mismatch"场景
- **实际行为**: 重放返回 `ENGINE_EVENT_REJECTED(reason="runner_call_manifest_mismatch")`，与首次 mismatch 使用相同 reason
- **直接证据**: engine_ingest.py:2424-2434 检查 `resolution.status != COMPLETE` 后直接使用 `_REASON_RUNNER_CALL_MANIFEST_MISMATCH`；无分支区分"首次 mismatch"与"重放已有 mismatch link"
- **影响**: 不影响 fail-closed 行为（worker stream 仍停止）；不影响幂等性（link event 不会重复写入）；仅影响 rejected diagnostic reason 的语义精确性，可能导致 audit / Tool Trace 消费者无法区分"新发现的 mismatch"与"重放已知 mismatch"
- **建议改法和验证点**: 在 `existing_link is not None` 且 `resolution.status != COMPLETE` 分支中，改用 `_REASON_RUNNER_CALL_ITERATION_LINK_CONFLICT`；更新对应测试断言 `test_iteration_started_mismatch_fails_closed_after_link` 中 replay 的 reason 断言
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无

## Residual Risk

- Tool Trace 当前仍只强制投影 `RUNNER_CALL_INPUT_ASSEMBLED` signal；`RUNNER_CALL_INPUT_ITERATION_LINKED` 是 durable truth 但最小实现不要求 Tool Trace 投影 link event。design / README 已明确 prepared `complete` 与 Engine linked `complete` 的语义区别。
- `_find_unlinked_prepared_runner_call_manifest_events` 使用 Python 端过滤而非 SQL anti-join；当前 scope（run_id + attempt_id + execution_id）下单 Attempt ordinary manifest 预期极少，bounded scan 可接受。若未来 manifest 数量增长，可升级为 SQLite JSON1 anti-join。
- 本次未修改 Engine contract，Engine 仍只提供 `ITERATION_STARTED` observation；Host manifest id 保持 Host-only。

## 结论

**accept**

实现完整覆盖 plan 所有关键场景：`RUNNER_CALL_INPUT_ITERATION_LINKED` append-only 且不越层；missing / ambiguous / mismatch / conflict 均 fail closed 且 `stop_worker_stream=True`；link + preview 与 link + rejected 同 transaction；旧 `payload_iteration_id is None and iteration_index == 0` fallback 已彻底删除；continuation `iteration_index == 0` 只在 accepted prior observation 后写 limited-signal manifest；mismatch link / rejected 不 seed continuation prior observation；Tool Trace 最小实现未误改 projection；tests 覆盖 plan 全部场景且无 raw SQL / 脆弱 fixture；README / design / control doc 已同步且不过度承诺。

唯一 finding（001）为低严重度语义偏差，不影响 fail-closed 正确性、幂等性或数据一致性，不构成阻断。
