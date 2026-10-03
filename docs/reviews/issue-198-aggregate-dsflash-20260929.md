RUNTIME/PROVIDER/MODEL: claude/ds-flash/deepseek-flash[1m]
CANARY=ds-flash-c43b217d

# Code Review

## Scope

- Mode: current changes（issue 级 **aggregate**：S1+S2 组合、交互与残余分类。本 review 不以 S2 slice 复审或 S1 单提交 review 充数；既有的 slice review/adjudication 只作为**输入材料**，本文全部结论来自本次独立走读代码路径与本次实跑命令）
- 仓库/工作区: `/private/tmp/dayu-issue198-aggregate-dsflash`（detached worktree，从目标 commit 建立）；目标 PR #197 未被 push/评论/修改
- Branch or PR: detached HEAD = `2643de25d6258fe2d83b527ea3823ffa3eb19bff`；开始与结束 `git status --porcelain` 均为空（结束时仅多出本 review 文件）
- 指定增量范围: PR #197 旧 head `9735800cb55a40336469593fa2fddae43c9c69ad` 之后的三个提交 `47a9cb64`（S1 计划/文档）、`7234d42d`（S1）、`2643de25`（S2）
- **范围校正（直接证据）**: `9735800` **不是** HEAD 的祖先（`git merge-base --is-ancestor 9735800 HEAD` 为假），`git rev-list --count 9735800..HEAD` = 3 成立，但两点 diff 混入了 PR #197 分支与当前主线之间的无关分歧（删除 `dayu/cli/workspace_root.py`、`tests/cli/test_workspace_root.py`、多份其它 WU 的 `docs/gateflow`/`docs/reviews` 文件，以及 `dayu/cli/agent_entrypoint.py`、`dayu/fins/upload_format_contract.py`、`dayu/fins/storage/_fs_source_integrity.py`、`dayu/cli/session_execution.py`、`dayu/runtime/log.py` 之外的多处差异）。因此本次 effective base 取三提交的直接父 `8d8d494fbbce0052372fb1b42097c9f7222cfa28`，review scope = `git diff 8d8d494f..HEAD`（56 文件、6246 insertions、88 deletions）。已逐项核对：该范围内**不含** `dayu/cli/workspace_root.py`、`dayu/cli/agent_entrypoint.py`、`dayu/fins/upload_format_contract.py`、`dayu/fins/storage/_fs_source_integrity.py` 等无关文件，即两点 diff 的其余部分不是 #198 内容。
- Included scope
  - 生产改动 8 文件：`dayu/fins/direct_events.py`、`dayu/fins/ingestion_runtime.py`、`dayu/fins/pipelines/cn_download_workflow.py`、`dayu/fins/pipelines/cn_pipeline.py`、`dayu/runtime/log.py`、`dayu/service/fins_wait_adapter.py`、`dayu/cli/output.py`、`dayu/cli/commands/fins.py`
  - 测试/文档：`tests/runtime/test_log.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/fins/test_cn_download_workflow.py`、`tests/fins/test_cn_download_runtime.py`、`tests/cli/test_output.py`、`tests/cli/test_fins_commands.py`、`tests/service/test_fins_wait_adapter.py`、`README.md`、`dayu/fins/README.md`、`tests/README.md`
  - 跨层组合面：storage typed `unsafe_publication` → 单一 public reason 映射 → direct RESULT → CLI／wait JSON → 后台 job 持久摘要；部分发布守恒与 rollback/repair 状态；未知 download 的安全类型指纹与包内帧（producer 与 CLI 外层）；RESULT→安全 ERROR 顺序；typed／no-source／非 download 不误记；S1/S2 组合后的隐私与文档；已审候选与已提交内容一致性；既有真实 CLI 证据的独立复核
- Excluded scope: 其它 WU（点号元数据 inspector、workspace-root o03、upload material o-series、CNInfo 单日发现窗口）的实现与文档；`dayu/engine`、`dayu/host`、`dayu/config` 与本次无交集的代码；与 #198 无关的既有失败（见 Residual Risk）
- Parallel review coverage: 无。按派发要求未使用 subagent，未派发任何子 Agent

## Findings

未发现实质性问题。

以下四条是本轮重点反证面，均已沿真实调用链走读并给出直接证据；此外列出反向怀疑的排除过程，便于总控复核"为什么没有 finding"。

