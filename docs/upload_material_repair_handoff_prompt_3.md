# upload_material 修复交接 prompt 3

本文件是下一位总控的执行入口。全程中文。先核实现场，再按用户已经批准的修复目标推进；不要求用户重述裁决或授权。

## 0. 当前状态和下一入口

- PR197 review findings已闭环：F1 rejected；F2/F3/F4/F5/F6/F7已修且完成各自finalcloseout。F5单完整S1 `0d8de8cb`，aggregate/source `3d0d390206739a8bb255dee517b5b61bfc4497b6`，正式PRreview `4a370a4fd8ca82de8f01fa8ea58aa83ddd92b192` 已普通push/readback。最后将本prompt/closeout与候选准备保全的提交为docs-only；接手必须实时核最终本地/tracking/live/PR同head，不能把source审查OID当最终Githead。main本地/tracking/远端为`fac32ecbff9bfe792b63ee9667c8697826b631f4`，保持未动。
- 最终本地验证1747受影响回归passed/3既有warnings/fullpyright0/23改动生产coverage≥80；MiMo/MiMo-flash双审及root独裁通过；不是最终真实CLI/oracle/scenarios/全PR846逐行验收，GHchecks当时无记录。
- **接手执行入口：G1身份/参数统一正式计划**，见下文6个候选WU与已裁17标签。无需再fix本轮已闭环findings；所有成立新增修复即时登记artifact。当前无活动runner/产品writer，后续工作未实施。
- 最终真源 `docs/gateflow/pr-197-review-findings-final-closeout-20261002.md`。停点是本轮findings闭环后的交接；下一位依据这里现成授权继续后续队列，不等待用户重复裁决。

本轮按用户最新指令，在闭环 PR review findings 后停下交接。下一位先执行剩余上传修复队列，不重新裁决或重做已闭环 findings。`docs/upload_material_oracle_celibration_handoff_prompt_2.md` 是早期逐项裁决交接，不能替代本文件。

## 1. 唯一工作树、分支及权限

- 只能在 `/Users/leo/workspace/dayu-agent-r` 的 `codex/upload-material-oracle` 上做计划、实现、修复、文档、验证、暂存、提交、推送。Git remote=`github`；PR=`https://github.com/noho/dayu-agent-r/pull/197`。
- 不改main，不新建branch/worktree/clone/detached。审查在同一主树只读进行，用普通文件快照/manifest核版本，不创建隔离Git工作树。只保留既有archive分支，不把其旧版本当开发入口。
- 普通commit/push和更新已有draftPR已授权；用户手工merge。不得merge、approve、mark-ready、request-review；#198授权closeout评论已经发布，不重复。
- 写入前读取AGENTS.md、gateflow/sub-agents技能、`git status --short --branch`/当前分支/log，核本地/远端同名branch/PR head及main。盘点任何dirty成果，保全后继续；发现错误分支或无法证明所属范围时先停止写入，不能reset/强推覆盖。
- 接手必须实时读回，不能沿用旧MERGEABLE/测试/head；最终产品源码未变化的docs-only提交可以明确证明后复用对应审查/验证，不能把旧真实CLIrun偷偷改成新head。

## 2. 子Agent路由（用户明确要求）

使用 `$sub-agents`，通过 `codex-agent-run` / `claude-agent-run` runner子进程派发，不用内置spawn或tmux替代。总控自己负责裁决；gpt-6-sol负责plan / implement / fix；MiMo / MiMo-flash两路同时独立并行review，Kimi已被用户替换。历史Kimi/DS证据原样保留，不代表当前默认路由。

所有调用显式传入 `--cwd /Users/leo/workspace/dayu-agent-r`，全新独立output / stderr（Codex另last-message），全新label/Claude instance、no-persist、每轮preflight及当前校验文件。Codex总控每runner一次独立exec_command require_escalated；不复合后台&、不bypassPermissions。先核skill及runnerhelp/catalog，profile只能记录请求配置；实际runtime/provider/model以本次event证据为准，事件不暴露model则记unknown，不能从当前配置或进程补造。

Claude审查使用stream-json全新.jsonl独立output（允许覆盖preflight默认JSON格式，需登记）；本轮实际runner支持原生 --effort medium，下次先核help后使用，不更改全局profile或把它当速度保证。

主控取得managed外层exit和完整结构化终态后，检查全部toolresults、每个非零/failed/error及恢复、stderr、当前校验文件实际读取、fullreport、实际源码/输入SHA和验证结果，自行采纳/部分采纳/驳回；不能以作者自报或两个reviewer一致代验。JSONL仅用LF分隔，Unicode分隔符可在合法JSON字符串内。未terminal不能验收，已terminal不重poll；不能仅因慢/0bytes杀进程或重派，不用ps/pgrep/kill-0判活。遵循skill有限重试和用户既有角色限制，不无限重试或自行换实现路由。

并发只允许不冲突写入范围；同一产品writer与依赖它的review串行，两review同步只读同版。artifact当前状态必须与真实managed结果一致。

## 3. Gateflow slice 原则（必须遵守）

