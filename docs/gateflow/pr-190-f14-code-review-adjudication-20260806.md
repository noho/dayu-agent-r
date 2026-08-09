# PR 190 F14 code review adjudication

## Gate metadata

- gate: `code review`
- base: `b222b8b064f096d899a9de708e45cd1fb6e732e6`
- implementation artifact: `docs/gateflow/pr-190-f14-s1-implementation-20260806.md`
- AgentMiMo review: `docs/reviews/pr-190-f14-code-review-mimo-20260806.md`
- AgentDS review: `docs/reviews/pr-190-f14-code-review-ds-20260806.md`
- AgentController review: `docs/reviews/code-review-20260806-233618.md`
- verdict: `NEEDS_FIX`

## Accepted findings

### C1 — Medium — `run_id=None` user anchor 被静默当成完整已消费 group

接受 AgentController F1。accepted plan 与 implementation docstring均明确 `run_id=None` 不能建立 whole-Run proof，但当前 `group_consumed` 没有要求 non-null `run_id`。这会让恰好出现在 consumed refs 中的 singleton user row绕过 typed/atomic fail-closed。修复必须只收紧 Host metadata proof并补 owner regression。

### M1 — Medium — 缺少 3+ 轮 frontier 单调、exact-once 与 canonical order owner test

接受 AgentMiMo F1。当前 two-terminal fixture只验证一次最终 view，不能证明逐轮 frontier单调推进，也没有显式核对每一阶段的 gap/duplicate/order。需要按accepted plan A.3补三轮以上阶段性断言；不得用偶然event sequence常量固化行为。

### M2 — Medium — 缺少 correction 离开 recent floor 后的 reconnect同源测试

接受 AgentMiMo F2。restart view equality 只证明重开store确定性，不证明 correction从raw recent晋升到accepted replacement后，ordinary RunInput/Memory/reconnect不再依赖recent window。需要在Host integration边界构造 aging → accepted replacement → reopen/reconnect，并断言raw correction不再作为表面fallback、正式replacement/evidence refs保持同源。

### M3 — Low — design校验时机表述不精确

接受 AgentMiMo F3。将“build 启动前”改为“build期间”，并区分accepted chain读取时ref校验与material projection时frontier/atomic proof。

### D2 — Low — user-anchor proof与selector atomicity缺少代码级cross-reference

接受 AgentDS F2 的文档增强部分，不接受其 `NEEDS_FIX-Medium` 定级。当前算法正确，accepted plan与Host design已有不变量；但在metadata helper注释/docstring中直接说明proof owner为whole-group selector与`_atomic_material_units`，可降低未来semantic ownership drift。与C1一并修正。

### D3 — Low — 纯转换helper的raises docstring不规范

接受 AgentDS F3。删除 `:raises Exception: 不主动抛出异常。`；项目要求完整说明实际异常，不应声明不存在的宽泛异常。

## Rejected findings

### AgentDS F1 — 拒绝

`_post_compact_delta_rows` 的SQL明确 `ORDER BY event_sequence ASC`，`_event_log_row_from_host_row`保持顺序，`grouped`按该tuple单次append，因此`group[0].event_sequence`机械等于该group的minimum sequence。attachment或其他事件插入不会改变相关rows的全局升序。改成`min()`只会重复计算同一事实，不能消除真实隐式依赖；若未来调用者不再提供canonical order，应在输入contract处校验，而不是本slice预防未授权接口变化。

### AgentDS 总体 PASS — 不采纳

review正文列出 `NEEDS_FIX` findings却给PASS，且未覆盖Controller直接发现的plan/code矛盾。Gateflow由Controller裁决，以上accepted findings修复并由原reviewers re-review前不得通过code review gate。

## Fix scope

AgentCodex在原implementation/fix上下文继续：

1. production只改`dayu/host/compact_material.py`的metadata proof/docstring，不新增cursor/schema/fallback。
2. owner/integration tests只补C1、M1、M2所需最小场景，复用production builder/Memory/RunInput owner；不得复制状态机或修改Oracle。
3. 修正`docs/host/design.md`时序表述，必要时同步Host README但不扩张职责。
4. 先证明C1 regression在当前实现失败，再修复；M1/M2为coverage completion，不要求伪造旧实现失败。
5. 重跑focused tests、受影响union、coverage、focused pyright/Ruff与diff-check，更新implementation artifact。

## Next gate

完成fix后，AgentMiMo与AgentDS必须基于本adjudication做窄re-review；AgentController核对直接证据后才能接受code review gate。
