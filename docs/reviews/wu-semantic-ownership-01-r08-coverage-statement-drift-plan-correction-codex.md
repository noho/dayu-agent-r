# WU-SEMANTIC-OWNERSHIP-01 R08 Coverage Statement Drift Plan Correction

## 1. Gate 结论

本轮是既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 内 R08 的 coverage-statement drift
plan-only correction，不是新 WU、slice 或 implementation gate。

Accepted finding `R08-CR-PCF03` 已完整写入唯一最终计划。修改仅涉及最终计划与本 artifact；
没有实现 candidate 6，没有修改 product/tests/README/control/design/prior review/S1/S2 artifacts，
没有运行测试、coverage acceptance、pyright 或 implementation，也没有 stage、commit、push 或建 PR。

### Controller validation follow-up

Controller 直接证据成立：中间 plan SHA
`81b4eb985412513df96051dcfa9dc3e830611b5f127d19f5162eee3afc8a34d6` 的 fresh prefix-five
命令仍含 candidate 5 exact node 的 `--deselect`，所以命令实际只运行 prefix four，机械结果应回到
历史 `381/485`，不可能满足文字/checker 锁定的 `387/485`。该中间 plan 未通过 validation，不能作为
accepted plan evidence。

本 follow-up 已删除该 `--deselect` 与前一 test path 的残留续行符，并把两个 proof 命令的集合不变量
写回 `§6.6`：

- prefix-five 在 guards 仍为 entry hash、candidate 6 尚不存在时整文件收集，且无任何 deselect，
  因此包含原五个 exact nodes；
- prefix-six 在 candidate 6 exact node/import 写入 guards 后收集同一 tests 文件集合，且无任何
  deselect，因此包含原五项与 candidate 6 共六项。

本 artifact follow-up 前 SHA-256 为
`889b886e92687f69bf18f765e73e8ae4278c541c1171844718c7905d17129aa3`；final artifact SHA-256
由完成本文件写入后的只读 handoff 计算并报告，不在文件内自引用。

## 2. 第一性原理与 root evidence

修正动机成立。直接 coverage JSON 证明旧计划把源文件行跨度误当成 coverage statements：

- dead helper 在 coverage.py 中是 1 个 covered definition statement 加 8 个 missing body
  statements，共 9 statements；不是 12 statements；
- deletion 正确且必须保留；旧 helper definition/caller/import 已为 `0/0/0`；
- actual owner 仍是
  `read_runtime.py::_collect_available_document_types_for_source_documents`，保持
  `list[_SourceDocumentSummary] -> list[str]`、调用 `resolve_document_type_for_source` 并返回
  `sorted(...)`；
- Controller all-five 只读诊断为 `387/485 = 79.79381443% < 80.00%`。它只作计划根因证据，
  不能冒充 implementation acceptance；
- 旧 `382/482 = 79.25%` 与 `388/482 = 80.50%` 预测均已明确标记 superseded。

因此 root fix 不是回滚 deletion、降低 whole-file threshold、恢复 compatibility/omnibus tests 或继续
删除 production，而是对无下划线 production owner `resolve_document_type_for_source` 增加一个最小
owner-contract node，覆盖当前三个稳定 missing business branches。

## 3. 修改段落

唯一最终计划已修正以下段落：

1. `§0-§1`：更新 gate、before-plan SHA、stopped tree locks、accepted finding 与直接 root evidence。
2. `§2-§3`：保留正确 deletion、actual owner、原五项测试、shared no-touch 与 whole-file exact-key
   `>=80.00%`；删除“五项不可变/无 test delta/candidate 5 first-prefix”的旧指令。
3. `§6.1-§6.5`：把当前 continuation 收敛为无 production delta、guards-only candidate 6 delta；
   补齐 exact node、唯一 import、中文 docstring、三条业务断言和全部禁止事项。
4. `§6.6`：用 fresh prefix-five/prefix-six exact proof 替代 candidate-4/candidate-5 proof；任一
   numerator、denominator 或 threshold relation drift 均 fail closed。
5. `§6.7-§6.9`：更新 guards import/node AST proof、stopped-tree exact diff、retained deletion/source
   proof、README no-update 与后续 immutable review 顺序。
6. `§7-§10`：更新 aggregate deepreview checklist、stop conditions、implementation handoff 与本
   plan-only gate 的 authored-path/hash 自检。

## 4. 后续 accepted implementation 的唯一边界

