# gateflow aggregate deepreview — public memory scenario smoke (DS, 2026-05-26)

## 审查范围

`git diff e38913c..HEAD`，共 30 files, +6100/-2 lines。包含 S1a/S1b/S2/S3/S4 五个已通过各自 slice review 的 committed slice。

## 审查结论

**PASS。** 无阻塞问题。所有 slice 的 committed 状态一致、测试通过、pyright 干净、文档准确、无隐藏的私有持久化读取或装配边界破坏。

---

## Findings

### F1. [INFO] 非阻塞 — Provider display path 使用 `__main__` 前缀

**文件:** `utils/smoke_host_public_conversation_memory_scenarios.py:108`

```python
_PROVIDER_IMPORT_DISPLAY_PATH: Final[str] = "__main__:discover_smoke_tools"
```

该常量用于构造 `PythonImportPathProvider(import_path=...)` 并放入 `ToolsDiscoveryProviderSpec.location`。在当前 smoke 脚本中，实际 callable 通过 `discover_from_bindings(provider=discover_smoke_tools)` 直接传入，`spec.location` 不会被 `discover_from_bindings` 解析 — `ToolsDiscovery().discover_from_bindings()` 只调用已传入的 `binding.provider`，不经过 `resolve_provider_callable` 路径（参见 `dayu/runtime/tools_discovery.py:216-264`）。因此当前无功能影响。

**风险：** 该 `spec.location.import_path` 会出现在 provider diagnostics 和 source refs 中。如果未来有人复制此 pattern 并使用 `ToolsDiscovery().discover()`（会实际解析 import path），`__main__:discover_smoke_tools` 将无法解析（模块导入时 `__main__` 是调用脚本而非 `utils.smoke_host_public_conversation_memory_scenarios`）。建议将 display path 改为与 assembly test 一致的 `utils.smoke_host_public_conversation_memory_scenarios:discover_smoke_tools`。**现有模式继承自 `smoke_host_public_multiturn.py:101`，并非本 diff 引入的新问题。**

### F2. [INFO] 非阻塞 — 直接导入 `dayu.host.context_budget` 子模块

**文件:** `utils/smoke_host_public_conversation_memory_scenarios.py:68`

```python
from dayu.host.context_budget import DEFAULT_ESTIMATOR_CHARS_PER_TOKEN
```

`DEFAULT_ESTIMATOR_CHARS_PER_TOKEN` 是 `dayu.host.context_budget` 模块 `__all__` 中的公开常量（值 3），用于保守 token 估算。但该常量未从 `dayu.host.__init__` 重导出，因此 smoke 脚本直接导入 Host 子模块。`context_budget.py` 是 Host context governance 层的公共契约模块，不是私有实现 — 它定义了 `ContextBudgetPolicy` dataclass 和 estimator helper，被 smoke 脚本仅用于 `_estimate_chars_as_tokens` 的整数除法。不构成私有实现泄露。

**建议：** 如果后续 `DEFAULT_ESTIMATOR_CHARS_PER_TOKEN` 被提升到 `dayu.host.__init__` 重导出，可统一为顶层导入。当前无功能影响。

### F3. [PASS] Smoke 脚本确实只走 Host public API

**验证方式：** 全文搜索 `durable|event_log|memory_table|compact_payload|db_path|sqlite`（不区分大小写），仅在模块 docstring 第 9 行出现一次，声明脚本"不读取 durable store、EventLog、memory 表、compact payload 内容"。

**实际使用的 Host 接口：**
- `open_host(options)` — public constructor
- `host.ensure_session(request)` — public session management
- `host.submit_followup(session_id, request)` — public run submission
- `host.watch_session_events(session_id)` — public event streaming
- `host.get_session(session_id)` — public session snapshot
- `host.get_run(run_id)` — public run snapshot（仅在 `_terminal_failure_summary` 错误路径中使用）

**装配使用的接口（非 Host private）：**
- `ConfigLoader` / `resolve_runtime_locations` / `prepare_scene` — `dayu.runtime` 基础设施
- `discover_service_tools` / `compose_open_host_options` / `compose_submit_followup_request` — `dayu.service` 装配 helper
- `ToolsDiscovery().discover_from_bindings()` — runtime 工具发现
- `MockFinanceMemoryTool` — 脚本自有 mock，不经过真实 Fins 工具链

