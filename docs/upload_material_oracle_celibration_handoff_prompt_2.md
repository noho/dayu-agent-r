# upload_material 第一轮 oracle calibration 接手指令（第二轮交接，起点 UM-O11）

本文件是给接手 Agent 的可执行任务说明。全程中文。文件名中的 `celibration` 沿用用户指定拼写。

用户发出“执行 upload_material_oracle_celibration_handoff_prompt_2.md 接手任务，继续下一项”时：阅读本文件及相关证据，直接从 **UM-O11** 开始，按“运行了什么、观察到什么、你的建议是什么”逐项详细呈报，供用户裁决。每次只呈报一项并等待用户回复；不要把此指令解释为修复实现授权。本文件是上一份 `docs/upload_material_oracle_celibration_handoff_prompt.md`（起点 UM-O08）的第二轮版，其历史内容已由本文件和既有 adjudication artifact 取代。

## 1. 目标与成功标准

目标命令：`dayu-cli upload_material`。任务是第一轮 oracle calibration：通过真实 CLI 运行事实，让用户决定应承诺的行为，再登记 accepted oracle、accepted scenarios、修复项和待补跑项。

接手首轮成功标准：

1. 不要求用户重述背景或再次批准只读接手。
2. 知道 UM-O01～UM-O10 已裁决且已落盘 artifact，不重新询问这些决定，也不重开这些项。
3. 重读 UM-O11 原始证据并详细呈报。注意：上一会话（2026-09-23）已详细呈报过 UM-O11，但用户未裁决、未落盘，该呈报不在仓库中；新会话必须以原始证据为准重新呈报，本文件第 7 节的要点仅供核对方向，不得当作证据引用。
4. 呈报后停在等待用户裁决；不自动开始 UM-O12 或产品修复。

整体第一轮成功标准：36 项均完成用户裁决，事实与建议分离；被质疑或证据不足的项完成必要补证；只把 accepted 行为登记为 oracle/scenarios；修复项与待补跑项可追溯到原始证据。readiness 须单独满足仓库既有完整性检查，不因讨论结束自动成立。

## 2. 仓库、背景与当前阶段

- 仓库：`/Users/leo/workspace/dayu-agent-r`。
- Git remote 名称为 `github`，不是 `origin`。
- init / prompt / interactive / download / upload_filing 已闭环，不改写其冻结证据或 accepted oracle。
- PR #196：`https://github.com/noho/dayu-agent-r/pull/196`；已确认 merged，squash merge commit 为 `fac32ecbff9bfe792b63ee9667c8697826b631f4`（即本 calibration 的 validation commit）。
- 分支 `codex/upload-material-oracle` 已存在；2026-09-24 核实 HEAD 为 `ade529a8`（UM-O10 裁决登记 commit），工作树干净。接手先用 `git status --short`、`git branch --show-current`、`git log` 只读核实实时状态。
- 分支历史中还夹有其他任务的提交（如 `3337c3f3` upload_filings_from 错误投影修复、docling 升级系列等），与本 calibration 无关；保留不动、不纳入本轮变更、不得混入裁决证据。
- 当前阶段：第一轮真实运行已冻结（validation commit `fac32ecb`）；UM-O01～UM-O10 已逐项裁决并落盘；UM-O11 曾呈报但未裁决；未进入第二轮 conformance；upload_material 尚未进入 readiness scope；正式 `docs/cli_ci_oracles.json` / `docs/cli_ci_scenarios.json` 的统一登记与 scenario 映射仍待后续完成。

本 calibration 相关提交：

| 提交 | 内容 |
| --- | --- |
| `ade529a8` | UM-O10 裁决登记 |
| `32925b36` | UM-O01～O06/O08/O09 裁决登记 + handoff 引用更新 |
| `297c0682` | 第一轮 handoff 文件 |
| `09542c44` | UM-O07 裁决登记 |
| `ed430656` / `d30a07c8` / `8f8a494b` | CN/SEC/HK download 修复，非本 calibration 运行基线 |
| `fac32ecb` | PR #196 squash，validation commit |

原始 CLI 证据来自旧 validation commit，不能宣称已验证当前 HEAD 或后续 Docling 版本。

## 3. 接手必读与权威顺序

先读：

1. 根目录 `AGENTS.md`，遵守目录、语义 owner、中文及验证约束。
2. `docs/cli_ci.md`、`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`。大文件按结构分段读取，了解现有 registry/readiness 与 download/upload_filing lineage，不复制其业务语义。
3. 五个已落盘裁决文档（按编号顺序）：
   - `docs/reviews/upload-material-um-o01-o06-oracle-adjudication.md`
   - `docs/reviews/upload-material-um-o07-oracle-adjudication.md`
   - `docs/reviews/upload-material-um-o08-oracle-adjudication.md`
   - `docs/reviews/upload-material-um-o09-oracle-adjudication.md`
   - `docs/reviews/upload-material-um-o10-oracle-adjudication.md`
