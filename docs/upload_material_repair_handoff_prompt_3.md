# upload_material 交接 prompt 3

> 最新状态：2026-10-04。**本轮全部授权工作已完成，剩余授权WU=0。** 原产品修复、真实upload_material CLI CI、第三方诊断独立修复、正式oracle/scenario独立登记均已final closeout pass。旧“G1–G6/17项尚未实施”“先修PR findings”的排程不再适用。

全程中文。接手先只读核Git/PR/main/最后closeout与证据，等待用户明确的新工作指令；下一业务动作由用户手工merge PR197。不得重开已闭环任务，不能自动执行延期/范围外事项。

## 1. 现场状态与当前入口

- 唯一workspace：`/Users/leo/workspace/dayu-agent-r`；唯一开发分支：`codex/upload-material-oracle`；remote：`github`；既有draft PR：`https://github.com/noho/dayu-agent-r/pull/197`。
- 已验收checkpoint：plan `d054c0fece08d3fb5b3ed71207b3dbb8ec7f5d8c`、S1 `238b28980dcbdebc4b44005d75003f00a4a719da`、aggregate/正式PR所审head `3f44c82a6a0e6aafde28cf7d919c51c884212979`、accepted PRreview `640d868fb8ac5c834be551ad2040193b53a72615`。最后正常push后local/tracking/live remote/PR同640d868f；本prompt和final closeout随后治理commit会更新最终head，因此接手必须实时查询，不能据旧快照reset/覆盖成果。
- main本地/tracking最后核为 `fac32ecbff9bfe792b63ee9667c8697826b631f4`，本轮未动。不得改main、新branch/worktree/clone/detached，所有计划/实现/fix/docs/tests/commit/push都只能此主工作树此分支；review同树只读，用普通文件快照/manifest固定版本。
- 登记真源：`docs/gateflow/upload-material-registry-control-20261004.md`、`docs/gateflow/upload-material-registry-plan-20261003.md`（accepted SHA `896762824e3de6ba7538fc710fc13fb8a5f33838788dd84335b7efea7f3ddad0`）、`docs/gateflow/upload-material-registry-plan-review-acceptance-20261004.md`。
- 当前gate：**completed / final closeout pass**。正式MiMo30185/DS95628双PR审查actual0，root核1163完整路径身份、全部required证据与双保，无新finding。全部8项登记findings已修；最终186 tests/full pyright0/批准-m strict0与final两source同源，合法wholeproof字节不变；治理commit复用同bytes验证，不冒最新head重跑802。
- 最终真源：`docs/gateflow/upload-material-registry-final-closeout-20261004.md`、`docs/gateflow/upload-material-registry-pr-review-acceptance-20261004.md`、`docs/gateflow/evidence/upload-material-registry-20261003/pr-review-proof.json`及`draft-pr-pass.json`。无在途runner，无待实现slice/待修finding/待自动开始WU。下一入口：用户手工merge PR197，merge前fresh核最终head、测试绑定与可合并状态。

## 2. 已完成工作及来源

| 工作 | 最新真源 | 状态 |
|---|---|---|
| #198 | `docs/gateflow/issue-198-final-closeout-20260929.md` | 已闭环；授权closeout comment已发布，不重复 |
| 旧PR197 F2–F7含F5 | `docs/gateflow/pr-197-review-findings-final-closeout-20261002.md` | 已闭环；F1 rejected |
| 全部原17修复＋O20F02 | `docs/gateflow/upload-material-unified-repair-final-closeout-20261003.md` | 一个WU三个完整行为slices已闭环 |
| upload_material真实CLI CI | `docs/reviews/upload-material-cli-postrepair-root-adjudication-20261003.md`、旧public bundle | 802次实际selected执行已完成及总控裁决；不是pytest替代 |
| 第三方转换器诊断通道 | `docs/gateflow/upload-material-converter-diagnostics-final-closeout-20261004.md` | 单S1独立WU已闭环；22eca closeout |
| 正式oracle/scenario登记 | `docs/gateflow/upload-material-registry-final-closeout-20261004.md` | 单S1所有固定gates闭环，全部8项已修；完成 |

真实CI和登记始终在产品修复WU完成后独立开展，不能追溯并入同WU。原六候选WU只是历史准备，不恢复该排程；22个独立residual不是自动新增scope。

## 3. runner路由与执行约束

