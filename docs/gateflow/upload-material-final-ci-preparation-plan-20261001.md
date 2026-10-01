RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-b05d3e9b

# PR197 最终 upload_material 真实 CLI CI 预备计划

任务：`pr197-final-ci-preparation-sol-20261001-01`。运行模型的独立元数据未提供，故实际模型记为 unknown，不从角色名称或 canary 推断。此文交 root 裁决，MiMo/Kimi 独立审查；本 Agent 不派发任何 Agent。

本轮只读准备与新增文档/证据，不是最终 mandatory matrix，不是 accepted oracle、readiness 或 CI pass。真实 CLI CI 全部 **not-run**；没有真实上传、下载、转换、OCR、provider/网络调用或私密输入读取。公开 parser 构造/help 的离线执行只证明发现当前命令面。没有新增持久 Python 脚本，故不触发新脚本非空 include pyright 交付条件；依任务要求未重跑 pytest/full pyright/coverage。

## 1. 身份、真源和停止边界

首次实测 branch=`codex/upload-material-oracle`，HEAD=`244056c50a1cbbff2458a79bc5f3fcbde8086417`，本地 main=`fac32ecbff9bfe792b63ee9667c8697826b631f4`。PR197 OPEN/draft、PR head/base 是本轮输入事实；本 Agent 未做网络 readback，不能冒称独立验证了 live PR/tracking head。末次本地核验见证据文件。HEAD 的非冻结 docs checkpoint 可以变化；冻结字节不能变化。

冻结清单 `workspace/tmp/pr197-final-ci-preparation-sol-20261001-01/freeze.json` 的 SHA-256 为 `d1f162ecb55b01004b62c9d1371446b7321cbbee28b1da70749388a1350ee580`，41 files、allowed=[]。首次逐件比较工作树与独立 originals 的 SHA 均等于清单期望值；末次用同样逐件算法独立读取，不只比较清单文件。证据见 `freeze-start-verification.json`、`freeze-end-verification.json`。两者均在本任务证据目录。

行为 authority 顺序：本轮用户最终选择 → [修复范围与最终收口约束](upload-material-repair-scope-and-ci-closeout-20261001.md)及正式 adjudication → 已接受 goal/plan → 历史建议/当前实现。旧时间线保留但不作 live 门禁。本轮 live 状态采用任务输入：F3 code/aggregate accepted；F4/F7 accepted slices/aggregate；F6 的 21 个未提交候选文件双审在途；F5 mixed known/unknown Q1 尚无具体业务选择。没有把未提交候选当 final commit 或已通过产品事实。

原批准队列剩余 17 修复标签与 XBRL 方向按 root 的现行队列继续；本轮不由旧 artifact 的“未实施”字样重算 live 完成数、不重新裁决 36 项、不实施等待中的修复。最终 CI 必须等待全部 approved 必需修复、必要 review fix、最终提交和门禁核收。F5 未决选择、真实来源授权或关键证据缺失均保持 gap，不能自行填补。

旧 Raw `../.dayu-cli-ci/upload-material-calibration-20260818-mNeTId` 已由用户确认删除。历史三个报告 digest、160 次执行和具体文件内容均未重新核验。不能复原旧原始字节或相同旧 corpus 身份；可以依据仍在的正式裁决重建新场景定义。新 manifest 应分别记录 historical-reference 与本 run verified-evidence，并声明 supersede lineage，不能伪造旧 Raw、重新询问备份或把旧 160 当上限。

## 2. 已核实的 owner 与可用入口

以下是当前源码的入口定位，不能作为正确行为 oracle。额外只读源码的首末 SHA 清单在 `extra-read-start-identities*.json` / `extra-read-end-identities.json`；所有正式裁决 SHA 在冻结清单与 `final-ci-adjudication-index.json` 中。

| 职责 | 当前实际入口/helper | 最终计划的使用边界 |
|---|---|---|
| 静态命令/参数发现 | `dayu/cli/arg_parsing.py:build_parser`、`_register_upload_material_command`、日志选择 `_finalize_log_level_selection` | 用实际 parser action 顺序、choices/default/required/nargs/别名生成 inventory；另保存最终真实 `dayu-cli --help` / leaf help。不能仅用源码 regex。 |
| CLI direct 分发与生命周期 | `dayu/cli/commands/fins.py:_run_fins_direct_command_async`、`_prevalidate_upload_material_request`、`_upload_material_stream`、`_wait_for_terminal_handling_sigint`、`_consume_fins_direct_events` | CLI 参数 → Fins admission → Service → validated stream；同一次事件终态与取消事实取证，不创建虚构 Host Run。 |
| workspace 解析 | `dayu/cli/workspace_root.py:resolve_workspace_root` | 检查 base 别名/默认 cwd/regular-file/链接环；不能在 material 输出层补规则。 |
| direct Service | `dayu/service/fins_direct.py:FinsDirectCommandService.from_workspace_root`、`upload_material`、`process_material`、`process_filing`、`download` | process_material 明确取 MATERIAL；generic process 当前取 FILING，不能用它冒充 material 消费。 |
| 准入与执行 | `dayu/fins/ingestion_runtime.py:admit_fins_upload_material_request`、`ValidatedFinsUploadMaterialRequest`、`_admit_material_upload_facts`、`_produce_direct_upload`；`dayu/fins/service_runtime.py:ProductionFinsUploadRunner._run_material_upload` | 当前已存在资产 handoff；剩余名称/日期/动作/身份等 contract 要在后续 owner 修复后验证，不把现状当完成。 |
| 资产/命名 | `dayu/fins/upload_asset_plan.py:plan_upload_assets`、`docling_storage_name`、`normalize_upload_asset_path`；`dayu/fins/storage/asset_filename_contract.py:source_asset_name_collision_key` | 完整 original identity → derived identity 的唯一 helper；最终 form canonical helper 属 O17 后续修复，不能另写 CI 规范化器。 |
| capability/格式文案 | `dayu/documents/docling_runtime.py:DOCLING_CONVERTER_CAPABILITY`；`dayu/fins/upload_format_contract.py:project_fins_upload_format_text`、`FINS_UPLOAD_FORMAT_TEXT` | capability、CLI/tool/batch 说明与实际部署一致；当前 MAX_MATERIAL_UPLOAD_FILES=100 是实现发现，最终冻结时核对其公共 contract，O04 原裁决本身未给数值。 |
| 身份/版本/转换/发布准备 | `dayu/fins/pipelines/docling_upload_service.py:build_material_ids`、`validate_material_upload_ids`、`evaluate_upload_overwrite_precondition`、`prepare_upload`、`publish_prepared_upload`、`commit_prepared_upload_batch`、`_resolve_document_version` | 只定位 owner；不固定 SHA-1 字面算法、旧派生名或旧 skip 行为为 oracle。 |
| 公司事实 | `dayu/fins/pipelines/upload_company_meta.py:resolve_upload_company_meta_decision`；SEC/CN material workflow 的独立 company/document batch | 公司条件必填、alias 唯一性和发布顺序独立取证。 |
| 仓储 public reads | `dayu/fins/storage/fs_source_document_repository.py:classify_source_integrity`、`list_source_integrity`、`get_source_meta`、`read_source_snapshot`、`get_primary_source` | 文档/内容只经仓储协议读取；完整性与已发布 manifest 条目由仓储 owner 验证，不能读 private JSON 自建业务真相。 |
| 后续读取 | `dayu/fins/tools/read_runtime.py:FinsReadRuntime`、`_create_processor_from_snapshot` | 消费 snapshot 的 primary；后续真实 CLI process_material 与适用真实 prompt/tool read 证明跨命令消费，不能只有文件存在。 |
| wait/Agent 投影 | `dayu/service/fins_wait_adapter.py:FinsIngestionWaitPollAdapter`、`_completed_result_value`、`_failure_message`、`_cancelled_outcome` | 只在实际 Host awaiting lane 关联 canonical EventLog/工具输出/模型输入；与 direct 无 Host 产物分开。 |
| 取证复用 | `utils/cli_ci_run_observation.py:classify_public_evidence_path`、`observe_run_terminals`、`evaluate_success_dependency`、`classify_required_run_evidence`、`scan_public_evidence_files`、`write_final_publication_scan_report` | 前后 FS producer 与最终 scanner 复用 raw DB/path 分类；Host terminal/helper 不能套到不存在 Host Run 的 direct lane。 |

