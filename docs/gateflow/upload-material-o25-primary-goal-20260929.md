# UM-O25-F01：material 主原件选择与跳过决策 goal confirmation

- Gate：goal confirmation pass。隔离 checkout `/private/tmp/dayu-upload-o25`，分支 `codex/upload-material-o25`，基线 HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`，开始时干净。用户已在主工作区 `docs/reviews/upload-material-um-o25-oracle-adjudication.md` 明确接受“多文件必须指定主原件，单文件自动选”，并授权闭环代码进入 PR #197。冻结 S24/S25 是旧 validation commit 的不同输入顺序观察，不是当前 HEAD 的行为验收。

## 动机与代码事实

`docling_upload_service.py:_build_pending_assets` 当前把首个 Docling 产物设为 `primary_document`，而 material CLI 没有 `--primary`，tool 显式拒绝 material `primary`。该 primary 被 source meta 持久化并由 `get_primary_source()`/read runtime 作为后续分析默认源消费，所以多文件输入顺序目前会改变跨命令读取的业务事实。`_build_upload_source_fingerprint` 按原件名排序，逆序输入仍可同指纹；同一 workspace 中更换期望主文件可能被 skip，不能只补 help 或改结果排序。动机成立，严重性是被读取的内容可能不是用户指定的主材料，owner 在 Fins 文件选择与资产规划，不在 UI/read adapter。

## 目标与成功信号

1. 多文件 material 必须在公开 CLI/tool/Service 输入显式指定**唯一主原件**；单文件未给 selector 时自动选择唯一原件。缺失、重复、未精确命中、delete 携带 selector 在转换和发布前给 typed、可行动且安全的失败；不从 basename、argv 顺序或转换结果猜主文件。
2. 同一 Fins owner 用 exact 原件 selector 与 O04/O23 的唯一原件→Docling 名称规划得到 `primary_document`；所有原件仍转换。角色进入 source fingerprint/skip、source meta/manifest 的同源摘要及 read snapshot。相同原件字节而更换主文件应改变角色指纹并实际更新，同一主文件正逆序应相同；material document ID 由业务身份保持。
3. owner/CLI/tool/Service/跨命令 read 测试与隔离真实 CLI 覆盖单文件自动、多文件合法/缺失/重复/未命中、同一 workspace 主文件变更及 `process_material` 的读取事实；测试、pyright、逐改动生产文件覆盖率目标 >=80%，README 按触发与读者职责更新。

## 边界与依赖

O04/O23 必须先建立唯一资产名和文件名→Docling 文件名函数；本 work unit 消费该规划，不能在自身再造转换名映射。O21/O22 内容失败、O16 action/files、O13/O14/O15 发布状态、O33 并发等独立 work unit 不在此实现，但集成时需用共同 owner 回归。不要为旧“首文件隐式 primary”行为加兼容分支，不改变 Docling 抽取质量或 filing 已有主文件选择语义。若现有 selector 契约无法跨三个公开入口表达 exact path，plan 需给直接代码证据和最小接口修订；若 O04/O23 规划尚未通过/实施，不进入本项 implementation。下一 gate：Sol plan 与 Kimi/MiMo 独立 planreview。
