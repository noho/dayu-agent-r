# UF-FIX09 local-only final closeout

## Gate 元数据

- gate：`final closeout`
- work unit：`UF-FIX09 shared-interruptible-docling-converter`
- branch：`codex/upload-filing-oracle`
- accepted implementation/deepreview target：`94600b641bf977b164d50908540e08e2acaebc98`
- execution mode：`local-only-by-explicit-user-instruction`
- completed at：`2026-08-13T08:31:00+08:00`
- completion status：`PASS`
- artifact：`docs/gateflow/uf-fix09-final-closeout-20260813.md`

## Root cause 与唯一 owner

直接证据表明，旧 upload 路径在当前线程同步执行 Docling，只能在转换返回后再次观察取消；
因此 HK PDF 与 US DOCX 收到 SIGINT 后仍等待自然转换结束，并可能先投影
`upload.completed`、再投影 cancelled。旧 download 已使用 interruptible process primitive，
但 Docling-specific process runner 仍由 download 私有持有，形成 download/upload 两套生命周期。

修复后的唯一 Docling conversion owner 是
`dayu.fins.pipelines.docling_process_converter.ProcessDoclingConverter`：它拥有不可变输入 bytes、
child 内 converter construction、闭合配置、typed result/error、exact IPC descriptor、poll、
cancel observation 与 Docling cleanup phase；`dayu.runtime.interruptible_process` 继续只拥有层中立的
process/process-group terminate、grace、kill、join/reap、IPC close 与 cleanup primitive。
storage publication 仍由 Fins workflow/batch owner 提交；direct/durable terminal 只从同一 typed
publication summary 做 first-committer 投影，不由 CLI 或 UI 重解释。

## 修改结果

- 新增共享 `ProcessDoclingConverter`，每次调用独立创建 handle、temp 与 IPC，shared instance 不持有
  operation mutable state；正常结果携带同源 UTF-8 JSON bytes、size 与 SHA-256。
- 删除 `dayu/fins/pipelines/cn_docling_process.py` 及 download-specific runner，不保留兼容 re-export、
  透传 facade 或旧常量。
- `DefaultFinsRuntime` 只构造一个 converter instance，并注入 download CN/HK、upload_filing CN/HK、
  upload_filing SEC、upload_material CN/HK 与 upload_material SEC 路径；standalone CN/SEC pipeline
  也默认构造同一 concrete owner 类型。
- upload service/workflow 以 canonical `CancellationToken` 贯穿 conversion 与最后 publication
  checkpoint；publication 前取消胜出则 rollback 且返回 cancelled，commit/no-op/failed summary
  已接受后迟到取消不回滚、不改写 terminal。
- direct stream 在 operation lock 内只 claim 一次 prepared terminal event group；durable job store 在
  file lock 内 atomic first-commit terminal record，再从 accepted record 投影 progress/event。
  cancelled 不生成 completed，failed/completed/cancelled 均只有一个 canonical terminal。
- converter construction、execution、serialization、IPC、child crash、取消、外层 task cancel、
  terminate/kill/close/temp cleanup 均有闭合 outcome/exception 与 cleanup path。

## Caller inventory 与迁移状态

| Caller | 状态 | 共享 owner / 说明 |
| --- | --- | --- |
| CN/HK download Docling | migrated | `CnPipeline` 注入同一 `ProcessDoclingConverter` |
| CN/HK upload_filing | migrated | `DoclingUploadService` 直接消费 typed converter result |
| SEC upload_filing | migrated | `SecPipeline` 注入同一 converter |
| CN/HK upload_material | migrated | 与 filing 共用 `DoclingUploadService` |
| SEC upload_material | migrated | 与 filing 共用 `DoclingUploadService` |
| process/read 已发布 Docling JSON | not a converter caller | 只消费仓储已发布 JSON；读取一致性回归已通过 |
| `dayu.tools.web.web_fetch_orchestrator` | assigned to later work unit | 非 Fins caller、无 Fins cancellation token，不能反向依赖 Fins owner |

仓库扫描确认旧 runner/旧 upload conversion seam 零残留；Fins 内 concrete construction 只指向
`ProcessDoclingConverter`。

## Local Gateflow commits

| Gate | Commit |
| --- | --- |
| accepted plan | `9527c6e0fd430082219b13daee31d300a8b44be4` |
| accepted S1 | `26e77e36d5a3340ad7f1aa75c2a538a3dd424f96` |
| accepted S2 | `87389ebc194b51343d11b7e32bf5873389298fea` |
| accepted S3 | `d40ac173fd308b3329ed7216e0c26b9951663cdc` |
| accepted aggregate deepreview | `94600b641bf977b164d50908540e08e2acaebc98` |

本 artifact 的 local-only closeout commit 由 controller 在写入后创建，其 hash 记录在最终用户报告；
不能在 commit 内容中自引用自身 hash。

## 双路 review 与 finding 状态

### Plan review

