# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4 Real-Windows Plan Amendment Review — AgentCodex

## Review metadata

- Timestamp（本机时钟）：`2026-07-20 05:28:40 +0800`。
- Reviewer：AgentCodex。
- Work identity：既有 `WU-SEMANTIC-OWNERSHIP-01` umbrella remediation continuation / `AR-F07 WIN4`；不是新 WU。
- Reviewed target：`docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md` 的 real-Windows diagnostic
  bounded amendment。
- Plan hash before amendment：`2359f24251838ec5d779ed0a1eb804ebacce3405e102a0cbc50a70f5844fd73a`。
- Plan hash after amendment：`79e984d6fe5fe1ce08cd1affc60b241f9691c6ba94b9ec3e75850676b9d61bb4`。
- Frozen remote code/evidence target：`b85def887e72dc69e972f42a82a18989523f8634`。
- Locked evidence runs：R11 `29703932798`；R12 `29703933666`。
- Conclusion：`pass / CODE_GENERATION_READY / IMPLEMENTATION_NOT_AUTHORIZED`。

本 review artifact 不实施 production/test/workflow 变更，不更新 control/design/README，不 stage、commit、push、dispatch 或
操作 PR。

## Reviewed inputs and evidence scope

已完整读取：

- `AGENTS.md`；
- `docs/phaseflow-umbrella-optimization-control.md`；
- amendment 前完整 WIN4 remediation plan；
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-failure-controller-adjudication.md`，其锁定
  SHA-256 为 `254022d11c6e52324622ba9b52050a3ae6832d84333eece145572c0c1ec6d4cf`。

已核对冻结 target 的相关直接代码/测试/workflow/evidence：

- `dayu/cli/output.py` 的 current terminal summary owner；
- `tests/cli/test_upload_filings_from_command.py` 的 real Windows execution、company-name oracle、旧 display断言与
  artifact oracle写入顺序；
- `dayu/cli/commands/init.py` 的 required/optional secret收集、普通 input/confirmation与 error mapping；
- `tests/cli/test_init_command.py` 的现有 getpass/input fakes与 transaction/non-disclosure tests；
- `tests/cli/test_init_smoke.py` 的 anonymous redirected stdin、bounded outer process、real Windows setx node；
- CPython 3.11 `getpass.py` 的 `win_getpass()`/`fallback_getpass()`/`_raw_input()`分支；
- `.github/workflows/r11-upload-script-windows.yml` 与 `.github/workflows/r12-init-windows.yml` 的 node、artifact与
  always-upload contract；
- standalone R11 JUnit/stdout 的 `3 passed, 1 failed`、exit `0` 后旧 display assertion，以及 published storage artifact
  inventory。

R12 run-specific canary未读取、派生或回显；R12的 value-free scan结论、timeout位置与安全 failure truth仅使用 Controller
已裁决 artifact。未读取 GitHub Secrets 或 configured production values。

## Goal, non-goals and success signal

Goal 是在既有 plan 中增加最多两个、按真实 semantic owner切分且可直接交给 implementation agent 的 slices：

1. `WIN4-RW-S1` 删除 test consumer 对 display literal 的成功耦合，以 process exit和 public Fins storage owner facts
   证明 upload success，同时保留 company-name oracle与 artifact integrity。
2. `WIN4-RW-S2` 在 CLI secret-input owner按 stdin capability区分 TTY hidden getpass与 redirected line-oriented input，
   由 owner tests锁定 EOF/interrupt/order/non-disclosure。

Non-goals 保持：不修 output renderer、setx/harness/workflow、Fins production/schema、Config/Host durable domain、Issue
142/151/175/177/178、统一 authorization/secret infra或 Gemini quota。

本地 success signal 是 owner tests、CLI regression、coverage、pyright、Ruff、diff/allowlist、README/source scans全部满足；
最终 closure signal仍是 accepted implementation commit上的 fresh R11/R12 dispatch、同 run artifact integrity和 R12
Controller-owned value-free canary gate，不能由本地 Windows skip或历史 run替代。

## Assumptions tested

| Assumption | Adversarial test | Direct evidence and disposition |
| --- | --- | --- |
| R11是 upload failure | 检查 assertion前的 process结果与 published tree | execution先 exit `0`；stdout含 typed `status="ok"`；storage已发布完整 company/source artifacts。假设被证伪，根因锁定 stale display consumer。 |
| 可把旧词换成 current prefix | 比较业务事实 owner与 renderer owner | display由 `dayu/cli/output.py`拥有且可演进；test应消费 process/storage facts。替换为另一硬编码词被拒绝。 |
| raw filesystem存在即可证明业务成功 | 用 semantic-ownership约束挑战 `rglob` | raw count只能证明 artifact物理完整性；业务成功改由 `dayu.fins.storage` public repositories读取 published company/source snapshot。 |
| R12是 setx再次 hang | 检查 input→confirmation→staging→setx顺序 | hang在首个 required secret；setx尚无执行机会。假设被证伪，禁止重开 WIN4-S2。 |
| redirected OS handle会使 Windows getpass消费 stdin | 检查 CPython 3.11 `win_getpass()`对象身份条件 | `sys.stdin is sys.__stdin__`仍成立时走 `msvcrt.getwch()`，stream被忽略。root cause成立。 |
| 修复需要 Windows特判 | 对比真实 owner与输入 capability | TTY/redirected是直接语义；OS/test identity是间接代理。采用 `sys.stdin.isatty()`，拒绝 platform/GitHub Actions分支。 |
| test harness shim更便宜 | 检查 owner与真实 CLI behavior | shim只修单一测试入口并保留生产缺陷；被禁止。production helper保持 owner-local且无通用 infra。 |
| 两 finding可合并成一个 slice | 比较 owner、路径、blast radius与验证 | S1是 test success oracle，S2是 production CLI input contract；必须独立 review/rollback，精确拆成两个 slices。 |

## Required review lenses

### Architecture boundary review

`WIN4-RW-S1` 只修改 test consumer，但业务事实从 public `dayu.fins.storage` repository读取；不把 storage语义复制到 CLI
renderer、raw JSON或 workflow。`WIN4-RW-S2` 只在 UI/CLI input owner内增加模块级私有 helper；不下沉到
`dayu.runtime`，不侵入 environment persistence、Config、Host或 Fins。依赖方向和 `UI -> Service -> Host -> Engine`边界
没有变化。

### Best-practice review

方案使用 capability detection、单一 logical-line read、明确 EOF与 interrupt semantics、owner-level negative tests、动态
non-disclosure断言和 fresh remote acceptance。它避免用 timeout、display text、mock或 warning suppression获得假绿；README
决策与实际用户输入行为同步。

### Optimal-solution review

可信替代方案包括修改 renderer、给 test换 prefix、修改 harness、Windows-only input shim、PowerShell/PTY/console wrapper。
前四项修错 owner或制造重复语义，最后一项显著扩大 blast radius。plan采用两个最小 owner-local变更，是当前证据下更简单、
可测试且可演进的路径。

### Overengineering review

未增加 class/Protocol/factory/callback、跨模块 secret helper、credential broker、redaction framework、process framework、schema
或 migration。redirected input只增加一个模块级私有 helper；storage success只复用现有 public repositories。

### Overcoupling review

两个 slices串行但没有代码依赖；只有最终 remote rerun依赖二者同时 accepted。S1不需要修改 Fins/output/workflow，S2不需要修改
harness/setx。README与 S2保持同一提交/回滚边界，没有建立额外 docs transaction。

## Findings

没有未修复 material finding。amendment已收敛以下最强反例：

- display词再次漂移不会让真实 upload假失败；
- stdout出现成功词但 exit/storage失败不会假通过；
- redirected stdin不再落入 Windows console getpass；
- TTY不会因自动化修复而失去 hidden input；
- EOF、interrupt、required/optional/confirmation顺序和 secret non-disclosure均有 owner-level negative tests；
- remote closure不能复用历史 run或跨 run混合 artifact/canary evidence。

## Open questions

`0`。implementation agent不需要重新决定 owner、API形态、line-ending、EOF/interrupt、slice路径、README或 remote closure。

## Residual risks and tracking destination

1. 非 Windows本地无法替代真实 CPython 3.11 Windows console/redirected handle行为；由 fresh R12 closure gate追踪。
2. caller pipe、OS handle与 CLI process memory必然暂存输入值；本 WU只承诺 CLI不主动回显/投影。更广 transport threat model
   属于独立安全设计，禁止在本 amendment顺手实现。
3. fresh remote若在已修 owner之后出现新 failure，必须回到 diagnostic-first plan amendment；不得用当前两个 root cause解释。
4. Controller继续独立拥有 same-run canary scan；implementation/test不得取得 run-specific needle或共享派生实现。

## Final plan review conclusion

`pass / CODE_GENERATION_READY / IMPLEMENTATION_NOT_AUTHORIZED`

amendment的 motivation、root cause、semantic owners、两个 slices、允许/禁止路径、顺序、negative tests、coverage/pyright/Ruff/
diff/README/source scans、fresh remote rerun、same-run canary gate与 deferred/security boundary均已明确。下一步只能进入
Controller validation及 AgentMiMo/AgentDS 双路完整 plan review；在 accepted amended-plan commit前不得 implementation。
