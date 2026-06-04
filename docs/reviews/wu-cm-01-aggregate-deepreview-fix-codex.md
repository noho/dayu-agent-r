# WU-CM-01 Aggregate DeepReview Fix - Codex

## Gate

- Work unit: WU-CM-01
- Gate: aggregate deepreview fix
- Scope: 仅修复 controller adjudication 中 accepted findings。
- Artifact path: `docs/reviews/wu-cm-01-aggregate-deepreview-fix-codex.md`

## 修复摘要

### F-1 根 README 残留旧术语

状态：已修复。

修复内容：
- 将根 `README.md` 中 memory capability 描述从 `working memory / episode summary` 改为已落地的五类 session memory：Trace、Evidence / Fact、Session Summary、Answer Anchor、Forward Intent。
- 未改动其它用户手册内容。

### F-2 `run_input.py` compact artifact message path 旧 payload reader

状态：已修复。

修复内容：
- 删除旧 compact payload reader：`_optional_summary_text_from_compacted_payload`、`_preserved_fact_refs_summary`、`_preserved_canonical_evidence_refs`。
- 删除相关旧字段常量：`episode_summary_candidate`、`candidate_id`、`goal`、`open_questions`、`user_constraints`、`preserved_fact_refs`、`canonical_evidence_refs`、`evidence_backed_fact_refs`。
- 新增 vNext-aware reader，只读取 `accepted_candidate` 与 `accepted_evidence_mapping_refs`。
- `CompactArtifactView.represented_evidence_refs` 改为来自 `accepted_evidence_mapping_refs`，与 accepted evidence 去重语义同源；不读取 prompt-local `evidence_labels` 作为 canonical refs。
- compact artifact SystemMessage 改为渲染 vNext accepted candidate 摘要与 accepted evidence mapping refs，不再渲染旧 `episode_summary` / `preserved_fact_refs` 文案。
- 更新 `tests/host/test_run_input_builder.py` 覆盖 vNext reader。

### F-3 `test_public_compact_smoke.py` `evidence_input` 命名残留

状态：已修复。

修复内容：
- 将测试变量名、docstring 与 AssertionError 文案中的 `evidence_input` 改为 `evidence_material`。
- 保持 JSON key 为当前契约 `evidence_material`。

## 验证

已执行：

```bash
source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_public_compact_smoke.py -q
```

结果：`47 passed, 1 skipped in 1.08s`。

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。

```bash
git diff --check
```

结果：无输出。

## README 决策

- 根 `README.md` 已按 F-1 更新。
- `dayu/host/README.md` 未更新：本次只清理内部 compact artifact reader 和测试命名，不改变 Host public contract、公共接口、状态机、事件流或扩展点说明。

## 未覆盖风险

- fixed in current slice：accepted findings F-1、F-2、F-3 均已在当前 fix 中处理。
- assigned to controller rejected findings：`context_events.py` 旧字段 fail-closed 常量与 `ForwardIntentTypeVNext.OPEN_QUESTION` 按 controller adjudication 为 rejected findings，本轮未修改。
- residual risk：本轮未执行额外 re-review；按用户要求不进入 re-review gate。

## 完成状态

aggregate deepreview fix 已完成；未 commit、未 push、未开 PR、未 merge。
