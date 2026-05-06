# Host P2 OLD / NEW 专项 Plan Review

## 审查结论

`docs/host/phase2-plan.md` 的主方向成立：P2 没有把 OLD `TruncationManager` 机械迁回 Engine，而是把截断、cursor、TTL、scope token 与 `fetch_more` 收束到 Host-owned ToolRuntime，并明确要求 canonical RunEvent 作为截断 / 补读事实真源。这符合 `docs/host/migration-plan.md` 中 P2 “截断 / 补读不是不可审计黑盒”的目标，也符合 `docs/host/design.md` 中 Engine 只消费 `ToolExecutor`、Host 负责治理事实的边界。

但 plan 仍有几个需要在实施前收紧的缺口。最高风险不是“关键词遗漏”，而是初始 `scope_token` 的交付通道、OLD LLM 可执行续读语义在 P2 被有意后移后的验收口径、以及测试是否能证明 cursor 是工具执行时就登记并落 EventLog，而不是等到 `fetch_more` 才补登记。下面 findings 按严重程度排序。

## Findings

### P1：初始 `scope_token` 交付通道未闭合，可能导致 public `fetch_more_tool_result` 无法被真实调用

**直接证据**

- NEW plan 要求 `ToolFetchMoreRequest` 必填 `scope_token`：`docs/host/phase2-plan.md:145-152`。
- NEW plan 同时禁止把 `scope_token` 明文写入 RunEvent：`docs/host/phase2-plan.md:233-234`。
- NEW plan 又声明 P2 不把 `fetch_more` 暴露给 Engine / LLM，当前 Engine projection 不投影 `fetch_more_args`：`docs/host/phase2-plan.md:41-42`、`docs/host/phase2-plan.md:83-85`。
- OLD 的可调用路径是：截断信息构造 `fetch_more_args`，其中包含 cursor 与 scope token；LLM 投影只保留 `next_action` / `fetch_more_args`；`fetch_more` schema 要求 cursor / scope_token。证据见 `/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:646-657`、`/Users/leo/workspace/dayu-agent/dayu/engine/tool_result.py:226-289`、`/Users/leo/workspace/dayu-agent/dayu/engine/tool_registry.py:250-280`。
- NEW 当前 Engine tool outcome projection 不投影 `truncation`，只投影业务 `value`：`dayu/engine/agent.py:240-256`、`dayu/engine/agent.py:278-294`。

**影响**

P2 的 public `fetch_more_tool_result(request)` 需要 `scope_token`，但 plan 没定义调用方从哪里拿到初始 token。若从 canonical RunEvent 获取，会违反“不写 scope token 明文”；若从 Engine tool message 获取，P2 又明确不投影；若只在进程内测试 fake executor 中保存，就会变成测试专用语义，无法支撑真实 UI / Service 补读。

**建议修复方向**

在 plan 中明确初始 token 的非 EventLog 交付通道，并把该通道纳入 public 契约或显式后移。例如：

- P2 只支持 Host 内部 / 测试 harness 直接拿到 `ToolFetchMoreHandle`，真实 UI 补读后移；或者
- `fetch_more_tool_result` 不面向普通 UI，只面向持有 execute 返回对象的上层 harness；或者
- 增加一个不会进入 EventLog 的受控读取接口，返回 cursor + scope token handle，同时 EventLog 只写 fingerprint。

无论选哪条，都要补测试证明 scope token 不进入 RunEvent / stream，同时真实调用方能拿到调用所需 token。

**修复状态**

已修复。`docs/host/phase2-plan.md` 现在明确新增非 EventLog 的受控
`get_tool_fetch_more_handle(...)` 契约：调用方只能按 session / run / 原始 tool_call /
cursor fingerprint 换取 `ToolFetchMoreHandle`，再构造 `fetch_more_tool_result(...)` 请求。
plan 同时写明 `scope_token` 不进入 RunEvent、preview、Engine projection、timeline projection 或日志；
P2 真实调用方限定为同进程 Host UI / Service adapter 或测试 harness，远程 UI / LLM 主动补读后移。
测试清单已增加 handle delivery 覆盖，要求证明 RunEvent 不含明文 token 但受控调用方能拿到 handle。

### P1：P2 有意不恢复 OLD LLM 可执行 `fetch_more`，验收表述需避免误称“完整继承 OLD fetch_more 语义”

**直接证据**

