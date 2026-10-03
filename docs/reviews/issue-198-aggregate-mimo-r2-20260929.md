# Code Review

RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]
CANARY=mimo-1b9eff68

issue #198 整项 aggregate deepreview 的**修复性重试**（label `issue198-aggregate-mimo-r2-20260929-01`）。
前轮 `issue198-aggregate-mimo-20260929-01` 内容审查完成但一条复合 shell 命令以 exit 1 结束，
严格协议判 `agent_status=failed`，不能计 gate；本轮按同 provider 修复性重试要求**独立重做**整项
审查与验证，不把前轮内容直接充当本轮结论。本 review 只产出本文件，未修改任何生产代码、测试、
README、旧 review 或 gate artifact，未 commit、push、PR、merge、对外发消息或派发子 Agent。

## Scope

- Mode: current changes（Gateflow aggregate deepreview gate：issue 增量 `9735800c…HEAD` 恰 3 个提交）
- Branch or PR: 工作树 HEAD `2643de25d6258fe2d83b527ea3823ffa3eb19bff`；目标 draft PR #197
  （`codex/upload-material-oracle` → `main`），远端旧 head `9735800cb55a40336469593fa2fddae43c9c69ad`
- Base: 三个提交的共同父提交 `8d8d494fbbce0052372fb1b42097c9f7222cfa28`
- Output file: `docs/reviews/issue-198-aggregate-mimo-r2-20260929.md`
- Included scope: 三个提交引入的全部 56 个文件（`git diff --stat 8d8d494f..HEAD`：
  **56 files changed, 6246 insertions(+), 88 deletions(-)**，本轮独立复算一致），含：
  - 生产代码（10 文件 +562/-56）：`dayu/fins/ingestion_runtime.py`、`dayu/fins/direct_events.py`、
    `dayu/fins/pipelines/cn_download_workflow.py`、`dayu/fins/pipelines/cn_pipeline.py`、
    `dayu/service/fins_wait_adapter.py`、`dayu/cli/output.py`、`dayu/cli/commands/fins.py`、
    `dayu/runtime/log.py`，及根 `README.md`、`dayu/fins/README.md`
  - 测试：`tests/runtime/test_log.py`、`tests/fins/test_fins_ingestion_runtime.py`、
    `tests/fins/test_cn_download_workflow.py`、`tests/fins/test_cn_download_runtime.py`、
    `tests/cli/test_output.py`、`tests/cli/test_fins_commands.py`、
    `tests/service/test_fins_wait_adapter.py`（`tests/service/test_fins_direct.py` 仅回归验证、无改动）
  - gateflow/review artifact：goal、plan（10 次 fix 记录）、S1/S2 implementation、
    code review adjudication、S2 fresh/replay CLI 证据、S1/S2 各轮 review artifact、
    `tests/README.md`
- Excluded scope:
  - 远端旧 head `9735800c…` 相对 merge-base 的远端独有提交（UM-O03/UM-O20、fins 点号元数据
    deepreview 等）及其逆向差异：不属 issue #198 增量；`tests/fins/test_fins_storage_atomicity.py`
    在 tree-to-tree diff 中的 426 行变化来自远端侧点号元数据 WU，与 #198 三提交无关。
  - 独立 WU 的产品语义（点号元数据忽略规则、upload material 修复、CNInfo 单日发现合同）。
- Parallel review coverage: 无。本轮由单一 reviewer 逐文件走读并独立执行验证，未派发子 Agent。

## 当前快照（current snapshot）

| 核对项 | 本轮实测 | 结论 |
| --- | --- | --- |
| `git rev-parse HEAD` | `2643de25d6258fe2d83b527ea3823ffa3eb19bff` | 与任务要求一致 |
| `git log 9735800c..HEAD` | 恰 3 个提交：`47a9cb64e63780de…`（accepted plan）、`7234d42dbaea6031…`（accept S1）、`2643de25d6258fe2…`（accept S2） | 满足「相对 PR #197 原 head 恰 3 个 #198 提交」 |
| diff 体量 | 56 files changed, 6246 insertions(+), 88 deletions(-) | 与前轮记录一致 |
| `git diff --check 8d8d494f..HEAD` | 真实退出码 0（Python subprocess 直取），无空白错误 | 通过 |
| Python 导入树 | `dayu` 及 9 个涉改模块全部导入成功，`dayu.__file__` 指向本 worktree `/private/tmp/dayu-issue198-aggregate-mimo-r2/dayu/__init__.py` | 停止条件不触发 |
| 工作树状态 | 仅 `?? docs/reviews/issue-198-aggregate-mimo-20260929.md`（前轮 artifact，未触碰） | 干净 |

