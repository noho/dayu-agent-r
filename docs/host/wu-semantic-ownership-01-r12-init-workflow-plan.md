# WU-SEMANTIC-OWNERSHIP-01 / R12 `dayu-cli init` 工作流修复计划

## 0. Gate 身份与结论

- 本文是既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的最后一个内部 remediation sub-WU R12 的 **plan-only gate**，不是新 WU，也不授权实现。
- 计划输入以当前仓库代码、`docs/ui/design.md`、remediation plan §19、Controller entry artifact 和 OLD 用户工作流为证据；OLD 的 schema、架构、迁移与兼容行为不具 authority。
- 动机成立：当前 `dayu/cli/commands/init.py` 只做非交互复制，普通模式遇到已存在的 package asset 即失败，`--overwrite` 又先复制旧 `config/` 再覆盖，且没有模型选择、受控密钥持久化、workspace-root 锁与 first/reset prewarm。这不是文案偏差，而是 init owner 没有承诺既定用户状态机。
- 未发现 design contradiction。R12 可以在既定 owner boundary 内完成；无需改变 Service/Host/Engine 分层、当前 schema、迁移策略或其它 issue 的 owner。
- 本计划固定为三个 cumulative slices。每个 slice 通过 implementation review 后才进入下一 slice；S3 通过后停在 Controller closeout checkpoint，不自行 stage、commit、更新 control 或打开后续 WU。

## 1. 目标、完成信号与非目标

### 1.1 目标

实现一个以当前 schema 为唯一配置 contract 的交互式 `dayu-cli init`：

1. 用户明确选择一对普通/思考模型；Ollama 与 custom 只在 staging 配置中产生完整当前-schema model record。
2. 只把用户明确选择持久化的秘密写入 OS 环境；workspace、日志、错误、测试 artifact 和 CI artifact 不出现 secret value。
3. `FIRST / PRESERVE / OVERWRITE / RESET` 四态行为稳定，只有一个 managed-root manifest；普通模式保留整个用户配置树，overwrite/reset 使用全新 package defaults。
4. workspace-root 锁、containment、symlink/reparse-point 拒绝、同父目录 staging/backup、transaction-private validation workspace、Service-owned Fins effective-root override、受控 swap/rollback 共同保护 public `.dayu/` 与 `config/`。
5. 仅 first/reset 成功发布后做一次非网络 prewarm；prewarm 失败只警告，不回滚已验证配置。
6. POSIX 与真实 Windows CLI smoke 覆盖最终用户工作流；每个新增/修改 production 文件单文件覆盖率至少 80%，full pyright 零诊断、R12 changed-path Ruff 零诊断、full Ruff 精确基线 fingerprint 零差异、README、diff 与 source scans 通过。

### 1.2 完成信号

- 四态测试证明相同输入总是得到同一状态与同一 mutation contract，普通/overwrite/reset 不再依赖旧 copier 的偶然行为。
- 选择目录、known manifest role projection、环境变量名称、managed roots 都分别只有一个 owner；消费者不从 raw JSON、目录内容、字符串或旧 workflow 反推。
- 任一 publish 故障或 `KeyboardInterrupt` 后，managed roots 恢复为发布前逐字节内容，或在 FIRST 时保持不存在；不存在半发布 config。
- 用户自建 prompt/manifest 在 PRESERVE 保留，known manifests 只改 `model.default_model_id`；OVERWRITE/RESET 不合并旧 config。
- package 与用户 workspace 均不由 init 创建或删除 `assets/`；用户 `portfolio/` 与其它非 managed roots 永远不参与 reset/swap。
- 真实 Service/Fins discovery 的 filesystem side effect 只发生在 transaction-private validation workspace；validation 与其 pre-publication cleanup 前后，public `.dayu/`、`portfolio/`、`assets/` 和 publication 前的旧 `config/` 都保持 byte/identity 不变。
- 合法 staging config 中未配置、显式绝对或显式相对的 Fins `workspace_root` 都保留原始 bytes；R12 validation 只通过 Service effective-config owner 的显式 override 把三者的 in-memory effective root 无条件定向到同一个 transaction-private validation workspace。普通 runtime 仍保留显式配置语义，非 Fins provider 与 Web storage-state effective config 不受 override 影响。
- 实际 Windows runner 完成 init state smoke，并继续通过 R11 两个真实 `.cmd` argv/CLI 节点。

### 1.3 明确非目标

- Issue 142：不设计或调用 workspace migration，不读取旧 schema，不增加 schema/version compatibility。
- Issue 151：不实现 Write/assets owner；init 不创建、复制、删除或接管 package/user `assets/`。
- Issue 175：不改变 Docling 进程隔离。
- Issue 177：不改变文档截断、`fetch_more` 或文档工具结果 contract。
- Issue 178：不改变 storage state lifecycle；只把整个 `.dayu/` 当作一个 managed root 参与 reset/rollback，不枚举其内部 storage state。
- Web、WeChat、render：不改变入口、服务装配或渲染行为；`wechat` 只作为已有 known manifest 接受 thinking model projection。
- Topic 8：不修改 240 字 exception truncation 决议或相关代码。
- Topic 9：不设计统一 tool authorization；init 只保留本地文件系统、环境变量与交互确认的局部安全边界。
- 不创建 fallback、compatibility shim、旧名 re-export、loose parsing、`hasattr/getattr` 补偿或 `_init_model_role` 元数据。
- 不联网验证 API key、endpoint、Hugging Face 或模型可用性；不把 prewarm 变成模型请求。

## 2. 证据基线与起始 hashes

实现开始前由 implementation agent 重新计算以下 SHA-256。任一 tracked 文件漂移都停止该 slice 并交 Controller 重判；`ABSENT` 路径若已出现也停止。工作树中既有 Controller 修改与 entry artifact 不属于 R12 implementation，不得覆盖。

基线：

- Git commit：`5d4deef8d37fb75b496d33fef9e2da11111a76d6`
- Git tree：`b0879b5e6ee0369119737fd925502eda8f4c58e2`
- OLD workflow evidence：`/Users/leo/workspace/dayu-agent/dayu/cli/commands/init.py` = `f23c41835c22514dbead1f7121d64f7b6a010cb64e2527f9e1d80aa75a4f7e8e`

拟修改/新增路径：

| 路径 | 起始 SHA-256 |
|---|---|
| `dayu/cli/commands/init.py` | `c33db7318476e54f81630c5e5ec8b33e94a6281dd12ecd2ddc7ee85da57b10ab` |
| `dayu/cli/arg_parsing.py` | `d8442bc64dd823cf92b09eec408a1b4437fae07a0f6b89b06afe9b25e7521b0e` |
| `dayu/cli/init_catalog.py` | `ABSENT` |
| `dayu/cli/init_environment.py` | `ABSENT` |
| `dayu/cli/init_workspace.py` | `ABSENT` |
| `tests/cli/test_init_command.py` | `c7d226ed8f72ae846c3f3cca1cd500a2342e7050750415cb0022ea5e5bb15364` |
| `tests/cli/test_arg_parsing.py` | `d3a4abcc22093ff6c4e06edebf249282f1fbac9d9eb3a575c618f28210742658` |
| `tests/cli/test_init_catalog.py` | `ABSENT` |
| `tests/cli/test_init_environment.py` | `ABSENT` |
| `tests/cli/test_init_workspace.py` | `ABSENT` |
| `tests/cli/test_init_smoke.py` | `ABSENT` |
| `.github/workflows/r12-init-windows.yml` | `ABSENT` |
| `dayu/service/host_assembly.py` | `54559d2ea0446316b4ff82bf66594dfaa5d7b75067d495f5d3558d2ea94bbe52` |
| `dayu/service/entrypoint_runtime.py` | `014c5ea0cf16d3538793883277672d70764d5a812054028369c98c229c0115c6` |
| `tests/service/test_host_assembly.py` | `04675e6629e80d8348e9abc1f87f4c4b7762b59e9eef17d6dd67f1b3689a203e` |
| `dayu/service/README.md` | `4f4f30b8e1caae100c9329fe42515ca504f7057e29e92381e15cd35851f6be9d` |
| `README.md` | `b6e1bcfc580e794fba2eb7528aacc6a6b0f8e8dd4763eb7b27ce5636460d8733` |
| `dayu/config/README.md` | `cc28ee57ad886e1aa948a1ee0355f6f619fa3d9c8b1e1ad8b524d31a5f8298bd` |
| `tests/README.md` | `478efffcbf5d3e4f172ec5a7373e49996cf62f3b85a485fdcd60af7623f1c4c1` |

只读依赖锚点：

| 路径 | 起始 SHA-256 | R12 用法 |
|---|---|---|
| `dayu/runtime/filelock.py` | `269f30e4bacb87660713d68d192027f2e6c0c88657014871fbcab14a1f5bf2df` | 直接复用同步 `file_lock`；不复制锁语义 |
| `dayu/runtime/config_loader.py` | `a5b5b05de27a85df106a6ebd0a0a54681d5e9ae1366312fdaa9a06816db7018e` | 当前五配置文件/schema 的唯一校验 owner |
| `dayu/config/models.json` | `d817a17135a01e1e7d89ada9e6b93b107d29fa9715105340c7ff44d505cf8b68` | package model catalog 真源；静态选项只引用其 ID |
| `tests/runtime/test_filelock.py` | `799b0ea609f222ac37f5ad67026ad0c2344122e6eecf1089833ea175550ab8df` | 锁回归锚点 |
| `tests/runtime/test_config_loader.py` | `3a4deb04e2d1cee0e05096f7ee2508d5213474e3cfbf26bf264069a03f1c78da` | 当前 schema 回归锚点 |
| `tests/runtime/test_scene_prepare.py` | `ca57baa9544e6b7c9be43af37aece14c746e53904ff864806fa6bd3f82626389` | manifest/scene 实装校验锚点 |
| `.github/workflows/r11-upload-script-windows.yml` | `8eae09d59e69413adbb2c49dc60c3c431834bab7f230c410b9e981100d3f84c5` | R11 真实 Windows 节点名称/依赖证据；R12 不修改它 |

Ruff immutable baseline 也是实现输入，不得只保存计数：

- 工具版本：`ruff 0.15.11`。
- 在上述 Git commit/tree 与当前工作目录下运行 `python -m ruff check dayu/ tests/ utils/ --output-format=json`，精确产生 `144` 个历史诊断；原始 JSON stdout SHA-256 是 `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`。
- R12 七个已有 candidate Python 路径 `dayu/cli/commands/init.py`、`dayu/cli/arg_parsing.py`、`tests/cli/test_init_command.py`、`tests/cli/test_arg_parsing.py`、`dayu/service/host_assembly.py`、`dayu/service/entrypoint_runtime.py`、`tests/service/test_host_assembly.py` 在起始点的 scoped Ruff 均为零；S1/S2 新文件在起始 commit 不存在。因此 R12 每一 slice 都必须同时满足“累积 changed paths 零诊断”与“full JSON 诊断集与该 SHA 逐字节相同”，不清理 144 个历史问题，也不允许增、删、移动或改写任一诊断。

16 个 package known manifest 也是只读模板；起始 hash 必须逐个核验：

```text
audit.json                                             9102bd6a81f7ff423b312130553ead7c2d913cb7999dbcb23f67b2102f11d9e0
confirm.json                                           e8d3bd959424bac3ed1aa8db0303842776af9d62bd3cc30097e8d25fe4caabb8
conversation_compaction.json                           a4b35fc302ea0d16475bccf10e9998299aa1dd3f1d4c2f8f4c885953d3847be9
decision.json                                          89f0202c85a7fd6ae8507a248c7bf0c47aefe4967c5799cce6d4cfdd0260c123
fix.json                                               a7c7ac765060be1c9de0a54078ce34ab71f3cc418f795c14c63ede56bd152e05
infer.json                                             d70fbdad34b3b3121b20192fb791448a56bf656f3c952d00db8a72ac00ebb760
interactive.json                                       050800d1dfd4d31a28d89b5069132fa803195192ac7b27a929cc3aefe94815bf
overview.json                                          4cb7ce05635df78326dd2c63a2814704dd64da6c94e77902241b8db0acfbd50f
prompt.json                                            1ebd2910507262d0f6720488d7163b32936b1e7eff88a141c1eee686209f54fa
regenerate.json                                        bc73ceb4e0f0a8812d10745077e8f5c85a6f69b883b806d1661f6fd65a1c4f5d
repair.json                                            a2a332b4f06fc9e14eda468bc684c18869601b4a3c82d51e0ee3d9627a2fb085
smoke_host_public_conversation_memory.json             a89b13f92803c8a173d376a998c2ccc91020f681fc0a7af19b4a622472cfc8fb
smoke_host_public_conversation_memory_scenarios.json   cf88ebe57d9e116abd459f9550828538ad841806a7d45152ac6467f6c739874c
smoke_host_public_multiturn.json                       9d291b633e8581ff735d5d75a4a0963b110ee8e5c59a33469fab0771e804f4b7
wechat.json                                            4c9c3d5c29ec36861d902a3d9c5aa8fab018162f272e64181256973c8a34987d
write.json                                             af6935856d87eac8278c0a29dc2a30a3f88b57c8a34504539c8b420e0678e4a0
```

## 3. 唯一 semantic owners

