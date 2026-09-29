RUNTIME/PROVIDER/MODEL: claude/ds-flash/deepseek-flash[1m]
CANARY=ds-flash-1f017680

# Code Review

## Scope

- Mode: current changes（issue #198 **aggregate**：S1+S2 组合、交互与残余分类；label `issue198-aggregate-ds-flash-r2-20260929-01`，为前轮 `issue198-aggregate-ds-flash-20260929-01` 的**同 provider 修复性重试**）
- 绝对工作区：`/private/tmp/dayu-issue198-aggregate-dsflash-r2`；生成时间由系统时钟取得：2026-09-29 21:52:26 CST
- Branch or PR: detached HEAD = `2643de25d6258fe2d83b527ea3823ffa3eb19bff`（开始与结束 `git status --porcelain` 均只含本 review 文件，产物代码/测试/README 零改动）
- Base 与范围校正（本次独立复算，非沿用前轮结论）：`9735800cb55a40336469593fa2fddae43c9c69ad` **不是** HEAD 的祖先（`git merge-base --is-ancestor 9735800 HEAD` 为假），故旧 head 不能作 base。三提交的真实共同基线取 `git diff 8d8d494fbbce0052372fb1b42097c9f7222cfa28..HEAD` = 56 文件、6246 insertions、88 deletions。
- Included scope
  - 生产改动 8 文件：`dayu/fins/direct_events.py`、`dayu/fins/ingestion_runtime.py`、`dayu/fins/pipelines/cn_download_workflow.py`、`dayu/fins/pipelines/cn_pipeline.py`、`dayu/runtime/log.py`、`dayu/service/fins_wait_adapter.py`、`dayu/cli/output.py`、`dayu/cli/commands/fins.py`
  - 测试：`tests/runtime/test_log.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/fins/test_cn_download_workflow.py`、`tests/fins/test_cn_download_runtime.py`、`tests/cli/test_output.py`、`tests/cli/test_fins_commands.py`、`tests/service/test_fins_wait_adapter.py`
  - 文档：`README.md`、`dayu/fins/README.md`、`tests/README.md`
  - 组合面：storage typed `unsafe_publication` → 唯一 public reason 映射 → direct RESULT → CLI／wait JSON → 后台 job 持久摘要；可证明发布范围内的部分摘要守恒与 rollback 边界；未知 download 异常的安全类型/帧指纹诊断与 RESULT→日志顺序；RESULT 终态约束放宽的实际可达面；READM/证据一致性
- Excluded scope: 其它 WU（点号元数据 inspector、workspace-root、upload material、CNInfo 单日发现窗口）的实现与文档；`dayu/engine`、`dayu/host`、`dayu/config` 与本次无交集部分；本沙箱缺网络导致的既有失败
- Parallel review coverage: 无。按派发要求未使用 subagent，未派发任何子 Agent

## Findings

未发现实质性问题。

以下五条是本轮独立走读的反证面（均由我本人从代码/测试/证据文件直接读取，不采信旧 review 文字）。每条的排除过程附直接证据，便于总控复核"为什么没有 finding"。

1. **typed `unsafe_publication` 从 storage 到 direct/CLI/wait/job 的事实保真**
   - storage owner 在 `dayu/fins/storage/source_integrity.py:311-324` 与 `_fs_source_integrity.py:311,338,437` 抛 `SourceIntegrityPreflightError`；`cn_download_filing_workflow.py:173,603` 与 `sec_download_filing_workflow.py:238,275,383,505` 同型。
   - Fins 在唯一异常投影点用显式全量表 `_SOURCE_INTEGRITY_PUBLIC_REASONS`（`ingestion_runtime.py:6910-6915`）按 **enum 成员身份**映射到 `FinsDownloadFailureReason`（`direct_events.py:174-180`），不解析字符串。`_download_exception_cause`（`ingestion_runtime.py:6918-6931`）是唯一 unwrap 点，`_classify_direct_error`（`:7185`）与 `_download_public_failure_from_exception`（`:6949`）各自再 unwrap 一次，对已 unwrap 的 `cause` 为幂等 no-op。
   - `FinsPublicFailure.__post_init__` 拒绝非该 enum 的 `reason_code` 与非 STORAGE/带 transport 组合（`direct_events.py:251-255`）；`to_json_value()["reason_code"]` 输出 `.value` 或 `null`（`:273`）。
   - 消费者面：CLI 只打印公共 `.value`（`cli/output.py:485-499`）；wait 只序列化 `failure.to_json_value()` 并追加 `scope_note`（`fins_wait_adapter.py:608-623`）。全仓 `reason_code` 的构造点只有 `_download_public_failure_from_exception`，无第二份映射或下游重算。
