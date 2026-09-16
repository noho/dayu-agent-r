# upload_material 第一轮 oracle calibration 接手指令

本文件是给接手 Agent 的可执行任务说明。全程中文。文件名中的 `celibration` 沿用用户指定拼写。

用户发出“执行 upload_material_oracle_celibration_handoff_prompt.md 接手任务，继续下一项”时：阅读本文件及相关证据，直接从 **UM-O08** 开始，按“运行了什么、观察到什么、你的建议是什么”逐项详细呈报，供用户裁决。每次只呈报一项并等待用户回复；不要把此指令解释为修复实现授权。

## 1. 目标与成功标准

目标命令：`dayu-cli upload_material`。任务是第一轮 oracle calibration：通过真实 CLI 运行事实，让用户决定应承诺的行为，再登记 accepted oracle、accepted scenarios、修复项和待补跑项。

接手首轮成功标准：

1. 不要求用户重述背景或再次批准只读接手。
2. 知道 UM-O01～UM-O07 已裁决，不重新询问这些决定。
3. 读取 UM-O08 原始证据与 UM-O07 最终裁决，详细说明 UM-O08 的运行、观察和修订建议。
4. 明确原“两个 ID 参数统一空值规则”建议已因移除 internal_document_id 参数而失去前提。
5. 呈报后停在等待用户裁决；不自动开始 UM-O09 或产品修复。

整体第一轮成功标准：36 项均完成用户裁决，事实与建议分离；被质疑或证据不足的项完成必要补证；只把 accepted 行为登记为 oracle/scenarios；修复项与待补跑项可追溯到原始证据。readiness 须单独满足仓库既有完整性检查，不因讨论结束自动成立。

## 2. 仓库、背景与当前阶段

- 仓库：`/Users/leo/workspace/dayu-agent-r`。
- Git remote 名称为 `github`，不是 `origin`。
- init / prompt / interactive / download / upload_filing 已闭环，不改写其冻结证据或 accepted oracle。
- upload_filing 原提交：`527a00923391d7e1f6882f91bfdcf38b7686ca5b`。
- PR #196：`https://github.com/noho/dayu-agent-r/pull/196`；前任已真实确认 merged，squash merge commit 为 `fac32ecbff9bfe792b63ee9667c8697826b631f4`。
- 原始 Git preflight、main fast-forward 更新、创建 `codex/upload-material-oracle` 分支已完成。接手不重做切 main/pull/重建分支。
- 当前阶段：第一轮真实运行已冻结，正在逐项用户裁决。upload_material 尚未进入 accepted readiness scope；未进入第二轮 conformance。
- 用户曾要求暂停；现在已明确恢复讨论。暂停仅是执行指示，不应写入 artifacts。

已知本地提交：

| 提交 | 内容 |
| --- | --- |
| `09542c44` | UM-O07 最终裁决登记 |
| `8f8a494b` | 港股财期纠正及 SEC 业绩附件补源，两项独立 download 修复 |
| `d30a07c8` | SEC F-1/F-1/A 支持补齐 |
| `ed430656` | 交接时另已存在的 CN 季报选择修复，非本 calibration 运行基线 |

2026-09-16 交接检查分支仍为 `codex/upload-material-oracle`，HEAD 为 `ed430656`。当时有三个其他任务的 untracked 文件：

- `docs/plans/docling-2-127-upgrade.md`
- `docs/reviews/plan-review-20260916-105307.md`
- `docs/reviews/plan-review-20260916-105857.md`

接手先用 `git status --short`、`git branch --show-current`、`git log` 只读核实实时状态。保留这些外部任务文件，不纳入本轮变更。只读证据说明可以继续；如果要执行新的 Git preflight/切分支/补跑或修改文件，先按任务原约束处理工作树状态与隔离，未知改动不得覆盖。原始 CLI 证据来自旧 validation commit，不能宣称已验证当前 HEAD 或后续 Docling 版本。

