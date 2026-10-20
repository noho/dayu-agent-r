# IE-B1 Bash 安装 owner 实现与隔离验证回执

本回执只交付 writer 的 implementation / validation slice，依据已确认的
[goal](public-original-read-r1-r3-20261020-install-entry-goal.md)、
[direction](public-original-read-r1-r3-20261020-install-entry-plan-direction.md)、
[v2](public-original-read-r1-r3-20261020-install-entry-bash-plan-v2.md) 及主控
[bash-adjudication](public-original-read-r1-r3-20261020-install-entry-bash-adjudication.md) 末节 plan-pass。
下一入口是主控冻结本次 writer 文件并派发既定双路完整代码审核；没有代主控核销 finding，
没有 commit、push、PR、tmux、merge 或 live sync。旧 R1–R3 与版本有效证据不重开。

## 基线、输入与准确输出

分支 `fix/public-original-read-r1-r3-20261020`，基线及本轮 HEAD 均为
`1856cf8d97468423c6a3ece5558a312d31802b20`。起始 dirty 的 control/authorization、计划、
裁决和 review 属于主控；没有修改它们（仅 v2 获额外窄修授权）。这是实际 dirty 源码快照，
**不是核收 commit**，也没有把 0.1.5 当作 commit 身份。

所有工程证据根：
`workspace/tmp/bash-implementation-20261020-194550/`（下称 `E/`，系统时钟创建）。
输入为仓库 `AGENTS.md`、根 README 的 Agent 更新职责、`tests/README.md` 的职责、上述四份
已授权记录；另只读 `pyproject.toml`、平台约束、公开入口测试及 init 环境持久化 owner，核对职责。

本轮 writer 文件精确清单：

- `scripts/install-source.sh`
- `scripts/install_source_query.py`
- `tests/install/test_source_install.py`
- `tests/install/test_install_source_query.py`
- `README.md`
- `tests/README.md`
- `pyrightconfig.json`
- `docs/gateflow/public-original-read-r1-r3-20261020-install-entry-bash-plan-v2.md`（仅 BP1a/BP3a）
- 本回执 `docs/gateflow/public-original-read-r1-r3-20261020-install-entry-bash-implementation.md`

`E/writer-final-snapshot/` 保存上述全部文件原始字节；`E/writer-final-manifest.json` 给出每文件
路径、快照路径、大小、权限、SHA256。`E/delivery/install-input-snapshot/` 完整保存此次安装所需
pyproject/README/LICENSE/dayu/constraints/scripts；`install-input-manifest.json` 保存路径、类型、
权限、mtime、hash/链接文字。`E/installation-input-byte-verification.json` 将必要文件逐字节与当前
工作树、delivery 的 fresh/legacy 实际安装源码核对。各 run 的 baseline-head/status/dirty.diff
保留实际 HEAD 与 tracked dirty 差异；新文件由快照覆盖，不把 `git diff` 的 tracked 部分当完整输入。
`E/scope-untouched.*` 记录 `dayu/` 和 `pyproject.toml` 对 HEAD 无变化。

## 实际 owner 行为

动机与根因成立：原 README 只安装仓库 venv，没有完成本次包安装到默认命令的交付。
本 slice 在安装 owner 修复，不改业务 CLI、版本声明、财报业务或调用方环境。

Bash 3.2 脚本拥有预检、适用锁选择、同一目标 venv/pip、有限 profile/入口发布、阶段失败以及
正常 shell 检查。唯一版本与 console target 仍来自 pyproject，实际安装事实来自目标 site 的
真实 dist-info。Python helper 只读标准库查询平台、venv、metadata/source；不发布文件，不管理
profile，不生成版本状态或安装数据库。其必要性是同时可靠验证实际 site 唯一 metadata、
URL 编码与 symlink 归一化、声明与 console target、实际模块来源；没有嵌入 Python 规避类型。

- 选择 Python 3.11 和现有匹配锁；额外校验 64 位解释器，避免把 OS 的架构名称当作 Python 位数。
  Windows Git Bash 使用 native 路径转换及 Scripts/.exe；Windows Python 与 WSL Linux 混用拒绝。
