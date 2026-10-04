# upload_material oracle/scenario 独立登记最小计划

任务：`upload-material-registry-plan-fix-sol-20261004-03`。Gate：planfix。状态：**complete（R01–R04 集中计划修订完成，待 root 核验与同版 delta 双路 re-review；不表示 plan 已 accepted 或 registry 已 ready）**。独立 UM-CI-N01-F01 已 final closeout pass，依赖解除。本轮只更新本计划及独占 `workspace/tmp/upload-material-registry-20261003/plan-fix-sol-03/`，不实施、不提交、不派发 review。

唯一修订依据：`docs/gateflow/upload-material-registry-plan-adjudication-20261004.md` 与 `workspace/tmp/upload-material-registry-20261003/root-plan-fix-queue-02.json`。本次原计划 exact bytes 保存为 `plan-fix-sol-03/before-plan.md`，SHA `5c95926bbf7ef2dab07499462c730bd071c83aec90133819685f71d36c6cc31c`；下述 plan-final-sol-02 的核查、PR 实读、source11 当时一致和归档核收均是该轮历史，不冒作本轮新测量。本轮只读核实 HEAD/local tracking/main、registry SHA、必要子 shape/receipt/治理 anchor 与五模块身份；不访问网络核 PR、不重 hash 归档或 Raw。

历史来源保全（plan-final-sol-02）：延续原 `upload-material-registry-plan-sol-20261003-01` partial 方案、19 predicates、一个 S1 与来源索引，只集中补闭环依赖、新测量、登记 target 和验证使用方式。原计划 exact bytes 已保存在本轮 `plan-before.md`，SHA `64dc49b0673432a990993445356a84a39daafe3a851aadbc77f87da639387f6c`，36071 bytes；旧 `plan-sol-01/` 所有产物保持原件，下文原轮次事实与授权更新明确保留为历史，不抹除旧 pending 轨迹。

## 1. Binding goal、第一性原理与事实

唯一工作区 `/Users/leo/workspace/dayu-agent-r`；唯一分支 `codex/upload-material-oracle`；最终登记设计 target、plan-final-sol-02 实际 HEAD/local tracking `github/codex/upload-material-oracle`/PR197 均为 `22eca6c313005e3c5185340f2d6b535ab2583056`；main=`fac32ecbff9bfe792b63ee9667c8697826b631f4` 未动。PR197 在 plan-final-sol-02 实读 OPEN/draft、base main；本 planfix 不网络核 PR。本轮 HEAD/tracking 均22eca、main不动，tracked/index=0；五个起始未跟踪计划/控制/裁决/双报告归属已由 root 指定，保原件。plan-sol-01 起始唯一未跟踪候选为本计划，身份/SHA/36071 bytes 已核准；旧 plan-sol-01 起始 HEAD799/status空只属原轮次历史。身份变化或未知 dirty ownership 必须停。用户已授权原修复结束后的 CLI CI 和登记；`workspace/tmp/upload-material-registry-20261003/goal-confirmation.md` 是本 WU 的 binding scope。原 17 修复及 O20F02 已关闭，不重开旧产品 WU，也不实现 22 residual。

动机成立：现有 schema 1 registry 只有旧五命令的历史 ready proof，没有 upload_material 正式登记；802 次真实运行及双审不能自行建立稳定 predicate、authority、覆盖和双向 refs。因此缺口在 **registry 的 coverage/adjudication closure owner**，不是产品转换、发布或展示 owner。只补登记与可复核 proof；不新增 generic CI 框架、不修当前产品，也不把 reviewer 建议转成 authority。

成功信号与设计映射：

| Goal/success | 最小决定 | 验证 |
|---|---|---|
| 已裁语义稳定登记 | 一个 material oracle、稳定 predicate IDs、逐 surface 精确 authority | 唯一 current accepted owner、逐项 authority 范围校验 |
| 场景与事实双向闭合 | 新 scenario 与 selected evidence/mandatory assignment 精确映射 | argv/index/raw/hash/public refs、正反向 refs、六 coverage dimensions |
| 旧历史精确保持 | 旧 record 每条 canonical compare，冻结 accepted_oracle_refs 不迁移 | 6/1328 全集 identity/value/hash 对比 |
| readiness 由事实派生 | 一个 bounded validator 重算 proof；产品 failure 独立记录 | 负例、counts、digest、status 投影 |
| 既有 PR 的登记增量可审 | bounded Git 摘要与本地双副本 refs | exact main...head、旧已审字节复用、新数据全审 |

这里不包含原修复的新验证、不扩其它命令完整 campaign、不把 extraction quality 变成验收。没有 design_doc 额外目标；依据 AGENTS、Gateflow、`docs/cli_ci.md` §4.1–4.7/5.1/11.1–11.2（§11.2 是 raw DB bounded diagnostic/public 投影边界的真源） 和 binding goal。

### 直接核验及证据位置

定义 `R = workspace/tmp/upload-material-unified-repair-20261002/post-wu-preparation/`，`E = workspace/evidence/upload-material-cli-20261003-79977b3a-01/`，`B = output/evidence-backup/upload-material-cli-20261003-79977b3a-01/`，`P = workspace/tmp/upload-material-registry-20261003/plan-sol-01/`。这些只是相对路径缩写，不是新的业务 identity。

原 plan-sol-01 只读核对保留于 `P/fact-check.json`，原来源 exact-byte SHA/size 保留于 `P/read-source-manifest.json`；802 每次真实 command/result/双流/所有关键 artifact 的 local ref 和 SHA 记于 `P/selected-evidence-index.json`。`P/mandatory-assignment-draft.json` 是逐次映射工作底稿，**不是** accepted registry，不证明候选 authority 已足以覆盖其所有 surface；下述规则决定正式 assignment。

- 31 authority 原件 SHA 与 `R/oracle-authority-index.json` 一致；读取必要 Accepted 和后续补充节，定位原件，不用历史 header 的“未实施”判断当前修复状态。`root-authority-sections.json` 的首个 O01–06 sections 为空，已另读原件正文；O19 后续 E01 另读原件末节和独立 evidence artifact。
- 冻结 `E/public/observed-behavior.md` exact-byte SHA：`f35d33f5ff62b1e45d6f6ecf7ae1bcf7db4139f33c5b2af714e59ea0680ef53c`。只 hash，不重复全文读 20MB。公开 20,518 文件、96,795,332 bytes 双副本 SHA 全一致；sole scan 的 20,517 descriptors 全匹配，唯一 self 排除是 secret-scan 本身。
- 9 matrix/index 对合计 802：631 basic +118 supplement +35 owner-v2 +5 batch-v1 +4 batch-v2 +2 batch-consumption +2 tree +1 native-PDF +4 parser-edges。每次真实 argv/result 与 raw 对账，双流 SHA 全匹配。496 error /302 success /4 cancel 是 process observation，不是 correctness 计数。
- 物理 invocation 粗分类：743 upload_material（含 help/parser/seed/diagnostic），3 root-parser，19 cross-wiring，35 Service-owner，2 shell。正式 obligation/accepted 数必须另算，不能把 743 或 802 当 accepted 总数。
- 14 parser leaf：primary upload_material；5 cross 为 upload_filing、upload_filings_from、process_filing、process_material、tool_trace analyze；8 out 为 init、prompt、interactive、download、process、session list/resume/purge。完整 command path 来自实际 argv/冻结 parser，不从目录名或 top 标签猜。
- `R/registry-before-identity.json` 的每条旧 record canonical SHA 与当前一致，原 `.before` 全 JSON value 也一致：6 oracle（5 accepted/1 superseded、105 accepted predicates），1328 scenario（1294 accepted/34 superseded）。旧 proof target 是 `256786b255021ee429a20f22aad726b1ad33916c`，不是 799 重跑五命令。
- private `input-runtime-harness-source.tar.gz` 两副本 exact SHA `fe8d76e129af72b344392a9f6591d2fad21a310f785771b8146b6510931ddbf1`，592,888,231 bytes；final workspaces 两副本 SHA `dffdfa2ca4957870169f5ba802ca62fe94bd0c5a868970db91d78c8d3dbd7e18`，3,396,901 bytes。本地保全部输入/runtime/workspace/runner及双审原件，公开与 private 不混。
- root 对全部802 argv/report核对、982 published public file 检查、27 query errors 的边界和双审校正保留在原 root JSON；query error 是否 mandatory gap 要逐 surface 判断，不能从 frozen final-gap-list=[] 自动推出 ready。

