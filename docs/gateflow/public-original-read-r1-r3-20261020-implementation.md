# R1–R3 implementation / validation 回执

日期：2026-10-20。分支 `fix/public-original-read-r1-r3-20261020`，base/HEAD `8bf8daec8a022fd705e6cfe32c4283605f1fe6ca`。唯一 implementation writer；未启动其它 agent，未 commit/push/建 PR/merge，未改 live、调用方工作区或原件。plan-pass 依据 control 与 plan-pass 文件，按已批准唯一 slice 实施。

## 状态

唯一 implementation slice 已完成实现与验证，可交总控冻结当前字节并进入完整双路 Deepreview。当前没有 writer 范围内未完成项或未解决验证失败；不宣称 code-review-pass、draft-PR-pass 或 live-pass。总控负责审核、裁决、必要修复派发及 PR。

## 实际改动与唯一 owner

- storage：完整复制过程保留实际 SHA-256/size，经 full snapshot `get_content_identity` 暴露；light 明确拒绝。descriptor 携带已校验声明角色，删除 inspection 内重复角色容器；不改持久 schema、revision、primary 选择或下载链。
- CN/HK 原件 owner：`project_report_original` 消费 typed descriptor，仍要求唯一显式 original 且为 PDF；`read_report_pdf` 使用 storage 实际身份，保留 exact publication、locator、非空与取消规则，不重复计算摘要。
- 原文 domain/processor：严格 UTF-8/BOM 码点窗口；保真 token、原始属性/namespace、parent/ancestors 及显式 unknown 父级、可省略闭合/未知边界、CDATA/处理指令；非数值 occurrence 的原值、format、context/target 及资源目标声明、可见性声明、continuation/exclude 引用。长字符串、属性、祖先与 diagnostics 受显式预算约束，完整跨度可公开回读；不转换业务真假。
- read runtime/cache：四个新 public 方法；同一 entry 下按资产懒建文本/索引和便利 primary processor，key 含 source kind；身份来自 active full borrow，按 opaque publication revision 失效。缓存不保存请求 token/范围/预算；旧 active borrow 与新发布结果各自同版。
- 便利章节取消任意 5,000 字裁剪；目录/章节增加实际 source_asset，章节明确 section_view。原九种便利能力保留。
- tools/config：十三个 process-backed read 工具，同一 runtime 结果投影；原文页与 Host 显示截断分别续读，先一次省略 limit 的 fetch_more 取齐本页。namespace 发现、概念对象字段及最小例、hash 标签和 has_financial_data 范围进入原文 schema/现有 fins-read 指引。
- Host 当前字段校验只允许标量数组 items schema（`dayu/runtime/tool_call_projection.py`）；未修改 Host/runtime 机制。concepts 仍为已批准对象数组，工具 schema 用 array 与完整条目说明表达，条目不删字段、不 loose parse，由 runtime owner 严格拒绝缺项、额外键或非法类型。真实结构发现→facts process 工具联合测试验证此路径。
- 验收 utility 只从公开 DefaultFinsRuntime/read runtime 读取，原件字节只作外部指纹验真。allowlist 复制目标 source 完整文件及必要 identity/meta/manifest 导航，全部新 runtime 指向本库隔离副本；不下载、上传、预处理或用私有 parser 替代 API。

## 确切文件范围

生产源码：

- `dayu/fins/cancellation.py`
- `dayu/fins/domain/original_read_contract.py`
- `dayu/fins/pipelines/report_original_source.py`
- `dayu/fins/processors/original_content.py`
- `dayu/fins/processors/sec_form_section_common.py`
- `dayu/fins/storage/_fs_source_integrity.py`
- `dayu/fins/storage/_fs_source_snapshot.py`
- `dayu/fins/storage/repository_protocols.py`
- `dayu/fins/tools/cache.py`
- `dayu/fins/tools/error_contract.py`
- `dayu/fins/tools/fins_limits.py`
- `dayu/fins/tools/fins_tools.py`
- `dayu/fins/tools/read_runtime.py`
- `dayu/fins/tools/read_runtime_helpers.py`
- `dayu/fins/tools/result_types.py`
- `dayu/fins/tools/search_engine.py`

测试：

- `tests/fins/test_cn_annual_report_source.py`
- `tests/fins/test_fins_read_runtime.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_original_read_contract.py`
- `tests/fins/test_original_read_runtime.py`
- `tests/fins/test_processor_read_consistency.py`
- `tests/fins/test_read_runtime_semantic_ownership_guards.py`
- `tests/fins/test_read_search_regression.py`
- `tests/host/test_fins_original_read_truncation_fetch_more.py`
- `tests/runtime/test_scene_prepare.py`
- `tests/tools/test_combined_tools_acceptance.py`

