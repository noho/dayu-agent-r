# UF-FIX01 validation atomic boundary — Plan Fix Adjudication

## 1. Gate metadata

- **work unit**：`UF-FIX01 validation-atomic-boundary`
- **gate**：plan review fix
- **status**：`plan-fix-complete / re-review-pending / implementation-not-started`
- **branch**：`codex/upload-filing-oracle`
- **baseline HEAD**：`b3cb1f1b16f4d552eb762de3be59dc75c7586ab6`
- **fixed plan**：`docs/gateflow/uf-fix01-validation-atomic-boundary-plan-20260813.md`
- **review inputs**：
  - `docs/reviews/plan-review-20260813-093247.md`
  - `docs/reviews/plan-review-20260813-094750-agentds.md`
  - `docs/reviews/plan-review-20260813-101207-rereview-agentds.md`
- **artifact path**：`docs/gateflow/uf-fix01-validation-atomic-boundary-plan-fix-20260813.md`
- **changed scope**：只修订 plan 并新增本 adjudication；未修改生产代码、测试、README、registry/evidence，
  未运行实现、未提交。
- **next gate**：plan re-review。

## 2. Controller decision summary

Controller 接受 MiMo F01–F04 与 AgentDS DS-01–DS-08，要求全部在 plan gate 修复。MiMo F01 与
DS-08 是同一个 fresh-absent/guard-order 缺陷的独立复证，仍分别记录。没有 deferred finding。

Controller 继续接受 AgentDS re-review 新 finding R-DS1；该 finding 仅纠正 basename 参数适用 code 数量与
S2 exact message 覆盖，不改变既有 code、message、domain、allow-list 或 owner 语义。

Controller 接受 final consistency finding C-01；该 finding 只纠正整个 WU 的本地 Gateflow commits 与外部
PR/push/main 禁令边界，保留 plan gate 本身未提交的历史事实，不改变 implementation contract。

Open Questions 的裁决为：Q1/Q3/Q4 接受并在 plan 中确定化；Q2 因 Controller 已直接验证现有 factory
contract 而 `rejected-with-reason / resolved`。不存在需要实现阶段再决定的 open question。

## 3. Finding adjudication

