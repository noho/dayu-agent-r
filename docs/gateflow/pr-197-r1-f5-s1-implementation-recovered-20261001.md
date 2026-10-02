RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/GPT-6（当前会话未暴露精确模型路由标识）
CANARY=gpt-6-sol-3da8bc98

# PR197 F5-S1 恢复实施

任务 pr197-f5-s1-recover-sol-20261001-01；implementation in progress，尚无代码 gate pass。

初检：freeze SHA256 28a044f3fa13b0b7bbc0cc3ba2d1d0c3c2ffd2f904478c3d17faa8bf13dc82e1；67 current 与 67 originals 全部匹配。branch codex/upload-material-oracle，HEAD 3a836a463aab3eeffb050facd592e614801d6ca9，main fac32ecbff9bfe792b63ee9667c8697826b631f4。accepted checkpoint 是接受真源，计划 202 行及 SHA 匹配。沿用既有 21 产品 partial；root controller、历史报告与其他 writer 成果只读保全。远端状态来自用户输入，未网络复核。

## 本轮集中修复登记

- F5-R01，owner=ingestion_runtime job store/runtime 生命周期。直接源码仍无 mandatory normal/cancel 双投影，锁内取消不保存本次业务摘要，会丢已发布 A。状态：待修；落实 accepted §7–8，不从 JSON 反算。
- F5-R02，owner=runtime public projection。当前 omitted_count 用 discovered 减 visible known，且缺 unknown 构造参数；unknown 被误计为省略文档。状态：待修；改为 known rows 差值并复用 contract 有界投影。
- F5-R03，owner=workflow typed integrity abort。真实单 filing 完整性失败分支缺 uncertain_reports 必填参数。状态：待修；原 cause 与全文未知 tuple 保全。
- F5-R04，owner=SEC typed summary producer/runtime empty summary。mandatory schema caller 未迁移。状态：待修；真实无 unknown 明确传空 tuple，不扩 SEC 解析。

语义依据均为已接受计划；未新裁决，不拆机械 slice。不派发、不提交、不推送、不操作 PR。

工具迁移记录：一次临时 AST 迁移脚本遇 StopIteration（exit1）；同 shell 后续验证仍启动，不能以其外层状态覆盖该脚本失败。原因是测试 fail_save 没有 finished_at 参数；已按真实签名修正。pytest-01 collection exit2 原因是迁移生成 tuple 未加括号，已修正，不作为产品验证通过。

- F5-R05，owner=download contract/public typed projection。真实 240 字 ID 预算回归发现 operation owner 接受 240 字文档 ID，而 FinsDownloadPublicDocument 使用通用 120 字短文本界限，导致正常 typed 结果无法公开。属于 accepted §7 真实 ID 不裁断与既有文本边界；修复 public 文档 ID 复用下载 owner 的 240 常量，不扩大其他字段或预算。

- F5-R06，owner=workflow HK/CN 时序。新增 HK 本地读取后的取消点原初稿无条件执行，导致 CN 原 discovery checkpoint 提前被取消。组合测试直接复现；已只在 HK 读取后增加该点，CN 原协议/时序保全，测试不改旧 CN 断言。
