# PR 190 F11/F12 S3 Compact v3 Implementation

## Gate metadata

- Gate：`implementation review fix`
- Work unit：PR 190 F11/F12 S3 — F12 Host compact v3 原子纵向切换
- Branch：`codex/interactive-oracle`
- Start HEAD：`1943904eea9e30357805c9f1d2b6f6e815b37c86`
- Initial implementation status：`COMPLETED`（历史）
- Status：`SUPPLEMENTAL_IMPLEMENTATION_REVIEW_FIX_COMPLETED`
- Current gate：`supplemental implementation review fix complete`
- Next entry point：MiMo / DeepSeek fresh-session independent re-review
- Artifact path：`docs/gateflow/pr-190-f11-f12-s3-compact-v3-implementation-20260805.md`

## Outcome

S3 已在单一未提交 worktree diff 中完成 fresh compact v3 原子迁移。生产代码不保留 v2
alias、re-export、compatibility wrapper、旧字段 reader 或 loose parser；candidate、prompt、
provider transport、acceptance、artifact/event persistence、Memory、RunInput、dispatch 与 ingest
已切到同一 v3 contract。

语义 owner 如下：

- `dayu/host/compaction.py`：v3 typed input/candidate/accepted truth、durable policy audit 类型、
  共享字符计量原语与唯一 audit actual derivation/validation helper。
- `dayu/host/compact_structure.py`：唯一 immutable output structure descriptor；同源派生
  LLM-facing concise rules / concrete template、provider-native formal JSON Schema 与 strict parser。
- `dayu/host/context_governance.py`：唯一 accept/reject owner；从同一 Memory policy 投影 caps，
  从 accepted candidate 派生 represented coverage、root-boundary omitted exact complement 与
  policy usage audit。
- `dayu/host/compact_payload.py`、`context_events.py`、`compact_artifact.py`：canonical
  event/artifact strict boundary；candidate digest、coverage partition 与 audit exact binding 任一漂移
  都 fail closed。
- `dayu/host/memory.py`：Memory estimator 的公开 owner，复用 compact/Memory 共享计量原语；只消费
  strict parsed committed semantics，不从文本或下游展示重算 durable audit。
- `dayu/host/run_input.py`、`dispatch.py`、`engine_ingest.py`：只消费 committed Memory / accepted
  truth，不形成第二套 compact 解释。

## Implemented contract

1. fresh input 使用 `dayu.context_compaction.input.v3`，显式携带九项 required、无 default 的
   `output_caps`；request digest 覆盖 immutable source boundary 与真实 caps。
2. fresh output 使用 `dayu.context_compaction.output.v3`，root 固定六个 required keys：
   `schema`、required-nullable `session_summary`、`evidence_facts`、`answer_anchors`、
   `forward_intents`、`reference_continuity`。模型不再生成 diagnostics、drop ledger/reason、
   coverage 或 policy usage。
3. `compact_structure` descriptor 的 template、rules、formal schema 与 parser 使用相同 root/nested
   字段定义；投影每次返回 fresh value，调用方 mutation 不能污染 owner-held structure；schema
   name/digest 与 JSON Schema transport 同源。
4. LLM-facing initial/repair prompt 不注入完整 formal schema。两者都自足包含 concrete template、
   字段类型/必填性/允许值、null、来源、caps 与最小 shape；repair 基于同一完整输入 whole-candidate
   重产，不依赖前次输出。request/source-boundary digest 的字段名和值都不进入模型上下文。
5. prompt 只要求模型输出五类业务内容与真实来源引用，不暴露 Host、omitted coverage、policy audit
   等治理事实；正式 JSON Schema 只通过 typed structured-output capability 进入 provider transport。
6. `NONE`、`JSON_OBJECT`、`JSON_SCHEMA` 三态只由 `RunnerSpec.structured_output_capability` 决定，
   不按 provider/model 名称分支。
7. `derive_compact_represented_sections_v3` 是 candidate provenance → represented sections 的唯一
   derivation helper；Context Governance、canonical reader 与 artifact writer 共同复用。boundary 中
   未引用 label 由 governance 派生为 omitted exact complement；durable boundary 重验顺序、disjoint、
   union 与 candidate sections。