## 3. 接手必读与权威顺序

先读：

1. 根目录 `AGENTS.md`，遵守目录、语义 owner、中文及验证约束。
2. `docs/cli_ci.md`、`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`。大文件按结构分段读取，了解现有 registry/readiness 与 download/upload_filing lineage，不复制其业务语义。
3. 本文件的已裁决记录及 `docs/reviews/upload-material-um-o07-oracle-adjudication.md`。
4. 外置冻结 `observed-behavior.md`、`observed-behavior.json`，再读当前项目的原始证据。

权威顺序：用户最终裁决 > 此次正式 adjudication > 冻结报告中的原建议。冻结报告仍将各项写为 pending，它是当时快照；不能据此把 UM-O01～UM-O07 恢复为未裁决。UM-O08～UM-O36 尚未逐项讨论，不得将“尚未提出异议”推定为已经全部接受。

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
- 不自行 commit/push/建 PR；此前 commit 授权已用于对应提交，不构成后续持续授权。
- 尚未讨论的观察不得写为 accepted。正式 registry 尚未完成统一登记，不能宣称第一轮已闭环。
- 当前不需重跑完整矩阵。若证据存在缺口、原始场景无法支撑结论或用户要求验证新版本，再确定最小补跑范围。
- 任何有副作用的 CLI 只能使用明确隔离的 CI-owned workspace，不使用用户投资 workspace。真实材料可从 `/Users/leo/Documents/_2我的投资/1财报` 只读取固定输入并保留来源、版本及 hash。
- 不用单元测试、直接 Python 调用、mock/fake provider 或 converter 冒充 CLI evidence。
- 补跑仍须记录 exact argv/cwd/非敏感环境/stdin、双流/屏幕/exit/耗时、文件系统前后 diff、workspace/log、DB/EventLog/Trace/memory/job 查询、信号/超时/子孙与残留进程、secret scan、manifest 与 SHA-256。

## 6. 已裁决 UM-O01～UM-O07

UM-O01～UM-O06 的确认来自本轮用户逐项“同意建议，下一个”；当时约定完整讨论后统一登记，它们尚未分别写入正式 registry。保留这些确认，不再次请求裁决；后续统一落库不得依据简略摘要扩张语义。

| 编号 | 已确认决定 |
| --- | --- |
| UM-O01 | 接受 help/public surface 作为发现基线；不能由 help 推定实现正确，也不要求保留后来裁决移除的参数。 |
| UM-O02 | 接受已观察的 usage/parser 基线，包括非法输入 exit 2 和重复 scalar 最后值生效。 |
| UM-O03 | 接受正常 workspace 路径解析；regular-file base 的通用 storage_io 错误登记修复。 |
| UM-O04 | 文件数量、重复路径/basename/stem 冲突应在相应输入 owner 边界明确校验并给 typed 原因；登记修复。 |
| UM-O05 | form/name 业务必填字段校验过晚登记修复，应在开始上传前拒绝。 |
| UM-O06 | material name 长度契约登记修复，由 metadata owner 定义并校验上限；241 字符成功不构成应接受无限长度或已确定具体上限。 |
| UM-O07 | 稳定身份与一致性规则接受；公开 internal_document_id 参数移除登记修复；document_id 不匹配的错误投影与校验边界登记修复。 |

UM-O07 最终详情以 `docs/reviews/upload-material-um-o07-oracle-adjudication.md` 为准：

- material 稳定身份来自规范化 form/name/fiscal；持久化 document_id/internal_document_id 当前相同。
- 保留公开 document_id 作为一致性断言，不能覆盖 owner 身份；失败保持零持久化副作用。
- 移除 CLI `--internal-document-id`、LLM upload tool 的 material 同名输入以及 request 透传；不保留兼容 alias/wrapper。
- 底层统一文档模型保留 owner 生成的 internal_document_id；filing 中来源 ID 的独立语义不在此次删除范围。
- UM-A24/A25 是发现冗余参数的证据，不转成长期 accepted scenarios。
- 具体摘要算法、固定摘要字面值、通用错误文案和先 upload.started 后校验不作为 contract。
- 两个已登记修复标识：`UM-O07-F01`（移除输入）与 `UM-O07-F02`（document_id 错误与校验边界）。尚未实施。

