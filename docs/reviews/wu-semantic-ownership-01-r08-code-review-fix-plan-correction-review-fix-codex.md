# WU-SEMANTIC-OWNERSHIP-01 R08 Corrected-Plan Review Finding Fix — AgentCodex

## 1. Gate 结果

- umbrella：`WU-SEMANTIC-OWNERSHIP-01`
- remediation sub-WU：既有 `R08`；不是新 WU、feature 或 issue
- gate：corrected-plan review finding fix（plan-only）
- accepted finding：仅 `R08-CR-PCPR-F01`
- branch：`phaseflow/host-issues-control`
- HEAD：`243768c323a6aa86ee8a35fea144a00ef9b2af98`
- entry plan SHA-256：`86bb76c768609451ca5f2de297f04f971832b719c6ca5a8b4a94d1617753fa65`
- final plan SHA-256：`a79268ea8d45f6af8854859269ce3592506f753272c32ecffab76d765cad7a02`
- protected `dayu/fins + tests` binary diff SHA-256（before / after）：
  `7a7ebf939b758ce8fdd92413210743e5a90b65272df62e466bf70332eb771d6d` /
  `7a7ebf939b758ce8fdd92413210743e5a90b65272df62e466bf70332eb771d6d`
- 结果：`COMPLETE — RETURN TO CONTROLLER FOR COMPLETE CORRECTED-PLAN RE-REVIEW`

本 turn 只修改 corrected plan §6.1 candidate 2/3，并新增本 artifact。没有修改 product、tests、
README、control、design 或 prior artifacts，没有执行 implementation、stage、commit、push 或 PR。

## 2. 第一性原理与语义 owner

Finding 成立。未知 section/table ref 的 processor 协议输入异常与调用方可见失败是两个相邻但
不同的责任：typed `DocumentProcessor` fixture 只负责提供 processor 会产生的精确 `KeyError`
输入；`FinsReadRuntime` public seam 才拥有把该输入转换为 `FinsReadArgumentError` 的公共失败
语义。测试必须穿过 public runtime 并只观察公共失败，不能直接断言 fixture，也不能在测试侧
建立第二套异常 normalization。

该修复补齐后续实现所需输入条件，不改变 production contract、测试候选结构或 coverage policy。

## 3. 精确 diff

唯一 plan delta 是 §6.1 表中 candidate 2 与 candidate 3 的第四列：

```diff
-| 2. section public payload projection | `test_read_section_projects_minimal_navigation_payload_and_rejects_unknown_ref` | `FinsReadRuntime.read_section` public seam | 通过真实 repository + typed `DocumentProcessor` protocol fixture 提供含合法/非法 children、page range、content/title 的 section；断言 public `children` 只含有效 `ref/title`、page range 与 citation/identity 来自 runtime，未知 `ref` 精确抛 `FinsReadArgumentError`。不得断言 processor 私有状态、父标题调用次数或其它偶然顺序。 |
-| 3. table public payload projection | `test_get_table_projects_self_describing_data_shapes_and_rejects_unknown_ref` | `FinsReadRuntime.get_table` public seam | 通过同类 repository-backed typed processor inputs 分别给出 records、合法 Markdown 与普通文本；断言 public `data.kind` 及各 shape exact keys/values、table identity/citation，并断言未知 `table_ref` 精确抛 `FinsReadArgumentError`。typed fixture 只提供协议输入，不得成为被断言对象；不得读 processor private method/state。 |
+| 2. section public payload projection | `test_read_section_projects_minimal_navigation_payload_and_rejects_unknown_ref` | `FinsReadRuntime.read_section` public seam | 通过真实 repository + typed `DocumentProcessor` protocol fixture 提供含合法/非法 children、page range、content/title 的 section；断言 public `children` 只含有效 `ref/title`、page range 与 citation/identity 来自 runtime。对于未知 `ref` 输入，typed fixture 的 `read_section` 必须抛 `KeyError`，再由 `FinsReadRuntime.read_section` public seam 精确转换为 `FinsReadArgumentError`；测试只观察该 public runtime failure，不直接断言 fixture 或其 `KeyError`。不得断言 processor 私有状态、父标题调用次数或其它偶然顺序。 |
+| 3. table public payload projection | `test_get_table_projects_self_describing_data_shapes_and_rejects_unknown_ref` | `FinsReadRuntime.get_table` public seam | 通过同类 repository-backed typed processor inputs 分别给出 records、合法 Markdown 与普通文本；断言 public `data.kind` 及各 shape exact keys/values、table identity/citation。对于未知 `table_ref` 输入，typed fixture 的 `read_table` 必须抛 `KeyError`，再由 `FinsReadRuntime.get_table` public seam 精确转换为 `FinsReadArgumentError`；测试只观察该 public runtime failure，不直接断言 fixture 或其 `KeyError`。typed fixture 只提供协议输入，不得成为被断言对象；不得读 processor private method/state。 |
```

