# WU-SEMANTIC-OWNERSHIP-01 P2-B Plan Review - AgentMiMo

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P2-B Host memory/test contract hardening`
- Gate: adversarial plan review
- Plan: `docs/host/wu-semantic-ownership-01-p2-b-plan.md`
- Delivery: `docs/reviews/wu-semantic-ownership-01-p2-b-plan-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p2-b-plan-controller-validation.md`
- Source adjudication: `docs/reviews/fullrepo-semantic-ownership-controller-adjudication.md`
- Design truth: `docs/host/design.md`, `docs/engine/design.md`

## Verdict

**pass-with-findings**

Plan 整体可接受，设计真源引用准确，stop condition 覆盖关键风险点。有 2 个 medium findings 和 2 个 low findings 需要在实施前或实施中处理。

## Findings

### F1 [medium]: 方案表述歧义 — "增加显式 typed field" 的 schema 归属未明确

**证据：** Plan S1 写道：

> 为 memory projection / run input event view 增加显式 `assistant_final_answer_text` 或等价 typed field；或在构造 assistant selected recent material 时通过同一个 helper 读取 terminal answer continuity text，但不把它写回 payload dict。

这两个方案的风险等级不同：

- 方案 (a) 增加显式 typed field：改动 memory projection / run input 的 event view 结构。
- 方案 (b) 构造时读取但不写回：不改 view 结构，只改消费方式。

Plan 的 stop condition 写的是"实施发现消除 payload mutation 必须新增或迁移 durable EventLog schema 字段"，但方案 (a) 改的不是 EventLog schema，而是 read model / projection 的 typed field。`docs/host/design.md:43` 明确"Projection、timeline、audit、usage、tool trace、outbox、memory snapshot 都不能反向成为 EventLog 真源"，所以 memory projection 的 event view 是 read model，不是 durable schema。

**影响：** 实施 agent 可能误判方案 (a) 为"durable schema change"而触发 stop condition，或者反过来认为改 read model typed field 不需要 design truth sync。

**建议 plan 修复：** 在 S1 的 allowed changes 中明确：
- 方案 (a) 改的是 memory projection / RunInputBuilder 的 read model typed field，不是 EventLog durable schema；这属于 read model 内部结构变更，不需要 durable migration，但需要同步 `docs/host/design.md` 中 memory projection 与 RunInputBuilder 的消费契约描述。
- 方案 (b) 不改 read model 结构，只改消费路径；同样需要 design truth sync。
- 两个方案都不需要停止，除非发现必须改 EventLog schema 才能消除 payload mutation。

### F2 [medium]: 相对 import 解析的 package root 确定性未给出具体算法

**证据：** Plan S1 写道：

> 在 `tests/host/test_import_boundary.py` 修改 `_imported_module_names(...)` 或新增 helper，使 `ast.ImportFrom` 的 `node.level > 0` 能按当前被扫描文件所属 package root 解析为绝对模块名。

Plan 有 stop condition："相对 import 解析需要跨 package root 推断且无法从文件路径和 package root 得到确定模块名"，但没有说明具体算法。

Python 相对 import 的解析规则是确定性的：
- `from .x import y` 表示同 package 下的 `x` 模块
- `from ..x import y` 表示父 package 下的 `x` 模块
- 解析需要知道：当前文件的绝对路径、当前文件所属 package 的 root 路径

从这两个信息可以确定当前模块在 package 中的位置（通过计算路径差），然后用 `node.level` 向上回溯 package 层级，拼接 `node.module` 得到绝对模块名。这是确定性的，不需要跨 package root 推断。

**影响：** 实施 agent 可能因为不确定算法而过度设计（引入完整的 import resolver）或不足设计（只处理简单 case）。

**建议 plan 修复：** 在 S1 的 allowed changes 中补充算法描述：
```
# 相对 import 解析算法
# 1. 从被扫描文件的绝对路径和 package root 计算当前模块的 package-relative 位置
# 2. node.level 表示向上回溯的 package 层级数
# 3. 从当前 package 位置向上回溯 node.level 层，拼接 node.module 得到绝对模块名
# 4. 若 node.level 超出 package root，报错无法解析
```

### F3 [low]: source scan assertion 未覆盖 `tests/host/test_memory_projection.py`

**证据：** Plan S1 的 rollback / verification point 写道：

> `rg -n "merged\\[_PAYLOAD_FIELD_FINAL_ANSWER\\]|transient ``final_answer``|snapshot_digest=\"pending\"" dayu/host tests/host/test_compact_material.py tests/host/test_run_input_builder.py` 不应显示 production payload mutation 或业务测试散落 sentinel。

但 source scan assertion 只验证 `test_compact_material.py` 和 `test_run_input_builder.py`，没有覆盖 `test_memory_projection.py`。

Plan 在 MiMo 12 的证据中说："memory projection 测试本身没有当前直接证据显示 `"pending"` sentinel 大量散落"，但 Plan 也说要增加 cross-path equivalence test，这些新测试可能引入 sentinel。

**影响：** 新增的 cross-path equivalence test 可能意外引入 sentinel 模式而不被 source scan assertion 捕获。

**建议 plan 修复：** 将 `tests/host/test_memory_projection.py` 加入 source scan assertion 的目标文件列表。

### F4 [low]: cross-path equivalence test 的具体断言内容未明确

**证据：** Plan S1 写道：

> 在 `tests/host/test_run_input_builder.py` 或 `tests/host/test_memory_projection.py` 增加 cross-path equivalence test：同一 `RUN_SUCCEEDED` + terminal payload descriptor source 经 durable memory projection 和 ordinary RunInputBuilder 进入 LLM-facing assistant continuity 时文本一致，且两条路径都不泄漏 refs/digests。

但没有说明具体断言什么：
- "文本一致"是指完全相同还是语义等价？
- "不泄漏 refs/digests"是指不包含这些字符串，还是不以它们作为 LLM-facing 语义？

**影响：** 实施 agent 可能写出过于宽松或过于严格的断言。

**建议 plan 修复：** 补充具体断言描述：
- 文本一致：两条路径产出的 `assistant_final_answer_text` 字符串完全相同。
- 不泄漏：断言产出文本不包含 `terminal_summary_ref`、`terminal_summary_digest`、payload ref、artifact ref、event id、digest 等内部治理标识。

## Accepted Plan Compliance

| 检查项 | 状态 | 说明 |
|---|---|---|
| 动机成立 | ✅ | P2-B 动机成立，严重性保持 P2 正确 |
| 直接证据 | ✅ | 三个 finding 都有直接代码证据和设计真源引用 |
| Owner boundary | ✅ | 四个 owner boundary 识别正确，无遗漏 |
| Non-goals | ✅ | 明确列出不做的事情，无过度设计 |
| Stop conditions | ✅ | 五个 stop condition 覆盖关键风险点 |
| Allowed files | ✅ | 包含所有需要修改的文件，无不必要的文件 |
| Validation matrix | ✅ | 包含必要的测试命令 |
| Propagation audit | ✅ | 8 条路径覆盖从 Engine 到 tests 的完整链路 |
| README triggers | ✅ | 正确识别需要检查的 README |
| One-slice 策略 | ✅ | 三类 finding 代码量小、验证矩阵共享，one-slice 合理 |

## Residual Risks

1. **MiMo 08 设计风险：** 方案 (a) 和 (b) 的选择会影响 read model 结构，但 stop condition 正确控制了 durable schema 风险。实施时必须先做 design truth sync，确认 `_terminal_answer.py` 和 `docs/host/design.md` 对 terminal answer continuity 的描述一致。

2. **MiMo 09 实现风险：** 相对 import 解析算法需要处理 edge case（如 `node.level` 超出 package root、`node.module` 为 None）。Plan 的 stop condition 正确，但建议补充算法描述以降低实施风险。

3. **MiMo 12 迁移风险：** 从手写 snapshot 到 shared factory 的迁移可能引入新的 bug。Plan 的 source scan assertion 和 cross-path equivalence test 正确控制了这个风险。

4. **cross-path equivalence test 覆盖风险：** 当前 Plan 只要求一个 cross-path equivalence test，但实际可能需要多个 case（有/无 terminal descriptor、有/无 inline final_answer）。实施时需要根据代码实际情况补充 case。
