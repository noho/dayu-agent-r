# WU-SEMANTIC-OWNERSHIP-01 P3-E S2 Code Review — AgentDS

## Scope

- Mode: current changes (uncommitted workspace diff vs HEAD)
- Branch: `phaseflow/host-issues-control`
- Base: `HEAD` (uncommitted staged changes)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-e-s2-code-review-ds.md`
- Reviewed artifacts:
  - Plan: `docs/host/wu-semantic-ownership-01-p3-e-tool-result-wait-fins-contracts-plan.md` S2 section
  - Implementation: `docs/reviews/wu-semantic-ownership-01-p3-e-s2-implementation-codex.md`
  - Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-e-s2-controller-validation.md`
- Included files:
  - `dayu/service/wait_callback_endpoint.py`
  - `dayu/host/accepted_result_projection.py`
  - `tests/service/test_wait_callback_endpoint.py`
  - `tests/host/test_accepted_result_projection.py`
  - `tests/host/test_resolve_wait_command.py` (stale assertion alignment only)
  - `tests/README.md`
  - `docs/host/issues-implementation-control.md` (gate bookkeeping only)
- Excluded:
  - `docs/cli_ci*`, `docs/reviews/code-review-20260710-*` (unrelated untracked)
  - Already-committed S1 (`7c8bc0a8`) — not regressed by S2 diff
  - S3 files (Fins direct, CLI fins — not yet implemented)
- Consumer files read for boundary check:
  - `dayu/host/read_api.py`
  - `dayu/host/run_input.py`
  - `dayu/host/evidence.py`
  - `dayu/host/memory.py`
  - `dayu/host/compact_material.py`
- Parallel review coverage: 无（单 reviewer 逐路走读）

## Findings

未发现实质性问题。

以下逐项记录每个 review focus 的验证路径与直接证据。每项的结论为通过（无 finding），而非跳过。

---

## 1. Wait callback endpoint: bare-string `provider_status_ref` 拒绝

**验证路径**:

- 生产入口: `_provider_status_ref_from_json(raw: JsonValue)`（`dayu/service/wait_callback_endpoint.py:542-558`）
- 旧 bare-string 分支（`isinstance(raw, str)`）已删除。函数体仅有一条路径：`raw is None` → `None`；否则通过 `_require_json_object(raw, "provider_status_ref")` 强制要求 object shape（行 553）。
- object shape 校验: 必须含 `adapter_key`（通过 `WaitAdapterKey(...)` 构造，行 555）、`status_ref`（行 556）、可选 `status_digest`（行 557）。
- 无任何代码构造 `WaitAdapterKey("callback")` 作为 fallback 或默认值。

**直接证据**:
- `dayu/service/wait_callback_endpoint.py:542-558`: 函数签名、分支逻辑、object 校验 ✅
- 全量 source scan: `rg -n 'WaitAdapterKey\("callback"\)' dayu/service/` 无命中 ✅

**测试**:
- `tests/service/test_wait_callback_endpoint.py:304-317`: `test_string_provider_status_ref_returns_malformed_payload_without_adapter_call`
  - 设置 `outcome["provider_status_ref"] = "jobs/provider-1/status"`（裸字符串）
  - 断言 `response.status_code == 400`（行 315）
  - 断言 `status == "malformed_payload"`（行 316）
  - 断言 `adapter.envelopes == []`（行 317），确认 adapter 未被调用 ✅
- `tests/service/test_wait_callback_endpoint.py:621-638`: `_lost_body()` fixture 使用 typed object `provider_status_ref`（`adapter_key`、`status_ref`、`status_digest`），不再使用裸字符串 ✅

**结论**: 通过。裸字符串 `provider_status_ref` 在 Service transport 入口处被拒绝；无 fake `WaitAdapterKey("callback")` resolver 残留。

---

## 2. Accepted result projection: raw outcome status reconstruction 移除

**验证路径**:

- 删除项确认:
  - `_status_from_raw_outcome(...)`: 全量 source scan 零命中 ✅
  - `_FIELD_RESULT`、`_FIELD_KIND`、`_FIELD_OK` 常量: 已从 `dayu/host/accepted_result_projection.py` 中删除 ✅
- 新 `_accepted_status(payload, diagnostics)`（行 391-418）:
  - 先检查 `_DIAGNOSTIC_RESULT_PAYLOAD_UNAVAILABLE` 或 `_DIAGNOSTIC_EVENT_PAYLOAD_UNAVAILABLE` 是否在 diagnostics 中 → 映射 `LOST`（行 402-406）✅
  - 再读取 `resolution_kind`（优先，行 407-410）✅
  - 再读取 `tool_fact_kind`（次优先，行 411-414）✅
  - 两者均不可用 → 映射 `UNKNOWN` + `accepted_status_unavailable`（行 415-418）✅
  - 签名变更为返回 `tuple[AcceptedToolResultStatus, tuple[str, ...]]`，调用点 `project_accepted_tool_result` 行 206 已对齐 ✅