| 业务语义 | 唯一 owner | 消费者限制 |
|---|---|---|
| init 生命周期、提示顺序、fresh workspace pre-lock bootstrap、选择、四态决策、publish 后 prewarm 与用户输出 | `dayu/cli/commands/init.py` | argparse 只解析显式 flags；workspace transaction 不创建/删除 workspace root；不得在测试/README 重建状态机 |
| 可选 provider/model pair、required env ref、known manifest 两组角色、dynamic model record 生成 | 新 `dayu/cli/init_catalog.py` | orchestration 不从 model 名、provider 字符串或 manifest 内容猜角色 |
| secret persistence plan、POSIX profile block、Windows user-env 调用与脱敏结果 | 新 `dayu/cli/init_environment.py` | workspace transaction 不接触 secret value；日志只消费 env name/result |
| managed-root manifest、containment/symlink/same-filesystem staging、transaction-private validation workspace identity/cleanup、swap/rollback/reset transaction | 新 `dayu/cli/init_workspace.py` | orchestration 只能提交 typed request；不得自行 `rmtree`/`replace` managed roots 或 validation tree |
| init 进程间互斥与 timeout | `dayu/runtime/filelock.py` | R12 直接复用 `<workspace>/.dayu-init.lock` 且显式 `timeout_seconds=None`；它只串行 init，不代表 Host 或其它 Dayu 进程持有同一锁 |
| 当前配置/schema 的解析与有效性 | `dayu/runtime/config_loader.py` 与当前 package JSON schema | init 不做 loose parser、旧字段映射或重复 schema validator |
| package defaults | `dayu/config/**` | init 只复制到 staging；R12 不改 package models/manifests |
| public `.dayu/` 内部名称、创建与生命周期 | 现有 Host/runtime/CLI/artifact 各自的 typed owner | init 只在 RESET 中对 whole root 做 transaction；不创建、迁移、枚举或重解释内部状态 |
| private validation workspace 内 Fins runtime layout/content | 现有 Service/Fins production owner | Service/Fins 只消费 init transaction 传入的 private root 并保持真实 discovery 语义；`init_workspace.py` 只拥有该 private container 的 identity、containment、pre-publication cleanup 与 durability，不解析或接管其内部业务语义 |
| Fins provider effective `workspace_root` 的识别、普通 runtime 显式/默认 precedence 与 R12 validation 强 override | 既有 `dayu/service/host_assembly.py::assemble_effective_tool_provider_configs(...)` effective-config owner | CLI 只把 transaction owner 产生的 canonical absolute private root 作为朴素显式参数传入；不得按 provider id/import path/source id 猜 Fins、删除或改写 raw/staging config，非 Fins provider 不消费该 override |

所有新增模块、类、函数都使用严格具体类型，模块/类有中文概览 docstring，函数 docstring 完整列出参数、返回值、异常；不得使用 `Any`、`object`、无类型签名、无理由 lazy import、嵌套类/函数或显式参数塞入 extra payload。

## 4. Catalog、model 与 manifest projection contract

### 4.1 静态选择目录

`init_catalog.py` 定义不可变 `InitModelChoice`（`choice_id`、展示名、ordinary model ID、thinking model ID、可空 required secret env name、kind）与有序 tuple。菜单顺序和精确映射如下；该表是代码生成输入，不允许按 `models.json` 遍历顺序动态生成：

| 展示项 | ordinary | thinking | expected provider | required env |
|---|---|---|---|---|
| Mimo Token Plan | `mimo-v2.5-pro-plan` | `mimo-v2.5-pro-thinking-plan` | `mimo` | `MIMO_PLAN_API_KEY` |
| Mimo SG | `mimo-v2.5-pro-plan-sg` | `mimo-v2.5-pro-thinking-plan-sg` | `mimo` | `MIMO_PLAN_SG_API_KEY` |
| Mimo Pro | `mimo-v2.5-pro` | `mimo-v2.5-pro-thinking` | `mimo` | `MIMO_API_KEY` |
| DeepSeek Pro | `deepseek-v4-pro` | `deepseek-v4-pro-thinking` | `deepseek` | `DEEPSEEK_API_KEY` |
| DeepSeek Flash | `deepseek-v4-flash` | `deepseek-v4-flash-thinking` | `deepseek` | `DEEPSEEK_API_KEY` |
| OpenAI | `gpt-5.4` | `gpt-5.4-thinking` | `openai` | `OPENAI_API_KEY` |
| Anthropic | `claude-sonnet-4-6` | `claude-sonnet-4-6-thinking` | `anthropic` | `ANTHROPIC_API_KEY` |
| Gemini 2.5 Flash | `gemini-2.5-flash` | `gemini-2.5-flash-thinking` | `gemini` | `GEMINI_API_KEY` |
| Gemini 2.5 Pro | `gemini-2.5-pro` | `gemini-2.5-pro-thinking` | `gemini` | `GEMINI_API_KEY` |
| Gemini 2.5 Flash-Lite | `gemini-2.5-flash-lite` | `gemini-2.5-flash-lite-thinking` | `gemini` | `GEMINI_API_KEY` |
| Gemini 3.1 Pro Preview | `gemini-3.1-pro-preview` | `gemini-3.1-pro-preview-thinking` | `gemini` | `GEMINI_API_KEY` |
| Gemini 3.1 Flash-Lite Preview | `gemini-3.1-flash-lite-preview` | `gemini-3.1-flash-lite-preview-thinking` | `gemini` | `GEMINI_API_KEY` |
| Qwen Plus | `qwen-plus` | `qwen-plus-thinking` | `qwen` | `QWEN_API_KEY` |
| Ollama | runtime `ollama` | 同一个 runtime `ollama` | `ollama` | 无 |
| Custom OpenAI-compatible | runtime `custom-openai` | 同一个 runtime `custom-openai` | `custom-openai` | `CUSTOM_OPENAI_API_KEY` |

目录显示仍是一个 15 项有序 tuple，但 package-default 校验与 dynamic 校验必须分离：

1. 对前 13 个非 dynamic paired choices，必须把 ordinary/thinking 两个 ID 都交给当前 `ConfigLoader` / `ModelsConfig` 的既有 extends resolver 加载并 fail closed：两个 ID 都存在，且各自对应的 **resolved model record** 的 `provider` 和 `api_key_ref` 都精确匹配表中承诺；thinking child 通过现有 extends chain 继承这些字段是合法输入，禁止把 raw child 未重复写继承字段误判为缺失，也禁止在 catalog owner 中另造 extends resolver、补默认或接受别名。
2. 对 Ollama，package-default 阶段只要求唯一 `ollama` template 存在且是 `provider=ollama`、`api_key_ref=null` 的完整当前-schema record；交互后在 staging 复制它并替换显式 model/endpoint/context 字段，然后重新校验。
3. `custom-openai` 在 package `models.json` 中不存在是预期事实；package-default 阶段不得对它做 ID 存在性校验。它只在显式交互后生成 staging current-schema record，并与 Ollama 一样由真实 `ConfigLoader` 重载校验。

Ollama/custom 都不得从用户旧 config 猜测，也不能让静态校验与 dynamic builder 同时成为 schema owner。

### 4.2 Dynamic model record

- Ollama：要求非空 model 名、完整 endpoint URL（默认当前 package `http://localhost:11434/v1/chat/completions`）与大于零且非 bool 的 `context_window_tokens`。以 package `models.ollama` 的完整当前-schema record 为模板，在 staging 中只替换这些显式字段；ordinary/thinking 都引用 `ollama`，不需要 secret。
- Custom：要求完整 endpoint URL、非空 model 名、大于零且非 bool 的 context window、`CUSTOM_OPENAI_API_KEY`。生成完整 `openai_compatible` 当前-schema record `custom-openai`；endpoint 必须按用户输入原样校验和写入，不猜 `/chat/completions` 后缀。模板精确包含 `provider=custom-openai`、输入 model/endpoint/context、`api_key_ref=CUSTOM_OPENAI_API_KEY`、Authorization Bearer 模板与 JSON content type、tool/stream/stream-usage 三项 `true`、timeout `3600.0`、retries `3`、SSE idle `120.0`、heartbeat `10.0`、`provider_request_extension=null`。
- Custom runtime hints 不复制 Ollama 或任意当前 provider record。其直接业务证据是已锁定 SHA-256 `f23c41835c22514dbead1f7121d64f7b6a010cb64e2527f9e1d80aa75a4f7e8e` 的 OLD init：`_CUSTOM_OPENAI_TEMPERATURE_PROFILES` 精确承诺八个 temperature，`_build_custom_openai_catalog_entry` 承诺 streaming capability。当前 `ConfigLoader` 的 `RunnerOptionHintConfig` 又要求每个 hint 自足包含 `temperature/top_p/stream`；当前 package `models.json` 对这八个 semantic hint 一致把 `top_p` 投影为 `1.0`，并且只把 `conversation_compaction` 投影为非流式。因此 catalog owner 只做下表这一次明示的 OLD-workflow → current-schema 投影，不将它宣称为通用 provider 默认：

| hint id | OLD temperature 直接证据 | current-schema `top_p` 投影 | current-schema `stream` 投影 |
|---|---:|---:|---|
| `write` | `1.0` | `1.0` | `true` |
| `overview` | `1.0` | `1.0` | `true` |
| `audit` | `0.8` | `1.0` | `true` |
| `decision` | `1.0` | `1.0` | `true` |
| `interactive` | `1.0` | `1.0` | `true` |
| `prompt` | `1.0` | `1.0` | `true` |
| `infer` | `0.5` | `1.0` | `true` |
| `conversation_compaction` | `0.4` | `1.0` | `false` |

如实现时上述 OLD 证据或 current-schema 精确字段契约已漂移，必须停止并交 Controller；不得回退成 Ollama 值、另一 provider 值或隐式默认。
- 所有 URL 只做本地语法/方案校验，不发网络请求；空白、控制字符、非正整数直接在 mutation 前失败。
- record 写入 staging `models.json` 后，必须由真实 `ConfigLoader` 重新加载；catalog builder 不成为第二套 schema owner。

### 4.3 Known manifest role projection

目录以两个不可变 basename 集合承诺角色：

- ordinary：`conversation_compaction`、`fix`、`overview`、`regenerate`、`repair`、`smoke_host_public_conversation_memory`、`smoke_host_public_conversation_memory_scenarios`、`write`。
- thinking：`audit`、`confirm`、`decision`、`infer`、`interactive`、`prompt`、`smoke_host_public_multiturn`、`wechat`。

上述 ordinary/thinking 集合只拥有 16 个 `model.default_model_id` 的投影角色；pre-publish scene validation 使用与角色正交的两个锁定 basename 集合：

- production runtime manifests（13 个）：`audit`、`confirm`、`conversation_compaction`、`decision`、`fix`、`infer`、`interactive`、`overview`、`prompt`、`regenerate`、`repair`、`wechat`、`write`。
- test-owned manual-smoke manifests（3 个）：`smoke_host_public_conversation_memory`、`smoke_host_public_conversation_memory_scenarios`、`smoke_host_public_multiturn`。它们的 `manual-smoke` tag 是测试场景事实，不是 production tool/provider 事实。

projection 规则：

1. 只打开 staging `config/prompts/manifests/<known>.json` 的精确 16 个文件；每个必须存在。projection helper 不实现 manifest parser；13/3 两组分别按 §6.4 的既有 `prepare_scene` 路径验证。
2. 只修改 `model.default_model_id`；保留 `runner_option_hint_id` 与其它字段。
3. 16 个集合必须无交集、并集等于 package known manifest basenames；缺失、多余 package known manifest 或重复即 fail closed。
4. 用户新增 manifest 不被枚举为角色、不被改写；普通模式原样保留它。overwrite/reset 从 package defaults 起步，自然不复制旧用户 manifest。
5. 禁止 `_init_model_role`、文件内容启发式、旧 `default_name`、role fallback 或对用户 manifest 的兼容重写。
6. owner tests 必须对全部 16 个文件断言 projection 后的 model ID、其余字段保持和 current parser 装配；三个 `smoke_host_public_*` 只在测试中使用显式 test-owned `manual-smoke` catalog fixture。production 不得为空目录补救、注入 synthetic/manual-smoke product tool、伪造 provider、跳过真实 tag selection、放宽 `allow_empty` 或复制 manifest parser。

## 5. Secret persistence contract

### 5.1 收集与显式选择

- required key 已在当前进程环境中非空：复用，不提示值、不持久化、不重写 profile/registry。
- required key 缺失：用隐藏输入收集；随后明确显示目标 OS store 与 **变量名**，询问是否持久化，默认 `No`。拒绝或持久化失败时，在任何 workspace publish 前终止；不得以“只在当前进程可用”作为 fallback。
- 可选集成只包括 `TAVILY_API_KEY`、`SERPER_API_KEY`、`FMP_API_KEY`、`HF_ENDPOINT`、`HF_TOKEN`。逐项明确询问，空输入表示跳过；提供的值进入同一个 typed persistence plan。`HF_ENDPOINT` 只做本地字符串校验，禁止 OLD 的联网 probe。
- 任一新值存在时，persistence plan 在执行前一次性展示目标和 env names 并做最终确认，默认 `No`；不展示值。`No` 时在 workspace mutation 前终止。secret value 只活在 `repr=False` 的受限 typed entry 与 writer 调用范围，不进入异常 message、日志、workspace 或测试 snapshot。
- 值含 NUL、CR 或 LF 一律拒绝；变量名只能来自 catalog/上述固定可选集合，用户不能输入任意 env name。

### 5.2 POSIX owner 行为

