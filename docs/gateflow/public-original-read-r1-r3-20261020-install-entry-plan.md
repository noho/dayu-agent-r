# PR206 默认命令入口安装增量计划

## 1. 依据、状态与本轮边界

本计划承接已确认的 [binding scope](public-original-read-r1-r3-20261020-install-entry-goal.md)，不重新索取目标确认。使用仓库 `AGENTS.md` 与 Gateflow；用户将本轮明确限定为 plan writer，因此本轮止于计划交付，不实施或推进后续 gate。

- 工作分支：`fix/public-original-read-r1-r3-20261020`。
- 本增量起点/base HEAD：`1856cf8d97468423c6a3ece5558a312d31802b20`，不是重新指定 PR206 的远端 base。
- 实际 preflight 分支和 HEAD 与上述一致。工作树已有主控的 authorization-update/control 修改及新 install-entry-goal；已只读核对它们恰为本次授权与入口记录，不改写、不纳入本 writer 的文件所有权。
- 同 PR206；版本保持 `0.1.5`。既有 R1–R3、版本增量、自身 `.venv` 安装和人工默认链接修正的有效证据不重开，也不算本次安装流程已验证。
- 本轮仅新增本计划及 `workspace/tmp/install-entry/plan-evidence/` 内必要隔离取证。未修改源码、测试、README、pyproject、控制/授权/目标记录；未安装包、改真实入口、操作 PR 或 tmux。

**Blocking open questions：无。** 主控计划核对/适用计划审核、实现、验证、独立代码审核、工程核收和真实 sync 均未完成；不能据本计划宣布任何一个后续 gate 通过。

## 2. 直接证据与根因

| 直接来源 | 已观察事实 | 对方案的约束 |
| --- | --- | --- |
| `README.md:9`、`:31` | 根 README 面向最终用户；源码安装目前只有 venv、activate、editable pip install，没有默认入口和持久 PATH 的发布步骤 | 修复安装交付 owner；README 只写可执行安装/检查/失败处理，不塞入工程门禁或取证过程 |
| `pyproject.toml:1`、`:7`、`:97` | setuptools 生成包；版本唯一声明为 `0.1.5`；console script 为 `dayu-cli = dayu.cli.__main__:exit_module` | 保留包安装机制和 CLI target；无需改 pyproject 或增版本 API |
| `dayu/cli/__main__.py` | 负责 application 启动和进程退出，不负责安装发布 | 不在业务 CLI 增加旧环境发现、入口修复或运行时 fallback |
| `dayu/cli/init_environment.py:1`、`:124`、`:349` | `init` 的持久化 owner 是用户确认的模型/可选集成环境变量与对应 shell profile，不是安装命令入口 | 不把 PATH 安装写入挤入 init；安装脚本保持独立，并逐字保留 init 的现有 block |
| `tests/cli/test_public_package_entrypoints.py` | 现有真实 wheel 测试核对声明、metadata 和 entrypoint，但不安装包或发布默认命令 | 可作受影响包契约回归，不能代替本次默认安装验收 |
| `pyrightconfig.json`、`tests/README.md` | 全量 pyright 目前覆盖 dayu/tests/utils；尚无专用源码入口发布脚本 | 若新增安装脚本，须纳入全量 pyright，不通过放 utils 获得脚本豁免 |

用户已给定的历史是：原 `/Users/leo/.local/bin/dayu-cli` 指向 `/Users/leo/.local/share/uv/tools/dayu-agent/bin/dayu-cli`（0.1.4），现已人工改向本仓 `.venv/bin/dayu-cli`。本计划仅引用该事实，没有检查真实默认链接、旧 uv 环境或调用方 PATH/项目环境。

动机成立，但范围是**源码安装交付缺少默认入口发布**，没有证据说明 console script、版本声明或财报业务存在新缺陷。激活只影响当前进程及其子进程；独立的新 shell 不因先前 activate 自动选中该 venv。只补一条 `ln -s` 还隐含了 `~/.local/bin` 已在有效 PATH 前部，无法独立满足已确认目标。

