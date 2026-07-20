# WU-SEMANTIC-OWNERSHIP-01 R05-S1 Validation Continuation — AgentCodex

## 1. Gate、scope 与结论

- umbrella：WU-SEMANTIC-OWNERSHIP-01。
- gate：既有 R05-S1 validation continuation；不是新 WU，不重新 implementation，不进入 R05-S2。
- accepted plan-correction commit：cf2f832cfe45b4a58a179d842d6b09c337d99f24。
- validation-resume transition / HEAD：2c068869843837546e6c6bc0a5285918b01d8b29。
- fixed plan base：5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1。
- verdict：PASS / READY_FOR_CONTROLLER_VALIDATION。
- stop status：本 continuation 在 Controller validation 前停止；未进入 code review、commit、aggregate、push、PR 或 R05-S2。
- artifact path：docs/reviews/wu-semantic-ownership-01-r05-s1-validation-continuation-codex.md。

第一性原理复核继续成立：observation timeout 只证明本轮同步观察没有在 Host 预算内取得可发布结果，不能证明 external job lost、cancel 已成功或 durable lifecycle 已终止。当前七路径 diff 把该事实投影为 WaitPoller-owned transient diagnostic + 既有 claim release/backoff；durable state 继续拥有原子 projection，runner 继续唯一拥有 publication fence，typed LOST 与 explicit lifecycle terminal outcome 继续由原 owner 承诺。没有出现要求修改其它 owner 的直接证据。

## 2. Preflight、commit 与受保护输入

执行：

    git branch --show-current
    git status --short
    git rev-parse HEAD
    git cat-file -t cf2f832cfe45b4a58a179d842d6b09c337d99f24
    git cat-file -t 2c068869843837546e6c6bc0a5285918b01d8b29
    git merge-base --is-ancestor cf2f832cfe45b4a58a179d842d6b09c337d99f24 2c068869843837546e6c6bc0a5285918b01d8b29
    git merge-base --is-ancestor 2c068869843837546e6c6bc0a5285918b01d8b29 HEAD

结果：

- branch 为 phaseflow/host-issues-control，非 protected trunk。
- HEAD 精确为 validation-resume transition。
- 两个 commit object 均存在，accepted correction 是 resume transition 的 ancestor，resume transition 是 HEAD。
- continuation 开始时 tracked worktree 精确为七个受保护 product/test/design paths；另有既有 untracked implementation artifact，未修改。
- 原 implementation artifact SHA-256 为 b8ec89aafc6008587791958cb356f0124cec76199959f2ea3b62272ee3496732。

七个受保护路径：

1. dayu/host/durable/state.py
2. dayu/host/wait_adapter.py
3. docs/host/design.md
4. tests/host/test_phase7_waiting_integration.py
5. tests/host/test_wait_adapter_polling.py
6. tests/host/test_wait_observation_runner.py
7. tests/host/test_wait_record_state.py

continuation 前执行：

    git diff --binary -- \
      dayu/host/durable/state.py \
      dayu/host/wait_adapter.py \
      docs/host/design.md \
      tests/host/test_phase7_waiting_integration.py \
      tests/host/test_wait_adapter_polling.py \
      tests/host/test_wait_observation_runner.py \
      tests/host/test_wait_record_state.py \
      | shasum -a 256

结果：

    3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2

与 accepted protected digest 精确一致。七路径完整 diff 已逐行读取；本 continuation 未修改其中任何路径。

## 3. Test-first red 与当前 production green

### 3.1 原 red 证据重新确认

原 test-only red 的 exact command：

    source .venv/bin/activate
    python -m pytest -q \
      tests/host/test_wait_observation_runner.py::test_poll_observation_timeout_releases_with_backoff_and_late_result_cannot_resolve \
      tests/host/test_wait_observation_runner.py::test_cancelled_abandon_timeout_releases_with_backoff_and_late_result_cannot_mark_terminal \
      tests/host/test_phase7_waiting_integration.py::test_poll_observation_timeout_keeps_waiting_then_ready_resumes_run

保留日志 workspace/tmp/r05-s1-red.txt 的 SHA-256：

    18d3e599823570b51b833666338920a64aabea2bfd68ca5c515485bb96bad70f

日志结果为 3 failed in 0.47s，三个失败均落在 owner semantic assertion：