验收辅助代码：`utils/verify_public_original_read_r1_r3.py`。文档：`dayu/fins/README.md`、`dayu/config/README.md`、`dayu/config/prompts/base/tools.md`、`tests/README.md` 及本回执。

冻结字节及逐文件 SHA/size：`workspace/tmp/public-original-read-r1-r3-20261020/release-source/`、`release-files.json`。总控维护的 goal/control/plan/review 文件保持只读，不在 writer 快照内。

## 验证事实与证据

证据根 `W=workspace/tmp/public-original-read-r1-r3-20261020/`。以下均实际激活 `.venv` 后执行，非基线或历史 live 复用；实际子进程 argv、环境覆盖、开始/结束、退出均保存在对应 `.command.json` / `.execution.json`。Python 为本库 `.venv/bin/python`；公开 API module 为本库源码树，distribution/dependency 版本及所有 Fins 模块 SHA/size 见 API receipt。

### 测试与类型

- 完整受影响回归：**1,399 passed，退出 0，78.63 秒**。3 条第三方 edgartools deprecation warnings 不属于类型错误。实际输出 `W/release-tests.stdout/.stderr`，执行回执 `W/release-tests.execution.json`。
- 最后全量类型检查：`source .venv/bin/activate && pyright`，**退出 0，0 errors / 0 warnings / 0 informations**。实际输出 `W/release-pyright.stdout/.stderr`，工具实际退出记录 `W/release-pyright.execution.json`；CLI 新版提示未触发依赖升级。
- 最终实际测试 argv（完整文件集，新增搜索回归用于取消 owner import 迁移后的完整文件覆盖，不缩分母）：

```bash
source .venv/bin/activate
coverage run --rcfile /Users/leo/workspace/dayu-agent-r/workspace/tmp/public-original-read-r1-r3-20261020/coverage-release/.coveragerc -m pytest -p no:pytest_cov tests/fins/test_original_read_contract.py tests/fins/test_original_read_runtime.py tests/fins/test_read_search_regression.py tests/host/test_fins_original_read_truncation_fetch_more.py tests/fins/test_fins_storage_atomicity.py tests/fins/test_fins_storage_provider.py tests/fins/test_storage_asset_filename_contract.py tests/fins/test_fins_read_runtime.py tests/fins/test_read_runtime_semantic_ownership_guards.py tests/fins/test_processor_read_consistency.py tests/fins/test_processor_registry.py tests/fins/test_financial_read_contracts.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_cn_annual_report_source.py tests/fins/test_sec_pipeline_download.py tests/documents/test_processors.py tests/tools/test_combined_tools_acceptance.py tests/host/test_toolruntime_truncation_fetch_more.py tests/runtime/test_scene_prepare.py -q
```

运行环境覆盖：

```text
COVERAGE_FILE=/Users/leo/workspace/dayu-agent-r/workspace/tmp/public-original-read-r1-r3-20261020/coverage-release/.coverage
COVERAGE_PROCESS_START=/Users/leo/workspace/dayu-agent-r/workspace/tmp/public-original-read-r1-r3-20261020/coverage-release/.coveragerc
```

coverage 使用独占配置 `W/coverage-release/.coveragerc`，`concurrency=multiprocessing`、`parallel=true`，以 `coverage run -m pytest -p no:pytest_cov` 避免 pytest-cov 双 collector。`coverage combine --keep`、`coverage json` 与 `coverage report -m` 均实际退出 0；精确 argv/退出在 `W/release-coverage-{combine,json,report}.command.json/.execution.json`，完整输出同前缀 `.stdout/.stderr`。保留父子原始 `.coverage.*`；未添加生产行 exclude/omit，也不按改动行或全包平均计算达标。

### 逐生产文件覆盖率

所有 16 个新增/修改生产 Python 文件均达到 **≥80%**。每个文件的完整未覆盖行及分母见 `W/coverage-release/modified-files.json`；原始完整 JSON 为同目录 `coverage.json`，逐行报告 `W/release-coverage-report.stdout`。

