# WU CLI Conformance F01-F07 S7 Implementation

## 1. 结论与边界

- 入口：PR 190 当前分支，`HEAD=b8f87e3b09998ec764de9bbfa83e684e871c949c`。
- 结论：S7/F07 Host Context Governance 已按 fresh v2 contract 完成原子 closure；不存在 alias、compat re-export、old reader、loose parser 或 downstream compensation。
- 执行形态：一个 outer slice、一个 unstaged working tree；未 stage、commit、push、切 branch 或创建 stash。工作区原有 `stash@{0}: On phaseflow/wu-cm-01: partial WU-CM-01 Slice C typed contract attempt` 未读取、应用或改动。
- 禁止区：Engine production、CLI/Service production、Fins、frozen registry、README 均未修改。README 的旧文字由 S8 负责，见 §9.3 扫描说明。
- 用户批准的 owner/test boundary exception 与 full-pyright 直接 consumer exception 见 §8；没有新增 production/test 文件。本文件是唯一新增文件。

## 2. 动机、owner 与实现闭包

动机成立。原实现同时存在旧输入/输出 contract、非严格 raw JSON、candidate 与 coverage 双真源、最后一个 reactive pass 冒充 root truth、未提交 truth 可被下游观察，以及 durable serializer 仍读取旧业务枚举 `.value` 的直接证据。正确 owner 分布如下：

| 语义 | 唯一 owner | closure |
|---|---|---|
| fresh typed input/candidate/canonical JSON | `dayu/host/compaction.py` | 定义 strict v2 类型；删除旧映射 symbols/literals 与已失去消费者的 instruction 类型 |
| committed material/source boundary | `dayu/host/compact_material.py` | previous-*、trace、evidence、answer 逐项形成 typed boundary；current input 独立且不可引用 |
| raw LLM JSON | `dayu/host/llm_compaction.py` | `object_pairs_hook` 拒绝任意层 duplicate key；每层 exact keys/types/enums；prompt 自足给出 schema、最小示例与禁止事项 |
| candidate accept | `dayu/host/context_governance.py` | 唯一构造 `CompactAcceptedTruthV2`；验证 empty、diagnostics-only、low-info、coverage、kind、caps、duplicate、contradiction |
| operation/repair/reactive root | `dayu/host/compaction_operation.py`、`compact_pipeline.py` | whole-candidate repair、immutable pass input、ordered queue、global attempt budget、root revalidation |
| terminal artifact/event | `compact_artifact.py`、`compact_payload.py`、`context_events.py`、`dispatch.py`、`engine_ingest.py` | terminal permit 下单一 accepted/failure terminal；strict v2 committed projection |
| Memory/RunInput/trace | `memory.py`、`durable/memory.py`、`run_input.py` | 只消费 committed canonical event；represented∪dropped 替换；current input 保留；durable business text 直接存 `str` |

传播闭包逐项完成：

- [x] contract definition / canonical JSON
- [x] input producer / rolling source boundary
- [x] LLM-facing producer / strict parser
- [x] accept / operation / reactive queue
- [x] persistence / canonical reader
- [x] terminal writer / reactive owner
- [x] projection / next input / trace
- [x] tests / fake / public smoke
- [x] active design truth

## 3. Fresh v2 contract evidence

### 3.1 Input sample

```json
{
  "schema": "dayu.context_compaction.input.v2",
  "current_input": {"readable_text": "继续比较经营现金流"},
  "source_boundary": [
    {
      "source_label": "E1",
      "source_kind": "evidence_material",
      "readable_text": "工具：财报检索\n查询：FY2025 revenue\n结果：100\n来源：10-K"
    }
  ]
}
```

`CompactCurrentInputV2.source_ref` 与每个 boundary entry 的 `source_refs` 仅保留在 Host typed object，不进入 LLM JSON。空 boundary 在 Host selection/no-op 边界结束，不调用 compactor。

### 3.2 Candidate sample

```json
{
  "schema": "dayu.context_compaction.output.v2",
  "session_summary": null,
  "evidence_facts": [
    {"claim": "FY2025 revenue is 100", "support_labels": ["E1"], "context_labels": []}
  ],
  "answer_anchors": [],
  "forward_intents": [],
  "reference_continuity": [],
  "diagnostics": [],
  "explicitly_dropped_sources": []
}
```

### 3.3 Source-kind / semantic-section matrix

| source kind | 合法 represented section |
|---|---|
| `previous_session_summary` | `session_summary` |
| `previous_evidence_fact` | `session_summary`、`evidence_facts.support_labels` |
| `previous_answer_anchor` | `session_summary`、`answer_anchors` |
| `previous_forward_intent` | `session_summary`、`forward_intents` |
| `previous_reference_continuity` | `session_summary`、`reference_continuity` |
| `trace_material` | `session_summary`、fact context、`forward_intents`、`reference_continuity` |
| `evidence_material` | `session_summary`、`evidence_facts.support_labels`、`reference_continuity` |
| `answer_material` | `session_summary`、fact context、`answer_anchors`、`forward_intents`、`reference_continuity` |

