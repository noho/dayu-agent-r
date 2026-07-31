# WU-CLI-INIT-01 Goal Confirmation

## Gate

- Work unit：`WU-CLI-INIT-01`
- 类型：CLI public contract / workspace initialization bug fix
- gate：`goal confirmation`
- decision：`pass`
- 日期：2026-07-30
- accepted oracle：`cli.init.workspace-initialization@1`
- 修复前基线 commit：`933908a8`
- current gate / next entry point：`plan`

## Preflight

- 当前分支：`ci/pr-179-first-ci-readiness`
- 分支不是 `main`、`master`、`develop` 或 `release/*`。
- 修复前 handbook 与 init oracle 已由用户明确要求提交为
  `933908a8 docs: record CLI calibration workflow and init oracle`。
- 提交后工作树干净，不存在来源不明的 dirty changes。
- 本 work unit 没有 design document；用户裁决、accepted oracle、修复前真实 CLI
  观察和当前代码是设计依据。

## 第一性原理判断

目标成立，而且应先于其它 CLI oracle calibration 完成。`init` 是 workspace 配置、
prompt assets、scene 默认模型和 secret ref 的上游 owner；继续用已知不符合 oracle
的 init 产物校准 `prompt` 或 `interactive`，会把错误前置状态固化成下游 oracle。

本 work unit 的严重性为高。它不是纯 UI 修补：

1. 当前公开 parser 仍让 `init` 接受无业务语义的 `--config`，模型覆盖参数仍叫
   `--model-name/-m`。
2. init 已把模型选择投影到 16 个已知 scene manifest，但 compactor assembly 丢弃
   `conversation_compaction` 的 model hint，继续使用 execution profile baseline。
   包内默认 manifest 也存在同源漂移：其它 scene 默认继承 Mimo Token Plan，
   `conversation_compaction` 却默认使用 DeepSeek Flash，迫使未 init 用户同时具备
   两家 provider credential。
3. 可恢复的交互输入错误当前直接结束向导；reset confirmation 的 Ctrl+D 被折叠成
   默认 No，与 accepted EOF contract 不一致。
4. FIRST/PRESERVE/OVERWRITE/RESET transaction 已有较强 whole-tree 与 rollback
   基础，但仍需按 accepted oracle 补齐所有 managed config 文件类别、partial repair
   和真实下游可运行证据。
5. Custom 默认 context window 为 131072，而默认 `standard-256k` profile 要求
   262144；这种 init 自己生成的内部不兼容不能被归类成“provider 不可用”。

## Provider 可用性裁决

15 个选择都必须进入真实 validation matrix，但“真实”不等于强求外部依赖全部成功：

- credential、endpoint 和服务均可用时，必须发出真实 provider 请求并获得真实响应；
- required API key 缺失时，init 在 secret 输入 EOF/拒绝路径安全失败是正确结果；
- key 存在但 provider 拒绝、限流或 endpoint 不可达时，真实 prompt 以明确、脱敏、
  bounded、非零结果失败是正确结果；
- Ollama 服务未运行、Custom endpoint 未配置等已证明的外部前置条件缺失，同样可以
  是正确失败；
- 任何失败都不得静默回退到其它 provider/model，不得用 mock/fake 伪装成功，也不得
  把 init 生成的内部 schema/profile 不兼容误归因于外部 provider。

每个 matrix row 必须记录 precondition classification、实际 effective model/provider、
是否真正发出请求、terminal outcome、脱敏诊断和无 fallback 证据。

## 目标

让 `dayu-cli init` 完整符合 `cli.init.workspace-initialization@1`：

1. 裸 init 使用 `./workspace`；init 命令面彻底不存在 `--config`。
2. 正式主 Run 模型覆盖参数为 `--model/-m`，不保留 `--model-name` 兼容入口。
3. init 选择的普通/思考模型成为所有对应 scene 默认模型；ordinary/thinking 与
   `conversation_compaction` 的 resolved provider、底层 provider model、endpoint
   和 credential ref 必须同源，只允许 thinking extension、temperature、stream 等
   scene runner options 不同。主 Run `--model/-m` 不修改 workspace，也不覆盖
   compactor。
