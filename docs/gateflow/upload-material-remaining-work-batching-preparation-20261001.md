RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-e1d29507

# upload_material 剩余修复粗分组预备 proposal

身份：`pr197-remaining-batching-preparation-sol-20261001-01`；实际模型无可读取遥测，记 unknown，路由身份按任务指定 gpt-6-sol。只读预备，不是新 WU、accepted plan、plan gate pass 或实施授权。
动机成立：18 个 label 不是 18 个独立 WU；同源受理和状态转换若按字段拆，会反复重绑、重复审查。同组仍保持各语义 owner、纯校验/仓储/转换职责，不合成 god function。

## 版本与证据边界

- 唯一 workspace `/Users/leo/workspace/dayu-agent-r`，branch `codex/upload-material-oracle`；首末 HEAD `5fc5e4f0c685c4a998a72ce4fbe02c3f889cf368`，main `fac32ecbff9bfe792b63ee9667c8697826b631f4`。
- 首读 AGENTS、执行成本纠正、scope-and-ci-closeout；本轮 canary 从指定 `sub-agents.Vju2lS/canary.txt` 实读，未引用旧轮 canary。没有派发外部 runner/子 Agent；Sol 实施、MiMo/Kimi（quota 时 DS）双审、root 总裁决的职责不变。
- freeze SHA 首末均 `a403ca0d84dc449bb914174f1e503b641c3da6a7dd3cb8dc54c6132709b3febf`；17 件 current/originals 首末匹配。HEAD 相等仅为背景，字节身份逐件验证。
- queue/handoff **仅用 pinned**：logical `docs/gateflow/upload-material-issue-198-repair-sequence-20260928.md` / `docs/upload_material_repair_handoff_prompt_3.md`，physical 为任务临时根 `pinned/` 下同路径；commit 均上述 5fc，SHA 分别 `21aab5925db1231d20d344e513169813a63398e00a8a3198f81b951584257a0c` / `2fca37e57a36b7feda1b9000394513de59e8dbd42554db64bd2874f658201198`，与 exact git bytes 匹配。未读可变根 queue/handoff/controller，也未读本轮 MiMo/DS/Kimi 新产物。
- 新读取的必要正式裁决、旧计划/adjudication、20 个源码文件和 7 个测试文件共 77 件版本记录在 `workspace/tmp/pr197-remaining-batching-preparation-sol-20261001-01/read-proof-end.json`：逐件 logical/physical、5fc git blob、SHA、读取范围及首末结果；全部与 5fc 字节相同，已建立首值者均无漂移。该清单是精确版本索引，不声称全文件审查；`asset_filename_contract.py` 只核字节，命名行为直接核 `upload_asset_plan.py:267`。
- 临时根另有 `identity-start.json`、`additional-start-index.json`、`supplemental-start-index.json`、`tests-start-index.json`。较宽候选 hash 索引只为核验实际读取版本，未据此开展全 repo review；未读取候选内容不能当产品证据。
- 正式裁决目录 inventory 为 31 件；本轮只核相关 17 件（含 O34 发布边界），不重裁历史。旧 Raw 已删除；本轮没有访问旧原件、私有资料、OCR 或网络，历史运行叙述不能冒充本轮实证。

## 表一：18 label 的合同、owner 与依赖

表中 Axx 展开为 `docs/reviews/upload-material-um-oxx-oracle-adjudication.md`；A01–06 为 `upload-material-um-o01-o06-oracle-adjudication.md`。Pxx/Pstate/Pfiscal/Pcontent 指 `docs/gateflow/upload-material-` 对应下列真实计划；Jxx 为对应 `*-plan-review-adjudication-20260929.md`。行为批准与计划门禁分别记录。
简称 D=`dayu/fins/pipelines/docling_upload_service.py`，R=`dayu/fins/ingestion_runtime.py`，U=`dayu/fins/upload_usage_contract.py`，S=`dayu/fins/storage/`，W=SEC/CN（含 HK）material workflow；入口 CLI→Service→R、tool→R、独立 pipeline→同一准入。

