# Code Review — WU-SEMANTIC-OWNERSHIP-01 P3-K S2 Fix Re-review

## Scope

- Mode: current changes (fix re-review)
- Branch: `phaseflow/host-issues-control`
- Base: `b5bcf767`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-k-s2-rereview-mimo.md`
- Included scope:
  - `tests/host/recovery_support.py` — fix for `P3-K-S2-CR-F01`
- Excluded scope: all production code, S1/S3 files, control docs, README, broader refactor
- Review gate: S2 fix re-review by AgentMiMo

## Finding Re-review

### P3-K-S2-CR-F01 — `_HOST_DB_FILENAME` 常量未覆盖 `attempt_count_for_run` 和 `current_attempt_id_for_run`

**判定：已修复。**

逐项验证：

#### 1. 两个 path join 是否已改用 `_HOST_DB_FILENAME`

**通过。** `git diff b5bcf767 -- tests/host/recovery_support.py` 确认：

- `attempt_count_for_run`（原 line 765）：`sqlite3.connect(root_path / "host.sqlite3")` → `sqlite3.connect(root_path / _HOST_DB_FILENAME)`
- `current_attempt_id_for_run`（原 line 787）：`sqlite3.connect(root_path / "host.sqlite3")` → `sqlite3.connect(root_path / _HOST_DB_FILENAME)`

两处变更均为纯字符串 → 常量替换，SQL 语义不变。

#### 2. `rg` 扫描结果是否充分

**通过。** `rg -n '"host\.sqlite3"' tests/host/recovery_support.py` 返回：

```
67:_HOST_DB_FILENAME = "host.sqlite3"
```

literal `"host.sqlite3"` 仅存在于 `_HOST_DB_FILENAME` 常量定义行。全部 6 个 SQLite 连接路径（line 674, 710, 744, 765, 787, 806）均使用 `_HOST_DB_FILENAME`。

#### 3. 验证命令是否覆盖变更且仍然通过

**通过。** Fix artifact 与 controller validation 均记录：

- `rg -n '"host\.sqlite3"|_HOST_DB_FILENAME' tests/host/recovery_support.py` — pass
- `pytest tests/host/test_recovery_multiprocess.py tests/host/test_admission_multiprocess.py -q` — `9 passed`
- `python -m pyright dayu/ tests/ utils/` — `0 errors, 0 warnings, 0 informations`
- `git diff --check` — pass

#### 4. 是否引入了生产代码、S1/S3 文件、control doc、README 或 broad raw SQL 重构

**通过。**

- `git diff b5bcf767 --name-only` 显示变更文件为：`AGENTS.md`、`CLAUDE.md`、`tests/host/public_smoke_support.py`、`tests/host/recovery_support.py`、`tests/host/stress_support.py`。
- 其中 `AGENTS.md`、`CLAUDE.md`、`public_smoke_support.py`、`stress_support.py` 的变更属于 S2 主体变更，不在本 fix scope 内。fix 本身只修改 `recovery_support.py` 中的两行 path join。
- 未修改任何 `dayu/` 下的生产代码。
- 未修改 S1 allowed files（`test_memory_projection.py`、`test_tool_result_envelope.py`、`test_run_input_builder.py`、`test_engine_event_contract.py`）。
- 未修改 S3 allowed files（`fake_cancellation.py`、`runners/openai/_fakes.py`、`test_fins_direct.py`、`fake_compaction.py`、`memory_snapshot_factories.py`）。
- 未修改 control doc 或 README。
- 未引入 broad raw SQL 重构；变更仅将两个 literal 字符串替换为已有模块常量。

#### 5. 是否引入新的 material issue

**未发现。**

变更本质是 `str` literal → module-level constant 的纯替换。常量 `_HOST_DB_FILENAME = "host.sqlite3"` 在模块作用域内定义（line 67），两个函数均在同模块内，作用域可见性无问题。SQL 语句、参数、返回值处理均未变更。

## Findings

未发现实质性问题。

## Open Questions

- 无。

## Residual Risk

- 无本轮新增 residual risk。
- S2 主体 review 中标记的 stress 残留失败（`test_sustained_watch_slow_consumer_reconnect_stress`、`test_scheduler_liveness_long_run_mixed_flow_stress`）仍属于后续独立 work unit，不在本 fix scope 内。

## Verdict

**PASS.** `P3-K-S2-CR-F01` 已修复。两个受影响函数的 path join 已统一使用 `_HOST_DB_FILENAME`，`rg` 扫描确认 literal 仅存于常量定义，验证命令全部通过，未引入新 issue 或 regression。