直接代码：`dayu/cli/commands/fins.py:_prevalidate_upload_material_request` 构造请求、在 Service factory 前交给 Fins admission；`dayu/service/fins_direct.py:upload_material` 原样提交 validated request；`dayu/fins/upload_asset_plan.py` 规划资产/primary；`dayu/fins/upload_format_contract.py` 唯一定义 MAX_MATERIAL_UPLOAD_FILES=100；`docling_upload_service.py` 名称240、财政年1800..2100 owner；这些事实解释有效设计，不能代替用户对新期望的裁决。文件存取仍只通过 Fins storage；validator 只读已导出的 evidence，不调用业务仓储写入或真实 CLI。

### 原 plan-sol-01 并发 authority 更新与恢复（历史保留）

写计划期间 root 发布明确补充：binding goal新增“用户后续裁决/依赖变化”，`R/oracle-candidates.json` 的 `user_adjudication` 记录用户实际答复“第三方诊断也遵守 CLI 日志规则（建议）”，received_at=2026-10-03T09:15:58.686979+00:00；root synthesis新增接受段，`docs/reviews/upload-material-cli-postrepair-root-adjudication-20261003.md` 为bounded发布。已实际重读这些原件和独立诊断WU goal；不是依据review共识猜用户答案。以 `user_adjudication.accepted_predicate` 和binding goal末节为最新authority，candidate内未及时替换的 allowed_variants/forbidden_variants “user pending”历史字样不作为当前规则。数量/措辞可由转换器实际输出变化，必须遵循已接受CLI通道/等级边界，不发明额外固定日志条数或新质量条件。

来源manifest中 root synthesis JSON 从 `d470eef3822c521bb02b76b02528e3f4e21ca37e8f2591881d298f9edb3880d9` 漂移至 `09df70c18d0c5e2485e0a395b75f6f2dd56847faec07e4e39c2cf30a707fe179`；已记录 `P/source-refresh.json`，重读新authority并刷新来源manifest，旧SHA保history，不静默覆盖读取历史。新root裁决文件是其他owner并发写入，本轮未写；branch/HEAD/产品/两个registry和frozen public均保持指定身份。该有来源且goal已补充的授权更新不扩登记生产修复范围；当时依赖改为**独立N01-F01修复与真实补验的新target冻结**，当时 plan 仍 partial。此段保留来源历史；本轮已按下节核验 dependency closed，不再要求重复答复，不把计划 complete 当 registry ready。

### 最终依赖、版本范围与新观察来源（plan-final-sol-02 已核事实，本轮沿用）

定义 `F = workspace/tmp/upload-material-registry-20261003/plan-final-sol-02/`、`D = workspace/tmp/upload-material-converter-diagnostics-20261003/`。`F/source-manifest.json` 逐文件保 exact SHA/bytes/读取职责，`F/fact-check.json` 保独立核对结果，`F/readiness-dependency.json` 保 closed 依赖与登记尚待实现的区别。31 authority 原件逐SHA匹配；旧6/1328整文件与独立 `.before` 全value一致、逐身份canonical一致、两个旧proof exact value一致。802 selected/assignment 逐row核 identity/真实command/role/refs，九matrix counts与原底稿一致；本轮没有重hash722Raw或97MB整树，原树/sole scan健康检查明确引用原root与P proof。

依赖闭环依据：`docs/gateflow/upload-material-converter-diagnostics-final-closeout-20261004.md`，`docs/gateflow/evidence/upload-material-converter-diagnostics-20261003/{code-review-proof,aggregate-proof,pr-review-proof}.json`，`D/closeout-checkpoint-readback.json`。独立S1 accepted PR review=`764f3f7f6e18076a9119900c1c2aca1b15ce7a46`；closeout=`22eca6c313005e3c5185340f2d6b535ab2583056`，最后checkpoint只改治理。11产品/测试/README current exact bytes与 `D/code-review-freeze-03/manifest.json` 及 code-review-proof.source11 相同；不能把“同源码”冒作当前完整889/802重跑。

focused04实测来源以 `D/code-fix-sol-01/real-matrix-result.json.runs` 为准（5完整runs，SHA `3293641330337c0647e731b7666ace52478fc5ead2b12373ce3f8c1d7fc2f6b3`）；`result.json.real_runs.PDF_runs` 仅摘要，不作为runs集合。`result.json.fresh_root` 是对象，实际 `.path`=`/private/tmp/dayu-cli-upload-material-diagnostics-20261003-s1-01`，本轮只读必要字节，不clean、不重建、不运行产品。XBRL独立来源为 `result.json.real_runs.XBRL`，result SHA `a120a1ca46b0f0a5681cdb2fbf89e69a3ca60c203972d6c03e38cb96f40dedcd`。

| 实测case | 实际wait/exit与流 | owner事实/范围 |
|---|---|---|
| NATIVE-DEFAULT-04 | actual_wait=true/0；业务stdout848 bytes、stderr0 | Docling4783614 bytes/91页，source meta与权威manifest一致 |
| NATIVE-QUIET-04 | actual_wait=true/0；业务stdout848 bytes、stderr0 | quiet保业务；同一原件与已发布Docling，诊断抑制 |
| NATIVE-LOG-04 | actual_wait=true/0；业务stdout848 bytes、stderr0；INFO log22231 bytes | 观察129 Docling WARNING+1 RapidOCR WARNING；按等级入文件，不混stdout |
| NATIVE-ERROR-04 | actual_wait=true/0；业务stdout848 bytes、stderr0；ERROR log0 bytes | 同样完整发布；高等级空log是所测合法观察 |
| NATIVE-SIGINT-04 | actual_wait=true/130；stdout372/stderr159 bytes | owned child实际wait后缺席、请求tmp已回收、publication=null；不推广所有切点/全局零副作用 |
| XBRL-REAL-NATIVE-04 | 真CLI actual_wait=true/0，native11 pass/exit0 | MLAC实例发布/owner readback，原workspace/private/parentlog/admin/runtime/taxonomy写与network deny-default边界保持；native11不是11次CLI |

四PDF input SHA均为 `96de32a720641251b44c3e27e25ce2aa7ab035a15182b6260ef0ef06aa041dc0`；owner readback Docling SHA均为 `3b87c242b9b0f5853c40b1bf0b29c1c8b0d5a79882ea192b49fcbf5be62eb393`。大小、页数、日志条数、具体hash仅是固定样本实测，不写入稳定expected/forbidden业务规则。

实测target不是登记22eca：PDF `command.json.checkpoint_parent`=`8009ba4e100081fd1b56f64ddf5bc0c42a06e808`，带当时dirty_source与parent/child实际module source SHA。5实际module源码（process_diagnostics/log/docling_process_converter/interruptible_process/macos_sandbox）已逐SHA与当前源码比对一致；XBRL实际进程也核同一源码。`source-final.json` SHA `84d19555ea7212c00abffaae718f120867cbeb2611e6646085f705a7d2213784` 保历史11清单，其中 `tests/runtime/test_process_diagnostics.py` 后续已由 code-review-freeze-03 同版审字节替代；该测试变化不能被抹去，也不使实测5模块来源虚假变成22eca执行。最终已审 source11 是冻结 review 身份 metadata，实测5模块才是 live 产品 source guard；两者分别记录。S1 允许 tests/README.md 加登记测试条目，不把其旧 SHA 当 current，不用授权文档新增推断产品漂移；其它产品未改由 S1 文件边界和后续 root/PR 审查确认，不声称799产品整体与22eca同字节。

`D/root-code-fix-sol-01-retention.json` 记录双private归档：`workspace/evidence/upload-material-post-ci-gate-runners-20261003/private/diagnostics-code-fix-sol-01.tar.gz` 与 `output/evidence-backup/upload-material-post-ci-gate-runners-20261003/private/diagnostics-code-fix-sol-01.tar.gz`，10393004 bytes，SHA `1eebba3d163d8fd556046996ce0466773a08c40a2b4ecbde7ca7e080e02d808d`；plan-final-sol-02 实核两副本与归档内必要matrix/source成员；本 planfix 只读 receipt shape/bytes/SHA，不复制或重 hash 归档。归档是保全来源，不能用private ref替代formal public evidence。

