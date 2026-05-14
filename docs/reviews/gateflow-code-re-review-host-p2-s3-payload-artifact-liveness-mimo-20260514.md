# Code Re-review

## Scope

- Mode: current changes (re-review of accepted findings fix)
- Branch: `feat/host-phase2-durable-store-eventlog`
- Base: `main`
- Output file: `docs/reviews/gateflow-code-re-review-host-p2-s3-payload-artifact-liveness-mimo-20260514.md`
- Included scope:
  - `dayu/host/durable/_validation.py` (new)
  - `dayu/host/durable/event_log.py` (fix: import from `_validation`, remove duplicated helpers)
  - `dayu/host/durable/idempotency.py` (fix: import from `_validation`, remove duplicated helpers)
  - `dayu/host/durable/payload.py` (fix: import from `_validation`, BYTES format rejects non-None `payload_json`)
  - `dayu/host/durable/liveness.py` (fix: import from `_validation`, remove duplicated helpers)
  - `tests/host/test_payload_store.py` (fix: `test_bytes_payload_rejects_payload_json`)
  - `tests/host/test_artifact_store.py` (fix: `test_artifact_ref_rejects_negative_size`)
- Excluded scope: Slice 1/2 committed code, `dayu.runtime`, Engine/Fins/Service/UI, README changes (unrelated to fix)
- Input artifacts:
  - `docs/reviews/gateflow-code-review-host-p2-s3-payload-artifact-liveness-controller-adjudication-20260514.md`
  - `docs/reviews/gateflow-fix-host-p2-s3-payload-artifact-liveness-20260514.md`
- Parallel review coverage: 无

## Accepted Findings Verification

### S3-F1 - durable scalar validation helpers extraction - PASS

**要求**: 抽取 `dayu.host.durable._validation` 作为 durable 层私有标量校验 helper，替换 `event_log.py`、`idempotency.py`、`payload.py`、`liveness.py` 中的重复 helper。无公共导出、兼容 facade 或 re-export；行为/错误文案不变。

**验证结果**: PASS

**证据**:

1. **`_validation.py` 内容** (lines 1-123): 承载 7 个标量校验函数：
   - `require_non_empty_text` (line 14)
   - `require_optional_non_empty_text` (line 27)
   - `require_sha256_digest` (line 42)
   - `require_optional_sha256_digest` (line 55)
   - `require_text` (line 70)
   - `optional_text` (line 84)
   - `require_int` (line 98)
   - `optional_int` (line 112)

   所有函数实现与原各模块副本完全相同，错误文案一致。

2. **四模块已切换 import**:
   - `event_log.py:17-23`: `from dayu.host.durable._validation import (optional_text as _optional_text, require_int as _require_int, ...)`
   - `idempotency.py:13-20`: `from dayu.host.durable._validation import (optional_int as _optional_int, optional_text as _optional_text, ...)`
   - `payload.py:17-24`: `from dayu.host.durable._validation import (optional_text as _optional_text, require_int as _require_int, ...)`
   - `liveness.py:22-28`: `from dayu.host.durable._validation import (optional_text as _optional_text, require_int as _require_int, ...)`

3. **旧副本已删除**: 各模块底部的 `_require_non_empty_text`、`_require_optional_non_empty_text`、`_require_text`、`_optional_text`、`_require_int`、`_optional_int`、`_validate_digest` 等函数定义已从 `event_log.py`、`idempotency.py`、`payload.py`、`liveness.py` 中完全移除。

4. **无公共导出**: `dayu/host/durable/__init__.py` 为空（line 1-7），不导出 `_validation`。`_validation` 模块内函数使用公开命名（无前导下划线），但作为模块私有（模块名以 `_` 开头），符合 controller 要求的 "private durable helper module"。

5. **import 边界**: `_validation.py` 只依赖 `codec.is_sha256_digest`、`errors.HostDurableError`、`transaction.SQLiteScalar`，均为 durable 层内部模块，无跨层依赖。

6. **别名保持**: 各模块 import 时使用 `as _` 前缀别名（如 `require_text as _require_text`），保持模块内私有调用风格不变。

### S3-F2 - validate_artifact_ref negative artifact_size_bytes test - PASS

**要求**: 在 `tests/host/test_artifact_store.py` 新增聚焦测试，覆盖 `validate_artifact_ref` 拒绝负数 `artifact_size_bytes`，断言错误文案 `Artifact size must be non-negative`。

**验证结果**: PASS

**证据**:

1. **测试位置**: `test_artifact_store.py:145-155` (`test_artifact_ref_rejects_negative_size`)
2. **测试内容**:
   ```python
   def test_artifact_ref_rejects_negative_size() -> None:
       """artifact ref 拒绝负数 artifact_size_bytes。"""
       with pytest.raises(HostDurableError, match="Artifact size must be non-negative"):
           validate_artifact_ref(
               LocalArtifactRef(
                   artifact_relative_path="sha256/ab/value",
                   artifact_digest=sha256_digest_bytes(b"content"),
                   artifact_size_bytes=-1,
               )
           )
   ```
3. **被测代码**: `artifact.py:132-133`:
   ```python
   if artifact_ref.artifact_size_bytes < 0:
       raise HostDurableError("Artifact size must be non-negative")
   ```
4. **错误文案一致**: 测试 `match` 与实现抛出的 `"Artifact size must be non-negative"` 完全匹配。

### S3-F3 - BYTES format rejects non-None payload_json - PASS

**要求**: `SQLitePayloadWriteRequest` 当 `payload_format is BYTES` 时，显式非 `None` 的 `payload_json` 会被拒绝，新增聚焦测试覆盖并断言错误文案 `bytes payload must not include payload_json`。

