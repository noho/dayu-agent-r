# UF-FIX09 S3 Code Review 裁决

## Gate

- Gate：UF-FIX09 S3 code review
- Base：`87389ebc194b51343d11b7e32bf5873389298fea`
- 冻结 diff SHA-256：`650ee7f5fdd16a838724346e5a3989ff44f1336b203983e580e1d6b383f4b27b`
- Scope：S3 allowlist 的 6 个仓库文件；UF-PF09 fresh evidence 属 deterministic review 通过后的后续 gate
- AgentMiMo：`docs/reviews/code-review-20260812-212813.md`
- AgentDS：`docs/reviews/code-review-20260812-212841.md`

## Findings 裁决

### A1 — 接受为测试缺口：durable terminal save 后 projection 异常安全网缺少直接覆盖

- 来源：AgentDS finding 001
- Reviewer 严重度：中
- Controller 严重度：低（测试覆盖缺口，不是当前 correctness defect）
- 直接证据：`_run_upload_job` 已先原子保存 accepted terminal；后续 progress/event projection 抛异常时进入 `_save_failed_from_exception`，该 helper 读取已保存终态并拒绝覆盖。现有实现正确，但测试只覆盖 save 后 late cancel，没有直接让 projection 抛异常。
- 裁决：`fixed in current slice`。
- 修复边界：只在 `tests/fins/test_fins_ingestion_runtime.py` 增加 deterministic test；不得增加生产 hook，不得改生产语义。用现有 fake/job-store/event boundary 触发 projection 或 append 失败，断言 record 保持原 SUCCEEDED/FAILED、没有第二 terminal event、没有终态改写。
- 验证：最小测试、S3 两份完整受影响测试、plan focused matrix、pyright、格式与 diff check。

### R1 — 不接受为缺陷：cancelled save 返回已有非-cancelled winner

- 来源：AgentDS finding 002
- Reviewer 严重度：低
- 裁决：rejected；不是 residual risk。
- 理由：`save_cancelled_if_active` 名称描述的是提交请求，不承诺返回 cancelled；其公共 contract 明确“已有终态则原样返回”。调用方使用 `saved` 与 `saved_disposition` 命名，并从 atomic save 返回的最终 record 投影 progress/event，准确表达 first-committer。若并发 winner 已 completed/failed，投影 winner 正是 accepted plan 要求。增加解释性兼容分支或特殊判断会反而制造第二语义路径。

### A2 — 接受：direct upload claim 后事件构造异常可能丢失 RESULT

- 来源：AgentDS re-review `docs/reviews/code-review-20260812-214805.md` finding 001
- 严重度：中（controller 上调；属于本 S3 引入的终态可见性缺陷）
- 直接证据：`_produce_direct_upload` 先调用 `claim_upload_summary` 写入 `_terminal_status`，之后才由 `_emit_context_progress` / `_emit_claimed_direct_result` 构造并入队事件。若构造阶段因有界文本、detail 或 event contract 校验抛异常，外层 catch 再调用 `_emit_direct_result(FAILURE)`，但 `claim_terminal` 因已有 terminal 返回 `None`，stream 可能以 done 结束且没有 RESULT。
- 裁决：`fixed in current slice`。
- 理由：冻结 plan 第 10.2 节要求同一次仲裁决定 progress/result，禁止二者分裂。该窗口由 S3 的“先 claim 后构造”重排直接产生，不能分类为既有架构 later work。
- 修复边界：在 `dayu/fins/ingestion_runtime.py` 的 direct upload owner 内先用 pure typed helper 构造可见 progress/result（不入队），构造成功后再执行单次 `claim_upload_summary`，claim 成功后只按顺序调用不会抛异常的 `_put_direct_queue`。构造失败发生在 claim 前，外层既有异常路径可正常 claim 并投影唯一 FAILURE。不得增加 terminal query、fallback、兼容分支或测试专用生产 hook。
- 测试：使用 invalid-but-summary-valid 的有界投影输入或既有 public fake boundary，在事件构造时确定性抛错，断言只出现一个 FAILURE RESULT、无 accepted completed progress/result、无双终态；同时保留四时点与正常 completed/failed/cancelled 行为。

## 共同通过项

