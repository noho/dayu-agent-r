# 巨潮美的修复：implementation / offline validation

状态：本子任务源码和离线验证已完成；真实 CLI、独立组合审核及 work unit 裁决仍待总控。没有 commit、push、开 PR、merge，没有执行写原业务 workspace 的正式 CLI，也没有修改 goal、control 或 accepted plan。

## 绑定目标、动机与 owner

- Binding scope：[已确认目标](cninfo-midea-20261018-goal-confirmation.md)、[accepted plan](cninfo-midea-20261018-plan.md)、[control](cninfo-midea-20261018-control.md) 及本次 implementation 交接；分支 `fix/cninfo-midea-report-identification-20261018`，HEAD/base `1b2166305428d894696974519615cfc4a0ca3b20`。
- 修改前已完整读取 AGENTS.md、上述三份文件；复用现有原始字节和基线，没有重新取证、联网采集或重复跑基线，没有派 agent。
- 动机成立的直接证据仍是现有官方 `1225065145` 完整 PDF、真实 pypdf 首页、原 owner cause 和单因素文本对照：明确“全文”后缀被误拒。修复是原 owner 封闭语法的补齐，不从标题、发布日期、其他页面或股票身份补偿。
- 年度/性质与解析拒绝原因归 `cn_annual_report_facts`；本地声明/字节关系与其拒绝原因归 `cn_annual_report_source`；来源/阶段由实际调用边界提供；候选与持久化身份继续由原 selection/identity/storage owner 产生。消费者不解析异常字符串。
- 原始调用没有当次响应/PDF/失败 source ID 快照。这里证明当前复现和修复，不猜测原始失败的唯一 source ID。

## 实际变化

1. facts owner 只在既有封闭后缀集合中增加精确 `全文`，与裸标签同为 full；保留空白归一和所有标签必须一致的规则。`全文摘要`、`全文说明`、`全文（未知）`、错年、全文/摘要冲突及证据不足仍拒绝。仍只读物理首页，没有自然年度/日期推断、多页扫描、OCR 或个股分支。
2. facts owner 新增 `CnAnnualReportFactsError` 和四个封闭原因；source owner 为原声明异常附独立封闭原因。底层 cause 保留供开发取证，不进入默认拒绝诊断。
3. 新增窄共享 `cn_annual_report_diagnostics`：warning 记录 provider、显式来源引用、实际阶段和可用文档身份。正常数字来源可定位；格式不适合安全展示的引用只显示“不可展示”和完整 SHA256，不伪装来源。安全引用经 JSON 转义，长度由封闭格式限制。没有正文、URL、绝对路径、任意异常文本或 traceback。
4. 接入 remote/local discovery、下载复核、COMPLETE 原件复核、本地声明读取。发现前不造 document_id；public safe message、provider protocol/不可重试、单 filing `source_document_facts_mismatch` 与完整性/取消边界保持既有契约。没有公共 schema、仓储协议或状态机变更。
5. 新增 `test_cninfo_midea_regression.py` 和长期 fixture `tests/fins/fixtures/cninfo_midea_20261018/`。两份全文、两份摘要均为**官方完整原件的物理首页派生 PDF，绝非完整原件**；冻结公司映射和四分类原始响应。`provenance.json` 保存官方 URL、采集 UTC、完整原件 hash/字节/页数、派生 hash、文本 hash、页码与 pypdf 生成方式。测试不依赖 `workspace/tmp`；保留原 13 份官方样本。完整原件仍可从既有取证目录取回。

## 回归与实际结果

以下命令均在仓库 cwd，先 `source .venv/bin/activate`，设置 `PYTHONDONTWRITEBYTECODE=1`。每个进程已等待并观察真实退出；不是从日志末行推测退出。

最终证据根 `V = workspace/tmp/cninfo-midea-20261018/implementation-validation/final/`。

