# WU-CM-01 Slice C Fix Re-Review - Controller Adjudication

## 裁决

- Gate: WU-CM-01 Slice C fix re-review
- Verdict: pass
- Next gate: accepted slice commit

Controller 接受 Slice C implementation + fix。两路 re-review 均为 pass，code review accepted findings F-1 / F-2 / F-3 已关闭，无新增 blocking finding。

## Accepted Findings Closure

- F-1 `host_assembly` context window truth：已修复。`_memory_projection_policy_from_config` 使用 effective model-derived `context_window_size` 参数，并由 service assembly test 覆盖 profile policy window 与 model window 不一致的场景。
- F-2 duplicate section owner dedicated coverage：已修复。`tests/host/test_compact_material.py` 保留 vNext no-old-goal bridge 测试，并新增 public builder 路径的 `DuplicateMaterialSectionOwnerError` 覆盖。
- F-3 vNext budget limiting coverage：已修复。`tests/host/test_memory_projection.py` 新增 evidence fact budget cap 截断与 `BUDGET_LIMIT_REACHED` diagnostic 覆盖。

## Deferred / Rejected Items

- compact artifact message reader vNext-aware cleanup：deferred-with-owner，后续 RunInput / compact artifact cleanup slice。
- `_memory_messages` `del policy` cleanup：rejected-with-reason，低价值清理。
- `_snapshot_with_goal` helper API cleanup：rejected-with-reason，测试可读性清理。
- old schema_version explicit rejection message：rejected-with-reason，fresh schema fail-closed 足够。

## Controller Validation

已在 controller 侧复验：

```bash
source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/host/test_durable_schema.py tests/host/test_projection_checkpoint.py tests/host/test_durable_concurrency_matrix.py tests/host/test_memory_repair.py -q
```

结果：`63 passed`

```bash
source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_recovery_dispatch.py tests/host/test_engine_ingest_mapping.py -q
```

结果：`168 passed`

```bash
source .venv/bin/activate && pytest tests/host/test_admission_queue.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_resolve_wait_command.py -q
```

结果：`59 passed`

```bash
source .venv/bin/activate && pytest tests/service/test_host_assembly.py tests/runtime/test_config_loader.py -q
```

结果：`67 passed`

```bash
source .venv/bin/activate && pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py -q
```

结果：`10 passed, 1 skipped`

```bash
source .venv/bin/activate && pytest tests/host/test_public_contracts.py tests/host/test_public_tool_wiring_smoke.py -q
```

结果：`42 passed`

```bash
source .venv/bin/activate && python -m json.tool dayu/config/execution_profiles.json >/dev/null
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
git diff --check
```

结果：JSON valid；pyright `0 errors, 0 warnings, 0 informations`；diff check clean。

## Residual Risk

- Deferred cleanup：compact artifact message path 仍可后续替换为 vNext-aware reader；当前旧 reader 对缺字段返回空值，不阻塞 Slice C acceptance。
- Optional real-provider behavior 未运行；保持既有 optional smoke owner，不作为 Slice C blocker。
