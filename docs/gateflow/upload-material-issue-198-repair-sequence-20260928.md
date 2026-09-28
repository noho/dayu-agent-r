# upload_material 裁决修复与 issue #198：依赖顺序

日期：2026-09-28。来源：`docs/reviews/upload-material-um-o01-o06-oracle-adjudication.md`、O07～O36 各单项裁决、GitHub issue #198、当前代码和工作树。此文件是总控队列，不替代各 Gateflow work unit 的 goal confirmation/plan/review。所有闭环代码按用户要求进入现有 draft PR #197；用户手工 merge。冻结 oracle 观察不等于当前 HEAD 已修复。

## 修复清单

已接受 **22 项可进入具体设计的 upload_material 修复方向**；其中部分仍有必须在相应 work unit goal/plan 明确的规则。另有 `UM-O20-F02` 仅为条件性处置原则，不能在补证前选定产品修复。

| 分组 | 修复项 | 共同语义边界 |
| --- | --- | --- |
| 工作区路径 | `UM-O03-F01` | 公共 workspace path 目标类型校验。 |
| 请求与身份 | `UM-O05-F01`、`UM-O06-F01`、`UM-O07-F01/F02`、`UM-O09-F01`、`UM-O10-F01`、`UM-O11-F01`、`UM-O12-F01`、`UM-O16-F01`、`UM-O17-F01` | 无条件及状态条件必填、日期/期间域、公开 ID、form canonical 真源与运行时拒绝。 |
| 文件资产 | `UM-O04-F01`、`UM-O23-F01`、`UM-O25-F01` | 单次规划原件/派生资产名，再选唯一 primary 并同源投影到 fingerprint、meta/manifest 与 read。 |
| 发布状态 | `UM-O13-F01`、`UM-O14-F01`、`UM-O15-F01`、`UM-O18-F01` | 目标存在性、重复删除 tombstone、amended 事实和状态转换。 |
| 内容与格式 | `UM-O20-F01`、`UM-O21-F01`、`UM-O22-F01` | 共享 capability 的公开说明、安全文件标签与空字节 typed content failure。 |
| 并发 | `UM-O33-F01` | 同一 auto identity 的权威状态串行化与幂等 skip。 |
| 条件项 | `UM-O20-F02`，前置 `UM-O20-E01` | 有效 Docling JSON/XBRL 样本和依赖快照先补证；再裁决 XBRL runtime/部署能力的具体修复。 |
| 独立 issue | GitHub #198 | download source integrity typed failure 投影与真正未知异常的脱敏日志。 |

点号元数据忽略逻辑已有未提交代码，属于 storage source integrity 的独立 work unit，不能把它冒充 issue #198 或 upload_material 修复；用户要求其闭环代码同样进入 PR #197。O36 的 `E01/E02` 是证据标签/报告范围纠错，不是产品修复。

## 硬依赖与建议顺序

1. **先隔离并闭环现有脏工作树。** issue #198 与点号元数据 work unit 独立；优先 #198，因为其 typed public failure 已有未提交半成品而真正未知异常日志仍缺失。各自只 stage 自己的文件/hunk，均进入 PR #197。`UM-O03-F01` 路径修复独立，可在后续输入批次处理。
2. **请求与身份真源先于发布。** `UM-O16-F01` 的 action/files 错误应早于 O14/O15 的状态错误；O05/O06/O07/O09/O10/O11/O12/O17 必须在身份生成、`upload.started` 和公司/材料业务提交前给出同源规范化及校验。O06 具体长度和 Unicode 计数口径待该 work unit 明确，不能从 241 字符样本倒推阈值。
3. **资产规划先于 primary。** `UM-O04-F01` 与 `UM-O23-F01` 是一个命名/冲突设计闭环：统一函数规划全部原件与 Docling 文件名。`UM-O25-F01` 必须消费该规划结果，以同一 primary 选择更新指纹、skip、持久化和 read；不保留首文件隐式选主。
4. **动作规则先于高级状态。** O14/O15 使用同一 published source precondition；O13 的重复 tombstone 转换复用仓储状态真源。O18 amended 与内容版本独立、且影响跳过决策，实施前须明确首次发布、同内容改标记、删除/恢复规则。
5. **内容失败与格式能力并行但同源。** O21/O22 合并设计 typed content failure 链；O20-F01 修改共享格式说明。先执行 `UM-O20-E01` 的有效格式补证，之后才可选择 O20-F02 的实现路径。
6. **同一身份并发最后处理。** O33 依赖稳定的 identity、fingerprint、skip、状态转移；先补采 L06 失败方底层异常，不能凭 generic `storage_io` 猜根因。修复后复跑 success+skip 和不同内容竞争。
7. **正式 oracle/scenario 与 readiness 最后。** 按每项 accepted 行为及修复后的隔离真实 CLI 证据登记，不覆盖冻结原始记录；download 既有闭环 oracle 也不能被 #198 的实现静默改写。

所有 work unit 必须依 Gateflow 单独确认目标、生成 plan、双路 review、实施/复审、验证及 checkpoint；总控维护跨项依赖与残余风险。当前进度：issue #198 goal confirmation pass，下一 gate 为 plan；其它 work unit 未开始。`UM-O20-F02` 及任何补证后新增目标须另做 goal confirmation。
