# P12.6 Slice 3 Implementation Artifact

## 动机判断

Slice 3 动机成立。`docs/host/design.md` §24 / §25 已明确 accepted evidence envelope 只是 provenance anchor，不得作为 evidence 内容容器；raw evidence 必须来自 `TOOL_RESULT_ACCEPTED` canonical fact 引用的 payload / descriptor，并做 digest / descriptor 校验。当前 Slice 1/2 产物已经建立 material pack 与 segment selection，但 evidence reader 仍需要 selected block ref、raw payload 校验、chunk provenance 与 evidence-only map 的硬化。

## 改动文件

- `dayu/host/compaction_evidence.py`
- `dayu/host/payload_resolution.py`
- `dayu/host/compact_material.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_toolruntime_accept_barrier.py`
- `tests/host/test_compact_material.py`

未修改 `docs/host/implementation-control.md`；该文件进入任务前已有 dirty diff。

## 实现摘要

- 新增 `SelectedEvidenceBlockRef` 与 `collect_selected_compaction_request_evidence_inputs(...)`，按 selected evidence block refs 精确读取 `TOOL_RESULT_ACCEPTED`，并校验 Session、event class 与 event type。
- 新增 `event_payload_object_for_result_ref(...)`，在 payload descriptor 路径上校验 EventLog payload ref / digest 与 accepted result ref 一致，再读取 JSON object。
- raw evidence material 只从 `raw_tool_outcome` 序列化生成；`accepted_evidence_envelope` 只提供 evidence id、tool call metadata、source / locator metadata 和 payload refs。
- selected raw reader 遇到缺失 raw payload、payload digest mismatch、producer mismatch 或 `result_preview` 字段时 fail closed，不做 preview fallback。
- `compact_material.py` 增加 deterministic evidence chunking，单 evidence 超过 `EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS` 时输出 `E1.1` / `E1.2`，provenance 继续指向同一个 canonical accepted evidence id，并记录 `chunk_parent_label` / `chunk_ordinal`。
- 新增 `prompt_local_evidence_map(...)` evidence-only typed view 校验，确保 evidence label 映射包含 canonical accepted evidence id、tool result event、tool call event、payload / artifact refs。

## 测试结果

- `source .venv/bin/activate && pytest tests/host/test_compaction_operation.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_compact_material.py -q`
  - 结果：48 passed
- `source .venv/bin/activate && python -m pyright dayu/host/compaction_evidence.py dayu/host/evidence.py dayu/host/payload_resolution.py dayu/host/compact_material.py tests/host/test_compaction_operation.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_compact_material.py`
  - 结果：0 errors
- `git diff --check`
  - 结果：pass

## README 是否更新

未更新 README。已检查 `dayu/host/README.md` 与 `tests/README.md`：本次变更是 Host 内部 compaction evidence reader、material provenance 与既有 Host 测试覆盖增强，不改变 public contract、运行命令、测试层级或 README 中的稳定说明。

## 风险与未覆盖项

- `dispatch.py` / `engine_ingest.py` 仍保留 Slice 1 初始 request wiring，对旧 range collector 的调用未在本 slice 修改；这两个文件不在本次允许修改清单内，按实施计划由 Slice 5 接线到 selected material / frozen overflow list。
- Artifact descriptor payload 仍按现有 `payload_resolution` fail closed；若后续需要从 artifact descriptor 重建 raw evidence，需要 Controller 做 storage/design 裁决。
- Host 仍不解析财报业务 locator semantics；source / locator refs 只作为 opaque metadata 进入 provenance map。
