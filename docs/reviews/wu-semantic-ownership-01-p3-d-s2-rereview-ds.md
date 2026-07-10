# WU-SEMANTIC-OWNERSHIP-01 / P3-D / S2 Re-Review

## Scope

- Mode: re-review gate (S2 fix verification)
- Agent: AgentDS
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-d-s2-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-d-s2-code-review-controller-adjudication.md`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-d-s2-rereview-ds.md`
- Accepted findings under review: `P3-D-S2-CR-F01`, `P3-D-S2-CR-F02`
- Rejected finding excluded by instruction: `P3-D-S2-CR-F03`
- Parallel review coverage: 无（单人走读所有 fix 变更文件）

## Re-review Evidence

### P3-D-S2-CR-F01 — 已修复

**要求**: fatal PROVIDER_PROTOCOL_ERROR activity 不再投影为 `HostActivityKind.PROVIDER_DIAGNOSTIC`；非致命 PROVIDER_DIAGNOSTIC 保持 `PROVIDER_DIAGNOSTIC` kind 并使用 `INFO` status；Service entrypoint 保留区分。

**直接证据**:

1. **新增 `HostActivityKind.PROVIDER_PROTOCOL_ERROR`**: `dayu/host/api.py:2537` — `PROVIDER_PROTOCOL_ERROR = "provider_protocol_error"`，独立于 `PROVIDER_DIAGNOSTIC = "provider_diagnostic"`（line 2536）。

2. **Read API 投影分离**: `dayu/host/read_api.py`:
   - `_provider_protocol_error_activity` (line 1434): `kind=HostActivityKind.PROVIDER_PROTOCOL_ERROR`，`status=HostActivityStatus.FAILED`
   - `_provider_diagnostic_activity` (line 1462): `kind=HostActivityKind.PROVIDER_DIAGNOSTIC`，`status=HostActivityStatus.INFO`
   - `_activity_from_row` dispatch (line 1096-1099): 两个 event type 分别路由到独立投影函数，`PROVIDER_PROTOCOL_ERROR` 先于 `PROVIDER_DIAGNOSTIC` 匹配

3. **Service entrypoint 保留区分**: `dayu/service/entrypoint_runtime.py`:
   - `EntrypointActivityKind.PROVIDER_PROTOCOL_ERROR` (line 104) — 新增枚举成员
   - `_entrypoint_activity_kind_from_host` (line 1291-1292): 新增 `PROVIDER_PROTOCOL_ERROR` 映射
   - 已有 `PROVIDER_DIAGNOSTIC` 映射不变 (line 1289-1290)

4. **测试证实**:
   - `test_provider_protocol_error_activity_is_bounded` (`tests/host/test_host_activity_event_projection.py:603-604`): 断言 `kind is HostActivityKind.PROVIDER_PROTOCOL_ERROR` 且 `status is HostActivityStatus.FAILED`
   - `test_provider_diagnostic_activity_is_nonfatal` (`tests/host/test_host_activity_event_projection.py:634-635`): 断言 `kind is HostActivityKind.PROVIDER_DIAGNOSTIC` 且 `status is HostActivityStatus.INFO`
   - `test_submit_entrypoint_turn_preserves_provider_protocol_error_activity` (`tests/service/test_entrypoint_runtime.py:863-864`): 断言 `kind is EntrypointActivityKind.PROVIDER_PROTOCOL_ERROR` 且 `status is EntrypointActivityStatus.FAILED`

5. **测试通过**: 全部 126 个受影响测试通过 (`tests/engine/test_agent_phase2.py`, `tests/host/test_host_activity_event_projection.py`, `tests/service/test_entrypoint_runtime.py`)。

6. **pyright**: 0 errors, 0 warnings, 0 informations。

**结论**: F01 已修复。

---

### P3-D-S2-CR-F02 — 已修复

**要求**: context overflow `CONTEXT_LENGTH_EXCEEDED` 且 `context_overflow_detection=None` 有显式回归覆盖，且不产出 `PROVIDER_DIAGNOSTIC`。

**直接证据**:

1. **新回归测试**: `tests/engine/test_agent_phase2.py:871` — `test_context_overflow_without_detection_emits_only_compaction_request`:
   - 输入: `RunnerHTTPErrorData(error_code=CONTEXT_LENGTH_EXCEEDED, context_overflow_detection=None)`
   - 断言事件流为 `[ITERATION_STARTED, CONTEXT_COMPACTION_REQUESTED, ITERATION_COMPLETED, RUN_FAILED]`（line 901-906）
   - 断言 `EngineEventType.PROVIDER_DIAGNOSTIC not in {event.type for event in events}`（line 907-909）
   - 额外断言 `compact_event.data.provider_request_id` 正确传递（line 911-912）

