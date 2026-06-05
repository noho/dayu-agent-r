# WU-CM-01 PR Review - Controller Adjudication

## 裁决

- Gate: WU-CM-01 PR review
- PR: https://github.com/noho/dayu-agent-r/pull/116
- Verdict: fix required
- Review artifacts:
  - `docs/reviews/wu-cm-01-pr-review-mimo.md`
  - `docs/reviews/wu-cm-01-pr-review-ds.md`
- Next gate: PR review fix

MiMo 给出 PASS，仅 low / info findings。DS 给出 PASS 但列出 2 个 Medium 与若干 Low / Info findings。Controller 从第一性原理复核后，接受其中会造成 contract drift、错误 repair reason 或 README / design 真源不同步的事项进入当前 PR fix gate；其余质量建议不阻塞当前 draft PR gate，记录 owner 后 defer。

## Accepted Findings

### F-1 `_PAYLOAD_FIELD_DISPLAY_TEXT` 重复定义

- 来源：MiMo F-1 / DS F-1。
- 文件：`dayu/host/memory.py`。
- 裁决：accepted。

同一模块内重复定义同值常量虽不影响运行，但属于明确维护缺陷，当前 fix 可用单行删除关闭。

### F-2 `previous_compacted_view` 只渲染 facts，未渲染五类 stable view

- 来源：DS F-2 / F-4。
- 文件：`dayu/host/compact_material.py`，测试 `tests/host/test_compact_material.py`。
- 裁决：accepted。

设计真源要求 `previous_compacted_view` 包含上一轮 accepted compacted view 的 session summary、accepted evidence-backed facts、answer anchors、forward intents 与 reference continuity items。当前 material pack 已从 snapshot 构造五类 stable block，但 `_previous_compacted_view_vnext()` 只映射 facts，其余四类被丢弃。这是 compact input contract 映射缺口，不应通过降级设计来掩盖。

### F-3 `USER_VISIBLE_RUN_STATE` trace block 未进入 vNext trace material

- 来源：DS F-3。
- 文件：`dayu/host/compact_material.py`，测试 `tests/host/test_compact_material.py`。
- 裁决：accepted。

设计真源要求 `trace_material` 包含用户输入、助手最终回答和用户可见 Run 状态。当前 `_trace_material_vnext()` 只映射 `USER_INPUT`。`ASSISTANT_FINAL_ANSWER` 当前由 `_ordinary_section_for_kind()` 路由到 `ANSWER_MATERIAL`，本轮不要求双路重复；但 `USER_VISIBLE_RUN_STATE` 没有其它 vNext 渲染路径，必须映射到 trace material。

### F-4 `dayu/config/README.md` 未列出 vNext memory policy 字段

- 来源：DS F-5。
- 文件：`dayu/config/README.md`。
- 裁决：accepted。

`execution_profiles.json` 已落地完整 `memory_projection_policy` 字段集合。配置 README 只写 semantic group，不足以作为配置说明手册。当前 fix 应补充字段列表，保持与已落地接口一致，不写未来计划。

### F-5 `_required_text()` 死代码

- 来源：DS F-9。
- 文件：`dayu/host/compact_material.py`。
- 裁决：accepted。

`_required_text()` 在调用 `_require_non_empty_text()` 后再检查 `None`，该分支不可达。当前 fix 应删除死代码并收紧签名或等价简化，避免类型语义误导。

### F-6 inline delta repair view 缺失时使用错误 repair reason

- 来源：DS F-10。
- 文件：`dayu/host/memory.py`、`dayu/host/compact_material.py`，必要时更新 dispatch / tests。
- 裁决：accepted。

当 lag 未超过 inline 阈值但 `inline_delta_repair_view is None` 时，当前代码使用 `SNAPSHOT_LAG_OVER_THRESHOLD`。该 reason 与实际原因不符，并可能误导下游 recovery / rebuild 策略。当前 fix 应引入或复用准确的 `MemoryRepairReason` 语义，更新对应测试，避免把“view 未提供”伪装成“大滞后”。

### F-7 `TraceMemoryView` 设计真源字段 drift

- 来源：DS Residual Risk。
- 文件：`docs/host/design.md`。
- 裁决：accepted。

设计真源 24.4 中 `TraceMemoryView` 仍写 `reference_continuity_items`，但当前 vNext memory projection 的 `TraceMemoryView` 是 `selected_recent_window`；reference continuity 已由独立 memory section 表达。当前 fix 应同步设计真源，避免 design source 与代码 contract 不一致。

## Deferred Findings

### D-1 `memory.py` / `context_fallback.py` 缺少 `__all__`

- 来源：MiMo F-2 / DS F-6。
- 裁决：deferred-with-owner。
- Owner / Destination：WU-CM-01 post-PR cleanup 或后续 Host public surface hardening。

`__all__` 是导出审计优化，不是当前 PR correctness、contract 或 schema 阻塞项。

### D-2 `compaction_operation.py` string category / decision 可改 enum

- 来源：DS F-7。
- 裁决：deferred-with-owner。
- Owner / Destination：后续 compact operation typed cleanup。

当前字段由模块内常量集中写入，review 未给出错误数据路径；改 enum 会扩大 API 面，当前 PR fix 不处理。

### D-3 `_empty_string_tuple()` 可简化

- 来源：DS F-8。
- 裁决：rejected-with-reason。

该 helper 明确表达 dataclass tuple default 语义，且无行为风险；不为语法偏好触发改动。

### D-4 slice1 诊断常量命名

- 来源：MiMo F-3。
- 裁决：deferred-with-owner。
- Owner / Destination：后续诊断字符串清理。

常量为 module-private 诊断值，不影响外部 contract。

### D-5 large evidence chunk、repair 集成测试、quality gate 拒绝路径、fallback path 与并发矩阵

- 来源：DS residual risks。
- 裁决：deferred-with-owner。
- Owner / Destination：GitHub Issue 80 / Conversation Memory evaluation 与后续 Host test hardening。

这些是覆盖增强和评测问题，不构成当前 PR 主路径 correctness blocker。当前 PR 已覆盖 public smoke、memory projection、durable schema、run input、dispatch、engine ingest 与 full host suite。

## Required Fix Validation

```bash
source .venv/bin/activate
pytest tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py -q
pytest tests/service/test_host_assembly.py tests/runtime/test_config_loader.py -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

若 fix 修改 dispatch repair branching，追加相关 dispatch scheduler tests。若 fix 修改 compact input contract，测试必须断言五类 previous compacted view 与 `USER_VISIBLE_RUN_STATE` trace material。
