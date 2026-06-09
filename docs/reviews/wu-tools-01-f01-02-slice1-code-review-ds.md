# Code Review — WU-TOOLS-01-F01-02 Slice 1

## Scope

- Mode: current changes
- Branch: `work/wu-tools-01-f01-02-cancellation`
- Base (plan commit): `af3ac6b8`
- Output file: `docs/reviews/wu-tools-01-f01-02-slice1-code-review-ds.md`
- Included scope: `dayu/fins/ingestion_runtime.py`, `dayu/fins/tools/download_tools.py`, `dayu/fins/tools/preprocess_tools.py`, `tests/fins/test_fins_ingestion_tools.py`, `tests/fins/test_fins_ingestion_runtime.py`, `dayu/fins/README.md`, `tests/README.md`, `docs/reviews/wu-tools-01-f01-02-slice1-implementation-codex.md`
- Excluded scope: 后续 Slice 2/3/4（Web、Doc、Fins read tools）、control doc（只做一致性检查，不当 production defect）
- Parallel review coverage: 无。所有路径由本 reviewer 逐行走读。

## Findings

### F1-未修复-中-`_create_queued_job` 成为死代码
- **入口/函数**: `FinsIngestionRuntime._create_queued_job`
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:1160-1193`
- **输入场景**: 任何调用方（此前由 `start_download` / `start_preprocess` 调用）
- **实际分支**: Slice 1 重构后，`start_download` (line 1050) 和 `start_preprocess` (line 1107) 各自直接获取 `_start_lock` 并调用 `_create_queued_job_record`，不再经过 `_create_queued_job` wrapper。
- **预期行为**: 不需要的私有方法应删除，避免死代码扩散和后续误用。
- **实际行为**: `_create_queued_job` 保留在模块中但无任何调用方（grep 全仓仅定义无调用）。
- **直接证据**: `start_download:1049-1068` — 直接获取 `_start_lock` 后调用 `_create_queued_job_record`；`start_preprocess:1106-1124` 同理。`_create_queued_job:1186` 持有自己的 `with self._start_lock:`，但已无路径进入。
- **影响**: 死代码本身不产生正确性缺陷，但违反项目"禁止兼容性代码"规则。若 future 代码误用 `_create_queued_job`（它在锁内调用 `_create_queued_job_record` 但不做 token checkpoint 且不执行 submit 决策），可能引入新的 orphan job 窗口。
- **建议改法和验证点**: 删除 `_create_queued_job`（line 1160-1193），或将调用方参数路由改为仍经 wrapper 并在 wrapper 内完成 checkpoint+submit。若删除，验证 pyright 和全量 tests 通过。
- **修复风险（低）**: 删除私有方法，无外部调用方。
- **严重程度（中）**: 非阻塞性代码卫生，但违反项目明确规则。

### F2-已裁决-中-Submit前取消产生无runner的CANCELLING orphan job
- **入口/函数**: `FinsIngestionRuntime.start_download` / `start_preprocess`
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:1058-1059`, `1115-1116`
- **输入场景**: durable create 后、executor submit 前 token 观察到取消。
- **实际分支**: line 1058: `if _is_start_cancelled(cancellation_token):` → line 1059: `return _job_start_from_record(self.request_cancel(start.job_id))`。`request_cancel` 将 job 标记为 `CANCELLING`，`cancellation_requested=True`。不调用 `executor.submit`。
- **预期行为**: 按 plan 设计，job record 应在 cancelling 或 cancelled 状态，不 submit 后台操作。这是 plan 的 explicit invariant。但 plan 同时将两阶段启动 deferred，承认 awaiting accept 前 orphan job 窗口无法完全关闭。
- **实际行为**: job record 停在 `CANCELLING`，没有后台 runner。工具 callable 将 `CANCELLING` 状态的 `FinsIngestionJobStart` 投影为 `ToolCancelledOutcome` 直接返回给 Engine（不经 awaiting/wait adapter），因此 Host 不会为此 job 创建 wait record。job file 持久存在但无任何路径将其推进到 `CANCELLED` 终态。
- **直接证据**: `download_tools.py:86-87` — `if start.status in {CANCELLING, CANCELLED}: return _cancelled_outcome(started_at)` — 返回同步取消 outcome，不返回 `ToolAwaitingOutcome`。`ingestion_runtime.py:1058-1059` — 不调用 `executor.submit`。
- **影响**: job file 残留在 Fins workspace `.dayu/fins_ingestion/jobs/` 下，不会自动清理。不影响 Engine/Host 正确性——工具已返回取消 outcome，Engine 正常消费，Host 未创建 wait record。长期累积可能造成 workspace 膨胀，但由于 Fins workspace 是确定性路径且 job record 体积有界（<8KB），膨胀风险有限。
- **建议改法和验证点**: Plan 已将两阶段启动 deferred 到 WU-WAIT-03 或独立 follow-up。本 Slice 不需要修复。如需缓解，可在 `start_download`/`start_preprocess` 的 cancel 分支中直接调用 `_save_cancelled` 把 job 终态化为 `CANCELLED`，而非仅 `request_cancel` 停在 `CANCELLING`。但注意 `_save_cancelled` 需要完整 `FinsIngestionJobRecord` 参数（当前 checkpoint 处 `start` 是 `FinsIngestionJobStart`，其 `record` 仍是 `QUEUED` 状态——需先 `request_cancel` 再读取最新 record 做 terminal save）。
- **修复风险（低）**: 直接 terminalize 的改动仅影响已确定的 cancel 路径。
- **严重程度（中）**: Plan 明确认可此行为（"create 后、submit 前取消后 job 停在 CANCELLING"），不阻塞 Slice 1。Severity 来自长期 orphan job 累积，但不属于 correctness/safety issue。

