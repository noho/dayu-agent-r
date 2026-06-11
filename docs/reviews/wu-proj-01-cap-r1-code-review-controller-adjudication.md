# WU-PROJ-01-CAP-R1 Code Review Controller Adjudication

## 元数据

- Work unit: `WU-PROJ-01`
- Review gate: CAP-R1 code review
- Date: 2026-06-11
- Controller: Phaseflow
- Review artifacts:
  - `docs/reviews/wu-proj-01-cap-r1-code-review-mimo.md`
  - `docs/reviews/wu-proj-01-cap-r1-code-review-ds.md`
  - `docs/reviews/wu-proj-01-cap-r1-implementation-codex.md`

## 总控裁决

CAP-R1 当前 implementation 不直接进入 accepted slice commit；进入 fix gate。

AgentMiMo 与 AgentDS 均确认 `compact_material.py` source builder 的 delta event cap、evidence block cap、query text truncation 已移除，`dispatch.py` required / rebuild projection correctness path 已改为 `budget=None`，after-commit / after-compact 只保留 opportunistic one-batch catch-up，且现有 focused tests 与 pyright 通过。

总控接受上述 PASS 部分。

## Accepted Findings

### CAP-R1-F1: `compaction_evidence.py` 剩余 query truncation 必须在当前 PR 修复

裁决：`accepted`

两路 review 均建议将 `dayu/host/compaction_evidence.py` 的 `_READABLE_QUERY_TEXT_MAX_CHARS` / `_READABLE_QUERY_TRUNCATED_MARKER` 判为 out of scope。总控不接受该 out-of-scope 建议。

理由：

- 用户点名质疑的是 `_READABLE_QUERY_TEXT_MAX_CHARS` 本身，而当前 production code 中仍存在同名常量与同名 truncation marker。
- `compaction_evidence.py` 虽然不是 `compact_material.py` pre-dispatch source builder，但它构造的是 selected evidence material 的 `readable_query_text`，会进入 compactor LLM 消费的 material input。
- Host 设计真源要求 compact material data block 是 latest accepted compacted view、post-compact delta material 与 current input anchor 的去重、分段、可读投影；长 material 应按 material block / evidence-block 内部分段处理，而不是用固定字符数截断 LLM-facing query metadata。
- 这不是把预算常量挪配置，也不是新增治理项；这是删除当前 PR 已经裁决为过度设计的同类 LLM-facing query truncation。

Fix 要求：

- 删除 `dayu/host/compaction_evidence.py` 的 `_READABLE_QUERY_TEXT_MAX_CHARS` 与 `_READABLE_QUERY_TRUNCATED_MARKER`。
- 让 selected compaction evidence query text 只做规范化与空值校验，不做固定字符截断，不追加 truncated marker。
- 补测试证明 selected compaction evidence semantic query 超过旧 1200 字符时完整保留。

### CAP-R1-F2: `_bounded_query_text` 命名残留必须同步清理

裁决：`accepted`

`compact_material.py` 中 `_bounded_query_text` 已不再 bounded；`compaction_evidence.py` 修复后也不应继续使用 bounded 命名。该命名会误导后续维护者以为这里仍有生产语义上限。

Fix 要求：

- 将相关 helper 重命名为表达规范化语义的名称，例如 `_normalized_query_text` 或 `_readable_query_text_from_text`。
- 不保留兼容 alias / wrapper。

## Rejected / Deferred Findings

### ordinary RunInput accepted evidence 数量上限

裁决：`rejected-with-reason` for CAP-R1

`dayu/host/run_input.py` 中 `_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT = 8` 是 ordinary dispatch bounded material selection 的规模上限，位于 ordinary RunInputBuilder 路径，不是本次 CAP-R1 点名的 compact source builder delta cap、compactor query truncation 或 projection catch-up correctness budget。

CAP-R1 fix 不扩大到该路径，避免把本次 bug fix 扩展成 ordinary prompt selection policy 重设计。

## 验证要求

AgentCodex fix 后必须至少运行：

- `python -m pytest tests/host/test_compaction_operation.py tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py tests/host/test_memory_repair.py tests/host/test_open_host_runtime.py`
- `pyright`
- `git diff --check`

若修改 `dayu/host/` 或 `tests/` 触发 README 检查，必须阅读对应 README 更新约束并记录是否需要更新。
