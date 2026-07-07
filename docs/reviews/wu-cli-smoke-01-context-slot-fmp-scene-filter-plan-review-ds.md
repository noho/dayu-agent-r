# WU-CLI-SMOKE-01 Context Slot / FMP / Scene Tool Filtering Plan Review — AgentDS

## Review Metadata

- **Reviewer**: AgentDS
- **Date**: 2026-07-07 15:08 CST
- **Plan artifact**: `docs/host/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan.md`
- **Design sources**: `docs/host/design.md`, `docs/engine/design.md`
- **Control doc**: `docs/host/issues-implementation-control.md`
- **Review scope**: per user directive — root cause accuracy, package placement, slice readiness, checkpoint commit 2a61fbfd protection, upload/FMP-api/empty-slot/base_user/current_time correctness, validation matrix coverage
- **Review conclusion**: **pass-with-findings**

## Assumptions Tested

| # | Assumption | Verdict |
|---|-----------|--------|
| A1 | `ScenePrepare.prepare()` 先渲染 fragment 再选工具，导致 `<when_tool>/<when_tag>` 未解释 | **成立** — 直接证据: `dayu/runtime/scene_prepare.py:464` 先 `_render_fragment_content`, `:473` 再 `_select_tools` |
| A2 | CLI 把 raw `--ticker` 字符串直接映射到 context slot | **成立** — 直接证据: `dayu/cli/commands/prompt.py:651` 行 `CONTEXT_SLOT_FINS_DEFAULT_SUBJECT: (ticker if ticker is not None else DEFAULT_FINS_SUBJECT)` |
| A3 | OLD 仓库有可复用 FMP 能力，新仓 `dayu.fins` 无 resolver 子包 | **成立** — OLD: `dayu-agent/dayu/fins/resolver/fmp_company_alias_resolver.py` 存在; 新仓: `dayu-agent-r/dayu/fins/` 无 `resolver/` 子目录 |
| A4 | 推荐落点符合分层边界 | **成立** — `dayu.runtime.scene_prepare` 不 import fins/service/host/engine/ui; `dayu.fins` README 明确包根不导出业务符号 |
| A5 | 3 slices 形成可独立验证的行为闭环 | **成立但有 findings** — 见 Finding DS-F02, DS-F03 |
| A6 | 验证矩阵覆盖 runtime/service/cli/fins/config/docs/real smoke | **成立但有 gap** — FMP fake-HTTP 测试路径未显式说明与 OLD 测试夹具的关系 |

## Root Cause 判断评估

Plan 识别三个根因，均得到直接代码证据支撑：

1. **ScenePrepare 未实现 when_tool/when_tag 过滤** — 确认。`tools.md` 中 `<when_tag doc>` (行 27), `<when_tag fins>` (行 39), `<when_tag ingestion>` (行 67), `<when_tag web>` (行 74), `<when_tool get_current_time>` (行 81) 当前作为普通 markdown 文本进入 LLM。`prepare()` 方法行 464-476 先渲染 fragment 再选工具，条件块在渲染时无解释能力。

2. **Slot 生成散落且 raw ticker/default 文本进入 LLM** — 确认。`prompt.py:651` 直接传 `ticker` raw string; `interactive.py:910` 同样; `session.py:653` 传 `"未指定具体公司"` 常量和 `"本地 CLI 用户"`. 违反 CLAUDE.md LLM-facing 文本约束：模型应看到自解释业务文本。

3. **FMP resolver 缺少新仓 public contract** — 确认。OLD `fmp_company_alias_resolver.py` 实现了两跳算法 (`search-symbol` -> `search-name`) 和严格同名过滤，但使用 `Any` 类型、`os.environ` 隐式读 key、`urllib.request.urlopen` 无 Protocol 抽象。新仓 `dayu/fins/` 无 `resolver/` 子包。

根因判断准确，无遗漏、无误判。

## Findings

### DS-F01 — 高 — `base/soul.md` 未列入 affected files，`base_user` 删除存在跨文件遗漏风险

