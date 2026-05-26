# Code Review: Host Public Conversation Memory Smoke S1

- **Review artifact**: `docs/reviews/gateflow-code-review-conversation-memory-smoke-ds-20260526.md`
- **Reviewed slice**: S1 public finance conversation memory smoke
- **Approved plan commit**: `dbb9862`
- **Plan artifact**: `docs/reviews/gateflow-plan-conversation-memory-smoke-20260526.md`
- **Plan re-reviews**:
  - `docs/reviews/gateflow-plan-re-review-conversation-memory-smoke-mimo-20260526.md`
  - `docs/reviews/gateflow-plan-re-review-conversation-memory-smoke-ds-20260526.md`
- **Implementation artifact**: `docs/reviews/gateflow-implementation-conversation-memory-smoke-s1-20260526.md`
- **Reviewer role**: code review worker (not controller, not implementer)
- **Date**: 2026-05-26

---

## Verdict: PASS

No blocking findings. The implementation faithfully executes the approved plan and incorporates all controller corrections.

---

## Review Scope

| File | Status |
|---|---|
| `utils/smoke_host_public_conversation_memory.py` | 新增，1538 行 |
| `dayu/config/prompts/manifests/smoke_host_public_conversation_memory.json` | 新增，51 行 |
| `dayu/config/prompts/scenes/smoke_host_public_conversation_memory.md` | 新增，8 行 |
| `README.md` | 更新，手工 smoke 小节新增条目 |
| `docs/reviews/gateflow-implementation-conversation-memory-smoke-s1-20260526.md` | 新增，implementation artifact |

---

## 1. Public API Boundary — PASS

**运行期 Host 调用检查**：

脚本运行期仅使用以下 public Host handle 方法（`utils/smoke_host_public_conversation_memory.py:405-484`）：

- `open_host(assembly.options)` — async context manager
- `host.ensure_session(...)` — session 创建/复用
- `host.submit_followup(...)` — 每轮 prompt 提交
- `host.watch_session_events(session.session_id)` — 事件流监听
- `host.get_session(session.session_id)` — 每轮后 session 快照
- `host.get_run(run_id)` — 仅用于 terminal failure 摘要（line 877）

**未访问的私有内部路径**：

- 无 durable store、scheduler、command handle、EventLog reader 导入。
- 无 memory projection reader、conversation transcript 表、compact material builder 导入。
- 无 SQLite 查询 `.dayu/host/dayu_host.db` 或任何 memory/transcript 表。
- 无内部 memory snapshot 或 private compaction diagnostic object 读取。

**Assembly helper 使用**（line 497-552）：

`ConfigLoader`、`resolve_runtime_locations`、`discover_service_tools`、`prepare_scene`、`compose_open_host_options`、`compose_submit_followup_request` 均为 Host 打开前的 typed composition，不穿透 Host private command path。符合计划 §4 的 allow list。

---

## 2. Anti-Cheat 验证 — PASS

### 2.1 无 context slot 注入

- Manifest `context_slots: []`（`smoke_host_public_conversation_memory.json:49`）。计划要求 manifest schema 必须包含 `context_slots` 字段，使用空数组表示不声明任何 slot。
- `ScenePrepareRequest.context_slot_values={}`（line 521）。
- Manifest 中无 `fins_default_subject`、`base_user` 或任何隐藏 slot 声明。
- Scene prompt（`smoke_host_public_conversation_memory.md`）仅包含执行契约说明，不含公司名、财务数值或任何可泄露答案的内容。

### 2.2 被测公司仅出现在合法位置

搜索 `招商银行` 在全部新增文件中的出现位置：

| 位置 | 是否合法 |
|---|---|
| `_TARGET_COMPANY` 常量（line 107） | 合法 — 模块级常量 |
| `_FACT_*` 常量组（lines 111-118） | 合法 — 确定性事实常量 |
| `_ASSERTION_LINE`（lines 119-124） | 合法 — 断言核对行 |
| `_PRESSURE_CHUNK`（line 127） | 合法 — 压力文本标记 |
| `_mock_finance_fact_payload` 返回值（line 734） | 合法 — mock 工具证据 |
| Round 1-4 用户 prompt（lines 980, 999, 1018, 1033） | 合法 — 用户 prompt |
| `README.md` smoke 说明 | 合法 — 文档说明 |