原802独立target799与其sole frozen report/scan原SHA保持；focused04为新独立observations/lineage，最终登记target22eca只表示注册绑定和现有源码身份，不将所有历史run的target改成22eca。原五command target256786仍保历史，不宣5cmd重跑。诊断新predicate依既有用户选择从后续run生效；799 native129stdout只作发现及旧转换/发布窄范围证据，没有quiet/log-file新信用。

## 2. Authority 与固定 predicate 集合

只新增 `cli.upload_material.document-publication@1`，category=behavioral，scope.command=upload_material。version=1；supersedes/superseded_by=null。一个 oracle 聚合本命令已决语义，不按 36 标签机械创建36 owner。同一稳定 predicate 只能有一个 current accepted owner；下面19个 ID 不与旧105重用。精确 Accepted 段和有效补充的路径/SHA/heading/body digest 写进 authority-index，绝不只引用 O 标签。

| 稳定 predicate_id | Authority/语义与边界 | mandatory evidence/assignment |
|---|---|---|
| upload_material.public-parser | O01/O02/O07/O08；公开面、usage拒绝、scalar last-wins；无 internal 输入 | HELP/USAGE/SCALAR/REPEAT、parser-edges；exact argv、screen、exit、副作用；合法 --file 缩写只作当前 parser fact，不造永久 alias oracle |
| upload_material.workspace | O03及已接受路径修复；default/relative/Unicode/别名/隔离 symlink、非法普通文件明确拒绝 | WORKSPACE/PATH/SUP-ROOT-BASE；cwd、目标 before/after、错误、零业务发布 |
| upload_material.identity-admission | O05/O06/O07/O08/O17及240选择；form/name必填，trim后<=240 Unicode码点，无NFC/截断；确定ID与公开ID一致性断言 | REQUIRED/NAME/FORM/DOCID；admission输出、company/source/meta/manifest同源，无效身份零业务变化 |
| upload_material.fiscal-date | O09/O10/O11及 accepted repair plan；year1800..2100，FY/H1/Q1/Q2/Q3/Q4规范化；year/period独立可省，严格日历、可选空值按已决入口规则 | FY/PERIOD/DATE/SUP-OPTION-year*；输入与owner存储值，不猜日期容错 |
| upload_material.company-identity | O12及条件company-name/current设计；既有canonical/alias不被他公司占用 | COMPANY/ALIAS/TICKER；前置公司事实、冲突typed结果、保持旧事实；AL000 syntax样本不证明alias数量cap |
| upload_material.asset-selection | O04/O23/O24与accepted plan；数量100前置99/100/101，重复path/basename拒绝，全original/derived唯一，同stem不同basename可成功 | ASSET/SUP-ASSET/FILE-LIMIT；转换前拒绝或全部资产public一致；不硬码编码名/新规则 |
| upload_material.conversion-publication | O19/O20/O26/O34及material成功选择；受支持内容逐文件Docling+权威published manifest；JSON仅Docling，XML/XBRL仅实例；公司独立 | FORMAT/CONTENT-10/native-PDF；source原件/Docling摘要、manifest published状态及source事实；13 formats不推广任意同后缀内容 |
| upload_material.typed-content-failure | O21/O22/O34；empty_input_file、转换失败稳定五字段/安全label，不部分材料发布 | CONTENT/SUP-CONTENT及owner-v2；原始字节、CLI投影与public-terminal的kind/code/message/label/retry_hint逐字段；badHTML实际成功只观察、不发明质量fail |
| upload_material.action-state | O13/O14/O15/O16及S2accepted设计；auto幂等/更新，active create拒绝，missing update/delete拒绝；action-files优先；tombstone幂等/恢复 | STATE/MISSING/NO-FILES/DELETE/PAIR/INTEGRITY；before/after/public完整性、版本/ID；create-deleted无overwrite仅plan240回归，不升新oracle |
| upload_material.amended-overwrite | O18补充；samebytes amended无overwrite仅metadata/版本保持；overwrite强制重新转换，版本按fingerprint | STATE-same*/PAIRWISE-04；direct conversion/progress及meta/manifest，PAIRWISE04 fingerprint同、false→true、v1→v1、stored1已证，无重跑 |
| upload_material.primary-role | O24/O25；单文件自动、多文件唯一exact原件selector；role入fingerprint/skip，不改变业务ID | PRIMARY/SUP-PRIMARY/ROLE；同序/逆序/选主改变、public primary及process回指；不从argv首项反推 |
| upload_material.cross-consumption | O27及本campaign实际wiring设计；上传不隐式process，单独process exact ID/primary/source版本可消费 | PROCESS-US/CN/HK、ROLE-PROCESS、BATCH3两条；配对producer/source/publicprocessed，不能以exit0替代 |
| upload_material.direct-boundary | O28；direct CLI无Host/Agent符合边界，查询absent与未查询不同 | durable-before/after、run-terminals、query owner_scope/模式；不制造Run/Trace/Memory或全局“不持久化”结论 |
| upload_material.operator-logging | O02/O29；selector互斥、quiet保业务Print、log append、stdin不当文件 | LOG/SUP-ROOT/STDIN；两流、等级、append前缀、business终态；32 log格6非空/高等级空合法；不代替N01第三方通道的新独立predicate |
| upload_material.sigint | O30；优雅130、取消与成功区分、所测切点进程清理、已发布A不误伤 | CANCEL/TREE-SIGINT/retry；signal时刻、terminal、实际wait、process tree、before/after及恢复；不承诺所有切点零公司事实 |
| upload_material.crash-retry-observation | O31；外部强杀无业务终态、所测重试恢复 | CRASH/TREE-SIGKILL；kill方式/时刻、wait、已见PID采样、恢复；无任意parentdeath500ms保证 |
| upload_material.concurrent-publication | O32/O33与S2；不同identity最终共存，同identity linearized create+same完整状态skip，真实I/O不重写为skip | CONCURRENT全部paired结果和最终manifest/文档；不同bytes按实际权威state冲突，不锁定偶然winner/调度 |
| upload_material.converter-diagnostic-channel | UM-CI-N01 user_adjudication.accepted_predicate（2026-10-03T09:15:58.686979+00:00）；第三方诊断不得混业务stdout，quiet抑诊断保业务，log-file按CLI等级/无文件遵既定去向 | 799 native raw保发现证据；focused04 default/quiet/INFOlog/ERRORlog实际双流/文件/ownerreadback独立source-bound；future S1导出纯观察public bundle后才纳入formal evidence，未测组合不信用 |
| upload_material.evidence-lineage | O35/O36；实际输入/终态与证据标签纠偏、superseding lineage，不由aggregate数定义业务pass | 全selected逐row引用、源输入digest、collector failure与replacement；不新增timeout正确性或旧Raw可用保证 |

XBRL安全、UNSAFE/REPAIR_REQUIRED failclosed、broken/circular路径阶段、具体资源允许/拒绝等额外 correctness surfaces 必须引用当前 accepted plan/硬约束精确段，作为 `current-design`/`hard-contract` assignment，不假装用户新业务oracle：macOS arm64/Py3.11真实受控，明列runtime只读/公开XSD可读，private workspace/private内容/network禁止；Win/Linux延期。broken/circular files保accepted plan112原IO出口，不要求与primary selector同文案。名称codepoint规则和资产文件名collision规范是不同owner，不混为名称NFC规则。

逐mandatory correctness assignment过程：先读取每row的 frozen claim/state/input_class，再读 exact command/result/public before-after/原件provenance/required_surfaces；将实际被触达的surface映射到上表或精确 objective/hard/current-design，不按prefix、error或“summary成功”接受。`mandatory-assignment-draft.json` 只给定位起点；正式版每条必须包含义务稳定ID、触发/前置、predicate/authority精确ref、measurement、required evidence descriptors、actual sufficient/缺口/不适用理由。每个 surface 必须能写入唯一适用的已批准 authority（或精确 current-design/hard-contract）以及真实测量的 required refs；无法写入唯一 owner、authority 不适用或 required refs 不充分时，登记具体 gap 并停止交 root 裁决，不以 review 票数接受。现成已裁用户选择不重开、不重复问用户。任何额外字段/surface或多owner不能自动接受，必须报告gap/停。table一项内部有多个独立measurement时，在assignment列出measurement ID，不用散列更多oracle owner。

