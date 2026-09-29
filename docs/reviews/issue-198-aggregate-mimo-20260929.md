# Code Review

RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]
CANARY=mimo-3ae9849b

issue #198 整项 aggregate deepreview（S1+S2 组合、交互与残余分类）。依据
`/Users/leo/.codex/skills/deepreview/SKILL.md` 的 Review Method 与固定 finding format 执行；
本 review 只产出本文件，未修改任何代码、测试、README 或既有 gate/review artifact，未
commit、push、PR 或派发子 Agent。

## Scope

- Mode: current changes（Gateflow aggregate deepreview gate：issue 增量 `9735800c…HEAD` 三个提交）
- Branch or PR: 工作树分支 HEAD `2643de25d6258fe2d83b527ea3823ffa3eb19bff`；目标 draft PR #197
  （`codex/upload-material-oracle` → `main`），远端旧 head `9735800cb55a40336469593fa2fddae43c9c69ad`
- Base: 精确增量基线为三个提交的共同父提交 `8d8d494fbbce0052372fb1b42097c9f7222cfa28`
  （`git merge-base 9735800c… 2643de25` 同值；`git log 9735800c…HEAD` 恰为 3 个提交）
- Output file: `docs/reviews/issue-198-aggregate-mimo-20260929.md`
- Included scope: 三个提交引入的全部 56 个文件变更（`git diff --stat 8d8d494f..HEAD`：
  56 files changed, 6246 insertions(+), 88 deletions(-)），含：
  - 生产代码：`dayu/fins/ingestion_runtime.py`、`dayu/fins/direct_events.py`、
    `dayu/fins/pipelines/cn_download_workflow.py`、`dayu/fins/pipelines/cn_pipeline.py`、
    `dayu/service/fins_wait_adapter.py`、`dayu/cli/output.py`、`dayu/cli/commands/fins.py`、
    `dayu/runtime/log.py`
  - 测试：`tests/runtime/test_log.py`、`tests/fins/test_fins_ingestion_runtime.py`、
    `tests/fins/test_cn_download_workflow.py`、`tests/fins/test_cn_download_runtime.py`、
    `tests/cli/test_output.py`、`tests/cli/test_fins_commands.py`、
    `tests/service/test_fins_wait_adapter.py`（`tests/service/test_fins_direct.py` 仅作回归验证、无改动）
  - 文档：根 `README.md`、`dayu/fins/README.md`、`tests/README.md`
  - gateflow/review artifact：goal、plan（10 次 fix 记录）、S1/S2 implementation、
    code review adjudication、S2 fresh/replay CLI 证据、S1/S2 各轮 review artifact
- Excluded scope:
  - 远端旧 head `9735800c…` 相对 merge-base 的远端独有提交（UM-O03/UM-O20、fins 点号元数据
    deepreview 等 8+ 个提交）及 `git diff 9735800c..HEAD` 中对它们的逆向差异：不属
    issue #198 增量，未计入本 review（`tests/fins/test_fins_storage_atomicity.py` 在该
    tree-to-tree diff 中的 426 行变化即来自远端侧点号元数据 WU，与 #198 三提交无关）。
  - 独立 WU 的产品语义（点号元数据忽略规则、upload material 修复、CNInfo 单日发现合同）。
- Parallel review coverage: 无。本 review 由单一 reviewer 逐文件走读，未派发子 Agent。

## 精确 commit / diff

| 提交 | 内容 | 体量 |
| --- | --- | --- |
| `47a9cb64e63780deb568a9e2c6fdd0120441cf2f` | docs: accept issue 198 S1 download failure plan（accepted plan + 12 份 plan review artifact + S1 裁决前半） | 14 files, +1563/-8 |
| `7234d42dbaea603112c6fed52776281228d261a7` | gateflow: accept issue-198 S1（typed 预检贯通、部分发布守恒、job 同源、wait scope_note、CLI `reason_code=`） | 30 files, +3556/-65 |
| `2643de25d6258fe2d83b527ea3823ffa3eb19bff` | gateflow: accept issue-198 S2（`safe_exception_trace`、producer/CLI 安全诊断、CLI 日志提示收口、README F2 落位） | 20 files, +1128/-16 |

