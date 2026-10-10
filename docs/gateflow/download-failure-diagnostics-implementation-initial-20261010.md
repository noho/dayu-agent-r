# 下载失败诊断：S1 implementation partial artifact

RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6
CANARY=gpt-6-sol-ada5a456

- Work unit：download-failure-diagnostics-20261010；slice：S1。
- Gate：implementation；**partial / scope blocked，未完成，不声明任何 gate pass**。
- Artifact：`docs/gateflow/download-failure-diagnostics-implementation-20261010.md`。
- 下一入口：总控裁决测试文件权限后恢复 implementation S1；目前不能进入 code review。
- 本轮没有子 Agent，没有 commit/push/PR/review/fix 后续 gate；没有调用方文件读取、生产 query、新来源观测或远端下载。
- 上述 model 字段是本会话自报，不用于独立证明物理后端型号；canary 内容通过工具实际读取，不是猜测或沿用旧轮次。

## Preflight 与冻结输入

工具实际读取本轮 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.UJQ5Zx/canary.txt`，逐字内容为 `gpt-6-sol-ada5a456`，原文件无结尾换行。

已读根 `AGENTS.md`、`/Users/leo/.codex/skills/gateflow/SKILL.md` implementation slice、已确认 goal、approved plan 的 §3—§5、总控 plan re-review 裁决，以及本轮实际修改的 owner 和测试代码。未重新 plan，未另造接口。

- branch 实测：`fix/download-failure-diagnostics-20261010`。
- preflight / postflight HEAD：`a1df000835c61d1acfa383532488746e1487ed7b`。
- base：`c65c2aa28fae9c47ad947783d63f7559db7768c4`。
- approved plan SHA256 实测：`7de77259a5ca545ef959376471f7d902c48fd31dece024b3ce04468b7e18c9f9`。
- preflight dirty 只有 `docs/gateflow/download-failure-diagnostics-state-20261010.md`，属于总控，已获本轮明确 ownership 说明；本 Agent 未修改它。后续该文件继续由总控更新，不计入本 Agent changed files。
- 修改前 pyright 0 错误引用总控已完成验证，不重跑基线。

动机由同源代码证据确认：runtime 公开摘要只取前十行；CN/HK adapter 将真实 workflow 原因替成通用说明。完整结果原已存在于 operation-local typed owner，无需增加网络流程、历史仓储或 source schema。

## 停止原因与最小所需路径

按 plan §5.2 必跑 `tests/fins/test_f5_workflow_rebuild.py`。其 `test_actual_adapter_observation_wait_and_cli_keep_a_and_unknown` 第 283 行固定要求：

```python
assert len(text.splitlines()) == text.count("\n") == (4 if cancel_after_a else 6)
```

新协议要求每个下载终态默认增加且只增加一条完整诊断物理行。因此真实 owner/adapter/observation/wait/CLI 链分别输出 5 / 7 行。四个参数化用例均因这一旧总行数断言失败；真实 raw 引用、已处理计数及 wait 断言已执行到该行，没有以新错误推断原失败原因。

直接失败证据：`workspace/tmp/dfdiag-affected-round1.txt`，SHA256 `383ec0a92dee4e9c997faf0d61432759418952f9102159b26b1678586432bc76`，外层 pytest exit 1，四例报 `5 != 4` / `7 != 6`。该文件在本轮测试 exact 允许名单之外，**未修改**。

最小所需范围：仅增加 `tests/fins/test_f5_workflow_rebuild.py` 的修改权限，迁移上述用例为按 `Fins download diagnostics: ` 前缀筛选恰一条、剥离后 JSON 还原同源对象的断言；保留现有引用、计数、通道、退出码和 wait 断言。无需名单外生产变更、另一接口或来源流程修复。不能通过少输出诊断、条件隐藏诊断或兼容分支保住旧总行数测试。

本轮发现这一 scope blocker 后停止实现，仅完成现有状态的只读验证及本 partial artifact。下面显式保留范围内尚未收尾的问题，不把它们包装为基线失败，也不以 scope blocker 掩盖自己的未完成工作。

## 本 Agent 完整 changed files

| 文件 | 当前改动 / 状态 |
|---|---|
| `dayu/fins/download_contract.py` | 增加并 export 4096 下载摘要预算常量；计数、来源 schema、source repository 不改。 |
| `dayu/fins/direct_events.py` | `download_result` 唯一 constructor 真源，`download` 派生 property；projection classmethod 与 shared row helper；完整 diagnostics JSON；typed 与 event operation 校验。 |
| `dayu/fins/ingestion_runtime.py` | direct producer/emit/claim/event 全链传完整结果；取消 replace 完整快照；activation helper 收口；删除旧 public helper；下载 durable 预算同源。 |
| `dayu/fins/pipelines/cn_pipeline.py` | FAILED/SKIPPED 严格读取 workflow reason_code/reason_message，删除 fallback 与通用原因。 |
| `dayu/cli/output.py` | 原终态通道机械序列化唯一诊断行；human summary 增加 terminal_disposition。 |
| `tests/fins/test_download_failure_diagnostics.py`（新增） | 完整 owner、超十行、三来源、未知元数据、特殊身份、操作负例、通道和输出异常测试；43 例已独立通过。 |
| `tests/fins/test_cn_download_runtime.py` | strict fixture 补真实字段；新增 workflow 观察器、外部故障输入、真实 CN/HK 链与 strict 负例；新增测试存在 import 错误，尚未通过。 |
| `tests/fins/test_f5_result_contract.py` | public projection 调用移到 direct owner，不保留 runtime helper。 |
| `tests/fins/test_fins_direct_stream.py` | DOWNLOAD success fixture 使用显式完整 typed 空结果。 |
| `tests/fins/test_fins_ingestion_runtime.py` | full constructor 迁移；新增 activation 两异常与 prepare-cancel 请求同源断言；新增签名缺类型 import，尚未收尾。 |
| `tests/cli/test_output.py` | fixtures 迁移完整 typed 事实，行计数转前缀解析；有一条 locator 字符串断言被机械替换误改，尚需恢复为公共字符串预期。 |
| `tests/cli/test_fins_commands.py` |合法 DOWNLOAD fixture 与固定绝对 executable 空 rebuild；原多命令 fixture 的 processed_count 展示断言尚需按实际操作迁移。 |
| `tests/service/test_fins_direct.py` | 合法 fixture 区分下载 / 非下载的完整结果。 |
| `tests/service/test_fins_wait_adapter.py` | fixtures 从完整 typed 结果派生 bounded JSON，不由公开行反推真源。 |
| 本 implementation artifact | preflight、partial 实现、验证证据、范围阻断与未覆盖项。 |

只写以上指定生产/tests/artifact；三个允许 README 尚未修改。`test_cn_download_workflow.py`、`test_fins_ingestion_tools.py` 本轮未修改。不存在未知 dirty。临时文本验证输出放 `workspace/tmp/`；无常驻分析工具，无临时脚本。

## Owner / dataflow 与当前实现

来源 workflow 负责候选身份、披露日期、报告日期、coverage 与 safe reason；CN/HK adapter 在直接 owner 输入处严格消费 reason pair。未修改 SEC adapter 的既有安全文案，只机械投影它已有 typed 值。

完整 `FinsDownloadResultSummary` → runtime 身份/计数校验 → direct claim/event → `FinsResultSummary.download_result`。`download` property 只调用 `FinsDownloadPublicSummary.from_result_summary`，保持前十行、omitted 与独立 uncertain 预算。完整 FAILED 数组和 bounded rows 共享 `_download_public_document`，PurePosixPath 仅转相对 string；未知 form/date 保持 null，未知 coverage 保持空数组。

CLI 用 `json.dumps(..., ensure_ascii=True, sort_keys=True)` 原通道输出诊断；默认不依赖 log-file，不调用文本截断器。SUCCESS/partial 在 stdout，FAILURE/CANCELLED 在 stderr。整体 failure 独立于每候选失败，不造候选原因。request-scoped 空结果只由持有请求的 runtime owner 构造；取消在完整 typed snapshot 上覆盖 terminal，未处理候选没有伪结果。

Service wait 原实现仍只序列化派生 `download` bounded JSON。durable job 下载摘要维持已有 schema 与 4096 预算，没有 failed_documents、完整诊断 wrapper 或新增 memory/trace 字段。activation 保留原异常同对象 raise，失败 record 改复用既有 owner helper。上述正常链主体已落地，**尚未完整验证所有取消、activation、typed abort 分支**。

## Plan §5.1 八组 success signal 的证据与缺口

| 组 | 实际证据 | 状态 / 缺口 |
|---|---|---|
| 1 owner/public | 新文件 `test_failures_after_first_ten_are_complete_and_same_source`：11 skip + 1 downloaded + 12 failed，24 rows / 12 failures / bounded 10 / omitted 14；typed 同对象、逐字段同源与 durable 预算。三来源 × 0/1/10/11/12 × null/已知、240 码点身份及每个非下载 operation 的 owner 负例均通过。 | 新 owner 文件 43 passed，exit 0；覆盖正常/all-failed/取消与 CLI，不等于全部 runtime 已通过。 |
| 2 CN/HK 真链 | 现有 CN/HK workflow/runtime 大批隔离 Fs 用例在整组执行中通过；strict fixture 原缺 reason_message 的四例已作迁移。新增真实 workflow 观察器只记录原结果，故障输入仅替外部 PDF transport。 | 新增真实 reason 矩阵尚因 import 错误不能收集；period_metadata_mismatch 的独立真链断言尚未补齐，不能宣称满足本组。 |
| 3 runtime | 整组原正常/部分失败/全失败/空结果/provider/typed integrity 回归已经执行，大多数通过；activation 新断言与 request-scoped typed 空结果代码已加入。 | 新 activation/prepare-cancel 第一次执行因日期字段名称误写失败，已修为 request bound；最新最终矩阵未重跑。两处新增测试 import/type 未完成；SEC 原因治理无新增承诺。 |
| 4 cancellation/stream | `test_fins_direct_stream.py` 现有 clean exhaustion、唯一/重复/缺失/后续 RESULT、原 BaseException/close 与终态 typed fixture 在整组运行通过；新 owner CLI 取消保持原 prefix，failure null。 | runtime downloaded+failed 前缀及 terminal claim 竞争的专用新增断言尚未完成；prepare-cancel 已加入但未最终验证。 |
| 5 CLI | 新 owner 单行 reversible JSON 与 SUCCESS/partial/FAILURE/CANCELLED 各通道、无截断 >10 failed、特殊身份、OSError 传播通过。 | 原 test_output 一条 locator 断言误写、旧测试总行数及非下载 fixture 迁移尚需收尾；名单外 F5 四例阻断。 |
| 6 LLM/durable | 新 owner durable budget/schema 验证通过；原 F5 contract 与 wait 回归整组无新增 failure，runtime public helper 调用已移 owner。 | 超十失败 observation→wait 三终态 dedicated 断言尚未加齐；不能以 owner 字段不序列化代替全链验证。 |
| 7 service/入口 | Service 受影响 fixture 已迁移，整组后一次 Service 用例没有报错。 | CLI 默认 quiet/临时日志下 12 失败经主入口的专用用例尚未完成；同对象 full result 的新增 service 断言尚未补齐。 |
| 8 fixed executable | `test_fixed_cli_download_diagnostics_on_empty_rebuild`：fresh tmp root、仓库外 tmp cwd、固定绝对 binary、timeout=60；真实 subprocess returncode=0，stdout 唯一 prefix，stderr 无 prefix，parsed ticker 0700 / FY,H1 / 原窗口 / rebuild true / counts 全零 / failed_documents=[] / terminal succeeded。最终 pytest exit 0，1 passed。 | 只证明新 protocol 实际装配加载；没有网络来源失败观测，不证明旧 8 项原因或真实生产下载成功。 |

## 实际测试命令、退出与计数

所有 pytest/pyright 命令均先 `source .venv/bin/activate`。表中集合为精确文件集合缩写，下面定义，以便复现；输出记录是运行当时版本，不冒充停止时所有文件的最终通过。

- A（plan §5.2 全受影响集合）：`tests/fins/test_download_failure_diagnostics.py tests/fins/test_cn_download_runtime.py tests/fins/test_cn_download_workflow.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_direct_stream.py tests/fins/test_f5_result_contract.py tests/fins/test_fins_ingestion_tools.py tests/cli/test_output.py tests/cli/test_fins_commands.py tests/service/test_fins_direct.py tests/service/test_fins_wait_adapter.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_f5_workflow_rebuild.py`。
- B：A 去掉新增 owner 文件和最后三个只读回归文件。
- C：`tests/fins/test_download_failure_diagnostics.py tests/cli/test_output.py tests/fins/test_fins_direct_stream.py tests/service/test_fins_direct.py tests/service/test_fins_wait_adapter.py`。
- D：`tests/fins/test_cn_download_runtime.py tests/cli/test_output.py tests/cli/test_fins_commands.py tests/service/test_fins_direct.py tests/fins/test_fins_ingestion_runtime.py`。

| 实际命令（激活后） | 真实外层 exit / 结果 | 证据 |
|---|---|---|
| `python -m pyright dayu/fins/download_contract.py dayu/fins/direct_events.py dayu/fins/ingestion_runtime.py dayu/fins/pipelines/cn_pipeline.py dayu/cli/output.py` | 1；1 error（activation 旧实参），随后已删除该实参。 | 本轮工具原输出。 |
| `python -m pyright dayu/ tests/ utils/`（首轮） | 1；36 errors，旧 runtime import 被误移除，随后已恢复该测试 import。 | 本轮 session 97295 真实 exit。 |
| `python -m pytest B -q --tb=short > workspace/tmp/dfdiag-initial-tests.txt 2>&1` | 2；collection 1 error（上述 runtime import）。 | initial-tests。 |
| `python -m pytest C -q --tb=short > workspace/tmp/dfdiag-owner-tests.txt 2>&1` | 1；143 passed / 19 failed / 3 warnings。 | owner-tests。 |
| `python -m pytest A -q --tb=short > workspace/tmp/dfdiag-affected-round1.txt 2>&1` | 1；1385 passed / 29 failed / 3 warnings，123.90s。无 skip。 | round1 SHA256 见停止原因。 |
| `python -m pytest D -q --tb=short > workspace/tmp/dfdiag-affected-round2.txt 2>&1` | 1；836 passed / 19 failed / 3 warnings，97.89s。无 skip。 | SHA256 `f190d79634611149b6cc7df061f5766371791176f47546bff215f892a8e38068`。 |
| `python -m pytest tests/cli/test_fins_commands.py -k fixed_cli_download_diagnostics_on_empty_rebuild tests/fins/test_fins_ingestion_runtime.py -k 'activation_submit_failure_terminalizes_prepared_observation or cancel_prepared_download_preserves_request_and_never_submits or fixed_cli_download_diagnostics_on_empty_rebuild' -q --tb=short` | 1；4 failed / 674 deselected / 3 warnings；固定 binary 实际已返回 0，旧 forms 预期错误；其它三例日期字段错。随后字段和 forms 预期已修，尚未完整重跑三例。 | 本轮 session 1965 原输出。 |
| `python -m pytest tests/cli/test_output.py tests/service/test_fins_direct.py tests/cli/test_fins_commands.py -q -x --tb=short` | 1；1 failed / 3 warnings，旧总换行数断言；随后本允许文件的该断言已移除。 | session 19343 原输出。 |
| `python -m pytest tests/fins/test_cn_download_runtime.py -k 'real_workflow_failure_reasons or real_skip_and_hk_rebuild or reason_owner_strictly' -q --tb=short` | 2；1 collection error：错误地从 download_contract import FinsDownloadProgressSink。当前仍未修。 | 本轮工具原输出。 |
| `python -m pyright dayu/ tests/ utils/ > workspace/tmp/dfdiag-partial-pyright.txt 2>&1`（停止时） | **1；2 errors / 0 warnings**。 | SHA256 `52a00dcf18c92ecbedf6b1fa2fb2398717ac63e481325c535b42c1dd41000a03`。 |
| `python -m pytest tests/cli/test_fins_commands.py -k fixed_cli_download_diagnostics_on_empty_rebuild -q > workspace/tmp/dfdiag-fixed-cli.txt 2>&1` | **0；1 passed / 215 deselected / 3 warnings**，2.89s。 | SHA256 `d82683c4b5a8a9d9b8e7f6422024e4a7cd6422b79bc9dc63ec9f0be9631a402e`。 |
| `python -m pytest tests/fins/test_download_failure_diagnostics.py -q > workspace/tmp/dfdiag-owner-final-partial.txt 2>&1` | **0；43 passed / 3 warnings**，1.19s。 | owner-final-partial。 |

停止时 pyright 两个本轮新增错误（不是基线）：

1. `tests/fins/test_cn_download_runtime.py:39` 的 `FinsDownloadProgressSink` 需要从实际 owner `dayu.fins.ingestion_runtime` 引入，当前 import symbol unknown。
2. `tests/fins/test_fins_ingestion_runtime.py:10444` 的新 helper 类型签名缺 `FinsDownloadRequest` import。

范围内剩余失败还包括 `test_output.py` 的公共 locator 文本断言被误替成 PurePosixPath 代码文本，以及 CLI 多命令 fake 原来借 DOWNLOAD 事件显示 processed_count，现在完整 DOWNLOAD 专属摘要按 owner 正常忽略非下载 details；需把 fixture 按其测试 operation 构造成真正合法终态，不能在生产增加兼容 details 输出。

`git diff --check` 当前发现两测试文件共六处 trailing whitespace。原输出保留在 `workspace/tmp/dfdiag-partial-diff-check.txt`。这些也是本轮未收尾项，不归为基线。

### Coverage 与资源型验证

未执行 broad coverage 命令与 `coverage report --fail-under=80`：在 scope blocker 与新增测试 collection/type 错误未收尾时，coverage 不能替代完成验收。没有修改 coverage 配置、排除生产行或用新增行覆盖率冒充逐文件覆盖。

| 生产文件 | 本轮最终逐文件 coverage |
|---|---|
| download_contract.py | 未测，不能声明 >=80%。 |
| direct_events.py | 未测，不能声明 >=80%。 |
| ingestion_runtime.py | 未测，不能声明 >=80%。 |
| cn_pipeline.py | 未测，不能声明 >=80%。 |
| cli/output.py | 未测，不能声明 >=80%。 |

本轮已跑的受影响集合没有资源型 skip；broad fins/cli/service 尚未执行，因此不能推断其资源型集成 skip 数或基线 failure。现有 3 warnings 为 edgar deprecation。所有报告失败按具体本轮原因列出，无未验证的“基线失败”免责标签。

## README decision

已读根 README、`dayu/fins/README.md`、`tests/README.md` 与 `dayu/README.md` 的职责边界。

- 根 README：按计划需更新默认完整诊断行、原 stdout/stderr 捕获、0 与 partial_failure 区别、临时日志历史限制；scope 停止时尚未修改。
- Fins README：需更新 operation-local full result / bounded public / LLM 接口、原因 owner、取消快照边界；尚未修改。
- tests README：需记录 owner、strict 真链、bounded wait、固定 executable 离线验证及证据限制；尚未修改。
- dayu README：不触发跨层、装配或 Host/Engine/runtime 边界变化；已检查，不修改。
- 未修改生产网络流程、来源数据 schema、source repository、退出码政策、SEC 原因治理或其它 README。

## Fixed binary 实际加载身份

从 `/private/tmp` 执行固定 venv Python `-B -c`，未设置 PYTHONPATH；工具真实 exit 0。命令 import `dayu.cli.main`、`dayu.cli.output`、`dayu.fins.direct_events`、`dayu.fins.download_contract`、`dayu.fins.ingestion_runtime`、`dayu.fins.pipelines.cn_pipeline`，输出 sys.executable/version、每个 `__file__` 及 SHA256，并检查新 property / diagnostics method。

- binary：`/Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli`。
- binary SHA256：`42b7131da40fa45cbbdd6f9be4004b6a947f34b92a13e3571c0b1aed21b88af1`。
- shebang：`#!/Users/leo/workspace/dayu-agent-r/.venv/bin/python3.11`；entrypoint `dayu.cli.__main__:exit_module`。
- fixed Python sys.executable：`/Users/leo/workspace/dayu-agent-r/.venv/bin/python`；version 3.11.15。
- 实际 `dayu_agent-0.1.4.dist-info/direct_url.json`：editable=true、URL 指向本仓库。
- `isinstance(FinsResultSummary.download, property)` 为 True；新 diagnostics method callable 为 True。
- 下表模块路径均为 `/Users/leo/workspace/dayu-agent-r/` 加所列相对路径，HEAD 仍为 accepted plan commit，修复在当前未提交 working tree；**不能用 HEAD 或 0.1.4 版本号单独代表修复身份**。

