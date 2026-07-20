# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4 Remediation Plan — AgentDS Complete Re-Review

## Identity

- **Review type**: adversarial plan re-review（非新 WU、非 implementation、非 control transition）
- **Reviewer**: AgentDS
- **Reviewed target**: final remediation plan
  `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`
  - SHA-256: `0bd1382288a06cafb77f8bbced45b4b7e08d48c9ab895dfdac1fdad0efddbbe9`
  - 634 lines, 12 sections
- **Baseline HEAD**: `54e2dcbf653fb8c37b0206bd7aabbbf329ef040e`
- **Date**: 2026-07-20
- **Previous reviews ingested**:
  - AgentMiMo: `e5af0d3d08ca910a1da18e74f0a1f5c17c0ad643f7fa01fc762fc2bb087afaaf` (PASS_WITH_RISKS)
  - AgentDS: `cb4ef70a0b28c1e168710cf3afabbbb2b3b17b0916ca3c54bfb03561fdd83fce` (PASS-WITH-RISKS)
- **Controller artifacts ingested**:
  - Adjudication: `a61568b1c4212286a8f92c80c7794ce5c889be56e3e333f6a1bd0ad87d7c9ba4`
  - Codex fix: `fabf821f453996d3d2d141d530a5ac7ef28211f51eee513c55de43bc8083579a`
  - Controller validation: `f9be890e3abccf117167d911f91ec0df54d816a37026c9eb40916c5b6005ed52`
- **Related design/discussion**:
  - `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`
  - `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`
  - `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`
- **Slog**: 本次是既有 WU 内 AR-F07 WIN4 remediation final plan 的完整 re-review，不是新 WU。

## 1. Input Integrity Verification

| 输入 | Expected SHA-256 | Actual SHA-256 | Match |
|------|------------------|----------------|-------|
| Final plan | `0bd1382288a06cafb77f8bbced45b4b7e08d48c9ab895dfdac1fdad0efddbbe9` | `0bd1382288a06cafb77f8bbced45b4b7e08d48c9ab895dfdac1fdad0efddbbe9` | ✓ |
| Controller adjudication | `a61568b1c4212286a8f92c80c7794ce5c889be56e3e333f6a1bd0ad87d7c9ba4` | `a61568b1c4212286a8f92c80c7794ce5c889be56e3e333f6a1bd0ad87d7c9ba4` | ✓ |
| Codex fix | `fabf821f453996d3d2d141d530a5ac7ef28211f51eee513c55de43bc8083579a` | `fabf821f453996d3d2d141d530a5ac7ef28211f51eee513c55de43bc8083579a` | ✓ |
| MiMo review | `e5af0d3d08ca910a1da18e74f0a1f5c17c0ad643f7fa01fc762fc2bb087afaaf` | `e5af0d3d08ca910a1da18e74f0a1f5c17c0ad643f7fa01fc762fc2bb087afaaf` | ✓ |
| DS review | `cb4ef70a0b28c1e168710cf3afabbbb2b3b17b0916ca3c54bfb03561fdd83fce` | `cb4ef70a0b28c1e168710cf3afabbbb2b3b17b0916ca3c54bfb03561fdd83fce` | ✓ |

全部固定输入 SHA-256 匹配。Controller validation artifact 的实时 SHA-256
`f9be890e3abccf117167d911f91ec0df54d816a37026c9eb40916c5b6005ed52` 也经读取验证——该文件未被用户指定 expected SHA，
其锁定的 plan SHA (`0bd13822...`) 与 codex fix SHA (`fabf821f...`) 均与本次验证一致。

## 2. WIN4-PR-F01..F04 Closure Verification

### 2.1 WIN4-PR-F01 — S1 Pre-Execution Oracle 精确性

**原始 finding**: MiMo RISK-1 + DS Finding 1.2a — S1 oracle 实现指导不够具体，可能用简单字符串计数而非结构化解析。

**Plan 最终锁定位置**:
- §0.1 disposition lock: 明确接受并锁定
- §4 WIN4-S1 step 2: 精确实现 contract
- §5.1: 对应 negative cases
- AgentCodex fix artifact §WIN4-PR-F01: CLOSED IN PLAN

**最终 contract 逐项验证**:

