# 601225 年报全文 S1：implementation artifact

- Gate：implementation S1；S1 实施和真实验收执行已完成；本 owner 不判 gate pass，待总控实际退出复核与双路deepreview。
- Scope：已接受的唯一 S1，官方 FY 原文确认 → 正确年度选择 → 独立来源增量保留。
- 分支 / accepted plan HEAD：fix/601225-annual-fulltext / 7709c015db26c095f16cb77b5d383411cd76b652。
- 生产基线：7637bb0b4fbca212a4db0f4cfc09655e66516695。
- Binding plan SHA256：7a2acac94ca5592b5848a3ca78c77be55e2f79766f69f83db558f0017d615aaf；冻结计划、旧 review 和总控 state 未修改。

## 已落地 owner 行为

- facts：只读实际 PDF 首页；保留物理行，封闭 suffix，冲突/跨行摘要/未知标签安全失败。无披露年减一、三 ID 分支或 OCR。
- selection：统一标题准入；FY facts map 精确对应原 raw 来源，隐藏摘要排除，原文年分组；H1/Q/HK 原选择规则保留。
- acquisition：mandatory typed CN 本地原件/gate 输入；仅交付所选 FY 远端 prepared 与本地同版 witness；SHA/size/candidate 完全匹配。
- source：唯一原件投影与 exact snapshot read owner；source_url 精确从 snapshot.source_meta 读取，predicate 为原字符串非空，原样保留。provider/source_id 是身份，locator 不参与匹配。
- integrity：早期纯 inventory 拒绝检查，无 repair 授权；最终真实 selected 新 inventory 才裁决唯一 repair。
- publication：CN FY 同源 ID 复用，异源占槽按来源 hash 独立保留；A 同窗分类/meta，canonical JSON list；每次 COMPLETE 必须同 revision 实际 original full/year 证明；无 witness 读取 exact 原件，prepared 不替代证明。
- B：相同身份后的 staged metadata 再匹配；CN FY B COMPLETE rollback→fresh A，丢弃旧 payload 的三轮 churn；repair 成功后 fresh inventory 才开放 company/后续候选。
- scope：三种 integrity 类型 request abort，年度三个业务 reason 单 filing failed；取消原类型与 snapshot/lease/batch 关闭，保真实已提交前缀。
- HK：共享必填签名迁移，CN tuple 非空拒绝；新 handoff 为空，未改变 HK 业务选择/覆盖匹配。
- 依赖：pypdf>=6.1.3,<7；公共 lock 固定6.1.3；requirements.txt、storage schema/protocol/Fs、CLI/Service/Host/Engine/调用方未改。

## Changed files

- `docs/gateflow/601225-annual-fulltext-s1-implementation.md`