| 生产文件 | 覆盖率 | 完整文件 statements |
| --- | ---: | ---: |
| `dayu/fins/cancellation.py` | 100.00% | 13 |
| `dayu/fins/domain/original_read_contract.py` | 100.00% | 136 |
| `dayu/fins/pipelines/report_original_source.py` | 98.33% | 60 |
| `dayu/fins/processors/original_content.py` | 95.98% | 373 |
| `dayu/fins/processors/sec_form_section_common.py` | 80.12% | 1122 |
| `dayu/fins/storage/_fs_source_integrity.py` | 86.86% | 624 |
| `dayu/fins/storage/_fs_source_snapshot.py` | 89.34% | 422 |
| `dayu/fins/storage/repository_protocols.py` | 82.44% | 410 |
| `dayu/fins/tools/cache.py` | 96.92% | 65 |
| `dayu/fins/tools/error_contract.py` | 100.00% | 14 |
| `dayu/fins/tools/fins_limits.py` | 100.00% | 18 |
| `dayu/fins/tools/fins_tools.py` | 86.25% | 400 |
| `dayu/fins/tools/read_runtime.py` | 85.53% | 1113 |
| `dayu/fins/tools/read_runtime_helpers.py` | 80.34% | 473 |
| `dayu/fins/tools/result_types.py` | 100.00% | 143 |
| `dayu/fins/tools/search_engine.py` | 82.55% | 470 |

### 开发树真实公开 API

最终行为版本命令：

```bash
source .venv/bin/activate
python utils/verify_public_original_read_r1_r3.py --source-workspace /Users/leo/workspace/portfolio-manager-v2/workspace --workspace-root /Users/leo/workspace/dayu-agent-r/workspace/tmp/public-original-read-r1-r3-20261020/input-workspace --evidence-root /Users/leo/workspace/portfolio-manager-v2/orch/workpapers/g0-refactor-implementation-20261020 --output-dir /Users/leo/workspace/dayu-agent-r/workspace/tmp/public-original-read-r1-r3-20261020/development-api-7
```

实际结果：**外层及程序退出均 0；1,774 次完整公开调用**。证据 `W/development-api-7.execution.json`、`W/development-api-7.stdout/.stderr`、`W/development-api-7/receipt.json` 与 `calls.json`；每次输入、完整返回/错误、耗时、RSS 和返回文件 SHA 均有独立文件，不是裸 pass。`W/development-api-7-summary.json` 保存复核汇总。

- 六批原 **53** 次调用实际重放；原 `atat-page1` 的 not_supported 单列并保持，其余正向导航/阅读保留。600660/0700 的既存 PDF/Docling sections/page/cover 均经原公开入口，无下载或重新转换。ATAT/FUTU 三次表格的 data、table_ref、table_type、caption、row/col、within_section、is_financial 与历史完整返回逐字段相等，比较结果在 summary；不要求新增 source_asset 后 JSON hash 与旧版相等。
- 七份原始锚文件及 TSM 附件经公开四 API；先实际读取结构中 xmlns 原声明取得 URI，再查询 expanded concepts，51 个保存锚的实际原文、fact node、context 定位逐一经公开文本窗口回读。MSFT 三条 TradingSymbol 均保留，3 个 contextRef 和 3 份 context span 各不相同；不输出财年、用途或报告准入解释。
- 七份原文逐页 cold/warm 遍历均等于严格原文，包含 5,000 之后及 EOF；TSM 附件另完整续读并与隔离副本原文相等。ASML 24,864,734 bytes/码点，每轮 380 页：首次文本遍历调用耗时合计 **46.939 秒**，第二次 **46.786 秒**；首次结构发现 **1.441 秒**。本次进程 high-water RSS **983,072,768 bytes**。这些是实际测量，无额外 SLA。cold 标签指新 runtime 的首次资产/能力获取及第一次遍历；资产枚举先构建 source entry，后续冷遍历窗口也会复用已完成文本；warm 为第二次遍历，不声称清 OS cache 或每页都冷。
- TSM 主件 `tsm-6k_20220812.htm` 与附件 `tsm-ex991_18.htm` 的实际 SHA/size 分别与任务书 34,492 / 10,997,629 bytes 一致。主件 href opening、链接内部原文、附件开头及全文均公开回读；reading primary 始终是附件。
- TSM 主件原件包含 SEC SGML `<DOCUMENT>/<TYPE>/<TEXT>` 外层。API 如实 `parse_status=partial`，不伪造完整 HTML 树；未决父级 `parent_status=unknown,parent=None`，未知上层使 ancestors_complete=false。所需链接局部父级 resolved、闭合 explicit、原文 span 可精确回读。这是已批准 partial 合同的实际返回，不能把它解释为完整零事实；没有改原件或强行改成 complete。
- 每次 runtime finally close；同 runtime 暖读、新 runtime 重开验证一致。真实 Fs owner 测试另覆盖 filing/material 同 ID、空资产、无声明摘要、A→B/同 bytes 重发、旧 active borrow 与新 publication 各自同版、取消/失败/close/eviction/cleanup 等；版本故障注入仅在测试隔离 Fs 资产。
- allowlist 复制及读取共 **1,236** 个必要原件/导航文件。原件与副本 before/after SHA/size 全等，见 `W/development-api-7/input-fingerprints-{before,after}.json`；不复制调用方业务产物/config/secrets/staging/locks/jobs，不重写 meta/manifest/primary/revision。