- NEW plan 明确 P2 不把 `fetch_more` 做成 LLM 可见工具：`docs/host/phase2-plan.md:83-85`。
- OLD 中 `fetch_more` 是自动注册的工具 schema，首个真实工具注册后出现，且 `ToolRegistry.execute("fetch_more", ...)` 直接进入 `TruncationManager.execute_fetch_more`：`/Users/leo/workspace/dayu-agent/dayu/engine/tool_registry.py:250-285`、`/Users/leo/workspace/dayu-agent/dayu/engine/tool_registry.py:507-508`。
- OLD `project_for_llm` 专门只投影 `next_action` 与 `fetch_more_args`，使 LLM 能拿到可执行参数：`/Users/leo/workspace/dayu-agent/dayu/engine/tool_result.py:226-289`。

**影响**

如果 P2 验收写成“迁移 OLD fetch_more 续读语义”，实施 Agent 可能误以为需要恢复 LLM 主动续读；也可能反过来只做 public API，漏掉 OLD 中“模型能基于最新截断结果继续读取”的核心用户体验。当前 plan 的技术选择可以成立，但它继承的是 cursor / token / TTL / single-use 的可靠性语义，不是完整 OLD LLM-facing 续读闭环。

**建议修复方向**

把 P2 验收口径改清楚：P2 必须继承 OLD 的底层可靠语义；LLM 主动调用 `fetch_more` 是后续 phase 的显式非目标。测试名和 review gate 中避免用“完整 OLD fetch_more 语义”这类表述，改为“OLD cursor lifecycle 语义”和“NEW 不恢复 LLM-facing fetch_more”。

**修复状态**

已修复。`docs/host/phase2-plan.md` 的目标、非目标、测试清单和 review gate 已改为：P2 只继承
OLD cursor lifecycle、token、TTL、single-use、limit clamp、page structure 等底层可靠语义；
OLD LLM-facing `fetch_more` schema、`next_action` / `fetch_more_args` projection 明确后移。
这不是 P2 阻塞，因为 P2 的架构目标是先把 Host ToolRuntime 与 canonical RunEvent 事实层闭合，
不把不可执行半协议回流 Engine。

### P2：`session_id` / `tool_call_id` 校验是 NEW 语义收紧，但 plan 未说明与 OLD 跨 iteration 续读的关系

**直接证据**

- NEW plan 要求 cursor record 绑定 `session_id`、`tool_call_id`，并要求 `fetch_more` 校验 run / session / tool_call：`docs/host/phase2-plan.md:187-193`。
- OLD cursor record 保存 `run_id`、`iteration_id`、`tool_call_id`，但 `_validate_cursor_context` 明确“仅校验 run_id，允许同一 run 内跨 iteration 续读”：`/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:592-594`、`/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:732-753`。
- OLD 测试覆盖同一 run 跨 iteration 续读成功：`/Users/leo/workspace/dayu-agent/tests/engine/test_tool_registry_v2.py:306-331`。

**影响**

NEW 对 session / tool_call 的绑定更强，方向上合理，因为 public Host API 不应只靠 run_id。但 plan 没说明这是对 OLD 的安全强化，也没要求测试证明“同一原始 tool_call 的后续 page 仍可跨 Agent iteration / caller turn 续读”。实施时如果把当前 caller 的 iteration 或新 tool_call 错当成校验对象，会把合法续读拒掉。

**建议修复方向**

在 plan 中明确：`tool_call_id` 必须绑定“产生截断 cursor 的原始 tool call”，不是 `fetch_more` 请求自身的新 tool call；P2 public fetch_more 不引入 Engine iteration 校验。测试增加一条“同一 run / session / 原始 tool_call，跨后续调用时仍可补读；不同 tool_call_id 被拒绝”。

**修复状态**

已修复。`docs/host/phase2-plan.md` 已明确 `tool_call_id` 绑定产生截断 cursor 的原始工具调用，
不是 `fetch_more` 请求自身；P2 public fetch_more 不引入 Engine iteration 校验，也不把后续 caller turn
当成新的绑定对象。测试清单已增加“同一 run / session / 原始 tool_call 后续 caller turn 仍可补读；
跨 run / session / 原始 tool_call 被拒绝”。

### P2：scope token 生成字段缺少 `session_id`，与 plan 的 session 绑定目标不一致

**直接证据**

- NEW plan 要求 cursor record 绑定 `session_id`，并校验 session：`docs/host/phase2-plan.md:187-193`。
- NEW plan 对 scope token 的生成字段只列出 cursor、scope_hash、run_id、tool_call_id、created_at，未包含 session_id：`docs/host/phase2-plan.md:190-191`。
- OLD token payload 包含 cursor、scope_hash、run_id、iteration_id、tool_call_id、created_at；OLD 本身没有 session 维度：`/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:693-702`。