- `README.md`
- `constraints/lock-common-py311.txt`
- `dayu/fins/README.md`
- `dayu/fins/downloaders/cninfo_downloader.py`
- `dayu/fins/downloaders/hkexnews_downloader.py`
- `dayu/fins/pipelines/cn_annual_report_facts.py`
- `dayu/fins/pipelines/cn_annual_report_source.py`
- `dayu/fins/pipelines/cn_download_filing_workflow.py`
- `dayu/fins/pipelines/cn_download_identity.py`
- `dayu/fins/pipelines/cn_download_models.py`
- `dayu/fins/pipelines/cn_download_protocols.py`
- `dayu/fins/pipelines/cn_download_source_upsert.py`
- `dayu/fins/pipelines/cn_download_workflow.py`
- `dayu/fins/pipelines/cn_report_selection.py`
- `dayu/fins/storage/source_integrity.py`
- `docs/gateflow/601225-annual-fulltext-s1-checks.md`
- `pyproject.toml`
- `tests/README.md`
- `tests/fins/fixtures/cninfo_annual_fulltext/1204545056.pdf`
- `tests/fins/fixtures/cninfo_annual_fulltext/1205110621.pdf`
- `tests/fins/fixtures/cninfo_annual_fulltext/1206005283.pdf`
- `tests/fins/fixtures/cninfo_annual_fulltext/1207678369.pdf`
- `tests/fins/fixtures/cninfo_annual_fulltext/1209875597.pdf`
- `tests/fins/fixtures/cninfo_annual_fulltext/1209875598.pdf`
- `tests/fins/fixtures/cninfo_annual_fulltext/1213161682.pdf`
- `tests/fins/fixtures/cninfo_annual_fulltext/1213161683.pdf`
- `tests/fins/fixtures/cninfo_annual_fulltext/1216619553.pdf`
- `tests/fins/fixtures/cninfo_annual_fulltext/1219815158.pdf`
- `tests/fins/fixtures/cninfo_annual_fulltext/1223301988.pdf`
- `tests/fins/fixtures/cninfo_annual_fulltext/1223301999.pdf`
- `tests/fins/fixtures/cninfo_annual_fulltext/1225178190.pdf`
- `tests/fins/fixtures/cninfo_annual_fulltext/annual-raw.response.json`
- `tests/fins/fixtures/cninfo_annual_fulltext/provenance.json`
- `tests/fins/test_cn_annual_report_facts.py`
- `tests/fins/test_cn_annual_report_source.py`
- `tests/fins/test_cn_download_identity.py`
- `tests/fins/test_cn_download_models.py`
- `tests/fins/test_cn_download_runtime.py`
- `tests/fins/test_cn_download_workflow.py`
- `tests/fins/test_cn_pipeline.py`
- `tests/fins/test_cn_report_selection.py`
- `tests/fins/test_cninfo_downloader.py`
- `tests/fins/test_f5_workflow_rebuild.py`
- `tests/fins/test_hkexnews_downloader.py`
- `tests/fins/test_source_integrity_preflight.py`
- `utils/observe_601225_cli_http.py`
- `utils/validate_601225_annual_fulltext.py`

## owner checks

731 passed；12 个修改生产文件和全部修改/新增测试逐文件 >=80%；pyright 0 errors/0 warnings、pip check 0、pypdf 6.1.3。命令、exit、逐文件分母/百分比及历史失败见 [S1 checks](601225-annual-fulltext-s1-checks.md)。目录 source 收集与原模块 source 命令的 NumPy collection 失败均如实保存，无覆盖排除。

## P6 四次真实公开 CLI 与全部来源

独立根：`workspace/tmp/601225-cli-s1/`。所有 CLI 通过真实 `.venv/bin/dayu-cli` 裸 download、原 production runtime/Docling，未传 forms/overwrite/rebuild，未 mock 官方或转换。两个 first 实际等待至进程退出，两个 repeat 也实际退出；无在途进程被停止。

| 场景 | CLI PID | 原 exit / observer exit | 仓储全部源 | PDF attempt / wire GET | conversion started / completed | 全部 HTTP attempt / wire |
| --- | ---: | --- | ---: | --- | --- | --- |
| clean-01 | 69301 | 0 / 0 | 35 COMPLETE | 39 / 39 | 35 / 35 | 79 / 79 |
| clean-02 | 3795 | 0 / 0 | 35 COMPLETE | 4 / 4 | 0 / 0 | 44 / 44 |
| seeded-01 | 70559 | 0 / 0 | 37 COMPLETE | 37 / 37 | 35 / 35 | 77 / 77 |
| seeded-02 | 3796 | 0 / 0 | 37 COMPLETE | 2 / 2 | 0 / 0 | 42 / 42 |

每次实际 FY raw 均为冻结集合的19条，四个 bare 分类/分页完整；startup/finish/PID/seq/hooks 与 wire/transport闭合，未知PDF、observer捕获错误、意外redirect/retry均为零。first不是34基线，也不从summary10/omitted25推断全集：actual仓储完整35/37条已逐件读回，全部 primary JSON通过真实SDK模型/origin核验。public diagnostics均 success / exit0 / failure null / failed_documents []，failed/rejected/uncertain为0，terminal_disposition=succeeded。

