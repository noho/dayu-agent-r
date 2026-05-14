# Code Re-Review: Host P2 S3 Payload / Artifact / Liveness Fix Verification

## Scope

- **Mode**: current workspace changes (fix verification re-review)
- **Branch**: `feat/host-phase2-durable-store-eventlog`
- **Base**: Slice 3 implementation (uncommitted workspace)
- **Output file**: `docs/reviews/gateflow-code-re-review-host-p2-s3-payload-artifact-liveness-ds-20260514.md`
- **Included scope**: 全部未提交 workspace 改动（`_validation.py` 新增、`event_log.py`/`idempotency.py` 提取重构、`payload.py`/`liveness.py`/`artifact.py` Slice 3 新增、相关测试、README 更新）
- **Excluded scope**: 已提交 Slice 2 commit `50ba2d7`、docs/reviews/ 下现有 review artifacts
- **Parallel review coverage**: 无

## Verification Evidence

### 测试

```
tests/host/test_payload_store.py + test_artifact_store.py + test_host_instance_liveness.py: 27 passed
tests/host/test_event_log_store.py + test_idempotency_store.py + test_event_log_multiprocess.py: 20 passed
tests/host (all): 94 passed
```

### 类型检查

```
python -m pyright dayu/host tests/host: 0 errors, 0 warnings, 0 informations
```

## Accepted Findings Verification

### S3-F1 — VERIFIED FIXED — duplicated durable scalar validation helpers extracted

**验证点**: 所有 durable 模块的内联 scalar 校验 helper (`_require_non_empty_text`, `_require_optional_non_empty_text`, `_require_text`, `_optional_text`, `_require_int`, `_optional_int`, `_validate_digest`) 已抽取到 `dayu/host/durable/_validation.py`。

**证据**:

1. `_validation.py` (L1-123) 承载 8 个纯标量校验函数，不表达 EventLog/idempotency/payload/liveness 业务语义。
2. `event_log.py` 原 5 个本地 helper 全部删除；L17-23 从 `_validation` import 5 个函数。
3. `idempotency.py` 原 6 个本地 helper（含 `_validate_digest`）全部删除；L13-20 从 `_validation` import 6 个函数（含 `require_sha256_digest as _validate_digest`）。
4. `payload.py` L17-24 从 `_validation` import 6 个函数。
5. `liveness.py` L22-28 从 `_validation` import 5 个函数。
6. `SQLiteScalar` import 已从 `event_log.py` 和 `idempotency.py` 中移除。
7. `_validation.py` L9-11 只依赖 `dayu.host.durable.codec`、`dayu.host.durable.errors`、`dayu.host.durable.transaction`，均为 durable 内部依赖。

**边界验证**:
- `dayu/host/__init__.py` 未导入 `_validation` — 无公共导出。
- `_validation.py` 未从 `dayu.engine`/`dayu.service`/`dayu.ui`/`dayu.fins` 导入 — 无跨层穿透。
- EventLog/idempotency 回归测试 20 passed — 行为未改变。
- 错误文案未改变（对比 old/new diff 逐字一致）。

### S3-F2 — VERIFIED FIXED — validate_artifact_ref negative artifact_size_bytes 有直接测试

**生产代码** (`artifact.py:132-133`):
```python
if artifact_ref.artifact_size_bytes < 0:
    raise HostDurableError("Artifact size must be non-negative")
```

**测试代码** (`test_artifact_store.py:145-155`):
```python
def test_artifact_ref_rejects_negative_size() -> None:
    with pytest.raises(HostDurableError, match="Artifact size must be non-negative"):
        validate_artifact_ref(
            LocalArtifactRef(
                artifact_relative_path="sha256/ab/value",
                artifact_digest=sha256_digest_bytes(b"content"),
                artifact_size_bytes=-1,
            )
        )
```

测试直接调用 `validate_artifact_ref`，构造合法路径与合法 digest、仅 `artifact_size_bytes=-1`，精确断言错误文案。覆盖 negative branch，不依赖 artifact store 集成路径。

### S3-F3 — VERIFIED FIXED — BYTES payload 拒绝非 None payload_json

**生产代码** (`payload.py:412-416`):
```python
if (
    request.payload_format is SQLitePayloadFormat.BYTES
    and request.payload_json is not None
):
    raise HostDurableError("bytes payload must not include payload_json")
```

该检查在 `_validate_sqlite_payload_request` 内，位于 `_encode_sqlite_payload` 之前，确保在编码阶段不会被静默忽略。

