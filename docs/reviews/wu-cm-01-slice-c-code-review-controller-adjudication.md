# WU-CM-01 Slice C Code Review - Controller Adjudication

## 裁决

- Gate: WU-CM-01 Slice C code review
- Verdict: fix required
- Review artifacts:
  - `docs/reviews/wu-cm-01-slice-c-code-review-mimo.md`
  - `docs/reviews/wu-cm-01-slice-c-code-review-ds.md`
- Next gate: WU-CM-01 Slice C fix

Slice C implementation 主体方向可进入 fix gate。两路 reviewer 均确认 vNext policy / snapshot / durable schema / prompt assembly / config-service / README 同步整体对齐设计真源，且 required tests 与 pyright 已复现通过。但 DS F-1 是真实 contract bug，必须修复后才能进入 re-review。

## Accepted Findings

### Accepted F-1: `context_window_size` 参数被 Service assembly 丢弃

- 来源：DS F-1。
- 严重性：blocking。
- 文件：`dayu/service/host_assembly.py`。
- 裁决：accepted。

`_memory_projection_policy_from_config` 接收的 `context_window_size` 参数来自 effective model config；设计真源要求 Service / composition root 把 effective model 的 `context_window_tokens` 作为 Host `MemoryProjectionPolicy.context_window_size`。当前实现使用 `policy.context_window_size`，静默丢弃 model-derived 参数，与 `docs/host/design.md` 冲突。必须改为使用函数参数，并补 service assembly 测试覆盖 profile policy context window 与 model context window 不同时的映射。

### Accepted F-2: `DuplicateMaterialSectionOwnerError` dedicated 覆盖丢失

- 来源：DS F-2。
- 严重性：medium test coverage。
- 文件：`tests/host/test_compact_material.py`。
- 裁决：accepted。

Production guard `_raise_on_duplicate_section_owner` 仍存在，旧 dedicated unit test 被替换为 vNext bridge 测试后缺少直接覆盖。必须补一个 vNext-relevant duplicate section owner test，验证同一 canonical source refs + content digest 进入两个 LLM-facing section 时仍 raise `DuplicateMaterialSectionOwnerError`。

### Accepted F-3: vNext budget limiting 缺少直接单测

- 来源：MiMo Advisory-2。
- 严重性：medium test coverage。
- 文件：`tests/host/test_memory_projection.py`。
- 裁决：accepted。

旧 budget tests 随旧 memory 概念删除后，新 `_limit_facts` / reference / anchor / intent 路径缺少直接覆盖。至少补一个 focused vNext projection test，断言 per-section cap 超限时会截断并记录 `BUDGET_LIMIT_REACHED` diagnostic。优先覆盖 facts；如实现代价低，可同时覆盖 reference continuity。

## Rejected / Deferred Findings

### Deferred: compact artifact message path 旧 payload reader

- 来源：MiMo Advisory-1。
- 裁决：deferred-with-owner。
- Owner / Destination：后续 RunInput / compact artifact cleanup slice。

当前旧 reader 对 vNext payload 缺字段时返回空值，不导致错误行为；本 Slice C fix gate 优先关闭 correctness bug 与测试覆盖缺口。后续可替换为 vNext-aware compact artifact message reader，但不阻塞当前 Slice C acceptance。

### Rejected: `_memory_messages` `del policy` cleanup

- 来源：DS F-3。
- 裁决：rejected-with-reason。

这是低价值清理，不影响 behavior / contract / tests。当前 fix gate 不扩大到接口清理。

### Rejected: `_snapshot_with_goal` helper API cleanup

- 来源：DS F-4。
- 裁决：rejected-with-reason。

这是测试可读性清理。若 F-2 duplicate coverage fix 需要调整该 helper，可顺手简化；否则不作为独立 accepted finding。

### Rejected: old schema_version explicit rejection message

- 来源：DS F-5。
- 裁决：rejected-with-reason。

当前 schema 规则按 fresh schema 起库处理，old snapshot 缺 vNext required keys fail closed 已足够，不要求兼容或专门错误信息。

## Required Fix Validation

Fix gate 至少运行：

```bash
source .venv/bin/activate
pytest tests/service/test_host_assembly.py tests/host/test_compact_material.py tests/host/test_memory_projection.py -q
python -m pyright dayu/ tests/ utils/
```

若修改 compact material 或 memory projection helper 触发相关批次，追加实现 artifact 中已列的 affected pytest 批次。
