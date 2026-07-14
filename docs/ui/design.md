# UI And CLI Design

本文是 UI / CLI 产品入口的稳定设计真源。UI 位于 `UI -> Service -> Host -> Engine`
最上层，拥有公开命令、参数、用户工作流、输出通道和交付状态；它不得绕过 Service
装配直接依赖 Host、Engine 或 Fins storage 实现。

Host / Engine / Tool / Fins 的设计分别归 `docs/host/design.md`、
`docs/engine/design.md`、`docs/tool/design.md` 与 `docs/fins/design.md`。UI 只能消费这些
层提供的 public typed contract，不得从内部字段、日志、路径、状态文本或测试 fixture
反推业务事实。

## 1. Public Entrypoint Lifecycle

只有具备真实可运行能力的入口才进入 package scripts、根 README、公开 help grammar 与
public entrypoint tests。一个尚未实现的能力可以由 GitHub Issue 追踪，但不得用占位命令
提前冻结未来的子命令、参数、位置参数、退出码、unavailable 文案或安装 extras。

Web、WeChat 与 render 都已有独立 ISSUE 追踪。当前 WU 不通过仅支持 `--help` 和
unavailable diagnostic 的 `dayu-web`、`dayu-wechat`、`dayu-render` 占位入口定义未来
产品 contract。对应 ISSUE 实现真实能力时，必须在同一 WU 中完成：

- 产品入口及其参数/输出设计。
- `UI -> Service -> Host` 的真实调用链；render 若是纯本地转换器，也必须明确自己的
  输入、输出与资源 owner，不得伪装成已接通 Service 的入口。
- package scripts、安装依赖、README、help、成功/失败路径与 smoke tests。