| Finding | Controller status | Plan fix status | 具体修订位置 | 裁决与修订 |
| --- | --- | --- | --- | --- |
| MiMo F01 | accepted | 已修复 | §6.3、S1、§12.1 | 先调用 storage 既有 `_ticker_dir_for_read`；exact absent 才在 guard 前返回；existing 才 acquire once + 两次 unguarded read。补 symlink/broken symlink/descriptor/meta corruption fail-closed 与零 lock 路径测试。 |
| MiMo F02 | accepted | 已修复 | §6.1、S2 | 删除“至少”，冻结 23-member `FinsUploadUsageCode` 穷尽闭集；增加 UF-003–006、015–019、021–024、026–038 exact scenario→code→message mapping 和判定优先级。 |
| MiMo F03 | accepted | 已修复 | §6.4、S1 | 明列 direct download、runtime/durable download、direct preprocess、legacy preprocess/upload job、isolated job-store 首写回归与 exact durable assertions。 |
| MiMo F04 | accepted | 已修复 | §6.1、S2 | 固定唯一 `render_cli_error(f"dayu-cli upload_filing: {usage_failure.message}")` 路径和 exact one-line stderr；明确这是 `FinsUploadUsageFailure`，不是 runtime `FinsUploadFailureReason`。 |
| DS-01 | accepted | 已修复 | §6.1、§7 | pure types/validator 只在 `ingestion_runtime.py`；concrete wrapper 精确命名为 `prevalidate_fins_upload_filing_request_for_workspace` 且只在 `service_runtime.py`；禁止第二名字/alias，CLI 不 import storage。 |
| DS-02 | accepted | 已修复 | §6.2.1、§6.3、§7、S3 | 加入 `sec_pipeline.py`，固定 `service_runtime → SecPipeline → SecUploadWorkflowHost → workflow` repository/request 透传；CN 对称，HK 走同一 CN facade/state repository。 |
| DS-03 | accepted | 已修复 | §6.2.1、§7、S2/S3 | 固定 CLI/Service/Runtime/Runner/SEC-CN facade exact signatures；preflight typed object 原样传递；workflow fresh snapshot + 同一 validator 是 authoritative recheck，旧 snapshot 派生值不得 commit authorize。补 non-CLI consumer typed usage 行为。 |
| DS-04 | accepted | 已修复 | §6.5、§7、S2 | `docling_upload_service.resolve_upload_action` 保持唯一 owner；新增同模块 pure `evaluate_upload_overwrite_precondition` typed disposition，validator/workflow/prepare 共用，不复制且不改 UF-FIX02/08/10 语义。 |
| DS-05 | accepted | 已修复 | S3 | 增加 company-stage 中途失败与 delete source-stage 失败注入；都断言 rollback/commit counts、published tree 与逐文件 SHA-256。 |
| DS-06 | accepted | 已修复 | §7、S3、§12.1 | 把 UF-FIX09 回归落在 `tests/fins/test_fins_ingestion_runtime.py` 的 `DefaultFinsRuntime.get_ingestion_runtime` composition owner test；断言 shared converter/runtime/cancel token identity 与 async prepare。 |
| DS-07 | accepted | 已修复 | §6.1、§6.6、§7、S2/S4 | CLI typed usage catch 位于 protocol/generic catch 前；workflow catch 固定 cancelled→Docling typed→storage typed/OSError→generic Exception，禁止字符串分类。 |
| DS-08 | accepted | 已修复 | §6.3、S1、§12.1 | 与 F01 同源但独立关闭：明确 canonical-root helper 在 guard 前执行，fresh absent 后 `.dayu`/`portfolio`/lock 均不存在；existing guard acquire/release 各一次。 |
| R-DS1 | accepted | 已修复 / closed | §6.1、S2 | 将“两个文件 code”纠正为穷尽点名四个文件相关 code：`FILE_NOT_FOUND`、`FILE_NOT_REGULAR`、`FILE_SUFFIX_NOT_ALLOWED`、`CONVERTER_SUFFIX_UNSUPPORTED`；S2 增加四者接收已去路径化 basename 后的 exact message owner assertions。 |
| C-01 | accepted | 已修复 / closed | §3、§13；§1/末行保持 | 整个 WU 按 Gateflow 生成本地 checkpoint/implementation/fix/closeout commits；PR、push、main 更新在本 WU 明确禁止且不等待或请求授权。§1 与末行继续记录 plan gate 本身不提交。 |

## 4. Open question adjudication

| Question | Status | Plan fix status | 具体修订位置 | 裁决 |
| --- | --- | --- | --- | --- |
| Q1 prepare/delete/skip 真实分支 | accepted / resolved | 已修复 | §6.5、§12.2 | 固定现状：pre-cancel 返回 cancelled；delete 返回 `_PreparedDeleteMutation`；non-delete fingerprint 相同返回 terminal skipped；其余转换后返回 `_PreparedAssetMutation`。skip 不 begin batch，delete 只在 publish 阶段用 batch。 |
| Q2 repository factory 参数 | rejected-with-reason / resolved | 不需代码计划变更 | §6.4、§7“明确不修改”、§12.2 | Controller 已验证 `build_fs_repository_set` 已有并透传 `create_directories`；不把 `_fs_repository_factory.py` 加入 files，不新增 wrapper。 |
| Q3 CN/HK snapshot 等价性 | accepted / resolved | 已修复 | §6.3、§6.2.1、§7、S3、§12.2 | SEC/CN/HK 使用同一 protocol/implementation/result shape；CN 与 HK 各有 market-route/recheck owner assertion。 |
| Q4 non-CLI usage projection | accepted / resolved | 已修复 | §6.2.1、§7、S2、§12.2 | raw filing 的 direct/observed/legacy runtime entry 在业务启动前抛同一 typed `FinsUploadUsageError`；只有 CLI 映射 exit 2，Host/Engine 不改。 |