| Contract 要素 | Plan 位置 | 是否锁定 | 代码可行性 |
|--------------|-----------|---------|-----------|
| 在执行 `.cmd` 前运行并 fail closed | §4 S1.2 | ✓ | 在 `subprocess.run` 前断言，不受 execution returncode 影响 |
| 按 CRLF physical line 解析 | §4 S1.2 | ✓ | Python `splitlines` / `split(b"\r\n")` 直接可用 |
| 排除 `REM Regenerate:` 注释和固定 batch header | §4 S1.2 | ✓ | 现有 `.cmd` 固定以 `@echo off`/`chcp 65001`/`setlocal` 开头 |
| 只允许唯一非 `REM` 的 `upload_filing` 业务命令 | §4 S1.2 | ✓ | filter + count == 1 |
| 使用现有 Windows batch/CRT argv oracle 或等价逐 token 解析 | §4 S1.2 | ✓ | 现有 `_decode_windows_batch_fixed_token()` (L960-986) 已验证可用 |
| 证明 `--company-name` 恰好一个且下一 token 精确为 `Apple Inc.` | §4 S1.2 | ✓ | token-based index access |
| 禁止 whole-file `count` / substring / POSIX loose parser | §4 S1.2 + §5.1 | ✓ | 显式禁止 |
| 禁止从 execution result 反推输入 | §4 S1.2 | ✓ | 显式禁止 |
| 禁止 comment-only 证明 | §4 S1.2 + §5.1 | ✓ | negative case: comment 含 company-name 但命令不含 → fail |

**直接代码证据**: `tests/cli/test_upload_filings_from_command.py:960-986` 已存在 `_decode_windows_batch_fixed_token`
函数，实现 Windows batch percent doubling 与 caret 解码。S1 oracle 可直接复用该函数对提取的业务命令行做
token 级解析。

**结论: CLOSED。** Plan 现在精确锁定了实现 contract，implementation agent 无需重新设计 oracle 策略。

### 2.2 WIN4-PR-F02 — Cleanup-Timeout 后非阻塞进程状态投影

**原始 finding**: DS Finding 3.2a — cleanup bounded wait 再次 timeout 时未指定 process 终态。

**Plan 最终锁定位置**:
- §2.3 step 5: 精确 cleanup-timeout 后行为
- §4 WIN4-S3 step 2: negative case 覆盖
- §5.3: 对应 negative cases
- AgentCodex fix artifact §WIN4-PR-F02: CLOSED IN PLAN

**最终 contract 逐项验证**:

| Contract 要素 | Plan 位置 | 是否锁定 |
|--------------|-----------|---------|
| cleanup bounded wait 再次 timeout 后只调用一次非阻塞 `poll()` | §2.3.5 | ✓ |
| `None` 投影为 `process_state_after_cleanup_timeout=running` | §2.3.5 | ✓ |
| Integer 投影为 `process_state_after_cleanup_timeout=exited` 并进入 `cleanup_returncode` | §2.3.5 | ✓ |
| 不得再次 wait/kill | §2.3.5 + §5.3 | ✓ |
| 不得递归治理 process tree | §2.3.5 + §5.3 | ✓ |
| 不得把 post-cleanup poll 冒充 deadline 前自然退出 | §2.3.5 + §5.3 | ✓ |
| Negative case: cleanup timeout 后 `running` 与 `exited` 两种 poll 结果均覆盖 | §5.3 | ✓ |

**结论: CLOSED。** Plan 现在精确区分了四种终止状态（deadline 前自然退出、deadline 时 kill 成功、cleanup
timeout → running、cleanup timeout → exited），无混淆空间。

### 2.3 WIN4-PR-F03 — Anonymous-File Primitive 与 Handle Lifetime

**原始 finding**: DS Finding 3.3a — stdin temp file 的 unlink 时机未显式指定。

**Controller 裁决**: 接受 cleanup-contract 风险事实，但拒绝 DS 的 `mkstemp` / named-path / retained-path warning
方案。锁定 `tempfile.TemporaryFile(mode="w+b")` context handles，contract 是 handle lifetime。

**Plan 最终锁定位置**:
- §0.1 disposition lock: 明确拒绝 named-path 方案
- §2.3 steps 1-8: 完整 handle lifetime contract
- §4 WIN4-S3 step 1: 实现 contract
- §5.3: 对应 negative cases
- AgentCodex fix artifact §WIN4-PR-F03: CLOSED IN PLAN

**最终 contract 逐项验证**:

