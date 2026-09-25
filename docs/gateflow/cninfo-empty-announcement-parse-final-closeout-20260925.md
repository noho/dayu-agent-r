# Final Closeout：cninfo-empty-announcement-parse（000333 巨潮公告列表格式异常修复）

- Gate: `final closeout`（`draft-PR-pass` 后）
- Work unit: 000333 下载时巨潮公告列表格式异常（fixture-refresh-20260925 dayu-repair-prompt）
- 日期：2026-09-25
- 状态：**work unit completed**（待用户 merge draft PR #197）

## What changed（本 work unit）

1. `dayu/fins/downloaders/cninfo_downloader.py`：`_query_announcements` 响应解析改为显式四分支——
   缺 `announcements` key 维持协议失败（fail-closed）／ `null` = 空页（与 `[]` 同义）／ list 照旧／
   其它类型协议失败；模块 docstring 记录巨潮空结果编码事实。无 public contract / schema / 状态机变更。
2. `tests/fins/test_cninfo_downloader.py`：4 组回归测试（事故形态 FY 双公告 + H1/Q1/Q3 null、null 空页、
   缺 key、非 list 非 null）。
3. Docs artifacts：plan、plan review + re-review、S1 implementation、slice code review、aggregate deepreview、
   PR review、本 closeout（`docs/gateflow/cninfo-empty-announcement-parse-*`、`docs/reviews/*20260925*.md`）。
4. 环境处置（非代码，用户点名授权）：删除受管 workspace 中 Q1 2026 filing 目录内的工具残留
   `.claude/.cc-writes`（0 文件）；来源文件与元数据未动。

## 根因与直接证据（任务书交付项 1）

1. **代码缺陷（已修复）**：巨潮 `hisAnnouncement/query` 空结果以 `announcements: null` 编码（key 存在、
   值为 null）。两次独立取证（沿生产 `CninfoDiscoveryClient` 请求路径，脱敏记录响应特征）显示：
   FY 查询 `announcements`=list(2)/`totalRecordNum`=2，H1 查询 `announcements`=null/`totalRecordNum`=0，
   顶层 key 集一致。解析 owner 把非 list 一律判协议违规 → bare 请求 FY,H1,Q1,Q3 中 H1 空结果即整体 abort，
   与 2026-09-25 19:09:50 事故错误文案、路径完全一致（确定性复现）。
2. **运行环境阻塞（已处置）**：修复 1 后复验暴露第二根因——workspace 中 Q1 2026 filing
   （`fil_cn_f76e8bca…`）目录被 9/24 某 agent 会话残留 `.claude/.cc-writes`（0 文件）污染，
   storage owner 判 `unsafe_filesystem_entry`（`_fs_source_integrity.py` `_validate_physical_structure`：
   source 目录只允许 meta/identity/已声明普通文件），`classify_source_integrity_preflight` 抛
   `SourceIntegrityPreflightError(UNSAFE_PUBLICATION)`，被 producer 兜底投影成误导性“下载执行失败”
   （完整 traceback 取证在案）。删除残留后 inventory 7/7 恢复 complete。

## 实际改动文件与测试结果（任务书交付项 2）

- 改动文件：上述 1、2 共 2 个代码文件（+ docs artifacts）。
- `pytest tests/fins/test_cninfo_downloader.py -q`：58 passed。
- `pytest tests/fins -q`：2124 passed, 1 skipped；1 failed（`test_blob_read_projects_real_socket_io_error_without_private_locator`
  为沙箱禁 AF_UNIX bind 的环境伪失败，**非沙箱复跑通过**，与改动无交集）。
- `pyright dayu/fins/downloaders/cninfo_downloader.py tests/fins/test_cninfo_downloader.py`：0 errors, 0 warnings。

## 复验（任务书交付项 3）

命令（与事故同参，仅换新日志名，未传 `--forms/--overwrite/--rebuild`）：

```bash
/Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli \
  --base /Users/leo/workspace/portfolio-manager-v2/workspace \
  download --ticker 000333 --start 2025-01-01 --end 2025-03-31 \
  --log-file /Users/leo/workspace/portfolio-manager-v2/orch/workpapers/fixture-refresh-20260925/midea/download-recheck-final-20260925.log
```

- **退出码 0**；终态：`Fins succeeded … status="success"`；
  summary `discovered=1 downloaded=0 skipped=1 rejected=0 failed=0 omitted=0`。
- 文档行：`document_id="fil_cn_95d26c810c326725ece2cc478a6a4c012fe1c9ce" form_or_period="FY"
  filing_date="2025-03-28" disposition="skipped" reason_category="integrity_complete"`（本地 source 完整，
  跳过远端传输）。
- 新日志：`…/midea/download-recheck-final-20260925.log`（首次失败证据 `midea/download.log` 原样保留；
  另有诊断过程日志 `download-recheck-20260925.log` / `-debug-` / `-trace-`）。
