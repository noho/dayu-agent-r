# Code Re-Review

## Scope

- Mode: current changes (corrective fix loop re-review)
- Branch: `codex/interactive-oracle`
- Base: `df99f858` entry HEAD
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-integration-corrective-code-rereview-mimo.md`
- Included scope: controller adjudication (`wu-cli-conformance-f01-f07-integration-corrective-controller-adjudication.md`), fix artifact (`wu-cli-conformance-f01-f07-integration-corrective-fix-codex.md`), updated implementation artifact (`wu-cli-conformance-f01-f07-integration-corrective-implementation-codex.md`), five corrective data/test files
- Excluded scope: S8 baseline READMEs, frozen registry, S8 implementation artifact, production code
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### DS-02 Closure — Dispatch Count Exact-Once 自足证明

**验证目标**: dispatch record 查询是否按 `(run_id, attempt_id)` 自足绑定，不隐含依赖单 Attempt policy。

- `tests/host/test_phase5_local_execution_integration.py:1582-1588` — SQL 已修正为：
  ```sql
  SELECT COUNT(*)
  FROM host_attempt_dispatch_records
  WHERE run_id = ? AND attempt_id = ?
  ```
  参数为 `(refs.run_id, refs.attempt_id)`；旧查询仅绑定 `(refs.run_id,)`。✓
- helper 已持有 `refs.attempt_id`（来自 `_refs()` 的 durable join），无需额外查询。✓
- 断言 `int(dispatch_count_row[0]) == 1` 现在精确统计目标 Attempt 的 dispatch record，即使未来 continuation policy 创建多个 Attempt 也不会误计。✓

**结论**: DS-02 完全关闭。

### DS-08 Closure — Five-File Fingerprint 与验证顺序

**验证目标**: 五个 corrective 文件的 SHA-256 是否与当前 working tree 重算一致；验证顺序是否确保 fingerprint 对应已验证的精确文件集合。

**Fingerprint 重算**:

| 文件 | artifact 声称 | 重算结果 | 状态 |
|---|---|---|---|
| `docs/cli_init_workspace_manifest_v1.json` | `c646c2a0...` | `c646c2a0...` | MATCH |
| `tests/cli/test_smoke_cli_init_provider_matrix.py` | `cd6fe484...` | `cd6fe484...` | MATCH |
| `tests/runtime/..._assembly.py` | `c2521212...` | `c2521212...` | MATCH |
| `tests/service/test_host_assembly.py` | `80c2c399...` | `80c2c399...` | MATCH |
| `tests/host/test_phase5_local_execution_integration.py` | `8e849638...` | `8e849638...` | MATCH |

**验证顺序** (implementation artifact §6.3):

1. DS-02 dispatch SQL fix applied → `tests/host/test_phase5_local_execution_integration.py` modified
2. Phase5 focused (9 passed) on fixed files
3. Four corrective focused (187 passed, 3 warnings) on fixed files
4. Complete suite (6571 passed, 10 skipped, 6 deselected, 3 warnings in 219.51s)
5. Changed Python Ruff (All checks passed!)
6. Full repository pyright (0 errors, 0 warnings, 0 informations)
7. JSON/diff/hash/status audit
8. Five-file SHA-256 computed from working tree
9. Implementation artifact updated with fingerprints (§6.3)
10. Fix artifact created

顺序保证：fingerprint 计算在所有验证之后、artifact 写入之前；artifact 写入不修改被验证文件。✓

**结论**: DS-08 完全关闭。

### Disposition Integrity — 未绕开其余裁决

逐项复核 controller adjudication 中被驳回或关闭的 finding，确认 fix loop 未实现任何被禁止的改动：

| ID | Disposition | 未绕开验证 |
|---|---|---|
| DS-01 | REJECT-NON-ACTIONABLE | `_assert_exactly_once_dispatch_outcome` 仍用 tuple index 读取 SQL 结果，未改 row factory。✓ |
| DS-03 | REJECT-OUT-OF-SLICE | `test_queue_promotion_after_terminal_and_cancel_wakes_dispatch` 仍包含 terminal + cancel 双场景，未拆分。✓ |
| DS-04 | REJECT-ALREADY-EXPLICIT | promoted 场景仍用 `expected_factory_creations=2` 累计值，未改为 per-run 计数。✓ |
| DS-05 | CLOSED-BY-DIRECT-EVIDENCE | 无修改需要。✓ |
| DS-06 | REJECT-BY-DESIGN | helper 仍同时断言 public `get_run` 与 raw SQLite，未删除 durable 侧检查。✓ |
| DS-07 | REJECT-FALSE-CONTRACT-INFERENCE | fake compactor 生成策略未修改。✓ |
| DS-09 | CLOSED-CORRECT | implementation artifact 仍区分 changed Python Ruff（已绿）与 full-repository 97 debt（非 blocker）。✓ |
| DS-10 | CLOSED-CORRECT | 三个 package SHA-256 未变。✓ |
| DS-11 | CLOSED-CORRECT | system/user prompt 边界断言未变。✓ |
| MiMo-R1 | RESIDUAL-OWNER-ASSIGNED | 无修改需要。✓ |

**结论**: fix loop 仅实现了 DS-02 和 DS-08，未绕开任何被驳回或关闭的 disposition。

### Production / Frozen / S8 Baseline Integrity

- `dayu/` 非 README working-tree delta: **零**。✓
- `docs/cli_ci_oracles.json` SHA-256: `f9972d94...` — 与 fix artifact 声称一致。✓
- `docs/cli_ci_scenarios.json` SHA-256: `7f283b03...` — 与 fix artifact 声称一致。✓
- `README.md` SHA-256: `ce5d0a9c...` — 匹配。✓
- `dayu/host/README.md` SHA-256: `3ba963ff...` — 匹配。✓
- `dayu/config/README.md` SHA-256: `0700d670...` — 匹配。✓
- `tests/README.md` SHA-256: `b2b6e60e...` — 匹配。✓
- S8 implementation artifact (`wu-cli-conformance-f01-f07-s8-implementation-codex.md`) SHA-256: `5c7b9031...` — 匹配。✓
- Index: 空，未 stage。✓

**结论**: 无 production 变更，所有 protected baseline 完整。

### Validation Record 一致性

fix artifact §3 声称的验证结果与 implementation artifact §6 最终记录一致：

| Gate | Fix artifact | Implementation artifact | 一致 |
|---|---|---|---|
| Phase5 focused | 9 passed | 9 passed | ✓ |
| 四类 corrective focused | 187 passed, 3 warnings | 187 passed, 3 warnings | ✓ |
| 完整 suite | 6571 passed, 10 skipped, 6 deselected, 3 warnings in 219.51s | 6571 passed, 10 skipped, 6 deselected, 3 warnings in 219.51s | ✓ |
| Changed Python Ruff | All checks passed! | All checks passed! | ✓ |
| Full repository pyright | 0 errors, 0 warnings, 0 informations | 0 errors, 0 warnings, 0 informations | ✓ |

## Open Questions

无。

## Residual Risk

- MiMo-R1（scheduler 未来改 barrier 时需同步测试）仍为 `RESIDUAL-OWNER-ASSIGNED`，非当前 blocker。
- cancel-watchdog / SIGKILL recovery 偶发现象仍为 `assigned to later S8 validation owner`。
- full-repository Ruff 97 debt 仍为 `assigned to later work unit`。