- 根据已检测 shell 在 `~/.zshrc` 或 `~/.bashrc` 中选择一个 profile；不同时写多个文件。shell 不受支持时 fail closed 并在 mutation 前说明。
- 只有在用户已显式确认 persistence plan 后才允许触及选中 profile。profile 若是 symlink（包括 dangling symlink）拒绝；已存在普通文件保留原 mode。若所选 `~/.zshrc`/`~/.bashrc` 不存在，writer 在同父目录 exclusive 创建私有临时文件、显式设为 `0600`、写入并 `fsync`，再用 `os.replace` 原子创建 profile；不先创建空 public profile，不受 umask 偶然行为决定最终 mode。
- 以一对固定 begin/end marker 管理 **唯一一个** Dayu init block。解析时 marker 缺失则追加，恰好一对则整体替换，重叠/不配对/多块则拒绝，不做宽松修复。
- 每个值用 `shlex.quote` 形成 `export NAME=<quoted>`；无论替换还是不存在时的首次创建，都使用同父目录私有临时文件、`fsync`、目标 mode 和 `os.replace` 原子发布。写后从磁盘重新解析，仅校验变量名/marker 结构；错误不得包含值。
- profile 原子发布与写后校验全部成功后，才把本次 persistence plan 的全部新值注入当前 init 进程的 `os.environ`，保持 POSIX/Windows 成功语义一致；profile 写入或写后校验失败时不得做进程内注入，也不得 publish workspace。§7 import-only prewarm 不读取或转发这些值。

### 5.3 Windows owner 行为

- 逐项使用 argument-safe user environment API：`subprocess.run(("setx", name, value), shell=False, capture_output=True, text=False, check=False)`；不得构造 command string、调用 shell 或记录 stdout/stderr。
- 单项成功后才记录其 env name；全部 `setx` 成功后才把同一批值注入当前 `os.environ`，随后允许 config publish。任一 partial failure 都不得把这一批新值注入当前进程。
- `setx` 跨变量不具事务性。中途失败时 workspace 保持不变，结果只报告“已写变量名 / 未写变量名”，不声称回滚、不输出值。该限制必须在 CLI 文案与测试中显式。
- Windows 真实 CI 使用随机前缀的非 secret sentinel 验证 setx/用户环境读取并清理测试变量；生产 key 只在 mock/隔离输入中出现，artifact 不收集 registry value。

## 6. 四态与单一 managed-root transaction

### 6.1 唯一 manifest

`init_workspace.py` 定义唯一 `ManagedRootManifest` 常量，精确包含：

```text
.dayu    whole-tree
config   whole-tree
```

该对象同时驱动 existing-target snapshot、reset 展示/确认、containment/symlink 校验、backup、publish、rollback 与 cleanup。禁止在任何消费者另写路径 tuple；`.dayu` 内部目录不能单独列出。lock 固定为 `<workspace>/.dayu-init.lock`，位于两个 managed roots 外，不属于 manifest。

`.dayu/` 的内部语义仍由现有 Host/runtime/CLI/artifact 边界各自所有：它们决定内部名称、创建、校验与生命周期。Init 只在已确认 RESET 的 whole-root transaction 层面把 `.dayu/` 移出 public path 并在发布成功后清理 backup；FIRST/PRESERVE/OVERWRITE 均不创建、迁移、枚举、修补或重解释 `.dayu/` 内部状态。

public `assets/`、public `portfolio/`、workspace 根其它文件不在 manifest。init 不得创建/删除 public `assets/`，不得删除或重建 public `portfolio/`；真实 Service/Fins discovery 可以在 transaction-private validation workspace 内创建自己的 `.dayu/` / `portfolio/`，但这两个 private side effects 不加入 managed-root manifest，只能随身份锁定的 transaction-owned private container 在 publication 前清理。§7 import-only prewarm 不调用 Fins/Service/runtime assembly，也不得创建或修改 public/private 这些路径。

### 6.2 状态机

`InitMode` 是 typed enum；状态只由 manifest snapshot 与 flags 决定：

| 条件 | 状态 | staging base | 旧树处理 | prewarm |
|---|---|---|---|---|
| 无 reset/overwrite 且 `config/` 不存在 | `FIRST` | package defaults | 已有 `.dayu/` 也原样不动 | 是 |
| 无 reset/overwrite 且 `config/` 存在 | `PRESERVE` | 逐字节复制现有整个 `config/`，再只补 package 中缺失的 prompt assets | `.dayu/` 原样不动；发布时只替换 `config/` | 否 |
| `--overwrite` 且无 reset，不论 roots 是否存在 | `OVERWRITE` | package defaults | 不合并旧 config；`.dayu/` 原样不动 | 否 |
| 显式 `--reset`，不论 `--overwrite` | `RESET` | package defaults | reset contract 处理两个 whole roots | 是 |

补充精确定义：

- `PRESERVE` 的“prompt assets”仅指 package `config/prompts/` 下相对路径缺失的 **普通文件**；已有文件一个字节也不覆盖。只在复制某个 missing file 时创建它的 missing parent directories；不复制 package 空目录，不定义空目录协议，也不做目录级 merge。package 其它顶层 config 缺失项不借此补齐。完成 missing prompt file copy 后，只允许 model selection 对 staging `models.json` 和 16 个 known manifests 作显式 projection。
- 状态判定优先级是 `RESET > OVERWRITE > (config exists ? PRESERVE : FIRST)`；`.dayu/` 是否存在不被反推成 config 初始化状态。显式 overwrite 即使面对缺失 config 仍是 OVERWRITE，因此不得获得 first prewarm。
- `OVERWRITE` 与 `RESET` 必须从 package defaults 新建 staging，禁止把旧 config 复制到 staging 后 overlay。
- `RESET` 先显示“`.dayu-init.lock` 只串行 init，不锁定 Host/CLI/Web/WeChat 或其它 Dayu 进程；请先停止当前 workspace 的 active Dayu 进程”的明确警告，再列出 snapshot 中实际存在的 managed roots，默认 `No` 精确确认。R12 不做 Host lock、process discovery、kill 或统一治理。`No`/EOF/interrupt 时零 workspace-root bootstrap、零 managed-root mutation、零 secret persistence、零 prewarm。
- reset confirmation 在收集 secret 前完成。确认后获取锁并重取 snapshot；若 identity/type/symlink 状态与展示时不同，释放锁并要求用户重跑，不能按旧确认继续。
- `--reset --overwrite` 由 reset 明确支配，不新增兼容报错或第五种状态。

### 6.3 Workspace bootstrap、lock、containment 与 symlink

- `commands/init.py` 是 fresh workspace root 的唯一 pre-lock owner。它先解析用户请求路径：若最终 workspace path 已存在，用 `lstat`/resolved identity 拒绝 symlink、dangling symlink、普通文件或其它非目录类型；若不存在，只记录 missing 状态，此时 read-only managed-root snapshot 是两个 root 均 absent 的 typed snapshot，不为了 snapshot 创建目录。RESET 的 unlocked snapshot、active-process 警告和默认-No 确认先于创建，因此取消 RESET 不会留下新目录。
- 对非 RESET，或已明确确认的 RESET，若 workspace root 仍不存在，`commands/init.py` 在获取 workspace-local lock 之前显式执行 `mkdir(parents=True, exist_ok=True)`。这是锁存在所必需的最小 bootstrap，不是 managed-root publication；这一 owner 在并发创建后立即重做 `lstat`/resolved identity 和普通目录校验。权限、ENOSPC 或类型竞争失败直接终止；init 不拥有 workspace root 删除语义，因此后续取消/失败不得删除已 bootstrap 的 root。
- 随后精确调用 `file_lock(<workspace>/.dayu-init.lock, timeout_seconds=None, create_parent_dirs=False)`。`None` 显式选择当前 runtime lock 的可中断无限等待语义，不引入 magic timeout；在进入可能阻塞的 acquire 前，CLI 必须输出既定用户可见“正在等待此 workspace lock”通知，包含 workspace 与 lock path 但不得显示 secret。该 public notification 同时是 §8 S3 real-subprocess smoke 的可观察协调点，不是 test-only sentinel。等待中 SIGINT 必须零 publish；已获取 token 后 SIGINT 必须经现有 typed release 语义释放。
- lock path 本身在获取前和获取后都必须是 workspace 内普通非 symlink 文件；symlink/dangling symlink/目录拒绝。获锁后还必须复核 workspace root 与 bootstrap 后记录的 identity/resolved path 相同，然后才取第二次 managed-root snapshot。
- 锁覆盖：第二次 snapshot、选择与输入、secret persistence、staging、校验、swap、rollback、cleanup；交互期间持锁是有意串行化，避免两个 init 基于同一旧状态收集后竞争发布。该锁只证明 init-to-init serialization；Host 当前不消费它，不能把它写成 init-to-Host 互斥。
- 对 manifest root、所有已存在 descendant、staging、validation、backup 使用平台对应的 no-follow classification；发现 symlink（含 dangling）、Windows reparse point、非预期 special file、resolved path 越界即在 managed-root mutation 前拒绝。lexical containment 与 resolved containment 都相对同一 canonical workspace。
- 交易在 workspace root 下生成不可预测、唯一、仅本 transaction 持有的 private staging/backup directories；它们与 public `.dayu`/`config` 共用 workspace 这一父 filesystem，并在 rename 前显式核验 `st_dev` 相同。private staging 内另建一个专用于真实 Service/Fins discovery 的 validation workspace root；它不是 public workspace、package/config root 或 backup，也不能被发布。transaction owner 在把该 root 传给 Service assembly 前记录其 identity 与 containment，后续只按该 identity 管理。临时名/prefix 是内部实现细节，不是 public、README 或 LLM-facing protocol；不能把跨 filesystem copy 宣称为 atomic。

#### 6.3.1 Symlink/reparse-safe identity-locked deletion

- cleanup 只操作 transaction 自己创建并记录 identity 的 staging/validation/backup；禁止按 glob、名称猜测或删除 public path。identity 至少包含 canonical lexical/resolved parent、`st_dev`、`st_ino` 和 file type；Windows 另含 `st_file_attributes` / `st_reparse_tag`。删除前必须重新取得 no-follow identity 并与记录值精确相等，目标必须仍在同一 transaction-private parent 内且不是 symlink/reparse point。删除入口先通过同父 `os.replace` 把目标移到本 transaction 新生成的 quarantine basename，再对 quarantine 重取 identity；只有 identity 与原记录相同且原名称已缺失才可递归删除。任一不一致都 fail closed，不尝试猜测或清理替代对象。
- POSIX 只有在当前解释器直接报告 `shutil.rmtree.avoids_symlink_attacks is True` 时才使用其 Python 3.11 `lstat/open/fstat` fd-safe 路径；调用时不提供吞错/重试 callback。不得用 `os.walk(followlinks=False)` 冒充 fd-safe deletion。若目标 POSIX 平台缺少该 capability，停止并交 Controller，不自行造通用 filesystem framework。
- Windows 不把 `shutil.rmtree.avoids_symlink_attacks is False` 解释为“Python 3.11 必然跟随 link”或“所有正常 init 必须失败”。Python 3.11 官方 contract 明确 Windows 自 3.8 起不会先删除 directory junction 的 target contents，且 `os.stat(..., follow_symlinks=False)` 会禁用 name-surrogate reparse traversal；owner-local Windows 路径必须在 quarantine 前后及递归删除前用 `st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT` / `st_reparse_tag` 拒绝 root、nested symlink、junction、mount-point 或其它 reparse entry，再调用 Python 3.11 Windows `shutil.rmtree` 删除已验证的 ordinary private tree。若 scan 与删除间出现 reparse entry，标准库只能删除/拒绝该 entry 本身，外部 sentinel 必须保持不变；任何无法分类的 attribute、identity drift 或删除错误都 fail closed。不得引入通用 Windows filesystem abstraction、shell `rmdir` 或 PowerShell cleanup。
- 直接平台证据固定为 Python 3.11.15 `shutil.rmtree` 文档的 fd-safe capability 与 Windows junction 说明、Python 3.11.15 `os.stat(..., follow_symlinks=False)` / `st_file_attributes` / `st_reparse_tag` contract，以及项目 `.venv` 的 macOS probe（`shutil.rmtree.avoids_symlink_attacks is True`）。S3 Windows runner 必须记录自身 Python 3.11 capability，并用外部 sentinel + nested junction 做非跳过证明；普通 symlink 若 runner 无创建权限可以按精确 privilege error skip，但必须保留 skip reason，不能替代 junction/reparse 证明。
- validation cleanup 删除中途失败时，只承诺 transaction-private staging/container 仍可定位，并报告精确 operation、失败 path、异常类型和 partial-deletion 状态；不承诺已删除内容仍完整，不复制/快照取证树，也不新增 cleanup journal。validation tree 已全部删除但其 POSIX parent directory sync 失败时，唯一 retained truth 是仍存在的 transaction-private staging/container；validation child 必须不存在。typed diagnostic 报告 retained staging path、`deletion durability unconfirmed` 与 `validation_parent_directory_sync` stage，不得声称已删除 validation tree 仍被保留。

#### 6.3.2 File content、directory-entry 与 platform durability

