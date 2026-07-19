# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4 remediation plan review/re-review finding fix — AgentCodex

## Gate identity and scope

- Umbrella work unit：既有 `WU-SEMANTIC-OWNERSHIP-01`。
- Continuation：`AR-F07` WIN4 remediation；不是新 WU / sub-WU。
- Gate：同一plan gate内的plan review finding fix、Controller执行性校正与plan re-review finding fix；
  implementation仍未授权。
- Baseline：`54e2dcbf653fb8c37b0206bd7aabbbf329ef040e`。
- 修改边界：只修订锁定 plan，并更新既有本 fix artifact。
- Production/tests/README/workflow/control/review原件：零修改。
- Stage/commit/push/workflow dispatch：未执行。

## Locked inputs read before fix

- Controller plan-review adjudication：
  `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-review-controller-adjudication.md`；follow-up后
  已重新完整读取，当前SHA-256
  `a61568b1c4212286a8f92c80c7794ce5c889be56e3e333f6a1bd0ad87d7c9ba4`。
- AgentMiMo complete review：
  `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-review-mimo.md`，锁定
  SHA-256 `e5af0d3d08ca910a1da18e74f0a1f5c17c0ad643f7fa01fc762fc2bb087afaaf`。
- AgentDS complete review：
  `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-review-ds.md`，锁定
  SHA-256 `cb4ef70a0b28c1e168710cf3afabbbb2b3b17b0916ca3c54bfb03561fdd83fce`。
- Pre-fix locked plan：
  `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`，SHA-256
  `a290f4184b42ce841f7002f7fab179b12caa42c70ca41e5ee8c60c03c3ee2cf6`。
- Controller validation 与第四轮 Windows evidence adjudication：已完整读取。
- Controller discussion：
  `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` 已完整读取；相关稳定
  design truth 已核对 `docs/fins/design.md`、`docs/ui/design.md`、`docs/tool/design.md` 全文及
  `docs/host/design.md` 的 trusted-local canonical secret 与 public/trace/audit/log 零明文边界。

两路 review 均认可 WIN4-F01..03 的 root-cause chain、owner 与三 slice 方向，没有 plan-fail finding。
Controller 是 accepted/rejected disposition 的唯一 owner，本 artifact 不重新裁决 review candidates。

### Plan re-review finding-fix locked inputs

- Controller plan re-review adjudication：
  `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-rereview-controller-adjudication.md`，
  38 lines，SHA-256 `50dfcf9e73849fd16a265fff92ffe54a7dbadceb2bda54d0c73dca4243465371`，已完整读取。
- AgentMiMo complete re-review：
  `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-rereview-mimo.md`，343 lines，external
  SHA-256 `9bd74bb26f53ec2b9c91a4a39e2db39408e856b5fe206123a09734b5de23cd41`，已完整读取。
- AgentDS complete re-review：
  `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-rereview-ds.md`，508 lines，external
  SHA-256 `1c57731127d2fa090ed97c9885e62ce2a92fb621b73b17e13cffce3d1ddb80a0`，已完整读取。
- Re-review 前final plan：634 lines，SHA-256
  `0bd1382288a06cafb77f8bbced45b4b7e08d48c9ab895dfdac1fdad0efddbbe9`，已完整读取。
- Re-review 前本fix artifact：138 lines，SHA-256
  `fabf821f453996d3d2d141d530a5ac7ef28211f51eee513c55de43bc8083579a`，已完整读取。
- Plan-fix Controller validation：
  `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-fix-controller-validation.md`，42 lines，
  SHA-256 `f9be890e3abccf117167d911f91ec0df54d816a37026c9eb40916c5b6005ed52`，已完整读取。

## First-principles and semantic-owner judgment

首轮四项与本轮两项 accepted finding 均成立：原 plan 方向正确，但裁决前对应contract仍不够
code-generation-ready。修复必须写在对应 owner boundary，不允许下游补偿。

| Finding | 唯一 owner | Fix boundary |
| --- | --- | --- |
| `WIN4-PR-F01` | R11 Windows real-smoke test input/oracle | pre-execution `.cmd` business-command token oracle |
| `WIN4-PR-F02` | `_run_init()` direct outer-process cleanup projection | cleanup-timeout 后一次 non-blocking poll |
| `WIN4-PR-F03` | `_run_init()` anonymous stdio handle lifetime | 三个 `TemporaryFile(mode="w+b")` context handles |
| `WIN4-PR-F04` | R12真实Windows setx canary producer + R12 closure Controller | R12 public-run-id-derived canary及R12 exact-value scan gate |
| `WIN4-PR-RR-F01` | §2.3 R12 canary双owner公共派生contract | 唯一Python bytes literal、single NUL、完整bytes与known vector owner tests |
| `WIN4-PR-RR-F02` | §9.3 R12 closure Controller procedure | dispatch-returned `run_id`、accepted-commit metadata与same-run evidence lineage |

