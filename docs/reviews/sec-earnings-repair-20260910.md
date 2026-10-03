# Dayu SEC 业绩补源修复交接 · 2026-09-10

代码修复和隔离验证完成，未提交。未更新投资项目真实 workspace，未提取或批准投资经营指标，未改变冻结财务数字。真实缓存的有限补源由投资主 Agent 独立验收后执行。

1. **根因与修复边界**

ATAT 两份原始 HTML 经生产 `_extract_head_text(..., max_lines=120)` 后，标题均在规范化文本第 92 字符处。修复前均为 `EXCLUDE_NON_QUARTERLY`，当前业绩强信号为 false。因此本次直接根因是标题语法未被强信号覆盖，而非标题在扫描窗口之外。原规则未覆盖 “Reports Third Quarter of 2024 Unaudited Financial Results” 和 “Reports Fourth Quarter and Full Year 2024 Unaudited Financial Results”，导致正文中的 Operational Highlights 提前触发经营更新排除。

在 `sec_6k_rules.py` 的分类 owner 增加通用当前季度业绩标题模式，由强信号、正向保留和预告判断共同引用。保留扫描上限及原排除顺序；单独全年、纯月度/经营更新、业绩预告和电话会安排仍被排除。没有 ticker/accession 白名单。

8-K 的附件索引和封面链接发现原来仅对 6-K 启用。`sec_downloader.py` 将该入口扩展至 8-K，选择同披露 EX-99 HTML；SEC 类型索引可识别通用附件名，文件名识别增加 `exhibit99`，覆盖 META 命名。保留 6-K 的既有通用同披露 HTML 补链。8-K 只从同目录安全相对路径选择附件并去重，拒绝外部、父目录、子目录和编码路径；没有增加图片下载器或全附件抓取。

无需新 CLI 参数或存储迁移。正常增量仍先跳过完整来源；现有 `--overwrite` 重新发现文件并对 6-K 再次分类，绕过同版本拒绝注册表的快速跳过。`--rebuild` 是正式本地来源的元数据重建，不能取得附件或把拒绝文件提升为正式来源。

2. **准确改动清单与版本**

- 生产代码：`dayu/fins/pipelines/sec_6k_rules.py`、`dayu/fins/downloaders/sec_downloader.py`。
- 新测试：`tests/fins/test_sec_earnings_repair.py`。
- 新夹具及审核产物：`tests/fins/fixtures/sec_earnings_repair_v1/`，包括 12 份完整 Raw HTML、2 份来源清单、说明和审核结果/日志；各文件摘要见同目录 `change_manifest.json`。
- 文档：根 `README.md`、`dayu/fins/README.md`、`tests/README.md`，以及本交接。

没有提交；基线 HEAD 是 `fac32ecbff9bfe792b63ee9667c8697826b631f4`。当前 tracked `git diff --binary` 的 SHA-256 为 `d388219ba04c42bde5ec55908190a02755e7023b01acddb69177b315b187463b`，该摘要包含先前未提交的港股等改动，不能把整个工作树当成本次修复。

开始时的 20 个改动文件均已保留；其中 17 个字节不变，3 个 README 仅插入本次说明。基线与比较记录位于 `workspace/tmp/sec_earnings_fix/baseline.json`、`baseline.diff`、`baseline_verification.json`。本任务未修改已有 `tests/fins/test_sec_pipeline_download.py` 或港股生产代码。

3. **验证命令与实际结果**

从项目根目录执行：

```bash
source .venv/bin/activate
pytest -q tests/fins/test_sec_earnings_repair.py \
  tests/fins/test_sec_downloader.py \
  tests/fins/test_sec_pipeline_download.py \
  tests/fins/test_sec_pipeline_download_stream.py \
  tests/fins/test_hk_period_rebuild.py \
  tests/fins/test_cn_report_selection.py \
  --cov=dayu.fins.downloaders.sec_downloader \
  --cov=dayu.fins.pipelines.sec_6k_rules --cov-report=term-missing
pytest -q tests/fins/test_fins_storage_atomicity.py \
  -k 'concurrent or cross_process_writer or recovery_try_lock'
python -m pyright dayu/ tests/ utils/
git diff --check
```

结果：第一组 **272 passed**，3 个既有 edgartools 弃用警告；第二组 **8 passed / 201 deselected**。覆盖率：`sec_downloader.py` **94%**，`sec_6k_rules.py` **87%**。全量 pyright **0 errors / 0 warnings**，diff whitespace 检查通过。

新增离线集成测试调用真实 `dayu.cli.main.main`，仅替换 HTTP transport；12 份正文均为真实字节。先通过生产 CLI 模拟旧规则形成历史完整封面或拒绝缓存，然后恢复规则、以 `--overwrite` 补源。验证文档 ID、封面字节、每个文件大小/SHA-256、重新计算的 source fingerprint、完整性检查、manifest/仓储索引、processed `reprocess_required`、跨公司/跨披露日隔离、附件失败回滚、三个附件发现取消检查点、以及第二次增量无受管文件变化。

