# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 1 Provider Quota Stop Controller Adjudication

## 1. Gate identity

- 时间：`2026-07-19`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01` aggregate regression fix Slice 1 local-trust verification continuation；不是新 WU 或新 slice。
- AgentCodex artifact：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-implementation-codex.md`，SHA-256 `2c1274e17bc37a0837782fc6cb657fa1cb566ad57c340754023796a5d8703cfe`。
- AgentCodex verdict：`STOPPED / EXTERNAL_PROVIDER_QUOTA_TYPED_SKIP / CONTROLLER_DECISION_REQUIRED / NOT_READY_FOR_REVIEW`。

## 2. Controller code and scope validation

Controller完整读取五个新增 test deltas与 implementation continuation evidence，确认：

- `tests/host/test_run_input_builder.py` 先从 EventLog durable payload和 effective dispatch decision证明 resolved headers exact retention，再证明 Engine `AgentRunRequest.runner_spec.headers` exact retention；messages、memory、compact与 runner-call projection均为零 sentinel。
- Tool Trace、audit、public HostEvent/activity与 LocalProxy operator log分别从其直接 owner验证零 sentinel；没有字段名黑名单、下游 repair、production fallback、secret infrastructure或统一 authorization framework。
- 五个 tests使用同一个显式 synthetic value；没有读取、写入或输出真实 configured secret value/ref。
- Production、README、workflow、config与其它 test/utility paths没有新增 delta。前三个既有 Slice 1 test hashes保持 `5acf57...`、`86968b...`、`f60a1d...`；五个新增 owner tests final hashes与 AgentCodex handoff一致。
- `git diff --check` PASS，staged tree为空。

Controller独立 fresh 复核：

```text
five exact owner nodes = 5 passed
full pyright = 0 errors / 0 warnings / 0 informations
five modified owner test files Ruff = All checks passed
git diff --check = PASS
staged tree = empty
```

AgentCodex其余 final-tree evidence被接受为当前树证据：canonical `5181 passed / 10 skipped`且只有 AR-F02 import-boundary单节点失败；三个 required real smoke PASS；configured-value semantic classification仅在 exact Host internal owner保留非零，所有 zero-required surfaces为零；219-path ledger只有九个 AR-F05 owner paths低于80%。

## 3. Stop reproduction and root cause

Controller两次 fresh运行：

```bash
source .venv/bin/activate
pytest tests/host/test_public_real_runner_matrix_smoke.py -q -rs
```

两次结果均为 `3 passed, 1 skipped`。唯一 skip是 Gemini provider返回 typed `RESOURCE_EXHAUSTED` / HTTP 429；直接 response说明 free-tier per-project/per-model daily request quota limit为20。Controller在第一次 response给出的 provider `RetryInfo` backoff后做一次复核，仍返回相同 daily quota exhausted分类；没有继续循环重试。

该 skip：

- 不是 local-trust projection leak；
- 不是当前 test或production defect；
- 不是 credential缺失；
- 是当前外部 provider quota state；
- 使 final exact-exclusion coverage run相对 accepted plan固定分类多一个 typed skip。

Accepted plan §6.1/§6.2明确要求 Slice 1维持既有10 skips，不允许新增未裁决 skip、retry、额外 deselect或 waiver。因此 Controller不能用仍有效的 coverage ledger替代这个未通过的真实 provider gate，也不能授权 code review。

## 4. Finding and state adjudication

```text
S1-QUOTA-F01 = ACCEPTED EXTERNAL VALIDATION BLOCKER / OPEN
local-trust code finding = 0
production defect = 0
scope drift = 0
AR-F01 = OWNER EVIDENCE PASS / FINAL CLOSED NOT SIGNED
AR-F03 = OWNER EVIDENCE PASS / FINAL CLOSED NOT SIGNED
AR-F04 = OWNER EVIDENCE PASS / FINAL CLOSED NOT SIGNED
S1-SEC-F01 = OWNER EVIDENCE PASS / CLOSED_AS_NO_CODE_BLOCKER NOT SIGNED
AR-F02 = OPEN_BY_SEQUENCE
AR-F05 = OPEN_BY_SEQUENCE
AR-F06 = RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX
AR-F07 = PENDING_RELEASE_BLOCKER
```

Slice 1 remains `NOT_READY_FOR_REVIEW`。不授权 code review、commit、Slice 2/3、aggregate deepreview、push或PR。

## 5. Exact recovery entry

外部 Gemini quota恢复后，在没有任何 code/test/worktree drift的前提下，由 AgentCodex在同一 Slice 1 / 同一 implementation artifact继续 validation-only gate：

1. 重新核对所有 protected/mutable hashes与 staged-empty；任何 drift先 STOP。
2. Fresh执行 public real runner matrix，必须4 provider nodes全部PASS、零新增 skip。
3. 从 `coverage erase`开始 fresh重跑 accepted plan §6.2 exact-exclusion coverage全命令；只允许 AR-F02 failure，skip/deselect分类必须回到 accepted baseline，219 ledger保持仅九个 AR-F05 paths `OPEN_BY_SEQUENCE`。
4. Fresh重跑 configured-value semantic scan、pyright、mutable-path Ruff、`git diff --check`与staged-empty；只追加同一 implementation artifact。
5. 全部PASS后回到 Controller validation；不得自行进入 review。

不得修改 provider config、替换 model/key、改变 smoke skip语义、增加 retry或把 typed skip记为 success。若 daily quota在恢复尝试中仍未解除，继续保留本 stop，不新增 WU或 finding。

## 6. Verdict

`STOP ACCEPTED / EXTERNAL GEMINI DAILY QUOTA BLOCKER / SLICE 1 NOT READY FOR REVIEW`