必须使用 `$sub-agents` **通过runner子进程派发Agent**；总控自己负责裁决；**gpt-6-sol负责plan / implement / fix，MiMo (`mimo`) / ds-flash (`ds-flash`)两路同时独立并行review**。不用内置spawn或tmux替代，不自行换实现provider。

每调用显式 `--cwd /Users/leo/workspace/dayu-agent-r`，全新label/Claude instance、preflight/no-persist、独立output/stderr，Codex另独立last-message。Codex总控每runner一次独立exec_command require_escalated，不复合后台&或bypassPermissions。Claude用stream-json完整逐tool轨迹（preflight默认JSON格式可显式改，但需记录）。实际模型以event metadata可见值为准，不从CANARY/profile/请求provider猜backend。

每shell固定绝对workspace，测试/反例输出只独占 `workspace/tmp/`；临时变量先赋值再消费，不能把inline env assignment与同命令参数扩展混用造成根目录fixture。写作用域不重叠才并发；实现与其review串行。

总控必须核真实managed外层exit/结构化终态、全部toolresults、非零/failed/error/compound遮蔽/truncation及恢复、stderr、CANARY逐字、实际来源/源码SHA/验证，而后自行裁决；自报和两票不能代验。JSONL以 `bytes.split(b'\n')`，不能用Unicode splitlines。未terminal不验收；已terminal不重poll；不ps/pgrep/kill-0，不因为慢或输出暂静杀进程/重派。有限重试按skill及用户授权。

## 4. Gateflow slice规则与修复登记

严格 `$gateflow`：以可验证**行为增量**切slice，数量尽量少，每slice值得一次implementation+review成本；不按模块/文件/owner/技术层机械切分。默认避免超过3个，超过在plan说明为何不能合并；上游/用户明确阈值优先。planreview须挑战过多切分、能否合并、gate成本及future-slice越界。

本次登记只有一个完整S1，成立findings在各审查循环的**一次集中fix**处理，未为字段/文件/文案nit再开slice；现全部8项均已修复。成立修复立即写durable artifact/controller再fix，防压缩丢失。scope外只分类residual，不顺带实施。

不能跳过、合并或重排gate：goal→plan→planreview/fix/re-review→acceptedplancommit→implementation→code review/fix/re-review→accepted slicecommit→aggregate deepreview/fix/re-review→accepted deepreviewcommit→ready-to-open-draft-PR→push→核既有draftPR197→PR review/fix/re-review→accepted PRreviewcommit→push→draft-PR-pass→finalcloseout。用户要求所有slices完成后才PRreview。每acceptedfinding都须已修/同版复审，未修/部分修/证据失效不得pass；延期需既有授权、owner/destination/非阻塞理由，不发明新目标。

## 5. 不得漂移的既有用户裁决

- material各action的form/material_name均按已裁必须指定，去首尾空白后material_name最多240个Unicode码点，上传启动前统一拒超限，不能截断或新增Unicode归一化规则。form类别处理用同一owner函数，各入口调用。material year可选且域1800–2100；filing域不同，不机械同步。period六枚举、tool显式空值与缺省差异及year/period组合按正式artifact，不补猜默认。
- public internal_document_id输入移除仅针对已裁公开入口，不能删durable字段；document_id如果提供只能owner一致断言，不可改owner生成规则。action/files/ID预检、deleted的无文件规则与首错顺序按已裁artifact同步各入口，不在一个CLI局部补丁。
- 所有支持格式上传经Docling转换；抽取准确性不属本项目职责，确定上游问题留证提issue，不擅自补抽取算法。文件名→Docling文件名用同一真源函数，不多入口反推stem。
- 每份文档Docling生成并manifest登记成功才上传/下载成功；未登记就未成功，非overwrite检查同语义。company是独立事实，不能把文档失败反算为company未发生。
- 多文件primary以真实唯一成员选择、单文件默认；角色指纹与primary切换A→B→B保持ID、版本按既有指纹v1/v2/v2规则，不引入另套变更检测。
- active create非overwrite拒same/diff；missing update包含overwrite仍拒；从未出现delete拒。tombstone重复delete无新业务变化；恢复后再删除是新周期。
- 同字节amended切换：非overwrite只更新metadata/保内容版本；overwrite强制重转换发布，内容版本仍按既有指纹。
- 同一完整身份/角色指纹/amended/company别名的并发才可verified skip且零业务变化；different/corrupt/IO/releasefailure不能冒充skip。真实双CLI barrier验证，不用fake/mock事件当进程观察。
- CNInfo新下载filing_date用中国本地披露日；历史日期迁移另议。process单独运行；directCLI无FinsAgent产物正确；UI Print/log分开；SIGINT协作优雅退出，保持真实终态。
- F5可信同公司年度证据可以推断则推断；仍失败继续A、单列B不确定不猜。当前窗口为query_window ∩ union(period_windows)，local可信年度不受窄remote窗误滤；同sourceID核心事实冲突保原ValueError。fresh schema不兼容旧库；unknown>0整体FAILURE/jobFAILED/CLI1，取消优先130；已发布A保留。不得复刻已拒绝的consumer fallback/typed KeyError补偿或52周/过渡财年/超窗新网络推断。