2. **部分摘要守恒与发布状态的 owner 证明边界（真实仓储触发，非 spy 伪造）**
   - `tests/fins/test_cn_download_runtime.py:1435` 的 Phase B 用例按计划配方用 storage identity owner 的 `_identity_directory_path` + `_FILING_IDENTITY_NAMESPACE` 造未发布 exact-target 目录并写非点号 `undeclared.bin`，经真实 `begin_batch` copytree 与真实 `classify_staged_source_integrity` 触发 typed（`:1499-1506`），断言 direct 恰一个 RESULT、`discovered=2/downloaded=1/failed=1`、`PARTIAL_FAILURE`、`reason_code=unsafe_publication`，job 同 counts 同 disposition 同安全消息（`:1528-1551`）。
   - `:1677` 的 post-repair 用例经真实 classifier 断言 direct／job 双方 `terminal_disposition=succeeded`、`failed_count=0`、已发布行保留、`failure.reason_code=unsafe_publication`，并断言 `company_path.read_bytes() == old_company`、`pdf_path.read_bytes() == original_pdf`，清除 mutation 后同请求 `skipped+downloaded` 守恒恢复（`:1822-1870`）。即"文档终态"与"整体操作失败"确由两个独立事实分别表达，且都来自同一 `filings` 快照。
   - 首候选前的循环前 company pre-swap typed **未**被包住（`cn_download_workflow.py:282-289` 的 `_publish_cn_company_after_repair` 调用在 try 之外），原异常裸透传 → 请求级零候选 `FAILED`，与 `:429` 处的 post-repair catch 是两个不同调用点，未互相污染。
   - `_integrity_abort`（`:492-547`）的 `_build_summary`/`_build_result` 只从同一 `filings` 派生，且 `_build_result` 内 `list(filings or [])` 复制列表（`:965`）、`warnings`/`notes` 亦复制（`:963-964`）；行 dict 单向写入后不再被改写。
   - 单 filing 流的所有终态事件（`cn_download_filing_workflow.py:208,224,279,353,442,461`）均在 `yield` 后立即 `return`，且 `_retry_cn_filing_after_identity_change`（`:513`）递归到下一轮前不产出终态事件；因此 typed catch（`cn_download_workflow.py:344-369`）追加的 `failed` 行与任何既有行不可能重复，`discovered = 四类行数之和` 成立。注入的 `reason_code="source_integrity_preflight"` 落在 `_project_cn_document_row` 的 `reason_category`（自由文本，`download_contract.py:264,294`，非封闭 enum），不会因未注册值 raise。
   - `FinsResultSummary` 放宽的实际可达面已独立枚举：全仓 `FinsResultStatus.FAILURE` 构造点中唯一带非 None `download` 的是 `ingestion_runtime.py:4367`（#198 目标）与 `:4437`（无来源文档）；后者条件是 `failed_count > 0 and downloaded_count == 0 and rejected_count == 0`，经 `_terminal_disposition_from_counts`（`download_contract.py:546-552`）必为 `FAILED`，放宽前后行为一致。`CANCELLED` 仍被拒绝（`direct_events.py:681-685`）。
3. **未知 download 异常的安全诊断（S2）**
   - `dayu/runtime/log.py:91-180` 只依赖 stdlib 与 `dayu.contracts.json_value`/`dayu.runtime.log_levels`（`log.py:40-41`），无业务层 import，层中立成立。类型部分按 `vars(builtins)` 身份取内建祖先（`:127-132`），自定义类型只输出 `module + "\0" + qualname` 的 SHA-256 前 16 hex（`:136-143`）；帧部分要求 `f_globals` 与 `sys.modules` 同字典、`__file__` 与 `co_filename` 严格解析同一、位于传入包根内且各段为合法标识符，否则 `[external]`（`:156-180`）；整体与逐帧均对内部异常返回固定安全串（`:110-112`、`:179-180`），不读 message/args/cause/locals/源码行。
   - producer 与 CLI 外层复用同一 helper，`source_root` 分别由 `ingestion_runtime.py:4381`（`Path(__file__).parent.parent` = `dayu`）与 `cli/commands/fins.py:220`（`.parent.parent.parent` = `dayu`）解析，均正确指向包根。
   - 顺序与不误记有 owner 级断言：`tests/fins/test_fins_ingestion_runtime.py:6200-6212` 在 logger.error 包装内断言 `result_spy.call_count == 1`，即必然先 RESULT 后日志；`:6233-6239` 断言恰一条 ERROR、`exc_info is None`、URL/token/绝对路径不入日志；`:6155-6166` 对非 EXECUTION 分类断言 `unknown_records == []`。
   - CLI 提示只在 download 失败详情后出现（`cli/output.py:410` 的调用被 `result.download is not None` 门控，`:485-501` 条件为 `kind is EXECUTION`），storage 分类不追加；常量在 `cli/output.py:69` 单点持有。
