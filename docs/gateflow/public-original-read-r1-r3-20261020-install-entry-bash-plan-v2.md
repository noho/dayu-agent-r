# PR206 默认入口安装增量：Bash 修订计划 v2

## 1. 基线、目标与本轮状态

**当前修订：v2，2026-10-20。** 以旧 `install-entry-bash-plan.md` 全文（SHA256 `a6ec1737b2e32a33c2f761d8d31e026d66971f529965510da0f864d98f6dd20a`）为基线，仅按 [bash-adjudication](public-original-read-r1-r3-20261020-install-entry-bash-adjudication.md) 窄修 DS 报告 `185725` 的 BP1–3，并澄清 Q1/Q2。旧文件不改，MiMo69913 仍审该冻结对象；本 v2 不代替其终态/裁决。BP1–3 的正式状态仍由主控在双路窄复审后回写，本文件只提交计划层修订与机制证据，**不宣称审核通过或实施完成**。

本计划依据已经确认的 [install-entry-goal](public-original-read-r1-r3-20261020-install-entry-goal.md) 和最新 [plan-direction](public-original-read-r1-r3-20261020-install-entry-plan-direction.md)，不重新索取目标确认。默认一个工程 slice；本文件是待主控核对及适用计划复审的计划，**没有实施，也没有安装成功结论**。

- 核验分支：`fix/public-original-read-r1-r3-20261020`；HEAD：`1856cf8d97468423c6a3ece5558a312d31802b20`；沿用 draft PR206，包版本保持 `0.1.5`。
- preflight dirty 项为主控所有的 control/authorization、goal/direction、旧 plan、Bash plan/adjudication 及三份既有 review，没有源码、README、测试或 pyproject 改动；不作为分支冲突处理，不纳入本轮写入。
- 旧 `install-entry-plan.md` 的 Python publisher / zsh-only 方案及 `docs/reviews/plan-review-20261020-183115.md`、`183342.md` 原样保留。它们的 pass 不放行本方案；仍适用的 owner/root cause 事实可以引用。
- 旧 R1–R3 和版本证据不重开。历史入口只采用用户给定事实：`/Users/leo/.local/bin/dayu-cli` 曾指向 `/Users/leo/.local/share/uv/tools/dayu-agent/bin/dayu-cli`（0.1.4），PM 已手工改为本仓 `.venv/bin/dayu-cli`；允许保留人工现状，但不能用它证明新流程。

动机成立，严重性限定为安装交付缺口。根 README §1.1 只创建 venv、激活并 editable 安装，没有把本次安装交付为下一正常 shell 的默认命令。因此包已装入 `.venv`、help 在激活 shell 通过，都不足以证明裸 `dayu-cli` 来源正确；无需改业务 CLI 或财报处理。成功信号仍是：执行更新 README 的源码安装后，未激活仓库 `.venv` 的新正常 shell 裸命令实际命中本次 0.1.5，并能绑定已核收源码 commit。

本轮只新建本 v2 计划及独立 `workspace/tmp/public-original-read-r1-r3-20261020/install-entry-20261020T101200Z/bash-plan-fix-evidence/`；旧 `bash-plan-evidence/` 仅作原计划机制证据引用。没有修改真实 HOME、default/profile、live `.venv`，没有 commit/push/PR/tmux 操作，也没有读取旧 uv 环境内部或调用方环境。

## 2. 直接依据与机制取舍

| 依据 | 可支持的判断 |
| --- | --- |
| 根 `AGENTS.md`；根 README 的 `Agent更新约束`、§1.1/§1.2 | 安装交付应修在安装 owner；根 README 只承载最终用户操作。当前 wheel 段裸 help 会受源码默认入口影响，必须同 slice 消歧 |
| `pyproject.toml` 的 project/version/scripts、setuptools 包范围 | 唯一版本声明仍为 0.1.5；console script 是 `dayu.cli.__main__:exit_module`；不新增版本 API、安装依赖或业务 fallback；`scripts/` 不进入业务 wheel |
| `dayu/cli/__main__.py`、`main.py`、`arg_parsing.py` | `python -m dayu.cli --help` 是真实公开 module 入口；`--help` 属 argparse，不能凭假命令或 metadata 替代真实退出 |
| `dayu/cli/init_environment.py` | init 独立拥有 secret 持久化 block；安装脚本不能借用/改写它，也不能把默认入口安装塞进 init |
| 三个平台 lock 文件首部及其公共 `-c lock-common-py311.txt` | 锁是 Python 3.11、特定 OS/架构的依赖选择，不能把 macOS arm64 锁用于所有平台，也不能由 Bash 语言推导依赖跨平台实测 |
| `tests/cli/test_public_package_entrypoints.py`、`pyrightconfig.json`、`tests/README.md` | 已有 wheel 构建/metadata 测试不验证默认入口安装；pyright 当前覆盖 dayu/tests/utils，新增 Python 若在 scripts 须纳入，不以放入 utils 豁免 |

