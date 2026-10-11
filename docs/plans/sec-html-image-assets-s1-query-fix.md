# SEC HTML 图片资产 S1 query/fragment 修复记录

- Work unit：sec-html-image-assets；gate：fix；唯一 approved slice：S1；finding：accepted C7 / mimo NEW-001。
- Branch：fix/sec-html-image-assets；accepted plan/HEAD：771299b8244e5cb25ce8f943ab41671d8e59e16c；真实旧生产基线：297bfbbc67b7d7468e3dfb6669a3385c4dd10d18。
- 已读取根 AGENTS、Gateflow、goal、approved plan、原两路 review、root195654、原 code-fix artifact/JSON、205113/210925 re-review、root212519 与公开 query probe；原记录保持历史。
- 状态：**C7 已实施并完成新代码验证，待总控独立双路 re-review**。本 worker 不宣称 review gate / accepted slice / final closeout pass。
- 新 fix artifact：docs/plans/sec-html-image-assets-s1-query-fix.md；本轮验证真源：docs/validation/sec-html-image-assets-query-fix.json。

## 根因与 owner

动机成立但属低严重度可用性问题：最终 path 安全的必要图片，因为将丢弃的 query/fragment 含普通 % 或 %GG 而提前 typed 失败。直接同源证据是 srcset 对完整普通 token 预检、URL helper 在取 path 前对完整 value 预检，以及总控四个 typed reject / 一个 accepted 对照。approved plan 第108行要求 path 严格 %HH、候选先标准 urljoin 再去最终 query/fragment。

只在 SEC downloader 两个语义边界修复：srcset 仍持有有限分界/descriptor/data 语法，普通 URL 交共享 URL/path owner；_validate_image_address_text 对原始全地址保留 Cc/Cs 与反斜杠检查，raw percent 与单次解码规则约束 path。data 完整 token 的百分号语法保留。candidate/base 的标准 urljoin、完整分号 path、首 base/首属性、origin/完整申报边界、编码分隔/点段、严格 UTF8、%25、单组件 storage name 与碰撞契约均未迁移或放宽。

本 worker 修改现有文件仅 sec_downloader.py、test_sec_html_image_assets.py、Fins/tests README；新增本文与本轮 validation JSON及独立 workspace/tmp root。真实 validator 沿现有可复核矩阵执行，无需修改。其余三生产 owner、另外三测试、根 README、storage/schema、6-K 筛选、package0.1.4 与未发布 download contract v1.3.0 均未修改；没有外站递归、数值解析或 workflow fallback。

## Findings 与 owner contract 证明

- C7：已实施修复待 re-review。三入口及 base query/fragment 百分号正例、file/directory/query-only/fragment-only 的标准解析、semicolon/%25 同 canonical 去重、exact HEAD/GET、仓储 name/URI/size/hash/完整 descriptor fingerprint、普通 retry/repeat 通过。非法 path %/二次 triplet/编码分隔/点段/UTF8 继续 typed 失败，fresh/upgrade 在 begin 前失败且零图片请求，旧 publication 保留；合法新候选 GET404 经过真实 Fs rollback，fresh MISSING、upgrade 元数据/revision/bytes 保留，解除故障后发布并幂等快跳。
- root 原四个失败输入与一个对照均经公开 list_filing_image_files 新探针接受，canonical identity 正确，禁止网络；五项结果在 query-owner-probe.json。
- C1/C3/C4/C5/C6 沿 root212519 的已修复裁决；原对应 owner 回归在新 broad 内通过，不改写原 review。C2 保持 rejected-with-reason / 未修复（未采纳），无 Cf 黑名单。
- srcset path 非法百分号测试迁移到 URL/path owner 级 typed contract；srcset 专属错误断言继续验证 data 百分号与列表分界，未为旧测试保留兼容判断。

## 最终验证

全部测试及 pyright 命令先 source .venv/bin/activate；精确 argv/cwd、非敏感显式开关、exit、原始日志/hash 与前后八文件 hash 在新 JSON 中。最终生产/测试修改后冻结，collect/broad/pyright/real及公共 probe 前后一致。

| 验证 | 新实际结果 |
| --- | --- |
| owner test_sec_html_image_assets.py | exit0；332 passed |
| collect tests/fins tests/cli/test_fins_commands.py | exit0；3773 collected |
| broad 同一范围 + clean coverage | exit0；3764 passed / 9 skipped |
| 全仓 pyright | exit0；0 errors / 0 warnings / 0 informations |
| 公开总控输入 probe | exit0；5 accepted / identity asserted |
| opt-in 真实 CLI validator | exit0；2 passed / 0 skipped / 24 CLI |
| git diff --check；临时 runner/probe pyright | exit0 |

覆盖率来自本轮独立 rawdata；清除 Coverage 默认 exclude/partial 规则后重新报告，rawdata hash 前后不变，未 append/exclude/ignore。四 owner 均无 excluded lines、均 >=80%，完整 line map、原默认报告及新 clean 报告均保留；新报告命令与 policy 在 JSON 中。

| Owner | Clean coverage |
| --- | --- |
| sec_downloader.py | 95.06% |
| sec_download_filing_workflow.py | 84.16% |
| sec_pipeline.py | 89.54% |
| sec_rebuild_workflow.py | 85.93% |

