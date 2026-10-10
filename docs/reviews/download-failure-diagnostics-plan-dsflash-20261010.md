# 下载失败诊断计划：独立 plan review（ds-flash 路）

RUNTIME/PROVIDER/MODEL: codex/ds-flash/gpt-6.1-sol
CANARY=ds-flash-fc9a6574

- Reviewer：dfdiag-plan-review-dsflash-20261010-01
- Review timestamp（本轮系统时钟）：2026-10-10 12:14:06 +08:00（2026-10-10T04:14:07Z）
- Reviewed target：`docs/gateflow/download-failure-diagnostics-plan-20261010.md`
- Plan SHA256：`e12f2f475bbc18d9c6d111a885882f54374d23e3769190cd3f4a31e2468218ca`（读取时核验一致）
- 冻结 HEAD：`c65c2aa28fae9c47ad947783d63f7559db7768c4`（核验一致）；Branch：`fix/download-failure-diagnostics-20261010`（核验一致）
- Goal（binding scope）：`docs/gateflow/download-failure-diagnostics-goal-20261010.md`
- 既有证据：`workspace/tmp/download-failure-diagnostics-20261010/old-evidence-owner-read.json`（record_sha256 `6d42a496a0fd4bbfce4a320025e77fa92758098c380ba51513a689527f15fce7`，source_count=45，8 项 published_meta=missing）
- 结论：**pass-with-risks**（Finding 1 须在 implementation 前由总控裁决；其余核验范围内 code-generation-ready）

## 1. Reviewed Target And Scope

本轮独立 review 的对象是上述 plan artifact，审查视角为用户指定的：最小性、goal alignment、契约/字段 owner、全失败/部分失败/取消/整体中止/协议错误、长期有界 LLM 与全量 operator 界限、测试足够且范围真实、slice 数量与机械拆分、schema 与部署验证；并重点核验 strict reason 的所有 workflow 分支、取消前缀守恒、constructor 迁移范围。核验依据为：

- `AGENTS.md`、goal artifact、plan artifact、既有证据 JSON；
- 固定 HEAD 上的真实生产代码与测试（只读）；
- 一次离线反例：在 fresh 临时目录对固定 CLI 执行 `download --rebuild`（不触网、不触碰生产来源），验证 plan 测试 8 的装配前提。

本轮未：修改任何代码/文档（只写本 artifact）、执行生产仓储查询、下载或恢复、读取另一路 review 报告、派发子 Agent、fix/commit/push/PR。

当前 `git status --short` 有 4 个未提交文件：`download-failure-diagnostics-goal-20261010.md`、`download-failure-diagnostics-old-evidence-20261010.json`、`download-failure-diagnostics-plan-20261010.md`、`download-failure-diagnostics-state-20261010.md`。按任务输入，goal/state/证据属总控、plan 属计划 Agent，ownership 已由总控确认无冲突；本 reviewer 只记录事实，不裁决。

## 2. Assumptions Tested

