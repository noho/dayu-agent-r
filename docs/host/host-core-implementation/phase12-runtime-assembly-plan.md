# Phase 12 Runtime Assembly 实施计划

本文档是 Phase 12 plan gate 的 implementation-ready handoff。架构真源只取自 `docs/host/design.md` 与 `docs/host/implementation-control.md`；不引用、不依赖 discussion draft。

## 1. Phase 目标与非目标

### 目标

- 在 Host 外部落地 `ToolsDiscovery`、`ScenePrepare` 与 `ConfigLoader` 三个 runtime assembly 组件。
- 让外部装配方在调用 `open_host(options)` 与 `SubmitFollowupRequest` 前，能用强类型结果完成业务 `ToolBundle`、scene inputs 与 execution config 装配。
- 保持 Host 不 import 具体业务工具、不扫描业务包、不读取应用配置文件、不拼接财报场景 prompt。
- 保持 `dayu.runtime` 层中立：只能依赖标准库与 `dayu.contracts`；不得 import `dayu.host`、`dayu.engine`、`dayu.service`、`dayu.ui`、`dayu.fins` 或具体业务工具包。
- 删除旧 `dayu/config/llm_models.json` 与 `dayu/config/run.json`，按新 schema 起库，不提供兼容读取路径。
- 迁移旧项目 `dayu-agent` 的 scene manifest 与这些 manifest 直接引用的 prompt fragment assets 到当前项目配置资产目录，并用新 `ScenePrepare` parser / assembly 测试验证。

### 非目标

- 不修改 Host durable state machine、Host command path、ToolRuntime accept barrier 或 Engine execution path。
- 不新增、不删除、不重命名、不重塑 `dayu.host` public exports、`open_host(options)`、`OpenHostOptions` 现有字段、Host handle 方法或 public request / response dataclass 字段。
- 不实现 Audit / Tool Trace / Outbox projection；该能力归 Phase 13。
- 不实现真实 Service workflow、Skill workflow、多 Run step graph、checkpoint / resume、replay / retry policy 或 structured parser。
- 不把财报 prompt 文案、业务工具实现、Fins storage 访问逻辑放入 `dayu.runtime`。
- 不让 per-run request 携带 raw `ToolBundle`、`ToolDefinition`、callable binding、provider adapter、profile lookup、patch dict 或无结构 extra payload。

## 2. 契约清单

- `ToolDefinition`：位于 `dayu.contracts.tool_declaration`，承载工具名、LLM-facing `ToolSchema`、单工具 `ToolCallable`、truncate spec、display metadata 与 tags；`name` 必须与 `schema.function.name` 同源。
- `ToolBundle`：位于 `dayu.contracts.tool_declaration`，只包含 `ToolDefinition` 元组并校验工具名唯一；Host construction 接收的是已装配业务 bundle，不接收 discovery adapter。
- `@tool`：位于 `dayu.contracts.tool_declaration`，在工具函数现场同源声明 schema / truncate / display / tags，并返回 `ToolDefinition`；`ToolsDiscovery` provider 输出应使用该契约或直接返回等价 `ToolDefinition`。
- `HostToolingOptions`：当前位于 `dayu.host.tooling`，是 `open_host(options)` construction-time 工具输入边界，字段包括 `business_tool_bundle`、`source_refs`、`framework_tool_policy` 与可选 `wait_adapter_registry`；P12 不修改其字段。
- `ToolBundleSourceKind` / `ToolBundleSourceRef`：canonical owner 必须迁移到 `dayu.contracts`，优先新增聚焦模块 `dayu/contracts/tool_source.py`，也可使用职责等价的 contracts 模块。`dayu.host.tooling` 从 `dayu.contracts` import 这两个 canonical types；现有 `dayu.host` public exports 可以继续导出同一 canonical type，以保持 Host 既有 public surface。这不是兼容性 wrapper / facade，也不是旧语义转发，而是在 ownership 下移后保留 Host 对外公开的同一契约入口。P12 不新增、不删除、不重塑 `HostToolingOptions.source_refs` 字段或 Host 行为。
- `SubmitFollowupRequest` per-run override 字段：当前允许 runtime assembly 映射进入的字段只有 `system_prompt`、`tool_names`、`runner_spec`、`runner_options`、`agent_policy`。`user_prompt` 是调用方本次输入；`behavior` 与 `target_run_id` 是 UI / Service 请求控制，不来自 scene / config。
- `RunnerSpec`：完整 typed Runner 规约，包含 provider、model、endpoint、`api_key_ref`、headers、tool calling / streaming / stream usage capability、default timeout、max retries、provider request extension、SSE idle timeout / heartbeat。ConfigLoader 输出不能是 patch。
- `RunnerCallOptions`：完整 typed Runner 调用参数，包含 temperature、max tokens、top-p 与 stream。temperature profile 从 scene / execution profile 映射到该完整对象。
- `AgentPolicy`：完整 typed Agent 策略，包含 max iterations、continuation attempts、tool execution timeout、fallback mode / prompt、continuation prompt 与连续失败工具批次阈值。scene hints 只能由 Service 映射成完整对象。
- `OpenHostOptions` construction-time boundary：durable store / artifact roots、SQLite / lane 参数、worker factory、ordinary baseline、`HostToolingOptions`、context budget、compactor baseline、memory projection、memory catch-up batch size 与 truncation manager 开关只能在 Host 外部装配时确定；单个 Run 不得改写这些 opener inputs。