- `_payload_status_text(payload, field_name)`（行 441-461）:
  - 字段缺失 → `payload.get(...)` 返回 `None` → `not isinstance(None, str)` → `None` ✅
  - 非字符串（`int`/`bool`/`list` 等）→ `not isinstance(value, str)` → `None` ✅
  - 空白字符串 → `value.strip() == ""` → `None` ✅
  - 所有边界条件均正确 fail-closed；不从 raw outcome 恢复 ✅
- `_status_from_text(value)`（行 421-438）:
  - 已知值（`completed`/`failed`/`cancelled`/`governed_error`/`lost`）→ 对应枚举 ✅
  - 未知值 → `UNKNOWN` ✅
- Diagnostic 常量模块化:
  - `_DIAGNOSTIC_ACCEPTED_STATUS_UNAVAILABLE = "accepted_status_unavailable"`（行 54）
  - `_DIAGNOSTIC_RESULT_PAYLOAD_UNAVAILABLE = "result_payload_unavailable"`（行 55）
  - `_DIAGNOSTIC_EVENT_PAYLOAD_UNAVAILABLE = "event_payload_unavailable"`（行 56）
  - 替换了原来的 magic string，源码中不再出现裸字符串 `"result_payload_unavailable"` ✅

**直接证据**:
- `dayu/host/accepted_result_projection.py:391-418`: `_accepted_status` 完整逻辑 ✅
- `dayu/host/accepted_result_projection.py:441-461`: `_payload_status_text` 所有边界处理 ✅
- Source scan: `_status_from_raw_outcome`、`_FIELD_RESULT`、`_FIELD_KIND`、`_FIELD_OK` production 零命中 ✅

**测试**:
- `tests/host/test_accepted_result_projection.py:351-360`: blank `tool_fact_kind` → `UNKNOWN` + `accepted_status_unavailable` ✅
- `tests/host/test_accepted_result_projection.py:447-455`: unknown `tool_fact_kind="unexpected-status"` → `UNKNOWN` + `accepted_status_unavailable` ✅
- `tests/host/test_accepted_result_projection.py:772-779`: `tool_fact_kind=None` + raw `result.ok=False` → `UNKNOWN` + `result_details_text == "reason=not found"`（raw outcome details 抽取保留）✅
- `tests/host/test_accepted_result_projection.py:691-697`: missing result payload → `LOST` + `result_payload_unavailable` ✅
- `tests/host/test_accepted_result_projection.py:505-530`: `resolution_kind="cancelled"` 优先于 `tool_fact_kind="completed"` → `CANCELLED` ✅

**结论**: 通过。Accepted status 不再从 raw outcome `kind` 或 `result.ok` 重建；typed status 缺失/空白/未知 → `UNKNOWN`+diagnostic；unavailable payload → `LOST`。

---

## 3. Consumer boundary: raw outcome status reconstruction 未发生

逐 consumer 走读：

| Consumer | 文件(行号) | 消费方式 | raw outcome 用途 | status 真源 |
|---|---|---|---|---|
| read_api | `dayu/host/read_api.py:1236-1245` | `project_accepted_tool_result(...)` → `projection.status` | 不读取 | `projection.status`（唯一真源）|
| run_input | `dayu/host/run_input.py:3479` | `project_accepted_tool_result(...)` | 仅 result text | `projection.status.value`（行 3527）|
| evidence | `dayu/host/evidence.py:435` | `accepted_tool_raw_outcome_text_from_payload(...)` | LLM-facing result text | 不提供 status |
| memory | — | 消费 accepted evidence material | 不直接读取 | 不直接消费 status |
| compact_material | `dayu/host/compact_material.py:2557` | `project_accepted_tool_result(...)` → `projection.llm_material` | fail-closed on missing（行 2563） | 不读取 raw outcome status |

**直接证据**:

- `dayu/host/read_api.py:1285-1297`: `_accepted_result_activity_state(status)` 只接受 `AcceptedToolResultStatus` 枚举，不读取任何 raw outcome 字段。`UNKNOWN`/`LOST`/`FAILED`/`GOVERNED_ERROR` 均映射 `FAILED/ERROR`（fail-closed）✅
- `dayu/host/evidence.py:435-445`: raw outcome helper 只服务于 LLM-facing evidence material，不推断 accepted status ✅
- 全量 grep: `raw_tool_outcome` 在所有 consumer 中仅用于 result text/details/evidence material 或 fail-closed 检查，无任何 pattern `raw_tool_outcome.*kind.*status` 或 `result.*ok.*status` 用于 status 重建 ✅