8. policy audit 九项 actual 只由 `derive_compact_policy_usage_actuals_v3` 从 accepted candidate 派生；
   字符计算复用 Memory estimator 的同一字符单位。canonical event parser、artifact writer 与 Memory
   boundary 都调用同一 exact validator，同时检查 actual 等于 candidate 派生值且不超过 cap。
9. owner tests 覆盖 summary/fact/anchor/intent/reference 五项 char actual 被向下篡改、artifact audit
   mismatch、represented/omitted overlap 与缺失分区；这些反例均在 strict owner boundary fail closed。
10. Persistence schema 升为 fresh artifact version 4；Memory/RunInput 保持 committed event、accepted
    candidate、coverage、audit 与 projection 的单一真源。

## Cross-slice S2 completion fix

最终 full-suite 首轮暴露 S2 accepted implementation 的 owner 漏投影：
`dayu/cli/init_catalog.py::_build_custom_openai_record` 生成的动态 Custom OpenAI-compatible 完整
模型记录缺少当前 schema 必填 `structured_output_capability`。根据总控裁决，本次在真正 owner
显式投影 `StructuredOutputCapabilityConfig.NONE.value`，并在 owner test 同时断言 raw JSON
`"none"` 与 resolved typed enum `NONE`。ConfigLoader 没有增加默认值、兼容 fallback 或 provider
名称推断。

对应四条原失败测试已先定点复核为 `4 passed`，随后纳入最终 full suite PASS。

## Historical blocker and decision provenance

implementation 首次进入时曾记录 `BLOCKED_BEFORE_IMPLEMENTATION`：最初 S3 allowed-tests 清单漏列
五个直接 import/构造 v2 production contract 的 Host tests/fixtures；若不迁移则 full Host suite
无法 collection，若保留 v2 symbol 则违反 fresh schema。该判断及当时未实施事实保留为历史证据。

用户在 2026-08-05 裁决“测试跟着相应修改就好了”，总控更新 plan 并新增
`pr-190-f11-f12-s3-scope-correction-20260805.md`，解除该 blocker。后续用户进一步明确：

- 所有直接 v2 test/fixture consumer 可做必要 mechanical v3 migration；
- 两个直接 evidence harness consumer 可做纯 mechanical migration；
- prompt 不得全文注入 formal schema或暴露 Host 治理术语；
- durable audit 必须与 candidate exact 同源；
- S2 Custom model capability 漏洞必须在当前 work unit 真正 owner 收口。

因此历史 blocker 状态为 `RESOLVED`，当前 implementation 状态是 `COMPLETED`，不是 `BLOCKED`。

## Changed files

Production / config owner：

- `dayu/host/compact_structure.py`（new）
- `dayu/host/compaction.py`
- `dayu/host/context_governance.py`
- `dayu/host/llm_compaction.py`
- `dayu/host/compact_material.py`
- `dayu/host/compact_pipeline.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/compact_artifact.py`
- `dayu/host/compact_payload.py`
- `dayu/host/context_events.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/memory.py`
- `dayu/host/run_input.py`
- `dayu/cli/init_catalog.py`（cross-slice S2 completion fix）
- 两个 conversation compaction prompt assets
- `docs/cli_init_workspace_manifest_v1.json`

Tests / fixtures / approved harness consumers：

- compact owner、pipeline、operation、artifact/event、Memory、RunInput、dispatch/ingest、public smoke、
  cancellation/terminal、Tool Trace 与 Service assembly 相关 Host tests/fakes/fixtures
- `tests/host/test_open_host_runtime.py`、`tests/host/test_public_open_host_options.py` 的直接 prompt
  template consumer migration
- `tests/cli/test_init_catalog.py` 与 publication manifest digest test
- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `utils/smoke_host_public_r03_semantic_ownership.py`

Docs：

- accepted plan、scope-correction 与本 implementation artifact
- `dayu/host/README.md`
- `dayu/config/README.md`

## Prompt and structure metrics

Raw prompt bytes / SHA-256：

| Asset | Before bytes | After bytes | Before SHA-256 | After SHA-256 |
|---|---:|---:|---|---|
| `conversation_compaction.md` | 2510 | 822 | `4bd476db45f17bebaa7eb951c8354d10189df1faadb9c1c530619d9f3352f60a` | `97479acc0cc686cb9a72d18b310aff58cabba4d4b223c6773a12249b5ed333e5` |
| `conversation_compaction_user.md` | 13919 | 4301 | `5f5a51519e11eae0f162e8623e3c55d3946e1613bd36bfe4c38cc3e61eb827c0` | `59b50e13ea636c434fcabe26adf6d9ed22665dfcba03533ebcf5e9b524b87b76` |