| Contract 要素 | Plan 位置 | 是否锁定 | 正确性评估 |
|--------------|-----------|---------|-----------|
| 三个 `tempfile.TemporaryFile(mode="w+b")` context handles | §2.3.1 + §4 S3.1 | ✓ | POSIX: 匿名文件无目录项；Windows: `O_TEMPORARY` 关闭即删 |
| stdin handle: 写入 input_text、flush、rewind、清空 frame 变量 | §2.3.1 | ✓ | 清空 frame 变量降低 failure-frame 持有风险 |
| Popen 只接收 handle，不接收 `input=` | §2.3.1 | ✓ | 消除 sentinel 进入 communicate 路径 |
| stdout/stderr 写入各自 handle | §2.3.2 | ✓ | 普通文件不等 pipe EOF |
| 三个 handle 覆盖 child execution + bounded cleanup 完整生命周期 | §2.3.3 | ✓ | 生命周期在 helper 内自足 |
| 成功时 rewind + read + strict UTF-8 decode | §2.3.4 | ✓ | typed result 不含 argv/path/input |
| failure path 不读取 stdout/stderr 内容 | §2.3.5 | ✓ | handle 只关闭，不读取 |
| 三个 handle 在 `finally` / context unwind 关闭 | §2.3.8 | ✓ | context manager 保证 unwind |
| 不记录 path | §2.3.8 | ✓ | 显式禁止 |
| 不使用 `mkstemp` / `NamedTemporaryFile` / pytest `tmp_path` | §2.3.8 + §5.3 | ✓ | 显式禁止 |
| 不增加显式 unlink / retained-path warning / 新 cleanup framework | §2.3.8 + §5.3 | ✓ | 显式禁止 |

**安全性分析**: `tempfile.TemporaryFile` 在 POSIX 上创建真正匿名的文件（`O_TMPFILE` 或立即 unlink），进程崩溃
时内核回收。在 Windows 上使用 `O_TEMPORARY` flag，handle 关闭时文件系统删除。plan 拒绝对该文件建立 durable
path 语义——contract 是 handle lifetime，而不是 durable cleanup。这与 F03 的安全目标（sentinel 不进入
JUnit/workflow evidence）完全一致。

**结论: CLOSED。** Plan 现在精确锁定了 `TemporaryFile` handle lifetime contract，拒绝了 named-path 方案，
没有引入新 cleanup framework。

### 2.4 WIN4-PR-F04 — R12 Controller Canary Scan Gate

**原始 finding**: DS Finding 5.5a — 真实 artifact 必须有可执行 non-disclosure gate，但原方案（Controller 扫描
configured secret / runtime needle）因当前 R12 test 内部随机生成值且 GitHub Secrets 不可读取而不可执行。

**Controller 裁决**: 改为 test-owned、run-specific、非秘密 canary — 从公开 `GITHUB_RUN_ID` 经固定
domain-separated 纯函数派生 API-key-shaped canary。Controller 从公开 R12 run id 独立重算并扫描。

**Plan 最终锁定位置**:
- §2.3 steps 1-5 (canary 派生 contract)
- §4 WIN4-S3 step 3 (canary 实现 contract)
- §5.4 (canary negative cases)
- §6.6 (security scans)
- §8 (closure matrix R12 Controller canary scan row)
- §9.3 (security gate)
- §12 (completion report contract)
- AgentCodex fix artifact §WIN4-PR-F04: CLOSED IN PLAN

**Canary 派生 contract 完整链**:

1. **输入**: 公开 `GITHUB_RUN_ID` 环境变量 → 必须为正十进制整数 → `str(int(GITHUB_RUN_ID))` 得到 canonical decimal text
2. **Domain separator**: ASCII bytes `dayu-ar-f07-win4-r12-canary-v1\0`
3. **派生**: `sha256(domain_separator + canonical_run_id.encode("ascii")).hexdigest()`
4. **最终 canary**: `sk-dayu-test-<64 lowercase hex digest>`
5. **性质**: 无 secret/key/salt、无时间或随机输入、纯函数可独立重算

**Controller 扫描 contract**:

| Contract 要素 | Plan 位置 | 可执行性 |
|--------------|-----------|---------|
| Controller 只从公开 R12 run id 独立重算 canary | §9.3 | ✓ 纯函数，Python 一行可算 |
| 扫描 R12 完整 workflow log + 全部 downloaded artifacts（含解包 JUnit/stdout/stderr/source-hash/embedded R11） | §9.3 | ✓ `gh run download` + `find` + `rg` |
| 递归 exact-value scan，零命中才通过 | §9.3 | ✓ `rg -r '' --files-with-matches` 或等价 |
| 不读取/扫描 GitHub Secrets 或 configured production values | §9.3 | ✓ 显式禁止 |
| Controller 不从 test output/artifact 取得 needle | §9.3 | ✓ 强制独立重算 |
| 命中只记录 R12 run id、artifact-relative locator、`match_category=test_canary`、gate status | §9.3 | ✓ value-free evidence |
| 扫描命令/review/control 零回显 canary | §9.3 | ✓ |
| Standalone R11 不在 scan 范围 | §9.3 | ✓ R11 未消费 canary |

