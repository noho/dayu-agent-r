# WU-SEMANTIC-OWNERSHIP-01 R08 Candidate Exhaustion Controller Adjudication

## 1. Gate 与 tree lock

本裁决仍属于既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` / R08 cumulative code-review fix continuation，不是新 WU、feature、issue 或独立 sub-WU。

| 项 | Controller 独立值 |
|---|---|
| accepted corrected-plan commit | `0dc85654bb29612a547e7976f3eeb4801171f786` |
| final corrected plan SHA-256 | `a79268ea8d45f6af8854859269ce3592506f753272c32ecffab76d765cad7a02` |
| stopped implementation artifact | `docs/reviews/wu-semantic-ownership-01-r08-test-only-code-review-fix-codex.md` |
| stopped artifact SHA-256 | `620bde13307b341d99c2e3c65bf523fc9e97753adef1997e51aed5d4b1f2acdb` |
| cumulative `dayu/fins + tests` binary diff SHA-256 | `65a924066d45b4e90f2ef2e6767b96c8ce8e4fbd2c5b1d9ea698875c94706dff` |
| guards SHA-256 | `553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d` |
| shared `test_fins_read_runtime.py` SHA-256 | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` |
| staged paths | empty |
| `git diff --check` | PASS，无输出 |

AgentCodex 正确执行了强制 stop：五个授权 candidate 形成完整连续前缀，最后一次 incremental set 为 `391 passed`，但 `read_runtime_helpers.py` 只有 `388/494 = 78.54%`；没有越界增加第六节点、降低阈值、修改 production 或伪称最终 §6.6/§6.7 已通过。

## 2. 第一性原理与直接代码证据

### 2.1 计划假设已被实测否定

两路 plan review 对五候选 coverage 的估算高于真实执行结果。真实 ledger 是：

```text
320/494 = 64.78%
340/494 = 68.83%
352/494 = 71.26%
371/494 = 75.10%
382/494 = 77.33%
388/494 = 78.54%
```

因此 final corrected plan 的“候选足以过线”假设不成立；这不是测试失败，也不是产品裁决矛盾，而是新的 plan/code evidence，Controller 可在同一 R08 内修正。

### 2.2 Root owner 是重复且不可达的 private helper

Controller 在 final `.coverage` 上核对 missing lines：`read_runtime_helpers.py:409-420` 共 12 个 executable statements 全部未覆盖，对应 private `_collect_available_document_types` 的完整函数体。

Production/source scan：

```text
rg '_collect_available_document_types\(' dayu tests
dayu/fins/tools/read_runtime_helpers.py:393:def _collect_available_document_types(...)
```

除定义外零 caller、零 import。实际 public `list_documents` suggestion path 使用唯一 typed owner：

```text
FinsReadRuntime.list_documents
  -> read_runtime.py::_collect_available_document_types_for_source_documents
  -> resolve_document_type_for_source
  -> return sorted(doc_types)
```

因此不能为死 helper 写测试或增加第六个 coverage node。保留两个相同业务事实的 private producers 违反唯一语义 owner；删除无 caller 的 helper 才是 root-cause 修复。

### 2.3 数学闭包

删除 12 个全部未覆盖的 executable statements 后：

- candidate 4 截止点：`382 / (494 - 12) = 382/482 = 79.25%`，仍未过线；
- candidate 5 完整前缀：`388 / 482 = 80.50%`，首次过线。

所以当前五节点完整连续前缀仍是机械最短前缀；不删除任何已有 stable-owner test，也不增加第六节点。

## 3. Accepted finding

### `R08-CR-PCF02` — dead duplicate document-type collector blocks honest whole-file coverage

**ACCEPTED / requires plan correction before production mutation.**

Plan correction 必须精确授权：

1. 保持 whole-file `>=80.00%`、五个 tests、shared-file deletion boundary 与所有 compatibility/private/fake/coverage-bypass 禁止。
2. 在既有 production allowlist 内只删除 `dayu/fins/tools/read_runtime_helpers.py::_collect_available_document_types`；不得改 `resolve_document_type_for_source` 或 `read_runtime.py::_collect_available_document_types_for_source_documents`。
3. 增加 source/AST scan，证明旧 helper 定义/caller/import 零存在，public suggestion 仍只由 typed read-runtime owner 产生并保持 sorted output。
4. 删除后从零运行一个 exclude-candidate-5 coverage proof，机械证明 candidate 4 为 `382/482 <80%`；再运行包含 candidate 5 的完整 incremental set，证明 `>=80%`。不得用历史估算代替新 tree 实测。
5. 过线后从零完整执行 §6.6/§6.7 全部 acceptance gates；旧 incremental sessions 只作 stopped-tree evidence，不作最终通过证据。
6. README trigger 必须检查；private dead helper 删除无用户契约变化时不机械修改 README。

## 4. Explicitly rejected alternatives

| alternative | 裁决 |
|---|---|
| 增加第六个 test/family | REJECTED：没有新的业务 owner 需求，属于 coverage padding |
| 直接测试 `_collect_available_document_types` | REJECTED：为零 caller 死代码制造测试，固化重复 owner |
| 恢复/搬运原四 shared-file tests 或九 imports | REJECTED：重开 `R08-CR-CF01` compatibility/omnibus 越界 |
| 降低 80% threshold、omit/pragma | REJECTED：弱化 AGENTS.md 验收 |
| 删除已实现 candidate 1-5 中任一节点 | REJECTED：按新 denominator，candidate 4 仍低于 80%，candidate 5 才首次过线 |
| 顺手清理其它 missing branches/dead code | REJECTED：没有当前 code evidence/owner necessity，扩大 scope |

## 5. Next gate

当前 gate 回到同一 R08 的 plan-only correction。AgentCodex 只允许修改 final plan 并新增 plan-correction artifact，不得修改 stopped product/test tree、README、control、prior artifacts。Controller validation 后必须由 AgentMiMo/AgentDS 对完整计划并发 review；任何 accepted finding 仍须 fix/re-review。只有新 plan accepted local commit 后，才可授权 AgentCodex 删除该单一 dead helper 并完成全量验证。

R09-R12、Issues 142/151/175/177/178、统一 authorization、其它 production cleanup、Host/Engine/Service/UI、push 与 PR 继续未授权。
