# PR 190 F17 Final Closeout

## Outcome

F17 已从 root cause 修复：当前 package prompt raw bytes、冻结 workspace publication manifest
中唯一对应 asset entry、保存后 manifest raw bytes digest 与测试 pin 已重新形成严格单向派生链。

没有修改 prompt 内容、production init transaction、validator、fixture/assertion、CLI 产品行为、
Host/Engine schema/public contract、Oracle/scenario registry 或 readiness 状态。F14 coverage frontier 与
F15/F16 修复未被回滚或稀释。

## Root cause 与唯一 owner chain

F13 更新了 `conversation_compaction_user.md` 的 LLM-facing bytes，却遗漏 init publication 的两个
派生 consumer：manifest asset digest 与 manifest raw-byte test pin。production init 行为本身正确，
strict validator 也正确 fail closed；错误是真源 bytes 改变后冻结 consumer 未同步。

唯一链路：

1. `dayu/config/prompts/scenes/conversation_compaction_user.md` raw bytes：LLM-facing 内容 owner；F17 只读。
2. `dayu.cli.init_workspace` transaction：production publication owner；F17 不改。
3. `docs/cli_init_workspace_manifest_v1.json`：冻结 publication consumer；只更新目标 entry。
4. 保存后的 manifest raw bytes：manifest identity producer。
5. `FROZEN_MANIFEST_SHA256`：manifest identity consumer；从第 4 步实际 bytes 重算。

没有动态 expected、loose comparison、compatibility、fallback、第二 manifest、第二 cursor 或测试跳过。

## Final publication truth

- Prompt raw SHA-256：
  `22e7bc5015cb369ff228a754b557493594b8313c99877944b5a7c08da0dc1c88`
- Manifest target entry：
  `22e7bc5015cb369ff228a754b557493594b8313c99877944b5a7c08da0dc1c88`
- Manifest raw SHA-256：
  `064f80660b2cba0f16db392a46e8dc68ac45fdcd31252f96423c854e342cae22`
- `FROZEN_MANIFEST_SHA256`：
  `064f80660b2cba0f16db392a46e8dc68ac45fdcd31252f96423c854e342cae22`
- Inventory：5 directories / 43 files / 16 model pointers
- Fresh production FIRST strict result：`valid=true`、`issues=()`；不存在第二个 path、digest 或
  model-pointer mismatch。

## Actual product/test changes

相对 F17 起点 `e1217811ad57e48c90e3763994930e53378ba060`，产品/测试 consumer 只有：

- `docs/cli_init_workspace_manifest_v1.json`：1 insertion / 1 deletion，唯一 target entry digest。
- `tests/cli/test_smoke_cli_init_provider_matrix.py`：1 insertion / 1 deletion，唯一 raw manifest pin。

以下 protected paths 均零 diff：prompt、`utils/smoke_cli_init_provider_matrix.py`、production transaction、
validator、fixture/assertion logic、`docs/cli_ci.md`、README、Oracle/scenario/readiness registries、Host/Engine
schema/public contract。

其余 F17 files 都是 Gateflow evidence；加上本 closeout 后完整 evidence inventory 为：

- `docs/gateflow/pr-190-f17-goal-confirmation-20260807.md`
- `docs/gateflow/pr-190-f17-plan-20260807.md`
- `docs/gateflow/pr-190-f17-plan-acceptance-20260807.md`
- `docs/gateflow/pr-190-f17-plan-review-adjudication-20260807.md`
- `docs/gateflow/pr-190-f17-implementation-20260807.md`
- `docs/gateflow/pr-190-f17-implementation-review-acceptance-20260807.md`
- `docs/gateflow/pr-190-f17-aggregate-review-adjudication-20260807.md`
- `docs/gateflow/pr-190-f17-aggregate-deepreview-acceptance-20260807.md`
- `docs/gateflow/pr-190-f17-pr-review-adjudication-20260807.md`
- `docs/gateflow/pr-190-f17-pr-review-acceptance-20260807.md`
- `docs/gateflow/pr-190-f17-draft-pr-gate-pass-20260807.md`
- `docs/gateflow/pr-190-f17-final-closeout-20260807.md`
- `docs/reviews/plan-review-20260807-143241.md`
- `docs/reviews/plan-review-20260807-143636.md`
- `docs/reviews/plan-review-20260807-144241.md`
- `docs/reviews/plan-review-20260807-144253.md`
- `docs/reviews/code-review-20260807-145315.md`
- `docs/reviews/code-review-20260807-145453.md`
- `docs/reviews/code-review-20260807-150010.md`
- `docs/reviews/code-review-20260807-150018.md`
- `docs/reviews/code-review-20260807-150638.md`
- `docs/reviews/code-review-20260807-150646.md`
- `docs/reviews/code-review-20260807-151055.md`
- `docs/reviews/code-review-20260807-151116.md`
- `docs/reviews/pr-190-review-20260807-152226.md`
- `docs/reviews/pr-190-review-20260807-152555.md`
- `docs/reviews/pr-190-review-20260807-153345.md`
- `docs/reviews/pr-190-review-20260807-153416.md`