**结论: CLOSED。** 新的 canary gate 是双 owner contract：test owner 产生 canary（从公开 run id 纯函数派生），
Controller owner 独立验证。双方不需共享 secret、不需读取 GitHub Secrets、不需将随机值写成 needle。

**Residual risk note**: domain separator `\0` 的字节级解释（NUL 0x00 vs 字面量 backslash-zero）在 plan 文本中
未完全消除歧义。§5.4 的 owner test 约束（"任一漂移都必须由owner test失败"）提供了实施级锁——test 代码中
的 domain separator bytes 是 Controller 独立重算的真源。见 Finding REREVIEW-01。

## 3. R12 Canary Scan 可执行性详细验证

### 3.1 派生可执行性

Controller 独立重算 canary 的完整步骤：

```
1. 从公开 GitHub Actions URL 取得 R12 run id（例如 https://github.com/noho/dayu-agent-r/actions/runs/<run_id>）
2. run_id_str = str(int(str(run_id)))  # canonical decimal
3. domain = b"dayu-ar-f07-win4-r12-canary-v1\0"  # 见 Finding REREVIEW-01
4. canary = "sk-dayu-test-" + hashlib.sha256(domain + run_id_str.encode("ascii")).hexdigest()
```

步骤 1-4 均为确定性操作，不需要任何 secret。唯一要求 Controller 能找到正确的 R12 workflow run——这是
procedural step，不是 technical blocker。R12 workflow 的 run id 出现在 workflow dispatch 响应或 GitHub Actions
UI 中，是公开信息。

### 3.2 扫描可执行性

```
gh run download <run_id> --dir workspace/tmp/r12-scan
rg -r '' --files-with-matches "<canary>" workspace/tmp/r12-scan/
```

`rg` 对全部解包 artifact 做 exact-value 匹配。若 R12 test 正确（canary 不进入 stdout/stderr/safe failure/JUnit），
扫描零命中。扫描命令本身不包含 canary 值（canary 在 Controller 本地变量中），review/control doc 只记录
结果不记录 canary。

### 3.3 Standalone R11 不伪造证明

Plan §9.3 明确 standalone R11 "没有消费该canary，不进入本scan，也不得声称由本scan证明其non-disclosure"。
这是正确的——扫描一个从未输入的值不能提供 non-disclosure 证明。Standalone R11 按自己的 artifact integrity
与无 secret-input contract 验收。

### 3.4 GitHub Secrets 不作为 Needle

Plan §9.3 明确 "Controller不得读取、请求、导出或扫描GitHub Secrets/configured production values；当前R12
workflow没有把这些值作为本test input，因此它们不是本canary gate可验证的needle"。这是正确的——本 gate
只验证 test harness 不会把自己的 canary 复制到 evidence，不声称验证 production secret 的 non-disclosure。

### 3.5 跨 artifact 扫描范围

R12 workflow 运行 embedded R11 测试，embedded R11 evidence 进入 R12 artifact bundle。因此 R12 的 canary
scan 自然覆盖 embedded R11。Standalone R11 是独立 workflow，不在 scan 范围——这是正确区分。

## 4. TemporaryFile / Cleanup Poll / Command Oracle 边界审查

### 4.1 TemporaryFile Handle Lifetime

**设计决策**: 拒绝 named-path 方案（`mkstemp` / `NamedTemporaryFile` / `tmp_path` / unlink / retained-path
warning），锁定 `tempfile.TemporaryFile(mode="w+b")` context handle。

**审查结论: PASS。** 理由：

1. F03 的安全目标是 sentinel 不进入 JUnit/workflow evidence——不是建立 durable test artifact path 语义。
2. `TemporaryFile` 的 contract 是 handle lifetime：handle 关闭 → 文件消失（POSIX 匿名/POSIX unlink/Windows
   `O_TEMPORARY`）→ 不存在"残留文件需要清理"的问题。
3. 不存在"unlink 失败后 sentinel-bearing file 残留在磁盘"的 failure mode——因为文件本来就是匿名的或
   close 时自动删除的。
4. 引入 named-path + unlink + retained-path warning 反而会把"防止 sentinel 泄漏"的需求扩张为"建立 durable
   cleanup 语义"——这正是 plan 正确拒绝的过度设计。