已执行 `.venv/bin/python -B -c …`，直接调用 build_parser/format_help、遍历 argparse action（未启动 main，未初始化 workspace，未写 log 或加载转换器）。真实双流/exit/完整 argv 保存在 `parser-public-help.*` 与 `commands-parser.json`。结果 exit 0、stderr 空，14 leaf：init、prompt、interactive、download、upload_filing、upload_material、upload_filings_from、process、process_filing、process_material、session list/resume/purge、tool_trace analyze。

当前 upload_material 面：ticker 必填；action auto/create/update/delete，默认 auto；forms/files 为 nargs+；material-name/document-id/internal-document-id/fiscal-year/fiscal-period/amended/filing-date/report-date/company-name/overwrite；base/-b/workspace 与公共日志选项。当前仍有 internal-document-id，尚无 material primary selector。它们是待修入口发现，禁止把旧参数转成永久 oracle 或凭空执行尚不存在的 `--primary`。最终 selector 名称以 approved owner contract 和 final parser 为准。

检索范围内的 `utils/` 只有通用 `cli_ci_run_observation.py`，未发现完整的 upload_material campaign runner 或专用 readiness validator。不能把上述 helper 冒称一键 CI。root 后续应先确认可复用 harness 是否存在；如需新增，作为另一个经授权的准备工作交付，不能在本轮实现。runner 必须满足后述模板展开/双流/FS/查询边界/coverage 校验合同。

## 3. 36 项行为 predicate、场景族和边界来源映射

表中 predicate 是对**已裁行为的候选映射**，不新增正式 oracle ID/version。编号 UM-Oxx 是观察/裁决标签。每行读取了正式行为与 repair 段，未用索引引用次数判覆盖。所有场景族均 planned，真实执行均 not-run；同一新场景可承担多行 claim，但各 correctness surface 不能互相抵扣。正式 input/scenario ID 由最终 inventory 冻结阶段分配。

通用取证包 E：exact argv/lexical paths、cwd、stdin/TTY、双流原字节/exit、cast 回放 screen、before/after/diff、仓储 public source/meta/primary/integrity、已发布 manifest 登记、公司独立事实、version/fingerprint、日志与进程时间线；DB/Host/Trace 适用性按第 7 节逐场景证明。表内“零副作用”只适用于对应已裁输入拒绝，不外推到所有转换失败/取消。

