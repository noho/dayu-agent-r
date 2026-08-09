# WU CLI Conformance F01-F07 — Integration Corrective Fix

## 1. Gate 与范围

- Gate：corrective implementation fix loop。
- Work unit：PR 190 / WU CLI Conformance F01-F07。
- Entry HEAD：`df99f858c6e01d3555eb5c16c3358160909a1f1a`。
- Controller adjudication：`FIX-LOOP-REQUIRED`。
- 接受项：仅 DS-02、DS-08。
- 状态：`READY-FOR-CONTROLLER-REREVIEW`。
- Next entry：handoff 给总控进入 corrective re-review；本 artifact 不宣称 re-review 已通过。
- Artifact path：`docs/reviews/wu-cli-conformance-f01-f07-integration-corrective-fix-codex.md`。

本 fix loop 没有 stage、commit、push 或 PR 操作，也没有修改 production、frozen registry、S8 owner
README、S8 implementation artifact、fake compactor、既有测试拆分或其他被驳回的 DS 建议。

## 2. 接受项 closure

### DS-02 — closed

`tests/host/test_phase5_local_execution_integration.py` 的 durable dispatch-record exact-once 查询从只按
`run_id` 计数，最小修正为同时按 `run_id` 与 `refs.attempt_id` 计数。helper 已持有这两个 owner ref，
因此目标 Attempt 的 exact-once assertion 现在自足，不再隐含依赖当前单 Attempt policy。

### DS-08 — closed

implementation artifact 初版在原 implementation validation 后创建。最终 SQL 修正与本 fix loop 的
全部验证完成后，才计算五个 corrective data/test 文件的 working-tree SHA-256；随后才把 fingerprint
写入 implementation artifact 并创建本 fix artifact。因而完整 suite、full pyright、focused tests、
changed Ruff 与审计均对应同一精确文件集合，artifact 写入不会改变该集合。

| validated working-tree file | SHA-256 |
|---|---|
| `docs/cli_init_workspace_manifest_v1.json` | `c646c2a0c7b508f8cc07d7f446273fb37117a8b1d9e47da82bf09f32e9dfd65e` |
| `tests/cli/test_smoke_cli_init_provider_matrix.py` | `cd6fe484080290a7ec66a70449697cb49e7fef7bb3c125fd0bb5240a4beaaad4` |
| `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` | `c2521212c5705b68cfcdd5bc59cc24fd22ff9be45f36b80a78c2098885c2c991` |
| `tests/service/test_host_assembly.py` | `80c2c399c9a84ab63d95d4ffbdb9220edf4dc3df04248fd260f25cadfd47c884` |
| `tests/host/test_phase5_local_execution_integration.py` | `8e84963898076b851496a51785d5c8038baf4546f448b0eb7f6bdb800fdcef83` |

## 3. Validation

全部 Python 命令均在 `source .venv/bin/activate` 后运行。

| Gate | Result |
|---|---|
| Phase5 focused | `9 passed` |
| 四类 corrective focused | `187 passed, 3 warnings` |
| 完整 suite | `6571 passed, 10 skipped, 6 deselected, 3 warnings in 219.51s` |
| Changed Python Ruff | `All checks passed!` |
| Full repository pyright | `0 errors, 0 warnings, 0 informations` |
| JSON parse | publication manifest 与两个 frozen registry 全部通过 |
| `git diff --check` | 通过 |
| Production scope audit | 除受保护 README 外，`dayu/` 零 working-tree delta |
| Index audit | 空；未 stage |

三条 pytest warning 均来自 `edgar` 依赖的 deprecation warning，不属于当前改动。

## 4. Protected-state audit

- `docs/cli_ci_oracles.json`：`f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`。
- `docs/cli_ci_scenarios.json`：`7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`。
- `README.md`：`ce5d0a9c850b6978da7393c789c378b353c2397c0b1c4a2c4b2c475aac5c6003`。
- `dayu/host/README.md`：`3ba963ff0b9cc960c68a6464ec14ab33c1ad8374b3f9e6324b9a97759c7e7317`。
- `dayu/config/README.md`：`0700d6709f7c239a499f6e221daefcedba32ea46c8f430484e56e02aa0310812`。
- `tests/README.md`：`b2b6e60e5525f888a28434661f6a2dbc2f328acdcf4d9579547fb933e0219c28`。
- S8 implementation artifact：`5c7b90314c489e84d7fcea7eb59ae2d1df408cf190a2626a3ae049963a411ebb`。

## 5. Residual risk 与 handoff

本 fix loop 没有发现稳定 production defect，也没有改变 controller 对 DS-01、DS-03–DS-07、DS-09–
DS-11 或 MiMo-R1 的 disposition。既有 cancel-watchdog/recovery 偶发现象、full-repository Ruff 97 与
后续 real-evidence acquisition 的 owner/disposition 均保持 implementation artifact 原记录。

DS-02/DS-08 已关闭，handoff 给总控进入 corrective re-review；全 work unit 仅 final closeout 停止，
中间 gate 不停。