| label | 已批准行为依据 | 当前实际 owner / 入口 | 硬依赖与安排；计划处置 |
| --- | --- | --- | --- |
| UM-O05-F01 | A01–06：form/name 生命周期前 typed 必填 | R `_admit_material_upload_facts`/`_normalize_upload_request` 为实际准入接缝；D builder 仍晚期判空；U 持 closed code/message | O17 canonical 先于合法 form 投影；可在同组内部实现。P05 required-identity + J05 C2/C3 重绑 validated handoff/W/U；现版不得直接实施。 |
| UM-O06-F01 | A01–06 + `o06-name-length-goal-20260929.md`：trim 后 240 Unicode 码点，无截断/新 Unicode 归一化 | 名称同一 admission；job 摘要限制不能代替业务 owner | O16 组合优先、O05 form/name 必填先于长度有 J06 直接裁决；非独立部署依赖。P06 name-length 可复用矩阵，需补 accepted PR-F1/F2/F4 及实际 U；gate 未过。 |
| UM-O07-F01 | A07：移除公开 internal_document_id，保留持久/输出内部 ID 和 filing 身份 | R request、CLI 注册/tool schema/Service 透传；D `validate_material_upload_ids` | 与 F02 同一完整身份 slice；不得按入口拆。P07 ids 保留输入移除/持久字段边界，基于最终 request 形状重绑；gate 未过。 |
| UM-O07-F02 | A07：document_id 只作稳定身份断言，mismatch 前置/零业务副作用 | D `build_material_ids`/`validate_material_upload_ids`，R admission；W 目前事件前调用但 R 受理尚未完整 | 完整 form/name/fiscal seed 必须先于 ID 断言；O05/O17/O09/O10 可同 slice 顺序满足，无必须独立 WU 的源码证据。P07/J07 EMPTY/MISMATCH 规则复用；旧身份处置仍独立。 |
| UM-O09-F01 | A09：material year 1800..2100，生成身份前拒绝非法值 | D 身份域，R 投影；filing year/period 域在 `domain/filing_semantics.py`，本轮未审其实现 | 与 O10/O07 同一 seed 校验；不是 F5 年度锚点推断。Pfiscal/Jfiscal 候选需将新 code 从旧 R 重绑 U，保留 filing 1000..9999；缺同版第二路。 |
| UM-O10-F01 | A10：FY/H1/Q1/Q2/Q3/Q4，trim/upper/空转 None；tool 空文本参数拒绝保留 | D 当前私有 period 规范化及 W 两份重算需要收敛到既有 `normalize_fiscal_period` | 先规范 fiscal 再断言 ID；可与 O07 合并。Pfiscal 复用入口差异与 zero-side-effect 矩阵，不造长度阈值/解析器；gate 未过。 |
| UM-O12-F01 | A12 + A34：状态条件公司缺名 typed 拒绝；合法公司提交与材料独立 | `upload_company_meta.py:47` 纯 decision；R admission、S published snapshot/guard；当前 material 无独立 state 协议 | O16/O05 是接受时前置；O07/fiscal 稳定 exact ID 先于状态读。P12 company/J12 已正式 plan pass，但未实施；需按最终源码最小重绑，PR5 active-only/no-runner 条件不丢。 |
| UM-O13-F01 | A13：同 tombstone 周期重删保时间/revision/meta/manifest/资产字节，恢复再删为新周期 | S `_fs_source_document_core.py:_toggle_source_deleted` 当前每次重写；D delete 调用 | 不硬依赖 O07/fiscal/O25，owner 状态链可独立验证；可并入 O12/O14/O15/O18 状态闭环，保持共享 filing 回归。P13 tombstone 可复用；缺有效第二路，gate 未过。 |
| UM-O14-F01 | A14：active create 无 overwrite 同/异内容均先拒绝，零公司/文档业务写 | D `evaluate_upload_overwrite_precondition`，R material admission + S writer-owned state | O12 同版 snapshot/材料 batch 复验是真依赖，可同组实现；不能单一入口再读。Pstate/Jstate 可复用矩阵，PR-C5 候选未双审通过；不扩大 tombstone create 的业务承诺。 |
| UM-O15-F01 | A15：missing update（含 overwrite）/never-existed delete 前置 typed 拒绝；tombstone 重删允许 | 同 O14，缺失不是任意 FileNotFoundError；S 负责最终状态 | 与 O12/O14 用同 snapshot、同材料 publication helper/单材料 batch；公司 batch 独立。Pstate 同版重绑，无需再按动作拆；gate 未过。 |
| UM-O16-F01 | A16：auto/create/update 有文件，delete 零文件；先于目标/读取 | R 静态 admission + typed selection；planner 当前 delete 可接 raw files；U code/message 已唯一 owner | **J16 C3→U 已由 R import 和 U enum/mapping 直接核实**，不是 `dayu.runtime` 新副本。P16 action-files 复用 typed requested/pipeline action 合同，必须重绑 planner/handoff/U 和错误时序；gate 未过。 |
| UM-O17-F01 | A17：form 一个 trim/upper helper，ID/meta/manifest/事件同源，不增枚举 | D builder 目前局部 canonical；R/W/batch 仍分散投影，`upload_batch.py` 持 routing 域 | 与 O05/O06 同完整受理 slice 可合并，helper 与 routing owner 分开。P17 form/J17 PR6-F1/F2/F3 未闭合；实际 batch CLI 测试仍断言 ESG_REPORT 预先 upper，必须迁移。 |
| UM-O18-F01 | A18 补充裁决：同字节异 amended 无 overwrite 仅 metadata；overwrite 强制转换/发布，版本仍 fingerprint | D prepare/version；S source meta 唯一持久事实→manifest/终态，W 当前未传 amended | 依赖 O12 同版 guard、O14/O15 合法动作，O25 最终角色 fingerprint；可与状态闭环合组。P18 amended/J18 PR4-F1–F6 全部未修；批量必要同源 planfix 后双审，不能假称 accepted。 |
| UM-O20-F02 | A20 条件原则 + `o20-xbrl-runtime-goal-20260929.md` 用户受控 XBRL goal pass | `dayu/documents/docling_runtime.py` capability/转换边界，依赖/锁文件；Fins 只消费 outcome | 真实 taxonomy/引用隔离/安装与正样本是证据硬条件，不依赖 F5。P20 xbrl-runtime 最新 P0/J20 PR10-F1/F2 未修；无已冻结 taxonomy 产品 API；blocked，不合并伪成功。 |
| UM-O21-F01 | A21：转换失败附当前安全文件标签，材料无部分发布 | D `_build_pending_assets` 当前 material 直接 rethrow；共享 typed failure/canonical label owner | 与 O22 合一条内容失败传播闭环；O04/O23 已入 PR 是已存在资产身份前提，不当待实现。Pcontent failure/Jcontent 单路已核，缺第二路；重绑当时 handoff。 |
| UM-O22-F01 | A22：material/filing 同一 0-byte typed content failure | D `_build_original_assets` 当前仅 filing 拒空；`upload_failure.py` 传播既有 typed reason | 与 O21 同 owner 链；tool st_size 提前截断必须移除，路径形状仍前置。Pcontent 保留 observation 无 job/真实 job 双摘要区别；gate 未过。 |
| UM-O25-F01 | A25：多文件唯一 primary；同源 pair→角色 fingerprint/meta/read，全部原件仍转换 | `upload_asset_plan.py` 单次规划、`docling_storage_name`；D 当前首转换产物 primary；入口当前无 material selector | 依 O16/已入 PR O04/O23 真实 handoff；与 O07/fiscal 无强制分开依赖，可同行但建议独立完整发布验收。P25 primary/J25 最小重绑：plan 当前只有 filing_primary 字段，禁止预造 API；缺第二路。 |
| UM-O33-F01 | A33 + 旧 E01 同源 traceback：stale auto→create→FileExistsError；相同目标权威确认后一成功一 skip | D identity/fingerprint/action，S writer/publication guard；不是 CLI storage_io 文案 | 依最终 snapshot/target/tombstone/fingerprint/amended 完整性。P33 concurrency/J33 C1–C3 候选未过 gate；certainty 不足回 S owner，不能要求 scope 外 download WU 自动先完成。 |