```bash
source .venv/bin/activate
PYTHONDONTWRITEBYTECODE=1 \
COVERAGE_FILE=workspace/tmp/cninfo-midea-20261018/implementation-validation/final/.coverage \
python -m pytest -p no:cacheprovider \
  --basetemp=workspace/tmp/cninfo-midea-20261018/implementation-validation/final/pytest \
  tests/fins/test_cn_annual_report_facts.py \
  tests/fins/test_cn_annual_report_source.py \
  tests/fins/test_cninfo_downloader.py \
  tests/fins/test_cninfo_midea_regression.py \
  tests/fins/test_cn_report_selection.py \
  tests/fins/test_cn_download_workflow.py \
  tests/fins/test_cn_download_runtime.py \
  tests/fins/test_cn_download_identity.py \
  tests/fins/test_source_integrity_preflight.py \
  --cov=dayu.fins --cov-report=term-missing \
  --cov-report=json:workspace/tmp/cninfo-midea-20261018/implementation-validation/final/coverage.json -q
PYTHONDONTWRITEBYTECODE=1 pyright
PYTHONDONTWRITEBYTECODE=1 pyright \
  --project workspace/tmp/cninfo-midea-20261018/implementation-validation/pyright-tools.json --outputjson
```

| 验证 | exit / 实际结果 | 可取回输出 |
| --- | --- | --- |
| 最终受影响 tests + coverage | 0；630 passed，3 条既有 edgartools 弃用 warning，32.73s | V 下 `pytest.stdout.txt` / `pytest.stderr.txt` / `coverage.json` / `.coverage` |
| 最终全仓 pyright | 0；0 errors / 0 warnings / 0 informations | V 下 `pyright.stdout.txt` / `pyright.stderr.txt` |
| 临时工具及生成脚本 pyright | 0；实际分析 6 个文件，0 errors / 0 warnings | V 下 `pyright-tools-06.json` / `.stderr.txt`；独立配置显式排除项为空 |
| 验收 runner `--help`（未启动 CLI） | 0；实际可导入并展示参数 | V 下 `tool-help.stdout.txt` / `.stderr.txt` |
| 隔离 Fs 读回工具 smoke | 0；两份来源、一份 storage manifest、两次 publication 相等、转换只发生首次两次 | V 下 `tool-snapshot-smoke-02.stdout.txt` / `.stderr.txt`、`tool-snapshot-smoke/receipt.json` 及 before/after 可取回快照 |
| `git diff --check` | 0 | 最终 receipt 的进程记录 |

新增实际断言：2025/full 与 2024/full；精确后缀、同年一致与冲突；坏字节/零页/加密/空白提取的 owner reason；复杂官方摘要证据不足仍拒绝；四个官方分类得到七个真实来源候选，两个 FY 都完成真实 facts，摘要不 GET，prepared 字节/hash 同源。真实隔离 Fs 覆盖 prepared、直接下载、无 witness COMPLETE、本地发现与有 witness repeat；核对 owner 产生的财年、来源、覆盖财期、身份、revision、全部资产和 metadata。repeat 无实际 mock-transport GET，无新增转换，全部 publication 不变。另覆盖落选准入坏 FY 的整次 discovery 失败、本地声明拒绝、下载/COMPLETE 的坏件和错年，以及含私密 URL/路径/正文/控制符的 cause 不外泄。既有完整性/取消/已提交前缀回归一并通过。

离线测试中的网络由 MockTransport 提供原冻结字节，转换器是明确的测试转换器；没有 fake facts 正例，不以这些转换字节冒充真实 Docling 产物。非 FY PDF、实际业务 workspace 与真实网络/转换验收没有在本子任务执行。

逐修改生产文件语句覆盖率（完整文件，无排除生产行）：

| 文件 | covered / statements | 覆盖率 |
| --- | --- | --- |
| `cn_annual_report_facts.py` | 47 / 47 | 100.00% |
| `cn_annual_report_source.py` | 71 / 72 | 98.61% |
| `cn_annual_report_diagnostics.py` | 22 / 22 | 100.00% |
| `cninfo_downloader.py` | 354 / 390 | 90.77% |
| `cn_download_filing_workflow.py` | 285 / 306 | 93.14% |
| `cn_download_workflow.py` | 321 / 356 | 90.17% |