标准机制的本线只读证据在 `install-entry-20261020T101200Z/alternatives/`：`uv-tool-install-help.{json,stdout}`、`uv-tool-update-shell-help.{json,stdout}`、`pip-install-help.{json,stdout}`；各 help 实际退出 0。uv 支持 `-e/--editable`、constraints、force、指定 Python 和 reinstall；update-shell 说明可确保工具 executable directory 在 PATH。pip 支持 editable、约束和指定解释器，`--user` 是平台用户目录，且存在 scripts 不在 PATH 的警告。

**选用：一个 Bash 源码安装脚本，调用标准 `venv` + 目标解释器的 `pip`，再做有限的入口与 PATH 发布和安装后检查。** 不再保留“先 pip，再运行独立复杂 Python publisher”的结构。

- uv editable 是可行标准机制，不能以“不支持 editable”排除。但本需求必须保留给定旧 uv 目标树，不能直接把同名旧 tool 的 install/force 当作无损转换。另设 uv tool 根、另装 uv、维护第二个托管环境并不能消除用户文件碰撞、PATH 优先级和新 shell 来源验证，反而多一个安装前提。当前无需迁移到 tool manager；这不是声称 uv 本身不能实现该目标，也没有执行 uv install/update-shell 来猜测其副作用。
- `pip --user` 可生成脚本，却不承诺当前解释器、跨平台 scripts 位置、默认 PATH 优先级或保留既有入口；不能仅删掉 venv/activate 即认为目标已满足。保留仓库 `.venv` 是本次最少变更的隔离安装目标。
- Bash 新增的自有职责只限：选择已有适用锁、串联安装、发布一个默认入口、维护有限启动文件的 PATH block、核验本次安装。拒绝通用安装后端/profile 框架、平台插件、安装数据库、durable journal、旧环境扫描和自动卸载。

旧版机制取证在 `bash-plan-evidence/receipt.json`：macOS 上隔离 HOME/源外 cwd 的 `/bin/bash -ic/-lic`、`/bin/zsh -ic/-lic` 均解析到隔离 `.local/bin` 并执行明确标记的 startup probe，退出 0；Bash stderr 为无 TTY 的 `no job control`，不能当业务错误或丢弃记录。它只证明标准启动文件与小型 Bash launcher 的机制，不证明安装或业务 help。另以当前 `.venv/bin/python -I -m dayu.cli --help` 在源外 cwd 只读执行，退出 0、stdout 2219 字节、stderr 0，只支持源码 venv 的 `-I`/module 入口机制，不能证明 wheel 的 user-site 可见性；没有执行 wheel 安装，不把此证据当新流程验收。

v2 窄取证见 `bash-plan-fix-evidence/receipt.md`、命令记录/两通道及 `probe.py`：BP1 用独立 index/worktree 和来自当前 HEAD 的五个 tracked 输入证明旧 tracked-only 检查漏未跟踪安装脚本，新存在/未跟踪检查能拒绝脚本与源码（含 ignored 源码），tracked 改字节也被拒绝，而无关临时证据和具名缓存不阻塞；没有写真实 Git index/objects 或创建 commit。BP2 在 Python 3.11 实测 `-E -P` 的 `ignore_environment=1`、`safe_path=True`、`no_user_site=0`、`ENABLE_USER_SITE=True`，cwd/空路径不在 `sys.path`，实际存在于隔离 HOME 的 user-site 会进入搜索路径；同解释器对照 `-I` 的 `no_user_site=1`。源外 cwd、隔离 HOME、注入无效 PYTHONHOME/PYTHONPATH 下，当前 venv 的 `-B -E -P -m dayu.cli --help` 退出 0。BP3 的标准 HOME 在 zsh `-ic/-lic` 通过；继承非 HOME ZDOTDIR 及 `.zshenv` 重定向两个反例均在真实启动后被断言拒绝，合成配置字节不变。这些都是机制探针；未安装 wheel、未运行未来安装脚本、未完成正式 sync。

## 3. 唯一 owner 与必要运行条件

| 语义 | Owner / 边界 |
| --- | --- |
| 包名、版本、console script target | `pyproject.toml`；不复制版本常量，不新增 `--version` |
| 安装目标、约束选择、默认入口及 PATH 发布、阶段退出 | 新 `scripts/install-source.sh`；属于源码安装交付，不 import Dayu，不进入 UI/Service/Host/Engine/runtime |
| 安装产生的 console script、dist-info、editable source | 标准 venv/pip 与目标解释器的实际安装 metadata；Bash 只调用和核验，不自行制造 metadata |
| 正常 shell 采用何种启动文件及命令解析 | 目标 Bash/zsh 的真实启动行为；脚本可配置其 PATH block，不能伪造 alias/function、绕开正常启动文件或强行改用户其它配置 |
| init secret block | 原 `dayu/cli/init_environment.py`；双方只拥有各自 block，顺序执行应互相保留 |
| 工程核收 commit、交付指纹与正式验收事实 | 主控的交付/安装回执；不是脚本新增的版本状态或业务结论 |

脚本以 Bash 3.2 可用语法为最低基线，避免依赖 macOS 上不存在的 Bash 4+ 特性或把 GNU-only 文件命令当作所有平台都有。输入只需目标正常 shell（`--shell bash|zsh`）及 Python executable（`--python` 可选，默认 `python3.11`，只接受单个 executable/path，不接受待 eval 的命令字符串）。显式选择 shell 避免把“脚本由 Bash 执行”误当成“用户正常 shell 就是 Bash”。源码根由脚本位置确定，不依赖调用 cwd；不增加安装 backend/profile 对象或配置文件。