覆盖由五个业务 section 的 label 引用派生，diagnostics 不计覆盖；显式 drop 单独持有闭集 reason。accept invariant 为：

```text
boundary_labels == represented_labels ∪ explicitly_dropped_labels
represented_labels ∩ explicitly_dropped_labels == ∅
```

## 4. Deterministic validation matrix

| §9.8 类别 | owner-level evidence |
|---|---|
| 1 strict JSON | top/nested duplicate、unknown、missing、type、enum、blank 与旧 v1 全部 strict reject |
| 2 source coverage | unknown/duplicate/kind mismatch/uncovered/overlap/duplicate drop 与 exact partition |
| 3 semantic quality | empty、diagnostics-only、all-drop、low-info、精确 duplicate/contradiction；相似但不相同文本不误判 |
| 4 caps | session summary 字符上限，以及 facts、anchors、intents、references 各 section 的 item-count 与 aggregate-size `==cap` accept、`+1` reject；复用同一 `MemoryProjectionPolicy` 与 `estimate_memory_size_units`。diagnostics 不属于 Memory policy cap |
| 5 repair | 首次 `None`；invalid 后 bounded redacted report；32/240/8192；完整 replacement success；execution failure 不伪造 feedback |
| 6 materialization | invalid attempt/intermediate pass 的 accepted artifact/event/Memory/RunInput/public trace 写计数为 0；final truth 单次提交 |
| 7 reactive multi-pass | immutable/disjoint pass boundary、ordered queue、cross-pass duplicate/cap/budget root revalidation、global attempt budget |
| 8 exhaust/terminal | all-invalid、mixed execution+invalid、late success/failure、cancel race 保持单一 terminal 与既有 fallback/fail-closed |
| 9 rolling | previous-* 全量边界；第二次 accepted replacement 后无旧 Memory 残留；两个 followup 同源 |
| 10 public smoke | real prompt/schema 经 assembly/public Host；合法 candidate accepted，非法 candidate 无 fake bypass |

## 5. Repair transcript 与 terminal timeline

脱敏 repair transcript 的形状为：

```json
{
  "previous_attempt_number": 1,
  "issues": [
    {
      "code": "uncovered_source",
      "json_path": "$.source_boundary",
      "message": "每个输入引用标签必须被业务内容表示或显式丢弃。",
      "source_labels": ["E1"]
    }
  ],
  "additional_issue_count": 0,
  "required_action": "返回一个完整 replacement candidate，不是 patch，也不得沿用先前 JSON。"
}
```

feedback 不携带 raw candidate/input 文本、canonical ref、event/tool-call id、digest、cursor、路径、环境或 secret。operation timeline：

```text
immutable root/pass input
  -> semantic attempt N
  -> strict parse
  -> governance reject: diagnostic only; optional whole-candidate repair
  -> per-pass private accepted truth
  -> all-pass root aggregate + coverage/duplicate/contradiction/caps/budget revalidation
  -> terminal permit
     -> one artifact + one CONTEXT_COMPACTED
     -> or one CONTEXT_COMPACTION_FAILED + existing fallback/fail-closed
  -> committed event
  -> Memory catch-up
  -> ordinary RunInput/public trace projection
```

late/stale contender 在 permit 关闭后只能留下 bounded diagnostic，不能产生第二 terminal。

## 6. Committed identity 与 rolling evidence

| consumer | source of truth | identity/coverage |
|---|---|---|
| compact artifact | final `CompactAcceptedTruthV2` | candidate digest、root boundary、derived represented/drop coverage |
| EventLog | 同一次 terminal commit | artifact ref/digest、candidate digest、boundary、coverage、successful response identity |
| Memory | committed `CONTEXT_COMPACTED` strict parser | 用 represented∪dropped coverage 删除/替换，绝不消费 operation object |
| ordinary RunInput | committed Memory/event projection + current input | current input 保留；不重读 raw LLM JSON |
| public trace | committed terminal identity | 不暴露 invalid attempt/intermediate pass |

rolling round 1 形成 committed snapshot R1；round 2 把 R1 的 summary/fact/anchor/intent/reference 分别投影成 previous-* boundary。R2 candidate 必须逐项 represented 或 drop，commit 后 snapshot 只含 R2 replacement；连续两个 followup 的 artifact/EventLog/Memory/RunInput/trace 都引用 R2 同一 canonical truth。

## 7. Checkpoint ledger