| 观察与正式段落 | 当前有效行为 predicate / 后续明确选择 | 必要输入、触发与场景族 | 核对信号、修复依赖及未知边界 |
|---|---|---|---|
| O01 [合并裁决 §UM-O01](../reviews/upload-material-um-o01-o06-oracle-adjudication.md) L28–36 | help 发现公开面，不证明业务可省略或转换成功；内部 ID 按 O07 删除 | root/leaf help，所有公开参数/别名/default/choices；删除参数用正面 inventory deletion 证明 | help+parser 身份；旧 internal ID 场景不保留 coverage 数字，移除要求的拒绝补证与 current scenario 删除分开处理 |
| O02 [§UM-O02](../reviews/upload-material-um-o01-o06-oracle-adjudication.md) L38–52 | 已裁 usage 类拒绝 exit2、普通输出无 traceback；重复 scalar 最后值生效 | ticker 缺失/空/路径型、未知/移除选项、choice/int/value 缺失、文件缺失/目录/不支持、多 forms、日志冲突；合法对照/两次 scalar 次序 | parser 与实际有效请求/零发布；不能外推所有新 typed 业务失败的 exit |
| O03 [§UM-O03/F01](../reviews/upload-material-um-o01-o06-oracle-adjudication.md) L54–75 | 正常路径指向相应 workspace；regular-file base 在 path owner 给可操作错误 | fresh/已有目录、默认 cwd、相对/绝对、别名、重复 base、空格/Unicode、CI 内 symlink、普通文件、链接环 | E、原普通文件字节不变；O03-F01，owner=`dayu.cli.workspace_root.resolve_workspace_root`；PR197-R1-F3 的分析 utils 显式输入路径修复不属此依赖；越出 CI 根的真实操作禁止 |
| O04 [§UM-O04/F01](../reviews/upload-material-um-o01-o06-oracle-adjudication.md) L77–92；O23 L37–45 | 数量/重复 path、basename、规划后真实资产冲突在转换前 typed 拒绝；同 stem 不同 basename 可合法 | 0/1、最终公共上限 N−1/N/N+1（当前 N=100）、重复 path、同 basename 不同父目录、同 stem/不同 stem、original-derived 交叉冲突、逆序、控制名/大小写碰撞 | 无转换/无发布与安全原因；O04/O23 同一 planner 合并 claim，不注册两套冲突规则 |
| O05 [§UM-O05/F01](../reviews/upload-material-um-o01-o06-oracle-adjudication.md) L94–110 | form/name 无条件业务必填，开始上传前拒绝缺失/空 | 每种 action 的缺失、空、trim 后空；有效对照；配 missing target 验证输入优先级 | 无 upload.started、无材料发布；O05，与公司条件必填区别 |
| O06 [§UM-O06/F01](../reviews/upload-material-um-o01-o06-oracle-adjudication.md) L112–122；本轮用户选择 | material_name trim 后最多 240 Unicode 码点，不静默截断 | 239/240/241、前后空白、中文/非 BMP、组合字符分解序列；合法公司/文件隔离混杂 | 名称/ID/meta/LLM 投影同源，超限零发布；O06。计数是码点，不能换成字节/字素 |
| O07 [Accepted/两个修复](../reviews/upload-material-um-o07-oracle-adjudication.md) L24–64 | stable identity owner 生成；public document_id 只作一致性断言；移除全 material 用户链 internal ID | 省略 ID、正确断言、错误断言；旧 internal ID 空/非空拒绝的补证；CLI/tool/batch 输入声明核对 | ID/事件/meta/manifest 一致，错 ID 零副作用且尽早拒绝；O07-F01/F02。不固定摘要算法 |
| O08 [Accepted/修复关联](../reviews/upload-material-um-o08-oracle-adjudication.md) L22–34 | 显式空 public document-id 在 CLI 输入拒绝且零持久化；内部空值行为不接受 | 空/空白 public ID 与省略有效对照，旧 internal 空值移除补证 | 与 O07 共享场景，不增加“保留内部 ID 空值规则”的 oracle |
| O09 [F01](../reviews/upload-material-um-o09-oracle-adjudication.md) L29–46 | fiscal_year 合法域 1800–2100 含端点；身份生成前拒绝域外 | 1799/1800/2100/2101、−1/0/10000、2024、非整数 parser 类 | 公司/文档零业务发布、ID/meta 同源；O09；不冻结错误文案 |
| O10 [Accepted/F01](../reviews/upload-material-um-o10-oracle-adjudication.md) L24–52 | period trim/uppercase、空→null；仅 FY/H1/Q1/Q2/Q3/Q4 | 六枚举逐项、` q1 `、空/空白/省略、nonsense/超长；配 form 规范化 | source identity/meta 一致、非法零发布；O10/O17 同源，长度被枚举吸收 |
| O11 [Accepted/F01](../reviews/upload-material-um-o11-oracle-adjudication.md) L24–50 | 非空 filing/report 日期严格 YYYY-MM-DD 且真实公历；空 filing_date→null | 合法闰日/非法闰日、2025-02-30、格式缺位/垃圾、两个字段分别测试；空 filing、合法对照 | parse_iso_calendar_date owner，先于公司/文档持久化；O11。空 report_date 尚未由该裁决定义，留 decision/evidence gap |
| O12 [Accepted/F01](../reviews/upload-material-um-o12-oracle-adjudication.md) L23–50 | 状态条件公司名必填；真实 alias 不能被另一公司占用；不得把 company-name 无条件 parser 必填 | fresh auto/create/update 缺名/有名，既有公司可省名路径，canonical 与真实异名冲突、并发 final check | 无 started/零业务副作用的缺名拒绝；公司唯一性发布 owner；O12。ticker 等价后缀去重另由 O26 解释 |
| O13 [Accepted/F01](../reviews/upload-material-um-o13-oracle-adjudication.md) L26–47 | auto fresh→v1，相同→skip、不同→升版；delete tombstone 幂等；恢复同字节保 ID/版本 | create baseline→同 auto→异 auto→同 update→delete→重复 delete→同内容 auto restore→再次 delete | 重复 delete meta/manifest/tombstone 时间字节保持；恢复再删为新周期；O13。异内容/并发恢复须独立取证，未获新状态语义不猜 |
| O14 [Accepted/F01](../reviews/upload-material-um-o14-oracle-adjudication.md) L23–44 | active 目标 create 无 overwrite，同/异内容都 typed conflict，零公司/文档业务发布；overwrite 可替换 | fresh create、active same/different create±overwrite；配 O18 同字节强制转换 | admission/最终 publication、ID/version/meta/manifest；O14。tombstone create 未被旧证据裁定，标待决边界 |
| O15 [Accepted/F01](../reviews/upload-material-um-o15-oracle-adjudication.md) L23–43 | update/delete never-existed 前置 typed missing；overwrite 不赋予 upsert；重复 tombstone delete独立 | fresh/既有公司 missing update±overwrite、never delete、tombstone delete、合法 update/delete、竞争消失 | 无 started/零业务发布，锁/脚手架另记；O15，与 O16 输入组合优先级分开 |
| O16 [Accepted/F01](../reviews/upload-material-um-o16-oracle-adjudication.md) L26–46 | auto/create/update≥1 file，delete=0；非法组合不转换、不忽略、不删除 | fresh/active/missing 三类无文件动作，delete 带一/多文件，合法正例；与 selector 组合 | typed action/files 原因、稳定输入拒绝顺序；O16/O15，不从混杂旧例推出结果 |
| O17 [Accepted/F01](../reviews/upload-material-um-o17-oracle-adjudication.md) L22–40；本轮选择 | form trim/uppercase 单一 canonical helper，ID/meta/manifest/事件使用同一值 | ` material_other ` / MATERIAL_OTHER 独立配对，US/CN/HK；结合 period | 两次真实输入 ID 等价与持久化 canonical 一致；O17，不新设 form 枚举/长度 |
| O18 [Accepted/F01/补充选择](../reviews/upload-material-um-o18-oracle-adjudication.md) L22–50 | amended 独立布尔事实，不入 ID；同字节改变标记无 overwrite 只metadata保内容版本，overwrite强制Docling并发布、版本仍按fingerprint | 基线 false/true × incoming false/true × overwrite false/true 的八格同字节；首次 amended、异字节±标记、delete/restore 取证 | source meta→manifest/result 同源，重转换真实进程证据、版本不机械递增；O18/O12/O14/O15。未定义的恢复细节只记录待裁，不能重开已裁八格 |
| O19 [Accepted/E01后续](../reviews/upload-material-um-o19-oracle-adjudication.md) L34–64 | 支持格式每文件进入 Docling，成功 original+JSON；抽取质量归上游；CI内 lexical symlink 补证有独立 lineage | PDF/DOCX/PPTX/HTM/HTML/XHTML/MD/TXT/CSV/XLSX；大写 .TXT、空格中文路径；准确传 lexical symlink | E+original digest/转换产物对应；O20 子类型另列；旧 F15 仅普通目标，后补成功不扩展悬空/越界链接契约 |
| O20 [Accepted/F01/E01/F02](../reviews/upload-material-um-o20-oracle-adjudication.md) L27–63；本轮 XBRL 已批准方向 | .json=Docling JSON；.xml/.xbrl=XBRL instance 候选；后缀非成功保证；部署 capability/依赖一致 | 本 run 真实 Docling JSON 正样本；完整 instance+taxonomy/dependency；普通 JSON/XML/linkbase 负例；受控 OS 矩阵 | 来源/version/hash/依赖/OS/manifest；XBRL 受控推进不能擅自改为移除支持或编本地抽取器；具体 corpus 与运行前置尚 gap |
| O21 [Accepted/F01](../reviews/upload-material-um-o21-oracle-adjudication.md) L25–45 | 不可转换文件 typed content failure，safe file_label 同源；多文件任一失败零材料部分发布 | corrupt PDF/DOCX、valid+corrupt 正逆序，US/CN/HK普通/debug | converter owner标签→事件/result/durable；company 可独立留存；O21。不声称任意 commit 故障已验证 |
| O22 [Accepted/F01](../reviews/upload-material-um-o22-oracle-adjudication.md) L24–42 | 0字节在Docling前产生已有 content/empty_input_file，安全标签/非空文件建议 | 单/多文件空字节、有效对照，filing共享原字节准入回归 | 无转换/无材料发布、普通/debug分类一致；O22/O21共同传播，不新增 runtime 错误 |
| O23 [Accepted/F01](../reviews/upload-material-um-o23-oracle-adjudication.md) L35–45；本轮唯一helper选择 | 完整 original storage identity→derived 唯一规划；同stem不同basename可成功；全集合唯一 | probe.txt+probe.md / deck.txt+deck.md、真实交叉冲突、重复path/basename、逆序、不同stem；都带最终合法 selector | 两 original+两JSON、primary/manifest映射；O23细化O04，共享 helper 同时回归filing；旧commit回滚不当可接受行为 |
| O24 [Accepted](../reviews/upload-material-um-o24-oracle-adjudication.md) L35–39 | 多文件全部转换完整发布；同主文件/同文件集逆序 ID/role-aware fingerprint 一致 | 真正不同stem多文件、正逆序、同selector；不同selector对照 | requested/stored originals计数、2+2资产/角色；必须新带selector，旧无selector成功不是正向oracle；无独立修复，合并O25 |
| O25 [Accepted/F01](../reviews/upload-material-um-o25-oracle-adjudication.md) L32–46 | 多文件显式唯一 exact-path主原件；单文件自动；角色进入fingerprint/skip；ID仍业务身份 | 缺/合法/重复/未命中selector、delete带selector、单文件省略、同workspace改primary、逆序同主、同stem组合 | 对应derived为primary，改角色不错误skip，真实process_material/read消费；O25。当前参数名尚未落地不能先冻结 argv |
| O26 [E01/Accepted](../reviews/upload-material-um-o26-oracle-adjudication.md) L21–29 | US/CN/HK真实文件转换与发布、按各owner实际字段断言；等价后缀ticker并非独立alias | 每市场授权真实PDF/DOCX等受控样本；真实异名alias另建对照 | company-name在公司、year/period与alias字段按final schema真实归属；不复制旧全字段都在manifest的摘要；无独立产品修复 |
| O27 [Accepted](../reviews/upload-material-um-o27-oracle-adjudication.md) L21–27；本轮process单跑选择 | 上传不自动process；真实process_material按exact ID/source版本/primary独立消费 | US/CN/HK上传→检查processed未生成→同base process_material；多文件选主变更→新消费 | processed/source identity/version/fingerprint对应，读primary不按argv重选；不拿generic process(FILING)代替；无独立修复 |
| O28 [Accepted](../reviews/upload-material-um-o28-oracle-adjudication.md) L21–27；本轮direct选择 | direct CLI发布Fins业务事实，无需FinsAgent/Host Run/Trace/Memory/legacy job产物 | upload/process direct；明确定位查询；tool_trace analyze对无布局workspace的对照 | queried/absent/owner_scope/候选模式；不能把无DB写成无持久化，也不能扩到Agent工具lane；无独立修复 |
| O29 [Accepted](../reviews/upload-material-um-o29-oracle-adjudication.md) L33–39；本轮UIprint/log选择 | 日志等级不取消业务进度/终态；日志append；quiet/debug-stream冲突顺序无关；显式files不被stdin替代 | 全日志枚举/快捷别名、quiet/debug-stream各自合法及两种冲突顺序、同log两次上传/skip、pipe/DEVNULL | 双流与log前缀追加关系、E；无独立修复，不由debug-stream无额外stdout判断诊断是否生效 |
| O30 [Accepted](../reviews/upload-material-um-o30-oracle-adjudication.md) L23–29；本轮SIGINT选择 | SIGINT graceful有界退出、取消不报成功、无本次残留worker；早期不强制业务取消文本 | early/运行中/Docling活跃切点、同base原argv重试；信号时间以实际事件/进程证据标定 | exact signal target/time、退出/双流、进程树和终端恢复；不要求所有取消零FS或公司回滚；无独立修复 |
| O31 [Accepted](../reviews/upload-material-um-o31-oracle-adjudication.md) L23–29 | 进程组SIGKILL与同base重试窄行为；无协作取消机会 | CI-owned独立process group、publication前活跃切点 killpg、同argv重试 | -9/no业务终态为观察，残留0归外部kill条件；不能证明只杀parent、任意commit时点；无独立修复 |
| O32 [Accepted](../reviews/upload-material-um-o32-oracle-adjudication.md) L24–30 | 同ticker不同文档/不同ticker并发文档完整共存，manifest不丢更新 | 两类pair同步启动/结束，标注shared before/after归属 | 每成员终态/ID及pair最终仓储状态，不能把共享diff全归每成员；无独立修复 |
| O33 [Accepted/F01/新证据范围](../reviews/upload-material-um-o33-oracle-adjudication.md) L25–43 | identical fresh auto并发：权威state线性化为一create一verified skip，唯一完整文档、skip不重写；无法证明相同则typed真实冲突 | 同identity同字节pair重复轮、异字节竞争、顺序auto、不同identity对照；owner有界异常诊断 | 再验证identity/fingerprint/integrity，不能泛storage_io→skip；O33。后续诊断解释该HEAD该次，不能反推旧L06根因 |
| O34 [Accepted/代码顺序](../reviews/upload-material-um-o34-oracle-adjudication.md) L35–49；本轮成功/独立发布选择 | 每文档所有文件Docling后，权威已发布manifest登记才文档成功；company与document独立发布 | 正例、身份拒绝/转换失败/取消/冲突，分别核公司与文档；download同公共必要条件受影响回归 | staging≠published；缺条目⇒未成功，不能倒推有条目⇒CLI必成功；post-commit异常/极短commit窗口尚未定义采集方法，不以mock补证 |
| O35 [Accepted](../reviews/upload-material-um-o35-oracle-adjudication.md) L25–31 | raw/index一致、双流/exit/signal/timeout/residual真实记录，汇总不推产品成功 | 每场景取证校验，真实timeout预算边界另列、取消/强杀归属 | 不复用旧160/500ms为普遍保证；timeout未真实触发则明确gap；无独立产品修复 |
| O36 [E01/E02/Accepted](../reviews/upload-material-um-o36-oracle-adjudication.md) L17–28 | 15前置归因替代+3标签替代的历史lineage；S12/S16基线、S18–22诊断；补证不关闭其它义务 | 新模板先校验precondition/argv，same-stem与distinct-stem按actual basename；输入拒绝隔离公司/目标缺失混杂 | preserve历史引用、new-run替代，不机械25全失效；O33/timeout/commit后证据仍独立gap；无新修复 |

