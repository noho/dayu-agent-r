# SEC HTML 图片 S1 aggregate 修复记录

- Work unit：sec-html-image-assets；Gate：fix；唯一已确认 S1；仅 accepted AGG-001。
- Branch：fix/sec-html-image-assets；accepted S1：da0ebd0d06196f3cff6d44b68af661e2d6679ceb；base：297bfbbc67b7d7468e3dfb6669a3385c4dd10d18。
- 状态：**AGG-001 已实施并完成本轮验证，待 root 独立双路 re-review**；本 worker 不判 gate 通过。
- 本文及 docs/validation/sec-html-image-assets-aggregate-fix.json 为本轮交付；本 worker 未写 control/goal/approved plan/reviews/原三 validation 与原实施 fix artifacts。仅 control 在执行期间由 root 更新派发与中间结果，范围核对已分类并保留前后 hash/diff，未恢复或代写。没有 stage/commit/push/PR、其它 Agent 或 TCOM 操作。

## 根因、所有权和实现边界

动机成立且是高严重度：当前下载版本、空指纹、只登记 HTML 的来源被 rebuild 从本地 files 重新计算非空指纹，普通 Phase A 因而零请求跳过，必要缺图无法补齐。已读 AGENTS、Gateflow、goal/approved plan、root224555、mimo221004 和 attempt4 probe/log，并沿正式调用链核对。

正式 SEC 下载持有完整远端描述符集合的认证权；rebuild 只重建本地元数据。仓储 _upsert_source_document 先复制 previous_meta 再 update(req.meta)，因此 rebuild 不写 source_fingerprint，原值由既有仓储 merge 保留。删除 _resolve_rebuild_source_fingerprint、其专属 build_source_fingerprint 依赖和旧 helper 测试，无透传 wrapper；_can_skip_fast、下载 owner、storage/schema 和筛选不改。版本、文件 hash、document_version、source_provider、原来源身份不因 rebuild 获得升级，其它已有元数据行为保持。

正式 Fs 创建/更新会用 setdefault 把未提供 source_fingerprint 规范为空字符串；本轮分别测试显式空值和创建请求字段缺席。另以正式 replace_source_meta/batch API 建立物理缺席指纹的新独立来源，验证 rebuild 后按既有仓储规范为空值，仍未获得下载认证，随后普通 HTML/图片 GET 完整发布。不手改 meta 文件；rebuild 更新请求完全省略认证字段，既有非空/空值均原样保留，下载版本缺席仍缺席。字面上的物理缺席保留不是现有 update merge 行为，若要求此不变量，必须由 root 对冻结的 storage owner 边界另行裁决；本 worker 未改仓储缺省契约。

## Owner 回归

通过真实 Fs blob/source/batch 建立 current/old/missing download_version × 非空/显式空/请求缺席指纹的缺图来源。重建后认证、files 描述符/hash/bytes、内容版本与 identity 保留；current 非空保持原快跳，其余普通路径执行 HTML GET、完整依赖发现、图片 GET 和全集 fingerprint 发布。空旧指纹正式下载沿已有版本 owner 保留 v1，非空发生变化升 v2；这不是 rebuild 升级。必要图片 GET404/timeout/空响应在重建后保留旧 meta/revision/bytes，解除故障成功并 repeat 零请求。真实 staging update 后注入异常覆盖三种指纹输入，旧 publication 原样；既有 rebuild 取消/rollback/fiscal/manifest/processed 回归继续通过。

## 本轮验证

全部测试/类型命令先 source .venv/bin/activate；精确 argv/cwd/安全显式开关、log/exit/统计和执行前后九文件 hash 在新 JSON。最终源码与测试冻结后执行 collect/broad/pyright/real；受影响两测试共 471 passed；HTML 图片 owner 为 347 例。

| 验证 | 本轮实际结果 |
| --- | --- |
| collect tests/fins tests/cli/test_fins_commands.py | 3788 collected / exit0 |
| broad 同范围 | 3779 passed / 9 skipped / exit0 |
| 全仓 pyright | 0 errors / 0 warnings / 0 informations / exit0 |
| 新合成 10-K 认证探针 | 显式空及正式事务物理缺席指纹均无认证升级，ordinary HTML/图片 GET，exit0 |
| opt-in 两例真实 SEC validator | 2 passed / 0 skipped / 24 CLI |
| whitespace / 临时验证脚本 pyright | exit0 |

五 owner 使用独立 broad.coverage；未 append/exclude/ignore，Coverage 默认 exclude/partial 清除后重报，rawdata hash 前后不变，完整行图和默认/clean 两报告保留。

| Owner | Clean coverage | Excluded lines |
| --- | --- | --- |
| sec_downloader.py | 95.06% | 0 |
| sec_download_filing_workflow.py | 84.16% | 0 |
| sec_pipeline.py | 89.54% | 0 |
| sec_rebuild_workflow.py | 85.82% | 0 |
| sec_download_state.py | 82.71% | 0 |

真实 root：/Users/leo/workspace/dayu-agent-r/workspace/tmp/sec-html-image-assets-aggregate-fix-zzrqumba。基线由 git archive297 逐字节核对，经原生产 CLI 正式播种旧来源，禁止手补旧源。两例各 12 CLI：fresh、两次基线播种、ordinary upgrade、fresh/upgrade exact 必要图片 GET404 失败诊断及旧 publication 原子保留、retry、四成功 base repeat。完整 filing 图 28、目标图 27；四成功 base 共 112 图片读回，真实 metadata/URI/size/SHA256/远端全集指纹和版本断言成立。新增第五 producer 纳入现场 context/sample 源码身份。4 个预期故障 CLI exit1 保留，另外20 exit0；未运行真实 processor/LLM/OCR 或财务数值验收。

