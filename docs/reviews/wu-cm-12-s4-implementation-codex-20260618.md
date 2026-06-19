# WU-CM-12 Slice S4 Implementation

## 改动

- 在 proactive normal `run_compaction_operation` 无 accepted candidate 后、写 `CONTEXT_COMPACTION_FAILED` 前，插入 bounded tier 1-3 recovery loop。
- Tier 1 使用 `fallback_selected_recent_window_item_cap` / `fallback_selected_recent_window_char_cap` 重建 compact input；selection 支持 strict item cap，并在 strict cap miss 后 whole-drop 后续候选，避免用更晚小块绕过 caps。
- Tier 2 增加 previous compacted view whole-drop degrade helper，固定优先级为 evidence-backed facts、reference continuity、answer anchors、forward intents、session summary；保留项不截断、不改写、不合成。
- Tier 3 使用同一 bounded selected delta，但传入空 `previous_compacted_view`，形成 delta-only compact input。
- Accepted recovery output 仍通过既有 `_append_compacted_event` 写 `CONTEXT_COMPACTED`；所有 tier 失败后仍只写一次既有 `CONTEXT_COMPACTION_FAILED` 并进入 tier 4/5 dispatch fallback。
- 扩展 proactive durable cancellation token，使其同时检查 Run 状态、input cursor、Session 缺失/关闭；commit transaction 前也重新检查 Session open 状态。
- MiMo review fix：recovery accepted 复用同一个 operation anchor 时，`accepted_attempt_number` 改为 normal 已完成 proposal attempts + 已失败 recovery proposal attempts + 当前 accepted tier attempt 的全局序号；cancellation-before-attempt 不计入已完成 proposal call。

## 测试覆盖

- Tier 1：normal fail 后 tier 1 accepted，断言 fallback caps 选择结果并写当前 Run 的 `CONTEXT_COMPACTED`，且 `accepted_attempt_number=2`。
- Tier 2：tier 1 fail 后 tier 2 accepted，断言 previous view 只保留最高优先级 section 且文本 byte-exact，且 `accepted_attempt_number=3`。
- Tier 3：tier 1/2 fail 后 tier 3 accepted，断言 previous view 为空且 delta material 保留，且 `accepted_attempt_number=4`。
- Stale guards：覆盖 recovery tier attempt 前 stale、tier proposal 执行期间 stale；既有 normal stale commit 测试继续覆盖 commit 前 recheck 不写 `CONTEXT_COMPACTED`。
- All tiers fail：断言只为当前 Run 写入 0 个 `CONTEXT_COMPACTED`，写一次 failed 并进入既有 dispatch fallback。
- Compact material helper：覆盖 strict fallback item cap、char cap 不绕序，以及 section-aware degrade 的 deterministic keep/drop；补充同一最高优先级 section 全部带 `eventlog-seq:<n>` source refs 时按最大 source sequence 降序，且文本 byte-exact。

## 验证

- `source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py tests/host/test_compaction_operation.py tests/host/test_compact_material.py -q`
  - 结果：`166 passed`
- `source .venv/bin/activate && pyright dayu/host/dispatch.py dayu/host/compact_material.py dayu/host/compaction.py tests/host/test_dispatch_scheduler.py tests/host/test_compaction_operation.py tests/host/test_compact_material.py`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过

## README 决策

- 已检查 `dayu/host/README.md` 的 Agent 更新约束与 `tests/README.md` 的 README 更新边界。
- 本次改动是 Host 内部 proactive compact recovery 与对应测试，不改变 Host public API、Engine contract、测试层级、测试运行方式或 README 面向的稳定开发接口；因此不更新 README。

## Residual Risk

- 本 slice 只闭环 proactive recovery。Reactive recovery 未扩展；execution replacement guard 对 proactive 无 execution id 可比对，未引入 reactive scope。
- Tier failure proposal 未写入 tier 专属 durable metadata，也未新增 durable payload 字段；failed event 的 schema 与 tier 4/5 fallback 保持既有形状。