1. **typed `unsafe_publication` 从 source preflight 到 direct/CLI/wait/job 保真**（storage → workflow → adapter → runtime → 消费者）
   - storage owner 抛出 `SourceIntegrityPreflightError(SourceIntegrityPreflightReason.UNSAFE_PUBLICATION)`（`dayu/fins/storage/source_integrity.py:191-208, 311`），四值封闭。
   - runtime 在唯一异常投影点用显式全量表 `_SOURCE_INTEGRITY_PUBLIC_REASONS`（`dayu/fins/ingestion_runtime.py:6910-6915`）以 enum 成员身份映射到公共 `FinsDownloadFailureReason`（`dayu/fins/direct_events.py:174-180`），**不解析字符串**（全仓 `unsafe_publication` 字面量只出现在这两个 enum 定义处，无第二份映射）。
   - `FinsPublicFailure.__post_init__` 拒绝非该 enum 的值与非 STORAGE/带 transport 的组合（`direct_events.py:252-255`）；`to_json_value()["reason_code"]` 输出 `.value` 或 `null`（`direct_events.py:273`）。
   - direct producer 由 `_download_exception_cause` 单点 unwrap 私有 adapter failure（`ingestion_runtime.py:6918-6931`），同一 cause 同时进入 `_classify_direct_error`（→`STORAGE`）与 `_download_public_failure_from_exception`（→`storage/unsafe_publication` + 修复提示，`ingestion_runtime.py:6975-6983`），RESULT 的 `error_kind` 与 `failure.kind` 同源一致。
   - CLI 只打印公共 `.value`（`dayu/cli/output.py:488-499`），wait 只序列化 `failure.to_json_value()` 并追加 `scope_note`（`dayu/service/fins_wait_adapter.py:592-623`）；Service 侧无其它 `failure` 消费者（`grep` 仅命中 wait adapter）。
   - job 路径 `_save_typed_download_failure`（`ingestion_runtime.py:5005-5041`）与 direct 使用同一公共失败映射与同一已验证 typed summary，只把 `summary.to_json_summary()` 与安全 `safe_message` 写入 failed record。job 持久摘要**不含** public `reason_code`，与已登记的残余 WU 一致（见 Residual Risk）。
2. **部分发布守恒与 rollback/repair 状态**
   - CN/HK workflow 在「单 filing Phase A/B typed」与「post-repair 分类/显式 revision conflict/company pre-swap typed」两处收口：前者把当前候选记为一个私有 `failed` 行后冻结 `filings` 快照（`cn_download_workflow.py:344-369`），后者在已处理 filing 之后保留既有唯一终态行、不新增 `failed` 行（`cn_download_workflow.py:395-441`）；快照经 `_build_summary`/`_build_result` 从同一 `filings` 派生且列表被复制（`cn_download_workflow.py:521-568, 911-989`）。
   - 首候选前的 whole-kind preflight 与「无 repair 的循环前 company pre-swap typed」保持原异常裸透传 + 请求级零候选 `FAILED` 摘要（`cn_download_workflow.py:260-289` 与 runtime `_empty_download_summary_from_request`），不会由空 `filings` 派生 `SUCCEEDED`。
   - adapter 只对该私有 abort 严格投影（先校验 `status == "integrity_failed"`，再复用抽出后的唯一纯投影 helper，`cn_pipeline.py:1371-1395, 1450-1518`），不伪造 `ok`、不绕过 row/locator 校验；`_execute_download_request` 在 adapter 边界对 `persisted_summary` 执行 `_bounded_download_summary` 与 `_validate_download_summary_request_identity`（`ingestion_runtime.py:5396-5399`）。
   - `FinsResultSummary` 的放宽限于「FAILURE + 有 public failure + 已由 row/count owner 派生的 `FAILED/PARTIAL_FAILURE/SUCCEEDED`」，仍拒绝 CANCELLED（`direct_events.py:677-690`）；我枚举了 `dayu/` 内全部 `FinsResultStatus.FAILURE` 构造点（producer 异常分支、no-source 分支、preprocess/upload、observation 兜底），只有 #198 目标路径能构成被放宽的组合，没有别的调用者会静默产出误导状态。
   - rollback 语义只承诺 owner 可证明的范围：storage `commit_batch` 的 staged whole-tree 校验先于 publication guard/swap，所以 pre-swap typed 时旧 target 未被物理替换；代码与测试都未宣称 cleanup 成功，也未用 `__cause__` 判定发布归零（`cn_download_workflow.py` 中止路径不检查异常链）。
