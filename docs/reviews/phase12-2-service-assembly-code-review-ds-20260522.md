# Code Review — Phase 12.2 Service Assembly

## Scope

- **Mode**: current changes (scoped to Phase 12.2)
- **Branch**: `docs/phase12-design-discussion`
- **Base**: `main`
- **Output file**: `docs/reviews/phase12-2-service-assembly-code-review-ds-20260522.md`
- **Included scope**:
  - `dayu/runtime/config_loader.py`, `dayu/runtime/scene_prepare.py`, `dayu/runtime/assembly.py`, `dayu/runtime/location.py`, `dayu/runtime/tools_discovery.py`, `dayu/runtime/tool_truncation.py`, `dayu/runtime/_digest.py`, `dayu/runtime/__init__.py`
  - `dayu/config/host_runtime.json`
  - `dayu/service/__init__.py`, `dayu/service/host_assembly.py`
  - `utils/smoke_host_public_multiturn.py`
  - `tests/runtime/test_config_loader.py`, `tests/runtime/test_scene_prepare.py`, `tests/runtime/test_smoke_host_public_multiturn_assembly.py`
  - `tests/service/test_host_assembly.py`
  - `README.md`, `dayu/README.md`, `dayu/config/README.md`, `tests/README.md`
  - Plan/implementation artifacts: `docs/reviews/phase12-2-service-assembly-plan-codex-20260522.md`, `docs/reviews/phase12-2-service-assembly-implementation-codex-20260522.md`
- **Excluded scope**:
  - `docs/reviews/repo-review-20260522-070034.md`, `docs/reviews/repo-review-20260522-070045.md`（controller 指令忽略）
  - Other `dayu/engine/`, `dayu/host/`, `dayu/contracts/`, `dayu/fins/` 中未被 Phase 12.2 直接触及的已有代码
- **Parallel review coverage**: 4 个 `Explore` subagent 分别覆盖 (1) plan/implementation artifacts, (2) `dayu/runtime/*` 全部 8 文件, (3) `dayu/service/*` 全部文件, (4) smoke 脚本、测试与 READMEs。主 reviewer 逐条在源码中验证每项 finding 的直接证据。

## Review Approach

沿 8 个审查重点逐项走读真实代码路径：

1. **架构边界走读**：检查 `dayu/runtime/*` 全文 import 语句、`dayu/service/host_assembly` 的依赖方向、Service helper 是否放在正确层。
2. **ConfigLoader fail-fast 与无兼容旧 schema 走读**：检查异常体系、类型系统、extends 校验、跨文件引用校验、`_LEGACY_CONFIG_FILES` 仅诊断用事实。
3. **ScenePrepare 拥有 scene 解释权走读**：检查 `prepare()` 输出 `PreparedSceneInputs.system_prompt`、Service/smoke 是否不再自行合成 system prompt。
4. **host_assembly 是真正 assembly helper 走读**：检查三公开函数、私有 helper 数量、是否传 raw dict 进 Host、是否有兼容 facade。
5. **smoke 脚本真实 Service-like assembly 走读**：走读 `_prepare_runtime_assembly()` 调用链，检查 location → ConfigLoader → ToolsDiscovery → ScenePrepare → Service helper → open_host 完整链。
6. **config/scene schema 到 Host public contracts 映射摩擦检查**。
7. **测试与 README 覆盖当前事实检查**。
8. **AGENTS.md / CLAUDE.md 违规检查**：中文 docstring、严格类型、`Any`/`object`、魔法字符串泛滥、反向依赖。

## Findings

### 1-未修复-低-`_agent_fallback_mode_from_config` 用手工 if/elif 链替代 StrEnum 原生构造

