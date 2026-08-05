# Code Review — PR 190 S4.2 accepted terminal payload DS-F01 fix 后独立 re-review

## Scope

- **Mode**: current changes (uncommitted, post-fix vs baseline)
- **Branch**: `codex/interactive-oracle`
- **Base**: `f7957b6343f4647ce0c6058a08e9ae84ab629f30`
- **Output file**: `docs/reviews/pr-190-f11-f12-s4-accepted-terminal-payload-ds-rereview-20260805.md`
- **Review date**: 2026-08-05
- **Reference artifacts**:
  - 首轮 DS review: `docs/reviews/pr-190-f11-f12-s4-accepted-terminal-payload-ds-review-20260805.md`
  - MiMo review: `docs/reviews/pr-190-f11-f12-s4-accepted-terminal-payload-mimo-review-20260805.md`
  - Controller adjudication: `docs/reviews/pr-190-f11-f12-s4-accepted-terminal-payload-review-adjudication-20260805.md`
  - DS-F01 fix: `docs/reviews/pr-190-f11-f12-s4-accepted-terminal-payload-ds-f01-fix-20260805.md`
- **不得引用**: MiMo rereview（controller 裁决仅允许 DS 独立 re-review）
- **Included scope**:
  - `dayu/host/context_event_payload.py` — durable payload owner（新增）
  - `dayu/host/dispatch.py` — proactive writer 路径
  - `dayu/host/engine_ingest.py` — reactive writer 路径
  - `dayu/host/run_input.py` — `DurableCompactArtifactProvider._load_compact_artifact_tx`（DS-F01 修复点）+ 6 处 consumer
  - `dayu/host/compact_material.py` — consumer
  - `dayu/host/compaction_terminal.py` — consumer
  - `dayu/host/projection.py` — consumer
  - `dayu/host/durable/tool_trace.py` — consumer
  - `dayu/host/proactive_compaction.py` — consumer
  - `tests/host/test_run_input_builder.py` — DS-F01 owner test（新增）
  - `tests/host/test_dispatch_scheduler.py` — proactive oversized owner test
  - `tests/host/test_engine_ingest_mapping.py` — reactive oversized owner test
- **Excluded scope**: `dayu/host/context_events.py`（零 diff）、oracle/scenario/registry（零 diff）、MiMo rereview artifact
- **Parallel review coverage**: 无（本 re-review 为主 reviewer 独立逐项验证）

## 验证方法

逐项验证 DS-F01 修复与测试、核对 DS-F02 至 DS-F08 的 controller rejected-with-reason 直接证据，并执行 adversarial correctness bug 搜索。不修改生产/测试代码，不 commit/push，不 real-provider。

## Findings

### 逐项状态

#### DS-F01 — 已修复，PASS ✅

- **验证点**: `DurableCompactArtifactProvider._load_compact_artifact_tx`
- **直接证据**: `run_input.py:1973` — `payload = resolve_context_compacted_payload(transaction, row)`
  - 原实现使用 `_payload_object(row)`（只 inline parse），现已改为复用统一 resolver
  - 与同文件其他 5 处已迁移 consumer 一致（line 4248、line 5491-5492、line 5571、line 5593-5596）
  - 无 fallback、默认值、inline 特例或兼容 shim

- **Owner test 验证** (`test_run_input_builder.py:539-606`):
  - 使用 2048-byte inline threshold 写入真实 descriptor-backed `CONTEXT_COMPACTED`
  - 断言 `payload_json == "{}"`（hot object 为空）
  - 断言 `payload_ref` / `payload_digest` 非 None
  - 断言 descriptor `payload_kind is ARTIFACT_REF`，`payload_size_bytes > inline_threshold_bytes`
  - 断言 `view.compaction_event_ref == compacted.event_id`
  - 断言 `view.compact_artifact_ref == "compact-artifact:test"`
  - 断言 `view.compact_artifact_digest` 与 `view.represented_evidence_refs` 正确

- **Digest corruption fail-closed 验证** (line 596-606):
  - 篡改 EventLog `payload_digest` 后再次调用同一 provider
  - 断言 `HostDurableError` 且消息匹配 `"payload integrity validation failed"`
  - 验证 resolver → `sqlite_payload_object` → `resolve_json_payload` → `_validate_descriptor_identity`（payload_resolution.py:104 `descriptor.payload_digest != expected_digest`）→ fail closed

