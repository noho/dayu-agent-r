# WU-SEMANTIC-OWNERSHIP-01 / R03-S1 Plan Correction Controller Adjudication

## 1. Verdict

Controller verdict：**MATERIAL_PLAN_BOUNDARY_CORRECTION_REQUIRED**。

R03-S1 仍是既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的内部 remediation slice，
不是新 WU、不是第四个 R03 slice，也不改变 Topic 3/4 产品裁决。当前未提交实现必须保留；
在修订计划完成双路 review 并由 Controller 接受前，不得继续 production 修改、进入 code
review、S2、S3 或 aggregate。

## 2. Direct evidence

- Controller 初次独立验证：9 个 owner/consumer 文件 `364 passed`；全 Host
  `1928 passed, 1 skipped, 5 deselected`；pyright、ruff、coverage 和
  `git diff --check` 均通过。
- 静态 owner-contract 复核发现三处 S1 内缺口：旧 `TOOL_AWAITING` 测试 fixture、
  descriptor 冷热正文互斥校验缺失、accepted-result execution identity 的
  `None` 兼容放行。
- AgentCodex 在既有 allowlist 内补上前两类修复及 strict execution equality 后，直接受影响
  四文件为 `163 passed`，memory 单文件为 `63 passed`。
- 9 文件矩阵随后为 `369 passed, 3 failed`。三个失败都来自真实
  `resolve_wait` producer 路径，不是测试替身或展示层推断。
- 直接源码证据位于
  `dayu/host/durable/run_transition.py::_waiting_tool_result_event_request`：fresh
  `TOOL_RESULT_ACCEPTED` 的 `execution_id` 被硬编码为 `None`；与其 envelope 链接的
  canonical `TOOL_CALL_REQUESTED` 则拥有 suspended Attempt 的真实 execution id。

因此严格 consumer 抛出 `HostDurableError` 是正确结果；恢复 `None` 放行、修改测试期望、
在 `waiting.py` 加 seam 或下游 fallback 都会掩盖 producer owner 的错误语义。

## 3. Required plan correction

修订计划必须在 R03-S1 内完成以下最小 owner-correct 扩边：

1. 将 `dayu/host/durable/run_transition.py` 加入 S1 production allowlist；该 durable
   transition 是 wait-resolution `TOOL_RESULT_ACCEPTED` EventLog identity 的直接 writer owner。
2. `TOOL_RESULT_ACCEPTED.execution_id` 必须取 suspended source Attempt 的 durable
   execution identity，不得取 resume Attempt identity、`None`、payload 字段或下游推断值。
3. transition 前置条件必须证明 `WaitRecord.execution_id` 与 suspended
   `AttemptRow.execution_id` 同源；不一致时不得写 result/resume/terminal facts。
4. 测试至少覆盖 resume outcome 与 terminal outcome 两个 union 分支，断言写出的
   `TOOL_RESULT_ACCEPTED.execution_id` 精确等于 suspended Attempt execution id；同时覆盖
   execution 不同源时无 partial facts。测试文件扩边应由修订计划基于现有 owner-level fixture
   选择并显式列出，禁止用 loose fixture 固化旧 `None` 行为。
5. 保留当前 strict accepted-result equality、descriptor storage-shape guard、
   governance-only `TOOL_AWAITING` fixture 及对应 no-publication 反例。

该修订不授权修改 Engine/Service/UI/Fins、实现 S2 blacklist 删除、S3 opaque-ref propagation、
Issue 177/178 或统一 tool authorization framework。

## 4. Gate routing

下一 gate 是 **R03-S1 plan correction**：AgentCodex 只修改 R03 accepted plan 并产出 correction
artifact；随后 AgentMiMo / AgentDS 对完整修订计划并发 review。Controller 接受后，才能返回
同一 R03-S1 implementation continuation。当前 worktree 中已完成的 implementation diff 是
有意状态，不得删除、回滚或覆盖。