**结论**: 通过。所有 consumer 通过统一 `project_accepted_tool_result(...)` 消费 typed status；无任何 consumer 从 raw outcome 重建 accepted status。

---

## 4. Tests coverage assessment

| 测试关注点 | 测试函数 | 文件(行号) | 覆盖状态 |
|---|---|---|---|
| 裸字符串 provider ref 拒绝 | `test_string_provider_status_ref_returns_malformed_payload_without_adapter_call` | `test_wait_callback_endpoint.py:304` | ✅ |
| typed object provider ref 接受 | `_lost_body()` fixture + 全部 lost callback 测试 | `test_wait_callback_endpoint.py:621` | ✅ |
| blank typed status → UNKNOWN | `test_accepted_projection_handles_null_tool_name_and_blank_status` | `test_accepted_result_projection.py:300` | ✅ |
| unknown typed status → UNKNOWN | `test_accepted_projection_handles_governed_error_and_unexpected_status` | `test_accepted_result_projection.py:416` | ✅ |
| raw details 抽取 while status UNKNOWN | `test_projection_maps_raw_result_ok_false_and_extracts_details` | `test_accepted_result_projection.py:748` | ✅ |
| missing payload → LOST | `test_projection_handles_missing_result_descriptor_and_missing_payload` | `test_accepted_result_projection.py:640` | ✅ |
| resolution_kind 优先于 tool_fact_kind | `test_projection_wait_resolution_status_takes_priority` | `test_accepted_result_projection.py:505` | ✅ |
| UNKNOWN consumer coverage | read model / run input / memory / compact material 全量通过 | 311 passed in 1.73s (controller validation) | ✅ |

**结论**: 通过。关键行为均有测试覆盖；negative test（裸字符串 provider ref）存在且正确；raw outcome details 抽取与 UNKNOWN status 解耦验证存在。

---

## 5. README 变更

**直接证据**:
- `tests/README.md:145`: 变更仅追加"裸字符串 `provider_status_ref` 拒绝"到 Service wait callback endpoint 测试覆盖摘要。该 README 职责为记录测试分层与已有测试覆盖范围（见 `tests/README.md` 内 `Agent更新约束【必须遵守】`）；本次追加不超出其声明边界 ✅
- `dayu/host/README.md`: no-op 决策有效——S2 收紧的是 projection status owner 的内部规则，未改变 Host public 边界描述 ✅

**结论**: 通过。

---

## Open Questions

无。

## Residual Risk

1. **`UNKNOWN` 在 Read API 中映射为 `FAILED/ERROR` severity**: 这是现有 consumer 策略（`_accepted_result_activity_state` 行 1297: 非 COMPLETED/CANCELLED 一律 FAILED/ERROR）。若产品层需要区分 UNKNOWN（无法判断）与 FAILED（明确失败），应作为后续 projection/display policy 变更处理，不能恢复 raw outcome fallback。S2 未改变此策略，风险属于 pre-existing。

2. **External callback 兼容性**: 若外部真实 callback 调用方仍发送旧 shape（bare-string `provider_status_ref`），现在会收到 `malformed_payload`（HTTP 400）。这是 S2 明确要求的 fail-closed 行为，非回归。生产部署时需确认所有 callback producer 已迁移到 object shape。

3. **S3 未实施**: P3-E S3（Fins direct unique RESULT protocol error、`FinsDirectStreamContractViolation` 删除、CLI fins 对齐）仍未开始。S2 独立可 ship。

## Conclusion

**PASS**

S2 实现正确完成其全部目标：

- **Wait callback endpoint**: bare-string `provider_status_ref` 在 Service transport 入口处被拒绝；无 fake `WaitAdapterKey("callback")` resolver 残留；object shape 校验覆盖 `adapter_key`、`status_ref`、`status_digest`。
- **Accepted result projection**: `_status_from_raw_outcome`、`_FIELD_RESULT`、`_FIELD_KIND`、`_FIELD_OK` 已删除；typed status 缺失/空白/未知 → `UNKNOWN` + `accepted_status_unavailable`；unavailable payload → `LOST` + `result_payload_unavailable` / `event_payload_unavailable`。
- **Consumer boundary**: read_api、run_input、evidence、memory、compact_material 均通过统一 `project_accepted_tool_result(...)` 消费 typed status；无任何 consumer 从 raw outcome 重建 status。
- **Tests**: negative provider ref test、blank/unknown typed status → UNKNOWN、missing payload → LOST、raw details extraction while status UNKNOWN 全覆盖；311 passed + pyright 零错误。
- **README**: `tests/README.md` 变更在声明职责范围内；其他 README no-op 决策有效。

所有变更均落在语义 owner boundary（Service callback mapper → transport 校验 owner；Host accepted-result projection → typed status projection owner）内；无语义漂移、无下游特例、无 raw outcome fallback 残留。