## Findings

未发现实质性问题。

本轮按 deepreview 方法对 S1+S2 组合独立走读真实调用链（以下位置均为本轮实际打开核对的行号），
七条关键闭环沿同一逻辑/数据路径直接验证成立：

1. **storage typed `unsafe_publication` 全链路保真**：`dayu/fins/storage/source_integrity.py:182`
   四值封闭 `SourceIntegrityPreflightReason` → `ingestion_runtime.py:6910` 唯一映射表
   `_SOURCE_INTEGRITY_PUBLIC_REASONS`（4 键 4 值，与两侧 enum 全集一一对应）→
   `ingestion_runtime.py:6918 _download_exception_cause` 单点 unwrap 私有
   `FinsSourceDownloadAdapterFailure`（`ingestion_runtime.py:588`，构造器 `TypeError`
   拒绝非封闭 cause）→ `ingestion_runtime.py:6934 _download_public_failure_from_exception`
   唯一映射点（`SourceIntegrityPreflightError` → `FinsPublicFailure(kind=STORAGE,
   transport=None, reason_code=…)`, 6975-6983）→ public `reason_code` 经
   `direct_events.py:273 to_json_value()` 输出 enum `.value`、CLI `output.py:488`
   取同一 `.value`（None → `"-"`）、wait JSON 同帧 `failure.reason_code`、job 安全 message 同源。
   `direct_events.py` 不 import `dayu.fins.storage`（import 表核对），公共 enum 独立；
   无消费者从字符串、行、日志或事件顺序反推公开码。
2. **部分发布守恒与 rollback/repair 状态**：`cn_download_workflow.py:344-369` 单 filing
   Phase A/B typed → 当前候选一行私有 `source_integrity_preflight` 失败 + `FILING_FAILED`
   + `CnDownloadIntegrityAbort`（`_integrity_abort` 521-568 只从已处理 `filings` 真源冻结
   快照）；post-repair 分类块 395-415 的 catch 同时覆盖 classifier typed 与显式
   `SourceIntegrityRevisionConflictError`（401-402）；company `_publish_cn_company_after_repair`
   pre-swap typed 在 422-441 以同一快照收口；循环前 whole-kind（260-264）与 company（282-289）
   typed 裸透传不伪造 filing 行，direct/job 用 `_empty_download_summary_from_request(
   …, terminal_disposition=FAILED)` 零候选摘要（`ingestion_runtime.py:4345-4355、5028-5034`）；
   `CnDownloadCancelledError` 先于 typed catch（340-343、443-445）保留取消控制流；
   mid-filing `SourceIntegrityRevisionConflictError` 走宽 `except Exception`（370-390）继续
   循环，残余归属 `fins-download-storage-sibling-errors`（已登记）。`cn_pipeline.py:1387-1393`
   仅 adapter 边界捕获私有 abort，经 `_summary_from_integrity_abort`（1450-1474，严格拒绝
   非 `integrity_failed` status）复用唯一纯投影 `_project_cn_pipeline_summary`，再抛
   `FinsSourceDownloadAdapterFailure(exc.cause, persisted_summary)`；正常入口
   `_summary_from_pipeline_result`（1423-1447）仍只接受 `ok/cancelled`。
3. **未知 download 安全类型指纹与包内帧**：`dayu/runtime/log.py:91 safe_exception_trace`
   只输出 `vars(builtins).get(name) is ancestor` 身份证实的内建祖先（115-143）、自定义类型
   `module\0qualname` SHA-256 前 16 hex 指纹（不输出原名，元数据失败回 `redacted`）、受信
   `dayu.*` 帧（`sys.modules` 字典同一 + `__file__`/`co_filename` 严格解析同一 + 位于调用方
   包根 + 合法标识符相对 `.py` 路径 + 正整数行号，146-180）或 `[external]`/`[unavailable]`，
   `deque(maxlen=16)` + `truncated` 标志；整体 `except Exception` 返回固定安全串（110-112）。
   producer 传 `ingestion_runtime.py` 的 `parent.parent`（= `dayu`），CLI 外层传
   `fins.py` 的 `parent.parent.parent`（= `dayu`），均不 import 反向层。
