# Host Public Conversation Memory Smoke 计划

## 0. Gate 与角色

- 当前 gate：plan。
- 角色：planning worker only。
- Work unit：新增 public-API-only conversation memory finance smoke。
- Repository：`/Users/leo/workspace/dayu-agent-r`。
- Branch：`feat/phase-12-5-conversation-memory-optimize`。
- 本 artifact 只给 implementation worker 使用；不实施、不提交、不推送、不开 PR。

## 1. 可行性与动机判断

动机成立。`/Users/leo/workspace/dayu-agent/docs/conversation_memory_test.md` 的原始测试目标覆盖真实交互、真实财报工具、compaction 日志和 durable memory 表内查；其中“查表验证 pinned_state / confirmed_facts”与本 work unit 的 public Host API 约束冲突，不能照搬。可行的最小子集是借用测试组 D 的核心意图：先由工具确认一个财务事实，再制造上下文压力触发 compaction，后续在禁用工具的轮次中要求模型复述已确认事实，验证多轮 continuity 和反漂移。

推荐场景子集：

- 主路径采用测试组 D“净息差 confirmed fact 跨轮一致性”。
- 借用测试组 B 的“最近轮追问连续性”，但只作为辅助轮次，不扩大到 IFRS 口径切换。
- 不采用测试组 A 的双公司切换、测试组 C 的 8000-15000 字长披露、测试组 E 的 20+ 轮稳定性；这些要么依赖真实财报语料，要么会把手工 smoke 变成长时稳定性测试，不适合作为 public API smoke 的首个入口。

关键边界：

- 只证明 public Host 多轮路径能把 mock tool accepted facts 带到后续 run input / memory / compact 可见上下文里。
- 不证明所有 Conversation Memory 生产语义，不直接读取 memory snapshot、durable store、EventLog 或内部 compaction material。

## 2. 直接证据

- `/Users/leo/workspace/dayu-agent/docs/conversation_memory_test.md`：测试组 D 要求第 12/13 轮回到净息差讨论时数值与第 2 轮一致，且第 8-10 轮观察 compaction。
- `utils/smoke_host_public_multiturn.py`：已有手工 smoke 的正确 public handle 调用形态是 `open_host(options)`、`ensure_session`、`submit_followup`、`watch_session_events`、`get_session` / `get_run`，并通过 mock `manual-smoke` tool 与 pressure padding 观察 compact。
- `dayu/config/prompts/manifests/smoke_host_public_multiturn.json` 和 `dayu/config/prompts/scenes/smoke_host_public_multiturn.md`：当前 smoke scene 使用 `manual-smoke` tag、允许工具调用、通过 scene prompt 收口回答行为。
- `dayu/host/api.py`：`Host` public protocol 暴露 `ensure_session`、`get_session`、`get_run`、`submit_followup`、`watch_session_events`；`HostEvent.final_answer` 是 public terminal answer 观测点；`SessionSnapshot` / `RunSnapshot` 只提供 public read model，不暴露 memory 内部。

## 3. 目标文件与命名

新增：

- `utils/smoke_host_public_conversation_memory.py`
  - 新手工 smoke 脚本。
  - 默认 scene id：`smoke_host_public_conversation_memory`。
  - 默认每次 fresh slot，显式 `--reuse-session` 时复用稳定 slot。
- `dayu/config/prompts/manifests/smoke_host_public_conversation_memory.json`
  - scene manifest，结构参考 `smoke_host_public_multiturn.json`。
  - `capability_tags` 使用 `smoke_host_public_conversation_memory`。
  - `tool_selection` 选择 `manual-smoke` tag，`allow_empty=false`。
- `dayu/config/prompts/scenes/smoke_host_public_conversation_memory.md`
  - scene prompt，要求模型优先回答当前财务问题、禁止披露 smoke 运行细节，并在被要求时输出固定核对行。

更新：

- `README.md`
  - 在“手工 smoke”章节新增 Host public conversation memory smoke 入口说明。

不建议本 work unit 修改：

- `dayu/host/api.py`：public API 足够，不需要新增 Host 方法。
- `dayu/fins/**`：本 smoke 必须使用 mock tool，不接真实 Fins。
- `tests/**`：utils 手工 smoke 不要求单元覆盖；只保留现有测试，并运行相关验证命令。

## 4. Public API 与装配决策

实现可以复用 `utils/smoke_host_public_multiturn.py` 的 assembly 思路，但运行期 Host 调用必须只包含：

