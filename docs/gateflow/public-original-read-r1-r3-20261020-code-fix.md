# R1–R3 code fix 回执

日期：2026-10-20。分支 `fix/public-original-read-r1-r3-20261020`，基线/当前 HEAD
`cd37d5759b1152eb1571fd410ff6275c30c83e25`。本轮为用户指定的唯一 fix writer；未派 agent、
未调用其它模型，未 commit/push/建 PR/merge、未改 live、未对外发消息。

## 范围与 gate

已读 AGENTS.md、Gateflow、goal/plan/control/implementation、正式 code-adjudication 及 C1 主控证据。
双路完整审核及正式裁决已收齐，允许进入本轮 fix。以正式 accepted 清单 D1–D4、C1–C4、M1、T1、T2、L1 为范围。
既有总控脏文件与审核报告只读；不改 goal、plan、control、既有实施回执、裁决和审核记录。

修复动机成立：D1/C1/D3/C4 有原文引用/语法和完整性直接反例；D2/C2 有实际懒构建与借用生命周期冲突；
D4/C3 是公共错误/参数语义在消费者层偏离 owner；M1/T1/T2/L1 是正式验收缺口。
无财报用途、主体、真假、年度或准入判断变更；storage snapshot 继续唯一持有资产身份和 opaque revision，
processor 继续唯一持有原文/结构/引用事实，runtime 继续持有参数、版本、分页及资源借用。
不改下载选文/primary/持久 schema，不加 fallback/兼容逻辑，不裁剪内容。

## 逐项修复与验证落点

以下“已修复”是 writer 的实现与自验结论；正式 finding 状态仍由后续双路受影响面复审及总控回写。