Scene prompt 和 manifest 中均无 `招商银行`。无通过 scene context 泄露答案的路径。

### 2.3 manifest 模型与 runner 配置合理性

- `default_model_id: "mimo-v2.5-pro-plan"` — 可被 CLI `--model-id` 覆盖，不构成硬编码约束。
- `runner_option_hint_id: "interactive"` — 适合交互式 smoke 场景。

---

## 3. Mock Tool 与断言正确性 — PASS

### 3.1 MockFinanceFactTool 设计

- 类实现 `call_count`、`last_marker` 观测状态（lines 237-238）。
- `track_session()` 方法限定计数 scope 为本次 fresh session（lines 241-252），避免 Host recovery 旧 run 污染本次 smoke 断言。
- `__call__` 仅在 `context.session_id == self._tracked_session_id` 时递增计数（line 268），符合 controller correction "startup recovery of old runs may call the mock tool; assertions should measure this smoke session, not stale recovered sessions"。
- 参数 `include_pressure` 控制 `pressure_blob` 返回（line 731）：`true` 时填充 120,000 字符压力文本，`false` 时返回空字符串。返回 shape 稳定（字段始终存在），符合计划 §5。

### 3.2 工具实例恢复路径

`_find_mock_finance_fact_tool()`（lines 632-645）通过 `isinstance(definition.callable, MockFinanceFactTool)` 从 `assembly.effective_tool_bundle` 中恢复实例。不依赖模块级全局变量或外部副本。符合计划 §6 和计划 §8。

### 3.3 工具发现合并策略

`_discover_smoke_service_tools()`（lines 555-595）按三步安全合并：
1. 先通过 `discover_service_tools(config)` 获取 Service 工具。
2. 若已存在 `MockFinanceFactTool` 实例（可能来自 config），直接返回。
3. 若存在同名非 smoke 工具，抛出 `ValueError` 防冲突。
4. 否则通过 `ToolsDiscovery` 发现内置 smoke provider 并合并。

### 3.4 断言分层验证

| 轮次 | 硬断言 | Soft/log 观察 |
|---|---|---|
| Round 1 | terminal SUCCEEDED, final answer 非空, call_count==1, last_marker 匹配 | assertion line 缺失时打印 OBSERVE |
| Round 2 | terminal SUCCEEDED, final answer 非空, call_count==1 | assertion line 缺失时 soft-missing；不因格式遵循失败而否定 memory |
| Round 3 | terminal SUCCEEDED, final answer 非空, call_count==1 | 无内容断言；仅观察 answer preview |
| Round 4 | terminal SUCCEEDED, final answer 非空, call_count==1, marker/Hard check `1.88%`/`-0.14pct` | 自然语言"一致性"判断留给人工观察 |

断言分层与计划 §7 完全一致。

### 3.5 归一化策略

`_normalize_answer()`（lines 1277-1286）：去空白 + 统一全角百分号（`％`→`%`）+ 转小写。不依赖语义猜测或 LLM 判断。符合计划 §6 "不要做语义猜测"。

---

## 4. Context Pressure 与 Compaction 行为 — PASS

### 4.1 压力计算

`_compact_pressure_padding()`（lines 1040-1074）按 `OpenHostOptions.context_budget_policy` 计算 additive pressure：

1. 计算 soft/hard threshold token 数。
2. 目标 token 数 = min(soft + extra, hard - margin)，确保不突破 hard threshold。
3. 从目标中扣除 reserve 和 tool pressure 估算值，得到 prompt pressure token 数。
4. 使用 `DEFAULT_ESTIMATOR_CHARS_PER_TOKEN` 将 token 估算转为字符数。