## 3. 场景分类、formal集合与不计信用

Formal scenario ID 为 `upload_material.<source_scenario_id>`，version=1；source_scenario_id保原值。这个前缀只表示登记campaign，**command字段必须真实**，没有 scope 字段代替 command。cross 为实际 leaf，Service写 `service.upload_material`，shell写 `sh`；physical executable/path/完整argv保 invocation，不伪造CLI invocation。只对属于本material closure且有充分authority和evidence的正式场景写accepted；其它行保留在assignment/evidence ledger，不能凑满802。

- Primary product、help/parser（只覆盖其实际surface）、Service独立operation、shell/cross wiring、seed/dependency、diagnostic、no-credit 分别统计。Service-v2有35 actual operations，32 public failure/3HTML成功；process success计数不是其业务success。v1 datetime observer故障全保原件，不计selected802或正式credit。
- Root/BATCH/FILING/TRACE只证明本campaign共享owner接线。其它五command历史record完全保持；新wiring records可作为material proof关联证据，但不把process/filing/batch登记成完整新命令ready。
- `BATCH-GENERATE`、`BATCH-SCRIPT-CONSUME`、`BATCH-PROCESS-MATERIAL`、`BATCH-PROCESS-FILING`、`BATCH2-PROCESS-MATERIAL`、`BATCH2-PROCESS-FILING` 原真实拒绝/缺脚本/缺ID仅diagnostic，不计positive credit。替代positive精确为BATCH2-GENERATE/BATCH2-SCRIPT-CONSUME及BATCH3-PROCESS_MATERIAL/BATCH3-PROCESS_FILING；shell实际执行生成脚本的child文档/public加载另关联，不改其command成upload_material。
- TICKER-ALIASES-100/101先AL000 syntax拒绝，只计syntax，不计aliascount。USAGE-OLD-FILE-OPTION不能证明--file删除，PARSER-EDGE-file-valid保当前parser事实。STATE-*-create-deleted及PAIRWISE-05无overwrite只有current-design regression credit，不新增tombstone规范或固定storage_io。
- CONTENT-10 exact --files为lexical symlink；O19E01后续补证已完成，不能再列“合法性待用户”；断链/循环/越界不外推。
- FORMAT-PDF-NATIVE-FULL转换/发布有既有authority；第三方stdout日志surface已由N01接受并在独立F01 focused04验证闭环。旧记录保持原版本事实，使用上节新source作独立补证。保19741stdout bytes、stderr0、129 WARNING、91页nativePDF SHA `96de32a720641251b44c3e27e25ce2aa7ab035a15182b6260ef0ef06aa041dc0`；原799未测native quiet/logfile不作信用；focused04四场景的该surface独立使用新来源，不回填原799。
- rejected/needs-more-evidence的新主观候选只进candidate/assignment，不参与formal coverage；不是因不写accepted就没有correctness gap。每个mandatory gap必须显式记录owner/destination，阻readiness。

## 4. Schema、data flow 与唯一owner

保 `schema_version=1` 和既有record字段形状；增加新records与proof，不做旧record migration。Oracle必填字段沿用 `oracle_id,version,status,category,scope,predicates,allowed_variants,authority_basis,observed_behavior,user_adjudication,applicable_from,supersedes,superseded_by`；predicate为 `predicate_id,expected:string[],forbidden:string[]`。authority_basis附精确来源描述。新 material `observed_behavior` 精确复用旧 `cli.upload_filing.document-publication` 的六内键形状（13 是旧 record 顶层键数），必填且不加 `frozen` 别名或 provider matrix：

| 内键 | 类型、配对与来源含义 |
|---|---|
| run_ids | `string[]`，恰两项，顺序固定 cli802 原 run ID、新 diagnostics-focused04 source ID（focused 来源合并五 PDF 与独立 XBRL CLI，并非捏造单次运行） |
| report_ids | `string[]`，恰两项，与 run_ids 按下标成对；分别为 E/public/observed-behavior.md 与新 focused public 纯观察报告的 repo 相对路径，不使用私有路径 |
| report_digest_sha256 | `string[]`，恰两项64小写hex，与上述 report_ids 按下标成对；原802 exact SHA 保冻结，新 focused 报告 SHA 在 S1 导出冻结后产生 |
| adjudication_artifacts | 非空 `{path:string, sha256:string}[]`；path 为列明的 repo 相对批准来源/authority-index，SHA 为原件 exact bytes；它们是裁决引用，不能冒观察报告。两 source 的 authority refs 在 assignment 精确对应 |
| report_frozen | `bool`，正式候选固定 `true`，表示两份所引报告已冻结，不代表业务通过 |
| scenario_refs | 非空 `string[]`，最终 formal material campaign scenario IDs（原802选择与 focused 独立 IDs），与 registry/assignment 正反 refs 一致；不凑802+6 |

这六键只引用实测/裁决事实；direct CLI 没有 LLM provider 数据。current accepted resolution只按stable predicate；old accepted_oracle_refs仅冻结历史依据，不能修改。

Scenario沿用 `scenario_id,source_scenario_id,version,status,command,path_kind,coverage_claims,invocation,precondition,accepted_oracle_refs,oracle_predicate_refs,correctness_surfaces,authorization_requirements,resource_budget,required_evidence,observed_evidence,user_adjudication_identity,applicable_from,supersedes,superseded_by`。coverage_claims保六维稳定ID数组；raw_stable_claims保原freeze claims，不以表述重命名历史。path_kind按真实help/positive/negative/cancel/crash/owner/wiring声明，不能替代覆盖。observed_evidence保真实execution_outcome、exit、evidence_status/gap_kind与local_ref/report SHA；额外source/required ref描述在companion assignment，不把显式业务字段丢入extra payload。

新增 `proof_version=6`（proof结构版本，不改registry schema version），最小增量字段：每份 `historical_ready_proofs` 只保存其本 registry 原顶层 proof exact JSON value；`campaigns.upload_material` 存新target/run/report/authority/inventory/assignment/proof identity；旧五scope command proof保历史target和counts，不把旧证据改799。两个registry顶层proof仍为 `readiness_proof` 唯一当前入口；commands/registry_scope可加入upload_material，但wiring消费者不是新增ready scope。旧readiness_proof_history_20260802原value不变。每份新顶层proof的historical_ready_proofs只持有其本registry原proof exactvalue；两份原proof互不覆盖、不迁移到旧record。该history位于新proof内部，canonicalbasis去顶层proof时一并排除；validator仍独立对before proof逐全值核保。顶层target_commit明确为登记设计target `22eca6c313005e3c5185340f2d6b535ab2583056`；`campaigns.upload_material.registration_target` 同值；`campaigns.upload_material.evidence_sources` 分别记原802 target799、focused04 actual parent+dirty_source+实际moduleSHA及当前same-byte比对，各有自己的run/report/scan identity。old target256786留在historical与各command proof；不得把顶层target传播覆盖历史source.target，不宣当前22eca新802/五命令运行。未来治理commit可以改变HEAD，只有须复用的产品源码 exact bytes 仍与其登记绑定身份一致才能复用：validator 只 live guard measured_source 五模块，其它原产品未改由本 S1 文件边界及后续 root/PR 审查确认；源码漂移failclosed由root决定重冻结，不在validator里自动换target。

Campaign proof必填：parser/interactive identity/version/SHA，14leaf分类与适用scope，九matrix/index SHA，report refs/SHA，31authority+followup identities/SHA，mandatory obligations与每维mandatory/covered/gap，accepted scenario/oracle/predicate计数、supporting/diagnostic/no-credit实际计数，current refs，dangling/duplicate/uncovered/pending/gap检查，旧recordcanon保护结果，dual-local证据完整性，产品finding refs与独立registry validation_result。count每个义务只由唯一stable ID去重；coverage多维独立，不能用positive抵消negative/state或cross；PAIR66覆盖由pairwise-method真实投影核算，非exit数量。