4. **证据文件与 README 的一致性（本轮实跑复算）**
   - 两份 CLI 证据文档 SHA-256 逐字复算一致：fresh `cbb38609…348545`、replay `8a014d41…412ed997`。
   - fresh 证据目录 `/private/tmp/issue198-cli-wide2-9aklx640` 的 8 条流全部逐字复算一致（`23c41eda…` / 空 `e3b0c442…` / `3d31052a…` / `0804026d…` / `dc00b1c4…` / `93e88e89…` / `1e5f1a46…` / 空 `e3b0c442…`）；replay 目录 7 条声明流同样逐字一致（`cc02b78f…`×2 / 空 / `0804026d…` / `5349d095…` / `c83123c0…`）。
   - 我直接打开 `typed.stderr` 与 `typed.log` 复核内容（不只比哈希）：stderr 为 `classification="storage" source="cninfo" transport="-" reason_code="unsafe_publication" retry_hint="请检查并修复工作区来源状态后重试；重复下载不会自行修复。"`，且**不含** CLI 的 `--log-file` 提示；log 仅一条普通 INFO，无任何 `fins.download.*` 事件。与"typed storage 不产出 unknown 诊断"的合同一致。
   - README：根 README 的 `请使用 --log-file PATH 重试并查看日志` 字面量只出现 1 次（§3.1），§5.1 以引用方式指向而非重复，§5.2 上传段落已删除该提示句——F2 的"不重复提示"落实；`dayu/fins/README.md` 与 `tests/README.md` 的新增句与代码行为逐条可对应。
   - S2 11 文件候选 diff 从**提交**复算得 `2a79d0713b965be82734552d89619f56957968d62b0344a2652d8848797cfc54`，与 S2 裁决记录**逐字一致**。
5. **架构与项目指令核对**
   - 无新增反向依赖：`dayu/runtime/log.py` 不 import Fins/CLI/Host；`dayu/fins/direct_events.py` 的 import 面（`direct_events.py:20-29`）不含 `dayu.fins.storage`，符合"公共失败契约不持有仓储实现依赖"的 plan 约束。
   - 生产 diff 无新增 `hasattr`/`getattr(`；删除 `_FINS_DIRECT_UNKNOWN_FAILURE_MESSAGE` 后由 `CLI_LOG_LOCATION_HINT` 单点接管，未留兼容 re-export / wrapper。
   - `_failure_message` 的"缺 download 即拒绝"在 base `8d8d494f` 已存在（`git show 8d8d494f:dayu/service/fins_wait_adapter.py:600-602`），#198 只新增 `scope_note` 并把 docstring 改为 AGENTS.md 要求的中文 Args/Returns/Raises，未把跨操作不变量塞进 `FinsResultSummary`。

## 本轮实跑验证记录

环境：`.venv` Python 3.11.15，`dayu.__file__` 指向本 worktree。**以下每条命令自身 exit0**；我刻意不运行已知会非零或挂起的命令（见下节）。