4. **RESULT→安全 ERROR 顺序**：`_run_direct_stream_producer`（4337-4384）先 `_emit_direct_result`
   再仅对 `EXECUTION` 公共失败记一次 `fins.download.unexpected_failure`（4378-4382）；
   测试 `tests/fins/test_fins_ingestion_runtime.py:6196-6212` 在 logger 调用内断言 RESULT spy
   已计 1；CLI 外层事件名 `fins.download.command_unexpected_failure`（`fins.py:217-221`）与
   producer 事件名分流，producer 已收口的失败不进入 CLI except 链，无重复记录。
5. **typed / no-source / 非 download 不误记**：typed 四值与 OSError 走 STORAGE 分类
   （`ingestion_runtime.py:7188-7191`），仅 `EXECUTION` 记 unknown 诊断；
   `test_direct_download_preserves_every_preflight_reason`（6259-6304）断言 caplog 无
   `fins.download.unexpected_failure`；无来源文档是非异常 RESULT 路径不伪造 unknown 诊断；
   非 download 外层保留 `_LOGGER.exception` raw traceback 与逐字固定文案
   `dayu-cli {command}: 命令执行失败，请使用 --log-file PATH 重试并查看日志`
   （`fins.py:224` 由 `output.py:69 CLI_LOG_LOCATION_HINT` 唯一常量拼接，退役
   `_FINS_DIRECT_UNKNOWN_FAILURE_MESSAGE`；专测逐字断言 `test_fins_commands.py:91、3200`）。
6. **Service / JSON / 日志 / README 同一语义**：`output.py:478-501` 失败详情 `reason_code=` 与
   `to_json_value()["reason_code"]` 同取公共 enum `.value`，文档行 `reason=`（472）保持自由
   文本旧语义；`fins_wait_adapter.py:592-623` 失败帧固定字段 `scope_note`（私有命名常量
   `_DOWNLOAD_FAILURE_SCOPE_MESSAGE`，逐字「下载摘要只统计已处理文档；整体下载操作失败，
   请按失败原因和处理建议处理。」）与 `failure`（含 `reason_code`/`retry_hint`）、
   `download` 同帧，缺 download 的 typed 失败帧 `ValueError` 拒绝（609-610）；测试
   `test_fins_wait_adapter.py:505、534` 用独立字面预期逐字断言。`CLI_LOG_LOCATION_HINT`
   常量唯一位于 `output.py`（grep 全 `dayu/` 核对）。
7. **S1+S2 组合隐私**：未知异常 message/cause 含 URL、token、绝对路径的场景由
   `tests/runtime/test_log.py` 与 producer/CLI 测试断言不进入日志、stderr、RESULT、job record
   或 wait JSON；typed job 二次保存 WARN 仅固定事件标识 `fins.download.typed_failed_record_save_failed`
   （`ingestion_runtime.py:5041`，测试 `test_fins_ingestion_runtime.py:6525` 逐字断言消息体，
   无 `exc_info`/类名/路径）。

`FinsPublicFailure.__post_init__`（`direct_events.py:251-255`）拒绝非 enum `reason_code` 与
非 STORAGE/带 transport 的组合；`FinsResultSummary.__post_init__`（631-690）的 #198 diff
仅把「FAILURE+download 必须 FAILED disposition」放宽为「禁止 CANCELLED disposition」
（678-682），成功/取消自身约束未动，与 fix4/fix6 裁决合同一致。逐项对抗审查（失败模式、
状态机各路径、参数生效链、branch ordering、overcoupling、semantic ownership drift、
LLM-facing 文本）未发现可由同一逻辑/数据路径直接证据支撑的实质缺陷。边界观察已归入
Residual Risk 并带 owner。

## 前轮协议失败复盘与隐藏 finding 核查

前轮唯一失败命令为覆盖率复合命令尾段的 `echo ===`（分隔 echo）。本轮专项核查结论：
**该失败命令没有隐藏任何 code finding**，证据链如下（均为本轮实际执行）：

1. **失败机制复现为纯 shell 词法层**：Python wrapper 内 `zsh -c "echo ==="` → 真实退出码 1、
   stderr 逐字 `zsh:1: == not found`。zsh 默认 EQUALS 展开把 `=name` 解析为命令 `name` 的
   路径，`===` 查找名为 `==` 的命令失败即 exit 1；引号包裹 `'==='` 则 exit 0。失败发生在
   zsh 词法展开阶段，命令体根本未执行，与被审代码、测试、pyright 无任何数据通路。