## 失败尝试及恢复

首轮 owner-first 为 15 failed / 456 passed：9 例夹具遗漏 ingested_at，既有 rebuild 正常补齐而全 files 断言不符；6 例错误预期空指纹下载应升 v2，owner 实际保留 v1。补全正式输入及纠正既有 owner contract 后 owner-recovery 471 passed。未为这些测试改生产行为。

原 reviewer probe 的新 root 重放 exit1：空指纹已保留、ordinary 已发请求，但合成 6-K HTML 没有财报筛选证据，被既有 6k_filtered 拒绝。保留 attempt1 源码/log/root；改新合成探针 form 为10-K隔离本缺陷，exit0；原 mimo attempt1–4 完全未改。

首次 broad 忘设 COVERAGE_FILE，主动 Ctrl-C exit130；原 command/log 记录 interrupted，不冒充完成，默认路径产生的中止 rawdata 移入新 evidence/interrupted-default.coverage，随后显式独立路径 broad-recovery 完整成功。本轮早期 collect/type/freeze 保留为前测试修订尝试；final-freeze 才是新最终身份。首次汇总范围检查 exit1 发现 root 对 control 的外部进度更新，保留 finalize-scope-attempt command/log 与旧临时 finalizer，核对 control diff 后只分类外部 delta，未忽略任何源代码/tests/其它冻结文件漂移。辅助 ps 权限拒绝、查询误填非存在文件、一次临时 artifact patch 未匹配均未改变代码/业务，未当作验证 pass。所有旧 JSON 原样且仅为前代码历史；不复用旧3773/3764/9、14 commands/176 inventory为新 final。

## 文档、风险与交接

已先读 README 职责：Fins README 更新稳定下载认证边界，tests README 更新正式仓储 owner 回归证明；根 README 命令与用户流程无需变化且冻结；未改变分层装配，不触发 dayu/README。原业务base/证据目录只读且本轮无需访问，零写。身份值只从 zshrc literal 在内存复用，不 source 整文件，不保存 UA/headers/env。

| ID | 分类 | Owner / destination |
| --- | --- | --- |
| R1 | fixed in current slice | S1 worker/总控；/Users/leo/workspace/dayu-agent-r/docs/validation/sec-html-image-assets-aggregate-fix.json |
| R2 | fixed in current slice | SEC downloader/workflow/rebuild/tests；AGG-001 独立双路 re-review |
| R3 | assigned to later work unit | SEC transport/workflow维护者；独立远端重校验/指纹策略需求 |
| R4 | assigned to later work unit | SEC downloader/Fins storage维护者；有真实样本的目录资产地址契约/其它HTML资源解析需求 |
| R5 | assigned to later work unit | 后续需求提出方；外站/跨申报/OCR/数值提取独立需求 |
| R6 | assigned to later work unit | SEC transport维护者；独立响应内容校验/validator同响应身份需求 |
| R7 | assigned to later work unit | Fins processor/分析能力维护者；独立图片读取/OCR验收 |
| C2 | assigned to later work unit | Fins storage/展示维护者；有样本的全局Unicode文件名展示契约需求 |
| DS-OQ2/RR10 | assigned to later work unit | SEC downloader/workflow维护者；独立公共typed transport契约需求 |
| DS-RR9-real-shapes | assigned to later work unit | SEC downloader/tests维护者；有真实新形态样本的独立验收需求 |

R3–R7/C2/typed transport/新形态样本沿既有分类及归宿，不发明 issue 或新验收。R1/R2 实施验证交付待 re-review，没有未分类 residual risk；AGG-001 最终 finding 状态及 gate 裁决由 root 负责。下一未完成入口：AGG-001 独立双路 re-review。

| 最终 source/test | SHA256 |
| --- | --- |
| dayu/fins/downloaders/sec_downloader.py | `b122aeeadf408e067e9f2e2487a3af03b9345a57d3f2bd2b640254443080e937` |
| dayu/fins/pipelines/sec_download_filing_workflow.py | `7ae63fe553a923e6e227e617f0f74af971d70b4acffbdb5fcd870306dd78215b` |
| dayu/fins/pipelines/sec_pipeline.py | `7f23befde2446ff224bb749d452b255704f5abd3ae72175151ab55464598c0d7` |
| dayu/fins/pipelines/sec_rebuild_workflow.py | `e4d45cfd42957d6666d9516aeb96afd95b602262186fd8d8b0897fbf4d1a964e` |
| dayu/fins/pipelines/sec_download_state.py | `3ec57f7ca7c589be5f2306ca727bac5e9e45014208f4af04d93f319921372e41` |
| tests/fins/test_sec_html_image_assets.py | `822b8640069092b0bea0c707657c29369fbaa6afe906ff2ed39e64e319b1fb35` |
| tests/fins/test_sec_html_image_assets_real_cli.py | `e3bbea33df0bad93e33125c0146146379ee32e92d57bcc8725db79a12acc22e2` |
| tests/fins/test_sec_pipeline_download.py | `f90a41a3dfeb1b2d96ba20dd0050623539f3ab16e6bd483bf4d0e6a2536ff9d1` |
| tests/fins/test_sec_earnings_repair.py | `ee96d43ce71365311c16f3170f227e0fef2f2d5836248bbf48ccc88697c24f85` |
