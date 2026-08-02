# S7/F07 Code Review Fix — Codex

## Gate 与边界

- Work unit：`WU-CLI-CONFORMANCE-F01-F07`
- Gate：S7/F07 code review fix loop
- PR：`190`
- Entry / current HEAD：`b8f87e3b09998ec764de9bbfa83e684e871c949c`
- 裁决真源：`wu-cli-conformance-f01-f07-s7-code-review-controller-adjudication.md`
- 状态：accepted finding 已修复并验证；停止在独立 re-review 前，不宣称 re-review 通过。

本轮只处理总控接受的 `C-001`、`C-002` 与 `M-R1/DS-1 accepted-in-part`。没有重开或修改已拒绝/关闭的 material enum、anchor schema、free-text `intent_type`/`reason`、single-attempt convenience API 或 typed exception refactor；没有增加 v1 fake、compatibility alias/default shim、loose parser 或 diagnostics-large operation fake。

## Finding closure

### C-001 — duplicate key repair feedback 泄密

结论：已在 strict LLM-output parser / repair-feedback owner 修复。

- `dayu/host/llm_compaction.py`
  - duplicate key 仍由 `object_pairs_hook` 在 JSON object 转成 dict 前严格拒绝。
  - duplicate key 的 raw key 不再进入 `json_path`；该 hook 不拥有父路径，因此使用稳定的根路径 `$`，由 `DUPLICATE_JSON_KEY` code 自解释失败类别。
  - parser report 的 `json_path` 与 `message` 均经过同一个 diagnostic redactor 与 240 字符上限，不增加 fallback reader。
- `dayu/host/context_governance.py`
  - repair feedback 的 `json_path`、`message`、每个 `source_label` 全部先脱敏再截断；脱敏后的 labels 再确定性去重。
  - 保留 32 issues、每字段 240 字符、整体 8192 字符边界；单 issue 的大量 labels 会从尾部确定性裁剪，不能绕过整体 cap。
  - validation code、attempt number 与固定 required action 不含 raw LLM 文本，继续作为自解释反馈。
- deterministic regression
  - `test_secret_bearing_duplicate_key_report_and_repair_feedback_are_safe` 使用同时包含 `api_key=sk-secret-123`、`token`、`Bearer`、`password` 的恶意 duplicate key，证明 strict reject、所有 secret 不出现在 report/feedback、字段与整体均 bounded。
  - `test_repair_feedback_is_separate_and_requires_whole_candidate` 对长 `json_path`、长 `message`、长 `source_labels` 分别验证脱敏和截断，且 immutable input 与 whole-candidate repair 语义不变。
  - `test_raw_parser_reject_is_semantic_repair_not_execution_retry` 证明 operation 收到的 previous report 同样 secret-safe，semantic repair 未伪装成 execution retry。

### C-002 — Memory policy cap 文档精度

结论：只修正文档陈述，不扩展产品策略。

- `docs/host/design.md`
- `docs/reviews/wu-cli-conformance-f01-f07-s7-implementation-codex.md`

两处现在精确描述实际 `MemoryProjectionPolicy`：session summary 使用字符上限；evidence facts、answer anchors、forward intents、reference continuity 各自使用 per-section item-count 与 aggregate-size 上限；Context Governance 与 Memory 复用同一 policy instance 和 `estimate_memory_size_units`。diagnostics 不属于 Memory semantic projection，因此不受 Memory policy cap，但仍受 strict shape 与 deterministic duplicate 校验。

### M-R1 / DS-1 accepted-in-part — fresh v2 owner tests

结论：只恢复总控点名的防御路径测试。

- `tests/host/test_compaction_operation.py`
  - `test_cancellation_after_attempt_one_failure_stops_before_attempt_two`：attempt 1 失败后、attempt 2 前收到 cancellation，第二次 prepare/run 均不发生，且无 accepted truth。
  - `test_accepted_result_missing_manifest_or_response_identity_fails_closed`：accepted result 缺 proposal manifest 或缺 successful response identity 均在 operation owner fail closed。
  - operation repair 测试额外证明 secret-bearing parser report 进入下一 attempt 前已脱敏。
- `tests/host/test_compact_pipeline.py`
  - `test_reactive_later_pass_failure_returns_no_partial_truth`：较早 pass 成功、较晚 pass 失败时不发布 partial truth，最终只有一个 failure result，所有 rejected attempts 保持 fresh v2 事实。

