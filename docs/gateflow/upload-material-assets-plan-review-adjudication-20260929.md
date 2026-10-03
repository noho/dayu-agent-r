# UM-O04/O23 plan review 总控裁决

- Gate：`plan review -> fix`；候选 plan `docs/gateflow/upload-material-assets-plan-20260929.md`，HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`，未实施。
- MiMo `docs/reviews/plan-review-20260929-033914.md`：预检 ok、显式绝对 `/private/tmp/dayu-upload-assets`、独立 output/stderr；进程 exit 0、Claude JSON `subtype=success/is_error=false`、91 turns、canary `mimo-54204e4e` 匹配，stderr 仅 `[claude-code:unrecognized_model]` 白名单提示，`agent_status=completed`。Kimi 首轮 `docs/reviews/plan-review-20260929-023619.md` 已有条件通过和 F1/F2/F4；当前新增 MiMo findings 仍需修 plan，并待 Kimi/MiMo 有效双路 re-review。Sol 原 plan JSONL 有两条 `git diff --no-index` exit1，按协议 `agent_status=failed`，落盘内容仅是候选。

## findings 与计划修订任务

| Finding | 裁决 | 计划修订和完成信号 |
| --- | --- | --- |
| MiMo F1 高：`meta.json`、`.identity.json` 控制名与原件同层碰撞；所谓既有 storage 保留名校验并不存在 | **accepted**。root cause 是 storage 布局控制名与资产名同 namespace，不能靠最后 commit 回滚。 | storage filename/layout owner 新增并公开纯资产名判定，复用现有控制名常量；planner 消费其结果，不自行复制保留名列表，不改仓储完整性/发布实现。封闭 typed reason 显式包含保留控制名；原件 `meta.json` 与 `.identity.json`（及保守 case 变体）在 converter 前拒绝，路径安全；删除错误声称 `material_manifest.json` 与 document 目录原件同层碰撞。F1 与 Kimi 的失败分类修订合一。 |
| MiMo F2 中：一次规划 handoff 对独立 pipeline 入口双解 | **accepted**。 | raw 与 validated handoff 类型分明；pipeline material 入口使用必填 validated handoff；Service/runtime/CLI/tool 与独立 SEC/CN/HK 调用方均在各自首个生命周期事件前调用同一 admission **一次**，随后原样传同一对象。不得用可空 plan、入口缺失后重建或下游重算；按真实调用签名列明迁移点与必要测试。 |
| MiMo F3 中：APFS case/Unicode 变体可在真实文件系统别名冲突 | **accepted 为本 goal 的真实碰撞判定精度修复**。用户已确认 O04 的真实名字冲突须转换前 typed 拒绝，此处无需扩大 goal。 | asset namespace 冲突比较键采用保守 `NFC + casefold`（再 NFC 以消除 casefold 新产生的组合差异），原件/派生实际保存名不改。按同一键检查 original-original、derived-derived、交叉碰撞及保留控制名；不同源目录的 `Deck.txt`/`deck.txt` 与 NFC/NFD 等价名测试在 converter 前拒绝。保守多拒和其它平台特殊 alias 作为已分类残余，storage 最终完整性仍保留。若文件系统证据证明该键不能满足已确认真实碰撞目标，停止实施再裁决，不做转换后 fallback。 |
| MiMo F4 低：filing identity 迁移与 S1/S2 白名单矛盾 | **accepted**。 | 由 Sol 在计划中决定最小可验收 slice；首个切片若迁移唯一映射，必须同时迁移 `docling_upload_service.py` 的 filing 调用并删除旧实现，不留下双真源窗口。若这样使纯 S1 不再构成独立行为增量，可合并成一个端到端切片，不能机械分层。按最终切片精确列文件和完成信号。 |
| MiMo F5 低：original 名缺独立 255 检查 | **rejected-with-reason（对 material）**。material 派生名是完整 original 名追加 `_docling.json`；派生名 `<=255` 字节在同一 UTF-8 边界数学上已蕴含 original `<=255`，重复检查不会覆盖 reviewer 所举目标卷 `NAME_MAX<255`。 | 计划只需明确这一蕴含关系；目标卷更小的风险列为跨平台残余，若有直接目标卷限制证据则在 storage filename owner 对 actual limit 统一裁决。filing 原件身份另由其现有规则与文件系统最终验证保护，本 WU 保留 filing 行为。 |
| MiMo F6 低：100 个完整真实转换成功硬门槛超出 goal | **accepted**。 | 100 侧真实 CLI 证明进入正常处理、converter 被启动；101 侧 typed 拒绝且 converter 未启动；小 N（至少两个同 stem）真实转换/发布成功；owner 级 100/101 边界通过。100 完整转换可作增强证据，不设 closeout 硬门槛。拒绝路径仍需零 source 发布。 |
| MiMo F7 低：100 上限与通用 `_MAX_TUPLE_ITEMS` 耦合 | **accepted**。 | material 文件数唯一常量放 Fins 资产规划 owner，usage 文案/tool schema 从该真源派生；通用 tuple 上限保持独立语义，当前同值不暗示未来必须同步。file count 1..100 与 101 精确测试，不靠多处字面量。 |

Kimi 首轮关于 public error reason 与 filing 身份回归的 finding 与 MiMo F1/F4 一起由 Sol 修订；两路都要在下一轮复证。O19 新 fresh symlink argv 补证见主工作区 `docs/gateflow/upload-material-o19-e01-evidence-20260929.md`：CLI 会把 lexical link resolve 成目标，O04 path identity 测试应按当前路径 owner 核对，不将冻结 F15 误写为已测 symlink。

当前 gate 未通过，下一步 Sol 仅修计划，随后有效 Kimi/MiMo 并行 re-review。所有产品、测试、README、真实 CLI 仍未实施。修复项已登记于本 artifact 和主总控队列；O25 的 primary 选择继续为后续依赖，不在本 WU 提前实施。

## Kimi 首轮交叉裁决补充

Kimi `docs/reviews/plan-review-20260929-023619.md` F1 **accepted**：Sol 计划须明确 `FinsUploadUsageCode`、`FinsUploadFailureCode` 的两个 closed code 集合及 `fins_upload_failure_from_exception` 触点，规划 typed 错误在独立 pipeline 直调也不能退化为 `unexpected_runtime`；与 MiMo F1 的保留名 typed reason 一并设计，而非仅在 CLI 入口拦截。F2 **accepted**：切片若保持两个，首片的 owner 契约及 filing identity 迁移须列出受影响 filing 测试/pyright，明确它只是内部可验证增量；更简洁的单片亦可由 Sol 按 Gateflow 成本和行为闭合度选择，不能留下双实现。F4 **accepted**：当前 SEC/CN 直调末组件 symlink 的 basename 可能保留链接名，统一 resolve 后会采用目标名；新 O19-E01 真实 CLI 仅证明 CLI 已如此，计划要披露 facade 对齐并迁移受影响旧断言，不写兼容分支。

Kimi 将 case/Unicode 别名作为非阻塞残余，MiMo 以 goal 的“真实资产名冲突在转换前拒绝”指出可复现反例。总控采纳 MiMo F3：不把实际可撞名输入留给转换后 storage 回滚；保守碰撞比较键是当前已确认 goal 的实现精度，原保存名仍逐字保持。Kimi 认为 100 完整真实转换是硬要求，MiMo 指出 binding goal 用语是“100 可进入正常处理”；总控按 goal 的确切成功信号采纳 MiMo F6 分级证据，真实 CLI 必须覆盖 100/101 两侧，但 100 侧以成功进入正常处理且 100 次转换启动为必要，不能把资源昂贵的 100 次完整发布暗升为验收标准。若运行成本可承受，完整成功可增强证据。

## Sol 首次 plan fix 候选与总控新核对

`assets-plan-fix-sol-20260929-01` 预检 ok、显式 `/private/tmp/dayu-upload-assets`、独立 output/stderr，进程 exit0、JSONL `turn.completed`、canary `gpt-6-sol-8b953d37` 匹配；但一条 websocket reconnect error event、一次 `git diff --no-index --check` exit1，stderr 有非白名单 websocket 与 apply_patch verification error，故严格 `agent_status=failed`。总控核对候选 plan SHA-256 `2042e16420ac58ab9f85bbbaa444f23d8b111398202cafb81140aec87cf0144b`，F1/F2/F3/F4/F7 和 Kimi 分类器触点大体落实，并合为一个端到端 slice；只能作候选，未进入实现。

新发现一项需修 plan 的验收精度：§真实 CLI 把 100 侧写成“100 次 converter 均启动”。真实 CLI 的顺序转换若第 1 次因内容/资源失败，仍已证明数量 admission 接受 100；强迫 100 次启动实质重建上一轮已撤销的昂贵硬门槛。binding goal 要求实际 CLI 覆盖上限两侧，精确完成信号应是：owner/廉价受控 converter 测试证明 100 个都能走规划/转换调度，真实 CLI 100 输入已通过数量 admission 且至少启动首个 converter；若后续内容/资源失败如实分类，不冒充“成功发布 100”。101 真实 CLI 在转换前 typed 拒绝；小 N 真实 CLI 完成发布。Sol 下一次仅修此文案与测试/停止条件的一致性。另请复核 §入口中 `raw | validated` 双类型 façade 是否为必要业务入口，而非为保旧 scalar API 的兼容分支；若只是旧路径保留，应改成明确单一 typed raw admission 入口和必填 validated 内层，不留下可空 plan 或双套规则。随后再有效双路 re-review。

## Sol 第二次 plan fix 候选

`assets-plan-fix2-sol-20260929-01`：预检 ok、显式 `/private/tmp/dayu-upload-assets`、独立 output/stderr，进程 exit0、JSONL `turn.completed`、canary `gpt-6-sol-0ff13360` 匹配、stderr 空；一条复合 `git status && shasum` command execution exit1，按协议 `agent_status=failed`。总控核对计划 SHA-256 `fb67ad6c75703e39305fc2d8675af64f0827368f23a7cd95dc0dbac245ad9a6b`：真实 CLI 100 输入只需通过数量 admission 且启动至少首个 converter，廉价受控 converter 测全部 100 个调度，101 前置拒绝，小 N 真实完整发布；raw façade 与必填 validated 执行方法分开，旧 scalar API 同切片迁移，不用 raw|validated 联合或可空 plan。修订内容仅作候选，Kimi/MiMo 有效双路 plan re-review 前不实施。

## MiMo 第二轮复审与总控裁决

MiMo `docs/reviews/plan-review-20260929-051109.md` 预检 ok、显式 checkout、独立 output/stderr、process exit0、Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、65 turns、canary `mimo-2261830c` 匹配，stderr 仅白名单模型名提示，`agent_status=completed`。结论 `pass-with-risks`；前轮高/中项已闭合，但新增四项低 finding。Kimi 对同版尚无有效第二路，计划 gate 未通过。

| Finding | 总控裁决 | plan 修订与验收 |
| --- | --- | --- |
| F1 测试触点漏列 Service/runtime/tool 的必改调用 | **accepted**。旧 scalar 签名迁移确会影响 `tests/service/test_fins_direct.py`、`tests/fins/test_fins_service_runtime.py`、`tests/fins/test_fins_ingestion_tools.py`；`tests/fins/test_filing_upload_publication.py` 是否改取决于私有 pair 形状。 | 同一切片测试白名单显列前三文件与条件性第四文件，并核对 repo 内全部旧 scalar/request 导入调用；受影响套件与逐生产文件 coverage 命令同步。 |
| F2 storage 控制名集合三处字面可能漂移 | **accepted**。成员事实属于 storage 布局 owner，不能只在 planner 新建第三份集合并靠对拍测试维持。 | 新 storage 纯契约导出唯一保留名集合；`_fs_source_integrity.py` 两处 walker 同片改为消费同一集合，行为不变，扩生产/测试白名单并用 owner 测试证明 `meta.json`/`.identity.json` 与非控制名。若有 import cycle，先重排底层常量归属而非复制。 |
| F3 `MISSING_FILES` 与逐文件不存在/非普通文件混淆 | **accepted 限定含义，后半延期独立 WU**。binding goal 是数量与资产身份冲突，`MISSING_FILES` 仅 upsert 空列表；非 CLI 文件不存在/类型错误现有 `unexpected_runtime` 与 CLI 路径泄漏是不同 root cause，不应凭本项扩全部输入检验。 | plan 写明只校验已确认的资产身份/数量，不声称消除所有 path 错误；另登记 `fins-material-file-existence-admission`，复用 Fins 公共文件标签与 `FILE_NOT_FOUND`/`FILE_NOT_REGULAR` 真源，后续独立 goal/plan。当前 WU 的已有文件合法样本仍通过；不把不存在映成 `MISSING_FILES`。 |
| F4 filing/material 重复规范路径检查可能双实现 | **accepted**。两 source kind 对规范路径 exact 身份为同一可复用事实；filing 的其它独立限额/角色保持。 | 将纯 path normalization/duplicate identity helper 置于唯一资产规划 owner，material planner 与 filing 静态 admission 共用；迁移 filing 测试确保规范化与 error code 没变，不新增兼容 re-export。若循环依赖阻碍，先给实际 import 图/owner 证据回 plan，不在下游复制。 |

MiMo OQ1 validated 类型所在模块及 import cycle 由 Sol 在 plan 以实际 import 图收口；OQ2 filing 分支此前已有的 filename prefix 验证只有同源迁移必要时才改，合法身份不漂；OQ3 `MISSING_FILES` 精确为 upsert 空 files。与本轮新 F3 相关的独立 work unit 已同步主队列。Sol 下一轮仅修 plan，再由 Kimi/MiMo 对同版有效双路复审；产品未实施。

Sol `assets-plan-fix3-sol-20260929-01`：预检 ok、显式 `/private/tmp/dayu-upload-assets`、独立 output/stderr、process exit0、JSONL `turn.completed` 且无失败 command/error、canary `gpt-6-sol-c7e4e8ee` 匹配；stderr 有两条非白名单 `apply_patch verification failed`，按严格协议 **agent_status=failed**，其报告只作候选。总控独立核对 plan SHA `e7034db68ca4f4b2b2e901a898861f6c27d6f170562c4f9d6b1e7fdac856cfe0`：已列 Service/runtime/tool 测试与旧 scalar 对账，storage 保留名单集合供两 walker 共用，`MISSING_FILES` 缩到空 upsert 并登记独立 WU，filing/material 路径身份纯 helper 与无环 import 图、逐文件 coverage 和停止条件均落盘。Kimi/MiMo 对此同版有效 plan re-review 前不得实施。
## MiMo 第三次同版复审与裁决（2026-09-29）

`docs/reviews/plan-review-20260929-055331-assets-mimo.md` 对候选 SHA `e7034db68ca4f4b2b2e901a898861f6c27d6f170562c4f9d6b1e7fdac856cfe0` 复审：预检 ok、绝对 cwd/独立 output+stderr，process exit0，Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、canary `mimo-308aec55` 匹配，stderr 仅白名单模型提示，`agent_status=completed`；结论 `pass-with-risks`。旧 F1–F4 已落计划，新增两低项和三个精度问题；Kimi 有效第二路仍缺，plan gate 不通过。

- **F5 低 accepted。** storage document 控制名集合必须是三处消费同一真源：除 `_fs_source_integrity.py` 两处，还要将 `_fs_maintenance_core.py:579-583` 的内联同义集合改为消费同一常量，精确加入生产白名单与对应 storage 测试；仍保持 exact membership 和无环。不能自称唯一集合而遗留第三份。
- **F6 低 accepted。** 删除 CLI 丢 selection 的投影路径时，`fins.py` 上游 raw request 构造前仍执行现有逐文件 exists/is_file 预检，保持 material 缺失文件/目录的 exit2 和既有文案；这只是现行 CLI 准入防回归，跨入口 owner 级文件不存在/非普通文件 typed 统一仍属于已登记 `fins-material-file-existence-admission` 后续 WU。补 CLI 两例回归断言，不把缺单个文件映作 `MISSING_FILES`。
- **OQ1 收敛。** 三个复用 code 的用户文案仍由唯一 Fins usage message owner 提供，planner 只产 typed fact 与参数，不自建另一套同 code 文案；100 上限当前 filing/material 一致，限额未来分离时共用 schema/message 再同源演进，登记残余，不在本片暗改 filing 文案。
- **OQ2 收敛。** planner 接收显式已判定的 `upsert/delete` 操作模式及原始路径/选择，不自行从 `auto` 或文件空值猜动作；模式由 Fins admission 唯一解析并传入，delete 无资产绕过 upsert 校验。
- **OQ3 收敛。** 控制名的大小写/Unicode 保守键变体归 `RESERVED_CONTROL_NAME`，真正业务 original/derived 相撞归 `ASSET_NAME_COLLISION`；前者测试钉住 `META.JSON`，不依赖原件遍历顺序。

Sol 下一轮只修本 plan 及白名单/命令；Kimi/MiMo 同版复审前产品不实施。O25 仍以本 WU accepted+integrated 为实施前提。

`assets-plan-fix4-sol-20260929-01` 预检 ok、绝对 cwd/独立 output/stderr/last-message，process exit0、JSONL `turn.completed`、canary `gpt-6-sol-62fc0de7`，无失败 command；但 stderr 有一条非白名单 `apply_patch verification failed`，按严格协议 **agent_status=failed**。总控独立实读候选 plan SHA `e1d9151a97c11cbf1b2f5552cb3ca2880a28fde89e9f3a7179883f16baa98c66`：第三处 maintenance walker 消费、CLI raw request 前保留 exists/is_file+exit2、usage 文案唯一 owner（为避免 import 环迁至低层合同）、显式 upsert/delete、`META.JSON` reserved reason 与对应白名单/测试均入文；旧 100/101、filing identity、O25 依赖未见回退。新低层 usage owner 的迁移面较广，应由独立 reviewer 从 import 图/现有 consumer 直接反证；不能仅凭 agent 自述计 plan pass。待有效 Kimi/MiMo 同版复审，产品未实施。

## MiMo 第四轮复审与总控裁决（2026-09-29）

MiMo `docs/reviews/plan-review-20260929-assets-rereview4-mimo.md` 对 SHA `e1d9151a...` 结构化 success、canary `mimo-96bbb6d7` 与本地基准逐字匹配、stderr 仅白名单模型提示；`agent_status=completed`，结论 `pass-with-risks`。总控按源码核对其四项低 finding 并全部接受为 plan 精度修复，旧高/中项未回退，但 plan gate 仍缺 Kimi 同版有效审查。

- **F1：usage owner 的依赖随迁。** `FinsUploadUsageFailure` 与工厂使用 `_MAX_TEXT_CHARS`，该常量仍有非 usage 调用；新 owner 应定义独立命名的 usage 文本上界，原常量留原处服务其它规则，禁止新 owner 反向 import runtime 或散落裸 `240`。仅供工厂使用的 `_FILE_USAGE_CODES` 同迁，工厂 owner 测试移入 `tests/fins/test_upload_usage_contract.py`；补真实 import 无环验证。
- **F2：validated handoff 的协议触点。** `ingestion/observation_handle.py` 的两个方法仍注解 raw `FinsUploadRequest`；若新 validated material 沿 tool observation 传递，必须同片迁移协议及 `tests/service/test_fins_wait_adapter.py` fake。白名单和 `rg` 对账加 `FinsUploadRequest|FinsRuntimeUploadRequest` 裸别名，不能靠条件性扩展掩盖必经触点。
- **F3：常量使用事实。** `_IDENTITY_DESCRIPTOR_FILENAME` 在两个 walker 的直接 import 仅供迁移的集合字面，迁后应删 dead import；`_SOURCE_META_FILENAME` 还有 meta_path 用途可留。计划原括号断言二者均仍使用与代码不符，须改精确。
- **F4：迁移描述精度。** 当前 retry hint 全在 `upload_failure.py`，并无旧模板可迁；为维持本计划同源业务 hint，可将新 planner reason 的 retry hint 在低层 usage owner 定义、旧 public failure hint 保留原 owner，逐字列清而不声称旧 hint 迁移。filing 的现行 100 上限参数真源点名 `_MAX_TUPLE_ITEMS`，不能裸传 `100`。`test_filing_upload_publication.py` 不 import usage 类型；纳入缘由是 prepared asset 形状可能变且无论是否改都跑发布回归。

下一步须由 Sol 只修 plan 并对新 SHA 进行 Kimi/MiMo 同版 planreview；产品未实施。当前自动审批拦截新的外部 Sol 派发，不能绕过；本轮仅登记可核验的修复清单。

用户随后明确授权 `$sub-agents`，自动审批放行。`assets-plan-fix5-sol-20260929-01` 预检 ok、绝对 `/private/tmp/dayu-upload-assets`、独立 JSONL/stderr/last-message；进程 exit0、`turn.completed`、canary `gpt-6-sol-1831a3e3` 匹配、stderr 空，但四条探测/导入命令非零，严格 **agent_status=failed**。总控独立实读候选 SHA-256 `88b03cd247dc5d6d6c1fa9cb3dc113046a5c796ab40a61083d0c1cd00a049e13`：F1 usage 命名上界与 `_FILE_USAGE_CODES`、F2 observation 协议/fake、F3 dead import、F4 hint/filing limit/test 缘由都已写入；100/101、CLI exit2、唯一 Docling 命名、filing identity 与 O25 依赖未回退。当前 checkout 缺 `.venv` 和待实施新模块，真实 import smoke 属实施 gate，不以失败探测证明代码缺陷，也不称已验证无环。下一步同 SHA Kimi/MiMo planreview；产品未实施。

## MiMo 第五轮同版复审（2026-09-29）

`assets-plan-rereview5-mimo-20260929-01` 对 SHA `88b03cd2...049e13` 进程 exit0、Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、canary `mimo-377ca477` 匹配，stderr 仅白名单模型提示；artifact `docs/reviews/plan-review-20260929-assets-rereview5-mimo.md`，结论 pass-with-risks、**零新增 finding**。总控实读其 owner 反证：F1 usage 上界 `_MAX_TEXT_CHARS` 与 `_FILE_USAGE_CODES` 消费点、F2 observation 协议两个触点/四个实现与 fake、F3 walker 常量真实用途、F4 retry hint 与 filing `_MAX_TUPLE_ITEMS` 均有可实施锚点；100/101、统一原件→Docling 名和 O25 依赖未回退。`.venv`/待新增模块 import smoke 留实施验证，不作为 plan 已通过的证据。Kimi 同 SHA 尚运行，当前仍不得判双路 plan pass。

## 第五轮双路计划复审最终裁决（2026-09-29）

Kimi `assets-plan-rereview5-kimi-20260929-01` 对同 SHA 进程 exit0、Claude JSON `subtype=success/is_error=false/terminal_reason=completed`、canary `kimi-00ae7455` 匹配，stderr 仅白名单提示；artifact `docs/reviews/plan-review-20260929-assets-rereview5-kimi.md`，结论 pass、无新增 finding。总控实读其 F1–F4 的源码/导入图反证，与 MiMo 同版结论一致且两路独立。残余：新模块真实 import smoke、逐生产文件 coverage/pyright/真实 CLI 归实施 gate；`FinsProductionUploadRunner` 类名笔误以同计划白名单里的真实 `ProductionFinsUploadRunner` 为准，实施 code review 必须核对；保守碰撞键、卷名长度、TOCTOU 与一次性指纹变化均已登记。无未分类阻断项。

**plan gate pass**。下一 entry：accepted plan commit；随后 Sol 单一端到端实施、Kimi/MiMo 双路 code review。O25 依赖本 WU accepted+integrated 结果，不因计划通过就启动 O25 产品实施。