| 实际模块 | SHA256 |
|---|---|
| dayu/cli/main.py（只读） | a61ccd24765e9890eff71f38dbc91176d02174c5df9bab14e66d5400613dfa08 |
| dayu/cli/output.py | 9aa54696e8e67c5daaa721d5311052e5003c2c6c14c3520f5c8ff4c2bcdc97cd |
| dayu/fins/direct_events.py | 1eeae91e2004875b70384bb15f1d8ca5f1c7e1bb25083ac2e23a59d1177742fe |
| dayu/fins/download_contract.py | 9c66c790a49095307391380c7ddd807b7655d0e3a5bf69aefd58e31185788dd3 |
| dayu/fins/ingestion_runtime.py | 9c6a776bf2d665161671bd5497bbf1fa26ea12a0640193a74f724e2e552b8b08 |
| dayu/fins/pipelines/cn_pipeline.py | 470f4fcaef4d264ae7a08f660e134dda4b9d7382810759b9cd36b91897124e2d |

固定 CLI smoke 在 fresh pytest tmp 根、另一临时空 cwd 执行本 binary 的 `download --base <fresh fixture root> --ticker 0700 --start 2018-01-01 --end 2026-10-10 --rebuild`；没有原生产 root。该来源 workflow rebuild 分支在 discovery/resolve_company 之前 local 返回。新默认 protocol 机械可用已独立验证；本轮不安装、不发布、不把 empty rebuild 冒充远端失败或生产恢复。

