# PR206 安装 owner：C1–C6 必要修复与受影响验证

本回执是 fix writer 的实现/验证交付，不是正式 finding 核销或工程核收。
依据 [binding 裁决](public-original-read-r1-r3-20261020-install-entry-bash-code-adjudication.md)、
[已确认目标](public-original-read-r1-r3-20261020-install-entry-goal.md)、最新 Bash 方向及 v2，
仅修 C1–C6。双路完整首审为 [204535](../reviews/code-review-20261020-204535.md)、
[204928](../reviews/code-review-20261020-204928.md)，不重开旧 R1 业务历史。

基线及交付时 HEAD 均为 `5c179fdcb217634c31d66c60a141cf2909987f39`，分支
`fix/public-original-read-r1-r3-20261020`，同 PR206，包版本保持 0.1.5。
这是 dirty 字节交付，**不是核收 commit**。初始 control 追加、两份 review 和裁决是已声明的
主控 owned 内容；本 writer 未改它们。未 commit/push/PR/tmux/merge，未执行真实 HOME、
默认入口、profile 或 live `.venv` 安装，未读取真实旧 UV 内部、其它工具环境或调用方项目配置。
现有 `.venv` 仅 source 后运行测试与 pyright。

证据根为系统时钟创建的 `workspace/tmp/install-entry-bash-code-fix-20261020-210107/`，以下记为 E。
`run_validation.py`、`finalize_evidence.py` 是 E 内保存的临时取证代码。原实施目录与失败历史不改。

## 根因、owner 与修复

动机成立：平台适用性必须来自真正执行 pip 的解释器；新正常 shell 必须能使用正常工具路径。
这些语义属于安装 owner，不能由 metadata 后验、调用方配置或测试 fixture 补救。
版本/console target 真源仍是 pyproject，实际安装事实仍来自目标解释器 site 中的 dist-info。

| Finding | 实际修复 | owner 级证据 |
| --- | --- | --- |
| C1 | helper 的 `_identity()` 统一拥有 Python 3.11、64 位及 ABI 校验与 OS/架构投影；venv 查询同时返回该身份和 scripts。已有 venv 直接用自身身份选锁，不调用 bootstrap 选锁；fresh 写前检查 bootstrap，创建后再核实际 pip 解释器与该锁一致。已有环境不适用时在 pip/profile/入口写入前失败，不删除或重建 | `test_32bit_python_cannot_select_64bit_lock` 对 platform/venv/installed 三模式；`test_venv_query_projects_its_own_platform`；`test_existing_venv_identity_rejected_before_writes` 四例。OS/架构不适用及 32 位明确拒绝；合法 arm64 身份在 bootstrap 为 `/bin/false` 时仍到达预期入口冲突。全树指纹含根 `.`，已有 venv/HOME 均零写入 |
| C2 | 移除固定系统 PATH。`prepare_shell_path` 只移除直接 VIRTUAL_ENV 与本源码 venv 的 bin/Scripts（含同目录链接别名），其它正常项、空项、重复项和顺序保留，合法 `.local/bin` 保留。`resolve_shell` 在 SHELL 名称与 `--shell` 一致时用其 executable，否则从清理后的正常 PATH 选择外部 executable；不新增参数、不读项目配置、不发现通用 profile | `test_normal_path_tools_shell_location_and_venv_cleanup` 覆盖 SHELL 优先于 PATH 中另一 Bash、SHELL 不匹配时按 PATH 选择；非系统位置 wrapper 实际 exec `/bin/bash`，两类 profile 工具可用；`test_shell_path_preserves_exact_normal_items` 精确断言。最终真实矩阵同时提供 normal-tools、合法 `.local/bin`、明确 venv 污染 |
| C3 | 源码根的 `cd` 局部使用 `CDPATH=`，保留脚本位置和 `pwd -P`；不修改调用方 CDPATH | `test_relative_readme_invocation_ignores_cdpath` 用真实相对 README 调用和另一 `scripts` 目录，仍在正确源码看到预期既有 venv 冲突，原树不变；四次真实完整安装也携带该 CDPATH 反例 |
| C4 | 根 README 最简说明非目录型入口 symlink（含悬空）只替换链接本身并保留目标，HOME/profile/必要父目录/目标 venv symlink 拒绝，以及 Bash 非登录与登录两类文件及优先级 | README 与现有入口/profile 保全、冲突、Bash 优先级测试一致；真实 legacy 转换与完整 repeat 验证 |
| C5 | tests README 通用命令改为无参 `python -m pyright`，复用配置唯一 scope；未改 include 或排除项 | 最终 `pyright-handoff` 实际分析 **839** 文件，0 errors/warnings/informations，exit 0 |
| C6 | `inspect_entry`/`publish_entry` 显式接收现有 Python OS 投影，仅 `win32` 拒绝同名 `.exe`，POSIX 保留无关 `.exe` 且允许发布 | `test_exe_collision_follows_execution_platform` 的 darwin/linux/win32 三分支与原 Git Bash native 转换预检；真实 fresh/legacy 及 repeat 都保留同名合成 POSIX `.exe` 字节、权限、mtime |