未恢复任何 v1 fake/fixture；diagnostics-only validity 继续由 accept-barrier owner test 覆盖，没有新增冗余的 diagnostics-large operation fake。

## 本 fix loop 的文件

Production：

- `dayu/host/llm_compaction.py`
- `dayu/host/context_governance.py`

Tests：

- `tests/host/test_llm_compaction.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_compact_pipeline.py`

Docs：

- `docs/host/design.md`
- `docs/reviews/wu-cli-conformance-f01-f07-s7-implementation-codex.md`
- `docs/reviews/wu-cli-conformance-f01-f07-s7-code-review-fix-codex.md`（本 artifact）

未修改 frozen registry、README、Engine production、CLI/Service production，也未 stage、commit、push 或操作 PR。当前较大的 unstaged diff 是同一个 S7 outer slice 的既有 implementation；本轮保留它且没有 checkout/reset/stash。

## 验证记录

### Focused owner validation

```text
pytest -q tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_compact_pipeline.py
43 passed in 0.36s

python -m pyright dayu/host/llm_compaction.py dayu/host/context_governance.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_compact_pipeline.py
0 errors, 0 warnings, 0 informations

ruff check <上述 production/tests>
All checks passed!
```

### Accepted plan §9 S7 matrix

精确运行 §9 列出的 15 个 test files：

```text
711 passed, 1 skipped, 3 warnings in 10.57s
```

skip 是既有 provider environment gate；三条 warning 均来自 `edgar` 依赖的 deprecation warning。

### Modified-production coverage

同一 15-file S7 matrix 对 14 个 S7 修改 production 文件逐文件计数：

| Production file | Coverage |
|---|---:|
| `dayu/host/compact_artifact.py` | 87% |
| `dayu/host/compact_material.py` | 85% |
| `dayu/host/compact_payload.py` | 88% |
| `dayu/host/compact_pipeline.py` | 93% |
| `dayu/host/compaction.py` | 83% |
| `dayu/host/compaction_operation.py` | 87% |
| `dayu/host/context_events.py` | 88% |
| `dayu/host/context_governance.py` | 89% |
| `dayu/host/dispatch.py` | 85% |
| `dayu/host/durable/memory.py` | 85% |
| `dayu/host/engine_ingest.py` | 89% |
| `dayu/host/llm_compaction.py` | 82% |
| `dayu/host/memory.py` | 90% |
| `dayu/host/run_input.py` | 86% |
| **TOTAL** | **87%** |

所有修改 production 单文件均 `>=80%`。

### Repository/static/integrity validation

```text
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations

ruff check <all changed Python files>
All checks passed!

python -m json.tool docs/cli_ci_oracles.json
PASS
python -m json.tool docs/cli_ci_scenarios.json
PASS

git diff --check
PASS
git diff --cached --name-only
<empty>
```

Fresh v2 active production/test/design scan（排除本轮明确禁止修改的 README）零命中。按 §9 原始路径包含 README 扫描时，只命中 `dayu/host/README.md:735` 的历史 v1 描述；它不是 active symbol/reader，且 controller 本轮明确禁止 README 修改，留给既定 S8 文档 gate。reactive queue scan 仍命中 owner、engine-ingest consumer 与 tests：`CompactPipelinePassQueuePlan` 和 `build_reactive_pass_queue_plan` 均保留。

Frozen JSON registry 解析成功且 byte digest 未变：

```text
f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4  docs/cli_ci_oracles.json
7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef  docs/cli_ci_scenarios.json
```

## Residual risk 与下一 gate

- deterministic owner closure、secret-safe feedback、retry cancellation、accepted identity guards 与 later-pass failure 已由 fresh v2 tests 覆盖。
- LLM 仍可能给出形式合法但自然语言质量较低的候选；这是 accepted plan 已分类的模型评估风险，不由 validator 伪装解决。
- README 历史说明属于已排期 S8 文档同步，本 fix loop 无权修改。
- 本轮没有未分类 blocker，也没有 frozen oracle 与唯一 owner 不可同时满足的直接反例。

**Fix verdict：PASS（implementation fix complete）。下一合法动作仅为独立 code re-review；本轮在该 gate 前停止。**