tool pressure（`_SMOKE_TOOL_PRESSURE_CHARS = 120_000`）与 Round 2 prompt pressure 共同校准，非独立打满。符合计划 §5 additive pressure 要求。

### 4.2 压力文本构造

使用 ASCII-heavy 稳定 padding（`_PRESSURE_PAD_TOKEN`，lines 128-134），避免中文重复块导致 tokenizer 超预算。`_repeat_to_chars()` 逐行构造确保确定性。符合实现报告中的设计说明。

### 4.3 Compaction 观察

- `_print_compact_pressure_plan()` 打印 context window、soft/hard threshold、tool/prompt pressure chars、estimated tokens，不输出完整 pressure prompt。
- `_print_compact_summary()` 仅打印 compact artifact root 路径与文件数量，不读取 artifact 内容。
- compaction 是否实际发生仅作为日志观察项，不承载 pass/fail 权重。符合计划 §7。

---

## 5. Manifest / Scene / README 一致性 — PASS

### 5.1 Manifest

- `schema_version: 1`，`scene: "smoke_host_public_conversation_memory"`，与脚本 `_DEFAULT_SCENE_ID` 一致。
- `tool_selection.mode: "select"`，`tool_tags_any: ["manual-smoke"]`，`allow_empty: false`。与 smoke tool 注册 tag 一致。
- `fragments` 引用 `base/agents.md`、`base/fact_rules.md`、`scenes/smoke_host_public_conversation_memory.md`，顺序合理。
- `agent_policy.max_iterations: 20`，对四轮 smoke 充足。

### 5.2 Scene Prompt

仅包含执行契约：优先回答财务问题、按允许工具调用、不披露 smoke 细节、按用户要求输出核对行、输出 Markdown 格式。无公司名、财务数值或任何预先植入的答案。

### 5.3 README

新增条目位于"手工 smoke"章节（README.md:982-992），包含：
- 脚本用途（验证多轮 conversation memory continuity）
- 运行命令
- mock tool 说明（不调用真实 Fins）
- 四轮结构简述
- stdout 关键输出
- 通过标志

无内部 memory 表、EventLog 查询步骤。符合计划 §10。

---

## 6. 项目规则合规性 — PASS

### 6.1 严格类型

- 无 `Any`、`object`、无类型参数、无类型返回值。
- 所有函数签名完整标注参数与返回类型。
- 使用 `Final` 标注模块级常量。
- 使用 `| None` 联合类型语法（Python 3.11）。
- pyright 验证：`0 errors, 0 warnings, 0 informations`（implementation report 确认）。

### 6.2 中文 Docstring

- 模块、类（`SmokeArgs`、`RoundResult`、`RuntimeAssemblyResult`、`MockFinanceFactTool`）均有中文概览 docstring。
- 所有函数均有中文 docstring，包含 `:param`、`:returns`、`:raises`。
- 复杂逻辑（如 `track_session`、`_discover_smoke_service_tools`）有清晰的中文行内注释说明意图。

### 6.3 禁止项检查

- 无 `hasattr` / `getattr` 使用。
- 无 lazy import。
- 无 God object / God function / God dataclass。
- 无兼容性 re-export 或 wrapper/facade。
- 无魔法数字/字符串（除工具 schema 内字段名字面量，符合例外规则）。
- 模块级常量集中在文件顶部（lines 95-166），命名统一使用 `_UPPER_CASE` 前缀。

### 6.4 分层架构

- 脚本位于 `utils/`（分析辅助代码），不导入 `dayu.engine` / `dayu.host` 私有内部模块。
- 通过 `dayu.service.host_assembly` 的 public helper 完成 Host 打开前组装，符合分层约束。

---

## 7. Non-blocking Findings

### N1: `_compact_pressure_reserve_tokens` 条件分支相同