规划阶段只做了 shell 机制取证：隔离 HOME 的 `.zprofile` 先将 PATH 设为系统路径，`.zshrc` 再加入该 HOME 的 `.local/bin`；真实 `/bin/zsh -ic` 与 `/bin/zsh -lic` 均解析、执行隔离 marker，退出 0，stderr 为空。证据：[zsh-startup-receipt.json](../../workspace/tmp/install-entry/plan-evidence/zsh-startup-receipt.json)。这不是包安装、脚本实现、旧入口替换或用户真实 shell 的通过证据。

## 3. 最小方案及 owner

采用**现有包安装命令 + 一个小型默认入口发布脚本**，一个 implementation slice。包安装仍由 README 显式调用 venv/pip；新增 `scripts/publish_source_entry.py` 只发布该安装的默认入口和当前 macOS/zsh 所需的持久 PATH，不包装依赖解析或环境管理。

取舍依据：只有 `mkdir/ln` 的 README 命令不足以覆盖 PATH 持久化；继续堆入 profile block 去重、碰撞校验、失败处理，会变成难测试的内嵌安装程序。小脚本将这些已经必要的文件发布行为放到单一 owner，README 保持短且可复制。它不是通用 bootstrap：不做平台矩阵、shell 探测链、uv 迁移、可配置安装后端、插件、安装数据库或运行期自修复。

| 语义/动作 | 唯一 owner / source of truth |
| --- | --- |
| 包名、包版本、console script 声明 | `pyproject.toml`，由 setuptools/pip 产生实际安装 metadata 和 executable |
| 将当前源码安装到仓库 `.venv` | README 源码安装步骤及 venv/pip；失败由真实进程退出状态判定 |
| `.venv/bin/dayu-cli` 与默认链接、持久 PATH 的关联 | 新入口发布脚本；不委托调用方或业务 CLI |
| 实际安装版本与 metadata 位置 | 目标 venv 解释器的实际 site-packages 内 `.dist-info`；源码声明只用于对照 |
| 本次安装对应的精确 source commit | 工程/安装回执：核收 commit、源码干净性、安装命令与 editable `direct_url.json` 的源码路径关联；不在产品中新增版本或 commit 真源 |
| 其他工具环境、调用方项目配置 | 原 owner 保留；本增量不读其内部、不迁移、不删除、不改配置 |

脚本属于源码安装交付，不属于 UI/Service/Host/Engine/Runtime；放 `scripts/` 而非仅供分析的 `utils/`，也不塞入 `dayu` 业务包。仅用标准库，无 Dayu 运行期 import、lazy import 或新分层依赖。对实现所需输入优先直接使用有类型的源码根目录、HOME 路径参数；命令入口从自身文件位置及当前用户 HOME 取得这些已知输入，无需公开可配置目标/平台框架。函数拆分、局部类型和原子替换的具体写法由实现者决定。

## 4. 安装公共契约与必要失败行为

### 4.1 目标与发布顺序

1. 在检出的源码根目录执行 README 命令，使用 Python 3.11 创建/复用 `.venv`，用**该目录内解释器**执行现有 editable 安装及现有平台约束。
2. pip 成功之后才调用入口发布脚本；README 用 `&&` 串联依赖步骤，不允许 pip 已失败仍继续发布默认入口。无需 activate 才能完成安装。
3. 脚本先校验当前解释器确属此源码根的 `.venv`、目标 console script 存在且可执行，以及该 venv 中实际安装的 dayu-agent metadata 与本次源码安装来源一致。对照版本只读取 pyproject，不另写 `0.1.5` 常量；不得接受 cwd 的 `.egg-info` 作为安装证明。editable 来源应指向当前源码根。
4. 仅将 `$HOME/.local/bin/dayu-cli` 发布为指向**当前源码根下 `.venv/bin/dayu-cli` 的绝对符号链接**。不复制 executable、不生成运行期 wrapper，不靠当前工作目录解析目标。
5. 预检入口和 profile 的允许形态，准备完整新内容/临时链接；持久 PATH 写入成功之后再替换默认链接。已有文件用同目录原子替换避免撕裂；不引入跨文件事务框架。
6. 完成后校验发布的链接与脚本自己的 profile block；退出 0 只表示这些安装发布动作完整成功。README 还要求在新开的未激活正常 zsh 中检查命令和 help；不得把当前 shell 的 activate/export/rehash 作为该检查。

