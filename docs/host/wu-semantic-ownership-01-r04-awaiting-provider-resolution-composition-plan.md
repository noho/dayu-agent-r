# WU-SEMANTIC-OWNERSHIP-01 R04 awaiting provider resolution composition plan

## 0. 计划身份与 gate

- WU：`WU-SEMANTIC-OWNERSHIP-01` umbrella remediation continuation，不新建 WU。
- 固定 slug：`r04-awaiting-provider-resolution-composition`。
- gate：R04 plan fix；本文件是独立、可直接生成代码的 implementation plan，不授权 implementation。
- accepted code baseline：`f7006a80`；`dc565d8c` 只包含 R03 completion / R04 transition 文档。
- 下一 gate：Controller re-validation，随后双路完整 plan re-review；计划接受前不得实现、提交或推送。

## 1. 目标、成功条件与非目标

目标是让 awaiting provider 的恢复方式和 poller 部署策略各归唯一 owner，并由 Service 按 typed input 组合：

1. provider config 显式拥有 `poll | callback | manual`；Fins provider 负责严格解析并向 Service 提供 typed mode。
2. `host_runtime.json` 显式拥有完整、必填、无代码默认值的 wait poller policy snapshot。
3. Service 只组合 typed mode、typed policy、registry 和显式 callback transport；不得从 scene、tool name 或入口类型发明 resolution policy。Fins observation handle 恢复所需的稳定结构映射不属于 policy 推断。
4. Host 只执行 Service 传入的显式 policy；无 policy 或 disabled 不启动 poller，enabled 且缺 registry 失败关闭。

完成必须同时满足：三条真实装配路径行为一致；所有 negative matrix 通过；每个修改的生产 Python 文件覆盖率 `>=80%`；受影响测试、pyright、README、source/propagation/security scans 和真实 assembly smoke 通过。

明确非目标：R05 observation-timeout / retry-backoff / `LOST` 状态机；Engine handshake 改动；Issue 175 process isolation；callback transport 本体；scene / `execution_profiles` 配置；统一 tool authorization；permission DSL；Issue 142/151/177/178；R05-R12 后续能力。保留现有身份、权限、callback 映射、文件边界、egress、cancel、durable wait 和 ToolRuntime 安全机制。

## 2. 第一性原理 owner 与 contract

| 语义 | 唯一 owner | contract / 禁止事项 |
|---|---|---|
| provider 的恢复方式 | Fins awaiting provider config + Fins 共享 parser | 闭集 `poll/callback/manual`；缺失、null、非字符串、空串、大小写变体、未知值均失败；不得默认 |
| provider mode 的装配校验 | Service provider-assembly boundary | 只用现有 provider identity 路由到 Fins parser，并检查 recognized non-awaiting provider 的字段误用；不解析 raw mode、不拥有第二 enum/parser |
| poller 部署参数 | `dayu/config/host_runtime.json` | 12 个字段全部 required；ConfigLoader 只做层中立 typed parse；不得 import Host/Fins/Service/Engine |
| Host policy 值对象 | `dayu.host.wait_adapter.WaitPollerRuntimePolicy` | 只承载已解析值，所有字段构造时必填；无模块默认、无无参构造、无 `None` fallback |
| 是否装配 poller | Service composition | 只依据 active provider typed modes、runtime policy、poll registry、callback transport；scene 只控制单次 run 的 tool exposure |
| poller 生命周期与执行 | Host | `OpenHostOptions.wait_poller_policy=None` 表示不启动，不是部署默认；enabled 缺 registry 失败 |
| callback transport | 未来显式 authenticated transport owner | 当前仓库不存在该 owner；callback 必须在打开 Host 前 composition error，不新增 marker/protocol/facade |

已审计 public boundary：`dayu.host.api` 的 runtime-checkable structural policy Protocol 可避免 ConfigLoader 反向依赖，保持不变；`OpenHostOptions.wait_poller_policy: ... | None` 是 composition 开关，保持不变；`dayu.host.open_host` 已实现 disabled/no-policy 不启动和 enabled/no-registry fail-closed，预期不改。