C1–C6 writer 修复与本轮验证已完成；其正式 accepted/已修复状态由主控收齐双路受影响面复审后裁决。
没有以本文替代复审，也没有把 C1/C2 延期到真实 sync。

## 最终检查

最终有效检查使用 `E/run_validation.py checks handoff` 保存完整 argv、cwd、环境白名单、
起止时间、两通道及退出。各检查均先 `source .venv/bin/activate`：

```bash
source .venv/bin/activate
COVERAGE_FILE=workspace/tmp/install-entry-bash-code-fix-20261020-210107/coverage-handoff \
  python -m pytest tests/install -q \
  --basetemp=workspace/tmp/install-entry-bash-code-fix-20261020-210107/pytest-handoff \
  --cov=scripts.install_source_query --cov-report=term-missing
python -m pyright --outputjson
bash -n scripts/install-source.sh
```

- `tests-handoff.*`：exit 0，**92 passed**，helper 全文件 **96%（106 statements，4 missed）**。
- `pyright-handoff.*`：exit 0，**839 files，零诊断**。通用 scope 由 pyrightconfig 唯一决定，未绕过类型错误。
- `bash-n-handoff.*`：exit 0；安装器 `--help` 与 README 参数一致，exit 0。
- `E/pytest-handoff/` 保存所有 Bash 测试子进程的完整 argv/cwd/输入环境/两通道/真实退出。
  受控身份、Windows/Git Bash 和 I/O 失败仅为边界合同测试，不冒充真跨 OS、跨架构安装。
- 旧 BP3a 的 unset/empty/HOME/其它 ZDOTDIR 及启动文件设置路径测试仍在本次实际运行，未弱化。
  BP1a 的精确 `.DS_Store` 排除及 raw-blob/未跟踪源码约束保持原字节；正式 guard 仍由主控 sync 时执行。

未变公开包/wheel 测试按旧有效证据复用，没有重装未变 wheel 矩阵、重扫财报 fixture 或增加业务/LLM/live 门槛。

## 最终字节的真实 README 隔离安装

`E/run_validation.py install` 从当前 tracked 安装输入完整复制源码、独立 HOME 和新 venv。
只复制 pyproject/README/LICENSE/dayu/constraints/scripts，不带 live site 或财报 fixture。
所有安装实际执行 `/bin/bash scripts/install-source.sh --shell <zsh|bash>`，cwd 为对应源码根；
完整 `pip install -e <source>[test,dev,browser] -c <适用平台锁>`，没有 no-deps、marker/fakepip/help。

| 场景 | 真实 shell | 完整安装 | 独立 metadata / shadow metadata | 新正常 `-ic` / `-lic` |
| --- | --- | --- | --- | --- |
| fresh-1 | `/bin/zsh` | 0 | 0 / 0 | 0 / 0 |
| fresh-2（完整 repeat） | `/bin/zsh` | 0 | 0 / 0 | 0 / 0 |
| legacy-1 | 非系统位置 wrapper → `/bin/bash` | 0 | 0 / 0 | 0 / 0 |
| legacy-2（完整 repeat） | 同一 wrapper → `/bin/bash` | 0 | 0 / 0 | 0 / 0 |