所有修改生产文件达到 >=80%。未以全包平均数代替逐文件核对。

迭代记录保留在 `implementation-validation/`：首次新增回归 69 passed / 4 failed，失败是新测试错误猜测复杂摘要原因、summary 字段及缺 primary 的测试更新请求；随后按真实 owner 合同修正测试，74 passed。扩大回归首次同样 630 passed。临时工具首次直接 pyright 被 workspace exclude 排除，因此不将该次零错误当有效验证；独立配置首次实际发现 7 项工具类型/导入问题，修正后最终含收据脚本的 6 文件检查通过。读回 smoke 首次因脚本导入路径缺 repo 退出 1，补命令 `PYTHONPATH` 后实际退出 0。未靠生产 fallback 或降低规则消除失败。

## 验证版本与可取回 snapshot

- 验证代码为上述 base 上的当前未提交组合版本；没有用同一 HEAD 冒称工作树未变化。
- `V/implementation-receipt.json` 保存实际解释器、Python/依赖版本、导入路径、HEAD/branch/base、dirty status、逐文件 SHA256、原证据逐字节校验、最终各进程退出记录。
- `V/source-snapshot.tar.gz` 保存验证时的源码、测试、永久 fixtures、review 文档及临时验收脚本；`V/working-tree.diff` 保存 tracked binary diff；未跟踪的新文件也进入 snapshot 和 hash 清单。snapshot 不含业务 workspace。
- 原官方完整件仍在 `workspace/tmp/cninfo-midea-20261018/annual-evidence/`；原 2025 PDF hash 为 `16f95f70527db59dcf2736f276a9479cf7ee917e5f71e4f6cbbe83acbad9f4b6`，2024 为 `b17a9b9b84bca1d2a4e4a3cadc5dd5ba5c85e3f1fd2d758acd3315b5b040ecd9`。冻结首页和 raw 的永久 provenance 另在 tests fixture 内，不依赖这些临时原件。

## README decision

修改前已读目标文档的职责约束。

- `dayu/fins/README.md`：更新，说明精确首页语法、失败关闭和 owner 拒绝诊断的稳定边界；没有写工作单状态或测试流水账。
- `tests/README.md`：更新，去掉固定样本数，补永久 provenance、实际 owner/入口/安全日志与离线证明边界。
- 根 `README.md`：已检查，不改；CLI 参数、日志路径用法、默认输出和最终用户操作没有变化。现有首页规则说明仍准确。
- 其他 README：没有 Engine/Host/config 或整体分层装配变化，不触发。

## 供总控执行的真实 CLI 验收工具

工具仅在 `workspace/tmp/cninfo-midea-20261018/`，不进入生产抽象：

- `run_midea_cli_acceptance.py`：固定本仓库绝对 CLI、原 base/ticker/日期和普通增量参数；只替换全新 log-file，拒绝覆盖已存在 run-dir。保存实际 PID/start/end/exit、stdout/stderr、diagnostics、CLI shebang/工作树版本与 snapshot。首跑非零时拒绝用 repeat 掩盖。
- `midea_cli_observer.py`：sitecustomize 只在 CLI PID 安装 HTTPTransport、HTTP11 实际发送、Response.read 和真实 ProcessDoclingConverter 透传观察；子进程不重复装载。原请求/响应/返回对象/异常均透传，响应读取完成后才保存生产消费的字节及 hash。记录 conversion start/end/error、hook 完整性和解释器结束。没有响应替换、URL 改写或生产规则改动。
- `midea_cli_snapshot.py`：只经 `SourceDocumentRepositoryProtocol` 的 inventory/meta/exact snapshot API 读取 source，并复制仓储物化出的资产，保存 revision、provenance、descriptor、actual hash、原件 facts 和 Docling 主资产原字节。manifest 由 storage public reads 触发的实际 owner JSON read 只读观察取得；保存 JSON 和规范 JSON hash，**不冒称原始 manifest 文件字节 hash**。不直接读取受管目录或写业务 publication。

精确运行命令（在仓库 cwd；首跑结束并检查真实退出、diagnostics 后再执行第二条）：

