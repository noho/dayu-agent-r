# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4 Remediation Plan — AgentMiMo 最终完整 Re-Review

## Gate identity

- Work unit：既有 `WU-SEMANTIC-OWNERSHIP-01` umbrella。
- Continuation：`AR-F07` 第四轮真实 Windows evidence remediation。
- Gate：plan-fix 后最终完整 re-review（第二轮 re-review）。
- Baseline HEAD：`54e2dcbf653fb8c37b0206bd7aabbbf329ef040e`。
- 本 artifact 不是 implementation、不是 control transition、不 stage/commit/push/dispatch。

## 固定输入完整性确认

| 输入 | Expected SHA-256 | Actual SHA-256 | 状态 |
| --- | --- | --- | --- |
| Final plan（plan-fix 后） | `2359f24251838ec5d779ed0a1eb804ebacce3405e102a0cbc50a70f5844fd73a` | `2359f24251838ec5d779ed0a1eb804ebacce3405e102a0cbc50a70f5844fd73a` | ✓ 673 lines |
| Cumulative plan-fix Codex | `52f5ae11a409b6d3ed5c3b16c30973972b876b8dc4f2d4ff7ff91f3dfb6ccbe4` | `52f5ae11a409b6d3ed5c3b16c30973972b876b8dc4f2d4ff7ff91f3dfb6ccbe4` | ✓ 199 lines |
| Rereview Controller adjudication | `50dfcf9e73849fd16a265fff92ffe54a7dbadceb2bda54d0c73dca4243465371` | `50dfcf9e73849fd16a265fff92ffe54a7dbadceb2bda54d0c73dca4243465371` | ✓ |
| Rereview fix Controller validation | `c550314a5d39302f779400503e8708b128db1562a192a393770c460d6e51a4d6` | `c550314a5d39302f779400503e8708b128db1562a192a393770c460d6e51a4d6` | ✓ |
| 首轮 MiMo review | `e5af0d3d08ca910a1da18e74f0a1f5c17c0ad643f7fa01fc762fc2bb087afaaf` | — | ✓ 已读取 |
| 首轮 DS review | `cb4ef70a0b28c1e168710cf3afabbbb2b3b17b0916ca3c54bfb03561fdd83fce` | — | ✓ 已读取 |
| 首轮 Controller adjudication | `a61568b1c4212286a8f92c80c7794ce5c889be56e3e333f6a1bd0ad87d7c9ba4` | — | ✓ 已读取 |
| Plan-fix Controller validation | `f9be890e3abccf117167d911f91ec0df54d816a37026c9eb40916c5b6005ed52` | — | ✓ 已读取 |
| Rereview MiMo | `9bd74bb26f53ec2b9c91a4a39e2db39408e856b5fe206123a09734b5de23cd41` | — | ✓ 已读取 |
| Rereview DS | `1c57731127d2fa090ed97c9885e62ce2a92fb621b73b17e13cffce3d1ddb80a0` | — | ✓ 已读取 |
| Fourth evidence adjudication | 已完整读取 | — | ✓ |

### 代码事实验证

| 文件 | 读取状态 |
| --- | --- |
| `dayu/cli/init_environment.py` | ✓ L402-443：`_persist_windows_environment` 使用 `capture_output=True, text=False`，无 timeout、无 DEVNULL |
| `tests/cli/test_init_smoke.py` | ✓ L162-199：`_run_init` 使用 `subprocess.run(input=input_text, capture_output=True, text=True, timeout=180)` |
| `tests/cli/test_upload_filings_from_command.py` | ✓ L832-904：Windows test 生成 argv 不含 `--company-name`；L960-986：`_decode_windows_batch_fixed_token` 已存在 |
| `tests/cli/test_init_environment.py` | ✓ 1246 lines 已读取 |

---

## 一、WIN4-PR-F01..F04 闭合逐项验证

### WIN4-PR-F01 — S1 pre-execution oracle 必须解析真正业务命令

**最终 plan 锁定**：§4 S1 step 2 + §5.1。

