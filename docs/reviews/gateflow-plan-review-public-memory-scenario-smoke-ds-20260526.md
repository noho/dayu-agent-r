# Host Public Conversation Memory Scenario Smoke — Plan Review — DS — 2026-05-26

## Gate

当前 gate：plan review。
Review target：`docs/reviews/gateflow-plan-public-memory-scenario-smoke-20260526.md`
Reviewer：AgentDS (deepreview planreview)。

## Review Scope

Adversarial plan review。挑战 plan assumptions、coverage gap、specification completeness、contract conflicts、implementation readiness。不修改 plan、code、tests、README。本 artifact 只给 controller 裁决和 implementation worker 使用。

## Evidence Baseline

- Plan artifact：`docs/reviews/gateflow-plan-public-memory-scenario-smoke-20260526.md`
- 旧参考文档：`/Users/leo/workspace/dayu-agent/docs/conversation_memory_test.md`（仅参考，不照搬）
- 现有最小 smoke：`utils/smoke_host_public_conversation_memory.py`
- Host public API：`dayu/host/api.py` (`Host` protocol, `SessionSnapshot`, `HostEvent`, `HostEventKind`)
- 现有 manifest：`dayu/config/prompts/manifests/smoke_host_public_conversation_memory.json`
- Scene migration 测试：`tests/runtime/test_scene_assets_migration.py`
- 现有 multiturn smoke：`utils/smoke_host_public_multiturn.py`（作为 assembly pattern 参考）

## Review Checklist

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 1 | 动机判断是否公允 | PASS | §1 明确拒绝照搬旧项目路径，正确识别可用边界为 public API proxy |
| 2 | 现有 smoke 是否保持语义不变 | PASS | §4 禁止修改现有 smoke；§15 明确不抽取 shared helper；§16 S1 non-goals 重申 |
| 3 | A-E 场景覆盖是否完整或诚实分类 | PASS (with N1-N3) | 见下方逐场景分析 |
| 4 | 是否避免私有 DB/EventLog/memory 读取 | PASS | §5 禁止运行期读取列表完整；§2 non-goals 明确 |
| 5 | Mock tool schema/data 是否足够具体 | PASS (with N4) | §7 固定 facts 表完整；schema 字段明确 |
| 6 | CLI flags 是否完整且不泄露内部 | PASS | §6 参数设计清晰；不增加 DB/memory dump 开关 |
| 7 | 断言是否可归一化、不打穿 public boundary | PASS | §9 hard/soft 分层；归一化只做空白/全角/大小写 |
| 8 | 验证命令是否可执行 | PASS | §13 命令具体、pass marker 明确 |
| 9 | Docs 更新决策是否合理 | PASS | §14 触发判断正确；不更新的 README 有明确理由 |
| 10 | Residual risks 是否诚实 | PASS | §15 五个风险均有 owner 和 mitigation |
| 11 | Implementation slices 是否独立可验证 | PASS | §16 S1-S4 各有 allowed files、objective、completion signal |
| 12 | 项目编码约束是否满足 | PASS | §11 中文 docstring、no Any/object、no lazy import、no hasattr/getattr 均声明 |

## 逐场景 Coverage 分析

### A. pinned_state 演进与抗漂移代理验证

- 覆盖：主体切换（茅台→五粮液→茅台）、期间固定（2024H1）、口径固定（百万元）、marker 隔离（A4 不含五粮液 marker）。
- 诚实分类：明确 "不直接证明内部 pinned_state JSON 单调 patch"，由 Host memory 单元测试覆盖。
- **PASS**。

### B. 追问连续性

- 覆盖：代词指代（"这个数"）、最近轮 referent 解析、缺失事实拒绝编造。
- 诚实分类：不覆盖旧文档 IFRS 口径新增（由 A 组和 E 组约束 recap 覆盖）。
- **PASS**。

### C. 单轮极长输入 minimum-preserve

- 覆盖：长文本 anchors 分散在首/中/尾、追问 factor2 指代还原。
- 诚实分类：不直接证明 `_build_minimum_preserved_turn_view` 调用或降级路径命中。
- Gap：长输入文本生成方法未指定（见 N2）。
- **PASS (with N2)**。

### D. confirmed facts 跨轮一致性与 compaction pressure

- 覆盖：工具确认→分组复述→topic shift→回看一致性；新 marker 避免与最小 smoke 混淆。
- 诚实分类：compaction 触发只作观察不硬断言；public API 无 compact terminal 事件契约。
- **PASS**。

### E. 长会话稳定性

- 覆盖：25 轮、9 主题顺序、工具间歇启用/禁用、constraints recap。
- 诚实分类：不证明 episode 数量/pinned_state 去重/budget 裁剪内部算法。
- Gap：25 轮具体 prompt 未提供（见 N3）。
- **PASS (with N3)**。

## Findings

### Blocking Findings

**无 blocking finding。**