- poll timeout 的旧结果 lost == 1，新 contract 要求 lost == 0；
- abandon timeout 的旧 durable row 已写 poll_abandoned_at，新 contract 要求为 None；
- Phase 7 integration 的旧结果 lost == 1，新 contract 要求继续 WAITING。

同时从固定 base 5ba0d8b... 直接读取 dayu/host/wait_adapter.py，确认旧 poll timeout 分支确实构造 WaitPollLost(ResolveWaitLostOutcome(...)) 并调用 resolve；旧 abandon timeout 分支确实调用 _MarkWaitRecordAbandonTimeoutOperation。由此 red failure 与旧 production root cause 逻辑/数据同源，不是 fixture/setup 问题。由于 continuation write allowlist 禁止回滚或改写七个受保护路径，本轮不在主工作树重造 test-only 状态；改为核对 immutable red log、固定 base 源码，并在当前 production 上重新执行相同 exact nodes。

### 3.2 当前三个 owner 节点

执行同一 exact command，结果：

    3 passed in 0.41s

### 3.3 Durable owner preservation

执行：

    source .venv/bin/activate
    python -m pytest -q \
      tests/host/test_wait_record_state.py::test_cancelled_poll_timeout_release_preserves_claimability_after_due \
      tests/host/test_wait_record_state.py::test_poll_abandon_success_marks_row_and_clears_claim

结果：

    4 passed in 0.30s

证明 timeout retry 与 explicit applied/unsupported/noop terminal marker 继续由两个合法 durable operation 分开承诺。

### 3.4 Focused owner / branch matrix

执行：

    source .venv/bin/activate
    python -m pytest -q \
      tests/host/test_wait_observation_runner.py::test_timeout_invalidates_token_and_late_result_cannot_publish \
      tests/host/test_wait_observation_runner.py::test_poll_observation_timeout_releases_with_backoff_and_late_result_cannot_resolve \
      tests/host/test_wait_observation_runner.py::test_cancelled_abandon_timeout_releases_with_backoff_and_late_result_cannot_mark_terminal \
      tests/host/test_wait_observation_runner.py::test_supervisor_close_uses_one_shared_deadline_and_stays_closing \
      tests/host/test_wait_adapter_polling.py::test_poll_adapter_ready_result_resolves_wait \
      tests/host/test_wait_adapter_polling.py::test_poll_adapter_not_ready_leaves_wait_active \
      tests/host/test_wait_adapter_polling.py::test_poll_adapter_lost_result_closes_run \
      tests/host/test_wait_adapter_polling.py::test_abandon_adapter_snapshot_projection_failure_releases_with_backoff \
      tests/host/test_wait_adapter_polling.py::test_cancelled_poll_wait_is_abandoned_once_without_resolve \
      tests/host/test_wait_adapter_polling.py::test_failed_cancelled_wait_abandon_is_retried_next_poll \
      tests/host/test_wait_adapter_polling.py::test_active_poll_claim_suppresses_second_poller_adapter_call \
      tests/host/test_wait_adapter_polling.py::test_expired_poll_claim_allows_retry \
      tests/host/test_wait_adapter_polling.py::test_invalid_poll_deadline_fails_closed_without_business_lost \
      tests/host/test_wait_record_state.py::test_cancelled_poll_timeout_release_preserves_claimability_after_due \
      tests/host/test_wait_record_state.py::test_poll_abandon_success_marks_row_and_clears_claim \
      tests/host/test_phase7_waiting_integration.py::test_poll_observation_timeout_keeps_waiting_then_ready_resumes_run

结果：

    19 passed in 0.56s

覆盖 Ready、NotReady、authoritative typed LOST、poll/abandon timeout、snapshot failure、explicit lifecycle terminal、retry、claim CAS、expired claim、invalid deadline、token invalidation、capacity/shared close deadline 与真实 durable resume。

### 3.5 四个 Host focused files

执行：

    source .venv/bin/activate
    python -m pytest -q \
      tests/host/test_wait_observation_runner.py \
      tests/host/test_wait_adapter_polling.py \
      tests/host/test_phase7_waiting_integration.py \
      tests/host/test_wait_record_state.py

结果：

    69 passed in 0.91s

### 3.6 R04 ownership preservation