## 6. 证据与登记边界

- 原802source target `79977b3a52f8566672e3b462f786f1004dfd3f89`，public双副本：`workspace/evidence/upload-material-cli-20261003-79977b3a-01/public`、`output/evidence-backup/upload-material-cli-20261003-79977b3a-01/public`；20518文件完整双SHA保全已完成。nine matrix 631/118/35/5/4/2/2/1/4，765 CLI/35 Service/2 shell；Service实际32failure/3success。原观察永久保持，不能改pass/fail。
- 新focused source六测量：5次真实PDF CLI（default/quiet/log/error/SIGINT）＋1次独立真实受控XBRL CLI，native11仅支持；PDF actualparent8009dirty、registrationtarget22eca、旧802target799分别保。新public双副本 `workspace/evidence/upload-material-diagnostics-focused04-22eca6c3-01/public` 与 `output/evidence-backup/upload-material-diagnostics-focused04-22eca6c3-01/public`，40文件（sole scan catalog39）；一次最终secret/canary内存probe扫描后冻结，不再导出/改扫/重写。
- 五live measured产品源码SHA严格复用，11份reviewed_source是固定历史anchor元数据，不live guard授权的tests/README。登记schema1保持、新proofv6只去顶层registry_status/readiness_proof；旧proof各自single-own-element array opaque全值保，历史refs保，不兼容旧schema读取。
- 当前正式候选808assignment=802+6；9有意除外→799formal。六维最终当前proof35/61/0/166/217/50，不用此前调整前45；PAIR66。coverage/ref/oldvalue机器检查与19条自由文本规则/纯观察人工审查均必需；不能把helper绿色、聚合exit或log样本数量/hash当业务oracle。
- 沿用31份逐项用户裁决及明确补充作为authority；review共识不产生authority。`docs/gateflow/evidence/upload-material-registry-20261003/`是bounded登记证据，不将原Raw巨量入Git或污染纯观察report；private归档只核receipt、不给public coverage信用。
- 原202608 evidence目录用户确认删除：历史缺口保持，不造旧Raw/hash/输入，不重复索要备份。后续新来源supersede lineage保在新run。
- 子Agent完整stream/scratch/原件双private保全在 `workspace/evidence/upload-material-post-ci-gate-runners-20261003/private` 及 `output/evidence-backup/upload-material-post-ci-gate-runners-20261003/private`，0600/0700；receipt与root审计在各自scratch，不能丢未提交裁决/失败原件。

## 7. 闭环后边界与下一入口

**本轮全部授权WU已完成，剩余0。** 下一入口由用户手工merge PR197；Agent不merge/approve/markready/requestreviewers/newPR/外部issue/comment/删branch。#198既有授权评论已发布并核收：`https://github.com/noho/dayu-agent-r/issues/198#issuecomment-5893424991`；Closes #198保留，GitHub issue仍OPEN待merge关闭，不重复发评论。

Linux/Windows XBRL真实部署验证获用户明确延期，macOS已验；历史CNInfo日期迁移/旧Raw缺口/原22residual assigned to later work unit（原owner/destination保持），Docling抽取准确性归上游existing #4437。它们不是自动获批的剩余实施WU，不启动新scope，不宣跨平台通过。

最终核Gitlocal/tracking/live branch/PR head/main与测试绑定；GitHubchecks为空不代表CI绿，不能沿用旧MERGEABLE作未来保证。所审产品/validator/tests/registry字节在治理commit保持；原802与focused6各自actualtarget/lineage，不能重标为最终head实跑。

最终变化/验证/文档/findings/风险owner/PR和issue关联真源为registry-final-closeout-20261004.md；controller最新段completed，旧在途段均历史。原prompt旧字节保在`workspace/tmp/upload-material-registry-20261003/handoff-prompt3-before-20261004.json`和Git历史，所有裁决/失败原件与代码均保留。接手只读恢复现场后，等待明确新工作指令。
