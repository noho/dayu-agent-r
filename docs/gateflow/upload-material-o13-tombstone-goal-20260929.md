# UM-O13-F01：重复 delete tombstone 幂等 goal confirmation

- Gate：goal confirmation pass。隔离工作区 `/private/tmp/dayu-upload-o13`，分支 `codex/upload-material-o13`，基线 HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`，开始时干净。
- 用户已接受 `docs/reviews/upload-material-um-o13-oracle-adjudication.md` 的 F01，后续授权全部修复进入 PR #197。本项只处理 tombstone 周期的持久状态幂等，冻结 A07/A08/A09 是缺陷与链路证据，不把旧 A08 时间改写变为合同。

## 动机与直接代码证据

`dayu/fins/storage/_fs_source_document_core.py:_toggle_source_deleted` 当前在每次 `deleted=True` 时无条件写新的 `deleted_at=now_iso8601()`、`updated_at=now_iso8601()`，然后重新写 meta 与 manifest。重复 delete 因此丢失首次进入 tombstone 的时间事实，且改动业务元数据字节；冻结 A08 对同一已删除文档观察到两个时间字段变化。问题严重性是持久状态语义错误，owner 明确在仓储 source-document 状态转换，CLI/manifest 不应补算。

## 目标与成功信号

1. 现存 active 文档首次 delete 将 `is_deleted=true` 并设置本 tombstone 周期的 `deleted_at`；在同一 tombstone 周期再次 delete 仍返回成功/已删除，但保留 `deleted_at`、`updated_at`、source meta 与 manifest 业务字节不变，不重新发布 tombstone 或升内容版本。
2. 恢复（auto 同内容）清 tombstone；随后再 delete 是新周期，应生成新的 `deleted_at`。恢复/再次删除和首次删除的事件、meta、manifest 都投影仓储唯一状态事实。共享 source-document owner 对 filing 与 material 的消费者要核对，不改变 filing 已接受的行为。
3. owner 仓储测试、material 入口状态链测试和隔离真实 CLI 首删→重删→恢复→再删证据覆盖时间/版本/文件字节/双流/退出码；受影响测试与 pyright 通过，每个改动生产文件单文件覆盖率目标 >=80%，按 README 触发规则处理。

## 边界与停止条件

O14/O15 前置目标状态与未存在 delete typed 拒绝另行实现；本项只对仓储已存在且 `is_deleted` 已真时 no-op。O18 amended 与 O33 并发 auto 另行处理。不得在 CLI、manifest writer、测试 fake 或单市场 workflow 独自修复时间；不得从日志或前次命令时间反推。若仓储 batch/manifest 契约使 no-op 无法保持业务字节并正确返回 handle，先以直接证据确认 owner 状态边界，再调整 plan；不做下游补偿。下一 gate：Sol plan → Kimi/MiMo 独立 planreview。
