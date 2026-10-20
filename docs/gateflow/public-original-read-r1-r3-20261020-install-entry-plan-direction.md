# 默认入口安装计划方向纠正（用户追问后）

本记录不改变已确认goal：同PR206、包版本0.1.5，README源码安装后未激活的新正常shell应命中本次安装；本线负责默认入口，工程核收并获通知后才真实sync，merge另授权。保留用户给定旧默认链接/手工修正历史，不查调用方环境或配置。

用户连续追问“只承诺macOS/zsh是什么意思”“Python安装不是平台无关吗”“wheel安装与-c约束的原理区别”“直接删除venv/activate是否就可”。主控已说明：pip机制跨平台，wheel/editable决定安装来源形态，-c约束依赖；目标解释器决定安装环境，脚本目录/PATH与旧默认入口是否更新是另一个安装交付事实。去掉venv行不能自动保证裸命令对应本次安装。

主控承认首版计划过早把安装交付绑定为zsh专用profile逻辑，当前不将该取舍放行实施。下一版须优先比较标准Python安装/现成CLI工具安装机制能否以更少自建机制满足默认入口发布和来源绑定，再保留必要的平台差异；不先把自行维护.zshrc作为既定方案，也不把平台依赖锁文件误当pip仅支持该平台。用户尚未要求新增任意OS完整业务矩阵，不据此扩财报运行时或测试所有未知shell。

首版plan SHA e21092e541111d0207094a624fa31fd7d13f6b1d7326e6c33396a8c2491766f2及goal快照保持，不修改在途审查对象。MiMo43101和DS14840继续正常收取；其报告仅裁决首版，不能作为将来修订方案的pass，不擅自停止/换provider。两路收齐后由指定gpt-6-sol修订，按实际重要契约受影响面补审核。当前尚无代码/README/真实安装修改。

只读替代机制证据：workspace/tmp/public-original-read-r1-r3-20261020/install-entry-20261020T101200Z/alternatives/。实际执行uv --version、uv tool install --help、uv tool update-shell --help、python3.11 -m pip install --help，均退出0，命令/完整帮助/时间已存。当前uv支持editable、constraints、指定Python、force、reinstall，并提供工具入口PATH配置命令；pip帮助明确--user是平台用户目录，脚本可能在PATH外。此为能力取证，没有执行uv install/update-shell、没有读取旧uv环境/工具清单或调用方环境，不预先宣布某个替代方案已选定或验证通过。

## 用户明确选定 Bash 编排（最新）

用户明确：使用 Bash 脚本完成安装。主控接受该方向，并说明 Windows 需 Git Bash 或 WSL，WSL 安装属于 Linux 子系统；不声称原生 PowerShell/cmd 直接执行 Bash，也不凭脚本语言声明跨平台实测通过。下一版使用独立 bash-plan 文件；首版保留历史，不按首版 Python publisher/zsh-only 方案实施。平台中立的安装编排与依赖约束适用平台分开说明；仅引入满足已确认目标所需机制，不新增任意平台完整业务回归。

首版双审已实际收齐：DS14840 外层/runtime0/0、success、502.471856秒，报告183115；MiMo43101 外层/runtime0/0、success、730.218879秒，报告183342。完整final与报告已读。两路只证明旧版计划；新方向不能复用其pass。主控采纳DS F1为accepted/未修复（新默认源码入口可能遮蔽wheel段裸命令验证，须在同slice明确目标环境入口）；sync风险应分类为covered by later approved slice而非新决策。MiMo声称uv/pipx不支持editable的替代方案理由不成立：本线实际uv帮助支持-e，不能据该断言排除标准机制；其余已证实旧版owner/rootcause可作为背景，不代替新方案审核。