3. **未知 download 的安全类型指纹与包内帧（producer 与 CLI 外层）**
   - `dayu/runtime/log.py` 纯新增 105 行，只依赖 stdlib 与 `dayu.contracts.json_value`/`dayu.runtime.log_levels`，无 Fins/CLI/Host import（无反向依赖、层中立）。
   - `safe_exception_trace`（`log.py:91-112`）只输出单行 `exception_type/custom_type/stack/truncated`；类型部分按 `vars(builtins)` 身份校验取内建祖先，自定义类型只输出 `module"\0"qualname` 的 SHA-256 前 16 hex（`log.py:115-143`）；帧部分要求 `f_globals` 与 `sys.modules` 同字典、`module.__file__` 与 `co_filename` 严格解析同一、位于传入包根内且各路径段为合法标识符，否则固定 `[external]`（`log.py:146-180`）；整体对任何内部异常返回固定安全串，不读取 message/args/cause/locals/源码行。
   - producer 日志与 CLI 外层 catch 复用同一 helper，`source_root` 分别由各自文件位置解析为 `dayu` 包根（`ingestion_runtime.py:4381`、`dayu/cli/commands/fins.py:220`），事件名分别为 `fins.download.unexpected_failure` 与 `fins.download.command_unexpected_failure`，均不带 `exc_info`。
   - CLI stdout/stderr、公共 RESULT 与 wait JSON 不承载调用栈或异常类型；CLI 外层对 download 与非 download 的最终用户文案逐字保持既有文本，且 `--log-file` 提示常量在 `dayu/cli/output.py:69` 唯一持有（全仓无第二份字面量）。
4. **RESULT→安全 ERROR 顺序与"不误记"**
   - producer 在异常分支先 `_emit_direct_result`（唯一终态，经 cancellation claim）再写安全 ERROR（`ingestion_runtime.py:4365-4382`）；测试用 spy 在日志提交前断言 RESULT 已投递（`tests/fins/test_fins_ingestion_runtime.py:6196-6243`）。
   - 日志条件是「download 且公共分类为 EXECUTION」：typed preflight 为 STORAGE（不记）、no-source 是非异常 RESULT 路径（不记）、非 download 因 `context.download_request is None` 使 `public_failure is None`（不记）；CLI 侧非 download 仍保留原 `logger.exception` 行为（`tests/cli/test_fins_commands.py:3181-3204`）。
   - job 路径的 typed 二次保存失败只写固定标识 `fins.download.typed_failed_record_save_failed`、不设 `error_type`、不写动态信息，测试断言不逃逸且 job 不被虚称终态（`tests/fins/test_fins_ingestion_runtime.py:6463-6530`）。

反向怀疑的排除（逐条给直接证据，避免"看起来合理"式结论）：

- **已审候选 ≠ 已提交内容？** 初看 S1 交付的单据与提交内容算出的 14 文件 `git diff --binary` 摘要不一致（f1e1a915… vs 39018b65…）。逐层反证后确认是**摘要算法基线差异**而非内容漂移：在主工作区 `/Users/leo/workspace/dayu-agent-r`（HEAD `7234d42d`）对同一 14 文件执行 `git diff --binary 8d8d494f -- <14 文件> | shasum -a 256` 得到 `f1e1a915…`，逐字一致；worktree-vs-提交的差异**仅为另一 WU 的点号元数据句**（`README.md` +1 行、`dayu/fins/README.md` +1 行、`tests/README.md` +1 行）与两处空行归一化，无任何 #198 行被改动或丢失（其余 11 文件 `git diff --name-only 7234d42d -- …` 为空）。S2 的 11 文件摘要 `2a79d071…` 可由提交直接逐字复算。
- **真实 CLI 证据是否被"窗口替换"成伪证？** 流哈希与发布物可独立复算（见验证记录 7），且 `typed.stderr` 明确不含 `--log-file` 提示与 `fins.download.*` 事件、`typed.log` 只有一条普通 INFO；`recovery.stdout` 与 baseline 逐字节相同；注入用的外来文件在恢复后被清理。
- **`FinsResultSummary` 放宽是否会被其它调用者误用**：见上第 2 条的最后一段（枚举全部构造点）。
- **是否存在下游重算 public reason**：`unsafe_publication` 字面量全仓只在两个 enum 定义处；CLI/wait/JSON 只取 `.value`；`reason_category`（文档行自由文本）与 `reason_code`（公共枚举）在 CLI 输出中标签不同，未混用。

