# IE-B1 完整代码审核裁决与必要修复

## 首轮完整双审事实

固定base1856cf8d97468423c6a3ece5558a312d31802b20/head5c179fdcb217634c31d66c60a141cf2909987f39，22文件完整diff SHA1ea55eae804392dc80f6a1b08daf86caf84d8d907d048424834c41d7e76c6378。DS37473外层/runtime0/0 success1877.652801秒，报告204535；MiMo67035外层/runtime0/0 success2118.829733秒，报告204928。完整final和两份报告全读。MiMo无materialfinding，DS五项；主控按直接证据逐项裁决，不按票数放行。两路各自81tests/pyright0/helper96%，沙箱rc文件名EPERM失败及隔离目录禁沙箱后通过均保留，不当代码缺陷或删除失败。源/tests/README/config当前仍冻结5c版本，未push/安装。

BP1a/BP3a由两路实质独立核销，主控正式改为accepted/已修复（实现与代码审核层），不再延期到sync。旧DS F1 wheel裸命令伪确认已修复，实际wheel-venv/flags/site与文档同源；未声称wheel-user-site整轮矩阵。BP1主控正式commit/rawblob guard仍是核收通知后执行的流程，不是未修复代码。

## Findings逐项裁决（C编号为本次代码审核）

- C1＝DS1：accepted/未修复，中。锁选择事实来自bootstrapPython，而实际pip由已有venvPython执行；当前_venv不验证该解释器位宽/OS/架构。须在安装owner闭合实际pip解释器→适用锁，重用同一身份查询/校验，已有不匹配环境在任何pip/profile/entry写前拒绝，不能自动删/重建旧venv或只下游metadata补救。验证可以受控身份输入，不声称真跨架构OS；同架构fresh/repeat保持。
- C2＝DS2：accepted/未修复，中。固定系统BASE_PATH既改变被选shell也丢失正常工具路径，不能代表用户新正常shell。主控独立有效反例在controller-normal-path/receipt.json：同一真实/bin/bash，隔离profile依赖正常PATH里的fixture工具；当前check_shell丢弃该目录导致写前失败，实际继承正常PATH的-ic/-lic均0。修在安装进程对其直接输入SHELL/PATH的解析/验证owner，不查找项目调用方环境或配置，不要求调用方补安装。默认应保留正常PATH的其它项、只清除明确的活动/本源码venv污染；不得不加区分剥掉合法~/.local/bin而使其中其它profile工具失效。刻意clean最小PATH可以保留作额外隔离反证，不可冒充唯一正常入口验证。优先复用现有--shell+安装进程SHELL/PATH，避免新增必填参数/通用shell发现框架。
- C3＝DS3：accepted/未修复，低。CDPATH可让相对脚本目录的cd查找别处并输出目录，破坏source-from-script。当前直接证据通常是预检错误退出；报告“完整另一源码必可装错”受cd额外stdout影响未实证，主控不采该最坏结果当事实。仍应以CDPATH=的局部cd修正有效源码运行被误拒，保持pwd-P规范化，增加相对README调用反例。
- C4＝DS4：accepted/未修复，低。README需简述入口symlink替换本身/保留目标与HOME/profile/必要父目录链接拒绝、Bash涉及两类启动文件；这是本轮旧入口核心用户行为说明，不新增治理probe。
- C5＝DS5：accepted/未修复，低。testsREADME通用显式3目录pyright838遗漏helper，而默认839；改通用命令为无参使用配置单一真源。
- C6＝DS OQ.exe：主控收束为本slice的明确平台策略，accepted/未修复，低。exe搜索碰撞只在nativeWindows/GitBash有该执行语义；POSIX不因无关同名.exe拒绝且必须保留文件。用已有平台事实作最小显式输入，不让测试倒逼保持跨平台无条件拒绝，不从文件名/历史猜OS，不做清理旧exe工具环境。新增对应受控分支测试，不声称真实Windows通过。

C1–C6均fixed in current slice，owner用户指定gpt-6-sol fix writer，destination本次必要修复/受影响验证及MiMo/DS双路复审；未核销前不PR交付/真实安装。高层目标/版本0.1.5/同PR206/工程核收后通知才sync/merge另授权不变，无新用户决策。C2是既有“正常shell”契约在安装owner修正；v2相关正常PATH示例可有限同步，不回到zsh-only或系统bin-only承诺，不扩未知shell通用框架。

## 主控证据纠正

controller-shell-resolution最早探针假定/opt/homebrew/bin/bash存在，实为No such file；0/0/1退出组不能证明预期的函数冲突。已在receipt.json标INVALID、保留receipt-original-invalid.json与correction.json，撤回该解释，不作C2依据。C2依据是冻结代码数据链与后来真实/bin/bash的controller-normal-path直接反例，后二者不依赖不存在的Homebrew版本。代码/真实HOME/live均未因此修改。

## 风险/边界裁决

- 非本机OS/真实非系统Bash版本/TTY、完整wheel-user-site、ACL/xattr/hardlink等未知具体平台：assigned to later work unit，owner安装维护者，有具体runner/复现再核，不声称已过；C2正常输入的受控分支在本slice修，不能用此标签延期已接受缺口。
- 并发profile写：assigned to later work unit，安装/init维护者；当前顺序保全。部分失败/路径优先级/迁移位置限制：fixed in current slice，由诚实错误及README披露，不新增回滚库。
- 真实自身sync/精确commit/rawblob/metadata/help：covered by later approved slice，工程核收明确通知后的主控。报告中将“真实旧UV内部保全核对”列为未来sync要求的措辞rejected-with-reason：用户禁止读真实旧UV内部，只有合成树机制证据与已给链接历史，不能新增真实旧环境扫描/指纹门槛。保持旧目标不写的算法与本线默认入口回执即可。
- 原R1–R3/0.1.5业务源码/依赖不变证据仍适用，修复只安装owner/直接测试文档；无全业务/LLM/原失败live回归新门槛。

current gate / next entry point：fix，然后按实际差异及C1–C6执行双路受影响面re-review；不重开未变部分，不制造第二次全仓完整审核。

## C1–C6 writer修复回执与复审入口

fix71339实际0/0turn.completed907.062148秒。主控完整读取fix报告/rawhandoff/版本映射，独立核8writer文件保存字节、494输入四位置、20个实际安装/回读/正常shell进程全0、旧树含根.保全；92tests/helper96%/pyright839零诊断/bash-n0，包业务/版本/依赖/config未变。所有当前证据支持writer实现完成，不替代独立复审；C1–C6正式未核销。

实际正常PATH保留合法homebin与profile工具、仅除明确venv污染；真实矩阵覆盖非系统位置wrapper实际exec本机Bash3.2，不冒充不存在Homebrew5。源码定位CDPATH局部中和、已有venv实际身份选锁、POSIX.exe保留与win32碰撞拒绝、文档范围正确均在当前writer版本。仅按实际变更面与C1–C6启动MiMo/DS双路re-review，原完整审核未变面复用；不重开全repo/财报业务/旧UV内部核验。
