# WU-CLI-DOWNLOAD-02 Slice 3 Implementation（DL-F13）

## 1. Gate 边界

- Gate：Slice 3 implementation。
- 起点：branch `codex/download-oracle`，HEAD
  `9e037e3fb16eeaa14ceb185009a5ad16015a87aa`，worktree clean。
- 本 gate 只实现 accepted plan 的 DL-F13；未进入 code review、deepreview、真实 provider
  或真实 CLI evidence。
- 未修改 policy、Service / Host / Engine、storage schema、其它命令、观察 harness 或真实
  CLI；未 commit。

## 2. Preflight 与输入

实现前已完整读取并核对：

- `AGENTS.md`；
- `docs/gateflow/wu-cli-download-02-plan-20260810.md`，重点复核 §5.3、§6 Slice 3、§7、§8；
- goal confirmation artifact；
- Slice 2 implementation、code review adjudication、两份初审与两份复审 accepted artifacts；
- `docs/engine/design.md` 与 `docs/host/design.md`。

结论：问题动机成立。period identity、coverage、provider category 与 source meta 的语义 owner
均在 Fins；无需改变 Host / Engine 或 storage schema。

## 3. Consumer inventory

在任何编辑前重跑 accepted inventory：

- `CnReportCandidate` production constructor 仅位于 `cn_report_selection.py`；
- candidate identity production consumer 仅位于 Slice 3 allowlist 内的 selection、workflow、
  filing workflow 与 source upsert；
- `FinsDownloadDocumentResult` production constructor 为 CN 3 个、SEC 4 个、generic runtime
  2 个；
- `FinsDownloadPublicDocument` production constructor仅为 runtime public projection 1 个；
- `build_cn_filing_ids(...)` 的 candidate download 调用点仅为两个 allowed workflow；upload
  路径不消费 candidate，不属于本次迁移；
- Service wait adapter 只机械调用 `to_json_value()`，无需 production 修改。

未发现 allowlist 外真实 production constructor/consumer，因此继续实现；未加入 default、
compatibility property、wrapper 或 fallback。

## 4. 实现结果

### 4.1 Provider discovery 与分类 owner

- HKEX Q1～Q4 共用一个全 results category spec：
  `t1code=10000,t2Gcode=3,t2code=-2`；删除 `13600` production 语义。
- category spec 继续去重，四个 quarter 只触发一次全 results query。
- 新分类器先只读 category 判定 report/results family；family 确定后才共同解释 category 与
  title 的期间事实。
- report 与 results 对共享 half/full-year token 分别解释为 H1/FY report 或 Q2/Q4 result；
  family/期间歧义均返回 `None`。
- 同一 HK source ID 先按 URL、category、title、filing date、language 核心事实去重；事实
  冲突 fail closed。

总控中途指出的两个 contract 风险已在继续 downstream 前修正：report family marker 不再
使用裸 `INTERIM`，且 family 内期间事实不再只读 title。对应正负 owner tests 已补齐。

### 4.2 Candidate identity 与 coverage

- 新增 frozen/slots 必填 `CnReportPeriodProjection(identity_period, covered_periods)`；校验非空、
  canonical order、无重复且包含 identity。
- 删除 `CnReportCandidate.fiscal_period`，不保留 property；candidate 只持有
  `period_projection`。
- CNInfo、HK annual/interim report 使用 singleton；HK Q2 使用 `(H1,Q2)`，Q4 使用
  `(FY,Q4)`，Q1/Q3 使用 singleton。
- selection grouping、排序、窗口、business limit、missing、form、report kind 与 ID 均只消费
  identity；coverage 不满足 baseline missing，也不增加 source/manifest 数量。

### 4.3 Source、workflow、rebuild 与 public projection

- source meta 的 `form_type`、`fiscal_period`、`report_kind` 同源于 identity，并新增必填
  `covered_fiscal_periods`。
- ordinary、skip、failed 与 rebuild workflow rows 均携带 coverage。
- rebuild 对 fresh source meta coverage 做 required list、成员、非空、去重、canonical order、
  identity inclusion 严格校验；缺失或畸形 fail closed。
- `FinsDownloadDocumentResult` 与 `FinsDownloadPublicDocument` 新增无默认必填 coverage；SEC
  四个和 generic runtime 两个 constructor 显式传 `()`。
- CN adapter 严格读取 required array；runtime、public serializer、Service wait 与 CLI row
  原样投影，不从 form/title/字符串重算。

### 4.4 README

在行为与 focused tests 稳定后，先读取各 README 的内部更新边界，再更新：