## 旧证据引用与不可恢复边界

本轮只读归档 `docs/gateflow/download-failure-diagnostics-old-evidence-20261010.json`，SHA256 实测 `008ecadf2488e8fe236d8fcfb41cfed923027ed82c36a1c5dad67252dd961bd2`。引用总控已经公共 storage owner 读取完成的 8 missing / 45 来源，不重新 query。

- source_count=45；canonical metadata SHA256 `d2010a1e5d30be536dd4f24b1cc53490ddeec68a875ad2e03d611e712b502b50`。
- record SHA256 `6d42a496a0fd4bbfce4a320025e77fa92758098c380ba51513a689527f15fce7`。
- 原 stdout SHA256 沿用 goal/plan：`a9c8a3cc2babdd8c93313345e55f1638c27fea15b6b56c5d7f8d37b1ebd07f3a`，原 stderr 0 字节。

| 原 document_id | 可恢复 | 当前 published_meta | 原日期 / form / report_date / coverage / reason / URL |
|---|---|---|---|
| fil_cn_76fad62cd9ba3141f4cab67e8e2a0c220a93a27d | 身份、PDF file_failed 阶段 | missing | 未知 |
| fil_cn_04fb4018812cf15ca633495dbd9fcac3cb033378 | 同上 | missing | 未知 |
| fil_cn_307f1a281919204de1d3c3cb5f95322463819734 | 同上 | missing | 未知 |
| fil_cn_2a0ebbf2c2935ee14a39fec8744d626853a68424 | 同上 | missing | 未知 |
| fil_cn_d56f9cdc70daa5174522111629889cc74795448b | 同上 | missing | 未知 |
| fil_cn_535e021474217e2750d6063d7046a72ead52f7b5 | 同上 | missing | 未知 |
| fil_cn_a44583fc024459f5a22ee4eed537dea35e8882ac | 同上 | missing | 未知 |
| fil_cn_4043a094cd9d2292c378e6b6c8f1856868291372 | 同上 | missing | 未知 |

