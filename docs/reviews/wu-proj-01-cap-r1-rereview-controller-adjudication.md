# WU-PROJ-01-CAP-R1 Re-Review Controller Adjudication

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: CAP-R1 re-review
- Date: 2026-06-11
- Controller: Phaseflow
- Review artifacts:
  - `docs/reviews/wu-proj-01-cap-r1-rereview-mimo.md`
  - `docs/reviews/wu-proj-01-cap-r1-rereview-ds.md`

## 结论

CAP-R1 re-review accepted。

AgentMiMo 与 AgentDS 均裁决 `PASS`，无 blocking findings，无非阻塞 findings。总控接受该结论。

## 关闭依据

- `dayu/host/compact_material.py` 删除 pre-dispatch source builder 的 query truncation、delta event cap 与 evidence block cap；post-compact delta 读取不再有固定 `LIMIT`。
- `dayu/host/compaction_evidence.py` 删除 selected compaction evidence query 的固定字符截断；`readable_query_text` 只做规范化与空值校验，完整保留 semantic query / arguments query。
- `dayu/host/dispatch.py` required catch-up 与 rebuild correctness 路径传 `budget=None`，不再由固定 batch / scanned event budget 提前截断。
- `dayu/host/open_host.py` 与 `dayu/host/dispatch.py` 剩余 one-batch projection 行为已明确命名为 opportunistic non-correctness catch-up。
- `_bounded_query_text` stale 命名已清理为 `_normalized_query_text`，未保留兼容 alias / wrapper。
- ordinary RunInput accepted evidence selection cap 未被修改，符合 CAP-R1 非目标。

## 验证

总控复验：

- `python -m pytest tests/host/test_compaction_operation.py tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py tests/host/test_memory_repair.py tests/host/test_open_host_runtime.py` -> 173 passed
- `pyright` -> 0 errors
- `git diff --check` -> passed

## 后续

`WU-PROJ-01-CAP-R1` 从 active residual risk 表移除。`WU-PROJ-01-S3-R1` 与 `WU-PROJ-01-S4-R1` 仍需当前 PR 后续 gate 重新裁决和实施。