## 4. Finding closure 与拒绝项保持

| 裁决项 | 处理 | 状态 |
|---|---|---|
| `R08-CR-PCPR-F01` candidate 2 | 明确未知 section ref 时 fixture `read_section` 抛 `KeyError`，由 `FinsReadRuntime.read_section` 转换；只观察 public failure | CLOSED |
| `R08-CR-PCPR-F01` candidate 3 | 明确未知 table ref 时 fixture `read_table` 抛 `KeyError`，由 `FinsReadRuntime.get_table` 转换；只观察 public failure | CLOSED |
| DS M1 | 不接受、不修改 candidate 1 | NOT IMPLEMENTED |
| DS L1-L3 | 不接受、不增加解释、白名单或 stop rule | NOT IMPLEMENTED |

以下边界保持逐字结构与执行语义不变：五候选顺序、五个 exact node names、增量 coverage
ledger、首次 whole-file `>=80.00%` 立即停止、五候选耗尽 stop、path/symbol allowlist、§4 product
contract、R07 no-touch、Host truncation owner、retained security、R09-R12 与 Issues
142/151/175/177/178 deferred 边界。

## 5. 路径、protected tree 与 staged 证据

本 turn authored paths 精确为 2 条：

```text
docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-review-fix-codex.md
```

- protected changed paths：`23`；本 turn 导致的 protected drift：`0`。
- protected diff before / after 精确相同，均为 `7a7ebf...1d6d`。
- staged paths：空。
- 进入本 turn 前已有的 product/test/README changes 与 S1/S2/previous correction artifacts 保持原样；
  它们不是本 turn authored delta。
- control、design、两路 review、Controller adjudication 与其它 prior artifacts 无本 turn 修改。

最终 `git status --short --untracked-files=all`：

```text
 M dayu/fins/README.md
 M dayu/fins/domain/financial_result_contract.py
 M dayu/fins/domain/xbrl_result_contract.py
 M dayu/fins/pipelines/sec_fiscal_fields.py
 M dayu/fins/processors/bs_report_form_common.py
 M dayu/fins/processors/bs_six_k_processor.py
 M dayu/fins/processors/financial_base.py
 M dayu/fins/processors/html_financial_statement_common.py
 M dayu/fins/processors/report_form_financial_statement_common.py
 M dayu/fins/processors/sec_processor.py
 M dayu/fins/processors/sec_xbrl_query.py
 M dayu/fins/processors/six_k_form_common.py
 M dayu/fins/tools/fins_tools.py
 M dayu/fins/tools/read_runtime.py
 M dayu/fins/tools/read_runtime_helpers.py
 M dayu/fins/tools/result_types.py
 M docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
 M tests/README.md
 M tests/fins/test_financial_read_contracts.py
 M tests/fins/test_fins_read_runtime.py
 M tests/fins/test_fins_storage_provider.py
 M tests/fins/test_processor_read_consistency.py
 M tests/fins/test_read_runtime_semantic_ownership_guards.py
 M tests/fins/test_sec_pipeline_download.py
?? docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-codex.md
?? docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-review-fix-codex.md
?? docs/reviews/wu-semantic-ownership-01-r08-s1-implementation-codex.md
?? docs/reviews/wu-semantic-ownership-01-r08-s2-cumulative-implementation-codex.md
```

## 6. Validation

- entry plan hash：PASS，精确匹配 `86bb76c...fa65`。
- final plan hash：PASS，`a79268ea...a02`。
- protected binary diff hash before / after：PASS，均为 `7a7ebf...1d6d`。
- `git diff --check`：PASS，无输出。
- 两条 authored doc paths whitespace check：PASS，无 whitespace error。
- `git diff --cached --name-only`：PASS，空。
- tests / pyright / Ruff：未运行；本 gate 只修计划 finding，不实现测试或代码。

## 7. Handoff

停止回 Controller。下一未完成 gate 是 Controller validation 后的 AgentMiMo / AgentDS 两路完整
corrected-plan re-review；不得进入 test implementation、code re-review、aggregate deepreview、
accepted-plan commit、R09-R12、push 或 PR。
