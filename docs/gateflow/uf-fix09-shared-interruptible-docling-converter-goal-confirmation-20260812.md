# UF-FIX09 shared-interruptible-docling-converter Goal Confirmation

## Gate

- Gate：goal confirmation
- Work unit：`UF-FIX09 shared-interruptible-docling-converter`
- Branch：`codex/upload-filing-oracle`
- Baseline HEAD：`3f24d75adba49868fbc8646ac9c81f5a0a4a3c2e`
- Decision：`confirmed-by-user`
- Current gate / next entry point：`plan`

## Git preflight

- 当前分支、HEAD 与用户给定预期一致；当前分支不是 protected trunk。
- 初始工作树 clean；无 merge、rebase、cherry-pick、revert、bisect 或 sequencer 状态。
- 本地 `main`、远端 `github/main` 与 merge-base 均为 `256786b255021ee429a20f22aad726b1ad33916c`；已使用仅允许 fast-forward 的 `git fetch github main:main` 核验更新。
- 当前分支只比 `main` 多独立 oracle commit `3f24d75a`，不存在需要策略裁决的分叉。

## 第一性原理判断与直接证据

本 work unit 成立，且严重性评估准确。问题不是 CLI 单纯“响应慢”，而是同一业务转换事实存在两套生命周期实现，上传路径还把取消观察放在不可中断同步转换之后：

1. 冻结报告 SHA-256 已复核为 `e2d3b58954576a2aa1cec3cbc3809134ad34c81d5147df778cef82e7173232c3`。UF-L02 的 HK PDF 在 SIGINT 后总耗时 `31.780388s`，UF-L04 的 US DOCX 为 `21.564391s`；两者都先输出 `upload.completed`，随后才输出 cancelled/exit 130。取消后未发布 source，同 workspace 原样重试分别成功。
2. `DoclingUploadService._build_pending_assets` 在 producer thread 内同步调用 `_convert_with_docling`；转换期间只在调用前后检查 `UploadCancellationChecker`，不能把 token 传播给 Docling 工作。
3. `FinsIngestionRuntime._produce_direct_upload` 在 `run_upload` 返回后无条件先投影 `_upload_completed_progress_type(summary)`，随后才检查 `context.cancellation_checker()`；`cancelled` summary 又被该 helper 归为 `upload.completed`，直接解释了冻结屏幕顺序。
4. download 的 `ProcessCnDoclingConversionRunner` 已经用 `InterruptibleProcessHandle` 实现 poll、terminate grace、kill grace、close、临时目录删除与输出 size/digest 校验；测试直接覆盖忽略 terminate 后升级 kill、POSIX nested process group 清理和 very-early cancel。
5. download 与 upload 仍各自持有 runner/config/error/output 逻辑：前者只支持 PDF 并返回 bytes，后者同步返回 `JsonObject`；grace/kill/cleanup 语义无法由其它 Fins caller 复用。

因此 root cause 是 Fins Docling conversion 缺少唯一 process-level semantic owner，导致 upload 只复用了同步 converter construction，却没有复用 download 已证明有效的可中断进程生命周期；完成进度又在 direct-stream terminal/publication 仲裁之前提前投影。

## 正确 semantic owner 与依赖方向

- `dayu.runtime.interruptible_process` 继续只拥有层中立的 spawn、独立 process session/group、IPC、wait/poll、terminate、kill、join/reap、queue close 与 cleanup primitive；不得 import Docling、Fins、Host、Engine、Service 或 UI。
- 唯一共享的 Fins Docling process conversion owner 必须位于 `dayu.fins`。它拥有 immutable input bytes、stream/file name、转换配置、child 内 converter construction、Docling JSON 序列化、typed success/failure/cancel outcome、IPC descriptor 校验与对 runtime primitive 的调用策略。
- download CN/HK 与 filing/material upload 只保留有真实市场/业务语义的 workflow adapter；不得保留两套 process runner 或纯透传兼容 facade。
- `FinsIngestionRuntime` 继续拥有 direct stream 的取消/terminal first-committer 仲裁与用户可见 progress/result 投影；storage batch owner 继续拥有 source publication commit。
- Host/Engine 不参与 direct `upload_filing` 生命周期；不创建或伪造 Run、Attempt、EventLog、Memory、Tool Trace 或 runtime SQLite。

## 目标与 scope boundary

目标是建立一个共享、typed、可协作中断的 Fins Docling converter，并迁移：

- CN/HK download 的 PDF -> Docling JSON；
- US/CN/HK `upload_filing`；
- US/CN/HK `upload_material`；
- 当前与上述调用链共享 Docling conversion contract 的 Fins caller。

当前 call-site inventory 的边界结论：

- `dayu.fins.pipelines.cn_docling_process`：本轮必须迁移、删除或重命名，不能作为 download-specific runner 保留。
- `dayu.fins.pipelines.docling_upload_service`：本轮必须迁移到共享 process owner，filing/material 两条路径因此同时覆盖。
- `dayu.documents.docling_runtime`：仍是 child 内可复用的 Docling converter construction/backend fallback helper，不拥有 Fins process/cancel/publication 语义。
- `dayu.tools.web.web_fetch_orchestrator`：直接调用 `dayu.documents.docling_runtime` 将 PDF/非 HTML 内容导出 Markdown，既不属于 Fins storage/publication，也不能反向依赖 `dayu.fins`；本轮只登记为不适用 caller，不迁移。
- process/read 路径通过 `FinsDoclingProcessor` / `DoclingProcessor` 读取已发布的 `*_docling.json`，没有创建或调用 Docling converter；没有本轮迁移对象。