| # | plan 关键假设 | 直接证据 | 结论 |
| --- | --- | --- | --- |
| 1 | CN/HK workflow 的每个 FAILED/SKIPPED 行都提供 `reason_code` 与 `reason_message`，adapter 严格化不会失败 | `cn_download_filing_workflow.py:203-206`（failed）、`:219-222` / `:437-440`（skipped，reason=integrity_complete）；`:259-277`、`:345-351`（failed，`project_cn_filing_failure` 结果）；`_build_filing_result`（`:834-858`）参数类型 `reason_code: str, reason_message: str` 并复制 `skip_reason = reason_code`；`cn_download_workflow.py:378-382`（integrity abort failed）、`:405-410`（单候选异常 failed）；`cn_download_rebuild.py:217-252`、`:386-427`（CN rebuild failed 均带 reason）；`hk_download_rebuild.py:85-166`（HK rebuild 的 failed/skipped 均补 reason） | 成立；strict 读取在全部生产分支有上游供给 |
| 2 | 删除 `skip_reason` fallback 不破坏生产语义 | `skipped` 的生产来源只有 integrity_complete（2 处）与 period_metadata_current（HK rebuild），且 `skip_reason` 是 `reason_code` 的副本（`:858`） | 成立；现有测试 fixture 需同步补 `reason_message`（在允许测试名单内） |
| 3 | 取消路径不丢已处理前缀 | `cn_pipeline.py:1502` 已有 `replace(summary, terminal_disposition=CANCELLED)`；`ingestion_runtime.py:6352-6379` 已有取消收口；typed `FinsDownloadResultSummary.__post_init__` 允许 CANCELLED 覆盖且保留 rows | 成立；plan 迁移为 typed 层 replace 与现状语义一致 |
| 4 | 完整 typed rows owner 已存在且不丢数据 | `download_contract.py:412-509`（`document_rows` 完整、计数守恒、`omitted_count` property 恒 0）、`:511-558`（`from_document_rows` 派生 counts/terminal） | 成立；无需新增持久化即可取得完整失败 |
| 5 | constructor 迁移范围收敛 | 生产构造点全部在 `ingestion_runtime.py`（`_direct_result_event`、`_observation_failure_result`、`_observation_cancelled_result`、`_mark_observation_failed`）；读取点 `service/fins_wait_adapter.py:519-626`、`cli/output.py:253/408-411` 都走 `.download`；`dataclasses.replace(..., download=...)` 出现在 `tests/service/test_fins_wait_adapter.py:524`、`tests/fins/test_fins_ingestion_runtime.py:6325` | 成立；生产文件仅需 plan 已列 5 个，测试迁移文件都在允许名单 |
| 6 | LLM wait 保持有界、durable 不变 | `service/fins_wait_adapter.py:519-624` 只序列化 `result.download.to_json_value()`；`FinsDownloadPublicSummary` 强制 `<=10` rows（`direct_events.py:458`）；durable 走 `to_json_summary`（`download_contract.py:643-649`） | 成立；plan 的 bounded/full 双通道边界与代码一致 |
| 7 | 预算常量同源可与现状等价 | `ingestion_runtime.py:203` `_MAX_SUMMARY_JSON_CHARS=4096`；download durable/public uncertain 调用点 `:4978-5028`、`:6060`、`:6857`、`:8868` 均属下载路径；`direct_events.py:29-30` 已有公共 row/240 常量 | 成立；新增 `FINS_DOWNLOAD_SUMMARY_MAX_JSON_CHARS` 值相同，无 schema/行为变化 |
| 8 | 测试 8（固定 CLI 空库 rebuild）前提成立 | 离线实测：fresh base + `--ticker 0700 --start 2018-01-01 --end 2026-10-10 --rebuild`，1.6 秒完成、外层 returncode=0、stdout `Fins summary: ... start="2018-01-01" ... rebuild=true discovered=0 ...`、stderr 空；代码上 rebuild 在 `cn_download_workflow.py:169-227` 于 discovery/resolve_company 之前 return；空目录下 `_list_external_identities` 返回空（`_fs_identity.py:361-400`）、`_inspect_source_kind_unguarded` 对缺失根返回空 inspection（`_fs_source_integrity.py:213-243`） | 成立（新诊断行待实现后由该测试验证） |
| 9 | 全失败 / 部分失败 / 整体中止 / 协议错误语义 | `_produce_direct_download`（`:4367-4432`）全失败→FAILURE+whole failure、部分失败→SUCCESS+partial_failure；`FinsSourceDownloadAdapterFailure`（`:613-648`）→persisted_summary 前缀结果；validated stream 协议错误保持原异常（`direct_events.py` validated stream） | 成立；plan §3.5 表格与代码路径一致 |
| 10 | “SEC 现有 adapter 原因保真” | `sec_pipeline.py:1933-1973` 对 SKIPPED/REJECTED/FAILED 一律 `reason_message=_sec_safe_reason_message(...)`（`:2092-2114` 为通用文案），而 SEC workflow 提供具体 `reason_message`（如 `sec_download_filing_workflow.py:318-322` 的 `exc.safe_message`、`:604-621` 的 failed 文件摘要） | **不成立（证伪）**，见 Finding 1 |

## 3. Findings

### 1-未修复-中-SEC 投影仍在 adapter 层重写 reason_message，plan 的“SEC 原因保真/同源”声明与代码事实冲突

