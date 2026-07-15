# WU-SEMANTIC-OWNERSHIP-01 R03 Aggregate Re-Review Controller Adjudication

## 1. Gate 与最终结论

- gate：R03 complete aggregate re-review。
- MiMo artifact：`docs/reviews/wu-semantic-ownership-01-r03-aggregate-rereview-mimo.md`。
- DS artifact：`docs/reviews/wu-semantic-ownership-01-r03-aggregate-rereview-ds.md`。
- zero-change fix：`docs/reviews/wu-semantic-ownership-01-r03-aggregate-deepreview-fix-codex.md`。
- Controller validation：`docs/reviews/wu-semantic-ownership-01-r03-aggregate-deepreview-fix-controller-validation.md`。
- decision：`ACCEPTED_AGGREGATE_RE_REVIEW / ZERO_FINDING / ACCEPTED_LOCAL_COMMIT_AUTHORIZED`。

两路 reviewer 都重审了 `8c6ae966..HEAD + working tree` 的完整 S1-S3、F01-F03、zero-change proof 与 Controller post-proof additions，而不是只审 Markdown delta。MiMo 与 DS 均明确返回 `PASS`、accepted finding `0`、blocking open question `0`；Controller 接受该一致结论。

## 2. Findings 最终 ledger

| finding set | final status |
|---|---|
| `R03-AGG-CV-F01` | `CLOSED`；typed Compact evidence 保留 shared renderer exact text。 |
| `R03-AGG-CV-F02` | `CLOSED`；shared projection 正确区分 hot inline 与 cold descriptor并严格 fail closed。 |
| `R03-AGG-CV-F03` | `CLOSED`；request/awaiting/result strict diagnostics 只消费 typed canonical facts。 |
| initial aggregate deepreview findings | accepted `0`、rejected `0`、deferred `0`。 |
| aggregate re-review findings | accepted `0`、rejected `0`、deferred `0`。 |
| blocking open questions | `0`。 |

没有 accepted finding 被留作“后续优化”，也没有 re-review 新增 current fix gate。

## 3. Protected proof 与 post-proof additions 裁决

两路独立确认：

- protected path count=`80`；ordered-path SHA=`75d464307db88470d1f8efcb9b302c9f18b3d3bc4396ca8bff5ae0ff4ee10e9a`；
- zero-change 时 status/path SHA=`8ee8baa8cd0e667ea08c106f904dd2bace5893cd3a8c51a130db8ba4680eeed5`；
- R03 product/tests/README/smoke 与关键 artifacts 的逐文件 content hash 未漂移；
- zero-change proof 后只出现三项授权动作：AgentCodex 新增 zero-change artifact、Controller 新增 validation artifact、Controller 更新 control gate；
- 80-path aggregate content SHA 当前变化只来自已明确授权的 control content delta；其它 79 个 protected paths 未变化；
- staged set 为空，`git diff --check` 通过，无 unauthorized target。

因此 zero-change proof 没有被 Controller gate-state 更新伪造或破坏。

## 4. 组合语义与安全最终裁决

- ordinary / awaiting accepted call 继续复用唯一 canonical request atom writer；`TOOL_AWAITING` 不复制 arguments/digest。
- wait-resolution result identity 来自 suspended source Attempt，precondition mismatch 在 mutation 前 fail closed。
- RunInput、Durable Memory、Memory、Compact、LLM-ready Tool Trace 从同一 typed accepted material派生；缺 material 统一 fail closed。
- opaque refs 只在 internal provenance/audit owner，未进入 RunInput、Memory、Compact 或 LLM-readable Trace 业务来源。
- LLM-facing source/query/schema 文本业务可读，无 safe-arguments blacklist repair、internal ref guessing 或 governance id 冒充业务事实。
- DNS/peer、path containment、symlink、resource budget、atomic/process fencing、Host durable integrity 与 internal provenance 均保留。
- 未设计或实现统一 tool authorization framework、BusinessSource abstraction、credential broker 或 compatibility shim。
- Issue 142、151、175、177、178 未被偷带实现。

## 5. Residual risk 最终状态

| risk / observation | final owner / destination | blocker? |
|---|---|---|
| 两个 full-suite logging-order failures | `utils/smoke_web_ci.py` / Web smoke test-harness owner；若 umbrella 最终 aggregate regression 仍复现，必须进入最终 aggregate finding ledger并由该 owner关闭。 | 否；隔离共同运行 `2 passed`，不经过 R03 changed owner。 |
| macOS coverage + NumPy/Pandas spawn instrumentation | validation harness/environment owner；未来 process-boundary 变更继续使用 plain spawned-process tests取证。 | 否；Web/Fins完整文件 plain tests已通过。 |
| waiting private helper store 实例化 | Host waiting owner；`STYLE_OBSERVATION / NO_CURRENT_FIX`。 | 否。 |
| Host wait expiry中文文案 | Host waiting error projection owner；`OWNER-CORRECT / NO_CURRENT_FIX`。 | 否。 |
| future cold wait-result hypothetical | Host wait-result schema + RunInput/shared projection owner；只有 owner schema 真正改为 cold descriptor时重新验证。 | 否；当前 wait result inline。 |

所有 residual risk 均有 owner/destination；没有当前 R03 accepted finding。

## 6. Accepted local commit 授权

Controller 只授权提交当前 R03 aggregate exact scope：

- `dayu/host/accepted_result_projection.py`
- `dayu/host/compact_material.py`
- `tests/host/test_accepted_result_projection.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_toolruntime_accept_barrier.py`
- `tests/runtime/test_smoke_host_public_r03_semantic_ownership_assembly.py`
- `utils/smoke_host_public_r03_semantic_ownership.py`
- 本轮 aggregate validation/fix/deepreview/re-review/Controller artifacts；
- `docs/host/issues-implementation-control.md` 当前 R03 gate-state diff。

提交前必须再次通过 `git diff --check`、确认 staged path 与该 exact scope 完全一致、确认无 credential/raw config 与 deferred owner path。不得 push，不得混入 R04。

accepted local commit 只完成 R03 internal remediation sub-WU；不完成 umbrella WU。commit 后必须记录 R03 completion report、accepted commit 与 residual owner，再以前一 accepted commit 为 base 进入 R04 plan gate。