Plan 精确锁定：
- 按 CRLF physical line 排除 `REM Regenerate:` 和固定 batch header
- 只接受唯一非 `REM` 的 `upload_filing` 业务命令
- 使用现有 Windows batch/CRT argv oracle 或等价 Windows 语义逐 token 解析
- 断言 `--company-name` 恰好一个且下一 token 精确等于 `Apple Inc.`
- 禁止 whole-file `count`、substring presence、POSIX loose parser、从执行结果反推输入、comment-only 证明

**代码事实对照**：
- 当前 Windows test L844-860 生成 argv 不含 `--company-name`，POSIX test L738-739 有 → 修复方向正确
- `_decode_windows_batch_fixed_token()` L960-986 已实现 Windows batch percent doubling 与 caret 解码 → S1 oracle 可直接复用
- §5.1 negative case："comment 含 company name、唯一业务命令不含" → fail closed

**结论：CLOSED。** Oracle 实现策略精确到 code-generation-ready 级别。

---

### WIN4-PR-F02 — S3 cleanup-timeout 后必须投影非阻塞进程状态

**最终 plan 锁定**：§2.3 step 5 + §5.3。

Plan 精确锁定四种终止状态：
1. deadline 前自然退出 → `returncode_at_timeout=<int>`
2. deadline 时未退出 → kill → bounded wait 成功 → `cleanup_returncode=<int>`
3. cleanup timeout + poll()=None → `process_state_after_cleanup_timeout=running`, `cleanup_returncode=not_available`
4. cleanup timeout + poll()=int → `process_state_after_cleanup_timeout=exited`, `cleanup_returncode=<int>`

- 此后不得再次 wait/kill
- 不得递归治理 process tree
- 不得把 post-cleanup poll 冒充 deadline 前自然退出

**结论：CLOSED。** 状态机边界无混淆空间。

---

### WIN4-PR-F03 — S3 必须锁定 anonymous-file primitive 与 lifetime

**最终 plan 锁定**：§0.1 + §2.3 steps 1-8 + §4 S3 step 1 + §5.3。

Plan 精确锁定：
- 三个 `tempfile.TemporaryFile(mode="w+b")` context handles
- 覆盖 child execution 与 bounded cleanup 完整生命周期
- `finally` / context unwind 关闭
- 禁止 `mkstemp`、`NamedTemporaryFile`、pytest `tmp_path`、显式 unlink、retained-path warning、新 cleanup framework
- 安全 contract 是 anonymous handle lifetime 与 evidence 零泄漏

**代码事实对照**：
- 当前 `_run_init()` L179-199 使用 `subprocess.run(input=input_text, capture_output=True, ...)` → Plan 要求改为 `Popen[bytes]` + 三个 TemporaryFile handles + `wait(timeout=180)` → 方向正确
- `TemporaryFile` 在 POSIX 上创建匿名文件（`O_TMPFILE` 或立即 unlink），Windows 上使用 `O_TEMPORARY` → handle 关闭即删除

**结论：CLOSED。** Handle lifetime contract 精确，拒绝 named-path 方案正确。

---

### WIN4-PR-F04 — 真实 R11/R12 closure 必须有可执行 canary scan gate

**最终 plan 锁定**：§2.3 canary contract + §4 S3 step 3 + §5.4 + §6.6 + §8 + §9.3 + §12。

Canary 派生 contract：
- 输入：公开 `GITHUB_RUN_ID` → 正十进制整数 → `str(int(GITHUB_RUN_ID))`
- Domain separator：Python bytes literal `b"dayu-ar-f07-win4-r12-canary-v1\x00"`（31 bytes，末字节 single NUL `0x00`）
- 派生：`sha256(domain_separator + canonical_run_id.encode("ascii")).hexdigest()`
- 最终 canary：`sk-dayu-test-<64 lowercase hex digest>`
- 已知向量：run id `"1"` → `sk-dayu-test-b8f2210d1ead3aac3a52408adb9de03c4e848d4c101f790e218ecc76e3350b97`