| checkpoint | focused result | pyright | 初始失败与修复 |
|---|---:|---:|---|
| A schema + source boundary | baseline 118 passed；fresh closure 117 passed | 0 errors | 删除旧 contract 测试后计数减少 1；prompt/material/fake 全量迁移 |
| B strict parser + accept | 32 passed | 0 errors | duplicate/unknown/coverage/caps 的初始不一致由 parser/唯一 accept owner 修复 |
| C whole-candidate repair + operation | 25 passed | 0 errors | repair feedback 跨 scheduler attempt 显式传递；不把 execution retry 当 semantic repair |
| D committed projection + reactive multi-pass | 519 passed | 0 errors | 修复最后一 pass 冒充 root truth、cross-pass reroute、空 boundary 与 durable business text owner |

后续 controller 精确 pyright 初始输出为 4 errors：`test_accepted_result_projection.py` 2 个旧 `evidence_material` attribute、`test_compaction_cancellation_scope.py` 1 个旧 `accepted_candidate` attribute、`test_proactive_compaction_operation.py` 1 个缺 `repair_feedback`。迁移后这 3 个文件为 `61 passed` 且 `0 errors`。用户点名的 `tests/host/test_compaction_attempt_manifest.py` 在 entry/current tree 均不存在，因此没有新增占位或猜测替代；严格采用“以 pyright 精确输出为准”的三个真实文件。

full-repository pyright 随后直接发现 6 errors：`test_dispatch_scheduler.py` 的 optional policy fake signature，以及两个现存 public smoke utils 的旧 contract consumer。它们分别改为 required typed policy、fresh v2 source boundary/candidate；没有向 production 添加 property、alias、default 或 wrapper。最终 focused 与 repository pyright 均 0 errors。

完整矩阵的第一次、第二次运行均为 `767 passed, 1 skipped, 1 failed`，唯一失败是非 S7 语义的 scheduler 10ms lane acquire race：目标测试要验证 worker stream exception→LOST，却在负载下先 timeout→FAILED；该测试单独复跑通过。把该测试自身的 lane timeout 明确设为 1 秒后，完整矩阵连续运行与 coverage run 均为 `768 passed, 1 skipped`。未修改 scheduler production 语义。

## 8. Allowlist exception ledger

entry/current 均为 SHA-256；numstat 是相对 `b8f87e3b` 的直接 diff。所有例外均是唯一直接 owner/typed shared factory/stale active consumer，不改变 frozen oracle 或产品语义，故无需用户再次裁决。

| 文件 | 原计划漏列的直接证据 | entry SHA-256 | current SHA-256 | numstat |
|---|---|---|---|---:|
| `dayu/host/durable/memory.py` | durable forward-intent/reference serializer 仍调用业务文本 `.value`；这里是正确持久化 owner | `9423b7d6971c76cea68638247838a59bc2144b83df13121296db507d2f347fce` | `0792501591967ee4af54dccf43cf3c3d2c4910300314b4eb697cf3c20c6f7083` | `+23/-73` |
| `tests/host/memory_snapshot_factories.py` | 多个 allowed tests 共用的 typed Memory factory 仍构造旧 enum | `dd6b5d692864205520b3c3fe0691042b8dce340e52b333b05eababaabe025662` | `208d2c95779a8bb5a994792e74d2254fa8077d25b9e40026875b6a84e5a6fb26` | `+5/-7` |
| `tests/host/test_accepted_result_projection.py` | precise pyright：旧 input `evidence_material` reader | `fa8cafa4b1f6043ae0d50d7c51e82857ac148444a1f33572d27d4958b874ab64` | `ede884400008f1f2da57e3119c515a0ef6026185ad6547686eaa527ae87b9a8b` | `+67/-96` |
| `tests/host/test_compaction_cancellation_scope.py` | precise pyright：旧 operation result `accepted_candidate` reader | `46a3d4a7a0187ec59088c3f73d9a018627fecbca7b28a5de8d0ee2d961df0357` | `6cce2a82b125e1ff325bfc486887db12b8d31f114272caf23b30fabd76c1b272` | `+13/-16` |
| `tests/host/test_proactive_compaction_operation.py` | precise pyright：fresh prepared input 缺显式 `repair_feedback` | `c0500852bda3328ff6a74ec4a28a3135011d479a073581a1be25a61750a1bf29` | `ae23f06841ad7f24cc8d08d2270883dada5b4737e6ef66c153936096f54db060` | `+24/-69` |
| `utils/smoke_host_public_conversation_memory_scenarios.py` | full pyright 与旧-symbol scan 直接证明真实 public smoke fake 仍输出旧 candidate；按 fresh source boundary 完整构造，不加 compat | `f5d89e7b6b9754045721da7f51679e292f80af4310adaa780e4b01987debdfc0` | `7f09477bddbf573d76f418a04bf82f5f12fb71ef73ccfab0dcd915e4816e7a43` | `+103/-164`（`-w`：`+99/-160`） |
| `utils/smoke_host_public_r03_semantic_ownership.py` | full pyright 直接证明 smoke diagnostic 仍读旧 `evidence_material`；改读 typed evidence boundary 的自解释来源行 | `fdbf75c6bb4b665bbbcebd1fb9b98c918f14cd1d11da1127154b02a5e6e39858` | `85740695f7bd8ee42cea40b97335ca10b725121b358dea17ab4a90cbb424a055` | `+6/-4`（`-w` 相同） |

