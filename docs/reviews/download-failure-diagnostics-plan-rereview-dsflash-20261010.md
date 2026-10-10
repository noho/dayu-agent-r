RUNTIME/PROVIDER/MODEL: codex/ds-flash/gpt-6.1-sol（runner 配置/自报名；物理后端型号未独立证明，不以自报或 Node 元数据作身份证据）
CANARY=ds-flash-7e934412

# 下载失败诊断计划 re-review：ds-flash 路

- Reviewer：dfdiag-plan-rereview-dsflash-20261010-01
- Review timestamp（本轮系统时钟）：2026-10-10 12:45:46 +0800（2026-10-10T04:45:46Z）
- Reviewed target：`docs/gateflow/download-failure-diagnostics-plan-20261010.md`（修订后 plan）
- Plan SHA256：`7de77259a5ca545ef959376471f7d902c48fd31dece024b3ce04468b7e18c9f9`（读取时实测一致）
- 冻结 branch / HEAD：`fix/download-failure-diagnostics-20261010` / `c65c2aa28fae9c47ad947783d63f7559db7768c4`（实测一致）
- 共同输入：AGENTS.md、goal、state、修订 plan、plan-fix、plan-adjudication、old-evidence JSON、本路初始 review（dsflash）
- 边界：未读取另一路（mimo）初始或复审报告；未读取调用方 workflow/gate/审核包/范式；未查询生产 storage、未联网、未 download/overwrite/recovery；未派发子 Agent；未改代码或 plan；只新增本文件
- 结论：**P1—P4 全部判定已解决（文档修订层面）；无新增实质 finding；计划在冻结 scope 内仍 code-generation-ready（re-review pass）**。本报告不代表总控 gate 裁决，不宣布任何 gate pass；P1—P4 的“已修复”只指计划文本修订，代码与测试尚未实现，不能当作实际验证。

## 1. 冻结身份与 preflight

- `git branch --show-current` = `fix/download-failure-diagnostics-20261010`；`git rev-parse HEAD` = `c65c2aa2...`；均与冻结输入一致。
- `shasum -a 256` 修订 plan = `7de77259...`，与交接 hash 一致；读取全程 HEAD 未漂移。
- `git status --short` 仅本 unit 已知 owned 的未跟踪文档（goal/state/old-evidence/plan/plan-adjudication/plan-fix 与两路 review）；tracked 生产、测试、README 无差异。与交接“本次没有生产代码改动”一致。
- 本路初始 review 基于同一 HEAD，本次 fix 仅改 Markdown，未触生产代码。其 assumptions 1—7（CN/HK 全部 FAILED/SKIPPED 生产分支供给 `reason_code`/`reason_message`、取消前缀守恒、constructor 迁移范围收敛、LLM/durable 有界、固定 CLI 离线 rebuild 装配前提等）继续有效，本报告直接复用该同 HEAD 证据，只对修订之处与必要 owner 路径做限定复核，并独立验证 P1—P4。

## 2. P1—P4 逐 finding 最终状态

### P1-已修复-低-删除 SEC 原因保真不实声明，收窄为 CN/HK 范围

- **裁决要求**（adjudication）：删除“SEC 现有 adapter 原因保真”及跨来源原因修复承诺；通用完整接口保留既有 typed rows；SEC 只验证完整性/身份/既有安全投影不变；不修改 SEC 生产代码；CN/HK 真实安全原因保真仍必达。
- **计划修订落点**：§1（L24）、§2 SEC 行（L40）、§5.1 测试 3（L201）、§8（L305）、§9 风险表（L328）、§4 允许文件（L171-177，五个生产文件不含任何 SEC 文件）。
- **独立证据**：SEC adapter 确实以通用文案替换上游原因——`sec_pipeline.py` 的 SKIPPED/REJECTED/FAILED 三个分支均走 `_sec_safe_reason_message(...)`（约 L1933-1973 调用、L2092-2114 定义，返回值固定为“该文档按下载策略跳过/该文档未通过来源筛选规则/SEC 来源未能完成该文档”）；上游 `sec_download_filing_workflow.py` 实际提供 `reason_code`/`reason_message`（L314-325 provider 失败、L614-623 file_download_failed）。CN/HK 的严格投影目标是 `cn_pipeline._project_cn_document_row`（L1506-1591），当前仍为 `reason_code or "cn_document_failed"` + 通用文案（L1576/L1587-1588），正是计划要替换的不保真点。
- **最终状态**：resolved（文档级）。旧肯定句已从 §1/§2/§5.1/§8/§9 全部消失；计划只对 CN/HK 承诺真实安全原因保真，SEC 仅断言身份/顺序/字段机械进入 diagnostics 且既有安全文案与分类保持原值。
- **残余**：SEC 原因治理显式列为后续 work unit（需另定范围），未扩大本轮生产改动；P1 的“跨来源修复”扩范围请求被 rejected-with-reason 后，计划遵守了该裁决。