- 以可验证行为增量切slice，不按模块、文件、owner或技术层机械拆分；数量尽量少，每slice值得一次implementation+review门禁成本。
- 默认避免一个WU超过3个implementation slices；超过须在plan说明为何不能合并/减少。用户、design_doc或上游handoff明示不同阈值时优先，不把3机械当硬上限。
- planreview必须审过多/机械切分/能否合并/gate成本是否超过风险/是否诱发提前做future-slice工作。
- 每slice写id/objective/outcome、allowedfiles、依赖、exactchanges、函数/调用链/数据流/状态/异常/不变量、非目标、验证断言、completion/stop。只能当前approvedslice，除非acceptedplan明确一次可做多个。
- scope外项登记residual/deferred，不顺带实施；所有成立修复立刻登记artifact及主队列/controller，防上下文压缩丢失。集中实施同一完整行为的必要修复，不为单个字段、finding、文案nit另切slice或独立fixloop。
- 减少slice不能跳过/合并/重排技能的完整GateOrder：已有goal confirmation有效→plan→planreview/fix/re-review→acceptedplancommit→implementation→code deepreview/fix/re-review→accepted slicecommit→aggregate deepreview/fix/re-review→accepted deepreviewcommit→ready-to-open-draft-PR→push→核已有draftPR197（既有create draft PR状态复用，不另建PR）→PR deepreview/fix/re-review→accepted PRreviewcommit→push→draft-PR-pass→finalcloseout。每个acceptedfinding必须已修并经复审验证，无blocking问题且风险已分类才pass。

## 4. 当前成果和历史证据

- 本组review findings最终closeout：`docs/gateflow/pr-197-review-findings-final-closeout-20261002.md`。
- F2/F3/F4/F6/F7历史最终closeout：`docs/gateflow/pr-197-findings-except-f5-final-closeout-20261001.md`（accepted PRreviewc305067f）。
- F5 acceptedplan：`docs/gateflow/pr-197-r1-f5-plan-v2-20261001.md`；code最终裁决：`docs/gateflow/pr-197-r1-f5-s1-code-review-final-adjudication-20261002.md`；aggregate：`docs/gateflow/pr-197-r1-f5-aggregate-review-final-adjudication-20261002.md`；正式PR review：`docs/reviews/pr-197-review-20261002-root-adjudication.md`。
- 同版验证原件：`docs/gateflow/evidence/pr197-f5-aggregate-fix-20261002/`；正式PR冻证：`docs/gateflow/evidence/pr197-f5-prreview-20261002/`；final推送读回/旧prompt逐字档案/七preparedSHA：`docs/gateflow/evidence/pr197-final-handoff-20261002/`。
- 当前prompt是完整替换，不仅追加状态；旧prompt全字节与SHA可从该目录`handoff-prompt3-before-replacement.json`逆解，旧内容不再是执行入口。

#198真源 `docs/gateflow/issue-198-final-closeout-20260929.md`：整项已完成，既有评论 `https://github.com/noho/dayu-agent-r/issues/198#issuecomment-5893424991` 已授权发布并读回；PR保留唯一Closes #198，用户merge后预计关闭。旧分叉已处理，不重新整合/创建工作树。分支/裁决保全审计 `docs/gateflow/upload-material-local-branch-integration-audit-20260930.md`、`docs/gateflow/upload-material-local-evidence-preservation-20260930.json`。

早期候选、capacity失败、inprogress及旧controller活动块都是历史，已保存，不可拿它们覆盖最终accepted源码。完整历史队列见 `docs/gateflow/upload-material-issue-198-repair-sequence-20260928.md`，本轮PR裁决controller见 `docs/gateflow/pr-197-review-repair-adjudication-20260930.md`。精确用户裁决/独立artifact优先，旧oracle观察不是当前行为。

## 5. 仍待实施的队列与依赖

当前剩17个原upload修复标签：

`O05F01 O06F01 O07F01 O07F02 O09F01 O10F01 O12F01 O13F01 O14F01 O15F01 O16F01 O17F01 O18F01 O21F01 O22F01 O25F01 O33F01`。另`O20F02`受控XBRL。已有O03、安全点号元数据、O11、O20F01、O04/O23资产规划及#198不重复实施。22个独立residual候选不是自动新增scope。

建议按6个完整行为WU组织，下面都是准备proposal，尚无acceptedplan/implementation；必须绑定最终代码正式planreview，不能把17label逐个切17slice：

| 候选WU | 修复标签/目标 | 依赖 | 准备artifact |
| --- | --- | --- | --- |
| G1身份/参数统一 | O05/O06/O07×2/O09/O10/O16/O17，共8标签 | 起点 | upload-material-g1-consolidated-plan-preparation-20261001.md |
| G2 primary与角色指纹 | O25；多文件exact唯一primary、单文件默认、全材料Docling；filename→Docling共享owner函数 | G1接口固定后接续，具体硬依赖以正式plan核准 | upload-material-g2-primary-plan-preparation-20261001.md |
| G3 文件状态和覆盖 | O12/O13/O14/O15/O18，共5标签 | G2 | upload-material-g3-state-plan-preparation-20261001.md |
| G4 内容拒绝及真实文件标签 | O21/O22 | 与company独立事实一致，可按无冲突范围并行 | upload-material-g4-content-plan-preparation-20261001.md |
| G5 真实并发幂等 | O33 | G1–G3 | upload-material-g5-concurrency-plan-preparation-20261001.md |
| G6受控XBRL | O20F02，跨平台依赖/taxonomy/有效instance | 正式P0依赖与计划核准 | upload-material-xbrl-p0-plan-preparation-20261001.md |