Web 入口由 GitHub Issue [#84](https://github.com/noho/dayu-agent-r/issues/84) 追踪；
WeChat 入口由 GitHub Issue [#147](https://github.com/noho/dayu-agent-r/issues/147)
追踪。Render 使用用户确认的既有独立 ISSUE，不在当前 WU 另造 grammar 或重复 issue。

## 2. `upload_filings_from`

`upload_filings_from` 是必须实现的 CLI 能力，不属于未实现入口。它的产品行为对齐 OLD
`/Users/leo/workspace/dayu-agent`：扫描指定目录、识别和分类 filing/material，并生成适配
当前平台的可执行批量上传脚本；命令本身不直接上传文件。

Fins 拥有文件识别、财期/material 分类、去重、过滤与 typed batch plan。CLI 拥有命令行
参数、脚本路径、平台脚本格式、argv quoting、用户可读生成结果。CLI 不得重复实现 Fins
分类规则，Fins 也不得依赖 CLI parser 或拼接命令行。

稳定行为如下：

- macOS/Linux 生成可执行 shell script，Windows 生成 `.cmd` script；参数必须使用平台
  正确 quoting，路径中的空格、引号及 shell 特殊字符不得改变 argv 边界。
- `--output` 指定脚本路径；未指定时在 `--base` workspace root 下生成包含 ticker 的默认
  文件名。
- 生成脚本的每条命令调用当前受支持的 `upload_filing` / `upload_material` 公共 CLI，保留
  batch plan 中的 ticker、action、files、财期、日期、amended、company/material metadata。
- 命令输出生成位置以及 recognized/material/skipped 的用户可读摘要，便于用户检查后执行。

当前实现新增的 `{schema_version: 1, commands: [argv...]}` 不是产品需求，也没有独立机器
consumer，因此不作为公共 batch/replay contract 保留。生成脚本中的 argv 是当前 CLI
grammar 的执行投影，不是第二份 versioned public schema。未来若需要机器消费的 batch API，
必须先定义 domain entry schema、consumer、版本 owner 与执行/失败语义，不能直接把 CLI argv
数组当作领域协议。

OLD 只作为该用户工作流的产品行为参考；当前实现仍必须遵守本仓库的 Service/Fins 边界、
严格类型、错误 contract 和测试约束，不迁移 OLD 的旧架构或兼容分支。

## 3. `dayu-cli init`

`dayu-cli init` 的用户工作流对齐 OLD `/Users/leo/workspace/dayu-agent`，但配置字段与
实现边界必须使用本仓库当前 schema 和分层。它不是只复制文件的非交互式命令；首次安装或
重新配置时还负责引导用户选择 provider/model 方案、配置该方案需要的 API Key、更新 workspace
scene manifest 的默认模型，并询问可选 Web/FMP/HuggingFace 配置。Secret 只写入用户明确选择的
系统环境变量持久化位置，不写进 workspace JSON、Host durable state、日志或 LLM-facing 文本。

Init 把当前 package config 与 prompt assets 安装到 `<workspace_root>/config`。若当前产品包提供
其它明确的 workspace bootstrap assets，init 同步安装；当前仓库没有 `dayu/assets`，不得仅为
形式对齐从 OLD 搬入尚未实现的 write/template 产品能力。Write 与其 assets 由 GitHub Issue
[#151](https://github.com/noho/dayu-agent-r/issues/151) 追踪。

无 `--overwrite` 且 config 已存在时，保留用户配置，并只补齐 package 新增而 workspace 缺失的
prompt assets，然后继续交互配置流程。`--overwrite` 明确要求用当前 package defaults 重建
config tree，再应用本次交互选择；它不是逐文件兼容 merge。

配置集合可能跨多个文件共同生效，因此 config 安装/overwrite 保留整棵 tree 的
stage/swap/rollback：

- 在同一 workspace filesystem 内建立私有 staging tree。普通缺失-asset 同步以现有 config
  为输入；`--overwrite` 以当前 package defaults 为输入。
- 所有 staging 写入成功后才替换最终 config tree；已有 tree 先移动到私有 backup。
- 最终替换失败或安装阶段被中断时恢复原 tree；成功后清理 backup，失败路径清理 staging。

Reset/bootstrap 与未来 migration 必须受同一个 workspace-level exclusive lock 保护，避免两个
init 进程交错删除、复制和修改配置。Workspace migration framework 继续由已存在的 GitHub
Issue [#142](https://github.com/noho/dayu-agent-r/issues/142) 追踪；本 WU 不重复实现该 issue，
也不把 OLD 的具体 migration 或旧 schema compatibility 搬进 init。

Init 只能修改和删除明确列出的 Dayu-owned workspace 路径。所有目标必须同时满足 lexical
containment 与 resolved containment；目标路径或其已有祖先/子树包含 symlink 时 fail closed，
不得沿 symlink 写入或递归删除 workspace 外部内容。该 containment/symlink 规则是 init
filesystem mutation 的 correctness 与局部安全边界，最终 closeout 必须单独列为安全相关行为。

`--reset` 是显式破坏性操作。它必须先向用户列出目标并取得明确确认，然后按 OLD 语义删除
`<workspace_root>/.dayu`、`<workspace_root>/config`，以及当前产品存在时的
`<workspace_root>/assets`，再按首次初始化流程重建。`.dayu` 整体是 Dayu-owned 可重建运行态
根，因此 reset 会删除 Host/runtime/CLI/artifact 以及
`<workspace_root>/.dayu/web_tools_storage_states`；不得删除 `portfolio` 或其它用户业务文件。

Browser storage-state lifecycle 已延后到 GitHub Issue #178，但这不妨碍 `init --reset` 删除
Dayu-owned `.dayu` 中的该目录。显式全量 workspace reset 只表达“清空可重建 Dayu state”，
不拥有 storage-state 的命名、TTL、刷新、并发发布、credential/session 或日常 cleanup 语义。

OLD 的首次运行 prewarm 保留为 init 用户工作流的一部分，但 prewarm 失败只能形成明确 warning，
不能把已经成功安装的配置伪装成失败或留下半写配置。Provider 菜单、模型组合和 API key ref
必须从一个 init-owned typed catalog/contract 产生；不得让 CLI、README 和测试各自维护不一致的
硬编码方案列表。

Whole-tree staging、backup 名称与临时目录布局是实现细节，不是 LLM-facing 或跨版本公共
协议。稳定承诺只有：目标范围明确、安装不留下半更新 config、失败恢复旧状态、路径不逃逸。