| ID | 正确 owner | 实际变更及 owner 级验证 |
| --- | --- | --- |
| D1 | `OriginalStructure` 的资产内 ID/引用索引 | 删除 target 分组及反推 target 的遍历；按 exact ID、全资产唯一性和 context/continuation 元素类型解析。保留 fact target 与 resource_target_* 原文声明字段，资源声明不作为合法分组。真实 Fs/public runtime 的 HTML/XHTML 合成输入覆盖非默认 fact target + 默认 resources/continuation、原文 span 回读、重复 ID、未决引用和资源原声明。旧错误 target 预期迁移到正确 owner 断言，无兼容分组。 |
| D2 | runtime 的只读缓存诊断 | 跳过尚未完成便利 processor 的 entry，诊断直接消费已建 processor，不触发 lazy accessor；已建候选原 revision 校验和 borrow cleanup 保留。实际 registry 计数验证先枚举 B，再对 A 使用坏 ref/table_ref 时只构建 A；既有 stale 诊断回归在完整受影响集重跑。 |
| D3 | 原文 HTML 词法关系 owner | 补 head、colgroup、optgroup、ruby 的确定省略边界，扩充 p 的合法块边界；父级结束/EOF 的省略闭合按允许父级收束，不再把所有 optional 标签无条件关闭。真实公开入口验证 head/body、行组、colgroup、option/ruby 的父子/兄弟与 closure；不能合法省略的 dt/thead、未闭 title 保持 partial/unknown。未引入 DOM 重建或第二 parser。 |
| D4 | 原文 runtime 公共错误 owner | 同一原文借用边界将缺失/删除文档映射 typed not_found；指定文件不在 snapshot 完整清单也返回 not_found。提示在当前 ticker/source_kind 重新 list_documents/list_document_assets，使用 exact filename/hash，不沿用旧 ref/table_ref 提示。Python 四 API 和实际 process→Host 的七种 missing 组合覆盖 code/hint；真实解码失败与物理损坏仍分别拒绝，不降为 missing；既有版本/参数/格式/consistency 错误保留。 |
| C1 | `original_format` 原文格式 owner | 一个 typed 判定同时产生文本/结构/inline 能力与索引语法；runtime 从同版 descriptor 媒体/后缀消费该判定，删除仅 `.xml` 的独立模式判断。XHTML/XML media、无格式后缀的 XML、XHTML 后缀均保持大小写；主控 `<P>A</p>` 真实 Fs/public runtime 反例为 partial/unknown，没有 explicit 小写闭合。 |
| C2 | entry/active borrow 生命周期 owner | 移除三类懒能力构建完成后对 runtime open 状态的错误二次拒绝；已取得 borrow 受 entry 资源计数保护，可以在 close retire 后完成。新 entry publication 与关闭后新读取仍受原关闭屏障约束。真实公开 text/structure/便利目录三条路径均在 entry 已发布、borrow 已取得后阻塞构建→close→释放 barrier；断言当前结果成功、关闭后新读失败、最后 release 清理 snapshot/retired/pending。另将既有“发布前关闭”测试从实际已在发布后的 registry hook 迁到真实 full snapshot 返回前，继续断言 close 后零 entry publication、零 processor 构建且 snapshot 清理。 |
| C3 | storage 文件名单组件准入 owner | 删除 runtime 对 `[ ] * ?` 的额外拒绝，继续复用 source_asset_name_collision_key 校验并 exact 匹配；不作 glob 展开、不取 basename、不改大小写。真实 Fs 枚举→原样回读三种字面量文件名；已有非法路径/非原样值测试保留。 |
| C4 | 同一完成索引的全资产引用完整性 | 构建时一次校验所有 continuation 边/共享长链/循环/类型/重复 ID/未知边界，并缓存状态与首跳位置。结构和 facts 的 parse_status 只来自全资产 diagnostics，与当前页/概念独立；投影不逐页再走长链。后页坏引用的首个 facts/结构页即 partial，各页 diagnostics 一致；1,000 跳共享尾链的六页读取不重复解析引用。 |
| M1 | provider outcome 的统一禁值断言 | 为四个新工具加入真实 Fs HTML 成功参数，严格断言参数域等于全部十三工具，按工具真源列表遍历成功/失败/取消 39 个 nested 投影；同时扫描两份 source 的实际 revision/private key/workspace/path。未放宽任何禁值，filename/hash/span 正常通过。 |
| T1 | 实际 process-backed provider + Host 截断交互 | 新联合测试让六条 occurrence 分三页，每页 facts 先被 Host 截为一项；一次省略 limit 的真实 fetch_more 取齐本页，再按 next_offset 进入下一页。校验资产、完整性、页内条数、末页状态、顺序、唯一 opening span，最终与公开 runtime 完整 occurrence 数组逐项相等，无漏重。 |
| T2 | runtime snapshot 竞争与资源转移 owner | 在真实 Fs 返回两个 full snapshot、尚未发布 entry 前设置 barrier，确定进入竞争分支。两公开枚举结果相等、两临时根不同、恰一胜方根存活且为 cache entry 所持 snapshot；败方立即清理，runtime close 后两根均消失。既有能力单构建测试独立保留。 |
| L1 | provider 的 LLM schema/说明与 README | 自足列出 qname.status 枚举和含义、quote 的值/类型、duplicate 的重复原属性语义及小例；说明目录 source_asset 字段/内容校验用途，全资产 parse_status 与资源 target 原声明边界。provider 概览和测试概览改为十三工具，并在实际 schema 断言这些说明。 |

主要新增回归：[test_original_read_review_regressions.py](../../tests/fins/test_original_read_review_regressions.py)。
工具/Host 与扫描落点为原有 `tests/host/test_fins_original_read_truncation_fetch_more.py`、
`tests/fins/test_fins_storage_provider.py`；测试 helper 仅扩展真实仓储发布的文件名、媒体、文档 ID 和字节输入，
未替代 parser/runtime 结果。D1 以正式裁决纠正原 plan 中 target 分组技术描述，未改冻结 plan 或删除原文承诺。

## 被验证版本与可取回源码

证据根 `W=workspace/tmp/public-original-read-r1-r3-20261020/`。
最终冻结版本为上述 HEAD + `W/code-fix-final.diff` + 新回归文件；完整 writer 文件快照为
`W/code-fix-source-final/`，34 文件逐项 SHA/size 为 `W/code-fix-files-final.json`，包括本轮四个生产 Python 文件、
新测试和此前 writer 的未变文件。manifest SHA-256：
`65421c455aa882c386d82224d24dc71af4fb65160a125059f8e3dcfa77b3d3a5`。
final diff SHA-256：`d47d5543b46a2f21182c15353ecc385dc70d80e7ac40889f5bc0b71cf3ad44bd`。
`W/code-fix-version-final.json` 保存 branch/HEAD/diff SHA、182 个 Fins 模块指纹及只读 gate/review 文档指纹。
新公开 API 输出另保存完整 Fins、utility、prompt 源码快照与逐模块指纹。hash 不替代实际保存字节。
初次冻结 `code-fix-source/`、`code-fix-files.json`、`code-fix.diff` 和 `code-fix-version.json` 也保留；
两次冻结间仅 `tests/fins/test_processor_read_consistency.py` 的真实 barrier/断言迁移，没有生产变更。
`W/code-fix-final-version-check.json` 核对最终快照、当前文件、API-8 的 182 模块和只读 gate/review 文档，所有 mismatch 为空。