### 3.1 整合与未知项处理

O04/O23 同一资产规划合同；O07/O08 同一内部ID删除和公开ID断言；O10/O17 共享规范化但分别保留 period 值域/form 投影 surface；O21/O22 同一 typed reason/label 传播但空字节与转换失败的触发不同；O24/O25 同一多文件/primary/role fingerprint场景组；O27/O28 相同 direct 链但“消费成功”与“Host治理不存在”分别举证；O30/O31 不合并信号语义；O34/O35/O36 是发布/证据/lineage约束，不能给别的义务提供 coverage 抵扣。

已有来源不足以给以下新业务分支写最终期望：F5混合确定/不确定Q1；显式空report_date；tombstone显式create；未被后续approved owner contract定义的不同内容/并发恢复；任意commit时点强杀、parent-only kill、post-commit异常、timeout公共语义。最终inventory若证明它们在scope内，保留候选场景与correctness gap，root先查已有具体选择；查无后才提交新的具体问题，不重裁既有36项。成功manifest的必要条件、graceful SIGINT及同字节overwrite规则已明确，不列成待决。

## 4. 输入资产清单与解除条件

本轮不生成输入、不下载、不转换。输入记录最少包含：新本地asset引用、业务/格式类别、生成方法或公开来源、源文档/发行人/市场/披露期、版本/发布日期、原件字节SHA256、文件长度/实际媒体类型、license/使用授权范围、所需dependency/taxonomy/OS/设备、允许网络/写入边界、适用场景族、old/new lineage。不存在的hash/version留null+gap，禁止写随机digest占位。

