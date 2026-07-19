# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4 Real-Windows Plan Amendment Review Fix — AgentCodex

## Result

`PLAN_FINDINGS_FIXED / WIN4-RW-PR-F01..F04_ADDRESSED / READY_FOR_CONTROLLER_VALIDATION_AND_DUAL_COMPLETE_REREVIEW / IMPLEMENTATION_NOT_AUTHORIZED`

## Identity and evidence

- Timestamp（本机时钟）：`2026-07-20 05:49:14 +0800`。
- Work identity：既有 `WU-SEMANTIC-OWNERSHIP-01` umbrella remediation continuation / `AR-F07 WIN4`；不是新 WU。
- Fixed target：`docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`。
- Plan before：1045 lines，SHA-256
  `79e984d6fe5fe1ce08cd1affc60b241f9691c6ba94b9ec3e75850676b9d61bb4`。
- Plan after：1060 lines，SHA-256
  `7e82df117c5d7b97e13d8ee2ec156c19de6689c129f09cec979cd0b1bf8adb76`。
- AgentMiMo review：SHA-256 `6782a69f3fa47e895c47321f3c8674050357afea0a48cede474682617b9aca36`。
- AgentDS review：SHA-256 `7df6dbf7e8b12b705611b85f97a35fe9655b96b39e124f02716100ba5b8e7e91`。
- Controller adjudication：SHA-256
  `80c4966b839c968e3fa75cbac1271f8019d9d88c962281a6d9bb33134259ae15`，与指定值精确一致。

已完整读取 `AGENTS.md`、目标 plan 全部 1045 行、AgentMiMo/AgentDS 两路完整 review 与 Controller adjudication。
本次未读取、派生、落盘或回显 run-specific canary。

## First-principles disposition

四项 accepted findings 均成立，但都是既有 owner contract 的 plan 精确化，不支持扩大实现范围：

1. Public `SourceSnapshotProtocol` 已拥有 context-manager lifecycle；CLI test只能正确消费该 contract，不能重复拥有
   close-after-use 测试语义。
2. Secret-input capability 的 production owner读取 `sys.stdin`；既有 tests若依赖 ambient TTY或绕过 helper，就不能确定性验证
   owner boundary。
3. TTY 与 redirected EOF 的运行时表现不同，必须在 owner contract中显式映射为同一 value-free error。
4. CR 剥离只属于 CRLF logical ending；没有已移除 LF 的 bare CR 是 value的一部分，必须保留。

因此只修 plan specification与相关 owner-test/coverage/completion-report文字，不修改 owner、slice、allowlist、remote closure、
security或 deferred scope。

## Finding-by-finding fixes

### WIN4-RW-PR-F01 — fixed

- Plan位置：§13.2.1，after L747-L756；§13.5.1，after L849-L850。
- 修复：冻结
  `with source_repository.read_source_snapshot(..., materialize_files=False) as snapshot:`；identity、source kind、primary
  filename与 descriptors只在 `with` 块内读取。
- 边界：明确 CLI test不重复增加 Fins protocol owner的 close-after-use test。

### WIN4-RW-PR-F02 — fixed

- Plan位置：§13.4 WIN4-RW-S2，after L828-L832；§13.5.2，after L858-L863。
- 修复：受影响既有 getpass tests必须把 production实际读取的 `sys.stdin` 替换为 test-owned严格 typed TTY fake；
  `isatty()` 恒为 `True`，`readline()` 若被调用立即 assertion失败。
- Redirected owner tests：使用真实 `io.StringIO` 或等价严格 typed stream，并显式保证 `isatty() == False`。
- 禁止：mock production `_read_secret_input`、修改/依赖 `sys.__stdin__`、依赖本机或 CI ambient TTY。

### WIN4-RW-PR-F03 — fixed

- Plan位置：§13.2.2，after L775-L777；§13.5.2，after L866-L868。
- 修复：TTY path只捕获 `getpass.getpass()` 的 `EOFError`；redirected path只把 `readline() == ""` 识别为 EOF；
  两路都映射为同一 value-free `CliInitOperationError("secret input ended before completion")`。
- Interrupt边界：`KeyboardInterrupt` 仍不捕获、不改写。

### WIN4-RW-PR-F04 — fixed

- Plan位置：§13.2.2，after L770-L774；§13.5.2，after L864-L865；§13.6.1，after L903-L904；§13.6.3，
  after L928-L929；completion report，after L1056-L1057。
- 修复：只有实际移除了末尾单个 LF，且新末尾是 CR时，才继续移除该单个 CR；孤立 trailing CR原样保留。
- Owner evidence：增加 bare-CR preservation owner test、focused evidence与 coverage要求；禁止 `rstrip` 或等价过度删除。

## Preserved invariants

- Semantic owners未改变：WIN4-RW-S1仍属于真实 Windows smoke success oracle；WIN4-RW-S2仍属于
  `dayu/cli/commands/init.py` secret-input boundary。
- Amendment仍精确为 `2` slices；S1→S2顺序未改变。
- §13.3 allowlist逐项未改变。
- Remote workflow、dispatch identity、same-run evidence/canary closure contract未改变。
- Trusted-local、public/trace/audit non-disclosure、安全边界与 Issue 142/151/175/177/178 等 deferred范围未改变。
- 未实施 production/test/README/workflow/design/control变更，未 stage、commit、push、dispatch或操作 PR。

## Validation and diff checks

- `git diff --check -- docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`：PASS，零输出。
- Plan finding-source scan：F01 public `with`、F02 test-owned TTY/redirected streams、F03 两种 EOF、F04 bare-CR/
  no-`rstrip`均有明确命中。
- Exact-slice/allowlist scan：仍只存在 `WIN4-RW-S1` 与 `WIN4-RW-S2` 两行 allowlist定义。
- Production/test/README/workflow tracked diff与 untracked scan：before为零，完成后亦为零。
- Staged diff：零。
- 本任务是 plan-only finding fix，没有运行 implementation tests、coverage或 pyright；这些 gate仍由 fixed plan §13.6约束后续
  implementation，不得用本 artifact误报为已验证。

## Open questions and residual risk

Open questions：`0`。

没有新增 residual risk。既有真实 Windows capability、外部 transport暂存与 unexpected fresh-run failure风险继续由 fixed plan
§13.8/§13.9 的原 owner/destination跟踪；下一步只能是 Controller validation与 AgentMiMo/AgentDS 对完整 fixed plan的双路
re-review，不能进入 implementation。