**影响**

如果 P2 把 session 作为权限边界，scope token 也应把 session 纳入签名材料，否则 session 校验只能依赖 cursor record 的普通字段。对于 in-memory P2 这不是立即可利用的外部漏洞，但会让“session-bound token”与实现事实不一致，后续持久化或跨进程迁移时容易漂移。

**建议修复方向**

将 `session_id` 加入 scope token payload，或者明确 scope token 只证明 cursor record 未被篡改，session 校验独立完成。更推荐前者，并补“同 run 不同 session + token 复用被拒绝”的测试。

**修复状态**

已修复。`docs/host/phase2-plan.md` 已把 `session_id` 加入 `scope_token` 生成材料：
cursor、scope_hash、session_id、run_id、tool_call_id、created_at。测试清单已增加 token 生成材料包含
session_id，以及跨 session 复用 cursor / token 被拒绝。

### P2：测试清单没有显式覆盖“执行时产生截断事实与 cursor”，容易把 cursor 登记推迟到 `fetch_more`

**直接证据**

- NEW plan 要求 ToolRuntime execute path 在底层工具执行后截断并写 RunEvent：`docs/host/phase2-plan.md:54-62`。
- 测试清单只写了 `Cursor issued fact`、`EventLog truth` 和 fetch_more ordering：`docs/host/phase2-plan.md:350-358`，没有要求断言底层 executor 调用完成后、任何 fetch_more 之前 cursor 已存在且 canonical `tool_result_truncated` / `tool_cursor_issued` 已 append。
- OLD `apply_truncation` 在普通工具执行结果返回时立即 `_store_cursor` 并返回 truncation info：`/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:62-144`、`/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:393-402`。

**影响**

实现可能只在 public `fetch_more_tool_result` 被调用时才补建 cursor / 事实。这样会破坏 OLD 的可靠语义：截断发生的事实、cursor lineage、TTL 起点都应来自原始工具执行时刻，而不是补读请求时刻。

**建议修复方向**

测试清单增加一项：fake business executor 返回超限结果后，`ToolRuntimeToolExecutor.execute` 返回前已经完成截断、cursor 生成、TTL 起算、canonical facts append；随后不调用 fetch_more 也能通过 `stream_run_events` 观察到截断 / cursor issued facts。

**修复状态**

已修复。`docs/host/phase2-plan.md` 测试清单已新增 `Execute-time cursor facts`：fake business executor
返回超限结果后，`ToolRuntimeToolExecutor.execute` 返回前必须完成截断、cursor 生成、TTL 起算和
canonical `tool_result_truncated` / `tool_cursor_issued` append；不调用 fetch_more 也必须能从
`stream_run_events` 观察到事实。

### P3：截断目标选择规则仍有歧义，可能不小心保留 OLD 启发式字段选择

**直接证据**

- NEW plan 写“截断目标选择应优先使用显式 truncate spec；没有 spec 时不启发式截断”，并要求如保留 OLD 启发式需证明：`docs/host/phase2-plan.md:209-210`。
- OLD 在有 truncate spec 但没有 `target_field` 时，会对 dict 选择最长文本字段或最大列表路径：`/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:239-283`。

**影响**

“没有 spec 时不启发式”不能覆盖“有 spec 但没有 target_field 时是否启发式”。如果 P2 想避免 Host 理解业务结果结构，应明确只截断直接 value 或显式 target_field；如果想继承 OLD，应承认这是一个启发式并覆盖 nested list / longest text 测试。

**建议修复方向**

在 plan 中把规则写成二选一：

- 严格 NEW：dict/list wrapper 必须有显式 target_field / field_path，否则不截断；
- 继承 OLD：允许 longest text / largest nested list 启发式，并用 OLD 测试迁移证明。

当前架构约束下，更推荐严格 NEW，避免 Host 过度理解业务 payload。

**修复状态**

已修复。`docs/host/phase2-plan.md` 已选择严格 NEW：无显式 truncate spec 不截断；直接 `str` /
`list` / `bytes` value 可整体截断；wrapper dict 必须提供显式 `target_field` 或 `field_path`；
P2 不继承 OLD longest text / largest nested list 启发式。测试清单、不可接受临时实现、review gate
和停止条件均已同步，若实施需要启发式必须先停止修 plan。