## 3. Slice 计划

### Slice 1: ToolsDiscovery provider protocol and ToolBundle aggregation

- 写入范围：`dayu/runtime/tools_discovery.py`、`dayu/runtime/__init__.py`、`tests/runtime/test_tools_discovery.py`、`dayu/contracts/tool_source.py` 或等价 contracts source ref 模块；必要时新增 runtime provider report 契约文件。
- 实施任务：
  - 将 `ToolBundleSourceKind` / `ToolBundleSourceRef` 的 canonical 定义迁移到 `dayu.contracts`，并让 `dayu.host.tooling` import canonical types；`dayu.host` 可继续公开导出同一 canonical type 以保留 Host public surface。
  - 定义 provider callable 协议：显式接收无 Host / Service 上下文的 provider spec，返回 provider identity、version ref / source refs 与 `ToolDefinition` 集合。
  - 支持显式 Python import path 与 package entry point，两者都必须解析成 provider callable；不递归扫描 package。
  - 校验 provider identity 非空且不重复，provider enabled / disabled 生效。
  - 聚合多个 provider 输出为 `ToolBundle`，重复工具名报配置错误。
  - provider 返回空集合默认报错，只有 provider spec 显式 `allow_empty=true` 时允许。
- 测试：
  - fake provider callable 聚合成功。
  - import path 与 entry point 解析到 callable。
  - duplicate provider identity、duplicate tool name、disabled provider、empty provider without `allow_empty`、empty provider with `allow_empty`。
- README 触发：
  - 修改 `dayu/runtime` 公共能力，检查并按职责更新 `dayu/README.md`。
  - 若新增 `dayu/contracts` 公共契约，检查 `dayu/README.md` 术语 / 稳定边界是否需同步。
- 验收标准：
  - 外部装配方可以不 import Host 得到业务 `ToolBundle` 与 provider report。
  - `ToolsDiscovery` 不 import Host / Engine / Service / UI / Fins / 具体业务工具包。
- 停止条件：
  - 如果 provider protocol 需要 Host lifecycle、EventLog、ToolRuntime accept barrier 或 Service workflow 信息，停止并回设计讨论。
  - 如果实现需要新增、删除或重塑 Host public fields、Host public exports 或 Host 行为，停止并回设计讨论；source ref canonical ownership 下移到 `dayu.contracts` 本身不是停止条件。

### Slice 2: Source refs / digest and reserved framework tool validation

- 写入范围：`dayu/runtime/tools_discovery.py`、公共 source ref 契约文件、`tests/runtime/test_tools_discovery_digest.py`、`tests/runtime/test_tools_discovery_import_boundary.py`。
- 实施任务：
  - 生成稳定 source refs：`EXPLICIT_PROVIDER`、`CONFIG_BINDING`、`PACKAGE_ENTRYPOINT`。
  - 计算 `content_digest`，覆盖 tool name、LLM-facing schema、truncate spec、tags 与 display metadata；不得 hash callable 对象。
  - 对业务工具名执行 framework reserved name 校验，至少拒绝 `fetch_more`。
  - 明确 digest / source refs 只用于解释、诊断、trace、audit 或后续 snapshot refs，不是权限、lease、fencing、Host truth 或 owner。
