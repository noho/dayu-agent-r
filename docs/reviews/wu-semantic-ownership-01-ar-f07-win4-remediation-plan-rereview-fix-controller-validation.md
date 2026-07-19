# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4 remediation plan re-review fix Controller validation

## Locks

- final plan：673 lines，SHA-256 `2359f24251838ec5d779ed0a1eb804ebacce3405e102a0cbc50a70f5844fd73a`。
- cumulative AgentCodex plan-fix artifact：199 lines，SHA-256 `52f5ae11a409b6d3ed5c3b16c30973972b876b8dc4f2d4ff7ff91f3dfb6ccbe4`。
- Controller re-review adjudication：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-rereview-controller-adjudication.md`。
- staged tree empty；production/tests/README/workflow零diff；`git diff --check` PASS；AgentCodex full pyright为0 diagnostics。

## Accepted finding validation

### WIN4-PR-RR-F01

Plan现在只允许Python bytes literal `b"dayu-ar-f07-win4-r12-canary-v1\x00"`，明确求值长度31、末字节single NUL `0x00`，并显式禁止backslash+zero和字面backslash+`x00`。Owner tests必须锁完整bytes和canonical run id `"1"`的known vector `sk-dayu-test-b8f2210d1ead3aac3a52408adb9de03c4e848d4c101f790e218ecc76e3350b97`。Controller与test依据文字contract独立实现，不共享helper/constant/artifact needle。双owner字节歧义关闭。

### WIN4-PR-RR-F02

Plan §9.3现在冻结Controller procedure：使用本次dispatch response返回的唯一R12 `run_id`；下载前验证workflow name/path、event、target branch/ref、accepted implementation `head_sha`；status/log/JUnit/source-hash/artifact inventory/download/hash/embedded R11/canary scan必须全部来自同一run与metadata tuple。Missing、mismatch、ambiguous、下载不完整或跨run混用均fail，禁止从最近run、summary、时间戳或artifact名反推。错误run造成假零命中的路径关闭。

## Preservation audit

- WIN4-PR-F01..F04其余闭合未变化。
- S1仍禁止POSIX loose parser；只允许现有Windows batch/CRT或等价Windows语义parser。
- 没有共享canary helper、workflow修改、GitHub Secret读取、configured production secret扫描、named-file或process-tree框架。
- Standalone R11仍不声称R12 canary证明；R12 scan只覆盖其同run完整evidence与embedded R11。
- Config/Host trusted-local与Tool Trace/audit plaintext-zero裁决未改变。

## Decision

结论：`PASS / READY_FOR_FINAL_DUAL_COMPLETE_PLAN_REREVIEW / IMPLEMENTATION_NOT_AUTHORIZED`。

下一gate由AgentMiMo/AgentDS完整re-review最终plan及所有plan finding链；通过后Controller才能接受plan commit。