| # | 验证 | 命令 | 退出码 | 结果 |
| --- | --- | --- | ---: | --- |
| 1 | 计划口径 8 文件受影响测试 | `python -m pytest tests/runtime/test_log.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/cli/test_output.py tests/cli/test_fins_commands.py tests/service/test_fins_wait_adapter.py tests/service/test_fins_direct.py -q` | 0 | **856 passed**, 3 warnings（edgartools 弃用） |
| 2 | 全量 pyright | `python -m pyright dayu/ tests/ utils/` | 0 | **0 errors, 0 warnings, 0 informations** |
| 3 | HEAD / 祖先关系 | `git rev-parse HEAD`；`git merge-base --is-ancestor 9735800 HEAD` | 0 | HEAD = `2643de25…`；旧 PR head 非祖先（故 base 取 `8d8d494f`） |
| 4 | 工作区洁净 | `git status --short` | 0 | 仅本 review 文件 |
| 5 | S2 候选 diff 复算 | `git diff --binary 7234d42d 2643de25 -- <11 文件> \| shasum -a 256` | 0 | `2a79d071…97cfc54`（与 S2 裁决逐字一致） |
| 6 | S1 提交 diff 复算 | `git diff --binary 8d8d494f 7234d42d -- <14 文件> \| shasum -a 256` | 0 | `39018b65…b477fe4` |
| 7 | 主工作区对照 | `git -C /Users/leo/workspace/dayu-agent-r diff --binary 8d8d494f -- <14 文件> \| shasum -a 256` | 0 | `f1e1a915…f0f6bd21`（与 S1 裁决记录逐字一致） |
| 8 | 差异成分定位 | 同上 `diff --stat 7234d42d -- <14 文件>` | 0 | 仅 `README.md`/`dayu/fins/README.md`/`tests/README.md` 3 文件 5 insertions/2 deletions，全部为另一 WU 的点号元数据句与空行归一；11 个代码/测试文件与 S1 提交**逐字节相同** |
| 9 | 证据文档摘要 | `shasum -a 256 docs/gateflow/issue-198-s2-cli-fresh-evidence-20260929.md …-replay-evidence…` | 0 | `cbb38609…` / `8a014d41…`（与记录一致） |
| 10 | fresh CLI 原始流 | `shasum -a 256` on `/private/tmp/issue198-cli-wide2-9aklx640/*` | 0 | 8 条流全部与证据表逐字一致 |
| 11 | replay CLI 原始流 | `shasum -a 256` on `/private/tmp/issue198-cli-replay-e23865b8/*` | 0 | 7 条声明流全部与证据表逐字一致 |
| 12 | typed 流内容直读 | `Read` 两个原始流文件 | 0 | storage/unsafe_publication 正确，CLI 提示与 unknown 诊断均不出现 |
| 13 | 静态核对 | `rg`（提示字面量、`reason_code` 构造点、`FinsResultStatus.FAILURE`、`hasattr/getattr`、`dayu.runtime.log` 导入面、`--log-file` 字面量） | 0 | 单点持有 / 无第二映射 / 放宽面有界 / 无新增反射 / 层中立 |

## 前轮协议失败与本轮实际验证范围

- 前轮 `issue198-aggregate-ds-flash-20260929-01` 的内容审查已完成且结论与本轮一致，但它在同一任务下运行了**返回 1 的插桩（coverage）与全矩阵命令**以及**挂起的全量 suite**，违反本任务"每条 shell 命令自身 exit0"协议，**不能计 gate**。这是流程合规问题，不是内容结论被推翻；本轮不复制其结论，所有判断重新走读。
- 本轮据此**主动放弃**三类已知会非零/挂起或与语义无关的验证，并如实标注为**本轮未验证**（不作为通过证据，也不冒充失败）：
  - coverage 插桩口径（前轮 4 个取消时序用例在插桩下调度差异失败；单文件覆盖率 94/91/85/85% 仅来自两路 re-review 记录，本轮未复跑）；
  - 全量 suite 与 `tests/cli` 全目录（本沙箱 74 项 TTY/subprocess/provider-discovery 失败在 base 与 HEAD 同集）；
  - 真实 CLI 复跑（依赖外部 provider 与网络；本轮改为对既有真实流的哈希与内容双重复核）。
- 因此本轮的独立性来自：重新走读全部 8 个生产文件与关键 owner 测试的真实调用链 + 上述 13 条 exit0 实证；而不是重跑前轮那些非零命令。
- 全程未修改生产代码、测试、README 或旧 review/gate artifact；未 commit、push、PR、merge、对外发消息或派发子 Agent。

## Open Questions