包安装和 profile/link 不是一个原子事务。脚本不声称回滚 pip，也不把部分文件发布描述为完整安装成功。

### 4.2 入口状态

| 初始状态 | 必须行为 |
| --- | --- |
| `.local/bin` 或 `dayu-cli` 缺席 | 按需建立目录，创建指向本次 `.venv/bin/dayu-cli` 的链接 |
| `dayu-cli` 为历史旧链接或其它旧符号链接 | 替换**链接目录项本身**；不沿链接打开或修改旧目标。旧 uv 环境全部保留，无需识别其包或版本 |
| `dayu-cli` 为 dangling symlink | 仍按链接处理，不以 `exists()` 误判为完全缺席或向旧目标写入 |
| 链接已指向本次目标 | 完整安装步骤仍可重复执行；结果收敛到同一链接和唯一 PATH block，不累加内容 |
| 入口为普通文件、目录或特殊文件 | 非零退出并指出冲突路径，不静默删除/覆盖未知内容；这是显式失败，不是“旧入口已处理” |

已知真实人工链接属于“已指向本次目标”状态，允许保留；工程必须另外在隔离场景验证旧链接与缺席入口，不能仅验证这个 no-op 路径。

### 4.3 新正常 shell 的 PATH

- 本次默认入口交付限于当前实际 **macOS、zsh、标准 HOME 下的 `~/.zshrc`**。在该文件末尾维护唯一、独立命名的 Dayu 源码安装 PATH block，将 `$HOME/.local/bin` 放在命令搜索前部并保留原 PATH 其它项；不要复用或改写 `dayu-cli init` 的 secret block。
- `.zshrc` 被普通交互 zsh 与登录交互 zsh 读取；macOS 登录时 `.zprofile` 中的 PATH 配置发生在前，因此不用只在当前安装 shell 临时 export，也不只写登录专用 `.zprofile`。
- profile 缺席则创建；存在则保留自己 block 以外的字节和现有权限。重复执行只保留一个完整 block，安装结果不依赖 profile 中原先是否已有 `.local/bin`。
- 不解析用户整份 shell 配置、不改 alias/function、不增 `.zshenv`/系统 profile。非标准 `ZDOTDIR`、profile 为链接/非普通文件、损坏或重复的受管 marker 等不能在允许边界内确定写入时，明确非零退出；不自行追踪到其它配置文件或声称已完成。无需为这些无当前证据的配置实现支持框架。
- 现有 Linux/Windows 包安装说明保留；新默认入口步骤明确标为 macOS/zsh，不冒称多平台默认入口已经交付。

### 4.4 失败的最小承诺

- 安装命令失败：不进入入口发布；保留真实退出码与失败输出。现有 venv 可能已被 pip 部分修改，不能承诺整个安装回滚。
- 目标/metadata/source identity 不合法，或预检发现入口/profile 冲突：非零退出，默认链接和 profile 原字节不变；不导入业务 CLI 作 fallback，不扫描别处的安装来补足。
- 写入阶段 I/O 错误或中断：不得输出成功；已存在的单文件内容不能被截断。链接最后发布，因此 profile 成功、链接发布失败时，旧链接仍在；允许保留已生效的 PATH block，须明确报告“profile 已更新、入口未完成”等实际阶段和目标路径，重复执行可收敛。不增加 durable journal 或强行伪装全部回滚。
- 若最终替换已完成后读回失败，报告真实部分状态/无法确认，不谎称恢复旧态。清理自有临时项，清理失败则报告保留路径；不输出 profile 内容或 secret。
- 不删除旧链接目标及其父环境，不修改调用方项目配置；权限不足或特殊用户配置也不自动扩大操作路径。

