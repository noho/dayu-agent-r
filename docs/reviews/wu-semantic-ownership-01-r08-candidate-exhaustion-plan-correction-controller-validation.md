# WU-SEMANTIC-OWNERSHIP-01 R08 Candidate Exhaustion Plan Correction Controller Validation

## 1. 结论

**PASS / READY FOR DUAL COMPLETE PLAN REVIEW。**

本次是既有 umbrella WU 内 R08 的 plan-only correction，不是新 WU。AgentCodex 已把
`R08-CR-PCF02` 写入唯一最终计划真源，且没有修改 stopped product/test/README tree、control、
既有 review artifacts 或 S1/S2 implementation artifacts，也没有 stage 或 commit。

## 2. 验证对象与锁

| 项目 | Controller 复核结果 |
|---|---|
| 最终计划 | `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md` |
| correction 前计划 SHA-256 | `a79268ea8d45f6af8854859269ce3592506f753272c32ecffab76d765cad7a02` |
| correction 后计划 SHA-256 | `0145d1de9b3bbe93ff200e792a40b4e850c36346b43e80a5f6e239cac745a3e9` |
| AgentCodex artifact | `docs/reviews/wu-semantic-ownership-01-r08-candidate-exhaustion-plan-correction-codex.md` |
| AgentCodex artifact SHA-256 | `5bd1c191bf7a4bcd8544c8d4076211e53a24c1b30868fb44f819f46c4f8862dc` |
| stopped `dayu/fins + tests` binary diff | `65a924066d45b4e90f2ef2e6767b96c8ce8e4fbd2c5b1d9ea698875c94706dff`，保持 |
| guards test | `553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d`，保持 |
| shared runtime test | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692`，保持 |
| actual owner source | `dayu/fins/tools/read_runtime.py` SHA-256 `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657`，本 gate 未改 |
| staged tree | empty |
| `git diff --check` | PASS，无输出 |

AgentCodex 本 gate 的 authored delta 精确为最终计划与新 correction artifact 两条路径。工作区
其余 modified/untracked 路径继续是 umbrella R08 的受保护累计实现与既有 S1/S2 artifacts；不能被
视为本 gate 新写入，也不得删除、覆盖或提交进 plan-only commit。

## 3. 计划内容复核

最终计划已经 code-generation-ready 地固定：

1. 唯一生产改动是删除
   `dayu/fins/tools/read_runtime_helpers.py::_collect_available_document_types` 的完整定义；禁止修改
   `resolve_document_type_for_source`、实际 owner
   `read_runtime.py::_collect_available_document_types_for_source_documents` 或任何其它生产 symbol。
2. 五个已授权 stable-owner tests、guards/shared-file 内容锁与 whole-file exact-key `>=80.00%`
   阈值保持不变；禁止 compatibility/private-helper direct/fake/omnibus test、skip/xfail、coverage
   pragma/omit 或第六个 coverage-padding node。
3. 删除后必须先用 source/AST scan 证明旧 helper definition/caller/import 全零，并证明实际
   typed/sorted owner 的 definition/caller、输入输出类型、shared resolver 调用和 sorted 返回仍在。
4. 两次 coverage proof 各自从 `coverage erase` 开始：排除 candidate 5 必须为
   `382/482 = 79.25% < 80.00%`；包含全部五项必须至少为
   `388/482 = 80.50% >= 80.00%`。两者共同证明完整五项仍是 first/shortest threshold-crossing
   prefix。
5. 两次 proof 通过后必须再次清空 coverage，从零执行原 §6.6/§6.7 的完整 acceptance validation；
   stopped-tree incremental ledger 不得复用为新 tree 的通过证据。
6. README trigger 已明确检查；单一 private dead-helper 删除不改变用户 contract，因此本
   continuation 不机械修改 README。
7. R09-R12、Issues 142/151/175/177/178、统一 tool authorization、其它 dead-code cleanup 与
   S1/S2 artifacts 都保持 out-of-scope/no-touch。

## 4. 直接代码证据复核

Controller 对当前 stopped tree 的只读复核确认：旧 private helper 只有一个定义，没有 caller 或
import；实际 list-documents suggestion owner 位于 `read_runtime.py`，接受 typed
`list[_SourceDocumentSummary]`，调用 `resolve_document_type_for_source` 并返回
`sorted(doc_types)`。因此删除重复且不可达的 producer 是 owner-boundary root fix；增加测试、直测
private dead helper、降低 coverage gate 或引入兼容 shim 均不是可接受修复。

## 5. 下一 gate

只授权 AgentMiMo 与 AgentDS 对 SHA-256
`0145d1de9b3bbe93ff200e792a40b4e850c36346b43e80a5f6e239cac745a3e9` 的完整最终计划并发
`/planreview`。Reviewer 必须核对完整累计计划，而不是只审新增段落。任何 accepted finding 仍须由
AgentCodex plan-only fix 并双路 re-review；计划 accepted local commit 前不得删除 helper、运行
implementation validation、进入 code review/deepreview 或提交产品代码。