- 三个事实严格分开：`fsync` 普通文件只提交该文件已写内容；对包含 rename/create/delete 的 parent directory 做 sync 只提交 directory entry/namespace change；symlink/reparse-safe deletion 只防越界或跟随外部 target，不承诺擦除已删除数据块或阻止 forensic recovery。
- POSIX 在 publication 前对 staging target config 的每个普通文件执行 no-follow open + `fsync`，并从叶到根 sync staging config directories；validation tree 删除后 sync 其 staging parent；public replace 序列完成后 sync workspace root。rollback 逆序完成后也 sync workspace root；post-publication backup/quarantine 删除后再次 sync workspace root。任一 pre-publication file/directory sync failure 都按 §6.4 fault matrix abort/rollback；post-publication sync failure只进入 truthful cleanup warning。
- Windows 的 Python 3.11 `os.fsync` 只为普通文件提供 `_commit()`；Python 3.11 的 `dir_fd` operations 在 Windows 不可用，现有标准库没有与 POSIX parent-directory `fsync` 等价且被本项目直接验证的接口。R12 因此仍对每个 staging 普通文件 `fsync`，继续使用同 volume `os.replace` 作为单个 namespace transition 和 live-process rollback primitive，但明确不承诺 successful return 已把 public/cleanup directory entries crash-durable 到 stable storage，也不因缺少 directory fsync 把正常 Windows init 永久拒绝。R12 不为扩大该承诺引入 `ctypes`/Win32 flush framework；若未来需要 power-loss 等价保证，必须以直接平台机制证据另行设计。
- Windows 上任一 `os.replace`/文件 `fsync`/删除错误仍是 typed failure：publication success boundary 前逆序 rollback，boundary 后 cleanup warning；不降低 public-root isolation、same-volume 要求、每次 replace 的 atomic destination visibility、rollback 或错误路径真值。两个 managed roots 仍不是一个 single-syscall transaction；该既有 residual 不扩展 Host/process lock。

### 6.4 Validate、swap 与 rollback

1. 先在同父 staging 构造目标 `config/`；FIRST/OVERWRITE/RESET 从 package defaults，PRESERVE 从上述保留规则。
2. 应用 dynamic model record 与 known manifest projection。
3. pre-publish validate 先用真实 `ConfigLoader` 读取 staging 当前五配置文件，得到唯一 `staging_runtime_config: RuntimeConfig`。既有 Service `assemble_effective_tool_provider_configs(...)` 新增一个朴素 keyword-only `fins_workspace_root_override: pathlib.Path | None = None` 输入，并仍由现有 `_is_fins_workspace_bound_provider_config(...)` 唯一识别 owner：普通 runtime `entrypoint_runtime` 调用显式传 `None`，继续以 valid raw Fins `config.workspace_root`（绝对/相对）优先、调用方 `workspace_root` 只补默认；R12 init validation 是唯一 production non-`None` consumer，精确调用 `workspace_root=<canonical public workspace>` 与 `fins_workspace_root_override=<recorded canonical absolute private validation root>`。这样非 Fins effective config 继续看到普通 public runtime root，只有 Fins root被隔离。Service 仍校验 raw Fins root 的现行 type/non-empty grammar，但当 raw 值是合法未配置、显式绝对或显式相对路径时，override 无条件成为 in-memory effective Fins root；不得改写 `ToolDiscoveryProviderConfig.config`、staging/public bytes或 schema。override 不进入非 Fins provider，Web `playwright_storage_state_dir` 仍只消费普通 public `workspace_root`。然后调用真实 `discover_service_tools(...)` 一次，使用 `SceneToolCatalog.from_tool_bundle(discovered_tools.tool_bundle)` 产生真实 catalog并复用于 §4.3 锁定的13次 `prepare_scene(ScenePrepareRequest)`；每次 request都显式传入且只传入两个锁定 required slot `{"current_time": "", "fins_default_subject": ""}`。CLI 不 import/copy Service 的 Fins provider ids/import paths/source ids，不删除 raw `workspace_root`，不增加 schema/fallback/compat/test seam；assembly 不是 metadata-only seam。真实 Fins binding 在 private override root 创建 `.dayu` / `portfolio` 是必须被测试观察到的生产副作用。三个 exact `smoke_host_public_*` 的 `manual-smoke` tag selection只由 test-owned explicit catalog fixture调用同一 current parser验证，不得注入 production discovery。projection helper与测试仍覆盖全部16个 `model.default_model_id`。用户新增 manifests只保留，不由 init loose-parse或猜 role；production禁止空/合成 catalog、synthetic product provider、metadata-only provider/discovery开关、重复 parser、test shim、跳过真实 tag selection或放宽 `allow_empty`。若 implementation entry的13/3 basename、tool tag、required-slot集合或 Service Fins classification已漂移，停止并交 Controller，禁止就地推断或 fallback。
4. 13 个 production manifests 全部通过后，`init_workspace.py` 必须按 §6.3.1 的 platform path 对 dedicated validation workspace 执行 identity-locked no-follow cleanup。POSIX 只有 cleanup 与 staging-parent directory sync 都成功才可离开 validation gate；Windows 只有 identity/reparse checks、quarantine 与删除成功才可离开，并按 §6.3.2 不声明等价 directory crash-durability。cleanup/identity/reparse/delete fault 必须在 public config publication 前 abort；POSIX parent-sync fault同样 abort。删除未完成时报告 retained staging 与实际 remaining/quarantine path；validation child 已删除而 POSIX parent sync 失败时只报告仍存在的 staging/container、child absent 与 `deletion durability unconfirmed`。不得降级成 publication 后 warning，也不得清理 public `.dayu` / `portfolio` / `assets` 作为补偿。
5. secret persistence 全部成功后才允许 publish。POSIX 单 profile 替换原子；Windows 部分成功限制按 §5.3 报告。
6. 对本状态需要替换/删除的每个 existing managed root，先 `os.replace` 到同父唯一 private backup；再 `os.replace` staging config 到 `config/`。RESET 的 `.dayu/` 不创建替代 staging，它移到 backup 后在 public `.dayu/` path 上缺失；FIRST 不凭空创建 `.dayu/`。
7. 多个 root 的 transaction 是“逐 root same-volume `os.replace` + 故障 rollback”，不得声称跨 root single-syscall 原子。POSIX **publication success boundary** 是 validation cleanup/parent sync、staging file/content+directory sync、本状态全部 replace 与 workspace-root directory sync 成功；Windows boundary 是 validation safe cleanup、staging regular-file fsync 与本状态全部 same-volume replace 成功，且明确没有 parent-directory crash-durability承诺。在 boundary 前的 replace/file-sync/POSIX-directory-sync/interrupt 故障都按记录的逆序恢复全部 backup；FIRST 则 identity-checked 删除本 transaction 已放到 public path 的 config，之后 POSIX sync workspace root。普通 pre-publish validation 失败尚未替换 managed root，只有在 §6.3.1 安全条件成立时才清理 transaction staging；validation cleanup fault按第 4 项保留可定位 private path并 abort。若环境写入已经成功，失败报告另列已写 env names，不能回滚或打印 values。rollback 删除 public transaction object、逐个 backup→original replace 或 POSIX rollback directory sync 任一步失败时，必须报告精确 stage、当前 public root truth 与仍可恢复 backup/staging path，不能静默吞掉或声称全部恢复。
8. 越过 publication success boundary 后才按 §6.3.1 删除 transaction backups、quarantine 与空 staging container；这是 cleanup，不是 publication correctness 的一部分。删除未开始/中途失败必须返回 typed warning，报告仍存在 path、精确 operation 与 partial state；删除完成后 POSIX workspace-root sync 失败则报告 cleanup path 已不存在与 `deletion durability unconfirmed`，不得谎称路径仍保留。Windows successful cleanup 不承诺 parent-directory crash durability，但不是 warning/failure。任何 post-publication cleanup fault 都不 rollback、不把已发布 config 报告为失败、不改变 init 成功 exit status。不得删除用户 assets、portfolio 或任何 manifest 外路径；该边界与第 4 项 pre-publication validation cleanup fault 禁止复用 warning 语义。

## 7. First/reset-only 非网络 prewarm

- owner 是 `commands/init.py` 的模块级私有 immutable import-root tuple 与模块级私有同步 helper；不新增第四个 init support module，也不建立通用 lifecycle/cache/preload framework。
- CURRENT direct contradiction 已锁定：`compose_open_host_options` 的 ordinary selection 可消费 scene/ordinary override，但 compactor selection 只消费 `execution_profile.compactor_baseline.model_id`；当前四个 profiles 都固定为 `deepseek-v4-flash`，且 `ServiceAssemblyOverrides` 没有 compactor override。因此 R12 不能用 selected model pair 的单一 env/ref 完成真实 assembly；§6.4 获准的 Service effective Fins-root correction与模型/compactor selection正交，不授权为了 prewarm 修改 execution profiles、Service composition或Host，§7 必须保持 OLD-aligned import-only。
- OLD SHA-256 `f23c41835c22514dbead1f7121d64f7b6a010cb64e2527f9e1d80aa75a4f7e8e` 的 `_run_init_prewarm` 直接语义只是依次调用 `importlib.import_module(...)`，不执行 prompt/interactive/write 业务或 runtime assembly。CURRENT 从 OLD tuple 过滤掉已删除模块后仅保留两个真实用户入口 import roots，顺序锁定为 `("dayu.cli.commands.interactive", "dayu.cli.commands.prompt")`；已删除的 `dayu.cli.dependency_setup`、`dayu.cli.interactive_ui`、`dayu.cli.commands.write` 和任何 placeholder 都不得出现。
- CURRENT import graph 的唯一 owner 仍是被导入模块自身：`dayu.cli.commands.prompt` / `dayu.cli.commands.interactive` 都直接 import 共享 `dayu.cli.session_execution`，后者直接 import `dayu.service.entrypoint_runtime` 的正常用户入口 assembly symbols。Init 只维护上述两个 root strings 并调用 `importlib.import_module`；不得把 `dayu.cli.session_execution`、`dayu.service.entrypoint_runtime` 或更深 Host/Engine/Fins transitive modules 复制进另一份 prewarm list，也不得调用其中任何 function/class。
- helper 不接受 workspace/config/env/selection 参数，不读取 `os.environ` 或 secret typed entry，不加载 ConfigLoader/scene，不构造 request/result，不创建 event loop，不调用 `prepare_entrypoint_runtime`、`compose_open_host_options`、`prepare_host_admin`、Fins registry/provider、`open_host` 或其它 runtime entry。唯一允许的效果是 Python 正常 import mechanism 把真实模块放入当前进程 `sys.modules`；不得另造 cache、resource close、FD cleanup 或反射 lifecycle。
- 只在 FIRST/RESET 完成 config publication 后调用一次；PRESERVE/OVERWRITE 必须以调用计数断言为零。失败只输出 warning 与经过脱敏的异常类型/安全摘要，init 仍以配置发布成功结束，不回滚、不输出 secret、HTTP body、environment value 或 module globals。
- import-only prewarm 禁止网络、provider/model/endpoint probe、下载、Host/Engine/Fins/Service runtime assembly、workspace/config/profile/environment/`.dayu`/portfolio mutation。测试在 `PYTHONDONTWRITEBYTECODE=1` 的隔离 subprocess 中用 socket/network fail-fast seam、临时 workspace tree hash 和 environment snapshot 证明除了进程内 `sys.modules` import cache 外零外部状态变化；不得把测试 seam 放进 production。
- 测试必须同时证明 exact two roots、CURRENT transitive graph 确实加载 `dayu.cli.session_execution` 与 `dayu.service.entrypoint_runtime`、deleted write/placeholder roots 不存在，以及 helper 连续调用两次结果稳定。若 import roots/graph 漂移、导入开始需要 secret/network/Dayu runtime state，或必须调用 assembly 才能“预热”，停止并交 Controller；不得扩大 module list 或引入 fallback framework。

## 8. 三个 cumulative implementation slices

### S1 — Typed catalog、manifest projection 与 OS environment owner

允许路径：

- 新增 `dayu/cli/init_catalog.py`
- 新增 `dayu/cli/init_environment.py`
- 新增 `tests/cli/test_init_catalog.py`
- 新增 `tests/cli/test_init_environment.py`

实现：

1. 按 §4 建立 typed catalog、静态一致性验证、dynamic record builder 与 exact known-manifest projection helper。helper 只接受明确 staging path 和 typed selection，不接受 loose mapping/extra payload。
2. 按 §5 建立 typed persistence request/result、POSIX writer、Windows writer 与 redacted error。平台选择通过明确 platform 参数/标准平台值，不使用 `getattr` 探测。
3. S1 是内部 contract slice，不改变 public `dayu-cli init` 行为，也不修改 package JSON。测试直接针对 owner contract。

必须断言：

- 15 项显示目录顺序不变；13 个非 dynamic pair 的所有 ID 通过现有 `ModelsConfig` extends resolver 后，resolved provider/api ref 精确一致，任何缺失/错配即 fail closed。测试必须包含一个 raw thinking child 只写 `extends` 而正确继承字段的成功例，以及父/child override 导致 resolved mismatch 的拒绝例；禁止 raw-field check 或 duplicate resolver。package `ollama` template 单独校验；package 缺少 `custom-openai` 不是静态错误，custom 只在 staging builder + 真实 `ConfigLoader` 路径校验。
- 两个 role 集合精确等于 16 个 package known manifests，只改 `model.default_model_id`，user-added manifest byte-identical；16 个 projection 均用 current parser 验证，其中三个 exact `smoke_host_public_*` 只使用 test-owned explicit `manual-smoke` catalog fixture，production module 不含该 fixture/provider。
- Ollama/custom 输出可由真实 `ConfigLoader` 读取；custom 八个 runtime hints 逐值等于 §4.2 的 OLD/current-schema 投影；URL/context/secret ref 边界拒绝准确；无旧字段与 `_init_model_role`。
- POSIX marker 0/1/多块、existing mode、quote、symlink、atomic replace 故障；supported shell 的 profile 不存在时只在确认后原子创建且 mode 精确为 `0600`；Windows argv tuple、`shell=False`、partial success names；POSIX 与 Windows 都只在整批持久化成功后把新值注入当前进程，任一失败不注入且不 publish；所有异常/captured output/repr 都不含 sentinel secret。