## 5. 一个必要 slice 与影响文件

**Slice IE1：源码安装可发布默认入口，且在下一正常 zsh 生效。** 包括安装契约实现、测试和用户文档，不机械拆成多个 slice。

预期变更：

- 新 `scripts/publish_source_entry.py`：上述有限发布 owner，标准库、有类型签名及中文模块/函数文档；不加入业务包、安装后端或通用配置模型。
- 新 `tests/install/test_source_entry.py`：owner 级文件发布/失败契约及真实 subprocess/zsh 场景。可新增该测试目录所必需的最小文件；不要在 `tests/cli` 伪装成业务 CLI 行为。
- `pyrightconfig.json`：将新脚本所在 `scripts` 纳入现有全量检查，不排除/压制它的报错。
- 根 `README.md`：按已读职责更新源码安装命令、macOS/zsh 默认入口与新终端检查、可执行的失败说明。只写实际用户操作；不写审核、commit 绑定取证或本工程历史。
- `tests/README.md`：当前测试层级/命令与 pyright 覆盖范围说明加入 install/scripts；此文件没有独立 Agent 更新约束，按其既有测试手册职责更新。
- 实现/验证/审核/交付事实由主控记录到本线 gate artifact；临时证据放本次 `workspace/tmp/install-entry/` 独立目录。

明确不修改 `pyproject.toml` 的版本、entrypoint 或依赖，不改业务 CLI、调用方、其它工具环境；不触及 Engine/Host/Fins/Config 代码，因此不触发其 README 更新。安装脚本不改变四层依赖/装配边界，`dayu/README.md` 无需更新。若实现实际偏离这些判断，主控应重新核对职责和 scope，不机械扩写 README。

README macOS 源码安装块预期形态如下，最终措辞与局部实现由实现者完成：

```bash
python3.11 -m venv .venv &&
.venv/bin/python -m pip install -e ".[test,dev,browser]" \
  -c constraints/lock-macos-arm64-py311.txt &&
.venv/bin/python -I scripts/publish_source_entry.py
```

安装之后新开正常 zsh，运行 `command -v dayu-cli` 与 `dayu-cli --help`；预期命令入口为 `~/.local/bin/dayu-cli`，help 退出 0。需要 Chromium 时用 `.venv/bin/python -m playwright install chromium`，避免取消 activate 后误用其它环境的 `playwright`。不要为本次增量改变 wheel 安装语义；根 README 应避免让 macOS 源码默认入口承诺被误读为任意 wheel 安装都会改 shell 配置。

## 6. 工程验证：隔离 HOME、目标与真实命令

### 6.1 自动化 owner 验证

必须覆盖：缺席入口、给定历史形态的旧链接、dangling link、已正确链接、整个安装重复执行；同一旧目标树的文件清单与逐文件 SHA256 安装前后完全一致。旧环境只用隔离 HOME 下的合成目录和 sentinel 字节，不打开真实 uv 环境，不以模拟的旧版本 metadata 充当历史事实。

还需覆盖：profile 缺席/已有其它设置及 init block 的保留、PATH 已包含/未包含目标目录、唯一 block 和重复运行的内容稳定、绝对目标/仓库外 cwd、普通文件或目录入口冲突、无效目标/安装来源、profile 形态或 marker 错误、预检失败不修改已有文件、profile 发布失败、profile 成功后链接发布失败及如实非零结果。故障注入留在文件系统发布 syscall 边界，不用 fixture/fallback 将错误来源塑成正确数据；无须枚举与当前契约无关的环境组合。

真实 zsh 测试通过子进程传入隔离 HOME 和干净环境；不要修改 pytest 父进程 HOME。从仓库外 cwd 用 `/bin/zsh -ic` 及 `/bin/zsh -lic`，不带 `-f`，不在被验证 shell 里手动 source/export/activate。至少一组 `.zprofile` 先把旧目录放前或移除 `.local/bin`，证明 `.zshrc` 安装步骤仍使 `command -v dayu-cli` 选中新入口。marker/sentinel 只能证明发布和选择，不能冒充实际 dayu-agent 的 help/metadata。

