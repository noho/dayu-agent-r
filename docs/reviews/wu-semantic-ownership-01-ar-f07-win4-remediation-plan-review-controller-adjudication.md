# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4 remediation plan review Controller adjudication

## Review locks

- baseline：`54e2dcbf653fb8c37b0206bd7aabbbf329ef040e`。
- reviewed plan：`docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`，SHA-256 `a290f4184b42ce841f7002f7fab179b12caa42c70ca41e5ee8c60c03c3ee2cf6`。
- AgentMiMo：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-review-mimo.md`，SHA-256 `e5af0d3d08ca910a1da18e74f0a1f5c17c0ad643f7fa01fc762fc2bb087afaaf`，结论 `PASS_WITH_RISKS`。
- AgentDS：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-review-ds.md`，SHA-256 `cb4ef70a0b28c1e168710cf3afabbbb2b3b17b0916ca3c54bfb03561fdd83fce`，结论 `PASS-WITH-RISKS`。
- 两路均确认 WIN4-F01/F02/F03 的 root-cause chain、唯一 owner、三 slice 方向、forbidden paths 与用户裁决成立；没有 plan-fail finding。

## Accepted plan findings

### WIN4-PR-F01 — S1 pre-execution oracle 必须解析真正业务命令

接受 MiMo `RISK-1` 与 DS `Finding 1.2a` 的同一事实。当前 plan 已要求在执行 `.cmd` 前做结构化 oracle，但实现策略仍可能被误写成 whole-file substring count。AgentCodex 必须补充：

- oracle 在执行 `.cmd` 前运行并 fail closed；
- 按 CRLF 行识别并排除 `REM Regenerate:` 注释和固定 batch header，只解析唯一的 `upload_filing` 业务命令；
- 使用现有 Windows batch/CRT argv oracle 或等价的逐 token 解析，证明 `--company-name` 恰好一个且下一 token 精确为 `Apple Inc.`；
- 禁止 whole-file `count`、substring presence、从执行结果反推输入，或只证明 regeneration comment 含该参数。

DS `Finding 1.2b` 所要求的 pre-execution placement 已被原 plan §4 S1 step 2 明确覆盖，不另立第二项 finding；上述补强只把其 fail-closed 顺序锁定得更具体。

### WIN4-PR-F02 — S3 cleanup-timeout 后必须投影非阻塞进程状态

接受 DS `Finding 3.2a`。原 plan 已区分 deadline returncode、kill 后 cleanup state 与 cleanup returncode，但 cleanup bounded wait 再次 timeout 时没有说明 direct outer process 的当时状态。AgentCodex 必须补充：cleanup timeout 后只调用一次非阻塞 `poll()`，把结果投影为 names/value-free 的 `process_state_after_cleanup_timeout=<running|exited>` 与可用的 integer returncode；不得再次等待、再次 kill、递归治理 process tree或把该事实伪装成自然退出。

### WIN4-PR-F03 — S3 必须锁定 anonymous-file primitive 与 lifetime

接受 DS `Finding 3.3a` 所指出的“计划必须明确临时载体清理契约”，但拒绝其 `mkstemp` / named path / retained-path warning 方案。该方案会把本轮 test-local projection 修复扩张为路径、unlink 与残留治理，并建立 reviewer 假设的 named-file语义。

AgentCodex 必须把计划锁定为 `tempfile.TemporaryFile(mode="w+b")` context managers：不使用 `mkstemp`、`NamedTemporaryFile` 或 pytest `tmp_path` 承载 sentinel；三个 handle 在 child execution与bounded cleanup期间保持有效，并在 helper 退出的 `finally` / context unwind 中关闭；不记录 path，不增加显式 unlink、retained-path或新的 cleanup framework。这样 owner contract 是 handle lifetime，而不是新的 durable test artifact。

### WIN4-PR-F04 — 真实 R11/R12 closure 必须有可执行 canary scan gate

接受 DS `Finding 5.5a` 中“真实 artifact 必须有可执行 non-disclosure gate”的有效部分。Controller不能读取GitHub Secrets，也不能取得当前测试内部用 `secrets.token_urlsafe()` 随机生成且未安全发布的原值；把这些值写成Controller scan needle会形成不可执行伪gate。

AgentCodex 必须补充一个 test-owned、run-specific、非秘密 canary：R12真实Windows setx test只从公开 `GITHUB_RUN_ID` 经过固定domain-separated纯函数派生API-key-shaped canary，本地非workflow路径可继续使用随机值。测试本身继续断言canary不在stdout/stderr与safe failure text；Controller从公开R12 run id独立重算同一canary，对新R12 workflow log和全部downloaded artifacts（含其embedded R11 artifacts）做exact-value扫描，零命中才通过。独立R11 workflow没有消费该canary，不能把对其扫描一个从未输入的值写成有效安全证明。扫描命令、review artifact和控制文档不得回显canary；若命中，只记录run、artifact locator、match category与状态，不复制matched content。

本 finding 不要求、也不允许读取或扫描GitHub Secrets/configured production值；这些workflow不把它们作为当前test input。它也不改变用户裁决：Config/Host internal SQLite/EventLog属于trusted-local domain，只有Tool Trace/audit不得泄漏API key明文；本 gate只验证当前test harness不会把自己的canary复制到JUnit/workflow evidence。

## Rejected or already-satisfied candidates

- DS `Finding 2.2a`：风险真实，但已由 plan §2.2 的“不绑定、格式化、记录或转抛 raw TimeoutExpired”以及 S2 exact change/negative case完整覆盖；不是未覆盖 plan finding。实施与review仍必须逐条验证。
- DS `Finding 2.2b`：30秒是 bounded owner budget，不是财务业务事实；为证明常量而在真实 workflow加入 timing instrumentation没有当前消费者，拒绝。
- DS `Finding 3.1a`：plan已有 direct pipe/descendant EOF evidence和方案理由；无需枚举、逐一排除所有替代方案。
- DS `Finding 4.1a`：plan已明确 `Dependencies: S2` 且“S2必须在S3前完成”，硬依赖语义无歧义。
- DS `Finding 4.4a`：README与S3同一 accepted slice提交/回滚，现有gate自然保持一致，无新问题。
- DS `Finding 5.1a`：plan已明确更新严格 `_SetxRecorder` 签名/记录字段并覆盖全部现有行为矩阵；具体受影响测试数量属于实施扫描，不需要在plan冻结易漂移计数。
- DS `Finding 5.6a`：plan §9.1与§10已明确 unexpected recurrence 为 `NEEDS_MORE_EVIDENCE / DIAGNOSTIC_FIRST PLAN AMENDMENT REQUIRED`；它会阻塞AR-F07 closure但不被误判成当前root cause，状态树已经完整。
- MiMo `RISK-2`：串行 S1→S2→S3 是用户指定且利于独立证据归属的执行次序，不修改。

## Decision and next gate

结论：`FIX_REQUIRED / IMPLEMENTATION_NOT_AUTHORIZED`。

AgentCodex 只修改 plan 与 plan-fix artifact，关闭 WIN4-PR-F01..F04；不得修改 production、tests、README、workflow，不得 stage、commit、push或dispatch workflow。Controller验证后必须由AgentMiMo/AgentDS并发完整re-review；双路re-review和Controller裁决通过后才能进入accepted plan commit。