| 资产类 | 后续可取得方式 | 覆盖范围与当前状态 |
|---|---|---|
| 纯合成TXT/MD/CSV、HTM/HTML/XHTML | 在授权CI-owned inputs根生成有效小文档，固定UTF-8内容与生成器版本；正文用明显合成标记，无私密数据 | identity、动作、边界、重复/覆盖、primary、log；planned/not-run，生成后hash。HTML/XHTML必须真正对应声明语法，不只是改后缀 |
| 合成PDF/DOCX/PPTX/XLSX | 合法格式生成工具/库按冻结版本生成小文档；记录容器版本、生成recipe和hash；实际Docling转换仍必须真实 | O19各格式+多文件/取消；合法生成不等于已转换成功。大文件/扫描版PDF只有实际义务需要才生成，OCR模型资产须受控 |
| 空/损坏/非支持/普通JSON/XML/linkbase | CI-owned生成0字节、可复查损坏容器、子类型不符内容；记录操作recipe与合法母本hash | O02/O20/O21/O22；损坏样本可合成，但不能把普通JSON/XML负例当有效XBRL正例 |
| 重复/路径/边界材料 | 同源文件复制命名、两个目录同basename、same-stem different suffix、original-derived collision、Unicode/空格/大写、100±1计数、CI内lexical symlink | O03/O04/O19/O23/O25。词法路径与target分别记录；链接不可让真实执行越过授权根 |
| Docling JSON正样本 | 从本run真实转换成功产物经仓储public source读取，冻结Docling/Docling-core/schema版本与原母本、输出hash；再次通过真实upload_material转换链 | O20-E01。禁止手拼“看似Docling”的JSON冒充真实正例；当前尚无新产物 |
| US/CN/HK真实财报材料 | root登记具体授权公开URL/来源标识或授权可读文件路径、发行人/报告名、发布日期与version/hash；后续执行者才采集 | O26/O27市场真实正例。旧R01–03只历史标签，旧输入不可恢复；本轮未获具体新来源/版本/hash，**input-source gap** |
| 有效XBRL instance .xml/.xbrl | 受控真实instance及taxonomy/schema/linkbase依赖完整包；授权公开来源或授权文件，固定bundle hash/URL/version、离线catalog/cache策略和允许访问域 | O20/XBRL方向。不是任意XML或单独linkbase。具体来源、version/hash、taxonomy包、dependency与OS支持清单尚缺，**blocked until supplied/frozen** |
| Docling/XBRL部署依赖与OS | final commit对应lock/build digest；Python/Docling/Docling-core/arelle等实际包版本、可选依赖、模型资产/网络需求、macOS/Linux/Windows支持范围与backend/device | 用户批准受控推进，当前没有受控运行快照，不能声称某OS成功或把缺依赖归内容损坏。只测用户批准的支持OS；若额外OS属于新产品支持，另issue/具体决定 |
| 下载真实财报与CN披露日边界 | 对最终回归inventory中所需SEC/CNInfo/HKEX文档授权具体source；CN新记录中国本地披露日的跨UTC日界样本/公开时间依据 | F6相关download回归。历史披露日迁移另议，不能变成本轮自动采集/回填旧数据 |

纯合成输入能够重建边界场景，但不能替代O26真实市场材料、有效XBRL和真实外部依赖。当前未知项不是用户否决CI；root把具体来源/可用性/授权登记完才解除相关执行阻塞。若本轮没有新来源，留gap，不联网自行搜集，不要求用户寻找已删除旧备份。

## 5. 从最终门禁到readiness的可执行顺序

下列均是后续执行者步骤，本 Agent未执行。合同 owner=[docs/cli_ci.md](../cli_ci.md) §§2.1–2.8、4.3–4.7、5.1、6、11、13。历史tmux Agent通信/phaseflow路由由本轮外部runner协议替代；不调用其代理路由。终端采集资源若需tmux只属于CI运行资源，与派发Agent不同。

