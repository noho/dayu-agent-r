# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4 remediation plan final re-review Controller adjudication

## Final locks

- plan：`docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`，673 lines，SHA-256 `2359f24251838ec5d779ed0a1eb804ebacce3405e102a0cbc50a70f5844fd73a`。
- cumulative AgentCodex plan-fix：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-fix-codex.md`，199 lines，SHA-256 `52f5ae11a409b6d3ed5c3b16c30973972b876b8dc4f2d4ff7ff91f3dfb6ccbe4`。
- AgentMiMo final complete re-review：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-final-rereview-mimo.md`，external SHA-256 `d92a19720effdeec628444d9c08b270b1f2dcb3ad0566fd0399b6dabf2d8c2d6`，PASS，material finding 0。
- AgentDS final complete re-review：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-final-rereview-ds.md`，external SHA-256 `9e719b02ee606ae334ae79eb67c492bc2d727c73bf8ab3c5aad4dd889bfe066a`，PASS，material finding 0。
- staged tree在裁决前empty；production/tests/README/workflow零diff；`git diff --check` PASS。

## Final finding ledger

| Finding | Final status | Owner contract |
| --- | --- | --- |
| WIN4-PR-F01 | CLOSED | S1 pre-execution唯一非REM业务command的Windows逐token oracle |
| WIN4-PR-F02 | CLOSED | cleanup timeout后一次non-blocking poll与互斥状态投影 |
| WIN4-PR-F03 | CLOSED | 三个anonymous `TemporaryFile(mode="w+b")` handles的context lifetime |
| WIN4-PR-F04 | CLOSED | R12 test canary producer + Controller独立重算/同run scan |
| WIN4-PR-RR-F01 | CLOSED | 31-byte、末字节NUL `0x00`的唯一bytes literal与known vector |
| WIN4-PR-RR-F02 | CLOSED | dispatch-returned R12 run id、metadata与same-run evidence lineage |

两路final re-review没有新增accepted finding。DS此前POSIX parser与shared-helper suggestions保持rejected：plan已禁止POSIX loose parsing，Controller/test不得共享实现。所有首轮rejected/already-satisfied candidates零回流。

## Scope and safety judgment

- 三slice是当前umbrella WU的内部remediation units，不是新WU。
- S1只修真实Windows test input/oracle；不改Fins production contract。
- S2只在`init_environment` owner删除setx无消费者pipe、增加direct bound并保留names-only/no-retry。
- S3只修test-local process/evidence projection与tests README；不引入named-file、process-tree、JUnit/plugin或global subprocess framework。
- Config/Host internal SQLite/EventLog trusted-local；Tool Trace/audit/public/LLM-facing/operator log plaintext-zero裁决保持。
- 不读取GitHub Secrets，不实施unified authorization、secret infrastructure、Issue 142/151/175/177/178或Web/WeChat/render deferred能力。

## Decision

结论：`PASS / PLAN_ACCEPTED / READY_FOR_EXACT_SCOPE_ACCEPTED_LOCAL_COMMIT`。

Accepted plan commit后按WIN4-S1→WIN4-S2→WIN4-S3顺序逐slice执行implementation、双路code review、accepted finding fix、双路re-review与accepted commit。在计划提交完成前仍不得修改代码或dispatch workflow。