- **入口/函数**: `_agent_fallback_mode_from_config` (host_assembly.py:807)
- **文件(行号)**: `dayu/service/host_assembly.py` (815–818)
- **输入场景**: runtime config 中的 `fallback_mode` 字符串值为 `"force_answer"` 或 `"raise_error"`。
- **实际分支**: 在 815 行 `if value == "force_answer"`、817 行 `if value == "raise_error"` 分支，逐条手工映射到 `AgentFallbackMode.FORCE_ANSWER` / `AgentFallbackMode.RAISE_ERROR`。
- **预期行为**: `AgentFallbackMode` 是 `StrEnum`（见 `dayu/engine/contracts/agent_policy.py:15`），每个成员值等于其名字符串（`FORCE_ANSWER = "force_answer"`，`RAISE_ERROR = "raise_error"`）。`StrEnum` 原生支持 `AgentFallbackMode(value)` 直接构造，无需手工 if/elif 映射。
- **直接证据**:
  - `AgentFallbackMode` 定义为 `class AgentFallbackMode(StrEnum)`（`dayu/engine/contracts/agent_policy.py:15`），成员值 `FORCE_ANSWER = "force_answer"`（同文件 line 25）。
  - host_assembly.py:815–818 手工逐条比较字符串并返回枚举成员，而非 `return AgentFallbackMode(value)`。
- **影响**: 当前映射正确，无行为错误。但如果 `AgentFallbackMode` 新增成员（如 `FALLBACK_TO_DEFAULT`），此函数会漏掉新值，需同步修改。`AgentFallbackMode(value)` 会自动覆盖新增成员。这是 maintainability 问题，不影响当前正确性。
- **建议改法和验证点**: 替换为 `return AgentFallbackMode(value)`；若传入非法值，`StrEnum` 构造自动 `raise ValueError`，与原函数 line 819 行为一致。验证点：运行 `pytest tests/service -q` 和 `pytest tests/runtime/test_scene_prepare.py -q`。
- **修复风险（低）**: `StrEnum` 构造对合法值与原 if/elif 行为完全等价；非法值同样抛 `ValueError`。
- **严重程度（低）**:
- **blocking**: 否。不影响当前正确性，Phase 12.2 assembly 工作正常。

### 2-未修复-低-根 README.md 引用四个不存在的文件

- **入口/函数**: 根 `README.md` 用户手册章节引用。
- **文件(行号)**: `README.md` (316, 670, 1177, 1181)
- **输入场景**: 读者跟随 README 文档导航点击链接。
- **实际分支**: 四个链接指向不存在的文件。
- **预期行为**: README 中引用的文件应在磁盘上存在，或移除对不存在文件的引用。
- **直接证据**:
  - `README.md:316`: `详见[dayu/web/README.md](dayu/web/README.md)` — `dayu/web/` 目录完全不存在（`ls dayu/web/` 返回空）。
  - `README.md:670`: `回退 dayu/assets/定性分析模板.md` — 文件不存在（`ls dayu/assets/定性分析模板.md` 返回 No such file）。
  - `README.md:1177`: `保留仓库中的 [LICENSE](LICENSE) 和 [NOTICE](NOTICE)` — `NOTICE` 不存在（`ls NOTICE` 返回 No such file）。
  - `README.md:1181`: `请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)` — 文件不存在。
- **影响**: 文档死链，不影响代码正确性。新读者可能困惑。
- **建议改法和验证点**: 为每个引用决定：如文件计划后续创建，保留但标注"（待创建）"；如文件不会创建，移除引用。CLAUDE.md 文档约束要求"不写未来计划"，建议移除或替换为实际存在的路径。
- **修复风险（低）**: 仅文档修改。
- **严重程度（低）**:
- **blocking**: 否。文档漂移不阻塞 Phase 12.2 功能正确性。

### blockable finding count = 0

## Architecture Boundary Verification

以下逐项对 8 个审查重点做基于直接代码阅读的验证结论。

### 重点 1: dayu.runtime 不 import host/engine/service/ui/fins；Service helper 在 dayu.service 层

