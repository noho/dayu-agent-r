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

- `WU-CLI-FINS-OBS-01-R3`：deferred to future CLI/Fins UI output redaction policy work unit。
- `WU-CLI-FINS-OBS-01-R5`：deferred to future Agent command streaming / UI work unit。
- `WU-CLI-FINS-OBS-01-R10`：deferred to future production poller / wait backoff work unit；当前 lightweight process-local observation contract 下可接受。

Closed and removed from the active residual table:

- `WU-CLI-FINS-OBS-01-R6`：Slice A/B 与 Slice C review 已确认 direct event / runtime direct boundary 没有 reintroduce job sidecar。
- `WU-CLI-FINS-OBS-01-R7`：Slice D0 review 已确认 observation handle contract-only checkpoint 未越界扩张。
- `WU-CLI-FINS-OBS-01-R8`：Slice D review 已确认 process-local observation registry concurrency 由 `_observation_lock` 保护。
- `WU-CLI-FINS-OBS-01-R9`：Slice D review 已确认 wait adapter 的 `TRANSIENT_UNAVAILABLE` bounded pending 与 corrupt / missing handle LOST recovery。

## Next Entry

当前 work unit 本地完成。总控默认 next entry point 回到 backlog 选择；默认下一条为 `WU-OBS-00` 的 GitHub Issue / dependency / code scope discussion。
