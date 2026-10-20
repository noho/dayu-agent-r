# R1–R3 工程交付与 final closeout

工程 work unit 已完成：完整审核、必要修复/双路受影响面复审、独立 draft PR 及总控交付核对均通过。
PR：[noho/dayu-agent-r PR 206](https://github.com/noho/dayu-agent-r/pull/206)，保持 **draft / open / 未合并**。

## 改了什么

R1：新增四个公开 FinsReadRuntime 操作及对应工具——资产清单、原文窗口、物理结构、精确 namespace 非数值 occurrence 查询；工具由九个增至十三个。原文、结构与声明均绑定 exact 文件名、storage 实际 SHA/size 和可回读 span，分页可取齐全文，重复 occurrence/context/namespace 不被便利视图吞掉。

R2：删除封面 producer 的 5000 字符静默裁剪；便利 section 标明 source_asset/section_view，完整原件可从同版原文入口续读。ASML 任务书尾文与实际保存 JSON 的差异保留在 goal confirmation，原证据未改。

R3：清单显式保留 TSM 主件与附件角色、实际字节身份及 href 原文定位，调用方可选件，不修改 primary、选文、下载、原件或业务准入判断。继续复用既有 storage full snapshot、processor、read runtime/cache/borrow 生命周期，未建平行真源。审核中发现的格式、引用、错误恢复、懒构建/close、诊断成本、精确文件名、资产级完整性和必要验证缺口均在正确 owner 收束；最后的 head noscript 边界仅补 processor 内容集合。

## 验证与版本

源码复审精确 commit：`f7eee0c5a85d8810d63e32976f17c36922640f90`。
首轮交付核对 head：`eb230ad43cb2aa79384bf1f7f22bcde721243cda`；base：`8bf8daec8a022fd705e6cfe32c4283605f1fe6ca`。
后续只提交本文/控制记录等工程审计文档；最终发布 head/base、完整 diff 和最终推送收尾回执保存于
`workspace/tmp/public-original-read-r1-r3-20261020/pr-delivery-verification-final.json`，不以文档自引用制造提交循环。

- 最终窄修及两位独立 reviewer 均实际执行 99 项原文/真实 process/Host 测试、全量 pyright，退出均0，类型检查0 errors/0 warnings/0 informations。17 个修改生产 Python 完整文件覆盖率有效达到80%以上；本次唯一修改的原文 processor 为391/402=97.2637%，无新增omit/exclude。
- 旧完整受影响集实际为1 failed/1452 passed，唯一旧同步边界测试迁移到真实 full snapshot 返回前后整文件55 passed；源代码未变的其余断言复用，不把退出1写成一次全绿。当前99项是新生产版本的受影响面实跑，不伪称再跑1453全量。
- API-8保留1774次完整返回、原53调用重放、七份锚/TSM附件全文和51锚回读、MSFT三 occurrence、TSM双资产/关系、CN/HK PDF/Docling正向。ASML cold/warm各380页、24,864,734字符均与原件逐字相等；全部1236项允许输入与副本前后指纹未变。
- 后续生产差异仅head开放时遇noscript的规则；八份保存原文均无该起始候选，182模块仅original_content变化，其余181模块及依赖相同，故旧未变断言可复用；新head、body对照、未闭合partial/unknown、XML隔离、版本/span/分页由当前真实公开入口与独立探针证明。未把旧API标签head误当新版本。

详细实际命令/退出、完整原始返回、902份可取回源码快照、逐文件hash及覆盖率警告保全见
[code-fix-2](public-original-read-r1-r3-20261020-code-fix-2.md)；首次实现与第一次修复证据沿对应回执可取回。

## 审核与交付核对

完整双路审核报告134629/135446，第一轮受影响面报告143203/150149，第二轮窄复审报告153921/155306均实际退出并读完整final/报告；无在途writer/reviewer。最终 **12项accepted全部已修复**，S1正式deferred-with-owner，全部风险已分类，无needs-more-evidence或阻断问题。证据与逐项终裁见
[code adjudication](public-original-read-r1-r3-20261020-code-adjudication.md)。

主控实际核对repository/head repository均为`noho/dayu-agent-r`，PR206的branch/main、draft状态、title/body及精确head/base；按精确OID compare取得完整60文件diff，保存GitHub与本地两份完整补丁及hash。两者仅index缩写/hunk尾部函数标签格式不同，全部hunk范围、mode、正文相同，每个index均与相应Git blob前缀核符；未用可变PR diff替代。读取diff前后OID不变，远端工作分支head与本地一致，无未交付实质源码变化。

实际远端check runs=0、status contexts为空，仓库无workflow；main受保护，但required_status_checks的contexts/checks均为空。必要本地检查已满足，**不声称远端CI执行通过**。首次校验器的index-only比较和“main未保护”前提断言曾失败，已保留完整格式差异与实际保护设置核清；未放宽补丁内容或必要CI要求。
首轮完整交付回执为`workspace/tmp/public-original-read-r1-r3-20261020/pr-delivery-verification-initial.json`，compare快照SHA256：`74581a8b887cb64cb1ecb91472e1863d2943107b92017b2475c8a81dc0a4ebfa`。本文纯记录提交后再收尾核最终OID/diff/push，不重开同内容完整审核。

## 文档、issue与残余风险

按职责更新Fins/config/tests README、既有fins-read提示/工具自足说明和本任务gate记录；根README的安装/CLI及层次装配未变，无机械扩写。最新授权与原通知历史保留在
[authorization update](public-original-read-r1-r3-20261020-authorization-update.md)。
任务来自本地上游handoff，**未指定GitHub issue**，issue关联/closeout comment/自动关闭预期均不适用；未新建或评论外部issue。

- S1实际供应商接受度：assigned to later work unit，Provider/Engine owner + 项目协作助手安排调用方后续补验；无已证拒绝，不扩共享runtime，不作为本线安装门槛。
- head noscript无真实财报样本、一个未闭合组合仅独立探针覆盖：assigned to later work unit，Fins capability/tests owner在后续边界扩展或自然补验时加入；当前正反公开入口证据已证明正确，低风险非阻断。
- 空coverage子库形成原因：assigned to later work unit，测试/coverage runtime owner；原库/警告保留、完整分母达标，未猜测原因。
- CSS/脚本/浏览器DOM、跨资产document set、XBRL transformation/业务解释、总字节/硬中断、SEC durable original_main、OLD同输入动态对照：沿已确认非目标及code-fix-2风险表assigned to later work unit，原Fins/runtime/storage/调用方/总控owner不变。OLD静态同链路已有对应限制，不笼统称重构新增回归。
- merge：requiring explicit user decision，用户owner，当前未授权也未执行。工程核收后的指定源码安装为covered by later approved slice，owner本线，条件和顺序如下。

## 下一接续与安装边界

先使用tmux-agents重新discovery、核对title为portfolio-manager的项目协作助手身份，报告实际工程交付、证据、精确分支/commit、停点和待办。**等待工程获核收并收到明确安装通知后**，才按本仓README“从源码安装”步骤安装指定版本，无需PR merge。

本线只报告自身实际安装命令、退出、源码commit、安装位置及README要求的公开入口检查`dayu-cli --help`；无需了解、查找或核验调用方环境/入口，不重复业务回归、不另加原失败用例或实际LLM出站门槛。当前尚未执行安装，亦不宣称调用方可用。通讯/安装实际回执随后保留在本任务workspace/tmp证据目录，原授权历史不删改。