## 取消、转换返回与 publication commit boundary

本轮必须冻结如下 first-committer 语义：

1. cancellation 在 source publication commit 开始前胜出：共享 converter 终止整个 child process group，完成 terminate→bounded grace→必要时 kill→join/reap/IPC close/temp cleanup；workflow 不开始或回滚 publication，direct stream 只提交 canonical cancelled terminal，不投影 `upload.completed`。
2. conversion 正常返回但 publication 尚未 commit：仍需在 storage commit 前由同一 cancellation/terminal owner 做确定性检查；取消胜出则不发布。
3. storage 原子 commit 已开始并成功：该 source fact 已提交，迟到取消不得回滚或把已发布成功伪装成 cancelled；success terminal/progress 从同一已提交结果投影。
4. converter error、serialization/IPC error、child crash、外层异常与 shutdown 都必须走 typed failure/cleanup 路径；不得用 UI 过滤、字符串特例、fallback 或 loose parsing 修正终态。

## 成功信号

1. download、upload_filing、upload_material 共享同一 Fins process conversion owner；没有重复 grace/kill 常量、cleanup 状态机或无语义 wrapper。
2. HK PDF 与 US DOCX 实际转换中一次 SIGINT 后，token 被观察，整个 process group 有界清理，CLI exit 130；无 `upload.completed`、无 source publication、无 worker/子孙进程/IPC/temp/staging/backup/lock residue，原 argv/workspace 可重试成功。
3. conversion-return/cancel/publication-commit race 有 deterministic owner-level test；已提交 publication 不被迟到取消改写。
4. download 的正常转换、fallback、cancel、nested process group cleanup 和重试不回归。
5. 普通成功路径的输入 bytes、Docling JSON、meta/manifest/digest 与 downstream process/read 消费不漂移。
6. direct upload 保持无 Host durable lifecycle；focused-real UF-PF09 保存 queried-absent proof。

## 预计受影响模块

- 共享 owner：`dayu/fins/pipelines/` 下新增或由 `cn_docling_process.py` 重命名后的 Docling process conversion 模块。
- 迁移调用方：`dayu/fins/pipelines/cn_download_filing_workflow.py`、`dayu/fins/pipelines/docling_upload_service.py`，以及必要的 CN/SEC pipeline composition/runtime 装配。
- commit/terminal 投影：`dayu/fins/ingestion_runtime.py`、必要时 `dayu/fins/service_runtime.py`，只在其现有 owner boundary 内改动。
- tests：runtime process primitive 回归、共享 Fins converter owner、CN download、Docling upload service/integration、CN/SEC filing/material pipeline、ingestion runtime 与 CLI SIGINT/race tests。
- docs：实现后按 README 自身约束检查 `dayu/fins/README.md`、`tests/README.md`、根 `README.md` 与 `dayu/README.md`；当前不预判机械更新。

## 非目标

不处理 UF-O09、UF-O10、格式/help 漂移、XBRL companion、multi-file primary/collision、renamed update、delete 后 auto、existing source auto repair、计数、company meta refresh、并发、其它 upload_filing 修复、Host cancel 状态机、Engine event/schema、ToolAwaiting、schema migration、旧接口兼容或 137 条 full-real matrix。review 命中这些内容时只能归为 `assigned to later work unit`。

## 为什么不是过度设计

系统已经有生产级层中立 process primitive 和一套 download-specific Fins runner；本轮不是新增 supervisor/framework，而是把既存重复业务 runner 收敛到一个 Fins owner，并把 upload 接到同一条已验证 cleanup state machine。迁移范围只覆盖真实共享相同 Docling JSON conversion contract 的 Fins caller；Web Markdown extraction 和 JSON reader 被明确排除，避免为了“全局统一”制造反向依赖。

## Agent 初始化与 blocking open questions

- `$init-agents` pane discovery 已确认：AgentMiMo=`ai-0:1.1`、AgentCodex=`ai-0:1.4`、AgentDS=`ai-0:1.5`；用户指定的 CLI 类型覆盖 skill 默认表，MiMo/DS 按 Claude Code `/planreview`、`/deepreview`，Codex 按 Codex Agent 任务文本执行。
- 尚未向任何 Agent 发送任务；每个新 gate/slice 会重新 discovery，单独 `/clear`、wait idle、capture，再发送正式任务并 wait/capture。
- Blocking open questions：无。
- 用户已明确确认 goal confirmation；不存在当前 stop condition。

## Validation 与 residual risks

- 已验证 Git preflight、冻结 report SHA、oracle/scenario 中 UF-FIX09/UF-PF09、关键生产 call path、现有 cancellation/process cleanup tests 与 direct-stream terminal owner。
- 当前未运行测试或 pyright，因为尚未进入 implementation。
- residual risk：共享 converter 的最终同步/异步 public shape、错误联合和 slice 划分需要在 plan gate 由 AgentCodex基于上述冻结 owner/commit boundary细化；分类为 `covered by later approved slice`，不构成 goal-confirmation blocker。
- Completion status：`confirmed`。
- Artifact path：`docs/gateflow/uf-fix09-shared-interruptible-docling-converter-goal-confirmation-20260812.md`