| 本轮生产文件（相对 `dayu/fins/`） | SHA-256 | bytes |
| --- | --- | ---: |
| processors/original_content.py | ca61c6fe0a624ea01e6fad58ada15aba2dab03a61c140ee3d8c6972e5576c389 | 37190 |
| tools/read_runtime.py | 6a435e6528033b69eb7cd7e5d61935155de76e37731a5cce07c9da1dd90397d8 | 147485 |
| tools/fins_tools.py | 1d94898be489445b6d2375b2b004e24a9c1ff9a9e4c95d403facdc549891d28b | 80508 |
| tools/provider.py | bfe5900086aa4b7f779fe04f1ac3d83d77f13b8a7ded8650d37a7da536cc110e | 6929 |

生产修改只涉及 `processors/original_content.py`、`tools/read_runtime.py`、`tools/fins_tools.py`、
`tools/provider.py`；没有修改共享 `dayu.runtime`、Host 验证框架或 concepts schema shape。

## 验证命令、结果与失败修正

所有检查均在本库 `source .venv/bin/activate` 后运行。下列 `code-fix-*.command.json` 保存完整 argv/cwd，
对应 `.execution.json` 保存实际开始/结束、耗时、退出，`.stdout/.stderr` 保留完整原始输出。
`W/code-fix-validation-env.json` 保存最终 coverage 环境，临时 runner 为 `W/code-fix-run.py`。

- 初始 smoke：`source .venv/bin/activate && python -m pytest tests/fins/test_original_read_contract.py tests/fins/test_original_read_runtime.py -q`；工具执行回执退出 0，37 passed / 3 warnings，2.95 秒。仅初步实现，无本轮独占 stdout 文件，不作为最终版本放行证据。
- `code-fix-targeted-1`：三个原文测试文件，72 passed，退出 0。
- `code-fix-pyright-1`：退出 1，14 errors；均在新增测试的 `**args` 推断或 NotRequired 字段访问，改为显式 TypedDict 和键存在性断言，未 ignore/cast 掩盖生产错误。
- `code-fix-tool-tests-1`：7 failed / 112 passed，退出 1；新增测试误用 ToolFailedOutcome.failure，按真实 contract 改为 `.result`。
- `code-fix-targeted-2`：2 failed / 84 passed，退出 1；运行期间移动常量导致后两个新进程读取了中间源码而返回 execution_error。补回常量后停止修改运行中的源码，所有受影响断言在冻结版本重跑；该混版输出失效，不是最终证据。
- `code-fix-pyright-2`：退出 1，1 error；测试 TypedDict 使用 dict(...) 的推断不被接受，改为严格类型字面量。
- `code-fix-targeted-3`：195 passed，退出 0；随后仅新增更完整 HTML/XHTML target 合成输入、解码/损坏反例及测试类型修正。
- `code-fix-targeted-4`：203 passed，退出 0；源码与当前冻结版本相同。
- `code-fix-pyright-3`：全量 pyright 退出 0，0 errors / 0 warnings / 0 informations。

### 最终受影响测试与类型

完整受影响集实际运行 **1,453 项**：`code-fix-tests-final` 退出 1，**1 failed / 1,452 passed**，
96.72 秒。唯一失败是 C2 直接受影响的旧测试，其 registry hook 实际在 lazy entry 发布后，
错误声称“entry 发布前”并要求已取得 borrow 失败。修复的是测试同步边界，不修改/放宽生产契约：
改在真实 full snapshot 已取得且 entry 未发布时阻塞，断言 close 后拒绝 entry publication、
registry 零构建、资源清理；已发布 borrow 可完成由三条新公开回归独立验证。

