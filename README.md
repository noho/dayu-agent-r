# 大愚 Agent — 用户手册

`大愚 Agent` 是面向买方财报分析的通用 Agent。当前可用的用户入口集中在
`dayu-cli`：可以初始化工作区、下载或上传财报、预处理文档、进行单次问答、
多轮交互，以及查看和清理 CLI Session。

本文档面向最终使用者。

## Agent更新约束【必须遵守】

- 本文档是最终用户使用手册，只写用户完成安装、初始化、配置、财报下载 / 上传 / 预处理、提问、交互式分析、Session 管理、查看日志与排障所需的当前可用操作。
- 更新本文档时必须先核对当前 CLI / Web / WeChat 入口、参数解析、用户可见输出和对应实现；代码真源高于设计文档和历史说明。
- 本文档可以写面向用户的命令、参数、工作区文件位置、输出文件位置、日志定位方式、常见错误和排障步骤。
- 不写 Host / Engine / Service / Runtime / Fins 内部架构、公共契约细节、状态机、测试清单、代码阅读顺序、review / work unit 过程状态或开发者迁移计划。
- 不写未来计划、未落地能力或内部治理术语；若必须提到尚未实现的用户入口，只能作为用户可见限制简短说明。
- 涉及开发者架构、包边界或代码阅读路径时，链接到 `dayu/README.md` 或对应子包 README，不在本文档展开。

开发文档入口：

- [整体架构](dayu/README.md)
- [配置手册](dayu/config/README.md)
- [Engine 手册](dayu/engine/README.md)
- [Host 设计](docs/host/design.md)

## 1. 安装

项目默认和依赖锁定环境是 Python 3.11。Docling 模型栈统一约束为
`transformers>=4.57.6,<5.0.0`；不要在受控约束上另行升级到 Transformers 5.x，
否则使用 `torch 2.2.x` 的 macOS Intel 环境无法运行 Docling。

### 1.1 从源码安装

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test,dev,browser]" \
  -c constraints/lock-macos-arm64-py311.txt