支持条件与依赖锁分开说明：

| 运行环境 / 目标 shell | 安装目标与锁选择 | 验证承诺 |
| --- | --- | --- |
| macOS，正常 Bash 或 zsh | Python 3.11，arm64 使用 `lock-macos-arm64-py311.txt`；保留 README macOS 14+ 条件 | 当前工程可真实验证该 OS 上两个 shell 的安装交付 |
| Linux，正常 Bash 或 zsh（已安装该 shell） | Python 3.11，x86_64 使用 `lock-linux-x64-py311.txt` | 实现应遵守相同契约；未实际执行时明确未实测，不扩财报业务矩阵 |
| Windows Git Bash，正常 Bash | 本机 Windows Python 3.11 x64，使用 `lock-windows-x64-py311.txt`；venv scripts 为 `Scripts` / `.exe`，用 Git Bash 自带路径转换工具转换必要 native 路径 | Bash 可作为安装编排；不声称原生 cmd/PowerShell 直接运行它，不假称已做真实 Windows 验证 |
| WSL，正常 Bash 或 zsh | 使用 WSL 的 Linux Python，按 Linux OS/架构选锁 | 安装位于 Linux 子系统，不是原生 Windows 环境 |

从所选 Python 的标准平台/版本信息选择**现有**匹配锁；无匹配锁、Python 非 3.11、Windows Python 与 WSL 混用、必要 Bash/文件工具/路径转换或目标 shell 不可用，均在变更前清楚失败。不得 fallback 到 macOS 锁、无约束安装或自动下载另一 Python。当前三份锁存在不等于本轮真实通过三 OS；其依赖可用性与完整业务支持没有新增承诺。其它架构/shell 不在此最小安装契约内，不猜测用户配置。

Python 如需参与，仅使用简短标准库查询平台、sysconfig 路径、pyproject 与已安装 metadata/source；不承担文件发布，不复刻 pip 安装/版本算法。不新增独立 Python publisher。若确有新增 Python 文件，仍须完整中文 docstring、严格签名及 pyright，不能以内嵌/脚本身份掩盖类型问题。

## 4. 一个 slice 的安装契约

**IE-B1：Bash 完成源码包安装、默认入口配置及新正常 shell 检查。** 代码、测试和文档同 slice 交付，不按文件或角色机械拆分。局部函数、临时文件生成和内部数据结构留实现者决定；下列公共行为不得弱化。

### 4.1 安装与发布顺序

1. 校验输入/平台/工具、源码根与已有 `.venv` 身份，预检需要写入的入口和 profile 形态。已有 `.venv` 必须属于该源码目标且版本适用；遇到链接、错误类型或其它环境不递归删除/重建。可保留同目标有效 venv 重复安装。入口目的地的既有父目录（含 `.local`、`.local/bin`）为 symlink 时明确失败，不沿链写入（Q1）；zsh 还须按 §4.3 在真实启动后核验有效 ZDOTDIR。上述预检在创建/复用安装环境及任何入口/profile 写入之前完成，已知冲突不先写再报错。
2. 创建/复用源码根 `.venv`，只用**该 venv 的解释器**执行 `-m pip install -e <源码根及[test,dev,browser] extras> -c <匹配的平台锁绝对路径>`。不需要 activate；不读取当前 `VIRTUAL_ENV` 来决定目标。pip 失败立即终止，不发布入口，不伪装回滚已经发生的包变更。
3. 从源外 cwd 用目标解释器 `-I` 核验真实安装：通过 sysconfig 的 purelib/platlib 定位目标实际 `.dist-info`，检查 Name/Version、entry point、`direct_url.json` 的 editable/source；版本与源码 pyproject 一致，本线为 0.1.5。不得仅在仓库 cwd 调 `version()`，不得把源码 `.egg-info` 或 PYTHONPATH 影子当安装证明。
4. 从目标 scripts 路径获得 pip 真正生成的 console script（POSIX `dayu-cli`、Windows `dayu-cli.exe`），先执行它的真实 `--help` 并检查退出。不可用其它安装或 marker 补足。
5. 准备 profile 的必要 PATH block 和 `$HOME/.local/bin/dayu-cli`。profile 成功之后最后发布默认入口，再做读回与新正常 shell 核验。每一文件的发布不得截断原文件、沿旧符号链接写目标或意外把临时文件移动进链接目标目录；BSD/GNU 工具差异必须在实际使用处验证。无需跨文件事务。
6. 安装后从源外 cwd 启动所选 shell 的正常交互与登录交互模式（`-ic`、`-lic`），移除继承的 venv/PYTHONPATH/PYTHONHOME，初始 PATH 不含仓库 `.venv` 或刻意注入的 `.local/bin`。zsh 同时断言启动后的有效 ZDOTDIR 仍为 HOME。检查默认入口是外部命令、解析到本次入口，裸 `dayu-cli --help` 真正退出 0。不手动 source/profile、activate、export 目标目录，不用 `-f/--norc` 绕过启动文件。失败返回非零，不能输出“安装完成”。