`_CanonicalMemoryBusinessText` 已完全删除；durable serializer 直接持久化 `str`，reader 保持 strict fresh semantics，roundtrip 由 `test_memory_projection.py` 覆盖。两个 utils 是 AGENTS 定义的 smoke/分析脚本，不是 production/test 文件；扩展只为满足 controller 的 full-repository pyright 0 与 active old-symbol 0，不纳入 production coverage 要求。

utils churn 最小化 ledger：第一次迁移后误对两个整文件运行 `ruff format`，numstat 分别为 `+143/-242` 与 `+39/-109`。总控纠正后，仅用 `apply_patch` 基于 entry 原文恢复所有未触及行，再施加 strict v2 consumer 与首文件 E402 的最小 patch；最终 numstat 降为 `+103/-164` 与 `+6/-4`。第一文件忽略空白后的 `+99/-160` 与最终 diff 基本相同，剩余主体是删除旧 section/alias reader并完整改写 strict v2 fake candidate，非纯格式化；第二文件只剩 import 与 typed evidence boundary 读取。未使用 checkout/reset。

## 9. Final validation

### 9.1 Tests and type checks

- S7 plan 列出的 15 个路径，加 3 个 precise-pyright owner tests：`768 passed, 1 skipped, 3 warnings in 8.24s`。
- coverage 同一矩阵：`768 passed, 1 skipped, 3 warnings in 11.15s`。
- skip：真实 provider 环境 gate；没有 skip S7 owner contract。
- focused pyright：`0 errors, 0 warnings, 0 informations`。
- full repository `python -m pyright`：`0 errors, 0 warnings, 0 informations`。
- 两个 public smoke scripts `--help`：exit 0，证明 import/CLI surface 可加载。
- utils focused pyright：`0 errors`；utils Ruff：All checks passed；相关 public smoke：`23 passed, 1 skipped`。

### 9.2 Modified production coverage

| file | coverage |
|---|---:|
| `compact_artifact.py` | 87% |
| `compact_material.py` | 85% |
| `compact_payload.py` | 88% |
| `compact_pipeline.py` | 93% |
| `compaction.py` | 83% |
| `compaction_operation.py` | 89% |
| `context_events.py` | 88% |
| `context_governance.py` | 91% |
| `dispatch.py` | 85% |
| `durable/memory.py` | 85% |
| `engine_ingest.py` | 89% |
| `llm_compaction.py` | 83% |
| `memory.py` | 90% |
| `run_input.py` | 86% |
| total | 87% |

所有修改 production Python 单文件均 ≥80%。

### 9.3 Static, diff, frozen and workspace checks

- Ruff check：All checks passed。两个 utils 保留 entry 原格式，未再执行整文件 formatter。
- `git diff --check`：clean。
- fresh old-symbol/literal scan：active production/config/tests/runtime/service/design 零命中。按 plan 原命令把整个 `dayu/host`（包含禁止修改的 README）纳入时，仅命中 `dayu/host/README.md:735` 的既有 `conversation_compact_output_v1`；该文件是 S7 明确禁止修改、S8 明确负责的非 active 文档，不是 active consumer/reader。排除该 frozen README 后为零命中。
- reactive queue scan：`CompactPipelinePassQueuePlan` 与 `build_reactive_pass_queue_plan` 在 builder、engine consumer 和 owner tests 均存在。
- frozen hashes：
  - `docs/cli_ci_oracles.json` = `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`
  - `docs/cli_ci_scenarios.json` = `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`
- `HEAD` 仍为 entry `b8f87e3b09998ec764de9bbfa83e684e871c949c`；index 无 staged file；没有 commit/push/PR 操作。

## 10. Residual risk

deterministic contract、atomic terminal、durable projection、rolling replacement 与竞态不变量已有 owner tests。剩余风险是 LLM 生成内容的自然语言事实质量；validator 只判断 schema 可证明的 duplicate/contradiction，不用模糊相似度或自然语言真假判断伪装确定性。README 的旧非 active 描述按明确 S8 边界保留。