- 测试：
  - 同一 provider 声明顺序稳定时 digest 稳定。
  - callable 引用变化但声明内容不变时 digest 不变。
  - schema / truncate / tags / display 任一声明变化时 digest 变化。
  - 业务工具名为 `fetch_more` 时拒绝。
- README 触发：
  - 如新增 public source ref 契约，检查 `dayu/README.md` 的 Runtime / Host 边界说明。
- 验收标准：
  - `ToolsDiscovery` 输出的 source refs / digest 可解释 ToolBundle 来源，并能由外部装配方映射到 `HostToolingOptions.source_refs`。
- 停止条件：
  - 如果需要 Host 保存 provider callable、discovery adapter 或配置文件路径本体，停止。
  - 如果需要让 `ToolRuntime` 改变 framework tool 注入 / accept barrier，停止。

### Slice 3: ConfigLoader typed config loading / validation and legacy config removal

- 写入范围：`dayu/runtime/config_loader.py`、`dayu/config/models.json`、`dayu/config/execution_profiles.json`、`dayu/config/host_runtime.json`、`dayu/config/tool_discovery.json`、删除 `dayu/config/llm_models.json` 与 `dayu/config/run.json`、`tests/runtime/test_config_loader.py`、必要的配置 fixture。
- 实施任务：
  - 定义四类 typed config view：
    - `models.json`：`model_id`、runner kind、provider、model、endpoint、`api_key_ref`、headers、tool calling / streaming / stream usage capability、default timeout、max retries、SSE idle timeout / heartbeat、provider request extension、context window tokens。
    - `execution_profiles.json`：默认 profile、ordinary model id / runner options / agent policy、compactor model id / runner options / artifact root、context budget、memory projection、truncation 配置，以及 scene hints 到 typed execution inputs 的映射边界；具体 schema sketch 与 typed view 见 §4。
    - `host_runtime.json`：store / artifact roots、SQLite、lane、worker factory kind、dispatch poll interval、memory projection catch-up batch size、truncation manager 开关、prompt / scene asset roots。
    - `tool_discovery.json`：provider id、import path 或 entry point、source kind、source id、enabled、`allow_empty`。
  - 实现包内默认配置 + workspace 覆盖配置按文件类型分别加载。
  - overlay 规则固定为顶层 map 按稳定 id 合并；同 id workspace 记录整条替换；不做隐式 deep merge。
  - `extends` 只允许单继承；解析后必须得到完整 typed record；循环、多个父项、缺字段、非法字段类型均报配置错误。
  - ConfigLoader 不解析环境变量、不替换 secret、不脱敏，只原样读取 schema 表达的配置值。
  - 删除旧配置文件，不提供旧路径兼容读取、兼容测试、compat wrapper 或 re-export。
- 测试：
  - 四个新配置文件可加载并产出 typed config view。
  - workspace 整条替换覆盖包内默认记录。
  - 单继承 `extends` 成功，循环 / 多继承 / partial deep merge / 缺字段失败。
  - `api_key_ref`、headers、provider request extension 等值按 schema 原样保留。
  - 旧 `llm_models.json` / `run.json` 不再被读取；测试不为旧文件提供兼容路径。
- README 触发：
  - 修改 `dayu/config/`，必须检查并按职责更新 `dayu/config/README.md`。
  - 若项目级配置入口变化影响用户跑通方式，检查根目录 `README.md`。
- 验收标准：
  - Service / composition root 可以从 ConfigLoader 输出映射到完整 `RunnerSpec`、`RunnerCallOptions`、`AgentPolicy` 与 `OpenHostOptions` construction-time inputs。
  - 映射失败在调用 Host 前失败，不进入 Host 状态机。
- 停止条件：
  - 如果需要 ConfigLoader 构造 Host、创建 provider client、读取 Fins storage、解释 scene manifest 或保护 / 解析 secret，停止。
  - 如果发现需要新增 `SubmitFollowupRequest` override 字段或 `OpenHostOptions` 字段，停止。

### Slice 4: ScenePrepare typed manifest assembly helper and scene input output