本机为 macOS arm64，实际 `/bin/bash` 3.2.57、`/bin/zsh` 5.9；版本命令也保存于 E。
这是受控真实 wrapper，不是不存在的 Homebrew Bash 5 实测。主控 `controller-shell-resolution`
明确 INVALID，未采用；有效 `controller-normal-path/receipt.json` 与代码直接链作为 C2 动机证据。

正常输入保留 `normal-tools` 和合法 `$HOME/.local/bin`；两处分别提供 profile 依赖工具，
启动文件不再因丢失工具路径失败。初始 PATH 含活动合成 venv 与本源码 venv bin，并给定 VIRTUAL_ENV；
shell 检查只移除这些污染，profile 实际断言它们缺席。每次完整流程内部的 `-ic/-lic` 都真实运行，
另有源外 cwd 的逐模式独立后验记录。保留合法 `.local/bin` 不等于借已有 Dayu 成功：
fresh 入口缺席，legacy 预置合成旧链接，均断言发布后的完整 launcher 字节等于 owner 对新 console
生成的期望字节、普通文件类型、精确解析路径、实际 dist-info 与 editable 源码同源。

每个 `<label>.command.json/.stdout/.stderr` 保存完整命令、环境白名单、两通道、实际退出。
`<label>-metadata` 在源外 cwd 用目标 Python `-I` 定位实际 purelib/platlib 中唯一 dist-info，
核对 Name/Version=0.1.5、entry target、editable direct_url、源码、解释器/prefix/scripts/console/module origin。
`<label>-shadow-metadata` 的 cwd 与 PYTHONPATH 注入假 dayu/999 dist-info，并设置无效 PYTHONHOME，
同一 `-I` 查询仍退出 0、指向真实安装，未退化为 cwd metadata 或 PYTHONPATH 证明。
正常 shell 后验断言外部类型、精确解析路径及裸 `dayu-cli --help` 退出 0；真实 console 的内容另保存，
脚本内部源外 console help 的两通道与退出包含在完整安装日志。

legacy 旧树仅为本轮合成资产。`legacy-legacy-before.json` 与 `legacy-{1,2}-legacy-after.json`
严格相等：含根 `.`、完整路径集合、类型、权限、mtime、普通文件 hash、链接原文；不跟随链接读外部。
两种场景的无关 POSIX `.exe` 指纹不变，原 profile 前缀保留、单 managed block，完整 repeat 幂等。
`fresh-assertions.json`、`legacy-assertions.json` 与 `install-complete.txt` 保存最终断言。

`PIP_CONFIG_FILE=/dev/null` 禁用外部配置；普通下载缓存显式复用
`workspace/tmp/bash-implementation-20261020-194550/download-cache`，来源为前次 author 工程创建的
普通 pip HTTP/wheel cache。`cache-origin.txt` 和每个 run 的环境记录保存确切来源；实际 pip 日志保留
命中/下载与完整依赖结果。没有读取真实 UV 或其它工具环境，没有向 live `.venv` 安装。

## 精确版本、旧证据复用与失败历史

`writer-final-snapshot/` 完整保存本次八个 writer 文件，`writer-final-manifest.json` 给出路径、
快照路径、权限、大小和 SHA256。额外 `dirty-scope-snapshot/` / `dirty-scope-manifest.json`
保存交付时全部本任务 dirty 文件并标注 writer/controller 所有权；这只是快照，不修改主控文件。

`install-input-snapshot/` / `install-input-manifest.json` 保存全部安装必要原字节；
`installation-input-byte-verification.json` 将 **494 文件**逐字节映射到当前工作树、保存快照和
fresh/legacy 真实安装源码四位置。`final-head/status/dirty.*` 保存实际基线、状态与 tracked binary diff；
不能把 tracked diff 当作未跟踪报告的完整交付，也不能把 0.1.5 等同于核收 commit。