Evidence ref在读前拒lexical traversal/非允许绝对路径，核resolved root containment、leaf/ancestor无symlink；E/B相同relative ref逐SHA核，private 归档双核保的历史完整性仅从 fixed receipt 引用，validator 不读取/重 hash 它们、不公开内容、不计 public credit。Digest：exact文件用bytes SHA256；record canonical为UTF-8 `json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))`。registry digest basis去掉**顶层**registry_status/readiness_proof后canonical全值（两个文件各自），不递归删record业务字段；两个proof相互引用对方basis，无自hash循环。summary/assignment的引用digest来自原件bytes，报告只引用sole secret-scan结果，不重新产生第二份scan truth。这是 v6 有意采用的新 canonical basis，区别于历史 v5 的 records 数组单独 canonical basis：v5 仅用于历史说明，旧 opaque proof 只与各自 before 原 proof 做全值比较保留，禁止重算、兼容解析或把 v6 算法套到旧值；无旧 proof 代码 consumer 需要迁移。不据旧 digest 与新 basis 不同改回 records-only。未来 docs/cli_ci.md §4.6/5.1 必须同步 v6 新规则及此历史边界，不拿新算法证明旧 live evidence 仍存在。

数据流：immutable authorities+selected raw+old snapshots → strict read/parse →逐surface assignment与新records候选 → oldcanon/ref/coverage/evidence/hash验证 → readiness proof →两个registry_status同一result投影。判据owner是下面的validator；JSON和Markdown不各算一次readiness。所有新 oracle `applicable_from` 必填为 `{date:string,target:string}`，date 是 S1 登记 freeze 的实际 ISO 日历日期（YYYY-MM-DD），target 固定字符串 `next-upload-material-conformance-run`；所有新 scenario 的 `applicable_from` 必填为字符串 `next-upload-material-conformance-run`。不把799作为后验pass起点；799 observation事实永不回填。N01已独立修复闭环；历史产品failure与新证据都保留。一般登记ready与产品fail仍可并存（以authority/evidence闭合为条件），不自动修复、不改冻结观察。

### 最小validator决定

已读 `utils/cli_ci_run_observation.py`：它拥有Host terminal/public路径分类/secret scan，不拥有registry refs、mandatory或版本选择。复用 `classify_public_evidence_path` 识别将提交Git的public引用卫生；保sole frozen scanner结果，不重跑它、不调用final-publication writer改冻结tree。direct路径不调用Host terminal读取、不造HostRun。无须修改该helper。

只新增 `utils/cli_ci_upload_material_registry.py`，标准库+`dayu.contracts.json_value.JsonValue` 与上述路径classifier。使用朴素参数、模块级函数；不造plugin/profile/factory/callback框架、不在生产包放登记工具。公开辅助类型限定为 `RegistryValidationError`、`RegistryValidationReport`（immutable counts/errors/gaps/proof，不含业务状态bag）；内部parse用严格JsonValue与typed mapping/tuple，不用Any/object/hasattr/getattr/loose default。必填缺失/错误type/未知关键enum/ref多owner直接异常，不降格解释。

函数职责：`load_registry(path: Path) -> JsonValue`；`canonical_digest(value: JsonValue) -> str`；`compare_historical_records(before: JsonValue, current: JsonValue, record_kind: Literal["oracle","scenario"]) -> tuple[str,...]`；`validate_upload_material_registration(oracles: JsonValue, scenarios: JsonValue, assignment: JsonValue, authority_index: JsonValue, evidence_root: Path, backup_root: Path, focused_evidence_root: Path, focused_backup_root: Path, focused_source: JsonValue, source_root: Path, registration_target: str, before_oracles: JsonValue, before_scenarios: JsonValue) -> RegistryValidationReport`；`main(argv: Sequence[str] | None = None) -> int`。仅CLI command行可以选择输出报告位置；validator不写registry。Report由一个producer产生checks/counts/proof；单次实现prepare data在独占tmp构造两份registry候选，以去顶层status/proof的basis验证一次，生产唯一result，再将同一result/proof投影到两候选并用同一validator --check复核投影一致后写目标registry。candidate尚无当前proof时由validate函数返回report供准备步骤使用，不调用strict --check冒ready；--check始终要求现有两proof/status与重算结果一致，避免bootstrap循环。全部中文docstring含参数/返回/异常，utils免单测coverage要求不免pyright。

validator CLI 唯一支持显式 `--check` 模式；无缺省模式，缺 `--check`、缺必需参数、未知参数或参数误用均 exit2，不执行 bootstrap。候选 data/proof 的一次 producer 仅通过上述函数 API；strict CLI 总验证已有两 proof/status 与重算 result 一致。

validator CLI契约：`--oracle-registry PATH --scenario-registry PATH --authority-index PATH --assignment PATH --before-oracles PATH --before-scenarios PATH --evidence-root PATH --backup-root PATH --focused-evidence-root PATH --focused-backup-root PATH --focused-source PATH --source-root PATH --registration-target SHA --output PATH --check`。只读validate，不生成oracle/自动裁决，不启动CLI/network/provider。exit0只表示完整readiness proof通过；exit1为已定位validation/gap（输出机器报告）；exit2参数误用/坏格式（原始错误如实留存）。必须保file/section/row ID可定位错误；独立N01-F01已经closed；新public bundle尚未导出时，真实validation仍须报missing evidence/gap，不手翻ready。source dependency closed不等于registration readiness passed。partial report不能被--check当0通过。

### 两个固定 evidence source 的朴素接线与只读验收

此处补齐原单 `evidence_root/backup_root` 不足以容纳新focused来源的可实施性问题，保持一个validator、一个S1，不新增genericframework或readiness层。validator直接接收原802两root、新focused两root、focused_source对象、源码root与登记target。两固定source ID只作引用标签：`cli802`、`diagnostics-focused04`；assignment每个required evidence descriptor明确给 `source_id, relative_path, bytes, sha256`。无source默认值、不按prefix猜root、不全局search、不将两个root合并后放宽containment。

- 原 `--evidence-root/--backup-root` **只**绑定 `E/public` 与 `B/public`，run_id=`upload-material-cli-20261003-79977b3a-01`，target799；sole report/scan SHA固定为本plan已给两值，原31authority/9matrix inventory和802 descriptors原件保留。
- 新 `--focused-evidence-root/--focused-backup-root` **只**绑定未来S1的 `workspace/evidence/upload-material-diagnostics-focused04-22eca6c3-01/public` 与 `output/evidence-backup/upload-material-diagnostics-focused04-22eca6c3-01/public`。目录名中的22eca是登记来源标签，不改变实际run target。先完成导出、冻结及双副本再validate，不允许指向fresh private root、其父目录或tar archive。
- `--focused-source` 指向新增bounded `docs/gateflow/evidence/upload-material-registry-20261003/focused-source.json`；它是明确typed companion descriptor，不是第二readiness owner。`--source-root` 是唯一workspace；其读取职责精确列于下文：实测源码、批准 authority 原件及列明治理 descriptor/receipt，全部严格 repo containment。它不是第五 public evidence root，不能代替四 publicroots 或读取任意 private 证据。`--registration-target` 必须精确匹配顶层proof、campaign.registration_target与下述source登记target；该参数不伪称执行了此commit，Git HEAD/tracking/PR readback由root在accepted checkpoint核准。

`focused-source.json` schema1只承载此来源，必填如下（无默认、无额外payload；所有SHA64小写hex、bytes非负int而非bool）：

