# 美的 2021Q1 完整报告发现修复

## Gate 状态和授权

- work unit：midea-q1-full-report；base HEAD：d30a07c870e3602638d8943ab71a5eaa3e01fc9b。
- preflight：codex/upload-material-oracle，初始 working tree clean。
- goal confirmation：用户回复“1”，后明确允许调度全部三个子 Agent；目标按前一轮所列诊断、有限修复、隔离验证执行。
- 用户明确“不自动提交”，覆盖 Gateflow 默认 commit/push/PR 行为。各 accepted commit gate 记录 no-commit（用户约束）；不创建或宣称 PR pass，最终交付本地 review-ready 修复。
- 当前 gate / next entry point：ready-to-open-draft-PR（未进入；用户明确不自动提交，本轮只交付本地修复）。授权范围内本地修复 completed；不宣称 PR/final-closeout gate pass。
- plan review：`docs/reviews/plan-review-20260915-203419.md`，pass-with-risks；无 accepted finding，fix/re-review 无需执行；accepted plan commit：no-commit（用户明确约束）。
- implementation S1：`docs/reviews/midea-q1-implementation.md`，阶段初始结果 209 focused tests passed、selection 覆盖率 91%、全库 pyright 0 errors、真实 CLI 五轮和来源勾稽通过。
- code review / fix / re-review：`docs/reviews/code-review-20260915-203849.md` 与 `docs/reviews/midea-q1-review-fix.md`；F1 rejected-with-reason，F2/F3 accepted 且已修复，复审通过。修复后 210 passed、coverage 92%、全库 pyright 0 errors；accepted slice commit：no-commit（用户约束）。
- aggregate deepreview：`docs/reviews/code-review-20260915-205037.md` PASS；无新增 finding，fix/re-review 无需执行；accepted deepreview commit：no-commit（用户约束）。最终代码普通 CLI 再次 skip 且快照不变，六轮审核通过。
- 本地 closeout：`docs/reviews/midea-q1-closeout.md`；来源、Raw、底稿、最终结果与独立公开命令已列全。原投资 Agent 为后续投资 workspace/G1 验证 owner。

## 目标、动机和成功信号

确认巨潮是否披露完整报告；只有直接证据成立才修复发现阶段。让同日、同修订优先级的完整中文财报优先于正文，使美的 2021Q1 公开下载选中真实全文，并证明旧正文可通过公开覆盖入口替换，随后增量跳过。

成功：合成回归覆盖选择契约；公开 CLI 下载真实全文；PDF 确认完整合并资产负债表及 2021-03-31 期间；身份、文件集合、hash/fingerprint、manifest 一致；再次增量无改动。测试和 pyright 通过。

## 直接证据和第一性原理

- `cn_report_selection.py:409` 的 `_pick_best_cninfo_announcement` 使用 `(is_amended, announcement_date)` 的 `max`。同分使用输入第一个值；未表达正文/全文偏好。此模块为候选选择语义唯一 owner。
- 原交接目录：`/Users/leo/Documents/_2我的投资/workpapers/valuation_research/cadence_rule_fix_20260912/primary/MIDEA/v5/source_gap_20260915_v1`。Request/Response 中 meta 与 manifest 前后 hash 未变化。
- 隔离未修复 CLI 已下载 source_id `1209870319`、标题《2021年第一季度报告正文》，9 页，PDF SHA256 `6487428b3b848029094a10972771207270cb36a85e42b81b04ae2ff5a89f6939`。底稿 `workspace/tmp/midea-q1-cli/workpapers/before-v1/audit.json`。
- 巨潮原始查询两种窗口均返回 3 条且 hasMore=false：英文全文 `1209870381`、中文正文 `1209870319`、中文全文 `1209870320`；announcementTime 相同。Raw：`workspace/tmp/midea-q1-source/data/raw/`。因此真实候选漏选已成立；全文 PDF 内容仍待公开 CLI 验证，标题不能证明财务表齐全。
- `cn_download_identity.resolve_cn_download_ids` 对 CN 沿用财期身份；阶段机 COMPLETE 且非 overwrite 即 skip。更换非修订 source_id 仍命中旧 ID。已有 `--overwrite` 可重新下载并原子更新，因此无需修改身份、存储或默认增量契约。

## 范围与非目标

生产只改 `dayu/fins/pipelines/cn_report_selection.py` 的 CN 排序 owner。保持标题过滤、财期/财年投影、HK 选择、下载身份、schema、缓存/覆盖状态机不变。使用既有 public CLI 和 storage 协议。禁止投资目录写入、直接替换受管文件、特殊 ticker 分支、全局屏蔽正文、PDF 内容启发式筛选、自动回溯补源、全新修复命令或下载架构重构。

## 实现决策

同财年财期分组内按以下元组取最大值：

1. 是否有真实报告修订标记，沿用现有 amended 规则与过滤，修订仍优先。
2. 公告日期，较新优先。
3. 报告形态：标题不含“正文”优先于含“正文”。已过滤的摘要/英文不进入比较。不要求标题包含“全文”，普通《第一季度报告》同样可优先。
4. announcement_id、source_url：按字符串稳定排序，只为同分确定性，不承诺它们代表新旧或质量。