2. **失败前序输出完整落账、无数据丢失**：该复合命令的实质段是覆盖率报告，前轮记录其
   「输出成功打印后」尾段才失败。本轮以同口径（statement+branch、8 个 owner 生产文件 +
   含 `tests/fins/test_cn_pipeline.py` 的 owner 测试、排除 2 个 S1 已登记插桩敏感取消时序
   测试）独立复跑，8 个覆盖率数字与前轮记录**逐项完全一致**（见「本轮实际验证」§4），
   证明前轮覆盖率数据真实、完整、无截断；分隔 echo 之后本无审查数据可丢。
3. **前轮结论不依赖该命令尾段**：前轮 7 条闭环与 findings 全部由调用链走读 + 受影响测试 +
   pyright 支撑，这些验证本轮已独立重做（856 passed、pyright 0/0/0、字面断言 12/12 PASS）。
   `echo ===` 是纯格式分隔符，不产生断言输出，其 exit 1 不可能掩盖测试失败或类型错误。

另按同一失败类比对：S2 首轮 MiMo、S1 F1 首轮 MiMo 亦自报过 zsh `===`/`====` exit 1，S2 裁决
当时认定其「内容无生产 code finding」。三次同根均属 reviewer shell 用法问题，不是产品信号。

## Open Questions

- 无。原「精确单日 CNInfo 筛选 0 候选」验证缺口已终裁为独立 WU
  `fins-cninfo-single-day-discovery-window`（provider 列表行为，非 #198 代码缺陷）；
  fresh 三日窗口真实发布→typed 失败→恢复证据本轮已独立复核原始流哈希与字面断言（见验证 §5），
  不再是本 issue 的阻断问号。storage 异常构造器无 runtime enum 校验维持
  `deferred-with-owner` 至 `fins-direct-projection-failsafe`（S1 裁决原分类）。

## Residual Risk

每项均为已登记分类，无未分类残余；owner 按语义真源标注（分类与前轮一致，本轮逐项复核
owner 归属仍成立）：

| 残余 | 分类 | owner / 去向 |
| --- | --- | --- |
| 泛异常 / precommit ValueError、OSError / post-commit release / physical swap+rollback 双失败后已确认文档可能退回零摘要（明确缺陷，非正确行为） | `assigned to later work unit`：`fins-download-indeterminate-publication-state` | storage batch owner 先给 typed terminal publication certainty，再由 Fins result/job/LLM 投影 owner 表达 |
| `SourceIntegrityRepairBlockedError` / mid-filing `SourceIntegrityRevisionConflictError` 仍落 EXECUTION、`reason_code=None`，retry 提示可能误导重试（安全诊断事件按 S2 合同属预期） | `assigned to later work unit`：`fins-download-storage-sibling-errors` | Fins download 公共分类 owner；不得私造公开 reason |
| 二次投影失败（RESULT 构造、typed job catch 的 failure/summary 构造、logger handler 再抛）仍可能经 `threading.excepthook` 泄出原始 traceback；typed job catch 的不逃逸承诺仅覆盖读取/保存一步（与 plan 合同一致） | `assigned to later work unit`：`fins-direct-projection-failsafe` | Fins runtime 投影 owner；连同 storage 异常构造器 runtime 校验一并审查 |
| 非 download 外层 raw traceback 日志；generic job `_save_failed_from_exception` 把 `str(exc)` 写入 failure record 及其 Service/LLM 投影；既有二次保存 WARN 的 `exc_info=True` | `assigned to later work unit`：`fins-other-raw-diagnostics-audit` | Fins 诊断审计 owner |
| 无来源文档 Fins 公共 `retry_hint` 在默认临时日志模式下指向退出后不可查日志 | `assigned to later work unit`：`fins-download-no-source-retry-hint` | Fins 公共 hint owner（Service/JSON 路径） |
| 后台 job failed record 只持久化安全 message，不持久化 `reason_code`/`kind`（direct RESULT 与 wait JSON 均带 `reason_code`；plan 合同只承诺 safe message + 同源摘要） | `assigned to later work unit`：`fins-download-job-reason-code-persistence` | Fins job record schema owner |
| SEC/其它来源 typed 中止仍可能丢已处理文档行投成零摘要 | `assigned to later work unit`：`fins-download-other-source-summary-conservation` | SEC/其它 workflow 收口 owner（plan OQ4/F5） |
| CNInfo 精确单日窗口 `2025-03-28…28` 与本地日 `03-29` 均 0 候选，accepted plan 单日 baseline recipe 未按原命令通过（三日窗口替代证据已核） | `assigned to later work unit`：`fins-cninfo-single-day-discovery-window` | CNInfo discovery owner |
| 奇异安装布局可能令全部受信帧降级 `[external]`（有界脱敏取舍） | `tracked in closeout`（S2 记录） | 跨布局诊断退化留 closeout |
| coverage 插桩下取消时序测试敏感（见下方本轮新增观察） | `tracked`（S1 记录，本轮扩展观察） | 插桩敏感性另查，非 #198 语义 |
| 点号元数据忽略规则 / 点号测试 / README 相邻句 | 独立 WU（远端侧已落 UM 系列提交） | 不计入 #198 |