安装脚本返回 0 表示本次包/metadata、入口/profile 发布及受支持正常 shell 检查均通过。成功输出只需说明安装目标、默认入口和应重新打开终端；不宣称改变调用者已经运行的父 shell。

### 4.2 默认入口与旧目标保留

为避免 Windows symlink 权限前提，统一发布**小型 Bash launcher 普通文件**，只 `exec` 本次 venv 中 pip 生成的绝对 console script，并原样传递 `"$@"`。它是本次安装交付的入口重定向，不包含 CLI 解析、版本判断、环境搜索、自动修复或 fallback；Python console script target 仍唯一属于 pyproject/pip。路径正确引用，空格/中文不变成代码，不使用 eval；目标移动或删除后自然失败，不自行寻找其它安装。

| 入口原状态 | 行为 |
| --- | --- |
| 目录/入口缺席 | 按需建立用户目录，发布本次 launcher |
| 给定历史旧 symlink、dangling symlink、当前人工修正 symlink | 只替换链接目录项，绝不打开/修改它指向的旧 executable 或环境；不需要知道旧包版本。工程用隔离历史形态验证，不恢复真实旧链接 |
| 与本次预期 launcher 字节完全一致 | 幂等 no-op；仍执行完整包安装与核验 |
| 其它普通文件、目录、特殊文件；无法安全替换的目录型链接或执行平台入口碰撞 | 明确冲突路径并非零退出，不以 marker 头就认定未知文件可覆盖，不静默删除/改写用户文件 |

不引入自有 launcher 格式解析/迁移框架；不同源码路径留下的非同字节普通入口属于显式碰撞，不能猜其可被覆盖。README 说明保留源码/venv 位置；如需迁移且遇碰撞，按错误定位处理用户文件，不自动清理。已知 symlink 的旧目标树及父工具环境完整保留，不读取真实旧 uv 安装内部、不调用旧 executable、不删除其它工具。

### 4.3 PATH 与用户 profile

- 目的地固定为用户 `$HOME/.local/bin`，将它放到 PATH 前部，其余 PATH 项保留。README 简短说明该操作也会影响此目录中其它同名命令的优先级。
- zsh：只配置标准 HOME 的 `.zshrc`。**BP3 检测点在任何安装/发布写入之前**：保留用户真实启动配置及继承的 ZDOTDIR，按 §4.1 第 6 项相同的源外 cwd/去 venv 环境启动目标 zsh 的 `-ic` 和 `-lic`，查询启动完成后的 `${ZDOTDIR-$HOME}`（包含 `.zshenv` 的设置），并在该 shell 内断言 `[[ "${ZDOTDIR-$HOME}" -ef "$HOME" ]]`；查询/断言非零即失败。只接受有效目录与 HOME 为同一目录，不接受 HOME 下另一个子目录；不另找 profile，不用 `ZDOTDIR=$HOME` 或 `-f` 绕开用户配置。发布后新正常 shell/正式验收复用同一断言。Bash：配置 `.bashrc` 以及 Bash 实际会选择的第一个登录启动文件（依次 `.bash_profile`、`.bash_login`、`.profile`；均缺席则建立 `.bash_profile`）。登录文件直接加入同一短 block，不猜它有没有间接 source `.bashrc`。只处理这些必要文件，不建通用 profile 探测链。
- 每个目标文件只允许一个独立的 `dayu source install PATH` block，不能复用 init marker。block 只负责在 `.local/bin` 尚非首项时前置它；重复 source 不继续累加前缀，不能仅因为目录出现在 PATH 尾部就不处理优先级。
- 最小更新策略：block 缺席时追加；已存在且与预期完整 block 相同则不改；重复、残缺、被改写的 marker/block 明确拒绝。不为本次需求做任意 block 编辑器。保留原内容字节、现有权限与 init block；没有末尾换行时只增加必要分隔换行，不能重排/规范化原文件。缺席文件采用适当用户私有权限。
- profile 为 symlink、目录或特殊文件，或者必要父路径不能安全写入时，拒绝并保留用户文件。不能沿 profile 链接写其它路径、擅自接管系统 profile、改 alias/function，不能静默覆盖用户已追加的 PATH 规则。原 block 后的用户规则若使新 shell 检查失败，如实失败，不移动用户内容。
- 顺序运行安装和 init 应互相保留各自 block；同一文件并发写入不在本次承诺，不引入跨 owner 锁/事务。交付时将此边界列入风险。

### 4.4 失败与重复执行

- 预检/安装来源校验失败：非零、说明阶段和安全路径；不修改默认入口/profile，不输出 profile 正文或 secret。外部命令失败保留可诊断输出和非零状态，不用管道最后一条成功掩盖它。
- pip 失败：可能留下目标 venv 的部分安装，诚实说明；不碰默认入口。无需回滚整个 pip 或卸载其它环境。
- 发布 I/O 错误/中断：不得输出成功；已有单文件不被截断。profile 已完成而入口未完成时如实报告阶段，旧入口不得被沿链写坏；若入口目录项替换未能完成或最终状态无法确认，明确说明，不谎称全回滚。清理只涉及自有临时项，清理失败报告残留路径。
- 新 shell 解析/metadata/help 失败：即使发布已经发生，也返回非零并说明失败环节，不改写用户 alias/function 强行通过。重复执行在已知可恢复状态收敛；用户文件碰撞仍需显式处理，不能把重试当覆盖授权。
- 整个流程重复执行，目标安装与入口相同、每个 profile 单 block、外部原字节和旧目标树不变。无需保证包管理器日志或 dist-info 安装时间逐字不变。