- 根 `README.md`：用户可见 mode 互斥、CN/HK bare policy、baseline missing 与 CLI coverage
  行；
- `dayu/fins/README.md`：全 results discovery、category-first、identity/coverage owner 与
  public contract；
- `tests/README.md`：当前 download owner matrix 与 coverage 测试事实。

未更新 `dayu/README.md`、Host/Engine README 或 design doc，因为分层与装配边界未变化。

## 5. 验证

### 5.1 Accepted focused union

最终在 `.venv` 中执行 plan §7.1 的完整 13-file union：

- `1065 passed`；
- 仅有 3 条既有 edgartools deprecation warning。

### 5.2 实际修改 production 文件整文件 line coverage

| Production file | Coverage |
|---|---:|
| `dayu/cli/output.py` | 81% |
| `dayu/fins/direct_events.py` | 87% |
| `dayu/fins/download_contract.py` | 88% |
| `dayu/fins/downloaders/hkexnews_downloader.py` | 85% |
| `dayu/fins/ingestion_runtime.py` | 90% |
| `dayu/fins/pipelines/cn_download_filing_workflow.py` | 86% |
| `dayu/fins/pipelines/cn_download_models.py` | 97% |
| `dayu/fins/pipelines/cn_download_rebuild.py` | 86% |
| `dayu/fins/pipelines/cn_download_source_upsert.py` | 86% |
| `dayu/fins/pipelines/cn_download_workflow.py` | 93% |
| `dayu/fins/pipelines/cn_pipeline.py` | 90% |
| `dayu/fins/pipelines/cn_report_selection.py` | 91% |
| `dayu/fins/pipelines/sec_pipeline.py` | 82% |

所有实际修改 production 文件均达到 `>=80%`；未使用 omit、pragma、changed-lines 或阈值
豁免。

### 5.3 Static 与 contract guards

- changed-files Ruff check：通过；
- changed-files Ruff format check：通过，23 个 Python 文件均已格式化；
- 13 个 production module `compileall`：通过；
- 全量 `pyright`：通过，`0 errors, 0 warnings, 0 informations`，显式进程状态
  `PYRIGHT_EXIT=0`；
- `git diff --check`：通过；
- old contract guard：无 `TargetPeriodResolution`、`resolve_target_periods`、
  `CnReportQuery.target_periods` 或 candidate compatibility `.fiscal_period`；
- HK category guard：新增 production 语义无 `13600` 或旧 quarterly constant；
- identity guard：两个 candidate download ID call site 均只传
  `period_projection.identity_period`，没有遍历 coverage；
- required-field guard：公共 coverage 无默认；SEC/generic 的空 tuple 均为显式 constructor
  参数；rebuild/CN adapter 不用 `.get(default)` 读取 coverage；
- public JSON guard：CN/HK 与 SEC summary 经真实 `to_json_value()`、`json.dumps`、
  `json.loads` strict round-trip；每个 `documents[]` 均有 JSON array coverage；wait adapter 与
  CLI row owner tests 通过；
- README boundary guard：三份 README 未写 implementation/review/WU 历史。

特例 guard 口径在总控反馈后校正：禁止的是本次新增分类/分支中的 ticker、title、date、URL
特例，而不是删除 production 既有的自解释 ticker docstring 示例。已恢复
`hkexnews_downloader.py` 原有 `0700/00700/700.HK` 输入格式示例；对新增 semantic diff 与分类
逻辑检查后，不含 ticker/title/date/URL 特例。

首次 artifact 收口时曾在未取得可靠全量 pyright 退出状态的情况下误记为 pass；总控独立
复核发现 `tests/service/test_fins_wait_adapter.py` 对 `JsonValue` 的嵌套访问未收窄。随后在测试
中逐层以 `isinstance` 收窄 download mapping、documents list、document mapping 与 coverage
list，未使用 `Any`、cast、ignore 或默认值。修正后依次通过精确测试、该测试文件 pyright、
全量 pyright `PYRIGHT_EXIT=0`、完整 13-file focused union（1065 passed）、受影响 Ruff/format
与 `git diff --check`；本 artifact 仅记录修正后的最终状态。

## 6. Residual risks 与停点

- 按 gate 约束未运行真实 provider、真实 CLI 或 post-fix evidence；provider 行为只由严格、
  无网络 raw HTTP fixtures 验证。
- 未执行 commit；worktree 保留本 Slice implementation、tests、README 与本 artifact。
- 下一入口是 Slice 3 code review；本 gate 在该入口前停止，不自行进入 review。
