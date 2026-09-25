# 港股季度识别与本地缓存纠正交接

版本：2026-09-07 r1。修复未提交；基线 HEAD 为 `fac32ecbff9bfe792b63ee9667c8697826b631f4`。
验证环境：项目 `.venv`，Python 3.11。验证仅使用 pytest 临时 workspace。

## 根因与边界

`cn_report_selection.py` 原先把三个月的四种中英文写法列为 Q1 token，并在多季度命中时
吞掉部分 Q1 冲突。HK 财年还会回退到披露年份。单文件下载对 COMPLETE 来源直接 skip；
原本 rebuild 重用旧身份财期。因此只改识别函数不能纠正持久化财期。

另一个关联问题是原 ID 由财期分配。纠正后的同一 provider/source ID 必须继续绑定旧 ID；
若该旧 ID 占用了后续真实 Q1 的分配位置，新来源必须获得独立 ID，避免覆盖已纠正的 Q3。

修改仍由 report selection owner 产生季度事实，现有 download rebuild owner 负责持久化。
没有新增 CLI 参数，没有对公司或 document_id 做生产代码特例，没有下载、解析投资项目正文。
旧缓存缺少 provider 分类时，只从原始标题识别 report/results 家族，不从旧 Q1 标签反推事实。

## 结果契约

- 三个月只表示长度；有明确季度时使用明确季度，有截止日与同公司邻近年度截止日时按财年判断。
- 年度证据采用明确全年/十二个月业绩截止日，须为相距不超过 366 天的规则月末日历。
  日期、类别、季度、累计期间或财年标签冲突时返回不确定；不使用披露日期推季度或财年。
- 保持 report FY/H1 与 results Q1～Q4 的身份边界；Q2 coverage 为 H1/Q2，Q4 为 FY/Q4。
- HK rebuild 在取得 ticker writer lock 后读取来源，按旧或新身份加披露日筛选目标；同事务更新
  source meta、filing manifest 及已存在的 processed 财期索引。取消和写入异常回滚暂存。
- document_id、internal_document_id、正文、文件名/文件 hash、source/remote fingerprint 与内容版本不变。
  财期元数据及其 source revision 可以变化。重复执行不再发布 source/manifest/processed 改动。
- 普通增量发现同来源已有财期不一致时返回 `period_metadata_mismatch` 并要求 rebuild，
  不把新候选财期冒充已纠正的持久化事实。重建后增量复用原 ID 并 skip 完整正文。

## 独立验证后执行的确切 CLI

以下命令本轮均未在投资 workspace 执行。原任务 Agent 应先独立检查本地年度截止日证据，
并按投资项目既有规则另起 Raw/底稿版本后再执行正式更新。

```bash
cd /Users/leo/workspace/dayu-agent-r
source .venv/bin/activate

dayu-cli download --base '/Users/leo/Documents/_2我的投资/workspace' --ticker 3690 --forms Q1 Q3 --start 2024-11-29 --end 2024-11-29 --rebuild
dayu-cli download --base '/Users/leo/Documents/_2我的投资/workspace' --ticker 3690 --forms Q1 Q3 --start 2025-11-28 --end 2025-11-28 --rebuild
```

影响范围是 **3690、指定披露日、纠正前或纠正后身份为 Q1/Q3 的本地下载来源**，不按 ID 硬编码选择。
年度公告可作为只读日历依据，即使位于该披露日窗口之外，也不会因此被更新。

有充分年度证据时预期：

| 保留的 document_id | 财年 | 身份/coverage | report_date |
| --- | --- | --- | --- |
| fil_cn_d50c1a9b989cc8c25a6a56527f8e17f7bbf9c1c1 | 2024 | Q3 / [Q3] | 2024-09-30 |
| fil_cn_ff9df5c7cf46d61df96844584c4a0f5c9fa10ef9 | 2025 | Q3 / [Q3] | 2025-09-30 |

首次成功结果的 disposition 使用既有 `downloaded` 枚举，但下载文件数为 0；第二次为 `skipped`，
原因为 `period_metadata_current`。信息不足为 `uncertain_hk_period`，CLI 退出 1 并保留对应旧来源；
**这不代表该来源已经纠正**。来源物理不完整为 `incomplete_source`，不会进行仅财期修改。

若缺少年度截止日来源，可由原任务 Agent 经 Dayu 获取年度业绩后重试，例如：

```bash
dayu-cli download --base '/Users/leo/Documents/_2我的投资/workspace' --ticker 3690 --forms Q4 --start 2024-01-01 --end 2026-09-07
```

这条准备命令可能新增年度正文，不属于上述“仅财期”纠正动作，本轮未执行。若年度标题仍无明确
截止日，重建继续保留不确定性，不允许手工改 meta/manifest 冒充识别成功。

## 测试与审核底稿

原始问题来源：用户提供的两个 document_id、披露日及只读诊断
`/Users/leo/Documents/_2我的投资/workpapers/valuation_research/common_step4/20260907-r1/Dayu_Period_Diagnosis.md`。
没有提取真实投资财务数据，未生成或更新投资项目 Raw/底稿。代码验证沿用项目测试目录结构：