### 4.2 Cleanup-TimeOut 单次 Non-Blocking Poll

**状态机验证**:

| 阶段 | 操作 | 结果 |
|------|------|------|
| `wait(timeout=180)` 正常返回 0 | success path | pass |
| `wait(timeout=180)` 正常返回非 0 | ordinary nonzero | `_assert_init_result` 按 returncode 失败 |
| `wait(timeout=180)` TimeoutExpired | 进入 cleanup | — |
| → `poll()` 返回 None | kill + bounded wait | — |
| → → bounded wait 正常返回 | `cleanup=completed`, `cleanup_returncode=<int>` | fail |
| → → bounded wait timeout | ONE non-blocking `poll()` | — |
| → → → `poll()` 返回 None | `process_state_after_cleanup_timeout=running` | fail |
| → → → `poll()` 返回 int | `process_state_after_cleanup_timeout=exited`, `cleanup_returncode=<int>` | fail |

四个终止状态不混淆：
- deadline 前自然退出 → `returncode_at_timeout` (int)
- kill 成功 → `cleanup=completed`
- cleanup timeout + process running → `cleanup=timeout` + `process_state_after_cleanup_timeout=running`
- cleanup timeout + process exited → `cleanup=timeout` + `process_state_after_cleanup_timeout=exited`

**审查结论: PASS。** 状态区分正确，无二次 wait/kill，无 process tree 治理，不把 post-cleanup poll 冒充 deadline
前自然退出。

### 4.3 Pre-Execution Command Oracle

**实现可执行性**: 现有 `_decode_windows_batch_fixed_token()` (L960-986) 已验证可对 Windows `.cmd` 的 batch body
行做 token 级解码。S1 oracle 的实现路径：

1. `script_bytes.split(b"\r\n")` → 按 CRLF 分行
2. 排除 `REM Regenerate:` 行和固定 header 行（`@echo off`/`chcp 65001`/`setlocal`）
3. 在剩余行中找含 `upload_filing` 的行 → 必须恰好一行
4. 对该行用 `_decode_windows_batch_fixed_token` + `shlex.split` 等价解析
5. 逐 token 验证 `--company-name` 恰好出现一次且下一 token 为 `Apple Inc.`

**审查结论: PASS。** oracle 策略从现有代码可直接推导，implementation agent 无需发明新解析器。

## 5. Rejected Candidates Non-Backflow Verification

Plan §0.1 disposition lock 完整保留了所有 rejected / already-satisfied candidates：

| Candidate | 原始 disposition | Plan §0.1 锁定 | 是否有回流 |
|-----------|-----------------|---------------|-----------|
| `TimeoutExpired` 不绑定/格式化/记录/转抛 | already satisfied | ✓ "保持该约束，不增加 exception inspection..." | 无 |
| 不为 30s owner budget 增加 timing instrumentation | rejected (DS 2.2b) | ✓ "不为 30 秒 owner budget 在真实 workflow 增加 timing instrumentation" | 无 |
| 不枚举 PIPE/handle-table/process-tree 替代方案 | rejected (DS 3.1a) | ✓ "不枚举或逐一实现 PIPE/handle-table/process-tree 等替代方案" | 无 |
| 不新增 dependency framework | rejected (DS 4.1a) | ✓ "S2→S3 现有依赖已经是必须先后关系，不新增 dependency framework" | 无 |
| `tests/README.md` 与 S3 同一 slice | rejected (DS 4.4a) | ✓ "不新增 docs transaction 机制" | 无 |
| `_SetxRecorder` 不冻结易漂移测试数量 | rejected (DS 5.1a) | ✓ 保持 | 无 |
| WIN4-F01 recurrence 进入 diagnostic-first | already satisfied (DS 5.6a) | ✓ "阻塞 closure，不成为当前 root cause 的第二种解释" | 无 |
| 保持用户指定 S1→S2→S3 串行顺序 | rejected (MiMo RISK-2) | ✓ "保持用户指定的 S1→S2→S3 串行顺序，不改为并行实施" | 无 |
| DS named-path 方案 | rejected in adjudication | ✓ "`mkstemp`、`NamedTemporaryFile`、pytest `tmp_path`、retained-path warning、显式 unlink 与新的 cleanup framework 均被拒绝" | 无 |
| DS Finding 1.2b (oracle placement) | already satisfied | ✓ 并入 F01 精确 fail-closed 约束 | 无 |
| DS Finding 2.2a (TimeoutExpired) | already satisfied | ✓ 保持不绑定/格式化/记录/转抛 raw exception | 无 |