- 冻结 plan：`docs/gateflow/uf-fix09-shared-interruptible-docling-converter-plan-20260812.md`
- 初轮 AgentMiMo：`docs/reviews/plan-review-20260812154406.md`
- 初轮 AgentDS：`docs/reviews/plan-review-20260812-154453.md`
- 综合裁决：`docs/gateflow/uf-fix09-shared-interruptible-docling-converter-plan-review-adjudication-20260812.md`
- re-review AgentMiMo：`docs/reviews/plan-review-20260812-160847.md`
- re-review AgentDS：`docs/reviews/plan-review-20260812-160907.md`
- 状态：10 组 accepted findings 全部由 AgentCodex 修订并闭环；两路 pass，无 unresolved finding。

### S1 code review

- 初轮：AgentMiMo `docs/reviews/code-review-20260812-165218.md`；AgentDS
  `docs/reviews/code-review-20260812-164911.md`
- re-review：AgentMiMo `docs/reviews/code-review-20260812-170513.md`；AgentDS
  `docs/reviews/code-review-20260812-170314.md`
- 裁决：`docs/gateflow/uf-fix09-s1-code-review-adjudication-20260812.md`
- 状态：2 个 accepted owner-level test gaps 已修复；两路 pass。

### S2 code review

- 初轮：AgentMiMo `docs/reviews/code-review-20260812-174511.md`；AgentDS
  `docs/reviews/code-review-20260812-174021.md`
- re-review：AgentMiMo `docs/reviews/code-review-20260812-175731.md`；AgentDS
  `docs/reviews/code-review-20260812-175301.md`
- 裁决：`docs/gateflow/uf-fix09-s2-code-review-adjudication-20260812.md`
- 状态：重复 digest 计算 finding 已修复；terminal work 正确归 S3；callable/token transport finding
  按冻结 plan §11.1 以直接证据拒绝；两路 pass。

### S3 code review

- 初轮：AgentMiMo `docs/reviews/code-review-20260812-212813.md`；AgentDS
  `docs/reviews/code-review-20260812-212841.md`
- 中间 re-review：AgentMiMo `docs/reviews/code-review-20260812-214049.md`；AgentDS
  `docs/reviews/code-review-20260812-214805.md`
- 最终 re-review：AgentMiMo `docs/reviews/code-review-20260812-220519.md`；AgentDS
  `docs/reviews/code-review-20260812-220206.md`
- 裁决：`docs/gateflow/uf-fix09-s3-code-review-adjudication-20260812.md`
- 状态：durable projection failure test gap 与 direct claim-before-event-construction defect 均已修复；
  owner contract 外 raw overwrite 假设被拒绝；两路最终 pass。

### Aggregate deepreview

- 初轮 AgentMiMo：`docs/reviews/uf-fix09-aggregate-deepreview-20260812-221109.md`
- 初轮 AgentDS：`docs/reviews/code-review-20260812-220949.md`
- no-op fix confirmation：`docs/gateflow/uf-fix09-aggregate-fix-confirmation-20260812.md`
- re-review AgentMiMo：`docs/reviews/uf-fix09-aggregate-rereview-20260812-222742.md`
- re-review AgentDS：`docs/reviews/code-review-20260812-222603.md`
- 裁决：`docs/gateflow/uf-fix09-aggregate-deepreview-adjudication-20260812.md`
- 状态：无 material finding；partial batch rollback 与 callable/token 两项 observation 均由既有
  owner contract 直接证明为正确/重复裁决；两路 re-review pass。

所有 accepted findings 已闭环；无未分类风险、blocking question 或 requiring-user-decision finding。

## Final deterministic validation

- 影响矩阵：`525 passed, 3 warnings in 12.32s`。包含 runtime primitive、Docling runtime、共享
  converter、upload service、CN download workflow/runtime/pipeline、SEC filing/material stream、
  ingestion runtime/tools、read consistency 与 CLI commands。
- 真实 Docling integration：`1 passed in 5.96s`，环境
  `DAYU_RUN_DOCLING_UPLOAD_INTEGRATION=1`。
- full pyright：`pyright dayu tests utils` -> `0 errors, 0 warnings, 0 informations`。
- `git diff --check`：pass。
- 旧 symbol scan：zero matches。
- coverage：runtime primitive 88%；shared converter 95%；upload service 86%；CN download workflow
  86%；CN pipeline 91%；SEC upload workflow 89%；ingestion runtime 91%；service runtime 86%。
- `sec_pipeline.py` 为 40%：它不是本轮新增或显著修改 owner，只改 converter injection 边界；
  受影响 filing/material stream 行为已在 525-test matrix 中通过。该边界已在 S3/aggregate review
  明确裁决，不以无关 SEC 全模块测试扩大本 work unit。
- 测试按 `source .venv/bin/activate` 后执行；没有用 mock/fake 替代下述真实 conformance。

## UF-PF09 focused-real evidence