执行：

    source .venv/bin/activate
    python -m pytest -q \
      tests/runtime/test_config_loader.py::test_host_runtime_wait_poller_policy_block_is_required \
      tests/runtime/test_config_loader.py::test_host_runtime_wait_poller_policy_fields_are_all_required \
      tests/runtime/test_config_loader.py::test_host_runtime_wait_poller_policy_rejects_unknown_field \
      tests/fins/test_fins_ingestion_tools.py::test_awaiting_resolution_mode_parser_accepts_closed_typed_modes \
      tests/fins/test_fins_ingestion_tools.py::test_awaiting_resolution_mode_parser_rejects_missing_or_illegal_values \
      tests/fins/test_fins_ingestion_tools.py::test_each_fins_awaiting_provider_validates_mode_before_runtime_creation \
      tests/service/test_host_assembly.py::test_compose_open_host_options_projects_complete_config_owned_wait_policy \
      tests/service/test_host_assembly.py::test_scene_tool_selection_does_not_own_wait_poller_composition \
      tests/service/test_host_assembly.py::test_manual_mode_composes_binding_without_background_poller \
      tests/service/test_host_assembly.py::test_poll_and_manual_modes_partition_runtime_composition \
      tests/service/test_host_assembly.py::test_callback_mode_fails_closed_before_open_host

结果：

    35 passed, 3 warnings in 1.80s

三个 warning 均来自 edgar 第三方 deprecation，不是失败。

### 3.7 Aggregate functional matrix

执行：

    source .venv/bin/activate
    python -m pytest -q \
      tests/host/test_wait_observation_runner.py \
      tests/host/test_wait_adapter_polling.py \
      tests/host/test_phase7_waiting_integration.py \
      tests/host/test_wait_record_state.py \
      tests/engine/test_agent_phase3_tool_call.py \
      tests/runtime/test_config_loader.py \
      tests/fins/test_fins_ingestion_tools.py \
      tests/service/test_host_assembly.py \
      tests/service/test_fins_wait_adapter.py \
      tests/service/test_entrypoint_runtime_interactive_path.py

结果：

    359 passed, 3 warnings in 3.27s

## 4. Changed-owner coverage

为遵守 continuation 只允许 workspace/tmp validation outputs 的 write allowlist，本轮只把 coverage data file 通过环境变量定向到 workspace/tmp；pytest/coverage 参数与修订后 plan 完全一致。

执行：

    source .venv/bin/activate
    export COVERAGE_FILE=workspace/tmp/r05-s1-validation-continuation.coverage
    python -m pytest -q tests/host \
      --ignore=tests/host/test_toolruntime_executor.py \
      --ignore=tests/host/test_dispatch_scheduler.py \
      --cov=dayu.host.durable.state \
      --cov=dayu.host.wait_adapter \
      --cov-branch \
      --cov-report=term-missing \
      --cov-report=json:workspace/tmp/r05-s1-coverage.json

结果：

    1830 passed, 2 skipped, 5 deselected in 51.56s
    dayu/host/durable/state.py  83%
    dayu/host/wait_adapter.py   86%
    TOTAL                       84%

session 整体绿色。只使用了计划精确允许的两个 ignore；没有第三个 ignore、额外 deselect、xfail、retry 或 failure exemption。

执行逐文件门禁：

    python -m coverage report --include='dayu/host/durable/state.py' --fail-under=80
    python -m coverage report --include='dayu/host/wait_adapter.py' --fail-under=80

结果：

- durable/state.py：83%，exit 0。
- wait_adapter.py：86%，exit 0。

执行 actual changed-production list：

    git diff --name-only 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1 -- dayu

结果精确为：

    dayu/host/durable/state.py
    dayu/host/wait_adapter.py

随后按该实际列表重新运行上述两个逐文件门禁，仍分别为 83% / 86%，均 exit 0；没有遗漏或用 aggregate coverage 替代单文件 threshold。

## 5. Pyright 与 Ruff

### 5.1 Full pyright

执行：

    source .venv/bin/activate
    python -m pyright dayu/ tests/ utils/

结果：

    0 errors, 0 warnings, 0 informations

版本更新提示不是类型错误。

### 5.2 Changed-file Ruff