组合产品 diff 基线：`git diff 8d8d494f..HEAD -- dayu/ tests/ README.md`。S1 切片曾以 14 文件
diff SHA 锁定（最终 `f1e1a91557cda273c5d0b77900920381727322a8edea69d6061cda27f0f6bd21`），
S2 切片以 11 文件 diff SHA `2a79d0713b965be82734552d89619f56957968d62b0344a2652d8848797cfc54`
锁定；两者在各自 accepted slice commit 中已落库，且 S2 产品/测试字节在 README-only F2 修前后
一致（S2 裁决记录）。本 review 对最终落库快照（= 当前 HEAD）独立走读，未依赖切片自述结论。

## Findings

未发现实质性问题。

本 review 按 deepreview 方法对 S1+S2 组合做了跨层反证，以下关键闭环均沿同一逻辑/数据路径
直接验证成立（证据见「验证」）：

1. **storage typed `unsafe_publication` 全链路保真**：`source_integrity.py:SourceIntegrityPreflightReason`
   四值封闭枚举 → `_fs_source_integrity._inspect_source_kind_unguarded`（unassignable root /
   untrusted manifest 抛 `SourceIntegrityPreflightError(UNSAFE_PUBLICATION)`）→
   `cn_download_workflow` typed 收口或裸透传 → `cn_pipeline.CnDownloadAdapter` 私有
   `FinsSourceDownloadAdapterFailure`（持原 cause 对象）→ `ingestion_runtime._download_exception_cause`
   单点 unwrap → `_download_public_failure_from_exception` 唯一映射
   `_SOURCE_INTEGRITY_PUBLIC_REASONS`（键/值全集双向断言 + 每对 `.value` 相等，由
   `test_direct_download_preserves_every_preflight_reason` 固定）→
   `FinsPublicFailure(reason_code=…, kind=STORAGE, transport=None)` → direct RESULT、
   CLI `reason_code=`、wait JSON `failure.reason_code`、job safe message 同源。无消费者从
   字符串、行、日志或事件顺序反推公开码；`direct_events.py` 不 import storage，公共 enum 独立。
2. **部分发布守恒与 rollback/repair 状态**：单 filing Phase A/B typed → 当前候选一行
   `failed` + `FILING_FAILED` + `CnDownloadIntegrityAbort`（含已处理 `filings` 快照）；post-repair
   分类块 catch 同时覆盖 classifier typed 与显式 `SourceIntegrityRevisionConflictError`；
   post-repair `_publish_cn_company_after_repair` catch storage pre-swap typed（`commit_batch` →
   `_validate_complete_source_tree` → `_validate_complete_source_kind_tree` →
   `_inspect_source_kind_unguarded` 在 physical swap/backup 之前抛 typed，storage 代码注释
   「完整性校验只读 transaction staging，必须先于 publication guard」为直接证据）；
   循环前 whole-kind / company pre-swap typed 裸透传并配请求级
   `_empty_download_summary_from_request(..., FAILED)` 零候选摘要（`terminal_disposition=FAILED`
   由 override matrix 测试钉死，防误派生 `SUCCEEDED`）；post-repair 不新增重复 `failed` 行或
   第二次 `FILING_FAILED`；`CnDownloadCancelledError` 先于 typed catch 保留取消控制流；
   mid-filing `SourceIntegrityRevisionConflictError` 仍走普通 `except Exception` 继续循环
   （残余行为由注入测试锁定归属）；direct/job 对同一已验证 snapshot 分别发唯一 RESULT /
   写 failed record，`result_summary` 精确等于同一 summary 的 `to_json_summary()`。
3. **未知 download 安全类型指纹与包内帧**：`runtime/log.safe_exception_trace` 只输出
   按 `vars(builtins).get(name) is ancestor` 身份证实的内建祖先、自定义类型
   `module\0qualname` SHA-256 前 16 hex 指纹（不输出原名）、受信 `dayu.*` 帧（模块字典同一 +
   `__file__`/`co_filename` 严格解析同一 + 位于调用方传入包根 + 合法标识符相对 `.py` 路径 +
   正整数行号）或 `[external]`/`[unavailable]`，`deque(maxlen=16)` + `truncated` 标志；
   整体格式化对 `Exception` 输入不抛出（内部失败返回固定安全串）。direct producer 传
   `dayu` 包根（`ingestion_runtime.py` 的 `parent.parent`），CLI 外层传 `fins.py` 的
   `parent.parent.parent`，均解析为 `dayu` 且不 import 反向层。