| 字段 | 类型与含义 |
|---|---|
| schema_version/source_id | `1` / 字符串固定 `diagnostics-focused04`；source ID仅引用标签 |
| registration_target | 字符串40hex；固定22eca，表示登记源码绑定 |
| measured_parent | 字符串40hex；PDF实际parent8009，保当时dirty状态，不捏造clean测量commit |
| measured_source | 数组，每项 `{relative_path:string, bytes:int, sha256:string}`；恰实际5模块 process_diagnostics/log/docling_process_converter/interruptible_process/macos_sandbox 的 module identities，和历史 command 中对应 module 的 dirty_source 身份一致（冲突拒绝）；仅这5模块逐 current bytes/SHA live guard，不把完整 dirty_source 中测试/文档扩为 live guard |
| reviewed_source | 同形数组；11份诊断已接受 review 的冻结身份 metadata，保 freeze03/source11 原 SHA/bytes/来源，精确比对下文固定 code-review-proof.source11 anchor；不读取这11个当前文件做 live guard，不把旧 tests/README SHA 冒 current。旧 source-final 测试当时差异仍在 source_records 中保留，不因合法 README 新增重跑产品 CI |
| source_records | 非空数组，每项 `{source_id:string, relative_path:string, bytes:int, sha256:string}`；指向focused **public内**保留的来源事实投影（原完整runs、XBRL实际字段、source identity的观察版）；原件exact SHA另列下面original_source_descriptors，投影SHA不能冒原件SHA |
| original_source_descriptors | 数组 `{label:string, bytes:int, sha256:string}`；实际real-matrix/result/source-final的原件身份标签，三原件SHA见§1；本地私有原件路径只存独占实施底稿/receipt，不给formal publicref；plan-final-sol-02 的 F manifest 负责历史原件核收。它们是来源标识，不能充作独立accepted authority |
| report / scan | 各一个 `{source_id:string, relative_path:string, bytes:int, sha256:string}`；只指新public观察报告 `observed-behavior.md` 和此bundle唯一 `secret-scan.json`；S1实际导出后计算，不在plan预编SHA |
| measurements | 非空数组 `{measurement_id:string, source_scenario_id:string, required_evidence:descriptor[], actual_exit:int, actual_wait:bool}`；五PDF含cancel与一个XBRL CLI分开，native11为XBRL supporting观察，不转11 CLI；expected/authority只在assignment/oracle，不写观察事实来源 |
| retention_receipt | `{relative_path:string, bytes:int, sha256:string}`；固定 repo 相对路径 `docs/gateflow/evidence/upload-material-registry-20261003/retention-receipt.json`，bytes 固定559，SHA 固定 `785f683849143b82cb6b07f916a36a3fad27f886f8e392711185040ecde61eb0`；只在未来 S1 精确复制 D/root-code-fix-sol-01-retention.json 原字节到此 bounded 路径；不进四 publicroots |

source-root 只读清单与职责（源码和治理引用均校 lexical 相对路径、resolved containment、leaf/所有 ancestor 无 symlink、regular file、exact bytes/SHA；不从内容递归发现新读路径）：

- Live 源码仅上述五个固定路径：`dayu/runtime/process_diagnostics.py`、`dayu/runtime/log.py`、`dayu/fins/pipelines/docling_process_converter.py`、`dayu/runtime/interruptible_process.py`、`dayu/runtime/macos_sandbox.py`。
- 31 authority 原件只限 `R/oracle-authority-index.json.files` 列出的精确路径：`docs/reviews/upload-material-um-o01-o06-oracle-adjudication.md` 与 `docs/reviews/upload-material-um-oNN-oracle-adjudication.md`，NN 恰为07,08,09,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36（不是任意 glob）；索引原件4915 bytes/SHA `8610ff1259a04f35a0dd21a474a52f63a3b8113752d35bebb63b2bfccc1b4521` 固定其集合，正式 authority-index 再列每份 exact bytes/SHA/适用正文 anchor。
- 已批准补充/current-design/hard-contract 的必要来源仅为 `R/oracle-candidates.json` 的既决 user_adjudication、binding goal、`docs/reviews/upload-material-cli-postrepair-root-adjudication-20261003.md`、`docs/gateflow/upload-material-unified-repair-plan-20261002.md`、`docs/gateflow/upload-material-converter-diagnostics-plan-20261003.md`、`AGENTS.md`、`docs/cli_ci.md`；正式 authority-index 列精确路径、bytes/SHA、适用正文 anchor 与批准 provenance，不能由本实现自行加其它私有来源。治理 append 的 owner/历史身份在该来源中明确，不自动视为产品 source identity 改变；未来 S1 使用的正文 anchor/digest 由 root 核准，内容的业务适用性仍人工复核。
- 读取 `reviewed_source` 的唯一冻结 anchor：`docs/gateflow/evidence/upload-material-converter-diagnostics-20261003/code-review-proof.json`，9735 bytes/SHA `a736639f30bcb6c0624c6f7a81c2cd3b83c6bc5fc0892e32f632bd424c94f3a9`；仅比对其 source11 数组与 reviewed_source 精确全值，不循它的 retention/private refs。freeze03 manifest 的原来源身份留作历史 provenance，不要求从其 scratch 路径读当前源码。
- Bounded 治理输入只限本 S1 列明的 authority-index/mandatory-assignment/focused-source、两 registry 与各自显式 before snapshot，以及上表 fixed retention-receipt；显式 CLI 参数不授权额外目录遍历。Receipt 当前允许形状恰七键：`bytes:int`、`sha256:string`、`primary:string`、`backup:string`、`equal:bool`、`mode:string`、`contains:string`（原件字段，无 schema_version）；核它的固定身份/类型及原值，不遍历 primary/backup 的 private archive 路径、不开 tar、不重 hash 归档、不给 private 保全 public credit。缺失、损坏、错 SHA/size、错误 shape 或非 regular/symlink receipt 均真实 validation negative，exit1 并定位 `focused-source.retention_receipt`/file。S1 精确 copy 后不修改原 D receipt 或归档。

示例ref形状：`{"source_id":"diagnostics-focused04","relative_path":"NATIVE-QUIET-04/stdout.bin","bytes":848,"sha256":"27efff735a4a6b8564c6100e58ea62dbdfc944d8d9e570f8493d0a7a242be762"}`。CLI显式传四个root，各ref按source_id选择**唯一**那对root；relative_path禁止绝对/..，校实际root和所有下级ancestor/leaf无symlink、resolved path在该root内、regular file、bytes/SHA和双副本同relativepath相同。source-root 的列明源码/治理 ref 同样 strict，普通root参数可为repo相对或实际绝对路径，但不允许通过 `/tmp` alias/symlink逃逸；用本plan给定workspace下真实路径。缺任意root/source/backup/SHA或ref source歧义均拒绝；validator不去解tar、读取freshroot或运行产品补缺。

S1数据准备在该gate独占scratch完成一次focused纯观察导出，再落新publicroot并双保；归档/输入/runtime/巨大Docling与旧Raw不进Git、不重新执行PDF/XBRL/native/provider。读取已存在fresh evidence与双归档必要记录，纯观察报告逐case只写exact argv/实际exit/wait/两流/log/前后owner事实/actual sources/cleanup范围及completeness，禁止混入accepted、建议、用户裁决、修复建议或产品pass规则。原source的checkpoint/dirty_source、测试清单历史差异不消失。实际argv中的普通财报或workspace路径仍是原运行观察，不是public evidence ref；不得通过字符串里存在路径就赋予跨root读取许可。

原PDF五case的 command/result/stdout/stderr/public-before/public-after、两个log，以及XBRL真实command/actual-exit/stdout/stderr/ownerreadback/kernel事实与actualwait/source identities形成必要raw refs。对无secret/rawDB的字节保exact复制SHA；含内部private读路径或rawDB治理字段的结构化原件只按既有owner投影允许的业务/查询事实，不携raw数据库/凭据，报告写明projection与原件SHA，不宣投影等于原件。巨大Docling保实际owner readback bytes/hash/已发布manifest/source引用，不嵌入整个Docling、taxonomy或输入tar。禁止更改业务事实或把未查询字段补默认值。

卫生owner复用 `utils.cli_ci_run_observation.classify_public_evidence_path` 和 `write_final_publication_scan_report`（实际secret/canary probe只在内存，缺实际probe依据须报gap，不写“已扫”）。新bundle完整落盘后只调用一次final scanner创建新 `secret-scan.json`，随后冻结SHA及双副本，不调用它改E/B。新scan只对新root真源负责，不取代原802 sole scan；每个source的scan descriptors须完整覆盖该source当前public文件，唯一scan自身排除沿既有owner。读后增删/脱敏或hash漂移会使该来源失效，不能悄悄再扫改真源。validator只读取两个既有sole scan并验证descriptor/ref/health，不执行scanner或导出。authority-index与assignment/registration proof单独位于bounded治理artifacts，不污染纯观察报告。

