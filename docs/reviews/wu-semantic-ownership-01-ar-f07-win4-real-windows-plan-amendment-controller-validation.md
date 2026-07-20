# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4 Real-Windows Plan Amendment Controller Validation

## Result

`PASS_WITH_MANDATORY_CHALLENGES / READY_FOR_DUAL_COMPLETE_PLAN_REVIEW / IMPLEMENTATION_NOT_AUTHORIZED`

## Identity and scope

- Umbrella：`WU-SEMANTIC-OWNERSHIP-01`；continuation：`AR-F07 WIN4`；不是新WU。
- Frozen remote target：`b85def887e72dc69e972f42a82a18989523f8634`。
- Plan before SHA-256：`2359f24251838ec5d779ed0a1eb804ebacce3405e102a0cbc50a70f5844fd73a`。
- Plan after SHA-256：`79e984d6fe5fe1ce08cd1affc60b241f9691c6ba94b9ec3e75850676b9d61bb4`。
- AgentCodex amendment artifact：
  `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-plan-amendment-codex.md`，
  SHA-256 `b985a2a402255c0be7fef49b2d428c70d3f5dd459f9026f2d958fa4dc8dc1cf9`。

AgentCodex只修改既有plan并新增指定artifact；production、test、README、workflow、design与stage均未改变。
Plan diff为379 insertions/7 deletions，`git diff --check`通过。

## Owner and root-cause validation

Controller独立复核两次dispatch metadata、failure logs、downloaded artifacts、当前CLI output owner、Fins storage public
repositories、CPython 3.11 getpass实现与init输入顺序，确认：

- WIN4-RW-F01发生在真实upload exit `0`且storage publication完成之后，旧`Fins result` display consumer是唯一失败点；
- WIN4-RW-F02发生在required secret读取，早于confirmation、staging和setx；Windows `win_getpass`的console path不消费
  OS-level redirected stdin；
- capability-based TTY/redirected分流是CLI secret-input owner的最小修复，不应使用Windows/GitHub Actions/test identity；
- `WIN4-RW-S1`与`WIN4-RW-S2`的owner、路径、验证和回滚边界不同，精确2 slices合理。

Plan把业务success迁移到process exit和`dayu.fins.storage` public repository facts，同时把filesystem count降为physical
artifact integrity，符合唯一owner约束。Controller额外验证了下载后的GitHub artifact不是可重新打开的完整storage snapshot：
upload bundle不含storage内部hidden identity descriptors。该事实不否定plan，因为repository读取明确发生在runner上的test
进程内、artifact上传前；下载bundle只能承担plan已限定的hash/count/inventory证据，不能被后续Controller当作业务仓储重放。

## Mandatory review challenges

两路review必须独立完整挑战：

1. `WIN4-RW-S1`是否在test进程内正确使用`FsCompanyMetaRepository`、`FsSourceDocumentRepository`和bounded
   `SourceSnapshotProtocol`生命周期，且不从downloaded artifact、raw JSON/private core或display text反推业务成功；
2. `_read_secret_input`的`isatty()`分流、prompt stderr+flush、单次`readline()`、LF/CRLF、EOF和KeyboardInterrupt语义
   是否自洽，尤其不能让pytest/Windows现有getpass fixtures意外走redirected path而固化错误测试；
3. required/optional/confirmation顺序和value-free error是否完整，是否需要更窄的owner-level seam而不引入callback/factory；
4. ROOT README与tests README更新是否确属读者职责，且不会把pipe transport误写成加密或推荐携带真实key的命令；
5. remote R11/R12 acceptance是否锁定fresh dispatch response run id、accepted implementation head与same-run evidence，
   并保持canary value-free、standalone R11无canary声明。

## Security and deferred boundary

- TTY secret仍由getpass隐藏；redirected secret只由caller-owned stdin传输，CLI不主动回显。Plan没有承诺外部shell/process
  inspection安全，也没有新增zeroization或credential broker。
- Config与Host internal SQLite/EventLog仍是trusted-local domain；Tool Trace/audit保持API key零明文。
- 无统一tool authorization、secret infrastructure、PowerShell/PTY/console/job-object/process-tree框架。
- Issue 142、151、175、177、178及Web/WeChat/render均未进入implementation scope。
- Gemini low-budget仍是`EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`。

## Next gate

下一gate只允许AgentMiMo/AgentDS并发完整review全部1045行amended plan与direct evidence。任何accepted finding必须由
AgentCodex修plan并双路完整re-review；在accepted amended-plan commit前不得implementation、push、dispatch或PR review。
