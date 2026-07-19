# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW-S2 Implementation Plan-Drift Fix — AgentCodex

## 1. Gate 结论

本轮是同一 umbrella `WU-SEMANTIC-OWNERSHIP-01` / `AR-F07` / `WIN4-RW-S2` implementation
continuation 内的 plan-only fix，不是新 WU、sub-WU、product fix、test implementation或 scope expansion。

Controller 接受的唯一 finding `WIN4-RW-S2-PD-F01` 已按裁决写回 remediation plan。当前状态是
`FIXED_IN_PLAN / PENDING_CONTROLLER_VALIDATION_AND_DUAL_COMPLETE_PLAN_REVIEW / IMPLEMENTATION_PAUSED`。

本轮只修改 remediation plan 并新增本文；未修改、回滚、格式化或 stage 四个 stopped implementation payload，未修改
`tests/cli/test_prompt_command.py`，未触碰 control/design/其它 artifact/product/test/README/workflow，未运行 implementation、
commit、push、dispatch、PR或 plan review。

## 2. 第一性原理与 owner 判断

修复动机成立，且严重性应限定为 plan allowlist/test propagation 缺口，不是 product finding。direct failing evidence证明：

1. full CLI mandatory regression 的唯一失败节点是
   `tests/cli/test_prompt_command.py::test_prompt_command_uses_init_generated_workspace_config`；
2. 该 direct consumer mock了 `getpass.getpass`，但没有把 production实际读取的
   `dayu.cli.commands.init.sys.stdin` 设为 TTY；
3. pytest capture stdin 的 `isatty()` 为 false，accepted `_read_secret_input()` 因而正确进入 redirected owner path，
   `readline()` 由 capture stream抛 `OSError`，CLI返回 `1`；
4. 让 production识别 pytest/mock/capture stream，或 redirected失败后 fallback到 getpass，会破坏 capability-only
   product contract并形成 test/compat shim；
5. 正确 owner是该 exact integration test的 stdin fixture。它只需提供 test-owned strict typed TTY fake，继续由既有
   getpass value序列提供 hidden values，并保留 prompt/runtime assembly业务断言。

因此最小且同源的修复是补齐 plan 对 direct consumer 的 node-scoped授权与验证矩阵，不修改 product owner。

## 3. `WIN4-RW-S2-PD-F01` 逐项修复

| Plan section | 修复 | 边界保持 |
| --- | --- | --- |
| §13.3 | 将 `tests/cli/test_prompt_command.py` 加入 WIN4-RW-S2 allowlist | ownership严格限 exact node的 strict typed TTY stdin fixture迁移；同文件其它 tests零 diff |
| §13.4 | 明确 exact node只补 `sys.stdin` TTY fake，`isatty()` 恒真且 `readline()` 误入立即失败 | 保留 getpass value序列、prompt/runtime assembly业务断言与执行顺序；不抽 compat/shared production seam、跨模块 facade，不改其它 prompt tests |
| §13.5 | TTY matrix加入 direct integration consumer | 必须证明只走 hidden getpass与 `readline()` fail-fast，不重测或重算 product语义 |
| §13.6.1/§13.6.2 | per-slice focused gate加入 exact node；full `pytest tests/cli -q` 继续 mandatory | 不以单 node green替代 full CLI regression |
| §13.6.4 | scoped Ruff加入 `tests/cli/test_prompt_command.py` | full pyright/full Ruff baseline contract不变 |
| §13.6.5 | allowlist检查加入 prompt file node-level diff review | 只允许 exact node fixture迁移；getpass序列、业务断言与其它 nodes零 diff |
| §13.6.6 | ownership/forbidden source scans加入 prompt file | forbidden production/test shim、private stdin identity、platform/PTY/process-tree与 deferred scope不变 |

Plan 的 product contract、README决定、安全边界、deferred scope、remote closure、same-run canary、S1→S2顺序与其它
slice边界均未改变。

## 4. Final plan identity

| 项目 | Before fix | Final |
| --- | --- | --- |
| plan lines | `1060` | `1084` |
| plan bytes | `73,440` | `75,492` |
| plan SHA-256 | `7e82df117c5d7b97e13d8ee2ec156c19de6689c129f09cec979cd0b1bf8adb76` | `58631c6e204500dd3ab9b5caf495294cdf25225feaf40c1b4f2aecd91671f279` |
| plan diff | — | `34` insertions / `10` deletions，仅 §13.3–§13.6 |

Final plan：`docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`。

## 5. Protected-state lock复核

| Lock | Expected | Final result |
| --- | --- | --- |
| Entry HEAD | `e3e138fedd43c8edcf0a7113ff3c0335c22c9485` | unchanged |
| `README.md` SHA-256 | `7cf41485076a96ba80f9ebeb7969c951f18e7478fe789db7a74adc8fde274cce` | unchanged |
| `dayu/cli/commands/init.py` SHA-256 | `b0601a962034d322f82edef2fbab7ce49e4b4a212b55bd81bbf276823d97e4c4` | unchanged |
| `tests/README.md` SHA-256 | `c5de013136b2c816f26d685511921dac9852775df7c0afed0352e2061d1b25fe` | unchanged |
| `tests/cli/test_init_command.py` SHA-256 | `1541fb84398339b202c1ae0f623e85f85c89bd4adc411083183456197bf9e5f8` | unchanged |
| four-path binary diff SHA-256 | `e67cd464d0a02f74aed4c0c948c4eec27efaf2f2899971592e4c35e8ea533669` | unchanged |
| `tests/cli/test_prompt_command.py` | zero diff | PASS |
| staged tree | empty | PASS |

Four-path lock复核使用：

```bash
git diff --binary HEAD -- README.md dayu/cli/commands/init.py tests/README.md tests/cli/test_init_command.py
```

对该命令的完整 binary diff bytes计算 SHA-256；未把 docs-only plan/fix artifact纳入 stopped payload lock。

## 6. Diff-check 与验证

- `git diff --check`：PASS。
- authored paths：精确为 remediation plan与本文，共 `2` 个 docs paths。
- `git diff --exit-code -- tests/cli/test_prompt_command.py`：PASS，零 diff。
- `git diff --cached --exit-code`：PASS，staged tree empty。
- 四个 protected payload逐文件 SHA-256：全部匹配。
- four-path binary diff SHA-256：匹配 `e67cd464...33669`。
- plan scope scan：§13.3 allowlist、§13.4 exact-node边界、§13.5 TTY matrix、§13.6 focused/Ruff/
  allowlist/source scans均命中；full CLI mandatory gate仍存在。
- product contract、README、安全/deferred/remote closure与其它 slice diff：零。
- pytest、coverage、pyright、Ruff与 remote workflow：未运行；本轮是 plan-only fix，且 implementation payload受保护。

## 7. Finding 与下一步

| Finding | 状态 |
| --- | --- |
| `WIN4-RW-S2-PD-F01` | `FIXED_IN_PLAN / PENDING_CONTROLLER_VALIDATION_AND_DUAL_COMPLETE_PLAN_REVIEW` |

Open questions：`0`。下一步仅由 Controller先验证本 docs-only plan fix，再由 AgentMiMo/AgentDS并发执行 dual complete plan
review；accepted findings全部关闭并形成 exact docs-only accepted-plan commit后，才可恢复 WIN4-RW-S2 implementation。

本轮停止在 plan review前；不自行 dispatch reviewer、不 stage/commit/push、不修改 control或恢复 implementation。