- `dayu/runtime/__init__.py:12-14` 硬约束 docstring 声明本包不得 import 业务层。
- 所有 8 个 `dayu/runtime/*.py` 文件中，grep `from dayu.(host|engine|service|ui|fins)` / `import dayu.(host|engine|service|ui|fins)` 返回 **0 匹配**。
- `dayu/runtime/` 仅 import `dayu.contracts`（允许）、标准库、以及 `dayu.runtime.*` 内部模块（允许）。
- 新增的 Service helper 在 `dayu/service/host_assembly.py`，不在 `dayu/runtime/`。Service 层正确地 import `dayu.runtime.*`（向下依赖，合法），并 import `dayu.host.*`、`dayu.engine.*`（向下依赖，合法）。
- 无反向依赖。

**结论：通过。**

### 重点 2: host_runtime.json Host construction tuning 字段与 ConfigLoader fail-fast

- `dayu/config/host_runtime.json` 新增 6 个 SQLite write retry 字段（`write_busy_retry_count`、`write_retry_initial_delay_seconds`、`write_retry_backoff_multiplier`、`write_retry_max_delay_seconds`）、`payload_inline_threshold_bytes`、`worker_startup_timeout_seconds`。这些字段足以替代 smoke-local 旧私有默认值。
- `ConfigLoader`（config_loader.py:2229 行）具有 5 个异常类的 fail-fast 体系（`ConfigLoadError` → `ConfigFileNotFoundError`、`ConfigShapeError`、`ConfigExtendsError`、`ConfigFieldError`）。
- 每类 JSON 值的读取都有专门 typed accessor（`_require_str_field`、`_require_positive_float_field`、`_require_int_field` 等），非法类型即时 raise。
- extends 继承链有完整校验：循环检测、自引用检测、多父 rejection、缺失父级检测。
- 跨文件引用校验：`host_runtime.lane_name` 必须存在于 `runtime_lanes`；`execution_profile.model_id` 必须存在于 `models`。
- `_LEGACY_CONFIG_FILES = frozenset({"llm_models.json", "run.json"})`（config_loader.py:26-27）仅用于诊断查询（`legacy_config_file_names()` 函数），loader 从不读取这些文件。
- 31 个 `@dataclass(frozen=True, slots=True)` 输出类型，所有字段完整类型标注。

**结论：通过。**

### 重点 3: ScenePrepare 直接输出 system_prompt

- `scene_prepare.py:510-512`：`PreparedSceneInputs(system_prompt="\n\n".join(rendered_messages), ...)`。
- `Service` 不再自行拼接 system prompt：`host_assembly.py:346` 直接用 `system_prompt=scene_inputs.system_prompt` 传给 `SubmitFollowupRequest`。
- `smoke` 脚本不再自行拼接：`smoke_host_public_multiturn.py:408-420` 通过 `prepare_scene()` 获取 `scene_inputs`，由 `compose_submit_followup_request()` 使用其 `system_prompt` 字段。
- ScenePrepare 是系统中系统级提示词的唯一生产者。

**结论：通过。**

### 重点 4: dayu.service.host_assembly 是真正的 Service assembly helper

- `host_assembly.py:961` 行，包含 20+ 私有辅助函数，三个阶段（工具发现 `discover_service_tools`、open_host 装配 `compose_open_host_options`、per-run 请求装配 `compose_submit_followup_request`）。
- 无兼容 facade：没有仅透传的函数、没有兼容旧路径的 re-export、没有 wrapper 仅调用另一个函数。
- 不传 raw patch dict 进 Host：`_compose_options()`（line 357-399）逐字段构造 `OpenHostOptions`，所有字段来自 typed config 对象。唯一 `dict[str, str]` 是 `_render_headers()` 内部用于构造 `RunnerSpec.headers`（typed attribute），不泄露进 Host。
- `env: Mapping[str, str]` 仅在 `_runner_spec_from_model()` 中用于解析 API key 和 header 模板变量，不传进 Host 可见对象。