目标 policy snapshot 必须包含：`enabled`、`poll_interval_seconds`、`claim_ttl_seconds`、`claim_batch_size`、`backoff_initial_delay_seconds`、`backoff_multiplier`、`backoff_max_delay_seconds`、`not_ready_observe_interval_seconds`、`idle_poll_interval_seconds`、`adapter_call_timeout_seconds`、`close_drain_timeout_seconds`、`max_outstanding_adapter_calls`。所有 duration/multiplier/count 必须是有限正数；整数位拒绝 bool；不新增无产品依据的字段间大小关系。

packaged snapshot 固定为：`true, 1, 60, 100, 30, 2, 300, 1, 5, 30, 5, 8`，顺序与上列字段一致。三个 packaged Fins awaiting providers 的 mode 均显式为 `poll`。

## 3. Mandatory baseline 逐项处置

| umbrella mandatory baseline | R04 处置 |
|---|---|
| provider mode 为 `poll/callback/manual` 且 provider-owned | 保留；由 Fins 单一 typed enum/parser 落地，Service 不解析/默认 raw 值 |
| `host_runtime.json` 持有完整 required snapshot | 保留；ConfigLoader layer-neutral typed projection，Service 一对一转为 Host 值对象 |
| poll/manual/callback/no-provider/disabled composition | 保留；按 §6.3 完整矩阵验证 |
| umbrella 原 R04-S1 provider mode | 完整保留并纳入唯一原子 S1；覆盖 disabled/non-Fins/available-tool negative cases 与 typed binding |
| umbrella 原 R04-S2 runtime policy | 完整保留并纳入同一原子 S1；完整 required snapshot、Host defaults/fallback 删除不得延后 |
| umbrella 原 R04-S3 composition | 完整保留并纳入同一原子 S1；typed composition、override/scene authority 删除与 mode/policy 同时生效 |
| source/propagation/security scans、README、smoke、handoff | 保留；命令和交付门槛见 §7-§10 |
| §7.4 closed production list 未列 `dayu/host/wait_adapter.py` | 基于直接证据细化：该文件当前拥有 10 个部署数值常量、policy dataclass defaults，以及 `WaitPoller`/`WaitPollerSupervisor` 的无参 fallback；§11.3 和 §7.5 R04-S2 又明确要求移除这些默认。若不改该 owner 文件会留下第二真源，因此只把此文件加入唯一 S1 allowlist，不扩展 Host API/open_host/runtime 边界 |
| umbrella 多 dotted-module `--cov` | 以等价验证替换：当前工具链会触发 NumPy “cannot load module more than once per process”；使用单一 `--cov=dayu --cov-report=json` 后逐文件读取覆盖率，语义等价且已验证可运行 |
| callback positive branch | 保留产品边界、替换当前验证：因 authenticated transport 尚不存在，R04 只验证 callback fail-closed；正向 transport 装配留给既有 WU-WAIT-01 / #89，不造假实现 |

## 4. 唯一原子 Slice 1：provider mode、runtime policy 与 composition

### 4.1 Allowed files

生产/配置仅允许：

- `dayu/config/tool_discovery.json`
- `dayu/fins/tools/_ingestion_tool_helpers.py`
- `dayu/fins/tools/download_provider.py`
- `dayu/fins/tools/preprocess_provider.py`
- `dayu/fins/tools/upload_provider.py`
- `dayu/config/host_runtime.json`
- `dayu/runtime/config_loader.py`
- `dayu/host/wait_adapter.py`
- `dayu/service/fins_wait_adapter.py`
- `dayu/service/host_assembly.py`
- `dayu/service/entrypoint_runtime.py`

测试/烟测仅允许：`tests/fins/test_fins_ingestion_tools.py`、`tests/runtime/test_config_loader.py`、`tests/host/test_wait_adapter_polling.py`、`tests/host/test_wait_poller_runtime.py`、`tests/host/test_wait_observation_runner.py`、`tests/host/test_open_host_runtime.py`、`tests/host/test_public_open_host_options.py`、`tests/service/test_fins_wait_adapter.py`、`tests/service/test_host_assembly.py`、`tests/service/test_entrypoint_runtime.py`、`tests/service/test_entrypoint_runtime_interactive_path.py`、`tests/service/test_entrypoint_runtime_prompt_path.py`、`tests/runtime/test_smoke_host_public_r03_semantic_ownership_assembly.py`、`utils/smoke_host_public_r03_semantic_ownership.py`、`utils/smoke_host_public_awaiting_entrypoint.py`。

