# UM-O17-F01：material form canonical 真源 goal confirmation

- Gate：goal confirmation pass。隔离工作区 `/private/tmp/dayu-upload-o17`，分支 `codex/upload-material-o17`，基线 HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`，开始时工作树干净。
- 用户在 `docs/reviews/upload-material-um-o17-oracle-adjudication.md` 明确接受 form 类别 `strip().upper()` 与“做成一个函数，其它地方调用”，随后授权所有修复进入 PR #197。本 goal 沿用裁决；冻结 A14/A15 只证明旧偏差，不冒充当前 HEAD 的修复证据。

## 动机、代码证据与严重性

动机成立。`dayu/fins/pipelines/docling_upload_service.py:build_material_ids` 对 form 做 `strip().upper()` 后参与稳定 ID seed；US `sec_upload_workflow.py` 与 CN/HK `cn_pipeline.py` 各自把原始 `form_type` 送入 upload.started、`prepare_upload`、source meta、material manifest 与结果。对于 `" material_other "`，当前身份按 `MATERIAL_OTHER` 产生，持久化与可读投影仍可能保留小写/空白。这是同一类别事实在 durable/事件/身份之间分叉，不只是展示文案问题。业务严重性在于后续检索、核对和引用会看到不一致类别；不改变 digest 算法本身。

## 目标与成功信号

1. 在 Fins material 语义 owner 或其直接上游输入边界设一个公开可复用的 form 类别规范化函数。有效文本统一 trim/uppercase，一次产生 canonical form；material 身份、US/CN/HK workflow、事件/结果、source meta/material manifest 只消费此真源，不在各消费者复制 `.strip().upper()` 或从 ID 反推。
2. `" material_other "` 与 `"MATERIAL_OTHER"` 分别在隔离真实 CLI 请求中产生相同稳定 ID，持久化 meta/manifest 和有 form 字段的事件/summary 均为 `MATERIAL_OTHER`；不同有效类别仍不同 ID。无第二套 raw form 持久化事实、无下游 fallback。
3. owner 行为测试、市场 workflow 和 direct/tool/CLI 可见链路测试，核对规范化同源与发布事实；按 AGENTS.md 跑受影响测试、pyright、每个改动生产文件单文件覆盖率目标 >=80%，检查相应 README 职责。

## 边界、依赖与停止条件

本项不新设 form 枚举/长度域；form 必填/空白 typed usage 由 O05，fiscal_period 允许域与 canonical 由 O10，稳定 ID 的公开断言/内部 ID 移除由 O07 负责。plan 需明确这些在共享 owner 的串行集成点，不能在本项独立增设相互冲突的必填或 period 规则。filing form 与 download form filter 是各自既有语义，不因字符串相似而改。若证明 material 身份 owner 与持久化投影不能共享同一 canonical 值，停止实施、记录直接反例并回到 owner 裁决，不在存储/显示层补偿。下一 gate：Sol plan → Kimi/MiMo 独立 planreview。
