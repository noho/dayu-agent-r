# WU-CM-01 Aggregate DeepReview Re-Review - Controller Adjudication

## 裁决

- Gate: WU-CM-01 aggregate deepreview re-review
- Verdict: PASS
- Review artifacts:
  - `docs/reviews/wu-cm-01-aggregate-rereview-mimo.md`
  - `docs/reviews/wu-cm-01-aggregate-rereview-ds.md`
- Fix artifact: `docs/reviews/wu-cm-01-aggregate-deepreview-fix-codex.md`
- Next gate: accepted deepreview commit

MiMo 与 DS 均确认 controller adjudication 中 3 个 accepted findings 已完成修复，且未引入违反设计真源、AGENTS.md 或 vNext contract 的新问题。

## Accepted Findings Closure

### F-1 根 README 残留旧术语

- 裁决：closed。
- 证据：`README.md` 已移除 `working memory` / `episode summary` 旧术语，改为当前已落地的五类 session memory：Trace、Evidence / Fact、Session Summary、Answer Anchor、Forward Intent。

### F-2 `run_input.py` compact artifact message path 旧 payload reader

- 裁决：closed。
- 证据：旧 reader 与旧 field constants 已删除；compact artifact message path 只读取 vNext `accepted_candidate` 与 `accepted_evidence_mapping_refs`，非法或旧 payload fail-closed，不保留旧 field alias。

### F-3 `test_public_compact_smoke.py` `evidence_input` 命名残留

- 裁决：closed。
- 证据：测试变量名、docstring 与 error message 已统一为 `evidence_material`，测试逻辑仍读取 vNext `evidence_material`。

## Rejected Findings Scope Check

- F-4 `context_events.py` 旧字段常量：保持 rejected-with-reason，未修改。
- F-5 `ForwardIntentTypeVNext.OPEN_QUESTION`：保持 rejected-with-reason，未修改。

## Required Validation

MiMo 与 DS re-review artifacts 均记录以下验证通过：

```bash
source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_public_compact_smoke.py -q
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
git diff --check
```

Controller 将在 accepted deepreview commit 前重复运行上述验证。

## Residual Risks

- 当前 aggregate accepted findings 无 residual risk。
- Rejected findings 已在 `docs/reviews/wu-cm-01-aggregate-deepreview-controller-adjudication.md` 记录裁决理由，不作为当前 work unit residual risk。