- **位置**: Plan §Affected Files / Modules, §Slice S2, §Slice S3
- **问题类型**: 切片遗漏 / 不可直接实施
- **当前写法**: Plan 列出 `dayu/config/prompts/scenes/*.md` 为允许修改文件，但 `base_user` 删除也需修改 `dayu/config/prompts/base/soul.md`（该文件第 1 行含 `{{base_user}}`）。Plan S2 说 "base_user 常量、slot name、测试期望全部删除"，S3 说 "{{fins_default_subject}} 只放在需要默认研究主体的 scene .md 中"，但均未提及 `soul.md` 的 `{{base_user}}` 引用。
- **反例/失败场景**: Implementation agent 按 plan 删除 manifest 中 `base_user` context slot 声明后，`ScenePrepare._render_fragment_content` 在解析 `base/soul.md` 的 `{{base_user}}` placeholder 时会抛出 `ScenePrepareError("unknown placeholder in fragment base_soul: base_user")`。因为 manifest 不再声明该 slot，placeholder 匹配后 `slot_names` frozenset 中无 `base_user`，触发 `_replace_placeholders` 行 1067-1068 的错误。
- **为什么有问题**: 虽然测试会捕获此错误，但 plan 作为 code-generation-ready artifact 应显式列出所有需要修改以完成 `base_user` 删除的文件。遗漏 `soul.md` 会导致 S2/S3 实施时出现预期外的 `ScenePrepareError`，增加 rework 轮次。
- **直接证据**:
  - `dayu/config/prompts/base/soul.md:1` 当前含 `{{base_user}}`（checkpoint commit 2a61fbfd 仅做 whitespace 归一，未删除引用）
  - `dayu/runtime/scene_prepare.py:1067-1068`: `if slot_name not in slot_names: raise ScenePrepareError(...)`
  - Plan 的 allowed files 列表仅含 `scenes/*.md` 和 `base/tools.md`，不含 `base/soul.md`
- **影响**: 实施 Agent 需自行发现 soul.md 引用 → 额外修复轮次 → 或测试失败后被动修复
- **建议改法和验证点**:
  1. 在 S2 或 S3 的 allowed files 中显式加入 `dayu/config/prompts/base/soul.md`
  2. 若 `base_user` 完全删除，soul.md 中需移除 `你的名字是:{{base_user}}` 行，或将整行替换为固定 persona 文本（如 `你的名字是:大禹`）
  3. 验证：`grep -r "base_user" dayu/config/prompts/` 返回空
- **修复风险**: 低 — 单文件修改，语义明确
- **严重程度**: 高

### DS-F02 — 中 — 空 slot 行清理规则存在两种不可组合的机制

- **位置**: Plan §Slice S1 (过滤规则), §Slice S3 (空 slot 行处理)
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: S1 说 "删除后对 3 个及以上连续空行压缩为 2 个换行"；S3 说 "对含空 slot 的 standalone placeholder 行，渲染后必须移除该行"。这两个规则作用于不同阶段且判断标准不同：一个是 post-filter compression，一个是 post-render line removal。Plan 未说明它们的执行顺序、是否同时生效、以及 "standalone placeholder 行" 的精确定义（仅含 placeholder 和空白？还是 placeholder 所在行全部内容替换后为空？）。
- **反例/失败场景**:
  1. 某 fragment 中 `<when_tag ingestion>...</when_tag>` 块被整体删除后留下 3 个连续空行 → S1 规则压缩为 2 个换行 → 再经 `"\n\n".join(rendered_messages)` 拼接 → 可能在 fragment 边界产生额外空行。
  2. `scenes/prompt.md:7` 内容为 ` {{fins_default_subject}}`（行首空格 + placeholder）。如果 `fins_default_subject` 返回 `""`，渲染后该行内容为 ` `（仅空格），既不算完全空行，也不明确属于 "standalone placeholder 行"。
  3. fragment 经条件块过滤后内容全空，`rendered_messages` 含 `""` 元素 → `"\n\n".join(...)` 产生连续 `\n\n` 分隔符。