代码修改后按 AGENTS 使用仓库现有 `.venv` **运行测试和类型检查**，不向该 live `.venv` 安装：

```bash
source .venv/bin/activate
python -m pytest tests/install/test_source_entry.py \
  tests/cli/test_public_package_entrypoints.py -q \
  --cov=scripts.publish_source_entry --cov-report=term-missing \
  --cov-fail-under=80
pyright
```

预期：受影响用例通过；新生产脚本单文件覆盖率至少 80%，不能只依赖未计入覆盖率的 subprocess 给出数字；全量 pyright 为 0 errors，不通过 Any、ignore、排除或降级设置掩盖错误。若改到其它代码，补对应受影响测试和文件覆盖断言。包契约测试使用既有隔离 wheel 构建，不安装进 live 环境；不重扫财报 fixture、不重跑未受影响的旧业务回归。

### 6.2 真实包安装集成

在 `workspace/tmp/install-entry/<implementation-run>/` 下准备当前待审源码的独立副本和来源 manifest，复制仅安装所需的 pyproject/README/LICENSE/dayu/constraints/scripts，不带 live `.venv`、真实 HOME、业务 fixture 或旧工具环境。使用已知 Python 3.11 创建副本自己的 `.venv`；需要依赖时在**这个隔离目标**执行真实安装。不要为了省依赖把现有 live `.venv` 当安装目标、冒用源码 metadata 或注入 PYTHONPATH。

验证命令以实际 README 安装块为准，记录真实 argv、cwd、环境白名单、stdout/stderr/退出码；不要让测试维护一份独立安装算法替代 README。隔离 HOME/源码目录是测试边界输入，已知解释器路径仅用于启动 Python 3.11，不盘点全局解释器或旧 uv 安装。

命令轮廓（`ENTRY_SOURCE_ROOT`、`ENTRY_HOME` 均为上述独立目录；实现者保存实际展开后的命令）：

```bash
# 在隔离源码根执行与 README 相同的三步；HOME 通过 subprocess env 传入。
python3.11 -m venv .venv &&
.venv/bin/python -m pip install -e ".[test,dev,browser]" \
  -c constraints/lock-macos-arm64-py311.txt &&
.venv/bin/python -I scripts/publish_source_entry.py
```

至少执行下列矩阵，不允许把已修真实链接当其中一行：

| 场景 | 准备与实际操作 | 必须断言 |
| --- | --- | --- |
| fresh | 隔离 HOME 无 `.local/bin/dayu-cli`、无 PATH block；真实执行完整安装块 | 链接正确、profile 持久化；新正常 shell 解析新入口；真实 metadata/来源属于隔离目标 |
| legacy | 隔离 HOME `.local/bin/dayu-cli` 指向其 `.local/share/uv/tools/dayu-agent/bin/dayu-cli`；保存旧目标树全部字节 manifest；完整安装 | 新链接替换旧链接，旧目标树逐字节不变；旧 executable 不被用于验证新安装 |
| repeat | 对 fresh/legacy 成功状态至少再次执行完整安装块，不只重跑发布脚本 | 全流程退出 0；链接一致、profile 单 block 且其它内容保持、旧目标树不变；新正常 shell 仍命中新目标 |

对真实包集成至少运行一次新 shell 的裸 `dayu-cli --help` 并保存真实退出，及目标解释器 `-I` 下实际 `.dist-info`、metadata 版本/位置和 editable 来源；要求与副本源码声明 `0.1.5` 及来源 manifest 一致。该隔离集成说明新流程的转换行为，不代替核收后的真实 HOME 正式验收。

## 7. 核收后真实 sync 与正式验收（本轮不执行）