**审查结论: PASS。** 所有 11 项 rejected / already-satisfied candidates 均被 plan §0.1 精确锁定，无回流。MiMo
RISK-1 和 DS Finding 1.2a 已通过 WIN4-PR-F01 关闭，不单独列为 rejected。

## 6. Overdesign Check

### 6.1 逐项验证

| 潜在过度设计 | Plan 是否引入 | 证据 |
|-------------|-------------|------|
| 新 cleanup framework | 否 | 锁定 anonymous handle lifetime，拒绝 named-path/unlink/retained-path |
| Timing instrumentation | 否 | 拒绝 DS 2.2b |
| Dependency framework | 否 | 拒绝 DS 4.1a |
| Process-tree 治理 | 否 | §2.2 明确不实施 Issue 175 |
| Secret infrastructure | 否 | §11 明确 zero unified authorization/secret infra |
| Generic diagnostic framework | 否 | §10 明确不借 diagnostic-first 进入 Issue 175 |
| Named-file lifecycle | 否 | §2.3 锁定 anonymous handle |
| 第二套 cleanup 语义 | 否 | §5.3 明确不产生/记录/清理 named temp path |
| Windows job object/process-isolation | 否 | §2.3 明确不引入 |
| 兼容性 re-export/wrapper/alias | 否 | §11 明确零 compatibility |
| R12 canary 成为 auth/identity framework | 否 | 只是固定纯函数 + scan，没有 token/role/session |

### 6.2 最小值边界

Plan 的三个 slice 只修改 5 个 product/test 文件 + 1 个 README：
- S1: 1 test file（R11 Windows real-smoke 输入修正）
- S2: 1 production file + 1 test file（setx stdio/timeout owner）
- S3: 1 test file + 1 README（harness safe failure + docs）

没有新增模块、class hierarchy、abstract base、factory、registry、plugin、middleware、observer、state-machine
framework 或 generic helper library。

**审查结论: PASS。** Plan 是最小化修复，没有过度设计。

## 7. 架构边界审查

### 7.1 分层合规

| 修改 | 所属层 | 是否跨层 |
|------|--------|---------|
| S1: test input 修正 | Test | 否。不修改 CLI/Fins production |
| S2: setx stdio/timeout | CLI → OS boundary | 否。`dayu/cli/init_environment.py` 是唯一 owner |
| S3: harness safe failure | Test | 否。`tests/cli/test_init_smoke.py` 是唯一 owner |

### 7.2 依赖方向

```
S1 (test) — 无生产依赖
S2 (production + test) — 无 S1 依赖，S3 依赖 S2
S3 (test + docs) — hard depends on S2
```

S3 的 harness 改动不能替代 S2 product fix（plan §4 S3 明确禁止）→ 正确。

### 7.3 Owner 唯一性

| 语义 | Owner | 是否唯一 |
|------|-------|---------|
| fresh create 需要 company name | `dayu/fins/pipelines/upload_company_meta.py` | ✓ |
| R11 Windows smoke 输入 | `test_windows_generated_script_runs_real_cli_into_temp_storage` | ✓ |
| setx stdio/timeout | `dayu/cli/init_environment.py::_persist_windows_environment()` | ✓ |
| outer CLI failure projection | `tests/cli/test_init_smoke.py::_run_init()` | ✓ |
| R12 canary producer | R12 real setx test (§2.3) | ✓ |
| R12 canary verifier | Controller (§9.3) | ✓ |

### 7.4 Public Contract 变更

无。S1-S3 均为内部修复：
- S1 修正 test input 使其满足既有 production contract（不修改 contract）
- S2 修改 setx 的 stdio handle 与 timeout（内部实现，外部 behavior 不变：names-only result 不变）
- S3 修改 test 的 failure projection（内部 harness 行为，production CLI 不变）

**审查结论: PASS。** 架构边界完整合规。

## 8. Findings

### REREVIEW-01 — Domain Separator `\0` 字节歧义（严重度: LOW）

- **位置**: Plan §2.3 canary 派生 contract — "ASCII bytes `dayu-ar-f07-win4-r12-canary-v1\0`"
- **问题类型**: 契约缺失（字节级精确值未在两个 owner 间完全消除歧义）
- **当前写法**: 使用 markdown backtick-quoted `dayu-ar-f07-win4-r12-canary-v1\0`，在 Python 上下文中
  `\0` 是 NUL byte (0x00)，但若有人按字面量复制 backtick 内字符（backslash + zero）作为 domain separator
  bytes，将产生不同的 canary。