- 写入范围：`dayu/runtime/scene_prepare.py`、`dayu/config/prompts/` 新 schema 示例资产、`tests/runtime/test_scene_prepare.py`、`tests/runtime/test_scene_tool_selection.py`。
- 实施任务：
  - 定义 scene manifest 第一版 schema：`schema_version`、`scene`、`version`、`description`、`capability_tags`、`extends`、`model`、`runtime`、`conversation`、`tool_selection`、`defaults`、`fragments`、`context_slots`。
  - `extends` 只允许空或单元素数组；多继承和循环继承均报错。子 scene 只能追加 fragments，不覆盖父 fragments。
  - fragment 直接从 configured prompt asset root 加载；`fragment.id` 与 `fragment.order` 重复均报错；missing required fragment 按 manifest defaults fail closed。
  - `context_slots` 只声明 Service 必须提供的 typed context 名称；Service 调用时传入 typed context slot values；ScenePrepare 校验 required slots 并渲染 / 拼接 prompt fragments。
  - `context_slots` 第一版只支持 string slot values；manifest 声明 slot 名称、`value_type="string"` 与 `required`，Service 通过 `Mapping[str, str]` 传入值。prompt fragment 中使用 `{{slot_name}}` 做确定性文本替换；缺 required slot、未知 placeholder、非 string 值或无法渲染均 fail fast。非 string slot values 不属于 Phase 12 范围。
  - 输出 `PreparedSceneInputs`：`system_messages`、tool selection result、model hints、runtime hints、conversation hint、fragment refs、source refs、content digest、capability tags。
  - `source_refs` 与 `content_digest` 由 manifest、直接引用 fragment 内容与 assembly 输入计算，不写死在 manifest。
  - `tool_selection` 第一版只支持：
    - `mode="all"`：映射为 `SubmitFollowupRequest.tool_names=None`。
    - `mode="none"`：映射为空 `frozenset()`。
    - `mode="select"`：`tool_names` 与 `tool_tags_any` 命中取并集；未知 name 报错；tag 无匹配默认报错，只有显式 `allow_empty=true` 时允许空选择。
- 测试：
  - 单 scene assembly 输出稳定 `system_messages`、fragment refs、source refs 与 digest。
  - required context slot 缺失失败；未知 placeholder 失败；非 string slot value 失败；string slot value 被 `{{slot_name}}` 渲染到对应 fragment。
  - 单继承父优先 context slot 顺序、子追加 fragment、子覆盖 tool_selection / conversation / runtime、concrete scene 必须显式声明 model。
  - 多继承、循环继承、重复 fragment id / order、未知 tool name、tag 无匹配失败。
  - `all` / `none` / `select` 的映射语义覆盖 names、tags 与并集。
- README 触发：
  - 修改 `dayu/runtime` 与 `dayu/config/prompts`，检查 `dayu/README.md`、`dayu/config/README.md`。
- 验收标准：
  - Service 不需要二次解释 prompt fragments，只把 `PreparedSceneInputs` 显式映射到 Host construction-time inputs 与 per-run request inputs。
  - ScenePrepare 不读取配置模型、不做工具发现、不持有 Host truth。
- 停止条件：
  - 如果 scene manifest 需要表达 workflow step graph、next scene、artifact store、parser、replay / retry / stop policy、failure classification 或 checkpoint / resume，停止。
  - 如果需要读取 Fins storage 或业务仓储来组装 prompt，停止。

### Slice 5: Legacy `dayu-agent` scene asset migration

- 写入范围：当前项目配置资产目录，建议为 `dayu/config/prompts/manifests/`、`dayu/config/prompts/base/`、`dayu/config/prompts/scenes/`；迁移验证测试放在 `tests/runtime/test_scene_assets_migration.py`。
- 实施任务：
  - 迁移源限定为 `/Users/leo/workspace/dayu-agent/dayu/config/prompts/manifests/*.json`。
  - 只迁移这些 manifest 直接引用的 prompt fragment assets，例如 `base/*.md` 与 `scenes/*.md`。
  - 将旧 manifest 改写为 P12 新 schema：补 `schema_version`、`capability_tags`、明确 `model`、`runtime`、`conversation`、`tool_selection`、`defaults`、`fragments`、`context_slots`。
  - `conversation_compaction` 可作为 no-tool scene manifest 迁移，但不得变成 Skill workflow 或 Host compactor public contract。
  - 不迁移 `dayu/config/prompts/tasks/` 下 task prompts、`.contract.yaml` contract files、workflow artifacts、未被 manifest 直接引用的模板或旧 README 中的流程说明。
  - 迁移内容作为配置资产，不进入 `dayu.runtime` 包逻辑。