正式focused scenario ID采用 `upload_material.diagnostics-focused04.<case>`，source_scenario_id=`diagnostics-focused04.<case>`，避免与原802 identity冲突；command保实际upload_material。六mandatory coverage维度仍为command/parameter、precondition-state、interactive branch/option、input-class、combination/high-risk、cross-command assertions；当前direct CLI无interactive分支时给scope有依据的not-applicable，不造已测分支。每维stable obligation逐surface匹配Accepted正文/后续选择/current-design/hard-contract与实际证据，positive/negative/state/跨入口不能互抵；19 predicate逐项无owner/ref/gap才可ready。802总数与focused独立数用于source对账，formal accepted数只能从真实最终assignment去重派生，不写成802+6。两registry最终都投影同一个 `RegistryValidationReport`；上节canonicalbasis只去顶层registry_status/readiness_proof，两个历史proof exactvalue和readiness_proof_history_20260802保持。

负例补充在同一S1 ownercontract tests内：root错接/任一focused SHA缺失或损坏/私有路径当publicref/一副本少文件/unknown或duplicate sourceID/源码SHA漂移/measured_parent伪改22eca/原802target与reportscan被覆盖/原source-final测试差异被无证据抹去/receipt缺失/损坏/size或SHA错误/shape错误/leaf或ancestor symlink/非regularfile；实测产品五模块漂移拒绝，授权 tests/README.md 新增不改 reviewed_source/冻结 anchor、不触发产品重新 CI。每项最小破坏一个可机器判断的 owner contract并断言row/file定位与exit，不增加产品规则或新metric/surface。

人工语义检查由 code review/root 逐份观察报告、逐 predicate/expected/forbidden 对照批准 authority 与实测范围完成：报告必须保持纯观察；不得把 WARN 样本数或 Docling 样本 hash 当业务 threshold。没有自由文本机器语义 contract，因此不承诺 pytest/validator 自动判断上述两项；机器仍验证 typed shape、path/ref/SHA、来源身份、coverage、old values 合同。人工发现违反先登记 code finding，再集中 fix/re-review；不以“helper 通过”证明自由文本业务语义正确，不加 NLP、关键词 blacklist、固定数字字面量禁入或新 schema framework。

## 5. 唯一行为 slice 与allowed files

**S1：完整 upload_material 正式登记、证据映射与readiness proof。** 目标是让后续conformance run能从唯一registry稳定解析本命令的正确性与证据；数据/helper/contract负例是同一个行为增量，拆分会制造暂时ready或孤立refs，故只有一个slice，不按文件/owner/数量分slice。

前提：同身份planreview和root裁决；N01既有用户答复与最新binding补充已读取，独立F01修复/focused04 source-bound测量/11份冻结 reviewed 身份/双归档已closed（live guard 仅实测5模块）。本最终plan补齐来源，不重跑802；planreview必须审新来源与public export/两root设计，再由root接受plan。正式登记仍待S1数据导出、validator/tests、各gate完成；不因closed依赖跳过planreview。未来实现允许写的精确文件：

1. `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`（只新增本campaign records、最小proof结构变化，旧record全值不变）。
2. `utils/cli_ci_upload_material_registry.py`（上述唯一validator）。
3. `tests/cli/test_cli_ci_upload_material_registry.py`（必要owner contract负例，非802 CLI重跑）。
4. `docs/cli_ci.md`（仅§4.6/5.1说明新的proof字段、v6全registry去顶层status/proof canonicalbasis与v5 records-only旧 opaque proof 全值保留边界、scope/lineage与本命令登记结果；实现未ready时如实标calibration，不能写宣告）。
5. `tests/README.md`（只在新增validator测试职责范围触发时加一条定位，先读职责，不机械扩写）。
6. `docs/gateflow/upload-material-registry-plan-20261003.md`（经review作本plan修订，不改旧WUplan）。
7. `docs/gateflow/evidence/upload-material-registry-20261003/authority-index.json`、`mandatory-assignment.json`、`readiness-proof.json`、`validation.json`、`review-target.json`、`focused-source.json`、`retention-receipt.json`（最后一项仅 S1 exact copy；bounded Git evidence；每项带local evidence refs，不内嵌巨量raw）。
8. 新focused双publicroot仅写上节纯观察报告/必要raw refs/source投影/sole scan，不把输入/runtime/private archive提交Git；只在未来S1授权gate执行。
9. 后续Gate artifacts只在 `docs/gateflow/upload-material-registry-{plan-review,plan-adjudication,implementation,code-review,code-adjudication,aggregate-review,aggregate-adjudication,pr-review,pr-adjudication,final-closeout}-20261003.md` 与 `docs/reviews/upload-material-registry-{plan,code,aggregate,pr}-{mimo,ds-flash}-20261003.md`，以及 `workspace/tmp/upload-material-registry-20261003/<该gate独占目录>/`。本列表是后续授权gate候选，**不是本轮写权限**。

不动dayu任何生产模块、tests旧实现、locks、pyright配置、control旧WU、frozen source/public/private/backup。rootREADME已读最终用户职责；仅内部registry变化不触用户安装/参数/流程，故不更新根README；不动engine/host/fins/config/dayuREADME。新helper无用户产品入口，不在手册塞内部治理。

S1执行：冻结old snapshot/来源SHA →精确copy bounded retention receipt（不访问其private归档）→导出既有focused04纯观察public bundle与双副本（不实跑）→生成authority-index（精确已决来源/后续选择/current-design/hard-contract分清）→逐mandatory完整assignment（包括所有802保留/排除理由，v1另历史）→新增oracle/scenario候选 →minimal validator及负例 →validate/proof/status一致 →bounded docs/evidence并冻结下述 review-target。不是在下游consumer加fallback。missing/corrupt/ref歧义立即failclosed；候选产品修复只记录原source refs/owner，另WU。

`review-target.json` 是 S1 最终候选准备完成、strict --check 核验后、进入 code review 前生成的冻结审查输入，不是另一个 readiness owner。精确必填 shape（无其它键/自 hash/未来审查结果）：`{schema_version:1, gate:string, registration_target:string, registry_candidates:{oracles:{path:string,sha256:string,registry_digest_basis:string},scenarios:{path:string,sha256:string,registry_digest_basis:string}}, evidence_sources:[{source_id:string,run_id:string,report:{relative_path:string,sha256:string},scan:{relative_path:string,sha256:string}}], authority_index:{path:string,sha256:string}, assignment:{path:string,sha256:string}, focused_source:{path:string,sha256:string}}`。所有 path 为列明 repo 相对路径、所有 SHA/digests 为64小写hex，registration_target 为固定22eca40hex；registry_candidates 指两目标 registry 候选最终 exact bytes 与各自 v6 basis；authority_index/assignment/focused_source 指本 S1 bounded 文件。evidence_sources 恰 cli802、diagnostics-focused04 两项，顺序/ID/报告和 scan 来源与 focused-source/assignment 一致，run_id 为各 source 引用标签，不冒作新的执行。

gate 初值精确 `code review`，后续仅可为 Gateflow `aggregate deepreview` 或 `PR review`；各审查入口冻结同版候选，需新审查输入时重建该 gate 的 descriptor 并在 gate artifact 保留先前 SHA。review-target 不存自身 SHA、未来 reviewer pass、accepted commit 或最终 HEAD 实跑声明。Root 在 accepted slice/review checkpoint 的 gate artifact 单独记录实际 branch/HEAD、被审 review-target SHA、source unchanged 核验及治理 commit 差异，说明固定 registration target 与实际 measured parent/dirty source 的区别；治理提交不能被说成22eca或最终HEAD重跑。候选字节改变须同版复审，不能靠 checkpoint 文字改写冻结审查输入。

Completion：root审每条authority/predicate/mandatory/evidence、oldcanon=0、ref/gap=0，proof一致、测试/type通过，formal code review re-review通过。Stop：身份变化、dirty冲突、来源SHA变、pending/inconsistent authority或未闭合的必要新target证据、无法唯一owner、mandatory真实证据缺失、新scope需求、未通过validator/type。不能以“原修复代码已完成”关闭本slice。

## 6. 验证命令与预期

本轮为计划与JSON取证，不执行受影响代码tests/pyright，不将未来命令写成已通过。未来S1必须激活venv后实际运行一次，保exact argv/双流/exit/target/source SHA，不重复无变化全量测试或802实跑。