```

按平台替换约束文件：

- macOS Intel：`constraints/lock-macos-x64-py311.txt`
- Linux x64：`constraints/lock-linux-x64-py311.txt`
- Windows x64：`constraints/lock-windows-x64-py311.txt`

如果需要浏览器回退抓取，再安装 Chromium：

```bash
playwright install chromium
```

### 1.2 安装 wheel

```bash
python3.11 -m pip install /path/to/dayu_agent-<version>-py3-none-any.whl
```

安装后确认公开入口：

```bash
dayu-cli --help
```

## 2. 初始化工作区

```bash
dayu-cli init
```

`init` 会交互选择一组普通/思考模型，并把当前配置与 prompt assets 发布到
`./workspace/config/`。Ollama 与 OpenAI-compatible 自定义模型会继续询问模型名、
endpoint 和上下文窗口；其它选项使用内置的当前模型目录。初始化会用真实配置加载和
scene 校验拒绝无效结果，但不会探测 endpoint、下载模型或发起网络请求。

常用形式：

```bash
dayu-cli init --base ./my-workspace
dayu-cli init --base ./my-workspace --overwrite
dayu-cli init --base ./my-workspace --reset
```

`init` 通过 `--base` / `-b` / `--workspace` 选择工作区；不传时使用
`./workspace`。配置固定读取该工作区的 `config/`，不存在时使用包内默认配置。

`init` 只有以下四种状态：

- FIRST：`config/` 不存在且未传覆盖参数，从包内默认配置开始创建。
- PRESERVE：`config/` 已存在且未传覆盖参数，保留用户配置、文件和自建 manifest；补回
  缺失的五个根配置文件与包内 prompt 文件，并把本次明确选择投影到已知模型/manifest
  字段。已经存在的文件不会被补缺步骤覆盖。
- OVERWRITE：传 `--overwrite`，从包内默认配置完整重建 `config/`，不合并旧配置。
- RESET：传 `--reset`，先列出实际存在的 `.dayu/`、`config/` 并默认选择 No；明确确认后
  移走整个 `.dayu/` 与旧 `config/`，再从包内默认配置重建。RESET 优先于 `--overwrite`。

四种状态都不会创建、删除或重建 public `portfolio/`、`assets/`。为防止写出工作区，
workspace、锁文件、受管树或其子树中的 symlink / Windows reparse entry 会被拒绝。
无覆盖参数时，普通文件占据 `config` 或 `.dayu` 也会被拒绝；`--overwrite` 可以重建被
普通文件占据的 `config`，`--reset` 可以重建被普通文件占据的 `config` 与 `.dayu`。
symlink、dangling symlink、special file 和非法 lock identity 在所有模式下都拒绝。

模型选择、动态模型名、endpoint、上下文窗口、secret 与 yes/no 输入不合法时会在当前
提示重新输入。RESET 确认输入 No 或直接按 Enter 时退出 `0` 且不修改工作区；输入 EOF
时退出 `1`，按 `Ctrl-C` 时退出 `130`。需要持久化必需 secret 时，最终确认输入 No、
直接按 Enter 或 EOF 都表示初始化未完成并退出 `1`，按 `Ctrl-C` 退出 `130`；这些路径
都不会发布部分配置。

当所选模型需要 API Key 且当前进程没有对应变量时，`init` 在真实终端（TTY）隐藏输入值；
stdin 被重定向时，每个 secret 提示写入 stderr，并从 stdin 逐项读取一行，CLI 不把值写回
stdout/stderr。两种方式都在一次最终确认中只展示目标与变量名。POSIX 写入当前 shell 对应的
`~/.zshrc` 或 `~/.bashrc` 的唯一 managed block；Windows 使用当前用户的 `setx`。可选集成只包括
`TAVILY_API_KEY`、`SERPER_API_KEY`、`FMP_API_KEY`、`HF_ENDPOINT`、`HF_TOKEN`。默认 No；拒绝或
持久化失败时不会发布 workspace 配置。secret 值不写入 workspace，也不进入成功/失败输出。

FIRST/RESET 发布成功后会在当前进程中导入 `prompt` 与 `interactive` 入口以减少首次冷启动；
该步骤不读取 workspace/env、不装配运行时、不联网。若出现 `prewarm warning`，配置仍已成功
发布，后续命令会按正常导入路径启动。

`.dayu-init.lock` 只用于串行多个 `init`，不会锁住正在运行的 CLI/Web/WeChat/Host。
执行 RESET 前必须先停止这个 workspace 的所有 active Dayu 进程；等待锁时可根据
`正在等待此 workspace lock` 提示确认命令尚未进入发布阶段。

初始化后的主要目录：

```text
workspace/
├── config/       # 配置 overlay 与 prompt assets
├── portfolio/    # 已导入的财报和材料
└── .dayu/        # Session、运行期状态与 artifacts
```

也可以在运行 `init` 前自行设置 API Key。具体模型引用哪个变量，以
`workspace/config/models.json` 为准。例如：

```bash
export MIMO_PLAN_API_KEY="..."
export FMP_API_KEY="..."       # 可选：为 ticker context 补充公司名
```

包内默认普通问答与会话压缩都使用 Mimo Token Plan 模型家族。`init` 选择的普通/思考
模型会投影到全部包内场景，会话压缩与该选择使用相同的 provider、provider 模型、
endpoint 和 credential 引用，但可以使用不同的采样与流式参数。

## 3. CLI 公共命令

```bash
dayu-cli <command> [参数]
dayu-cli <command> --help
```

当前命令：

| 命令 | 当前行为 |
|---|---|
| `init` | 初始化或重置工作区配置 |
| `prompt` | 提交一次财报分析问题 |
| `interactive` | 进入多轮终端交互 |
| `download` | 下载指定主体的财报 |
| `upload_filing` | 上传或管理单份 filing |
| `upload_material` | 上传或管理补充材料 |
| `upload_filings_from` | 扫描目录并生成可执行的批量上传脚本 |
| `process` | 预处理某主体的文档 |
| `process_filing` | 预处理单份 filing |
| `process_material` | 预处理单份 material |
| `session` | 列出、恢复或清理 CLI Session |
| `tool_trace` | 分析 Tool Trace 并发布诊断报告 |

### 3.1 全局路径与日志参数

| 参数 | 说明 |
|---|---|
| `--base` / `--workspace` | 工作区根目录，默认 `./workspace` |
| `--log-level LEVEL` | 可选 `debug`、`verbose`、`info`、`warning`、`error`、`critical`、`quiet`；`warn` 与 `warning` 等价 |
| `--debug` / `--verbose` / `--info` / `--warning` / `--error` / `--critical` / `--quiet` | 对应日志等级的快捷参数；同时保留与 `--warning` 等价的 `--warn` |
| `--debug-stream` | 额外打开高频 stream/SSE 诊断，不改变普通日志等级；不可与 `quiet` 组合 |
| `--log-file PATH` | 把诊断日志追加写入指定文件；可与任意合法日志等级选择组合 |

`--log-level` 和所有日志等级快捷参数彼此互斥，一次调用只能选择其中一个。
`--debug-stream` 可以单独使用，也可以与 `debug`、`verbose`、`info`、`warn` / `warning`、
`error` 或 `critical` 组合。

用户可见回答和进度仍写 stdout/stderr。未传 `--log-file` 时，诊断日志只保留到
当前 CLI 进程结束；需要排障留档时必须显式指定路径：

```bash
dayu-cli prompt "总结主要风险" --ticker AAPL \
  --debug --log-file workspace/prompt.log