验证：

```bash
source .venv/bin/activate
pytest tests/cli/test_init_catalog.py tests/cli/test_init_environment.py -q
pytest tests/cli/test_init_catalog.py --cov=dayu.cli.init_catalog --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/cli/test_init_environment.py --cov=dayu.cli.init_environment --cov-report=term-missing --cov-fail-under=80 -q
python -m pyright dayu/ tests/ utils/
python -m ruff check dayu/cli/init_catalog.py dayu/cli/init_environment.py tests/cli/test_init_catalog.py tests/cli/test_init_environment.py
# 再执行 §9.2 的 full Ruff JSON fingerprint 比较，必须仍为 144/051bd6... 且 cmp 零差异
git diff --check
```

S1 review gate：Reviewer 对照 §4/§5 逐项检查唯一 owner、无 secret 泄漏和当前 schema，并核验两个 S1 production 文件各自单文件 coverage `>=80%`；未 PASS 不进入 S2，禁止把 coverage gap 延后给 S2/S3。

### S2 — 单 manifest workspace transaction 与四态 orchestration

累积允许路径：S1 全部路径，另加：

- 新增 `dayu/cli/init_workspace.py`
- 修改 `dayu/cli/commands/init.py`
- 修改 `dayu/cli/arg_parsing.py`
- 修改 `dayu/service/host_assembly.py`
- 修改 `dayu/service/entrypoint_runtime.py`
- 新增 `tests/cli/test_init_workspace.py`
- 修改 `tests/cli/test_init_command.py`
- 修改 `tests/cli/test_arg_parsing.py`
- 修改 `tests/service/test_host_assembly.py`
- 修改 `dayu/service/README.md`

实现：

1. `init_workspace.py` 按 §6 建立唯一 managed-root manifest、typed snapshot/mode/request/result、platform-specific no-follow validation、same-parent staging/backup/quarantine、dedicated transaction-private validation workspace identity/cleanup、publish/rollback。
2. 删除当前 `_raise_for_existing_assets` 拒绝式语义与 overwrite 旧树 overlay；不能留 wrapper/fallback。既有 containment、SIGINT 与 rollback 测试迁移到新 owner contract，不为旧偶然行为保兼容。
3. `host_assembly.py` 只在既有 effective-config owner 增加 §6.4 的 Fins root override 参数与 precedence；`entrypoint_runtime.py` 的普通 runtime caller 显式传 `None`。不得改 Fins producer、provider schema、raw config、Web effective config 或 discovery chain；`dayu/service/README.md` 只记录 ordinary 与 validation override 的 owner contract。
4. `commands/init.py` 编排顺序固定为：解析/检查 requested workspace/flags → reset unlocked snapshot + active-process 警告 + 默认 No 确认（仅 RESET）→ 按 §6.3 显式 bootstrap missing workspace root → 以 `timeout_seconds=None`/`create_parent_dirs=False` 获取 init lock 并复核 workspace identity/managed snapshot → 交互选择/dynamic 参数 → 收集并确认 persistence plan → private same-filesystem staging/projection → staging `RuntimeConfig` + Service Fins-root override 指向 transaction-private validation root 的真实 discovery → §6.3.1 validation identity-locked cleanup → §6.3.2 platform durability gate → persistence → publish boundary → post-publication cleanup warning boundary → 安全输出。所有用户取消在对应 mutation 前终止；bootstrap 后的失败不删 workspace root。
5. `arg_parsing.py` 保留 `--reset`/`--overwrite` 两个显式 flag，但帮助文本改为真实交互/四态语义；不增加 old workflow hidden flag。

必须断言：

- FIRST、PRESERVE、OVERWRITE、RESET 及 `reset+overwrite` 的完整矩阵；PRESERVE 保留整个 config、自建文件/manifest，只按文件粒度补 missing prompt（只为 missing file 创建 parent），OVERWRITE/RESET 不合并旧树。
- fresh path FIRST 的完整成功流；并发 `mkdir(exist_ok=True)` 后身份复核；permission/ENOSPC、existing file、symlink/dangling symlink 和创建类型竞争均 fail closed。
- reset 先显示“停止 active Dayu”警告和精确 existing targets，默认 No/EOF/SIGINT 不创建 fresh root 且 managed-root byte hash 不变；确认后 TOCTOU snapshot 漂移停止；测试还要断言未调用 Host lock/process discovery/kill。
- manifest 只有 public `.dayu`/`config`；package/user public `assets` 永不创建/删除，public `portfolio` 与其它 root byte-identical，private validation `.dayu`/`portfolio` 不扩张 manifest。
- lock path/managed tree/descendant symlink 与越界拒绝；private staging/validation/backup/quarantine 唯一、位于 workspace root 内且 `st_dev` 一致，validation root identity 在真实 discovery 前锁定，测试不固定任何 private 名称；真实 init 锁竞争串行；显式 `timeout_seconds=None`，等待锁 SIGINT 无 publish。
- `tests/service/test_host_assembly.py` 直接断言 Service owner：普通 `None` 路径在未配置时注入 runtime root，显式绝对 root 原样保留，显式相对 root 按 runtime root 解析；override 对未配置/显式绝对/显式相对三个合法 raw case 都无条件产出同一 canonical absolute private root，raw mapping/serialized staging bytes 不变；relative override 自身被拒绝。相同测试还要覆盖 read/awaiting Fins classification、非 Fins provider 完全不消费 override、Web storage-state 仍只按普通 runtime root 解析。`entrypoint_runtime.py` 必须显式传 `fins_workspace_root_override=None`，只有 R12 init validation 传 non-`None`。
- pre-publish validation 从 staging `RuntimeConfig` 经上述 Service effective-provider assembly/discovery 和 `SceneToolCatalog.from_tool_bundle` 构造一次真实 catalog，只装配 13 个 runtime manifests 并传两个锁定空 slot。CLI owner tests 对 staging Fins root 未配置/显式绝对/显式相对三态分别运行真实 production discovery，观察所有 Fins side effect 只在 dedicated private override root 创建 `.dayu` / `portfolio`；同时证明 raw staging/public config bytes 未被 strip/改写，public `.dayu`、`portfolio`、`assets` 及旧 `config` 在 validation/cleanup 前后 byte hash和 filesystem identity 不变。越过 publication boundary 后 public `portfolio`/`assets` 仍不变，public `.dayu` 严格按四态 contract 处理（FIRST/PRESERVE/OVERWRITE 不变，RESET 移除），`config` 也只按四态 contract 变化。三个 `smoke_host_public_*` 仅由 test-owned `manual-smoke` fixture 验证；全部 16 个 model projection 保留。只允许上述 Service effective-config owner/caller/test/README diff；Fins/package/Host/Engine/Tool production 必须零 diff。production 不得出现空/合成 catalog、synthetic/fake provider、metadata-only discovery、manual-smoke provider、duplicate parser、test shim 或 `allow_empty` 放宽。
- POSIX tests 覆盖 fd-safe capability、nested symlink/dangling symlink、root identity drift、quarantine identity mismatch与外部 sentinel不变；Windows tests覆盖 `st_file_attributes` reparse classification、nested junction 外部 sentinel、normal ordinary-tree cleanup与 root identity drift。普通 Windows symlink无权限时只允许按精确 privilege error skip，junction test与正常 transaction不得 skip。
- required secret 拒绝持久化、POSIX writer failure、Windows partial failure均保持 workspace 未发布；输出只含 env name。

Syscall fault injection 只允许 tests 使用 `pytest.monkeypatch` / `unittest.mock` 在实际 owner module lookup boundary 替换 `os.open`、`os.stat/lstat`、`os.fsync`、`os.replace`、`os.unlink/os.rmdir`、`shutil.rmtree` 或抛 `KeyboardInterrupt` / `OSError(ENOSPC|EIO|EPERM)`；这是 syscall fault injection，不是 provider/catalog test shim。Production 函数不得为此新增 callback、factory、profile、默认 callable 参数或 test-only branch。精确 fault matrix：

| 阶段 / 注入点 | 必须注入的 operation | 预期 owner truth |
|---|---|---|
| staging/validation 前 | copy/write、普通文件 `fsync`、POSIX staging directory sync、真实 ConfigLoader/Service discovery/scene validation 抛错或 ENOSPC/interrupt | 尚无 public replace；安全 cleanup 可完成则删除本 transaction private tree，否则报告 retained staging；public roots byte/identity 不变 |
| validation cleanup identity | cleanup 前 no-follow `lstat/stat`、containment、root→quarantine `os.replace`、quarantine identity复核 | pre-publication abort；不递归删除 identity 不匹配对象；报告 `validation_identity` / `validation_quarantine` 精确 stage 与 retained staging |
| validation recursive delete | `shutil.rmtree` 内对应 `os.open/scandir/unlink/rmdir` failure，分别覆盖 deletion 未开始与 partial deletion | pre-publication abort；报告 actual failing operation/path与 partial state；只保证 staging 可定位，不承诺完整取证树；public roots不变 |
| validation delete 后 POSIX sync | validation/quarantine 已删除后 staging-parent `os.fsync` 失败或 interrupt | pre-publication abort；staging/container 存在、validation child 与 quarantine 不存在；diagnostic=`validation_parent_directory_sync` + `deletion durability unconfirmed`；Windows 无此 unsupported fault point |
| secret persistence | POSIX profile replace/validation、Windows partial `setx` failure | 尚无 public replace；workspace不发布；只报告 env names，遵守 §5 注入 truth |
| public backup moves | 对 manifest 顺序中每个实际存在 root 的 `original -> unique backup` `os.replace`，分别在调用前/后注入 OSError/ENOSPC/interrupt | 对已移动 roots按逆序 `backup -> original`；未移动 root不动；成功 rollback 后 byte/identity等于 snapshot，POSIX sync workspace root |
| config publish | `staging config -> public config` replace 调用前/后 fault | 移除/隔离仅由本 transaction 发布的 public config，再逆序恢复 backups；FIRST 回到 config absent；不触碰 manifest 外 roots |
| POSIX publication sync | 全部 replace 后 workspace-root `fsync` fault | 尚未越过 success boundary，执行同一逆序 rollback并再次 sync；Windows boundary不包含不存在的 directory fsync |
| rollback | 删除 transaction-published config、每个 `backup -> original` replace、POSIX rollback workspace-root sync逐项 fault | typed rollback failure；报告精确 failed stage、当前每个 public root truth与仍存在 backup/staging path；不得声称完整恢复 |
| post-publication delete | 每个 backup/quarantine/staging cleanup 的 identity check、rename/delete 未开始或 partial failure | init仍成功；typed warning报告实际 retained/partial path与operation；不 rollback |
| post-publication POSIX sync | cleanup path已删除后 workspace-root `fsync` failure | init仍成功；报告 path已不存在 + `deletion durability unconfirmed`；不得声称 retained；Windows不伪造此 fault |

每个表中 replace/fsync 边界都覆盖一次普通 `OSError` 和一次 `KeyboardInterrupt`；ENOSPC只注入能实际抛出它的 write/copy/replace/fsync boundary，不为 syscall 添加 production seam。RESET 两根 snapshot 不是单 syscall 原子仍按 §10.1 retained residual，不新增 Host/process lock。

验证：

```bash
source .venv/bin/activate
pytest tests/cli/test_init_catalog.py tests/cli/test_init_environment.py tests/cli/test_init_workspace.py tests/cli/test_init_command.py tests/cli/test_arg_parsing.py tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_entrypoint_runtime_prompt_path.py -q
pytest tests/runtime/test_filelock.py tests/runtime/test_config_loader.py tests/runtime/test_scene_prepare.py -q
pytest tests/cli/test_init_catalog.py --cov=dayu.cli.init_catalog --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/cli/test_init_environment.py --cov=dayu.cli.init_environment --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/cli/test_init_workspace.py --cov=dayu.cli.init_workspace --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/cli/test_init_command.py --cov=dayu.cli.commands.init --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/cli/test_arg_parsing.py --cov=dayu.cli.arg_parsing --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/service/test_host_assembly.py --cov=dayu.service.host_assembly --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_entrypoint_runtime_prompt_path.py --cov=dayu.service.entrypoint_runtime --cov-report=term-missing --cov-fail-under=80 -q
python -m pyright dayu/ tests/ utils/
python -m ruff check dayu/cli/init_catalog.py dayu/cli/init_environment.py dayu/cli/init_workspace.py dayu/cli/commands/init.py dayu/cli/arg_parsing.py dayu/service/host_assembly.py dayu/service/entrypoint_runtime.py tests/cli/test_init_catalog.py tests/cli/test_init_environment.py tests/cli/test_init_workspace.py tests/cli/test_init_command.py tests/cli/test_arg_parsing.py tests/service/test_host_assembly.py
# 再执行 §9.2 的 full Ruff JSON fingerprint 比较，必须仍为 144/051bd6... 且 cmp 零差异
test "$(git diff --name-only -- dayu/service tests/service | sort)" = "$(printf '%s\n' dayu/service/README.md dayu/service/entrypoint_runtime.py dayu/service/host_assembly.py tests/service/test_host_assembly.py | sort)"
git diff --exit-code -- dayu/fins dayu/host dayu/engine dayu/tools dayu/runtime dayu/config/models.json dayu/config/prompts/manifests docs/fins/design.md docs/host/design.md docs/engine/design.md docs/tool/design.md docs/ui/design.md pyproject.toml utils
test -z "$(git status --porcelain=v1 -- dayu/fins dayu/host dayu/engine dayu/tools dayu/runtime dayu/config/models.json dayu/config/prompts/manifests docs/fins/design.md docs/host/design.md docs/engine/design.md docs/tool/design.md docs/ui/design.md pyproject.toml utils)"
git diff -- dayu/service/README.md
git diff --check
```