- **Test helper 正确性**: `_append_descriptor_backed_current_run_compacted_event`（test_run_input_builder.py:4527-4613）使用 `store_context_compacted_payload()` 产生真实 descriptor-backed storage plan，并将三个字段（`event_payload`/`payload_ref`/`payload_digest`）原样写入 EventLog

- **测试结果**: `3 passed in 0.42s`（含 proactive + reactive + DS-F01 owner tests）

#### DS-F02 — Controller rejected-with-reason，证据确认 ✅

- **Controller 理由**: `run_write` 的 busy retry 每次都 rollback 整个 SQLite transaction 后重跑，无 savepoint/部分提交；外层重跑时 terminal permit 先读 canonical terminal；随机 event_id 是既有 proactive identity 选择，非本 blocker 引入
- **直接证据**:
  - `transaction.py:314` — `BEGIN IMMEDIATE`
  - `transaction.py:328-345` — busy/locked 时 rollback + sleep + retry 整个 operation（全事务级别）
  - `transaction.py:347-352` — `HostDurableError` 也 rollback 全事务
  - 不存在 savepoint 语义或部分提交路径
- **当前状态**: `dispatch.py:3288` 仍使用 `_new_event_id(_EVENT_ID_CONTEXT_COMPACTED_PREFIX)`（UUID），proactive/reactive event_id 确定性不对称是既有模式，非本 slice 引入
- **裁决确认**: 成立

#### DS-F03 — Controller rejected-with-reason，证据确认 ✅

- **Controller 理由**: 既有 `write_bounded_json_payload` 的通用 filesystem/SQLite rollback 属性；content-addressed artifact 的 orphan/cleanup 应由独立 durable-storage work unit 统一处理
- **直接证据**:
  - `payload.py:367-426` — `write_bounded_json_payload` 是通用函数（所有 caller 共享此路径）
  - `payload.py:413-419` — artifact 文件写入（`os.replace` atom rename + fsync）
  - `payload.py:420-426` — descriptor INSERT 在同一 SQLite transaction 内
  - `artifact.py:76-116` — `write_artifact_bytes` 是纯文件系统操作，不参与 SQLite transaction
  - CONTEXT_COMPACTED 不是该函数唯一 caller；修复只加在 compaction owner 会引入并发同 digest 误删风险
- **裁决确认**: 成立

#### DS-F04 — Controller rejected-with-reason，证据确认 ✅

- **Controller 理由**: 当前 activity contract 对 CONTEXT_COMPACTED 只投影固定 `completed` 状态/title，并仅从 payload 读取本事件不存在的 `failure_reason`；inline `{}` 与完整 payload 的可观察结果相同
- **直接证据**:
  - `read_api.py:1368-1371` — CONTEXT_COMPACTED → `status=COMPLETED`, `title="上下文压缩完成"`
  - `read_api.py:1382` — `summary=_bounded_summary(_payload_text(payload, _PAYLOAD_FIELD_FAILURE_REASON))`
  - `context_events.py:1195-1269` — `build_context_compacted_payload` 不包含 `failure_reason` 字段
  - `context_events.py:1339-1410` — `failure_reason` 仅在 `build_context_compaction_failed_payload` 中存在
  - `read_api.py:1590` — `_payload_text` 对缺失 key 返回 `None`
  - `read_api.py:1615` — `_bounded_summary(None)` 返回 `None`
- **裁决确认**: 成立

#### DS-F05 — Controller rejected-with-reason，证据确认 ✅

- **Controller 理由**: `CONTEXT_COMPACTION_ATTEMPT_REJECTED` 当前只有 inline canonical writer；本 slice 没有也不应为它虚构 descriptor-backed contract
- **直接证据**:
  - `tool_trace.py:667-670` — ACCEPTED 正确使用 `resolve_context_compacted_payload`
  - `tool_trace.py:671-675` — ATTEMPT_REJECTED 使用 `_json_object_from_text(row.payload_json)`（inline only）
  - `context_events.py:1471-1576` — `build_context_compaction_attempt_rejected_payload` 构造 inline-only payload
  - 不存在 descriptor-backed ATTEMPT_REJECTED writer path
- **裁决确认**: 成立

#### DS-F06 — Controller rejected-with-reason，证据确认 ✅

