# WU-SEMANTIC-OWNERSHIP-01 R05 Aggregate Zero-Change Fix Controller Validation

## 1. Gate 与 verdict

- umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU。
- gate：R05 aggregate zero-change fix Controller validation。
- AgentCodex artifact：`docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-fix-codex.md`。
- artifact SHA-256：`1ac2278d7419420f9a896805fdb4311c1a26d9bcb4e49784661744fa166ced43`。
- validation HEAD：`45fe5cc41f230014c3d7c3efcb6552f48764d6f4`。
- verdict：`PASS / READY_FOR_DUAL_FULL_AGGREGATE_REREVIEW`。

AgentCodex 正确执行了零产品改动 gate：accepted current finding 为零时，没有把 reviewer observation 或 later-owner residual 擅自升级为 R05 产品修改；唯一新增是指定 fix artifact。Controller 完整读取 artifact，并独立复算其核心证据。R05 产品、测试、设计、README transaction 未变化。

## 2. Controller 独立复算

### 2.1 Protected transaction

相对 R05 entry base `5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1`，按 aggregate validation 定义的 16 paths 执行 binary diff digest：

```text
41bd8c057cb5ff3d389f909a367a19037a65ae59ffda377cd317b9d1db4eda9a
```

有序 `git diff --name-only` path-set digest：

```text
ff3b00d67510c45396305a723a939b8006e9e740e61c8ff23ea6fb86e8389f4f
```

两者均与 R05 aggregate validation、两路 initial deepreview、Controller adjudication 和 AgentCodex fix record 精确一致。

### 2.2 Worktree ownership

Controller 复核时、写入本 validation artifact 前，完整 status 精确为：

```text
 M docs/host/issues-implementation-control.md
?? docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-controller-adjudication.md
?? docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-ds.md
?? docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-fix-codex.md
?? docs/reviews/wu-semantic-ownership-01-r05-aggregate-deepreview-mimo.md
```

- 排除唯一 fix artifact 后的 canonical status digest：`2976dd50b45e1e5fe56243dbf576fe37b6e33bcb21181fc9b5f836d0b6cb2e62`。
- 四个既有 dirty path 的有序 `shasum` manifest digest：`aaa13ec90e290326b0dd98eb04cb98f0708b6fa141d15a810d1f56852254df39`。
- staged paths：`0`。

这些值与 AgentCodex before/after record 一致，证明 AgentCodex 唯一写入为 fix artifact；没有修改 control、两路 review、Controller adjudication 或任何 product/test/design/README path。

## 3. Controller source / owner / security scans

Controller 独立执行并确认：

| 检查 | 结果 |
|---|---|
| `git diff --check` | exit `0`，PASS |
| untracked fix artifact whitespace | `git diff --no-index --check /dev/null <artifact>` 无 whitespace diagnostic；exit `1` 仅表示文件有内容 |
| no-diff owners | `agent.py`、Engine README、`_wait_observation.py`、`waiting.py`、durable schema、`dispatch.py`、`engine_ingest.py`、scheduler test 相对 R05 base empty diff |
| private smoke diagnostics | `_WaitPollerDiagnosticsHost`、`runner_dropped_count`、`observation_diagnostics_snapshot`、`._wait_poller`、`cast(` 零匹配 |
| timeout-only symbols | `mark_wait_record_poll_abandon_timeout`、`_MarkWaitRecordAbandonTimeoutOperation` 对 `dayu tests` 零匹配 |
| duplicate durable projection | `_durable_options_from_public_options`、`_durable_options_from_command_options`、smoke private `_durable_options` 零匹配 |
| unique durable projection | `HostDurableStoreOptionsSource` 与 `project_host_durable_store_options` 唯一定义于 `dayu/host/durable/options.py`；command/open-host/admin/smoke 共用 |
| old composition fallback | scene/name helper 与无参 `WaitPollerRuntimePolicy()` 零匹配 |
| deferred/security added lines | `authorization`、`permission`、callback transport、process isolation、process-backed、subprocess、Issue 175 零新增匹配 |

Controller 还直接走读了 poll/abandon timeout 分支：两者都在 non-close timeout 时调用 `_release_with_backoff` 写 transient diagnostic、释放 claim 并 backoff；timeout 分支不调用 resolver。Published typed result 才进入 `_resolve_claimed_wait`，authoritative `WaitPollLost` 路径保持。

## 4. Ledger、retained safety 与 residual

最终 ledger 保持：

| 分类 | 数量 | 状态 |
|---|---:|---|
| accepted current finding | 0 | CLOSED / NO PRODUCT FIX |
| no-fix observation | 3 组 | CLOSED WITH DIRECT REASON |
| retained residual | 2 | OPEN AT EXPLICIT LATER OWNER；R05 中未修、未 waive |
| blocker | 0 | NONE |

- `options.py` 缺少 `__all__` 不构成当前 public contract defect。
- scheduler-cross-owner 组合压力测试归 scheduler lifecycle residual 的后续 mandatory verification，不在 R05 用测试 shim 固化错误 oracle。
- scheduler close / terminal promotion coordination 是确定性真实 bug，owner 为 Host scheduler/lifecycle coordination；不归 R05 或 Issue 175，当前未修、未 waive。
- cancelled abandon 长期 capped retry 归 future Host durable evidence policy；不得从 timeout/retry count/timestamp 猜 LOST，当前未修、未 waive。
- token/generation fence、claim CAS、capacity/shared close deadline、typed LOST、explicit terminal marker、filesystem containment、allowed paths、Web 防御、DNS/peer proof、resource budgets、atomic write 与 process fencing 均未被本 gate 删除或放宽。

本 gate 没有实施 Issue 175、callback transport、统一 authorization/permission、R06+ 或 Issues 142/151/177/178。

## 5. 既有验证证据的使用边界

AgentCodex 没有冒充重跑测试、coverage、pyright、Ruff 或 public smoke；它明确只引用 `docs/reviews/wu-semantic-ownership-01-r05-aggregate-validation.md` 的 Controller evidence。由于 protected 16-path digest 未变，既有 `360 passed` functional aggregate、fresh 11-phase public smoke、S1 `83%/86%` coverage、S2 `88%/85%/100%` coverage、full pyright zero、changed Ruff green 与 full Ruff `167→165→162` 仍适用于相同产品 transaction。

README 不触发：本 gate 只增加 review/validation artifacts 和更新 control gate，不改变产品、测试 contract、架构、用户入口或工作流。

## 6. 下一 gate

下一 gate：AgentMiMo / AgentDS 双路 full R05 aggregate re-review。两路必须审查完整 16-path transaction、initial aggregate reviews、Controller adjudication、AgentCodex zero-change record 与本 Controller validation；确认 zero-change 唯一写入、finding ledger、Topic 5 closure、retained safety、两项 residual owner/destination 和 deferred boundary 均未漂移。

R05 aggregate accepted local commit、R05 completion、R06-R12、scheduler 产品修复、Issue 175、callback、统一 authorization、push 与 PR 均未授权。