### P2-已修复-中-下载 RESULT 一律携带 typed 结果，activation 收口复用唯一 helper

- **裁决要求**：所有合法 download terminal 由拥有 request 的 runtime 提供 typed `download_result`；`None` 只用于无下载结果的非下载合法结果；诊断方法遇 `None` 抛 `ValueError`；不新增 operation 字段/wrapper/下游空结果 fallback；`_mark_observation_failed` 复用 `_observation_failure_result`，删除冗余 `error_kind` 参数；原异常同对象保留；测试覆盖 executor submit 失败、prepare 取消、adapter 启动前失败及非下载拒绝。
- **计划修订落点**：§3.2（L70 唯一下载输入与删除兼容 constructor；L82 public projection 归属；L88 FinsEvent owner 约束）、§3.3（L99 `download_result is None` 抛 `ValueError`）、§3.5（L143-147 exact 改法；L149-159 终态表）、§5.1 测试 3/4（L201-203）。
- **独立证据（固定 HEAD 逐点核对）**：
  - `_mark_observation_failed` 仅有 activation 一处调用（L4009），实参为 `FinsErrorKind.EXECUTION`，`except` 后为裸 `raise`（L4011-4014）——原异常同对象传播成立；当前函数体用裸 `FinsResultSummary(...)` 构造、无 download（L7508-7521），与计划所述缺陷一致；其函数签名确带 `error_kind` 参数（L7489），复用 helper 后确可删除。
  - `_observation_failure_result`（L7386-7435）已持有 `download_request` 且固定 EXECUTION；当前以 `download=_public_download_summary(_empty_download_summary_from_request(...FAILED))` 包装（L7418-7427），改为直接传 typed 空 FAILED 并删包装属 owner 内最小改法，`failure` 安全投影保持（L7428-7434）。`_observation_cancelled_result`（L7441-7480）同构，改 typed 空 CANCELLED、failure=None。
  - `_empty_download_summary_from_request`（L6877-6913）产出 request-scoped typed summary（source/ticker/filters 来自原 request，counts 全零、rows=()）；typed 层允许“零候选 + FAILED/CANCELLED”终态覆盖（`download_contract.py` L433-508 `empty_terminal_override`），方案可构造且合法。
  - 完整结果迁移面闭合：`FinsResultSummary` 仅四处生产构造点（`direct_events.py` L6609 `_direct_result_event`；runtime L7404/L7459/L7508 三个 helper），`FinsEvent` 仅在 runtime 构造（L6527/L6600）；`_public_download_summary` 全部调用点（L4325/L4422/L4432/L6378/L6587/L7420/L7475）都落在计划声明的迁移范围内；`_emit_direct_result`/`_emit_claimed_direct_result`/`_direct_result_event` 当前参数即 bounded public summary（L6261-6340、L6544-6605），改为 typed 参数与 §3.5 描述一致。
  - 负例与迁移面：`FinsOperationKind` 共 7 值（含 DOWNLOAD，L93-103），非下载操作参数化可行；测试迁移面局限在允许清单内——`download=` constructor / `_public_download_summary` 的测试使用只有 `tests/cli/test_output.py`（L119/288/374/481）、`tests/fins/test_f5_result_contract.py`（L49）、`tests/fins/test_fins_ingestion_runtime.py`（L3509-3510、L6325 `replace(download=...)`）、`tests/service/test_fins_wait_adapter.py`（L524 `replace(download=None)`），全部在计划允许测试列表；activation 专项目标测试与 `_FailingSubmitExecutor` 均存在（`tests/fins/test_fins_ingestion_runtime.py` L10417、L3823），当前仅断言 FAILED，正按计划更新为 typed 空 FAILED + whole failure 断言。
- **最终状态**：resolved（文档级）。None 语义、拒绝分支、helper 复用、参数删除、异常对象与四类测试均已在计划中明确且与代码事实一致；无未覆盖的下载构造点。
- **残余**：实现后需由 code review 验证 fixture 确为“真实合法 typed result”而非伪造补齐（计划已写死该要求，属 implementation 验证项）。