**结论：通过。**

### 重点 5: smoke 脚本模拟真实 Service-like assembly

- `smoke_host_public_multiturn.py:389-443` `_prepare_runtime_assembly()` 完整链路：
  1. `resolve_runtime_locations()` — runtime location 解析
  2. `ConfigLoader().load()` — typed 配置加载
  3. `discover_service_tools(config)` — Service 工具发现 helper
  4. `prepare_scene(ScenePrepareRequest(...))` — scene 装配
  5. `compose_open_host_options(ServiceOpenHostAssemblyRequest(...))` — Service assembly helper
  6. `open_host(assembly.options)` — Host public handle
- 脚本级别常量（81-91 行）均为 smoke 专用标识名和显示参数（`_SMOKE_TOOL_NAME`、`_SMOKE_MARKER`、`_PROMPT_PAD_REPEAT` 等），不替代生产 schema 默认值。
- 无直接手写 `OpenHostOptions`，不跳过 Service assembly 层。

**结论：通过。**

### 重点 6: config/scene schema 到 Host public contracts 映射摩擦

- `host_assembly.py` 完整覆盖 model 选择、runner hint 选择、agent policy 合并、工具截断补齐、memory projection policy 构造、context budget policy 计算、provider extension 映射、header/env 解析、OpenHostOptions 字段构造、SubmitFollowupRequest 构造。
- 当前映射路径为：`ConfigLoader typed view → host_assembly selection/merge → Host public typed inputs`。中间无 raw dict 阶段，无信息丢失，无静默默认值覆盖。
- **无关键摩擦项**。唯一注意的是 `worker_backend` 在 JSON schema 中是裸字符串 `"local"` — 如未来支持 remote worker，需要新的 backend 名字符串约定和对应的 `OpenHostOptions` 构造分支。

**结论：通过，无摩擦阻断。**

### 重点 7: 测试与 README 覆盖当前事实

- 测试覆盖：
  - `test_config_loader.py`：19 个测试，其中 12 个显式 error path（循环/自引用/缺失父级/非法类型/部分记录 rejection/embedded-id 字段/旧 schema 字段/closed enum/lane 交叉引用/claim-ttl 业务规则/XOR 约束/JSON shape error）。
  - `test_scene_prepare.py`：27 个测试，其中 17 个显式 error path（缺失 slot/未知占位符/非字符值/未解析占位符/fragment 路径逃逸/符号链接逃逸/缺失 required fragment/重复 ID/循环继承/多重继承/legacy 字段/closed enum/非法 ID 格式/manifest scene-id 不匹配）。
  - `test_smoke_host_public_multiturn_assembly.py`：3 个测试，1 个 error path（工具未发现 fail-fast），1 个 boundary（`_find_smoke_tool` 隔离），1 个全面 happy path 断言。
  - `test_host_assembly.py`：2 个测试，覆盖 workspace overlay tuning 映射和 system_prompt 传递。
- README 覆盖：
  - `tests/README.md`、`dayu/config/README.md`、`dayu/service/README.md` 均以现在时态描述当前事实，无"未来计划"语言。
  - `dayu/config/README.md` 准确记录已删除的旧 schema（`llm_models.json`、`run.json`、`runner_options_profiles` 等）及其不可用性。
- 根 README.md 有文档漂移（见 Finding 2），但不影响代码事实覆盖。

**结论：通过（含 Finding 2 的文档漂移）。**

### 重点 8: AGENTS.md / CLAUDE.md 违规