- `Fins missing periods: "H1,Q1,Q3"`：既有 missing 语义（主源该 filing 窗口无此类报告）+ 业务事实，
  **可解释缺失**，非失败、非拒收、非数据缺失，不得为消除该行修改期间策略。

## 元数据核验（任务书交付项 4，逐项标注 meta 真源字段）

| 交付项 | 值 | 来源字段 |
|---|---|---|
| document_id | `fil_cn_95d26c810c326725ece2cc478a6a4c012fe1c9ce` | `meta.document_id` |
| meta.json 路径 | `/Users/leo/workspace/portfolio-manager-v2/workspace/portfolio/000333/filings/id-fc820675752844ea8aa8f07833b25650ac2c456520f5252042f383795ec50774/meta.json` | storage 布局 |
| revision | `7d79bbc27992444fb50380c122669116` | `meta._published_source_revision`（与 integrity inventory revision 一致） |
| source_fingerprint | `04a06af3afe93e76964c39de56f80bdfa68d6c994736f0329c63bdd7a345ded4` | `meta.source_fingerprint` |
| SHA 校验 | PDF 重算 `b17a9b9b…040ecd9` = `meta.pdf_sha256` = `meta.files[0].sha256`；docling 重算 `bf98154f…52dc5d` = `meta.files[1].sha256` —— **双文件一致** | `meta.pdf_sha256` / `meta.files[].sha256` 对账 `shasum -a 256` |
| 财务报表正文路径 | `…/id-fc820675…/fil_cn_95d26c810c326725ece2cc478a6a4c012fe1c9ce_docling.json`（CN 完成态 primary 指向 docling JSON） | `meta.primary_document` |
| ingest_complete | true | `meta.ingest_complete` |
| 身份核验 | ticker=000333、company=美的集团（`CNINFO:9900005965`）、form FY、fiscal_year=2024、filing_date=2025-03-28 ∈ [2025-01-01, 2025-03-31]、`source_id=1222951181`（巨潮“2024年年度报告”） | `meta.*` |

**跳过说明（任务书交付项 5）**：目标文档此前已由 Dayu 正式下载链路写入（`first_ingested_at=2026-09-23`），
本次 `integrity_complete` 核验后跳过。跳过本身不是恢复证据；恢复证据 = discovery/selection 走通
（`discovered=1`，候选来自巨潮实时响应解析）+ 上表全项核验一致。

## Docs updates

- `dayu/fins/README.md`：按其更新约束（不写实现细节）无需更新；`tests/README.md` 未定义约束且未新增测试层级，
  不机械同步；根 README / `dayu/README.md` 无用户可见变化。

## Finding status

| Review 环节 | findings | 状态 |
|---|---|---|
| plan review | 2（中：missing-periods 验收口径；低：元数据字段真源映射） | 均 accepted → plan 修复 → re-review `pass` |
| slice code review | 0 | pass |
| aggregate deepreview | 0 | pass |
| PR review | 0 | pass（记录于 `docs/reviews/pr-197-review-20260925-205425.md`） |

## Remaining risks / owners

| 风险 | 分类 / owner |
|---|---|
| storage 预检异常（如 `SourceIntegrityPreflightError`）被兜底投影为“下载执行失败”，掩盖真实原因 | requiring new issue / explicit user decision；owner：Dayu 维护方（本次排障实证代价） |
| 本验收为 skip 路径；全新 PDF+docling 落盘链路未在本窗口端到端演练 | assigned to later work unit（仅当需要下载演练时） |
| 其它 ticker/filing 目录可能同类工具残留污染 | assigned to later work unit（消费方 CMB/YUMC 下载排障时同口径处理） |
| 巨潮未来省略 `announcements` key 表达空结果 → 再次协议失败（fail-closed 设计使然） | 接受的残留边界 |
| `null` 与 `hasMore=true` 矛盾响应静默截断翻页（与 `[]` 同语义，实测未出现） | assigned to later work unit（仅当出现证据） |
| 仓库无 CI checks（`gh pr checks`：no checks reported） | requiring new issue / explicit user decision；owner：仓库维护方 |

## Draft PR / issue 关联状态

- Draft PR：https://github.com/noho/dayu-agent-r/pull/197（head `codex/upload-material-oracle` → `main`，
  按用户决策自混合分支直接开 PR，body 分节声明本 work unit 与 20 个捎带 commit 的边界）。
- Issue link status：本 work unit **非 GitHub issue**（来源为消费方 workpaper 任务书），无需 closing keyword；
  PR body 已声明。
- Issue closeout comment：不适用（非 issue）。

## Next entry point

1. 用户 merge PR #197 后：消费方 fixture-refresh 工作流继续（招商银行、百胜中国下载），同口径排障。
2. 建议开新 issue：storage 预检异常的 public 投影修复（`classification=execution` 兜底掩盖 typed 失败原因）。
3. 用户 merge 前如需对捎带 20 commit 重新评审，另开 review 任务。