## 5. Contract changes made to the plan

### 5.1 Unique validation/assembly ownership

- `ingestion_runtime.py`：`FinsUploadUsageCode`、usage/failure/validated types、
  `fins_upload_usage_failure`、`validate_fins_upload_filing_request`。
- `service_runtime.py`：唯一 concrete wrapper
  `prevalidate_fins_upload_filing_request_for_workspace(request, *, workspace_root)`，以及同一个 FS state
  repository 对 runtime/SEC/CN 的 composition。
- CLI：只做 ticker CSV syntax 与 exact UI mapping；空 CSV 通过 Fins message source 构造 typed usage failure，
  不拼业务文案、不 import storage。

### 5.2 Fresh-state authority

CLI preflight 只证明 factory 前 admissibility。workflow 可复用 deterministic ticker/document ID 来定位 fresh
snapshot，但必须丢弃旧 published state、resolved action 与 company decision，再调用同一 pure validator。
只有 fresh result 能进入 prepare/stage/commit；batch/storage commit 继续是并发 fail-closed owner。

### 5.3 Existing behavior preservation

- 两套 allow-list 的值不改；按现有 direct allow-list 后 converter allow-list 的顺序使用。
- year/date/period domain 不改；US 与 CN/HK 仍走各自现有 pure normalization。
- action/overwrite 只复用/类型化当前 helper，不处理 UF-FIX02/08/10。
- UF-FIX09 converter implementation/config/process lifecycle 不改，仅增加 composition owner regression。
- skip/delete/cancel/commit 采用现有 prepared/result 分支和 `commit_prepared_upload_batch` capability lifecycle；
  不增加补偿删除或第二 batch。

## 6. Validation of this fix gate

本 gate 的自检要求：

- worktree 只允许原 plan、本文 fix artifact、两份初始 review docs 与三份 re-review docs；所有 review docs
  不得被修改。
- `git diff --check` 与 untracked artifact whitespace check 通过。
- 原 plan 不再含 `validate_fins_upload_filing_request_for_workspace` 的冲突名字或“usage code 闭集至少覆盖”。
- 原 plan 明确包含 `sec_pipeline.py`、company/delete failure injection、DefaultFinsRuntime converter owner test、
  generic catch 前的 typed catch、Q1–Q4 resolved 与 blocker=无。
- 不运行 pytest/pyright：本 gate 没有生产/测试变更，也不授权实现。

## 7. Residual risks

- **TOCTOU**：`covered by later approved S2/S3`；fresh recheck 不是 commit lock，最终由 batch/storage fail closed。
- **lazy bootstrap regression**：`covered by later approved S1`；四类 download/preprocess/job 路径已列 exact tests。
- **format drift**：`assigned to existing later UF-FIX work unit`；本 WU 不改两套集合。
- **failure redaction**：`covered by later approved S4`；typed mapping 后才 bounds，禁止 raw exception text。
- **UF-FIX09 regression**：`covered by later approved S3`；composition owner identity test 已固定。
- **validation snapshot/full source snapshot 误用**：`covered by later approved S5 docs`；README 将写明用途边界。

无 unclassified residual risk，无 deferred finding，无 blocking open question。

## 8. Completion

两路初始 review、AgentDS re-review 与 Controller final consistency finding 的所有 accepted findings 均已在 plan
文本中修复；R-DS1、C-01 已 `accepted / closed`；Q2 已按 Controller 证据拒绝并关闭；其余 questions 已
确定化。最终 delta re-review 已分别关闭 R-DS1 与 C-01；Controller plan-gate adjudication 为 `pass`。
当前状态为 `accepted / implementation-authorized`，下一入口是 accepted-plan checkpoint commit 后的
implementation。本 artifact 不授权 push、PR 或 main 更新。