- **OQ1（低 / 当前不可达 / 已登记独立 WU）**：storage 的 `SourceIntegrityPreflightError.__init__`（`dayu/fins/storage/source_integrity.py:194-208`）不校验 `reason` 成员身份，且在**构造期**就读取 `reason.value`（`:208`）。我按"是否当前可达"分层实证：
  - 全仓构造点共 **13** 处（`source_integrity.py:311,314,322,324`；`_fs_source_integrity.py:311,338,437`；`cn_download_filing_workflow.py:173,603`；`sec_download_filing_workflow.py:238,275,383,505`），**全部传闭合枚举字面量**，无变量透传、无外部输入路径。
  - 传**普通非成员**（如 `str`）时在 `reason.value` 处先抛 `AttributeError`，异常对象根本无法构造，到不了 Fins 映射。
  - 只有传**带 `.value` 的伪对象**才能构造成功，随后在 `ingestion_runtime.py:6982` 的 `_SOURCE_INTEGRITY_PUBLIC_REASONS[exc.reason]` 抛 `KeyError`。**总控对该两段式观察的判断与我的独立复核一致。**
  - 本轮新增的直接证据（登记用，不升级为 finding）：该 `KeyError` 若发生，在 **job 路径**的后果比 direct 更重。`_save_typed_download_failure`（`ingestion_runtime.py:4997-5041`）把 `_download_public_failure_from_exception(cause, ...)` 放在自身 `try` **之外**，而 `FinsIngestionThreadExecutor.submit`（`:2340-2359`）是裸 `Thread(target=operation)`、无任何异常兜底——异常会经 `threading.excepthook` 输出原始 traceback，且 job record 停留在 `running`，与该函数 docstring"所有业务与运行时异常都会转换为 terminal job record"（`:4973-4974`）不符。base 上同类异常走的是**全程自兜底**的 `_save_failed_from_exception`（`:6073-6100`），故这是 #198 引入的**结构性**逃逸面，但在当前 13 处构造点不变式下**不可达**，故不立 finding。建议该独立 WU 一并覆盖 job 路径的终态兜底（可与已登记的 `fins-direct-projection-failsafe` 对齐取舍）。
- **OQ2（已裁决，仅登记复核）**：`fins.download.unexpected_failure` 也会记录 EXECUTION 分类中的**已知**条件（缺 adapter 的 `_UnsupportedDownloadSourceError`、`SourceIntegrityRevisionConflictError`）。总控已以 rejected-with-reason 定案（事件名表示"非封闭下载失败"，不承诺异常类未知）；我复核 `ingestion_runtime.py:4378` 的条件确为公共分类驱动、无第二份异常名单，`dayu/fins/README.md` 的表述（"封闭 storage 等其它公共分类不产出该诊断"）与代码一致，不另立 finding。
- **OQ3（低 / 表述边界）**：workflow 在 typed catch 中确会 `yield` 当前候选的 `FILING_FAILED`（`cn_download_workflow.py:352-357`，并由 `tests/fins/test_cn_download_workflow.py:2775` 固定），但 `_emit_adapter_download_progress`（`cn_pipeline.py:239-286`）的 stage 词汇表只覆盖 file/conversion 级（`download.file_*`、`download.conversion_*`），不含候选级 `FILING_FAILED`，故 direct CLI 看不到该候选级进度行。计划文字"发当前 `FILING_FAILED` 进度"在 workflow 层成立，属实现与计划文字的边界表述，不是行为缺陷。
- **OQ4（低 / 已裁决）**：`dayu/runtime/log.py` 的 `__all__`（`:437-446`）未列 `safe_exception_trace`，而 `ingestion_runtime.py:160` 与 `cli/commands/fins.py` 显式跨模块使用它。S2-R1/N4 已裁决为非阻断（`__all__` 只影响 wildcard import）。我无新证据推翻，仅登记：若该模块视 `__all__` 为公开契约，应补列以消除"跨层使用未声明公开符号"的歧义。
- **OQ5（低）**：真实 CLI 的 typed 失败证据全部落在 **whole-kind 零候选**路径（root 外来文件触发 `discovered=0`）；mid-filing（`discovered=2, PARTIAL_FAILURE`）与 post-repair（`succeeded` 文档终态 + 整体 FAILURE）只有 owner 级真实仓储测试，无真实 CLI 复现。这是有界取舍（本地可确定性注入 vs 外部 provider 不可控），但意味着"typed 部分摘要"没有端到端真实 CLI 证据。
- **OQ6（低 / 供总控核对审计链）**：S1 实施记录自报的 14 文件候选摘要 `f2766de5…` **无法**从 S1 提交复算；从提交复算得 `39018b65…`，从主工作区复算得 `f1e1a915…`（与 S1 裁决记录一致）。我按第 8 行证据定位到差异**仅为另一 WU 的 3 处 README 点号句 + 2 处空行归一**，11 个代码/测试文件在主工作区与 S1 提交之间**逐字节相同**，故确认是**摘要基线不同**而非内容漂移，`f2766de5` 应是当时 `git diff`（无 base，对 47a9cb64）口径。不构成代码缺陷，但建议后续在实施记录中显式写明 `git diff` 的 base，避免审计链歧义。

