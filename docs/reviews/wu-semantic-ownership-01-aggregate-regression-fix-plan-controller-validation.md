# WU-SEMANTIC-OWNERSHIP-01 aggregate regression fix plan Controller 验证

## Gate 身份

- Active work unit 仍是 `WU-SEMANTIC-OWNERSHIP-01`；这是 umbrella overdesign remediation continuation 的 aggregate regression accepted-finding 修复计划，不是新 WU。
- Reviewed target：`docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`。
- Target metrics：610 行 / 44,252 bytes / SHA-256 `a01e8772c49f975e2f66058a8febc470f063c900d169461494c506c43e14782e`。
- Immutable implementation baseline：`ed9bfa9fe071aba0227361c69a938010ce3abe09`；aggregate comparison parent：`3410d7422655c56bdf13c643f77c27f40b9d4550`。

## Controller evidence check

- 完整读取计划，并与 `AGENTS.md`、umbrella optimization control、overdesign controller discussion、五份 design 真源、aggregate regression evidence 和 Controller adjudication 对照。
- 计划只关闭 Controller 接受的 `AR-F01`—`AR-F05`：Slice 1 修 current-schema/test harness/artifact oracle，Slice 2 迁移 Fins public contract owner，Slice 3 只补九个 owner-path coverage tests；总计三个 slices，符合 umbrella slice 上限。
- 当前代码直接证明 Service allowlist 对 `dayu.fins.ingestion` 使用前缀匹配，且已允许 `dayu.fins.direct_events`；因此把 validator 物理迁入 `direct_events.py`、把 awaiting mode 放入 `dayu.fins.ingestion.awaiting_resolution` 能在不扩大 allowlist 的前提下关闭边界缺陷。
- `ValidatedFinsEventStream` 当前只由 `direct_stream.py` 持有，而 direct event、typed protocol error 与 operation kind 已由 `direct_events.py` 持有；计划的物理 owner migration 不复制类型、不保留 compatibility re-export/lazy import/facade，也不改变 terminal state machine。
- awaiting mode 三项语义当前确实混在 private tools helper，Service 直接越界消费；计划迁到 Fins ingestion public owner，同时保留 outcome/argument helpers 在 tools private owner，边界切分成立。
- compactor oracle 只使用 current runner manifest 的 `host_run_id` / `runner_call_kind` / `compaction_request_digest` 与 compact artifact 同源 digest，禁止 candidate-id、文件名、顺序、mtime、loose scan 和 historical fallback。
- Web logging 修复明确限制在 in-process test harness，并保护 standalone smoke、runtime logging 与全局 conftest 零 diff；host runtime fixture 只补 current required schema，不向 ConfigLoader 加兼容默认值。
- 九个低/未覆盖 production owners 全部被列为 zero-diff；测试暴露 production defect时必须停止重新裁决，禁止 coverage seam、实现镜像、omit、xfail 或 threshold 降级。
- `AR-F06` 始终是 `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`，coverage 仅使用已裁决的单 node exclusion，canonical non-coverage suite仍执行该 node；`AR-F07` 始终是外部 Windows `PENDING_RELEASE_BLOCKER`。
- 计划精确列出 mutable production/test/README allowlist、protected paths、pre-existing Controller-owned worktree hash保护、每 slice 双路 review/fix/完整 re-review、aggregate regression/deepreview、pyright、Ruff、coverage、build、README/security/deferred/no-code 和真实 smoke 门禁。
- 当前 `git diff --check` 通过，staged tree为空；除本 plan 外没有 AgentCodex 新增的 product/test/README/workflow/control 修改。

## Mandatory plan-review challenges

双路 reviewer 必须独立挑战而不能仅复述计划：

1. `direct_events.py` 合并 validator 后是否形成 import cycle、过宽 public module 或隐藏的额外 consumer，及 awaiting mode 新 owner是否真能保持 Service allowlist零改动。
2. logger registry snapshot/restore 是否能在成功、错误码、`SystemExit`、被测异常与新增 logger/handler 场景下完整恢复，且不会关闭调用前存在的 handler。
3. runner-call manifest 到 compact artifact 的 digest关联是否在 current schema中唯一、严格、可测试，是否遗漏 duplicate/malformed fail-closed 路径。
4. Slice 3 六个测试文件是否足以通过 public/owner-observable contract覆盖九个 production paths，而不复制私有算法或构造不可能状态。
5. 219-path ledger、R05 single-node coverage exclusion、Ruff immutable baseline和 Slice 1临时 import-boundary failure是否可执行且不会被误签为 waiver/PASS。
6. 三 slice顺序是否是最小可验证闭环，及每 slice 全量验证成本是否仍符合 umbrella optimization control。

## Verdict

**PASS_WITH_MANDATORY_CHALLENGES / READY_FOR_DUAL_COMPLETE_PLAN_REVIEW。**

当前不授权 implementation、stage、commit、push、PR、aggregate deepreview或 closeout。下一 gate 仅允许 AgentMiMo 与 AgentDS 对上述 immutable plan 做并发、完整、独立 `$planreview` 等价审查。