### 原 argv 与原始输出

```json
["/Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli", "--base", "/Users/leo/workspace/dayu-agent-r/workspace/tmp/601225-cli-s1/clean", "--debug", "--log-file", "/Users/leo/workspace/dayu-agent-r/workspace/tmp/601225-cli-s1/clean-01.log", "download", "--ticker", "601225.SH", "--start", "2018-01-01", "--end", "2026-10-12"]
```
- clean-01：实际 exit 0；原 `run.json`、`stdout.txt`、`stderr.txt`、`http.jsonl`、4份 `query-*.response.bin` 及 `http-summary.json` 均在 `clean-01/`；实际 operator 日志 `clean-01.log`。`clean-01.verify.json` 另外以当前严格观察 helper 从原 HTTP 事件重新对账，补核原 raw totalRecordNum、四分类与版本/seq，保存全部资产而不覆盖原记录。

```json
["/Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli", "--base", "/Users/leo/workspace/dayu-agent-r/workspace/tmp/601225-cli-s1/clean", "--debug", "--log-file", "/Users/leo/workspace/dayu-agent-r/workspace/tmp/601225-cli-s1/clean-02.log", "download", "--ticker", "601225.SH", "--start", "2018-01-01", "--end", "2026-10-12"]
```
- clean-02：实际 exit 0；原 `run.json`、`stdout.txt`、`stderr.txt`、`http.jsonl`、4份 `query-*.response.bin` 及 `http-summary.json` 均在 `clean-02/`；实际 operator 日志 `clean-02.log`。`clean-02.verify.json` 另外以当前严格观察 helper 从原 HTTP 事件重新对账，补核原 raw totalRecordNum、四分类与版本/seq，保存全部资产而不覆盖原记录。

```json
["/Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli", "--base", "/Users/leo/workspace/dayu-agent-r/workspace/tmp/601225-cli-s1/seeded", "--debug", "--log-file", "/Users/leo/workspace/dayu-agent-r/workspace/tmp/601225-cli-s1/seeded-01.log", "download", "--ticker", "601225.SH", "--start", "2018-01-01", "--end", "2026-10-12"]
```
- seeded-01：实际 exit 0；原 `run.json`、`stdout.txt`、`stderr.txt`、`http.jsonl`、4份 `query-*.response.bin` 及 `http-summary.json` 均在 `seeded-01/`；实际 operator 日志 `seeded-01.log`。`seeded-01.verify.json` 另外以当前严格观察 helper 从原 HTTP 事件重新对账，补核原 raw totalRecordNum、四分类与版本/seq，保存全部资产而不覆盖原记录。

```json
["/Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli", "--base", "/Users/leo/workspace/dayu-agent-r/workspace/tmp/601225-cli-s1/seeded", "--debug", "--log-file", "/Users/leo/workspace/dayu-agent-r/workspace/tmp/601225-cli-s1/seeded-02.log", "download", "--ticker", "601225.SH", "--start", "2018-01-01", "--end", "2026-10-12"]
```
- seeded-02：实际 exit 0；原 `run.json`、`stdout.txt`、`stderr.txt`、`http.jsonl`、4份 `query-*.response.bin` 及 `http-summary.json` 均在 `seeded-02/`；实际 operator 日志 `seeded-02.log`。`seeded-02.verify.json` 另外以当前严格观察 helper 从原 HTTP 事件重新对账，补核原 raw totalRecordNum、四分类与版本/seq，保存全部资产而不覆盖原记录。

### repeat 精确允许 GET 与转换

- clean-02 actual attempt 与 wire 均精确为 `{1204545056:1,1209875597:1,1213161682:1,1223301999:1}`。
- seeded-02 actual attempt 与 wire 均精确为 `{1204545056:1,1209875597:1}`。
- 三目标和所有已持完整来源均0GET；两个repeat全部 conversion started/completed=0。两seed摘要也0GET。
- 四项是落选原件的必要只读 facts 获取，包含2017落选全文，未缓存、转换、发布或修复；没有把debug缺席当零GET。