- **反例/失败场景**: test 代码中以 `b"dayu-ar-f07-win4-r12-canary-v1\x00"` 实现（NUL byte），但 Controller
  以 `b"dayu-ar-f07-win4-r12-canary-v1\\0"` 实现（两个字面量字符），Controller 重算的 canary 与 test
  产生的 canary 不同，scan 必然零命中——这恰好是"假阴性"：gate pass 但未真正验证 non-disclosure。
- **为什么有问题**: canary gate 要求 test 和 Controller 双方使用完全相同的 domain separator bytes。Plan 的
  文本表述未达到 code-generation-ready 的字节级精确度。
- **直接证据**: Plan §2.3 backtick-quoted string 与 §5.4 "任一漂移都必须由owner test失败" — owner test
  的约束可以作为实施级锁，但它在 plan 层面留下了双方理解不一致的可能。
- **影响**: 实施 Agent 和 Controller 若对 `\0` 有不同解释，canary gate 可能给出虚假 pass。不阻塞 plan
  approval，但应在 implementation 中明确锁定。
- **建议改法和验证点**:
  1. Implementation 中 test 代码使用显式 `b"dayu-ar-f07-win4-r12-canary-v1\x00"`（明确的 NUL byte 表示）
  2. Controller scan 前先验证：从同一公开 run id 独立计算后，与 test artifact 中的 canary（如果 test
     内部在 assertion 之前临时输出过一次 canary hash 的 hexdigest 用于自证）对比——但 plan 禁止 canary
     进入 artifact。替代方案：Controller 和 test 使用同一 Python helper module 中的同一 domain separator
     常量。但这会引入新依赖。
  3. 最简单的锁定：在 plan fix 中将 domain separator 写为显式 bytes literal
     `b"dayu-ar-f07-win4-r12-canary-v1\x00"`，明确 NUL byte。
- **修复风险**: 低
- **严重程度**: LOW — owner test 已锁定"任一漂移失败"，且 NUL byte 是该语境下最自然的解读（domain
  separator 使用不可打印字符防止与 run id 中的字符冲突）

### REREVIEW-02 — Controller 取得正确 R12 Run ID 的 Procedural Gap（严重度: LOW）

- **位置**: Plan §9.3 Controller canary scan
- **问题类型**: open question 未收敛（Controller 如何可靠定位"新 R12 run"的公开 run id）
- **当前写法**: Plan 说 "Controller从新R12 workflow公开run id按§2.3冻结纯函数独立重算canary"——假定
  Controller 能可靠找到正确的 run id。
- **反例/失败场景**: R12 workflow 可能被多次 dispatch；若 Controller 误取旧 run 的 id，scan 可能零命中
  （旧 run 的 log 不含 canary——如果当时 test 尚未实现 canary），产生虚假 pass。
- **为什么有问题**: run id 的选择是 canary gate 正确性的前提。若 Controller 选错 run，scan 在一个不包含
  canary 的 artifact set 上做 exact-value 搜索自然零命中，但这不证明 non-disclosure。
- **直接证据**: Plan §8 closure matrix 的 R11/R12 行要求 "新 JUnit/source-hash/artifact SHA-256由Controller
  重新计算"——这暗示 Controller 已经需要定位新 artifacts。但 R12 canary scan row 没有显式要求关联该 run 的
  commit SHA。
- **影响**: 若 Controller 选错 run → 虚假 pass → canary 可能实际上已泄漏但未被发现。
- **建议改法和验证点**:
  1. R12 canary scan gate 应额外要求 Controller 验证该 run 的 commit SHA 等于 accepted implementation commit
  2. 或在 implementation completion report 中明确记录 R12 run id，Controller 直接使用该值
  3. 这不是 plan fix 必须项，但 Controller 在执行 scan 前应确认 run 的 commit 匹配
- **修复风险**: 低
- **严重程度**: LOW — Controller 已在 closure matrix 其它 row 需要关联 commit SHA，可自然扩展到 canary scan

## 9. Open Questions

1. **R12 run id 定位**: Controller 如何确保扫描的是正确的 R12 run？（见 REREVIEW-02）建议在
   implementation completion report 中明确记录 R12 run id，Controller 直接使用。