1. Raw 逐笔输入：`tests/fins/test_cn_report_selection.py` 的原始公告标题/分类/日期和
   `tests/fins/test_hkexnews_downloader.py` 的未汇总 provider 响应 fixture。
   缓存复现使用 `tests/fins/test_hk_period_rebuild.py::_seed` 的合成原始标题、来源 ID 和披露日；
   错误 Q1 是显式构造的旧缓存状态，不宣称是从真实文件提取的数据。
2. 计算和审核底稿：这些测试调用实际 selection、HTTP downloader 边界、pipeline、仓储和生产 CLI；
   期望值、故障注入及排除项均在测试中显式定义，可重复执行。临时缓存由 pytest 隔离生成。
3. 最终结果：本交接文档仅依据通过的测试与类型检查形成，不输出投资金额、估值或未审核的财务结论。

检查包括：繁简中文、英文与中文数字日期，四季度及单季/累计组合，非自然年度，年度变更、
多日期/无效日期、明确财年标签冲突，真实 CLI 纠正后 source/manifest 完整性和 processed 查询索引，
正文/文件描述符/hash/fingerprint/内容版本逐项勾稽，重复执行整棵 published portfolio 逐字节一致，
两个独立仓储并发仅一次发布，取消/写入失败回滚，以及后续增量和真实 Q1 的 ID 占用处理。

```bash
source .venv/bin/activate
pytest -q \
  tests/fins/test_cn_report_selection.py \
  tests/fins/test_hk_period_rebuild.py \
  tests/fins/test_cn_download_workflow.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_hkexnews_downloader.py \
  tests/fins/test_cninfo_downloader.py \
  tests/fins/test_cn_download_runtime.py \
  tests/cli/test_fins_commands.py \
  tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_filing_upload_publication.py \
  --cov=dayu.fins.pipelines.cn_report_selection \
  --cov=dayu.fins.pipelines.hk_fiscal_calendar \
  --cov=dayu.fins.pipelines.hk_download_rebuild \
  --cov=dayu.fins.pipelines.cn_download_identity \
  --cov=dayu.fins.pipelines.cn_download_filing_workflow \
  --cov=dayu.fins.pipelines.cn_download_workflow \
  --cov=dayu.fins.pipelines.cn_download_models \
  --cov=dayu.fins.pipelines.cn_download_rebuild \
  --cov=dayu.fins.pipelines.cn_download_source_upsert \
  --cov-report=term-missing
pyright
git diff --check
```

最终结果（2026-09-07，r1）：**744 passed，3 个既有 edgartools 弃用警告，36.98 秒**。
9 个修改生产模块合计覆盖率 91%，单模块均 ≥80%：selection 92%、calendar 96%、HK rebuild 96%、
identity 93%、filing workflow 87%、download workflow 93%、models 97%、CN rebuild 86%、source upsert 86%。
全项目 `pyright`：**0 errors, 0 warnings**；`git diff --check` 通过。
审核结论：隔离缓存纠正、幂等性、身份/正文保留及相关回归通过；实际投资缓存的年度证据完整性未验证。

## 本次准确改动清单

生产代码：

- `dayu/fins/pipelines/cn_report_selection.py`
- `dayu/fins/pipelines/cn_download_models.py`
- `dayu/fins/pipelines/cn_download_source_upsert.py`
- `dayu/fins/pipelines/cn_download_rebuild.py`
- `dayu/fins/pipelines/cn_download_workflow.py`
- `dayu/fins/pipelines/cn_download_filing_workflow.py`
- `dayu/fins/pipelines/cn_download_identity.py`（新增）
- `dayu/fins/pipelines/hk_fiscal_calendar.py`（新增）
- `dayu/fins/pipelines/hk_download_rebuild.py`（新增）

测试：`tests/fins/test_cn_report_selection.py`；`tests/fins/test_hk_period_rebuild.py`（新增）。

文档：`README.md`；`dayu/fins/README.md`；`tests/README.md`；本交接文档（新增）。

保留此前未提交改动：`dayu/fins/domain/filing_semantics.py`、`dayu/fins/pipelines/sec_form_utils.py`、
`dayu/fins/processors/sec_processor.py`、`tests/fins/test_financial_read_contracts.py`、
`tests/fins/test_sec_pipeline_download.py` 均未由本任务编辑；`dayu/fins/README.md` 原有修改保留，
本任务仅追加港股契约说明。

## 已知限制

- 尚未检查真实 workspace 中年度证据是否齐全，也没有在真实两个来源上执行更新；结果是隔离合成缓存验证。
- 截止日推季度仅支持有邻近证据的规则月末财年；52/53 周财年、过渡年度、财年区间简写和
  标题无法唯一解析的日期不作猜测。明确季度仍须与可用日历证据相容。
- 不从正文自动抽取财年。在线窄日期窗口若没有年度证据，单独三个月公告可能不入候选；
  本地 rebuild 可以读取窗口外的同公司年度证据。
- rebuild 不负责修复损坏正文或恢复缺失文件。一个目标依据不足可以失败而其它有明确依据的目标成功；
  整体取消或仓储异常则回滚本次暂存。
- 财务年度采用结束年份；与显式财年标签冲突时保留不确定性。原有英文副本过滤规则保持不变。
- 未新增自动正式数据更新流程；后续财报数据更新由原任务 Agent 独立验证后推进。