4. 外置冻结 `observed-behavior.md`、`observed-behavior.json`，再读当前项目的原始证据。

权威顺序：用户最终裁决 > 正式 adjudication > 冻结报告中的原建议。冻结报告仍将各项写为 pending（当时快照）；不能据此把已裁决项恢复为未裁决。UM-O11～UM-O36 尚未逐项讨论，不得将“尚未提出异议”推定为已经全部接受。

## 4. 冻结证据与数据链

证据根目录：

```text
/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId
```

validation commit：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。

原运行使用 root 下 `.venv/bin/dayu-cli`，cwd 为 root 下 `repo`，Python 3.11；所有副作用位于 root 下 CI-owned `workspaces`。当前执行文件是否仍可用须真实检查；阅读历史记录不要求重装或重跑。

来源 → 原始逐笔 → 审核底稿 → 结果：

- 来源：`run-manifest.json`、`inputs/input-manifest.json`、固定输入与来源 SHA-256。
- Raw：每个 `evidence/<group>/<scenario>/` 中的 command/result、stdout/stderr `.bin` 与 `.txt`、screen、文件系统前后快照与 diff、durable、SQLite、process tree、key-json-artifacts。
- 审核与覆盖底稿：`matrix-inventory.json`、`matrix-supplement.json`、`matrix-supplement-2.json`、各 `*-execution-index.json`、`evidence-audit.json`、`secret-scan.json`、`artifact-sha256.json`、`evidence-manifest.json`、`report-digests.json`。
- 汇总：`observed-behavior.md` 和 `.json`；最终用户裁决在独立 adjudication 中登记。

原矩阵 135 + 补跑 22 + 标签修正补跑 3，共 160 次真实 CLI。exit：0=66、1=60、2=31、130=2、-9=1；timeout=0；残留进程计数=0；17 类必需证据无缺失；secret scan 0 findings。这些是观察事实，不是所有实现均正确的结论。

screen 是非 TTY stdout/stderr 合并解码视图，不是 GUI 截图或终端像素截图。未发现 DB/Trace 等须以 queried-but-absent 记录支持，不能把“没看到文件”当作完整查询。

已核对摘要：

| 文件 | SHA-256 |
| --- | --- |
| `observed-behavior.md` | `4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64` |
| `observed-behavior.json` | `23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0` |
| `evidence-manifest.json` | `fccbb5464eb8e95450cfc7efa2fad1ad6fab60e976d356a967340c2a19b66abd` |

保留冻结 evidence 原字节与原报告；修订建议写新 adjudication。采集方法有问题则在新的带日期/随机后缀隔离 evidence root 补跑，显式登记 supersede lineage，不能静默修正旧 Raw。临时脚本仅放 `workspace/tmp/`，长期分析辅助代码仅放 `utils/`。

## 5. 工作范式与授权边界

严格链路：真实 CLI → 屏幕/stdout/stderr/exit/文件系统/workspace/日志/DB/Trace/进程/持久化观察 → observed behavior → 用户逐项裁决 → 仅 accepted 行为写 oracle/scenarios。

- 代码、help、README、现有测试只用于识别 public surface、owner 和状态空间，不能替代真实 CLI evidence，也不能证明当前行为正确。
- 只读调查可进行。当前任务不授权产品修复、修复 Agent、正式开发流程或第二轮 conformance。
- 用户说“同意建议”只批准本项裁决方向；不等于授权实施修复。
- 用户说“同意建议，下一个”时，承接上一项决定并只呈报下一项。
- **登记纪律（本会话用户明确要求）**：修复项必须写入 `docs/reviews/upload-material-um-oNN-oracle-adjudication.md` artifact 才算登记；用户裁决后先落盘 artifact，再停下等用户指令（commit / 继续），不自动推进下一项。
- **commit 纪律**：不自行 commit/push/建 PR。commit 仅在用户明确指示后执行；commit message 末尾附 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。
- 落盘格式参照既有五份文档结构：证据与追溯（含冻结 SHA-256 核对）、Accepted 行为、已裁决修复项（标识、状态、动机、语义 owner、修复要求）、待补跑与 scenario 处置、裁决替代关系。
- 尚未讨论的观察不得写为 accepted。正式 registry 尚未完成统一登记，不能宣称第一轮已闭环。
- 当前不需重跑完整矩阵。若证据存在缺口、原始场景无法支撑结论或用户要求验证新版本，再确定最小补跑范围。
- 任何有副作用的 CLI 只能使用明确隔离的 CI-owned workspace，不使用用户投资 workspace。真实材料可从 `/Users/leo/Documents/_2我的投资/1财报` 只读取固定输入并保留来源、版本及 hash。
- 不用单元测试、直接 Python 调用、mock/fake provider 或 converter 冒充 CLI evidence。
- 补跑仍须记录 exact argv/cwd/非敏感环境/stdin、双流/屏幕/exit/耗时、文件系统前后 diff、workspace/log、DB/EventLog/Trace/memory/job 查询、信号/超时/子孙与残留进程、secret scan、manifest 与 SHA-256。

