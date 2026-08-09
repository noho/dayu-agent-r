# wu-cli-interactive-02 PR review adjudication

## Gate metadata

- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Gate：draft PR review initial adjudication
- PR：[#190](https://github.com/noho/dayu-agent-r/pull/190)
- Reviewed remote head：`a4ff05db`
- AgentMiMo artifact：
  `docs/reviews/pr-review-wu-cli-interactive-02-mimo-20260802.md`
- AgentDS artifact：
  `docs/reviews/pr-review-wu-cli-interactive-02-ds-20260802.md`
- Decision：`1 accepted / 3 rejected / 0 deferred / 0 unclassified`
- Next gate：AgentCodex PR review finding fix

## Controller decision

两路 reviewer 均从 GitHub draft PR #190 的远端 metadata、base/head、commit chain、
PR body 与完整 `main..a4ff05db` diff 独立审查。两路都确认：

- PR 为 OPEN/DRAFT，base=`main`，merge-base=`113ea34d`，无 base drift；
- 原始 `ae6bb96f`、`cc5c9d57` 是 PR commit chain 的前两个提交；
- F01–F13 owner implementation、docs、tests、secret boundary 与 merge correctness
  没有 blocking/high finding；
- GitHub 当前没有 reported checks，不能伪称 CI pass；现有 validation 仍以 durable
  local owner/integration/pyright/smoke evidence 为准。

AgentMiMo 没有 finding。AgentDS 提出四项观察；Controller 逐项回到 HEAD 代码与
项目约束裁决，只接受其中一项。

## Finding adjudication

### PR-A01 / accepted-low / duplicate accepted-result required-field owners

- **Source**：DS finding 2。
- **Direct evidence**：`dayu/host/dispatch.py` 与
  `dayu/host/engine_ingest.py` 分别定义内容完全相同的
  `_required_successful_response_identity(result)` 和
  `_required_compactor_manifest_reference(result)`。两路都从同一个
  `CompactionOperationResult` optional fields 产生相同 RuntimeError semantic。
- **Owner decision**：这些字段的 accepted-result presence invariant 属于
  `dayu.host.compaction_operation.CompactionOperationResult`，proactive/reactive
  callers 只应机械消费 typed owner，不各自维护校验与错误文本。
- **Required fix**：在 `CompactionOperationResult` 上提供两个明确的 required
  accessor method，迁移两类 caller，删除四个 local helpers，并把 existing guard
  test 移到 result owner，同时补 response identity missing guard test。不得改变
  dataclass fields、operation result construction、wire/schema、terminal CAS 或
  accepted/rejected behavior；不得新增 compatibility wrapper或 public re-export。
- **Severity**：low；当前两份实现一致，无现时行为 bug，但违反项目唯一 owner
  约束，未来 drift 风险真实存在。

### PR-R01 / rejected / missing breaking-change statement

- **Source**：DS finding 1。
- **Decision**：`rejected-explicit-new-contract`。
- **Evidence**：用户与 AGENTS.md 明确禁止旧 schema/旧测试兼容；F13 冻结语义要求
  successful Engine terminal/outcome 必须携带 required identity。`docs/engine/design.md`
  与 `dayu/engine/README.md` 已明确写出 `FinalAnswerData.response_identity` 和
  `EngineRunOutcomeFinalAnswer.response_identity` 是同一个 required typed fact，
  全仓构造点、Engine/Host tests 与 pyright 已同步闭合。再在 PR body 使用迁移/兼容
  叙事不会关闭新的 correctness gap。

### PR-R02 / rejected / dead `args` parameter

- **Source**：DS finding 3。
- **Decision**：`rejected-factual-error`。
- **Evidence**：远端 reviewed head 的
  `_resolve_interactive_binary_stdin(*, stdin, explicit_binary_stdin)` 不接收
  `ParsedCliArgs`；它真实使用两个参数选择显式 binary stream或标准
  `TextIOWrapper.buffer`，否则 fail closed。review artifact 引用的
  `def _resolve_interactive_binary_stdin(args)` 不是 PR HEAD 代码。

### PR-R03 / rejected / blank non-TTY should print feedback

- **Source**：DS finding 4。
- **Decision**：`rejected-frozen-contract`。
- **Evidence**：F06 明确要求空或纯空白 stdin 不创建 Run并 exit 0，non-TTY 不显示
  `dayu>`。新增 stderr 提示会改变已冻结 CLI output contract，并扩大正式 oracle；
  当前静默成功是预期行为而非 UX 缺陷。

## Residual-risk decision

- G01–G07、formal interactive scenarios 与 renderer target closure 继续属于后续
  calibration；不在 PR review fix 中处理。
- GitHub 无 reported checks 是明确 external validation gap。它不否定已完成的 full
  pyright、owner/integration tests 和真实 smokes，但 final closeout 必须如实记录。
- `INVALID_MULTIPLE` fail closed、whole-stdin blocking read、platform-specific signal
  能力均是已冻结或已分类边界；本 finding fix 不扩张新恢复、streaming或跨平台框架。
- 当前只有 PR-A01 进入 fix；没有 deferred、blocking 或未分类 residual risk。

## Next gate

AgentCodex 只修复 PR-A01，补 owner-level contract tests并运行受影响 Host tests、
coverage、full pyright、diff/secret checks。随后 AgentMiMo、AgentDS 必须对远端 PR
fix diff 与本 adjudication 同时独立 re-review；未双路通过前不得进入 final push
或 draft-PR-pass。
