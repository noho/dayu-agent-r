# WU-SEMANTIC-OWNERSHIP-01 R08 Candidate Exhaustion Implementation Controller Authorization

## 1. Authorization

本 artifact 授权既有 umbrella WU 内 R08 的 candidate-exhaustion implementation continuation；
不是新 WU，也不是新 slice。Accepted plan commit 为
`65fd8d5c852e1baf6ad8173e9eddf353ffe6b3b5`，最终计划 SHA-256 为
`0145d1de9b3bbe93ff200e792a40b4e850c36346b43e80a5f6e239cac745a3e9`。

只授权 AgentCodex 执行一个生产 symbol deletion、计划规定的完整验证并新增一个 implementation
artifact。不得 commit、stage、push 或创建 PR；完成后停回 Controller 建立 immutable code-review
lock。

## 2. Re-entry locks

| 项目 | 必须匹配 |
|---|---|
| branch | `phaseflow/host-issues-control` |
| accepted plan commit | `65fd8d5c852e1baf6ad8173e9eddf353ffe6b3b5` 是 HEAD ancestor |
| final plan SHA-256 | `0145d1de9b3bbe93ff200e792a40b4e850c36346b43e80a5f6e239cac745a3e9` |
| stopped `dayu/fins + tests` diff SHA-256 | `65a924066d45b4e90f2ef2e6767b96c8ce8e4fbd2c5b1d9ea698875c94706dff` |
| `read_runtime_helpers.py` before SHA-256 | `46e87c63a6a7baac20996139203064da95e261c4ef08b04f80821215f1a50b93` |
| `read_runtime.py` SHA-256 | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` |
| guards SHA-256 | `553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d` |
| shared test SHA-256 | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` |
| staged tree | empty |

任一锁不匹配必须停止回 Controller。S1/S2 implementation artifacts 继续保持原样、untracked、
no-touch；不能 stage 或重写。

## 3. Exact implementation allowlist

唯一生产改动：

```text
删除 dayu/fins/tools/read_runtime_helpers.py::_collect_available_document_types 的完整定义
```

不得修改该文件中的其它 symbol/import；不得修改
`resolve_document_type_for_source`、`dayu/fins/tools/read_runtime.py`、tests、README、config、
control/design/prior review/S1/S2 artifacts。不得增加 wrapper、alias、re-export、caller、兼容分支、
coverage node、skip/xfail/pragma/omit 或下游 fallback。

唯一新 artifact 路径为：

```text
docs/reviews/wu-semantic-ownership-01-r08-candidate-exhaustion-implementation-codex.md
```

## 4. Required execution order

1. 复核 §2 全部 re-entry locks。
2. 删除唯一 private dead helper，并立即按最终计划 §6.7.G 执行 source/AST proof：旧 helper
   definition/caller/import 全零；actual owner definition/caller、typed input/output、
   `resolve_document_type_for_source` 调用与 sorted 返回保持。
3. 记录 `read_runtime.py` SHA 保持不变，guards/shared tests 保持内容锁；确认除允许的 helper
   deletion 外没有新 product/test/README delta。
4. 从 `coverage erase` 开始运行最终计划 §6.6 的 exclude-candidate-5 proof；必须精确为
   `382/482 = 79.25% < 80.00%`。
5. 再次 `coverage erase`，运行 all-five proof；必须至少为
   `388/482 = 80.50% >= 80.00%`。
6. 两个 proof 通过后再次 `coverage erase`，从零完整运行最终计划 §6.6/§6.7：全部 focused、
   aggregate、full Fins tests，forced-truncation/AAPL/HTML/no-statement real smokes，15-file
   exact-key whole-file coverage，full pyright，scoped Ruff，source/AST/LLM/README/security/
   unique-count/no-touch scans 与 `git diff --check`。
7. 检查 README triggers；本 delta 是 private dead-helper deletion，不修改 README。
8. 写 implementation artifact，记录每条命令、exit/result、coverage numerator/denominator、warnings、
   final path/content/diff hashes、README decision 与 residual risks。不得把旧 incremental ledger 或
   旧 validation/review 当作本 tree 的通过证据。

任一 exact proof 或完整 gate 失败时，保留现场证据并停回 Controller；不得修改 tests、增加第六
node、降低阈值、扩大 production allowlist 或只重跑失败子集后宣称通过。

## 5. Handoff

AgentCodex 完成且全部验证通过后，Controller 将独立复核锁、受影响测试、coverage、pyright、Ruff、
scans 和 diff，再建立新的 cumulative immutable review lock，派发 AgentMiMo/AgentDS 双路完整 code
review。Implementation 本身不授权 code review、accepted implementation commit、aggregate deepreview
或 R09-R12。