表中artifact均位于docs/gateflow。旧prepare源码/静态locator可过时，不能直接当当前accepted计划。首入口G1（既有goal授权有效，不重新逐项裁决）：读取主队列对8标签的正式裁决与准备，gpt-6-sol在最终head给最少完整行为slice正式计划，MiMo/MiMo-flash并行planreview，主控裁决后实施。后续分组/并发必须由实际owner/依赖/写入范围决定，不为节省门禁跨未批准WU顺带做。

## 6. 不得漂移的既有用户裁决

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

仍有一个已登记、非产品语义finding的完整PR卫生项：`tests/fins/fixtures/sec_earnings_repair_v1/workpapers/final-pyright.log:4` 原始stdout末尾空行使 `git diff --check main...HEAD` exit2。本轮scoped/cached检查0不能代表完整PR检查0。destination仍为最终PR/CI收口，owner是验证证据资产；处理时保留原字节及SHA，例如可逆证据封装和所有有效引用一致更新，不能trim原证据伪造旧输出。本轮不为这个旧nit新切slice/重开已通过业务gate。

## 7. 受控XBRL的下一步

当前准备记录Docling2.127/core2.96、arelle-release未安装、upstream4437仍OPEN的证据只是当时快照；接手实时核准。目标补受控依赖/taxonomy配置，验证真实有效XBRL instance走完整CLI→Docling→manifest；macOS arm64/Linux x64/Windows x64 fresh标准安装、locks/pipcheck及真实资源可用性须正式验证，不用静态配置冒P0pass。未安装Arelle/未验证runner资源/样本失败不是XBRL已完成。

preparation指出Model load状态应在同进程unload前取，finally卸载后不能再读；taxonomy coverage用实际结构化load attempt/ZIP入口，不把URI集合或文本log冒称逐element覆盖。既有有效样本是candidate，必须真实验证。确认上游缺陷则保留失败证据并按既有授权向上游提issue，不重复现有4437。技术设计须正式planreview，不自动采用prepare所有建议。

## 8. 全部修复后真实CLI CI / oracle / scenarios

权威 `docs/gateflow/upload-material-repair-scope-and-ci-closeout-20261001.md`；准备 `docs/gateflow/upload-material-final-ci-refreshed-preparation-20261001.md`。后者仅49 pinned/36补源/36label/92 AST surface静态核准的准备，没有真实CLIrun，没有改registry。

旧 `/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId` 用户确认删除，保历史Raw/input/lineage gap；不能伪造原hash、原Raw或把新来源说成旧资料，也不再重复索要已确认删除的备份。保留31份正式逐项裁决；新公开来源/recipes/hash按既有授权受控选择，保新run与supersede lineage。不得读取未授权私有样本。

全部修复后：

1. 最终local/remote/PR同head，重新枚举actual parser的14leaf/full mandatory矩阵与输入corpus/policy。旧160不是上限；prepared locator不能替代当前parser。
2. 运行真实CLI：独立stdout/stderr、PTYscreen、FS/log/process、publicstorage及适用Host/SQLite有界证据；保源、输入、command、env、真实exit、same-run Docling JSON、publication manifest及lineage。pytest不代CLI。
3. 对UM-O01–36逐项按已accepted裁决验实际行为；异常抽取准确性归上游；直接CLI不虚构FinsAgent产物；进程/交互/日志语义按真实观察。
4. 正式material oracle/scenarios、双向coverage proof和readiness。当前registries的Fins只有download/upload_filing，material无正式项；全局已有init/prompt/interactive不表示material覆盖。读取scenario.command顶层，不错查scope.command。
5. 不原地改accepted registry版本；产品/parser/corpus/policy/oracle改变必须证明旧证据同字节有效，否则最终head新run。docs-only提交明确证明产品不变，不重标旧run。GH MERGEABLE/pytest全绿/字面ready都不代上述验收。

仓库目前无一键完整campaign validator；utils/cli_ci_run_observation仅观察工具。需要最小typed辅助工具时遵循用户目标/正式门禁，不由root绕gpt-6-sol直接补实现。

## 9. 完成报告和保全

每gate记录artifact、裁决、验证、finding最终状态、residual分类及下个未完成gate；gate通过自动继续，不为已完成普通gate重新要许可。用户新stop或真实blocking问题优先。阶段汇报简要实际进展，不以在途/selfreport报完成。所有开发成果和裁决进入同一PR197，最终普通push后实时核local/tracking/live remote/PR head/main；root不merge。全部剩余修复和最终CLI/registry验收完成后才报告总目标完成，剩余范围/风险明确列出。