## 验证记录

环境：`.venv` Python 3.11.15，`dayu.__file__` 指向本 worktree；以下命令均在 `/private/tmp/dayu-issue198-aggregate-dsflash` 执行，逐条自身 exit0（预期非零已单独标注）。

| 验证 | 命令 | 退出码 | 结果 |
| --- | --- | ---: | --- |
| 受影响测试（计划口径 8 文件） | `python -m pytest tests/runtime/test_log.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/cli/test_output.py tests/cli/test_fins_commands.py tests/service/test_fins_wait_adapter.py tests/service/test_fins_direct.py -q` | 0 | **856 passed**, 3 warnings（edgartools 弃用） |
| 全量 pyright | `python -m pyright dayu/ tests/ utils/` | 0 | **0 errors, 0 warnings, 0 informations** |
| 单文件覆盖率（--branch；8 生产文件；含 `tests/fins/test_cn_pipeline.py`，排除 4 个插桩敏感取消用例） | `coverage run --branch --source=… -m pytest <9 文件> -q -k 'not …'` + `coverage report` | 0 | 888 passed, 4 deselected；`runtime/log.py` 92%、`fins/ingestion_runtime.py` 88%、`cn_download_workflow.py` 92%、`cn_pipeline.py` 92%、`direct_events.py` 85%、`cli/output.py` 82%、`cli/commands/fins.py` 80%、`service/fins_wait_adapter.py` 92% —— 全部 ≥80% |
| 同口径不排除插桩敏感用例 | 同上不带 `-k` | 1 | 4 failed / 852 passed：均为取消时序用例在 coverage 插桩下的调度差异（其中 `tests/service/test_fins_direct.py::test_task_cancellation_closes_runtime_stream` 位于本次**未修改**的文件，证明与 #198 无关） |
| 回归对照：CLI 测试集 | `pytest tests/cli -q --timeout=30`（HEAD 与 base `8d8d494f` 各一次） | 1 / 1 | HEAD `74 failed, 1318 passed`；base `74 failed, 1316 passed`；**FAILED 集合逐行相同**（TTY/subprocess/provider-discovery 类，环境相关）；HEAD 净增 2 个通过用例 |
| 回归对照：非 CLI 测试集 | `pytest tests --ignore=tests/cli -q --timeout=60`（HEAD 与 base 各一次） | 1 / 1 | HEAD `17 failed, 6740 passed`；base `17 failed, 6705 passed`；**FAILED 集合逐行相同**（含 `tests/service/test_import_boundary.py` 的两处越界 import，经 `git log -S` 确认由 #195/#196 引入并在 base 已存在）；HEAD 净增 35 个通过用例 |
| 全量 suite | `pytest -q` | — | 本沙箱下一次在 `tests/cli` 内挂起（该目录单独运行 80s 完成），另一次在首个既有失败处停止；**不作为通过证据**，以上面两行的 base/HEAD 对照替代 |
| 审查完整性：S1 已审候选 | 主工作区 `git diff --binary 8d8d494f -- <14 文件>\| shasum -a 256` | 0 | `f1e1a91557cda273c5d0b77900920381727322a8edea69d6061cda27f0f6bd21`（与 S1 裁决逐字一致） |
| 审查完整性：S2 已审候选 | `git diff --binary 7234d42d 2643de25 -- <11 文件>\| shasum -a 256` | 0 | `2a79d0713b965be82734552d89619f56957968d62b0344a2652d8848797cfc54`（与 S2 裁决逐字一致） |
| 证据文件摘要 | `shasum -a 256 docs/gateflow/issue-198-s2-cli-fresh-evidence-20260929.md` / `…-replay-evidence…` | 0 | `cbb38609e5e40c7812a965e979407d6bd66ae74fcf2c0a9f0f7a7781ff348545` / `8a014d41f9a604b97aa53808dcb60c4cd8f64278206362b8fd24a644412ed997` |
| fresh CLI 原始流 | `shasum -a 256` on `/private/tmp/issue198-cli-wide2-9aklx640/*` | 0 | baseline.stdout `23c41eda…`、baseline.stderr `e3b0c442…`（空）、baseline.log `3d31052a…`、typed.stdout `0804026d…`、typed.stderr `dc00b1c4…`、typed.log `93e88e89…`、recovery.stdout `1e5f1a46…`、recovery.stderr `e3b0c442…` —— 与证据表逐字一致 |
| fresh CLI 发布物 | `find …/portfolio -type f -exec shasum -a 256` | 0 | `fil_cn_95d26c…pdf` = `b17a9b9b…`、`_docling.json` = `bf98154f…`（与证据文一致）；五份已发布来源文件俱在；注入用的 `issue198-unassignable-root.txt` 不在（恢复已清理） |
| fresh/replay 隐私扫描 | Python 逐流正则检查（受控外来 basename、`Traceback`、case 绝对路径、`https?://`、token 关键词、`fins.download.*`、`请使用 --log-file`） | 0 | typed/recovery 全部流零命中；typed 案例按设计不含 unknown 诊断与 CLI 提示 |
| replay 原始流 | `shasum -a 256` on `/private/tmp/issue198-cli-replay-e23865b8/*` | 0 | baseline/recovery stdout `cc02b78f…`、typed.stdout `0804026d…`、typed.stderr `5349d095…`、typed.log `c83123c0…`、空流 `e3b0c442…` —— 与 replay 证据表逐字一致 |
| 分层/单一真源静态核对 | `grep`（hint 字面量、`unsafe_publication` 字面量、`failure` 消费者、`dayu.runtime.log` import 面） | 0 | CLI 提示常量单点持有；`unsafe_publication` 只在两个 enum；Fins public failure 的 Service 消费者只有 wait adapter；runtime helper 无业务层 import |