本轮不执行下列动作；它们只有在 corrected plan 完成 Controller validation、双路完整 review、必要
fix/re-review 与 accepted local plan commit 后才可实施：

- 在 `tests/fins/test_read_runtime_semantic_ownership_guards.py` 新增且只新增
  `test_document_type_resolver_projects_material_other_and_cn_categories`；
- 唯一新增 import 是 `resolve_document_type_for_source`；
- node 必须直接调用该无下划线 production owner，提供完整中文 docstring，明确参数为无、返回值为无、
  断言失败异常，并精确断言：
  - `UNLISTED_MATERIAL + SourceKind.MATERIAL.value -> material`；
  - `None + SourceKind.FILING.value -> other`；
  - `FY + SourceKind.FILING.value -> annual_report`；
- 禁止直接测试 `_resolve_document_type`、读取 mapping constants、使用 fake repository、monkeypatch、
  compatibility input、参数化 omnibus、coverage-only empty execution，或产生其它
  test/product/README delta；
- fresh prefix-five 必须先精确复现 `387/485 = 79.79381443% < 80.00%`；随后才实施 candidate 6；
  fresh prefix-six 必须精确为 `390/485 = 80.41237113% >= 80.00%`；
- candidate 6 是新的 first/shortest threshold-crossing prefix。过线后停止新增测试，再次
  `coverage erase`，从零执行完整计划 `§6.6/§6.7`；任一 drift 都停止回 Controller。

Guards hash 只允许在后续 accepted implementation gate 因 exact node与唯一 import 改变。
Shared test、README、其它 tests、其它 production、S1/S2 artifacts 始终 no-touch。

## 5. Scope 与 deferred boundary

本 correction 不改变 §4 financial/XBRL product contracts、S1/S2 原 path allowlists、R07 no-touch、
Host truncation owner 或 whole-file exact-key coverage gate。R09-R12、Issues 142/151/175/177/178、
统一 authorization 与 Topic 8-9 code 继续 out-of-scope。

## 6. Hash locks

| Lock | Before | Final |
|---|---|---|
| plan SHA-256 | `0145d1de9b3bbe93ff200e792a40b4e850c36346b43e80a5f6e239cac745a3e9` | `115a6429653e4011cf68fc9f3f7e9d7d08431696e0c1a80269c56d2de71dc401` |
| stopped `dayu/fins + tests` binary diff | `3d9df8fefc485d0d19421fe6d2a3fe0402bf6f27d3b821d51125e039fa52ddf0` | `3d9df8fefc485d0d19421fe6d2a3fe0402bf6f27d3b821d51125e039fa52ddf0` |
| `read_runtime_helpers.py` after deletion | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` |
| `read_runtime.py` actual owner | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` |
| guards | `553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d` | `553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d` |
| shared test | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` |
| S1 artifact | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` |
| S2 artifact | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` |
| staged tree | empty | empty |

## 7. Authored paths 与完整 status

本 turn authored paths 精确为两条：

```text
docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
docs/reviews/wu-semantic-ownership-01-r08-coverage-statement-drift-plan-correction-codex.md
```

最终 `git status --short --untracked-files=all` 实测精确包含以下受保护既有 tree 与本 turn 两条路径：

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
?? docs/reviews/wu-semantic-ownership-01-r08-coverage-statement-drift-plan-correction-codex.md
?? docs/reviews/wu-semantic-ownership-01-r08-s1-implementation-codex.md
?? docs/reviews/wu-semantic-ownership-01-r08-s2-cumulative-implementation-codex.md
```

## 8. 文档自检

- `git diff --check`：PASS。
- 两条 authored doc paths 的 whitespace check：PASS。
- Authored path count：`2`。
- Proof command静态审计：PASS；两段命令各含同一 8 条 test paths，`--deselect` 命中均为 0。
  当前 guards 精确存在原五个 nodes，candidate 6 命中为 0；计划顺序先运行 prefix-five，再写入
  candidate 6 node/import，最后运行收集同一 guards 文件的 prefix-six，因此后者包含六项。
- Stopped tree/owner/guards/shared/S1/S2/staged locks：全部精确匹配。
- Tests / coverage acceptance / pyright / implementation：本 plan-only gate 未运行。
- README decision：无更新；本轮不改变用户可见 contract、测试职责或分层关系。

最终状态：**PLAN CORRECTION COMPLETE / STOP FOR CONTROLLER VALIDATION AND DUAL COMPLETE PLAN REVIEW**。