- **位置**：plan §3.4“Adapter 与 CLI 的精确变更”（生产文件只列 `cn_pipeline.py`）、§5.1 测试 3“SEC 现有 adapter 原因保真，新增公共能力不只对 0700 / CN 生效”、§8 goal alignment 表“原因和来源身份、日期/覆盖同源；strict adapter、shared row projection、完整诊断 null；测试 2/3”。
- **问题类型**：契约缺失 / 目标-验证不一致（同源承诺超出实际修复范围且与代码事实相反）。
- **当前写法**：plan 只把 `cn_pipeline._project_cn_document_row` 的 FAILED/SKIPPED 原因改为严格原样投影，并在测试 3 声称 SEC 现有 adapter 原因保真、把“同源”对齐到测试 2/3（测试 3 覆盖 SEC）。
- **反例/失败场景**：
  1. 实现者按测试 3 字面断言 “SEC typed row 的 reason_message 与 SEC workflow 提供的具体原因一致” → 断言失败；
  2. 实现者为让断言通过而修改 `dayu/fins/pipelines/sec_pipeline.py`（不在 plan 允许文件内），触发 plan 自身的“名单外生产改动停止报总控”条件，浪费一轮；
  3. 实现者弱化断言后交付：SEC 下载经新 CLI diagnostics 输出的 `reason_message` 仍是 `"SEC 来源未能完成该文档"`，operator 拿不到 workflow 已有的“请求超时/连接失败/文件下载失败”等具体安全原因，与 goal 的成功信号“真实安全失败原因”在 SEC 上不一致。
- **为什么有问题**：语义 owner 是 adapter 投影边界（与 CN 完全同构：`reason_code or fallback` + 通用 `reason_message`）。plan 一边把 CN 定为唯一已证实缺陷并在该处修复，一边把 SEC 声明为“已保真”，两者不能同时成立；同时把“同源”成功信号绑定到覆盖 SEC 的测试上，会使验证事实与代码事实冲突。
- **直接证据**：
  - `dayu/fins/pipelines/sec_pipeline.py:1933-1947`（SKIPPED：`reason_message=_sec_safe_reason_message(disposition)`）、`:1951-1973`（REJECTED/FAILED 同样替换）；
  - `dayu/fins/pipelines/sec_pipeline.py:2092-2114`（`_sec_safe_reason_message` 返回固定文案）；
  - `dayu/fins/pipelines/sec_download_filing_workflow.py:318-322`（provider 失败行带 `reason_message=exc.safe_message`）、`:604-621`（文件失败行带 `summarize_failed_download_file_reasons(...)`）——上游有具体原因，被 adapter 丢弃；
  - CN 对照：`cn_pipeline.py:1566-1585` 是同一模式（本次修复点）；
  - SEC 若做对称 strict 化并非纯文本替换：SEC workflow 多个 skipped 行只有 `skip_reason`/`reason_code` 而无 `reason_message`（`sec_download_filing_workflow.py:256-261`、`:283-287`、`:464-468`、`:541-545`、`:653-659`），范围会更大。
- **影响**：实现 Agent 跑偏（扩范围或弱化断言）/ 验证不可按 plan 声称验收 / 新诊断协议对不同来源语义不一致（CN 保真、SEC 通用）/ 未修复项被“原因保真”声明掩盖。
- **建议改法和验证点**（二选一，推荐 A）：
  - A（收窄，符合最小性与“不扩大修复”）：plan 明确 “SEC reason_message 同源不在本 slice，属 later work unit”；测试 3 改为断言 (i) SEC `reason_category` 保真（`reason_code` 未被替换）、(ii) SEC typed rows 原样进入完整 diagnostics（完整性与身份断言），不再声称 `reason_message` 保真；§8 alignment 表把“同源”范围收窄为 CN/HK。验证点：SEC 现有 `test_sec_pipeline_download*.py` 断言保持通过，且不出现 SEC 扩范围改动。
  - B（对称修复）：把 `dayu/fins/pipelines/sec_pipeline.py` 纳入允许文件，并同步给 SEC workflow 缺失 `reason_message` 的 skipped 分支补原因；需重新论证 slice 范围与 fixture 迁移。
- **修复风险（低/中/高）**：低（选项 A：只改 plan 文本与测试断言）/ 中（选项 B：扩大生产修改与 fixture 迁移）。
- **严重程度（低/中/高/严重）**：中。
- **Status**：accepted-candidate（证据直接、可由总控裁决；选项 A 不扩大修复范围）。

