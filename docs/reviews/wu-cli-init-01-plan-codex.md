# WU-CLI-INIT-01 Code-Generation-Ready Plan

## Gate metadata

- Work unit：`WU-CLI-INIT-01`
- 类型：CLI public contract / workspace initialization bug fix
- gate：`plan`
- decision：`accepted`
- 日期：2026-07-30
- accepted oracle：`cli.init.workspace-initialization@1`
- 修复前基线 commit：`933908a8`
- goal artifact：
  `docs/reviews/wu-cli-init-01-goal-confirmation-controller.md`
- plan review adjudication artifact：
  `docs/reviews/wu-cli-init-01-plan-review-adjudication-controller.md`
- goal artifact SHA-256（本 plan 读取时）：
  `01f56e6515d2707f7cafe3c077a37179eab4ac2ef53fe4d7caf1032404425576`
- oracle registry SHA-256（本 plan 读取时）：
  `a39bf94ff992f073d55c5fc64e839ab08b3ff71ca7d13bb1b9fb230127c92019`
- 本 artifact path：
  `docs/reviews/wu-cli-init-01-plan-codex.md`
- current gate / next entry point：`implementation S1`

本 plan 不修改 goal artifact 或 accepted oracle。当前工作树中的这两个文件由
Controller / 用户拥有；后续 implementation commit 不得把它们与本 work unit
实现文件误 stage。

## 1. 目标、动机与成功信号

### 1.1 目标

让 `dayu-cli init` 完整满足
`cli.init.workspace-initialization@1`，同时修复 package fallback、workspace
初始化、主 Run override 与 compactor 装配之间的模型语义漂移：

1. 裸 `init` 使用 `./workspace`；`init` 的命令面完全没有 `--config`。
2. Agent execution 的正式模型参数为 `--model/-m`；删除
   `--model-name`，不留 alias、shim 或兼容字段。
3. init 的 ordinary / thinking 选择投影到全部 16 个 package-known scene。
4. `conversation_compaction` 不拥有独立 provider/model family。它与同一 init
   选择的其它 scene 必须解析到相同的：
   - provider；
   - provider 实际 model 字符串；
   - endpoint；
   - credential ref。
   它只可以在 thinking extension、temperature、top-p、stream、runner option
   hint 等运行参数上不同。
5. 未执行 init 时，package manifests 和 execution-profile fallback 同样只使用
   一个默认 provider/model family，不要求 Mimo 与 DeepSeek 两家 credential。
6. 单次主 Run `--model/-m` 只覆盖该 Run；不写 workspace，也不覆盖 compactor。
7. 可恢复交互错误在当前步骤重试；EOF=1、parser misuse=2、SIGINT=130。
8. FIRST / PRESERVE / OVERWRITE / RESET / repair 由 managed-tree 实际结果判定，
   并保持 staging、原子替换、rollback 与 no-follow 安全边界。
9. 15 个 init choice 全部进入真实 provider matrix：外部不可用可以是明确、
   脱敏、bounded 的正确非零结果；任何内部 schema/profile/model/context
   incompatibility 都是产品 bug。

### 1.2 动机

该问题真实存在且严重性评估成立。`init` 是 workspace 配置、scene 默认模型、
secret ref 与后续 runtime 装配的上游 owner。当前实现会产生三类不同层级的错误：

- parser 公开了错误的命令契约；
- init / package config 产生了 compactor 与其它 scene 不同源的模型事实；
- workspace transaction 与交互状态机没有完整兑现 accepted repair / exit
  contract。

如果继续基于这些产物校准 `prompt`、`interactive` 或 provider matrix，下游证据会把
错误的前置状态固化成 oracle observation，因此本 work unit 应先完成。

### 1.3 成功信号

- `dayu-cli init --help` 不含 `--config`。
- `dayu-cli init --config path` 与
  `dayu-cli --config path init` 都由 parser owner 退出 2。
- `prompt`、`interactive`、`session resume` 展示并接受 `--model/-m`；
  `--model-name` 退出 2。
- 15 个普通 package scene、`conversation_compaction`、四个 execution profile
  fallback 均解析到 Mimo Token Plan family；ordinary / thinking 的 extension
  可以不同。
- 每个 init choice 的 ordinary / thinking pair 都通过统一 family identity
  校验；16 个 manifest 投影后，compactor 与主 scene 的 family identity 相同。
- Service assembly 在无主 Run override 时使用 scene default；有
  `--model/-m` 时仅 ordinary effective selection 改变，compactor 仍使用
  workspace/package family anchor。
- Custom / Ollama 输入的 context window 不低于本次 init 目标实际生效的 typed
  default execution profile 的 `min_context_window_tokens`；低值在 context 步骤
  原地重试，而不是发布后才失败。
- choice、动态 model name、endpoint、context、required secret、yes/no 输入错误
  都可在同一进程修正后继续。
- Enter 在 reset confirmation 表示 No 并退出 0；EOF 退出 1；SIGINT 退出 130；
  三者都无部分 publication。
- required secret persistence batch 的确认选择 No/Enter 或 EOF 都表示本次 init
  未完成、退出 1；SIGINT 退出 130；四者均不写环境值且不发布 config / `.dayu`。
- clean publication 由版本化 manifest 验证 5 个目录、43 个文件、内容摘要与模型
  投影；不依赖 CLI 自报 mode。
- PRESERVE 补齐缺失的五类根配置文件与 prompt 文件，保留用户文件和非 owner
  字段；不能无损保留时明确要求 `--overwrite`。
- OVERWRITE / RESET 以 whole-tree 重建、sentinel 消失/保留、rollback 后原始 digest
  判定。
- repair 对普通文件占据 managed root 只在对应显式 destructive mode 中执行；
  symlink、dangling symlink、special file、非法 lock identity 始终拒绝。
- package fallback、workspace default、单次 override 恢复和 15-row matrix 都有
  real-prompt、runner-input/trace 与 no-fallback evidence。

## 2. 非目标与 scope boundary

### 2.1 非目标

- 不修改 Host lifecycle、Engine loop、memory、EventLog 或 durable schema。
- 不新增 provider integration，不申请 credential，不启动 Ollama，不保证外部服务
  可用。
- 不把 mock/fake/cached answer 当作真实 provider evidence。
- 不修改 `prompt` / `interactive` 的其它业务或 UI 行为。
- 不为 `--model-name`、`init --config`、旧 schema 或旧测试保留兼容代码。
- 不新增通用 CLI framework、通用 smoke framework、配置迁移框架或第二套 config
  loader。
- 不改变 portfolio、Fins storage 或非 init-owned assets 的 owner。
- 不让 compactor 直接继承本次主 Run override；模型家族同源指 workspace/package
  default family，不指 invocation-local override。

### 2.2 允许边界

- CLI parser、init orchestrator、init catalog、workspace transaction。
- runtime-neutral 的 resolved model-family identity helper。
- Service model selection 的直接 assembly 边界。
- package scene manifests 与 execution-profile fallback 的默认模型 id。
- 对应 CLI / runtime / service tests。
- 一个窄职责 real provider smoke 与一个版本化 managed-file manifest。
- 命中触发规则的 README 与 CLI CI 执行说明。

## 3. Design document / oracle alignment

本 work unit 没有独立 design document。设计依据按优先级为：

1. 用户冻结的 compactor 模型家族同源语义；
2. accepted oracle `cli.init.workspace-initialization@1`；
3. goal confirmation artifact；
4. 当前生产代码与测试的直接证据。

本 plan 与 oracle 的关键映射：

| Oracle predicate | Plan owner / slice |
|---|---|
| `init.workspace-resolution` | S1 parser contract |
| `init.first-publication` | S4 managed transaction，S5 versioned manifest |
| `init.model-defaults-and-overrides` | S2 family identity，S3 package / Service assembly |
| `init.secret-handling` | S2 interaction state machine，S5 redaction |
| `init.interactive-validation-and-exit` | S2 |
| `init.preserve` | S4 |
| `init.overwrite` | S4 |
| `init.reset` | S4 |
| `init.repair-and-path-safety` | S4，S5 real downstream validation |
| `init.real-provider-validation` | S5 |

## 4. 第一性原理判断与直接代码证据

### 4.1 Parser contract

- `dayu/cli/arg_parsing.py::_build_global_arguments_parent(...)` 把
  `--config` 放在所有命令共享 parent 中，`_register_init_command(...)` 因继承该
  parent 而展示和接受 `--config`。
- 同文件 `_add_agent_execution_arguments(...)` 注册
  `--model-name/-m`，`ParsedCliArgs` 与 default namespace 仍使用
  `model_name`。
- `dayu/cli/session_execution.py::_prepare_session_runtime(...)` 是 CLI 到
  `ServiceAssemblyOverrides.model_id` 的唯一共享映射点，当前读取
  `args.model_name`。

结论：修复必须发生在 parser owner 与其直接 typed namespace consumer，不能在
`run_init_command` 中静默忽略 `config_dir`，也不能只改 help。