- `open_host(assembly.options)`。
- `host.ensure_session(...)`。
- `host.submit_followup(...)`。
- `host.watch_session_events(session.session_id)`。
- `host.get_session(session.session_id)`。
- `host.get_run(run_id)` 仅用于 terminal failure 摘要。

禁止：

- 直接 import 或调用 durable store、scheduler、command handle、EventLog reader、memory projection reader、conversation transcript 表、compact material builder。
- 通过 SQLite 查询 `.dayu/host/dayu_host.db` 或任何 memory / transcript 表。
- 读取内部 memory snapshot 或 private compaction diagnostic object。

Service-like assembly helper 可继续用于 Host 打开前的配置组合：`ConfigLoader`、`resolve_runtime_locations`、`discover_service_tools`、`prepare_scene`、`compose_open_host_options`、`compose_submit_followup_request`。这些是调用 Host public opener 前的 typed composition，不是 Host private command path。

## 5. Mock Tool 设计

工具 provider：

- provider id：`host-public-conversation-memory-smoke`。
- provider spec id：`host-public-conversation-memory-smoke`。
- provider import display path：`__main__:discover_smoke_tools`。
- tag：`manual-smoke`。

Python 工具类：

- 类名：`MockFinanceFactTool`。
- 实现模式参考 `utils/smoke_host_public_multiturn.py` 里的 `SmokeFactTool`：callable 实例持有 `call_count`、`last_marker` 等观测状态，并实现 typed `__call__`。
- 工具参数只用于 schema / tool-call contract 校验与 pressure 行为选择；除 `include_pressure` 外，`company`、`period`、`topic`、`metric` 不参与动态业务计算，返回固定 deterministic JSON，避免把 smoke 变成业务规则测试。

工具 1：`get_mock_finance_facts`

- 用途：返回固定的招商银行 2024H1 息差讨论事实。
- schema：
  - `company`: string，必填。
  - `period`: string，必填。
  - `topic`: string，必填。
  - `metric`: string，必填。
  - `include_pressure`: boolean，必填。
  - `additionalProperties=false`。
- 调用约束：第 1 轮必须允许且要求调用；后续轮次传 `tool_names=frozenset()` 禁用业务工具。

确定性返回值：

```json
{
  "marker": "DAYU_FINANCE_MEMORY_CMB_NIM_2024H1_V1",
  "company": "招商银行",
  "ticker": "600036.SH",
  "period": "2024H1",
  "topic": "息差",
  "facts": {
    "net_interest_margin": "1.88%",
    "net_interest_margin_yoy_change": "-0.14pct",
    "interest_earning_asset_yield": "3.45%",
    "interest_bearing_liability_cost": "1.74%",
    "retail_loan_share": "52.6%",
    "time_deposit_share": "37.2%",
    "npl_ratio": "0.94%"
  },
  "assertion_line": "DAYU_FINANCE_MEMORY_ASSERT marker=DAYU_FINANCE_MEMORY_CMB_NIM_2024H1_V1 company=招商银行 period=2024H1 net_interest_margin=1.88% yoy=-0.14pct",
  "note": "These are deterministic mock facts for Host public conversation memory smoke, not real Fins data.",
  "pressure_blob": "<optional deterministic repeated text>"
}
```

pressure payload：

- 保留 `utils/smoke_host_public_multiturn.py` 的自适应思路，按 `OpenHostOptions.context_budget_policy` 计算 prompt pressure，使估算总量落在 soft threshold 以上、hard threshold 以下。
- tool result 在 `include_pressure=true` 时包含 `pressure_blob`，内容为确定性重复文本，目标长度为 `_SMOKE_TOOL_PRESSURE_CHARS = 120_000`。
- `include_pressure=false` 时仍返回 `pressure_blob` 字段，但值固定为空字符串 `""`；这样返回 shape 稳定，同时不会制造工具侧 pressure。
- tool pressure 与 Round 2 prompt pressure 是 additive pressure，必须共同按同一个 `OpenHostOptions.context_budget_policy` 校准；两者与基础上下文的估算总量应落在 soft threshold 以上、hard threshold 以下，计算方式参考既有 `_compact_pressure_padding()` / reserve pattern，禁止把两段 pressure 分别独立打满。
- 常量必须集中定义，禁止散落魔法字符串/数字；schema 内字段名字面量例外。

### 模块级 `Final` 常量 inventory