前置条件：IE1 实现和必要验证完成，主控裁决适用计划审核及双路独立完整代码审核/必要复审，通过同 PR206 工程交付核对；**工程已核收，且收到明确安装通知**。届时才在真实自身仓库按更新 README sync，不先恢复真实旧链接造复现；现人工链接保留。安装前记录核收的完整 OID、当前源码根与 tracked 内容一致性；不能仍把本增量起点 `1856cf8d…` 写作未来新交付 commit。

正式检查使用真实 HOME、新的未激活正常 zsh，从仓库外 cwd 开始。示例启动形态如下，真实执行应保存两通道及退出码；不注入新的 `.local/bin` PATH，也不带 `-f` 跳过用户启动文件：

```bash
cd /private/tmp
env -u VIRTUAL_ENV -u PYTHONPATH -u PYTHONHOME \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin \
  /bin/zsh -lic '
    [[ -z "${VIRTUAL_ENV-}" ]] || exit 1
    command -v dayu-cli || exit 1
    whence -w dayu-cli || exit 1
    whence -p dayu-cli || exit 1
    dayu-cli --help
    entry_help_exit=$?
    print -r -- "help_exit=$entry_help_exit"
    exit "$entry_help_exit"
  '
```

不读取/输出整份真实 profile 或整个 PATH，不搜索其它命令环境。对同一个真实命令链形成可追踪回执：

1. `command -v`、zsh 命令类型及外部解析路径：必须是本次发布的 `/Users/leo/.local/bin/dayu-cli`；alias/function 或其它入口不能混同通过。
2. 仅解析这个入口本身的符号链接，结果为 `/Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli`；记录生成 executable 的解释器关联。当前已知路径可核对其 shebang，不向旧 uv 环境追踪取证。
3. 使用上一步实际目标解释器启动 `-I` 探针，记录 `sys.executable`、`sys.prefix` 及其真实 site-packages。venv 的 python 自身可能链接到基础解释器，不能仅凭 `python.resolve()` 丢掉 venv 身份。
4. 从该解释器的 `sysconfig` purelib/platlib 路径显式发现 dayu-agent distribution，记录实际 `.dist-info/METADATA`、Name、Version、`direct_url.json` 路径及 editable 源码目录。必须是目标 `.venv` 内的真实 dist-info、版本 `0.1.5`；不能仅用仓库 cwd 下裸 `version()` 或源码 `.egg-info` 得出结论。
5. 将 editable 来源目录关联到核收的完整 source commit，记录该目录 `git rev-parse HEAD` 与 tracked 内容无偏离的结果及实际安装命令。`direct_url.json` 的本地 editable 路径本身不包含 git commit，不能假称它已经独立证明 commit；不得新增产品级 commit/version 真源。
6. 保存同一个正常 shell 中**裸** `dayu-cli --help` 的完整实际命令、两通道和退出码 0。探针不替代该 help；源码/wheel 声明、旧 `.venv` 安装回执和人工修链均不能替代本次证据。

上述 metadata/关联探针仅为 gate 取证，放 `workspace/tmp/install-entry/<sync-run>/`，采用有类型/中文文档的临时代码；不加入业务 CLI、不会导入 Dayu 执行业务。若真实 shell 不符，诚实记录验收失败并按 owner 修复，不改调用方配置、不扫描其环境，不给自己补一次临时 export 宣称通过。portfolio-manager 独立验证仍由其 owner 负责。

## 8. 重要决策、审核与接续

供主控决定 Planreview 适用性的**重要安装公共契约/外部文件影响**：

- “README 源码安装成功”新增默认链接发布与持久 PATH 的承诺，不能只核 pip。
- 替换 `$HOME/.local/bin/dayu-cli` 目录项，明确保留旧目标；碰撞对象与失败状态有对外行为。
- 修改 `$HOME/.zshrc` 的唯一受管 block，将 `.local/bin` 置前；这会影响该目录内所有同名命令的搜索优先级，须在 README 对修改目标有简短说明，不能把它藏成无副作用操作。
- profile/link 的部分成功与非零退出语义，以及未来真实 sync 的核收/通知停点。

