# WU-SEMANTIC-OWNERSHIP-01 R08 Coverage Statement Drift Controller Adjudication

## 1. Gate 与结论

本轮仍是既有 umbrella WU 内 R08 的 candidate-exhaustion continuation，不是新 WU 或新 slice。
AgentCodex 正确执行 fail-closed stop：唯一 dead-helper deletion 与 source/AST owner proof 已完成，但
第一个 fresh coverage proof 实测为 `381/485 = 78.56%`，不等于 accepted plan 的
`382/482 = 79.25%`，因此没有继续 all-five/完整 acceptance gate。

Controller 以独立 coverage data file 运行只读 all-five 诊断，结果为
`387/485 = 79.79381443%`（`391 passed, 3 existing edgartools warnings`）。Coverage JSON 的
display rounding 虽显示 `80`，精确值仍低于 `80.00%`，不能接受为过线。

**Decision：ACCEPTED NEW PLAN FINDING `R08-CR-PCF03`。**

保留语义正确的 dead-helper deletion；回到同一 R08 的 plan-only correction。计划须新增且只新增
一个稳定 owner test（candidate 6），不得降低阈值、恢复 shared compatibility tests、增加 fake/private
test、删除更多生产代码或扩大其它 scope。

## 2. Protected stopped tree

| 项目 | Controller 复核值 |
|---|---|
| AgentCodex stop artifact | `docs/reviews/wu-semantic-ownership-01-r08-candidate-exhaustion-implementation-codex.md` |
| stop artifact SHA-256 | `7ef50fc542e5a630690fb88d2d5f86cf05fb4750c6bea2c6afa47f89a0d7d370` |
| stopped cumulative `dayu/fins + tests` diff | `3d9df8fefc485d0d19421fe6d2a3fe0402bf6f27d3b821d51125e039fa52ddf0` |
| `read_runtime_helpers.py` after deletion | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` |
| `read_runtime.py` actual-owner source | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657`，未变 |
| guards test | `553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d`，未变 |
| shared runtime test | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692`，未变 |
| S1 artifact | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748`，未变 |
| S2 artifact | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648`，未变 |
| staged | empty |
| `git diff --check` | PASS |

Agent candidate-4 JSON：
`workspace/tmp/r08-candidate-4-proof-coverage.json`，SHA-256
`f6f72ca0946a743d85ca89cfa7b1c108d0965bf74aeeef44000cf600c2c38b6e`。

Controller all-five JSON 使用独立 coverage data file，未覆盖 Agent `.coverage`：
`workspace/tmp/r08-controller-all-five-coverage.json`，SHA-256
`08e7a3c8a552b3d863b3bd5e0304642630ff26c094f2e7e73179d889d70fb811`；coverage data SHA-256
`475590a2b188e43ce28a3cef9aa97ca133be9056e9b6fa76a2e94cf0770c4710`。

## 3. Root cause

此前把源文件 `409..420` 的行跨度误当成 12 个 coverage statements。Fresh JSON 直接证明旧 helper
在 coverage.py 中实际贡献 9 个 statements：

- definition 行在模块 import 时执行，属于 1 个 **covered** statement；
- dead body 中只有 8 个 **missing** statements；
- 注释、docstring 与 multi-line call 的参数行不是独立 statements。

因此删除后的机械变化是：

```text
all-five: 388/494
delete one covered definition + eight missing body statements
=> 387/485 = 79.79381443% < 80.00%
```

Candidate 1-4 同理实测为 `381/485`。这不是产品失败，也不否定 deletion：旧 helper 的
definition/caller/import 已证明为 `0/0/0`，实际
`read_runtime.py::_collect_available_document_types_for_source_documents` 仍是唯一 typed/sorted
owner。失败只证明 plan 的 coverage arithmetic 与五候选 sufficiency 假设不成立。

## 4. Accepted finding `R08-CR-PCF03`

`read_runtime_helpers.py` 当前 all-five missing-lines 直接显示实际 business owner
`resolve_document_type_for_source` 的三个稳定分类分支仍未覆盖：

| Missing line | Owner contract |
|---|---|
| `_resolve_document_type: return "material"` | 未知 material form 归为通用 `material` |
| `_resolve_document_type: return "other"` | filing 无 form 时归为 `other` |
| `_resolve_document_type: return _CN_FORM_TYPE_TO_DOCUMENT_TYPE[form_type]` | CN/HK fiscal form `FY` 归为 `annual_report` |

`resolve_document_type_for_source` 是无下划线的 production owner helper，在
`read_runtime.py` 有两个真实调用点；它不是 dead/private test seam，也不是 compatibility behavior。
这三个分支直接决定 LLM-facing `document_type`，符合 AGENTS.md 的 owner-level contract test 要求。

计划须在既有
`tests/fins/test_read_runtime_semantic_ownership_guards.py` 新增 exact candidate 6：

```text
test_document_type_resolver_projects_material_other_and_cn_categories
```

并只增加 `resolve_document_type_for_source` 的显式 import。测试必须有完整中文 docstring，并精确断言：

```python
resolve_document_type_for_source(
    form_type="UNLISTED_MATERIAL",
    source_kind=SourceKind.MATERIAL.value,
) == "material"
resolve_document_type_for_source(
    form_type=None,
    source_kind=SourceKind.FILING.value,
) == "other"
resolve_document_type_for_source(
    form_type="FY",
    source_kind=SourceKind.FILING.value,
) == "annual_report"
```

不得直接测试 `_resolve_document_type`，不得读取映射常量，不得用 fake repository、monkeypatch、
compatibility input、参数化 omnibus 或 coverage-only empty execution。该 node 只消费唯一 public owner
并断言三条业务分类语义。

## 5. Corrected proof sequence

新计划必须：

1. 保留 dead-helper deletion、actual owner/source proof、原五个 tests、shared-file no-touch 与
   whole-file exact-key `>=80.00%`。
2. 把旧 `382/482` / `388/482` 假设标为 superseded，不得再作为 stop/acceptance 值。
3. 以 fresh all-five proof 精确复现 `387/485 = 79.79381443% < 80.00%`。
4. 实现 candidate 6 后再次 fresh proof；三条当前 missing owner branches 应使结果达到
   `390/485 = 80.41237113% >= 80.00%`。任一 numerator/denominator/阈值关系漂移仍 fail closed 回
   Controller。
5. Candidate 6 是新的 first/shortest threshold-crossing prefix；过线后停止新增测试，再次
   `coverage erase` 并从零执行原 §6.6/§6.7 完整 acceptance validation。
6. Guards hash 将在 implementation gate 被允许改变；shared test、README、其它 tests、其它
   production、S1/S2 artifacts 继续 no-touch。

## 6. Rejected alternatives

| Alternative | Decision |
|---|---|
| 接受 coverage display rounding 的 `80` | REJECTED：精确值 `79.79381443% < 80.00%` |
| 降低 whole-file threshold 或改 aggregate/changed-line threshold | REJECTED：违反 AGENTS.md 与 accepted gate |
| 恢复 shared compatibility/omnibus tests 或新增 fake/private-helper test | REJECTED：重开已关闭 `R08-CR-CF01` |
| 再删除其它 production/dead branches以缩小分母 | REJECTED：无当前语义 owner 证据，扩大生产 allowlist |
| 直接测试 private `_resolve_document_type` 或 mapping constants | REJECTED：测试下游实现细节，不是 public owner contract |
| 增加多个 coverage nodes或追求 100% | REJECTED：一个三断言 owner node 已有直接 missing-line 闭环 |
| 回滚正确的 dead-helper deletion | REJECTED：会恢复第二个不可达 producer |

## 7. Next gate

AgentCodex 只允许 plan-only correction：修改唯一最终计划并新增 plan-correction artifact；当前
product/test/README/S1/S2 tree 保持 immutable。Controller validation 后须再次双路完整 plan review；
任何 accepted finding 仍须 plan fix/re-review。新计划 accepted local commit 前不得实现 candidate 6、
运行 acceptance gate、进入 code review/deepreview 或提交产品代码。