Implementation worker 应在 `utils/smoke_host_public_conversation_memory.py` 顶部集中定义以下模块级 `Final` 常量，命名和值建议如下；如既有 smoke 中已有更贴近本仓库命名风格的同义常量，可保持语义和值一致后微调名称：

- `_DEFAULT_SCENE_ID: Final[str] = "smoke_host_public_conversation_memory"`。
- `_DEFAULT_SLOT_KEY_PREFIX: Final[str] = "manual-smoke-conversation-memory"`；默认 fresh slot 在此前缀后附加唯一后缀，`--reuse-session` 使用稳定 slot key。
- `_TOOL_NAME: Final[str] = "get_mock_finance_facts"`。
- `_TOOL_TAG: Final[str] = "manual-smoke"`。
- `_PROVIDER_ID: Final[str] = "host-public-conversation-memory-smoke"`。
- `_PROVIDER_SPEC_ID: Final[str] = "host-public-conversation-memory-smoke"`。
- `_PROVIDER_IMPORT_DISPLAY_PATH: Final[str] = "__main__:discover_smoke_tools"`。
- `_SMOKE_MARKER: Final[str] = "DAYU_FINANCE_MEMORY_CMB_NIM_2024H1_V1"`。
- `_ASSERTION_PREFIX: Final[str] = "DAYU_FINANCE_MEMORY_ASSERT"`。
- `_CLIENT_REQUEST_PREFIX: Final[str] = "manual-smoke-conversation-memory"`。
- `_DEFAULT_SUBJECT: Final[str] = "招商银行"`。
- `_DEFAULT_USER_ID: Final[str] = "manual-smoke-user"`。
- `_FINAL_PREVIEW_CHARS: Final[int] = 600`。
- `_SMOKE_TOOL_PRESSURE_CHARS: Final[int] = 120_000`。
- `_PRESSURE_CHUNK: Final[str] = "招商银行2024H1息差记忆压力文本"`。
- `_COMPACT_PRESSURE_RESERVE_TOKENS: Final[int]`：沿用既有 `smoke_host_public_multiturn` 的 reserve 值；若该脚本已定义同名或等价常量，以既有值为准。
- `_TERMINAL_TIMEOUT_SECONDS: Final[float]`：沿用既有 smoke 的 terminal timeout 值；若既有脚本已有等价常量，以既有值为准。
- stdout 前缀常量按用途集中定义，例如 `_STDOUT_PREFIX_ROUND_START = "SMOKE ROUND_START"`、`_STDOUT_PREFIX_ROUND_DONE = "SMOKE ROUND_DONE"`、`_STDOUT_PREFIX_FINAL_PREVIEW = "SMOKE FINAL_PREVIEW"`、`_STDOUT_PREFIX_ASSERT_MEMORY_VALUE = "SMOKE ASSERT_MEMORY_VALUE"`、`_STDOUT_PREFIX_COMPACT_ARTIFACT_ROOT = "SMOKE COMPACT_ARTIFACT_ROOT"`。

## 6. 轮次设计、断言与日志标记

固定 stdout 前缀：

- `SMOKE START Host public conversation memory finance smoke`
- `SMOKE CONTRACT open_host -> ensure_session -> submit_followup -> watch -> get_session`
- `SMOKE MEMORY_MARKER DAYU_FINANCE_MEMORY_CMB_NIM_2024H1_V1`
- `SMOKE ROUND_START label=...`
- `SMOKE ROUND_DONE label=...`
- `SMOKE FINAL_PREVIEW label=...`
- `SMOKE ASSERT_MEMORY_VALUE label=... status=pass|fail ...`
- `SMOKE COMPACT_ARTIFACT_ROOT ...`
- `SMOKE COMPACT_ARTIFACT_FILE_COUNT ...`
- `SMOKE PASS public Host conversation memory finance continuity`

### Round 1：工具确认事实

label：`round1-confirm-finance-fact`

tool_names：`assembly.scene_inputs.tool_selection.tool_names`

prompt：

```text
请调用 get_mock_finance_facts 查询招商银行 2024H1 息差事实，参数 company=招商银行、period=2024H1、topic=息差、metric=net_interest_margin、include_pressure=true。
工具返回后，请用一小段话回答，并原样包含工具返回的核对行 DAYU_FINANCE_MEMORY_ASSERT。
```

硬断言：