## Open Questions

- **OQ1（低 / 需更多证据）**：storage 的 `SourceIntegrityPreflightError.__init__`（`dayu/fins/storage/source_integrity.py:191-208`）不校验 `reason` 成员，而同文件的 `SourceIntegrityRepairBlockedError` 有 `isinstance` 校验；Fins 侧以 `exc.reason` 为字典键（`dayu/fins/ingestion_runtime.py:6982`）。非成员值会导致 KeyError 在 producer 的 except 块内抛出并逃逸，由 `threading.excepthook` 写出线程级原始 traceback（绕过安全日志且无 RESULT）。已核 `dayu/` 下 13 处构造点全部传闭合枚举成员，当前不可达（改动前的 `exc.reason.value` 写法则会 AttributeError 逃逸，风险面未扩大，故不立 finding）。建议由 storage owner 补成员校验，或让映射显式处理非成员值。
- **OQ2（已裁决，仅登记）**：`fins.download.unexpected_failure` 也会记录 EXECUTION 分类中的**已知**条件（缺 adapter 的 `_UnsupportedDownloadSourceError`、`SourceIntegrityRevisionConflictError`）。controller 已以 rejected-with-reason 定案（事件名表示"非封闭下载失败"，不承诺异常类未知）。我复核代码与负例测试（typed 与 no-source 均不产生该事件）后与裁决一致，不另立 finding；若未来要求事件名严格对应"未知类型"，需改由公共分类之外的第二信号驱动。
- **OQ3（低）**：workflow 的 `FILING_FAILED` 事件未进入 runtime 进度 sink 的封闭 stage 词汇表（`cn_pipeline.py:220-288` 只映射 file/conversion 级 stage），因此 direct CLI 看不到该候选级进度行。计划文字"发当前 `FILING_FAILED` 进度"在 workflow 层成立并由 `tests/fins/test_cn_download_workflow.py:2781` 固定；属实现与计划文字的边界表述，不是行为缺陷。
- **OQ4（低 / 已裁决）**：`dayu/runtime/log.py` 的 `__all__`（`log.py:437-446`）未列 `safe_exception_trace`，但 `dayu/fins/ingestion_runtime.py:160` 与 `dayu/cli/commands/fins.py` 显式跨模块导入它；S2-R1/N4 已裁决为非阻断（`__all__` 只影响 wildcard import，当前不作为公共 contract）。我没有新证据推翻该裁决，仅登记：若该模块视 `__all__` 为公开契约，应补列以消除"跨层使用未声明公开符号"的歧义。
- **OQ5（低）**：真实 CLI 的 typed 失败证据全部落在 whole-kind 零候选路径（root 外来文件触发），而 mid-filing／post-repair／单 filing commit typed 与 revision conflict 只有 owner 级真实仓储测试（无真实 CLI 复现）。这是有界取舍（本地可确定性注入 vs 外部 provider 不可控），但意味着"typed 部分摘要"没有端到端真实 CLI 证据。