当前 missing 不证明原历史 snapshot 或失败原因；45 不是本轮下载数或业务覆盖结论。本轮没有生产来源写入/overwrite/recovery，原 45 来源未触达。没有从身份、相邻候选或本轮合成故障推断原原因。

## Residual 风险、未覆盖项与交接

| 风险 | Gateflow 规范分类 | Owner / destination |
|---|---|---|
| 必跑 F5 regression file 未列允许修改名单，旧总行数断言与冻结新协议冲突 | requiring new issue or explicit user decision | 总控只需裁决增加上述一个测试文件权限；无须新设计或生产扩范围。 |
| 本轮 S1 新增完整投影与原因修复候选代码 | fixed in current slice | 当前 S1 实现候选；43 owner 测试已通过，但其余范围内未收尾义务见八组/验证，不能视为实现或 gate 已通过。 |
| SEC 已有安全原因泛化 | assigned to later work unit | Dayu 维护侧另定 SEC 原因 owner 范围；本轮只机械保留既有安全 typed 值。 |
| 旧 8 项原原因与元数据不可恢复；任何未来新观测或实际下载缺陷扩范围 | requiring new issue or explicit user decision | 巡检线另定明确候选、网络与仓储影响；本轮用户已授权如实未知，不重问同一旧证据查询。 |
| 未捕获终态、SIGKILL、崩溃、提前关闭流后的历史无法恢复 | requiring new issue or explicit user decision | 如需 durable 历史诊断，用户/总控另定 work unit；不在 S1 添仓储。 |
| 极端无界结果规模、内存与 repr 日志压力 | assigned to later work unit | Dayu 维护侧，真实扩展压力出现后另定性能工作；本轮无压力测试或分页框架。 |
| merge/approve/ready/reviewer/外部 comment | requiring new issue or explicit user decision | 用户额外授权范围；已授权 automatic commit/push/draft PR 不列为新阻断，本 Agent 不执行后续 gate。 |