本 plan 可以进入 implementation gate。所有 gaps 均为 non-blocking：implementation worker 可在不改变 plan 架构的前提下自行填充。

---

### Non-blocking Findings

#### N1: `--suite all` session continuity 机制未细化

- **位置**: §6 CLI 设计 + §5 Public API 调用流
- **问题**: §6 规定 `--suite all` "先跑 core 再跑 long，使用同一个 session"。但 §5 的调用流是单次 `async with open_host(...) as host:` + `ensure_session`。如果 core 和 long 在同一个 `open_host` block 内顺序执行，则 session 自然共享。然而 `_core_round_specs` 和 `_long_round_specs` 是两个独立函数，各自返回 `tuple[RoundSpec, ...]`，plan 未说明 `--suite all` 的顶层编排是：(a) 单次 `open_host` 内拼接两个 specs，还是 (b) 两次 `open_host` + `--reuse-session` 语义。方案 (a) 更简单但未声明；方案 (b) 需在 plan 中明确 `ensure_session` 的 slot key 复用规则。
- **Severity**: Low — implementation worker 可以合理选择方案 (a) 并在实现时裁决。
- **Recommendation**: Implementation worker 采用方案 (a)：单次 `open_host` 内先跑 core specs 再跑 long specs，session 自然共享，无需 `--reuse-session` 逻辑。实现后在本 review artifact 的 fix note 中确认选择。

#### N2: C2 长输入文本生成方法未指定

- **位置**: §8 场景 C 轮次 2
- **问题**: C2 prompt 要求 8,000-15,000 字确定性长文本，包含三个 anchors。Plan 只说 "由脚本生成，不读取外部文件"，但未指定生成方法。可选方案：(a) 重复模板段落并在固定位置插入 anchors，(b) 用固定中文财务分析模板展开。未指定可能导致不同 implementation worker 生成质量差异大的文本，影响 smoke 可复现性。
- **Severity**: Low — 方案 (a) 足够确定性且易于实现。
- **Recommendation**: Implementation worker 采用 deterministic 重复模板 + anchor 注入；在脚本模块常量中定义 `_LONG_INPUT_TEMPLATE`，确保每次运行文本完全一致。

#### N3: E 组长会话 25 轮 prompt 未提供

- **位置**: §8 场景 E
- **问题**: E 需要 25 轮围绕美的集团 9 个财务主题的 prompt。Plan 只给了主题顺序（营收→毛利→费用→...→同行对比）和第 25 轮 constraints recap prompt，其余 24 轮 prompt 未指定。Implementation worker 必须发明这些 prompt，这可能引入：(a) prompt 质量差异影响 smoke 可复现性，(b) 某轮 prompt 无意中泄露答案，(c) 轮次之间的语义连续性不足。
- **Severity**: Medium — 24 轮未指定的 prompt 是较大的实现自由裁量空间，可能影响 smoke 在不同运行间的行为一致性。
- **Recommendation**: Implementation worker 应在实现中为每轮定义 `Final` 常量 prompt 字符串；所有 prompt 只提问不泄露答案；prompt 之间保持主题递进；第 25 轮 constraints recap 不依赖中间轮的特定答案措辞。

#### N4: `calls_by_key` 追踪被设计但未用于任何断言

- **位置**: §7 Mock tool 行为段
- **问题**: Plan §7 规定 mock tool "累计 `call_count` 与 `calls_by_key`"。但 §9 Hard assertions 表只使用 `call_count`（"工具启用轮次 call count 按计划递增"），从未引用 `calls_by_key`。如果 `calls_by_key` 只是 dead tracking code，应在 plan 中明确其用途或删除。
- **Severity**: Low — 不影响正确性，但增加不必要的实现复杂度。
- **Recommendation**: Implementation worker 要么 (a) 在 mock tool 中保留 `calls_by_key` 并至少在一个 soft observation 中打印摘要（如 per-key 调用分布），要么 (b) 从 plan 的 tool 设计中移除 `calls_by_key`。推荐 (a)，因为它提供人工调试价值。

#### N5: `_assert_round_result` 单签名不足以清晰分发所有断言变体

- **位置**: §11 关键函数列表
- **问题**: Plan 提出 `_assert_round_result(result, tool, expected_tool_calls)` 作为统一断言入口。但 A-E 五个场景的 hard assertion 需求不同：
  - A1/D1: 需额外检查 answer 中的 marker + values
  - A4: 需额外检查 forbidden markers
  - B2/C3: 需检查特定 answer 子串
  - A2/A3/B3/C1/D2/D3: 只需 terminal status + tool count
  - E: 需累计 tool count + 最终轮 answer 多字段
  
  单一 `_assert_round_result` 无法自然承载这些差异。实现时可能出现脆弱的 if-elif 分支或 over-generalized assertion config。