README 仅允许：`dayu/config/README.md`、`dayu/host/README.md`、`dayu/service/README.md`、`dayu/fins/README.md`、`tests/README.md`；是否实际修改仍按 §8 的职责触发判断。

### 4.2 实现 contract

- 本计划只有这一个 implementation slice。下列 provider mode、runtime policy、Host defaults/fallback 删除、override/scene helper 删除、typed composition、tests、README、scans 与 smoke 必须在一次 implementation pass 内共同完成；中途不得创建 commit/checkpoint，不得保留旧 scene bridge、临时 fallback、compatibility field/wrapper 或任何过渡 seam。
- 在 Fins 共享 helper 定义 closed `AwaitingResolutionMode(StrEnum)` 与唯一严格 parser；完整中文 docstring/type，绝不 fallback。
- 三个 provider 在创建 runtime/tool definition 前调用同一 parser，保证直接 provider discovery 也校验 owner contract。
- Service 在 active filtering 前遍历全部 effective provider configs，并用 `_fins_awaiting_tool_name_from_provider_config` 现有 provider identity 识别当前 download/preprocess/upload 三个 Fins awaiting providers；识别后立即把 opaque config 交给 Fins parser，因此 disabled Fins provider 的缺失或非法 mode 同样 fail fast。
- 对 Service 已有 identity 明确认识的 non-awaiting providers（当前 Fins read 与 web），若 opaque config 存在 `awaiting_resolution_mode`，Service 只做字段存在性 misuse check 并失败；不得读取、规范化或解析该字段的 raw value，也不得把规则扩展为 generic future provider framework。未知第三方 provider 不由 R04 发明新语义。
- 只有 mode 校验通过后才做 enabled 与 available-tool filtering；disabled+legal 不进入 active metadata/registry，enabled 但 awaiting tool 不可用不制造 binding。进入后续装配的私有 typed metadata 携带 provider id、tool name、absolute workspace root、既有 source/version 事实和 `AwaitingResolutionMode`，后续不得再读取 raw mode。
- S1 修改 `_binding_for_tool_name`，以 typed `AwaitingResolutionMode` 精确映射 `WaitResumePolicy.POLL/CALLBACK/MANUAL`，替换当前硬编码 `WaitResumePolicy.POLL`。`_operation_kind_from_tool_name` 必须保留：它是 observation handle 恢复所需的稳定 `tool name -> FinsOperationKind` 结构映射，不是 resolution policy 推断。
- activation registry 覆盖 active awaiting tools；poll registry 输入只覆盖 active `poll` tools。这些 typed contracts 不得在旧 scene authority 尚存时单独落地；只有本唯一 slice 全部改动完成后才允许形成可 review 状态，届时 packaged 三 provider 均为 `poll`，完整产品路径必须可运行、可测试且全量 pyright clean。
- S1 owner tests 必须明确覆盖三模式、缺失/null/错类型/空串/大小写变体/未知值、disabled+illegal fail-fast、disabled+legal 不 active、recognized non-awaiting 字段误用、available tool 缺失不绑定，以及三种 typed mode 到 Host binding 的精确映射；同时断言 `_operation_kind_from_tool_name` 的 download/preprocess/upload 结构映射保持有效。

## 5. 同一原子 Slice 1：runtime policy contract

### 5.1 Scope 归属

本节不是第二个 slice；所有 allowed files、tests、smokes 与 README 已由 §4.1 统一封闭。本节只细化同一原子 S1 内的 runtime policy contract。

### 5.2 实现 contract