真实运行根：/Users/leo/workspace/dayu-agent-r/workspace/tmp/sec-html-image-assets-query-fix-hrox53vb。9539个 gitarchive 文件逐字节核对完成，旧生产四owner与 git show297身份一致；旧 CLI origin/version/fingerprint 被 observer 实证。两例各12命令：fresh、两个正式 baseline seeds、普通补齐、necessary image GET404 fresh/upgrade、旧 publication exact 保留、retry、四成功 base repeat。四注入故障 exit1 是验收内的真实失败，不作为失败尝试隐藏。每例全部已选 HTML 独立解析，目标引用为2019 17/15与2025 12/12；完整 filing 15+13=28，额外image_1a.jpg只记必要依赖。四成功 base共112图片读回，全部exact GET/descriptor source_url、仓储 URI/size/SHA256、metadata/manifest/revision与完整集合指纹断言成立。

原业务 workspace与原证据目录零写；本轮无需读取原业务base或TCOM撤回worktree。真实根不运行processor/LLM，未宣称OCR、财务数值或真实processed重算通过。身份只内存复用，最终新evidence/artifact值级无泄漏检查仅存布尔值，不保存UA值、请求头或完整env。

## 历史、异常与冻结界限

原 implementation/code-fix两份JSON及两个原实施/fixartifact、goal/plan/reviews保持开始hash；旧3646/3637/9与旧coverage是原冻结版本历史，未当作本轮结果。新完整8文件身份见下和validation JSON，真实矩阵/日志库存全部新建；本轮没有测试/类型/网络失败或中止。

范围审计首次 exit1 的原因是 control 在本worker期间新增总控后续review路由确认。只此受保护文档发生外部delta；保留scope-before/current hash与差异，不恢复、不代写。scope-audit-attempt1.log、scope-drift.json明确保留该失败核对尝试；不声称所有protected文件hash绝对不变，也不以此否定源码与真实验收冻结。首次artifact汇总exit1检测到Coverage默认排除Protocol省略号，未交付该口径；保留finalize-attempt1.log/JSON/原临时代码，以本轮rawdata关闭默认排除后重报。没有新增测试来执行无业务语义的Protocol方法体，没有改owner或复跑已通过broad以适配统计。其余冻结history、三生产owner/三测试/根README与HEAD/index均未变。没有stage/commit/push/PR/启动Agent。

| Source/test file | 最终 SHA256 |
| --- | --- |
| dayu/fins/downloaders/sec_downloader.py | `b122aeeadf408e067e9f2e2487a3af03b9345a57d3f2bd2b640254443080e937` |
| dayu/fins/pipelines/sec_download_filing_workflow.py | `7ae63fe553a923e6e227e617f0f74af971d70b4acffbdb5fcd870306dd78215b` |
| dayu/fins/pipelines/sec_pipeline.py | `7f23befde2446ff224bb749d452b255704f5abd3ae72175151ab55464598c0d7` |
| dayu/fins/pipelines/sec_rebuild_workflow.py | `6bee0c2eff93024fe478f4c7b1c5bced17d8c136afad6c2ead7eca745cfdf09b` |
| tests/fins/test_sec_html_image_assets.py | `f232f4833fb85dada9e4bc1000f78c1108a440c81a67711832ca4999de084fcd` |
| tests/fins/test_sec_html_image_assets_real_cli.py | `02f219058397e98feb5ac60fd916ddf819f2abd2c7b8fc131eb3c685d33472df` |
| tests/fins/test_sec_pipeline_download.py | `2be654b5a328316e705655e85e9edf5eea56520b206841de1bd5a771785ca0f8` |
| tests/fins/test_sec_earnings_repair.py | `ee96d43ce71365311c16f3170f227e0fef2f2d5836248bbf48ccc88697c24f85` |

## README decision 与 residual risks

按已读职责只更新 Fins 的稳定 path/query/data 边界与 tests 的 owner contract 验证边界；根 README 命令/工作流无新增变化，未机械修改；无分层/装配变化，不触发dayu/README。

| ID | 分类 | Owner / destination |
| --- | --- | --- |
| R1 | fixed in current slice | S1 worker/总控；/Users/leo/workspace/dayu-agent-r/docs/validation/sec-html-image-assets-query-fix.json |
| R2 | fixed in current slice | SEC downloader/workflow/rebuild/tests；S1 C7 独立双路 re-review |
| R3 | assigned to later work unit | SEC transport/workflow维护者；独立远端重校验/指纹策略需求 |
| R4 | assigned to later work unit | SEC downloader/Fins storage维护者；有真实样本的目录资产地址契约/其它HTML资源解析需求 |
| R5 | assigned to later work unit | 后续需求提出方；外站/跨申报/OCR/数值提取独立需求 |
| R6 | assigned to later work unit | SEC transport维护者；独立响应内容校验/validator同响应身份需求 |
| R7 | assigned to later work unit | Fins processor/分析能力维护者；独立图片读取/OCR验收 |
| C2 | assigned to later work unit | Fins storage/展示维护者；有样本的全局Unicode文件名展示契约需求 |
| DS-OQ2/RR10 | assigned to later work unit | SEC downloader/workflow维护者；独立公共typed transport契约需求 |
| DS-RR9-real-shapes | assigned to later work unit | SEC downloader/tests维护者；有真实新形态样本的独立验收需求 |

R1/R2本轮已完成实现验证，最终review状态由总控裁决；R3–R7及既有C2/typed边界/新形态样本沿既有授权归宿，无新增验收或未分类风险。下一未完成入口：S1 C7 独立双路 re-review；本 worker 权限在交付fix及证据后结束。