- terminal event kind 必须是 `SUCCEEDED`。
- final answer 非空。
- `MockFinanceFactTool.call_count == 1`。
- `MockFinanceFactTool.last_marker == "DAYU_FINANCE_MEMORY_CMB_NIM_2024H1_V1"`。
- final answer 如果包含 `DAYU_FINANCE_MEMORY_ASSERT`，则必须同时包含 `1.88%` 与 `-0.14pct`；如果不包含，不立即失败，但打印 `SMOKE OBSERVE round1 assertion line omitted by model`。
- `MockFinanceFactTool` 实例必须从 `assembly.effective_tool_bundle` 中按 type/name 恢复，模式参考既有 `_find_smoke_tool`；禁止用模块级全局计数器替代 effective ToolBundle 中真实注册的 callable 实例。

日志标记：

- `SMOKE TOOL_CALL_COUNT_AFTER_ROUND1 1`
- `SMOKE EXPECTED_FACT marker=... net_interest_margin=1.88% yoy=-0.14pct`

### Round 2：分组复述并制造 compact 压力

label：`round2-group-and-pressure`

tool_names：`frozenset()`

prompt：

```text
继续同一个会话，不要调用工具。请把刚才招商银行 2024H1 的息差相关事实按“资产 / 负债 / 息差”三组重排。
回答末尾请原样输出一行 DAYU_FINANCE_MEMORY_ASSERT，字段必须仍为 marker=DAYU_FINANCE_MEMORY_CMB_NIM_2024H1_V1、company=招商银行、period=2024H1、net_interest_margin=1.88%、yoy=-0.14pct。
下面是为了触发 Host proactive compact 的人工长上下文：<pressure padding>
```

硬断言：

- terminal event kind 必须是 `SUCCEEDED`。
- final answer 非空。
- 工具调用次数仍为 1。

可选硬断言：

- 如果 final answer 包含 `DAYU_FINANCE_MEMORY_ASSERT`，解析后必须匹配 marker、company、period、`1.88%`、`-0.14pct`。
- 不建议默认因为 Round 2 缺少核对行而失败，因为 pressure padding 可能影响模型格式遵循；但必须打印 `SMOKE ASSERT_MEMORY_VALUE label=round2-group-and-pressure status=soft-missing`。

后验日志：

- 打印 compact pressure 计划：context window、soft/hard threshold、tool pressure chars、prompt pressure chars、estimated tokens。
- 打印 compact artifact root 与文件数量；不直接读取 artifact 内容。

### Round 3：切换问题，制造干扰

label：`round3-topic-shift-no-tool`

tool_names：`frozenset()`

prompt：

```text
我换个问题：招商银行 2024H1 的不良率是多少？不要调用工具，只基于你当前可见上下文回答。
如果不确定，请明确说不确定；如果能看到已确认事实，请给出不良率。
```

硬断言：

- terminal event kind 必须是 `SUCCEEDED`。
- final answer 非空。
- 工具调用次数仍为 1。

日志标记：

- final answer preview 用于人工确认模型是否还能看到 `npl_ratio=0.94%`。
- 该轮是 topic-shift / no-tool pressure only，不承载 pass/fail 权重；即使模型回答“不确定”也不影响 smoke 结论，因为 `npl_ratio` 不在最终核对行内，不要求一定被 compaction 后上下文保留。

### Round 4：回到息差并核对一致性

label：`round4-confirmed-fact-consistency`

tool_names：`frozenset()`

prompt：

```text
回到刚才的息差讨论。请只根据这个会话已经确认过的事实回答：
招商银行 2024H1 净息差的具体数值是多少？同比变化是多少？这次确认的数是否与前面工具确认过的数据一致？
回答最后必须单独输出一行：
DAYU_FINANCE_MEMORY_ASSERT marker=DAYU_FINANCE_MEMORY_CMB_NIM_2024H1_V1 company=招商银行 period=2024H1 net_interest_margin=1.88% yoy=-0.14pct
```

硬断言：

- terminal event kind 必须是 `SUCCEEDED`。
- final answer 非空。
- 工具调用次数仍为 1，证明 Round 2-4 没有再次调用业务工具。
- final answer 必须包含 marker `DAYU_FINANCE_MEMORY_CMB_NIM_2024H1_V1`。
- final answer 归一化后必须包含 `1.88%` 与 `-0.14pct`。归一化仅允许去空白、统一全角百分号、统一大小写；不要做语义猜测。
- 通过时打印 `SMOKE ASSERT_MEMORY_VALUE label=round4-confirmed-fact-consistency status=pass marker=DAYU_FINANCE_MEMORY_CMB_NIM_2024H1_V1 net_interest_margin=1.88% yoy=-0.14pct`。

手工分析项：

