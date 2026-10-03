# UM-O04-F01 + UM-O23-F01：material 资产数量与身份规划 goal confirmation

- Gate：goal confirmation pass；work unit 合并两个已接受修复标签，两个标签仍分别验收。工作区 `/private/tmp/dayu-upload-assets`，分支 `codex/upload-material-assets`，基线 HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`，创建时干净。
- 用户此前逐项接受 `docs/reviews/upload-material-um-o01-o06-oracle-adjudication.md` 的 O04 和 `docs/reviews/upload-material-um-o23-oracle-adjudication.md` 的 O23，并补充要求“文件名 → Docling 文件名”统一函数防止漂移；后来授权全部修复进入 PR #197。冻结观察只作历史证据，当前设计依据以下本 HEAD 代码。

## 动机、直接证据与严重性

动机成立。`DoclingUploadService._build_original_assets` 对 material 用 `file_path.name`，`_build_pending_assets` 在每次转换成功后用 `file_path.stem + "_docling.json"`；因此 `deck.txt` 与 `deck.md` 的两个派生名相同，转换已经付费执行才在仓储发布阶段失败。`_build_filing_derived_asset_identity` 已从 filing original storage identity 构造派生名，两条 source kind 路径却各自拼接，没有统一函数。`_validate_source_files` 只检查存在/普通文件，不规划整批身份；原件相同 basename、重复路径、原件与另一派生名交叉碰撞都可能迟至后续阶段。仓储完整性拒绝仍是必要防线，但业务输入应在转换前被 typed 拒绝或被无冲突规划成功。

数量上限有可核对的**当前公共依据**：上传工具 `files` schema 的 `maxItems=100`（`dayu/fins/tools/upload_tools.py`），Fins `TOO_MANY_FILES` closed code/文案明确“不能超过 100 个”（`ingestion_runtime.py`），共享 `_MAX_TUPLE_ITEMS=100`。当前 material 的限额若迟至摘要或 stream 才触发，仍是时机/分类缺陷；本 work unit 不发明 101 样本之外的新阈值，统一采用已有公开的 **100**，并测试 100/101 两侧。

## 目标与成功信号

1. Fins material 文件数量、重复规范路径、重复 original basename 和规划后 original/derived 全局真实名字冲突，在 Docling 启动前由唯一 owner 校验。不能唯一规划的输入返回有界、路径安全、用户可修正的 typed usage；原件、派生资产、source meta/manifest 均不发布，也不把内部仓储异常写成 `unexpected_runtime`。100 个以内允许，101 个前置拒绝；合法多文件不因旧 stem 规则被误拒。
2. 用**一个**“original storage 文件名 → Docling storage 文件名”函数为 filing/material 派生 identity；material 基于完整原件 storage identity 而非截断 stem，支持 `probe.txt+probe.md`、`deck.txt+deck.md` 同次成功。统一规划一次得到 ordered original/derived 对应和全局唯一集合，之后转换、blob/file entry、primary、fingerprint、meta/manifest/read 只消费同一规划事实，不在消费者处重算。filing 既有 identity 算法和合法资产结果不因本项改变。
3. owner 级测试覆盖重复 path/basename、同 stem 不同 suffix、原件与派生名交叉碰撞、逆序、正常不同 stem、100/101 上限与 filing/material 映射。隔离真实 CLI 新证据核对成功/失败、转换是否启动、双流、exit、文件/meta/manifest/SQLite/process；冻结 F20/F21/F22/S19/S20 不当作修复后测试。

## 范围与非目标

- 资产身份/规划 owner 位于 Fins 文件选择与 `DoclingUploadService` 的直接上游或同一 owner 模块，plan 应依调用链确定 API 与 typed 失败投影；CLI/Service、仓储和显示层不独立计算名字。不同路径同 basename 仍拒绝，不从父目录推断覆盖。用户输入的不同 basename 同 stem 在可唯一规划时成功。
- 不改 Docling 内容抽取质量、格式 capability、conversion backend、存储完整性合同、文件数量 100 之外的其它业务字段或 action 状态机。不在本项决定 O25 primary 选择业务规则；现有 primary 若使用首转换文件，其消费的文件名必须来自同一计划，O25 后续只改选择规则。不能用仓储兼容或 CLI 回滚后重命名掩盖 owner 错误。
- 如果单文件名长度、文件系统限制或跨 source kind 命名空间使上述统一映射不可无冲突实现，plan 必须提出直接反例及有限规则，并停止扩写 goal；不得用任意 hash 截断与碰撞忽略解决。

下一 gate：gpt-6-sol 形成最小可实施 plan，再由 Kimi/MiMo 独立并行 plan review；未通过前不实施、不提交。所有闭环代码进现有 PR #197，用户手工 merge。