S2 review gate：Reviewer 必须逐状态和上述每个 fault row 审核 transaction，不接受仅看 happy path；必须核验 Fins root override precedence、raw config byte preservation、真实 Fins private side effect、public root byte/identity isolation、POSIX/Windows deletion capability、pre-publication validation cleanup fault与post-publication cleanup warning的不同边界。Service diff 必须精确限于 effective-config owner、ordinary caller、direct owner test和 owner README；Fins/package/Host/Engine/Tool/deferred ISSUE paths继续零 diff，且无 CLI-side Fins classification/raw stripping、synthetic provider/metadata-only/test shim。还要核验当前累积七个 production 文件各自单文件 coverage `>=80%`，其中 `commands/init.py` 只能引用 S2 当时已存在的 `test_init_command.py`，不得引用尚未创建的 S3 smoke。未 PASS 不进入 S3，禁止记录 gap 后延。

### S3 — 非网络 prewarm、真实 POSIX/Windows smoke、README 与 closeout

累积允许路径：S1/S2 全部路径，另加：

- 新增 `tests/cli/test_init_smoke.py`
- 新增 `.github/workflows/r12-init-windows.yml`
- 修改 `README.md`
- 修改 `dayu/config/README.md`
- 修改 `tests/README.md`

实现与 smoke：

1. 在 `commands/init.py` 接入 §7 exact-two-root import-only prewarm。FIRST/RESET 各一次，PRESERVE/OVERWRITE 零次，失败 warning 不改变 publish 结果。owner tests 与隔离 subprocess 必须证明只调用 `importlib.import_module`、不接受/读取 env 或 workspace、不调用任何 runtime assembly，并覆盖 exact roots、CURRENT transitive imports、deleted roots absent、连续两次稳定、零网络与零外部状态 mutation。
2. POSIX 真实 subprocess smoke 使用临时 HOME/workspace：以 Ollama 完成 FIRST；用真实 `ConfigLoader` 和 §6.4 scene validation 验证已发布配置（该验证不是 §7 prewarm）；添加 user manifest/文件并删除一个 package prompt，验证 PRESERVE；验证 OVERWRITE 恢复 package defaults；RESET No 前后整树 hash 相同；RESET Yes 重建；作为独立 reset boundary，预置 `portfolio/` 与 `assets/` sentinel 全程不变且 package 不创建 assets。另用非生产 sentinel 验证 profile marker/mode/脱敏。
3. 竞争 smoke 使用已有用户可见 waiting notification 作可观察协调，不新增 test protocol：test harness 先用真实 `file_lock` 持有 workspace `.dayu-init.lock`，再以完整 deterministic input 启动一个真实 `subprocess.Popen`，在 bounded read timeout 内等到该 CLI 的“正在等待此 workspace lock”通知后断言 config 尚未发布，随后释放 parent lock 并要求子进程成功退出。第二个场景在同一个 parent-held real lock 下启动两个真实 `Popen`，分别等到两者同一 public waiting notification 并确认零 publish 后才释放；两个 queued publishers 必须串行成功，最终配置由真实 `ConfigLoader` 读取。bounded timeout 只属于 test harness 的 read/process wait，用于令 hung test fail；production 始终是 `file_lock(..., timeout_seconds=None)`。禁止 `sleep`、timing luck、flaky marker、成功率/重试、finite production timeout、process-kill 协调、production-only sentinel 或 test shim。
4. `.github/workflows/r12-init-windows.yml` 使用 Windows + Python 3.11 + locked project dependencies，非 mock 地运行 FIRST→PRESERVE→OVERWRITE→RESET No→RESET Yes 正常 transaction 与真实 `ConfigLoader` 重载，证明缺少 POSIX directory fsync 不会永久拒绝普通 Windows init；记录 `shutil.rmtree.avoids_symlink_attacks` capability。job 必须在 scan 前预置 nested directory junction 指向外部 sentinel；按 §6.3.1，这一预置 reparse entry 必须令 transaction 在 publication 前 fail closed，typed diagnostic 必须如实报告当时实际 retained staging/quarantine path、absent path 与精确 failure stage，public config 不得发布，external sentinel 的 bytes 与 filesystem identity 必须不变。“只删除或拒绝 reparse entry 本身而不触碰 target”只可作为另一个 scan-delete race/syscall-fault 级证明，不能作为预置 junction 场景的同等成功标准。普通 symlink 仅在 runner 缺少 privilege 时按精确错误 skip，normal transaction/pre-seeded junction/root-identity/replace-failure rollback 与 scan-delete race/fault 证明不得 skip。额外用唯一 non-secret sentinel 执行真实 `setx`/user-env read/cleanup，严禁上传值。
5. Windows job 同时运行 R11 release blocker 的两个真实节点：
   - `tests/cli/test_upload_filings_from_command.py::test_windows_cmd_script_round_trips_adversarial_argv_with_real_cmd`
   - `tests/cli/test_upload_filings_from_command.py::test_windows_generated_script_runs_real_cli_into_temp_storage`
6. CI artifact 只允许测试报告、版本、文件 hash 与 env **names**；失败日志也不得 dump environment/registry values。
7. README 按各自 `Agent更新约束` 更新：根 README 只写最终用户 init 交互、四态、secret 目标/脱敏与排障，并明确 RESET 前必须停止 active Dayu 进程、`.dayu-init.lock` 只串行 init；`dayu/config/README.md` 写当前配置 owner、PRESERVE/OVERWRITE/RESET 与 manifest projection；`tests/README.md` 写 owner/fault/real-smoke 覆盖。无分层/装配边界变化，不修改 `dayu/README.md`；不修改 Host/Engine/Fins/config package README 之外的文档。

验证：

```bash
source .venv/bin/activate
pytest tests/cli/test_init_catalog.py tests/cli/test_init_environment.py tests/cli/test_init_workspace.py tests/cli/test_init_command.py tests/cli/test_arg_parsing.py tests/cli/test_init_smoke.py tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_entrypoint_runtime_prompt_path.py -q
pytest tests/runtime/test_filelock.py tests/runtime/test_config_loader.py tests/runtime/test_scene_prepare.py tests/runtime/test_scene_assets_migration.py tests/runtime/test_scene_tool_selection.py tests/runtime/test_tools_discovery.py -q
pytest tests/cli -q
pytest tests/cli/test_init_catalog.py --cov=dayu.cli.init_catalog --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/cli/test_init_environment.py --cov=dayu.cli.init_environment --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/cli/test_init_workspace.py --cov=dayu.cli.init_workspace --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/cli/test_init_command.py tests/cli/test_init_smoke.py --cov=dayu.cli.commands.init --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/cli/test_arg_parsing.py --cov=dayu.cli.arg_parsing --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/service/test_host_assembly.py --cov=dayu.service.host_assembly --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_entrypoint_runtime_prompt_path.py --cov=dayu.service.entrypoint_runtime --cov-report=term-missing --cov-fail-under=80 -q
python -m pyright dayu/ tests/ utils/
python -m ruff check dayu/cli/init_catalog.py dayu/cli/init_environment.py dayu/cli/init_workspace.py dayu/cli/commands/init.py dayu/cli/arg_parsing.py dayu/service/host_assembly.py dayu/service/entrypoint_runtime.py tests/cli/test_init_catalog.py tests/cli/test_init_environment.py tests/cli/test_init_workspace.py tests/cli/test_init_command.py tests/cli/test_arg_parsing.py tests/cli/test_init_smoke.py tests/service/test_host_assembly.py
# 再执行 §9.2 的 full Ruff JSON fingerprint 比较，必须仍为 144/051bd6... 且 cmp 零差异
git diff --check
```

S3 review gate：Reviewer 同时检查真实 smoke、七个累积 production 文件逐文件 coverage `>=80%`、docs/scans 和 Windows workflow；Windows normal transaction与junction/reparse sentinel必须有真实 job 证据。S3 可增加 smoke coverage，但不得修复或追认 S1/S2 已失败的早期 coverage gate。PASS 后只交 Controller checkpoint，不自行 close umbrella。

## 9. Coverage、全量验证与机械 scans

### 9.1 单文件覆盖率

聚合覆盖率不能替代单文件门槛。S1/S2/S3 各自验证块中的逐文件命令是当 slice 的强制 gate，只能引用该 slice 当时已经存在的测试；implementation artifact 必须记录每个新增/修改 production 文件的 `TOTAL`、`MISS`、百分比，分别达到 `>=80%`。下面是 S3 累积 final profile，不替代或延期 S1/S2 已列出的早期命令：

```bash
source .venv/bin/activate
pytest tests/cli/test_init_catalog.py --cov=dayu.cli.init_catalog --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/cli/test_init_environment.py --cov=dayu.cli.init_environment --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/cli/test_init_workspace.py --cov=dayu.cli.init_workspace --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/cli/test_init_command.py tests/cli/test_init_smoke.py --cov=dayu.cli.commands.init --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/cli/test_arg_parsing.py --cov=dayu.cli.arg_parsing --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/service/test_host_assembly.py --cov=dayu.service.host_assembly --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_entrypoint_runtime_prompt_path.py --cov=dayu.service.entrypoint_runtime --cov-report=term-missing --cov-fail-under=80 -q
```

若 coverage 插件把 imported support code 合并显示，仍须按模块分别运行，不能只报一个 package aggregate。

### 9.2 Full pyright zero 与 Ruff exact-baseline validation profile

R12 implementation entry 必须在任何 production/test 修改前捕获 full Ruff 原始 JSON 诊断集；该辅助文件只放 `workspace/tmp/`，不 stage/commit：

```bash
source .venv/bin/activate
python -m ruff --version
mkdir -p workspace/tmp
set +e
python -m ruff check dayu/ tests/ utils/ --output-format=json > workspace/tmp/r12-ruff-baseline.json
ruff_baseline_status=$?
set -e
test "$ruff_baseline_status" -eq 1
test "$(python -c 'import json,sys; print(len(json.load(open(sys.argv[1], encoding="utf-8"))))' workspace/tmp/r12-ruff-baseline.json)" -eq 144
test "$(shasum -a 256 workspace/tmp/r12-ruff-baseline.json | awk '{print $1}')" = "051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea"
```

每个 slice 结束时，先对当前累积 changed/new Python allowlist 运行 scoped Ruff 并要求 exit `0`/零诊断（S1/S2/S3 的精确 allowlist 已写在各自验证块），再执行 full fingerprint 比较：

```bash
set +e
python -m ruff check dayu/ tests/ utils/ --output-format=json > workspace/tmp/r12-ruff-current.json
ruff_current_status=$?
set -e
test "$ruff_current_status" -eq 1
test "$(python -c 'import json,sys; print(len(json.load(open(sys.argv[1], encoding="utf-8"))))' workspace/tmp/r12-ruff-current.json)" -eq 144
test "$(shasum -a 256 workspace/tmp/r12-ruff-current.json | awk '{print $1}')" = "051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea"
cmp workspace/tmp/r12-ruff-baseline.json workspace/tmp/r12-ruff-current.json
```

`cmp` 零差异是 full Ruff 通过条件：不仅数量仍为 144，每个 path/row/column/code/message/fix metadata 也不得新增、删除、移动或改写。这不是缩小 Ruff 命令：full command 每个 slice 都运行，只是如实接受 immutable base 的精确 144 诊断而要求 R12 零扩散。禁止清理这 144 项，也禁止用 ignore、配置排除、`noqa` 或更改 Ruff 版本/参数伪造 fingerprint。

Final tests/type/diff profile 仍为：

```bash
source .venv/bin/activate
pytest tests/cli -q
pytest tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_entrypoint_runtime_prompt_path.py -q
pytest tests/runtime/test_filelock.py tests/runtime/test_config_loader.py tests/runtime/test_scene_prepare.py tests/runtime/test_scene_assets_migration.py tests/runtime/test_scene_tool_selection.py tests/runtime/test_tools_discovery.py -q
python -m pyright dayu/ tests/ utils/
# 执行上述 S3 scoped Ruff + full Ruff fingerprint/cmp
git diff --check
```

Full pyright 不使用 baseline 例外；`python -m pyright dayu/ tests/ utils/` 必须 exit `0` 且零诊断。不得用 `type: ignore`、配置排除或缩小命令掩盖 R12 问题。任一 changed-path Ruff 诊断、full Ruff fingerprint 漂移或 full pyright 诊断都是停止条件，不授权扩大路径修复。

README 与边界核验：

```bash
rg -n "Agent更新约束|dayu-cli init|--reset|--overwrite|API_KEY|HF_ENDPOINT|HF_TOKEN|workspace_root|effective" README.md dayu/config/README.md dayu/service/README.md tests/README.md
git diff -- README.md dayu/config/README.md dayu/service/README.md tests/README.md
git diff --name-only
```

最终 source scans（每个命中逐项分类；预期 production 无禁止命中）：