只重跑受影响的整个一致性测试文件：`code-fix-consistency-final` **55 passed，退出 0，4.04 秒**。
其余 1,398 项在完整集同一生产源码下已通过；与重跑文件的 55 项合计当前 1,453 个唯一测试均有有效通过证据，
不把先前退出 1 写成一次全绿，也不为未变部分重复全量测试。完整运行与最终版本之间仅上述一处测试 boundary 变化，
生产/依赖/配置均未变，故其余断言和覆盖数据仍有效。3 条 warnings 均为既有 edgartools deprecation。

完整实际命令（环境见 `code-fix-validation-env.json`；runner 仅保存 argv/输出/退出）：

```bash
source .venv/bin/activate
export COVERAGE_FILE=/Users/leo/workspace/dayu-agent-r/workspace/tmp/public-original-read-r1-r3-20261020/coverage-code-fix/.coverage
export COVERAGE_PROCESS_START=/Users/leo/workspace/dayu-agent-r/workspace/tmp/public-original-read-r1-r3-20261020/coverage-code-fix/.coveragerc
coverage run --rcfile /Users/leo/workspace/dayu-agent-r/workspace/tmp/public-original-read-r1-r3-20261020/coverage-code-fix/.coveragerc -m pytest -p no:pytest_cov tests/fins/test_original_read_contract.py tests/fins/test_original_read_runtime.py tests/fins/test_original_read_review_regressions.py tests/fins/test_read_search_regression.py tests/host/test_fins_original_read_truncation_fetch_more.py tests/fins/test_fins_storage_atomicity.py tests/fins/test_fins_storage_provider.py tests/fins/test_storage_asset_filename_contract.py tests/fins/test_fins_read_runtime.py tests/fins/test_read_runtime_semantic_ownership_guards.py tests/fins/test_processor_read_consistency.py tests/fins/test_processor_registry.py tests/fins/test_financial_read_contracts.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_cn_annual_report_source.py tests/fins/test_sec_pipeline_download.py tests/documents/test_processors.py tests/tools/test_combined_tools_acceptance.py tests/host/test_toolruntime_truncation_fetch_more.py tests/runtime/test_scene_prepare.py --basetemp /Users/leo/workspace/dayu-agent-r/workspace/tmp/public-original-read-r1-r3-20261020/code-fix-pytest-final -q
coverage run --rcfile /Users/leo/workspace/dayu-agent-r/workspace/tmp/public-original-read-r1-r3-20261020/coverage-code-fix/.coveragerc -m pytest -p no:pytest_cov tests/fins/test_processor_read_consistency.py --basetemp /Users/leo/workspace/dayu-agent-r/workspace/tmp/public-original-read-r1-r3-20261020/code-fix-pytest-consistency-final -q
pyright
```

最后全量类型检查 `code-fix-pyright-final`：**退出 0，0 errors / 0 warnings / 0 informations**，37.10 秒；
对应最终测试文件，不复用早期类型结果。仅 CLI 新版提示，未升级依赖。
实际 Host 三份完整回执保存在 `W/code-fix-host-joint/`，receipt 关联本次测试实际持久 basetemp 路径及 SHA/size，
包含文本、结构/namespace/facts 和新增 facts 三页联合续读，不用 Python 成功冒充进程工具验收。

### 完整文件覆盖率

coverage 配置复制原 release 的完整 `source=dayu/fins`、`concurrency=multiprocessing`、`parallel=true`；
没有新增 exclude/omit，没有按改动行、函数子集或全包平均缩分母。合并本次两个运行的父子数据，
不混入旧 release 数据。`code-fix-coverage-{combine,json,report}` 均实际退出 0：

```bash
coverage combine --rcfile /Users/leo/workspace/dayu-agent-r/workspace/tmp/public-original-read-r1-r3-20261020/coverage-code-fix/.coveragerc --keep /Users/leo/workspace/dayu-agent-r/workspace/tmp/public-original-read-r1-r3-20261020/coverage-code-fix
coverage json --rcfile /Users/leo/workspace/dayu-agent-r/workspace/tmp/public-original-read-r1-r3-20261020/coverage-code-fix/.coveragerc -o /Users/leo/workspace/dayu-agent-r/workspace/tmp/public-original-read-r1-r3-20261020/coverage-code-fix/coverage.json
coverage report --rcfile /Users/leo/workspace/dayu-agent-r/workspace/tmp/public-original-read-r1-r3-20261020/coverage-code-fix/.coveragerc -m
```