### P3：TTL 清理策略只有过期访问测试，缺少 OLD 的创建时清理语义

**直接证据**

- NEW plan 测试清单只覆盖“过期 cursor 返回 expired，cursor 被清理”：`docs/host/phase2-plan.md:353`。
- OLD `_store_cursor` 每次创建新 cursor 前会调用 `_cleanup_expired_cursors(now)`，避免无人访问的过期 cursor 长期残留：`/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:568-577`、`/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:602-611`。
- NEW 风险部分提到内存压力与 TTL 清理，但没有落成验收项：`docs/host/phase2-plan.md:439-440`。

**影响**

P2 声明 in-memory cursor store 单进程有效可以接受，但如果只在 fetch_more 时清理过期 cursor，长时间只产生截断、不补读的 smoke 会积累原始大结果引用。这个风险在 P2 不一定阻塞，但应作为可靠语义测试或实现要求。

**建议修复方向**

增加“创建新 cursor 时 opportunistic 清理已过期 cursor”的可选但推荐要求；至少测试 expired cursor 在后续 execute 截断路径中被清掉，避免原始 payload 无界滞留。

**修复状态**

已修复。`docs/host/phase2-plan.md` 已把“创建新 cursor 前 opportunistic 清理过期 cursor”写成 P2
in-memory cursor 生命周期要求，并在测试清单增加 `TTL opportunistic cleanup`，要求覆盖只截断不补读时
后续创建 cursor 会清理此前过期 payload。

## OLD 可靠语义清单

### P2 必须继承

- schema 驱动截断：只有 `ToolTruncateSpec.enabled` 且 strategy / limit 有效时才截断；OLD 证据 `/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:82-93`。
- 四类基础策略：`text_chars`、`text_lines`、`list_items`、`binary_bytes`；OLD 证据 `/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:99-144`。
- 截断发生在普通工具执行返回路径，cursor 在首次截断时创建，而不是 fetch_more 时才创建；OLD 证据 `/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:393-402`。
- cursor 不可由调用方伪造：cursor 是随机 `uuid4().hex`，record 保存在内部 store；OLD 证据 `/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:575-599`。
- `scope_hash` 基于工具名 + 规范化参数生成，作为审计 / 追踪材料；OLD 证据 `/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:537-544`。
- `scope_token` 绑定 cursor、scope_hash、run / tool_call 等上下文字段，fetch_more 必须校验；OLD 证据 `/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:679-702`、`/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:755-782`。
- TTL 过期拒绝并删除 cursor；OLD 证据 `/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:167-170`。
- `limit` clamp：请求 limit 为正时不得超过原始 limit，否则使用原始 limit；OLD 证据 `/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:726-730`。
- single-use：成功续读后旧 cursor 失效，有剩余时发新 cursor / 新 token；OLD 证据 `/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:201-236`。
- 成功续读返回的是原 payload 的下一段，并保持模板结构；OLD 证据 `/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:184-195`、`/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:704-724`。
- scope token 缺失 / 错误、cursor 缺失 / 不存在 / 过期均返回 typed failure；OLD 证据 `/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:160-182`。

### 可后移

- LLM 主动调用 `fetch_more` 的 schema 暴露与 prompt 体验；OLD 证据 `/Users/leo/workspace/dayu-agent/dayu/engine/tool_registry.py:250-285`，NEW P2 已明确暂不做。
- OLD `project_for_llm` 对 `next_action` / `fetch_more_args` 的投影；OLD 证据 `/Users/leo/workspace/dayu-agent/dayu/engine/tool_result.py:226-289`，NEW 当前 Engine projection 不投影 truncation。
- 完整 ToolRegistry 发现、schema 版本、display info、middleware 链与业务工具迁移；NEW plan 已列为非目标。
- 完整用户 / workspace / doc ACL、path allowlist、多进程持久 cursor store、lease / fencing / recovery。
- OLD 启发式字段选择。如果 P2 选择严格显式 target，则最长文本 / 最大嵌套列表启发式可以不继承，但必须写清楚。

### 禁止迁回 Engine

- 禁止在 `dayu.engine` 新增 `TruncationManager`、cursor store、TTL 管理或 `fetch_more` 内置工具。
- 禁止让 Engine 感知 Host ToolRuntime、cursor store、权限实现或 RunEventStore。
- 禁止把 tool trace / audit / transcript 真源放回 Engine 或 Engine-side projection。
- 禁止为了兼容 OLD 导入路径做 re-export / facade。
- 禁止把财报业务语义、文档存取规则或 `dayu.fins.storage` 之外的财报访问逻辑塞进 Host / Engine。