- output root：v2 8 keys → v3 6 required keys。
- removed model-owned fields：`diagnostics`、`explicitly_dropped_sources` 及 drop reason。
- formal JSON Schema：保留为 provider-native transport；LLM prompt 中为 0 份全文 schema。
- publication manifest SHA-256：
  `d95de68e69b0aacc712ec6bf468c8604a91460a17f3e2497f397182517a6a9f8`。

## Implementation review fix outcome

总控 adjudication 接受的 A01-A07 已由原 implementation owner 修复：

1. prompt 不再使用“覆盖账本”，改为禁止输出已保留/未保留材料统计、逐项清单与省略解释。
2. repair LLM-facing 文本把 attempt 改为“前次输出编号”；Host internal attempt state 未改。
3. represented coverage candidate-binding validator 进入 `compaction.py::__all__`。
4. reviewer 指定的八处 stale v2 test docstring 机械改为 v3。
5. `session_summary` 在 cap 无法容纳有业务意义且可独立理解的摘要时必须为 `null`，禁止
   单字符、截断片段或占位文本凑非空；没有新增阈值、关键词或自然语言 verifier。
6. `compact_policy_usage_measurement_rules_v3` 由 `compaction.py` 的 existing actual derivation
   owner 投影五类 exact 字符规则；Context Governance 错误说明与 initial/repair prompt 共用，
   不形成第二套 caps 或 provider 分支。
7. repair-only 文本解释 `code/json_path/message/source_labels`、label 非业务事实与 issues
   有界脱敏摘要，继续要求结合同一完整输入 whole-candidate replay；initial 无 repair protocol。

R01 `compactor_input_projection.v2` 与 R02 `invalid_enum_value` 维持 controller 的
`rejected-with-reason` 裁决，未修改；两份历史 review artifact 保持原文。

## Delayed MiMo supplemental fix outcome

MiMo dynamic workflow 迟到返回的补充 findings 已按 adjudication 只修复 SA01-SA05：

1. packaged user prompt 用精简业务文本自足解释八种 `source_kind`，并明确 kind 只是材料类型，
   不是事实证明或推理依据；没有恢复 v2 drop ledger、initial repair protocol 或长示例。
2. Host README 的 Conversation Memory active contract 改为 output v3、Host-derived represented /
   omitted exact partition、required-null summary 清旧语义及 `CompactAcceptedTruthV3`。
3. durable reader 的 audit tamper matrix 补齐四个 item actual，现覆盖九项 actual exact binding。
4. `CompactAcceptedTruthV3` 在 accepted-truth owner 边界对 represented coverage 执行 root
   boundary 顺序校验，并由乱序反例锁定 fail-closed 行为。
5. `ContextCompactedSemanticPayload` 在访问字段前明确检查 `source_boundary` 必须为 tuple、
   每项必须为 typed boundary entry，且 `represented_coverage` 必须为 typed coverage；现有
   candidate-binding validator 保持唯一复用。

SR01-SR05 保持 `rejected-with-reason` 且未修改对应契约；A01-A07 的既有修复全部保持。

## Validation

最终验证（均在 `source .venv/bin/activate` 后执行）：

- S2 follow-up 四条定点测试：`4 passed`。
- compact structure / LLM owner 定点测试：`48 passed`。
- 完整项目 suite：`6696 passed, 10 skipped, 6 deselected`；随后只新增的 compact payload helper
  owner test 定点运行 `86 passed`。
- `python -m pyright dayu/ tests/ utils/`：0 errors。
- 修改 Python 文件 Ruff：PASS；`python -m compileall -q dayu tests utils`：PASS。
- publication JSON parse、raw-byte SHA-256、manifest frozen digest 与真实 init publication tests：PASS。
- production v2 symbol/schema/drop-ledger residue scan：0 matches；仅测试中的 forbidden-key 负断言保留旧字段文本。
- compactor prompt internal-governance/full-schema residue scan：0 matches。
- `git diff --check`：PASS。

最终 branch coverage（coverage.py exact percentage）：

