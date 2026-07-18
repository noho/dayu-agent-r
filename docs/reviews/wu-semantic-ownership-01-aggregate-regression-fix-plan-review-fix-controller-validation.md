# WU-SEMANTIC-OWNERSHIP-01 aggregate regression fix plan review-fix Controller validation

## 1. Gate identity

- 时间：`2026-07-18 16:50:03 +0800`。
- Work unit：`WU-SEMANTIC-OWNERSHIP-01`；这是既有 umbrella overdesign remediation continuation，不是新 WU。
- Gate：accepted plan-review finding fix validation。
- 结论：`PASS / AR-PLAN-PF01..02 CLOSED / READY_FOR_DUAL_COMPLETE_FIXED_PLAN_REREVIEW`。
- Implementation、stage、commit、push、PR、aggregate deepreview 与 closeout 仍未授权。

## 2. Immutable evidence

- Final plan：`docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`，640 行 / 50,784 bytes / SHA-256 `7e91421b8bc8c442dcf72e94c20eb84d4f27f2b9878b427481448d6f2f4ea714`。
- AgentCodex fix artifact：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-fix-codex.md`，90 行 / 9,320 bytes / SHA-256 `9dee714839efbef9b5743bfe55b7bb7ffc1d923e9906413479716a88c340069e`。
- Controller adjudication：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-controller-adjudication.md`，SHA-256 `a5876c47c38c3d80091e20e7958932af8cdf2430f80ef8ee96e9b40a647eaa06`。
- Branch / HEAD：`phaseflow/host-issues-control` / `ed9bfa9fe071aba0227361c69a938010ce3abe09`；staged tree为空。

## 3. Accepted finding closure

### AR-PLAN-PF01 — CLI direct-stream test consumer

`tests/cli/test_fins_commands.py` 已进入 Slice 2 精确 mutable test allowlist、focused pytest 与 direct-owner consumer scan。旧 `dayu.fins.direct_stream` scan 固定覆盖 `dayu tests utils` 并要求零命中；计划没有引入兼容模块、re-export、fallback 或 Service allowlist 扩张。`CLOSED`。

### AR-PLAN-PF02 — public-awaiting validation utility

Slice 2 已新增独立 mutable validation-utility allowlist，且唯一成员是 `M utils/smoke_host_public_awaiting_entrypoint.py`。该路径只允许迁移 `AwaitingResolutionMode` import；Controller 直接源扫描确认其非 import 使用位置精确为九处：455、456、457、786、807、823、839、852、919，计划与 fix artifact 均已按九处锁定。Owner migration 后必须 fresh 运行 public-awaiting smoke；definition、consumer 与 stale-private scans 均固定覆盖 `dayu tests utils`。`CLOSED`。

## 4. Scope and consistency validation

- Controller 完整通读 final plan 640 行与 fix artifact 90 行。
- `git status --short` 只比 plan-fix entry 多出固定 AgentCodex fix artifact；全部九个 pre-existing protected paths 的 status/SHA-256 与 entry baseline一致。
- Plan hash从 entry `a01e8772c49f975e2f66058a8febc470f063c900d169461494c506c43e14782e` 变为 final `7e91421b8bc8c442dcf72e94c20eb84d4f27f2b9878b427481448d6f2f4ea714`，与 fix artifact记录一致。
- 全文无“八个业务/类型使用位置”残留；§3.3—§3.5 引用、CLI test allowlist、validation utility allowlist、Slice 2 focused gate、final aggregate scans与 stop conditions互相一致。
- `git diff --check`通过；`git diff --cached --name-status`为空。
- AR-F06 保持 `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`；AR-F07 保持 `PENDING_RELEASE_BLOCKER`。Topic 8-9、security、deferred ISSUE 与 219-file coverage contract均未被扩写或弱化。
- 本 gate 是 plan-only；未运行 implementation tests、pyright、Ruff、build 或 product smoke，且这不替代后续 slice 门禁。

## 5. Next gate

AgentMiMo 与 AgentDS 必须分别对上述 immutable final plan 做从零完整 re-review，确认 `AR-PLAN-PF01..02` 真正关闭、rejected/no-fix 建议未被偷带、三个 slices仍 code-generation-ready，并报告任何新 finding。两路结果经 Controller 裁决前不得实施。