## 开放问题 / 待用户确认

- P2 的真实调用方如何获得初始 `scope_token`：已在 plan 中选择非 EventLog 的 Host
  `get_tool_fetch_more_handle(...)` 契约；P2 真实调用方限定为同进程 Host UI / Service adapter 或测试
  harness，远程 UI / LLM 主动补读后移。
- P2 是否接受“底层可靠语义迁移，但 LLM 主动 fetch_more 后移”的验收口径：已在 plan 中写清。
  这不是 P2 阻塞，因为 P2 先闭合 Host ToolRuntime / EventLog 事实层，OLD LLM-facing schema 与 projection
  需要后续独立设计。
- `session_id` 是否必须进入 scope token payload：已在 plan 中选择纳入 token 生成材料，并补测试清单。
- `tool_call_id` 校验应绑定原始被截断工具调用，还是 public fetch_more 请求自身：已在 plan 中选择绑定
  原始 tool_call，不引入 Engine iteration 校验。
- 截断目标选择是否采用严格显式 target 规则，彻底放弃 OLD dict 启发式：已在 plan 中选择严格 NEW，
  wrapper dict 必须有显式 `target_field` / `field_path`。
- terminal Run 后是否必须追加 denied RunEvent：已在 plan 中选择 typed failure without new RunEvent，
  遵守 P1.5 terminal guard；post-terminal audited fetch_more 留给 P6 / P7 / P11 讨论。

## 验证说明

本次只做文档专项 review，未修改生产代码，未运行 pytest / pyright。

## 复审结论

复审通过。修复后的 `docs/host/phase2-plan.md` 已在 plan 正文中闭合原 findings，不只是
在本 review 文档中标注修复状态；当前未发现阻塞 P2 plan review gate 的 blocker。

复审确认：

- 初始 `scope_token` 交付通道已闭合：plan 新增非 EventLog 的
  `get_tool_fetch_more_handle(...)` public 契约，调用方按 session / run / 原始 tool_call /
  cursor fingerprint 换取 `ToolFetchMoreHandle`；`scope_token` 只存在于短期 handle 和
  `ToolFetchMoreRequest`，不得进入 RunEvent、preview event、Engine message、timeline projection
  或日志。
- OLD / NEW 语义边界已写清：P2 继承 OLD cursor lifecycle、TTL、single-use、limit clamp、page
  structure、scope token 校验等底层可靠语义；OLD LLM-facing `fetch_more` schema 与
  `next_action` / `fetch_more_args` projection 明确后移，不在 P2 半协议回流 Engine。
- terminal 后 `fetch_more` 不破坏 P1.5 terminal guard：plan 要求 terminal RunEvent 后先检查并返回
  typed failure，不追加新的 denied / expired RunEvent；post-terminal audited fetch_more 留给 P6 / P7 /
  P11。
- 测试清单已覆盖语义与实现逻辑差异：新增 `Execute-time cursor facts`，要求 fake business executor
  返回超限结果后，在 `ToolRuntimeToolExecutor.execute` 返回前已经完成截断、cursor 生成、TTL 起算和
  canonical `tool_result_truncated` / `tool_cursor_issued` append，不能等到 `fetch_more` 时补登记。
- 其他原 findings 已在 plan 正文落地：`session_id` 进入 token 生成材料；`tool_call_id` 绑定原始被截断
  tool call 且不引入 Engine iteration 校验；wrapper dict 截断采用严格显式 target，不继承 OLD
  longest text / largest nested list 启发式；创建新 cursor 前 opportunistic 清理过期 cursor 已成为
  P2 生命周期要求和测试项。

仍需用户确认但不阻塞 review：

- P2 是否接受真实补读调用方限定为同进程 Host UI / Service adapter 或测试 harness；远程 UI、跨进程补读、
  LLM 主动补读后移。
- P2 是否保持 `ToolTruncationInfo` 只承载内部中性截断信息，还是在代码实施时确有必要增加可执行补读字段；
  若修改，仍必须保持强类型封闭契约且不得泄漏 token 到 Engine projection。
- terminal 后补读请求的审计事实是否进入 P6 / P7 / P11 的后续设计；P2 当前选择不追加 RunEvent 是为了
  遵守 P1.5 terminal guard。

本次复审只修改 review 文档，未修改生产代码，未运行 pytest / pyright。