- `.venv`、目的地父目录 `.local` / `.local/bin`、profile 和默认入口先预检。未知普通文件、特殊文件、
  目录、目录型链接、profile 冲突与同名 `.exe` 拒绝。入口仅接受缺席、安全 symlink 或逐字相同 launcher。
- pip 只对本源码 `.venv` 真实安装 `-e <source>[test,dev,browser] -c <platform-lock>`。
  来源检查在源外 cwd、目标 Python `-I` 下读取实际 purelib/platlib 的唯一 dist-info，核对 Name、
  Version、entry point、editable/direct_url、标准路径归一化后的 source 与实际模块 origin。
- 普通 launcher 只有 shebang 和 `exec <pip-console> "$@"`，没有运行时 fallback。旧 symlink
  只替换目录项，保留目标树。Bash 3.2 `%q` 可生成包含非 UTF-8 原始字节的合法 Bash 引用；
  工程对 launcher 保存原始字节、base64/hash，真实执行证据验证路径与参数，不擅自转码。
- profile 原文、权限及 init block 保留，独立 PATH block 精确匹配才幂等；损坏或多块拒绝。
  profile 先发布、入口最后发布，单文件临时项替换避免截断。失败报告阶段，不伪称跨文件回滚。
- 源外正常 Bash/zsh `-ic/-lic` 检查实际外部命令类型、解析路径及裸 `dayu-cli --help`。
  不 activate、不手动 source、不使用 `-f/--norc`，初始 PATH 不注入目标目录，移除继承 venv/Python 影子变量。
  成功只在安装、来源、console help、默认入口及两种正常 shell 全通过后输出。

## BP1a / BP3a 的有限修复

v2 原冻结副本仍为
`workspace/tmp/public-original-read-r1-r3-20261020/install-entry-20261020T101200Z/bash-plan-fix-evidence/bash-plan-v2.md`，
SHA256 `b280bbd5fdd86aadf9e0c302ac170c6e9316203f5d8310e8e10b024e647eadf7`，未修改；v1 和两版保存快照不变。
`E/bp1a-bp3a-narrow-diff.*` 保留真实 no-index diff（退出 1 表示有这份授权差异）。

BP3a：实现及 v2 示例只在 unset 时用 `${ZDOTDIR-$HOME}` 回退，显式 empty 拒绝。
真实 zsh 已覆盖 unset、empty、explicit HOME、非 HOME、`.zshenv` 设置 empty/非 HOME；
另以 `.zprofile` 仅在登录阶段设置 empty/非 HOME，验证先通过非登录检查后仍在 `-lic` 写前失败。
所有失败场景断言没有创建目标 venv、默认入口或 profile，原文件字节/权限/mtime 保持。
正常模式发布后再次断言有效值仍为 HOME；没有强制重设继承 ZDOTDIR 或绕过启动配置。

BP1a：v2 正式 sync 命令仅增加精确 `--exclude=.DS_Store` 与对应说明，保留具名 cache 排除及
普通/ignored 源码、额外脚本拒绝，不使用 `--exclude-standard`，不删除既有 `.DS_Store`。
commit 绑定、tracked/untracked guard 及正式输入 raw blob 对照仍由主控后续 sync 回执执行，
没有放入 CLI 或本安装脚本。主控已有原/修正命令三例证据适用复用；本回执不把未提交 writer 文件称作已核收。

两项 writer 修复已实现；**正式状态必须在本次双路完整代码审核实质复验后由主控核销，不能留到 live sync**。

## 验证命令与真实结果

先写 owner 行为测试再实现：`E/red.*` 记录 4 failed / 11 passed，退出 1（实现缺席时的正行为失败）；
实现后的首轮 `first.*` 为 15 passed、退出 0。随后按真实新增边界补充测试。
最终受影响检查均先 `source .venv/bin/activate`，现有 live venv 仅用于测试/类型检查，没有向其 pip 安装：

