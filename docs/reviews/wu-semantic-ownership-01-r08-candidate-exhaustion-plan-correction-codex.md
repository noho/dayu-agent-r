# WU-SEMANTIC-OWNERSHIP-01 / R08 Candidate Exhaustion Plan Correction — AgentCodex

## 1. Gate 结论

- umbrella：`WU-SEMANTIC-OWNERSHIP-01`
- remediation：既有 `R08`，不是新 WU、feature、issue 或独立 sub-WU
- gate：candidate exhaustion plan correction / plan-only
- accepted finding：`R08-CR-PCF02`
- 状态：`COMPLETED — READY FOR CONTROLLER VALIDATION AND COMPLETE DUAL PLAN REVIEW`
- 最终计划真源：`docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`
- correction 前 plan SHA-256：`a79268ea8d45f6af8854859269ce3592506f753272c32ecffab76d765cad7a02`
- correction 后 plan SHA-256：`0145d1de9b3bbe93ff200e792a40b4e850c36346b43e80a5f6e239cac745a3e9`

本轮只修改最终计划并新增本 artifact。没有实施 production/test/README 变更，没有修改
control、design、S1/S2 artifacts 或 prior review artifacts，没有 stage、commit、push 或创建 PR。

## 2. Re-entry 与 stopped-tree locks

修改计划前现场独立重算；Controller 随后确认派发文字中的 plan 路径和 shared hash 是摘录笔误，
并授权按下列实际真源继续：

| 项 | 现场值 | 结果 |
|---|---|---|
| branch | `phaseflow/host-issues-control` | PASS |
| final plan truth path | `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md` | PASS |
| accepted plan entry SHA-256 | `a79268ea8d45f6af8854859269ce3592506f753272c32ecffab76d765cad7a02` | PASS |
| stopped `git diff --binary -- dayu/fins tests` SHA-256 | `65a924066d45b4e90f2ef2e6767b96c8ce8e4fbd2c5b1d9ea698875c94706dff` | PASS |
| guards SHA-256 | `553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d` | PASS |
| shared `test_fins_read_runtime.py` SHA-256 | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` | PASS |
| `read_runtime.py` SHA-256 | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` | evidence lock |
| staged paths | empty | PASS |
| correction-entry `git diff --check` | no output | PASS |

Stopped artifact 保留的旧 incremental ledger 为：

```text
320/494 = 64.78%
340/494 = 68.83%
352/494 = 71.26%
371/494 = 75.10%
382/494 = 77.33%
388/494 = 78.54%
```

它证明五个授权 candidate 已形成完整连续前缀并触发 exhaustion stop；它不作为删除 dead helper
后的 acceptance evidence。

## 3. 第一性原理与直接 owner 证据

`R08-CR-PCF02` 的动机成立。当前 source/AST scan 得到：

```text
_collect_available_document_types: definition=1, caller=0, import=0
```

唯一 definition 位于 `dayu/fins/tools/read_runtime_helpers.py`，函数体共 12 个 executable
statements，final coverage 全部 missing。实际 public `list_documents` suggestion path 是：

```text
FinsReadRuntime.list_documents
  -> read_runtime.py::_collect_available_document_types_for_source_documents
  -> resolve_document_type_for_source
  -> return sorted(doc_types)
```

actual owner 使用 `list[_SourceDocumentSummary] -> list[str]` typed contract，并有一个 production
caller。旧 helper 不参与该路径，却重复产生同一“可用文档类型”业务事实。为 dead private helper
补 direct test 会固化第二 owner；增加第六个业务无关 test、恢复 compatibility/omnibus tests、
降低 80% threshold 或使用 pragma/omit/fake/empty execution 都只会掩盖根因。最小且正确的修复是
在重复 owner boundary 删除旧 helper，同时保持 actual typed/sorted owner不变。

数学闭包保持直接可验：

- 排除 candidate 5：`382 / (494 - 12) = 382/482 = 79.25% < 80.00%`；
- 包含全部五项：`388 / (494 - 12) = 388/482 = 80.50% >= 80.00%`。

因此五项完整连续前缀仍应是 first/shortest threshold-crossing prefix；无需第六节点，也不能删除
五项中的任何一项。

## 4. 最终计划修改

最终计划已在以下 owner/gate 边界吸收 accepted finding：

