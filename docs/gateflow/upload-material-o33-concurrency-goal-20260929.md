# UM-O33-F01：同一 material `auto` identity 并发幂等裁决 goal confirmation

- 状态：**goal confirmation pass**；用户已在 `docs/reviews/upload-material-um-o33-oracle-adjudication.md` 接受修复方向，并授权总清单按 Gateflow 修复、闭环代码进入 draft PR #197，用户手工 merge。本文件只固定目标/边界，不授予绕过 plan 与 Kimi/MiMo 双路 review 的实施。
- 证据：冻结 UM-L06 一成一败且失败方为通用 `storage_io`；当前 HEAD 独立补证 `docs/gateflow/upload-material-o33-e01-evidence-20260929.md` 在相同 identity 两进程并发复现，并在 workflow 捕获边界取得真实 `FileExistsError`：`auto` 读取 fresh 旧状态后被解析成 `create`，另一方先发布，仓储 create 时发现目标已存在。冻结原异常不能被新试验倒推。

## 第一性原理与语义 owner

动机成立：相同请求顺序重试已按权威 fingerprint 幂等 skip；并发窗口里的 stale action 却让第二请求报通用存储 I/O，用户无法区分正常竞争与真实存储损坏。当前代码持有 writer/publication guards，因此根因不是“无锁”的泛断言，而是**状态观察、动作决策、转换/发布之间缺少竞争后的权威同一性裁决**。material identity、请求动作和 source fingerprint 由 Fins 上传 owner 产生；已发布 target 的内容/完整性、revision 与提交可见性由 `dayu.fins.storage` 仓储 owner 产生；public failure/skip 从这两者的同一真源投影。CLI 不拥有业务纠错权。

## 已确认目标与成功信号

1. 在 fresh workspace，对完全相同的 `auto` identity 与字节输入同时启动两个进程，权威发布顺序为一方创建成功；另一方只有在**仓储确认同一已发布目标完整、identity 与本请求 fingerprint 相同**后返回幂等 skipped。最终恰一份 active 文档、一条 manifest、meta/资产完整；skip 不重写 source meta/manifest 或业务时间、版本。
2. 若竞争后权威状态不同、完整性不可证、指纹不同或另有公司/alias 状态漂移，不把冲突伪装为 skipped；从正确 owner 返回与事实匹配的 typed conflict/integrity/operational 结果。真正文件系统 I/O 故障仍保留 storage failure。不能靠 generic `FileExistsError`、异常文本或重试次数推断相同请求。
3. 顺序相同输入 `auto` 的既有 skip、不同内容 `auto` 的版本规则、O13 健康 tombstone 恢复/重复 delete、O32 不同 material identity/不同 ticker 并发保持原合同。接收后的状态漂移与 O12/O14/O15 已定 `source_publication_conflict` 优先级及 alias guard 不发生双真源：本 WU 只能在共享权威 owner 的明确竞争窗口判定同指纹 skip，不能旁路其 guard 或把任意 publication conflict 当作可跳过。
4. 受控同步点的 owner/真实仓储测试覆盖同指纹 success+skip、不同指纹 typed 冲突、真实 I/O、alias/状态漂移、无半发布与 skip 零业务 diff；隔离真实双进程 CLI 重跑多轮，保存每进程 exit/summary、实际启动时差、完整产物与 manifest/meta hash、进程终态。更新受影响测试、逐改动生产文件 coverage >=80%、Python3.11 pyright、README 按触发判定；经 plan/code/deepreview/PR review 后纳入 PR #197。

## 非目标、依赖和停止条件

- 不在 CLI/UI/Service adapter 根据 `storage_io` 或 `FileExistsError` 文案改写 skipped，不做无条件或无限次自动重试，不靠补充长时间全局锁取代同版状态/发布校验；不修改冻结证据或把一组竞态样本推断为统计成功率。
- 实施硬依赖：O12 同版 material published state、**材料发布的** guard 与公司决策，O14/O15 目标状态/后置漂移，O13 skip/tombstone，O04/O23 唯一资产名和 O25 primary/fingerprint 身份都已接受并集成。已接受 O34 允许合法公司事实在材料转换失败/取消后独立保留；O12 正因与此冲突回 plan gate，O33 不得假定公司/材料单 batch 原子化。若最终合同不提供可靠的 target 完整性、fingerprint、revision 或判定时机，先回对应 owner plan 裁决，不新造第二套快照或下游 fallback。O16/O05/O17/O09/O10/O07 等稳定 identity 规则集成后，需重核本 WU identity 输入与真实 CLI 样本。
- 若无法在仓储 owner 可证明的同版已发布状态上区分“相同完成”和“不确定/冲突”，停止实施并报告最小代码/数据证据；不得用一个笼统 skip 或 storage_io 完成本 goal。若需新增公开 schema/状态，回本 goal/plan 裁决。

## 下一 gate

依赖尚未集成，当前只能做条件性 plan 和独立 review；总控先核对实施基线及依赖顺序，再派 Sol 计划、Kimi/MiMo 同版并行复审。产品代码未修复，正式 scenario/readiness 未更新。