- **为什么有问题**: Implementation agent 需自己裁决这两种机制的交互方式，可能在边界 case 做出与 reviewer 预期不一致的选择。规则不够精确，code-generation 时存在歧义。
- **直接证据**:
  - Plan §S1 过滤规则第 6 条: "3 个及以上连续空行压缩为 2 个换行"
  - Plan §S3 Key decisions 第 2 条: "含空 slot 的 standalone placeholder 行，渲染后必须移除该行"
  - `dayu/runtime/scene_prepare.py:500`: `system_prompt="\n\n".join(rendered_messages)` — 空 fragment 产生额外分隔符
- **影响**: 实施 Agent 自行裁决 → review 可能推翻 → 返工
- **建议改法和验证点**:
  1. 明确空行清理只有一个规则：条件块过滤和 placeholder 替换后，对每个 fragment 独立执行"行内容经 strip 后长度为 0 则移除该行"，然后 `rendered_messages` 中排除空字符串再 join。
  2. 或明确两个规则的顺序和作用域：先 per-fragment 移除 standalone placeholder 行（定义：原始行内容去掉前后空白后等于 `{{slot_name}}` 且替换值为空），再对全量 system_prompt 压缩 3+ 连续空行。
  3. 测试需覆盖：fragment 全空、placeholder 行带前导空白、placeholder 行含其他文本且 slot 为空（应保留该行其它文本）、条件块删除后产生多个空行。
- **修复风险**: 低 — 规则澄清，不改变架构
- **严重程度**: 中

### DS-F03 — 中 — `current_time` slot 的 LLM-facing 文本格式未指定

- **位置**: Plan §推荐落点 / Slot LLM-facing function
- **问题类型**: 契约缺失
- **当前写法**: Plan 定义 `current_time(now: datetime | None = None) -> str` 函数签名，说明 "只返回可读时间文本，不暗示财报事实"，但未给出 LLM-facing 输出格式示例或规范。
- **反例/失败场景**: Implementation agent 可能返回 `"2026-07-07T15:08:31+08:00"`（ISO 格式）、`"2026年7月7日 15:08"`（中文格式）、或 `"# 当前时间\n现在是 2026-07-07 15:08:31 CST"`（markdown 标题格式）。不同格式对 LLM 的可读性和 prompt 布局影响不同，如果格式不当（如 ISO 格式），LLM 可能误解析为数据字段而非上下文信息。
- **为什么有问题**: LLM-facing 文本的格式直接影响模型理解。Plan 要求 "slot 文本是 LLM-facing"，但未给出格式规范，等于把设计决策下放给 implementation agent，增加了 review 返工风险。
- **直接证据**:
  - Plan 行 97-98: "current_time(now: datetime | None = None) -> str" "只返回可读时间文本"
  - 无格式示例或约束说明
  - `fins_default_subject` 有明确的 OLD 格式参考（`# 当前分析对象\n你正在分析的是 V（Visa Inc.）。`），`current_time` 没有
- **影响**: 实施 Agent 自行选择格式 → review 可能要求修改 → 返工
- **建议改法和验证点**:
  1. 指定 `current_time` 返回格式，例如：`"# 当前时间\n现在是 2026年7月7日 15:08 CST（星期二）。"` 或更简洁的 `"当前时间：2026年7月7日 15:08 CST"`
  2. 格式约束：使用 `Asia/Shanghai` 时区，中文星期，24 小时制，不暴露 ISO 时间戳
  3. 测试需覆盖格式断言
- **修复风险**: 低 — 格式规范补充
- **严重程度**: 中

### DS-F04 — 中 — FMP API key env var 名称未在 plan 中指定，implementation agent 需自行查找或发明

