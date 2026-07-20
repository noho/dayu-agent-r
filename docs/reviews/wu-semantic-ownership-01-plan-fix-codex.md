# WU-SEMANTIC-OWNERSHIP-01 plan fix report

## Metadata

- Gate: plan fix
- Agent: AgentCodex
- Plan artifact: `docs/host/wu-semantic-ownership-01-umbrella-plan.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-plan-review-controller-adjudication.md`
- Scope: 只修 umbrella plan，未实现生产代码，未修改测试、README 或控制文档。

## Changed files

- `docs/host/wu-semantic-ownership-01-umbrella-plan.md`
- `docs/reviews/wu-semantic-ownership-01-plan-fix-codex.md`

## C01-C11 coverage

| Controller item | Status | Plan update |
|---|---|---|
| C01 P0-A finish reason authority | Covered | P0-A 默认 root-cause fix 改为移除 `RunnerContentCompletedData.finish_reason` 与 `ContentCompleteData.finish_reason`；明确 `RunnerDoneData.finish_reason` / `IterationCompletedData.finish_reason` 是唯一 authority；新增 implementation 前消费者扫描和 stop condition。 |
| C02 P0-B `ingest_method` coverage | Covered | P0-B 要求先全量运行 `rg "ingest_method" dayu/fins/`；allowed files 显式覆盖 CN pipeline、CN rebuild/source upsert、SEC source upsert、storage core、maintenance 等已知路径，并要求覆盖扫描新增点。 |
| C03 P0-B preprocess helper scope | Covered | P0-B root-cause confirmation 必须先选择 boolean helper 或 typed status helper，列出 direct/job/awaiting/direct-stream consumers，并裁决 JSON summary 是否新增 `not_supported_count`。 |
| C04 P1-A consumer migration pressure | Covered | P1-A S3 增加逐消费者 completeness checklist，强制覆盖 Tool Trace、Read API、Durable Memory、Conversation Memory、RunInputBuilder、CompactMaterial；允许拆 S3a/S3b 但不得漏消费者。 |
| C05 P1-B `RUN_LOST` behavior | Covered | P1-B 写入 controller design decision：`RUN_LOST` 是 Host terminal/lifecycle fact，不是 public outbox terminal item；public outbox watermark 不应因 `RUN_LOST` 要求 item；若 design truth 缺失，先更新 `docs/host/design.md`。 |
| C06 P1-C waiting wording boundary | Covered | P1-C 明确业务级“等待工具结果返回”允许边界和治理级 waiting 禁止边界；要求扫描 prompt/config、tool schema/outcome helper、duplicate-tool/governance messages 是否进入 LLM context。 |
| C07 P2-A session resume boundary | Covered | P2-A 默认采用 Service-owned existing-session execution helper；CLI 只保留参数解析、终端渲染和 command-specific output；CLI-public helper 仅在 root-cause confirmation 证明其纯 UI/rendering 且 Service 下沉会泄漏 display concerns 时允许。 |
| C08 P2-B obsolete finding handling | Covered | P2-B root-cause confirmation 必须先产出 `active` / `obsolete-with-evidence` / `needs-design-update` / `deferred-with-owner` finding status table；obsolete finding 可用 controller-accepted no-code/no-commit pass 关闭。 |
| C09 P2-C prompt source migration | Covered | P2-C 必须先运行 `rg "AgentPolicy\\(" dayu/ tests/` 并按 layer 分类构造点；明确 Engine 不得 import runtime config/config loader，production/tests 都必须从所属 assembly/fixture 显式传 prompt。 |
| C10 Full-repository deepreview phase | Covered | deepreview phase 改为每轮至少派 AgentMiMo 与 AgentDS 做全仓 review；列出 Engine contracts、Host durable truth、Host projections、Fins contracts、CLI/Service boundary、LLM-facing text、config/prompt、tests/import-boundary 等维度；final closeout 要求 fixes 后至少两轮连续无新增 accepted current-umbrella finding，除非用户改变退出条件。 |
| C11 Sub WU contract conflict handling | Covered | Umbrella execution protocol 增加 sub WU contract conflict handling：后续 sub WU 与已 accepted contract 冲突时 controller 停下，先更新设计真源，再选择修改早前 accepted contract 或在当前 sub WU 增加 typed mapping，禁止下游 workaround。 |

## Validation

- Passed: `git diff --check`
- Passed: `git diff --no-index --check /dev/null docs/host/wu-semantic-ownership-01-umbrella-plan.md` produced no whitespace-error output. The raw command returned 1 because `--no-index` reports the new file diff against `/dev/null`; an equivalent output-empty check returned 0.
- Passed: `git diff --no-index --check /dev/null docs/reviews/wu-semantic-ownership-01-plan-fix-codex.md` produced no whitespace-error output. The raw command returned 1 because `--no-index` reports the new file diff against `/dev/null`; an equivalent output-empty check returned 0.

## Blocking open questions

None for this plan fix gate.