## 4. Open Questions

1. plan §6/§9 将旧 8 项 published metadata 的实时只读核查记为“未执行/尚未独立核验”，但本轮输入与既有证据文件显示总控已通过公开 storage repository（`create_directories=False`）完成核查：8 项均 missing、来源 45、record_sha256 已产出。用户已裁决该更新由总控处理、不作为 scope blocker；需总控在 plan/任务输入中刷新引用，避免 implementation 按旧表述重复生产查询（明确禁止）或在完成报告中漏报已核验事实。
2. plan §3.2 要求“下载终态（包括启动前失败、prepare 取消）由 runtime 明确提供 request-scoped typed 空结果”，但 `_mark_observation_failed`（`ingestion_runtime.py:7486-7512`，DOWNLOAD observation activation failure 路径）构造私有 `record.result` 时未提供下载结果，且该 result 不经 `FinsEvent.__post_init__` 约束。现状无行为回归（wait adapter 走 `error_message`/`details`），建议 implementation 明确该路径是否用 `record.context.download_request` 派生 typed 空结果，或显式声明私有 record 不受新约束。
3. plan §3.2 新增 `FinsEvent.__post_init__` 的“DOWNLOAD RESULT 必有 download_result / 非 DOWNLOAD 不得携带”owner 约束，但 §5.1 未明确其正负例断言的归属。建议在测试 1 显式补两条负例（缺 `download_result` 的 DOWNLOAD RESULT 被拒、非 DOWNLOAD 携带被拒），避免约束只由 fixture 迁移间接证明。
4. plan §5.1 测试 2 中“skip 的 integrity_complete / period_metadata_mismatch 原因也不泛化”的表述与代码事实有出入：`period_metadata_mismatch` 是 failed 分支（`cn_download_filing_workflow.py:203-206`），不是 skip。建议测试用例设计分别覆盖 skip 与 failed 两条链，避免误造成 skip fixture。
5. plan 测试 8 断言“唯一可解析新诊断行”，实现后 stdout 会同时存在现有 `Fins summary:`/`Fins document:` 行（离线 probe 已确认现状行形态）。建议测试以固定前缀 `Fins download diagnostics:` 解析，避免“唯一行”歧义。

## 5. Residual Risks

| 风险 / 未覆盖项 | 分类 | Owner / destination 与说明 |
| --- | --- | --- |
| FAILURE/CANCELLED 时诊断走 stderr，调用方若沿用“只保存 stdout”的旧习惯仍会丢诊断 | requiring explicit user decision | 调用方巡检线；plan §7 已写明两通道分别 capture，goal 已接受“捕获标准流即可保存”。旧运行恰为 SUCCESS+partial_failure（诊断在 stdout），新运行的全失败场景必须捕获 stderr |
| >10 的 skipped/downloaded 候选身份仍只以计数+bounded 前 10 行可见 | assigned to later work unit（如需） | 调用方巡检线；goal binding scope 只承诺完整失败诊断，未承诺完整 skip/downloaded 身份 |
| 旧 8 项原因/日期不可由现有证据恢复（metadata missing） | fixed in evidence（已分类） | 总控 evidence assessment；任何新观测须巡检线先确认范围，不得由 implementation 发起 |
| SEC `reason_message` 通用文案（若 Finding 1 选 A） | assigned to later work unit | 总控；如需同源则另开范围（含 SEC workflow skip reason_message 补齐） |
| 无持久化：未捕获终态、崩溃/SIGKILL、提前关闭流不可追回 | requiring explicit user decision | 用户/总控；goal 已接受本限制，不得由本 slice 扩成历史诊断仓储 |
| `dayu/fins/ingestion_runtime.py` 单文件覆盖率 >=80% 的基线风险（大文件、既有未覆盖路径） | implementation 验证项 | 实现者按 plan §5.2 先记录基线，不足时单列报总控，不据此修未授权业务 |
| 极端失败规模下 operator 端单行 JSON 长度与内存无单独压测 | accepted（plan 已声明不做分页/流式） | 后续按需压测；不增加框架 |
| `FinsResultSummary`（frozen dataclass）repr/eq 变更为包含完整 `download_result`，若故障路径打印 repr 可能把完整失败行带进日志 | 低风险观察项 | 实现时确认无 repr 通道进入 trace/日志；LLM 投影已隔离 |