### 4.2 Model family / compactor

- `dayu/cli/init_catalog.py::project_known_manifest_models(...)` 已拥有 16 个
  package-known manifest 的投影；`conversation_compaction` 当前在 ordinary role
  set。
- 当前 13 个静态 choice 的 ordinary / thinking resolved pair 已经在
  `provider/model/endpoint/api_key_ref` 四字段上相同；差异位于
  `provider_request_extension` 等运行参数。Ollama / Custom 使用同一个 model id。
- 当前 package manifests 中其余 15 个 scene 使用 Mimo Token Plan family；
  `conversation_compaction.json` 使用 `deepseek-v4-flash`。
- 当前四个 `execution_profiles.json` 的 run / compactor baseline 都使用
  `deepseek-v4-flash`，形成 package fallback 的第二模型家族。
- `dayu/runtime/assembly.py::select_runner_option_hint(...)` 已定义字段级
  `run_override > scene_model_hints > execution_baseline > base_policy`。
- `dayu/service/host_assembly.py::compose_open_host_options(...)` 的主 selection
  消费 `request.scene_inputs.model_hints`，compactor selection 却显式传
  `scene_model_hints=None`。

结论：family identity 的语义 owner 应位于 runtime-neutral assembly 层；package
默认值由当前 JSON / manifest owner 修正；Service 只通过既有 selection helper
选择 primary default、主 Run effective 与 compactor effective，不重新从 raw
字段猜测。

### 4.3 Interactive state machine / profile compatibility

- `dayu/cli/commands/init.py::_parse_model_choice(...)`、
  `_read_non_empty_input(...)`、`_read_positive_integer(...)` 一次非法输入即抛出。
- `_confirm(...)` 把 EOF 重写成默认 No，无法区分 Enter 与 Ctrl+D。
- endpoint 与动态 model name 的严格语法仅在
  `dayu/cli/init_catalog.py` 的 dynamic settings owner 中校验，导致错误不能在当前
  field prompt 立即重试。
- Custom 默认 context 是 131072，而 package default profile
  `standard-256k.min_context_window_tokens` 是 262144；Ollama 虽默认 262144，但
  用户可输入更小正整数。
- `dayu/runtime/assembly.py::validate_execution_profile_context_window(...)`
  已是运行期 profile/model compatibility owner，明确不会自动换 profile。

结论：init 不复制 profile 分档常量；唯一读取 API 是
`ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load_execution_profiles(...)`。
在已确认 reset、取得 lock、复核 locked snapshot 并确定 target mode 后，但在第一个
model-choice prompt 前只调用一次：

- FIRST / OVERWRITE / confirmed RESET 传
  `workspace_config_dir=None`，目标实际生效 profile 来自即将发布的 package layer；
- PRESERVE 传真实 workspace config dir，使用 ConfigLoader 的 layered typed load；
  workspace `execution_profiles.json` 缺失时由 loader 的 package layering 规则取得
  package layer，存在时其合法 overlay 就是本次 init 后实际生效的 target profile；
  存在但 JSON/schema/default-profile 引用非法时 fail closed，明确提示
  `rerun with --overwrite`，不得改传 `None` 或以 package 值掩盖损坏。

从返回的 `ExecutionProfilesConfig.default_execution_profile_id` 定位 target typed
`ExecutionProfileConfig.min_context_window_tokens`，再以显式参数传给 model selection
与 context reader。package source 的 `ConfigLoadError` 在 CLI adapter 边界转成不
包含原始配置值或路径的可操作 `CliInitOperationError`，提示 repair/reinstall package
config；PRESERVE 已存在 workspace profile 的 typed load 失败则提示
`--overwrite`。两者都退出 1，且不得进入 model/secret prompt、staging、环境写入或
publication；不得 loose-read JSON、硬编码 262144、自动换 profile，或在非法
workspace profile 上 fallback 到 package。运行期 validator 继续保留最终 fail-fast
责任。

### 4.4 Workspace transaction

- `dayu/cli/init_workspace.py` 已拥有 managed-root manifest、snapshot、private
  staging、真实 ConfigLoader / Service validation、backup、publication、rollback、
  fsync 与 no-follow cleanup。
- PRESERVE 的 `_copy_missing_prompt_files(...)` 只补 prompts，不补
  `config_file_names()` 的五个根配置文件。
- `snapshot_managed_roots(...)` 在 mode 决定前要求 managed root 必须是目录，所以
  即使显式 `--overwrite/--reset` 也不能 repair 普通文件 root。
- private cleanup 只接受目录；若显式 destructive repair 允许普通文件 root，其
  backup cleanup 也必须支持 identity-locked ordinary file。

结论：扩展现有 transaction owner，不新建 mutation helper。symlink/reparse/special
file 仍在 snapshot 边界 fail closed。

## 5. Semantic owners

| 语义 | 唯一 owner | 生产者 / 校验 / 消费 |
|---|---|---|
| CLI 可见参数与 parser exit 2 | `dayu.cli.arg_parsing` | parser 注册、typed namespace、init-specific rejection |
| invocation-local 主模型 override | CLI parser + `session_execution` 映射；Service typed override 消费 | `--model/-m -> ServiceAssemblyOverrides.model_id` |
| resolved model family identity | `dayu.runtime.assembly.ModelFamilyIdentity` 与构造 helper | 从 typed `ModelConfig` 产生 `provider/model/endpoint/api_key_ref` identity |
| init choice ordinary/thinking 同源 | `dayu.cli.init_catalog` | 复用 runtime family identity 校验 catalog pair |
| scene default model id 投影 | `dayu.cli.init_catalog.project_known_manifest_models` | 只更新 16 个 known manifest 的 owner 字段 |
| package default family | `dayu/config/models.json`、manifests、execution profiles | JSON / manifest current contract；ConfigLoader 解析 |
| primary default、main effective、compactor effective selection | `dayu.runtime.assembly.select_runner_option_hint`；`dayu.service.host_assembly` 编排 | Service 不从字符串或日志反推 |
| compactor runner 参数 | `conversation_compaction` manifest/model hint 与 model 内 `conversation_compaction` runner hint | 允许 temperature/stream/extension 不同，不拥有 provider family |
| dynamic input schema | `dayu.cli.init_catalog` | field validators 与 settings dataclass 复用 |
| target effective profile minimum | `ConfigLoader.load_execution_profiles(...)` 返回的 target typed default `ExecutionProfileConfig`；runtime compatibility validator | CLI 按 locked target mode 选择 package-only 或 workspace-layered source，在首个 model prompt 前只加载一次并显式下传 minimum；非法 workspace profile fail closed，不回落 package |
| 交互步骤、EOF/SIGINT/确认 | `dayu.cli.commands.init` | 明确状态迁移与 exit mapping |
| managed tree / mode / rollback / repair | `dayu.cli.init_workspace` | snapshot、staging、publish、rollback、cleanup |
| provider availability verdict | `utils/smoke_cli_init_provider_matrix.py` 的 evidence classifier | 只分类真实 subprocess / trace，不改变产品语义 |

若 implementation 发现必须从 raw JSON、日志字符串、时间顺序或 CLI 自报 mode
反推上述任一事实，应停止 slice 并返回 plan review；不得加入 fallback。

## 6. Public contract、schema 与 state machine

### 6.1 CLI public contract

| Surface | Accepted | Rejected |
|---|---|---|
| init workspace | `init [--base/-b/--workspace] [--overwrite] [--reset]` | 任意位置的 `--config`，exit 2 |
| Agent model override | `--model ID`、`-m ID` | `--model-name`，exit 2 |
| default workspace | `./workspace` | 空白 `--base` 仍为 usage error 2 |

为同时保持非-init 命令的现有 global-option 位置语义，并让 init 不展示
`--config`：

1. 建立不含 `--config` 的 common parent；
2. 建立在 common parent 上增加 `--config` 的 runtime parent；
3. 顶层 parser 使用 runtime parent，维持 command 前参数；
4. init child 只使用 common parent，其余 child 使用 runtime parent；
5. `parse_cli_args(...)` 在 parse 后、返回 typed namespace 前，对
   `command_name=init && config_dir is not None` 调用同一 parser 的
   `error(...)`，因此 `--config path init` 也是 parser exit 2。

这属于 parser owner validation，不是 init runner 的兼容分支。

`ParsedCliArgs.model_name` 改名为 `model`；所有生产 consumer 同步迁移，不保留旧
attribute。

### 6.2 Model-family contract

新增 immutable runtime-neutral identity：

```text
ModelFamilyIdentity
  provider: str
  provider_model: str
  endpoint: str
  credential_ref: str | None
```

`model_family_identity(model: ModelConfig) -> ModelFamilyIdentity` 是唯一构造函数。
比较失败只报告 model ids 与 `mismatched_fields`，不得回显完整 endpoint query、
header 或 secret value。

