# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 1 Local-Trust Resume Controller Authorization

## 1. Entry lock

- 时间：`2026-07-19 08:52:24 +0800`。
- Branch：`phaseflow/host-issues-control`。
- Slice base / HEAD：`ffbf48c2cf5f701c627fda1ebcce7aa1813383ab`。
- Final corrected plan：`docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`，SHA-256 `afaa18c5608e6eeae0046318865bd1b3dd2f9a176c4b0739aa5b099e0ae3a252`。
- Dual review：AgentMiMo `951c851a...3029c5`；AgentDS final corrected `64b17d4d...196da3`；Controller adjudication为 `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-local-trust-plan-review-controller-adjudication.md`。
- Staged tree必须保持为空。当前 worktree 的 design、plan、control、review/control artifacts 与三个既有 Slice 1 test delta均为当前 umbrella WU 的受保护有意改动，AgentCodex不得删除、回滚、覆盖或重写其历史证据。

三个既有 Slice 1 delta entry locks：

```text
5acf57a06d1c7fee82a27ae0c3ccdfcddfe745a42439a514c0551665904f96db  tests/service/test_host_admin.py
86968b937d4289d29427a2bd68934a074ca0499dfa3563ec326eae73f2432ee3  tests/tools/web/test_smoke_web_ci.py
f60a1d6e190c948986be355fc66ad71cb64e207691e8a12646ea23cbdcc66169  tests/host/test_public_compact_smoke.py
```

五个新增 mutable test owners 的 entry hashes：

```text
6b08be06304776ba08f3a00b7c40a0e031d45c16f28203b7b52761567e5da347  tests/host/test_audit_sink.py
236dde54dcdd38428fea84784091fa63a049931a5495bb883da127e8b784ffbd  tests/host/test_tool_trace_projection.py
798a7000086b5b0cc16565c0d34c78ddc6ae8b0d8eab6d81b8cfa8aa196fb9db  tests/host/test_host_activity_event_projection.py
f4e90d9baa4db40e06a13919ae96c9632ab09075ac504a791529e49e8f91cab3  tests/host/test_run_input_builder.py
12227f892d059116d48c78f1311a2f69a40e524eff1acfb476e2286b8cd1ec21  tests/host/test_logging.py
```

Existing implementation artifact `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-implementation-codex.md` 当前 SHA-256 为 `05800914dfd66912c05ca7eef4d8cacfab1a506572b161c4ce39362a4443b32a`；本 gate 只允许 AgentCodex在同一 artifact 追加本次 continuation 的 entry、delta、validation 与最终 verdict，不得重写或删去既有 stop history。

## 2. Exact mutable scope

只授权 AgentCodex继续修改以下八个 tests，并追加既有 implementation artifact：

```text
M tests/service/test_host_admin.py
M tests/tools/web/test_smoke_web_ci.py
M tests/host/test_public_compact_smoke.py
M tests/host/test_audit_sink.py
M tests/host/test_tool_trace_projection.py
M tests/host/test_host_activity_event_projection.py
M tests/host/test_run_input_builder.py
M tests/host/test_logging.py
M docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-implementation-codex.md
```

前三个 tests 已完成既有 Slice 1 修复，只允许为 full-gate failure作当前 plan 授权内的必要修正；不得顺手重构。后五个 paths 只允许加入 corrected plan §4.1 的 synthetic sentinel owner tests。Production、README、workflow、config、design、plan、control、其它 review artifacts与其它 `tests/**` / `utils/**` 全部零 diff。

不得 stage、commit、push、开 PR、启动 reviewer/subagent或开始 Slice 2/3。

## 3. Required continuation

- 使用单一 synthetic sentinel；不得读取或写出真实 secret value/ref。
- 先证明 Host internal `USER_INPUT_ACCEPTED.effective_execution_config.config.runner_spec.headers` durable round-trip保留 exact value，且 Engine执行输入 `AgentRunRequest.runner_spec.headers` 保留 exact value。
- 再从五个独立 owner边界证明：Tool Trace hot/cold/query、audit exact serialization、public HostEvent/activity、LLM-facing messages/memory/compact/runner-call observation、operator logs均不含 sentinel。
- 禁止字段名黑名单、下游 normalization/repair、loose scan、mock-only bypass、production改动、secret type split/descriptor/resolver/manager或统一授权框架。
- Real configured-value scan必须按 logical owner分类：Config source和 exact Host internal effective runner headers 是 `ACCEPTED_TRUSTED_INTERNAL`；其它 Host logical row/path必须为零。所有 `ZERO_REQUIRED` surfaces逐类计数为零。扫描输出与 artifact不得包含真实 secret value/ref或命中正文。
- 读取 `tests/README.md` 更新约束并记录 `NO_UPDATE` 直接理由，不修改 README。

## 4. Validation and stop rules

- Fresh执行 corrected plan §4.1 全部 focused tests与三个 real smoke；再执行 §6 全部门禁，包括 canonical suite、exact-exclusion coverage、full pyright、scoped/full Ruff baseline、build、six scans、README/security/deferred/no-code ledger、configured-value semantic scan、diff/check/staged-empty/exact allowlist。
- Canonical suite只允许顺序上尚未实施的 AR-F02 import-boundary单节点失败；其它失败立即 STOP。Coverage同样只允许该中间失败，九个 AR-F05 paths保持 `OPEN_BY_SEQUENCE`，不得签最终 coverage PASS。
- 若 owner test发现任何真实 Tool Trace/audit/public/LLM/log leak，立即 STOP并记录具体 projection owner，不得在本 gate私自修 production或扩大 scope。
- 若需要第九个 test、任何 production path、README、utility、design/plan/control修改，或 protected path/hash发生非授权漂移，立即 STOP。
- 完成后停在 Controller validation；不得自行发送 code review。

## 5. Authorized exit

只有全部门禁满足后，Slice 1 才可报告：

```text
AR-F01 = CLOSED
AR-F03 = CLOSED
AR-F04 = CLOSED
S1-SEC-F01 = CLOSED_AS_NO_CODE_BLOCKER
AR-F02 = OPEN_BY_SEQUENCE
AR-F05 = OPEN_BY_SEQUENCE
AR-F06 = RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX
AR-F07 = PENDING_RELEASE_BLOCKER
```

Next gate只能是 Controller validation，不能是 code review、Slice 2、commit或 aggregate。
