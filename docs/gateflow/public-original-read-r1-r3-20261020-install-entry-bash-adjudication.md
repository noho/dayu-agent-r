# Bash 默认入口计划/实现审核裁决

## 新Bash首审：DS已收，MiMo仍在途

DS88709外层/runtime0/0、success、549.648876秒，完整final及docs/reviews/plan-review-20261020-185725.md已读；MiMo69913仍在途，旧审查对象a6ec1737及保存副本冻结不改。DS原始工具错误/模型识别warning保留，退出不等于业务pass。

- BP1（DS F1）accepted/未修复：真实sync来源检查只查tracked会遗漏可执行安装/源码输入；限定本次安装交付输入补tracked存在/commit字节一致及额外未跟踪源码检查，不把无关临时证据文件升为新验收门槛。计划层修正后双路窄复审，实际执行在核收通知后。
- BP2（DS F2）accepted/未修复：wheel用-I会隐藏user-site，与未限定venv的安装段不自洽。同一目标解释器检查须可见其实际安装site并排除cwd/PYTHONPATH，如Python3.11的-E -P；优先避免为这一文档消歧强制新增wheel安装框架。由gpt-6-sol定最小正确命令并代码核对，计划层复审，最终README完整代码审再核。
- BP3（DS F3）accepted/未修复（明确既有契约的检测点）：有效ZDOTDIR必须按真实shell启动后值检查，含.zshenv设置；不强制改ZDOTDIR伪造正常shell，不扩profile管理。新正常shell仍使用用户配置，非HOME有效值按已确认方案变更前失败。

DS Q1目的地父目录symlink处理是局部安全预检：由实现/代码审核确认不沿不安全目录链写用户位置，无需通用路径框架，记录目标父目录链接明确失败；Q2隔离pip配置与可复用普通下载缓存不矛盾，记录实际使用配置/缓存路径及来源，不借live site-packages；二者非阻塞。Q3新开终端、Q4平台限定、Q5已定义碰撞失败均原计划已覆盖，交README/代码审查，无新目标。

为并行完成已明确窄修，只允许新建bash-plan-v2，旧bash-plan文件不变，因此MiMo仍审同一精确对象；不是终止或重派审核。待MiMo实际终态收齐并裁决后，对必要修订统一双路窄复审再放行，当前不实施。

风险：上述BP1–3 fixed in current slice（计划层先修，最终README/脚本由实施及代码审核证明），owner指定gpt-6-sol与主控；真实sync covered by later approved slice，owner主控/安装通知后；Linux/Windows实测及profile并发仍按原计划assigned to later work unit维护者，不因此新增平台业务门槛。

## Bash首审收齐及v2窄修交接

MiMo69913已实际退出，外层/runtime0/0、success、1080.395155秒，完整final与报告190523已读。无新增materialfinding；其未发现的BP1–3不抵销DS直接反例，主控维持accepted。OQ1路径归一化/OQ2Windows入口碰撞/OQ3pip空格中文路径均为实施/代码审检查点，非计划blocker。MiMo非标准风险标签由主控收敛：R2/R3/R7 fixed in current slice（README披露/诚实失败/真实行为测试，IE-B1 owner）；R4/R5 assigned to later work unit（维护者/runner或并发契约）；R6 covered by later approved slice（通知后sync）。

gpt-6-sol窄修24875已实际退出，外层/runtime0/0、turn.completed、620.181773秒；完整final、v2计划及窄diff/receipt已读。v2 SHA b280bbd5fdd86aadf9e0c302ac170c6e9316203f5d8310e8e10b024e647eadf7，旧a6ec1737保持。主控核对：三个已接受点均有明确计划检测点与可取回隔离反例，源码venv-I不变、wheel-E-P保留user-site、ZDOTDIR按真实启动值检查、commit guard限实际安装输入；不新增业务目标。计划层待双路窄复审核销，BP1–3正式仍未修复，不实施。所有probe均机制证据，未执行未来installer/真实wheel安装/sync；原rg不存在路径exit2、find调查exit130与no-index diff1保留，不改实际退出，也不冒充工程验证。

## 主控补充反例：BP3局部表达式的空值区别

在v2双路窄复审期间主控隔离真实zsh验证：ZDOTDIR未设置会读HOME/.zshrc；显式空值不读该文件，但`${ZDOTDIR:-$HOME}`会错误返回HOME并通过-ef。完整命令/两通道/实际退出在install-entry-20261020T101200Z/controller-zdotdir-empty/receipt.json。相同隔离目录补测`${ZDOTDIR-$HOME}`，unset/明确HOME两种通过，empty/其它目录两种拒绝，-ic/-lic共8例均符合预期；原始新旧两份回执保留。没有修改真实HOME或在途v2审查对象。

BP3a裁决deferred-with-owner，修复状态未修复，owner指定gpt-6-sol IE-B1实现者，destination本slice实现/验证及双路完整代码审核（须明确核销，不可留到真实sync）。授权依据用户已确认Bash方案/非标准启动目录拒绝、自动实施修复及既定完整双审。非阻塞依据：高层owner/契约/失败顺序已经明确且不变，此为已明确约束覆盖的局部默认值表达式；按Gateflow review规则“明确约束已覆盖的局部表达式…不得反复阻塞plan”，不为两个字符制造新计划循环。主控以本条明确覆盖旧示例：只在unset时回退HOME，显式空值必须拒绝；实现者同步窄修v2相应示例/记录并增加真实shell断言，最终代码审核实质复验此受影响面。若新证据显示不是局部表达式问题再回plan。v2当前hash保持供在途复审，不能假称其示例已经更改。