该修复不改变 Fins company-meta owner、setx persistence authority、Host trusted-local durable secret裁决，
也不新增 named-file lifecycle、process-tree治理、secret infrastructure或 diagnostic framework。

## Accepted finding closure

### WIN4-PR-F01 — CLOSED IN PLAN

Plan §4 S1 与 §5.1 现已锁定：oracle在执行 `.cmd` 前运行并 fail closed；按 CRLF physical line排除
`REM Regenerate:` 和固定 batch header，仅接受唯一非 `REM` 的 `upload_filing` 业务命令；使用现有
Windows batch/CRT oracle或等价 Windows-semantics token parser，证明 `--company-name` 恰好一个且下一 token
精确为 `Apple Inc.`。明确禁止 whole-file count、substring presence、POSIX loose parsing、从执行结果反推输入，
以及 comment-only 证明。

### WIN4-PR-F02 — CLOSED IN PLAN

Plan §2.3、§4 S3 与 §5.3 现已锁定：bounded cleanup wait再次 timeout 后，只调用一次非阻塞 `poll()`；
`None` 投影 `process_state_after_cleanup_timeout=running`，integer投影
`process_state_after_cleanup_timeout=exited` 并进入 `cleanup_returncode`。此后不再次 wait/kill，不递归治理
process tree，也不把 post-cleanup poll冒充 deadline前自然退出。

### WIN4-PR-F03 — CLOSED IN PLAN

Plan §0.1、§2.3、§4 S3 与 §5.3 现已锁定三个
`tempfile.TemporaryFile(mode="w+b")` context handles。handles覆盖 child execution与bounded cleanup完整生命周期，
并在 `finally` / context unwind关闭。不记录 path，不使用 `mkstemp`、`NamedTemporaryFile` 或 pytest `tmp_path`，
不增加 unlink、retained-path warning或新的 cleanup framework。

### WIN4-PR-F04 — CLOSED IN PLAN

Controller validation follow-up 的直接证据成立：当前R12 test在进程内用`secrets.token_urlsafe()`随机生成值，
Controller无法取得原值；GitHub Secrets不可读取，且当前workflow没有把configured production secrets作为test input。
因此先前的configured-secret/runtime-needle scan不可执行，已被更正而非保留为伪gate。

Plan §2.3、§4 S3、§5.4、§6.6、§8、§9.3与§12现已锁定：真实GitHub Actions test只从公开
`GITHUB_RUN_ID`按固定domain-separated SHA-256纯函数派生non-secret、API-key-shaped canary；workflow run id
缺失/非法时在CLI启动前fail closed，本地非workflow可继续随机。test继续断言实际canary不进stdout/stderr/safe
failure。第二次Controller执行性校正先锁定双owner基础：canary producer只有R12真实setx test，
Controller独立重算并扫描R12完整workflow log与全部downloaded artifacts（自然包含embedded R11 evidence），
零命中才通过；不从test artifact取needle，不读取或扫描GitHub Secrets/configured production values。
本轮`WIN4-PR-RR-F02`在下文进一步锁定dispatch-returned `run_id`与same-run lineage，不用本段基础描述替代。

standalone R11未消费该canary，因此不进入scan，也不得用从未输入的派生值声称non-disclosure证明；它继续按原
capability/four-node/argv/real-upload、artifact integrity与无secret-input contract验收。

### WIN4-PR-RR-F01 — CLOSED IN PLAN

Controller接受finding的动机成立：如果test与Controller把旧`\0`分别解释为NUL和backslash + zero，两者会
派生不同canary，错误needle的零命中将形成假pass。这是双owner contract缺口，不能留给implementation猜测。

Plan §2.3已将domain separator唯一冻结为Python bytes literal
`b"dayu-ar-f07-win4-r12-canary-v1\x00"`；该literal求值后是31 bytes，末字节是single NUL `0x00`。
明确禁止包含backslash + zero的`b"dayu-ar-f07-win4-r12-canary-v1\\0"`与包含字面backslash + `x00`的
`b"dayu-ar-f07-win4-r12-canary-v1\\x00"`。Owner tests必须锁定完整bytes、single NUL与canonical run id
`"1"`对应的已知canary vector。Test与Controller只依据plan文字contract分别实现；禁止共享
production/test helper、constant module或artifact needle。

### WIN4-PR-RR-F02 — CLOSED IN PLAN

Controller接受finding的动机成立：在并发或重复dispatch中根据“最近run”反推会取到历史run，并用错误run id
派生needle、扫描错误artifacts，同样可能零命中假pass。正确owner是Controller closure procedure，不是workflow或test
helper。

