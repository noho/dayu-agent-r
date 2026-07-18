# WU-SEMANTIC-OWNERSHIP-01 / R12 S2 implementation resume Controller validation

## 结论

- Gate：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 R12 S2 cumulative implementation continuation，不是新 WU。
- 裁决：`PASS_WITH_MANDATORY_REVIEW_CHALLENGES`。
- S2 implementation handoff 已满足进入双路完整 code review 的机械条件；当前 accepted/open implementation finding 为 `0`，review 尚未开始。
- 本裁决不授权 S3、aggregate、commit、push 或 PR。

## 固定 review target

Controller 在进入 review 前读取并固定以下 SHA-256；两路 reviewer 必须审查这一完整 cumulative target，不得只看最后一个 diff hunk：

| 路径 | SHA-256 |
|---|---|
| `dayu/cli/init_catalog.py` | `937315f3a6c83004788027c891c3b18e3cf2c848db2333430661998768ffe754` |
| `dayu/cli/init_environment.py` | `71be5ba886df7a9d33c6c15da1fba172540124684b02c65c67e17852d736b77f` |
| `dayu/cli/init_workspace.py` | `b5aac7f486d86d0c01896a2fc3533d028d0e5064f43982bb2974fddc7efd3fd7` |
| `dayu/cli/commands/init.py` | `fd927badc32fe5b266d3cd7f6d11500fd60c3b02ba78e413bdee318a67b52a21` |
| `dayu/cli/arg_parsing.py` | `add2353afbc64db84af1c4df899dfa8a692409131d91570d6c7fac7d1241319e` |
| `dayu/service/host_assembly.py` | `658b57e5378ea6ea849203106e2bd57b38e1d6917a93743264cd22ec2f2c27b9` |
| `dayu/service/entrypoint_runtime.py` | `4e16540335ae9a614381d59899dcda23f590f42320494a093e01ce0329344632` |
| `dayu/service/README.md` | `d1eed1d028fda7df7e913361fdd313109d262a952433ad8c99ef2a1c0c9f4d79` |
| `tests/cli/test_init_catalog.py` | `086a143cf8247b6fe5371d6df5c2c5c6cc974410973d81d60bb7ccd8b6d05d9f` |
| `tests/cli/test_init_environment.py` | `820c2bf262dd77628201977e7d4f823265e141ac0ae6a28791bd7d12cf5ad01a` |
| `tests/cli/test_init_workspace.py` | `c363bc1916ceb3204f517a038d70ce632d0c3d8fd17319651cfee2ecb8f3e95b` |
| `tests/cli/test_init_command.py` | `db965a53b3ff0f9d8449f784dc5ae8204ae0be0389780166457042377196807c` |
| `tests/cli/test_arg_parsing.py` | `9a0b7aa6647c7ca18dc96eb50714ec1cadff29ff2df51ccdf7edc0926ef1b9e2` |
| `tests/service/test_host_assembly.py` | `28e099404bcf931dc4c78158288705c1f1ff555966eadf08a3f5d3df865e6ad8` |

Implementation handoff `docs/reviews/wu-semantic-ownership-01-r12-s2-implementation-resume-codex.md` 为 231 行 / 21,107 bytes / SHA-256 `eaccec2ff8af46e7eccfc220250e2f81a9b90135b551d266c4e8f4bcce38564e`。

## Controller 独立验证

- focused cumulative regression：`373 passed, 3 warnings`；warning 均来自 edgar dependency deprecation。
- runtime anchors：`146 passed`。
- 单文件 coverage：`dayu/cli/init_workspace.py` 87.20% / 90 passed；`dayu/cli/commands/init.py` 90.69% / 18 passed；`dayu/service/host_assembly.py` 94.74% / 84 passed。
- `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- changed-path Ruff：`All checks passed!`。
- full Ruff：历史 baseline 与 Controller current 均为 144 diagnostics，JSON SHA-256 均为 `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`，`cmp` exit 0。
- `git diff --check` pass；staged tree 为空；S1 四路径 hashes 未漂移；Fins/Host/Engine/Tool/runtime/design/deferred scope 未发生越界修改。

## Mandatory review challenges

1. `dayu/cli/init_workspace.py` 为 1,618 行 transaction owner。reviewer 必须从唯一语义 owner、状态机可证性、rollback/cleanup fault truth、函数内聚度与 AGENTS.md 的 God object/God function 禁令审查；不能仅凭覆盖率接受。
2. 必须对抗性检查 FIRST/PRESERVE/OVERWRITE/RESET 在 snapshot drift、rename 已生效后抛错、partial cleanup、KeyboardInterrupt、symlink/reparse race 和 durability failure 下是否如实报告 public truth，且不碰 `portfolio`。
3. 必须确认 Service Fins override 先校验 raw grammar、只支配 Fins effective root、ordinary runtime 显式 `None`、Web/非 Fins 不消费，且没有引入通用 permission/auth framework。
4. Controller 单独复现 `tests/cli/test_prompt_command.py::test_prompt_command_uses_init_generated_workspace_config` 失败：旧测试无交互调用 init，当前 init 正确要求显式模型选择。该失败的语义 owner 是 S3 test/workflow migration；不得通过 S2 production implicit default、compatibility fallback 或 test shim 修复。reviewer 必须确认此分类成立，并检查是否还有同类调用点。
5. 必须确认 S3 的 prewarm、真实 POSIX/Windows smoke、真实 Windows junction/rollback、root/tests/config README 与 full CLI regression 仍未偷带入 S2，也未被错误宣称完成。

## 下一入口

并发派发 AgentMiMo / AgentDS 对固定 cumulative target 执行完整 `/deepreview`。所有 accepted findings 必须先由 AgentCodex 修复并经双路 re-review 关闭，才能进入 S3。
