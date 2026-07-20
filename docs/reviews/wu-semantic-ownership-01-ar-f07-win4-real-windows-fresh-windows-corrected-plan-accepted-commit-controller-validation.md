# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW-RF01 Accepted Corrected-plan Commit — Controller Validation

## Commit identity

- Timestamp：`2026-07-20T09:34:20+0800`。
- Accepted corrected-plan commit：`e2c9a31b25fb6d87e6fb4d618bb4043f556a55b0`。
- Subject：`docs: accept AR-F07 WIN4 corrected plan`。
- Parent：`b11eb95c8312e085755b81c630e9c359220d3ff1`。
- Tree：`834ef057f02657519d270ea2cc0d89380319610a`。
- Exact changed paths：`13`。
- Sorted path-list SHA-256：`8f7a24b03f5a6401e9b7fd24f51f0fe22b9af5c26eac278fee9aa3626e989a45`。
- Verdict：`PASS / CORRECTED_PLAN_COMMIT_ACCEPTED / ONE_TEST_IMPLEMENTATION_AUTHORIZED_AFTER_CONTROL_TRANSITION`。

## Scope validation

Controller 以 `git show --name-only` 与 staged path lock复核 commit。exact scope 只有：

- `docs/host/issues-implementation-control.md`；
- `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`；
- fresh Windows evidence adjudication；
- AgentCodex plan correction；
- Controller plan validation；
- 双路初审、Controller初审裁决；
- AgentCodex zero-change fix、Controller fix validation；
- 双路最终 re-review、Controller最终裁决。

commit 不含 product、test、README、design、workflow、GitHub Actions 或 secret value。commit 后 worktree clean、staged tree empty、
`git diff --check`通过；frozen corrected plan仍为 `1124` lines / SHA-256
`571ca834a515620283447a6c2166fc7bbd5dcf9393b685457a0ee7e959dc7ff2`。

## Accepted implementation contract

只允许 AgentCodex 修改 `tests/cli/test_upload_filings_from_command.py` 的
`test_windows_generated_script_runs_real_cli_into_temp_storage` 现有 snapshot assertion block：

1. `snapshot.primary_filename` exact-name必须恰好命中一个 public descriptor；
2. `source_path.name` exact-name必须独立地恰好命中一个 public descriptor；
3. raw-source descriptor `sha256` 必须非空且等于 `hashlib.sha256(fixture).hexdigest()`；
4. primary与raw-source允许不同，不得硬编码 Docling expected primary；
5. 不得增加 import/helper/schema/oracle字段，不得读取 private meta/raw storage path，不得修改 Fins/product、其它 test、
   README、design 或 workflow。

后续 control-transition docs commit只冻结 authorization evidence，不改变 plan/product contract。Agent入场时以该 transition后的
clean HEAD作为机械 diff base，并同时锁定本 accepted plan commit与 plan SHA；这样 transition docs不会被误计入 implementation
payload。若实现需要超出上述 block，立即 stop 并回 Controller。

## Validation and next gate

- AgentCodex 与 Controller已在 zero-change fix gate分别运行 full pyright，均为 `0 errors, 0 warnings, 0 informations`。
- 本 commit只有 docs/control/review；测试 N/A。
- Accepted/open plan finding、backflow、blocker、needs-evidence与design contradiction均为 `0`。

下一 gate：Controller提交本 validation与control transition，冻结 resulting clean HEAD；随后只授权 AgentCodex执行上述 one-test
implementation。不得 push、dispatch remote Windows、进入 PR review或 final closeout。