1. **完成approved开发门禁**。root核对原剩余17标签、XBRL及优先F3–F7；F3/F4/F7已accepted状态不重审旧裁决。F6先同版MiMo/Kimi审查/root裁决；F5先得到Q1具体选择，再完成approved slice。产品测试、非空类型验证、README、同版review、最终PR review/closeout仍由开发门禁负责，本预备文档不能替代。每个gate绑定真实代码SHA；root提供当前queue身份，不从旧artifact计数猜17个剩余名字。
2. **绑定final对象**。全部成果在唯一开发分支进入final commit后，只读核local/tracking/live/PR head一致、PR197仍OPEN/draft、实际base SHA与预期main一致。记录最终head/base、dirty排除集、repo remote身份与锁文件digest。当前21候选文件不得带入正式验证对象；本轮HEAD不是最终CI freeze。若base已合法变化，root显式记录新base及review影响，不能沿用旧SHA假称一致。
3. **冻结最终inventory并决定scope/profile**。在最终只读验证快照/隔离venv中直接运行build_parser导出root/全部leaf/action顺序；真实公开help双流取证；保存exact-byte和canonical inventory digest，二者用途区分。以owner交互声明、help/提示、真实运行discover建立独立interactive inventory，不写“无交互”结论仅因regex未找到input。声明in-scope upload_material及第6节受影响commands，每个其它leaf记录out-of-scope理由。当前两个registry的ready/proof不覆盖material，不能选material full-real；先按完整material范围的calibration-real组织新证据，正式proof闭环后才可使用适用full-real标准。focused-real仅局部诊断，不缩mandatory。
4. **构造完整mandatory候选矩阵**。由每个parser参数/default/choice/正反开关/依赖、每个动态branch与所有precondition/input类产生稳定coverage义务；单维全覆盖、pairwise+历史高风险组合。至少纳入第3节全部场景族，以及discover的新分支。把纯场景定义/触达目标/required evidence与判定层的已裁predicate分开；invocation不预写outcome。最终数量在算法展开和root核验后给出，不能固定160，也不能因预算不足删义务。
5. **冻结corpus与policy**。先补第4节来源gap；每个input先生成/采集于授权CI根再计算真实hash，冻结依赖/taxonomy/OS/model/provider policy与成本、时间、磁盘、外部写入授权。每场景映射input资产+前置状态recipe+oracle authority。有效XBRL/Docling JSON必须有完整正样本链。秘密只用既有secret-ref，不回显值；与private workspace隔离。
6. **建立新run**。root后续按既有授权建立CI-owned run root、marker、immutable run manifest、final SHA detached只读验证快照和final lock一致venv；此处只是计划，不在本轮开worktree/branch。固定UTF-8/TERM/终端尺寸，创建workspaces/logs/casts/evidence。run manifest写input/inventory/matrix/authority各digest、finalhead/base和历史Raw已删除状态。目录外部归属及清理规则依§2.8，不写共享workspace。
7. **逐场景真实执行**。先验证fresh/active/tombstone/partial/conflict前置，前置失败不得假执行后继；依赖helper只控制是否尝试，不产生产品verdict。使用实际final argv数组，保存lexical输入、stdin/信号/选择时间线、双流/exit/进程树；前后同一bounded查询/snapshot。根据真实TTY/非TTY发现交互，新增branch则扩matrix并新run补证，不改已冻facts。预算或依赖阻塞留blocked/not-run，outcome留无值。
8. **跨命令消费/证据关联**。每个已发布材料由同workspace真实process_material独立消费；primary变更/版本更新须消费新revision。若需要LLM read验证，使用实际prompt/awaiting tool lane与真实provider，保存effective tool schema、runner input、Host canonical EventLog/Trace/Memory对应事实；不强迫direct产生Host Run。download/upload_filing按第6节最小真实依赖矩阵回归。DB与Fins body读边界见第7节。
9. **冻结新observed report**。严格按§11.1生成主体：内嵌关键screen/literal输出、输入选择、生成物和业务/diagnostic before/after/delta、跨命令实际消费与gap；facts中不写修复方案/期望。核脱敏、raw refs、artifact SHA和mock/fake absence；生成exact UTF-8 SHA后冻结报告与evidence。observation_completeness仅由全部义务执行及证据充分性计算，不由exit0或error/cancel决定。
10. **映射裁决并独立审查**。MiMo/Kimi只在新report freeze后独立审证据充分性与既有predicate映射，root保留分歧并裁决。已裁36项直接引用本表来源及后续选择，不请用户再裁一次；新行为/未定义正确性surface才needs-more-evidence或具体业务决定。违反effective已裁规则为implementation failure，不能改oracle使代码通过；必要后续owner修复仍走既有授权门禁，新commit新run。scope外独立问题登记owner/destination，不自动扩实施范围。
11. **正式registry/lineage收口**。后续获授权的登记工作在开发分支维护 `docs/cli_ci_oracles.json` / `docs/cli_ci_scenarios.json`。oracle scope.command、scenario顶层command正确使用；按稳定predicate解析到恰好一个current accepted owner，历史accepted_oracle_refs不批量迁移；新版本保supersedes/superseded_by、旧raw不可用历史注记与新report digest。新正式ID/version仅此时分配，本轮不发明。现有其它命令record不原地改写。本步若改变最终PR head，root区分被测产品commit和登记commit，核对产品/parser/corpus/policy/oracle不变的复用证明；无法证明则新finalhead新run，不假称旧run绑定新head。
12. **重算readiness与最终收口**。两registry proof逐条验证：inventory未分类=0；mandatory有accepted claim；每场景sufficient frozen evidence；每surface有accepted oracle或适用objective/hard contract；rejected遗留gap有replacement或用户out-of-scope决定；双向refs无dangling/duplicate current owner；无not-run/blocked/unresolved evidence/correctness gap。proof列分维mandatory/covered/gap counts、target/inventory/version/digest、用户裁决identity、report digests与validation result，registry_status只由结果派生。readiness、observation completeness、产品verdict分别报告。PR review及最终CI均明确最终head/base；只有完整实际矩阵正确且无gap才可能full-real-pass，最后交用户手工merge，Agent不merge。

### 5.1 后续命令展开模板（本轮未运行）

实际CLI executable应为final验证venv的 `bin/dayu-cli`，不能继续引用控制工作树可变源码。`RUN_ROOT`、`CLI`、`BASE`、`FILE`、`DOCUMENT_ID`都是后续manifest内真实值；shell模板需由runner转换成argv数组保存，避免quote/空白/Unicode改变输入。

```text
[CLI, "upload_material", "--base", BASE, "--ticker", TICKER,
 "--action", "auto", "--forms", FORM, "--material-name", NAME,
 "--company-name", COMPANY_NAME, "--files", FILE]
[CLI, "process_material", "--base", BASE, "--ticker", TICKER,
 "--document-id", DOCUMENT_ID]
[CLI, "tool_trace", "analyze", ...final-parser-discovered-options...]
```

多文件模板必须在final parser发现并核对approved selector contract后加入**实际唯一selector参数**；不能目前硬写不存在的material `--primary`。document_id来源为权威已发布结果/public仓储读，不由CI重算hash。delete模板不带files/selector，仍带无条件form/name。正确ID/错ID、overwrite/amended/date等从第3节输入类展开，不预填exit或业务status。

## 6. 其它命令回归边界与gate影响

此表只圈实际共享owner的必要回归，不要求重做init/prompt/interactive全部既有1328场景，也不借受影响回归改旧oracle。全leaf仍由final inventory分类；受影响command内的mandatory由实际diff/依赖与合同生成，不只各跑happy path。

| 触发owner/gate | 受影响命令/lane | 后续证据和范围 |
|---|---|---|
| O03 workspace与共享CLI入口（owner：`dayu.cli.workspace_root.resolve_workspace_root`） | upload_material、upload_filing、download、process/process_filing/process_material；upload_filings_from输出路径按final路径owner | 相对/default/alias/regular-file/链接环前置拒绝、有效对照，原文件不变；PR197-R1-F3 是五个分析 utils 的显式输入路径修复，code/aggregate accepted，与本行 workspace owner 独立；本轮不重跑产品测试 |
| O04/O23/O25资产选择/命名/primary | upload_filing、material、upload_filings_from生成material请求 | filing唯一primary+companions不误全转换；同名/真实derived冲突；batch生成exact argv/selector再由真实CLI消费。脚本生成成功不是上传成功 |
| O13/O14/O15/O18/O33共享source动作/version/publication | upload_filing、material；download对相同source/integrity提交边界 | delete幂等/restore/overwrite/missing/并发/指纹、manifest；不用material语义覆盖filing独立来源ID或已冻oracle |
| O21/O22/shared failure label及F6 typed reason | download CN/SEC及必要HK映射、upload_filing/material、direct与awaiting | owner产生真实conflict/empty/content，screen/typed stream/LLM投影一致；21候选只确定潜在影响，不证明通过。CN新披露日跨日对照，历史迁移不做 |
| F4/F7 accepted slices/aggregate | final diff实际触达的共享upload admission/state/publication及消费者 | exact final SHA的真实场景验证；本轮没有读取其非冻结review artifacts，不推断未提供的细节或再裁accepted目标 |
| F5 pending Q1 | mixed known/unknown摘要及其direct/wait/job消费者（final实现决定实际范围） | 先用户具体选择；不能以当前counts/status含义当oracle。业务决定将影响场景期望、summary字节、LLM-facing/durable投影与readiness |
| Fins direct stream/terminal与CLI output | download/upload/process direct | success/error/cancel/clean exhaustion、终态只有一次、真实exit和关闭/worker清理；UI print与log分开；无虚构Host产物 |
| 同runtime的observed wait与legacy job接口 | `prepare_observed_upload/download/preprocess`、`poll_observation/cancel_observation`、`FinsIngestionWaitPollAdapter`；`start_upload/read_job/read_job_events`等 | 先用真实入口/授权确定可达lane；Host lane需要真实provider/tool触发，再查Host public truth/Trace/memory/input。legacy job是独立路径，不把不存在的wait/job顶层CLI命令编入parser矩阵 |
| process/read snapshot | process_material、process_filing、generic process和适用真实prompt/read | exactsource/processed/version/primary消费；generic process current FILING。真实Agent读取才需额外provider授权与输入，direct正例不强制用Agent |