**Python 独立验证**：
```
domain_separator = b"dayu-ar-f07-win4-r12-canary-v1\x00"
len(domain_separator) == 31 ✓
domain_separator[-1] == 0x00 ✓
sha256(domain_separator + b"1").hexdigest() == "b8f2210d1ead3aac3a52408adb9de03c4e848d4c101f790e218ecc76e3350b97" ✓
canary == "sk-dayu-test-b8f2210d1ead3aac3a52408adb9de03c4e848d4c101f790e218ecc76e3350b97" ✓
```

Controller scan contract（§9.3）：dispatch-returned `run_id` → metadata 验证 → 独立重算 canary → 同 run 递归 exact-value scan → 零命中。

**结论：CLOSED。** 双 owner contract 可执行，纯函数确定性已验证。

---

## 二、WIN4-PR-RR-F01..F02 闭合逐项验证

### WIN4-PR-RR-F01 — domain separator 必须冻结为无歧义 bytes literal

**原始 finding**：Plan 的 "ASCII bytes `dayu-ar-f07-win4-r12-canary-v1\0`" 允许 test 用 NUL byte 而 Controller 用 backslash+zero 两个字符，两者产生不同 canary，零命中形成假 pass。

**最终 plan 锁定**：§2.3 step 2。

Plan 现已精确锁定：
> Domain separator 的唯一真值是 Python bytes literal `b"dayu-ar-f07-win4-r12-canary-v1\x00"`。该 literal 求值后是完整 31 bytes，末字节是单一 NUL `0x00`；不得实现为包含 backslash + zero 的 `b"dayu-ar-f07-win4-r12-canary-v1\\0"`，也不得实现为包含字面 backslash + `x00` 的 `b"dayu-ar-f07-win4-r12-canary-v1\\x00"`。

§5.4 owner test contract：
> Owner tests 必须锁定第 2 项的完整 domain-separator bytes、末字节 single NUL `0x00` 和已知 run-id→canary 向量；任一 byte、canonicalization、prefix 或 digest 算法漂移都必须失败。

§2.3 step 6：
> Test owner 与 Controller owner 必须分别仅依据本节冻结的 bytes/formula/vector 实现与独立重算；禁止共享 production helper、test helper、生成的 needle artifact 或其它共享实现真源。

**验证**：
- Python bytes literal `b"dayu-ar-f07-win4-r12-canary-v1\x00"` 无歧义 → 任何 Python 实现者都会得到 31 bytes + NUL 末字节
- 已知向量 `run_id="1"` → `sk-dayu-test-b8f2210d1ead3aac3a52408adb9de03c4e848d4c101f790e218ecc76e3350b97` 已独立验证匹配
- 禁止 `\\0` 和 `\\x00` 两种误实现已显式写出

**结论：CLOSED。** 字节歧义已消除，Python literal 是唯一真源。

---

### WIN4-PR-RR-F02 — R12 scan 必须锁定 dispatch 返回的 run 与 accepted commit

**原始 finding**：仅写"新 R12 run"不足以防止并发/重复 dispatch 时误取旧 run；用旧 run id 派生并扫描旧 artifacts 会虚假零命中。

**最终 plan 锁定**：§5.4 + §6.6 + §8 + §9.3 + §12。

§9.3 Controller procedure 精确锁定：
1. **run_id 来源**：必须使用 dispatch response 返回的确切、唯一 R12 `run_id`；response 未返回、多个 candidate 或无法唯一对应时 gate fail；禁止从"最近 run"/"最近成功 run"/workflow summary/时间戳/artifact 名反推
2. **metadata 预检**：下载前验证 workflow identity/name `R12 init Windows gate`、path `.github/workflows/r12-init-windows.yml`、event `workflow_dispatch`、branch/ref 等于 dispatch target、`head_sha` 等于 accepted implementation commit SHA；任一 missing/mismatch/ambiguous → gate fail
3. **same-run lineage**：status/log/JUnit/source-hash/artifact 列表/全部下载/哈希/embedded R11/canary scan 全部使用同一 `run_id` 和 metadata tuple；missing/不完整/跨 run 混用 → gate fail
4. **独立重算**：metadata 通过后才能重算 canary；禁止共享 helper/从 test artifact 取 needle
5. **value-free 报告**：命中只记录 run_id、head_sha、artifact-relative locator、`match_category=test_canary`、status；不复制 canary/matched content