**裁决**: 此 finding 对应 plan R3（implementation artifact 已记录），是 plan 明确接受的 residual risk。建议 controller 裁决为 `accepted`（认定为 plan 已知限制），将彻底修复 deferred 到两阶段启动 WU。

### F3-未修复-低-`_CancelOnSecondCheckToken.check_count` 计数断言对 checkpoint 数量敏感
- **入口/函数**: `test_download_start_cancel_between_create_and_submit_marks_job_cancelled_and_does_not_submit` 及对应的 preprocess 测试
- **文件(行号)**: `tests/fins/test_fins_ingestion_runtime.py:571`, `782`
- **输入场景**: 使用 `_CancelOnSecondCheckToken` 模拟第二次 checkpoint 时取消。
- **实际分支**: `assert token.check_count == 2` — 断言 `is_cancelled()` 被调用恰好两次。
- **预期行为**: 行为测试应断言可观测结果（job status、cancellation_requested、executor.operations 为空），不应严格断言内部 checkpoint 调用次数。
- **实际行为**: 当前断言 48/48 通过。但若未来实现新增合法 checkpoint（例如在 ticker normalizer 后、request summary 构建后增加额外的安全检查点），`check_count` 变为 3，断言失败但行为可能完全正确。这是 brittle assertion。
- **直接证据**: `_CancelOnSecondCheckToken:214-215` — `self.check_count += 1; return self.check_count >= 2`；`test_download_start_cancel_between_create_and_submit:571` — `assert token.check_count == 2`。
- **影响**: 测试在非行为回归时断裂，浪费调试时间。不影响生产正确性。
- **建议改法和验证点**: 保留 `check_count >= 2` 的不等式断言或完全移除计数断言。行为断言（job status CANCELLING、cancellation_requested=True、executor.operations==[]）已充分验证 correct behavior。
- **修复风险（低）**: 仅修改测试断言。
- **严重程度（低）**: 不影响生产正确性，不会隐藏真实 bug。

### F4-未修复-低-`_CancelOnSecondCheckToken` 未实现完整的 `CancellationToken` protocol
- **入口/函数**: `_CancelOnSecondCheckToken`
- **文件(行号)**: `tests/fins/test_fins_ingestion_runtime.py:192-235`
- **输入场景**: 生产代码调用 `cancellation_token.cancel_reason()` 或 `requested_at()`。
- **实际分支**: 当前生产代码只调用 `is_cancelled()`，但 `CancellationToken` protocol 定义了三个方法。`_CancelOnSecondCheckToken.cancel_reason()` (line 217-226) 在 `check_count < 2` 时返回 `None`，`requested_at()` (line 228-235) 始终返回 `None`。这些实现与实际取消时机（第二次 checkpoint）不一致——第二次 checkpoint 时 `is_cancelled()` 返回 `True`，但 `cancel_reason()` 返回 `"host-cancelled"`, `requested_at()` 返回 `None`。若生产代码未来在取消路径中读取 `cancel_reason()` 或 `requested_at()`，测试行为与真实取消 token 行为偏差。
- **直接证据**: `_CancelOnSecondCheckToken:207-235`。
- **影响**: 当前无影响（生产代码仅使用 `is_cancelled()`），但测试替身与 protocol 语义不完全对齐，属于 future risk。
- **建议改法和验证点**: 在 `is_cancelled()` 返回 `True` 时，`cancel_reason()` 和 `requested_at()` 应返回非空值。可设置 `_cancelled` flag 在第一次 `is_cancelled() == True` 时触发，后续所有方法基于该 flag 响应。
- **修复风险（低）**: 仅修改测试替身。
- **严重程度（低）**: 当前生产代码只使用 `is_cancelled()`，不造成实际行为差异。