- **文件**: `utils/smoke_host_public_conversation_memory.py:1089-1099`
- **证据**: `if context_window_size >= _COMPACT_PRESSURE_LARGE_WINDOW_TOKENS` 的 if/else 两个分支均返回 `_COMPACT_PRESSURE_RESERVE_TOKENS`（8192）。
- **影响**: 对当前目标模型（大窗口）无实际影响。既有 `smoke_host_public_multiturn` 对小窗口有差异化逻辑（加 tool pressure estimate），此处简化可能在未来小窗口模型上产生偏差。
- **建议**: 若为有意简化，可合并为单 return 语句消除死分支；若为预留扩展点，建议加注释说明意图。
- **严重程度**: 低，不影响当前 smoke 正确性。

### N2: `_compact_pressure_padding` 重复计算

- **文件**: `utils/smoke_host_public_conversation_memory.py:1040, 1354`
- **证据**: `_print_compact_pressure_plan()`（line 1354）和 `_round2_prompt()`（line 997）各调用一次 `_compact_pressure_padding(options)`。函数为纯计算，结果确定性相同。
- **影响**: 微小性能开销（两次构造相同的压力文本）。不导致行为差异。
- **建议**: 可在 `_print_compact_pressure_plan` 中仅打印估算值而不构造完整 padding，或缓存结果。
- **严重程度**: 低，不影响正确性。

### N3: `_DEFAULT_SUBJECT` 常量重命名为 `_TARGET_COMPANY`

- **文件**: `utils/smoke_host_public_conversation_memory.py:107`
- **证据**: 计划常量 inventory 中命名为 `_DEFAULT_SUBJECT`，实现使用 `_TARGET_COMPANY`。
- **影响**: 无。`_TARGET_COMPANY` 语义更准确（表示被测公司而非"默认主体"），计划已允许命名微调。
- **严重程度**: 信息性，非缺陷。

---

## 8. Tests/Validation Reviewed

| 验证项 | 结果 | 来源 |
|---|---|---|
| `pytest tests/runtime/test_scene_prepare.py tests/runtime/test_smoke_host_public_multiturn_assembly.py tests/service/test_host_assembly.py -q` | 58 passed in 0.79s | implementation report |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations | implementation report |
| `python utils/smoke_host_public_conversation_memory.py --log-level VERBOSE` | `SMOKE PASS`，tool call count=1，Round 4 assertion status=pass，compact artifact count=4 | implementation report |

---

## 9. Residual Risks

1. **LLM 格式遵循不可控**: Round 2/4 依赖模型输出 marker 和核对行。当前采用 soft assertion + 归一化精确匹配策略缓解，但极端情况下模型可能完全忽略格式要求。此风险为 LLM-in-the-loop 固有，非代码缺陷。
2. **Compaction 发生时机不确定**: proactive/background compaction 不由脚本控制。脚本仅通过日志观察 artifact 文件数，不将 compaction 发生/未发生作为 pass/fail 条件。
3. **Provider/模型可用性**: API key、endpoint、quota/rate-limit 故障会导致手工 smoke 失败，属于环境问题而非代码问题。
4. **不覆盖真实 Fins 路径**: 此 smoke 使用 mock tool，不验证真实财报工具、财报仓储或真实财报数值。
5. **不读取内部 memory 状态**: public API 下无法直接证明 pinned_state/episode summary 的具体内容，只能通过"禁用工具 + 后轮值不漂移"形成后验证据。

---

## Review Conclusion

**Verdict: PASS.** 实现完整且正确地执行了批准计划的全部要求。关键检查项全部通过：

- Public API boundary 严格遵守，无私有内部访问。
- Anti-cheat 措施完备：无 context slot 注入、无 scene prompt 泄露、被测公司仅出现在合法位置。
- Mock tool 设计正确，session-scoped 计数防止 recovery 污染。
- 断言分层与计划 §7 一致，硬断言聚焦关键路径，soft observation 覆盖观测项。
- Pressure 校准遵循 additive 原则，不独立打满两段压力。
- Manifest / scene / README 与运行时 assembly 一致。
- 项目规则合规：完整类型标注、中文 docstring、无禁止模式。

3 个 non-blocking findings 均为低严重度，不影响 smoke 正确性或可运行性。
