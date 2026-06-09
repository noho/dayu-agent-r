# WU-TOOLS-01-F01-03 Slice 1 Implementation Artifact

## Metadata

- Work unit: `WU-TOOLS-01-F01-03 Production Fins CN/SEC Download And Upload Runtime/Tool Migration`
- Gate: `implementation`
- Slice: `Slice 1 Shared Fins Ingestion Contract And Upload Job Foundation`
- Implementer: Codex
- Date: 2026-06-09
- Artifact path: `docs/reviews/wu-tools-01-f01-03-slice1-implementation-codex.md`

## Scope

本次只实现 Slice 1：新增 typed upload job contract 与 `FinsIngestionRuntime.start_upload(...)` runtime start path，不迁移 OLD upload 业务逻辑，不新增 upload tool/provider/wait adapter，不修改 Host / Engine schema、状态机或公共契约。

## Changed Files

- `dayu/fins/ingestion_runtime.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `dayu/fins/README.md`
- `tests/README.md`
- `docs/reviews/wu-tools-01-f01-03-slice1-implementation-codex.md`

未修改 controller-owned dirty file：

- `docs/host/issues-implementation-control.md`

## Implementation Summary

- 新增 `FinsIngestionOperationKind.UPLOAD`。
- 新增 `FinsUploadFilingRequest`、`FinsUploadMaterialRequest` 与 `FinsUploadRequest` union，使用现有 `SourceKind.FILING` / `SourceKind.MATERIAL` 做 filing/material 分流，未新增 `FinsUploadKind`。
- 新增 `FinsUploadResultSummary`，结果摘要只包含有界 JSON 字段：`source_kind`、`document_id`、`internal_document_id`、`status`、`uploaded_files`、`primary_document`、`deleted`、`skip_reason`、`document_version`、`source_fingerprint`。
- 新增 `FinsJobCancellationChecker` 与 `FinsUploadRunner` typed protocol；runtime 通过 job store cancellation checker 把合作式取消边界传给 runner。
- 新增 `FinsIngestionRuntime.start_upload(...)`，沿用现有 start 语义：ticker 归一化、create 前取消 checkpoint、durable queued record、create 后 submit 前取消桥接、后台 executor submit。
- 新增私有 `_run_upload_job(...)`，只委托 `FinsUploadRunner.run_upload(...)`；默认未装配 runner 时写入明确 failed terminal record，message 包含 `unsupported upload runtime`，不执行真实上传、文件读取或仓储写入。
- 扩展 job serialization/deserialization validation：upload record 必须 `source=None` 且 `source_kind` 非空。
- 上传 request summary 不保存本地文件路径，只保存业务字段与 `file_count`，避免把显式 request 字段藏进 extra payload 或把路径写进 job record。
- 补充 runtime tests：queued upload job persistence、ticker normalization、create-before-submit cancellation、unsupported upload terminal failure、bounded request/result summary、`SourceKind` discrimination、upload record serialization validation。

## Validation

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -q
```

Result: passed, `35 passed, 3 warnings in 1.54s`. Warnings are existing `edgar` deprecation warnings.

```bash
source .venv/bin/activate && pyright
```

Result: passed, `0 errors, 0 warnings, 0 informations`. Pyright reported only an available version update notice.

```bash
git diff --check
```

Result: passed, no output.

```bash
git status --short
```

Result:

```text
 M dayu/fins/README.md
 M dayu/fins/ingestion_runtime.py
 M docs/host/issues-implementation-control.md
 M tests/README.md
 M tests/fins/test_fins_ingestion_runtime.py
?? docs/reviews/wu-tools-01-f01-03-slice1-implementation-codex.md
```

`docs/host/issues-implementation-control.md` 是 pre-existing controller-owned dirty file，本次未修改。

## README Decision

- `dayu/fins/README.md`: updated. 当前代码已新增 `start_upload` direct runtime contract、upload request/result/runner 边界和默认 unsupported terminal behavior；这些属于 Fins README 的当前 capability / public interface / state machine 事实范围。
- `tests/README.md`: updated. 当前 `tests/fins/test_fins_ingestion_runtime.py` 覆盖范围已新增 upload runtime contract、SourceKind 分流、unsupported failure 和 bounded summary，属于 tests README 的当前测试结构事实范围。
- 未更新 `dayu/config/README.md`：Slice 1 未修改 config 或 tool discovery provider。
- 未更新 `dayu/README.md`：Slice 1 未改变跨层装配、Service / Host / Engine 边界或用户可见 tool capability；upload 仍不是 awaiting tool。

## Residual Risks

| Risk | Classification | Owner / Destination | Notes |
|---|---|---|---|
| Production upload workflow 尚未接入，默认 upload runner absent 会失败终态。 | covered by later approved slice | WU-TOOLS-01-F01-03 Slice 4 | 当前 Slice 只建立 runner boundary 与 job lifecycle。 |
| Upload awaiting tool/provider/wait adapter 尚未接入。 | covered by later approved slice | WU-TOOLS-01-F01-03 Slice 5 | 当前 Slice 不暴露 upload tool，不改 Host / Engine。 |
| `start_upload` 已引入，需要纳入 Issue 129 prepare / activate tracking。 | tracked by existing issue | GitHub Issue 129 / controller authorization | 本轮明确禁止修改 GitHub Issue；后续 closeout 需由 controller/user 授权处理。 |
| 当前 daemon-thread Fins job crash recovery 仍可能留下非终态 job。 | tracked by existing issue | Issue 129 and WU-WAIT-02 / Issue 90 | 当前 Slice 未引入私有 Host-like state machine。 |
| External job physical cancel/revoke 不保证。 | tracked by existing issue | WU-WAIT-03 / Issue 92 | 当前 Slice 只提供 cooperative cancellation checker。 |

无 unclassified residual risk。

## Files Modified By Codex

- `dayu/fins/ingestion_runtime.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `dayu/fins/README.md`
- `tests/README.md`
- `docs/reviews/wu-tools-01-f01-03-slice1-implementation-codex.md`

## Completion Status

Slice 1 implementation complete. Per user instruction, stopped before code review / fix / commit / push / PR gates.