```

`--log-file` 不会创建缺失的父目录；请先创建父目录。父目录不存在或目标无法打开时，
CLI 会显示可操作的错误并退出 `1`，不会开始本次分析。

## 4. 问答与交互

### 4.1 单次问答

```bash
dayu-cli prompt "总结最新财报的主要风险" --ticker AAPL
```

`--ticker` 可省略。提供后，它既进入 CLI 请求身份，也通过共享 scene context
作为模型可读的“当前分析对象”；若显式配置了有效 `FMP_API_KEY`，context 会尝试
补充公司名，解析失败时仍保留 ticker。

常用参数：

- `--label LABEL`：绑定或复用 prompt Session。
- `--model ID` / `-m ID`：只覆盖本次主 Run 的模型配置；不写入 workspace，也不改变
  会话压缩模型。即使本次主 Run 显式选择不同的 provider family，会话压缩仍使用
  `init` 选择的 family；未执行 `init` 时使用包内默认 family，不跟随单次 override。
  `interactive` 与 `session resume` 使用相同参数。
- `--temperature FLOAT`、`--tool-timeout-seconds FLOAT`、`--max-iterations INT`：
  覆盖本轮执行参数。
- `--thinking` / `--no-thinking`：控制运行态思考展示。
- `--detail` / `--no-detail`：控制 activity stream 展示。

### 4.2 多轮交互

```bash
dayu-cli interactive
dayu-cli interactive --label earnings
```

不传 `--label` 时，每次启动创建一个新的未绑定 Session；传入 label 时复用
`cli.agent.<label>` 对应 Session。`prompt --label earnings` 与
`interactive --label earnings` 使用同一个 label owner 和同一个 Session；旧
`cli.prompt.*` / `cli.interactive.*` slot 不会被自动读取或迁移。`interactive`
不接受 `--ticker`；需要指定分析主体时，请直接写在本轮输入中。

TTY 输入中，Enter 提交，`Ctrl+J` 或支持 xterm Shift+Enter 序列的终端插入换行；
运行期间键入的 draft 会保留到当前任务收口，Enter 最多排入一个后续问题并在当前任务
终态后执行。独立 Escape 或第一次 `Ctrl+C` 请求取消当前任务；取消收口期间再次
`Ctrl+C` 只登记“收口后退出”，CLI 仍会等待当前 canonical terminal 和已经 accepted
的唯一后续任务完成，再以 130 退出。CSI、Alt 和 bracketed paste 不会因 Escape 前缀
误触发取消。

空闲且输入为空时，`Ctrl-D` 正常退出；运行期间 `Ctrl-D` 不取消任务。stdin 不是 TTY
时，`interactive` 会读取整个 UTF-8 输入流，只做一次提交，不显示提示符，也不把换行
拆成多个 Run；空白流不提交，非法 UTF-8 作为稳定用法错误退出。

交互会话可以按问题需要下载财报、列出已入库文档并读取财报内容，但不在会话中执行
预处理。需要预处理时，请使用第 5.4 节的 `process`、`process_filing` 或
`process_material` 独立命令。

## 5. 下载、上传与预处理

### 5.1 下载

```bash
dayu-cli download --ticker AAPL
dayu-cli download --ticker AAPL --forms 10-K 10-Q --start 2024 --end 2025
dayu-cli download --ticker 600519 --forms FY H1 --start 2024
dayu-cli download --ticker 0700 --rebuild
```

可用参数以 `dayu-cli download --help` 为准：`--forms`、`--start`、`--end`、
`--overwrite` 和 `--rebuild`。下载、上传和预处理命令会输出 direct progress 与
终态摘要；`Ctrl-C` 请求取消当前 direct operation。财报保存在
`<workspace>/portfolio/<规范 ticker>/`，例如 AAPL 对应
`workspace/portfolio/AAPL/`。

### 5.2 上传单份 filing 或材料

```bash
dayu-cli upload_filing \
  --ticker AAPL \
  --action create \
  --files ./AAPL-2024-10K.pdf \
  --fiscal-year 2024 \
  --fiscal-period FY \
  --company-name "Apple Inc."