## 5. 影响文件与 README 决策

预计修改范围：

- 新 `scripts/install-source.sh`：上述有限 Bash owner，中文概览及函数注释说明参数/输出/失败，Bash 3.2 语法；不能只包一层旧 Python publisher。
- 新 `tests/install/test_source_install.py`：以真实 Bash 子进程与隔离文件系统验证 owner 契约；必要测试辅助只在本目录，严格类型和中文 docstring。可增加最小测试文件，不扩财报 fixture。
- 根 `README.md`：按已读用户手册职责，替换源码安装块为脚本调用；说明 Python/Bash 条件、平台锁差异、目标 shell、Windows Git Bash/WSL 边界、保留源码位置、默认入口/PATH 影响、失败路径、新终端检查。可选 Chromium 改为目标 venv 解释器的 `-m playwright install chromium`，不能取消 activate 后仍裸用其它环境的 playwright。
- 同一 README §1.2：处理主控 accepted 的旧 DS F1 及本次 BP2；wheel 的安装和检查始终使用**同一明确目标解释器**（安装命令为 `"<目标Python路径>" -m pip install /path/to/dayu_agent-<version>-py3-none-any.whl`），从源外 cwd 检查 `"<目标Python路径>" -E -P -m dayu.cli --help`。Python 3.11 的 `-E` 忽略 PYTHONPATH/PYTHONHOME 等 Python 环境变量，`-P` 不把当前目录加入 module 搜索路径，两者保留该解释器正常启用的 user-site；不能继续用隐含 `-s` 的 `-I` 检查可能落入 user-site 的 wheel。同解释器、同 `-E -P` flags 记录实际 `.dist-info` Name/Version/路径、`sys.executable`、purelib/platlib 及启用的 user-site，断言 metadata 唯一、版本符合所装 wheel、实际模块来源属于该安装 site，排除源码 `.egg-info`/editable 影子。源码 venv 的 `-I` 检查保留。不能再把裸 PATH 的 `dayu-cli --help` 当 wheel 安装证明；不强制新增 wheel venv，不改变 wheel 安装语义或改成默认入口发布流程。
- `tests/README.md`：按其当前测试手册职责加入 install 测试及实际运行方式。Bash 不属于 pyright/Python coverage；仅当新增 scripts 下的 Python 文件时才扩 `pyrightconfig.json` include 并更新说明，不能无意义增加纯 Bash 的 Python 检查目录。

`pyproject.toml` 的版本/依赖/entry point、业务源码与其它层 README 不变；没有分层/装配改变，不触发 `dayu/README.md`。无需为 docs-only 计划运行测试；实现后按下节实际验证。最终影响不同，主控按实际 owner/README 职责重新核对。

README 源码命令的预期用户形式（最终须与实现 help 一致，不是本轮执行记录）：

```bash
# macOS 正常 zsh；正常 Bash 时把 shell 改为 bash
bash scripts/install-source.sh --shell zsh
# Linux / WSL 正常 Bash
bash scripts/install-source.sh --shell bash
# Windows Git Bash；替换为已安装的本机 Python 3.11 executable
bash scripts/install-source.sh --shell bash --python "/c/实际路径/python.exe"
```

上面平台分支只提供必要运行条件，不能在 README 写“Windows/macOS/Linux 已全部验证通过”。README 不放工程审核、commit 指纹或流程停点；这些属于 gate/安装回执。

## 6. 工程验证：不安装进 live

### 6.1 必须运行的检查与行为测试

实现后先激活当前仓库 `.venv`，仅用它运行测试/检查，不向它安装：

```bash
source .venv/bin/activate
bash -n scripts/install-source.sh
python -m pytest tests/install/test_source_install.py \
  tests/cli/test_public_package_entrypoints.py -q
python -m pyright
```

预期：语法检查及受影响测试通过，全量 pyright 0 errors，无 ignore/Any/排除掩盖。实际新增 Python owner 时增加受影响测试、将其纳入 pyright 并按 AGENTS 检查单文件覆盖率目标 >=80%；不为 Bash 虚构 Python coverage 数字。Bash 的有效性通过行为/失败断言证明，不只测 `bash -n` 或匹配源码字符串。新增影响才扩大对应测试，不重跑 R1–R3/完整财报业务或 live LLM。

自动化行为至少覆盖：

