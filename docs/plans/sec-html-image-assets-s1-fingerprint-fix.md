# SEC HTML 图片 S1 指纹 typed 边界修复记录

- Work unit：sec-html-image-assets；唯一已确认 S1；Gate：aggregate fix；仅 accepted AGG-002。
- Root 裁决：docs/reviews/code-review-20261011-233443.md；base 297bfbbc67b7d7468e3dfb6669a3385c4dd10d18；accepted S1 HEAD da0ebd0d06196f3cff6d44b68af661e2d6679ceb。
- 状态：**AGG-002 已实施并完成本轮验证，待 root 的新 mimo + ds-flash 独立 re-review**。本 worker 不判 gate pass，不写 control/goal/approved plan/reviews 或旧四份 validation JSON，不启动其它 Agent，不 stage/commit/push/PR/部署。

## 动机、根因与语义 owner

动机成立，按 root 裁决为中等严重度。正式 Fs source create/batch 契约允许 JsonValue；原快跳与内容版本读取以 str(raw) 把 None/0/False/数组/对象变成非空文本，而 source upsert 又通过 or 空值另解同一事实。当前正式生产 publisher 只写字符串，未证 TSM 原样例含坏类型；本修复不声称这是原 TSM 缺图根因。

sec_safe_meta_access 已是 SEC 元数据安全读取/版本计算真源，新增 read_published_source_fingerprint(Mapping[str, JsonValue] | None) -> str | None：仅字符串且 strip 后非空返回规范字符串，其余类型、缺席、空白返回 None，显式表示未知认证。不 str() 未知值，不重算、不伪造默认值、不要求 HEX/长度/regex。

_can_skip_fast（Phase A/B 共用）、_can_skip、resolve_document_version 与 source upsert 的重处理判断复用同一个 helper。已知字符串比较/strip/升版保持；未知旧指纹沿既有空指纹规则保留 document_version，旧 v7 仍 v7，processed 不据未知指纹推定变化。已知变化沿原 v7→v8 并标记重处理；同指纹仅升级下载契约不强制内容升位。

仅三个生产文件修改：sec_safe_meta_access.py、sec_pipeline.py、sec_download_source_upsert.py。此前 downloader、filing workflow、rebuild workflow、download state 四 producer 全部初始 hash 保持；AGG-001 重算 helper 未恢复，rebuild 请求继续完全省略认证字段，由既有仓储 merge 保留原值。没有 storage merge/schema、DocumentModels、CN/HK、6-K 筛选、processed 策略或 transport/解析范围变化，没有兼容 wrapper/re-export/getattr/Any/object 或新容器。

## Owner 契约与真实仓储副作用

直接 helper 分类覆盖所有 JSON 类型及 None meta、missing/空/whitespace、immutable Mapping、非 HEX 的非空字符串与 strip 对照。通过真实 Fs blob/source/processed/batch 发布 current/old 下载版本 × null/0/false/空数组/空对象/非空 JSON/empty/whitespace/missing，内容版本 v7，使用真实 downloader + MockTransport + workflow。

普通路径实际 HTML GET→完整图片发现/HEAD→图片 GET，正式 publication 的完整文件集合、URI/size/SHA256 和远端指纹一致；当前未知指纹在 Phase A/B 均不能快跳。rebuild 保留原认证/内容版本/文件和 processed。必要 GET404 旧 meta/revision/blob/processed 全保留，解除故障后 retry 成功，repeat 零目标请求且版本/发布不变。

完整来源的未知指纹另验证 remote_files_equivalent 晚跳：基础 GET/完整发现/HEAD 在先，图片 GET 与 begin 为零，不回写或手修指纹；必要基础 GET/发现失败优先。真实竞争 writer 当前版本且未知指纹仍丢弃第一轮并重新取得 HTML/图片，不把 winner 伪认证；HEAD/GET 取消保留旧发布。既有并发、取消、事务、6-K/8-K 选择与诊断回归由本轮广域测试保护。

## 本轮最终验证

所有测试/类型命令先 source .venv/bin/activate。最终七 production + 四 tests 的 11 hash 在 collect/broad/type/coverage/real 及其它 final commands 前后相同；每命令实际 argv/cwd/exit/log SHA 与 inventory size/SHA 在新 JSON，旧四 JSON hash/历史 count 原样且不充作 final。