**测试代码** (`test_payload_store.py:232-258`):
```python
def test_bytes_payload_rejects_payload_json(tmp_path: Path) -> None:
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

测试通过真实 `open_host_durable_store` + transaction runner 路径，`payload_format=BYTES` 且显式传入非 None `payload_json={"ignored": False}`，精确断言错误文案。

## Additional Verification Items

### payload descriptor

`payload.py` 中 `write_sqlite_payload` 与 `write_payload_descriptor_for_artifact` 两条写入路径均在 validation → encoding → digest check → insert → read-back 范式内，无半提交窗口。`_validate_expected_digest` 对 `expected_digest=None` 正确处理为跳过校验（`payload.py:464-465`）。

### artifact path safety

`artifact.py` 中的 containment 校验链完整：
- `_validate_relative_path_text` (L169-185): 拒绝空字符串、绝对路径、空字节、`.` / `..` 遍历。
- `_is_temp_relative_path` (L188-196): 拒绝 `.tmp/` 前缀路径。
- `_ensure_contained` (L246-259): 基于 `Path.resolve(strict=True)` + `relative_to` 的真实路径 containment。
- `_ensure_parent_dir_contained` (L263-278): 创建目录前逐级检查祖先 symlink 逃逸。
- `write_artifact_bytes` (L75-116): temp write → fsync → digest re-verify → atomic `os.replace` → final digest verify → `validate_artifact_ref` → cleanup on error。

### EventLog descriptor validation

`event_log.py:_validate_existing_payload_descriptor` (L507-549):
- `payload_ref is None` → 无 descriptor，直接返回（FK 约束兜底）。
- descriptor 不存在 → 返回（FK 约束兜底）。
- digest mismatch → `HostPayloadReferenceError`。
- `ARTIFACT_REF` descriptor → 校验 `artifact_relative_path` 非空 + 通过 `validate_artifact_ref` 拒绝 temp path。

与 `event_log.py:_validate_payload_reference` (L484-504) 组合：前者校验 payload_ref/digest 字段格式与配对，后者校验已存在 descriptor 内容一致性。

### liveness boundary

`liveness.py` L15-28 只导入 `_validation`、`codec`、`errors`、`schema`、`transaction`，均为 durable 内部依赖。`CRASHED_SUSPECTED` enum 值定义但无 writer — 按 adjudication 结论，是为 Phase 2+ recovery 预留的 schema foundation，当前无实现要求。

### strong typing / import boundaries

- `_validation.py` 所有函数签名使用完整类型标注（`str | None`、`SQLiteScalar`），无 `Any`/`object`。
- 所有 4 个生产模块未从 `dayu.engine`/`dayu.service`/`dayu.ui`/`dayu.fins` 导入。
- `event_log.py` `payload.py` 间的 cross-import 方向正确：`event_log.py` → `payload.py`（引用 `read_payload_descriptor`/`PayloadKind`），`payload.py` → `artifact.py`（引用 `validate_artifact_ref`/`LocalArtifactRef`）。均为 durable 内部单向依赖，无循环。
- `dayu/host/__init__.py` 未泄漏任何 `_validation` 或 durable 内部模块符号。

### README behavior

- `dayu/host/README.md`: durable foundation 描述新增 Payload descriptor、Local artifact helper、Host instance liveness 三段，与 Slice 3 实现一致。`当前未实现` 列表准确移除已实现项，保留 deferred 项（Session/Run/Attempt 状态机、recovery classifier、lease/fencing/takeover、artifact cleanup scheduler 等）。
- `tests/README.md`: 新增 Slice 3 测试运行命令与描述。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- `_validation.py` 作为 durable 私有 helper 的 scope 已在 adjudication 中限定。未来 durable 模块新增时如果引入新的 scalar 校验变体，需要在 code review 时决策是否归入 `_validation.py`。当前集中了现有全部 duplicate family，无遗漏。
- Artifact orphan 文件（SQLite rollback 后残留的已发布 artifact 文件）在 `test_sqlite_failure_after_artifact_publish_leaves_orphan_not_fact` 中有明确测试覆盖，确认 orphan 存在但不被视为 accepted fact。Cleanup 机制按计划属于后续 cleanup/diagnostics work unit，当前无 regression。

## Conclusion

**PASS**

三个 accepted findings (S3-F1, S3-F2, S3-F3) 已正确修复。测试全部通过（94 passed），pyright 干净（0 errors）。未发现新的 correctness、stability 或 maintainability 问题。