1. 输入/平台/适用锁及目标 scripts 路径；错误 Python/缺锁/不支持 shell、已有 `.venv` 异常形态明确失败。非本 OS 路径分支可用受控查询/文件布局测试，但报告为分支契约测试，不冒充真实 OS 执行。
2. 缺席入口、给定历史形态 symlink、dangling、人工同目标 symlink、相同 launcher、未知普通文件/目录/特殊形态及不安全目录型链接，目的地父目录 symlink 明确失败（Q1）；替换只能改目录项。空格/中文路径、源外 cwd、参数原样转发/退出码至少有真实 Bash 测试。
3. zsh 启动文件、Bash 非登录/登录启动文件优先级；BP3 隔离覆盖继承非 HOME ZDOTDIR 和 `.zshenv` 设置另一目录（含另一份 `.zshrc` 恰好提供正确 PATH 的反例），在任何安装/发布写入前失败，入口与配置原字节不变；标准 HOME 正常通过，发布后两种正常模式也断言有效值；profile 原文/权限/init block 保持，缺席/已有 PATH、block 重复与损坏、symlink profile、连续运行稳定；顺序 init-after-install 保留 PATH block 及反向保留 init block。不为其新增生产共享 helper。
4. pip/metadata/source/help 任一失败禁止成功及错误发布；profile 发布失败、profile 成功后入口失败、清理失败及安装后正常 shell 中 alias/function/后续 PATH 覆盖导致失败。故障测试可在外部命令/文件 I/O 边界注入，不用 fake metadata 把非法来源变成成功。
5. 在本机真实 Bash 与 zsh 子进程里用隔离 HOME、源外 cwd、干净初始 PATH，运行 `-ic`/`-lic`；登录 profile 先移除 `.local/bin`/前置旧目录，仍须由本次配置交付正确解析。不能仅检测启动文件存在。非 TTY 的 job-control stderr 应保留并说明。

### 6.2 用 README 流程真实隔离安装

在本次 work unit 的 `workspace/tmp/` 下另开 implementation run，HOME、源码、venv、pip config 与证据都隔离；普通下载 cache 可独立建立或显式复用。只复制安装所需的 pyproject/README/LICENSE/dayu/constraints/scripts，不带 live `.venv`、真实 HOME 或业务 fixture。来源用明确待审快照：优先 `git archive <待审OID>`；未提交实现则保存 tracked 文件及本 slice 新文件完整路径/SHA256 manifest，记录基线 OID 和差异，不能把 dirty 副本自称已核收 commit。工程回执保存 README/脚本版本和实际展开 argv、cwd、必要环境白名单、两通道/退出码。

从干净进程实际执行更新 README 的**同一脚本调用**；不复制另一套安装算法，不把 `--no-deps`、marker、当前 live 的已安装 metadata、PYTHONPATH 或 fake pip/help 当流程验收。可复用普通下载缓存提高效率，但必须真实 pip 安装到隔离 venv，不从 live 环境借 site-packages。Q2：回执记录隔离配置的 `PIP_CONFIG_FILE` 实际值/来源（可用目标平台空设备禁用外部配置），以及 `PIP_CACHE_DIR` 实际路径和普通下载缓存来源；配置隔离不等于必须清空下载缓存。

| 场景 | 实际执行与必要断言 |
| --- | --- |
| fresh | 独立 HOME 无默认入口/安装 block，独立源码无 venv；真实 README 安装退出 0；新 shell 命中新入口，实际 dist-info/source/help 属于该隔离目标 |
| legacy | 独立 HOME 下构造 `.local/bin/dayu-cli -> .local/share/uv/tools/dayu-agent/bin/dayu-cli`；旧树只是合成保全资产，不伪造真实旧 uv 安装事实。真实全流程后默认入口更新；旧目标树完全不变 |
| repeat | 对 fresh 和 legacy 成功状态各至少再次执行完整 README 安装脚本；不只重复最后发布动作。安装后仍命中同一目标、profile 单 block 且其它内容不变、旧树保持 |

legacy 保全 manifest 在隔离旧目标根生成，比较前后完整相对路径集合、条目类型、普通文件 SHA256/权限/mtime、symlink 原始目标等必要写入指纹（不以读取会改变的 atime 判断）；不跟随树内链接到外部。旧树允许 sentinel 字节验证保全，**新安装**必须用真实 pip/dist-info/CLI help。绝不打开真实 `/Users/leo/.local/share/uv/tools/dayu-agent` 内部。

各场景都保存新正常 shell 的 `command -v`、外部命令类型和 PATH 解析路径；目标解释器 `-I` 下的实际 dist-info Name/Version/位置、editable/direct_url、`sys.executable/sys.prefix`、scripts 路径及真实 help 退出。至少当前 macOS 上真实验证 Bash/zsh；若没有 Linux/Windows runner，就明确“实现目标/分支测试、未真实 OS 安装验证”，不能虚报通过，也不为本次目标新增三 OS 完整业务门槛。

## 7. 工程核收后的真实 sync 与正式验收

本节是已经授权的后续流程停点，风险分类为 `covered by later approved slice`，不是新用户决策，也不是第二个工程实现 slice。必须先完成主控计划核对/适用新方案复审、IE-B1、既定双路完整代码审核与必要修复复审、同 draft PR206 的交付核对；**工程核收并收到明确安装通知后**，才可按更新 README 在真实自身源码/live 目标安装。merge 仍另授权。当前 writer 不执行。