## Residual Risk

- **残余 WU 与 owner**（全部 `assigned to later work unit`，本 aggregate 不伪称解决；均已在 S1/S2 裁决与主修复队列登记）：

| WU | 覆盖的残余 | 本 review 的直接证据/边界 |
| --- | --- | --- |
| `fins-cninfo-single-day-discovery-window` | 精确单日筛选 0 候选（外部数据/产品行为） | CLI 证据两处均 exit0 但 `discovered=0`；三轮证据改用 3 日窗口并如实标注方法差异 |
| `fins-direct-projection-failsafe` | RESULT/日志构造或 logger handler 自身再次失败时的线程级原始 traceback | producer 已保证"先 RESULT 后日志"，但未兜底二次失败；`_run_direct_stream_producer` 的 finally 之后仍有逃逸面 |
| `fins-download-storage-sibling-errors` | `SourceIntegrityRepairBlockedError`、`SourceIntegrityRevisionConflictError` 的公共业务分类 | 二者仍落 EXECUTION（revision conflict 无 reason_code）；revision conflict 已按计划以 owner 测试固定 |
| `fins-other-raw-diagnostics-audit` | 非 download 外层与既有 job 路径的原始 traceback；generic job `str(exc)` 进入 failure record 的 Service/LLM 投影；既有 WARN 的 `exc_info=True` | CLI 非 download 仍 `logger.exception`；job generic 失败仍写 `str(exc)`，且 job 路径无 unknown 诊断 |
| `fins-download-no-source-retry-hint` | 无来源文档在 Service/JSON 路径的 retry hint 可操作性（默认临时日志下不可查） | `ingestion_runtime.py:4433` 仍提示"检查运行日志中的脱敏分类"；本轮只让 CLI 的共用提示准确指向运行日志 |
| `fins-download-job-reason-code-persistence` | 后台 job 持久摘要无 public `reason_code` | `_save_typed_download_failure` 只存内部 `to_json_summary()`（无 reason_code）+ 安全 message；当前无生产消费者 |
| `fins-download-indeterminate-publication-state` | physical swap/rollback 双失败、postcommit 失败，以及"已确认文档后 generic 异常退回零摘要"（含私有摘要校验失败路径） | 中止路径只在 owner 可证明的 pre-swap typed 保留快照；其余仍走既有零候选口径，未用异常名/时序猜发布状态 |
| `fins-download-other-source-summary-conservation` | SEC／其它来源 typed 中止丢失已处理文档行 | `sec_download_filing_workflow.py` 的 typed 抛出仍是裸透传 + 零候选摘要，本轮未改 |

- **测试覆盖缺口**：没有直接断言"非 download direct 失败不产生 `fins.download.unexpected_failure`"。代码结构上由 `context.download_request is None → public_failure is None` 保证（同一条数据路径），CLI 侧非 download 的反例已固定（`tests/cli/test_fins_commands.py:3181-3204`），故风险低。
- **coverage 插桩敏感性**：4 个取消时序测试在 coverage 插桩下失败，非插桩下 856/856 通过；其中 1 个位于本次未修改的测试文件。若后续需要插桩下的全绿，需单独调查调度敏感性（不属 #198 语义）。
- **本沙箱环境限制**：`tests/cli` 74 项与其余 17 项失败在 base 与 HEAD 完全同集（TTY/subprocess/provider-discovery/网络类；本沙箱无网络出口）；全量 suite 两次尝试分别挂起与提前停止，均未作为通过证据。CI 上的真实结果仍应以无沙箱环境为准。
- **文档/语义残余**：`dayu/fins/README.md` 与根 `README.md` 对 S1/S2 的描述经核对与代码一致（含"并非每次 EXECUTION 都会有 unknown 诊断"）；三份 README 中另一 WU 的点号元数据句仍在主工作区未提交，提交时按行隔离，本 review 未覆盖那些 WU。
- **工作树归属**：主工作区 `/Users/leo/workspace/dayu-agent-r` 仍留有其它 WU 的未提交改动（点号元数据 inspector、upload material 文档等）。这些内容不属于 #198，也未进入本 review 的任何结论。