4. 未 init 时，`dayu/config` 中所有 scene（包括 compactor）的默认 provider/model
   family 必须一致，不能要求两家 provider credential。
5. 可恢复交互错误原地重试；EOF=1、parser misuse=2、SIGINT=130，且没有部分发布。
6. FIRST/PRESERVE/OVERWRITE/RESET/repair 以真实 managed tree、状态清理与 rollback
   结果判定，不依赖 CLI 自报 mode。
7. 无 workspace config 与有 workspace config 两条路径均用真实 prompt 验证。
8. 15 个模型选择按上述 provider 可用性裁决形成完整真实 evidence。

## 成功信号

- `dayu-cli init --help` 不展示 `--config`；
  `dayu-cli init --config <path>` parser exit 2。
- Agent execution commands 展示并接受 `--model/-m`；
  `--model-name` parser exit 2。
- 16 个 package-known manifest 的普通/思考模型投影正确；生产 assembly 对每个主
  scene 使用对应 workspace model hint。
- compactor 与其它 scene 的 resolved provider、底层 provider model、endpoint 和
  credential ref 来自同一个 init 选择；其 thinking extension、temperature、stream
  等 runner options 可按 scene 不同。单次主 Run `--model/-m` 不改变 compactor
  model。
- 未 init 时，package scene defaults（包括 compactor）使用同一个 provider/model
  family 和 credential source。
- init 产生的默认 profile/model 组合内部兼容；外部依赖可用时
  `prompt/interactive` 不因 init-owned profile mismatch 失败。
- recoverable choice、endpoint、context 和 required-value 错误可在同一进程修正后
  成功。
- EOF、SIGINT、持久化拒绝、staging validation 失败均不发布半成品 config。
- preserve 保留用户内容、补齐缺失 managed files，只更新模型选择 owner 字段。
- overwrite 的最终 config tree 与当前 package manifest + 本次模型投影一致，旧树
  内所有 sentinel/extra entries 消失，`.dayu` 保留。
- reset 默认 No；确认后 `.dayu` 与 init-owned publication roots 被重建，portfolio
  与非 init-owned assets 保留。
- ordinary partial/corrupt state 可通过适用的 preserve/overwrite/reset 路径恢复；
  symlink、special file、非法 lock identity 继续安全拒绝。
- package fallback、workspace override、15-choice provider matrix 和
  single-run model override 都有脱敏 real-prompt evidence。
- 受影响测试、全量 pyright、`git diff --check` 通过；真实外部失败按 matrix
  classification 记录，不伪装 pass。

## 直接代码证据

- `dayu/cli/arg_parsing.py` 的 global parent 同时注册 `--config`，并被 init parser
  继承；Agent 参数当前注册为 `--model-name/-m`。
- `dayu/cli/init_catalog.py::project_known_manifest_models(...)` 已拥有 16 个已知
  manifest 的 default model 投影，普通/思考 role sets 各 8 个。
- `dayu/runtime/assembly.py::select_runner_option_hint(...)` 已定义
  `run_override > scene_model_hints > execution_baseline`。
- `dayu/service/host_assembly.py` 的 ordinary selection 消费 primary scene hint，
  但 compactor selection 显式传 `scene_model_hints=None`。
- 当前 package manifests 中其它 15 个 scene 默认使用 Mimo Token Plan family，
  `conversation_compaction.json` 却使用 `deepseek-v4-flash`；当前 execution profile
  compactor baseline 也使用 DeepSeek Flash。
- `dayu/cli/commands/init.py::_parse_model_choice(...)`、
  `_read_non_empty_input(...)`、`_read_positive_integer(...)` 当前把可恢复输入错误
  直接抛成 operation error；`_confirm(...)` 把 EOF 改写为默认 No。
- `dayu/cli/init_workspace.py` 已拥有 `.dayu/config` managed roots、
  private staging、whole-tree publication、backup/rollback 和 no-follow cleanup；
  不应另建第二套 workspace mutation helper。
