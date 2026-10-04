# UM-O06-F01：material_name 公共长度边界 goal confirmation

- Work unit：`UM-O06-F01`；workspace `/private/tmp/dayu-upload-o06`，branch `codex/upload-material-o06`，HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`。
- 当前 gate：goal confirmation **pass**（2026-09-29 用户明确回复“采用 240 个 Unicode 码点”）。阈值为对 `material_name` 去首尾空白后最多 **240 个 Unicode 码点**；超过 240 在上传启动前统一拒绝。计数按 Python 字符串码点长度，即 `len(name.strip())`；不新增 Unicode NFC/NFD 归一化或字节/字形簇计数。此数字现在是用户裁决的材料名称规则，不能再仅从 job 摘要常量推导。

## 动机及证据

动机成立：隔离冻结补跑 S01 以 241 字符名称上传成功，名称原样持久化并进入稳定 ID；原 UM-035 混入 missing state，不能用于长度归因。当前 HEAD `FinsUploadMaterialRequest.material_name` 为可选 raw 字段，`_normalize_upload_request` 未检查名称长度；material ID owner `build_material_ids()` 只 `strip()` 并拒空值。Fins job 摘要 `_upload_request_summary()` 走 `_optional_bounded_text()`，其通用 `_MAX_TEXT_CHARS=240` 按 `len(value.strip())` 限制，却不覆盖 direct material 入口，所以现有文本边界不是一致的公开名称规则。直接观察与代码事实共同说明需要一个在身份/摘要/存储/LLM 之前的一致 admission 校验；严重性是身份及入口契约漂移，并非已知数据损坏。

## 已确认目标及范围

目标：在 material 名称唯一业务 owner 处按 `len(name.strip()) <= 240` 设定公共上限，对 direct/job/tool 等公开入口统一拒绝超限输入，错误可行动且早于 `upload.started`、ID 生成、业务持久化；合法值身份算法保持原样，无静默截断。`None`/空名称的必填语义仍由 O05 负责，本项不可用长度校验取代或掩盖其错误；O05/O06 应在同一共享 admission owner 中合流，不形成两套长度/必填判断。真实 CLI 对 239/240/241 码点、emoji、组合字符、前后空白与有效对照做独立 workroot 验证，并补 owner 测试、pyright、README 职责判断。组合字符按实际码点分别计数，不新增规范化。

非目标：不在本项处理 O05 缺失、O17 form canonical、O16 文件动作、O04/O23 文件名；不把 job 摘要 240 的既有数字自动认作用户已确认的材料名称阈值，也不从 241 样本倒推 240。O05 同 owner 必须串行集成；后集成者复核前者 HEAD，避免重复校验/不同 code。

## 停止条件与下一步

若代码证明 direct/job/material ID 使用不同规范化结果，必须在 plan 明确唯一 canonical 名称 owner，不能在下游补截断或兼容逻辑。下一 Gateflow entry：gpt-6-sol plan，然后 Kimi/MiMo 同版双路 plan review；当前不实现、不汇入 PR。