| Production file | Coverage |
|---|---:|
| `dayu/cli/init_catalog.py` | 85.71% |
| `dayu/host/compact_structure.py` | 87.71% |
| `dayu/host/compaction.py` | 80.72% |
| `dayu/host/context_governance.py` | 85.90% |
| `dayu/host/llm_compaction.py` | 83.82% |
| `dayu/host/compact_material.py` | 81.00% |
| `dayu/host/compact_pipeline.py` | 89.66% |
| `dayu/host/compaction_operation.py` | 83.80% |
| `dayu/host/compact_artifact.py` | 80.65% |
| `dayu/host/compact_payload.py` | 82.84% |
| `dayu/host/context_events.py` | 83.78% |
| `dayu/host/dispatch.py` | 84.28% |
| `dayu/host/engine_ingest.py` | 85.38% |
| `dayu/host/memory.py` | 85.65% |
| `dayu/host/run_input.py` | 82.41% |

review-fix 后新增验证：

- focused prompt/compaction/null owner tests：`52 passed`。
- S3 focused owner/consumer/publication suite：`1071 passed, 1 skipped`。
- review-fix 触及生产文件 branch coverage：`compaction.py 81%`、
  `context_governance.py 86%`、`llm_compaction.py 84%`。
- `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- 全部 changed Python 文件 Ruff：PASS；`python -m compileall -q dayu tests utils`：PASS。
- publication manifest JSON parse、两个 prompt raw-byte hash、manifest frozen digest 与真实 init
  publication tests：PASS。
- A01-A04 residue scan：无目标 stale LLM-facing/test 文本；R01/R02 字面量仍保持原裁决。
- `git diff --check`：PASS。

delayed MiMo supplemental fix 后新增验证：

- direct owner tests：`143 passed`。
- S3 focused owner/consumer/publication suite：`1078 passed, 1 skipped`。
- supplemental 触及生产文件 branch coverage：`compaction.py 81%`、
  `compact_payload.py 84%`；coverage suite `706 passed, 1 skipped`。
- `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- 全部 changed Python 文件 Ruff：PASS；`python -m compileall -q dayu tests utils`：PASS。
- publication manifest JSON parse 与两条真实 publication/hash owner tests：PASS。
- raw prompt SHA-256：system `97479acc0cc686cb9a72d18b310aff58cabba4d4b223c6773a12249b5ed333e5`；
  user `59b50e13ea636c434fcabe26adf6d9ed22665dfcba03533ebcf5e9b524b87b76`；
  frozen manifest `d95de68e69b0aacc712ec6bf468c8604a91460a17f3e2497f397182517a6a9f8`。
- `git diff --check`：PASS。

## README decision

- 更新 `dayu/host/README.md`：记录 fresh v3 单一 structure owner、prompt/transport 分离、
  Host-derived coverage/audit 与 canonical exact validation。
- 更新 `dayu/config/README.md`：记录三个运行期 placeholder、formal schema 只走 transport、v3
  prompt 职责，以及动态 Custom model 显式 capability `none`。
- 不更新 `tests/README.md`：只增加既有 Host/CLI 层内 owner 断言，未新增测试层级、运行方式或维护规则。
- 不更新 `dayu/README.md`：`UI -> Service -> Host -> Engine` 分层与跨包 stable boundary 未改变。
- 不更新根 `README.md`：用户命令、参数、输出位置与工作流未改变。

## Residual risks

1. S3 是按 accepted plan 完成的原子 breaking migration，diff surface 较大；风险由 full suite、
   逐文件 branch coverage 与后续两路独立 review 控制。
2. 当前未执行 S4 真实 provider evidence；两个 harness 只做获准的 mechanical v3 migration，真实
   场景语义与 evidence contract 未提前改变。
3. 未发现其它 scope 外 production consumer、v2 production residue、兼容路径或已知测试/类型失败。
4. review-fix 的 natural-language 规则只能约束模型选择，deterministic tests 不证明任意摘要的
   自然语言质量；真实 provider cap-constrained behavior 仍由 S4 observation 负责。

## Completion status

S3 initial implementation：`COMPLETED`（历史）。A01-A07 implementation review fix：`COMPLETED`；
SA01-SA05 supplemental implementation review fix：`COMPLETED`。未 stage、commit、push；
未启动 reviewer/subagent。工作区保持未提交状态，等待总控在 fresh session 派发 MiMo 与
DeepSeek 两路独立 re-review。