## 表二：建议行为组与依赖（不改 root 优先排程）

每组默认一个完整可验证 slice；这是供后续 root 选择的 batching proposal，不固定新 WU 数量。跨现有 WU 汇总同 gate 的必要修复/同版双审时，各项状态和 root 裁决仍分别保留。

| 建议组 / 内部 labels | 最小源码范围与验证合同 | 可复用已核内容 / 真正新增验证 / 启动前重绑 |
| --- | --- | --- |
| G1 完整受理与稳定身份：O16、O17、O05、O06、O09、O10、O07-F01/F02 | R/U/D、W、CLI/tool/Service 请求链、batch form routing；顺序按已裁决入口局部优先级，组合→必填→长度/fiscal→ID；非法输入早于 lifecycle/记录/业务写，合法 canonical 一路到发布 | 复用 P16/P05/P06/P17/Pfiscal/P07 合同与已核 current validated handoff。新增 joint-invalid、240/241 emoji/组合码点、raw batch→canonical request→ID/meta、公开 internal 输入彻底移除、ID EMPTY/MISMATCH 跨入口；复用 O11 日期回归，必须迁移现存 delete+raw-file“成功”及 batch 预 upper 旧断言。统一 planfix U/C2/C3/PR6，不重复十份全计划。 |
| G2 主原件选择与角色发布：O25 | G1/既有资产 owner 后；单次 pair 计划→primary→fingerprint/版本→source meta/manifest→process/read，完整发布与 skip 验收 | 已核 `test_material_full_basename_mapping_and_order`、全文件转换测试及 filing 角色测试可作已有 contract/回归清单，未在本轮执行。新增 material A→B→B v1→v2→v2/末次 skip、非首项 primary、正逆序/非法 selector 零副作用；按最终 planner/handoff 重绑，无 filename 派生副本。 |
| G3 公司/目标/删除/amended 状态闭环：O12、O14、O15、O13、O18 | G1 后 exact identity；O18 同组部分须消费 G2 最终角色指纹。S 同版公司+source snapshot→动作/公司 decision→独立合法公司 commit→一个材料 batch/skip guard；D metadata-only/content/delete outcome，R active-only job 终态 | 复用已正式 accepted P12/J12 条件、Pstate/P13/P18 矩阵；新增 fresh/missing/active/tombstone 动作链，首删/重删/恢复/再删字节幂等，amended 八格与 delete 默认 false 但 published true，metadata-only 日期等字段不变。一次补 state PR-C5/O18 PR4-F1–F6，writer lock 交错放在 begin_batch 前；不新造公司+材料共同事务。 |
| G4 内容失败同源传播：O21、O22 | 资产 owner 已入 PR即可准备；与 G2/G3 是源码安排关系，无证据要求它们先 accepted。D bytes/converter 边界→typed failure→W/R→CLI/observation/job | 复用现存 nth-conversion 无材料发布、filing empty 及全文件转换 contract；新增 material 空字节单/多文件、损坏第二文件精确安全标签、direct/CLI 与 tool details 五字段对照、真实 job 同源双摘要、取消/公司已提交保留。两旧行为切片可合一次传播闭环，日志中立化同轮必要 fix。 |
| G5 并发权威裁决：O33 | G1/G2/G3 最终合同后；D 与 S publication 接缝，复验完整 exact identity/role fingerprint/目标状态/amended，结果 certainty fail closed | 复用 A33/E01 直接旧根因解释及已有 publication guard 实现，不复用旧运行通过票；新增可控 barrier owner 竞争、真实双进程一 success 一 skip、不同指纹/alias/corruption/真实 I/O、swap 后释放异常不得 skip。实际根因/调用点按最终源码重新核，保留单完整并发 slice。 |
| G6 受控 XBRL：O20-F02 | 根按原排程；Documents runtime+依赖锁/受控输入与进程边界→Fins 正常发布。P0 补证后才可冻结一个端到端转换实现 slice | 只复用已批准 goal/公开 capability/旧 blocked 的证据机制要求；旧 Raw 不可用。PR10 卸载前同次快照/结构化逐元素证据需补，taxonomy provenance/受控部署/支持平台隔离/有效 instance 真实 manifest 全新验证；当前缺口 blocked，不指定尚不存在 API/新平台规则。 |