```bash
source /Users/leo/workspace/dayu-agent-r/.venv/bin/activate
PYTHONDONTWRITEBYTECODE=1 /Users/leo/workspace/dayu-agent-r/.venv/bin/python \
  /Users/leo/workspace/dayu-agent-r/workspace/tmp/cninfo-midea-20261018/run_midea_cli_acceptance.py \
  --run-dir /Users/leo/workspace/dayu-agent-r/workspace/tmp/cninfo-midea-20261018/cli-first-01

PYTHONDONTWRITEBYTECODE=1 /Users/leo/workspace/dayu-agent-r/.venv/bin/python \
  /Users/leo/workspace/dayu-agent-r/workspace/tmp/cninfo-midea-20261018/run_midea_cli_acceptance.py \
  --run-dir /Users/leo/workspace/dayu-agent-r/workspace/tmp/cninfo-midea-20261018/cli-repeat-01 \
  --previous-run /Users/leo/workspace/dayu-agent-r/workspace/tmp/cninfo-midea-20261018/cli-first-01
```

子进程实际 argv 等价于：

```bash
/Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli \
  --base /Users/leo/workspace/portfolio-manager-v2/workspace \
  --log-file <本次全新run-dir>/dayu.log \
  download --ticker SZ:000333 --start 2025-01-01 --end 2026-10-18
```

每次检查 `run.json` 的 **actual_exit_code**，不要把观察工具 exit 2 误记为 CLI exit 2。工具仅在原 CLI exit 0 且观察/diagnostics/快照齐全时返回 0；repeat 还核对首跑与本次 before/after、零 PDF GET/转换、官方 raw 相等，否则返回 2 供总控核对。它不裁决整个 work unit pass。证据包括 `observations.jsonl`、全部 `http-*.response.bin`、`official-rows.json`、`http-conversion-summary.json`、`source-before/`、`source-after/`、`comparison.json`。通过原 raw parser 对公告 locator 归属来源，不从 URL 截取 ID。实际官方集合变化时保留原始响应交总控逐条对账，不硬编码七条通过。

HTTP 观察严格核对现装 httpx 0.28.1 / httpcore 1.0.9 与 wire signature；若版本或 hook 不符，只报告观察未齐，不修改生产行为。HTTP 字节是 httpx 实际交付生产的解码响应体；不是原始压缩 wire body。真实 HTTP/wire/转换观察尚未经过本次正式 CLI，离线 smoke 只验证读回和 manifest 捕获，须在真实验收中核对 started/finished/hooks/error_count。

## 风险、owner / destination 与未完成项

| 项目 | 分类 | owner / destination |
| --- | --- | --- |
| 合法“全文”误拒与入口语义漂移 | fixed in current slice；源码/离线验证完成，待审核 | implementation 已交付；总控 / 最终组合独立双审及实际验收 |
| 拒绝日志的来源/阶段/安全原因缺失 | fixed in current slice；离线回归通过 | implementation 已交付；总控 / 组合审核和真实默认 log-file 核对 |
| 原绝对 CLI 首跑、真实非 FY PDF/Docling、再次普通增量及真实观察闭合 | fixed in current slice；**尚未执行** | 总控 / control 的真实 CLI acceptance；不能以离线通过豁免 |
| 官方实时响应变化、网络/风控、模型或转换环境失败 | requiring new issue or explicit user decision（仅实际发生并排查后裁决） | 总控 / 真实验收按直接原因分类；不改参数规避 |
| 原始调用唯一历史 source ID 不可追溯 | assigned to later work unit；当前已确认的证明限制 | Fins 维护者 / 如另需历史追溯，另立有证据的任务 |
| 未证实的无文字、跨页、自然年度等布局 | assigned to later work unit；继续 fail closed | Fins 维护者 / 新官方拒绝证据驱动任务 |
| 独立双审、accepted findings 修复复审、commit/push/draft PR 与交付核对 | 本子任务不拥有，尚未完成 | 总控 / 后续 gates；没有宣称 work unit pass |
