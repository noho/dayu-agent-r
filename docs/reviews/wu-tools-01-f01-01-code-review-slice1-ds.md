# WU-TOOLS-01-F01-01 Slice 1 Code Review — AgentDS

## Verdict

**pass-with-findings**

Slice 1 实现精确完成了 ingestion job store 的 filelock convergence，未触碰 storage batch 或 `dayu/fins/_file_lock.py`，未引入 wrapper/facade/compatibility export。1 个 medium finding（docstring 缺口），plan 已预见的 R1 风险未在实现中收尾。无 blocking finding。

## Plan / Slice Conformance Checklist

| # | 检查项 | 结果 |
|---|--------|------|
| 1 | 只改 Slice 1 allowed files | PASS — 仅 `dayu/fins/ingestion_runtime.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/README.md`、`docs/host/issues-implementation-control.md`（gate bookkeeping only） |
| 2 | 未触碰 storage batch | PASS — `dayu/fins/storage/_fs_storage_infra.py` 未改 |
| 3 | 未触碰 `dayu/fins/_file_lock.py` | PASS |
| 4 | 删除 `import fcntl` | PASS |
| 5 | 添加 `from dayu.runtime.filelock import file_lock` | PASS — 只 import factory function，不 import `FileLock`、`RuntimeFileLockToken` 等 |
| 6 | 6 个 `.store.lock` 临界区直接使用 `file_lock()` | PASS — `create_job`(L702)、`save_job`(L724)、`save_succeeded_or_cancelled`(L755)、`claim_running_or_cancelled`(L803)、`read_job`(L841)、`request_cancel`(L860) |
| 7 | 删除 `_StoreFileLock` 类 | PASS — 原 L1945-2010 已删除 |
| 8 | 删除 `TracebackType`、`TextIO` import | PASS |
| 9 | 未新增 Fins wrapper / facade / compatibility export | PASS |
| 10 | job schema 不变 | PASS — `FinsIngestionJobRecord`、`_record_to_json`、`_record_from_json` 未改 |
| 11 | 状态机不变 | PASS — `FinsIngestionJobStatus`、`_TERMINAL_STATUSES` 未改 |
| 12 | job 路径不变 | PASS — `_LOCK_FILE_NAME` = `.store.lock`、`_job_path` 未改 |
| 13 | atomic replace 不变 | PASS — `_write_record_locked`、`_read_record_locked` 未改 |
| 14 | 读写顺序不变 | PASS — 所有方法仍在持锁后 read/modify/write |
| 15 | 删除 `test_store_file_lock_closes_stream_when_flock_fails` | PASS — 已删除 |
| 16 | 删除理由充分 | PASS — Fins 不再管理 lock stream/fd；runtime filelock 覆盖对应生命周期语义 |
| 17 | 未保留私有测试入口 | PASS — `_StoreFileLock` import 已从 test 文件删除 |
| 18 | tests/README.md 更新符合事实 | PASS — 仅删除 "文件锁失败关闭"，未做机械同步 |
| 19 | control document 仅 gate bookkeeping | PASS — gate → code review，status 更新，未修改实现真源 |
| 20 | `rg "_StoreFileLock\|import fcntl\|ingestion_runtime\.fcntl"` 零命中 | PASS |
| 21 | pyright 0 errors | PASS |
| 22 | `git diff --check` 通过 | PASS |
| 23 | tests 26 passed | PASS |
| 24 | runtime filelock + import boundary tests 23 passed | PASS |

## Findings

### F1 — Docstring 缺口：`RuntimeFileLockError` 未进入 Raises（Medium）