同源不要求 `model_id` 相同，也不要求以下字段相同：

- `provider_request_extension`；
- `runtime_hints.runner_option_hints.*`；
- temperature / top-p / stream；
- scene runner-option hint id；
- ordinary / thinking catalog id。

同源必须要求 identity 的四个字段全部相同。

Service selection 顺序：

1. `primary_default_selection`：主 scene hints + execution run baseline，
   `run_override=None`；
2. `ordinary_selection`：同一输入 + invocation run override；
3. `compactor_selection`：compactor scene hints + compactor baseline，
   `run_override=None`；
4. 比较 `primary_default_selection.model` 与
   `compactor_selection.model` 的 family identity；
5. Host ordinary baseline 使用 `ordinary_selection`，Host compactor baseline
   使用 `compactor_selection`。

因此 invocation override 可以与 workspace default family 不同，但不会改变或触发
compactor family mismatch。

这项 runtime 校验不是对 init publication 的重复校验。PRESERVE 明确保留用户已有
manifest / profile 编辑，用户也可以在 init 后继续编辑 workspace，因此“init 当时
发布同源”不能承诺“实际运行时仍同源”。Service assembly 是 primary scene 与
compactor 两个 typed selection 首次汇合、且 Host 尚未打开的最早 owner boundary；
它必须使用无 invocation override 的 `primary_default_selection` 与
`compactor_selection` 比较，避免把单次 `--model` 误判为 durable drift。真实
workspace/package default 已漂移时，在创建 provider client 或打开 Host 前 fail
closed，不回写配置、不改选其它模型、不 fallback。

### 6.3 Config/schema decision

- 不新增 JSON 字段，不改变 ConfigLoader schema，不做 migration。
- `models.json` 的 provider catalog 保持完整；只修改 package defaults 的引用。
- 16 个 package manifests 的目标默认：
  - ordinary：`mimo-v2.5-pro-plan`；
  - thinking：`mimo-v2.5-pro-thinking-plan`；
  - `conversation_compaction`：`mimo-v2.5-pro-plan` +
    `conversation_compaction` hint。
- 四个 execution profiles 的 `run_baseline.model_id` 与
  `compactor_baseline.model_id` 均改为 `mimo-v2.5-pro-plan`，保证 scene hint
  缺失时的 package fallback 也不引入第二家 credential。
- runner hint ids、profile governance policy、compactor prompt 与 artifact path
  不变。
- Custom 默认 context 不再使用 131072 常量；从 target effective typed default
  execution profile 取得默认值。FIRST / OVERWRITE / RESET 的 target 是 package
  profile；PRESERVE 的 target 是 workspace layered profile，workspace 文件缺失才由
  loader 采用 package layer。当前 checked-in package snapshot 解析为 262144，但
  init 生产代码不得写该字面量。Ollama 用户输入也应用同一 target typed minimum。

### 6.4 Init interaction state machine

```text
RESOLVE_WORKSPACE
  -> RESET_CONFIRM?  -- Enter/No --> CANCELLED_SUCCESS(0)
                    -- invalid --> same prompt
                    -- EOF --> FAILURE(1)
                    -- SIGINT --> INTERRUPTED(130)
  -> ACQUIRE_LOCK
  -> RESOLVE_TARGET_EFFECTIVE_PROFILE
       -- FIRST/OVERWRITE/RESET --> package typed profile
       -- PRESERVE --> workspace layered typed profile
       -- missing workspace profile --> package layer
       -- invalid workspace profile --> FAILURE(1), advise --overwrite, no publication
       -- other ConfigLoadError --> FAILURE(1), no managed publication
  -> MODEL_CHOICE    -- recoverable error --> same prompt
  -> DYNAMIC_MODEL_NAME? -- recoverable error --> same prompt
  -> ENDPOINT?          -- recoverable error --> same prompt
  -> CONTEXT?           -- syntax/profile error --> same prompt
  -> REQUIRED_SECRET?   -- empty/forbidden value --> same hidden prompt
  -> OPTIONAL_SECRETS
  -> PERSIST_CONFIRM? -- Enter/No --> INCOMPLETE_FAILURE(1), no env write/publication
                     -- invalid --> same prompt
                     -- EOF --> INCOMPLETE_FAILURE(1), no env write/publication
                     -- SIGINT --> INTERRUPTED(130), no env write/publication
  -> PREPARE_STAGING
  -> PERSIST_ENV
  -> PUBLISH
  -> SUCCESS(0)
```

所有 `input()` / `getpass` EOF 统一转为 value-free
`CliInitOperationError`；`KeyboardInterrupt` 原样传播到 exit 130。recoverable
错误只捕获明确的 owner validation exception，不捕获 `OSError`、transaction
failure 或编程错误。

两处默认 No 的业务状态不同，退出码不得为追求表面对称而统一：

- RESET confirmation 的 No/Enter 是拒绝 destructive reset；原 workspace 仍是
  有效完成态，因此 `CANCELLED_SUCCESS(0)`。
- `PERSIST_CONFIRM` 只在 persistence batch 非空时出现，No/Enter 或 EOF 一律表示
  该批次未完成并退出 1；其中 batch 包含所选 provider 缺失的 required secret 时，
  provider init 前置条件明确未完成，本次 init 必须报告
  `INCOMPLETE_FAILURE(1)`。已有 workspace root / lock 不等于 publication；
  config / `.dayu`、environment profile/setx 都保持未写。SIGINT 固定为 130。

### 6.5 Workspace mode / repair state machine

| Public state | 无 flag | `--overwrite` | `--reset` confirmed |
|---|---|---|---|
| config absent | FIRST；建完整 config | OVERWRITE；建完整 config | RESET；清 `.dayu` 后建 config |
| config ordinary directory | PRESERVE | whole-tree replace config | replace `.dayu` + config |
| config ordinary file | 安全拒绝 | no-follow backup 后 whole-tree replace | no-follow backup 后 replace |
| corrupt JSON/schema | PRESERVE 明确要求 overwrite | whole-tree rebuild | whole-tree rebuild + `.dayu` reset |
| `.dayu` ordinary file | 安全拒绝 | 安全拒绝（overwrite 不拥有它） | no-follow backup 后删除 |
| symlink/dangling/reparse/special | 所有 mode 安全拒绝 | 安全拒绝 | 安全拒绝 |

PRESERVE 的调用级顺序固定为：

1. 显式调用
   `shutil.copytree(public_config, staged_config_root, symlinks=True,
   ignore_dangling_symlinks=False)` 把用户 config 复制到 staged config，保留用户
   额外内容及 symlink/dangling symlink 的原始 shape；不得使用默认
   `symlinks=False` follow symlink，也不得把 workspace 外部目标内容复制成 staged
   regular file；
2. 按 `config_file_names()` 顺序对每个 staged root config 做 no-follow existence /
   shape 检查；只有路径确实缺失时才从 package 复制对应文件 bytes，已有 regular
   file 零改写，symlink/dangling/special 不当作“缺失”覆盖；
3. 再补 package prompt ordinary files，仍只补缺失项；
4. 最后只修改 init catalog 拥有的 model records 与 16 个 known manifest
   `default_model_id` owner 字段；
5. 运行完整 staging validation。已有非法文件不宽松解析、不覆盖、不删除，失败时
   明确提示 `--overwrite`。

在同一模块新增仅供该 owner 使用的 `_PrivatePathShape(StrEnum)`，值域精确为
`REGULAR_FILE="regular_file"` 与
`ORDINARY_DIRECTORY="ordinary_directory"`；扩展现有
`_cleanup_private_path(path: Path, *, expected_identity: PathIdentity,
expected_shape: _PrivatePathShape, private_parent: Path, platform_system: str,
stage: str) -> None`。调用方必须从创建记录或 locked snapshot 传入 expected identity
与 expected shape，不得从 cleanup 时的 actual path 反推，也不得在调用方分叉复制
安全协议。expected shape 的产生、actual shape lock 与 quarantine 后 shape recheck
都只能读取同一次对应 no-follow identity/stat 结果的 `PathIdentity.mode`，分别通过
`stat.S_ISREG(mode)` / `stat.S_ISDIR(mode)` 判定；不得使用
`Path.is_file()`、`Path.is_dir()` 或任何 follow-symlink API。owner 内的固定
dispatch 顺序为：

1. direct-child containment；
2. no-follow actual identity 读取并与 expected identity 精确锁定；
3. 从 actual no-follow identity 的 mode 通过 `stat.S_ISREG` /
   `stat.S_ISDIR` 得到 actual shape，并与 typed expected shape 精确匹配；
   symlink（包括指向 regular file/directory 的 symlink）、reparse、special fail
   closed；
4. `os.replace` 到 same-parent quarantine；
5. 对 quarantine 再做 identity/shape lock，并确认原名 no-follow absent；
6. 按 expected shape 分派：