所有 17 个本 work unit 新增/修改生产 Python 完整文件均 **≥80%**。原始全包报告/JSON 和全部父子数据保留，
完整逐文件缺失行、分母及 excluded_lines 见 `W/coverage-code-fix/modified-files.json`（这些文件 excluded_lines 全为空）。

| 文件（相对 `dayu/fins/`） | 覆盖率 | statements |
| --- | ---: | ---: |
| cancellation.py | 100.00% | 13 |
| domain/original_read_contract.py | 100.00% | 136 |
| pipelines/report_original_source.py | 98.33% | 60 |
| processors/original_content.py | 97.26% | 402 |
| processors/sec_form_section_common.py | 80.21% | 1122 |
| storage/_fs_source_integrity.py | 86.86% | 624 |
| storage/_fs_source_snapshot.py | 89.34% | 422 |
| storage/repository_protocols.py | 82.44% | 410 |
| tools/cache.py | 96.92% | 65 |
| tools/error_contract.py | 100.00% | 14 |
| tools/fins_limits.py | 100.00% | 18 |
| tools/fins_tools.py | 86.50% | 400 |
| tools/provider.py | 91.23% | 57 |
| tools/read_runtime.py | 85.64% | 1121 |
| tools/read_runtime_helpers.py | 80.34% | 473 |
| tools/result_types.py | 100.00% | 143 |
| tools/search_engine.py | 82.55% | 470 |

归并有一条 CoverageWarning：某子进程 `.coverage…pid14981.XFkwrZJx` 无法作为 coverage 数据读取。
该 53,248-byte 原始 SQLite 文件原样保留；只读复核 integrity=ok，但 coverage_schema/meta 和所有测量表均零行，
见 `code-fix-coverage-warning-{inspection,detail}.json`。不猜测退出根因，不修写数据或删除该警告。
其余有效数据仍按完整文件 statements 计数，缺失执行不会从分母删除；上述阈值不依赖该空测量文件。

### 当前源码真实公开 API

既有 utility 未修改，在同一个隔离 input-workspace 和新的独占 output-dir 实际执行：

```bash
source .venv/bin/activate
python utils/verify_public_original_read_r1_r3.py --source-workspace /Users/leo/workspace/portfolio-manager-v2/workspace --workspace-root /Users/leo/workspace/dayu-agent-r/workspace/tmp/public-original-read-r1-r3-20261020/input-workspace --evidence-root /Users/leo/workspace/portfolio-manager-v2/orch/workpapers/g0-refactor-implementation-20261020 --output-dir /Users/leo/workspace/dayu-agent-r/workspace/tmp/public-original-read-r1-r3-20261020/development-api-8-code-fix
```

`code-fix-api-8` 外层/程序**退出均 0，270.93 秒，1,774 次完整公开调用**。
实际 Python `.venv/bin/python`，dayu module 为本库源码，版本/依赖/模块指纹见新 `receipt.json`。
所有 runtime 仅指向隔离副本；没有在调用方源目录启动 runtime，没有下载/上传/预处理、改 meta/manifest/revision，
内容均从 DefaultFinsRuntime/read runtime 公开方法获得，外部字节指纹仅用于验真。

- 六批原 53 次调用重放，原 ATAT page not_supported 单列保留；600660/0700 的既存 PDF/Docling 正向阅读仍通过。
  ATAT/FUTU 三次 get_table 的 data/table_ref/table_type/caption/row_count/col_count/within_section/is_financial 与 API-7 逐字段相等。
- 七份锚文件及 TSM 附件的原文/namespace/fact/context/span 回读断言在当前 parser 同版重验；MSFT 三条 TradingSymbol
  保留三个不同 contextRef 且全部 resolved，无按值去重。
- ASML 24,864,734 码点，cold/warm 各 380 页拼齐、尾部/EOF 与严格原文相等，逐调用耗时合计 50.640 / 48.244 秒；
  cold 指新 runtime 首次遍历（每页仍复用已完成能力），不清 OS cache、不声称每页都冷。进程 high-water RSS 969,932,800 bytes，无新增 SLA。
