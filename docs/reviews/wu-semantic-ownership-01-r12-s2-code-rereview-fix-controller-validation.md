# WU-SEMANTIC-OWNERSHIP-01 / R12 S2 re-review fix Controller validation

## 结论

`PASS / READY FOR DUAL COMPLETE CUMULATIVE RE-REVIEW`。

AgentCodex 仅修改既定 environment/CLI owner 与对应测试，并产出 `docs/reviews/wu-semantic-ownership-01-r12-s2-code-rereview-fix-codex.md`（150 行、11,414 字节、SHA-256 `9b38c2759a16503230766ecc95092681dd4271364d790e612b677e48288405e4`）。S3、README、Windows workflow、stale caller migration、plan/control/reviewer artifact 均未被实现 agent 修改。

## Finding closure 证据

### R12-S2-RR-F01

- `commands/init.py` 在 typed/plain persistence interrupt、typed persistence error、普通 `OSError` 与 Windows non-success result 路径均先调用 `_try_abort_prepared_transaction`。
- abort helper 不执行 diagnostic I/O；只返回可空 `InitWorkspaceError` retained truth。
- persisted names、environment retained paths 与 abort failure 均在 abort 尝试后通过 owner-local best-effort diagnostic 投影。
- adversarial CLI test 对 typed/plain × abort success/failure 四组合使用 broken stderr；4/4 通过，abort 是首个事件，成功 abort 后无 `.dayu-init-transaction-*`，abort failure 时保留 truthful private transaction，全部 exit 130。

### R12-S2-RR-F02

- `init_environment.py` 把 private profile path no-follow identity 封闭分类为 owned/absent/drifted/unreadable。
- cleanup 只 unlink 精确 owned identity；absent 返回空，drifted/unreadable/缺失 identity 或 unlink failure 返回最小 `retained_paths`，不按名称删除未知对象。
- `EnvironmentPersistenceError` 与 `EnvironmentPersistenceResult` 都由 environment owner 携带 path-only retained truth；exception/result/repr 不携带 entry value。
- Controller 复跑原始直接 syscall 探针：replace-before `KeyboardInterrupt` + unlink `OSError` 后，typed status 为 interrupted、retained path 数为 1 且真实存在；文件真实包含 sentinel，但 exception/result repr 均不包含 sentinel。产品现在不再静默声称 cleanup 成功。
- unlink/identity-read × ordinary error/interrupt fault matrix 4 项与 identity drift 项合计 5 tests 全通过。

## 独立验证

- owner tests：`81 passed, 3 warnings`。
- S2 focused cumulative：`401 passed, 3 warnings`。
- adversarial environment fault probes：`5 passed, 51 deselected`。
- adversarial broken-stderr CLI probes：`4 passed`（包含在独立 focused invocation）。
- `dayu/cli/init_environment.py` 单文件 coverage：304 statements / 16 miss / 94.74%。
- `dayu/cli/commands/init.py` 单文件 coverage：284 statements / 27 miss / 90.49%。
- 按 AGENTS.md 先激活 `.venv` 的 full pyright：`0 errors, 0 warnings, 0 informations`。
- changed-path Ruff：pass。
- full Ruff：144 diagnostics；Controller current 与 immutable baseline SHA-256 均为 `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`，`cmp` 为 0。
- `git diff --check`：pass；staged tree 为空。
- 10 个 immutable S2 path SHA-256 与上游 Controller validation 精确一致。

## 固定 re-review target

本轮四个 changed target：

| 路径 | 行 / 字节 | SHA-256 |
|---|---:|---|
| `dayu/cli/init_environment.py` | 835 / 31,429 | `16353a72bce2efeeac1aae64f1f0c94cdca2e30e956be9412f2f0f20002059c0` |
| `dayu/cli/commands/init.py` | 743 / 27,820 | `fe5d4a434ccd5b528ef61cf80295652bbcc4bfa961bd0be3c6dc2aecf95a3e19` |
| `tests/cli/test_init_environment.py` | 1,245 / 48,353 | `5bc46652d54ae5e6860424c3acb952ce2dd615cb0df09eb1ae5c3b6c1f184618` |
| `tests/cli/test_init_command.py` | 964 / 34,238 | `25de81a149fcaee079c1e693b278258390d1710d87617e350abbe5abd914a4b2` |

Complete cumulative re-review 仍须覆盖 14 个 S2 implementation paths，并以既有 10 个 immutable hashes 加上上表 4 个 fixed hashes 为唯一 target。Reviewer 必须挑战：generic `Exception` diagnostic boundary 是否过宽、retained-path redaction/ownership 是否漂移、replace-before/after 与 identity uncertainty 是否仍有不真实 publication truth、broken stderr/abort failure 是否能改变 exit 130，以及 S3 boundary 是否未偷带。

当前 accepted findings 由 fix evidence 标记为待复审关闭；只有 AgentMiMo / AgentDS 双路 complete cumulative re-review 均确认关闭且无新 accepted finding，S2 才能进入完成状态。