源码对应：API-7 实际执行时完整 Fins 源码、utility 与 prompt 保存于 `W/development-api-7/source-snapshot/`；最终全部 16 个新增/修改生产 Python 文件 SHA 与当前开发树、测试版本逐项相等，没有 docstring 例外。工作树完整 writer 文件快照与 SHA/size 为 `W/release-source/`、`release-files.json`。验证之后仅写入本回执，不再修改生产/测试/utility/prompt/README。
### 工具 / Host 联合回执与修复追踪

真实 Fs→实际 process-backed provider→Host ToolRuntime→一次省略 limit 的 fetch_more，验证文本、结构、namespace 实际发现及非数值 facts；Fins 当前页与 Host 本页显示截断各自保留，取齐后才按 next_start/next_offset 前进。完整合成输入返回保存在 `W/host-joint-release/`（`receipt.json` 记录原 pytest 路径、保存文件 SHA/size，关联 `release-tests.execution.json`）；不能用 Python 原文分页代替此证据。

中途失败原样保留：旧 eager cache/角色 raw-meta 夹具/旧工具列表/section 精确键断言随 owner 迁移修正；无效 upload Markdown 夹具改为真实下载声明；Host 不支持 pattern/嵌套 items schema 的真实错误促成 provider 合同修复。后续 TSM 原文回执暴露未知父链过度确定，已在 parser 修复；nil/lang 前缀、扩展属性歧义与极长属性名不完整标志均补 owner 测试并完成修复。`development-api-1…6` 及所有阶段测试/pyright日志只是本轮早先版本证据，不冒充最终 API-7/release-tests 版本，不覆盖历史 live 回执。


## Docs decision

已实读并遵循 Fins README 的 Agent更新约束、tests README 更新边界和 config README 职责。Fins 文档更新已实现公开能力/坐标/角色/唯一缓存；tests 文档更新已有 owner、真实 Fs、Host 联合与装配入口；config 文档只更新指引及装配说明。tool_discovery.json 未变，无新 limit 键，无 loader 契约变化。根 README 的最终用户 CLI/安装/初始化/工作流、dayu README 分层装配、Engine/Host 生产机制均未变化，故不修改这些 README。

## 未完成项与分类风险

当前 writer 范围没有未完成项、外部 blocker 或未分类风险。未执行的下一步为总控双路 Deepreview/裁决及 PR，owner=总控，destination=本 work unit 的 code review gate；本回执不替代独立审核。

| 项目 | 分类 | owner / destination |
| --- | --- | --- |
| R1–R3、实际身份/选件、原文/结构/facts、分页/缓存/取消、角色消费者、工具/Host/scene、实际输入与覆盖率 | fixed in current slice | implementation writer → 本回执证据，交总控完整审核；writer 范围内验证失败均已修复，正式 code-review finding 状态由总控裁决。 |
| TSM SGML 未决外层不能被标为已知父链 | fixed in current slice | parser owner → 原文诊断、unknown parent 状态和真实回读；不是通过猜测修复输入。 |
| CSS/脚本/浏览器可见性、跨资产 inline document set、XBRL transformation 与业务解释 | assigned to later work unit | Fins capability owner / 调用方 → 新需求独立立项；当前明确 unknown/css_evaluated=false，保留原文。 |
| 同步 storage/第三方阻塞段的物理硬中断 | assigned to later work unit | Fins/runtime owner → 将来若提出硬时限，再独立处理；当前检查点取消、资源收口与 Host accept 屏障已验证。 |
| LRU 以 entry 数计上限，不是总内存字节硬上限 | assigned to later work unit | Fins runtime owner → 将来容量需求；当前已测 ASML RSS/耗时、分页有界，不新增全局 cache manager。 |
| SEC 没有独立 original_main durable 角色 | assigned to later work unit | ingestion/storage owner → 将来若要求机器保证原始提交主件，再设计 provenance；当前 unrecorded、显式选择与 href 回读已满足本 goal。 |
| merge、live sync 与实际安装 Python/CLI 同版复验 | requiring new issue or explicit user decision | 用户另授 merge 后由总控推进；当前未改 live，未声称安装环境已可用。 |