**§12 completion report contract** 也要求 implementation artifact 报告 dispatch-returned `run_id`、workflow identity/path/event/branch/ref/`head_sha`、same-run 范围、零命中结论。

**结论：CLOSED。** 错误 run 造成假零命中的路径已关闭。Controller procedure 从 dispatch response 到 same-run scan 的完整链已冻结。

---

## 三、重点挑战验证

### 3.1 bytes literal / single NUL / known vector

**挑战**：plan 的 domain separator 文字是否可能被误解？

**验证**：
- §2.3 使用 Python bytes literal `b"dayu-ar-f07-win4-r12-canary-v1\x00"` — 这是 Python 源码级精确表示，不存在解释空间
- 显式禁止两种常见误实现（`\\0` 和 `\\x00`）
- 已知向量 `run_id="1"` → `sk-dayu-test-b8f2210d1ead3aac3a52408adb9de03c4e848d4c101f790e218ecc76e3350b97` 已用 Python 独立验证
- Owner test 必须锁定完整 bytes + single NUL + known vector → 任何漂移都会导致 test 失败

**结论：PASS。** 无歧义。

### 3.2 test 与 Controller 独立实现

**挑战**：test 和 Controller 是否可能共享实现导致假验证？

**验证**：
- §2.3 step 6："Test owner 与 Controller owner 必须分别仅依据本节冻结的 bytes/formula/vector 实现与独立重算；禁止共享 production helper、test helper、生成的 needle artifact 或其它共享实现真源。"
- §9.3 step 4："禁止与 production/test 共享 helper、constant module 或生成实现；禁止从 test output/artifact 取得 needle。"
- Rereview Controller adjudication 拒绝了 DS 关于共享 helper 的建议："它会破坏'Controller 独立重算'并引入新依赖"

**结论：PASS。** 双方必须独立实现，无共享真源。

### 3.3 dispatch-returned R12 run_id

**挑战**：Controller 如何确保使用正确的 run_id？

**验证**：
- §9.3 step 1："必须使用能在本次 dispatch response 中返回确切 R12 `run_id` 的调用方式，并立即锁定该 `run_id`"
- "response 未返回、返回多个 candidate 或无法唯一对应本次 dispatch 时，当前 gate fail"
- "禁止从'最近一次 run'、'最近一次成功 run'、workflow summary、时间戳或 artifact 名反推 `run_id`"
- §12 要求 implementation completion report 记录 dispatch-returned `run_id`

**结论：PASS。** run_id 来源锁定为 dispatch response，排除所有猜测路径。

### 3.4 workflow path / event / branch / head_sha

**挑战**：metadata 验证是否完整？

**验证**：§9.3 step 2 要求同时断言：
- workflow identity/name 精确为 `R12 init Windows gate`
- workflow path 精确为 `.github/workflows/r12-init-windows.yml`
- event 精确为 `workflow_dispatch`
- branch/ref 精确等于 dispatch target branch/ref
- `head_sha` 精确等于 accepted implementation commit SHA

任一 field missing/mismatch/ambiguous → gate fail。

**结论：PASS。** 五项 metadata 全部锁定，无遗漏。

### 3.5 same-run artifacts lineage

**挑战**：是否可能混用不同 run 的 artifacts？

**验证**：
- §9.3 step 3："Workflow status/conclusion、完整 log、JUnit、source-hash、artifact 列表、全部 artifact 下载与哈希、embedded R11 evidence 以及 canary scan 必须全部使用第 1 项同一 `run_id` 和第 2 项同一 metadata tuple。"
- "任一 required JUnit/source-hash/artifact missing、下载不完整、无法证明 run lineage 或与其它 run 混用都是 gate fail"
- "不得用 workflow summary 或其它 run 的 green status 补齐"

