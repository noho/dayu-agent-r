# UM-O07-F01/F02 + UM-O08：material 身份公开输入 goal confirmation

- Gate：goal confirmation pass。工作区 `/private/tmp/dayu-upload-ids`，分支 `codex/upload-material-ids`，基线 HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`；开始时工作树干净。
- 用户已在 `docs/reviews/upload-material-um-o07-oracle-adjudication.md` 与 `upload-material-um-o08-oracle-adjudication.md` 逐项接受裁决，并授权全部修复进入 PR #197。此处沿用已确认的目标，不扩大身份算法或 filing 领域。

## 动机与当前直接证据

`build_material_ids` 对 material 生成相同的稳定 `document_id` 与持久化 `internal_document_id`。CLI `dayu/cli/arg_parsing.py`、Service `dayu/service/fins_direct.py`、tool schema `dayu/fins/tools/upload_tools.py` 和 Fins material request/workflow 仍接受并透传外部 `internal_document_id`；它仅是冗余一致性断言，schema 描述为可给定源文件 ID 会误导调用者。公开 `document_id` 不匹配在 identity owner 后段才抛笼统参数错误，观察到 upload.started 已发出。这是公开契约、错误 owner 和时序缺陷；重要性在于用户输入不能伪装为独立源身份，而且失败须在业务生命周期前定位到字段。

## 目标与成功信号

1. 从 material CLI help/argv、LLM tool schema、Service、Fins request、SEC/CN/HK workflow 的公开输入链移除 `internal_document_id`，无隐藏别名、兼容分支或 wrapper。底层持久化、结果、事件、manifest 中 owner 生成的该字段保留，并与稳定 document_id 同源；filing 独立来源身份不变。
2. 公开 `document_id` 只作 owner 生成身份的一致性断言。精确值正常上传；不匹配及显式空值在身份 owner 或直接上游校验边界给出字段级 typed usage，尽可能在 `upload.started` 前拒绝，且零业务发布。未提供则 owner 生成稳定 ID；成功的事件、meta、manifest 身份一致。
3. owner 与各公共入口测试覆盖旧参数空/非空均未知参数、tool schema 无此输入、无参/匹配/不匹配 `document_id`、无副作用与跨命令消费；隔离真实 CLI 补跑记录 help、exit、stdout/stderr、持久化与文件系统状态。

## 边界与残余

不改变 material ID 摘要算法、不添加外部来源 ID、不改变 filing 身份语义、仓储模型或其它字段验证。O17 form canonical、O09/O10 fiscal 域会影响 ID 的规范化输入，集成时必须串行核对；若无法在当前 owner 入口实现生命周期前校验，plan 应拿代码证据说明并停在设计裁决，不能下游补救。公开 document_id 的空值规则遵循 O08 已接受裁决，不为已移除内部 ID 建独立空值兼容。下一 gate：Sol plan，双路独立 planreview 后才能实施。