另外通过未替换 transport 的公开 CLI 在两个新临时 workspace 执行真实回源：六个 accession 全部成功，第二次均 `downloaded=0 skipped=1`；四份 8-K 又在仓储生成的历史完整封面夹具上完成真实 `--overwrite` 补源，封面逐字节未变，所有新增文件 hash 与 fingerprint 重算通过，其他目标 metadata 未变，随后再次增量跳过。

原始诊断来源 → Raw → 审核 → 交接的完整记录见：

- [来源与 Raw 说明](../../tests/fins/fixtures/sec_earnings_repair_v1/README.md)
- [机器可读审核结果](../../tests/fins/fixtures/sec_earnings_repair_v1/workpapers/validation.json)
- [最终回归日志](../../tests/fins/fixtures/sec_earnings_repair_v1/workpapers/final-tests.log)
- [并发锁回归日志](../../tests/fins/fixtures/sec_earnings_repair_v1/workpapers/lock-tests.log)
- [类型检查日志](../../tests/fins/fixtures/sec_earnings_repair_v1/workpapers/final-pyright.log)

4. **主 Agent 验收后执行的精确公开 CLI 命令**

以下命令尚未对投资 workspace 执行。先确认使用本工作树代码及已配置的 `SEC_USER_AGENT`；从项目目录执行：

```bash
cd /Users/leo/workspace/dayu-agent-r
source .venv/bin/activate
DAYU_REPAIR_BASE='/Users/leo/Documents/_2我的投资/workspace'

dayu-cli download --base "$DAYU_REPAIR_BASE" --ticker ATAT --forms 6-K --start 2024-11-19 --end 2024-11-19 --overwrite
dayu-cli download --base "$DAYU_REPAIR_BASE" --ticker ATAT --forms 6-K --start 2025-03-25 --end 2025-03-25 --overwrite
dayu-cli download --base "$DAYU_REPAIR_BASE" --ticker MSFT --forms 8-K --start 2025-07-30 --end 2025-07-30 --overwrite
dayu-cli download --base "$DAYU_REPAIR_BASE" --ticker META --forms 8-K --start 2024-02-01 --end 2024-02-01 --overwrite
dayu-cli download --base "$DAYU_REPAIR_BASE" --ticker META --forms 8-K --start 2025-01-29 --end 2025-01-29 --overwrite
dayu-cli download --base "$DAYU_REPAIR_BASE" --ticker META --forms 8-K --start 2026-01-28 --end 2026-01-28 --overwrite
```

预期原 accession/document_id 保持不变：

| document_id | 应正式登记的业绩附件 |
|---|---|
| fil_0001104659-24-120329 | tm2428837d1_ex99-1.htm（成为 6-K primary） |
| fil_0001104659-25-027458 | tm2510227d1_ex99-1.htm（成为 6-K primary） |
| fil_0000950170-25-100226 | msft-ex99_1.htm |
| fil_0001326801-24-000010 | meta-12312023xexhibit991.htm |
| fil_0001326801-25-000014 | meta-12312024xexhibit991.htm |
| fil_0001628280-26-003832 | meta-12312025xexhibit991.htm |

每个命令按公司、表单、包含边界的披露日期选择；当前没有 accession/document_id 下载筛选参数，同日同表单的其它披露也在选择范围内。本次真实查询各命令均发现 1 份目标。

`--overwrite` 会重新获取该披露当前选中的完整文件集合，包含封面、EX-99 和原有 XBRL 选择；通过原子事务更新 metadata、manifest、source revision 和相关处理失效标记。文件 hash 取实际字节；SEC fingerprint 按文件名与远端描述符的 ETag/Last-Modified 既有契约计算，不能要求人为维持旧值。它不等同于逐文件内容 hash。此次两轮真实回源确认封面内容没变。

完成后把上述每行的 `--overwrite` 去掉再执行，预期每行 `downloaded=0 skipped=1 rejected=0 failed=0`，受管文档不再变化。不要再次带 `--overwrite` 来检验增量幂等；该参数明确请求重新获取来源。

5. **限制与后续边界**

- 修复仍使用有界标题扫描；没有把任意晚出现的历史标题当作当前业绩，也没有重新设计 6-K 分类器。
- 8-K 选择的是可确认的同披露 EX-99 HTML，未实现通用图片、PDF 或全部附件抓取。类型索引缺失且文件名/安全封面链接都不能指向 EX-99 的材料不在本次保证范围。
- 实际补源仍依赖 SEC 可用性及身份配置；如远端文件随后变化，Dayu 应按新字节登记，而非强行保留旧 hash。单来源失败/发布前取消保留旧完整文档。
- 投资主 Agent 应独立验收来源完整性与所需业务口径，再仅对相关股票重走第 1–4 步。这里不重做 10 家已完成的 KPI，不批准第 4/5 步，不从 `.rejections` 提取财务数字，也不以手改受管清单替代正式补源。