**结论：PASS。** 同-run lineage 强制要求排除跨 run 混用。

---

## 四、边界未漂移验证

### 4.1 standalone R11

**验证**：
- §5.4："standalone R11 没有消费该 canary，不进入本 scan，也不得声称由本 scan 证明其 non-disclosure。"
- §8："standalone R11 的 closure evidence 只来自其 capability/four-node/argv/real-upload 结果、artifact integrity 与无 secret-input contract"
- §9.3："standalone R11 没有消费 R12 canary，继续按 artifact integrity 与无 secret-input contract 验收，不进入 scan"

**结论：PASS。** 边界清晰，standalone R11 不从 R12 canary scan 获得伪造证明。

### 4.2 GitHub Secrets

**验证**：
- §2.3 step 5："不读取 GitHub Secrets 或 configured production values，也不把它们加入 scan 范围"
- §5.4："Controller 不得从 test output/artifact 取得 needle，也不得读取或扫描 GitHub Secrets/configured production values"
- §6.6："Controller 不得读取、请求、导出或扫描 GitHub Secrets/configured production values"
- §9.3："当前 R12 workflow 没有把这些值作为本 test input，因此它们不是本 canary gate 可验证的 needle"

**结论：PASS。** GitHub Secrets 明确排除在 canary scan needle 之外。

### 4.3 POSIX parser

**验证**：
- §4 S1 step 2："不得使用...POSIX loose parser"
- §5.1："不得用...POSIX loose parsing"
- Rereview Controller adjudication 拒绝 DS POSIX parser open question："plan 继续禁止 POSIX loose parser，只允许 Windows batch/CRT 或等价 Windows 语义 parser"

**结论：PASS。** POSIX parser 禁止，只允许 Windows 语义 parser。

### 4.4 TemporaryFile / cleanup poll / TimeoutExpired

**验证**：
- TemporaryFile：§2.3 锁定 `tempfile.TemporaryFile(mode="w+b")`，禁止 `mkstemp`/`NamedTemporaryFile`/`tmp_path`/unlink/retained-path
- Cleanup poll：§2.3 step 5 锁定 cleanup timeout 后恰好一次非阻塞 `poll()`，不再次 wait/kill
- TimeoutExpired：§0.1 "保持该约束，不增加 exception inspection、logging、redaction shim 或 traceback repair"；§2.2 "不得绑定、格式化、记录或转抛 raw exception，因为 exception args 含完整 setx argv/value"

**结论：PASS。** 三个边界均在 plan 中精确锁定，无漂移。

### 4.5 无过度设计

**验证**：
- 无新增 abstraction、framework、secret infrastructure、diagnostic framework
- 无扩域（Issue 142/151/175/177/178、Web/WeChat/render 全部禁止）
- 无兼容性代码（§11 "零 compatibility re-export/wrapper/alias"）
- 三 slice 只修改 5 个 product/test 文件 + 1 个 README
- Canary 是 non-secret、test-owned、run-specific 的固定纯函数，不是 auth/identity framework

**结论：PASS。** 最小化修复，无过度设计。

---

## 五、Rejected / already-satisfied candidates 回流检查

| Candidate | 原 disposition | Final plan 状态 | 回流 |
| --- | --- | --- | --- |
| DS Finding 1.2b | 并入 F01 | §4 S1 fail-closed 约束 | 无 |
| DS Finding 2.2a | already satisfied | `TimeoutExpired` 不绑定/格式化/记录/转抛 | 无 |
| DS Finding 2.2b | rejected | 不增加 timing instrumentation | 无 |
| DS Finding 3.1a | rejected | 不枚举 PIPE/handle-table 替代方案 | 无 |
| DS Finding 3.3a named-path | rejected | 锁定 anonymous handle lifetime | 无 |
| DS Finding 4.1a | rejected | 不新增 dependency framework | 无 |
| DS Finding 4.4a | rejected | README 继续与 S3 同 slice | 无 |
| DS Finding 5.1a | rejected | 不冻结易漂移测试数量 | 无 |
| DS Finding 5.6a | rejected | unexpected recurrence 阻塞 closure | 无 |
| MiMo RISK-2 | rejected | 保持 S1→S2→S3 串行顺序 | 无 |
| DS re-review POSIX parser | 不形成 finding | 禁止 POSIX loose parser | 无 |
| DS re-review shared-helper | rejected | test/Controller 独立实现 | 无 |

