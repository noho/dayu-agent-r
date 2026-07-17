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

`init` 是非交互式文件初始化命令。它把包内当前配置和 prompt assets 复制到
`./workspace/config/`；它不会选择模型、询问或保存 API Key，也不会创建写作模板。

常用形式：

```bash
dayu-cli init --base ./my-workspace
dayu-cli init --base ./my-workspace --overwrite
dayu-cli init --base ./my-workspace --reset --overwrite
```

- 未传 `--overwrite` 时，只要任一受管目标文件已存在，命令就失败且不会覆盖。
- `--overwrite` 更新受管配置与 prompt 文件，同时保留 `config/` 下其它用户文件。
- `--reset` 只删除可重建白名单：`config/`、`.dayu/host/`、`.dayu/artifacts/`、
  `.dayu/web_tools_storage_states/`，随后重新复制当前配置。它不会删除整个 `.dayu/`、
  `portfolio/` 或工作区其它文件。
- 为防止写出工作区，`config/` 目标路径及其已有子树中不能包含 symlink。

初始化后的主要目录：

```text
workspace/
├── config/       # 配置 overlay 与 prompt assets
├── portfolio/    # 已导入的财报和材料
└── .dayu/        # Session、运行期状态与 artifacts
```

API Key 由用户显式设置为环境变量。具体模型引用哪个变量，以
`workspace/config/models.json` 为准。例如：

```bash
export DEEPSEEK_API_KEY="..."
export FMP_API_KEY="..."       # 可选：为 ticker context 补充公司名
```

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

### 3.1 全局路径与日志参数

| 参数 | 说明 |
|---|---|
| `--base` / `--workspace` | 工作区根目录，默认 `./workspace` |
| `--config` | Agent / Session runtime 使用的显式配置目录；相对路径必须位于工作区内 |
| `--log-level` | `debug`、`verbose`、`info`、`warn`、`error` 或 `critical` |
| `--debug` | 等价于 `--log-level debug` |
| `--debug-stream` | 同时打开普通 DEBUG 与高频 stream/SSE 诊断 |
| `--verbose` / `--info` / `--quiet` | 日志等级快捷开关 |
| `--log-file PATH` | 把诊断日志追加写入指定文件 |

用户可见回答和进度仍写 stdout/stderr。未传 `--log-file` 时，诊断日志只保留到
当前 CLI 进程结束；需要排障留档时必须显式指定路径：

```bash
dayu-cli prompt "总结主要风险" --ticker AAPL \
  --debug --log-file workspace/prompt.log
```

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
- `--model-name ID`：选择模型配置。
- `--temperature FLOAT`、`--tool-timeout-seconds FLOAT`、`--max-iterations INT`：
  覆盖本轮执行参数。
- `--thinking` / `--no-thinking`：控制运行态思考展示。
- `--detail` / `--no-detail`：控制 activity stream 展示。

### 4.2 多轮交互

```bash
dayu-cli interactive --ticker AAPL
dayu-cli interactive --ticker AAPL --label earnings
```

不传 `--label` 时，每次启动创建一个新的未绑定 Session；传入 label 时复用
`cli.interactive.<label>` 对应 Session。`interactive --ticker` 与 `prompt --ticker`
使用同一个模型可读 scene context 规则。

交互输入态使用 `Ctrl-D` 退出。运行态第一次 `Ctrl-C` 请求取消当前任务；任务仍在
收口时再次 `Ctrl-C` 会让本地 CLI 退出。

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
终态摘要；`Ctrl-C` 请求取消当前 direct operation。

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

通过 label 恢复 interactive Session 时必须给出 kind：

```bash
dayu-cli session resume \
  --label earnings \
  --kind interactive \
  --mode interactive \
  --ticker AAPL
```

清理 Session 需要显式确认；CLI 不会自动 close 或 cancel：

```bash
dayu-cli session purge --session-id <session-id> --yes
```

只有已关闭且全部任务都已终态的 Session 才能 purge。

## 7. 常见问题

### 配置文件已存在

`init` 默认拒绝覆盖。确认要更新受管配置时使用 `--overwrite`；需要清理可重建
Host 状态时再同时使用 `--reset`。

### init 报 symlink 错误

为保证所有写入留在工作区，`workspace/config` 或其已有子树不能是 symlink。
请改用工作区内真实目录后重试。

### 模型提示缺少 API Key

检查所选模型在 `workspace/config/models.json` 中的 `api_key_ref`，并在启动
`dayu-cli` 的同一环境中设置对应变量。`init` 不会代为保存 secret。

### 没有找到默认日志文件

这是当前设计：未传 `--log-file` 的诊断流在进程结束时自动清理。重现问题时加上
`--debug --log-file <path>`；排查高频流式链路时改用 `--debug-stream`。

### 批量上传脚本没有生成

先运行 `dayu-cli upload_filings_from --help` 核对 source、ticker 和 output 参数。源目录必须存在且不能是
symlink；脚本 output 必须位于工作区内。命令输出的 skipped reason 会说明文件因财期信息缺失、同期去重、
数量限制或路径安全检查而未进入脚本的原因。