dayu-cli upload_material \
  --ticker AAPL \
  --action create \
  --forms 10-K \
  --material-name "Investor Day" \
  --files ./investor-day.pdf
```

允许上传的文件后缀和每个 action 的必填字段由命令在执行前校验。查看完整参数：

```bash
dayu-cli upload_filing --help
dayu-cli upload_material --help
```

三个上传命令的 `--action` 默认都是 `auto`。单份上传还可显式使用
`create`、`update` 或 `delete`；批量脚本只会生成 `auto`、`create` 或 `update`。

### 5.3 从目录生成批量上传脚本

`upload_filings_from` 扫描和分类本地文件，生成当前平台可直接执行的脚本；生成阶段不上传文件：

```bash
mkdir -p ./workspace/scripts
dayu-cli upload_filings_from \
  --base ./workspace \
  --ticker AAPL,APPL \
  --from ./filings \
  --recursive
```

`--ticker` 接受逗号分隔值：首项是规范 ticker，其余项作为 aliases，脚本中的每条上传命令都使用同一组值。
`--action` 默认 `auto`；需要固定动作时可显式传 `--action create` 或 `--action update`。

未传 `--output` 时，脚本写到 `--base` 工作区根目录：POSIX 使用
`upload_filings_<TICKER>.sh`，Windows 使用 `upload_filings_<TICKER>.cmd`。`--output`
可以指向工作区内的既有目录，此时仍使用默认文件名；也可以指向工作区内的精确文件路径，命令不会替它补后缀。
显式文件的父目录必须已经存在。例如：

```bash
dayu-cli upload_filings_from \
  --base ./workspace \
  --ticker AAPL \
  --from ./filings \
  --output ./workspace/scripts/upload-aapl.script
```

需要补全公司名称和 ticker aliases 时，先在当前环境设置 `FMP_API_KEY`，再显式传
`--infer`。resolver 只在生成阶段调用；API key 不会写入脚本。生成成功后，stdout
会显示脚本绝对路径、recognized filing、material 和 skipped 数量，并逐项显示业务可读的跳过原因。

执行前先打开脚本检查文件与参数，再按平台运行：

```bash
# POSIX
/bin/sh ./workspace/upload_filings_AAPL.sh

# Windows
cmd.exe /d /c .\workspace\upload_filings_AAPL.cmd
```

脚本把调用者追加的参数逐元素追加到每一条上传命令。例如以下 POSIX 调用会让每条命令都收到
`--overwrite`；Windows 同样把参数放在 `.cmd` 路径之后：

```bash
/bin/sh ./workspace/upload_filings_AAPL.sh --overwrite
```

脚本输出必须留在 `--base` 工作区内，工作区自身、内部目录和既有目标不能是 symlink。
如果没有生成脚本，先查看摘要中的跳过原因并核对文件名是否含可识别的财年/财期；如果报 output
错误，确认目标父目录已存在且位于工作区内。`upload_filings_from --overwrite` 控制每条上传命令的
存储覆盖语义，不控制脚本文件替换。

### 5.4 预处理

```bash
dayu-cli process --ticker AAPL
dayu-cli process --ticker AAPL --document-id filing-1 --document-id filing-2
dayu-cli process_filing --ticker AAPL --document-id filing-1
dayu-cli process_material --ticker AAPL --document-id material-1
```

`--overwrite` 会请求重建已处理结果。

## 6. Session 管理

```bash
dayu-cli session list
```

通过 Session id 恢复单次 prompt：

```bash
dayu-cli session resume \
  --session-id <session-id> \
  --mode prompt \
  --ticker AAPL \
  "继续分析现金流"
```

通过 label 恢复 interactive Session：

```bash
dayu-cli session resume \
  --label earnings \
  --mode interactive