| 验证 | 本轮实际结果 |
| --- | --- |
| 受影响两测试 | 647 passed |
| tests/fins + tests/cli/test_fins_commands.py collect | 3964 collected |
| 同范围 broad | 3955 passed / 9 skipped |
| 全仓 pyright | 0 errors / 0 warnings / 0 informations |
| opt-in 两例真实 SEC | 2 passed / 0 skipped / 24 CLI |

覆盖采用独立 COVERAGE_FILE，本轮 fresh rawdata；无 append/exclude/ignore，清除默认 exclude/partial 后按完整生产行重报，rawdata SHA 不变，七 owner 均 >=80%，excluded_lines 全 0。

| Owner | Clean coverage | Excluded lines |
| --- | --- | --- |
| sec_downloader.py | 95.06% | 0 |
| sec_download_filing_workflow.py | 84.16% | 0 |
| sec_pipeline.py | 89.54% | 0 |
| sec_rebuild_workflow.py | 85.82% | 0 |
| sec_download_state.py | 82.71% | 0 |
| sec_safe_meta_access.py | 90.70% | 0 |
| sec_download_source_upsert.py | 88.64% | 0 |

真实新 root：/Users/leo/workspace/dayu-agent-r/workspace/tmp/sec-html-image-assets-fingerprint-fix-cf6t6etx。git archive297 正式旧 CLI 在全新 base 播种，9539 tracked 基线文件逐字节核对，七 producer 与 commit 同源；没有复制业务 base、改 meta 或手补图。两样例原业务矩阵保持，fresh/ordinary upgrade、fresh/upgrade exact 必要 GET404、旧 publication 原子保留、retry/repeat、URI/size/SHA/Fp/version 全完成。完整 filing 28 图、目标 27 图，四成功 base 共 112 逐图读回；4 expected exit1 + 20 exit0。每个真实 CLI 记录同期七 producer 身份，baseline 与 current 分开校验。UA 仅 memory 复用 zshrc literal，不保存值、原始 headers 或 env。

## 历史尝试与 README 决策

首轮 owner-first 505 passed/type0；扩展中间矩阵 owner-matrix 640 passed/type0，均保留各自源码身份，不拿中间结果代替 final。首轮 broad-final exit2，37 个 collection error 为 NumPy 重复加载：Coverage 对模块名目标在 sys_modules_saved 中通过 find_spec 导入父包，结束时恢复 sys.modules，已加载的 NumPy 扩展随后重复导入失败。直接代码证据见本轮 dependency 记录；改用此前验证使用的两个目录覆盖目标，对照 collect3964/exit0。使用全新 broad-recovery.coverage 完整重跑，不改代码、依赖、不 preload 或掩盖错误；原命令/log/rawdata/report 全保留。首次 finalizer 用文件入口启动，sys.path 未包含仓库测试包，import tests 退出1且未写 artifact；原脚本/traceback/真实命令退出码保留；随后 -m runpy 误把文件路径当 module 名，启动阶段退出1且脚本未执行，也保留原记录。最终以显式仓库导入路径执行文件入口，同一验证 helper 可正常复用；未 source zshrc 或保存完整 env。恢复后的所有 final commands 成功，没有未恢复的必要测试/类型/网络失败。初始目录检索范围过大且含不存在的 .agents/.codex、一次不存在测试文件搜索及旧脚本目录探索退出2，保留工具历史；后续改为已知精确路径，不把探索失败冒充验证成功。

已先读 README 约束：dayu/fins/README.md 更新稳定 known/unknown 指纹、快跳/版本/processed 同源边界；tests/README.md 更新 owner 分类、真实 Fs publication 回归与七 producer 真实身份核对。根 README 命令及用户工作流不变，冻结；分层装配不变，无其它 README 更新。原业务 workspace/证据未读写，TCOM 撤回 worktree 未读取。root 外部 control 治理进度仅核对记录，不恢复、不算源码漂移。

## Finding 状态、剩余风险与交接