## Residual Risk

- **残余 WU 与 owner**（全部 `assigned to later work unit`，本 aggregate 不伪称解决）：

| WU | 覆盖的残余 | 本 review 的直接证据/边界 |
| --- | --- | --- |
| `fins-cninfo-single-day-discovery-window` | 精确单日筛选 0 候选（外部数据/产品行为） | 两处单日实测 exit0 但 `discovered=0`；真实证据改用 3 日以上窗口并如实标注方法差异 |
| `fins-direct-projection-failsafe` | RESULT/日志构造或 logger handler 自身再次失败时的线程级原始 traceback | producer 已保证"先 RESULT 后日志"（`:6209` 断言），但未兜底二次失败；与本轮 OQ1 新增的 job 终态逃逸面同源，建议合并取舍 |
| `fins-download-storage-sibling-errors` | `SourceIntegrityRepairBlockedError`、`SourceIntegrityRevisionConflictError` 的公共业务分类 | 二者仍落 EXECUTION；revision conflict 的部分摘要守恒已由 S1 覆盖并保留 EXECUTION 分类（`cn_pipeline.py:1387-1393` 与 `tests/fins/test_cn_download_runtime.py:1877`） |
| `fins-other-raw-diagnostics-audit` | 非 download 外层与既有 job 路径的原始 traceback；`_save_failed_from_exception` 的 `error_type`+`exc_info` WARN | CLI 非 download 仍 `logger.exception`（`cli/commands/fins.py:223`）；该 WARN（`:6093-6099`）未在 #198 修改 |
| `fins-download-no-source-retry-hint` | 无来源文档在 Service/JSON 路径的 retry hint 可操作性 | `ingestion_runtime.py:4439` 仍提示"检查运行日志中的脱敏分类"；CLI 侧已改由共用提示准确指向运行日志 |
| `fins-download-job-reason-code-persistence` | 后台 job 持久摘要无 public `reason_code` | `_save_typed_download_failure` 只存 `to_json_summary()` + 安全 message；当前无生产消费者 |
| `fins-download-indeterminate-publication-state` | physical swap/rollback 双失败、postcommit 失败，以及"已确认文档后 generic 异常退回零摘要" | 中止路径只在 storage owner 可证明的 pre-swap typed 保留快照（`cn_download_workflow.py:422-441` 只捕 `SourceIntegrityPreflightError`），未用异常名/时序猜发布状态 |
| `fins-download-other-source-summary-conservation` | SEC／其它来源 typed 中止丢失已处理文档行 | `sec_download_filing_workflow.py` 的 typed 抛出仍是裸透传 + 零候选摘要，本轮未改 |
| （新增登记建议）job typed 终态兜底 | 见 OQ1：typed job 的公共失败投影在 try 之外，异常会逃逸且 job 停留 `running` | 当前不可达；建议并入 `fins-direct-projection-failsafe` 或独立 WU |

- **测试覆盖缺口**：无直接断言"非 download direct 失败不产生 `fins.download.unexpected_failure`"。结构上由 `context.download_request is None → public_failure is None`（`ingestion_runtime.py:4346-4364`）保证；CLI 侧非 download 反例已固定，故风险低。
- **本轮未覆盖的验证口径**：coverage 插桩口径、全量 suite、`tests/cli` 全目录、真实 CLI 复跑（见"前轮协议失败与本轮实际验证范围"）。CI/无沙箱环境下的真实结果仍应以外部为准。
- **环境事实**：主工作区 `/Users/leo/workspace/dayu-agent-r` 的 HEAD 为 `7234d42d`（不含 S2 提交），并留有其它 WU 的未提交 README 改动；这些内容不属 #198，可解释第 8 行的全部差异，本轮仅作只读核对。
- **文档／语义残余**：三份 README 的 #198 描述经与代码逐条核对一致（含"并非每次此类失败都会产生未知异常诊断"、"其它普通运行日志仍可能包含用户路径"两处诚实限定）。`dayu/README.md` 未改，因分层/装配关系无变化，符合 AGENTS.md 触发规则。
- **artifact 路径**（绝对）：本 review = `/private/tmp/dayu-issue198-aggregate-dsflash-r2/docs/reviews/issue-198-aggregate-dsflash-r2-20260929.md`。