- 测试：
  - 所有迁移后的 scene manifest 可被新 parser 校验。
  - 每个迁移 manifest 的直接 fragment 引用可加载并参与 assembly。
  - 测试显式确认未迁移 tasks、contract files、workflow artifacts 与未引用模板。
- README 触发：
  - 修改 `dayu/config/prompts`，检查 `dayu/config/README.md`；若用户手册入口变化，检查根目录 `README.md`。
- 验收标准：
  - 迁移资产能作为真实 scene asset fixture 通过 `ScenePrepare` assembly。
  - runtime assembly 测试不要求真实财报工具扫描、Fins storage 或外部模型调用。
- 停止条件：
  - 如果旧 manifest 的某项语义只能通过旧 Service workflow / Skill workflow 表达，不能塞入 scene manifest；停止并记录后续 owner。
  - 如果迁移需要引入业务工具实现或 Fins storage 访问，停止。

### Slice 6: Import boundary tests and README sync

- 写入范围：`tests/runtime/test_import_boundary.py`、可能新增 `tests/contracts/test_import_boundary.py` 覆盖公共契约、`dayu/README.md`、`dayu/config/README.md`、必要时 `tests/README.md`。
- 实施任务：
  - 增加 import boundary 测试：`dayu.runtime.tools_discovery`、`dayu.runtime.scene_prepare`、`dayu.runtime.config_loader` 不得 import Host / Engine / Service / UI / Fins / 具体业务工具包。
  - 增加 contracts 边界测试：公共 runtime assembly 契约不得反向依赖业务层。
  - README 只同步稳定事实：Runtime assembly 三组件职责、新配置文件职责、prompt / scene asset 目录职责、旧配置不兼容删除。
  - 不在 README 写过程状态、未来计划或 discussion 记录。
- 测试：
  - import boundary tests。
  - runtime focused tests。
  - docs 触发后运行相关配置 / scene parser tests，防止 README 示例与当前接口矛盾。
- README 触发：
  - `dayu/runtime` 能力变化触发 `dayu/README.md` 检查。
  - `dayu/config` 与 prompt asset 变化触发 `dayu/config/README.md` 检查。
  - 新增测试分层或运行方式变化触发 `tests/README.md` 检查。
- 验收标准：
  - 所有 P12 runtime assembly tests、import boundary tests 与 pyright 通过。
  - README 只更新职责范围内与当前代码一致的稳定说明。
- 停止条件：
  - 如果文档同步需要改变架构术语或 Host public interface 描述，停止并回设计讨论。

## 4. ConfigLoader 新 schema 计划

- 包内默认配置目录为 `dayu/config/`；workspace 覆盖目录由调用方显式传入，不由 ConfigLoader 猜测。
- 新 schema 文件：
  - `models.json`：模型目录。temperature profile 不属于模型能力，不放入该文件。
  - `execution_profiles.json`：ordinary / compactor / scene hints 到完整 typed execution inputs 的映射配置。
  - `host_runtime.json`：Host opener 部署默认值，全部属于 construction-time assembly inputs。
  - `tool_discovery.json`：ToolsDiscovery provider specs，只读出 typed provider specs，不 import provider。
- `execution_profiles.json` concrete sketch：

```json
{
  "default_profile": "ordinary",
  "profiles": {
    "ordinary": {
      "extends": null,
      "ordinary": {
        "model_id": "deepseek-chat",
        "runner_options_profile": "analytical",
        "agent_policy_profile": "default-agent"
      },
      "compactor": {
        "model_id": "deepseek-chat",
        "runner_options_profile": "compact",
        "artifact_root": "artifacts/compaction"
      },
      "context_budget": {
        "max_context_tokens": 64000,
        "reserved_response_tokens": 4096,
        "compaction_trigger_tokens": 56000
      },
      "memory_projection": {
        "enabled": true,
        "stable_layer_max_items": 200,
        "history_pool_max_items": 1200
      },
      "truncation": {
        "enabled": true,
        "default_max_chars": 12000,
        "fetch_more_tool_name": "fetch_more"
      }
    }
  },
  "runner_options_profiles": {
    "analytical": {
      "temperature": 0.2,
      "max_tokens": 4096,
      "top_p": 0.9,
      "stream": true
    },
    "compact": {
      "temperature": 0.0,
      "max_tokens": 2048,
      "top_p": 1.0,
      "stream": false
    }
  },
  "agent_policy_profiles": {
    "default-agent": {
      "max_iterations": 24,
      "continuation_attempts": 2,
      "tool_execution_timeout_seconds": 120.0,
      "fallback_mode": "finalize",
      "fallback_prompt": "请基于已获得证据给出可审计结论。",
      "continuation_prompt": "继续完成当前财报分析任务。",
      "consecutive_failed_tool_batches": 2
    }
  },
  "runner_hints": {
    "low_latency": {
      "model_id": "deepseek-chat",
      "runner_options_profile": "analytical",
      "max_tokens": 2048,
      "stream": true
    }
  },
  "agent_hints": {
    "strict": {
      "agent_policy_profile": "default-agent",
      "max_iterations": 12,
      "tool_execution_timeout_seconds": 60.0
    }
  }
}
```