- ConfigLoader 新增 frozen、全字段必填的 layer-neutral `WaitPollerRuntimePolicyConfig`，并作为 `HostRuntimeProfileConfig.wait_poller_policy` required 字段；JSON block 缺失、字段缺失/多余、类型错误、bool 冒充数值、NaN/Infinity、零或负数都失败。
- JSON、ConfigLoader、Host 值对象和 Service composition 必须与 §4 provider mode 在同一 S1 完成；不得在其中任一步建立可提交/可 review 的中间状态。唯一 slice 结束时必须可运行、受影响测试通过且全量 pyright clean。
- Service 逐字段、一对一把 ConfigLoader projection 构造成 Host policy，不加默认、不改值、不从环境/scene/override 补值；`ServiceOpenHostAssemblyResult.host_runtime.wait_poller_policy` 保留完整 typed snapshot 供 handoff/audit，即使最终 `OpenHostOptions` 因无 active poll provider 而不携带 policy。
- 同一原子改动内删除 `ServiceAssemblyOverrides.wait_poller_policy` 及 `_compose_options` 对它的读取，并直接替换为 §6 的 typed composition；同时删除 `with_entrypoint_wait_poller_policy`、`_scene_selects_fins_awaiting_tools` 及 entrypoint 调用。
- 同一原子改动内删除 Host policy dataclass 的全部 deployment defaults、模块级数值 defaults，以及 `WaitPoller`/`WaitPollerSupervisor` 的 `None`/无参 fallback；两者改为显式 keyword policy。
- 禁止临时 wrapper、compat field、hard-coded `None` 过桥、第二 policy owner 或只为跨步骤过渡的 seam。最终因“无 active poll provider”产生的 `OpenHostOptions.wait_poller_policy=None` 是 composition contract 结果，不是过渡方案。
- 保持 `dayu/host/api.py`、`dayu/host/open_host.py` 无改动；如实施证据显示 public contract 必须变化，立即停止并回到 Controller，不扩 allowlist。

## 6. 同一原子 Slice 1：composition data flow 与 matrix

### 6.1 原子 data flow

1. 从选中的 `HostRuntimeProfileConfig` 取得完整 typed policy snapshot；从本原子 slice 中已经 Fins parser 校验的 typed metadata 取得 active modes，禁止重读 raw config。
2. activation registry 使用全部 active awaiting metadata；poll registry 只使用 mode=`poll` 的 metadata；manual/callback 不得进入 poll registry。
3. 任意 active callback 且无 authenticated transport 时先整体 composition error；R04 不新增 transport marker/protocol/facade。
4. 无 active poll（无 provider或仅 manual）时，`OpenHostOptions.wait_poller_policy=None`；有 active poll 时一对一构造并传递完整 Host policy。policy disabled 仍显式传给 Host，由 Host 既有分支不启动；policy enabled 且 poll registry 缺失/空时在 `open_host` 前失败。
5. `_compose_options` 一次性写入最终 registry 与 policy；scene 只决定当前 run 的 tool exposure，不参与以上步骤。prompt/interactive 共用该路径。

### 6.2 实现 contract

- scene `all/select/none` 不改变相同 provider config/runtime snapshot 得到的 Host opener policy；测试必须比较 owner inputs 相同而仅 scene selection 不同时的结果。
- callback error 沿用 Service composition 现有异常惯例，不新增 public exception contract；callback positive transport 继续归 WU-WAIT-01 / #89。

### 6.3 完整 composition negative matrix

| active modes / runtime | registry / transport | 预期 |
|---|---|---|
| 无 active awaiting provider | 无 poll registry | 不向 Host 传 poller policy，不启动 |
| 仅 manual | activation 有、poll registry 无 | binding=`MANUAL`，不向 Host 传 policy，不启动 |
| 仅 poll，policy enabled | poll registry 非空 | 一对一传 policy，Host 启动 poller |
| poll + manual，policy enabled | poll registry 仅含 poll tools | 启动；只 claim/observe `POLL` wait，manual 不被后台轮询 |
| active poll，policy disabled | poll registry 可构造 | 一对一传 disabled policy；Host 不启动，不得用代码默认重启 |
| active poll，policy enabled，poll registry 缺失/空 | 缺失/空 | Service 在 `open_host` 前 composition error |
| 任意 callback（单独或混合） | 无 authenticated transport | Service 在 `open_host` 前 composition error；不得降级为 poll/manual |
| callback + 伪 marker/普通 callable | 非 registered authenticated transport | 同上；R04 不定义可绕过 marker |
| mode 缺失/null/非字符串/空串/未知/大小写变体 | 任意 | provider config parse error，不进入 composition |
| 非 Fins provider 声明该字段 | 任意 | owner misuse error，不 loose parse |
| disabled provider（任意合法 mode） | 不 active | 不创建 binding，不影响 poller 决策 |
| scene 未选择 active poll tool | active provider/policy/registry 不变 | Host 装配决策与 scene 选择前一致 |