- accepted fresh evidence root：`/Users/leo/workspace/.dayu-cli-ci/uf-pf09-20260813-fLVZWz`
- target：`94600b641bf977b164d50908540e08e2acaebc98`
- report：`/Users/leo/workspace/.dayu-cli-ci/uf-pf09-20260813-fLVZWz/observed-behavior.md`
- report SHA-256：`4af8f01e94d99ca936fa25b4a63c24dd9df5ca8766f4abc5dabe8b5403aabe16`
- secret scan：`complete`；76 files / 37,385,882 bytes；0 hit；0 validation error；final exclusive writer。
- HK PDF SHA-256：`9092450198195a7c07db95f76c1d9f886acd25cc37b07ea3cb71179f4f85f59c`
- US DOCX SHA-256：`fbb69b891cdf391ef82d67d30cac9638047ab811aedb85f1b7befe33e4edd16f`
- scenario scope：只执行 `UF-PF09`；accepted oracle/scenario registry 未修改。

每条 cancellation 都先由 root `py-spy` 原始 stack 同时证明 shared child target、
`convert_pdf_bytes_with_docling`、`run_docling_pdf_conversion` 与
`DocumentConverter.convert` 在栈，再向 CLI foreground process group 发送一次 SIGINT：

| Case | conversion-entered | SIGINT -> exit | Exit | Retry |
| --- | ---: | ---: | ---: | --- |
| HK PDF upload | 3.337s | 0.251s | 130 | same argv/workspace exit 0，发布 original + Docling JSON + meta/manifest |
| US DOCX upload | 3.331s | 0.214s | 130 | same argv/workspace exit 0，发布 original + Docling JSON + meta/manifest |
| HK download | 11.355s | 0.257s | 130 | same argv/workspace exit 0，发布完整 download source |

三条取消均具备 exact production phase：`child_started -> cancel_observed -> terminate_started ->
terminate_completed -> kill_not_needed -> handle_close_started -> handle_close_completed ->
temp_cleanup_completed -> cancelled_terminal_ready`。均只有一个 canonical cancelled、无
`upload.completed`、无 source/manifest publication、无存活记录 PID/PGID/descendant、无 temp/IPC/
repo batch/backup/staging/ingestion-job residue，且 `lsof +D` 无活跃 workspace handle。

workspace 保留的是仓储并发协议要求的已解锁 `.lock` inode，而不是 operation/worker residue；
退出后没有进程持有这些 inode。删除持久锁 inode 会制造两个 inode 上并发 file-lock 的错误语义，
因此未把安全的闲置协调文件误判为活跃 lock residue。

三个 workspace 均查询到 SQLite、EventLog、Memory、Tool Trace path 与 durable ingestion job 缺席；
`dayu-cli tool_trace analyze` 明确返回“不包含受支持的 Tool Trace 布局”。direct command 未创建
Host Run、Attempt、EventLog、Memory、Tool Trace 或 ingestion job。

未接受的采集尝试仍保留用于 audit，但不作为 pass evidence：`...-VAhtcE` 缺 stack/phase proof；
`...-2ZnnbC` 因采样权限不足未发送信号；`...-AC6OCj` 因 sudo PATH 缺 `lsof` 中止；
`...-XmN5Ta` 的两个失败键被直接证明为 controller 监控 shell 字面量造成的 matcher 假阳性。

## README decision

- `README.md`：更新用户可见首次 Ctrl-C、publication first-commit 与 exit 130 语义。
- `dayu/fins/README.md`：更新唯一 converter owner、typed terminal disposition 与
  direct/durable first-committer。
- `tests/README.md`：更新 CLI SIGINT 与 owner race/terminal 覆盖。
- `dayu/README.md`：不更新；`UI -> Service -> Host -> Engine` 分层与装配关系未改变。
- Host/Engine/config 生产目录未修改，相应 README 不触发。

## Residual risks 与非目标 owner

| 项目 | 分类 | Owner / 后续 |
| --- | --- | --- |
| company meta 独立事务 | assigned to later work unit | company-meta refresh work unit |
| Web fetch Docling cancellation | assigned to later work unit | web/document runtime work unit；不得反向依赖 Fins |
| 非 POSIX process-group/descendant guarantee | assigned to later work unit | cross-platform runtime work unit |
| UF-O09/UF-O10、格式/help、XBRL、multi-file、renamed update、delete/repair/count/meta/concurrency 等冻结项 | assigned to later work unit | 对应 upload_filing work units |
| Host cancel state machine、Engine event/schema、ToolAwaiting、schema migration | assigned to later work unit | Host/Engine/schema owners |

无 tracked issue 被本轮修改或评论；无 requiring-user-decision residual risk。

## 外部状态与 next entry point

- push：`not-applicable-by-explicit-user-instruction`
- PR URL / draft PR / ready / reviewer / PR review：`not-applicable-by-explicit-user-instruction`
- merge / branch deletion：`not-applicable-by-explicit-user-instruction`
- external issue modification/comment：`not-applicable-by-explicit-user-instruction`
- next entry point：保留当前本地分支与 commits；后续统一 conformance refresh 可消费上述 UF-PF09
  fresh evidence/report digest，并按独立 work unit 更新 registry。当前 work unit 到达
  `local-only final closeout pass`。