- `tests/cli/test_init_smoke.py` 与 `tests/cli/test_init_workspace.py` 已覆盖大量
  FIRST/PRESERVE/OVERWRITE/RESET sentinel 与 rollback contract，应在 owner
  boundary 扩展，而不是用新 harness 重写。

## Scope boundary

允许修改：

- `dayu/cli/arg_parsing.py`
- `dayu/cli/commands/init.py`
- `dayu/cli/init_catalog.py`
- `dayu/cli/init_workspace.py`
- `dayu/runtime/assembly.py` 与 `dayu/service/host_assembly.py` 中模型选择 owner 的直接
  调用边界
- `dayu/config/` 中仅为消除 init-generated internal incompatibility 所必需的当前
  schema/default 投影
- 对应 `tests/cli/**`、`tests/runtime/**`、`tests/service/**`
- `utils/` 下单一、窄职责的真实 init/provider smoke
- 触发规则要求的 README、accepted oracle/provider availability 修订和 Gateflow
  artifacts

任何 Host lifecycle、Engine loop、Fins storage、memory/EventLog schema 修改都超出
scope，除非 plan gate 发现无法绕开的直接 owner 证据并升级为 blocking question。

## 非目标

- 不修复或定义 `prompt`、`interactive` 的其它 UI/业务行为。
- 不新增 provider integration、申请/写入用户 credential、启动用户未提供的 Ollama
  服务或替外部 provider 保证可用性。
- 不把 mock/fake provider 当作真实 matrix 的通过证据。
- 不保留 `--model-name` 或 `init --config` 的兼容 alias/shim。
- 不新建通用 CLI framework、通用 smoke platform、配置迁移框架或第二套 config
  loader。
- 不改变 portfolio、Fins 文档或非 init-owned assets 的业务所有权。

## 不过度设计说明

方案应复用现有 parser、init catalog、workspace transaction、
`select_runner_option_hint(...)` 和 Service assembly owner。新增代码只处理已接受
oracle 暴露的缺口；真实 provider 检查使用 `utils/` 下一个窄 smoke 与版本化 matrix，
不抽象成新测试平台。

## Agent 分工

- AgentCodex（Codex Agent）：plan、implementation、fix，并写对应 Gateflow artifact。
- AgentMiMo（Claude Code / Mimo）：plan review、code review、aggregate deepreview、
  PR review 的第一路。
- AgentDS（Claude Code / DeepSeek）：同一 review gate 的独立第二路。
- Controller：裁决两路 findings、维护 gate state、检查 evidence/commit scope，并在
  stop condition 外持续推进。

每个新 gate/slice 派发前按 `init-agents` 重新 discovery；新 assigned task 先
`/clear`，Claude Code reviewer 使用 slash skill，AgentCodex 使用 dollar skill。

## Blocking open questions

None。用户已接受 init oracle 的模型、parser、交互、mode、repair、真实 prompt 和
provider-unavailable 语义，并于 2026-07-30 确认本 goal confirmation。

## 2026-07-30 用户补充裁决：Host SQLite credential

用户明确确认：Host SQLite 中持久化 resolved credential 明文没有问题。此前
“secret 不得持久化”的表述仅约束 init-owned workspace 配置及人类可读
evidence surface，不约束 Host 的 durable execution snapshot。

- init-owned workspace 配置仍只能保存 credential ref 或环境变量模板；
- 屏幕输出、日志、异常、Tool Trace、人类可读报告和 LLM-facing 内容仍不得投影
  credential value；
- raw Host SQLite（包括 EventLog payload）中的 resolved credential value 是允许且
  必须如实记录的观察事实，不构成 finding，不要求修改 Host，也不删除 raw evidence；
- CI 可以扫描并计数这类 Host SQLite 命中，但必须把它归类为 accepted observation，
  不能归类为 persistence violation。

该补充裁决消除了 S5-B 的 oracle 歧义，不扩大本 work unit 的产品代码 scope。

## Completion

本 gate 已由用户于 2026-07-30 确认并通过。下一未完成 gate 为 `plan`，由
AgentCodex 产出 code-generation-ready plan；随后按 Gateflow 固定顺序继续到
final closeout pass，除非出现明确 stop condition。