## 7. 测试与验证矩阵

变更前直接基线：以下 R04 相关 collection 共 `325 passed, 3 warnings`；单一 `--cov=dayu` 成功。该结果不是实施后验收，实施后必须重跑。

唯一 S1 必须在同一 implementation pass 中完成 §4-§6 的实现与对应 tests；不得先以 provider-only 或 policy-only 子集形成 checkpoint。全部实现完成后统一运行：

```bash
source .venv/bin/activate
python -m pytest \
  tests/runtime/test_config_loader.py tests/runtime/test_import_boundary.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/service/test_fins_wait_adapter.py tests/service/test_host_assembly.py \
  tests/service/test_entrypoint_runtime.py \
  tests/service/test_entrypoint_runtime_interactive_path.py \
  tests/service/test_entrypoint_runtime_prompt_path.py \
  tests/host/test_public_open_host_options.py tests/host/test_open_host_runtime.py \
  tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py \
  tests/host/test_wait_observation_runner.py \
  tests/runtime/test_smoke_host_public_r03_semantic_ownership_assembly.py \
  tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py \
  tests/tools/test_combined_tools_acceptance.py \
  --cov=dayu --cov-report=json:workspace/tmp/r04-awaiting-provider-resolution-composition-coverage.json
python -m pyright dayu/ tests/ utils/
```

从该 JSON 的 `files` 逐一读取本 WU 修改的生产 Python 文件 `summary.percent_covered`，每个必须 `>=80`；不得用总覆盖率替代，也不得加 pragma/omit 掩盖。新增/修改行为必须分别有 owner contract、传播、negative 和 composition 断言；测试不得靠旧默认构造 policy。

现有测试按 owner 边界迁移，不能机械删除获得绿灯：

| 旧测试类别 | 处置与新断言 |
|---|---|
| 直接构造 `ServiceAssemblyOverrides.wait_poller_policy` | 删除旧输入路径；重写为 `host_runtime.json -> ConfigLoader typed snapshot -> Service composition -> OpenHostOptions`，逐字段断言 12 个值 |
| `with_entrypoint_wait_poller_policy` / scene-selected auto-enable | 删除 helper 单测；重写为 scene all/select/none 的 negative/propagation tests，证明 opener policy 仅由相同 provider modes/runtime snapshot 决定 |
| Host `None` / disabled / enabled+missing registry | 保留 fail-closed tests；所有 `WaitPollerRuntimePolicy` fixture 改为显式完整 12 字段构造 |
| provider mode | 重写/新增为 S1 所列三模式、非法输入、disabled 与 recognized non-awaiting misuse owner tests |
| §6.3 matrix | 每一行至少一个 owner-level assertion；同时断言 typed mode、registry membership、policy projection 或 pre-open error，不以仅测最终 `None` 代替 |

基线失败只允许按 control doc 的精确六元组登记规则认领；多 dotted-module coverage 的 NumPy 重载是已证实的验证工具限制，已用上述单一 coverage session 等价替换，不登记为产品失败。

## 8. README 与设计边界

README 决策与必要更新属于唯一 S1 的完成条件，不得延后为独立 docs slice/checkpoint。实现完成后先读各 README 的 Agent 更新约束，再按职责更新：

- `dayu/config/README.md`：完整 required policy block、provider mode 配置契约。
- `dayu/host/README.md`：config-owned 显式 policy、Host 无 deployment defaults。
- `dayu/service/README.md`：删除 scene-selected auto policy 描述，改为 typed composition。
- `dayu/fins/README.md`：provider-owned mode 若构成已实现稳定 contract 则更新；不得写未来 callback transport。
- `tests/README.md`：更新 config/provider/composition/Host 验证边界。