- `execution_profiles.json` typed config view shape：
  - `ExecutionProfilesConfig`：`default_profile_id: str`、`profiles: Mapping[str, ExecutionProfileConfig]`、`runner_options_profiles: Mapping[str, RunnerOptionsProfileConfig]`、`agent_policy_profiles: Mapping[str, AgentPolicyProfileConfig]`、`runner_hints: Mapping[str, RunnerHintConfig]`、`agent_hints: Mapping[str, AgentHintConfig]`。
  - `ExecutionProfileConfig`：`profile_id: str`、`ordinary: OrdinaryExecutionConfig`、`compactor: CompactorExecutionConfig`、`context_budget: ContextBudgetConfig`、`memory_projection: MemoryProjectionConfig`、`truncation: TruncationConfig`。
  - `OrdinaryExecutionConfig`：`model_id: str`、`runner_options_profile_id: str`、`agent_policy_profile_id: str`。
  - `CompactorExecutionConfig`：`model_id: str`、`runner_options_profile_id: str`、`artifact_root: str`。
  - `RunnerOptionsProfileConfig`：`temperature: float`、`max_tokens: int`、`top_p: float`、`stream: bool`，由 Service 映射为完整 `RunnerCallOptions`。
  - `AgentPolicyProfileConfig`：`max_iterations: int`、`continuation_attempts: int`、`tool_execution_timeout_seconds: float`、`fallback_mode: str`、`fallback_prompt: str`、`continuation_prompt: str`、`consecutive_failed_tool_batches: int`，由 Service 映射为完整 `AgentPolicy`。
  - `RunnerHintConfig`：可覆盖 `model_id: str`、`runner_options_profile_id: str`、`temperature: float`、`max_tokens: int`、`top_p: float`、`stream: bool` 中的显式字段；缺省字段继承选中 profile 的 ordinary runner baseline。
  - `AgentHintConfig`：可覆盖 `agent_policy_profile_id: str` 与 `AgentPolicyProfileConfig` 中的显式字段；缺省字段继承选中 profile 的 ordinary agent baseline。
  - `ContextBudgetConfig`、`MemoryProjectionConfig` 与 `TruncationConfig` 只表达 Host opener construction-time baseline，不进入 per-run request patch。
- scene hints override 顺序：
  - Service 先选择 `execution_profiles.default_profile` 或调用方指定 profile，得到完整 ordinary baseline、compactor baseline、context budget、memory projection 与 truncation baseline。
  - scene `model.default_name` 覆盖 ordinary `model_id`；该 id 必须能在 `models.json` 中解析为完整 `RunnerSpec`。
  - scene `model.temperature_profile` 覆盖 ordinary `runner_options_profile_id`，只影响 Service 后续生成的完整 `RunnerCallOptions`，不改写 `models.json`。
  - scene `runtime.runner` 命中 `runner_hints` 后，按 hint 中显式字段覆盖 ordinary runner baseline；未知 hint 是配置错误。
  - scene `runtime.agent` 命中 `agent_hints` 后，按 hint 中显式字段覆盖 ordinary agent baseline；未知 hint 是配置错误。
  - 覆盖完成后，Service 必须产出完整 `RunnerSpec`、`RunnerCallOptions` 与 `AgentPolicy`；不得把 profile id、hint id、patch dict 或 raw config fragment 传入 Host。
- overlay：
  - 按配置文件类型分别加载包内默认与 workspace 覆盖。
  - 顶层 map 按稳定 id 合并。
  - workspace 同 id 记录整条替换包内默认记录。
  - 不做隐式 deep merge；partial record 缺必填字段即失败。
  - `extends` 只允许单继承；解析后得到完整 typed record；循环、多继承、父项不存在均失败。