## 6. 已裁决 UM-O01～UM-O10（不重问）

| 编号 | 裁决要点 | artifact |
| --- | --- | --- |
| UM-O01～O06 | help/public surface 发现基线；usage/parser 基线（exit 2、重复 scalar 最后值）；正常 workspace 路径解析；文件数量与重复输入前置校验登记；form/name 必填校验过晚登记；material name 长度契约登记。修复标识：`UM-O03-F01`、`UM-O04-F01`、`UM-O05-F01`、`UM-O06-F01`。 | `upload-material-um-o01-o06-oracle-adjudication.md` |
| UM-O07 | 稳定身份与一致性规则接受；移除公开 internal_document_id 输入（`UM-O07-F01`）；document_id 不匹配错误投影与校验边界（`UM-O07-F02`）；UM-A24/A25 不转 scenario。 | `upload-material-um-o07-oracle-adjudication.md` |
| UM-O08 | 接受公开 document_id 显式空值被 CLI 边界拒绝（exit 2、零副作用）；空内部 ID 并入 `UM-O07-F01`，不建独立修复；UM-037/S02 不转 scenario；补跑并入 UM-O07 清单。 | `upload-material-um-o08-oracle-adjudication.md` |
| UM-O09 | 无新增 accepted 行为；修复 `UM-O09-F01`：合法财年域 **1800–2100**（用户指定），identity/metadata owner 生成身份前校验、零持久化副作用；S03～S05 不转 scenario。 | `upload-material-um-o09-oracle-adjudication.md` |
| UM-O10 | 接受 trim/uppercase/空转 null 规范化；修复 `UM-O10-F01`：值域 **FY/H1/Q1/Q2/Q3/Q4**（用户指定，复用 filing 域 canonical 语义），长度被枚举吸收、不设独立上限；与 UM-O17 关联；S07/S08 不转 scenario。 | `upload-material-um-o10-oracle-adjudication.md` |

所有修复均为“方向已接受、未实施”。用户裁决先例：“值域类”修复由用户给定具体域（O09 财年 1800–2100；O10 财期枚举复用 filing 域）；同类建议应先判断业务动机与唯一语义 owner，再拆分“接受 / 修复 / 待补跑”。

## 7. 起点 UM-O11：必须从这里继续

主题：无效 filing/report 日期持久化。

必须读取的原始目录（相对于 evidence root）：

```text
evidence/actions/UM-A18-invalid-date-publication/
evidence/supplement/UM-S09-empty-filing-date-isolated/
evidence/supplement/UM-S10-invalid-filing-date-isolated/
evidence/supplement/UM-S11-invalid-report-date-isolated/
```

读取 command.json、result.json、screen.txt、filesystem-diff.json、key-json-artifacts.json，并按需核对 durable/sqlite/process 记录。不要只转述本文件。

上一会话（2026-09-23）已呈报要点，仅供新会话核对方向，**不得当证据引用**，必须重读原始文件后自行核实：

- A18：`--filing-date 2025-02-30` 与 `--report-date nonsense` 同时传入；S09：`--filing-date ""`；S10：`--filing-date 2025-02-30`（单变量隔离）；S11：`--report-date not-a-date`（单变量隔离）。S09～S11 分别 supersedes UM-049/050/051。
- 观察：四场景均 exit 0、完整 publication；非法日期字符串原样写入 source meta 与 material_manifest（meta 与 manifest 均有投影）；空串转 null。
- owner 调查：filing 域已有严格真源 `parse_iso_calendar_date`（`dayu/fins/domain/filing_semantics.py:375`，严格 YYYY-MM-DD + 日历存在性校验）；上传路径（`dayu/fins/tools/upload_tools.py` 与 `dayu/fins/pipelines/docling_upload_service.py`）仅作 nullable text 透传、无校验。
- 上一会话建议（用户未表态）：1) 接受空转 null；2) 登记修复 `UM-O11-F01`：日期语义 owner 在 publication 前做 format+calendar 校验（复用 `parse_iso_calendar_date`），非法值 typed 拒绝、零持久化副作用，禁止写入 meta 与 manifest；3) 不把非法值原样持久化写 accepted scenario；修复获授权后补跑拒绝与合法值对照。