执行：

    source .venv/bin/activate
    python -m ruff check \
      dayu/host/durable/state.py \
      dayu/host/wait_adapter.py \
      tests/host/test_wait_observation_runner.py \
      tests/host/test_wait_adapter_polling.py \
      tests/host/test_phase7_waiting_integration.py \
      tests/host/test_wait_record_state.py \
      tests/engine/test_agent_phase3_tool_call.py \
      utils/smoke_host_public_awaiting_entrypoint.py

结果：

    All checks passed!

两条 touched-file F401 已消失。

### 5.3 Full Ruff baseline registry

执行 required human command：

    source .venv/bin/activate
    python -m ruff check dayu tests utils

结果：

    Found 165 errors.
    exit 1

这是 plan 允许的既有 full Ruff residual，不能仅按数量继承。机器输出命令：

    python -m ruff check dayu tests utils \
      --output-format=json \
      --output-file=workspace/tmp/r05-s1-validation-continuation-ruff-current.json

固定 base registry 为 workspace/tmp/r05-s1-ruff-baseline.json，SHA-256 为 884f004d64984306aeff8c3c715f9e5c8a67a9bbf3c889046c823f344ce2e129。使用 jq 对相对路径、rule、row、column、normalized message、severity 排序并做双向集合差；exact command 与 baseline SHA 作为 registry 固定字段。

结果：

- baseline_count：167。
- current_count：165。
- added：空集合。
- removed：精确只有：
  1. dayu/host/durable/state.py / F401 / 40:5 / TERMINAL_RUN_STATUS_VALUES imported but unused / error；
  2. tests/host/test_phase7_waiting_integration.py / F401 / 8:22 / datetime.UTC imported but unused / error。
- exact_expected_delta：true。

因此其它 165 条 residual 的六元组与固定 base 精确相同；没有新增 rule、severity、path/location、fingerprint 或同数量替换。

## 6. Source、propagation、schema 与 no-diff audit

### 6.1 Timeout / terminal propagation

执行：

    rg -n 'WaitObservationTimedOut|wait_observation_timeout|wait_abandon_timeout|ResolveWaitLostOutcome' \
      dayu/host/_wait_observation.py dayu/host/wait_adapter.py dayu/host/waiting.py dayu/host/durable/state.py \
      tests/host

结果与人工核对：

- wait_observation_timeout / wait_abandon_timeout 只作为 WaitPoller diagnostic constants、两个 timeout branch 与测试预期存在。
- poll timeout 分支只调用 _release_with_backoff，写 ADAPTER_ERROR/wait_observation_timeout；没有构造 ResolveWaitLostOutcome 或调用 _resolve_claimed_wait。
- abandon timeout 分支只调用 _release_with_backoff，写 ABANDON_ERROR/wait_abandon_timeout；没有写 poll_abandoned_at。
- ResolveWaitLostOutcome 仍保留在 public typed contract、waiting owner、WaitPollLost 和 authoritative provider tests。

invalid symbol guard：

    if rg -n 'mark_wait_record_poll_abandon_timeout|_MarkWaitRecordAbandonTimeoutOperation' dayu tests; then
      echo 'invalid timeout-only abandon terminal symbol remains' >&2
      exit 1
    fi

结果：PASS，production/tests 零定义、零调用。

schema no-diff：

    git diff --exit-code 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1 -- dayu/host/durable/schema.py

结果：PASS / empty diff。poll_abandoned_at schema 未删除或迁移。

### 6.2 Late publication fence

执行：

    rg -n '_start_observation|_invalidate_token|_publish|WaitObservationTokenState|generation|result_queue' \
      dayu/host/_wait_observation.py dayu/host/wait_adapter.py tests/host/test_wait_observation_runner.py

结果：token、generation、single-slot result_queue、invalidate 与 publish checks 仍全部位于 dayu/host/_wait_observation.py；adapter/store 没有新增第二 token、event、queue、future 或 late-result fallback。focused token test 通过。

### 6.3 Claim/backoff 真源

执行：

    rg -n '_release_with_backoff|_backoff_delay_seconds|release_wait_record_poll_claim|poll_next_observe_at|poll_backoff_attempt' \
      dayu/host/wait_adapter.py dayu/host/durable/state.py tests/host

结果与人工核对：

- 两个 timeout branch 均进入同一个 WaitPoller._release_with_backoff。
- 该 helper 唯一地计算 record.poll_backoff_attempt + 1，并调用现有 _backoff_delay_seconds。
- durable projection 唯一调用 release_wait_record_poll_claim。
- 没有 timeout-local 时间公式、raw field update 或第二 scheduler/policy。

