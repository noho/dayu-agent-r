# WU-SEMANTIC-OWNERSHIP-01 / R12 S2 code-review fix Controller validation

## Gate 与结论

- Gate：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 R12 S2 accepted code-review fix validation，不是新 WU。
- AgentCodex artifact：`docs/reviews/wu-semantic-ownership-01-r12-s2-code-review-fix-codex.md`，184 行 / 12,754 bytes / SHA-256 `3a05658d3e5383223f04ef78d82135305597413a33fa263b1715abf4d48f4025`。
- Controller verdict：`PASS_READY_FOR_DUAL_COMPLETE_REREVIEW`。
- `R12-S2-CR-F01..F03` 在本地实现与 owner tests 中为 3/3 fixed；最终 closure 仍须两路 complete re-review。
- S3、aggregate、commit、push 与 PR 仍未授权。

## 固定 re-review target

四个 fix paths 终态：

| 路径 | 行 / 字节 | SHA-256 |
|---|---:|---|
| `dayu/cli/init_environment.py` | 776 / 29,178 | `55756e0662d203811a84325cb79c3a42ea13592b790ec02966f361e670e71a40` |
| `dayu/cli/commands/init.py` | 689 / 25,789 | `3acbbec9049c91fd238a167a7a5a708a03be9b49a73f03907a710f32dffd56ce` |
| `tests/cli/test_init_environment.py` | 1,146 / 44,114 | `406ad395bfa8e6c644bca8f7a9349181bdabfd770a7e2ea1772828d54379eed6` |
| `tests/cli/test_init_command.py` | 832 / 29,097 | `5f229547219f34db0116d8fed5a764ab2d741ae47423e62166bb4b1bca6f72cb` |

其余 10 个 cumulative fixed target hashes 与原 Controller validation 完全一致：`init_catalog 937315f3...754`、`init_workspace b5aac7f4...fd7`、`arg_parsing add2353af...19e`、`host_assembly 658b57e5...7b9`、`entrypoint_runtime 4e165403...632`、Service README `d1eed1d0...d79`、`test_init_catalog 086a143c...d9f`、`test_init_workspace c363bc19...95b`、`test_arg_parsing 9a0b7aa6...9e2`、`test_host_assembly 28e09940...ad8`。

## Controller 独立验证

- owner tests：`tests/cli/test_init_environment.py` + `tests/cli/test_init_command.py` 为 `73 passed, 3 warnings`。
- focused cumulative：`393 passed, 3 warnings`；相对 S2 implementation baseline 新增 20 个 owner tests。
- 单文件 coverage：`dayu/cli/init_environment.py` 93.93% / 52 passed；`dayu/cli/commands/init.py` 91.12% / 21 passed。
- full pyright：`0 errors, 0 warnings, 0 informations`。
- changed Ruff：pass；full Ruff baseline/current JSON SHA-256 均为 `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`，`cmp` exit 0。
- `git diff --check` pass；staged tree 为空；10 个 immutable hashes 全部保持。
- Controller plain-interrupt real-staging probe：exit `130`、`private_transactions=()`、public config absent，关闭原 CR-F03 复现。
- Controller POSIX replace-before-effect interrupt probe：typed result `written_names=()` / `unwritten_names=('OPENAI_API_KEY',)`、`.dayu-init-env-*` 为空、profile absent，关闭原 CR-F01 复现。

## Complete re-review mandatory challenges

1. 必须重新审查全部 14-path cumulative target，且重点验证 `EnvironmentPersistenceInterrupted` 继承 `KeyboardInterrupt` 后仍只含 redacted names/target、exit 130 不漂移、没有把 public schema 或通用 cancellation framework引入 R12。
2. 必须挑战 POSIX write/fsync/replace 调用前/后 truth：owner temp identity、replace-after-effect 对账、verification/injection interrupt、identity drift、cleanup failure/identity-read uncertainty 是否 fail closed，任何 retained object 是否可能仍含 secret。
3. 必须挑战 Windows first/middle/last `setx` 与 store 完成后的 injection interrupt：written/unwritten names 是否精确、不伪造 registry rollback、不泄露 values/captured output。
4. 必须挑战 CLI orchestration：plain/typed interrupt、abort success/failure、diagnostic write failure 的顺序是否会阻止 identity-safe abort；不得因输出失败再次遗留 prepared transaction或改变 durable truth。
5. 必须确认旧 prompt/init stale caller、prewarm、真实 POSIX/Windows smoke、README/full CLI、Windows workflow仍严格属于 S3，没有 production implicit default/compatibility fallback。

## 下一入口

并发派发 AgentMiMo / AgentDS complete cumulative re-review。若任何新 material finding 被接受，回到 AgentCodex fix；只有 accepted/open 为 0 后才能进入 S3。