- **中文 docstring**：所有公共函数、类、模块均有完整中文 docstring。验证通过。
- **严格类型**：所有函数参数、返回值有类型标注。`Any` 和 `object` 在任何审查文件中不出现作为类型标注。验证通过。
- **无魔法字符串泛滥**：所有审查文件中的字符串常量均声明为模块级 `Final` 常量。唯一的行内字面量是 `scene_prepare.py:512` 的 `"\n\n"` join 分隔符（极轻度）。验证通过。
- **无反向依赖**：`dayu/runtime/` 不 import 任何 `dayu.host`/`dayu.engine`/`dayu.service`/`dayu.ui`/`dayu.fins`。验证通过。
- **无兼容性代码**：无兼容性 re-export、兼容性常量 re-export、兼容性 wrapper/facade。验证通过。

**结论：通过。**

## Open Questions

- `AgentFallbackMode` StrEnum 成员值（`"force_answer"`、`"raise_error"`）与 JSON config schema 字符串一致，但设计上 config schema 应被视为 StrEnum 的"影射"还是独立真源？当前 scene_prepare.py `_AGENT_FALLBACK_MODES` frozenset（line 77）、host_assembly.py 手工映射（line 815-818）、与 `AgentFallbackMode` StrEnum（agent_policy.py:25）形成三处"相同值"的独立声明。如果 StrEnum 新增成员，scene_prepare（runtime 层）无法 import engine 枚举，必须在 `_AGENT_FALLBACK_MODES` 手工同步。这是设计取舍（runtime 不能 import engine 的硬约束）而非缺陷，但值得记录。

## Residual Risk

1. **`worker_backend` 裸字符串**：`host_runtime.json` 中 `"worker_backend": "local"` 和 `host_assembly.py:68` `_WORKER_BACKEND_LOCAL = "local"` 是裸字符串约定。如果未来支持 `"remote"` backend，需要新的字符串约定和对应的 `_compose_options()` 分支。当前仅支持 local worker 是 Phase 12.2 的显式 scope 限制，不是遗漏。

2. **`fallback_mode` 三处真源**：`AgentFallbackMode` StrEnum、`scene_prepare.py` `_AGENT_FALLBACK_MODES` frozenset、`host_assembly.py` `_agent_fallback_mode_from_config()` 各自独立声明 `"force_answer"`/`"raise_error"` 字符串。runtime 层无法 import engine 枚举（硬约束），所以 `_AGENT_FALLBACK_MODES` 的独立声明是架构必要的。但 host_assembly（Service 层）可以使用 `AgentFallbackMode(value)` 直接构造（见 Finding 1），减少一处手工映射。

3. **remote worker 未覆盖**：`host_assembly.py:382-383` 对 `worker_backend != "local"` 直接 `raise ValueError`。remote worker 在 Phase 12.2 scope 外，但当前实现正确地将此作为 fail-fast 处理。

4. **并发场景测试缺失**：当前测试覆盖 fail-fast、happy-path、boundary，但缺少女并发场景（多工具调用竞争、超时、worker 启动失败恢复）。这些由 Host/Engine 层负责，不属于 Service assembly 层测试范围。

5. **smoke 脚本 180s 超时**（`smoke_host_public_multiturn.py:612`）：硬编码超时是 smoke 脚本的安全网而非生产 policy，不构成 issue。

## Adapter Helper / Config-Contract 摩擦项

无。当前 config schema 通过 `host_assembly.py` 的三段映射（工具发现、open_host 装配、per-run 请求装配）正确转换为 Host public typed inputs。config 字段 → typed config dataclass → Host `OpenHostOptions` / `SubmitFollowupRequest` 的路径是完整的，无需额外 adapter helper。

## Conclusion

**PASS_WITH_FINDINGS**

两条 finding 均为 non-blocking（低严重程度，不阻塞 Phase 12.2 目标），blocking finding count = 0。

- Finding 1（`_agent_fallback_mode_from_config` 手工 if/elif 链）→ maintainability 优化建议。
- Finding 2（README 死链引用）→ 文档漂移。

8 个审查重点全部通过。Phase 12.2 service assembly 当前代码在 correctness、architecture boundary、public contract、typed config fail-fast、test error-path coverage 方面均符合设计要求。无阻塞合并问题。