根 README、`dayu/README.md` 和 design/control 文档不更新：本 slice 不改变用户入口、分层关系或已裁决设计。若实现迫使这些文档变化，停止并交 Controller。

## 9. Source、propagation、security scans 与 smoke

```bash
rg -n 'with_entrypoint_wait_poller_policy|_scene_selects_fins_awaiting_tools|WaitPollerRuntimePolicy\(\)' dayu/host dayu/service dayu/runtime
rg -n '_DEFAULT_CLAIM_BATCH_SIZE|_POLL_CLAIM_TTL_SECONDS|_POLL_BACKOFF_INITIAL_DELAY_SECONDS|_POLL_NOT_READY_OBSERVE_INTERVAL_SECONDS|_POLL_IDLE_INTERVAL_SECONDS|_POLL_BACKOFF_MAX_DELAY_SECONDS|_POLL_BACKOFF_MULTIPLIER|_ADAPTER_CALL_TIMEOUT_SECONDS|_CLOSE_DRAIN_TIMEOUT_SECONDS|_MAX_OUTSTANDING_ADAPTER_CALLS' dayu/host dayu/service dayu/runtime
rg -n 'awaiting_resolution_mode' dayu/config/tool_discovery.json dayu/fins/tools dayu/service tests
rg -n 'wait_poller_policy|awaiting_resolution_mode' dayu/config/prompts dayu/config/execution_profiles.json
rg -n 'from dayu\.(engine|host|service|ui|fins)|import dayu\.(engine|host|service|ui|fins)' dayu/runtime
git diff --check
git diff --name-only f7006a80 --
```

前两项生产 source scan 预期零命中；mode 命中只允许 owner/parser/typed composition/tests；prompt/execution profile 和 runtime reverse-import 预期零命中。全部 scans 与真实 smoke 属于唯一 S1 的完成门槛。最终 changed-files 必须是 §4.1 单一 allowlist；不得出现 Engine、design/control、callback endpoint、auth、permission、process isolation 或 R05 状态机变更。对 diff 再扫描 `authorization|permission|process_backed|subprocess|observation_timeout|ResolveWaitLostOutcome`，任何新增均失败并回退。

真实 smoke 必须使用 packaged `ConfigLoader -> provider discovery -> Service composition -> public Host`，覆盖：poll enabled 真正启动且 deterministic `not_ready -> ready`；manual 不创建后台 poller；callback 在 Host open 前失败；无 provider/disabled 不启动；prompt 与 interactive 对同一配置得到相同 opener 决策。复用并更新两个既有 `utils/smoke_host_public_*`，不访问真实外部 LLM/网络，不造 fake transport；smoke handoff 必须输出 typed provider mode、完整 runtime snapshot、是否装配 poll registry/policy，不输出 secret/raw credential。

## 10. Slice 顺序、停止条件与 handoff

计划只有一个原子 S1，不存在 slice 间顺序：provider mode/parser/binding/metadata、runtime policy、Host defaults/fallback 删除、override/scene helper 删除、typed composition、tests、README、scans 与 smoke 一次完成。实施过程中不得创建中间 commit/checkpoint，不得让 provider mode contract 暂时经过旧 scene authority，也不得建立临时 fallback、兼容字段/wrapper、hard-coded bridge 或其他 seam。只有全部 contract 与验证同时通过后才能进入 code review。

任一情形立即停止交 Controller：正确 owner 需要改变；public Host API/open_host、Engine handshake、callback transport、scene/execution profile、R05 状态机或 allowlist 外生产文件必须修改；现有安全机制需放宽；精确基线失败无法匹配；逐文件覆盖率或 pyright 无法通过。

implementation handoff 必须包含：base/head、实际 changed-files、唯一原子 S1 对 umbrella 原 S1/S2/S3 mandatory baseline 的逐项对照、composition matrix owner-level 结果、完整 pytest/coverage/pyright 输出、README 决策、所有 scans、真实 smoke 结果、baseline failure 六元组（若有）、残余风险，并明确确认无中间 commit/checkpoint。计划 review 接受前不开始 implementation；本 plan-fix continuation 完成后停在 Controller re-validation。
