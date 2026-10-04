# UM-CI-N01-F01 plan review 总控裁决

当前gate：plan fix。冻结计划SHAa58b95afbc9898969bf85e0c79ed0d3597339d2bbc3ddd420aedc80d30bf7289，HEAD79977b3a。两路managed实际exit0：MiMo44/44tools、ds-flash59/59tools，CANARY/模型流/报告/源输入SHA核验成功；完整错误、masked探针FAIL恢复、原工具轨迹均双份private保全。详本WUroot-plan-review-*-terminal-audit.json/retention.json。

两路pass-with-risks不等Gateflowpass。以下集中修订计划后，必须同版双复审，不拆slice，不先实施。

|rootID|来源|裁决/状态|修复边界|
|---|---|---|---|
|DN-R1|MiMoF1+DSF3|accepted/未修复|record投影/格式化/编码/写入异常不得穿透logging调用；坏诊断记capture incident，不伪正常记录或改转换分类|
|DN-R2|DSF2|accepted/未修复|writer关闭与在途emit同步，footer后无record；真实竞态负例|
|DN-R3|MiMoF2|accepted/未修复|secondaryerror载体写死，或收窄仅parent可见的不完整语义；不要在exactfooter发明payload，媒体坏不保证自报|
|DN-R4|DSF1|accepted/未修复|spawn覆盖必须实际收集/合并；保持每生产80%，拒绝缩成可测面；不改venv或沙箱边界|
|DN-R5|MiMoF3/rootDN-P02|accepted目标漂移/未修复|拒绝新增日志完整性业务成功门槛：已验证转换成功之后sidecar损坏仅secondarydiag，保原result/publication规则；无法建立fd隔离则不得启动转换；不为原success新套IPC_PROTOCOL|
|DN-R6|rootDN-P01|accepted明确生命周期/未修复|FD保到worker最终退出，structuredlogger在scope结束恢复；API与测试不要又要求同worker scope退出恢复公共FD|
|DN-D0|rootDN-P00|accepted文档澄清/未修复|plan-only stop来自父Agent派发范围，不是主用户新pause；root继续全部任务|

## 最小技术选择/拒绝额外scope

原级别保全、parent现公共准入、child不收用户logpath、XBRL只现work权、S1单行为slice均成立。rawunknown INFO是Fins最小路由选择，不是用户曾逐字批准INFO新oracle；日志前缀必须说明unknown且不按WARNING文字猜级别。rawbyte分块确定转义可接受，不新增业务问题；只读回归运行不须扩大编辑路径。quota/外部Logger/daemon未来WU没有已授权事实，只归outside当前goal/runtimeowner/未来明确选择；不顺带实现。

原修复WU保持closed，pure登记WU保持独立依赖，本轮不改两registry或生产。root仍按原material成功Docling+published manifest语义；日志新规则不得添加第三项材料成功判据。方案仅恢复已有目标，无须再问用户是否新增严格日志门槛。

精确requiredfix与验证见workspace/tmp/upload-material-converter-diagnostics-20261003/root-plan-review-adjudication.json；下一入口集中planfix→同版双re-review→acceptedplancommit。

## DN-R1 控制流边界补充（当前集中planfix适用）

修订草案出现“诊断操作catch BaseException且primary控制流在helper外”的说法。同步helper内部同样可收到KeyboardInterrupt/SystemExit，不能据同步性质保证控制流在外。捕获普通诊断Exception即可；KeyboardInterrupt/SystemExit/asyncio.CancelledError/GeneratorExit保持原传播/退出/取消，清理可以收资源后re-raise同一控制流，但不得降为secondary或成功。该补充只是bindinggoal原取消/primary合同，不新增业务predicate，不需用户重裁。具体说明/小probe要求见本WUroot-control-flow-clarification.json，集中planfix与同版re-review必须覆盖。
