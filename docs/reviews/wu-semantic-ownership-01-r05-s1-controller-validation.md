# WU-SEMANTIC-OWNERSHIP-01 R05-S1 Controller Validation

## 1. Gate 与 verdict

- implementation artifact：`docs/reviews/wu-semantic-ownership-01-r05-s1-implementation-codex.md`。
- validation continuation：`docs/reviews/wu-semantic-ownership-01-r05-s1-validation-continuation-codex.md`。
- accepted plan correction：`cf2f832cfe45b4a58a179d842d6b09c337d99f24`。
- validation-resume transition：`2c068869843837546e6c6bc0a5285918b01d8b29`。
- Controller verdict：`PASS / READY_FOR_DUAL_COMPLETE_CODE_REVIEW`。

R05-S1 的唯一产品 transaction 已落在 semantic owner boundary：`WaitPoller` 把 poll / cancelled-abandon observation timeout 解释为 poll-local transient diagnostic，复用既有 atomic claim release/backoff；durable state 删除 invalid timeout-only terminal primitive；Host design 真源同步纠正；owner tests 覆盖 late publication、retry、typed lost 与 explicit lifecycle terminal。没有 schema、Engine、scheduler、Service、config、README 或 deferred scope 修改。

## 2. Controller 独立验证

### 2.1 产品 digest 与 artifact immutability

- 七路径 protected digest：`3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2`。
- 原 stopped implementation artifact SHA-256：`b8ec89aafc6008587791958cb356f0124cec76199959f2ea3b62272ee3496732`。
- continuation 前后两者均未漂移。
- actual changed production list 相对 fixed plan base 精确为：
  - `dayu/host/durable/state.py`
  - `dayu/host/wait_adapter.py`

### 2.2 Functional validation

AgentCodex continuation 重新运行并通过：

- owner nodes：`3 passed`；
- durable preservation：`4 passed`；
- focused branch matrix：`19 passed`；
- four Host files：`69 passed`；
- R04 config/composition preservation：`35 passed, 3 warnings`；
- aggregate functional matrix：`359 passed, 3 warnings`。

Controller 独立重跑 aggregate matrix：`359 passed, 3 warnings in 3.59s`。三个 warning 均来自 edgar 第三方 deprecation。

### 2.3 Coverage

修订后的 changed-owner coverage measurement 精确只排除：

1. `tests/host/test_toolruntime_executor.py`
2. `tests/host/test_dispatch_scheduler.py`

AgentCodex 结果：`1830 passed, 2 skipped, 5 deselected in 51.56s`，state 83%、wait adapter 86%。Controller此前在相同 protected product digest 上独立运行同一命令得到 `1830 passed, 2 skipped, 5 deselected in 53.15s`；当前再次从本轮 coverage data独立执行两个逐文件 `--fail-under=80`，结果仍为 83% / 86%，均 PASS。没有第三个 ignore、xfail、retry 或 failure exemption。

### 2.4 Pyright 与 Ruff

- AgentCodex full pyright：`0 errors, 0 warnings, 0 informations`。
- Controller 独立 full pyright：同样为零错误。
- AgentCodex / Controller changed-file Ruff：`All checks passed!`。
- full Ruff registry：Controller 独立比较 fixed base JSON 167 与 current JSON 165；`added=[]`，`removed` 精确只有：
  - `dayu/host/durable/state.py:40:5 F401 TERMINAL_RUN_STATUS_VALUES`；
  - `tests/host/test_phase7_waiting_integration.py:8:22 F401 datetime.UTC`。

其它 165 条 path / rule / location / message / severity 与 base 同源，没有新增、替换或扩散。

### 2.5 Source、security 与 allowlist

Controller 独立确认：

- `mark_wait_record_poll_abandon_timeout` / `_MarkWaitRecordAbandonTimeoutOperation` 在 production/tests 零定义、零调用；
- `_wait_observation.py`、`waiting.py`、`agent.py`、durable schema、scheduler、ingestor、scheduler test 相对 base 无 diff；
- scheduler test 对 R05 owner symbols 零命中；
- production added lines 无 authorization、permission、callback transport、process isolation、Issue 175 等 deferred scope；
- actual changed production list只有两个 owner files；
- `git diff --check` PASS；
- current worktree 精确为七个 protected paths、原 implementation artifact与 continuation artifact。

### 2.6 README decision

S1 不更新 README 的裁决符合 accepted plan：当前只完成 Host state-machine transaction与设计真源句子，Host/tests README 和 public smoke 的稳定 final acceptance属于 R05-S2。Engine、根 README 和分层文档均无触发。此裁决不免除 R05-S2 后续 README acceptance。

## 3. Semantic contract 验收

Controller 逐项确认：

- poll timeout 保持 Wait / Run `WAITING`，写 `ADAPTER_ERROR / wait_observation_timeout`，release + backoff，不调用 resolve；
- cancelled abandon timeout 保持 `CANCELLED`，写 `ABANDON_ERROR / wait_abandon_timeout`，release + backoff，不写 `poll_abandoned_at`；
- late Ready / Applied publication 被既有 token/generation fence丢弃；
- 下一轮到期后 Ready 可恢复 Run，explicit lifecycle terminal可写 abandon marker；
- authoritative typed lost 继续经 common resolver 终止 Wait / Run；
- claim CAS、capacity、shared close deadline、invalid deadline fail-close与R04 config ownership均保留；
- no compat shim、no downstream fallback、no duplicate backoff/policy owner。

## 4. Residuals 与安全说明

- scheduler close / terminal promotion coordination 缺口仍由确定性 probe复现；它是独立 Host lifecycle residual，未修、未 waive、未建 issue、未归 Issue 175。corrected coverage 只与其解耦，不宣称修复。
- cancelled abandon 若 provider 永不返回 explicit terminal outcome，会按 capped backoff长期重试；future Host durable evidence policy才有权定义终止证据。
- Issue 175、callback、unified authorization、R05-S2、R06+均未实现。
- 本 S1 不删除或放宽现有 security / fencing / containment；也不实现统一 tool authorization framework。

## 5. Code review handoff

AgentMiMo / AgentDS 必须各自完整 review：

1. 七路径 product/test/design diff全文；
2. 修订后 plan、原 stopped implementation artifact、continuation artifact与本 Controller validation；
3. owner correctness、state transition、CAS/backoff、late publication、terminal preservation；
4. tests 是否断言 owner contract而非固化偶然行为；
5. code quality、类型、docstring、coupling、semantic ownership drift、retained safety与deferred leakage；
6. scheduler residual 是否被误修或隐藏；
7. coverage/Ruff/pyright/source evidence 是否可信。

finding 必须提供直接代码/数据证据、semantic owner、严重度、反例和精确修复建议。review verdict 不独立授权 commit；Controller 必须裁决全部 findings，任何 accepted finding 必须由 AgentCodex 修复并双路 re-review。

## 6. 下一 gate

下一 gate：AgentMiMo / AgentDS 并发完整 R05-S1 code review。

R05-S2、S1 product commit、aggregate、scheduler fix、Issue 175、callback、unified authorization、R06-R12、push 与 PR 均未授权。