## 7. 首项 UM-O08：必须从这里继续

主题：显式空 document_id/internal_document_id 行为不一致。

必须读取的原始目录（相对于 evidence root）：

```text
evidence/static/UM-037-document-id-empty/
evidence/supplement/UM-S02-empty-internal-id-isolated/
```

读取 command.json、result.json、screen.txt、filesystem-diff.json、key-json-artifacts.json，并按需核对 durable/sqlite/process 记录。不要只转述本文件。

UM-037 exact argv 的业务部分：

```text
upload_material --base <root>/workspaces/s037 --ticker AAPL
--action delete --forms MATERIAL_OTHER --material-name Deck --document-id ""
```

S02 exact argv 的业务部分：

```text
upload_material --base <root>/workspaces/supplement/empty-internal-id
--ticker AAPL --action auto --forms MATERIAL_OTHER
--material-name "Empty Internal ID" --files <root>/inputs/probe.txt
--internal-document-id "" --company-name "Apple Inc."
```

这里 `<root>` 指冻结 evidence root，仅为本说明缩写；原始 command.json 保存完整绝对路径。两次 action、workspace 和其它输入不同，不得声称这是其它变量完全一致的配对实验。归因须结合各自命令、输出及校验 owner。

已观察：UM-037 在 CLI 边界 exit 2；S02 将空内部 ID 视为未提供，真实上传 exit 0，requested=stored=1，生成 `mat_25708fd45f8859e0c6f1d5db976571573d50db3d`。精确持久化和副作用须读取原始证据后说明。

原始建议：两个显式 ID 参数共享空值规则。**该建议已失去前提**：UM-O07 已批准移除内部 ID 输入。

应提交给用户的修订建议（仍待 UM-O08 裁决）：

1. 接受公开 document_id 显式空值被拒绝的行为。
2. 空内部 ID 的问题并入 `UM-O07-F01` 参数移除修复；不再建立保留该参数并补空值校验的独立修复。
3. 未来修复后补跑该旧参数为空/非空均被作为未知参数拒绝，以及省略参数正常上传；不把当前“空串视作未提供”写入 accepted scenario。

建议的首轮答复结构：

> UM-O08：空身份参数
>
> 1. 运行了什么：列场景与准确参数，解释有效前置及两场景差异。
> 2. 观察到什么：逐场景 exit、stdout/stderr、文件/持久化结果；附可点击原始证据链接。
> 3. 我的建议：解释 UM-O07 如何改变本项结论，明确接受、合并修复和后续补跑范围。
>
> 停下等待用户裁决。

不要在首轮顺带详细展开 UM-O09。

## 8. 后续尚未裁决清单

下面均为原始建议或待讨论方向，不是已批准结论。每项详细运行及直接证据映射见冻结 observed report。

| 编号 | 主题 | 待讨论方向 |
| --- | --- | --- |
| UM-O09 | fiscal_year -1/0/10000 | 定义合法财年域，修复生成身份前校验。 |
| UM-O10 | fiscal_period 空值/大小写/任意值/长度 | 接受合理规范化，裁决值域与长度。 |
| UM-O11 | 无效 filing/report 日期持久化 | 修复日期格式和日历校验。 |
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

用户逐项确认后记住最终决定。统一登记前回读已有 adjudication，避免重复修复标识、相互矛盾的 oracle 或静默替换。修复接受不等于实现已正确，也不等于修复已获执行授权。

**接手后现在要做的事：读取 UM-O08 的原始证据，呈报 UM-O08，等待用户裁决。**