呈报须按“运行了什么、观察到什么、你的建议是什么”详细展开，并附绝对路径可点击证据链接。呈报后停在等待用户裁决；不要在首轮顺带详细展开 UM-O12。

## 8. 后续尚未裁决清单（UM-O12～UM-O36）

下面均为原始建议或待讨论方向，不是已批准结论。每项详细运行及直接证据映射见冻结 observed report。

| 编号 | 主题 | 待讨论方向 |
| --- | --- | --- |
| UM-O12 | 公司名称与 ticker alias | 接受 alias 冲突处理，修复 fresh 缺名称的错误分类。 |
| UM-O13 | auto/update/delete/恢复 | 确认动作链、版本和幂等语义。 |
| UM-O14 | create 命中已有文档 | 冲突还是幂等 skip；overwrite 的语义。 |
| UM-O15 | update/delete 目标不存在 | typed target-missing，避免 storage_io。 |
| UM-O16 | files/action 组合 | 前置拒绝上传无文件与 delete 带文件。 |
| UM-O17 | form/period 规范化同源 | ID 与 meta/manifest 统一 canonical 值。 |
| UM-O18 | amended 参数 | 明确并实现语义，或移除无效公开参数。 |
| UM-O19 | 单文件 converter 成功域 | 接受已测文件类型、大小写后缀和 symlink 范围。 |
| UM-O20 | XBRL/XML/JSON 后缀与实际转换能力 | 核定真实支持链路与 public contract。 |
| UM-O21 | 损坏内容与混合 batch | typed content failure、document publication 原子性。 |
| UM-O22 | 0-byte 文本 | 修复 runtime 误分类。 |
| UM-O23 | same-stem 派生名碰撞 | collision-safe identity 或前置拒绝；与 O04 合并梳理。 |
| UM-O24 | 真正不同 stem 多文件 | 接受转换、计数和稳定 ID。 |
| UM-O25 | primary 依赖 argv 顺序 | 明确公共选择契约。 |
| UM-O26 | 美/中/港固定真实材料 | 接受所测上传与元数据行为。 |
| UM-O27 | process_material 跨命令消费 | 接受真实消费链路。 |
| UM-O28 | DB/EventLog/Trace/Memory/job | direct boundary 与 queried-but-absent 证据。 |
| UM-O29 | quiet/debug/log/stdin | 诊断投影、日志追加、冲突选项和 stdin。 |
| UM-O30 | SIGINT 与重试 | 已测阶段的取消、原子性和恢复。 |
| UM-O31 | 进程组 SIGKILL 与重试 | 已测 kill 场景的恢复；不能泛化为任意单进程 kill。 |
| UM-O32 | 不同 identity 并发 | 已测不同 document/ticker 的发布行为。 |
| UM-O33 | 同一 auto identity 并发 | success+skip 或 typed conflict；拒绝通用 storage_io。 |
| UM-O34 | 公司与文档原子性边界 | 文档失败后保留公司事实是否接受，还是要求整命令原子。 |
| UM-O35 | 进程、timeout、traceback 总体 | 接受观察完整性；未超时不能证明超时处理正确。 |
| UM-O36 | 采集纠错与 supersede lineage | 确认补跑取代关系与覆盖完整性。 |

注意：原 F20/F23/F24 被误标为不同 stem，实际有碰撞；S23～S25 才是真正不同 stem 的多文件证据。原混入前置条件的场景用 S01～S17 隔离补跑；不能拿原场景失败倒推目标变量有校验。

## 9. 每项详细说明与收尾纪律

每项都要回答：

- 运行了什么：场景编号、exact argv 的关键部分、cwd/workspace、真实输入、前置状态与对照差异。
- 观察到什么：exit、屏幕、双流、文件与持久化、日志、DB/Trace 查询、信号/残留；区分直接证据与代码解释，未覆盖的边界明确标出。
- 你的建议是什么：先判断业务动机与唯一语义 owner，再拆分建议接受、修复和待补跑；说明与既有裁决的关联及替代关系。
- 附绝对路径的可点击证据链接；不要把摘要计数或报告描述冒充完整原始证据。

用户逐项确认后记住最终决定，按第 5 节登记纪律先落盘 artifact 再等指令。统一登记前回读已有 adjudication，避免重复修复标识、相互矛盾的 oracle 或静默替换。修复接受不等于实现已正确，也不等于修复已获执行授权。

**接手后现在要做的事：读取 UM-O11 的原始证据，呈报 UM-O11，等待用户裁决。**