AGG-002：accepted，已实施并验证待独立 re-review。AGG-001 依 root 已修复，本轮保留；C1/C3/C4/C5/C6/C7 没有本轮回归，C2 未采纳。未知认证 typed 边界 fixed in current slice，但最终 finding/gate 裁决仍归 root。没有新 slice/issue/goal、阻塞所有权问题或未分类风险。

| ID | 分类 | Owner / destination |
| --- | --- | --- |
| R1 | fixed in current slice | S1 worker/总控；/Users/leo/workspace/dayu-agent-r/docs/validation/sec-html-image-assets-fingerprint-fix.json |
| R2 | fixed in current slice | SEC downloader/workflow/rebuild/tests；AGG-002 独立双路 re-review |
| R3 | assigned to later work unit | SEC transport/workflow维护者；独立远端重校验/指纹策略需求 |
| R4 | assigned to later work unit | SEC downloader/Fins storage维护者；有真实样本的目录资产地址契约/其它HTML资源解析需求 |
| R5 | assigned to later work unit | 后续需求提出方；外站/跨申报/OCR/数值提取独立需求 |
| R6 | assigned to later work unit | SEC transport维护者；独立响应内容校验/validator同响应身份需求 |
| R7 | assigned to later work unit | Fins processor/分析能力维护者；独立图片读取/OCR验收 |
| C2 | assigned to later work unit | Fins storage/展示维护者；有样本的全局Unicode文件名展示契约需求 |
| DS-OQ2/RR10 | assigned to later work unit | SEC downloader/workflow维护者；独立公共typed transport契约需求 |
| DS-RR9-real-shapes | assigned to later work unit | SEC downloader/tests维护者；有真实新形态样本的独立验收需求 |
| AGG-002 | fixed in current slice | SEC 元数据安全读取/版本计算真源；root 新 mimo + ds-flash 独立 re-review |

真实 TSM 仍仅证明既有平铺 img/src，不证明新的真实 srcset/base 形态；合成矩阵覆盖其 owner 契约。未运行真实 processor/LLM/OCR 或财务数值验收，沿 R7；当前已知认证快跳不重新探测远端，沿 R3。下一未完成入口为 AGG-002 独立双路 re-review；root 负责裁决、checkpoint 与后续 PR，不由 worker 放行。

新证据：docs/validation/sec-html-image-assets-fingerprint-fix.json。

| 最终 source/test | SHA256 |
| --- | --- |
| dayu/fins/downloaders/sec_downloader.py | `b122aeeadf408e067e9f2e2487a3af03b9345a57d3f2bd2b640254443080e937` |
| dayu/fins/pipelines/sec_download_filing_workflow.py | `7ae63fe553a923e6e227e617f0f74af971d70b4acffbdb5fcd870306dd78215b` |
| dayu/fins/pipelines/sec_pipeline.py | `60fd23c360c65229d2540eae78fe32913a8df3505aa2b1bd4b856ab6d1d83cac` |
| dayu/fins/pipelines/sec_rebuild_workflow.py | `e4d45cfd42957d6666d9516aeb96afd95b602262186fd8d8b0897fbf4d1a964e` |
| dayu/fins/pipelines/sec_download_state.py | `3ec57f7ca7c589be5f2306ca727bac5e9e45014208f4af04d93f319921372e41` |
| dayu/fins/pipelines/sec_safe_meta_access.py | `a3d9b52d235fd2978927b86aaedec3cbf2d0c781626d734e55cabe69180f85ce` |
| dayu/fins/pipelines/sec_download_source_upsert.py | `e25414cb228ebac28117d1a17d89c389704f671c96aaccc4f0c29d8fb9884115` |
| tests/fins/test_sec_html_image_assets.py | `0968df44a0e239628cd06cea8c067905e0c242329f0a9aa0621be3aebfac3d47` |
| tests/fins/test_sec_html_image_assets_real_cli.py | `4c0b237526b4db8558b4c56bcfeb2e94bea01725b3fdb2cdbeb4a0cd55e80858` |
| tests/fins/test_sec_pipeline_download.py | `2219a250fbc32b7bc8e68f3aaddcb51ee55a30ec6a90eb98afbb5bac0705e415` |
| tests/fins/test_sec_earnings_repair.py | `ee96d43ce71365311c16f3170f227e0fef2f2d5836248bbf48ccc88697c24f85` |