Plan §5.4、§6.6、§8、§9.3与§12已锁定：Controller必须使用dispatch response返回的确切、唯一
R12 `run_id`；任何evidence下载/扫描前必须验证workflow identity/name `R12 init Windows gate`、path
`.github/workflows/r12-init-windows.yml`、event `workflow_dispatch`、dispatch target branch/ref与
`head_sha == accepted implementation commit SHA`。Workflow status/log、JUnit、source-hash、artifact列表/下载/哈希、
embedded R11与canary scan必须全部属于同一`run_id`和metadata tuple。任一mismatch、ambiguous、missing、
artifact不完整或无法证明same-run lineage都使当前gate fail；只能重新dispatch并锁定新response返回的
`run_id`，禁止从最近成功run、summary、时间戳或artifact名猜测。

## Rejected / already-satisfied disposition preservation

| Candidate | Preserved disposition |
| --- | --- |
| DS `Finding 1.2b` | 原 plan已有pre-execution placement；并入F01精确fail-closed约束，不另扩项 |
| DS `Finding 2.2a` | already satisfied；`TimeoutExpired`继续不绑定、不格式化、不记录、不转抛，不增加repair/redaction分支 |
| DS `Finding 2.2b` | rejected；不增加真实workflow timing instrumentation |
| DS `Finding 3.1a` | rejected；不枚举/实现PIPE、handle-table或其它替代方案 |
| DS `Finding 3.3a` named-path方案 | rejected；只接受cleanup-contract风险，锁定anonymous handle lifetime |
| DS `Finding 4.1a` | rejected/already satisfied；不新增dependency framework |
| DS `Finding 4.4a` | rejected/already satisfied；README继续与S3同slice |
| DS `Finding 5.1a` | rejected/already satisfied；不冻结易漂移测试数量 |
| DS `Finding 5.6a` | rejected/already satisfied；unexpected recurrence继续阻塞closure并进入diagnostic-first amendment |
| MiMo `RISK-2` | rejected；保持用户指定S1→S2→S3串行顺序 |
| DS re-review POSIX parser open question | 不形成finding；plan继续禁止POSIX loose parser，只允许Windows batch/CRT或等价Windows语义parser |
| DS re-review shared-helper suggestion | rejected；test/Controller必须独立实现与重算，无共享helper/constant/artifact needle |

## Exact artifact changes

修订后的 plan 为 673 lines，SHA-256：
`2359f24251838ec5d779ed0a1eb804ebacce3405e102a0cbc50a70f5844fd73a`。

Plan 精确变更范围：

1. §0 更新 gate status，并新增 §0.1 disposition lock。
2. §2.3 锁定 `TemporaryFile` primitive/handle lifetime与cleanup-timeout单次poll投影。
3. §4 S1/S3 写实 pre-execution token oracle与anonymous-handle implementation contract。
4. §5.1/§5.3 增加对应owner-level negative cases。
5. §2.3、§4 S3、§5.4、§6.6、§8、§9.3、§12 冻结R12 public-run-id canary派生、test assertions、
   R12 Controller独立重算/扫描与value-free报告contract；明确R12 artifacts包含embedded R11、standalone R11不在
   scan范围，并禁止读取/扫描GitHub Secrets或configured production值。
6. §0/§0.1将本轮标识为plan re-review finding fix，保持`WIN4-PR-F01..F04`其余闭合、既有rejected
   dispositions与implementation未授权。
7. §2.3、§4 S3与§5.4将domain separator唯一冻结为Python bytes literal/single NUL，增加完整bytes与
   known run-id vector owner-test contract，并禁止test/Controller共享helper或artifact needle。
8. §5.4、§6.6、§8、§9.3与§12将Controller procedure唯一锁定为dispatch-returned `run_id`、workflow
   identity/path/event/branch/accepted `head_sha` 预检与JUnit/source-hash/artifacts/canary scan same-run lineage；
   mismatch/ambiguous/missing全部fail closed。

未改动 S2 的 `TimeoutExpired` 核心约束、三 slice allowlist、production/test implementation、README/workflow、
control doc或任何既有 review artifact。

## Validation

- `git diff --check`：PASS。
- 两个untracked目标artifact独立whitespace check：均零输出。
- staged tree：empty。
- production/tests/README/workflow代码 diff：零。
- Literal/vector自校验：plan文件不含actual NUL byte；冻结Python literal求值后是31 bytes、末字节
  `0x00`；canonical run id `"1"` 的known vector与plan完整值匹配。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：PASS，`0 errors, 0 warnings,
  0 informations`。
- 本 gate未运行pytest、coverage或Ruff：只修改plan/fix Markdown artifact，没有受影响的生产或测试节点；
  不声称implementation validation通过。

## Gate result

`PLAN_REREVIEW_FINDINGS_FIXED / READY_FOR_CONTROLLER_VALIDATION_AND_DUAL_COMPLETE_REREVIEW /
IMPLEMENTATION_NOT_AUTHORIZED`
