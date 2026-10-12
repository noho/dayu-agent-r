# 601225-annual-fulltext：S1 总控交付复核

- Gate：implementation S1 → code review；不是 accepted slice、PR 或最终完成。
- Sol runner 实际退出0/completed，交付 implementation/checks artifacts已读；runner needs_review不等于不通过或自动通过。原25条工具异常为已保留的实现/夹具迁移、覆盖率collection与辅助工具启动失败，最终测试/类型/四次真实CLI证据已闭环，不能用退出0替代业务验收。
- HEAD为accepted-plan 7709c015db26c095f16cb77b5d383411cd76b652，生产修复在工作树；不冒充该HEAD已包含生产代码。
- 已复核实际命令/exit、final-2覆盖率和731 passed、最后delivery pyright0、pipcheck0、pypdf6.1.3；12生产文件及修改/新增测试逐文件>=80%。模块coverage收集触发NumPy重复加载，目录source收集同一13文件集且无排除，无降低门槛。
- 四个公开bare CLI均原exit0，非FY-only、无overwrite/rebuild，base与log均在独立workspace/tmp/601225-cli-s1。first clean/seeded各下载35、failed/rejected/uncertain0；仓储分别35/37（后者含2摘要），完整资产核验passed。两个repeat各35 skipped、0转换、诊断success。
- 总控另运行clean-first verify：实际exit0，全35 source通过。独立读取两base三目标实际PDF/JSON，官方SHA一致，FY2021/2023/2024/full，Docling正文非空；见controller target JSON。独立比对first→repeat全部sources记录逐值完全相等，seed两摘要与repeat记录完全相等，全文与摘要ID不同；不是只采纳compare自报。
- transport/wire均闭合；repeat clean精确GET {1204545056,1209875597,1213161682,1223301999}，seeded {1204545056,1209875597}，各1；三目标/全部已持完整源0GET，两个repeat所有conversion started/completed0。每run官方FY raw仍19条，当前strict helper已只读重对账原事件，不改变真实请求。
- 版本边界：初次CLI在实施工作树运行，启动未冻结commit。启动后hash差异为cninfo_downloader（重复raw提前拒绝从准入raw扩大为全部FYraw，本次19条均唯一）、identity注释/docstring、upsert未用旧常量移除；三者当前实际成功数据路径等价。helper最后收束通过对原事件重对账，four argv不包含被新拒绝的参数。当前repeat与owner tests另覆盖收尾实现；不伪造冻结版本/历史raw，也不因无实质路径变化重复两次完整转换。
- 原证据manifest134项重新实核，大小/hash全未变，caller目录/日志未写；当前原参数复现不冒充原调用历史全链。

## 范围、文档、风险与下一入口

实际变更均在已接受P1范围：facts/source、models/protocol、downloader/selection/identity/publication/inventory、对应tests/fixtures、两utils、依赖和三README。无storage schema/repository实现/CLI/Service/Host/Engine/调用方修改；无三ID生产特例。README按各自职责更新。

- code review/后续review/必要fix：fixed in current slice，owner MiMo/DS Flash/Sol及总控，destination对应正式artifacts；尚未通过，不自报完成。
- 历史启动树/raw；OCR/未知布局/其它公告/一般日期；隐藏坏摘要/未知旧身份/错年自动恢复；落选来源repeat获取成本；SDK有损origin与无derived_from的历史因果：assigned to later work unit；owners及destination维持accepted plan与S1implementation风险表，不升级新验收目标。
- 外部来源/转换当前四run无阻断；无未分类风险或待用户决定的范围变化。
- next entry point：code review S1，双路deepreview同版；没有slice commit/push/PR/merge，未操作其它任务。
- Artifacts：s1-implementation.md、s1-checks.md、workspace/tmp/601225-controller-final-source-comparison.json、controller-post-implementation-preservation.json、controller-clean-first.verify.json。