- 旧配置：
  - 删除 `dayu/config/llm_models.json`。
  - 删除 `dayu/config/run.json`。
  - 不保留兼容读取路径、兼容 wrapper、兼容测试或旧名 re-export。
- secret / env：
  - ConfigLoader 不解析环境变量、不替换 secret、不脱敏。
  - `api_key_ref` 与 provider 参数按 schema 原样进入 typed config view；Service / execution environment 负责使用和保护。

## 5. ToolsDiscovery 计划

- provider 来源：
  - 显式 Python provider callable import path。
  - package entry point；entry point 解析后也必须是 provider callable。
- provider identity：
  - provider id 非空且全局唯一。
  - source kind / source id 明确记录，用于 source refs。
- provider output：
  - 输出 `ToolDefinition` 集合。
  - `ToolBundle` 聚合后工具名唯一。
  - provider 空结果默认错误；显式 `allow_empty=true` 才允许。
- digest：
  - 由 ToolsDiscovery 统一计算。
  - 覆盖 tool name、LLM-facing schema、truncate spec、tags、display metadata。
  - 不 hash callable 引用本身，不依赖运行期引用标识或模块加载顺序。
  - digest 算法采用稳定序列化后的 SHA-256；序列化必须固定字段顺序，避免受 Python 对象 repr、callable identity 或模块加载顺序影响。
- source refs：
  - source refs 与 digest 用于解释、诊断、trace、audit 与后续 snapshot refs。
  - source refs 不是权限、lease、fencing、Host truth 或 owner。
- reserved framework tool name：
  - 业务工具不得占用 `fetch_more`。
  - 冲突在 discovery / aggregation 阶段 fail fast，不能等 ToolRuntime 才防御。

## 6. ScenePrepare 计划

- manifest schema：
  - 必填 `schema_version`、`scene`、`version`、`description`、`capability_tags`、`extends`、`model`、`runtime`、`conversation`、`tool_selection`、`defaults`、`fragments`、`context_slots`。
  - `schema_version` 是 manifest schema 版本；`version` 是 scene definition version。
  - `capability_tags` 给 Service workflow 或未来 Skill 引用，不表达 workflow。
- single extends：
  - `extends` 为空或单元素数组。
  - 多元素数组、循环继承、父项不存在均为配置错误。
  - 子 scene 追加 fragments；不覆盖父 fragments。
  - `context_slots` 继承去重并保持父优先顺序。
  - `tool_selection`、`conversation`、`runtime` 可显式覆盖；`model` 必须由 concrete scene 显式声明。
- prompt fragment asset loading：
  - 只加载 manifest 直接引用的 fragment path。
  - fragment path 从 prompt asset root 解析，不允许逃逸 asset root。
  - path containment 使用 resolved path 校验：fragment resolved path 必须位于 prompt asset root resolved path 之下，符号链接解析后仍不得逃逸。
  - fragment refs 与 source refs 作为诊断字段，不作为 Service 重拼 prompt 的入口。
- typed context slot values：
  - manifest 只声明 slot 名称、类型与是否必填，不携带值。第一版 declaration shape：

```json
{
  "context_slots": [
    {
      "name": "company_name",
      "value_type": "string",
      "required": true,
      "description": "财报主体名称"
    },
    {
      "name": "filing_period",
      "value_type": "string",
      "required": true,
      "description": "财报期间"
    }
  ]
}
```

  - `name` 必须非空且唯一，建议使用 `^[A-Za-z_][A-Za-z0-9_]*$`；`value_type` 第一版只能是 `"string"`；`required` 缺省视为 `true`；`description` 只用于诊断，不参与渲染。
  - Service 调用 `ScenePrepare` 时传入 typed request，而不是无结构 payload bag。第一版 API input shape：

```text
ScenePrepareRequest
  scene_id: str
  prompt_asset_root: Path
  context_slot_values: Mapping[str, str]
  available_tools: SceneToolCatalog
```

  - `context_slot_values` 只能是 string values；配置文件 JSON 输入或 Python 调用中出现非 string 值必须 fail fast。非 string slot values、结构化 slot values、列表 slot values 与 renderer callback 都不属于 Phase 12 范围。
  - 渲染机制是对每个 prompt fragment content 做确定性 `{{slot_name}}` 文本替换；placeholder 名称必须匹配已声明 slot。缺 required slot、fragment 中出现未知 placeholder、slot value 非 string 或渲染后仍残留未解析 placeholder 均 fail fast。
  - 渲染不执行表达式、不调用函数、不做条件分支、不解释 JSON/YAML，不提供默认值 fallback；需要业务派生文本时由 Service 在调用 `ScenePrepare` 前显式形成 string slot value。