### 6.4 Engine handshake no-diff

执行：

    rg -n 'tool_execution_timeout_seconds|await_or_cancel_or_timeout|ToolAwaitingOutcome|RUN_SUSPENDED' \
      dayu/engine/agent.py tests/engine/test_agent_phase3_tool_call.py
    git diff --exit-code 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1 -- dayu/engine/agent.py

结果：PASS / Engine empty diff。人工读取 agent.py 对应调用路径确认 timeout 只包住 _call_tool_executor / ToolExecutor.execute；BatchToolExecutionOutcome 返回后才解释 ToolAwaitingOutcome，accepted awaiting 后没有 timer reuse。aggregate matrix 中完整 Engine test file 已通过；未运行 R05-S2 smoke。

### 6.5 R04 config ownership

执行：

    rg -n 'awaiting_resolution_mode|wait_poller_policy' \
      dayu/config/tool_discovery.json dayu/config/host_runtime.json dayu/fins/tools dayu/service \
      dayu/config/prompts dayu/config/execution_profiles.json
    rg -n 'with_entrypoint_wait_poller_policy|_scene_selects_fins_awaiting_tools|WaitPollerRuntimePolicy\(\)' \
      dayu tests utils

结果：

- 三个 packaged provider mode 精确为 poll。
- host_runtime local policy 的 12 fields/value 精确保持 accepted plan snapshot：true、1、60、100、30、2、300、1、5、30、5、8。
- policy owner 仍为 config -> Service composition；prompt/execution profile 无 owner 命中。
- 第二条禁止项 scan 为零命中（rg exit 1，按预期 PASS）。

### 6.6 Expected no-diff 与 deferred scope

执行：

    git diff --exit-code 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1 -- \
      dayu/host/_wait_observation.py \
      dayu/host/waiting.py \
      dayu/engine/agent.py \
      dayu/host/durable/schema.py \
      dayu/host/dispatch.py \
      dayu/host/engine_ingest.py \
      tests/host/test_dispatch_scheduler.py

结果：PASS / 全部 empty diff。

执行 R05-S2、README、config/Service/Fins deferred-scope no-diff：

    git diff --exit-code 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1 -- \
      tests/engine/test_agent_phase3_tool_call.py \
      utils/smoke_host_public_awaiting_entrypoint.py \
      dayu/host/README.md \
      tests/README.md \
      dayu/engine/README.md \
      README.md \
      dayu/README.md \
      dayu/config \
      dayu/service \
      dayu/fins

结果：PASS / empty diff。Issue 175、callback transport、unified authorization、R05-S2 与 R06+ 均未进入本 slice。

## 7. Security、allowlist 与 diff

执行 production added-lines security/deferred scan：

    git diff --unified=0 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1 -- dayu \
      | rg -n 'authorization|permission|callback transport|process isolation|process_backed|subprocess|Issue 175'

结果：零命中（rg exit 1，按预期 PASS）。

focused matrix 重新通过，证明 cancellation、claim CAS、active/expired claim、capacity、shared close deadline 与 invalid deadline tests 未被删除或放宽。

执行：

    git diff --check
    git status --short
    git diff --name-only 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1
    git diff --stat 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1

结果：

- git diff --check：PASS。
- continuation artifact 创建前的 current uncommitted tracked paths 精确为七个受保护 paths；既有 implementation artifact保持 untracked。
- 相对 fixed plan base 的其它 docs/control/review paths全部属于已提交的 accepted plan / plan-correction evidence chain，不是本 continuation 写入。
- 本 continuation 唯一 durable write 是本 artifact；coverage/Ruff machine outputs 只位于 workspace/tmp。

## 8. README decision

已读取 dayu/host/README.md 的 Agent更新约束与 tests/README.md 的 README 更新边界。

- Host production contract 发生变化，最终 Host developer README 说明按 accepted plan 属于 R05-S2 acceptance；continuation task 明确禁止本轮更新 Host/tests README。S1 已在同一 semantic transaction 更新 docs/host/design.md 精确真源句，不提前制造中间 README contract。
- tests README 只记录稳定测试事实；R05 owner regression 与 public smoke 的最终说明同样由 accepted R05-S2 承担。本 S1 没有改变测试层级、通用运行方式或维护规则。
- Engine production no diff，现有 Engine README 已覆盖 handshake timeout 不证明底层工作停止；不机械更新。
- 根 README 与 dayu/README 没有用户入口、工作流、分层或装配 contract trigger。