- **Controller 理由**: `ATTEMPT_REJECTED`、`FAILED` 与 `RUNNER_CALL_INPUT_ASSEMBLED` 当前没有 descriptor-backed storage contract
- **直接证据**:
  - `proactive_compaction.py:464-468` — CONTEXT_COMPACTED 正确使用 `resolve_context_compacted_payload`；else 分支使用 `payload_object(row)`
  - 这些 event type 均无 `store_*` 函数或 descriptor-backed writer
- **裁决确认**: 成立

#### DS-F07 — Controller rejected-with-reason，证据确认 ✅

- **Controller 理由**: `PayloadStore` 当前无实例状态；proactive 内原本已多处按值实例化该 durable primitive
- **直接证据**:
  - `payload.py:155-160` — `class PayloadStore:` 无 `__init__`、无 `__slots__`、无类级可变状态
  - `dispatch.py:3307` — `PayloadStore()` 行内实例化
  - `engine_ingest.py:3114` — `self._payload_store` 注入方式
  - 两条路径行为完全一致（PayloadStore 所有方法只使用参数中的 `transaction`）
- **裁决确认**: 成立

#### DS-F08 — Controller rejected-with-reason，证据确认 ✅

- **Controller 理由**: `build_context_compacted_payload` 拥有 canonical semantic shape，不拥有 storage threshold；把 storage policy 塞进 semantic builder 会造成 owner drift
- **直接证据**:
  - `context_events.py:1195-1269` — semantic builder，无尺寸检查
  - `context_event_payload.py:79` — 尺寸检查在 storage owner（`store_context_compacted_payload`）
  - `event_log.py:1299-1307` — EventLog write 边界对 CANONICAL_FACT 做最终 inline size guard
  - 三层防护存在且各司其职
- **裁决确认**: 成立

### Adversarial Correctness Bug 搜索结果

#### 全 consumer 覆盖核查

对全部 11 处 CONTEXT_COMPACTED consumer 逐一验证，确认均使用 `resolve_context_compacted_payload` 或通过上层已解析 payload 间接消费：

| Consumer | 位置 | 解析方式 | 状态 |
|---|---|---|---|
| `compact_material._validated_compacted_payload` | compact_material.py:2493 | `resolve_context_compacted_payload` | ✅ |
| `compaction_terminal._strict_terminal_payload` | compaction_terminal.py:262-263 | `resolve_context_compacted_payload` | ✅ |
| `tool_trace._resolved_compactor_response_from_row` (ACCEPTED) | tool_trace.py:667-670 | `resolve_context_compacted_payload` | ✅ |
| `proactive_compaction._project_state` | proactive_compaction.py:464-466 | `resolve_context_compacted_payload` | ✅ |
| `projection.projection_event_view_from_row` | projection.py:717-718 | `resolve_context_compacted_payload` | ✅ |
| `run_input._load_pre_start_compact_artifact` | run_input.py:4248 | `resolve_context_compacted_payload` | ✅ |
| `run_input._memory_projection_payload` | run_input.py:5491-5492 | `resolve_context_compacted_payload` | ✅ |
| `run_input.DurableCompactArtifactProvider._load_compact_artifact_tx` | run_input.py:1973 | `resolve_context_compacted_payload` | ✅ (DS-F01 修复点) |
| `run_input._validate_loaded_compact_view_matches_event` | run_input.py:5571 | `resolve_context_compacted_payload` | ✅ |
| `run_input._compaction_trigger_source_for_compacted_event` | run_input.py:5593-5596 | `resolve_context_compacted_payload` | ✅ |
| `memory.MemoryProjectionEvent` | memory.py:975,1233 | 通过上层 `compacted_semantics` 传入 | ✅ |

#### Fail-closed 链路端到端验证

追踪 descriptor-backed CONTEXT_COMPACTED 的完整解析链路，确认 corruption 在任一层均 fail closed：

1. **Event identity check** → `resolve_context_compacted_payload:120-121` — 校验 event_class/event_type
2. **Ref/digest pairing** → `resolve_context_compacted_payload:122-123` — `(payload_ref is None) != (payload_digest is None)` 必须成对
3. **Descriptor resolution** → `event_payload_object:68-77` — ref 非 None 时走 `sqlite_payload_object`
4. **Descriptor identity** → `_validate_descriptor_identity:101-119` — ref/digest/kind-specific identity 全校验
5. **Row identity (SQLite path)** → `_validate_sqlite_row_identity:183-195` — id/format/digest/size 校验
6. **Artifact path containment (artifact path)** → `_read_verified_artifact_json_bytes:213-220` — `read_artifact_bytes` 做 containment guard
7. **Actual bytes validation** → `_validate_actual_bytes:244-247` — SHA256 digest + byte size 精确一致
8. **Canonical JSON parse** → `_canonical_json_object_from_bytes:250+` — UTF-8/JSON/object shape/canonical encoding 校验
9. **Canonical contract validation** → `validate_context_compacted_payload:1272+` — 所有必填字段、digest 格式、text 字段严格校验