未完成工作而非已完成证据：两处新增 type/import 错误、允许范围 fixture/display 迁移、真实 provider reason/mismatch 真链、runtime prefix/claim 三终态、bounded observation wait 三终态、CLI quiet/default-log 十二失败主入口、逐文件 >=80% coverage 和三个 README 更新。无资源型集成通过声明，无原生产失败原因恢复声明。

**Completion：S1 partial，按名单外必要测试迁移停止条件交总控；不是 code review-ready，不是 gate pass。总控若扩大该一个测试文件权限，则恢复同一个 S1 implementation，先完成上述范围内收尾和全部 plan §5 验证，再交 code review。**

## Postflight 并发总控补充

本 artifact 写完后的最终 status 新出现 `docs/gateflow/download-failure-diagnostics-test-scope-adjudication-20261010.md`。已只读确认它由总控 owned，裁决将上述 F5 文件纳入必要测试迁移，exact5 生产范围和 plan hash 不变；不是本 Agent 写入，不算未知 dirty。该裁决明确说明 runner 未收到补充时在正常终态后派发限定 continuation/fix。当前本轮已经按 scope blocker 停止实现并保存 partial；不撤销任何本轮失败或欠缺记录。后续由总控按该补充恢复同一 S1，仍先收尾实现/验证，不能跨到 code review 或宣称 pass。文件名单遗漏的总控裁决现已存在，不再重复要求总控作同一裁决；本轮未改 F5 文件。