## v2窄复审DS已收及局部非输入元数据修正

DS99536实际外层/runtime0/0、success、639.761708秒，完整final与报告192241已读（正文定位与剩余行补读见原件）。BP1核心闭合、BP2/3计划层已修复，指出局部命令会把真实repo两个既有ignored .DS_Store当源码而false-fail。主控已独立只读复现：原命令输出dayu/.DS_Store、dayu/config/.DS_Store；加精确basename --exclude=.DS_Store后为空；独立worktree同时放普通/ignored未核收Python与安装脚本，三者仍全部列出。完整命令/退出/两通道见controller-input-guard/receipt.json，无真实repo文件更改。

BP1a裁决deferred-with-owner，状态未修复，owner指定gpt-6-sol IE-B1实现者，destination同slice顺手窄修v2命令的具名非输入allowlist并在完整代码审核实质核对，不留到通知后才修、不删除真实.DS_Store、不泛化._*或--exclude-standard。授权依据既有Bash安装/必要修复、来源绑定且不误拒非输入/不删用户文件；非阻塞理由是BP1高层commit收录/字节/相关未跟踪输入契约已闭合，本项是已明确“排除具名非输入缓存”的局部清单遗漏，DS也判不阻塞IE-B1。按Gateflow明确约束覆盖的局部表达式规则不重复plan循环。MiMo7570仍审冻结v2，不改其对象。

DS残余分类由主控收敛：两个正常shell模式/TTY配置/metadata flags为fixed in current slice（IE-B1行为测试及如实失败/README），Windows换行rawblob与真机矩阵/并发写为assigned to later work unit（维护者，当前正式sync在macOS），正式自身sync为covered by later approved slice（核收通知后主控）。所有局部延期有明确owner/destination和现有授权，不改变目标/验收。

## plan-pass：核心契约双路窄复审收齐，转implementation / validation

MiMo7570实际外层/runtime0/0、success、1762.179624秒，完整final与176行报告193516已读；DS99536的完整报告192241（含补读行）亦已读。两路核v2 b280bbd5/窄diff c4f07e4c/旧a6ec1737一致，均pass-with-risks。MiMo一次Bash工具被内部安全分类服务超时拒绝，随后有只读取证与完整报告交付；记录原诊断，不据此改变业务结论，不声称该次被拒操作执行成功，无阻塞或需用户审批的余项。

BP1、BP2、BP3正式回写accepted/已修复（**计划层核心契约**），高层owner/顺序/版本与来源/正常shell承诺足够指导实现；README/实际脚本尚待实施及完整代码审核。双路均未发现新的高层blocker，无needs-more-evidence或blocking open question。主控已直接核版本、相互影响、单slice、安装停点及根因，放行IE-B1。不能把此plan-pass称作新安装通过。

BP3a与BP1a维持前节正式deferred-with-owner/未修复，明确由gpt-6-sol本slice窄修表达式/具名exclude及相应v2示例，两路完整代码审核实质复验后核销；它们有现有授权、非阻塞依据、owner/destination，不能以分类为由遗留到真实sync。旧冻结v2副本/原hash留作本次审查原件，作者只可做已限定微小文档修正，并记录差异供代码审查；不是重开高层计划。

MiMo残余统一裁决：R-a未来新增dayu*包根非py资源属assigned to later work unit，owner安装/打包维护者，destination新增实际安装输入时同步guard；当前布局的真实输入均覆盖，不为不存在包根泛化框架。R-b由BP1a fixed in current slice，不清理用户.DS_Store或加宽ignore。R-c“真实wheel user-site整轮安装”并非bindinggoal或v2§6的新增验收场景（报告自己也明确未新增wheel场景）；同目标解释器flags/site/入口与README一致性在本slice核对，完整wheel user-site安装矩阵assigned to later work unit，owner安装维护者/有具体平台复现时；不把报告的“既定位”误作用户新授权或新门槛。原0.1.5真实wheel及未变包内容证据按版本适用复用，-E-P flags的user-site机制有直接证据，不声称已真实wheel→user-site安装。R-d fixed in current slice（IE-B1实现/测试/双审），R-e covered by later approved slice（核收通知后主控正式sync），R-f/g assigned to later work unit（安装维护者真OS/并发需求）。R-h过程叙述由control/本裁决保持历史，不是业务风险。

next entry point：implementation / validation。版本0.1.5、同draft PR206、业务代码/R1–R3不变；真实HOME/default/profile/live.venv仍不改。所有实际新代码、必要README与测试完成后冻结版本，执行既定MiMo/DS完整代码审核/必要修复复审，再工程交付核收通知后才sync。merge未授权。

## implementation / validation通过，进入完整代码审核

writer47725实际0/0 turn.completed1686.269596秒，完整final/report/真实raw检查读毕；9writer文件及496安装输入四位置独立逐字节匹配，最终81tests、96%helper、pyright0、bash-n0、真实fresh/legacy/repeat及metadata退出0，旧树含根.保全证据适用；详见实施回执与主控readback。BP1a/BP3a实现变化确实存在、两个局部plan修正范围精确，但正式核销仍等下一轮指定双审，不拿writer自报关闭。保留所有失败/非TTY噪音及source版本映射，无业务R1–R3重扫，无真实live安装。冻结本增量当前组合版本，code review必须覆盖全部安装文件、测试/README、两个局部修正及整体目标/失败路径/owner交互。
