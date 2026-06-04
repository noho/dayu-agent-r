# WU-CM-01 Aggregate DeepReview - Controller Adjudication

## 裁决

- Gate: WU-CM-01 aggregate deepreview
- Verdict: fix required
- Review artifacts:
  - `docs/reviews/wu-cm-01-aggregate-deepreview-mimo.md`
  - `docs/reviews/wu-cm-01-aggregate-deepreview-ds.md`
- Next gate: aggregate deepreview fix

Aggregate deepreview 主体通过。MiMo 无 blocking finding；DS 标记 3 个 medium finding。Controller 接受其中 3 个作为当前 fix gate 事项，以消除文档旧术语、旧 compact artifact reader 残留和测试命名 drift。

## Accepted Findings

### F-1 根 README 残留旧术语

- 来源：DS Finding 1。
- 文件：`README.md`。
- 裁决：accepted。

根 README 的 memory capability 描述仍包含 `working memory` / `episode summary`，与 vNext 五类 session memory 不一致。必须改为当前已落地事实，避免新旧术语并存。

### F-2 `run_input.py` compact artifact message path 旧 payload reader

- 来源：DS Finding 2，MiMo Slice C Advisory-1。
- 文件：`dayu/host/run_input.py`，必要时补 `tests/host/test_run_input_builder.py`。
- 裁决：accepted。

旧 reader 对 vNext payload 无害但属于旧 compact payload mental model 残留；此前 deferred owner 不够具体。当前 fix gate 直接清理：删除或替换 `_optional_summary_text_from_compacted_payload`、`_preserved_fact_refs_summary`、`_preserved_canonical_evidence_refs` 及相关旧 field constants，改为 vNext-aware compact artifact message reader。不得恢复旧 field alias，也不得兼容读取旧 payload。

### F-3 `test_public_compact_smoke.py` `evidence_input` 命名残留

- 来源：DS Finding 3。
- 文件：`tests/host/test_public_compact_smoke.py`。
- 裁决：accepted。

测试实际读取 vNext `evidence_material`，但变量名、docstring 与 error message 仍写 `evidence_input`。必须改为 `evidence_material`，避免旧 compact material contract 术语残留。

## Rejected Findings

### F-4 `context_events.py` 旧字段常量

- 来源：DS Finding 4 / MiMo INFO。
- 裁决：rejected-with-reason。

这些私有常量只用于 fail-closed 拒绝旧 payload 字段，且由测试覆盖；不是兼容读取或 re-export。保留作为 schema 防守层。

### F-5 `ForwardIntentTypeVNext.OPEN_QUESTION`

- 来源：DS Finding 5。
- 裁决：rejected-with-reason。

`open_question` 是 vNext Forward Intent 的合法枚举值，不是旧 block kind 兼容残留。

## Required Fix Validation

```bash
source .venv/bin/activate
pytest tests/host/test_run_input_builder.py tests/host/test_public_compact_smoke.py -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

若 `run_input.py` reader 修改影响更多 prompt assembly 行为，追加相关 Host tests。