## Validation

Clean committed target 上最终结果：

- `pytest --collect-only -q tests/cli/test_smoke_cli_init_provider_matrix.py`：71 collected。
- `pytest -q tests/cli/test_smoke_cli_init_provider_matrix.py`：71 passed，3 个第三方 edgar
  deprecation warnings。
- fresh production FIRST publication + strict validator：`valid=true`、`issues=()`、5/43/16。
- 标准库 JSON parser + AST pin + raw-byte assertions：prompt=entry，manifest=pin，counts=5/43/16。
- `python -m json.tool docs/cli_init_workspace_manifest_v1.json`：exit 0。
- `python -m pyright dayu/ tests/ utils/`：0 errors / 0 warnings / 0 informations。
- changed-files Ruff：All checks passed。
- changed-files compileall：exit 0。
- `git diff --check e1217811..HEAD`：exit 0。
- exact changed-file guard：两个 product/test files 各一个单行 digest hunk；其它 protected paths 零 diff。

Controller 第一次 final digest assertion 命令含 f-string 转义语法错误，因 fail-fast 在静态检查前停止；
该只读 observation command 没有修改文件。修正后从 digest assertion 起重跑，全部通过。没有把该 harness
command failure 归为产品 failure，也没有把未执行步骤误记为成功。

没有运行全仓 pytest：F17 只改冻结数据 consumer，风险对称的 owner suite、fresh production publication、
full pyright 与静态检查已全部通过。GitHub 分支没有 status checks；本地结果不能表述成远端 CI PASS。

## Tests vs real observation

F17 验证使用 fresh 临时 workspace 与 production init lock/transaction owner 构造真实 publication tree；
它不是动态 fixture expected，也没有 fake/mock provider/tool 冒充 production scenario。F17 不调用 LLM provider、
财报工具或 PTY，因为本 work unit 没有修改 init/prompt/interactive runtime 行为，只修 deterministic publication
consumer。

因此本 closeout 不声称执行了新的 real provider/PTY/Oracle observation。F14/F15/F16 的历史真实 evidence
继续保留原 provenance；三条 replacement scenarios 仍为 `unadjudicated`，需要 Oracle controller 的真实观察
裁决后才可能形成 readiness proof。

## Review closeout

- AgentMiMo / AgentDS plan review 与 re-review：通过，remaining finding 0。
- AgentMiMo / AgentDS implementation code review：无实质 finding。
- Aggregate deepreview：产品 finding 0；一条 stale working-tree evidence finding 已由 AgentCodex 修复并双路复核。
- PR review：remaining product/code finding 0；错误 F17 baseline attribution 已修正并双路复核。
- GitHub no-checks：`deferred-with-owner`，repository CI / merge policy；明确保留为 gap。
- 其它 full-PR 候选已基于直接 owner evidence 驳回：已有 runtime/Engine enum invariant test；无 stream
  互斥 contract；README 明确旧 session scope 不迁移；future failure-payload storage 与同名测试文件不是当前 defect。

## Commits and PR state

F17 closeout 前 commits：

- `0d21529671803288768efeb350c73e1bc713140d` — accept plan
- `305c101232cc5114ee4736b402236c7f318dbad1` — refresh frozen publication digest
- `33f6c16d164930e7583d7db8cb4ea58b04eda541` — accept aggregate review
- `dcc083994c91313e485e6218e7d8bb64d55b6fa7` — fix aggregate evidence formatting
- `386da1fd6aea0b9b36b5cada50efce2969462cfa` — accept PR review
- `d969bf745d982a348a579f3a8b123316a49add3b` — record draft PR gate pass

本 artifact 所在 final closeout commit SHA 由 Controller 在提交后写入最终 handoff，避免在 commit 内容中伪造
自身尚未生成的 SHA。

PR 190 在 draft-pass head `d969bf745d982a348a579f3a8b123316a49add3b` 时为 `OPEN`、`DRAFT`、
mergeable/clean，base `main`，requested reviewers 空；no checks reported。Final closeout commit 只会
fast-forward 同一 head branch；完成后 Controller 必须重新读取 PR API 报告最终 SHA/status。

没有创建新 PR、merge、mark ready、approve/request reviewers、rebase、force-push 或删除分支。

## Remaining risks and adjudication state

- GitHub no-checks 是明确 CI gap；合并策略 owner 后续处理。
- 三条 formal replacement scenarios 保持 `unadjudicated`，Oracle/readiness 仍待用户裁决。
- F17 没有新的 real provider/PTY observation；它只证明 deterministic production init publication truth。
- 未来 package asset 变化仍会由 strict owner suite fail closed；本 work unit 没有引入自动改写 manifest 的第二写路径。
- PR 190 体量大；本次 full PR review 结合既有 review provenance 与并行重点走读，但 no-checks 和未裁决
  scenarios 使其不能被称为 ready 或 mergeable release proof。