**BP1：正式 sync 前先绑定安装输入，再执行 README。** 保存当次核收完整 OID（不是固定写本计划起点）、当前 HEAD、必要文件收录/字节与相关路径未跟踪检查。必要交付脚本 `scripts/install-source.sh`、pyproject/README/LICENSE、所选平台锁及公共锁必须确实在核收 commit，工作树字节一致；`dayu/`、`scripts/`、`constraints/` 中参与安装/导入的源码和资源也必须来自同一 commit。仅有 HEAD 相等、版本 0.1.5 或 tracked-only clean 不能放行。现有人工链接可保留，不恢复真实旧链接，不调查调用方入口/PATH/环境，也不让调用方补安装。

以下是在源码根执行的最小检查轮廓；`ENTRY_APPROVED_OID` 和 `ENTRY_PLATFORM_LOCK` 由主控填当次核收完整 OID、此次所选锁的仓库相对路径。每条退出/输出落盘；`ls-files --error-unmatch` 与对核收 OID 的 diff 必须联合成立，不能把“仅 index 收录”当作“已在 commit”。必要输入另保存工作树原始字节的 blob 比对（`git hash-object --no-filters -- <文件>` 等于 `git rev-parse "$ENTRY_APPROVED_OID:<文件>"`），覆盖核收 tree 中上述相关路径下的实际输入文件；不只比较脚本名字。该指纹属于交付回执，不是新增运行时状态库。

```bash
: "${ENTRY_APPROVED_OID:?填入当次核收完整OID}"
: "${ENTRY_PLATFORM_LOCK:?填入本次平台锁的仓库相对路径}"
[[ "$(git rev-parse HEAD)" = "$ENTRY_APPROVED_OID" ]] || exit 1
entry_install_paths=(scripts dayu constraints pyproject.toml README.md LICENSE
  setup.py setup.cfg MANIFEST.in ':(glob)dayu*/**/*.py')
git ls-files --error-unmatch -- scripts/install-source.sh pyproject.toml \
  README.md LICENSE constraints/lock-common-py311.txt "$ENTRY_PLATFORM_LOCK" || exit 1
git diff --no-ext-diff --exit-code "$ENTRY_APPROVED_OID" -- "${entry_install_paths[@]}" || exit 1
entry_untracked_inputs=$(git ls-files --others \
  --exclude=__pycache__/ --exclude=.pytest_cache/ \
  --exclude=.mypy_cache/ --exclude=.ruff_cache/ --exclude=.DS_Store \
  -- "${entry_install_paths[@]}") || exit 1
[[ -z "$entry_untracked_inputs" ]] || exit 1
```

未跟踪检查限定安装输入路径，故 `workspace/tmp/`、本轮 docs 及这些路径外的无关 ignored cache 无需 clean；只排除具名的非输入缓存目录与非运行期 OS 元数据 `.DS_Store`，不用 `--exclude-standard` 一概放过 ignored 源码。相关路径内其它未跟踪源码/脚本/包资源即使被 Git ignore 也拒绝；不能把缓存排除项当源码输入豁免。清单也覆盖当前 setuptools 可能读取的根 `setup.py/setup.cfg/MANIFEST.in` 及 `dayu*` 包根的 Python 源码；可选路径缺席正常，出现未核收输入即失败。新增真实安装输入时同步纳入该清单，不扩大成整工作树强制 clean。检查在真实安装前完成，并在安装后复核输入指纹（安装生成的非输入缓存不计），防止把安装前结论冒充整个执行期不变；当前 writer 仅提供隔离反例，不执行真实 sync。

安装之后，从源外 cwd 启动真实 HOME 的新正常未激活 shell。当前本机 zsh 的验收命令轮廓如下；路径/退出/两通道均须落盘。BP3 与写前预检一样保留用户真实启动配置/继承 ZDOTDIR，在 shell 启动完成后查询并断言有效值为 HOME；不强制重设它。这是后续执行要求，不是已经完成的证据：

```bash
cd /private/tmp
env -u VIRTUAL_ENV -u PYTHONPATH -u PYTHONHOME \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin \
  /bin/zsh -lic '
    [[ -z "${VIRTUAL_ENV-}" ]] || exit 1
    print -r -- "effective_zdotdir=${ZDOTDIR-$HOME}"
    [[ "${ZDOTDIR-$HOME}" -ef "$HOME" ]] || exit 1
    command -v dayu-cli || exit 1
    whence -w dayu-cli || exit 1
    whence -p dayu-cli || exit 1
    dayu-cli --help
    entry_help_exit=$?
    print -r -- "help_exit=$entry_help_exit"
    exit "$entry_help_exit"
  '
```

还须实际断言 `whence -w` 是外部命令而非 alias/function，解析路径为本次 `$HOME/.local/bin/dayu-cli`；不能只把上述输出记录下来就判 pass。Bash 对应使用 `bash -ic/-lic`、`command -v`、`type -t`（须 `file`）、`type -P`；其它 OS 使用其正常启动 shell 与系统初始 PATH，不硬套 macOS 路径。至少包含正常交互和登录交互检查。

解析入口是本次生成的 launcher 时，记录其实际字节/哈希及唯一 `exec` 目标，核对目标是本源码 `.venv` 的实际 console script；若保留 symlink 则记录原始与最终目标。记录该 console script 的实际解释器关联（POSIX shebang/必要 shell 引导，Windows 则按实际生成 launcher 核对），不要把 `.venv/bin/python` resolve 后的基础解释器误当成 venv 身份；同时保存目标 Python 的 `sys.executable`、`sys.prefix`、sysconfig scripts/purelib/platlib。