1. §0/§1/§2/§3：更新 candidate-exhaustion gate、stopped locks、第一性原理、唯一 owner、完成定义与 out-of-scope；明确只删一个 dead duplicate。
2. §6.1：把 re-entry 更新为 `65a...6dff` / guards `5531...928d` / shared `01db...6692` / staged empty；把本次唯一 production delta 与 test immutability 写成硬授权。
3. §6.2/§6.5：固定实施顺序为“匹配锁→删除 helper→source/AST proof→两个 fresh coverage proof→全量重跑”；旧 ledger 只作 stopped-tree evidence。
4. §6.6：新增排除 candidate 5 的 fresh `382/482=79.25%` proof，以及包含全部五项的 fresh 至少 `388/482=80.50%` proof；两次均从 `coverage erase` 开始，并在达标后再次从零执行原完整 acceptance matrix。
5. §6.7：保留 shared-file/compatibility/private-helper/fake/bypass guards；新增旧 helper definition/caller/import 全零和 actual typed/sorted owner仍存在的 source/AST scan。
6. §6.8：执行 README trigger check；private dead helper 删除无用户 contract 变化，不机械修改 README。
7. §6.9/§7/§8/§9：更新 immutable review handoff、aggregate audit、stop conditions 与 code-generation checklist。
8. §10：更新本 plan-only gate 的 authored paths、before hash、stopped locks 与交付要求。

§4 financial/XBRL product contracts、S1/S2 累计 destructive cutover、R07 no-touch、Host truncation
owner、Topic 8/9 no-code 裁决均未改变。

## 5. 下一 implementation gate 的精确边界

### 5.1 唯一生产改动

只允许删除：

```text
dayu/fins/tools/read_runtime_helpers.py::_collect_available_document_types
```

禁止修改：

- `resolve_document_type_for_source`；
- `dayu/fins/tools/read_runtime.py::_collect_available_document_types_for_source_documents`；
- 其它 production symbol、README、tests、S1/S2 artifacts、control/design/prior artifacts。

禁止为旧 helper 建 wrapper、alias、re-export、caller、兼容分支或下游补偿。

### 5.2 测试与 coverage 边界

- Whole-file exact-key threshold 保持 `>=80.00%`，不得改为 changed-line/aggregate threshold。
- 五个已授权 exact tests 全部保留，guards 内容锁保持 `55318914...928d`。
- Shared `test_fins_read_runtime.py` 保持 `01db5538...6692`，四个已删 nodes 与九 imports 不恢复、改名、参数化或搬运。
- 禁止 compatibility test、private-helper direct test、fake-only test、omnibus test、skip/xfail、coverage pragma/omit 或其它 bypass。
- 删除后先从零运行 exclude-candidate-5 proof，预期精确 `382/482=79.25%<80`；再从零运行 all-five proof，预期至少 `388/482=80.50%>=80`。
- 两个 proof 共同证明五项仍是 first/shortest threshold-crossing prefix；随后再次清空 coverage，从零执行原计划 §6.6/§6.7 全部 focused、aggregate、full Fins、real smoke、15-file exact-key coverage、full pyright、scoped Ruff、source/AST/LLM/README/security/no-touch 与 diff checks。

### 5.3 README 与 scope

README trigger 必须检查，但删除 private dead helper 不改变用户可见 contract，故不机械修改
README。R09-R12、Issues 142/151/175/177/178、统一 authorization、Host/Engine/Service/UI 与其它
production cleanup 继续 out-of-scope；不得触碰或重写 S1/S2 artifacts。

## 6. 本 plan-only gate 验证

| 验证 | 结果 |
|---|---|
| final plan SHA-256 | `0145d1de9b3bbe93ff200e792a40b4e850c36346b43e80a5f6e239cac745a3e9` |
| stopped cumulative diff before/after | `65a924066d45b4e90f2ef2e6767b96c8ce8e4fbd2c5b1d9ea698875c94706dff` / same |
| guards before/after | `553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d` / same |
| shared test before/after | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` / same |
| staged paths | empty |
| authored doc paths | 2：最终计划 + 本 artifact |
| `git diff --check` | PASS，无输出 |
| 两条 authored doc paths trailing-whitespace scan | PASS，无输出 |
| tests / pyright / implementation | 未运行；本 gate 为 plan-only，且明确禁止 implementation |

本 artifact 自身不能在自身内容中嵌入最终 SHA-256 而保持该值不变；写入完成后由外部命令重算，
并在 Controller handoff 中报告。

## 7. Stop 与 next gate

本 gate 到此停止。下一 gate 只能是 Controller plan-diff/protected-tree validation，随后由
AgentMiMo / AgentDS 对完整最终计划做双路 review；若有 accepted finding，仍须 plan fix/re-review。
新计划 accepted local commit 前，不得删除 helper、运行 implementation validation、进入 code
re-review/aggregate deepreview、修改 control、commit、push 或创建 PR。