最终F6候选是否accepted由root同版审查决定；若review使字节变化，重新hash、重新导出inventory、更新affected obligations。final PR diff/readiness登记本身若改变finalhead，遵循§5.11的复用证明或重跑要求，不把旧测commit宣称最终head。

## 7. 动态、终端和跨层取证合同

### 7.1 声明与discover

当前source定位显示direct stream SIGINT监听、显式files/stdin分离；本轮只运行parser help，**未真实discover动态分支**。final inventory必须至少核：help是否新增selector/删除内部ID；运行中的取消、第二次中断、TTY/non-TTY输入、EOF；主文件/overwrite条件是否出现提示；batch产物后继如何运行；错误状态是否引导重试。没有真实触发的branch不得标executed。若direct声明无prompt，保存owner声明+真实TTY/non-TTY观察证明；不要从源码缺少input调用直接判无交互。

每个dynamic branch/option记录owner、触发条件、前序输入链、public提示literal、实际按键/time、TTY条件、stable候选ID与digest。新discover扩义务；旧report不回写。合法但未裁新分支仅收事实，在新report冻结后再交root。

### 7.2 每场景所需证据

| 信号层 | 必需证据/适用性 |
|---|---|
| 执行 | command.json exact argv数组/词法路径、cwd、workspace identity、stdin/TTY、非敏感env/policy refs、开始/结束、原始stdout/stderr字节、returncode/signal/timeout；PTY cast不替代独立双流 |
| 屏幕 | 固定尺寸与locale/TERM、按键/选择序列、回放后的关键screen和finalscreen；内嵌literal，说明ANSI清除/重复行/prompt恢复/增量区域实际观察，不只列文件名 |
| FS | 相同bounded before/after算法与diff；从producer开始复用 `classify_public_evidence_path` 排除rawSQLite main/WAL/SHM路径，不在报告下游字符串删除；保存相对归属、created/modified/deleted、关键内容/metadata摘要与hash |
| Fins durable | 仓储协议public snapshot/meta/integrity/revision/primary及published manifest登记；original/JSON一一对应，counts不把两类资产混成stored originals；company与document各自delta；不从私有布局或DBbody推语义 |
| 日志 | 显式run-owned log-file，debug/normal分开，append前缀字节比较，事件与错误时间线；日志是diagnostic，不能由started推company已commit |
| 进程/取消 | CLI PID/PGID、子进程启动/结束、实际signal对象与时间、终态、清理后的观测窗口；early/Docling/post-publication切点不能只以固定sleep宣称触达；SIGKILL方法/采集器归属分开 |
| direct布局 | 对runtime/源码证明相关的SQLite/Host Run/EventLog/Tool Trace/Memory/job定位逐项查询记录queried/exists/owner_scope/候选模式，缺席是实际观察，不代表无Fins业务持久化 |
| Host/Agent | 仅适用实际Agent/awaiting lane：session/run/attempt/execution/tool-call identity，canonical EventLog、Tool Trace、wait outcome、memory/source refs、实际RunnerInput/effective tool schemas、UI/result；使用同ownerprojection，不手拼Host facts |
| SQLite | §11.2 checklist：判实际是否读写CI-owned SQLite。存在则bounded read-only URI + connection-local query_only，SELECT/明确metadata、同query before/after/delta、行/字段/字节/时间限额与identity/timewindow；不导出rawDB/path，不读Fins body/section/table/provider payload；不适用须直接证据，安全/归属不足记blocked |
| public Trace/扫描 | Host lane的Tool Trace通过production tool_trace analyze产生，public可分发输入用canonical cold JSONL；`observe_run_terminals`等只对实际HostRun使用。secret scan用当前实际secret内存probe与canary，不输出secret值；rawDB path hygiene与secret分别报告 |
| 交叉消费 | 同base真实process_material以及适用read/tool invocation与返回片段；同source ID/version/fingerprint/primary；实际未消费的产物记coverage gap，不能只信upload自报 |

业务manifest取证必须证明**已发布**条目与文档事实，不只是读到staging文件；仓储public integrity/snapshot与owner提供的必要manifest投影共同举证。若现有public投影不能回答条目问题，记录public-observability-gap交storage owner，不能在CI脚本解析内部JSON私自补真源。

每文档Docling+manifest必要条件不等于所有失败都零company变化；转换失败/取消留下合法company是已裁独立发布事实，前置非法metadata/identity/target拒绝的零业务发布规则分别验证。

### 7.3 状态和判定

`planned`=定义待执行；`attempted`=有真实启动尝试记录；`executed`=命令确实运行且有过程事实；`not-run`=未尝试；`blocked`=依赖/授权/前置阻塞。not-run/blocked没有execution_outcome。本轮公开parser探针属于准备命令executed，不计真实CI场景executed；所有真实CI义务为planned/not-run，来源/业务决定缺口另记blocked prerequisite。

execution_outcome success/error/timeout/cancel、evidence_status sufficient/missing/corrupt/ambiguous、gap_kind及readiness分别记录。error/cancel可证据完整，exit0不能证明correctness。后续run唯一primary verdict按§2.7优先级 `fail > blocked > oracle-review-required > limited-signal > full-real-pass/focused-real-pass`；本预备计划不产生run primary verdict。generic success汇总字段不能盖过actual cancel/error。

## 8. 残余分类、owner与destination