- **文件**: `dayu/fins/ingestion_runtime.py`
- **位置**: `FsFinsIngestionJobStore` 的 6 个公共方法（`create_job` L698、`save_job` L720、`save_succeeded_or_cancelled` L750、`claim_running_or_cancelled` L799、`read_job` L837、`request_cancel` L856）
- **影响**: 旧 `_StoreFileLock.__enter__` 在 `flock` 失败时抛 `OSError`，新 `file_lock()` 在 acquire 失败时抛 `RuntimeFileLockError`（非 `OSError` 子类）。当前 docstring 的 `Raises: OSError: 文件系统写入失败时抛出` 仍正确描述 `_write_record_locked` / `_read_record_locked` 的 I/O 路径，但未声明 `RuntimeFileLockError` 来自锁获取路径。调用方若仅按 docstring 捕获 `OSError`，锁获取失败将以未预期异常类型逃逸。
- **建议修复方向**: 在 6 个方法的 Raises 中补充 `RuntimeFileLockError: 文件锁获取失败时抛出。`。该类型已在 `dayu.runtime.filelock` 中作为公共 API 导出，直接引用不违反 import boundary。
- **裁决**: **accepted** — plan 已列为风险 R1，实现 agent 未在 Slice 1 中处理。建议在 Slice 2 或 Slice 3 收尾。
- **严重性**: Medium。不影响功能正确性（异常会正确传播，只是类型未文档化），但影响 API 契约的可读性。

## Validation Performed

| 验证项 | 命令 | 结果 |
|--------|------|------|
| Fins ingestion runtime tests | `pytest tests/fins/test_fins_ingestion_runtime.py -q` | 26 passed |
| Runtime filelock tests | `pytest tests/runtime/test_filelock.py -q` | 通过 |
| Runtime import boundary tests | `pytest tests/runtime/test_import_boundary.py -q` | 通过 |
| pyright on changed files | `pyright dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py` | 0 errors |
| pyright full | `pyright` | 0 errors |
| Reference cleanup | `rg "_StoreFileLock\|import fcntl\|ingestion_runtime\.fcntl" dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py` | 0 hits |
| Whitespace | `git diff --check` | 无错误 |
| Design doc alignment | 读取 `docs/host/design.md`、`docs/engine/design.md` | 无冲突 |
| Plan alignment | 读取 `docs/host/wu-tools-01-f01-01-filelock-plan.md` | Slice 1 范围内完全一致 |
| Implementation artifact review | 读取 `docs/reviews/wu-tools-01-f01-01-implementation-slice1-codex.md` | 验证记录可信；26 passed / pyright 0 errors 已被独立复现 |

## Residual Risks and Uncovered Areas

| # | 风险 | 分类 | Owner / Destination |
|---|------|------|---------------------|
| R1 | `RuntimeFileLockError` 不是 `OSError` 子类，docstring 缺口 | Low | Slice 2 或 Slice 3 收尾（plan R1） |
| R2 | Ingestion job store 无 dedicated lock acquisition failure 测试 | Low | 当前 job store 行为测试在真实文件系统上运行，lock acquisition 实际上总是成功。若需要验证 lock failure 路径，可在 future slice 加 monkeypatch 测试 |
| R3 | Storage batch convergence（Slice 2）未在本 slice 验证 | Deferred | Slice 2 |
| R4 | `dayu/fins/_file_lock.py` 删除（Slice 3）未在本 slice 验证 | Deferred | Slice 3 |

## Blocking Open Questions

无。

## Implementation Artifact 可信度评估

`docs/reviews/wu-tools-01-f01-01-implementation-slice1-codex.md` 的验证记录已独立复现：
- 26 passed / pyright 0 errors / rg 零命中 / git diff --check 通过 — 均与独立运行结果一致
- 声明 "未修改 storage batch 代码" 和 "未修改 `dayu/fins/_file_lock.py`" — 经 diff 审查确认属实
- 声明 "未新增 Fins wrapper / facade" — 经代码审查确认属实

Implementation artifact 记录的删除理由（"Fins ingestion job store 不再打开 lock TextIO / stream，也不再直接管理 fd lifecycle"）经审查成立。

唯一的遗漏是 plan R1（docstring 更新），implementation artifact 未提及是否处理该风险，也未说明为何跳过。这不影响 implementation artifact 的核心验证可信度，但应在当前 review 中记为 finding。