这些涉及用户目录持久文件和默认命令的公共安装承诺，**建议按重要契约执行 Planreview**，最终适用性与计划核对由主控记录；本 writer 未代替主控宣布审核 pass。计划审核聚焦 owner、外部文件边界、PATH、生效及失败验收，不要求先穷举本地代码实现。

一个 slice 完成后按既定 gate 顺序进入最终组合版本的独立完整代码审核；沿用 binding scope 指定 MiMo/DS 双路路由，由主控派发、裁决及必要修复/受影响面复审。本增量计划不重开 R1–R3 与 0.1.5 已核收事实；审查应检查新增安装交付与现有包契约是否一致。随后主控更新同 draft PR206，核对精确 head/base、完整 diff、标题/正文、必要 CI 与 push，完成工程 closeout。merge 仍另授权。

**本计划交付后的下一入口：主控计划核对及 Planreview 适用性裁决。** 实现、测试/覆盖率、全量 pyright、README 更新、双路审核、PR 更新及核收后真实 sync 均是后续事项，不能标为已做。

## 9. 风险分类、owner 与 destination

以下为规划风险及未覆盖项，不是已修复事实；其中 `fixed in current slice` 表示必须由 IE1 关闭的范围内风险，完成前须以实际证据改写状态，不能据分类提前放行。

| 风险/未覆盖项 | Gateflow 分类 | Owner | Destination / 非阻塞依据 |
| --- | --- | --- | --- |
| 仅装包未发布默认命令、旧链接仍命中 0.1.4、缺席与重装无证据 | fixed in current slice | IE1 实现者 | IE1 隔离真实安装矩阵；当前待实现，不可豁免 |
| 只在当前 shell 可用；持久 PATH 与 profile 文件/旧 init block 被误改；部分失败冒充成功 | fixed in current slice | IE1 实现者、独立 reviewer | owner 测试、真实 zsh/故障验证及代码审核；范围内必须关闭 |
| 新脚本未纳入类型检查或覆盖率仅统计父进程少量行 | fixed in current slice | IE1 实现者 | pyright include、owner 级覆盖率 >=80% 与测试 README；不得以 utils 豁免 |
| 真实正常 shell、实际解释器/安装 metadata 与核收 commit 尚无本次证据 | requiring new issue or explicit user decision | 主控/获通知后的自身安装执行者 | binding goal 明确要求先工程核收及明确安装通知，通知到达后进入真实 sync/正式验收；不是第二工程 slice。本轮无待答问题，但不能提前执行或将整个安装目标宣称完成 |
| 非 macOS/zsh、非标准 ZDOTDIR、特殊/链接 profile、用户后续覆盖或 alias/function 等配置 | assigned to later work unit | Dayu 安装维护者；若实际阻塞由主控裁决 | 本次不承诺通用支持；脚本可判定的异常显式失败。若真实验收遇到它们，先记录实际原因，再在现有 scope 能修则修；确需新增外部文件/配置支持时另作用户决策，不以 deferred 为由通过失败验收 |
| 把 `.local/bin` 提到前部会改变其中其它同名 executable 的优先级 | fixed in current slice | IE1 文档/实现 owner、计划 reviewer | README 说明该持久 PATH 操作与作用；不扫描其它工具，不自动改其它入口 |
| editable 源码在成功验收之后又被移动、删除或修改 | assigned to later work unit | 使用者/Dayu 安装维护者 | README 说明源码路径/venv需保留，迁移后按源码安装步骤重装；本次不造源码副本版本库或自动修复器 |
| 调用方独立验证、合并与外部同步 | assigned to later work unit | portfolio-manager / 有 merge 授权者 | 其独立接续；本线不得查其环境或代改配置，merge 另授权 |

不存在未分类 residual risk，也没有需要本轮用户回答的 blocking open question。当前仍未完成的是上述后续工程与正式验收，不是 R1–R3/版本工程的历史缺口。
