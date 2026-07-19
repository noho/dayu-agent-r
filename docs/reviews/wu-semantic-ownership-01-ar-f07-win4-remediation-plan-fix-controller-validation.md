# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4 remediation plan fix Controller validation

## Content locks

- baseline：`54e2dcbf653fb8c37b0206bd7aabbbf329ef040e`。
- final plan：`docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`，634 lines，SHA-256 `0bd1382288a06cafb77f8bbced45b4b7e08d48c9ab895dfdac1fdad0efddbbe9`。
- AgentCodex fix artifact：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-fix-codex.md`，138 lines，SHA-256 `fabf821f453996d3d2d141d530a5ac7ef28211f51eee513c55de43bc8083579a`。
- Controller plan-review adjudication：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-review-controller-adjudication.md`，SHA-256 `a61568b1c4212286a8f92c80c7794ce5c889be56e3e333f6a1bd0ad87d7c9ba4`。
- staged tree：empty；production、tests、README与workflow零diff；`git diff --check` PASS。

## Independent validation

### WIN4-PR-F01

Plan现在要求在执行`.cmd`前按CRLF physical lines排除`REM Regenerate:`与固定header，仅接受唯一`upload_filing`业务command，并使用现有Windows batch/CRT oracle或等价Windows-semantics parser逐token验证恰好一个`--company-name`及精确值`Apple Inc.`。whole-file count、substring、POSIX loose parser、comment-only与execution-result反推均被禁止。finding关闭。

### WIN4-PR-F02

Plan现在把cleanup bounded wait再次timeout后的唯一动作锁定为一次non-blocking `poll()`；`None`与integer分别投影为`running`/`exited`，deadline、cleanup与post-cleanup facts保持分离。再次wait/kill、process-tree治理与将post-cleanup状态伪装成自然退出均被禁止。finding关闭。

### WIN4-PR-F03

Plan现在精确锁定三个`tempfile.TemporaryFile(mode="w+b")` context handles，lifetime覆盖child execution与bounded cleanup，并在context unwind关闭；`mkstemp`、`NamedTemporaryFile`、`tmp_path`、显式unlink、retained-path warning与新cleanup framework均被禁止。它修复handle/evidence owner，不引入named-file lifecycle。finding关闭。

### WIN4-PR-F04

Controller在首次fix后发现原“configured secret/runtime needles”不可执行：当前R12 test内部随机值没有安全发布，GitHub Secrets不可读取，且workflow没有把production secrets作为test input。最终plan已修正为可验证双owner contract：R12 setx test从公开`GITHUB_RUN_ID`用固定domain-separated SHA-256纯函数派生non-secret API-key-shaped canary；Controller只凭公开R12 run id独立重算并扫描新R12完整log/artifacts（包含其embedded R11）。standalone R11没有消费canary，只按artifact integrity与无secret-input contract验收，不声称canary证明。不得读取/扫描GitHub Secrets或configured production values。finding关闭且没有伪gate。

## Boundary preservation

- Fins company-name fail-closed、storage/Docling与production Fins代码保持零改动。
- setx仍是Windows persistence authority；S2保留DEVNULL、close_fds、30秒direct timeout、names-only result与no retry。
- `TimeoutExpired`仍明确不得绑定、格式化、记录或转抛；其argv/value不得进入result/log/JUnit。
- Config/Host internal SQLite/EventLog trusted-local裁决未改变；Tool Trace/audit/public/LLM-facing/operator log仍不允许API key/header明文。
- 没有secret framework、unified authorization、process-tree framework、Issue 142/151/175/177/178或Web/WeChat/render扩域。
- 三slice次序、allowlist、stop conditions与真实Windows closure matrix保持完整。

## Decision

结论：`PASS / READY_FOR_DUAL_COMPLETE_PLAN_REREVIEW / IMPLEMENTATION_NOT_AUTHORIZED`。

下一gate由AgentMiMo/AgentDS分别从最终plan全文、原两路review、Controller adjudication、fix artifact与本validation出发做完整re-review。必须重点验证F04可执行性修正、F01-F03闭合和所有rejected dispositions未回流。双路通过前不得implementation、stage、commit、push或dispatch workflow。