- **位置**: Plan §Slice S2 (FMP resolver), §Risks / Open Questions
- **问题类型**: 契约缺失
- **当前写法**: Plan 说 "FMP resolver 接收显式 api_key，不在 Fins 内部读 env；Service/CLI 装配层从 env/config 读取并决定是否启用公司名增强"。但未指定 env var 名称。OLD 代码使用 `dayu.contracts.env_keys.FMP_API_KEY_ENV`；新仓 `dayu.contracts` 是否已有该常量需 implementation agent 自行核实。
- **反例/失败场景**: Implementation agent 需 grep 现有代码、检查 `dayu.contracts.env_keys`、或参考 OLD 代码才能确定 env var 名称。若自行发明新名称，可能与已有配置或用户环境不一致。
- **为什么有问题**: Plan 作为 code-generation-ready artifact，应对 implementation agent 屏蔽此类查找开销。env var 名称是 FMP resolver 的外部依赖契约，plan 应显式引用。
- **直接证据**:
  - OLD `fmp_company_alias_resolver.py:23`: `from dayu.contracts.env_keys import FMP_API_KEY_ENV`
  - Plan §Open Questions: "FMP API key 配置来源：OLD 直接读环境变量。新方案建议 FMP resolver 接收显式 key，Service/CLI 从 env/config 注入"
  - 未指明具体 env var 名称或 constants 路径
- **影响**: 实施 Agent 需自行查找 → 可能选错 env var → 用户环境不兼容
- **建议改法和验证点**:
  1. 在 plan 中显式指定 env var 名称（例如复用 `FMP_API_KEY_ENV` 或指定新常量路径）
  2. 若 `dayu.contracts` 当前无该常量，应在 plan 中说明是否新增
  3. 测试需覆盖 env var 注入路径
- **修复风险**: 低 — 名称确认
- **严重程度**: 中

### DS-F05 — 低 — Service slot 模块名二选一未收敛

- **位置**: Plan §推荐落点 / Slot LLM-facing function
- **问题类型**: 不可直接实施
- **当前写法**: Plan 说 "新增 `dayu.service.prompt_context` 或 `dayu.service.scene_context`"，未做出选择，也未给出选择标准。
- **反例/失败场景**: Implementation agent 需自行决定模块名，若两个 reviewer 偏好不同，可能导致 rework。模块名影响后续 import 路径和 README 文档中的引用。
- **为什么有问题**: Plan 应收敛到一个确定的模块名。两个候选名暗示 plan author 在命名上有未决的 tradeoff，但 plan 未说明 tradeoff 是什么、如何选择。
- **直接证据**: Plan 行 91: "新增 `dayu.service.prompt_context` 或 `dayu.service.scene_context`"
- **影响**: 轻微 — 模块名差异不影响功能，但增加了不必要的决策负担
- **建议改法和验证点**: plan 收敛到单一模块名。推荐 `scene_context`（更准确反映职责：context slot values 服务于 scene assembly，不仅限于 prompt scene）
- **修复风险**: 低
- **严重程度**: 低

### DS-F06 — 低 — FMP resolver contract 中 `ticker_aliases` 类型从 OLD 的 `list[str]` 变为 `tuple[str, ...]` 未说明理由

- **位置**: Plan §推荐落点 / FMP public contract
- **问题类型**: 契约缺失
- **当前写法**: Plan 定义 `FmpCompanyInfo(canonical_ticker: str, company_name: str, ticker_aliases: tuple[str, ...])`。OLD 代码 `FmpAliasInferenceResult` 使用 `ticker_aliases: list[str]`。Type mutation 合理（不可变优于可变），但 plan 未说明此变更。
- **反例/失败场景**: 若后续有人基于 OLD 代码的行为假设 alias 是 mutable list，会产生类型错误。
- **为什么有问题**: 微小的类型变更不会导致功能问题（pyright 会捕获），但 plan 应透明说明从 OLD 迁移时的契约变更。
- **直接证据**:
  - OLD `fmp_company_alias_resolver.py:39`: `ticker_aliases: list[str]`
  - Plan 行 114: `ticker_aliases: tuple[str, ...]`
- **影响**: 可忽略 — pyright 会捕获类型不匹配
- **建议改法和验证点**: plan 补充说明 "OLD 的 list[str] 改为 tuple[str, ...] 以符合不可变公共契约"
- **修复风险**: 低
- **严重程度**: 低

## Open Questions