## 重点审查项逐一回复

### start 前 token cancel 是否不创建 durable job
**通过。** `download_tools.py:81-82` 和 `preprocess_tools.py:80-81` 在调用 `runtime.start_*` 前检查 `cancellation_token.is_cancelled()`，命中时直接返回 `ToolCancelledOutcome`。`ingestion_runtime.py:1049`/`1106` 的 `_raise_if_start_cancelled` 提供二次防线。测试 `test_download_tool_cancelled_before_start_returns_cancelled_without_job` 和对应的 preprocess 测试验证了此行为（检查 job store 目录无 JSON 文件）。

### durable job create 后、executor.submit 前同步 checkpoint 是否真正无"看到取消仍 submit"窗口
**通过。** `ingestion_runtime.py:1050-1067` — `_start_lock` 覆盖了 `_create_queued_job_record`、cancel checkpoint (`_is_start_cancelled`) 和 `executor.submit` 的完整时序。line 1058 的 checkpoint 在锁内、`executor.submit` (line 1060) 之前。测试 `_CancelOnSecondCheckToken` 验证了 job 标记 CANCELLING 且 executor 未收到操作。

**但注意**：`_start_lock` 仅序列化同一进程内的 start 调用；它不阻止另一个进程/线程通过 `job_store.request_cancel` 在 submit 后立即写入取消请求。这属于 plan 已知的异步 cancel 窗口，不在本 Slice 范围内。

### holding `_start_lock` 时调用 `request_cancel` 是否会导致死锁、锁顺序问题或 filelock 问题
**通过。** `_start_lock` 是 `threading.Lock` (line 1010)，`request_cancel` → `FsFinsIngestionJobStore.request_cancel` 内部使用 `file_lock(...)` 即 `filelock.FileLock`。两者是完全独立的锁机制，不存在互等。锁顺序在所有路径上一致：先 `_start_lock`（如果需要），后 `file_lock`。没有路径先获取 `file_lock` 后获取 `_start_lock`。

### create 后 cancel 返回 ToolCancelledOutcome 与 job record 停在 CANCELLING 的语义是否符合 plan
**符合 plan，详见 F2。** Plan 明确此行为（Section 6: "Fins tool start 后、返回 awaiting outcome 前再次观察 token；若已取消，立即 `runtime.request_cancel(job_id)` 并返回 `ToolCancelledOutcome` 或保证 job record 进入 cancelling/cancelled 可由 wait adapter 收口"）。由于不 submit 后台 runner，job 停在 CANCELLING 无自动收口。这是 plan 明确 deferred 的两阶段启动 orphan 窗口。

### submit 后不再使用 Host token，后台只观察 job store durable cancel
**通过。** `start_download:1060-1067` 和 `start_preprocess:1117-1124` — `executor.submit` 传入的 lambda 不捕获 `cancellation_token`。后台方法 `_run_download_job` (line 1286) 和 `_run_preprocess_job` (line 1245) 不接收 token 参数。它们通过 `_mark_job_running_or_cancelled` → `claim_running_or_cancelled` 和循环中的 `job_store.read_job` + `cancellation_requested` 检查观察 durable cancel。

### ToolCancelledOutcome meta/message/hint 是否 LLM-facing 自解释
**通过。**
- `download_tools.py:44-46`: message=`"Fins download start was cancelled by the host."`, hint=`"Continue without this Fins download job unless the user asks to retry."`
- `preprocess_tools.py:44-45`: message=`"Fins preprocess start was cancelled by the host."`, hint=`"Continue without this Fins preprocess job unless the user asks to retry."`
- reason=`"host_cancelled"` 来自公共契约常量 `TOOL_CANCELLED_REASON_HOST_CANCELLED`
- meta 包含 `tool_name`、`started_at`、`finished_at`