`unchanged-install-inputs.json` 独立重算前次清单的 **493** 个未变文件（含 2 个非运行期
`.DS_Store`；实际本轮复用的 tracked 输入为 491 个），
与前次 `delivery/install-input-manifest.json` 的精确 hash 相同；`unchanged-scope.*` 证明 dayu、
pyproject、constraints、requirements、pyrightconfig 相对 HEAD 零 diff。
`reused-evidence-hashes.json` 记录可取回的两路 review、裁决、旧 writer/input manifest、旧检查和
wheel 安装/show/help/metadata/实际 wheel 文件的路径、大小、SHA256。仅复用这些证据对未变范围
仍支持的断言；不把旧正常 PATH/平台预检证据用来替代本次修复重验。R1–R3/业务和版本未变，
按 binding 裁决保留原有效证据，不新增财报业务/LLM 回归门槛。wheel 为前次独立 venv 安装，
不冒称 wheel→user-site 整轮矩阵已验证。

失败原件保留。首轮 `tests-first` 汇总为 90 passed，但其中三个受控 C1 负例曾因测试注入影响
stdlib import 的 struct 调用提前 TypeError；这三个反例证据明确 INVALID，不作为修复证明。
随后先加载真实查询模块、再注入身份，并断言具体错误及无 Traceback，最终四例覆盖适用/不适用身份、
已有环境零写入与 bootstrap 不参与。原日志、测试目录不覆盖/删除。
首轮直接检查未在启动时采集完整 ambient 白名单，故只保留历史，不作最终核收环境证明；
最终与 handoff 全部通过显式采集的 runner 重验。`early-checks-and-failure-history.json` 记录该限制。
最终安装/检查无未处理失败；非 TTY Bash 的 job-control stderr 原样保留，不伪报 TTY 验证。

## Docs decision、风险与下一入口

根 README 命中安装/入口用户工作流触发，按已读最终用户手册边界补最简 C2/C4 说明，不塞治理 probe。
tests README 命中直接测试变化，补 owner 覆盖并将通用 pyright 改为无参。
v2 仅同步 C2 的正常 SHELL/PATH 语义、§6 对应测试要求和 §7 示例，并追加纠正说明；
旧 v1、冻结快照、goal、authorization、control、裁决和旧报告不改。业务层/装配/版本/依赖不变，
不触发其它层 README，也无需修改已正确纳入 helper 的 pyright include。

| 风险/未覆盖 | 分类 | owner / destination |
| --- | --- | --- |
| C1–C6 的实现缺口、正常 PATH、位宽真源、CDPATH、平台化 exe、文档不一致 | fixed in current slice | 本 writer 实现与本次验证；正式状态由主控双路受影响面复审后核销 |
| 首轮受控测试提前失败、早期 ambient 环境记录不足 | fixed in current slice | 本 writer；保存历史并用精确断言、显式环境最终重验替代，不冒用早期证据 |
| Linux/WSL/Windows Git Bash 真机、真实跨架构/32 位、真实非系统 Bash 版本及 TTY 配置 | assigned to later work unit | 安装维护者 / 有对应 runner 或具体复现后验证；本轮只报告受控分支与本机 wrapper |
| wheel→user-site 整轮矩阵、任意未知配置、多个编辑器并发改 profile | assigned to later work unit | 安装/init 维护者；沿用已裁决边界，不为本次新增门槛 |
| 部分失败无跨文件回滚、PATH 前置影响其它同名命令、移动源码会失效 | fixed in current slice | 安装 owner 的阶段错误与 README 既有披露保持；不重设计恢复框架 |
| 正式核收 OID/raw blob/未跟踪输入 guard、同 PR206 交付核收、真实 HOME/default/profile/live sync | covered by later approved slice | 主控 / 双路复审和工程核收后，收到明确安装通知才执行；merge 另授权 |

writer 范围内没有未完成实现或验证 blocker。**下一入口：主控按 C1–C6 及实际差异执行既定双路
受影响面复审，裁决正式 finding 状态，再推进工程核收。** 本文不代替这两步、不触发真实 sync。