**本轮新增观察（扩展现有 `tracked` 插桩敏感项，非 #198 finding）**：覆盖率插桩的 9 文件
组合运行中，2 个**前 WU（`bd1d3e94` / PR #179）既有**取消时序测试稳定失败——
`tests/cli/test_fins_commands.py::test_cli_stream_owner_external_cancellation_closes_once_with_cleanup_cause`
与 `::test_cli_event_task_drain_deduplicates_same_primary_close_cause`（组合运行 2 次均
复现；失败面是测试 fake generator 在取消注入与 `aclose()` 两种交错下的 `cancellation_observed`
状态差，泄漏的是 fake 注入的 `close_error`）。二者在普通套件（856/892 passed）与
**单文件插桩运行**（156 passed）下均通过。#198 对 `fins.py` 的改动仅外层 catch 分流，
未触碰 stream owner 取消清理路径，故非 #198 语义缺陷；其交错差异是产品契约缺口还是测试
时序假设，归既有「插桩敏感性另查」一并判定。注意：前轮 aggregate 报告称插桩下「其余全绿」，
本轮组合插桩运行**不能复现该说法**（如实登记，见验证 §4）。

## 验证（本轮实际执行）

工作区 `/private/tmp/dayu-issue198-aggregate-mimo-r2`，`.venv` Python 3.11.15，全部在 HEAD
`2643de25d6258fe2d83b527ea3823ffa3eb19bff` 快照执行。以下为本轮真实命令与真实退出码；
预期无匹配/非零探针一律经 Python subprocess 捕获、打印真实退出码、wrapper 自身 exit 0：

1. **快照与导入树**：`git rev-parse HEAD` exit 0；`git log --format=%H 9735800c..HEAD` exit 0
   恰 3 个全 SHA；`.venv/bin/python -c "import dayu, …"` exit 0（9 模块导入 OK、
   `dayu.__file__` 指向本 worktree）；`git status --short` exit 0（仅前轮 artifact 一个
   untracked）；`git diff --check 8d8d494f..HEAD` 真实退出码 0。
2. **受影响测试（plan 八文件）**：`python -m pytest tests/runtime/test_log.py
   tests/fins/test_fins_ingestion_runtime.py tests/fins/test_cn_download_workflow.py
   tests/fins/test_cn_download_runtime.py tests/cli/test_output.py
   tests/cli/test_fins_commands.py tests/service/test_fins_wait_adapter.py
   tests/service/test_fins_direct.py -q` → exit 0，**856 passed**，3 条第三方 edgartools
   deprecation warning。与前轮/ S2 记录一致。
3. **扩展九文件普通套件**（加 `tests/fins/test_cn_pipeline.py`，不插桩、不 deselect）→
   exit 0，**892 passed**。
4. **全量 pyright**：`python -m pyright dayu/ tests/ utils/` → exit 0，
   **0 errors, 0 warnings, 0 informations**。