无反向依赖、无不通过 public API 的私有实现调用。**通过。**

### F4. [PASS] Manifest 无 context_slots 作弊

**文件:** `dayu/config/prompts/manifests/smoke_host_public_conversation_memory_scenarios.json`

- `context_slots: []` — 空数组，不需要任何运行时 context slot 值。
- `tool_selection.mode: "select"`, `tool_tags_any: ["manual-smoke"]` — 只选择带 `manual-smoke` tag 的工具。
- `fragments` 仅引用 `base/agents.md`, `base/fact_rules.md`, `scenes/smoke_host_public_conversation_memory_scenarios.md` — 标准 base + scene 组合。
- `agent_policy.max_iterations: 32` — 与 migration test 中的 `_OLD_SCENE_MAX_ITERATIONS` 映射值一致。
- 顶层字段只包含 `_ALLOWED_MANIFEST_FIELDS` 白名单内的字段，`model` 子对象只包含 `_ALLOWED_MODEL_FIELDS` 白名单，不包含旧 `conversation` / `runtime` / `default_name` / `temperature_profile` 字段。

**通过。**

### F5. [PASS] Scene markdown 无答案写死

**文件:** `dayu/config/prompts/scenes/smoke_host_public_conversation_memory_scenarios.md`

全文 8 行，核心规则：
- "优先回答用户当前财务问题" — 通用指引
- "当用户要求输出 `DAYU_MEM_ASSERT` 或同类核对行时，按用户给定字段原样输出" — 按用户给定字段输出，不预设值
- "如果会话里没有确认过某个事实，明确说明没有确认，不要编造数值" — 反幻觉约束

不包含任何具体数值、公司名称、ticker、marker、百分比或事实。每个 scenario 的具体 assert 文本由 smoke 脚本的 prompt 构造，不由 scene markdown 决定。**通过。**

### F6. [PASS] Assembly test 覆盖关键边界，非脆弱

**文件:** `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`

11 个测试，覆盖：

| 测试 | 覆盖边界 | 评估 |
|------|---------|------|
| `test_runtime_assembly_adds_builtin_mock_tool_and_selects_manual_smoke` | 真实 `_prepare_runtime_assembly` 路径，验证 tool selection 与 provider report | 正确 — 测试真实装配 |
| `test_runtime_assembly_fails_closed_on_non_smoke_same_name_tool` | workspace overlay 同名非 smoke 工具时 fail closed | 正确 — 防御性边界 |
| `test_cli_bounds_for_suite_and_long_rounds` | `--suite` 三种值和 `--long-rounds` 20..25 边界 | 正确 — CLI 边界 |
| `test_pure_spec_selection_counts_and_long20_final_label` | core/long/all 工具调用累计与 long20 最终 recap 轮标签 | 正确 — 规格选择逻辑 |
| `test_byd_long_input_is_deterministic_with_expected_anchors` | C2 长输入确定性与 anchor 约束 | 正确 — 长输入契约 |
| `test_mock_finance_memory_tool_tracks_session_and_calls_by_key` | MockFinanceMemoryTool session 追踪与 calls_by_key 摘要 | 正确 — mock 行为 |
| `test_pressure_off_and_padding_helper_cover_runtime_pressure_bounds` | pressure=off 与 auto padding 估算范围 | 正确 — pressure 契约 |
| `test_answer_normalization_contains_and_forbidden_behavior` | 归一化与硬断言路径 | 正确 — 断言 helper |
| `test_discover_smoke_tools_contract_exposes_single_manual_tool` | 内置 provider 输出 shape | 正确 — provider 契约 |
| `test_smoke_uses_fresh_session_slot_by_default` | fresh vs reuse slot key 语义 | 正确 — slot 语义 |
| `test_find_mock_tool_uses_discovered_bundle_shape` | 从 ToolBundle 恢复 callable 的类型正确性 | 正确 — 类型边界 |