- `REGULAR_FILE`：在 quarantine identity/shape recheck 后执行
  `os.unlink(quarantine)`；unlink 本身不跟随目标，不使用 `missing_ok`；
- `ORDINARY_DIRECTORY`：执行现有 POSIX
  `shutil.rmtree.avoids_symlink_attacks is True` capability gate / 非 POSIX ordinary
  tree validation，再走现有 fd-safe recursive delete；
- identity/type 漂移或 capability 缺失：fail closed，报告 retained truth。

transaction container、staged config 与 directory backup 显式传
`ORDINARY_DIRECTORY`；由 ordinary managed-root 产生的 file backup 显式传
`REGULAR_FILE`。不得新增第二套 mutation helper，也不得用
`unlink(missing_ok=True)` 掩盖 identity 漂移。

## 7. 受影响文件

### 7.1 生产代码 / config

- `dayu/cli/arg_parsing.py`
- `dayu/cli/session_execution.py`
- `dayu/cli/commands/init.py`
- `dayu/cli/init_catalog.py`
- `dayu/cli/init_workspace.py`
- `dayu/runtime/assembly.py`
- `dayu/service/host_assembly.py`
- `dayu/config/execution_profiles.json`
- `dayu/config/prompts/manifests/conversation_compaction.json`

不计划修改 `dayu/config/models.json`：当前 15 choices 的 static pair 已满足 family
identity，dynamic record 由 init catalog owner 生成。

### 7.2 Tests

- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_session_command.py`
- `tests/cli/test_init_command.py`
- `tests/cli/test_init_catalog.py`
- `tests/cli/test_init_workspace.py`
- `tests/cli/test_init_smoke.py`
- `tests/runtime/test_assembly_helpers.py`
- `tests/runtime/test_config_loader.py`
- `tests/service/test_host_assembly.py`
- 新增 `tests/cli/test_smoke_cli_init_provider_matrix.py`

### 7.3 Validation assets / docs

- 新增 `utils/smoke_cli_init_provider_matrix.py`
- 新增 `docs/cli_init_workspace_manifest_v1.json`
- `docs/cli_ci.md`
- `README.md`
- `dayu/config/README.md`
- `dayu/service/README.md`
- `tests/README.md`

明确不修改：

- `docs/reviews/wu-cli-init-01-goal-confirmation-controller.md`
- `docs/cli_ci_oracles.json`
- `dayu/README.md`
- Host / Engine / Fins README 与代码

## 8. 实现决策

1. parser 通过 common/runtime 两种 parent 解决 init-specific surface，不在 runner
   忽略 `--config`。
2. 删除 internal `model_name` CLI 字段，使用 `model`；provider config 内的
   `ModelConfig.model` 与 dynamic settings 的 `model_name` 不改名，因为它们表达
   provider model，不是 CLI option。
3. model family 是 resolved typed fact，不比较 raw `extends`、model id 命名、
   choice id 或 provider extension。
4. package scene 与 profile fallback 都统一到 Mimo Token Plan family，避免 dormant
   fallback 重新引入 DeepSeek credential。
5. Service 对 primary default 与 invocation effective selection 分开求值；这是保证
   `--model` 不污染 compactor 的最小必要状态，不把 override 复制给 compactor。
6. field-level dynamic validators 留在 init catalog，CLI 重试逻辑不复制 URL/schema
   规则。
7. target effective profile minimum 只通过
   `ConfigLoader.load_execution_profiles(...)` 的 typed default profile 读取一次并
   显式下传：FIRST / OVERWRITE / RESET 使用 package-only source，PRESERVE 使用真实
   workspace config dir 的 layered source，缺失 workspace profile 才取得 package
   layer；非法 workspace profile fail closed 并提示 `--overwrite`，不硬编码
   262144，不从 catalog/raw JSON 重算，也不 fallback 掩盖损坏。
8. PRESERVE 扩展为补齐全部 package managed files，不改写已存在文件；模型 projection
   仍只写 owner 字段。
9. destructive repair 只扩大 existing transaction 对 ordinary root file 的支持，
   不降低 symlink/reparse/special-file 防线。
10. provider smoke 使用真实 `dayu-cli init`、真实 `dayu-cli prompt`、真实 Host
    durable trace / runner-input projection；unit test doubles只测试 harness 自身，
    不计为 real matrix pass。

## 9. Implementation slices

### S1 — CLI public parser contract

- objective：移除 init `--config` 与 `--model-name`，建立正式 `--model/-m`。
- expected outcome：两种位置的 init config 都 exit 2；三个 Agent surfaces 使用新
  参数并映射同一个 `ServiceAssemblyOverrides.model_id`。
- allowed files：
  - `dayu/cli/arg_parsing.py`
  - `dayu/cli/session_execution.py`
  - `tests/cli/test_arg_parsing.py`
  - `tests/cli/test_prompt_command.py`
  - `tests/cli/test_interactive_command.py`
  - `tests/cli/test_session_command.py`
- prerequisites：None。
- exact changes：
  1. common/runtime parser parents；
  2. init post-parse parser rejection for pre-command `--config`；
  3. `ParsedCliArgs.model` 与 namespace default；
  4. `_add_agent_execution_arguments` 注册 `--model/-m`；
  5. `session_execution` 改读 `args.model`，错误字段名改为 `--model`；
  6. 更新所有 command conversion assertions。
- call path：
  `argv -> parse_cli_args -> ParsedCliArgs.model -> _prepare_session_runtime ->
  ServiceAssemblyOverrides.model_id`。
- invariants：
  - 非-init 的 `--config` 在 command 前/后仍可用；
  - `-m` 行为不变；
  - 不保留旧 attribute/alias。
- non-goals：不改变 Service override 结构或 Host API。
- tests：
  - init help absence；
  - init `--config` command 前/后两种位置均由 parser exit 2；
  - 对 `prompt`、`interactive`、`session resume` 参数化覆盖 `--config <path>`
    位于 command 前与 command 后的六个正向 case，全部成功 parse，并断言
    `ParsedCliArgs.config_dir` 精确等于输入 path；
  - prompt/interactive/session resume help 与 long/short form；
  - `--model-name` exit 2；
  - conversion 精确为 model id。
- validation：
  `pytest tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py
  tests/cli/test_interactive_command.py tests/cli/test_session_command.py -q`
- completion signal：无生产/测试 `args.model_name` 或公开 `--model-name` 残留。
- stop condition：argparse 无法同时保持非-init command-before option 语义时返回 plan
  review，不在 runner 加 shim。

### S2 — Model family owner 与 init interaction state machine

- objective：建立 resolved family contract，并使所有 recoverable input 原地重试，
  context 与本次 target effective typed profile 内部兼容。
- expected outcome：catalog pair、dynamic inputs、EOF/SIGINT/confirmation contract
  全部 owner-level 可测。
- allowed files：
  - `dayu/runtime/assembly.py`
  - `dayu/cli/init_catalog.py`
  - `dayu/cli/commands/init.py`
  - `tests/runtime/test_assembly_helpers.py`
  - `tests/cli/test_init_catalog.py`
  - `tests/cli/test_init_command.py`
- prerequisites：S1。
- exact changes：
  1. 新增 `ModelFamilyIdentity` 与唯一 typed constructor；
  2. catalog 对每个 choice 的 ordinary/thinking resolved identity 做四字段等值校验；
  3. init catalog 暴露 model-name / endpoint owner validators，settings dataclass 与
     UI step 复用；
  4. 在 `run_init_command(...)` 已取得 lock、复核 locked snapshot、确定 target
     mode 后且调用 `_select_model(...)` / 输出首个 model-choice prompt 前，只调用
     一次 `ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT)` 的
     `load_execution_profiles(...)`：FIRST / OVERWRITE / confirmed RESET 传
     `workspace_config_dir=None`；PRESERVE 传真实 workspace config dir，复用 loader
     的 typed layering，文件缺失时取得 package layer，文件存在但非法时 fail closed
     并提示 `--overwrite`，不得以 `None` 重试；用返回对象的
     `default_execution_profile_id` 索引 target typed profile，取得
     `min_context_window_tokens`，以普通显式参数传给 `_select_model` 与 context
     reader；不扩展 `validate_init_catalog(...)`、不增加新 loader API 或 loose JSON
     read；
  5. choice、model name、endpoint、context、required/optional secret、confirm 使用
     明确 loop；
  6. `_confirm` 区分 empty line 与 EOF；reset 与 persistence confirmation 按各自
     业务完成态映射退出码；
  7. context reader 要求 positive 且不小于 target effective typed profile
     minimum；
  8. errors 只输出 field rule / env name，不输出 secret、authorization、endpoint
     query。
- data flow：
  `locked target mode -> workspace_config_dir(None | real workspace config dir) ->
  ConfigLoader.load_execution_profiles(...) ->
  ExecutionProfilesConfig.default_execution_profile_id -> target typed
  ExecutionProfileConfig.min_context_window_tokens -> explicit parameter -> field reader ->
  InitModelSelection -> staging`；
  `ModelsConfig pair -> model_family_identity -> catalog validation`。
- fail-closed boundary：
  - `ConfigLoadError` 只在上述 CLI adapter 调用点转换为 value-free
    `CliInitOperationError`；
  - package-only source 或 PRESERVE 缺失 workspace profile 后的 package-layer
    failure，只说明 package execution profile 配置无效、异常类型以及
    reinstall/repair package config 的动作；PRESERVE 已存在 workspace profile 的
    typed load failure 只说明 workspace execution profile 无效并提示
    `rerun with --overwrite`；两类 diagnostic 都不拼接原异常文本、原始值或完整路径；
  - exit 1；不进入 model/secret prompt、transaction prepare、environment
    persistence 或 managed-root publication；
  - workspace profile 缺失只走 ConfigLoader 的 package layering；workspace profile
    存在但非法时不得重试 package-only load；
  - 不使用 262144 fallback，不自动选其它 profile；其它 `OSError` / programming
    error 不伪装成可重试输入。
- invariants：
  - provider extension / runner hint 差异不导致 family mismatch；
  - endpoint/model/ref 差异必然 fail closed；
  - unexpected `OSError` 不进入 retry loop；
  - EOF 永不被转换成 No。
- non-goals：不联网、不自动换 profile、不修改 ConfigLoader schema。
- tests：
  - 每个 family identity 字段 mismatch；
  - extension / hint 差异允许；
  - current 15 choices 通过；
  - invalid choice 后 valid；
  - invalid endpoint/context/model name 后 valid；
  - 按 FIRST / OVERWRITE / confirmed RESET 参数化证明 package typed default
    profile minimum 被精确下传；即使 destructive mode 面对已有 workspace profile，
    source 仍是 `workspace_config_dir=None`；
  - PRESERVE 的 workspace layered typed default profile minimum 被精确下传；
    workspace minimum 高于 package minimum 时，Custom/Ollama 较低 context 在原
    context 步骤重试，随后输入满足 workspace minimum 的值可继续；
  - PRESERVE 缺失 `execution_profiles.json` 时通过 loader package layer 取得 package
    minimum，不把缺失误报为损坏；
  - PRESERVE 存在但 malformed/schema-invalid/default-id-invalid workspace profile
    时通过唯一 typed API fail closed：exit 1、提示 `--overwrite`、诊断脱敏、
    package-only fallback 未发生、model/secret prompt 未发生、config / `.dayu`
    digest 不变；
  - malformed/missing/default-id-invalid package execution profile 在 package source
    下 fail closed：exit 1、诊断脱敏且可操作、model/secret prompt 未发生、
    config / `.dayu` 零 publication，且没有 262144 fallback；
  - required secret empty/control 后重试，输出无 value；
  - confirm invalid 后重试；
  - reset Enter/No=0、EOF=1、SIGINT=130；
  - required secret persistence batch 的 No/Enter=1、EOF=1、SIGINT=130，均断言
    init 未完成、环境值未写且 config / `.dayu` 零 publication；
  - 每个失败路径 public config/.dayu absent或 digest 不变。
- existing test migration：
  - 保留
    `test_reset_default_no_has_zero_bootstrap_or_managed_mutation` 的 `"n"` / `""`
    两个 `EXIT_SUCCESS` 断言不变；
  - 拆分或重命名
    `test_reset_eof_and_interrupt_have_zero_mutation`：EOF 分支从
    `EXIT_SUCCESS` 迁移为 `EXIT_FAILURE`，SIGINT 分支保持
    `EXIT_KEYBOARD_INTERRUPT`，两者仍断言零 managed-root mutation；
  - 保留
    `test_required_secret_refusal_stops_before_transaction_publication` 的
    `EXIT_FAILURE` owner contract，并扩展 Enter、EOF、SIGINT 与 env/config/
    `.dayu` 零写入断言；不得为旧 EOF=0 偶然行为增加兼容分支。
- validation：
  `pytest tests/runtime/test_assembly_helpers.py
  tests/cli/test_init_catalog.py tests/cli/test_init_command.py -q`
- completion signal：任一 mode 的 init 都无法构造低于其 target effective typed
  default profile minimum 的 dynamic record；PRESERVE 不会用 package minimum
  掩盖更高或非法的 workspace minimum。
- stop condition：若 family identity 需要 Host/Engine 或 raw provider payload 才能判定，
  停止并升级 owner question。

### S3 — Package defaults 与 Service compactor assembly

- objective：使 package / workspace compactor 与主 scene default family 同源，同时
  保持 invocation override isolation。
- expected outcome：未 init 只需 Mimo Token Plan credential；init 后每个 choice family
  一致；`--model` 不改变 compactor。
- allowed files：
  - `dayu/config/execution_profiles.json`
  - `dayu/config/prompts/manifests/conversation_compaction.json`
  - `dayu/service/host_assembly.py`
  - `tests/runtime/test_config_loader.py`
  - `tests/service/test_host_assembly.py`
  - `tests/cli/test_init_catalog.py`
- prerequisites：S2。
- pre-change DeepSeek reference inventory：
  - implementation 开始前运行并把完整输出记录到 S3 artifact：
    `rg -n 'deepseek-v4-flash' dayu tests utils README.md docs/cli_ci.md`；
  - **package-default owner / 偶然默认断言，必须迁移**：
    - `dayu/config/execution_profiles.json:8,12,94,98,180,184,266,270`：四个
      profile 的 run / compactor baseline owner；
    - `dayu/config/prompts/manifests/conversation_compaction.json:11`：package
      compactor scene default owner；
    - `tests/service/test_host_assembly.py:2615`：对上述旧 compactor package
      baseline 的偶然断言；改为新 Mimo owner assertion；
  - **显式 DeepSeek catalog / provider-specific production asset，必须保留**：
    - `dayu/config/models.json:3,6,70,71`；
    - `dayu/cli/init_catalog.py:138,139`；
    - `utils/smoke_async_agent_providers.py:161,165`；
    - `dayu/config/README.md:349,352` 的 DeepSeek catalog 示例；
  - **显式 DeepSeek 测试 fixture / provider contract，禁止机械替换**：
    - `tests/engine/test_provider_extension_config_adapter.py:104`；
    - `tests/engine/test_config_models.py:30,41,42`；
    - `tests/engine/test_smoke_async_agent_providers.py:156`；
    - `tests/runtime/test_assembly_helpers.py:73,108,122,320,328,338`；
    - `tests/runtime/test_config_loader.py:400`；
    - `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py:97`；
    - `tests/runtime/test_smoke_host_public_multiturn_assembly.py:38`；
    - `tests/service/test_entrypoint_runtime.py:108`；
    - `tests/service/test_entrypoint_runtime_interactive_path.py:44`；
    - `tests/service/test_entrypoint_runtime_prompt_path.py:50`；
    - `tests/service/test_host_assembly.py:117,2764`；
    - `tests/cli/test_interactive_command.py:87`、
      `tests/cli/test_prompt_command.py:109`、
      `tests/cli/test_init_catalog.py:239`；
    - `tests/cli/test_transient_delivery_interruption_path.py:301`；
    - `tests/host/public_smoke_support.py:782`；
    - `tests/tools/test_combined_tools_acceptance.py:387,539`。
  - 对最后一类只在新 runtime family owner check 暴露 fixture 内部 drift 时，调整该
    fixture 的 scene/profile 关系使测试意图自足；保留显式 DeepSeek provider 选择，
    不批量换成 Mimo。literal inventory 之外的隐式默认依赖由 focused + full test
    捕获，发现后按同一分类规则记录，不能凭测试失败机械替换。
- exact changes：
  1. package compactor manifest 改为 ordinary Mimo Token Plan id；
  2. 四 profiles 的 run / compactor baseline model id 改为 ordinary Mimo Token
     Plan id；
  3. Service 求值 primary default、main effective、compactor effective 三个
     selections；
  4. compactor 传入 `_prepare_compactor_scene_inputs(...)` 的 model hints，
     `run_override=None`；
  5. primary default 与 compactor family identity mismatch 时，在构造 Host options
     前 fail closed；
  6. Host options/diagnostics 继续使用现有 ordinary/compactor selection，不新增
     durable/public schema。
- state transitions：无 Host state change；全部在 open-host options construction
  前完成。
- invariants：
  - main override 可跨 family；
  - compactor 永远不用 invocation override；
  - compactor hint id 保持 `conversation_compaction`；
  - temperature/stream 保持 compactor hint 值；
  - family error 不展示 endpoint 或 credential value。
- runtime owner necessity：
  - init/PRESERVE 允许保留用户编辑，init 后也可能发生 manifest/profile 手工修改，
    因此 publication-time 同源不能替代 runtime check；
  - `primary_default_selection` 不带 invocation override，代表 durable
    workspace/package primary truth；`ordinary_selection` 才消费本次 `--model`；
  - Service assembly 是 primary/compactor typed selection 汇合且 Host 未打开的
    最早边界；mismatch 在这里 exit/fail closed，不 fallback、不回写、不把 invocation
    override 当 drift。
- non-goals：不删除 DeepSeek catalog，不把 compactor RunnerSpec 合并为 ordinary
  RunnerSpec，不修改 Host compaction lifecycle。
- tests：
  - package 16 manifests + 8 baseline refs family 全等；
  - package fallback assembly ordinary / compactor provider/model/endpoint/ref 全等；
  - 每个 static init pair / compactor projection family 全等；
  - no override 主 selection 使用 scene hint；
  - cross-family run override 只改变 ordinary selection；
  - compactor temperature/stream/hint 保持；
  - intentionally mismatched compactor manifest fail closed；
  -只提供 MIMO_PLAN_API_KEY 可完成 package assembly，不读取 DEEPSEEK_API_KEY。
- validation：
  `pytest tests/runtime/test_config_loader.py
  tests/service/test_host_assembly.py tests/cli/test_init_catalog.py -q`
- completion signal：package 与 workspace 两条 assembly 都没有 second credential
  requirement。
- stop condition：若 mismatch 只能在 Host 已打开后发现，停止；不得把校验放到 Host
  lifecycle。

### S4 — Managed whole-tree modes 与 repair

- objective：补齐 PRESERVE managed files，并在不降低路径安全的前提下支持显式
  ordinary-root repair。
- expected outcome：四态与 partial/corrupt matrix 完整，rollback 保持原始 truth。
- allowed files：
  - `dayu/cli/init_workspace.py`
  - `tests/cli/test_init_workspace.py`
  - `tests/cli/test_init_smoke.py`
- prerequisites：S2、S3。
- exact changes：
  1. PRESERVE 显式以
     `shutil.copytree(..., symlinks=True, ignore_dangling_symlinks=False)` 把用户
     config 复制到 staged config，禁止 dereference；随后逐个检查
     `staged_config_root / config_file_names()[i]` 的 no-follow shape，只从 package
     复制真正缺失的五个 root config，再补缺失 prompt，最后才应用 model/manifest
     owner 字段；
  2. 缺失文件 copy 保持 package bytes；已有 root config / prompt 内容零改写，
     dangling symlink 或 special file 不当作缺失覆盖，交给 validation fail closed；
  3. snapshot 接受明确 destructive mode，只允许该 mode 拥有的 root 为 ordinary
     regular file；
  4. snapshot digest 支持 ordinary file；symlink/reparse/special 仍拒绝；
  5. 给现有 `_cleanup_private_path(...)` 增加 typed expected shape；helper 内统一执行
     containment -> identity lock -> shape lock -> same-parent quarantine ->
     quarantine identity/shape recheck -> no-follow unlink 或 fd-safe recursive-delete
     dispatch；expected、actual、quarantine 三处 shape 都只从各自同一次 no-follow
     identity/stat 的 `mode` 通过 `stat.S_ISREG` / `stat.S_ISDIR` 判定，禁止
     `Path.is_file()` / `Path.is_dir()`；所有调用方只传创建/snapshot owner 记录的
     identity 与 shape；
  6. preserve validation failure 输出 `rerun with --overwrite` 的可操作诊断；
  7. overwrite/reset publication 与 rollback 复用现有 backup records。
- exact ownership：
  - overwrite 可替换 config regular file，不可替换 `.dayu` regular file；
  - reset 可替换 config / `.dayu` regular file；
  - no flag 不可替换 regular managed root。
- non-goals：不自动 repair nested symlink/special file，不解析 `.dayu` 内容。
- cleanup call-shape matrix：
  - transaction container / staged config / directory backup：
    `ORDINARY_DIRECTORY`；
  - config regular-file backup（overwrite/reset）与 `.dayu` regular-file backup
    （reset only）：`REGULAR_FILE`；
  - 调用方不得直接 unlink/rmtree、不得复制 quarantine/identity 协议、不得按 actual
    shape 选择分支；不新增第二个 cleanup helper。
- tests：
  - 每个根配置文件单独缺失时从 package 补齐且 bytes 精确相同；已存在 root config
    bytes 零改写；root config dangling/special 不被补齐逻辑覆盖；
  - 用户 config 内指向 workspace 外部 regular file 的 symlink 经 copytree 后在
    staged tree 仍是 symlink shape，外部目标 bytes 未被复制成 regular file，随后
    no-follow validation fail closed；dangling symlink 同样保留 shape 并失败；
  - prompt 文件与空目录 partial；
  - corrupt JSON preserve fail + overwrite success；
  - config regular file no flag/overwrite/reset；
  - `.dayu` regular file overwrite reject/reset success；
  - root/nested symlink、dangling、FIFO/reparse 全 mode reject；
  - overwrite extra file/dir/sentinel 消失且 `.dayu` identity 保留；
  - reset `.dayu`/config 消失重建，portfolio/assets identity 保留；
  - each backup / publish / fsync fault rollback 原 digest；
  - regular-file 与 ordinary-directory cleanup 分别经过同一 helper；expected shape
    mismatch、quarantine 前后 identity/type drift、unlink/rmtree/capability fault
    均 fail closed 并报告 retained truth；
  - quarantine recheck 中 symlink-to-regular-file 与 symlink-to-directory 的
    no-follow mode 都不满足 `stat.S_ISREG` / `stat.S_ISDIR` expected shape，证明
    cleanup 不会 follow target；
  - repair 后 ConfigLoader + 13 production scene validation。
- validation：
  `pytest tests/cli/test_init_workspace.py tests/cli/test_init_smoke.py -q`
- completion signal：每个 mode verdict 由 tree path、bytes、digest、identity 断言，不仅
  由 `result.mode`。
- stop condition：平台缺少 no-follow / fd-safe capability 时 fail closed，不增加
  unsafe fallback。

### S5 — Versioned publication manifest 与 15-row real provider matrix

- objective：建立 accepted oracle 要求的真实、脱敏、可复核 evidence。
- expected outcome：15 choices 全覆盖；外部不可用正确分类；内部不兼容 hard fail。
- allowed files：
  - `utils/smoke_cli_init_provider_matrix.py`
  - `tests/cli/test_smoke_cli_init_provider_matrix.py`
  - `docs/cli_init_workspace_manifest_v1.json`
  - `docs/cli_ci.md`
- prerequisites：S1-S4。
- exact changes：
  1. checked-in versioned manifest 固定 oracle id/version、5 dirs、43 files、全部
     relative paths、package-source digests、16 个 model projection owner paths；
     它是用户已确认行为的 immutable expected snapshot，不是从本次 actual tree
     派生的 cache；
  2. smoke 每 row 使用 fresh workspace/home，不写用户真实 profile；
  3. required key 已在 process env 时，init 不重新收集、不写入 init-owned
     workspace 配置；Host SQLite 的 durable execution snapshot 可以持久化 runtime
     已解析的 credential value；缺 key 时以 secret EOF/拒绝路径验证无 publication；
  4.成功 init 后运行真实 `dayu-cli prompt`，并以同一配置调用 production
     entrypoint assembly 取得 effective ordinary/compactor typed identity；
  5.从真实 Host tool-trace / runner-input projection 读取 run/request/manifest
     identity与 provider request observation，不直接把 ConfigLoader success 当请求；
  6. 对 response 只保存 terminal status、bounded preview、length、SHA-256 与 marker；
  7. endpoint identity 去 userinfo/query/fragment，仅保存 scheme、hostname、port、
     path digest；
  8. evidence 写入
     `workspace/tmp/wu-cli-init-01/<run-id>/matrix-report.json`；
  9. 全 report 做 secret canary / authorization / credential value scan；raw Host
     SQLite 中的 exact credential 命中只计为 accepted observation，report、config、
     log、Tool Trace 或其它 durable evidence 中的命中仍是 violation；secret canary
     在任何位置命中均失败。
- manifest validation boundary：
  - 正常 deterministic test、正常 smoke 与 live matrix 只读
    `docs/cli_init_workspace_manifest_v1.json`；独立遍历实际 publication tree、独立计算
    count/path/digest/model projection，再与 frozen expected snapshot 比较；
  - 禁止正常路径从 actual/package current tree 动态生成 expected 后在同一 run
    自比，禁止 mismatch 时自动更新 checked-in manifest，禁止把 count/path/digest
    放宽为只验目录存在；
  - expected 缺失、actual 多/少路径、digest 或 owner projection mismatch 都归类为
    `internal_product_bug` 并使 smoke 非零；
  - 本 slice 不提供 manifest generator。若未来增加 maintenance-only candidate
    generation，只能显式输出到 `workspace/tmp/` 的新 candidate path，不得覆盖
    checked-in v1、不得参与同一 run 的 pass 判定；candidate 必须经新
    oracle/scenario version、人工 diff review 与用户确认后，才可作为新冻结版本
    checked in。
- non-goals：不在默认 pytest 中调用公网；unit tests 只验证 classifier、schema、
  redaction、no-fallback assertions，不能签发 real pass。
- validation：
  - deterministic：
    `pytest tests/cli/test_smoke_cli_init_provider_matrix.py -q`
  - live：
    `python utils/smoke_cli_init_provider_matrix.py --oracle-version 1`
- completion signal：每 row 有 final availability class、request attempted truth、
  effective identity、trace identity、terminal outcome、no-fallback verdict。
- manifest tests：
  - frozen manifest 与独立 actual tree 精确匹配可通过；
  - actual 新增/删除/篡改文件或 model owner projection 均失败；
  - harness 不存在从 actual 生成 expected 的 normal-mode call path；
  - checked-in manifest 在 deterministic/live validation 前后 digest 不变。
- stop condition：
  - 任一 row 未分类；
  - internal incompatibility；
  - disallowed secret scan failure（不包括已接受的 Host SQLite credential
    observation）；
  - fallback observed；
  - credential/provider 可用却没有真实 response；
  均阻止 slice pass。

### S6 — README、aggregate validation 与 handoff

- objective：同步当前用户/开发者文档并形成 implementation completion evidence。
- allowed files：
  - `README.md`
  - `dayu/config/README.md`
  - `dayu/service/README.md`
  - `tests/README.md`
  - 当前 slice implementation artifact
- prerequisites：S1-S5。
- exact changes：
  - root README：init 无 `--config`、`--model/-m`、四态 repair、EOF/exit、compactor
    单 family；
  - config README：PRESERVE 补全部 managed files、package family defaults、dynamic
    target effective profile context minimum；
  - Service README：primary default / invocation override / compactor selection 边界；
  - tests README：focused commands、versioned manifest、real smoke 不属于默认 pytest。
- validation：见第 12 节。
- completion signal：文档只描述已实现行为，无 future tense / work-unit 术语。
- stop condition：任何测试、pyright、diff check 或 matrix internal-bug verdict 未通过。

## 10. Provider availability classification

### 10.1 封闭分类

每个 matrix row 必须同时记录：

`preflight_class`：

- `requestable`：credential ref 有非空值，dynamic endpoint/model 已明确，或 provider
  不需要 credential；
- `credential_missing`：required env 缺失；
- `endpoint_unconfigured`：Custom model/endpoint 未显式提供。

`availability_class`：

- `available`：真实请求发出并得到成功 provider response；
- `credential_missing`：init secret EOF/拒绝，exit 1，零 publication；
- `endpoint_unconfigured`：明确非零、零请求；
- `service_unreachable`：DNS/connect/timeout 等真实 transport failure；
- `provider_rejected`：鉴权、模型不存在或其它 provider 4xx/5xx 拒绝；
- `rate_limited`：provider 明确限流；
- `internal_product_bug`：schema/profile/context/model/family/assembly/trace contract
  失败。

`internal_product_bug` 永远不是可接受 unavailable；它使 matrix 整体 fail。
`available` 必须有 response；其它外部分支必须非零、bounded、脱敏且
`fallback_observed=false`。

### 10.2 Plan-time environment snapshot

以下只表示 2026-07-30 plan 时的候选前置状态，不替代 implementation 后的真实
verdict：

| Choice | Provider | Required ref / endpoint | Plan-time preflight |
|---|---|---|---|
| `mimo-token-plan` | Mimo | `MIMO_PLAN_API_KEY` | requestable（ref set） |
| `mimo-sg` | Mimo | `MIMO_PLAN_SG_API_KEY` | credential_missing |
| `mimo-pro` | Mimo | `MIMO_API_KEY` | requestable（ref set） |
| `deepseek-pro` | DeepSeek | `DEEPSEEK_API_KEY` | requestable（ref set） |
| `deepseek-flash` | DeepSeek | `DEEPSEEK_API_KEY` | requestable（ref set） |
| `openai` | OpenAI | `OPENAI_API_KEY` | credential_missing |
| `anthropic` | Anthropic | `ANTHROPIC_API_KEY` | credential_missing |
| `gemini-2.5-flash` | Gemini | `GEMINI_API_KEY` | requestable（ref set） |
| `gemini-2.5-pro` | Gemini | `GEMINI_API_KEY` | requestable（ref set） |
| `gemini-2.5-flash-lite` | Gemini | `GEMINI_API_KEY` | requestable（ref set） |
| `gemini-3.1-pro-preview` | Gemini | `GEMINI_API_KEY` | requestable（ref set） |
| `gemini-3.1-flash-lite-preview` | Gemini | `GEMINI_API_KEY` | requestable（ref set） |
| `qwen-plus` | Qwen | `QWEN_API_KEY` | requestable（ref set） |
| `ollama` | Ollama | localhost service | requestable（`/v1/models` HTTP 200） |
| `custom-openai` | Custom | key set；model/endpoint 未给 | endpoint_unconfigured |

不得在 report 中写 env value、authorization header、完整 custom query 或 shell
profile 内容。

## 11. 真实 prompt matrix

### 11.1 Mandatory rows

| Row | Workspace | Invocation | 必须证明 |
|---|---|---|---|
| `P00` | 无 config | real `prompt` | package default Mimo family、真实 response 或正确外部 failure、ordinary/compactor family 同源 |
| `P01` | init `mimo-token-plan` | real prompt | thinking default；ordinary projection 与 compactor family proof |
| `P02` | init `mimo-sg` | real prompt 或 secret EOF | availability classification |
| `P03` | init `mimo-pro` | real prompt | 同上 |
| `P04` | init `deepseek-pro` | real prompt | 同上 |
| `P05` | init `deepseek-flash` | real prompt | 同上 |
| `P06` | init `openai` | real prompt 或 secret EOF | 同上 |
| `P07` | init `anthropic` | real prompt 或 secret EOF | 同上 |
| `P08` | init `gemini-2.5-flash` | real prompt | 同上 |
| `P09` | init `gemini-2.5-pro` | real prompt | 同上 |
| `P10` | init `gemini-2.5-flash-lite` | real prompt | 同上 |
| `P11` | init `gemini-3.1-pro-preview` | real prompt | 同上 |
| `P12` | init `gemini-3.1-flash-lite-preview` | real prompt | 同上 |
| `P13` | init `qwen-plus` | real prompt | 同上 |
| `P14` | init `ollama` | real prompt | ordinary/thinking 同 id 可共享一次请求 |
| `P15` | init `custom-openai` | real prompt 或 endpoint-unconfigured | dynamic family/context 与 availability |
| `P16` | 任一 available workspace | `prompt --model/-m <different-family-id>` | 本 Run main effective 改变，compactor identity 不变 |
| `P17` | P16 同 workspace | 后续无 override prompt | 恢复 workspace default，workspace config digest 不变 |

每个 static choice 的 ordinary / thinking provider model id 若相同，可共享一次真实
provider request，但必须分别用 manifest / assembly evidence 证明 scene 投影。若实际
provider model 不同，则两个角色分别发真实请求。Ollama / Custom 同 model id 可共享。

### 11.2 Per-row evidence schema

每 row 至少包含：

- `scenario_id`、`choice_id`、`role_coverage`；
- `preflight_class`、`availability_class`；
- expected / effective config model id；
- resolved provider 与 provider model；
- redacted endpoint identity；
- credential ref name（无 value）；
- init exit、prompt exit；
- request attempted bool；
- client correlation / provider request id presence；
- Host run id、runner-call manifest event/ref/digest、input projection digest；
- terminal status；
- bounded response or diagnostic `{length, sha256, preview}`；
- before/after workspace managed-tree digest；
- `fallback_observed` 与用于判定的 observed provider/model set；
- secret scan result，以及不含 value/path 的 Host SQLite accepted observation count。

No-fallback 判定不能只看最终回答。至少同时要求：

1. Service typed effective identity 等于 expected；
2. runner input / trace 绑定同一 run；
3. observed provider/model set 不含其它 family；
4. failure terminal 后没有成功 terminal from alternate family。

## 12. Tests 与验证命令

所有命令先执行：

```bash
source .venv/bin/activate
```

Focused tests：

```bash
pytest tests/cli/test_arg_parsing.py \
  tests/cli/test_prompt_command.py \
  tests/cli/test_interactive_command.py \
  tests/cli/test_session_command.py \
  tests/cli/test_init_command.py \
  tests/cli/test_init_catalog.py \
  tests/cli/test_init_workspace.py \
  tests/cli/test_init_smoke.py \
  tests/runtime/test_assembly_helpers.py \
  tests/runtime/test_config_loader.py \
  tests/service/test_host_assembly.py \
  tests/cli/test_smoke_cli_init_provider_matrix.py -q