- 6 文件 allowlist 与冻结 digest 均由两路独立核验。
- strict exact status owner、pipeline/summary 同源、direct/durable 四时点、late cancel、CANCELLING 与 audit flag、cancelled 无 completed、failed 同源、download/preprocess、CLI SIGINT、README 与依赖/编码约束均通过。
- AgentCodex validation：plan focused matrix `522 passed`；真实 Docling integration `1 passed`；`ingestion_runtime.py` coverage `91%`；全量 pyright `0 errors`；修改文件 Black/Ruff 与 `git diff --check` 通过。

## 第二轮 re-review 裁决

- AgentMiMo：`docs/reviews/code-review-20260812-220519.md`，无 finding，结论 S3 可接受。
- AgentDS：`docs/reviews/code-review-20260812-220206.md`，确认 A2、A1、R1 全部闭环；另报一个低严重度 durable save→projection TOCTOU finding。

### R2 — 不接受为有效风险：假设 owner contract 外的 raw terminal 覆盖

- 来源：AgentDS 第二轮 re-review finding 001。
- 裁决：rejected；不是 residual risk，也不需要修复。
- 直接证据：finding 的触发前提是“另一个 process 在 atomic save 返回后覆盖同一 job 的 terminal record”。但该 store 的所有公开终态写接口都在同一 file lock 下执行 first-committer 检查，发现 `_TERMINAL_STATUSES` 后原样返回，不会覆盖已提交 terminal；生产架构同时只有一个 job writer。只有绕过仓储 owner、直接篡改文件才可能制造所述 stale snapshot，这不属于受支持 contract，也不能据此要求 projection 再读一次。
- 语义判断：`save_accepted_upload_terminal_if_active` 返回的 record 就是原子提交的 accepted winner；progress/event 必须从该同源 winner 投影。无条件重新读取反而会把 owner 外 raw mutation 引入业务语义，并扩大 I/O 与竞态面。
- 分类：无有效 residual risk。

## Docs Decision

- 根 README、`dayu/fins/README.md`、`tests/README.md` 均命中职责并已做最小更新。
- 分层/装配未变化，不更新 `dayu/README.md`。

## Residual Risks

- `fixed in current slice`：projection 异常安全网直接测试。
- `fixed in current slice`：direct upload claim 后构造异常导致 RESULT 丢失窗口。
- `covered by later approved gate`：UF-PF09 fresh evidence、aggregate deepreview、final validation。
- `assigned to later work unit`：company meta 独立事务、web fetch cancellation、非 POSIX descendant governance、格式范围扩展。
- `requiring user decision`：无。
- 未分类风险：无。

## Completion Status

初轮 accepted A1 已补测并通过双路 re-review；re-review 新发现 A2 并被 controller 接受。

AgentCodex 已按裁决完成 A2：direct upload 先纯构造同一 disposition 的 progress/RESULT 事件组，再单次 claim，claim 后仅通过不抛异常的 queue primitive 顺序投递；事件 contract 构造失败发生在 claim 前，由既有异常路径收口为唯一 FAILURE RESULT。新增 deterministic owner test 使用 121 字符、summary-valid 但 direct-label-invalid 的 public `document_id` 触发该边界，断言没有 completed/SUCCESS 或双终态。

- 修复后 base：`87389ebc194b51343d11b7e32bf5873389298fea`
- 修复后冻结 diff SHA-256：`c74a3af90309004f6fc74e6f314c23a8a48a25b296255804b524b25afad22133`
- 最小回归：`1 passed`
- ingestion runtime：`134 passed`
- CLI：`50 passed`
- plan focused matrix：`525 passed`
- 真实 Docling integration：`1 passed`
- 全量 pyright：`0 errors, 0 warnings, 0 informations`
- Black、Ruff、`git diff --check`：通过
- coverage：本轮显著修改 owner `ingestion_runtime.py` 为 `91%`；matrix 中另外 7 个相关 owner 为 `86%–95%`。未在 S3/A2 修改且冻结 matrix 仅覆盖其 upload stream 子路径的 `sec_pipeline.py` 为 `40%`，记录为验证覆盖边界，不扩大当前修复 scope；其受影响行为测试已包含在 `525 passed`。

同一冻结 target 已完成第二轮双路 re-review。AgentMiMo 无 finding；AgentDS 确认 A2/A1/R1 闭环，其新增 R2 因依赖绕过仓储公开 contract 的 raw terminal 覆盖而被拒绝。所有 accepted findings 已修复并复审通过，无 blocking question、未分类风险或 requiring-user-decision 项。S3 可 accepted。