### 三目标官方全文：实际原件/模型

实际 `.venv` 版本见 `environment-versions.json`：pypdf 6.1.3、docling 2.127.0、docling-core 2.96.0、pydantic 2.13.2、httpx 0.28.1、httpcore 1.0.9；安装后未再变更运行依赖。

| source_id | 实际 FY / kind | 官方 PDF SHA256（两套实际一致） | body.children / 非空texts |
| --- | --- | --- | --- |
| 1213161683 | 2021 / full | `41ec9bdf696e9e40a650288d042346ad03d05325a921e88fdc735efd5a7ccdb8` | 3222 / 3396 |
| 1219815158 | 2023 / full | `080827a40f33e613f876e60606daae838b83b715701c12a4f124712aa8bcbb7e` | 3906 / 3951 |
| 1223301988 | 2024 / full | `f3422819a11c1962ed4ae74d9a62e47a44635fc9e8b9d4de1e446824bbb91b86` | 3605 / 3695 |

所有目标均 active、ingest_complete、COMPLETE，meta.fiscal_year_source=source_document；实际 original由唯一显式角色投影，primary准确命中唯一声明Docling JSON。两个实际文件的size/SHA、meta.pdf_sha256、公开fingerprint helper复算、真实DoclingDocument.model_validate_json、非空pages/body/text及DocumentOrigin expected/actual全部相等。origin使用SDK create_file_hash与真实模型hex→Uint64规则；不把它当完整SHA审计签名，不创造derived_from。每个verify包含完整metadata、opaque revision、actual两SHA/size、两origin、content fingerprint和全部sources。

| 来源 | clean全文ID | seeded全文ID | 实际locator |
| --- | --- | --- | --- |
| 1213161683 | `fil_cn_465a3bb60a5b4314f4bf993c871bbc23f3b4d856` | `fil_cn_f5ddc6f56cfcab34720158d9e64b837889c3284b` | `http://static.cninfo.com.cn/finalpage/2022-04-28/1213161683.PDF` |
| 1219815158 | `fil_cn_f75b86b5f95835f81055f91927dc144866a3e686` | `fil_cn_f75b86b5f95835f81055f91927dc144866a3e686` | `http://static.cninfo.com.cn/finalpage/2024-04-26/1219815158.PDF` |
| 1223301988 | `fil_cn_aaacc5f8032608460b8d410e99b6ac742284f4d2` | `fil_cn_9d59e638bee6dc15f4ce52c900c1d043b71a9327` | `http://static.cninfo.com.cn/finalpage/2025-04-26/1223301988.PDF` |

### 真实摘要 seed 与逐字段保留

两份官方原件经生产create_docling_converter及当前conversion config实际转换后，经Fins batch/blob/source owner提交，未用模拟JSON。seed实际退出0，`seed.stdout.txt`记录两次 started/completed；`seed.verify.json`逐实际PDF确认summary、官方SHA、原seed财期ID、metadata/revision与真实model/origin。seed绕selection仅构造历史占槽输入，不替代发现网络证据。

| 摘要 source_id | 保留原ID | PDF SHA256 | 原JSON SHA256（first/repeat保持） |
| --- | --- | --- | --- |
| 1213161682 | `fil_cn_465a3bb60a5b4314f4bf993c871bbc23f3b4d856` | `a15100380ee1ae7930c612700d685aa18f9b02d794d92c4aa097cfaec8a029aa` | `f461e64755569b1eaa48c308e9afbc8fc0e7c72540694b92ba66d0004a9d4ee5` |
| 1223301999 | `fil_cn_aaacc5f8032608460b8d410e99b6ac742284f4d2` | `c6e5e1c9499c601b3cdd17cff87af9464ecf46afd3fa908d5a0e43113efd861f` | `62fad4eb8ff5d526c987987fbe6818adcee54cdad17b43dcfd7641985845cfd8` |

