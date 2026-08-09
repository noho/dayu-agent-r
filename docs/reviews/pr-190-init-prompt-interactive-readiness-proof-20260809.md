# PR 190 init / prompt / interactive 第一轮闭环证明

## 结论

在实现真源 `473e66b972e7e7a3e028ca1e9f4b2798ecb2b100` 上，`init`、`prompt`、`interactive` 已完成第一轮“真实运行 → 观察归档 → 用户裁决 → oracle/scenario冻结”，可以直接进入第二轮 CLI CI。

本结论不覆盖 `download`、`upload_*`、`process*`、`session` 或 `tool_trace` 命令本身的第一轮闭环。

## Current formal registry

| 命令 | Current accepted scenarios | Superseded | Unadjudicated | Evidence/oracle gap | 结果 |
|---|---:|---:|---:|---:|---|
| init | 59 | 0 | 0 | 0 | ready |
| prompt | 388 | 0 | 0 | 0 | ready |
| interactive | 609 | 3 | 0 | 0 | ready |

总计1056条current accepted scenarios。3条interactive superseded scenarios只保留历史运行、裁决和supersession provenance，不参加第二轮正式执行。

## Parser inventory

Parser inventory从 `dayu.cli.arg_parsing.build_parser()` 在目标实现commit上重新导出，不复用2026-08-02历史快照。

| Scope | Version | Parameters | SHA-256 |
|---|---:|---:|---|
| root | 3 | 13 | `b6696252b7e7c2895e758264e1656030c51f884673d9f5802f5e783bb5210be1` |
| init | 3 | 15 | `c75f31e5af807a0527bd9bcbe788f03885fa69a9bbce10394d7bc3ce73eda969` |
| prompt | 3 | 27 | `b7739eb2fa46f3199e76adc316fc41dbdd9afacec2ef0bdb4d37b04a8c3fe5d9` |
| interactive | 3 | 25 | `1953fd5ea3699c6a940628cc0b4f855bd89fb7dd3d9d2e39d9ef2a6764c36407` |

重新检查确认：root、prompt、interactive均不存在`--config`，interactive不存在`--ticker`。

## 最后一项裁决

### Cap-constrained replacement与fallback grounding

用户于2026-08-09根据以下复合证据裁决正确：

- `docs/reviews/pr-190-interactive-cap-constrained-memory-observed-20260808.md`
  - SHA-256：`54ca13f273402915f1657a95b0d3e50c2ba79ae84b4545ea7ace8e2d09376dce`
- `docs/reviews/pr-190-g06-fallback-grounding-postfix-observed-20260809.md`
  - SHA-256：`f4cefda475ebc0c6bf9b31d0b7a11cf12116eda4a7bd6d18236b648d19a881d4`

冻结结果：Host拥有caps、strict acceptance、bounded repair、fallback与durable truth；fallback继续主Run时，实际RunnerInput明确证据边界；当前材料不足时final answer明确无法回答，不从缺失历史、旧回答或模型常识生成未经支持的事实或风险。

### `session_summary=null`

用户于2026-08-09根据 `docs/reviews/pr-190-interactive-summary-null-observed-20260809.md` 裁决正确。报告SHA-256为 `b561e01a4b31ae9267479a70c72a388079299e3111d1be80f7463edd575de5db`。

冻结结果：已有非空摘要后，accepted `session_summary=null`只清除旧摘要；同一replacement中的5条EvidenceFact和1条AnswerAnchor保留；post-compact Run与跨进程reconnect消费同一状态。

## 独立复算

对两份registry做了不依赖proof自报值的独立复算：

- current accepted scenario：1056；
- unadjudicated：0；
- accepted scenario evidence status非`sufficient`：0；
- pending user adjudication identity：0；
- missing exact oracle refs：0；
- unresolved current oracle/predicate refs：0；
- empty correctness surfaces：0；
- dangling local report refs：0；
- local report SHA mismatch：0；
- parser removed-option contract mismatch：0；
- proof registry-basis mismatch：0。

Scenario array canonical digest：`202f4c81037b72b642cfc15ee0d1fb19a6d346f82e8c217cbff4d0df02c3e123`。

Oracle array canonical digest：`316d7ba4b06cc642df54d989bb0078d389eb04f6f809e4bc96124f770e6654cd`。

## 冻结文件

- `docs/cli_ci_oracles.json`
  - SHA-256：`2e29abfe7a170f4457a3f8586e4012f404588fa5621295b2124f07f731b81cf6`
- `docs/cli_ci_scenarios.json`
  - SHA-256：`9af45cad22ff819164b3198ca6be1d08ea0f8ae0646125825d45b8419039bbbc`
- `docs/cli_ci.md`
  - SHA-256：`af7b3b28f067db32c37ce847426f28314a05df52df5d459c07b260783f213ca1`

上述文件中的顶层version 3 `readiness_proof`是第二轮入口；`readiness_proof_history_20260802`只保留历史校准 provenance，不参与当前判定。

## 第二轮执行语义

第二轮不重新定义正确性。执行者必须按 `docs/cli_ci.md` 和 `docs/cli_ci_scenarios.json` 逐条真实运行current accepted scenarios，完整采集屏幕、exit、生成物、日志、Tool Trace、EventLog、Memory与SQLite证据，再由Agent-in-the-loop把观察结果对照冻结oracle判定。真实provider允许非确定性；证据缺失、secret finding、scenario漂移或oracle mismatch都不能由CLI自报summary覆盖。