决定：R05-S1 不更新任何 README；Host/tests README update 继续由 later approved R05-S2 覆盖，不是本 continuation 漏项。

## 9. Scheduler residual

原失败六元组保持：

1. exact command：原 full Host coverage command，只排除 tests/host/test_toolruntime_executor.py；
2. node：tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task；
3. error：HostApiError: Host execution is unavailable；
4. first stable frame：dayu/host/_execution_health.py:258 in raise_if_scheduler_unavailable；
5. fingerprint：scheduler close 已提交私有 close gate时，active worker clean EOF terminal closeout 同步 wake queue promotion，被 force health gate 拒绝；
6. validation HEAD：f52b81f9f4abd37a65c35ea98955a416079e5d9e plus preserved R05-S1 diff。

本 continuation 重新执行确定性 probe：

    source .venv/bin/activate
    python -m pytest -q workspace/tmp/test_r05_scheduler_close_probe.py

结果：

    1 passed in 0.31s

probe 以预期 HostApiError 为通过条件，证明 close gate -> clean EOF terminal closeout -> promotion wake rejection 的缺口仍可确定性复现。

同时执行：

    rg -n 'wait_adapter|WaitPoller|WaitObservation|WaitRecord|mark_wait_record_poll_abandon_timeout|release_wait_record_poll_claim' \
      tests/host/test_dispatch_scheduler.py

结果：零命中（rg exit 1，按预期 PASS）。

dispatch.py、engine_ingest.py 与 scheduler owner test 相对固定 base 均无 diff。final Controller adjudication 继续把它登记为 RETAINED RESIDUAL：已定位、未修、未 waive、未建 issue、未归 Issue 175。本 continuation 没有执行外部 issue mutation，也没有把 corrected coverage exclusion描述成修复或 inherited pass。

分类：requiring Controller / user destination decision 的独立 Host lifecycle residual；不属于 R05 timeout owner，不阻断修订计划已明确解耦的 S1 changed-owner coverage measurement。

## 10. Residual risks、uncovered areas 与下一入口

| Residual / uncovered area | 分类与 owner |
|---|---|
| scheduler close / terminal promotion coordination | RETAINED；Host scheduler lifecycle owner；未修、未 waiver、未建 issue、未归 Issue 175；destination 需 Controller / 用户另行裁决 |
| CANCELLED abandon observation 长期 timeout 且 provider 永不返回 explicit terminal outcome | RETAINED；future Host durable evidence policy owner；当前 claim CAS、capacity、finite timeout、late-result fence 与 capped backoff 只限制资源，不创造 terminal evidence |
| R05-S2 Engine regression/public smoke 与 Host/tests README final acceptance | covered by later approved R05-S2；本 continuation 明确未执行 |
| process-backed containment | tracked by existing Issue 175；与 scheduler residual、future durable evidence policy 均不同 owner |
| callback transport、unified authorization、R06+ | deferred to their own later WU/issue；本 slice 零实现 |

没有 unclassified R05-S1 validation risk，没有 required gate 被跳过或用旧证据替代。当前 verdict 为 PASS。唯一下一步是 Controller validation 本 continuation artifact；在 Controller PASS 前不得进入 R05-S2、code review、S1 product commit、aggregate、push 或 PR。

## 11. Continuation 结束完整性

本节在 artifact 创建后由最终命令复核：

    git diff --binary -- <seven protected paths> | shasum -a 256
    shasum -a 256 docs/reviews/wu-semantic-ownership-01-r05-s1-implementation-codex.md
    git diff --check
    git status --short

最终结果：

- seven-path digest：3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2，与 continuation 前和 protected value 精确相同。
- original implementation artifact SHA-256：b8ec89aafc6008587791958cb356f0124cec76199959f2ea3b62272ee3496732，与 continuation 前相同。
- git diff --check：PASS。
- current write allowlist：七个受保护 product/test/design paths、未修改的原 implementation artifact，以及本 continuation 唯一新增 artifact；没有其它 tracked/untracked path。