```

Expected focused assertions：

- parser/help/exit contract；
- family identity 与 override isolation；
- dynamic profile compatibility；
- interaction retries / EOF / SIGINT；
- four-state/repair/rollback；
- versioned publication manifest；
- smoke classifier/redaction/no-fallback schema。

单文件 coverage：

```bash
coverage erase
coverage run -m pytest <上述 focused test files>
coverage report --include='dayu/cli/arg_parsing.py,dayu/cli/session_execution.py,dayu/cli/commands/init.py,dayu/cli/init_catalog.py,dayu/cli/init_workspace.py,dayu/runtime/assembly.py,dayu/service/host_assembly.py,utils/smoke_cli_init_provider_matrix.py'
```

修改文件目标均不低于 80%；若大文件既有 uncovered lines 导致低于目标，必须补 owner
contract tests，不用 pragma、omit 或测试替身绕过。

全量 type check：

```bash
python -m pyright dayu/ tests/ utils/
```

真实 matrix：

```bash
python utils/smoke_cli_init_provider_matrix.py --oracle-version 1
```

真实外部 unavailable row 不使 harness 伪装成功；harness 只有在该 row 满足预期
nonzero/redaction/no-fallback 时才把 row 标为正确分类。`internal_product_bug`、
unclassified、disallowed secret leak、fallback 或 requestable+无真实 response 使
harness 非零；Host SQLite 中已接受的 resolved credential observation 不计为 leak。

最终检查：

```bash
git diff --check
rg -n -- '--model-name|init .*--config' dayu tests utils README.md dayu/config/README.md dayu/service/README.md tests/README.md docs/cli_ci.md
git status --short
```

残留扫描允许历史 review/archive 与 accepted oracle 描述旧行为；production、current
tests、current README 与 smoke invocation 不允许。

## 13. README / docs 决策

- `README.md`：必须更新。命中用户可见 init、CLI 参数、退出码、repair 与排障触发。
- `dayu/config/README.md`：必须更新。package defaults、PRESERVE managed files、
  compactor family 与 context compatibility 属于其职责。
- `dayu/service/README.md`：必须更新。primary default / invocation effective /
  compactor assembly 是当前 Service 稳定边界。
- `tests/README.md`：必须更新。测试层级、focused command、real smoke 与 manifest
  是其职责。
- `docs/cli_ci.md`：必须更新真实 matrix 的调用与 evidence 位置。
- `dayu/README.md`：检查后决定不更新。`UI -> Service -> Host -> Engine` 分层、装配
  角色与 public boundary 未变化；细节归 config / Service README。
- `dayu/host/README.md`、`dayu/engine/README.md`、`dayu/fins/README.md`：不更新，
  因为不修改其 owner contract。
- `docs/cli_ci_oracles.json`：不更新；accepted v1 已包含冻结语义。

## 14. 风险、open questions 与 residual risks

### 14.1 Blocking open questions

None。用户已经冻结：

- compactor 的 family identity 四字段；
-允许的 runner-option/extension 差异；
- package fallback 同源；
-主 Run override isolation；
- provider external failure 与 internal bug 的分类边界。

### 14.2 Implementation risks

1. argparse 的 command 前/后 global option 行为容易回归。S1 用两种位置的正反测试
   封闭。
2. package execution profile baseline 改为 Mimo 可能暴露依赖旧 DeepSeek baseline
   的偶然测试。S3 已冻结 pre-change `rg` inventory 与三类处置：只迁移
   package-default owner / 偶然默认断言，保留显式 DeepSeek catalog 与
   provider-specific fixture；不得机械替换。
3. Service 若用 ordinary effective selection做 family anchor，会错误拒绝跨-family
   `--model`。必须使用无 run override 的 primary default selection；同时必须保留
   runtime fail-closed，因为 PRESERVE / init 后用户编辑可重新制造 durable
   primary/compactor drift。
4. endpoint 可能含敏感 query；错误和 evidence 只输出 redacted identity。
5. ordinary-root file repair 扩大 cleanup shape。identity drift、quarantine fault、
   rollback fault 必须分别测试；shape 只能来自 no-follow stat mode，不能用
   follow-symlink predicate 或 `unlink(missing_ok=True)` 捷径。
6.真实 provider 非确定性、限流与 preview model 下线可能使可用性变化；每次 run
   重新分类，不把 plan-time snapshot 当 verdict。
7. provider 不返回 request id 不等于没请求；request attempted 还需 client
   correlation、transport/trace 与 terminal evidence。

### 14.3 Residual risk classification

- 外部 provider 当次不可用：`assigned to environment/provider owner`，只要 row 的
  unavailable contract 完整，不阻止产品实现通过。
- Windows junction/reparse 与 setx 的真实 node：`covered by approved cross-platform
  validation`；本地非 Windows skip 不能关闭该风险。
- Custom endpoint/model 未提供：`requiring explicit smoke invocation input`，不是
  产品 fallback。
- 任一内部 incompatibility、unclassified matrix row、secret leak 或 fallback：
  `fixed in current work unit`，不得 defer。

## 15. 不过度设计说明

本方案只新增一个四字段 value object 与一个窄职责 smoke：

- 复用 `ConfigLoader` typed config；
- 复用 `select_runner_option_hint(...)`；
- 复用现有 `init_catalog` 16-manifest projection；
- 复用现有 workspace transaction；
- 复用 Service assembly、Host trace 与 runner-input evidence；
- 不新增配置字段、provider abstraction、Host state、migration 或第二套 loader。

primary default selection 的额外一次 helper 调用是区分 workspace truth 与 invocation
override、并在 PRESERVE / 后续用户编辑造成 durable family drift 时赶在 Host open
前 fail closed 所必需的最小状态，不是通用 policy engine。ordinary-file cleanup 是
accepted repair contract 对现有 transaction 的 typed shape dispatch 扩展，不发展为
通用 filesystem library，也不新增 mutation helper。

## 16. Completion report format

每个 implementation slice artifact 使用：

```text
Gate: implementation
Work unit: WU-CLI-INIT-01
Slice: <S1-S6 / name>
Scope: <approved objective>
Changed files: <exact paths>
Semantic owner decisions: <owner and source of truth>
Implemented contract/state transitions: <exact>
Tests:
  - command
  - result / key assertions