2. **S1 oracle 的 `shlex.split` 等价性**: Plan 说"使用现有Windows batch/CRT argv oracle或等价的Windows语义逐
   token解析"。`shlex.split` 是 POSIX 语义（POSIX quoting rules），在 Windows 上对 batch file body line 的
   行为可能与 `cmd.exe` 实际解析不同。应使用现有的 `_decode_windows_batch_fixed_token`（它正确处理了
   `%%` → `%` 和 `^` escape）加空格 split，而非 `shlex.split`。

3. **S3 的 `process_state_after_cleanup_timeout` 字段命名**: 该字段只在 cleanup timeout 时出现，但在
   §2.3 step 5 和 §5.3 中使用。它的出现条件（只在 cleanup=timeout 时追加）在 plan 中通过 §5.3 的 negative
   case 间接隐含——可更明确。

## 10. Residual Risks

| Risk | Severity | Owner | Tracking |
|------|----------|-------|----------|
| Domain separator `\0` 歧义（REREVIEW-01） | Low | Implementation agent + Controller | 在 implementation 中锁定 `\x00` |
| Controller run id 定位（REREVIEW-02） | Low | Controller | 在 closure scan 前验证 commit SHA |
| S1 oracle 的 POSIX `shlex.split` vs Windows batch parser | Low | Implementation agent | 使用现有 `_decode_windows_batch_fixed_token` |
| R12 真实 Windows runner 尚未执行，所有 real-smoke 验证待确认 | Medium | Release gate | Plan §8 已列为 release blocker |

**注**: 第 4 项是 plan 已明确承认的 residual——local validation 不能替代真实 Windows runner evidence。这不
是 plan defect，而是当前 gate 的已知限制。

## 11. Conclusion

### 11.1 Per-Dimension Verdict

| Dimension | Verdict |
|-----------|---------|
| WIN4-PR-F01 closure (S1 oracle) | PASS |
| WIN4-PR-F02 closure (cleanup poll) | PASS |
| WIN4-PR-F03 closure (TemporaryFile) | PASS |
| WIN4-PR-F04 closure (R12 canary scan) | PASS |
| R12 canary derivation executability | PASS |
| R12 canary Controller scan executability | PASS |
| Standalone R11 non-falsification | PASS |
| GitHub Secrets not as needle | PASS |
| TemporaryFile handle lifetime boundary | PASS |
| Cleanup poll state machine boundary | PASS |
| Pre-execution command oracle boundary | PASS |
| Rejected candidates non-backflow | PASS |
| Overdesign absence | PASS |
| Architecture boundary compliance | PASS |
| Forbidden paths compliance | PASS |

### 11.2 Overall Conclusion

**PASS。**

Plan 的 WIN4-PR-F01..F04 四项 finding 均已闭合，contract 具体到 code-generation-ready 级别。三项 slice
的 owner、allowlist、stop condition、negative cases 和 validation matrix 完整且正确。

R12 public GITHUB_RUN_ID canary 的派生 contract 是冻结纯函数——无 secret、无 salt、无随机，Controller
可独立重算并执行 exact-value scan。Standalone R11 正确排除在 scan 范围外，GitHub Secrets 正确排除在
needle 范围外。

TemporaryFile handle lifetime、cleanup-timeout 单次 non-blocking poll 和 pre-execution command oracle
三个边界的 state machine 均无混淆。

全部 11 项 rejected / already-satisfied candidates 被 plan §0.1 disposition lock 精确保持，零回流，零过度设计。

两个 LOW-severity finding（REREVIEW-01 domain separator `\0` 歧义、REREVIEW-02 Controller run id
定位）不构成 plan fail，可在 implementation entry 或 Controller scan 执行时自然收敛。

### 11.3 Next Gate

Plan 已 `READY_FOR_DUAL_COMPLETE_REREVIEW`。本 re-review 是 DS 侧完整 re-review。待 AgentMiMo 侧
完整 re-review 完成后，由 Controller 裁决双路 re-review 结果，决定是否进入 accepted plan commit →
implementation authorization。

---

## Artifact Integrity

- **路径**: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-rereview-ds.md`
- **本 artifact SHA-256**: `5cd075a4751865898ce02f0db92dfbc795dafe5369225843f1689b4d2bd1ad73`
- **基线 HEAD**: `54e2dcbf653fb8c37b0206bd7aabbbf329ef040e`
- **审查结论**: `PASS`
- **Findings**: 2 (both LOW)
- **Open Questions**: 3
- **Residual Risks**: 4

本 artifact 不含随机 sentinel、registry value、configured secret、raw source content 或用户绝对路径。
本 artifact 不修改 plan/control/production/tests/README/workflow，不 stage/commit/push/dispatch。