```sh
source .venv/bin/activate
python -m pytest tests/cli/test_cli_ci_upload_material_registry.py tests/cli/test_cli_ci_run_observation.py -q
python -m pyright
python -m utils.cli_ci_upload_material_registry --oracle-registry docs/cli_ci_oracles.json --scenario-registry docs/cli_ci_scenarios.json --authority-index docs/gateflow/evidence/upload-material-registry-20261003/authority-index.json --assignment docs/gateflow/evidence/upload-material-registry-20261003/mandatory-assignment.json --before-oracles workspace/tmp/upload-material-unified-repair-20261002/post-wu-preparation/cli_ci_oracles.json.before --before-scenarios workspace/tmp/upload-material-unified-repair-20261002/post-wu-preparation/cli_ci_scenarios.json.before --evidence-root workspace/evidence/upload-material-cli-20261003-79977b3a-01/public --backup-root output/evidence-backup/upload-material-cli-20261003-79977b3a-01/public --focused-evidence-root workspace/evidence/upload-material-diagnostics-focused04-22eca6c3-01/public --focused-backup-root output/evidence-backup/upload-material-diagnostics-focused04-22eca6c3-01/public --focused-source docs/gateflow/evidence/upload-material-registry-20261003/focused-source.json --source-root /Users/leo/workspace/dayu-agent-r --registration-target 22eca6c313005e3c5185340f2d6b535ab2583056 --output workspace/tmp/upload-material-registry-20261003/implementation-01/validation.json --check
```

pytest contract 负例只覆盖可机器判断的结构/引用/来源合同（自由文本语义按§4人工检查）：重复current accepted owner；缺stable predicate；冻结accepted_oracle_ref不存在；oracle→scenario或scenario→oracle dangling；mandatory surface无authority；authority只是review共识；N01 authority正文缺失却status ready；每维gap被另维抵扣；batch-v1正向信用；v1 owner计802；alias100count假信用；Service/sh/cross伪command；改一条旧scenario accepted_oracle_refs或一条旧oracle canonical value；report/raw SHA坏/缺keypublicref/错argv；ref含..、absolute escape、symlink或resolved root containment失败；缺doublecopy；focused ref错误选802 root/重复source ID/缺focused descriptor SHA/混private ref为public/任一focused source SHA漂移/旧802report或scan被新scan替代/新target覆盖旧实测target；registry_status与重算result不一致；旧proof lineage写799；productfailure错误阻ready/强迫改old observation。用最小typed有效输入构造**一项contract破坏**，断言拒绝及定位；positive验证同义属性排序不影响canonical、superseded历史refs保持但stable current唯一、新产品fail与ready可并存。不是复制实现分支或fake产品pass。

utils无强制coverage>=80；若以后触prod owner则超当前scope必须停，不为补cov扩大本WU。fullpyright必须覆盖当前dayu/tests/utils，不exclude/ignore/降类型；如有触及旧报错按owner修且不扩scope，否则报告阻塞。已有helper不改业务，运行它的受影响测试只验classifier复用无回归。

Proof assertions：31authority identity匹配；802保存索引总量、真实类别/9matrix counts逐项相等；formal accepted/mandatory counts由实际assignment逐维派生，**不预写802或任意新accepted数量**；所有current refs、measurement refs、local SHA与正反refs闭合；旧6/1328 identity集合和值完全一致，旧105predicate/冻结refs不变；两个proof registry digest相互正确、status同result。后续如发现mandatory缺gap必须停补证请求，不能擅自重跑802或网络。

## 7. Evidence/Git、后续gate与风险

Git仅放bounded计划、registry新增records、validator/contract负例、authority/assignment/proof/validation/review-target摘要。97MB public、巨大private归档、完整runner和review streams均留E/B双副本，不提交Git，不修改源冻结证据。每条localref包含root相对ref、bytes/SHA、backup相对ref及匹配结果；公开summary不公开private内容/secret。旧Raw只 `old-evidence-unavailable`，新lineage `new-superseding-run`，不恢复、不推断旧实测成功。新record需足够业务可读字段，digest是引用标签，不能代替行为说明。

后续Gateflow顺序与durable产物（本轮全部不执行）：

| entry | artifact / pass证据 |
|---|---|
| plan review | planreview双路对应mimo/ds-flash计划artifact；root plan-adjudication逐finding accepted/rejected/deferred/needs-evidence；依赖closed proof/新source/full runs/两root参数与plain descriptor/public导出边界须同版审清，root接受后才进入S1 |
| fix / re-review | 修订本plan+fix明细、sameSHA双复审/root；accepted findings均已修并验证后才accepted plan commit |
| implementation / code review / fix / re-review | S1 implementation、validator proof/tests/type、两路deepreview、root code-adjudication、所需fix与同版复审；accepted slice commit |
| aggregate deepreview / fix / re-review | 新data/helper整个增量全审、old history保护/root裁决，accepted deepreview commit |
| ready-to-open-draft-PR / push / create draft PR | 用既有draft197登记增量，按root当前授权处理；push实际receipt，不新PR不改ready；既有PR复用情况明确写gate no-create原因 |
| PR review / fix / re-review / accepted PR review commit / push | exact `git diff main...HEAD`记录main SHA/head SHA/merge-base/paths/diff摘要及所审blob；旧已审sameidentity产品部分标reuse，新增registry/data/helper逐行全审，root判定，final push实际验证 |
| draft-PR-pass / final closeout | 有PR review artifact/checkpoint/push实际证据才成立；输出新登记/proof/finding/风险/PRURL/下一入口，不越权merge/comment |

PR review不能重审旧41k diff冒本轮成果：原799产品字节与已闭环diagnostics source11按各自accepted review精确复用，不声称799产品整体与22eca相同；任一所复用blob变化则失去复用并限定重新审；新增data逐record和source/evidence完整review。最终head/最终review artifact commit SHA只能现场核，review前OID或原799不能冒最终OID pass。accepted plan/slice/review commits由root未来gate执行，本轮不stage/commit/push/外部写。

风险分类：

- UM-CI-N01-F01：**已在独立授权WU修复闭环，非当前未决产品风险**；owner converter诊断/CLI日志owner及root，destination `docs/gateflow/upload-material-converter-diagnostics-final-closeout-20261004.md`。依赖已解除，不重开；新predicate从后续run生效、不追溯799。focused04 public投影尚待本WU唯一S1实施，属于本已授权登记行为的必要输入准备；不得把本轮plan complete写成registry ready。
- Win/Linux XBRL及历史日期/22 residual：**assigned to later work unit**，原owner/原closeout后续清单；不实现，不自动作为本macOSscope mandatory gap。
- Docling extraction quality：**tracked by existing upstream issue #4437**；上游owner，不给badHTML加本地质量拒绝。
- 旧Raw删除：**assigned to historical evidence lineage owner**；不可重验事实，如实标不可用，new run superseding；旧五command record/proof保历史语义，不能宣旧证据重新可读。
- 任何新missing/corrupt/current-design争议：**requiring new explicit decision/evidence action**；root/CI evidence owner；不能隐藏进summary或“无unadjudicated所以ready”。

原plan-sol-01真实工具问题（历史保留）：多次大对象stdout截断，已改为bounded结构摘要并将逐ref/digest落独占P原件；两次路径猜测rg错误（不存在的unified-plan/final-closeout文件名、domain下asset/material模块）已用rg --files定位实际unified-repair计划/closeout和dayu/fins/upload_asset_plan.py，读真实文件恢复。没有业务CLI/tool运行失败被掩盖；没有网络/provider/子Agent或Git写。

Completion report格式（本 planfix）：`result.json` 顶层固定 `runtime_provider_model`（route 与后端模型可见性分开）、`CANARY`、`task`、`gate=planfix`、`status=complete|blocked`、`branch`、`head`、`plan={path,sha256}`、`before_plan={path,sha256}`、`delta={path,sha256}`、`fixes`（R01–R04 逐位置/改法/只读 verification）、`validation`（真实 checks 与 future tests 分开）、`tool_failures`（全部非零/compound 遮蔽/截断及恢复）、`residuals`（分类/owner/destination）、`next_entry=parallel delta plan re-review`。本轮 CANARY 只是 route 标签证据，不能由授权模型/CANARY证明后台模型。明确未进入实现、old registries/product/index unchanged；完整一次集中四项完成后停止，由 root 核结果/delta、mimo+ds-flash 同版 delta 双复审，再按 Gateflow accepted plan commit，子 agent 不继续实施/提交。后续 S1 implementation 的报告仍须保 actual tests/type/validator 与来源/变更/风险证据，不沿用 planfix complete 冒登记 ready。