Pyright: <command/result>
Docs decision: <updated/not applicable + reason>
Findings fixed: <ids/status>
Residual risks:
  - <risk>
  - classification: fixed in current slice / covered by later approved slice /
    assigned to later work unit / tracked by existing issue /
    requiring new issue or explicit user decision
Completion signal: pass/fail
Stop condition: none/<reason>
Artifact path: <path>
```

最终 work unit closeout 必须报告：

- 改了什么；
- 验证了什么；
- package/workspace/override/compactor family evidence；
- 15-row availability summary；
- unavailable rows 的分类与 no-fallback evidence；
- README 更新；
- review findings 最终状态；
- remaining risks / owner；
- draft PR URL 与下一入口。

## 17. Plan completion

- goal：已确认且未改动。
- oracle：已重新读取，用户冻结语义已纳入。
- Controller A01-A09：
  - A01 保持 reset Enter/No=0、EOF=1、SIGINT=130，并精确列出旧测试迁移；
  - A02 固定 required secret persistence No/Enter/EOF=1、SIGINT=130 与 init
    未完成/零 publication；
  - A03 补齐三类非-init command 的 `--config` 前/后正向回归；
  - A04 固定唯一 typed profile API、加载时点与脱敏 fail-closed 边界；
  - A05 固定 checked-in manifest，normal validation 禁止 actual 动态自证；
  - A06 固定现有 cleanup owner 的 typed identity/shape dispatch；
  - A07 固定 PRESERVE 的 copytree -> staged root config 补缺 -> prompt 补缺 ->
    owner projection 顺序；
  - A08 固定 DeepSeek literal inventory 与迁移/保留分类；
  - A09 保留 Service primary-default 与 compactor runtime fail-closed，并说明
    PRESERVE / 后续用户编辑触发场景。
- Controller rereview R01-R03：
  - R01 固定 PRESERVE copytree 的 `symlinks=True` /
    `ignore_dangling_symlinks=False`，并以 staged shape 与外部目标 bytes 断言防
    dereference；
  - R02 固定 cleanup shape 只从 no-follow stat mode 通过 `stat.S_ISREG` /
    `stat.S_ISDIR` 判定，禁止 follow-symlink API；
  - R03 固定 target effective typed profile：FIRST / OVERWRITE / RESET 使用 package，
    PRESERVE 使用 workspace layered load；缺失取得 package layer，非法 workspace
    profile fail closed 并提示 `--overwrite`，更高 workspace minimum 使低 context
    在原步骤重试。
- plan：已按 plan review adjudication 的 A01-A09 与 rereview R01-R03 修订，
  code-generation-ready。
- blocking questions：None。
- plan gate decision：`pass`。AgentMiMo 与 AgentDS 最终独立 rereview 均为
  `pass`，没有未关闭 material finding。
- next entry point：`implementation S1 — CLI public parser contract`。