| 残余 | 分类 | owner / destination / 解除条件 |
|---|---|---|
| 原已批准必需修复尚未全部完成 | covered by later approved slice；当前执行前必需 | root现行17标签queue+XBRL方向；按原approved gate完成/最终commit，不能拿本文替代closeout |
| F6 21候选双审与最终必要fix | covered by later approved slice；当前执行前必需 | F6 owner/root同版MiMo/Kimi裁决；accepted后提交并核影响矩阵 |
| F5 mixed known/unknown Q1 | requiring explicit user decision；当前执行前业务阻塞 | root保留Q1，到具体选择后实施approved owner slice；不由runtime/provider派发授权代选 |
| final commit/local-tracking-live-PR identity、final PRreview/CI绑定 | assigned to later work unit/closeout；必需 | root最终收口；本轮仅本地head/base读回，网络readback not-run |
| material inventory/interactive discover/矩阵/数量、正式registry ID/version/proof | assigned to later CI preparation/registration；必需 | CLI CI owner/root；final parser+真实发现+全claim+冻结新证据+既有裁决映射，无dangling/gap才ready |
| 真实市场/XBRL来源版本hash授权、taxonomy/dependency/OS | input/dependency/authorization gap；相关执行必需 | root/corpus与Documents runtime owner；第4节逐项明确来源和受控环境，未解除不下载/转换 |
| 旧Raw/旧corpus不可复核 | historical evidence unavailable；不能恢复 | 证据owner；新run显式lineage与全新identity闭环，不删除历史，不要求重裁36项 |
| O19/O33新证据artifact在冻结允许清单外 | later evidence-source mapping gap | 已读取正式裁决中的后续段足够保持语义；root最终阶段若要引用那些raw则单独冻结授权身份，本轮不读取清单外artifact或声称hash已核 |
| 空report_date/tombstone create/未定义恢复等 | requiring new explicit decision only if final in-scope且无已有approved规则 | root先核已有具体选择/ownercontract；未定义留correctness gap，不能默认通过或偷偷缩scope |
| timeout/parent-only kill/任意commit窗口/post-commit异常的普遍保证 | requiring evidence/design decision；不能从旧窄观察泛化 | lifecycle/storage owner+root；已有mandatory timeout按真实方法取证；新增更强产品保证需明确issue/决定，不用fake完成真实CI |
| 完整campaign runner/readiness validator是否可复用未确认 | assigned to later CI tooling preparation；执行技术前置 | root/CLI CI tooling owner；限定检查utils未见一键实现，先核可用harness/交付命令，再执行；新增脚本需中文docstring/严格类型/真实非空include pyright |
| Docling本身内容抽取质量 | requiring upstream issue；scope外 | 先排除Dayu传入/写入/读取错误，确认上游则Docling issue，保留input/version/output；不本地特例改内容 |
| CN历史披露日回填/迁移、扩大OS支持、其它独立候选残余 | requiring new issue or explicit user decision；scope外 | root对应独立WU；当前只按新中国本地日裁决验证新记录，不迁移、不扩产品支持 |
| 本轮一次额外源码先读后hash | preparation evidence audit limitation | 本Agent：首检索fs_source_document_repository未先记SHA，已登记read-order-gap并先hash后重读、末hash；不追溯宣称首次读取字节已证明，交root裁决是否需再补独立读证 |

## 9. 本轮实际读取、命令与失败/恢复索引

自有证据根：`workspace/tmp/pr197-final-ci-preparation-sol-20261001-01/`。所有新文件均在此根或本报告，freeze/originals只读。证据完整路径/hash见该根 `artifact-manifest.json`，文档自身SHA见manifest与最终回复；manifest自身hash在最终回复，避免自引用hash循环。

| 实际工作 | 保存证据 | 结果与边界 |
|---|---|---|
| AGENTS、当前canary读取 | `agents.stdout.bin/stderr.bin/exit.txt`，`canary.stdout.bin/stderr.bin/exit.txt`；`commands-initial.json` | exit0，canary原内容逐字为上述CANARY；末尾换行不作为内容改写 |
| branch/HEAD/main/status、目标不存在 | `branch/head/base/status/output-exists.stdout.txt/stderr.txt/exit.txt` | git均exit0；`test -e` exit1表示目标当时不存在，是预期存在性检查而非执行失败。新增前已确认不存在 |
| freeze首末逐件核验 | `freeze-start-verification.json`、`freeze-end-verification.json` | 41当前+41独立originals，清单SHA与期望比对；任何不一致停止并报具体path |
| 正式31裁决、CLI CI合同、索引与scope/readiness来源 | `adjudications.stdout.bin`、`cli-ci-contract.stdout.bin`及双流/exit，`commands-reads.json`；冻结身份清单 | 行为/repair/后续选择实际读；索引只导航不证明覆盖。工具窗口曾截断大输出，随后按范围分别重读O32–36关键段与readiness段，完整原输出另保存在文件 |
| 额外owner定位及必要段 | `owner-search.*`、`owner-details.*`、`public-repository-read.*`、`material-owner-read.*`、`wait-projection-read.*`、`workspace-owner-read.*`、`service-direct-read.*`、`read-consumer.*`、`date-owner-read.*` | 命令argv/cwd/exit在 `commands-initial/reads/owner-reads.json`。源码身份见extra首末清单；未做产品执行 |
| parser实际构造/public help | `parser-public-help.stdout.bin/stderr.bin/exit.txt`、`commands-parser.json` | exit0、stderr空；14 leaf；本轮準备探针，不是最终freeze、不是真CLI CI |
| registry静态计数/proof范围 | `registry-static-observation.json` | 6oracle/1328scenario；command字段真实读取，material两者0；proof旧target256786…scope不含material。未运行正式readiness验证 |
| 本轮源码读取顺序缺口及恢复 | `read-order-gap.json`、`extra-read-start-identities-3.json`、重读双流/exit、末SHA | 首次fs_source_document_repository检索先于该文件专用首hash；承认原首次字节证明缺失，后续重读已绑定身份。不涉及任何冻结文件改变 |
| 收尾隔离/完整性 | `extra-read-end-identities.json`、`local-state-end.*`、`preparation-validation.json`、`artifact-manifest.json` | 只检查新增交付、首末身份与本地状态；不stage/commit/push/PR/merge、不开branch/worktree、不动main |

部分早期只读命令由工具原始回执提供，关键读取已重新以subprocess独立capture_output落盘；不得把后续重读文件伪装为早期那次原始双流。证据目录命令ledger明确记录实际保存的调用。完整本轮工具调用还保留在外部runner会话，不伪造本地历史trace。

末次本地读回 HEAD=`8e783c1acc402f363f71b32779a40986a5e0ccb3`，branch仍为唯一开发分支，main不变。已保存 `head-checkpoint-diff.stdout.bin/stderr.bin/exit.txt` 和 `commands-checkpoint.json`；从起始HEAD到该checkpoint的实际diff只有6个非冻结docs文件，不涉及产品源码。41冻结工作树文件及独立originals末核全部一致，26个额外源码首末身份一致（仓储首读顺序限制仍按上文保留）。本Agent未写这些root checkpoint文件、未读取其内容或据此升级F6候选门禁；任务输入门禁是本计划范围依据，交root按最新真实状态裁决。

本轮动机成立：material正式registry条目为0、旧Raw已删除且必需修复未全完成，必须先梳理来源/输入/完整矩阵构建方法；当前立即真实CI不能形成最终结论。交付仅为可审查候选计划及静态取证，**待root裁决**。本Agent到此停止，不进入执行gate。