```

label selector 不再接受 `--kind`。`--mode` 只选择本次输入方式；prompt 模式仍可使用
`--ticker`，interactive 模式不接受 `--ticker`。两个模式都从所选工作区的 `config/`
读取配置；该目录不存在时使用包内默认配置。

清理 Session 需要显式确认；CLI 不会自动 close 或 cancel：

```bash
dayu-cli session purge --session-id <session-id> --yes
```

只有已关闭且全部任务都已终态的 Session 才能 purge。

同一个工作区内，若两个 CLI 进程同时选择同一 Session，先进入的进程可以继续提交、改向或取消，
后进入的进程会以只读方式打开，并在尝试修改时得到明确错误。需要在后进入的进程继续操作时，
先在原进程正常退出当前 prompt 或 interactive 会话并等待其关闭完成，再退出并重新执行
`session resume`；已经打开的只读会话不会在原进程退出后自动变为可写。

## 7. Tool Trace 诊断

`tool_trace analyze` 只读分析现有 Tool Trace，并在指定目录发布同一次分析得到的
JSON 与 Markdown 报告：

```bash
dayu-cli tool_trace analyze ./workspace --output-dir ./reports/tool-trace
```

`INPUT` 必须显式选择以下一种输入：

- workspace 目录，例如 `./workspace`；
- `.dayu` 目录，例如 `./workspace/.dayu`；
- tool-trace 目录，例如
  `./workspace/.dayu/artifacts/tool-trace`；
- 单个 cold JSONL 文件，例如
  `./workspace/.dayu/artifacts/tool-trace/tool-trace-cold.jsonl`。

成功后输出目录包含：

```text
tool-trace-analysis.json
tool-trace-analysis.md
```

目录输入会按当前固定布局同时发现可用的 hot SQLite、cold JSONL 和 payload
artifacts；单文件或 tool-trace 目录输入是 cold-only，不会从父目录猜测 hot
数据库或 payload root，因此报告会明确标记相应 `limited_signal`，而不是把
“无法证明”写成“未发生”。同一输入若同时匹配多个布局会拒绝执行；此时传入更具体的
`.dayu` 目录或 cold JSONL 文件。工作区路径参数不参与 Analyzer 输入发现。

报告中的 findings 和 limitations 不改变成功退出码。输入路径或布局错误返回 `2`；
可信读取、分析或发布失败返回 `1`。发布第二个文件失败时，命令会分别列出本次已发布
路径和失败路径；既有报告不会被主动删除。

## 8. 常见问题

### 配置文件已存在

默认再次运行 `init` 会进入 PRESERVE：保留用户文件和自建 manifest，补齐缺失的五个
根配置文件与包内 prompt 文件。需要完全用包内默认配置替换 `config/` 时使用
`--overwrite`；需要同时移除整个 `.dayu/` 时使用 `--reset`，并先停止所有 active
Dayu 进程。

### init 报 symlink 错误

为保证所有写入留在工作区，workspace、`.dayu-init.lock`、受管树及其子树都必须是普通
目录/文件，不能是 symlink、dangling symlink 或 Windows junction/reparse entry。请改用
工作区内真实目录后重试；不要通过链接绕过检查。

### 模型提示缺少 API Key

检查所选模型在 `workspace/config/models.json` 中的 `api_key_ref`。可在运行 `init` 前设置
对应变量，或按隐藏输入和最终确认写入 POSIX shell profile / Windows 用户环境。输出只会
显示变量名；如果持久化失败，修复目标 profile/用户环境后重试，workspace 不会半发布。

### init 一直显示正在等待 workspace lock

另一个 `init` 正持有 `<workspace>/.dayu-init.lock`。等待方不会使用有限 production timeout，
也不会提前发布配置；让前一个 `init` 正常完成即可。该锁不代表其它 Dayu 进程已停止，
RESET 前仍必须自行停止 active CLI/Web/WeChat/Host。

### init 显示 prewarm warning

FIRST/RESET 的配置已经发布成功，warning 只表示本进程未完成两个 CLI 入口的 import-only
预热，不会触发回滚，也不包含 provider 响应或环境变量值。可直接运行 `prompt` 或
`interactive`；若正常导入仍失败，再使用 `--debug --log-file <path>` 收集诊断。

### 没有找到默认日志文件

这是当前设计：未传 `--log-file` 的诊断流在进程结束时自动清理。重现问题时加上
`--debug --log-file <path>`；排查高频流式链路时改用 `--debug-stream`。

### 批量上传脚本没有生成

先运行 `dayu-cli upload_filings_from --help` 核对 source、ticker 和 output 参数。源目录必须存在且不能是
symlink；脚本 output 必须位于工作区内。命令输出的 skipped reason 会说明文件因财期信息缺失、同期去重、
数量限制或路径安全检查而未进入脚本的原因。