```bash
rg -n "_init_model_role|default_name|llm_models|DAYU_INIT_PROVIDER_OPTION|workspace_migrations|migrat(e|ion)|compat|fallback|shim|hasattr\(|getattr\(" dayu/cli dayu/service/host_assembly.py dayu/service/entrypoint_runtime.py tests/cli tests/service/test_host_assembly.py README.md dayu/config/README.md dayu/service/README.md tests/README.md
rg -n "assets|portfolio|\.dayu|config" dayu/cli/commands/init.py dayu/cli/init_workspace.py tests/cli
rg -n "TAVILY_API_KEY|SERPER_API_KEY|FMP_API_KEY|HF_ENDPOINT|HF_TOKEN|MIMO_PLAN_API_KEY|MIMO_PLAN_SG_API_KEY|MIMO_API_KEY|DEEPSEEK_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|GEMINI_API_KEY|QWEN_API_KEY|CUSTOM_OPENAI_API_KEY" dayu/cli tests/cli README.md dayu/config/README.md
rg -n "authorization|authorisation|tool[_ -]?auth|permission" dayu/cli tests/cli
rg -n "assemble_effective_tool_provider_configs|discover_service_tools|SceneToolCatalog\.from_tool_bundle" dayu/cli/init_workspace.py dayu/cli/commands/init.py dayu/service/host_assembly.py dayu/service/entrypoint_runtime.py tests/cli/test_init_workspace.py tests/cli/test_init_command.py tests/service/test_host_assembly.py
rg -n "fins_workspace_root_override" dayu/cli dayu/service tests/cli tests/service utils
rg -n "_is_fins_workspace_bound_provider_config|financial-(read|download|preprocess|upload)-tools|dayu\.fins\.tools\..*provider|pop\([^)]*workspace_root|del [^\n]*workspace_root" dayu/cli/init_workspace.py dayu/cli/commands/init.py
rg -n "metadata[-_ ]?only|synthetic|fake[_ -]?provider|test[_ -]?shim" dayu/cli/init_workspace.py dayu/cli/commands/init.py tests/cli/test_init_workspace.py tests/cli/test_init_command.py
rg -n "prepare_entrypoint_runtime|compose_open_host_options|prepare_host_admin|build_fins_processor_registry|ServiceAssemblyOverrides|EntrypointRuntimeRequest|open_host|asyncio\.run" dayu/cli/commands/init.py
rg -n "importlib\.import_module|dayu\.cli\.commands\.(prompt|interactive|write)|dayu\.cli\.(dependency_setup|interactive_ui|session_execution)|dayu\.service\.entrypoint_runtime" dayu/cli/commands/init.py tests/cli/test_init_command.py tests/cli/test_init_smoke.py
rg -n "requests\.|httpx\.|urllib|socket|huggingface|download|web_search|open_host|run\(" dayu/cli/commands/init.py dayu/cli/init_catalog.py dayu/cli/init_environment.py dayu/cli/init_workspace.py
rg -n "Issue 142|Issue 151|Issue 175|Issue 177|Issue 178|Topic 8|Topic 9|Web|WeChat|render" dayu/cli dayu/service/host_assembly.py dayu/service/entrypoint_runtime.py tests/cli tests/service/test_host_assembly.py README.md dayu/config/README.md dayu/service/README.md tests/README.md
test "$(git diff --name-only -- dayu/service tests/service | sort)" = "$(printf '%s\n' dayu/service/README.md dayu/service/entrypoint_runtime.py dayu/service/host_assembly.py tests/service/test_host_assembly.py | sort)"
git diff --exit-code -- dayu/fins dayu/host dayu/engine dayu/tools dayu/runtime dayu/config/models.json dayu/config/prompts/manifests docs/fins/design.md docs/host/design.md docs/engine/design.md docs/tool/design.md docs/ui/design.md pyproject.toml utils
test -z "$(git status --porcelain=v1 -- dayu/fins dayu/host dayu/engine dayu/tools dayu/runtime dayu/config/models.json dayu/config/prompts/manifests docs/fins/design.md docs/host/design.md docs/engine/design.md docs/tool/design.md docs/ui/design.md pyproject.toml utils)"
```

解释标准：

- env 名称可出现，任何测试 sentinel 的 **值**、profile 内容或 subprocess captured output 不得进入 tracked artifact。
- `assets` 只允许“未创建/未删除”的断言和 README 边界。public `portfolio` 只允许独立 reset 保留与 validation isolation 断言；private `portfolio` 只允许 S2 测试证明真实 Fins side effect 已发生在 dedicated validation root 并被 transaction owner 安全清理，不得出现 prewarm side-effect 说明或 production 中对 public path 的硬编码删除。
- `compat/fallback/shim` 只允许测试证明不存在或 README 明确无兼容；production helper/name/comment 不得命中。
- authorization scan 应为空；Issue/Topic/Web/WeChat/render 不得产生新实现分支。`wechat` 的 exact manifest basename 是 §4.3 唯一允许的 production 命中。
- S2 real-validation positive scan 必须命中既有 Service effective assembly/discovery 与 `SceneToolCatalog.from_tool_bundle` 的唯一 production validation chain，并由 owner tests 证明 Fins effective root 是 transaction-private validation workspace；不得出现第二条 parser/provider chain。`fins_workspace_root_override` scan 的 production non-`None` consumer 必须只有 R12 init validation；ordinary `entrypoint_runtime` 必须显式 `None`，其它旧 utility/test callers只能消费 signature default。CLI classification/raw-strip scan production 必须为空；CLI 只可出现 override 参数名。negative scan 的 production 命中必须为空；测试命中只能是“禁止 synthetic/fake/metadata-only/test shim”的断言，不能以这些对象替代 13-manifest production discovery。Service exact diff必须仅为四个列名路径；Fins/package/Host/Engine/Tool/runtime/design/deferred ISSUE paths与 `utils` 的 tracked/untracked zero-diff命令必须通过。
- §7 forbidden runtime assembly-call scan 必须为空；测试命中只能是明确的 forbidden-call assertions。Import scan 的 production 允许项仅为 `importlib.import_module` 与 exact `dayu.cli.commands.prompt` / `dayu.cli.commands.interactive` roots；`session_execution` / `entrypoint_runtime` 只能作为测试对 CURRENT transitive graph 的断言，write/dependency_setup/interactive_ui 必须 absent。
- network scan 的标准库 `run(` 仅可对应 argument-safe `subprocess.run`；任何真实 network client/download/open Host/runtime assembly 命中均阻断。

## 10. 风险、停止条件与为何不过度设计

### 10.1 残余风险

- Windows `setx` 多变量写入不能跨调用回滚。R12 的正确 contract 是 config 不发布、只报告已写变量名；不伪造跨 OS transaction。
- 两个 managed roots 不能跨 root single-syscall 原子替换。R12 用 same-volume per-root replace、逆序 rollback 和故障测试提供 live-process 可恢复事务；RESET 两根 snapshot也不是单 syscall 原子。本轮不扩 Host/process lock，文案不得宣称更强保证。
- 真实 Service/Fins discovery 会在 effective root 创建 `.dayu` / `portfolio`。R12 不改变该 producer 语义；Service effective-config owner 的 validation-only override 无条件把合法 raw 未配置/绝对/相对 Fins root 定向到 transaction-private root，ordinary runtime继续保留显式配置。`init_workspace.py`只拥有 private container；identity/reparse/delete fault pre-publication abort并保留 truthful path，不触碰 public roots。
- POSIX 在直接支持时用 file/directory sync 建立 content 与 namespace crash-durability boundary。Windows Python 3.11 没有同等 parent-directory fsync contract；R12 诚实只承诺 staging file fsync、same-volume replace 的 process-visible atomic transition、live rollback、isolation 和 typed diagnostics，不承诺 power-loss 后 directory entry persistence。S3 real Windows normal transaction是 release evidence，不把该收窄伪装成 POSIX 等价。
- publication boundary 后 backup/quarantine/staging cleanup 可能失败。typed warning必须区分仍存在/partial path与已删除但 POSIX directory sync 未确认；已发布 config仍成功，不做反向 rollback。Windows正常 cleanup不声称 directory crash durability，也不因此产生虚假失败。
- import-only prewarm 依赖 Python 当前 import graph；`dayu.cli.main` 可能已通过正常命令注册加载相同 roots，因此 R12 只承诺 OLD-aligned import availability/稳定性检查，不承诺可测量的跨进程 cold-start 加速，也不为此新增 persistent cache/framework。
- CURRENT roots 的 transitive import 未来可能新增 import-time side effect；implementation tests 必须证明当前零网络、零 secret 需求、零 Dayu runtime/workspace mutation，漂移时停止而不是补 lifecycle/cleanup。
- `.dayu-init.lock` 只串行 init。若 active Host 或其它 Dayu 进程继续写 managed roots，RESET 仍可与外部 writer 竞争；当前 owner 是 reset 前强警告用户先停止它们，R12 不扩展到 Host lock/process discovery/kill。
- shell profile 可能包含无法安全管理的重复/损坏 marker。R12 fail closed，让用户显式修复；不做 loose repair。
- 三个 `smoke_host_public_*` package manifests 的 `manual-smoke` 选择只能由 test-owned catalog fixture 证明；production pre-publish 只对另外 13 个 runtime manifests 使用真实 Service discovery。该边界不降低全部 16 个 model projection 的 owner-level 测试要求，也不把测试工具提升为产品事实。
- repository full Ruff 的 144 个历史诊断归 repository owner；R12 只对 changed paths 零诊断和 full fingerprint 零差异负责，不清理或重分类历史基线。

### 10.2 必须停止并交 Controller 的条件

- 当前 schema 无法表达 catalog 指定的完整 dynamic record，OLD custom-hint 直接证据或 current-schema 投影已漂移，或真实 ConfigLoader/scene public seam 与 §4/§6.4 冲突。
- 13 个 production runtime manifest / 三个 `smoke_host_public_*` 的集合、tool tags 或 required context slots 不再精确等于 §4.3/§6.4 锁定值；或真实 Service effective-provider assembly/discovery 不再能从 staging `RuntimeConfig` 以 `workspace_root=<canonical public workspace>` 和 `fins_workspace_root_override=<recorded canonical absolute private validation root>` 装配 effective configs、让 override 无条件支配合法 Fins root并保留非 Fins ordinary public root，再经真实 `discover_service_tools(...)` 产生 `SceneToolCatalog.from_tool_bundle(...)`。
- 真实 discovery 的 `.dayu` / `portfolio` side effect 逃出 dedicated private validation root；Service override不能支配合法 raw 未配置/绝对/相对 Fins root；raw config bytes被改写；或 `init_workspace.py` 无法按 §6.3.1 platform contract identity/reparse-safe cleanup并在 public publication 前 fail closed。
- exact `dayu.cli.commands.prompt` / `dayu.cli.commands.interactive` roots 不存在、其 CURRENT `commands -> session_execution -> service.entrypoint_runtime` import graph 漂移，或 import 开始需要 secret/network/Dayu runtime state；不得引用 deleted write/placeholder、扩大 root list 或改成 runtime assembly。
- 除 `dayu/service/host_assembly.py` effective-config owner与 `dayu/service/entrypoint_runtime.py` ordinary caller外，还需要修改其它 Service production；或需要修改 `dayu/runtime/filelock.py`、`dayu/runtime/config_loader.py`、package `models.json`/manifests、Host/Engine/Fins/Tool production；或需要 metadata-only/synthetic/fake provider/test shim才可完成。
- 需要在未获用户明确选择时持久化 secret，或需要把 secret 写入 workspace/日志才能工作。
- 无法在单一 managed-root manifest 内实现 reset，或发现 public assets/portfolio 必须成为 managed root、必须清理 public Service/Fins path 才能完成。
- 需要旧 schema、migration、compat/fallback/shim、用户 manifest role 猜测、统一 tool authorization 或 Web/WeChat/render 行为变更。
- 起始 hashes/工作树 scope 漂移；full pyright 出现任一诊断；累积 changed-path Ruff 不是零；或 full Ruff JSON 不再是精确 `144`/`051bd6...` 且与 entry baseline `cmp` 不同。这些失败不授权修改 R12 allowlist 外路径。

### 10.3 为何不是过度设计

- 三个新模块分别承载已经存在且不可互换的三类 owner：静态选择事实、OS secret store、跨目录 transaction；orchestrator 只编排，不形成 God function。
- 没有引入通用配置 migration framework、通用 transaction engine、provider plugin registry、统一 authorization 或新公共 runtime abstraction。
- `filelock`、ConfigLoader 与 §6.4 real scene/tool validation 复用现有 owner；唯一 Service correction是在既有 Fins effective-config classification/precedence owner增加一个 direct `Path | None` 输入，普通 runtime显式不启用，R12 validation唯一启用。它不加 schema、provider framework、callback/factory或 Fins producer变化。Platform deletion只留在 `init_workspace.py` owner-local helper，不形成通用 FS framework；Windows不为 directory crash durability引入 Win32 wrapper。§7 只消费 Python模块 import graph，不调用 Service/Host/Engine/Fins runtime，不固定 public temp protocol、不造 magic timeout、不扩展 Host锁/进程治理、不发明 lifecycle/cache framework；package defaults不改。
- 三个 slices 按“纯 contract → 文件系统发布 → 实际入口/跨平台证明”累积，恰好隔离最高风险 seam，且没有超过用户规定的三个 slices。

## 11. Implementation completion report 与 Controller checkpoint

每个 slice 的 implementation artifact 必须包含：