4. **RESULT→安全 ERROR 顺序**：`_run_direct_stream_producer` 先 `_emit_direct_result`
   再 `_LOGGER.error("fins.download.unexpected_failure …")`，测试在 logger 调用内断言
   RESULT spy 已计 1；CLI 外层 `fins.download.command_unexpected_failure` 与 producer 事件名
   分流，producer 已收口的失败不会被 CLI 重复记录（except 链不交叉）。
5. **typed / no-source / 非 download 不误记**：typed 四值与 OSError 走 STORAGE 分支
   （`public_failure.kind is EXECUTION` 才记 unknown 诊断），`test_direct_download_preserves_every_preflight_reason`
   断言 caplog 无 `fins.download.unexpected_failure`；无来源文档非异常 EXECUTION 保留文档
   RESULT 详情且不伪造 unknown 诊断（`test_direct_download_document_failure_is_execution_without_unknown_diagnostic`）；
   非 download 外层保留 `_LOGGER.exception` raw traceback 与逐字固定文案
   `dayu-cli {command}: 命令执行失败，请使用 --log-file PATH 重试并查看日志`（专测逐字断言）。
6. **Service / JSON / 日志 / README 同一语义**：`_print_download_failure` 的 `reason_code=`
   与 `to_json_value()["reason_code"]` 同取公共 enum `.value`（None → `"-"`）；文档行
   `reason=` 保持自由文本旧语义；wait `_failure_message` 失败帧固定字段 `scope_note`
   （逐字独立字面断言）与 `failure.retry_hint` 同帧，缺 download 的 typed 失败帧被拒绝；
   根 README 的自足 storage 恢复句、EXECUTION 提示与「并非每次此类失败都会产生未知异常诊断」
   表述与代码行为一致；`dayu/fins/README.md` 的映射/守恒/诊断边界与实现一致；`CLI_LOG_LOCATION_HINT`
   常量唯一位于 `output.py`（旧 `fins.py` 重复常量已退役）。
7. **S1+S2 组合隐私**：未知异常的 message/cause 含 URL、token、绝对路径的场景由
   `tests/runtime/test_log.py` 五组用例与 producer/CLI 测试断言不进入日志、stderr、RESULT、
   job record 或 wait JSON；typed job 二次保存 WARN 只有固定事件标识
   `fins.download.typed_failed_record_save_failed`（无 `error_type`、无 `exc_info`、无类名/路径）。

逐项对抗审查（失败模式、状态机各路径、参数生效链、branch ordering、overcoupling、
semantic ownership drift、LLM-facing 文本）均未发现可由同一逻辑/数据路径直接证据支撑的
实质缺陷；下列边界观察不构成对本 change 的 defect，已归入 Residual Risk 并带 owner。

## Open Questions

- 无。原「精确单日 CNInfo 筛选 0 候选」验证缺口已由 S2 终裁分类为独立 WU
  `fins-cninfo-single-day-discovery-window`（provider 列表行为，不属 #198 代码缺陷）；
  fresh 三日窗口真实发布→typed 失败→恢复证据经本 review 独立复核（见验证 §4），
  不再是本 issue 的阻断问号。storage 异常构造器无 runtime enum 校验（S1 裁决
  deferred-with-owner 至 `fins-direct-projection-failsafe`）维持原分类，当前生产 raise 点
  与测试映射全集已封闭可达性。

## Residual Risk

每项均为已登记分类，无未分类残余；owner 按语义真源标注：