1. **FMP API key 在 Service assembly 中的注入点**：Plan 说 Service/CLI 从 env/config 读取 FMP key 并注入到 resolver。目前 `EntrypointRuntimeRequest` 是否已有字段可承载此配置？是否需要新增 optional field？Plan 将此事归入 Open Questions，在 plan gate 可以接受，但 implementation 前应确认。

2. **`utils` tag vs `utils/time` tag 的语义**：Plan S1 说 `prompt.json` 使用 `utils/time` tag。Util time tag selection follow-up 已完成（control doc 记录），但 plan 中写的是 `utils/time` 而非 `utils`。当前 `prompt.json` 仍写 `"utils"`（checkpoint commit 保持了 `utils`）。需确认 `get_current_time` 的实际 tag 是 `utils` 还是 `utils/time`，确保 tag 选择语法与工具 tag 一致。

3. **`soul.md` 中 `{{base_user}}` 的替换目标**：若 `base_user` 完全删除，soul.md 中 `你的名字是:{{base_user}}` 行应改为固定 persona 文本（如 `你的名字是:大禹`）还是直接删除？Plan 未说明。当前 checkpoint commit 保留了该引用。

## 验证矩阵评估

Plan 的验证矩阵覆盖：

| 层 | 自动测试 | 手工验证 | 评估 |
|---|---------|---------|------|
| Runtime (scene filtering) | `test_scene_prepare.py`, `test_scene_tool_selection.py`, `test_scene_assets_migration.py` | — | 充分 |
| Service (assembly/entrypoint) | `test_entrypoint_runtime*.py`, `test_host_assembly.py` | — | 充分 |
| CLI (context slots) | `test_prompt_command.py`, `test_interactive_command.py`, `test_session_command.py` | — | 充分 |
| Fins (resolver) | `test_fmp_company_info_resolver.py` | 真实 FMP key smoke | 充分。需确认新测试使用 fake HTTP client 覆盖成功/失败/无 key 路径 |
| Config (manifests/scenes) | 通过 runtime tests 间接覆盖 | — | 可接受。manifest/slot 变更由 runtime test 的 system_prompt 断言覆盖 |
| Docs | — | README review | 可接受 |
| Real smoke | — | prompt --ticker V / prompt no-ticker | 可接受。手工 smoke 依赖外部 key，不进入 CI |

Validation gap: FMP 新测试与 OLD 测试的关系未说明。OLD `fmp_company_alias_resolver.py` 的测试是否需要迁移或参考？Plan 说"实现从 OLD 迁移两跳算法"，但未说明测试夹具是否可复用 OLD 的 fake FMP response 数据。

## Residual Risks

| Risk | Severity | Suggested tracking |
|------|---------|-------------------|
| 条件块语法未来需要嵌套支持 | 低 | 当前 non-goal；若未来 tools.md 复杂度增长需要嵌套条件，再扩展 parser |
| FMP API 配额/rate-limit 场景下 `fins_default_subject` 的 fallback 延迟 | 低 | S2 stop condition 已覆盖：FMP 失败不阻塞 slot builder。但未指定 FMP 请求超时时 CLI 的体感延迟；建议默认 timeout ≤ 5s |
| `soul.md` 中 `{{base_user}}` 移除后 persona 行可能过短 | 低 | 设计决策，不属于代码缺陷 |

## Completion Report

- **Artifact path**: `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-plan-review-ds.md`
- **Conclusion**: **pass-with-findings**
- **Blocking findings count**: 0
- **Non-blocking findings count**: 6 (DS-F01 高, DS-F02 中, DS-F03 中, DS-F04 中, DS-F05 低, DS-F06 低)
- **Residual risks**: 3 (条件块嵌套、FMP 超时延迟、soul.md persona)

Plan 的根因分析准确，包落点符合分层约束，3 个 slices 语义闭环清晰，checkpoint commit 2a61fbfd 未被要求回滚，upload 暴露面风险、FMP API key 注入、空 slot 行清理、base_user 删除和 current_time 不机械添加均得到正确处理。Findings 集中于规格精度不足（空行清理规则的交互、current_time 格式、soul.md 遗漏、FMP env var 名称），均可通过小幅补充解决，不构成结构性阻塞。