2. **生产代码不变**: `dayu/engine/agent.py:1617-1622` 的 `detection is None` 短路逻辑未被修改，测试验证了已有正确行为。

3. **测试通过**: 该回归测试单独通过。

**结论**: F02 已修复。

---

## New Issues Scan

### Semantic Ownership Drift

- **无新增语义漂移**: Host Read API（`read_api.py`）拥有 activity kind 投影，Agent（`agent.py`）拥有 Engine 事件语义，Runner adapter 拥有事实产生。三层各在其 owner boundary 内变更，下游不越界修复。
- `_entrypoint_activity_kind_from_host` 采用直接 `is` 比较映射（`entrypoint_runtime.py:1269-1293`），无 fallback、无 loose parsing，无下游重复语义。

### Public Contract Mismatch

- `HostActivityKind.PROVIDER_PROTOCOL_ERROR` 已在 `dayu/host/__init__.py:41` 的 `__all__` 中导出（`"HostActivityKind"`），公共契约完整。

### Reverse Dependency

- 无新增反向依赖。所有变更遵循 `UI → Service → Host → Engine` 分层。`entrypoint_runtime.py` 仅从 `dayu.host.api` 导入公共类型。

### LLM-Facing Leakage

- fix artifact 的 propagation audit（`docs/reviews/wu-semantic-ownership-01-p3-d-s2-fix-codex.md:78-80`）确认 `PROVIDER_DIAGNOSTIC` 和 `PROVIDER_PROTOCOL_ERROR` 不进入 Outbox/memory/final answer/evidence/compact/LLM-facing prompts。
- `docs/host/design.md:1531` 新增行明确写明 `PROVIDER_DIAGNOSTIC` "不得进入 outbox terminal item、Conversation Memory、final answer、accepted evidence material、compact material 或 LLM-facing prompt messages"。
- 未发现新增 LLM-facing 泄漏。

### Test Weakening

- 无测试断言被削弱。原有 `test_provider_protocol_error_activity_is_bounded` 从 `kind=HostActivityKind.PROVIDER_DIAGNOSTIC` 更新为 `kind=HostActivityKind.PROVIDER_PROTOCOL_ERROR`，这是语义修复而非削弱。
- 新增 `_provider_diagnostic_activity` 函数有独立的 `test_provider_diagnostic_activity_is_nonfatal` 覆盖，原有 `PROVIDER_DIAGNOSTIC` 行为未被测试空白化。

### Branch Ordering

- `_activity_from_row` dispatch（`read_api.py:1096-1099`）: `PROVIDER_PROTOCOL_ERROR` 先于 `PROVIDER_DIAGNOSTIC` 匹配，无重叠竞争。

---

## Docs / README Validation

- `dayu/host/README.md`: 新增 `PROVIDER_DIAGNOSTIC` 和 `PROVIDER_PROTOCOL_ERROR` 在 Read API 中的行为描述，符合 README 职责范围（Host 公共 API 变更）。
- `docs/host/design.md`: 新增 `PROVIDER_DIAGNOSTIC` 在 EventLog 事件表、canonical event contract matrix 和 Engine-to-Host 投影映射表中的条目。与 `dayu/host/` 代码变更一致。
- 无过度更新：`dayu/engine/README.md`、`tests/README.md`、根 `README.md` 和 `dayu/README.md` 均被检查但未修改，符合 fix artifact 中的判断（Agent 行为未变，只加回归测试）。

---

## Open Questions

- 无。

## Residual Risk

1. **Service 层缺少非致命 `PROVIDER_DIAGNOSTIC` activity 的端到端回归测试**: `test_submit_entrypoint_turn_preserves_provider_protocol_error_activity` 覆盖了致命路径，但没有对应的 `test_submit_entrypoint_turn_preserves_provider_diagnostic_activity`。`_entrypoint_activity_kind_from_host` 中的 `PROVIDER_DIAGNOSTIC` 映射（line 1289-1290）依赖已有的一般 activity 投影测试（`test_submit_entrypoint_turn_emits_host_public_activity`）间接覆盖。这是已有覆盖缺口，非本次 fix 引入。
2. **S3 typed Engine error-code contract** 仍不在 S2 scope。

---

S2 re-review complete.