在模块级新增带完整中文 docstring 的私有排序 key 函数，替换现有无必要嵌套函数。正文 token 用模块级常量。无新增 public API/schema/state transition。保持较新正文和真实修订正文优先于较旧/未修订全文；跨日期不能仅凭名称推断谁取代谁。仅正文时照常返回。

## Slice S1：选择规则及回归

- allowed files：selection.py、tests/fins/test_cn_report_selection.py、tests/fins/test_cn_download_workflow.py、README.md、dayu/fins/README.md、tests/README.md、本 work unit artifacts。
- prerequisites：plan review 通过；真实候选证据已取得。
- 修改上述 CN key，其他选择路径不动。
- owner 测试：Q1/Q3 × 全文/无“全文”普通标题 × 输入顺序；仅正文；同日修订全文/正文；较新真正修订优先；较新普通报告优先；同分 ID/URL 稳定；英文全文/摘要更高 ID 不得入选；不同财年隔离。通过 public `select_cninfo_report_candidates` 断言 source_id、URL、title、period、amended。
- workflow 回归使用现有 fake discovery 和真实仓储：正文源 A1 成功后，全文 A2 默认增量跳过且原 meta 不变；overwrite 更新 source_id/title/url 和 PDF；精确两文件集合、SHA256、content fingerprint、manifest 投影一致；再次增量跳过且 source meta 不变。不在测试 fake 固化排序，不引入生产兼容补偿。
- 验证：`source .venv/bin/activate` 后运行 `python -m pytest tests/fins/test_cn_report_selection.py tests/fins/test_cninfo_downloader.py tests/fins/test_cn_download_workflow.py -q`；覆盖率统计 selection 目标 >=80%；`python -m pyright dayu/ tests/ utils/`。
- docs：Fins README 更新同日形态选择契约；根 README 下载段说明完整缓存需使用公开 overwrite 更新选中来源，rebuild 无法补全文；tests README 按职责记录新增验证入口，不机械写开发过程。
- completion：代码 review、fix/re-review 通过，验证无未裁决阻塞项；no-commit 按用户要求记录。
- stop：证据显示全文无效、修订规则有真实歧义、测试暴露新 owner/schema 需求时先裁决，不扩散范围。

## 真实 CLI 验证与审核链

源日志、请求、HEAD/Raw 响应和提取时刻在 `workspace/tmp/midea-q1-source/data/source_manifest/` 与 `workspace/tmp/midea-q1-cli/data/source_manifest/`。
逐笔原公告保留在 source/data/raw；每轮 CLI 文档经仓储读取后冻结到 cli/data/raw/<version>，不覆盖旧 Raw。
计算审核脚本及输出在 cli/workpapers；最终结果从审核通过底稿生成到 cli/outputs。

固定命令主干：`.venv/bin/dayu-cli download --base /Users/leo/workspace/dayu-agent-r/workspace/tmp/midea-q1-cli/isolated-workspace --ticker 000333 --forms Q1 --start 2021-04-29 --end 2021-04-30`。
未修复 baseline 已完成；S1 后先普通增量确认仍跳过旧源，再加 `--overwrite` 修复同一隔离 workspace，最后普通增量确认跳过。另用全新隔离 base 验证不带 overwrite 首次即可选择全文。全部保留 log-file、stdout/stderr、exit code、代码状态。

通过仓储核查全文 source_id=1209870320、来源URL、Q1/2021、PDF与Docling两文件；复算 file SHA256/size、pdf_sha256、source_fingerprint；remote_fingerprint 用实际 HEAD 字段与 raw 选择结果在底稿重放，不用内容 fingerprint 代替；核对 source meta 与 filing manifest。PDF 文本提取加页面渲染检查报告名、完整合并资产负债表、2021-03-31、股本/现金/借款行，不进行估值或财务数字汇总。首次 baseline 快照用 pypdfium2，环境无 Poppler，已记录提取器。

## 风险分类与最终交付

- 本轮修复：同日形态漏选和输入顺序不稳定。
- later approved validation：全文实际表格覆盖、公开 overwrite 及幂等性、manifest/fingerprint 审核，由本轮主 Agent 完成。
- 后续 owner：投资 workflow 主 Agent 独立审核后才可更新投资 workspace。本轮不声明 G1 数据审核通过。
- 当前范围外且明确保留：跨公告日期和不同修订级别按原有版本优先级；标题不能证明任意财报完整性，不新增自动表格审查。
- 外部源可用性：真实命令失败则留存证据并报告未通过，不能伪称公司未披露。
- 用户约束：不自动 commit/push/PR，因此不宣称 Gateflow draft-PR-pass/final-closeout-pass；交付本地审核完成状态和后续入口。

最终报告：根因、改动、测试命令与结果、精确隔离公开 CLI、四层证据路径、差异/例外、风险和 next entry point。