- 是否出现 compaction artifact 或日志中 compact 相关行。
- final answer 是否明确表达“与前面一致”，这类自然语言判断不做默认硬断言。

## 7. 哪些必须硬断言，哪些只做日志

必须硬断言：

- Host public handle 三段式闭环成功：session 创建、每轮 terminal succeeded、final answer 非空。
- 第 1 轮工具必须被调用一次。
- 第 2-4 轮工具调用次数不能增加。
- Round 4 最终回答必须包含 marker、`1.88%`、`-0.14pct`。
- `get_session` 返回 session status 非关闭/异常。

只做日志或 soft assertion：

- `SessionSnapshot.active_run_id` 与 `queued_run_ids` 只做 soft observation：每轮结束后打印 public snapshot 中的 active / queued 状态；若仍显示 active 或 queued，不直接失败，因为后台 compact / lane scheduling 可能存在短暂状态。
- Round 2 是否精确输出核对行。pressure prompt 可能降低格式遵循，缺失时不应直接否定 memory。
- compaction 是否实际发生。可以打印 artifact root/count 和 pressure 计划，但 proactive/background compact 不应通过内部表读强行确认。
- 模型是否“基于 episode summary 而非 raw transcript”回答。public API 下无法证明输入来源，只能通过“禁用工具 + 后轮值不漂移 + compact artifact/log markers”形成后验证据。
- 自然语言里的“一致/不一致”判断，优先人工看 final preview。

## 8. Implementation Slice

建议一个 slice 完成，避免把手工 smoke 拆成多个中间不可运行状态。

Slice：`S1 public finance conversation memory smoke`

允许修改：

- 新增 `utils/smoke_host_public_conversation_memory.py`。
- 新增 `dayu/config/prompts/manifests/smoke_host_public_conversation_memory.json`。
- 新增 `dayu/config/prompts/scenes/smoke_host_public_conversation_memory.md`。
- 更新 `README.md` 的手工 smoke 小节。

实现要求：

- 脚本模块、类、函数必须有中文 docstring，包含参数、返回值、异常。
- 严格类型：禁止 `Any`、`object`、无类型参数、无类型返回值。
- 常量化所有 smoke marker、工具名、scene id、slot key、stdout marker、pressure 参数。
- mock tool callable 使用 typed `ToolCallRequest` 与 `BatchToolExecutionContext`，返回 `ToolCompletedOutcome` / `ToolResultSuccess`。
- mock tool 实例通过 effective ToolBundle 恢复并断言调用状态，不能依赖模块级全局变量、global counter 或外部副本。
- 不使用 lazy import；不使用 `hasattr` / `getattr` 逃避类型边界。
- 不读取 durable DB、EventLog、memory table、compact payload 内容。
- terminal failure 摘要可以参考既有 smoke 的脱敏策略，禁止输出 API key、headers、完整 prompt、完整 pressure payload。
- 若 implementation worker 发现复制 `utils/smoke_host_public_multiturn.py` 的 assembly 代码过多，应优先保持本 slice 可读且稳定；不要在本 work unit 重构既有 smoke，除非 controller 另行批准扩 scope。

完成信号：

- 新脚本可运行到 `SMOKE PASS public Host conversation memory finance continuity`。
- Round 4 hard memory assertion 通过。
- README 只增加当前 smoke 的稳定使用说明，不写过程状态或未来计划。

## 9. 验证命令与预期输出

受影响 focused tests：

```bash
source .venv/bin/activate
pytest tests/runtime/test_scene_prepare.py tests/runtime/test_smoke_host_public_multiturn_assembly.py tests/service/test_host_assembly.py -q
```

预期：

- pytest 退出码 0。
- 既有 `smoke_host_public_multiturn` assembly 测试不受新 scene / script 影响。

类型检查：

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

预期：

- `0 errors, 0 warnings, 0 informations`，或至少无新增/扩散报错；若当前 branch 已有 pyright 报错，implementation report 必须列出基线与本变更是否新增。

手工 smoke：

```bash
source .venv/bin/activate
python utils/smoke_host_public_conversation_memory.py --log-level VERBOSE
```

关键预期 stdout：