- assembled system messages：
  - ScenePrepare 输出已装配 `system_messages`。
  - Service 不二次解释 fragments，只把结果映射到 `SubmitFollowupRequest.system_prompt` 或外部 request envelope。
- source refs and digest：
  - digest 基于 manifest、直接 fragment 内容与 assembly 输入计算。
  - source refs 解释 manifest / fragment 来源。
- tool_selection：
  - `all` -> `SubmitFollowupRequest.tool_names=None`。
  - `none` -> `frozenset()`。
  - `select` -> `tool_names` 与 `tool_tags_any` 命中工具并集。
  - 未知 tool name 报错；tag 无匹配默认报错；显式 `allow_empty=true` 才允许空选择。

## 7. Legacy `dayu-agent` scene asset 迁移计划

- 迁移源：
  - `/Users/leo/workspace/dayu-agent/dayu/config/prompts/manifests/*.json`
  - 这些 manifest `fragments[].path` 直接引用的 prompt fragment assets，例如 `base/*.md`、`scenes/*.md`。
- 迁移目标：
  - 当前项目配置资产目录，建议 `dayu/config/prompts/manifests/`、`dayu/config/prompts/base/`、`dayu/config/prompts/scenes/`。
- 明确不迁移：
  - `dayu/config/prompts/tasks/`。
  - `*.contract.yaml`。
  - workflow artifacts。
  - 未被 scene manifest 直接引用的 templates。
  - 旧 Service / Host / prompting 实现代码。
- 验证：
  - 迁移后的所有 manifest 均通过新 schema parser。
  - 迁移后的所有直接 fragment refs 均可加载。
  - 至少一个 no-tool scene 与一个 select-tools scene 完成 assembly。

## 8. Import boundary tests 与验证命令

每个 slice 修改后先运行 focused tests；phase 收口运行完整 P12 验证集。

```bash
source .venv/bin/activate
pytest tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py -q
```

```bash
source .venv/bin/activate
pytest tests/runtime/test_config_loader.py -q
```

```bash
source .venv/bin/activate
pytest tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py tests/runtime/test_scene_assets_migration.py -q
```

```bash
source .venv/bin/activate
pytest tests/runtime/test_import_boundary.py tests/contracts/test_import_boundary.py -q
```

```bash
source .venv/bin/activate
pytest tests/runtime tests/contracts/test_import_boundary.py tests/host/test_tooling_options.py tests/host/test_submit_followup_public_contract.py tests/host/test_per_run_tool_selection.py -q
```

```bash
source .venv/bin/activate
python -m pyright dayu/runtime dayu/contracts tests/runtime tests/contracts
```

若 implementation 触及 Host-facing mapping tests，再补跑：

```bash
source .venv/bin/activate
python -m pyright dayu/runtime dayu/contracts dayu/host tests/runtime tests/contracts tests/host
```

## 9. 风险与停止条件

- 如果实现看起来需要新增、删除、重命名或重塑 Host public command、Host handle method、`OpenHostOptions` 字段、`SubmitFollowupRequest` 字段或 `dayu.host` public exports，停止并回 Host public interface design gate。
- 如果实现需要修改 Engine execution path、Runner 协议状态机、Engine tool loop 或让 Engine 理解 Host tool governance，停止。
- 如果实现需要访问 `dayu.fins.storage`、读取财报仓储或把 Fins storage 语义放入 runtime assembly，停止。
- 如果实现需要表达 workflow、Skill semantics、step graph、checkpoint / resume、retry / replay policy 或 failure classification，停止。
- 如果实现发现当前 per-run override 字段不足，需要新增字段超过 `system_prompt`、`tool_names`、`runner_spec`、`runner_options`、`agent_policy`，停止。
- 如果 `dayu.runtime` 为满足功能不得不 import Host / Engine / Service / UI / Fins / 具体业务工具包，停止。
- 如果旧 `dayu-agent` asset 迁移需要 task prompts、contract files、workflow artifacts 或未引用模板才能表达 scene manifest，停止并把该需求转交 Service / workflow / Skill 后续 owner。