测试不依赖真实 LLM、不读取 durable store、不断言 Host 内部状态。断言针对 typed 公共 contract 输出，不是脆弱实现细节。**通过。**

### F7. [PASS] Migration test 正确新增 scene 映射

**文件:** `tests/runtime/test_scene_assets_migration.py:30`

diff 仅新增一行：
```python
"smoke_host_public_conversation_memory_scenarios": 32,
```

该值 (32) 与 manifest 中 `agent_policy.max_iterations: 32` 一致。migration test 的 `test_all_migrated_scene_assets_prepare_successfully` 通过 `prepare_scene` 遍历所有 manifest 并验证装配成功，自动覆盖了新 scene。测试通过（17 passed）。**通过。**

### F8. [PASS] README 与 tests/README 准确

**文件:** `README.md` (section 5.3), `tests/README.md` (assembly helpers 段落)

**README.md 5.3 节：**
- 正确声明 `--suite core` 默认，`--suite long` 需显式指定，`--suite all` 两者皆运行。✓
- 正确声明"不读取 durable DB、EventLog、memory 表或 compact payload 内容"。✓
- 正确声明"只注入 `manual-smoke` mock finance tool"。✓
- pass marker 文本 `SMOKE PASS public Host conversation memory scenario smoke` 与脚本 line 1780 一致。✓（S4 fix 已修正）
- 章节编号：5.1 → 5.2 → 5.3(新增) → 5.4(原 5.3 顺延)，连贯无跳跃。✓

**tests/README.md assembly helpers 段落：**
- 正确描述覆盖范围："CLI suite 解析、mock finance tool 装配、tool selection、pressure 文本和 slot key 语义"。✓
- 未声称覆盖真实 LLM 调用、Host 端到端或 durable 读写验证。✓
- 新增的 runner command 按字母序追加在 `test_smoke_host_public_multiturn_assembly.py` 之后。✓

**通过。**

### F9. [PASS] Gateflow 状态与 residual tracking 完整

所有切片 review artifacts 均在 `docs/reviews/` 下，命名规范一致：
- S1a/S1b/S2/S3/S4 各有一组 code-review + fix + re-review artifact
- Controller adjudication artifacts 覆盖 plan 与争议裁决
- 所有 slice review 结论均为 PASS，无开放 blocking issue

S4 review artifacts 明确记录了 residual risks：
1. public smoke 仅通过最终回答间接验证 conversation memory 语义 — owner：Host memory 单元/集成测试
2. 真实 provider 行为未在本 review 中运行 — owner：operator 按 README 手工执行

这两项 residual 在项目架构约束下是合理的 — smoke 脚本的设计意图就是 public API only 的可手工执行验证。**通过。**

---

## Residual Risks（非阻塞）

| # | Residual | 缓解措施 | Owner |
|---|----------|---------|-------|
| R1 | 真实 LLM smoke 未在本次 review 运行（需要 provider secret + 网络 + 成本） | README 5.3 节提供完整 CLI 命令，operator 按需手工执行 | operator |
| R2 | conversation memory 语义仅通过 final answer 间接验证，不经 durable table 验证 | Host-level `test_memory_projection.py`、`test_run_input_builder.py` 等覆盖 memory 物化语义 | Host memory 测试套件 |
| R3 | `_PROVIDER_IMPORT_DISPLAY_PATH` 使用 `__main__` 前缀，若未来切换为 `ToolsDiscovery().discover()` 会失败 | 不改 pattern 则无功能影响；该 pattern 继承自 `smoke_host_public_multiturn.py`，非本次引入 | 后续统一清理 |

---

## 验证汇总

| 项目 | 状态 |
|------|------|
| pyright (utils/smoke_*.py + tests/runtime/test_*assembly*.py + test_scene_assets_migration.py) | 0 errors, 0 warnings |
| pytest (17 tests) | 17 passed in 0.82s |
| Smoke 脚本 Public API 合规 | PASS |
| Manifest schema 合规 | PASS |
| Scene markdown 无答案写死 | PASS |
| Assembly test 边界覆盖 | PASS |
| Migration test 覆盖 | PASS |
| README / tests README 准确 | PASS |
| Gateflow artifact 完整 | PASS |
