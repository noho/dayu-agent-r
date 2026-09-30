# UM-O14-F01 + UM-O15-F01：material action/target 状态前置契约 goal confirmation

- Gate：goal confirmation pass。工作区 `/private/tmp/dayu-upload-state`，分支 `codex/upload-material-state`，基线 HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`，开始时干净。
- 用户已分别接受 `docs/reviews/upload-material-um-o14-oracle-adjudication.md` 与 `upload-material-um-o15-oracle-adjudication.md`，并授权全部修复进入 PR #197。两项共享动作/目标状态语义 owner，合成一个 work unit 计划与实现；各修复标签独立验收。

## 动机、直接代码事实与严重性

`dayu/fins/pipelines/docling_upload_service.py:evaluate_upload_overwrite_precondition` 已对 create+已有目标且无 overwrite 返回 `CREATE_TARGET_EXISTS`，对 update+缺失返回 `UPDATE_TARGET_MISSING`；`prepare_upload` 只对 filing 执行前者，对后者迟至文件验证/公司提交后才抛 `FileNotFoundError`。delete 不经过此 precondition，缺失目标落仓储异常。SEC/CN/HK material workflow 在读取 previous meta 后立即发 `UPLOAD_STARTED` 并先提交公司 meta，目标冲突/缺失才从后续上传或删除反映。当前流程会把业务状态错误误投为 storage_io、产生公司/身份副作用；O14 相同内容 create 还可能 skip。动机与严重性由代码加冻结 A04/A11–A13 直接支持，不能把 `FileNotFoundError` 文本或单个市场的偶然结果当 owner。

## 目标与成功信号

1. 对 active 已有材料显式 create 且未 overwrite，无论内容相同/不同，都由共享状态 owner 在 `upload.started`、公司提交和转换前返回动作明确的 typed conflict，零业务发布。显式 `create --overwrite` 可替换已有目标，ID 稳定、内容升版及 meta/manifest 同源；fresh create 正常。
2. 对从未存在目标的显式 update（有/无 overwrite）和 delete，由同一状态 owner 在上述生命周期/提交前返回动作明确 typed target-missing，零公司/材料业务持久化。overwrite 不把 update 变成 upsert。已删除 tombstone 的重复 delete 仍成功且不被误判 never-existed；O13 的 tombstone 时间幂等是独立 work unit。
3. SEC/CN/HK material、runtime direct/job/observation、Service/CLI/tool 均消费同一状态结果/错误投影。仓储 publication 边界仍在竞态时保障不能非法覆盖或删除；不靠 CLI 事后回滚。owner/市场/入口测试与隔离真实 CLI 证据覆盖目标状态矩阵、并发或 target 消失边界、公司/meta/manifest/SQLite/事件/双流；受影响测试、pyright、逐修改生产文件 >=80% coverage。

## 边界与停止条件

- O16 action/files 组合必须先于本项目标状态；O05/O07/O09/O10/O17 的稳定身份/字段准入确定被查目标；集成时串行核对这一优先顺序。本 work unit 不实现它们，也不定义 tombstoned create（O14 未覆盖）；若 published meta 无法区分 active/tombstone/never existed，plan 必须先以代码/仓储证据定 state owner 与最小规则，不臆造。
- O13 重复 delete 的 `deleted_at` 幂等另行修复；本项只不得阻断其现有重复删除成功路径。O18 amended、内容去重、Docling 格式与 storage 其它完整性不在范围。
- 真实状态读取应通过 `dayu.fins.storage` 仓储协议，不新建文件系统旁路；并发最终 publication check 不能被前置快照替代。若无单一 owner 可同时保证前置无业务副作用与并发拒绝，停止实现并记录不可达原因，不用下游 fallback。

下一 gate：Sol plan，随后 Kimi/MiMo 独立 planreview。当前无产品改动。