```text
SMOKE START Host public conversation memory finance smoke
SMOKE CONTRACT open_host -> ensure_session -> submit_followup -> watch -> get_session
SMOKE MEMORY_MARKER DAYU_FINANCE_MEMORY_CMB_NIM_2024H1_V1
SMOKE TOOL_CALL_COUNT_AFTER_ROUND1 1
SMOKE ASSERT_MEMORY_VALUE label=round4-confirmed-fact-consistency status=pass marker=DAYU_FINANCE_MEMORY_CMB_NIM_2024H1_V1 net_interest_margin=1.88% yoy=-0.14pct
SMOKE TOOL_CALL_COUNT 1
SMOKE PASS public Host conversation memory finance continuity
```

可选人工观察：

```bash
source .venv/bin/activate
python utils/smoke_host_public_conversation_memory.py --log-level DEBUG --keep-workspace
```

观察：

- stdout 中 compact pressure 摘要位于 soft/hard threshold 之间。
- `SMOKE COMPACT_ARTIFACT_FILE_COUNT` 大于 0 时，说明本次运行产生了 compact artifact；等于 0 不必然失败，需要结合日志判断是否 profile 未启用 compactor、模型窗口/阈值未触发或后台 compact 尚未完成。

## 10. README / Docs 决策

需要更新 `README.md`：

- 根 README 已有“手工 smoke”章节且列出 `utils/smoke_host_public_multiturn.py`；新增脚本属于项目级手工验证入口，应该在相邻位置补充。
- 只写：脚本用途、命令、mock tool、不使用真实 Fins、硬断言与日志观察项。
- 不写内部 memory 表、EventLog 查询步骤。

不需要更新 `dayu/config/README.md`：

- 新增 scene manifest / prompt 使用既有 schema，不改变配置覆盖关系、字段语义或 prompts 目录职责。

不需要更新 `tests/README.md`：

- 本 work unit 不新增/迁移单元测试分类；utils 手工 smoke 只通过 focused tests、pyright 和手工运行验证。

不需要新增其它 docs：

- 源文档 `/Users/leo/workspace/dayu-agent/docs/conversation_memory_test.md` 属于另一个 repo，只作为测试意图来源，不同步进本 repo。

## 11. 风险、非目标与开放问题

风险：

- LLM 可能不遵循“输出固定核对行”的格式。缓解：Round 4 只断言 marker 和两个确定性数值，Round 2 只做 soft assertion。
- proactive/background compaction 的发生时间不完全由脚本控制。缓解：compact 只作为日志观察项，核心 pass/fail 放在 public multi-turn no-tool continuity。
- 如果默认模型缺少 API key、endpoint 不可用、quota/rate-limit，手工 smoke 会失败。implementation report 需要区分环境失败和代码失败。
- 复制既有 smoke assembly 逻辑会带来维护成本。当前 work unit 范围优先新增可运行 smoke；若后续出现第三个 Host public smoke，再由单独 refactor 抽取 shared utils support 更合适。

非目标：

- 不证明真实 Fins 工具、真实财报仓储或真实财报数值正确性。
- 不证明 pinned_state 单调演进的全部语义。
- 不证明 compactor 一定把事实写入 episode summary / evidence-backed facts；public API 下不读取内部 memory。
- 不提供 CI 稳定自动化测试；这是手工 real-runner smoke。
- 不新增 Host public API。

Blocking Questions For Controller：

- 无。

## 12. Plan Fix Note

已处理 review artifacts：

- `docs/reviews/gateflow-plan-review-conversation-memory-smoke-ds-20260526.md`：接受 advisory findings 1-7，并作为计划澄清落入 §5、§6、§7、§8。
- `docs/reviews/gateflow-plan-review-conversation-memory-smoke-mimo-20260526.md`：吸收 mock tool 参数 deterministic 处理说明；Round 4 断言仍保持 marker + `1.88%` + `-0.14pct` 的 smoke 级硬断言，不额外扩大为 assertion-line 必须存在。

修复状态：

- `MockFinanceFactTool` 类名、`SmokeFactTool` callable 模式、effective ToolBundle 实例恢复路径已明确。
- `include_pressure` 的 `pressure_blob` 条件行为已固定为 true 时填充、false 时空字符串。
- `SessionSnapshot.active_run_id` / `queued_run_ids` 已从硬断言改为 soft observation。
- Round 3 已明确为 topic-shift / no-tool pressure only，不承载 pass/fail 权重。
- 模块级 `Final` 常量 inventory 已补齐，包含 scene id、slot key、工具名、tag、provider ids、marker、client request prefix、默认 subject/user、preview chars、pressure 参数、timeout 与 stdout 前缀。
- tool pressure 与 Round 2 prompt pressure 已明确为 additive，并需共同按同一个 `context_budget_policy` 校准。

Plan status：implementation-ready。