`seeded-first.compare.json`核两摘要原ID/meta/revision/PDF/JSON SHA全部不变，新全文分别取得独立ID；两个repeat compare逐全部已持来源核ID/meta/revision/两SHA与COMPLETE，不新增来源、不修改旧资产。三份compare均passed、differences=[]，三个实际命令exit0。

### 验收命令与失败保留

每条命令均先激活`.venv`；seed、四verify和三个compare的原argv/实际exit已汇总到`validation-commands.json`。checks命令/coverage见独立checks artifact。首次observer help实际CLI退出0但因无bare raw而observer辅助返回2；第一次clean启动因父目录不存在在spawn前失败，随后建独立根再正式执行，均未伪造CLI成功。普通实现/测试签名与夹具注入错误、NumPy coverage collection失败、utils导入修正等全部原日志仍在`workspace/tmp/601225-validation/`及会话执行记录，不删除或替换失败输出。正式四run、全部verify/compare没有外部网络/官方集合/SDK阻断。

- CLI执行期间仅扩大重复raw的提前拒绝范围（本次原19条无重复）及移除未使用旧常量、调整文档/测试/独立验收辅助；未改本次成功数据路径或真实Docling调用。原first响应与actual assets已完整核对，当前同版owner tests和最终checks另保留。
- observer当前正式模块具备仅本PID装载、grandchild sentinel不hook、原transport/Response.read返回、HTTP/1.1 wire send、pin/signature与完整性检查。first的原观察输出保留，最终verify用当前strict helper对同一原事件补充完整对账，不重复HTTP，不改业务事实。

## README 决定

根 README 只写最终用户年报增量保留与排障；Fins README 写 facts/source/publication 与两类错误作用域；tests README 写真实落地 fixture/owner/acquisition/HK 回归与独立实际验收方法。未改变分层、装配、入口参数或日志位置，dayu/README、Engine/Host/Config README 无触发。

## 残余风险与未完成项

| 项目 | Gateflow 类别 | owner / destination | 当前状态 |
| --- | --- | --- | --- |
| 代码、owner tests、类型/逐文件coverage、依赖、README | fixed in current slice | 实施 owner / 本 artifact、checks、总控 code review | 已实施并 checks 通过，未由总控验收 |
| 四次 bare CLI / actual Docling / wire对账 / 摘要保留 | fixed in current slice | 实施 owner、总控 / 独立 CLI 根与正式验收 | 四次实际exit0，全部verify/compare passed；待总控复核，不自判gatepass |
| 历史启动树/raw 缺失 | assigned to later work unit | 总控/取证维护者 / 独立历史可追溯任务 | 不补造历史全链 |
| OCR/未知首页布局、其它公司/公告、一般日期边界 | assigned to later work unit | Fins事实/日期维护者 / 独立相应任务 | 当前仅13官方首页确认；不足失败关闭 |
| 隐藏坏摘要、未知身份、旧错年自动恢复 | assigned to later work unit | Fins完整性维护者 / 独立历史完整性任务 | 本轮只安全失败、零该目标修复，不扩恢复 |
| 落选275页全文/摘要 repeat GET 成本 | assigned to later work unit | Fins维护者 / 后续性能任务 | 本轮按精确允许集合核对，不加缓存 |
| SDK origin 有损 Uint64、无 derived_from 的历史因果限制 | assigned to later work unit | Fins审计维护者 / 按需独立来源审计 | 本次核真实进度+两资产SHA/fingerprint/model/origin，不造schema |

- 尚未完成：总控实际退出/证据复核；后续双路 deepreview、finding裁决与commit/PR由总控负责。无当前实施/验收阻断。
- 本 owner 未 commit/push/PR/comment/issue，未派发、清理或终止其它 Agent/任务。
