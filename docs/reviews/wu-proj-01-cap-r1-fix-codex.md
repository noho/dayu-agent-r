# WU-PROJ-01 CAP-R1 Fix - AgentCodex

## Gate

- Work unit: `WU-PROJ-01`
- PR: `#136`
- Gate: `CAP-R1 fix`
- Artifact path: `docs/reviews/wu-proj-01-cap-r1-fix-codex.md`
- Scope: 只处理 Controller accepted findings 中的 compaction evidence query 固定截断与 stale `_bounded_query_text` 命名；不进入 re-review、commit、push、PR 或 merge。

## 修改摘要

- `dayu/host/compaction_evidence.py`
  - 删除 selected compaction evidence query 的旧固定字符截断常量 `_READABLE_QUERY_TEXT_MAX_CHARS` / `_READABLE_QUERY_TRUNCATED_MARKER`。
  - 将 `_bounded_query_text` 改为 `_normalized_query_text`，只做规范化与空值校验，完整保留 semantic query / normalized arguments query。
  - 复用 `compact_material.normalized_material_text`，使 selected compaction evidence 与 pre-dispatch compact material query 规范化语义同源。
- `dayu/host/compact_material.py`
  - 将已不再截断的 `_bounded_query_text` 重命名为 `_normalized_query_text`，调用点同步更新，不保留兼容 alias / wrapper。
  - limited-signal query helper docstring 从“有界”调整为“规范化”。
- `tests/host/test_compaction_operation.py`
  - 新增 `test_evidence_input_semantic_query_text_is_not_truncated`，证明 selected compaction evidence 的 semantic query 超过旧 1200 字符时完整保留，且不追加 `[truncated_query_text]`。

## 直接证据

- 总控文档 `docs/host/issues-implementation-control.md` 中 `WU-PROJ-01-CAP-R1` 明确 accepted fix：当前 PR 必须移除 `dayu/host/compaction_evidence.py` query text fixed-character truncation，并清理 stale `_bounded_query_text` 命名；ordinary RunInput accepted evidence selection cap 不在 CAP-R1 scope。
- 设计真源 `docs/host/design.md` 的 compact material 输入边界要求 compaction request data block 是 Host 对 latest compacted view、post-compact delta material 与 current input anchor 的去重、分段、可读投影；`evidence_material` 渲染 accepted tool evidence block，LLM-facing evidence material 应提供业务可读 tool / query / response / source text，而不是内部治理账本或 lossy preview。
- 代码核对结果：
  - `dayu/host/compaction_evidence.py` 当前不再定义 `_READABLE_QUERY_TEXT_MAX_CHARS` / `_READABLE_QUERY_TRUNCATED_MARKER`。
  - `dayu/host/compaction_evidence.py` 的 semantic query 与 arguments query 均进入 `_normalized_query_text`。
  - `dayu/host/compact_material.py` 的 pre-dispatch query helper 也统一为 `_normalized_query_text`。
  - `rg` 检查生产代码中不再存在 `_bounded_query_text` 或旧 query truncation 常量 / marker。

## 验证结果

- `source .venv/bin/activate && python -m pytest tests/host/test_compaction_operation.py::test_evidence_input_semantic_query_text_is_not_truncated tests/host/test_compact_material.py::test_pre_dispatch_evidence_query_text_is_not_truncated`
  - 结果：2 passed。
- `source .venv/bin/activate && python -m pytest tests/host/test_compaction_operation.py tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py tests/host/test_memory_repair.py tests/host/test_open_host_runtime.py`
  - 结果：173 passed。
- `source .venv/bin/activate && pyright`
  - 结果：0 errors, 0 warnings, 0 informations。
  - 备注：pyright 输出新版可用提示 `v1.1.409 -> v1.1.410`，不影响本次类型检查结果。
- `git diff --check`
  - 结果：通过，无 whitespace error。

## README 判断

- 已读取 `dayu/host/README.md` 的 `Agent更新约束【必须遵守】`。
  - 本次没有改变 Host public API、公共契约、状态机、事件流或稳定开发接口，只修正 compact evidence query material 的内部 helper 语义与测试覆盖；不属于该 README 职责范围，无需更新。
- 已读取 `tests/README.md`。
  - 现有 `tests/host/` P12.6 memory semantic smoke 描述已覆盖 `test_compaction_operation.py` 对 accepted evidence query_text 消费 durable tool-call request atoms 的测试族；本次只补同族防回归 case，无需新增测试分层说明。

## 剩余风险

- fixed in current slice：selected compaction evidence semantic query 的旧 1200 字符截断与 truncated marker 已移除，并由新增测试覆盖。
- fixed in current slice：`compact_material.py` 与 `compaction_evidence.py` 中 stale `_bounded_query_text` 命名已清理，未保留 alias / wrapper。
- assigned to later work unit：`WU-PROJ-01-S3-R1` 与 `WU-PROJ-01-S4-R1` 仍按总控文档保留为后续 gate，不在 CAP-R1 fix scope。
- no new issue required：本轮不修改 ordinary RunInput accepted evidence 数量选择上限、不重设计 context budget 或 selection policy。

## 完成状态

- CAP-R1 accepted findings 的 fix implementation 已完成。
- 已按要求完成测试、pyright 与 diff check。
- 本轮未 commit、未 push、未创建或修改 PR、未进入 re-review。