| 残余 | 分类 | owner / 去向 |
| --- | --- | --- |
| 泛异常 / precommit ValueError、OSError / post-commit release / physical swap+rollback 双失败后已确认文档可能退回零摘要（明确缺陷，非正确行为） | `assigned to later work unit`：`fins-download-indeterminate-publication-state` | storage batch owner 先给 typed terminal publication certainty，再由 Fins result/job/LLM 投影 owner 表达；真实 swap+rollback 双失败测试锁定 |
| `SourceIntegrityRepairBlockedError` / mid-filing `SourceIntegrityRevisionConflictError` 仍落 EXECUTION、`reason_code=None` 且 retry 提示可能误导重试（安全诊断事件按 S2 合同属预期） | `assigned to later work unit`：`fins-download-storage-sibling-errors` | Fins download 公共分类 owner；不得私造公开 reason |
| 二次投影失败（RESULT 构造、typed job catch 的 failure/summary 构造、logger handler 再抛）仍可能经 `threading.excepthook` 泄出原始 traceback；typed job catch 的不逃逸承诺仅覆盖读取/保存一步（与 plan 合同一致） | `assigned to later work unit`：`fins-direct-projection-failsafe` | Fins runtime 投影 owner；连同 storage 异常构造器 runtime 校验一并审查 |
| 非 download 外层 raw traceback 日志；generic job `_save_failed_from_exception` 把 `str(exc)` 写入 failure record 及其 Service/LLM 投影；既有 `_save_failed_from_exception`/`_save_download_unsupported` 二次保存 WARN 的 `exc_info=True` | `assigned to later work unit`：`fins-other-raw-diagnostics-audit` | Fins 诊断审计 owner |
| 无来源文档 Fins 公共 `retry_hint` 在默认临时日志模式下指向退出后不可查日志 | `assigned to later work unit`：`fins-download-no-source-retry-hint` | Fins 公共 hint owner（Service/JSON 路径） |
| 后台 job failed record 只持久化安全 message，不持久化 `reason_code`/`kind`（direct RESULT 与 wait JSON 均带 `reason_code`；plan 合同只承诺 safe message + 同源 download summary，禁止四值映射副本） | `assigned to later work unit`：`fins-download-job-reason-code-persistence` | Fins job record schema owner（S2 终裁已登记） |
| SEC/其它来源 typed 中止仍可能丢已处理文档行投成零摘要 | `assigned to later work unit`：`fins-download-other-source-summary-conservation` | SEC/其它 workflow 收口 owner（plan OQ4/F5） |
| CNInfo 精确单日窗口 `2025-03-28…28` 与本地日 `03-29` 均 0 候选，accepted plan 的单日 baseline recipe 未按原命令通过（三日窗口替代证据已核） | `assigned to later work unit`：`fins-cninfo-single-day-discovery-window` | CNInfo discovery owner；总控已以只读探针定位 `totalRecordNum=0` |
| 奇异安装布局可能令全部受信帧降级 `[external]`（有界脱敏取舍） | `tracked in closeout`（S2 记录） | 跨布局诊断退化留 closeout 记录，不扩 S2 范围 |
| coverage 插桩使 2 个取消时序测试失败（普通 suite 通过） | `tracked`（S1 记录） | 插桩敏感性另查，非 #198 语义 |
| 点号元数据忽略规则 / 点号测试 / README 相邻句 | 独立 WU（远端侧已落 UM 系列提交） | 不计入 #198；相邻 README 句已按行分别 stage |

## 验证

工作区 `/private/tmp/dayu-issue198-aggregate-mimo`，`.venv` Python 3.11；全部在最终快照
HEAD `2643de25d6258fe2d83b527ea3823ffa3eb19bff`、干净工作树上执行。

1. **受影响测试**（plan 指定八文件）：
   `python -m pytest tests/runtime/test_log.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/cli/test_output.py tests/cli/test_fins_commands.py tests/service/test_fins_wait_adapter.py tests/service/test_fins_direct.py -q`
   → exit 0，**856 passed**，3 条第三方 edgartools deprecation warning（与 S2 记录一致）。
2. **全量 pyright**：`python -m pyright dayu/ tests/ utils/` → exit 0，
   **0 errors, 0 warnings, 0 informations**。
3. **单文件覆盖率**（statement+branch，coverage 插桩下排除 S1 已记录的 2 个插桩敏感取消时序
   测试，其余全绿）：加入各 owner 测试文件后
   `dayu/runtime/log.py` 92%、`dayu/fins/ingestion_runtime.py` 88%、`dayu/fins/direct_events.py` 85%、
   `dayu/fins/pipelines/cn_download_workflow.py` 92%、`dayu/fins/pipelines/cn_pipeline.py` 92%、
   `dayu/service/fins_wait_adapter.py` 92%、`dayu/cli/output.py` 82%、`dayu/cli/commands/fins.py` 80%，
   均 ≥80%。方法边界照实记录：若只跑 plan 八文件（不含 `tests/fins/test_cn_pipeline.py`），
   `cn_pipeline.py` 为 79% —— 差异来自该文件 owner 测试的选取，不属覆盖缺口；
   `fins.py` 的 80% 为 branch 口径下限（statement 口径 85%）。