**验证结果**: PASS

**证据**:

1. **校验代码**: `payload.py:412-416`:
   ```python
   if (
       request.payload_format is SQLitePayloadFormat.BYTES
       and request.payload_json is not None
   ):
       raise HostDurableError("bytes payload must not include payload_json")
   ```
   位于 `_validate_sqlite_payload_request` 函数内，在 `_encode_sqlite_payload` 之前执行。

2. **测试位置**: `test_payload_store.py:232-258` (`test_bytes_payload_rejects_payload_json`)
3. **测试内容**:
   ```python
   def test_bytes_payload_rejects_payload_json(tmp_path: Path) -> None:
       """bytes payload 显式携带 payload_json 时会结构化拒绝。"""
       with open_host_durable_store(_options(tmp_path)) as store:
           def operation(transaction: HostTransaction) -> None:
               write_sqlite_payload(
                   transaction,
                   SQLitePayloadWriteRequest(
                       payload_ref="payload-bytes-with-json",
                       payload_id="sqlite-bytes-with-json",
                       payload_format=SQLitePayloadFormat.BYTES,
                       payload_json={"ignored": False},
                       payload_bytes=b"bytes",
                   ),
               )
           with pytest.raises(
               HostDurableError, match="bytes payload must not include payload_json"
           ):
               store.transaction_runner.run_write(operation)
   ```
4. **输入契约对称**: CANONICAL_JSON 格式已拒绝多余 `payload_bytes`（`payload.py:402-406`），BYTES 格式现拒绝多余 `payload_json`，输入契约对称。

## New Issue Scan

### Payload Descriptor

- `payload.py` 中 `_validate_sqlite_payload_request`（lines 388-416）对 CANONICAL_JSON 和 BYTES 格式的互斥约束现在完全对称。
- `_encode_sqlite_payload`（lines 419-448）不再需要防御 `payload_json` 泄漏，因为校验已在前置完成。
- descriptor 读取 `_payload_descriptor_from_host_row`（lines 469-502）仍使用 `_validation` 中的 helper，行为不变。

### Artifact Path Safety

- `artifact.py` 的 `validate_artifact_ref`（line 132）负数检查代码未被修改，只是新增了直接测试覆盖。
- `_validation.py` 不涉及路径校验逻辑，无影响。

### EventLog Descriptor Validation

- `event_log.py:507-549` 的 `_validate_existing_payload_descriptor` 未被修改，行为不变。
- `_validate_append_request`（lines 457-481）和 `_validate_payload_reference`（lines 484-504）使用 `_validation` 导入的 helper，行为不变。
- `append_event`（lines 209-288）调用 `_validate_existing_payload_descriptor` 的顺序不变：先校验 request，再校验已存在 descriptor，再编码，再写入。

### Liveness Boundary

- `liveness.py` 只导入 `_validation` helper，不引入新依赖。
- `_validate_identity`（lines 357-371）、`_require_same_identity`（lines 374-392）行为不变。
- 不引入 lease/fencing/takeover/orphan 语义。

### Strong Typing / Import Boundaries

- `_validation.py` 类型签名完整：所有参数和返回值均有类型标注。
- 无 `Any`、`object`、无类型参数或无类型返回值。
- `_validation.py` 不 import `dayu.runtime`、`dayu.engine`、`dayu.fins`、`dayu.service`、`dayu.ui`。
- 四个 consumer 模块的 import 行使用 `as` 别名保持模块内 `_` 前缀调用风格。

### README Behavior

- fix artifact 声明 "README 未更新"。`dayu/host/README.md` 和 `tests/README.md` 的 diff 属于 Slice 3 实现阶段的改动，非本次 fix 引入。fix 只调整内部校验复用与输入校验错误路径，不影响已文档化行为。正确。

## Verification Results

| 命令 | 结果 |
|---|---|
| `pytest tests/host/test_payload_store.py tests/host/test_artifact_store.py tests/host/test_host_instance_liveness.py -q` | 27 passed in 0.13s |
| `pytest tests/host/test_event_log_store.py tests/host/test_idempotency_store.py tests/host/test_event_log_multiprocess.py -q` | 20 passed in 0.30s |
| `pytest tests/host -q` | 94 passed in 0.43s |
| `python -m pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |

## Findings

未发现实质性问题。

## Open Questions

- 无

## Residual Risk

- `_validation` 模块内函数使用无前导下划线命名（如 `require_text`），但模块名以 `_` 开头表示私有。Python 中 `from dayu.host.durable import _validation` 仍可执行（`_validation` 出现在 `dir(pkg)` 中），但这不构成公共导出面，因为 `__init__.py` 未显式 re-export 且模块名以 `_` 前缀声明私有意图。未来新增 durable 子模块时需注意从 `_validation` 导入而非自行实现，当前 fix 已覆盖全部四个现有 consumer。
- Slice 3 实现阶段的 README 更新（`dayu/host/README.md`、`tests/README.md`）与本次 fix 无关，其正确性已在原 review 中验证。

## 结论

**PASS** — 三项 accepted findings 均已正确修复，验证证据完整。S3-F1：`_validation.py` 承载共享 helper，四模块已切换 import 且旧副本已删除，无公共导出或兼容 facade。S3-F2：`test_artifact_ref_rejects_negative_size` 直接覆盖负数 `artifact_size_bytes` 分支。S3-F3：`_validate_sqlite_payload_request` 对 BYTES 格式拒绝非 `None` `payload_json`，`test_bytes_payload_rejects_payload_json` 覆盖该输入契约。未引入新问题。全部 host 测试 94 passed，pyright 0 errors。