保留 G2：primary 改变会独立改变角色指纹、默认读取源与版本，有 A→B→B 独立验收，不按文件拆。保留 G4：typed content 失败发生于转换、须验证无部分材料发布/observation 与 job 区别，可与主选择独立验收。保留 G5：跨进程线性化和 post-commit 确定性有独立故障注入边界。保留 G6：部署与引用隔离证据不齐，混入其它组会把 blocked 能力伪装成普通转换修复。
G1 的 O05/O06/O17、O07/fiscal 同 seed 受理可合；G3 的 O13 可合，无证据强制拆。G2 理论上可与 G1 合，但身份无副作用验收与 role 发布/read 验收独立，当前 handoff 尚无 material primary；建议保留完整行为边界，不以共享 D 文件认定硬依赖。

## 残余、缺口与停止

| 分类 | owner / destination | 本次处置 |
| --- | --- | --- |
| 已在 PR / 已 closeout | O03、dotmetadata、O11、O20-F01、O04/O23 assets；#198 | 不计待实施、不重开；只在受影响合同内作为实际基线和回归。四 WU 组合 PR review MiMo34356/DS72633 在途属任务提供状态，本轮不核收新产物、不放 gate。 |
| F5Q1 未决 | HK 下载财期证据/投影 owner；root 的 F5 既有提问 | 仅 F5 公开 mixed-known/unknown 取舍 pending，用户未答不代选。实际 material W→D 直接消费请求 fiscal；HK title→`cn_report_selection.py`→`hk_fiscal_calendar.py` 与 rebuild 是另一条路径。未见原队列业务依赖 Q1；共享文件串行是安排，不是授权/语义依赖。 |
| 同 owner 必要计划修复 | G1 U/C2/C3/PR6、G3 state/O18、G6 PR10 | 后续同 gate 批量必要 fix+同版双审；P12 已 pass 可复用强制条件，其它未通过状态保留。此报告不修旧计划、不把 root/Agent 自报代替 accepted。 |
| 发布确定性 | S `_fs_storage_infra.py:commit_batch/_commit_batch_with_publication_guard`→G5/O12 owner | 当前源码明确 COMMITTED 后释放异常仍可抛，失败不证明 manifest 未发布。不得据失败或 FileExistsError 转 skip；若最终公开合同不能表达确定性，具体停回 owner。独立 `fins-download-indeterminate-publication-state` 归原 residual 队列，不自动新增前置 WU。 |
| 历史/独立候选 | legacy material seed/source strict reader/全局 usage 通道中立、batch `_derive_material_name` owner、历史公开路径/style/取证计数 | 保留原 destination；不做旧库兼容/历史身份迁移，不静默截断 batch 名称，不将 scope 外候选或非关键报告卫生变成本次必修。必要新业务取舍交用户，当前未给证据不设计。 |
| 输入定位/工具限制 | root 输入清单 / 本预备证据索引 | freeze 仅列 missing `docs/gateflow/upload-material-o06-material-name-plan-20260929.md`；rg 实际定位 `o06-name-length-plan-20260929.md`，精确 SHA 在读取清单。任务说“两文件”但 manifest 只有一项，第二精确文件名 needs-more-evidence，不猜。数次宽 cat/rg 输出被截断，随后用窄段核关键事实；探索 rg 对五个不存在路径报错，已用 imports/rg --files 定位真实 D/HK/S 路径，未从不存在 API 作设计。 |
| 最终验收 | root + 正式 CLI CI/oracle/scenario/readiness owner | 两 registry 字面 `registry_status=ready`，实读 6 oracle/1328 scenario，Fins 仅 download/upload_filing，material 正式条目均 0。全部批准修复后必须冻结真正最终 commit、完整新 mandatory 矩阵/真实 CLI/material oracle/scenarios/readiness；旧 Raw 删除不补造，本 proposal 不代这些验收。 |

用户现成 process 独立/direct CLI 不经 FinsAgent/UI print 与 log 分离/SIGINT graceful，以及 CNInfo 新下载中国披露日、历史另议，仍按原 owner/批准边界；本任务没有重开它们或新增未核 source 范围。
实施启动前须由实际最终源码重绑准入、state/guard、publication outcome、selector/handoff 与测试白名单；不得照旧计划中的函数名盲写。必要 owner/API 不存在或证据不足即具体 blocked/needs-more-evidence，不做 fallback、兼容 seam 或下游重算。
本轮仅新增本 proposal 和独占临时证据；未改产品/tests/README/config/旧报告/冻结/总控，未跑 pytest/pyright/cov（文档预备无需此类验证），未 stage/commit/push/PR/merge/branch/worktree。已完成身份及依赖核验，停止，不推进任何 gate。
