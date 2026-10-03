RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol
CANARY=gpt-6-sol-c5aaaaf3

# UM-O11 S1 根 README 日期段修复记录（2026-09-29）

- 范围：仅处理 O11-CR-F1；基线 HEAD `9141b5e9c65caaf52416f177a2641f8a7e1134ad`，工作区 `/private/tmp/dayu-upload-o11`。
- 结果：根 README 日期段文案已修；未修改产品代码、测试、其它 README、计划、旧评审或裁决，未推进 code review gate，未提交、push、PR 或 merge。
- 动机：MiMo 指出的缺格真实存在。原候选文案遗漏 CLI `upload_filing` 空串/纯空白日期拒绝，也未说明 CLI `upload_material --report-date ""` 当前的折叠行为。该问题是最终用户文档准确性问题，严重性为低；现有 CLI 与 Fins 准入无需改动。

## 修改与边界

仅改 `../../README.md` 上传章节的日期段：将日期格式要求限定于非空日期；明确 CLI `upload_filing` 两日期参数的空串/纯空白用法错误；说明 CLI `upload_material` 两日期参数当前的空串/纯空白折叠，并仅将 `--filing-date ""` 写作既有受支持用法。对于 material 的 `--report-date ""` 或纯空白写法，文案建议省略参数，不将其折叠行为升级为新的产品承诺。保留工具调用空串/纯空白拒绝及 `upload_filings_from` 的范围界限。根 README 的 `Agent更新约束` 允许当前 CLI 用法说明，并要求以实现核对用户可见行为；本修改符合该职责。

## 逐格 owner 核对

`dayu/cli/arg_parsing.py` 的两个日期参数没有输入归一化。以下结果来自当前 CLI owner 代码和 Fins 准入代码的调用链，而非测试夹具：

| CLI 命令 | 日期字段 | `""` | 纯空白，例如 `" "` | 直接证据与文案边界 |
| --- | --- | --- | --- | --- |
| `upload_filing` | `--filing-date` | 原文进入 Fins，拒绝 | 原文进入 Fins，拒绝 | `dayu/cli/commands/fins.py:695` 原文传递；`dayu/fins/ingestion_runtime.py:1288` 校验；README 明确拒绝 |
| `upload_filing` | `--report-date` | 原文进入 Fins，拒绝 | 原文进入 Fins，拒绝 | `dayu/cli/commands/fins.py:696` 原文传递；`dayu/fins/ingestion_runtime.py:1289` 校验；README 明确拒绝 |
| `upload_material` | `--filing-date` | CLI 折叠为 `None` | CLI 折叠为 `None` | `dayu/cli/commands/fins.py:736,1279-1289`；仅显式空串为 accepted plan 已接受的 CLI 例外，README 保留其既有支持 |
| `upload_material` | `--report-date` | CLI 折叠为 `None` | CLI 折叠为 `None` | `dayu/cli/commands/fins.py:737,1279-1289`；README 只陈述当前实现，并引导省略参数，不新增稳定空值用法 |

Fins 的 `_validate_optional_upload_iso_date`（`dayu/fins/ingestion_runtime.py:1372-1394`）只跳过 `None`，其余原文交由 `parse_iso_calendar_date`（`dayu/fins/domain/filing_semantics.py:375-404`）按完整 `YYYY-MM-DD` 和真实公历日校验。filing 静态准入与 material 共享准入分别按字段调用该 helper；CLI 的 material 空值折叠发生在构造 request 之前。`run_fins_direct_command` 把 `FinsUploadUsageError` 投影为用法错误退出码 `2`。已接受计划 `docs/gateflow/upload-material-o11-dates-plan-20260929.md` 仅接受显式空 `--filing-date ""` 的 CLI 例外，R2 保留其它 material 空值组合待独立裁决；本次文案不改变该边界。

## 验证与残余

- `git diff --check`：通过，exit `0`；README 仅日期段变化。新 artifact 为未跟踪文件，不包含在该命令的工作树 diff 检查中，已单独检查其行尾空白。
- 本轮是纯文档修复，没有改产品或测试代码，故未重跑产品测试和 pyright。修改前后六个产品/测试候选文件的 `git diff` SHA-256 均为 `3c5261daba2736581fc61848749462862c40baf8cdbbc504506e608d53284ee9`。先前实施与双路评审所记录的受影响测试 `714 passed`、三个生产文件覆盖率 `86%/91%/93%`、pyright `0 errors, 0 warnings` 未因本轮代码改动失效；这些是既有记录，不是本轮重跑结果。
- README 本轮文件 SHA-256：`c1cd17458804aa6415beccb03320dd0b2d922df89de596019f81534208775dc3`。
- 残余：R2 中 material 其它空值组合仍只有当前 CLI 实现事实，是否成为稳定产品契约需独立裁决；`upload_filings_from` 日期元数据及 O05/O16 集成仍在既有残余范围。本次没有对空 `--report-date` 做 fresh CLI 实跑，逐格结论限于当前 owner 代码；code review gate 的后续双路复核由总控另行安排，本轮到此停止。