**结论**: 任一环节 corruption 均抛出 `HostDurableError`，无静默降级路径。

#### 无第二真源 / 下游补偿确认

- `context_event_payload.resolve_context_compacted_payload` 是所有 consumer 的唯一 payload 恢复入口
- 无 `hasattr` / `getattr`、loose parsing、fallback 默认值或兼容 shim
- `compact_artifact_ref`（终端 payload 中的 artifact 引用）与 `payload_ref`（终端自身的 descriptor ref）命名空间不重叠，无反解混淆

#### 无新发现 correctness bug

adversarial 搜索覆盖以下场景，均未发现可达 correctness bug：
- 空 `accepted_evidence_mapping_refs` → `validate_context_compacted_payload` 接受空 list
- 极端大 `summary_text` → `store_context_compacted_payload` 正确委托 `write_bounded_json_payload` 外置
- 并发同 digest artifact 写入 → content-addressed 写 idempotent
- EventLog payload_ref 被篡改为其他有效 descriptor → `validate_context_compacted_payload` 会因 contract 字段缺失 fail closed
- `payload_inline_threshold_bytes = 0` → 所有 payload 走 descriptor-backed storage（正确）
- `payload_json = {}` 被误解析为真实 payload → `event_payload_object` 的 `payload_ref is None` 检查确保 ref 非 None 时不走 inline parse

## Test Results

| 测试范围 | 结果 |
|---|---|
| `test_durable_compact_artifact_provider_resolves_descriptor_payload_and_fails_closed` | ✅ PASS |
| `test_oversized_accepted_compact_terminal_uses_descriptor_truth` | ✅ PASS |
| `test_reactive_oversized_accepted_terminal_uses_descriptor_truth` | ✅ PASS |
| `tests/host/test_run_input_builder.py` (全 103) | ✅ 103 passed |
| `tests/host/test_dispatch_scheduler.py` + 其他受影响模块 (452) | ✅ 452 passed |
| `tests/host/` (全量) | ✅ 2425 passed, 2 skipped, 6 deselected |
| pyright (全仓) | ✅ 0 errors, 0 warnings, 0 informations |

## Open Questions

无。

## Residual Risk

1. **Artifact orphan on descriptor INSERT failure**（原 DS-F03）: `write_bounded_json_payload` 的 artifact 文件写入在 SQLite descriptor INSERT 之前，descriptor INSERT 失败后 artifact 文件残留。这是 `write_bounded_json_payload` 的既有通用属性，非本 PR 引入。Content-addressed storage（相同 digest → 相同路径）使后续重写 idempotent，实际 orphaning 影响低。建议由独立 durable-storage work unit 统一处理，不在 compaction owner 局部 patch。

2. **Savepoint retry 语义未测试**: 所有测试使用全事务级别的 `run_write`（`BEGIN IMMEDIATE ... COMMIT`），未覆盖 savepoint 或部分回滚场景。当前 `HostTransactionRunner` 不支持 savepoint retry，若未来引入，proactive event_id 非确定性（DS-F02）和 artifact orphaning 可能从 latent 变为 active。当前无功能影响。

3. **ATTEMPT_REJECTED / FAILED 未来 descriptor-backed 扩展**: 若这些 event type 未来引入 descriptor-backed storage（例如 ATTEMPT_REJECTED 携带大 `diagnostic_refs`），`tool_trace.py`（DS-F05）和 `proactive_compaction.py`（DS-F06）的 inline-only 解析需同步更新。当前这些 event type 无 descriptor-backed writer，不影响正确性。

## Final Verdict

**PASS** — DS-F01 修复正确，resolver 复用严格，owner test 验证了 descriptor-backed 正确解析与 digest corruption fail-closed。DS-F02 至 DS-F08 的 controller rejected-with-reason 均由当前事务/事件 storage/owner 直接证据支持。全 consumer 覆盖核查通过，无一遗漏。Fail-closed 链路经 9 层端到端验证。Adversarial 搜索未发现新 correctness bug。全部 2425 测试通过，pyright clean。