在同一源外 cwd，用该**目标解释器** `-I` 的标准库探针从其 purelib/platlib 定位唯一 dayu-agent `.dist-info`，记录 METADATA Name/Version、位置、entry points、`direct_url.json` 的 editable 标志和源码路径，排除 cwd/PYTHONPATH/用户 site/源码 `.egg-info` 影子。断言实际版本 0.1.5、source 正是已核收源码根；`direct_url` 本身不证明 commit，还必须联合该源码根的实际 HEAD、上述安装输入的 commit/字节/未跟踪指纹与核收 OID。脚本和回执不另存一份可被误当版本真源的状态库。

最后保存裸 `dayu-cli --help` 真实两通道和退出 0，核对入口 → pip console script → 目标解释器/实际 dist-info → editable source → 核收 commit/安装输入指纹全部一致。只读源码版本、在仓库 cwd 查 metadata、激活 venv 后通过、现成手工链接通过或本轮 startup probe 均不能替代此链。

## 8. 风险、未覆盖与下一入口

| 风险/未覆盖 | 分类 | Owner / destination |
| --- | --- | --- |
| Bash 安全发布、profile 保全/幂等、部分失败及旧目标树不变尚未实现证明 | fixed in current slice | IE-B1 实现者；§4/§6、完整代码审核，完成前不能因已分类而放行 |
| 旧 DS F1 / BP2：源码入口使 wheel 裸命令伪确认，`-I` 又隐藏可能的 user-site | fixed in current slice | 本 v2 §5 给出同目标 Python `-E -P` 与实际 site 归属检查；计划层待双路窄复审/主控回写，README owner（IE-B1）实现后由完整代码审核证明；正式 finding 状态不在本文件改写 |
| BP1：tracked-only guard 漏未核收安装脚本/源码 | fixed in current slice | 本 v2 §7 提供 commit 收录/字节/限定未跟踪检查及隔离反例；计划层待双路窄复审/主控回写，实际 guard 由主控/获通知后的 §7 sync 执行者执行，不提前放行真实安装 |
| BP3：启动配置中的有效非 HOME ZDOTDIR 未在写前检测 | fixed in current slice | 本 v2 §4/§6/§7 明确真实启动后查询、写前失败及验收断言；计划层待双路窄复审/主控回写，IE-B1 实现/隔离测试与完整代码审核证明 |
| PATH 前置影响 `.local/bin` 的其它同名命令；editable 源码/venv 移动或删除会失效 | fixed in current slice | IE-B1 README/实现 owner；披露有限副作用、失败清楚，不造恢复框架 |
| 真实 HOME sync、未激活新 shell、核收 commit/实际 metadata 的最终证据缺席 | covered by later approved slice | 主控/收到明确安装通知后的安装执行者；§7，既有授权流程停点，不提前宣称目标全部完成 |
| Linux/原生 Windows 尚无本轮真实 OS 执行证据；未知架构依赖锁/任意 shell 不受支持 | assigned to later work unit | Dayu 安装维护者；有真实平台需求/runner 时验证具体安装条件；本轮如实列实测范围，不声称全 OS 已通过，不新增业务门槛 |
| profile/入口碰撞（含 Q1 目的地父目录 symlink）、用户 alias/function 或后续 PATH 覆盖；Q2 隔离配置/缓存来源未记录 | fixed in current slice | IE-B1；§4/§6 预检、配置/缓存路径回执与新 shell 检查诚实失败，保留用户文件，不偷偷纠正。真实 sync 若遇到需改用户内容的具体冲突再由主控裁决 |
| 安装与 init 或其它编辑器同时写 profile | assigned to later work unit | 安装/init 维护者；本轮仅承诺顺序保全、明确不承诺并发；需要时再制定共享写入契约，不预建事务机制 |

Blocking questions：**无**。用户已确认 Bash 方向、目标、真实 sync 顺序和保留用户文件意图；本计划内机制选择无需重新询问。当前未完成：主控计划核对/新方案适用计划复审、全部实现/测试/pyright、完整代码审核/必要复审、工程交付核收、明确通知后的真实 sync/正式验收。下一入口是主控收齐并裁决仍审旧 Bash plan 的 MiMo69913 终态，对本 v2 的 BP1–3 及实际受影响面统一执行既定双路窄复审，并回写正式状态；Q1/Q2 交 IE-B1 实现/代码审核核对。不得把本次机制 probe 当计划 pass，不得沿用旧双审 pass 直接开始实施。本 writer 任务到计划交接为止。


## IE-B1 实现纠正（仅 BP3a / BP1a）

依主控 plan-pass 授权：本版相关 ZDOTDIR 示例只在 unset 时回退 HOME，显式空值拒绝；
正式 sync 的限定未跟踪输入命令仅新增精确 `--exclude=.DS_Store`，保留普通和 ignored
源码/安装脚本拒绝，不删除现有元数据、不使用 `--exclude-standard`。其余计划不变；
原冻结 v2 与 v1 保存快照不改。实现/验证详见 bash-implementation 回执，正式核销由主控双审裁决。
