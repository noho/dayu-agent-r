# WU-SEMANTIC-OWNERSHIP-01 R05-S2 Code Review Fix Controller Validation

## 1. Gate 与 verdict

- umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU。
- gate：R05-S2 accepted code-review findings fix Controller validation。
- AgentCodex artifact：`docs/reviews/wu-semantic-ownership-01-r05-s2-code-review-fix-codex.md`。
- Controller verdict：`PASS / READY_FOR_DUAL_COMPLETE_RE_REVIEW`。

Controller 独立读取 fix diff 与 artifact，并重跑关键验证。MiMo-001/DS-02、MiMo-002/DS-01、DS-05 三项 accepted current findings 已按裁决边界实现完成；四项 no-fix observations 未被偷带。当前没有 blocker，但 final acceptance 仍依赖 AgentMiMo / AgentDS 双路完整 re-review 与 Controller 最终裁决。

## 2. Owner 与实现复核

### 2.1 Durable construction projection

- 唯一 nested policy construction 已收敛到 `dayu.host.durable.options.project_host_durable_store_options(...)`。
- `HostDurableStoreOptionsSource` 只声明九个 durable storage construction 字段；它让 durable 下层同时接收 `HostCommandHandleOptions` 与 `OpenHostOptions` 的 structural typed 输入，不 import 上层 `dayu.host.api`，没有 callback/factory/query 行为。
- `dayu.host.command` 删除旧 private projection，不保留 wrapper/re-export；`open_host` 不再跨模块 import private helper。
- command opener、wait poller factory、execution/admin actor、scheduler store、admin seed 与 smoke durable read 均调用同一 owner helper。
- 新直接 owner test 对每个字段做可区分映射断言，并覆盖 durable options 现有 validation branches。

该 Protocol 是当前最小 dependency inversion，而不是新的业务 profile：它不持久化、不查找默认值、不解释额外字段、不拥有上层 opener 语义。re-review 仍需 adversarial challenge 其是否比直接参数或其它朴素接口更合适，以及 symbol/模块边界是否足够清晰。

### 2.2 Late publication evidence

- smoke 已删除 `_WaitPollerDiagnosticsHost`、`cast`、`._wait_poller`、`observation_diagnostics_snapshot()` 与 `runner_dropped_count`。
- 首轮 observation timeout 释放 claim 并写入 `ADAPTER_ERROR/wait_observation_timeout`；首轮 late Ready 返回后，poller 经过真实 backoff 到第二轮。
- 第二轮 adapter 先登记 observation entered，随后在返回 Ready 前阻塞。此时 smoke 从 public Run/outbox 与 durable Wait 读取：Run/Wait=`WAITING`、第二轮 claim 四字段 active、attempt=1、首轮 timeout diagnostic 保持、terminal outbox 为空。
- 因第一轮已返回而第二轮尚未返回，这一 owner-state boundary 直接证明首轮 result 没有 durable publication authority；只有释放第二轮 Ready 后才通过 public terminal/outbox 收为 `SUCCEEDED`。
- S1 owner-level runner test 继续拥有内部 dropped-count 诊断，S2 没有扩张 Host public diagnostics API。

### 2.3 Fake bounded waits

三个 provider-thread gate 均通过 `_wait_for_poll_adapter_gate(...)` 使用具名 `_TEST_OVERALL_DEADLINE_SECONDS` 有限等待；超时错误包含 gate 名与秒数。`abort()` 继续释放 late-result、second-observation 与 operation-finished gate，失败 cleanup 未被删除。

## 3. Controller 独立验证

所有 Python 命令均在 `.venv` 激活后运行。

| 验证 | Controller 结果 |
|---|---|
| fresh public awaiting smoke | PASS；handshake `0.001236s < 0.05s`、operation `0.300499s`、首轮 timeout/release/backoff/diagnostic、第二轮 blocked active claim、最终 public terminal/outbox 全部成立 |
| R05 ten-file aggregate | `360 passed, 3` 个第三方 edgar deprecation warnings |
| durable owner + public admin focused | `11 passed` |
| durable options owner branch coverage | `9 passed`；`dayu/host/durable/options.py 100%`，`73` statements / `8` branches，`--cov-fail-under=80` PASS |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| changed Python Ruff | `All checks passed!` |
| full Ruff registry | pre-fix `165`，post-fix `162`；精确 diff 只删除 touched `command.py` 两条与 `test_public_host_admin.py` 一条 F401 |
| `git diff --check` / staged area | PASS / empty |
| scheduler deterministic residual probe | `1 passed`，仍以预期 `HostApiError` 为直接证据 |
| source/propagation/private-coupling scans | removed private helpers、smoke duplicate、private poller/cast/counter、裸 gate waits、shortcut 均零命中 |
| protected no-diff owners | Engine production/README、S1 state/wait/runner/schema/design/tests、scheduler production/tests 均无 working-tree diff |

Controller protected tracked transaction digest：

`95f24a4e21e258e47d33bb1bafbe9d8fb25bcc3c2985941df6ed8f1bca123fc6`

新 direct owner test blob：

`tests/host/test_durable_options.py = 1c9c21a0df334709ba8dcb8188c48c5e7fdaa2fc`

## 4. README 与 scope

- `tests/README.md` 已登记 durable projection owner test，并把 public smoke 描述改成第二轮 observation blocked boundary 的业务 owner facts。
- S2 先前的 `dayu/host/README.md` current wait contract 仍准确；本 fix 没有增加新的稳定用户/Service public contract，无需继续机械扩写 Host README。
- Engine README、根 README、`dayu/README.md` 无触发变化。
- 没有统一 authorization、callback、Issue 175、scheduler fix、R06+ 或其它 deferred scope；现有安全/fence/cancellation/claim owners 无修改。

## 5. Finding ledger 与下一 gate

| 分类 | 数量 | 当前状态 |
|---|---:|---|
| accepted current finding | 3 | implementation complete，等待双路 re-review 关闭 |
| rejected-as-current-defect observation | 4 | CLOSED / NO FIX |
| retained R05 residual | 2 | 原 owner/destination 不变 |
| blocker | 0 | NONE |

下一 gate：AgentMiMo / AgentDS 双路完整 R05-S2 code re-review。两路必须审查整个 S2 transaction 和完整 initial review/fix evidence chain，不是只看三处局部 patch；必须重点挑战 structural Protocol 是否过度设计、第二轮 blocked observation 的 happens-before 证据、失败 cleanup、README/coverage/Ruff 证据与 retained/deferred boundary。

R05-S2 accepted local commit、R05 aggregate、scheduler fix、Issue 175、callback、统一 authorization、R06-R12、push 与 PR 均未授权。