- **Severity**: Low — 实现时的工程设计问题，不阻塞 plan 推进。
- **Recommendation**: Implementation worker 可以为 `RoundSpec` 增加可选的 `hard_answer_contains: tuple[str, ...]` 和 `hard_answer_forbidden: tuple[str, ...]` 字段，让 `_assert_round_result` 统一驱动。或者拆分为 `_assert_terminal_ok` + `_assert_tool_count` + `_assert_answer_contains` 三个独立 helper，由 per-round 断言函数组合调用。两种方案均可，但应在实现 slice 的 completion report 中说明选择。

## Plan Strengths (no action needed)

1. **边界诚实度高**：§2 non-goals 和 §5 禁止读取列表精确；pinned_state/compaction/长输入 的内部不可验证性均被诚实分类。
2. **断言鲁棒性设计好**：Hard/soft 分层 + 归一化只做去空白/全角/大小写 + 禁止语义猜测 — 这些降低 LLM flakiness 风险的设计是正确且必要的。
3. **现有资产保护到位**：§4 禁止修改 + §15 "不抽取 shared helper" 裁决 + §16 S1 non-goals — 三重保护确保现有最小 smoke 不被意外破坏。
4. **Scene asset 设计一致**：新 manifest 结构与现有 `smoke_host_public_conversation_memory.json` 一致；`max_iterations=32` 合理涵盖 long suite；fragment 选择与现有 smoke 对齐。
5. **Implementation slices 独立可验证**：S1-S4 各有清晰的 allowed files、objective、completion signal，可顺序推进并独立验收。
6. **与旧文档的正确距离**：§1 明确拒绝照搬 CLI 交互、真实财报语料、日志解析、SQLite 表内查 — 正确识别了旧文档中不适合 public API smoke 的部分。
7. **Mock tool 设计防御性好**：session-level 计数避免 startup recovery 污染；未知 key 返回 `known=false` 不抛异常；不用模块级全局计数器 — 这些细节体现了对 Host 运行时行为的理解。

## Adversarial Pass

### 反例 1: `allow_empty: false` 与空工具轮次的兼容性

**假设**: 如果 manifest `tool_selection.allow_empty: false` 阻止了 per-round `tool_names=frozenset()` 的执行。
**验证**: 现有最小 smoke manifest 同样设置 `allow_empty: false`（`"allow_empty": false`），且 rounds 2-4 使用 `_NO_TOOL_SELECTION = frozenset()` 通过真实 LLM 运行。因此 `allow_empty` 控制 scene-level 工具选择（必须至少有一个工具注册），不阻止 per-round 禁用工具有效。
**结论**: 无冲突。

### 反例 2: `max_iterations=32` 是否导致 scene migration test 失败

**假设**: `test_scene_manifest_agent_policy_carries_old_max_iterations_only` 对 `allow_tool_calls` 的检查可能失败。
**验证**: 测试代码只检查 `tool_timeout_seconds` 和 `tool_execution_timeout_seconds` 不在 agent_policy 中，不检查 `allow_tool_calls`。现有 `smoke_host_public_conversation_memory` manifest 同样有 `allow_tool_calls: true` 并通过测试。
**结论**: 无冲突。但需确认 `_OLD_SCENE_MAX_ITERATIONS` 中新增条目值为 `32`。

### 反例 3: `--pressure-mode off` 下 D 场景 compaction 覆盖

**假设**: pressure off 时 compaction 不触发，D 场景的 "compaction 后 public answer continuity" 覆盖落空。
**验证**: Plan §6 规定 pressure off 时 "compaction 相关观察标为 soft skipped"。Plan §8 D 场景的 soft 观察已标注 "缺失不立即失败"，hard 断言只检查 marker/values 而不检查 compaction 是否发生。
**结论**: 设计正确。D 场景在 pressure off 时退化为纯 cross-turn facts consistency 验证。

### 反例 4: 长会话中 session 被 Host 关闭

**假设**: E 组长会话中 Host durability/cleanup 逻辑可能在所有轮次完成前关闭 session。
**验证**: Plan §9 hard assertion 规定每轮后 `host.get_session(session_id).status` 不是 `CLOSED`。这是正确的防御。但 plan 未说明 session 意外关闭时的处理（abort remaining rounds? skip to summary?）。这属于运行时异常处理，不属于 plan 规格缺陷。
**结论**: 低风险，implementation worker 在 `_run_round` 超时/失败处理中自然覆盖。

## Controller Questions

无。Plan 无 blocking issue，无需 controller 裁决。所有 N1-N5 可在 implementation slice 内由 implementation worker 合理决策。

## Verdict

**PASS** — Plan is handoff-ready and code-generation-ready.

5 个 non-blocking findings 均为 Low/Medium severity，不阻塞 implementation gate。N3 (E 组 prompt 未指定) 是最大的自由裁量空间，但 implementation worker 可以通过定义 `Final` 常量 prompt 缓解。

Implementation worker 在启动 S1 前应阅读 N1-N5，并在 completion report 中说明每个 finding 的处理方式。

## Artifact Path

`docs/reviews/gateflow-plan-review-public-memory-scenario-smoke-ds-20260526.md`