message 和 hint 均为自足英文，不暴露内部治理术语。reason 使用公共契约常量白名单值。

### OSError / ValueError / terminal job handling 是否保持旧行为
**通过。** `download_tools.py:90-113` — ValueError → `ToolFailedOutcome(error="invalid_argument")`；OSError → `ToolFailedOutcome(error="fins_download_start_failed")`；Exception → `ToolFailedOutcome(error="fins_download_start_failed")`。`FinsIngestionStartCancelledError` 作为新增异常被独立 catch 并转为 `ToolCancelledOutcome`。旧错误处理分支未被修改或弱化。

### tests 是否覆盖 required behavior，是否有 brittle 计数或未覆盖 race
**部分通过，详见 F3/F4。** 四个 plan-required 测试均已实现：
- start 前取消不创建 job ✅（download + preprocess）
- create 后取消标记 job 且不 submit ✅（download + preprocess）

现有测试保持通过。脆弱点：F3（计数断言对 checkpoint 数量敏感）、F4（测试替身 protocol 不完整）。未覆盖 race：token 在 checkpoint #2 之后、`executor.submit` 之前的真实并发取消（属于 deferred orphan 窗口）。

### README 更新是否符合对应 README Agent更新约束
**通过。** `dayu/fins/README.md` 的更新内容（cancellation_token 参数、FinsIngestionStartCancelledError、取消流程）属于该 README 声明的职责范围（"当前代码已实现的 `dayu.fins` package 的 capability 定位、两条执行路径、对外接口、公共契约、状态机、关键机制"）。`tests/README.md` 的更新在 `tests/fins/` 段落中补充了新增测试的描述，符合其"只描述当前 `tests/` 已存在的事实"约束。

### pyright/test 结果是否可信
**通过。** 实测：`pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q` → 48 passed, 0 failed。`pyright dayu/fins/tools/download_tools.py dayu/fins/tools/preprocess_tools.py dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py` → 0 errors, 0 warnings（仅版本升级提示）。

## Open Questions

1. `_create_queued_job` 死代码是否需要在本 Slice 清理，还是 deferred 到后续清理 Slice？——若 controller 认为与本 Slice 契约变更无关，可 deferred。
2. CANCELLING orphan job 是否需要在本 Slice 中 terminalize（直接调用 `_save_cancelled`），还是严格按 plan deferred 到两阶段启动？——当前 plan 选择 deferred；若改为直接 terminalize，需确认 `_save_cancelled` 需要的是经过 `request_cancel` 后重新从 job store 读取的最新 record（而非 checkpoint 处持有的 `start.record` 仍是 `QUEUED`）。

## Residual Risk

| ID | Risk | Owner / Destination |
|---|---|---|
| R1 | Awaiting accept 前 orphan job 窗口（plan deferred 两阶段启动） | WU-WAIT-03 / 独立 follow-up |
| R2 | `_CancelOnSecondCheckToken.check_count == 2` 断言对 checkpoint 调用次数敏感 | 当前 WU Slice 1 测试维护 |
| R3 | `_CancelOnSecondCheckToken` 未完整实现 `CancellationToken` protocol（`cancel_reason`/`requested_at` 时机语义不一致） | 当前 WU Slice 1 测试维护 |
| R4 | `_create_queued_job` 死代码残留 | 当前 WU 或后续清理 Slice |
| R5 | Web / Doc / Fins read tools token 传播未实现 | Slice 2 / 3 / 4 |
| R6 | 没有跨进程并发 cancel 测试（`_start_lock` 是 threading.Lock，不同进程的 start+request_cancel 并发由 file_lock 保护） | 后续集成/压力测试 |

## Slice 1 准入裁决

Slice 1 无 blocking findings。F1（死代码）、F3（brittle 断言）、F4（不完整 protocol 替身）均可 deferred 或低风险修复。F2（orphan CANCELLING job）是 plan 明确认可的 residual risk。

**Slice 1 可进入 accepted slice commit**，前提是 controller 对 F1-F4 给出明确裁决（accepted / rejected-with-reason / deferred-with-owner）。