```bash
source .venv/bin/activate
COVERAGE_FILE=workspace/tmp/bash-implementation-20261020-194550/coverage-handoff \
  python -m pytest tests/install tests/cli/test_public_package_entrypoints.py -q \
  --basetemp=workspace/tmp/bash-implementation-20261020-194550/pytest-handoff \
  --cov=scripts.install_source_query --cov-report=term-missing
python -m pyright
bash -n scripts/install-source.sh
```

最终 `affected-handoff.*`：退出 0，**81 passed**；helper 单文件 **96%（103 statements，4 missed）**。
`pyright-handoff.*`：退出 0，0 errors / warnings / informations；`bash-n-handoff.*`：退出 0。
Pyright 提示新版本可用的原始输出保留，没有安装新版本或绕过检查。
`E/pytest-handoff/` 保留测试文件系统、实际 wheel 构建日志及每次 Bash 子进程的 argv/cwd/
环境白名单/两通道/退出 JSON，索引见 `behavior-command-index.json`。受控 metadata、launcher 参数、
Git Bash 路径转换、I/O 与清理失败均是 unit/边界测试，不冒充真实 OS 或 pip 安装成功。

最终字节版 README 真实矩阵以 `E/delivery/` 为准：

| 场景 | shell | 完整 README 安装 | 独立 `-I` metadata | 结论 |
| --- | --- | --- | --- | --- |
| fresh-1 | 本机 zsh | 0 | 0 | 独立 HOME、源码、venv，从缺席入口发布 |
| fresh-2 | 本机 zsh | 0 | 0 | 完整重复 pip/来源/发布/正常 shell，不仅重复发布 |
| legacy-1 | 本机 Bash 3.2 | 0 | 0 | 合成旧 symlink 转普通 launcher，旧树保持 |
| legacy-2 | 本机 Bash 3.2 | 0 | 0 | 同状态完整重复，仍正确来源与单 block |

每行 `<label>.command.json/.stdout/.stderr` 保留精确脚本 argv、源码 cwd、完整环境白名单、起止时间和退出；
`<label>-metadata.*` 记录实际 0.1.5 dist-info、editable/source、解释器、prefix、scripts、console、模块 origin。
源码目录含中文与空格。脚本内正常 shell/metadata/console 检查 cwd 为 `/`，不依赖源码 cwd。
没有 `--no-deps` 安装、fake pip/help、marker 成功或借用 live site-packages。
现有公共 wheel 测试的 `--no-deps` 仅是既有构建步骤；未用它代替任一真实安装。

工程配置为 `PIP_CONFIG_FILE=/dev/null` 禁用外部配置，`PIP_CACHE_DIR=E/download-cache`。
该普通 HTTP/wheel cache 首轮在本工程新建，后续显式复用；没有读取旧 UV 或其它工具环境。
`E/cache-origin.txt` 和各 run 的同名记录保存缓存来源，实际 pip 输出保存下载/命中来源与完整依赖结果。
较早 `E/`、`E/final/` 的成功矩阵与 `E/legacy-root-proof/` 的两次完整安装原件均保留，不覆盖为最终结果。
`legacy-root-proof` 补证清单包含旧树根 `.` 本身、所有相对路径、类型、权限、mtime、普通文件 hash、原始链接文字；
前后严格相等。其 Bash 发布逻辑与最终逐字相同，helper 后续仅增加安装前 64 位拒绝，保全证据仍适用。
这些旧树均明确为合成资产，没有读取真实旧 UV 安装。

`postcheck_v3.*` / `fresh,legacy-post3-{ic,lic}.*` 为额外正常 shell 证据：源外 cwd，真实 type/whence、
command-v、help 均退出 0；`fresh,legacy-shadow3-metadata.*` 在故意注入无效 PYTHONHOME、
假 PYTHONPATH/999 metadata 的情况下，目标 `-I` 仍定位正确安装。它们绑定 `E/final/` 源码，
与最终 Bash 逐字一致；helper 仅新增平台位宽拒绝，来源/正常 shell 检查未变，可作受影响范围外补证。

