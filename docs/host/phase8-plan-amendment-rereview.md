# P8 Plan Amendment 复审

## 审查范围

复审对象：`docs/host/phase8-plan.md` 与 `docs/host/migration-plan.md` 的计划修订，
新增 P8-S8（Durable Conversation Memory Store / Read Model Rebuild），原 S8/S9 顺延为 S9/S10。

变更文件状态：两个文件均为 unstaged modification（`M`），无 whitespace error。

## 1. 新 P8-S8 动机是否成立

**结论：成立。**

直接证据：

- `dayu/host/_durable_harness.py:188-190`：`build_durable_harness` 默认装配 `InMemoryConversationMemoryStore()`，这是纯内存实现。
- `dayu/host/_event_observer.py:153-169`：`startup_reconcile()` 委派 `drain()`，`drain()` 按 observer checkpoint 推进。若 checkpoint 已 caught up，`drain()` 不会 replay 已处理 EventLog。
- 推论：进程重启后 in-memory memory 丢失 + checkpoint 已 caught up = session memory snapshot 永久丢失。这是真实的数据丢失通道，不是假设性风险。

计划准确描述了该风险，且明确该问题必须在 P9 固定 production lifecycle / public interface 前解决。动机成立，严重性未被高估。

## 2. S8 边界是否正确

**结论：正确。**

逐项检查：

| 边界约束 | 是否明确 | 证据 |
| --- | --- | --- |
| 只做 Host internal durable memory read model / checkpoint-aware rebuild | 是 | 目标段明确"Host internal 路径能自行恢复，不要求 UI / Service 调用方触发 reload" |
| 不偷做 P9 Session / Run admission | 是 | 非目标段第一项明确列出 |
| 不固定 public memory edit / reset / forget API | 是 | 非目标段明确"那是 issue #24 / 后续 phase 范围" |
| 不让 UI / Service 参与恢复 | 是 | 非目标段明确列出 |
| 不迁移业务 memory | 是 | 非目标段明确列出 |
| 不升级成完整 long-term memory store | 是 | 非目标段明确列出 |

边界未越界。

## 3. 删除 InMemory 要求是否清楚

**结论：清楚。**

计划明确要求：

1. 删除 production `InMemoryConversationMemoryStore` 实现（`_conversation_memory.py` 中的类、`__all__` 导出、package re-export）。
2. 删除依赖 production InMemory 的测试用例。
3. 测试需要 fake 时迁移到 `tests/host/` 私有 helper（例如 `_memory_store_fake.py`）。
4. 禁止保留 production InMemory 来迁就旧测试。
5. 完成信号包含 `grep -R "InMemoryConversationMemoryStore" dayu/ utils/` 验证。

要求清晰，无歧义。

## 4. Slice 顺延是否完整

**结论：完整。**

逐项检查：

| 检查项 | 结果 |
| --- | --- |
| 原 S8（手工 Smoke）-> S9 | 已全量更新：标题、前置依赖（S7->S8）、完成信号补充 memory_recovered |
| 原 S9（文档同步与收口）-> S10 | 已全量更新：标题、前置依赖（S8->S9）、完成信号补充 durable memory 与 InMemory 清理、停止条件补充 InMemory 残留 |
| 新增测试清单 | `test_phase8_durable_memory_recovery.py` 已加入第 16 节测试计划与 P8 专项测试命令 |
| smoke 场景 | 场景 7（memory_recovered）已加入第 15 节 smoke 设计 |
| review gate | S8 架构边界 review 要求已加入第 18 节 Code gate |
| 并行规则 | 已更新为 S9/S10 可在 S8 通过后并行，不得与 S1-S8 并行 |
| 非目标边界描述 | 第 2 节非目标段已补充 S8 与 P9 public memory API 的区分说明 |
| 旧编号残留 | 已 grep 确认无旧 S8/S9 编号残留（diff 中旧 S8->S9、S9->S10 全量替换） |

顺延完整，无遗漏。

## 5. Residual risk owner 是否准确

**结论：准确。**

`migration-plan.md` §4.4 新增条目：

- `deferred-with-owner: P8-S8`：durable conversation memory read model / checkpoint-aware rebuild。准确描述风险、解决路径和边界。
- 原 `deferred-with-owner: P8-S7` 条目已补充"S7 仅验证 multiprocessing owner / fencing / recovery 语义，不解决 durable conversation memory read model rebuild；durable memory recovery 单独由 P8-S8 承接，不得在 S7 中偷做"。

风险归属清晰，未错误归到 P9/P16 或无主化。

## Findings

无。

## 结论

**PASSED**

本次计划修订动机成立、边界正确、要求清晰、顺延完整、风险归属准确。无 finding 需要修复。

允许进入 user confirmation + plan amendment commit gate。
