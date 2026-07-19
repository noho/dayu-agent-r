# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4-RW-S2 Corrected-Plan Re-Review Controller Adjudication

## 1. Verdict

**PASS / PLAN-DRIFT FINDING CLOSED / READY FOR EXACT-SCOPE DOCS-ONLY ACCEPTED PLAN COMMIT**

本 gate 是既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 AR-F07 WIN4-RW-S2 remediation continuation，不是新 WU、feature、issue，也不是重新打开历史 sub-WU。两路 reviewer 均从完整 final plan、initial review/adjudication、zero-change fix/validation、direct code/tests 与 protected tree 执行 re-review。

## 2. Immutable evidence

| 证据 | Controller 接受值 |
|---|---|
| final 1084-line plan SHA-256 | `58631c6e204500dd3ab9b5caf495294cdf25225feaf40c1b4f2aecd91671f279` |
| protected four-path binary diff SHA-256 | `e67cd464d0a02f74aed4c0c948c4eec27efaf2f2899971592e4c35e8ea533669` |
| AgentMiMo re-review artifact SHA-256 | `ab13a371adefd123de75ed1b689132387a67d4ac6c5bb5b5b778f32b92264aef` |
| AgentDS re-review artifact SHA-256 | `4c117367586fca572ceb4c3734de2ad21148f70ef6f0960072be49510ad22b79` |
| `tests/cli/test_prompt_command.py` diff | empty |
| staged tree | empty |

受保护的四个 payload 文件内容 hash 仍分别为：

- `README.md`: `7cf41485076a96ba80f9ebeb7969c951f18e7478fe789db7a74adc8fde274cce`
- `dayu/cli/commands/init.py`: `b0601a962034d322f82edef2fbab7ce49e4b4a212b55bd81bbf276823d97e4c4`
- `tests/README.md`: `c5de013136b2c816f26d685511921dac9852775df7c0afed0352e2061d1b25fe`
- `tests/cli/test_init_command.py`: `1541fb84398339b202c1ae0f623e85f85c89bd4adc411083183456197bf9e5f8`

## 3. Re-review adjudication

### AgentMiMo

- Verdict: `PASS`；new finding `0`；backflow finding `0`；blocker/open question `0`。
- 确认 §13.3 whole-file allowlist、§13.4 exact-node owner 与 §13.6 mechanical gates 已自足授权必要最小 test-local import/module-private typed fake。
- 确认 production owner 不得加入 pytest/mock/capture identity、read failure fallback、compat shim 或共享测试 seam。
- 确认 security、deferred scope 与 fresh real-Windows closure 边界无漂移。

**Controller 裁决：ACCEPTED，无 plan fix gate。**

### AgentDS

- Verdict: `PASS`；new finding `0`；backflow finding `0`；blocker/open question `0`。
- 独立匹配 final plan、protected diff、四文件 hashes、prompt test zero diff 与 staged empty。
- 确认此前 DS-F01 拒绝成立，DS-OBS-01 只是刻意 test-local 解耦的 information observation。

**Controller 裁决：ACCEPTED，无 plan fix gate。**

## 4. Finding closure

| Finding / observation | 最终状态 | Controller 理由 |
|---|---|---|
| `WIN4-RW-S2-PD-F01` | **CLOSED IN FINAL PLAN** | §13.3—§13.6 已只加入 prompt integration exact node 的 strict TTY fixture 迁移，并补齐 focused/Ruff/node-diff/source/full-CLI gates |
| DS-F01 | **REJECTED / NOT IMPLEMENTED** | exact-node owner 与 whole-file allowlist 已授权必要最小 imports/module-private fake；硬编码 import 拼写会把 plan 过度耦合到实现细节，其它 nodes/getpass sequence/prompt/runtime assertions 仍冻结 |
| DS-OBS-01 | **INFORMATION / NO ACTION** | 两个 test-local fake 刻意解耦，生产代码不应承载共享测试 seam |
| re-review new/backflow findings | **NONE** | 两路完整 re-review 均为零 |

最终 ledger：accepted/open `0`，needs-evidence `0`，design contradiction `0`，local blocker `0`，unclassified residual `0`。

## 5. Accepted implementation boundary

Accepted plan commit 完成并由 Controller post-commit validation/authorization 后，S2 implementation 只可：

1. 保留现有 four-path protected payload，禁止重做或丢失；
2. 在 `tests/cli/test_prompt_command.py::test_prompt_command_uses_init_generated_workspace_config` 内迁移 caller-owned stdin capability，允许该文件必要最小的 module-level typed TTY fake/import；
3. 保持其它 test nodes、getpass sequence、prompt/runtime assertions 不变；
4. 完整执行 focused、full CLI、coverage、pyright、Ruff、diff/source/security 与 POSIX redirected smoke gates；
5. 禁止 production fallback、pytest/mock/capture identity、shared test helper、compat shim、统一 secret/authorization framework，以及 Issues 142/151/175/177/178 或 Web/WeChat/render deferred scope。

SQLite/EventLog/config 继续属于 trusted-local domain；本 slice 只承诺 Tool Trace、audit、public/LLM-facing/operator diagnostics 不泄露 API key/header 明文。

## 6. Exact docs-only accepted-plan commit scope

只允许以下 12 个文档路径进入 accepted plan commit：

```text
docs/host/issues-implementation-control.md
docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md
docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s2-implementation-plan-drift-fix-codex.md
docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s2-implementation-plan-drift-fix-controller-validation.md
docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s2-implementation-plan-drift-review-mimo.md
docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s2-implementation-plan-drift-review-ds.md
docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s2-implementation-plan-drift-review-controller-adjudication.md
docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s2-implementation-plan-drift-review-fix-codex.md
docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s2-implementation-plan-drift-review-fix-controller-validation.md
docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s2-implementation-plan-drift-rereview-mimo.md
docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s2-implementation-plan-drift-rereview-ds.md
docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s2-implementation-plan-drift-rereview-controller-adjudication.md
```

不得把四个 protected payload、`tests/cli/test_prompt_command.py`、implementation artifact 或其它路径带入该 commit。Accepted plan commit 之后，Controller 必须单独验证 commit identity/scope、protected diff 与 staged/worktree，再授权 AgentCodex 继续 implementation。
