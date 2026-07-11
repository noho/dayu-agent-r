# Code Re-Review — WU-SEMANTIC-OWNERSHIP-01 P3-K S2 Fix

## Scope

- Mode: re-review（fix verification）
- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-K`
- Gate: S2 code-review fix re-review
- Accepted finding: `P3-K-S2-CR-F01`
- Source review artifact: `docs/reviews/wu-semantic-ownership-01-p3-k-s2-code-review-ds.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-k-s2-fix-codex.md`
- Controller fix validation: `docs/reviews/wu-semantic-ownership-01-p3-k-s2-fix-controller-validation.md`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-k-s2-rereview-ds.md`
- Branch: `phaseflow/host-issues-control`
- Base: `b5bcf767`
- Included scope: `tests/host/recovery_support.py` — fix for `_HOST_DB_FILENAME` usage in `attempt_count_for_run` and `current_attempt_id_for_run`
- Excluded scope: S1/S3 files, production code (`dayu/`), control doc, README, raw SQL refactor, other S2 findings already adjudicated in original review

## Re-Review Focus 逐项证据

### 1. `attempt_count_for_run` 和 `current_attempt_id_for_run` 是否使用 `_HOST_DB_FILENAME`

**通过。** 两个函数均已修复：

- `attempt_count_for_run`（line 765）：`sqlite3.connect(root_path / _HOST_DB_FILENAME)` ✅
- `current_attempt_id_for_run`（line 787）：`sqlite3.connect(root_path / _HOST_DB_FILENAME)` ✅

旧代码使用字面量 `"host.sqlite3"`，新代码统一使用模块级常量 `_HOST_DB_FILENAME`（line 67）。

### 2. `rg` 扫描：`recovery_support.py` 中 `"host.sqlite3"` 字面量仅剩常量定义

**通过。**

```
$ rg -n '"host\.sqlite3"' tests/host/recovery_support.py
67:_HOST_DB_FILENAME = "host.sqlite3"
```

仅一行匹配 — 即常量定义本身。文件中所有 6 处 SQLite 连接路径均通过 `_HOST_DB_FILENAME`：

| 行号 | 函数 | 用法 |
|------|------|------|
| 674 | `force_owner_pid_missing_and_heartbeat_stale` | `root_path / _HOST_DB_FILENAME` |
| 710 | `force_memory_projection_lag` | `root_path / _HOST_DB_FILENAME` |
| 744 | `event_type_count` | `root_path / _HOST_DB_FILENAME` |
| 765 | `attempt_count_for_run` | `root_path / _HOST_DB_FILENAME` |
| 787 | `current_attempt_id_for_run` | `root_path / _HOST_DB_FILENAME` |
| 806 | `projection_checkpoint_sequence` | `db_path=root_path / _HOST_DB_FILENAME` |

### 3. 验证命令覆盖且通过

**全部通过。**

- `pytest tests/host/test_recovery_multiprocess.py tests/host/test_admission_multiprocess.py -q` → `9 passed in 5.70s` ✅
- `python -m pyright dayu/ tests/ utils/` → `0 errors, 0 warnings, 0 informations` ✅
- `rg -n '"host\.sqlite3"' tests/host/recovery_support.py` → 仅常量定义（line 67）✅

### 4. 无生产代码、S1/S3 文件、control doc、README 或 raw SQL 重构

**通过。**

- `git diff --name-only` 输出：`AGENTS.md`, `CLAUDE.md`, `tests/host/public_smoke_support.py`, `tests/host/recovery_support.py`, `tests/host/stress_support.py`
- `git diff --name-only -- 'dayu/'` → 无输出（无生产代码变更）✅
- `public_smoke_support.py` 和 `stress_support.py` 的 diff 仅包含 S2 docstring 分类标记（`diagnostic-only：` 前缀），无代码逻辑变更 ✅
- 未新增 S1/S3 文件，未修改 control doc 或 README ✅

### 5. 无新增实质性缺陷

**通过。** 本次修复仅做字符串常量替换：`"host.sqlite3"` → `_HOST_DB_FILENAME`。不改变 SQL 语义、连接行为、事务语义、错误处理或函数签名。零回归风险。

## Findings

### P3-K-S2-CR-F01 — 已修复

- **原始 finding**: `_HOST_DB_FILENAME` 常量已引入但 `attempt_count_for_run` 和 `current_attempt_id_for_run` 仍使用字面量 `"host.sqlite3"`
- **修复内容**: 两个函数的 `sqlite3.connect(root_path / "host.sqlite3")` 改为 `sqlite3.connect(root_path / _HOST_DB_FILENAME)`
- **直接证据**: `recovery_support.py:765` 和 `recovery_support.py:787` 均使用 `_HOST_DB_FILENAME`
- **rg 扫描确认**: 文件中 `"host.sqlite3"` 字面量仅在 line 67 常量定义处出现
- **测试验证**: 9 passed, pyright 0 errors
- **判定**: **已修复**

无其他 findings。

## Open Questions

- 无。

## Residual Risk

- **其他测试文件中的 `"host.sqlite3"` 字面量**：`rg` 全量扫描显示 `tests/host/` 下仍有约 30 处其他测试文件使用字面量 `"host.sqlite3"`（如 `test_public_lifecycle_smoke.py`、`test_open_host_runtime.py`、`test_command_handle.py` 等）。这些文件不在 P3-K S2 scope 内，且各自在局部构造 `HostDurableStoreOptions(db_path=tmp_path / "host.sqlite3", ...)` 时不依赖 `recovery_support.py` 的 `_HOST_DB_FILENAME`。不属于本次 fix 的 regression，但若将来统一 DB 文件名，需要逐文件处理。
- **Stress 残留失败**：原始 code review 中记录的 stress 失败（`test_sustained_watch_slow_consumer_reconnect_stress`、`test_scheduler_liveness_long_run_mixed_flow_stress`）与本次修复无关，属于 production dispatch/scheduler 路径的 pre-existing issue，不在本 re-review scope 内。

## Verdict

**PASS.** `P3-K-S2-CR-F01` 已完整修复。两个 target 函数 `attempt_count_for_run` 和 `current_attempt_id_for_run` 均使用 `_HOST_DB_FILENAME`。`rg` 扫描确认文件中 `"host.sqlite3"` 字面量仅剩常量定义。测试通过（9 passed），pyright 通过（0 errors）。无生产代码、S1/S3 文件、control doc 或 README 变更。无新增实质性缺陷或回归。