- TSM 主件/附件身份、原始 href 关系及完整续读再次验证；reading primary 仍是附件。主件 SEC SGML 仍如实 partial，
  未决父链 unknown，所需链接局部定位可回读，未把原件修写为 complete。
- 1,236 份必要输入的原件/副本 before/after 全等；每次完整返回/错误、response SHA、时间/RSS 可取回。
  新回执 `development-api-8-code-fix/{receipt,calls,input-fingerprints-before,input-fingerprints-after}.json`；
  汇总 `W/code-fix-api-8-summary.json` 另核对所有响应保存 SHA，全部相符。

API-8 的 182 模块指纹与最终源码全等，API 运行至最终冻结只变化一处测试同步边界，因此无需再次重跑未受影响的 1,774 次调用。

## README decision

已实读 Fins README 的 Agent更新约束和 tests README 更新边界。更新 Fins 已实现公共契约：格式 owner、
exact 文件名、not_found 恢复、资产内引用、全资产完整性与 active borrow 跨 close；
tests README 更新实际新回归/Host facts 分页和十三工具禁值扫描。
本轮 config/prompt、安装/CLI/工作区布局/用户工作流、分层装配、Engine/Host 生产机制均未改变，
不触发这些 README 的职责更新；原 config README/tools.md 及相关有效装配测试保留，不机械扩写。

## 旧证据适用性与分类风险

原 `release-source`、`release-files.json`、release 测试/coverage/API-7、controller probe 和审核报告原样保留。
未变 storage 身份/角色/持久 schema、下载选文、PDF/Docling、数值/财务处理和原文窗口坐标算法的旧证据，
可在核对保存源码/命令/结果后支持这些未变 owner 的事实；实核 API-7 的 182 模块中仅本轮四文件改变、178 文件原样。
不以旧 pass 代替本轮被改变的引用、格式、
闭合、完整性、错误、懒构建/诊断与工具说明断言。最终受影响集和新 API 以本回执的当前同版结果为依据。

| 风险/未覆盖 | 分类 | owner / destination |
| --- | --- | --- |
| D1–D4、C1–C4、M1、T1、T2、L1 | fixed in current slice（writer 自验，待复审） | 当前 writer → 本回执/同版证据；总控 → 双路受影响面 re-review 核销，不据此改写既有裁决。 |
| S1 实际供应商对 itemless concepts schema 的接受度 | requiring new issue or explicit user decision；沿正式 deferred-with-owner，非阻塞本地 draft | Provider/Engine owner 与总控 → 用户另授 merge 后的 sync-to-live/实际出站验收；没有已证 vendor 拒绝，本轮不扩共享验证框架。 |
| CSS/脚本/浏览器可见性、跨资产 inline document set、XBRL transformation/业务解释 | assigned to later work unit | Fins capability owner / 调用方 → 新需求独立立项；保留 unknown/css_evaluated=false 和原文。 |
| LRU 非总字节硬上限；同步 storage/第三方阻塞段无硬中断 | assigned to later work unit | Fins runtime owner → 容量/硬时限需求；当前合作式取消、borrow cleanup 与 Host accept 屏障继续受测。 |
| SEC 无 durable original_main；OLD 同输入动态对照未做 | assigned to later work unit | ingestion/storage provenance owner / 总控后续对照工作 → 既有实施/审核 residual destination，不扩大本轮范围。 |
| merge/live 安装与真实 CLI/Python 同版复验 | requiring new issue or explicit user decision | 用户另授 merge 后总控推进；当前未改 live、未声称 vendor/live 可用。 |

writer 范围内无未完成修复、未分类风险或未解决验证失败。全部代码、测试、README 与 utility 已冻结，
最终 checks 后仅整理本回执和新的验证/版本记录，没有再改运行源码。
下一入口：总控读取本回执，进入 `fix -> 受影响面 re-review` 的双路复审并裁决 accepted 状态；
之后由总控依既有授权处理 draft PR。用户本次禁止 writer commit/push/建 PR，因此本轮停在冻结交付。
本回执不代表总控/双路复审放行，不是 review-pass、draft-PR-pass 或 final closeout。