### P3-已修复-低-旧证据核查改为引用已完成归档，不再重复生产查询

- **裁决要求**：引用已完成 owner-read JSON 与总控授权/结果；删除再次等待同一核查确认或重复生产查询步骤；治理锁影响如实说明；不执行任何新来源观测。
- **计划修订落点**：§6（L241-275，引用归档 hash/逐 ID 表）、§8（L308）、§9（L330-331）、§10（L351）、plan-fix P3 行。
- **独立证据**：`docs/gateflow/download-failure-diagnostics-old-evidence-20261010.json` 实测 SHA256=`008ecadf2488e8fe236d8fcfb41cfed923027ed82c36a1c5dad67252dd961bd2`，与 plan L251 一致；解析得 `source_count=45`、`canonical_metadata_sha256=d2010a1e...`、`record_sha256=6d42a496...`（关联既有 terminal-check）、`create_directories=false`、scope 为只读 published metadata；8 条 failed_documents 全部 `published_meta=missing`、`original_reason/original_dates/published_locator=null`；程序化比对确认 plan §6 表格 8 个 document_id 与 JSON 的 8 个 ID 数量、内容、顺序完全一致。plan 已删除“再次 query / 等待同一授权 / 尚未独立核验”的旧表述，改为引用归档并保留 45 来源结论。
- **最终状态**：resolved（文档级）。本轮同样未重复生产查询、未新观测，符合裁决边界。
- **残余**：8 项原原因/日期不可恢复属于已分类限制，不阻塞接口设计。

### P4-已修复-中-负例、mismatch 分类与唯一前缀解析规格化

- **裁决要求**：显式负例——DOWNLOAD RESULT 缺 typed result 拒绝、非 DOWNLOAD 携带拒绝；`period_metadata_mismatch` 必须 FAILED 而非 SKIPPED；诊断行按唯一固定前缀筛选后恰一条，不要求整通道只有一行。
- **计划修订落点**：§5.1 测试 1（L199 两类 owner 负例 + 合法非下载 terminal 诊断 ValueError）、测试 2（L200 period_metadata_mismatch 独立覆盖）、测试 5（L204 前缀筛选唯一物理行、两通道/非下载断言）。
- **独立证据**：`cn_download_filing_workflow.py` L201-215 在 HK 财期不一致时产出 `status="failed"`、`reason_code="period_metadata_mismatch"`、`reason_message="本地财期与来源识别不一致…"`（FILING_FAILED 事件），adapter 按 `_CN_STATUS_FAILED` 映射 FAILED（cn_pipeline L1579-1591）——计划要求“workflow failed + typed FAILED + 原因保真进入 failed_documents”与代码事实一致；CLI 现有输出把 SUCCESS 写 stdout、FAILURE/CANCELLED 写 stderr（`cli/output.py` L233-266），前缀常量与 `json.dumps(..., ensure_ascii=True)` 单物理行方案可直接落地；`tests/fins/test_output.py` 等多处 render 测试均在允许清单。
- **最终状态**：resolved（文档级）。三类规格均已写死且与现有 owner/通道行为自洽。
- **残余**：极端身份转义与 240 码点边界只写了测试意图，仍需 implementation 实测。

## 3. 计划整体可生成代码复核