4. **S2 fresh CLI 原始证据独立复核**（`docs/gateflow/issue-198-s2-cli-fresh-evidence-20260929.md`，
   证据快照 `/private/tmp/dayu-issue198-cli-wide2-9aklx640` 仍在）：
   - 8 份原始流逐字节复算 SHA-256 与字节数**逐项一致**：`baseline.stdout` 35262/`23c41eda…`、
     `baseline.stderr` 0/`e3b0c442…`、`baseline.log` 1842/`3d31052a…`、`typed.stdout` 208/`0804026d…`、
     `typed.stderr` 508/`dc00b1c4…`、`typed.log` 168/`93e88e89…`、`recovery.stdout` 862/`1e5f1a46…`、
     `recovery.stderr` 0/`e3b0c442…`。
   - 发布产物哈希一致：PDF `b17a9b9b…`、Docling JSON `bf98154f…`。
   - 独立 Python 字面断言 11 条全 PASS：typed.stderr 含 `classification="storage"`、
     `reason_code="unsafe_publication"`、修复提示，无 `--log-file` 提示、无 `Traceback`、
     无外来 basename、无盲目重试文案；typed.log 无两种 `fins.download.*` 事件、无 `Traceback`；
     typed.stdout 无失败详情；recovery 摘要 `discovered=1 downloaded=0 skipped=1`；mutation
     文件已清除。typed.stderr 实测形状为请求级零候选摘要
     （`discovered=0 … failed=0`）+ 安全 failure detail，与 whole-kind typed 合同一致。
   - 代码快照链：证据产生于 `/private/tmp/dayu-issue198-s2`（HEAD `7234d42d` + 11 文件候选），
     该目录现为同仓 worktree、HEAD 已推进至 `2643de25` 且 tracked 树干净；S2 产品/测试在
     README-only F2 修改前后逐字节相同（S2 终裁），故证据适用于最终落库快照。
5. **shell 命令执行记录（如实登记）**：审查期间一条复合命令（覆盖率输出成功打印后的
   `echo ===` 尾段）因 zsh `=` 展开规则 exit 1，属本人 shell 用法错误，无数据损失；
   其余命令（git 核对、测试、pyright、coverage、哈希与内容断言）均自身 exit 0。
   业务预期失败（typed CLI exit 1）未在本轮重放，消费既有 fresh 证据原始流并独立核哈希，
   符合任务允许的证据复用方式。
6. **快照复核**：审查结束时 `git rev-parse HEAD` 仍为
   `2643de25d6258fe2d83b527ea3823ffa3eb19bff`，`git status --short` 干净（仅本新文件在写入后
   出现）；未触碰任何既有 artifact。

## 审查方法覆盖说明

按 deepreview Review Method：先对齐 goal/plan/S1/S2 裁决合同，再以真实入口走读
`run_fins_direct_command` / `_run_direct_stream_producer` / `_run_download_job` /
`run_cn_download_stream_impl` / `CnDownloadAdapter.download` / `_failure_message` 主链路，
展开 `safe_exception_trace`、`_download_public_failure_from_exception`、`_save_typed_download_failure`、
`_integrity_abort`、`_project_cn_pipeline_summary` 等关键 helper 的
入参→条件→下游→返回/raise→副作用；核对 branch ordering（cancel → typed → generic）、
参数生效链（`reason_code` 来源→覆盖→消费点→非法值拒绝）、状态机（direct 单 RESULT、
job terminal 幂等、cancel claim、repair gate、batch pre-swap rollback）与外部协议边界
（CLI 双流、wait JSON、job record、operator 日志）。测试面判定其断言为 owner 级合同
（枚举全集、逐字文案、顺序、脱敏负向断言），未发现测试固化残余缺陷为期望行为。
