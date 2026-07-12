# Code Review — R3-C S3 Host Adapter Snapshot And Service-Owned Fins Wait Glue

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: main
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s3-code-review-ds.md`
- Review target: R3-C S3 — Host `WaitAdapterSnapshot` projection, Service-owned Fins wait adapter migration, old Fins wait adapter deletion
- Review date: 2026-07-13T01:25:49+08:00

### Included scope

**Production files:**
- `dayu/host/wait_adapter.py` — added `WaitAdapterSnapshot` + `WaitAdapterSnapshotProjectionError` + `_adapter_snapshot_from_wait_record()` + `_validate_adapter_snapshot_resume_token()`; changed `WaitPollAdapter` Protocol (`WaitRecordRow` → `WaitAdapterSnapshot`); changed `WaitPoller.poll_once()` / `_poll_cancelled_waits()` snapshot projection; added `WaitResumePolicy` to `__all__`
- `dayu/fins/ingestion/wait_adapter.py` — **deleted** (614 lines)
- `dayu/service/fins_wait_adapter.py` — **new** (599 lines), Service-owned adapter module reusing the migrated adapter logic with `WaitAdapterSnapshot` contract
- `dayu/service/host_assembly.py` — import path changed from `dayu.fins.ingestion.wait_adapter` to `dayu.service.fins_wait_adapter`

**Test files:**
- `tests/service/test_fins_wait_adapter.py` — **new** (797 lines), covering registry binding, activation runtime reuse, corrupt token fail-fast, all observation status→Host outcome mappings, transient unavailable, old snapshot created_at not forcing lost, abandon lifecycle (valid/corrupt/missing/LOST/non-transient-error/cancel-non-transient/transient-unavailable)
- `tests/host/test_wait_adapter_polling.py` — adapter fakes updated to `WaitAdapterSnapshot`; new `_SnapshotRecordingAdapter` + `test_poll_adapter_receives_minimal_host_snapshot` + parametrized `test_wait_adapter_snapshot_rejects_empty_or_too_long_resume_token` / `test_poll_adapter_snapshot_projection_failure_releases_with_backoff` / `test_abandon_adapter_snapshot_projection_failure_releases_with_backoff`; `_AbandonClaimStealingAdapter` / `_AbandonAlreadyMarkedAdapter` receive `wait_id` via constructor
- `tests/host/test_wait_observation_runner.py` — `_BlockingAdapter` updated to `WaitAdapterSnapshot`
- `tests/host/test_wait_poller_runtime.py` — `_SequenceAdapter` / `_BlockingReadyAdapter` updated to `WaitAdapterSnapshot`
- `tests/host/test_open_host_runtime.py` — `_ReadyPollAdapter` updated to `WaitAdapterSnapshot`
- `tests/service/test_host_assembly.py` — import path changed
- `tests/service/test_import_boundary.py` — added `dayu.fins.direct_event_text` to allowed imports
- `tests/fins/test_fins_ingestion_tools.py` — removed 583 lines: all wait adapter tests (`_wait_record`, `_boundary_from_now`, `_activation_request`, `_accepted_ack` helpers + 13 test functions) and all Host durable imports; Fins tests now only cover Fins-side contracts
- `tests/fins/test_fins_ingestion_runtime.py` — removed `_observation_wait_record` helper + all Host durable imports; `test_activation_submit_failure_is_observed_as_failed_by_wait_adapter` replaced by `test_activation_submit_failure_terminalizes_prepared_observation` (directly asserts `FinsObservationStatus.FAILED` on snapshot, not going through wait adapter)

**Documentation files:**
- `dayu/README.md` — "lightweight observation handle" → "lightweight observation handle 和 Service-owned wait adapter"
- `dayu/fins/README.md` — 60 lines changed: removed wait adapter as Fins responsibility, documented Service-owned `dayu.service.fins_wait_adapter`, removed Host import exception, clarified Fins only owns observation handle/snapshot contract
- `dayu/host/README.md` — documented `WaitAdapterSnapshot` projection contract
- `dayu/service/README.md` — documented `dayu.service.fins_wait_adapter` module and its import boundary
- `tests/README.md` — documented moved test coverage

**Other:**
- `utils/smoke_host_public_awaiting_entrypoint.py` — `_GatedReadyPollAdapter` updated to `WaitAdapterSnapshot`; removed `_OpaqueWaitInput` Protocol

### Excluded scope

- S1 Storage Identity, Commit Point, And Local Durability (not in this change set)
- S2 Single-Document Ingestion Atomicity (not in this change set)
- `docs/host/issues-implementation-control.md` — controller artifact, not reviewed here
- `docs/phaseflow-umbrella-optimization-control.md` — controller artifact, not reviewed here

## Findings

未发现实质性问题。

### Review Area 1: Host WaitAdapterSnapshot 投影的唯一所有权

**入口/函数**: `_adapter_snapshot_from_wait_record()` (新增) + `WaitPoller.poll_once()` / `_poll_cancelled_waits()` (修改)

**证据**:
- `dayu/host/wait_adapter.py:2254-2270` — `_adapter_snapshot_from_wait_record()` 是唯一的 `WaitRecordRow → WaitAdapterSnapshot` 投影点，使用 `parse_utc_timestamp()` 解析创建时间并校验 resume token
- `dayu/host/wait_adapter.py:1078-1095` — `poll_once()` 在调用 `adapter.poll_wait()` 前投影 snapshot；投影失败时通过 `WaitAdapterSnapshotProjectionError` fail-closed，走 `ADAPTER_ERROR` backoff，不调用 adapter
- `dayu/host/wait_adapter.py:1332-1347` — `_poll_cancelled_waits()` 在调用 `adapter.abandon_wait()` 前同样投影 snapshot；投影失败走 `ABANDON_ERROR` backoff
- `dayu/host/wait_adapter.py:230-282` — `WaitAdapterSnapshot` 是 frozen/slots dataclass，严格 3 字段：`tool_name: str`、`resume_token: str`、`created_at: datetime`；`__post_init__` 校验非空、token 长度上限、时区 aware
- `WaitPollAdapter` Protocol (`:899-924`) 改收 `snapshot: WaitAdapterSnapshot`，不再暴露 `WaitRecordRow`

**结论**: Host 唯一拥有 `WaitRecordRow → WaitAdapterSnapshot` 投影。adapter 不接收 `WaitRecordRow`、`deadline_at`、`expires_at`、`claim`、state mutator 或 durable governance 字段。投影失败在 Host 侧 fail-closed，不把非法 durable 数据传给外部 adapter。**PASS。**

### Review Area 2: Service Fins adapter 只消费 Host public contract

**入口/函数**: `dayu/service/fins_wait_adapter.py` 全模块

**证据**:
- `dayu/service/fins_wait_adapter.py:49-75` — 导入清单：`dayu.host.api` (public resolve outcomes, `WaitAdapterKey`), `dayu.host.wait_adapter` (public `WaitAdapterSnapshot`, `WaitPollResult`, registry types, lifecycle types, `WaitResumePolicy`)
- **不含** `dayu.host.durable` — rg 扫描确认零命中
- `dayu/service/fins_wait_adapter.py:359-376` — `_handle_from_snapshot()` 只消费 `snapshot.resume_token`、`snapshot.tool_name`、`snapshot.created_at`（已解析 `datetime`），不解析时间字符串、不补时区、不回退 `now`
- 整个文件中 `deadline_at`、`expires_at`、`.claim`、`state mutator`、`external_job_ref`、`snapshot_ref`、`wait_id`、`session_id`、`run_id`、`attempt_id` 均无有效命中（唯一命中 `external_job_ref_source` 是 `WaitExternalJobRefSource.RESUME_TOKEN` 枚举，属于 public binding contract，不是 durable row 字段读取）
- 对比旧代码 `_timestamp_or_now()` (已删除的 `dayu/fins/ingestion/wait_adapter.py:804-818`)：旧代码在时间戳解析失败时静默回退 `datetime.now(timezone.utc)`；新代码无此 fallback
- 旧代码 `_poll_error_result(wait_record, exc)` 中 `wait_record` 参数实际从未被函数体使用（已删除的 `:609-623`）；新代码 `_poll_error_result(exc)` 只收 `exc`

**结论**: Service Fins adapter 只消费 Host public `WaitAdapterSnapshot` / outcome / registry contract，不导入 `dayu.host.durable`，不读取 `deadline_at`、`expires_at`、`claim`、state mutator 或 `external_job_ref` 等 Host durable governance 字段。旧 `_timestamp_or_now` fallback 已消除，Host 侧已通过 `WaitAdapterSnapshotProjectionError` 保证投影合法性。**PASS。**

### Review Area 3: dayu.fins 清理完整，无 Host import 残留

**证据**:
```bash
rg -n '(^|[[:space:]])(from|import)[[:space:]]+dayu\.host' dayu/fins --glob '*.py'
# EXIT_CODE: 1 (zero matches)
```
- `dayu/fins/ingestion/wait_adapter.py` 已物理删除，`test ! -e` 确认不存在
- `dayu/fins/ingestion/` 目录下无兼容 re-export、wrapper 或 facade 模块 — compat scan 零命中
- `tests/fins/test_fins_ingestion_tools.py` 移除全部 Host import（`dayu.host.api`、`dayu.host.durable.state`、`dayu.host.durable.codec`、`dayu.host.wait_adapter`、`dayu.host.waiting`）
- `tests/fins/test_fins_ingestion_runtime.py` 移除全部 Host import（`dayu.host.durable.state`、`dayu.host.api`、`dayu.host.wait_adapter`）及 `_observation_wait_record` helper

**结论**: `dayu.fins` 生产代码完全没有 Host import；旧 `wait_adapter.py` 已删除且无残留 re-export/wrapper；Fins 测试不再引用 Host durable 类型。**PASS。**

### Review Area 4: 测试边界正确迁移

**Fins 测试不再固化 Service adapter 语义：**
- `tests/fins/test_fins_ingestion_tools.py` — 删除 13 个 wait adapter 测试（registry binding、poll mapping、abandon lifecycle、transient-unavailable-with-host-boundaries 等）及所有 Host durable 测试夹具（`_wait_record`、`_boundary_from_now`、`_activation_request`、`_accepted_ack`，共 ~583 行）
- `tests/fins/test_fins_ingestion_runtime.py` — `test_activation_submit_failure_is_observed_as_failed_by_wait_adapter` 改为 `test_activation_submit_failure_terminalizes_prepared_observation`：新测试只断言 `FinsObservationStatus.FAILED`，不通过 `FinsIngestionWaitPollAdapter` 间接观察，不消费 `WaitRecordRow` 或 `WaitPollReady`

**Service 测试覆盖 registry/activation/poll/abandon/snapshot 边界：**
- `tests/service/test_fins_wait_adapter.py` — 17 个测试（51 passed），覆盖：
  - registry binding: `test_fins_wait_adapter_registry_binds_supported_tools`、`test_fins_wait_adapter_registry_duplicate_binding_fails`
  - activation: `test_fins_wait_activation_registry_uses_shared_runtime`、`test_fins_wait_activation_adapter_activates_existing_resume_token`、`test_fins_wait_activation_adapter_rejects_corrupt_resume_token`
  - poll snapshot→outcome mapping: `test_fins_wait_poll_adapter_maps_observation_statuses`（全部 6 种 status）、`test_fins_wait_poll_adapter_rejects_failed_result_without_message`、`test_fins_wait_poll_adapter_corrupt_and_missing_handles_are_lost`
  - transient/snapshot boundary: `test_fins_wait_poll_adapter_transient_unavailable_is_not_ready`、`test_fins_wait_poll_adapter_old_snapshot_created_at_does_not_force_lost`
  - abandon lifecycle: `test_fins_wait_poll_adapter_abandon_cancels_and_cleans_observation`、`test_fins_wait_poll_adapter_abandon_corrupt_token_is_noop`、`test_fins_wait_poll_adapter_abandon_missing_observation_is_noop`、`test_fins_wait_poll_adapter_abandon_lost_snapshot_is_noop`、`test_fins_wait_poll_adapter_abandon_non_transient_error_is_noop`、`test_fins_wait_poll_adapter_abandon_cancel_non_transient_error_is_noop`、`test_fins_wait_poll_adapter_abandon_transient_unavailable_re_raises`

**Host 测试覆盖 snapshot projection contract：**
- `tests/host/test_wait_adapter_polling.py` — 新增 `_SnapshotRecordingAdapter` + 5 个新测试：
  - `test_poll_adapter_receives_minimal_host_snapshot` — 断言 adapter 只收到 3 字段 snapshot，字段值与 durable row 一致
  - `test_wait_adapter_snapshot_rejects_empty_or_too_long_resume_token` — 参数化测试空 token 与超长 token 被 `WaitAdapterSnapshot.__post_init__` 拒绝
  - `test_poll_adapter_snapshot_projection_failure_releases_with_backoff` — 参数化非法 `resume_token` / `created_at` → adapter 未被调用 → `ADAPTER_ERROR` backoff
  - `test_abandon_adapter_snapshot_projection_failure_releases_with_backoff` — cancelled wait 的非法 snapshot → abandon adapter 未被调用 → `ABANDON_ERROR` backoff

**结论**: Fins 测试不再固化 Service adapter 语义；Service 测试覆盖 registry/activation/poll/abandon/snapshot 全部关键边界；Host 测试覆盖 snapshot projection contract 的正向、拒绝与 fail-closed 路径。**PASS。**

### Review Area 5: README 同步正确，无 tool-security 实施

**证据**:
- `dayu/README.md` — 1 行变更：`lightweight observation handle` → `lightweight observation handle 和 Service-owned wait adapter`；仅说明已落地边界
- `dayu/fins/README.md` — 所有变更均为：删除 Fins wait adapter 作为 Fins 职责的描述；说明 `dayu.service.fins_wait_adapter` 作为 Service assembly component；删除 Fins→Host import 例外条款；将 "wait adapter" 术语改为 "Service wait adapter" 或 "awaiting observation"。无 tool-security 内容
- `dayu/host/README.md` — 2 段变更：说明 Host poller 在调用 adapter 前把 durable row 投影为 `WaitAdapterSnapshot(tool_name, resume_token, created_at)`；adapter 不接收 deadline/expiry/claim/state mutator。无 tool-security 内容
- `dayu/service/README.md` — 新增模块说明和 import boundary 约束，无 tool-security 内容
- `tests/README.md` — 更新测试覆盖描述，无 tool-security 内容
- 全量 diff 中 `dayu/config/prompts`、tool schema 文件零变更

**结论**: README 同步只说明已落地边界（Fins→Service ownership shift、snapshot contract、import boundary），没有实施也未声称实施 tool-security（URL/TLS/redirect/SSRF/upload allowlist/file authority/symlink-safe upload source/remote byte budget/LLM-facing security schema）。**PASS。**

### Review Area 6: AGENTS.md 约束合规

**证据**:
- **中文 docstring**: 所有新增/修改函数均有完整中文 docstring（参数、返回值、异常）。`dayu/service/fins_wait_adapter.py` 模块级 docstring 说明定位与不读取项；每个公开函数与私有 helper 均有完整中文说明
- **无 Any/object 签名**: rg 扫描 `\b(Any|object)\b` 在新 production 文件中零命中（`__all__` 除外）；`_run_async_observation` 的 `Coroutine` 类型参数从旧 `[object, object, ...]` 精确化为 `[None, None, ...]`
- **无 getattr/hasattr**: rg 扫描零命中
- **无兼容 shim**: 旧 `dayu/fins/ingestion/wait_adapter.py` 直接删除，无 re-export, wrapper, facade, lazy import；compat scan 零命中；`dayu/service/host_assembly.py` import 路径直接改为新模块
- **无下游 fallback 修语义**: 旧 `_timestamp_or_now()` fallback 已删除；Service adapter 不再解析时间字符串或补时区；非法 snapshot 在 Host 侧 `WaitAdapterSnapshotProjectionError` fail-closed

**结论**: 所有新增/修改生产代码符合 AGENTS.md 编码硬约束。**PASS。**

## Open Questions

无。

## Residual Risk

| Risk | Classification | Notes |
| --- | --- | --- |
| `WaitResumePolicy` 从 `dayu.host.wait_adapter` re-export | 低风险，已接受 | `WaitResumePolicy` 是 Host public enum，原在 `dayu.host.durable.state` 定义，现已从 `dayu.host.wait_adapter.__all__` 重新导出供 Service adapter 消费。如果将来 `WaitResumePolicy` 语义变化，Service adapter 的 `_binding_for_tool_name()` 需要同步。当前 risk 低：该 enum 值 `POLL` 是稳定 contract |
| Smoke 文件 `_GatedReadyPollAdapter` 删除了 `_OpaqueWaitInput` Protocol | 低风险，无影响 | `_OpaqueWaitInput` 是 smoke 内部 Protocol，用于原 `poll_wait(wait_record: "_OpaqueWaitInput")` 类型标注。改为 `WaitAdapterSnapshot` 后不再需要。smoke 不是生产代码 |

无其他未覆盖测试、未验证路径或已知 regression 风险。

## Validation

```bash
# 核心测试 (51 passed)
pytest tests/service/test_fins_wait_adapter.py tests/host/test_wait_adapter_polling.py tests/service/test_import_boundary.py -q