- slice ID、实际 changed paths、变更前后 SHA-256；
- semantic owner/contract 是否按本计划实现，是否出现 stop condition；
- 精确测试/coverage/full-pyright-zero/changed-path-Ruff-zero/full-Ruff JSON count+SHA+`cmp`/diff/scans 命令、exit code 与结果；
- secret redaction、成功后 current-process env 可见性与 partial-failure no-injection、managed roots、完整 syscall fault matrix、13/3 manifest catalog boundary、Fins root override三态 precedence/raw-byte preservation、真实 Fins private side effect与public root byte/identity isolation、POSIX fd-safe/Windows reparse deletion证据、platform durability truth、Service exact owner diff、Fins/package/Host/Engine/Tool/deferred zero diff、无 CLI classification/raw stripping或synthetic/metadata-only/test shim、exact-two-root import-only prewarm/zero-network/zero-external-state guard、可观察 lock contention coordination、POSIX/Windows smoke 的证据；
- README 实际更新或按约束不更新的理由；
- residual risks 及 owner，不得用“后续再补”替代失败 gate；
- reviewer 结论与允许进入的下一 slice。

R12 implementation 全部通过后，Controller 只执行并记录：

```bash
git diff --check
git status --short
git diff --name-only
```

并核验 Windows normal transaction/junction/rollback workflow、R11 两个真实 `.cmd` 节点、七个 production 文件各自 `>=80%`、full pyright零诊断、changed-path Ruff零诊断、full Ruff精确 fingerprint零差异、Service owner README、其它 README 与 source/zero-diff scans。随后停在 Controller checkpoint，由 Controller决定 control更新、umbrella closeout与后续发布；AgentCodex不自行 stage/commit。

## 12. 上一轮 plan-fix gate 自检记录（历史）

本轮 immutable original 是 483 行 / 41,413 字节 / SHA-256 `6470ec0aafc8214e4fb3f0df88539e4ec97525b992e359bc4abbc75f06b2f5d0`。修复后行数、字节数与完整文件 SHA-256 由本轮 AgentCodex 在文件关闭后机械计算，写入单独 plan-fix artifact 并在 Controller handoff 报告；完整 SHA 不能写回被测 plan 自身而仍保持同一值。本 gate 只允许修改本 plan，并新增 `docs/reviews/wu-semantic-ownership-01-r12-init-workflow-plan-fix-codex.md`；Controller entry/validation/adjudication、两路 review、control、production、tests、README 均不得变化。

- 计划路径：`docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`
- 机械度量：见本轮终态 handoff；以 `wc -l`、`wc -c`、`shasum -a 256` 的最终输出为准。
- untracked whitespace check：要求 `git diff --no-index --check /dev/null <plan>` 无诊断（命令因存在新增 diff 返回 `1` 是正常，出现诊断才失败）。
- workspace diffcheck：要求 `git diff --check` 无诊断。
- scope check：要求相对 plan-fix entry status 只有本 plan 的内容变化和上述 plan-fix artifact 新增；不修改/stage 其它路径。
- design contradiction：`NONE`
- blocking questions：`NONE`
- 该轮 checkpoint：`Controller plan-fix validation`；其后同一 fixed-plan SHA 已交 AgentMiMo/AgentDS complete re-review，本节保留为历史 provenance，不代表当前 gate。

## 13. 上一轮 fixed-plan re-review finding fix 自检记录（历史）

- immutable before plan：558 行 / 56,459 字节 / SHA-256 `37b00dfa00d39fce4ac136e803002a6c0bd61faa86882819001f942dfe1df79b`。
- authority：corrected AgentMiMo re-review `a1812b6f7539ee252de27d01ad4a40382163dd7c5955cafe029720370f2aaac5`、corrected AgentDS re-review `f08584c337d910663003ab8be39c42371b8b1cd27e02b19d3f1a9640711e9381`、Controller adjudication `1f5142be9a4e5468625719be760e90e93e48d9093c633901849b65ff76bcadc9`。
- 该轮落实 `R12-RR-PF-01..05`：resolved `ModelsConfig` truth、13 个真实 runtime manifest / 三个 test-owned manual-smoke manifest boundary、public waiting notification 协调的 real-lock smoke、成功持久化后的 current-process env 与当时的 prewarm 裁决、每 slice 当时可执行的逐文件 `>=80%` coverage；prewarm 部分已由 §14 的 CURRENT direct contradiction follow-up 取代。
- rejected/no-fix candidate `R12-RR-04` 保持拒绝：`dayu/config/README.md` 已拥有 package defaults、workspace overlay 与 init 用户工作流，R12 保留其 S3 更新范围；README trigger 不是排他授权清单。
- §1.3 的 Issue 142/151/175/177/178、Web/WeChat/render、Topic 8/9 no-scope，§10 的 security/deferred owner boundaries，以及此前拒绝的 Ruff cleanup、public temp protocol、finite production lock timeout、Host lock/process kill 全部保留。
- 本 gate 只允许修改本 plan，并新增 `docs/reviews/wu-semantic-ownership-01-r12-init-workflow-plan-rereview-fix-codex.md`；不得修改 control、既有 artifacts、production、tests、README、design/workflow，不 stage/commit。
- after plan 与新 artifact 的最终行数、字节数、SHA-256 只能在文件关闭后机械计算，并记录在本轮 artifact / Controller handoff；完整文件 SHA 不写回自身。
- 两文件分别要求 `git diff --no-index --check /dev/null <path>` 无 whitespace 诊断（新增 diff 返回 `1` 正常）；workspace 要求 `git diff --check` 无诊断；staged diff 必须为空。
- design contradiction：`NONE`；blocking questions：`NONE`。
- 该轮 checkpoint：`Controller fixed-plan re-review-fix validation`；Controller 完整读取后发现 §7 CURRENT contradiction，因此本节只保留历史 provenance。

## 14. Controller CURRENT-contradiction follow-up 自检记录

- immutable before plan：596 行 / 68,137 字节 / SHA-256 `4982cb476d5346559540a73bc245fabd0878cddd173cac1c8a7072c9249ca830`。
- immutable before rereview-fix artifact：151 行 / 13,304 字节 / SHA-256 `defefb9f0fc5cba4cf14cc39f42ad068afe484798b663d027aac9ddafc2c65fd`。
- CURRENT contradiction：ordinary selection 可消费 scene/ordinary override；compactor selection 只消费四个 profiles 均为 `deepseek-v4-flash` 的 `compactor_baseline.model_id`，且无 compactor override。非 DeepSeek selected-pair env 无法满足真实 assembly，R12 又无权改 execution profiles/Service/Host。
- OLD direct evidence：SHA-locked `_run_init_prewarm` 只循环 `importlib.import_module`；CURRENT exact roots 只保留真实 `dayu.cli.commands.prompt` / `dayu.cli.commands.interactive`，其 normal import graph 自有 `dayu.cli.session_execution -> dayu.service.entrypoint_runtime` transitive loading。Init 不复制 transitive graph、不调用 assembly、不引用 deleted write/placeholder。
- 本 follow-up 只允许修改本 plan 与既有 `docs/reviews/wu-semantic-ownership-01-r12-init-workflow-plan-rereview-fix-codex.md`；不得修改 control、其它 reviews/artifacts、production、tests、README、design/workflow，不 stage/commit。
- after plan/artifact 的最终行数、字节数、SHA-256 只能在两文件关闭后机械计算；两文件分别要求 no-index whitespace check 无诊断，workspace `git diff --check` exit 0，staged diff 为空。
- design contradiction：`NONE`；已由 CURRENT/OLD 直接证据确定唯一最小 import-only contract；blocking questions：`NONE`。
- 下一 checkpoint：`Controller fixed-plan re-review-fix follow-up validation`；禁止进入 implementation。

## 15. R12 S2 stop-condition plan correction 自检记录

- gate：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` / R12 S2 的 plan-only correction，不是新 WU；唯一 finding 是 accepted HIGH `R12-S2-IMPL-STOP-F01`。
- immutable before plan：608 行 / 71,044 字节 / SHA-256 `69ddfd888336cbb70d093743a96a56f18e694fa68436fb086be1c9b56dcb88c2`。
- authority：更新后的 S2 authorization SHA-256 `259abecca9fb36112013dcc3be72320d9fe824604ca39eeddb44936f779c2f86`；implementation stop handoff SHA-256 `b123dff616a0c4ac22bb3d1f47b00fe5913a9747e9f3e413ff34462ddbd82fcd`；Controller adjudication SHA-256 `f2bb4029d83716e5e2a18e16fe1ac8c7970db7396adf54e951d9378ae4e3785c`。
- correction：保留 staging `RuntimeConfig`、真实 Service effective assembly/discovery、`SceneToolCatalog.from_tool_bundle`、13/3 manifest boundary 与两个 required slots；只把 assembly `workspace_root` 从 public workspace 改为 transaction private staging 内 dedicated validation root，并把该 private container 的 identity-locked/no-follow cleanup + parent `fsync` 固定为 config publication 前的 transaction owner gate。
- failure boundary：private validation cleanup/parent-fsync fault 必须 pre-publication abort，保留并报告可定位 transaction-private staging path；post-publication backup cleanup 仍是 typed warning。两者不共用语义，任何路径都不清理 public `.dayu` / `portfolio` / `assets`。
- retained scope：产品裁决、FIRST/PRESERVE/OVERWRITE/RESET 四态、S1/S3、managed-root manifest、Service/Fins production、package manifests、README、control 与其它 artifacts 均不改变；不允许 synthetic/fake provider、metadata-only discovery、duplicate parser、fallback/compat 或 test shim。
- 本 gate 只修改本 plan，并只新增 `docs/reviews/wu-semantic-ownership-01-r12-s2-stop-condition-plan-fix-codex.md`；不得修改 product/test/control/既有 artifacts，不运行 implementation tests，不 stage/commit/push/开 PR。
- after plan 的最终行数、字节数与 SHA-256 只在文件关闭后机械计算并记录到上述新 artifact，避免 plan 自引用 hash。
- design contradiction：`NONE`；blocking questions：`NONE`。
- 下一 checkpoint：`Controller R12 S2 stop-condition corrected-plan validation`；当前禁止 implementation、双路 re-review、S3、aggregate 与 commit，后续 gate 只能由 Controller 授权。

## 16. R12 S2 corrected-plan review-fix 自检记录

- gate：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` / R12 S2 corrected-plan 的 plan-only review-fix，不是新 WU/sub-WU，不授权 implementation。
- immutable before plan：634 行 / 81,713 字节 / SHA-256 `1f4df5f942a49a5c95bd60f75d0ef3e8a3cbfacede2c2d8f7ecf3c42a1436715`。
- authority：AgentMiMo final review `b59e529f6371cee21279124cfe3b8d2e7f7d3c013eab8396652e641563e9bec4`、AgentDS final review `b8e4773047caade4020a1d55847a87bfad47918c2ea33da5ae41b210b3425c32`、Controller adjudication accepted groups `R12-S2-PR-F01..F06`。
- F01：§3/§6.4/§8/§9 把 validation-only Fins root override 放在既有 Service effective-config owner；ordinary runtime显式 `None`并保留 raw explicit root，R12 override支配合法未配置/绝对/相对 raw root且不改 bytes/schema；CLI不猜 provider、不 strip config。S2 exact allowlist加入唯一 Service owner/caller/direct test/README，Fins/package/Host/Engine/Tool/deferred paths继续零 diff。
- F02：§8 明确 `pytest.monkeypatch` / `unittest.mock` syscall fault injection不属于 provider/catalog test shim，禁止 production callback/factory/default-callable seam，并枚举 validation cleanup、publication、rollback与post-publication cleanup精确 fault matrix。
- F03：§6.3.1/§6.4/§8 固定 validation tree已删而POSIX parent sync失败时 retained truth仅为仍存在的 staging/container；child absent、`deletion durability unconfirmed`与精确 stage/path进入 typed diagnostic/test。Partial delete只承诺 retained path + failure stage，不承诺完整取证树。
- F04：§6.3.1 基于 Python 3.11 direct evidence区分 POSIX fd-safe capability与Windows junction/reparse contract；Windows `avoids_symlink_attacks=False`不导致正常 init永久失败，使用 owner-local quarantine/identity/reparse-safe path与真实 junction external-sentinel job，不建通用 FS framework。
- F05：§6.3.2/§6.4/§8 精确区分 file content、directory entry、secure deletion、per-root replace与rollback；POSIX拥有文件/目录 sync boundary，Windows保留普通文件 fsync、same-volume replace、live rollback、isolation和typed diagnostics，但诚实不承诺等价 parent-directory crash durability。S3 real Windows job必须跑正常 transaction。
- F06：§8/§9 exact Service allowlist、override consumer scan、CLI provider-classification/raw-strip negative scan与 Fins/package/Host/Engine/Tool/runtime/design/deferred zero-diff范围已同步；七个累积 production文件逐文件 coverage与 README trigger已更新。
- rejected/no-fix 保持：不为 partial delete复制/预快照完整 forensic tree；不把 RESET 两根 snapshot扩为 single-syscall atomic，不新增 Host/process lock、kill、watcher。Issue 142/151/175/177/178、Web/WeChat/render与统一 tool authorization仍不实施。
- §15 是上一轮历史 provenance；其中 Service production零 diff只描述当时 gate，已由本节 accepted F01 owner correction明确取代。S1→S2→S3仍恰好三个 cumulative slices，无新增 slice/sub-WU。
- 本 gate 只允许修改本 plan，并只新增 `docs/reviews/wu-semantic-ownership-01-r12-s2-stop-condition-plan-review-fix-codex.md`；不得修改 control、其它 review、product/test/README/workflow，不 stage/commit/push。
- after plan/artifact 的最终行数、字节数与 SHA-256 仅在文件关闭后机械计算；plan after identity写入新 artifact，不把完整 SHA写回 plan形成self-reference。
- design contradiction：`NONE`；blocking questions：`NONE`；accepted closure：`6/6`。
- 下一 checkpoint：`Controller validation`；禁止直接进入 implementation。