## 6. Validation

本轮执行的只读/离线验证与结果：

1. 身份核验：`git rev-parse HEAD` = `c65c2aa28fae9c47ad947783d63f7559db7768c4`；`git branch --show-current` = `fix/download-failure-diagnostics-20261010`；`shasum -a 256 docs/gateflow/download-failure-diagnostics-plan-20261010.md` = `e12f2f475bbc18d9c6d111a885882f54374d23e3769190cd3f4a31e2468218ca`，均与冻结输入一致。
2. 本轮 canary 文件逐字读取：`ds-flash-fc9a6574`（非旧轮次）。
3. CN/HK 原因链：核对 `cn_pipeline.py`、`cn_download_filing_workflow.py`、`cn_download_workflow.py`、`cn_download_rebuild.py`、`hk_download_rebuild.py` 全部 FAILED/SKIPPED 产生点（见 §2 假设 1/2 证据）。
4. 取消与 constructor 迁移：核对 `ingestion_runtime.py` 的 `_emit_direct_result`/`_emit_claimed_direct_result`/`_direct_result_event`/`_emit_direct_cancelled_result`/`_observation_*` 构造点与测试 `replace(..., download=...)` 使用点（见 §2 假设 3/5 证据）。
5. LLM/durable 界限：核对 wait adapter、public 常量与 durable 预算调用点（见 §2 假设 6/7 证据）。
6. 离线反例（plan 测试 8 前提）：`mkdir` fresh base/cwd 后执行固定 `.venv/bin/dayu-cli download --base <fresh> --ticker 0700 --start 2018-01-01 --end 2026-10-10 --rebuild`，1.6 秒返回，外层 `EXIT=0`，stdout 含 `Fins summary: ... start="2018-01-01" ... rebuild=true discovered=0 downloaded=0 ...`，stderr 为空；确认不触达 discovery/resolve_company 与生产来源。
7. 部署装配抽查：`.venv/bin/dayu-cli` shebang 指向 `/Users/leo/workspace/dayu-agent-r/.venv/bin/python3.11`；`dayu_agent-0.1.4.dist-info/direct_url.json` 为 editable=true、URL 指向本仓库。

未执行/未覆盖（明确声明）：

- 未运行 pytest / pyright / coverage（plan 尚未实现，reviewer 不改代码；这些属 implementation gate）；
- 未执行任何生产仓储查询、download/overwrite/recovery/业务查询（用户明确禁止，旧 metadata 事实以既有证据文件为准）；
- 未读取另一路 review 报告、未派发子 Agent、未触碰 goal/plan/state 与任何其它代码/文档；
- SEC 路径仅静态核验，未运行 SEC 链的真实下载测试；
- 真实远端下载、部署漂移的最终确认不在本轮（需巡检线范围裁决），离线 probe 不代表真实下载通过。

## 7. Final Plan Review Conclusion

**pass-with-risks**。核验范围内，plan 是 code-generation-ready 的：单一行为 slice、五个生产文件的 owner 链清晰；strict reason 的所有生产 workflow 分支（CN 正常链、CN rebuild、HK rebuild、integrity abort、单候选异常、取消）均实际提供 `reason_code`/`reason_message`；取消前缀守恒与 constructor 迁移范围有直接代码证据支撑；测试覆盖 >10 失败、部分失败、全失败、取消、LLM 有界与固定 CLI 装配，且离线反例证明测试 8 前提成立。

唯一 material finding 是 Finding 1（SEC 声明不实，中）：**必须在 implementation 前由总控裁决**——按选项 A 收窄表述与测试 3 断言（不改生产范围），或按选项 B 扩大 slice 对 SEC 对称修复。该 finding 未修复前，测试 3 不可按字面执行，也可能诱发超允许文件改动；其余 plan 内容在本轮未发现需要阻塞的实质问题。

首尾身份复述（本轮核验）：plan SHA256 `e12f2f475bbc18d9c6d111a885882f54374d23e3769190cd3f4a31e2468218ca`；冻结 HEAD `c65c2aa28fae9c47ad947783d63f7559db7768c4`；CANARY=ds-flash-fc9a6574。本 review 不代表总控 gate 裁决。