**结论：零回流。** §0.1 disposition lock 精确保持所有 rejected/already-satisfied candidates。

---

## 六、原 DS re-review 两项 LOW finding 验证

### REREVIEW-01 — Domain separator `\0` 字节歧义

**DS 原始严重度**：LOW。

**当前 plan 状态**：WIN4-PR-RR-F01 已在 plan-fix 中关闭。§2.3 现使用 Python bytes literal `b"dayu-ar-f07-win4-r12-canary-v1\x00"`，显式禁止两种误实现，owner test 锁定完整 bytes + known vector。

**结论：已由 WIN4-PR-RR-F01 覆盖并关闭。**

### REREVIEW-02 — Controller 取得正确 R12 Run ID 的 Procedural Gap

**DS 原始严重度**：LOW。

**当前 plan 状态**：WIN4-PR-RR-F02 已在 plan-fix 中关闭。§9.3 现冻结 Controller 必须使用 dispatch response 返回的唯一 `run_id`，下载前验证五项 metadata，same-run lineage 强制。

**结论：已由 WIN4-PR-RR-F02 覆盖并关闭。**

---

## 七、Material findings

**零 material findings。**

本次最终 re-review 验证了以下全部维度：

1. WIN4-PR-F01..F04 四项首轮 accepted findings 均已在 final plan 中精确闭合。
2. WIN4-PR-RR-F01..F02 两项 re-review accepted findings 均已在 plan-fix 后的 final plan 中精确闭合。
3. bytes literal / single NUL / known vector：Python literal 无歧义，已知向量独立验证匹配。
4. test 与 Controller 独立实现：禁止共享 helper/constant/artifact needle。
5. dispatch-returned R12 run_id：来源锁定为 dispatch response，排除猜测。
6. workflow path/event/branch/head_sha：五项 metadata 全部预检。
7. same-run artifacts lineage：同一 run_id + metadata tuple 强制。
8. standalone R11 不从 R12 canary scan 获得伪造证明。
9. GitHub Secrets 不作为 needle。
10. POSIX parser 禁止。
11. TemporaryFile/cleanup poll/TimeoutExpired 边界未漂移。
12. 无过度设计。
13. 所有 rejected/already-satisfied candidates 零回流。
14. DS 两项 LOW finding 已被 WIN4-PR-RR-F01/F02 覆盖关闭。

---

## 八、结论

**PASS。**

Final plan（SHA-256 `2359f24251838ec5d779ed0a1eb804ebacce3405e102a0cbc50a70f5844fd73a`，673 lines）已通过最终完整 re-review。

六项 accepted findings（WIN4-PR-F01..F04 + WIN4-PR-RR-F01..F02）全部精确闭合，contract 具体到 code-generation-ready 级别。R12 canary 双 owner contract（纯函数派生 + Controller 独立重算 + dispatch-returned run_id + same-run lineage + metadata 预检）完整可执行。standalone R11 边界清晰，GitHub Secrets 排除在 needle 外，POSIX parser 禁止，TemporaryFile/cleanup poll/TimeoutExpired 边界未漂移，无过度设计，零 rejected candidates 回流。

Plan 已满足 `READY_FOR_IMPLEMENTATION` 条件。

---

## Artifact integrity

- 本 artifact 不含随机 sentinel、registry value、configured secret、raw source content 或用户绝对路径。
- 本 artifact 不修改 plan/control/production/tests/README/workflow，不 stage/commit/push/dispatch。
- 本 artifact 路径：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-final-rereview-mimo.md`。
- 生成 timestamp：`20260720-021419`。