README wheel 段还实际用独立 `E/wheel-target`、`E/wheel-home` 运行同一目标解释器的真实含依赖安装：
`wheel-create/install/show/metadata/help.*` 全部退出 0。wheel 取自保留的真实公开入口测试构建产物；
`-E -P -m pip show dayu-agent` 与 `-E -P -m dayu.cli --help` 属于该解释器，探针核对唯一实际 dist-info、
版本、site、module origin 与非 editable direct_url，消除旧 DS F1 的裸 PATH 假确认。
这是独立 venv wheel 安装：`no_user_site=0`，但该 venv 的 `ENABLE_USER_SITE=False`；
**没有声称真实 wheel→user-site 安装矩阵通过**。BP2 既有 user-site flags 机制证据仍按 v2 适用。

## 失败历史与 docs decision

没有删掉失败：`red.*` 为测试先行；`pyright-2.*`、`pyright-final.*` 曾记录测试解释器定位的
3 个 `str | None` 报错，已改为严格返回 str 的函数，最终全量通过；`fresh-post-ic.*` 的临时后验探针
因 zsh 只读 `status` 退出 1；v2 后验脚本又因误按 UTF-8 读取 Bash `%q` 字节退出 1。
均只修临时取证脚本，v3 成功；原脚本、实际失败子进程日志、工具回传补记保存在
`E/tool-failure-history.json`。最初 rg 对尚不存在 scripts 的退出 2 亦记录。
有意注入的 pip 无索引失败、metadata/source/help/alias/function/PATH 冲突、mv/清理失败保留在测试子进程 JSON。
没有发生被掩盖的外部下载失败。非 TTY Bash job-control stderr 原样保留，不当成业务失败或真实 TTY 验证。

根 README 命中安装、默认入口、用户工作流触发，按最终用户职责更新源码脚本、平台条件、保留位置、PATH 副作用、
失败定位、新终端检查及同目标 Chromium 命令；wheel 仅给必要目标解释器、版本/位置和 help 命令，未塞治理验收脚本。
`tests/README.md` 命中新测试层级职责，记录 install 测试、coverage/type 方式。
只有新增 Python helper 才扩 pyright include。业务层及装配关系没有变化，不触发其它层 README。

## 风险分类、owner 与未完成项

| 项目 | 分类 | owner / destination |
| --- | --- | --- |
| 安装 owner、来源一致性、碰撞、profile 保全、失败幂等、BP1a/BP3a writer 修复 | fixed in current slice | 当前实现与测试；主控下一轮双路完整代码审核实质核对后正式核销 |
| 默认 PATH 前置影响同目录其它同名命令；移动源码/venv 会使入口失效 | fixed in current slice | README 安装 owner 已披露；不增加恢复框架 |
| 无跨文件事务，pip/发布失败可留下部分状态 | fixed in current slice | Bash 阶段输出及测试诚实处理；不声称回滚 |
| Linux/WSL/Windows Git Bash 真机安装、Windows 平台实际路径/.exe 运行、TTY 专属配置 | assigned to later work unit | 安装维护者 / 有对应 runner 时；本轮仅当前 macOS 两种真实正常 shell及受控分支测试 |
| 任意未知 shell 配置、多个 owner/编辑器并发写 profile | assigned to later work unit | 安装/init 维护者；当前仅有限配置与顺序保全契约，未建通用框架 |
| wheel user-site 真实整轮矩阵、完整模型/财报跨平台回归 | assigned to later work unit | 安装/业务维护者；非本 binding goal 的新增门槛，不冒充已验证 |
| 正式核收 commit、tracked/untracked/raw blob guard、真实 HOME/default/profile/live venv sync | covered by later approved slice | 工程核收及明确安装通知后的主控；BP1 执行与真实验收回执 |

没有 writer 范围内未完成实现/验证 blocker。当前**尚未**双路完整代码审核/必要复审、主控工程核收、
同 PR206 交付或真实 sync；下一入口由主控执行完整代码审核并核销 BP1a/BP3a。
真实 HOME、default、profile 和现有 live `.venv` 均未安装/发布变更；版本保持 0.1.5。