- **接口与 schema 具体**：新增 `FinsResultSummary.download_result`（typed）、`download` 派生 property、`FinsDownloadPublicSummary.from_result_summary` classmethod、`to_download_diagnostics_json_value` 方法与完整 JSON 字段表 + 最小示例（plan L62-121）；字段名与现有 owner 完全对齐——`FinsPublicFailure.to_json_value()` 恰好是 classification/source/transport_category/message/retry_hint/reason_code（direct_events L264-281），`FinsDownloadPublicSummary.to_json_value()` 与 `FinsDownloadPublicDocument.to_json_value()` 的键与 plan 的 summary/failed_documents 表逐字段相同（direct_events L504-547、L370-391）；退出码 0/1/130、240 字符、10 行上限、4096 预算常量均有真实来源（direct_events L36-38、download_contract L42/45）。
- **依赖方向可行**：`direct_events.py` 已从 `download_contract.py` 导入类型与常量（L22-33），新增 classmethod/常量无循环依赖；`cli/output.py` 已 import json；`cli/commands/fins.py` 经 validated stream 渲染并返回 `terminal.exit_code`（L916-923、L284）。
- **迁移面闭合**：FinsEvent 新操作约束只影响 runtime 唯一构造模块与允许测试文件（`FinsEvent(` 测试使用仅 test_fins_commands/test_output/test_f5_workflow_rebuild/test_fins_direct_stream/test_fins_direct，均在允许清单）；`tests/fins/test_f5_workflow_rebuild.py` 不在“测试允许”清单，但它用 runtime 真实 result 构造事件（L267-271），P2 迁移后天然满足约束；新增诊断行不会破坏其断言（`out == ""` 只针对 FAILURE/CANCELLED 走 stderr 的分支，`Fins summary:` 计数断言不受前缀不同的新行影响，L272-282）。无需名单外测试改动。
- **验证设计**：§5.2（L209-239）给出受影响测试集合、pyright 命令、逐文件 coverage（--fail-under=80 + 独立核对五个文件）；测试 8 的固定 CLI 离线 rebuild 前提已由本路初始 review 实测（EXIT=0、空计数、不触网，同 HEAD）支撑。
- **结论**：五个生产文件、一个行为 slice、无强制持久化/框架扩展，计划在冻结 scope 内仍可直接进入 implementation；未发现迫使实施者重新设计的缺口。

## 4. New Findings

无新增实质 finding。复核中确认以下为“观察”而非 finding：`FINS_DOWNLOAD_SUMMARY_MAX_JSON_CHARS` 的迁移点未逐行列举，但其值为既有 4096 的同一值、计划明确只统一 download durable/public uncertain 调用且不重构其它操作，不产生行为变化或返工风险。

## 5. Residual Risks（合法分类）

| 风险 / 未覆盖项 | 分类 | Owner / destination |
| --- | --- | --- |
| P1—P4 修订文本欠准/残留 | fixed in current slice（本次 plan fix 已修订，本报告验证） | 总控 re-review 终裁决 |
| CN/HK 原因保真、full/bounded 一致、取消前缀、activation typed 结果、CLI 转义、pyright/coverage | fixed in current slice（计划处理，尚未实现/验证） | implementation owner；不能以本报告当实现证据 |
| SEC 原因泛化/upstream 安全治理 | assigned to later work unit | Dayu 维护侧另定 SEC 原因 work unit；不改 SEC 生产 |
| 旧 8 项原原因/URL/日期不可恢复；新观测 | requiring explicit user decision | 巡检线已授权如实未知；新观测另确认范围 |
| 未捕获终态、SIGKILL/崩溃/提前关闭后的历史不可追回 | requiring new issue or explicit user decision | 用户/总控；本轮只承诺合法被消费 RESULT |
| 极端结果规模性能、完整 repr 日志体积 | assigned to later work unit | Dayu 维护侧；真实压力出现时另定 |
| 固定 binary 部署漂移 / 真实网络生产验证、merge | requiring explicit user decision | 总控处理部署阻断；生产观测与合并需巡检线/用户确认 |

## 6. 本轮未覆盖与限制

- 未运行 pytest / pyright / coverage / fixed CLI smoke（plan 未实现，只做文档级 re-review）。
- 未执行任何生产仓储查询、下载、overwrite、recovery 或网络访问；P3 只读归档 JSON 与 hash。
- 未读取另一路初始/复审报告，跨路一致性不由本报告负责；本轮无另一路复审可比。
- 未证明底层物理模型型号；未把模型自报当后端证明。
- P1—P4 的“已解决”只覆盖计划文本契约、owner 归属与迁移面；生产行为、类型与覆盖率证据属于 implementation gate，任何失败须如实上报。

## 7. Re-review Conclusion

**pass**（在冻结 HEAD/plan hash 与已确认 scope 内）：P1—P4 四个 accepted findings 均已按 adjudication 要求修订并被独立证据验证解决；未发现新增阻塞或实质问题；计划整体仍 code-generation-ready。此结论仅为 plan re-review 结论，**不宣布任何 gate pass**，最终裁决归总控；历史未知、SEC 后续治理与部署/合并仍是已分类残余风险。

首尾身份复述（本轮核验）：plan SHA256 `7de77259a5ca545ef959376471f7d902c48fd31dece024b3ce04468b7e18c9f9`；冻结 HEAD `c65c2aa28fae9c47ad947783d63f7559db7768c4`；Branch `fix/download-failure-diagnostics-20261010`；CANARY=ds-flash-7e934412。