# 边界扫描
rg -n '(^|[[:space:]])(from|import)[[:space:]]+dayu\.host' dayu/fins --glob '*.py'
# → 零匹配 ✓

test ! -e dayu/fins/ingestion/wait_adapter.py
# → PASS ✓

rg -n 'dayu\.host\.durable' dayu/service/fins_wait_adapter.py
# → 零匹配 ✓

rg -n '(hasattr|getattr)' dayu/service/fins_wait_adapter.py dayu/host/wait_adapter.py
# → 零匹配 ✓

rg -n '\b(Any|object)\b' dayu/service/fins_wait_adapter.py dayu/host/wait_adapter.py
# → 零命中（除 __all__） ✓
```

## Review Conclusion

**PASS** — R3-C S3 Host Adapter Snapshot And Service-Owned Fins Wait Glue 变更在全部 6 个专项审查区域内未发现实质性问题：

1. Host 唯一拥有 `WaitRecordRow → WaitAdapterSnapshot` 投影，`WaitPoller` 在调用 adapter 前统一 fail-closed 校验
2. Service Fins adapter 只消费 Host public snapshot/outcome contract，不导入 `dayu.host.durable`，不读取 deadline/expiry/claim/state mutator
3. `dayu.fins` 零 Host import，旧 `wait_adapter.py` 已删除，无兼容 re-export/wrapper
4. Fins 测试不再固化 Service adapter 语义，Service 测试覆盖 registry/activation/poll/abandon/snapshot 全边界
5. README 同步只说明已落地边界，无 tool-security 实施
6. 符合 AGENTS.md 编码硬约束（中文 docstring、无 Any/object/getattr/hasattr、无兼容 shim、无下游 fallback）
