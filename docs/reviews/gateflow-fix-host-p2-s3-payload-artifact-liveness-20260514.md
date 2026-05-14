# Gateflow Fix: Host P2 S3 Payload / Artifact / Liveness

## Gate

- **gate name**: code-review fix
- **work unit**: Host Phase 2 Slice 3 Payload / Artifact / Liveness
- **branch**: `feat/host-phase2-durable-store-eventlog`
- **date**: 2026-05-14
- **source adjudication**: `docs/reviews/gateflow-code-review-host-p2-s3-payload-artifact-liveness-controller-adjudication-20260514.md`

## Finding Status

### `S3-F1` - fixed

抽取 `dayu.host.durable._validation` 作为 durable 层私有标量校验 helper，只承载跨 durable module 复用的基础文本、digest 与 SQLite scalar 校验。

已替换以下重复 helper：

- `dayu/host/durable/event_log.py`
- `dayu/host/durable/idempotency.py`
- `dayu/host/durable/payload.py`
- `dayu/host/durable/liveness.py`

行为与错误文案保持不变；未添加公共导出、兼容 facade 或 re-export。

### `S3-F2` - fixed

在 `tests/host/test_artifact_store.py` 新增聚焦测试，覆盖 `validate_artifact_ref` 拒绝负数 `artifact_size_bytes`，并断言既有错误文案：

- `Artifact size must be non-negative`

### `S3-F3` - fixed

在 `SQLitePayloadWriteRequest` 校验中补齐 `BYTES` 格式约束：当 `payload_format is SQLitePayloadFormat.BYTES` 时，显式非 `None` 的 `payload_json` 会被拒绝，不再由编码阶段静默忽略。

新增聚焦测试覆盖该输入契约，并断言错误文案：

- `bytes payload must not include payload_json`

## Changed Files

- `dayu/host/durable/_validation.py`
- `dayu/host/durable/event_log.py`
- `dayu/host/durable/idempotency.py`
- `dayu/host/durable/payload.py`
- `dayu/host/durable/liveness.py`
- `tests/host/test_payload_store.py`
- `tests/host/test_artifact_store.py`
- `docs/reviews/gateflow-fix-host-p2-s3-payload-artifact-liveness-20260514.md`

README 未更新：本次修复只调整 durable 内部校验复用与输入校验错误路径，没有改变已文档化的用户流程、CLI、配置或 Host 对外开发手册行为。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_payload_store.py tests/host/test_artifact_store.py tests/host/test_host_instance_liveness.py -q`
  - Result: `27 passed in 0.14s`
- `source .venv/bin/activate && pytest tests/host/test_event_log_store.py tests/host/test_idempotency_store.py tests/host/test_event_log_multiprocess.py -q`
  - Result: `20 passed in 0.32s`
- `source .venv/bin/activate && pytest tests/host -q`
  - Result: `94 passed in 0.45s`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - Result: `0 errors, 0 warnings, 0 informations`

## Open Questions / Residual Risks

- No blocking open questions.
- No accepted finding remains unfixed.
- Residual risk is limited to future durable modules reintroducing local scalar helper copies; current fix centralizes the existing duplicated family without widening `_validation.py` into a business utility.