5. **覆盖率（statement+branch，8 owner 生产文件，owner 测试含 `test_cn_pipeline.py`，
   排除 S1 已登记 2 个插桩敏感取消时序测试）**：8 文件覆盖率与前轮记录**逐项一致**——
   `fins.py` 80%、`output.py` 82%、`direct_events.py` 85%、`ingestion_runtime.py` 88%、
   `cn_download_workflow.py` 92%、`cn_pipeline.py` 92%、`log.py` 92%、
   `fins_wait_adapter.py` 92%，均 ≥80%。**如实登记差异**：插桩下 pytest 真实退出码 1
   （2 failed, 888 passed, 2 deselected，即 Residual 的 2 个 #179 既有取消时序用例；
   组合运行两次复现一致），并非前轮所述「其余全绿」。后续 Python wrapper 复核：
   该 2 用例单文件插桩运行（156 passed）与仅这 2 用例插桩运行（2 passed ×2）真实退出码均为 0；
   失败 traceback 显示为 fake harness 在取消注入/`aclose()` 交错下的状态差（见 Residual）。
   首次覆盖率命令的 wrapper 因管道尾 `tail` 使 shell 退出码为 0，其内层 pytest 实为 exit 1，
   此处按真实情况登记，不计「本轮通过」。
6. **S2 fresh CLI 原始证据独立复核**（证据快照 `/private/tmp/issue198-cli-wide2-9aklx640`
   仍在；首轮一次 `isdir` 探针误报 MISSING，复查为探针异常，目录 11 项完整）：
   - 8 份原始流逐字节复算 SHA-256 与字节数**逐项一致**：`baseline.stdout` 35262/`23c41eda…`、
     `baseline.stderr` 0/`e3b0c442…`、`baseline.log` 1842/`3d31052a…`、`typed.stdout` 208/`0804026d…`、
     `typed.stderr` 508/`dc00b1c4…`、`typed.log` 168/`93e88e89…`、`recovery.stdout` 862/`1e5f1a46…`、
     `recovery.stderr` 0/`e3b0c442…`。
   - 发布产物哈希一致：PDF `b17a9b9b…`、Docling JSON `bf98154f…`。
   - 独立 Python 字面断言 12 条全 PASS：typed.stderr 含 `classification="storage"`、
     `reason_code="unsafe_publication"`、修复提示；无 `--log-file` 提示、无 `Traceback`、
     无外来 basename、无盲目重试文案；typed.log 无两种 `fins.download.*` 事件、无 `Traceback`；
     typed.stdout 无失败详情；recovery 摘要 `discovered=1 downloaded=0 skipped=1`。
   - typed.stderr 实测形状为请求级零候选摘要 + 安全 failure detail，与 whole-kind typed 合同
     一致。业务预期失败（typed CLI exit 1）本轮未重放，按任务允许复用既有 fresh 证据原始流
     并独立核哈希。
7. **前轮失败命令机制复现**：Python wrapper 内 `zsh -c "echo ==="` → 真实 exit 1、stderr
   `zsh:1: == not found`；`echo '==='` → exit 0。wrapper 自身 exit 0。
8. **shell 命令执行记录（如实登记）**：本轮所有 shell 命令自身 exit 0；内层真实非零退出码
   （§5 插桩 pytest exit 1、§7 zsh 探针 exit 1）均经 Python 捕获并如实打印。无未捕获失败，
   无 `echo ===` 式裸 `=`/`===`/glob 用法（唯一 `=` 出现在已引号包裹的 Python 字符串内）。

## 审查方法覆盖说明

先对齐 goal/plan（含 10 次 fix 现行合同）/S1/S2 implementation 与 adjudication/S2 fresh 与
replay 证据/前轮 aggregate review，再以真实入口独立走读 `run_fins_direct_command` /
`_run_direct_stream_producer` / `_run_download_job` / `_save_typed_download_failure` /
`run_cn_download_stream_impl` / `CnDownloadAdapter.download` / `_summary_from_integrity_abort` /
`_failure_message` 主链路，展开 `safe_exception_trace`、`_download_public_failure_from_exception`、
`_download_exception_cause`、`_integrity_abort`、`_project_cn_pipeline_summary` 等关键 helper
的入参→条件→下游→返回/raise→副作用；核对 branch ordering（cancel → typed → generic）、
参数生效链（`reason_code` 来源→唯一映射→JSON/CLI/wait/job 消费点→非法值拒绝）、状态机
（direct 单 RESULT、job terminal 幂等、cancel claim、repair gate、batch pre-swap rollback）
与外部协议边界（CLI 双流、wait JSON、job record、operator 日志）。测试面判定其断言为
owner 级合同（枚举双向全集、逐字文案、RESULT-before-log 顺序、脱敏负向断言），未发现测试
固化残余缺陷为期望行为。与前轮结论的差异仅一处：coverage 插桩组合运行的「其余全绿」不可
复现（见 Residual 新增观察），已如实登记并归入既有插桩敏感跟踪，不构成 #198 代码 finding。
