# WU-CLI-FINS-OBS-01 Final Closeout

## 结论

`WU-CLI-FINS-OBS-01` replacement implementation 已完成本地 final closeout。用户裁决的两个核心更正均已落地：

- CLI direct commands 使用普通 `AsyncIterator[FinsEvent]` live stream，不再通过 durable job id、sidecar JSONL、cursor 或 `request_cancel(job_id)` 传递事件。
- Fins awaiting tools 保留 `ToolAwaitingOutcome(EXTERNAL_JOB)` 非阻塞语义，但 await ref 收敛为轻量 `FinsObservationHandle`，不把 Fins ingestion runtime 强行升级为 durable job system。

Aggregate deepreview 中 AgentMiMo 发现的 BF-1 已修复并通过两路 re-review。当前没有 blocking finding。

## Accepted Commits

- `f79b59ab`：Slice A/B，Fins direct stream contract 与 CLI direct consumer。
- `a90d86aa`：Slice D0，lightweight observation handle contract。
- `11fd5e97`：Slice C，Fins direct ingestion runtime。
- `0b25416d`：Slice D，Fins awaiting tools / wait adapter 迁移到 lightweight observation。
- `044a966d`：Slice E，README / tests / control doc 同步。
- `f83fd497`：aggregate deepreview BF-1 fix、re-review artifacts、control-doc final closeout 与 residual reconciliation。

## Aggregate Review

- AgentDS aggregate deepreview：`docs/reviews/wu-cli-fins-obs-01-aggregate-deepreview-ds-20260616.md`，PASS。
- AgentMiMo aggregate deepreview：`docs/reviews/wu-cli-fins-obs-01-aggregate-deepreview-mimo-20260616.md`，发现 BF-1。
- BF-1：`tests/service/test_import_boundary.py` 未把 `dayu.fins.direct_events` 加入 Service public boundary allowlist，导致架构守护测试误判。
- Fix：`docs/reviews/wu-cli-fins-obs-01-aggregate-fix-codex-20260616.md`。
- Re-review：`docs/reviews/wu-cli-fins-obs-01-aggregate-fix-rereview-mimo-20260616.md` 与 `docs/reviews/wu-cli-fins-obs-01-aggregate-fix-rereview-ds-20260616.md` 均 PASS。

## Final Validation

```bash
pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py tests/service/test_import_boundary.py tests/cli/test_upload_filings_from_command.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_arg_parsing.py -q
# 282 passed, 3 warnings

pyright dayu/ tests/ utils/
# 0 errors, 0 warnings

git diff --check
# clean
```

Warnings are third-party `edgar` deprecation warnings already observed in prior slice validation.

## Residual Risk Reconciliation

Remaining active residuals:

- None after `WU-CLI-FINS-DIAG-01`.

Closed and removed from the active residual table:

- `WU-CLI-FINS-OBS-01-R3`：`WU-CLI-FINS-DIAG-01` 已确认当前项目真正敏感项仅限 `dayu/config/models.json` 引用的 API key；CLI/Fins output 不再把路径、document label、provider diagnostic summary 或业务摘要默认当 secret 脱敏，仍保留有界展示。
- `WU-CLI-FINS-OBS-01-R5`：`WU-CLI-FINS-DIAG-01` 已把 runtime/CLI diagnostic logs 移到 stderr，stdout 保持为用户 UI / command result 通道；prompt / interactive 用户可见 activity stream 仍转入 GitHub Issue #144。
- `WU-CLI-FINS-OBS-01-R6`：Slice A/B 与 Slice C review 已确认 direct event / runtime direct boundary 没有 reintroduce job sidecar。
- `WU-CLI-FINS-OBS-01-R7`：Slice D0 review 已确认 observation handle contract-only checkpoint 未越界扩张。
- `WU-CLI-FINS-OBS-01-R8`：Slice D review 已确认 process-local observation registry concurrency 由 `_observation_lock` 保护。
- `WU-CLI-FINS-OBS-01-R9`：Slice D review 已确认 wait adapter 的 `TRANSIENT_UNAVAILABLE` bounded pending 与 corrupt / missing handle LOST recovery。
- `WU-CLI-FINS-OBS-01-R10`：代码复核与用户裁决确认该项不是 active residual；observed path 使用进程内 `Queue(maxsize=32)` 和 process-local poll，同进程内存进出消费只形成有界背压保护，不构成需要 production poller/backoff work unit 追踪的独立风险。

Transferred follow-up:

- CLI session management transferred to GitHub Issue #145. Future work should remove obsolete `interactive --new-session`, keep fresh anonymous sessions as the default when `--label` is absent, keep ensure-by-label semantics for `--label`, and add explicit `resume` / `list` / `purge`.

## Next Entry

当前 work unit 本地完成。总控默认 next entry point 回到 backlog 选择；默认下一条为 `WU-OBS-00` 的 GitHub Issue / dependency / code scope discussion。
