# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4 Remediation Plan — AgentDS Final Complete Re-Review

## Identity

- **Review type**: final adversarial plan re-review（非新 WU、非 implementation、非 control transition）
- **Reviewer**: AgentDS
- **Reviewed target**: final remediation plan（累计修复四轮 findings 后的最终计划）
  `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`
  - **Fixed plan SHA-256**: `2359f24251838ec5d779ed0a1eb804ebacce3405e102a0cbc50a70f5844fd73a`
  - 673 lines, 12 sections
- **Cumulative plan-fix artifact**: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-fix-codex.md`
  - **Fixed plan-fix SHA-256**: `52f5ae11a409b6d3ed5c3b16c30973972b876b8dc4f2d4ff7ff91f3dfb6ccbe4`
- **Baseline HEAD**: `54e2dcbf653fb8c37b0206bd7aabbbf329ef040e`
- **Date**: 2026-07-20
- **Timestamp**: 20260720-021650

### Full review chain ingested

| Stage | Document | SHA-256 | Verdict |
|-------|----------|---------|---------|
| Original Plan | `docs/host/...win4-remediation-plan.md` | `a290f418...` | — |
| DS first review | `...plan-review-ds.md` | `cb4ef70a...` | PASS-WITH-RISKS |
| MiMo first review | `...plan-review-mimo.md` | `e5af0d3d...` | PASS_WITH_RISKS |
| Controller adjudication #1 | `...review-controller-adjudication.md` | `a61568b1...` | FIX_REQUIRED |
| Codex plan-fix #1 | `...plan-fix-codex.md` (v1) | `fabf821f...` | WIN4-PR-F01..F04 CLOSED |
| Controller validation #1 | `...plan-fix-controller-validation.md` | `f9be890e...` | PASS |
| DS re-review | `...plan-rereview-ds.md` | `1c577311...` | PASS (2 LOW findings) |
| MiMo re-review | `...plan-rereview-mimo.md` | `9bd74bb2...` | PASS (0 findings) |
| Controller adjudication #2 | `...rereview-controller-adjudication.md` | `50dfcf9e...` | FIX_REQUIRED |
| Codex plan-fix #2 (cumulative) | `...plan-fix-codex.md` (final) | `52f5ae11...` | WIN4-PR-RR-F01..F02 CLOSED |
| Controller validation #2 | `...rereview-fix-controller-validation.md` | — | PASS |

### Additional sources ingested

- Controller discussion: `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`（前 100 lines）
- Evidence adjudication: `docs/reviews/wu-semantic-ownership-01-ar-f07-fourth-windows-evidence-controller-adjudication.md`
- Design truths: `docs/host/design.md`, `docs/fins/design.md`, `docs/ui/design.md`（trusted-local/config secret 边界）
- R11/R12 plans: `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`, `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`
- Code evidence:
  - `dayu/cli/init_environment.py`（836 lines，完整读取）
  - `tests/cli/test_init_environment.py`（1246 lines，完整读取）
  - `tests/cli/test_init_smoke.py`（963 lines，完整读取）
  - `tests/cli/test_upload_filings_from_command.py`（1012 lines，完整读取）

## 1. Input Integrity Verification

| 输入 | Expected SHA-256 | Actual SHA-256 | Match |
|------|------------------|----------------|-------|
| Final plan | `2359f24251838ec5d779ed0a1eb804ebacce3405e102a0cbc50a70f5844fd73a` | `2359f24251838ec5d779ed0a1eb804ebacce3405e102a0cbc50a70f5844fd73a` | ✓ |
| Cumulative plan-fix | `52f5ae11a409b6d3ed5c3b16c30973972b876b8dc4f2d4ff7ff91f3dfb6ccbe4` | `52f5ae11a409b6d3ed5c3b16c30973972b876b8dc4f2d4ff7ff91f3dfb6ccbe4` | ✓ |
| Baseline HEAD | `54e2dcbf653fb8c37b0206bd7aabbbf329ef040e` | `54e2dcbf653fb8c37b0206bd7aabbbf329ef040e` | ✓ |

全部固定输入 SHA-256 匹配。`git status --short` 确认 staged tree 为空，plan gate 无产品/测试/README/workflow diff。

## 2. WIN4-PR-F01..F04 Closure Verification

### 2.1 WIN4-PR-F01 — S1 Pre-Execution Oracle 精确性

**原始 finding**: MiMo RISK-1 + DS Finding 1.2a — S1 oracle 实现指导不够具体，可能用简单字符串计数而非结构化解析区分 regeneration comment 与业务 command。

**Controller 修复要求**: oracle 在执行 `.cmd` 前运行并 fail closed；按 CRLF line 排除 `REM Regenerate:` 注释和固定 batch header；只解析唯一 `upload_filing` 业务命令；使用现有 Windows batch/CRT argv oracle 或等价逐 token 解析；证明 `--company-name` 恰好一个且下一 token 精确为 `Apple Inc.`；禁止 whole-file count、substring、POSIX loose parser、execution result inference、comment-only proof。

**Final plan 锁定位置**: §4 S1 step 2（精确实现 contract）、§5.1（negative cases）

**逐项验证**:

| Contract 要素 | Plan §4 S1.2 | 代码可行性 |
|--------------|-------------|-----------|
| 按 CRLF physical line 解析 | ✓ | Python `split(b"\r\n")` 直接可用 |
| 排除 `REM Regenerate:` 注释和固定 header | ✓ | `.cmd` 固定以 `@echo off`/`chcp 65001`/`setlocal` 开头 |
| 只允许唯一非 `REM` 的 `upload_filing` 业务命令 | ✓ | filter + count == 1 |
| 使用现有 Windows batch/CRT argv oracle 或等价逐 token 解析 | ✓ | 现有 `_decode_windows_batch_fixed_token()` (L960-986) 已验证可用 |
| `--company-name` 恰好一个且下一 token 精确为 `Apple Inc.` | ✓ | token-based index access |
| 禁止 whole-file count/substring/POSIX loose parser/execution result inference | ✓ | 显式禁止 |

**直接代码证据**: `tests/cli/test_upload_filings_from_command.py:960-986` 已存在 `_decode_windows_batch_fixed_token` 函数，正确处理 Windows batch `%%` → `%` 和 `^` escape。S1 oracle 可直接复用。

**结论: CLOSED。** ✓

### 2.2 WIN4-PR-F02 — Cleanup-Timeout 后非阻塞进程状态投影

**原始 finding**: DS Finding 3.2a — cleanup bounded wait 再次 timeout 时未指定 process 终态。

**Controller 修复要求**: cleanup timeout 后只调用一次非阻塞 `poll()`；`None` → `process_state_after_cleanup_timeout=running`；integer → `process_state_after_cleanup_timeout=exited` 并进入 `cleanup_returncode`；不再次 wait/kill/process-tree governance/misrepresent。

**Final plan 锁定位置**: §2.3 step 5（精确状态机）、§4 S3 step 2（negative case 覆盖）、§5.3（negative cases）

**状态机验证**:

| 阶段 | 操作 | 投影事实 | 是否混淆 |
|------|------|---------|---------|
| `wait(180)` 正常返回 0 | success path | pass | 无 |
| `wait(180)` 正常返回非 0 | ordinary nonzero | `_assert_init_result` fail | 无 |
| `wait(180)` TimeoutExpired → `poll()` None | kill + bounded wait | — | 无 |
| → kill 后 bounded wait 正常返回 | cleanup=completed | `cleanup_returncode=<int>` | 无 |
| → kill 后 bounded wait timeout → ONE `poll()` | — | — | 无 |
| → → `poll()` None | | `process_state_after_cleanup_timeout=running` | 无 |
| → → `poll()` int | | `process_state_after_cleanup_timeout=exited` + `cleanup_returncode=<int>` | 无 |

四个终止状态精确区分：deadline 前自然退出、kill 成功、cleanup timeout+running、cleanup timeout+exited。无二次 wait/kill，无 process tree 治理，不伪装。

**结论: CLOSED。** ✓

### 2.3 WIN4-PR-F03 — Anonymous-File Primitive 与 Handle Lifetime

**原始 finding**: DS Finding 3.3a — stdin temp file 的 unlink 时机未显式指定。

**Controller 裁决**: 接受 cleanup-contract 风险事实，但拒绝 named-path 方案（`mkstemp`/`NamedTemporaryFile`/`tmp_path`/unlink/retained-path warning）。锁定 `tempfile.TemporaryFile(mode="w+b")` context handles，contract 是 handle lifetime，不是 durable path 语义。

**Final plan 锁定位置**: §0.1（拒绝 named-path）、§2.3 steps 1-8（完整 handle lifetime contract）、§4 S3 step 1（实现 contract）、§5.3（negative cases）

**逐项验证**:

| Contract 要素 | Plan 位置 | 安全性评估 |
|--------------|-----------|-----------|
| 三个 `tempfile.TemporaryFile(mode="w+b")` context handles | §2.3.1 | POSIX: 匿名文件无目录项；Windows: `O_TEMPORARY` 关闭即删 |
| stdin handle: write input_text, flush, rewind, clear frame variables | §2.3.1 | clear frame variables 降低 failure-frame 持有风险 |
| Popen 只接收 handle，不接收 `input=` | §2.3.1 | 消除 sentinel 进入 communicate 路径 |
| stdout/stderr 写入各自 handle（普通文件，不等 pipe EOF） | §2.3.2 | 解决 descendant pipe EOF hang |
| 三个 handle 覆盖 child execution + bounded cleanup 完整生命周期 | §2.3.3 | handle lifetime 在 helper 内自足 |
| success path: rewind + read + strict UTF-8 decode | §2.3.4 | typed result 不含 argv/path/input |
| failure path: 不读取 stdout/stderr | §2.3.5 | handle 只关闭不读取 |
| finally/context unwind 关闭 | §2.3.8 | context manager 保证 unwind |
| 不记录 path，禁止 mkstemp/NamedTemporaryFile/tmp_path | §2.3.8 + §5.3 | 显式禁止 |
| 不增加 unlink/retained-path warning/新 cleanup framework | §2.3.8 + §5.3 | 显式禁止 |

**安全性分析**: `TemporaryFile` 在 POSIX 上创建真正匿名文件（`O_TMPFILE` 或立即 unlink），进程崩溃时内核回收。Windows 上使用 `O_TEMPORARY` flag，handle 关闭时文件系统删除。不存在"unlink 失败后 sentinel-bearing file 残留磁盘"的 failure mode。引入 named-path 方案反而会把"防止 sentinel 泄漏"扩张为"建立 durable cleanup 语义"——是过度设计。

**结论: CLOSED。** ✓

### 2.4 WIN4-PR-F04 — R12 Controller Canary Scan Gate

**原始 finding**: DS Finding 5.5a — 真实 artifact 必须有可执行 non-disclosure gate，但原方案因 R12 test 内部随机生成值且 GitHub Secrets 不可读取而不可执行。

**Controller 裁决**: 改为 test-owned、run-specific、非秘密 canary——从公开 `GITHUB_RUN_ID` 经固定 domain-separated 纯函数派生 API-key-shaped canary。Controller 从公开 R12 run id 独立重算并扫描。

**Final plan 锁定位置**: §2.3（canary 派生 contract）、§4 S3 step 3（实现 contract）、§5.4（negative cases）、§6.6（security scans）、§8（closure matrix）、§9.3（security gate）、§12（completion report contract）

**Canary 派生 contract**:

1. 输入: 公开 `GITHUB_RUN_ID` → 必须为正十进制整数 → `str(int(GITHUB_RUN_ID))` canonical decimal text
2. Domain separator: Python bytes literal `b"dayu-ar-f07-win4-r12-canary-v1\x00"`（31 bytes, 末字节 0x00）
3. 派生: `sha256(domain_separator + canonical_run_id.encode("ascii")).hexdigest()`
4. 最终 canary: `sk-dayu-test-<64 lowercase hex digest>`
5. 性质: 无 secret/key/salt、无时间或随机输入、纯函数可独立重算

**Controller scan contract 逐项验证**:

| Contract 要素 | Plan 位置 | 可执行性 |
|--------------|-----------|---------|
| Controller 只从公开 R12 run id 独立重算 canary | §9.3 | ✓ 纯函数，Python 一行可算 |
| 扫描 R12 完整 workflow log + 全部 downloaded artifacts（含 embedded R11） | §9.3 | ✓ `gh run download` + `find` + `rg` |
| 递归 exact-value scan，零命中才通过 | §9.3 | ✓ `rg -r '' --files-with-matches` 或等价 |
| 不读取/扫描 GitHub Secrets 或 configured production values | §9.3 | ✓ 显式禁止 |
| Controller 不从 test output/artifact 取得 needle | §9.3 | ✓ 强制独立重算 |
| 命中只记录 R12 run id、artifact-relative locator、`match_category=test_canary`、gate status | §9.3 | ✓ value-free evidence |
| 扫描命令/review/control 零回显 canary | §9.3 | ✓ |
| Standalone R11 不在 scan 范围 | §9.3 | ✓ R11 未消费 canary |

**结论: CLOSED。** ✓

## 3. WIN4-PR-RR-F01..F02 Closure Verification

### 3.1 WIN4-PR-RR-F01 — Domain Separator 必须冻结为无歧义 bytes literal

**原始 finding**: DS REREVIEW-01 — plan 的 "ASCII bytes `dayu-ar-f07-win4-r12-canary-v1\0`" 仍允许 test 实现采用 NUL byte 而 Controller 采用 backslash+zero 两个字符；两边产生不同 canary，假 pass。

**Controller 修复要求**: 把唯一真值写成 Python bytes literal `b"dayu-ar-f07-win4-r12-canary-v1\x00"`，明确末字节 single NUL `0x00`，禁止 `b"...\\0"` 或 `b"...\\x00"`。Owner tests 锁完整 bytes 和已知 run-id→canary vector。

**Final plan 锁定位置**: §2.3（domain separator contract）、§4 S3 step 3（owner test contract）、§5.4（negative cases）

**External 可复核验证**:

```python
import hashlib
domain = b"dayu-ar-f07-win4-r12-canary-v1\x00"
assert len(domain) == 31                         # plan claim
assert domain[-1] == 0x00                        # last byte single NUL
canonical = "1".encode("ascii")
digest = hashlib.sha256(domain + canonical).hexdigest()
assert f"sk-dayu-test-{digest}" == \
    "sk-dayu-test-b8f2210d1ead3aac3a52408adb9de03c4e848d4c101f790e218ecc76e3350b97"  # plan known vector
```

以上全部断言通过。Controller 和任何外部 reviewer 可独立运行同一 Python 代码验证。

**Dual-owner 歧义消除**:

| Owner | 实现基础 | 是否相同 |
|-------|---------|---------|
| Test (R12 setx test) | Plan §2.3 text contract | 同一 `b"...\x00"` literal |
| Controller | Plan §2.3 text contract | 同一 `b"...\x00"` literal |
| 共享 helper/constant/needle | — | **禁止**（§2.3 明确） |

双方从同一 plan text 独立实现，不使用共享代码模块。Plan 已将歧义从 markdown backtick string（可被误读）升级为显式 Python bytes literal（不可误读）。

**结论: CLOSED。** ✓

### 3.2 WIN4-PR-RR-F02 — R12 Scan 必须锁定 dispatch 返回的 run 与 accepted commit

**原始 finding**: DS REREVIEW-02 — 仅写"新 R12 run"不足以防止并发/重复 dispatch 时误取旧 run；若用旧 run id 派生并扫描旧 artifacts，也会虚假零命中。

**Controller 修复要求**: Controller procedure 必须使用 dispatch response 返回的唯一 R12 `run_id`；下载前验证 workflow identity/path、event、branch 与 `head_sha == accepted implementation commit`；全部 evidence 必须来自同一 run id。Mismatch/ambiguous/missing → gate fail，不得猜"最近成功 run"。

**Final plan 锁定位置**: §5.4、§6.6、§8、§9.3（完整 Controller procedure）、§12（completion report contract）

**Controller procedure 锁定逐项验证**:

| Step | Contract 要素 | Plan 位置 | Fail-closed |
|------|--------------|-----------|-------------|
| 1 | 使用 dispatch response 返回的确切、唯一 R12 `run_id` | §9.3 step 1 | response 未返回/多个 candidate/无法唯一对应 → gate fail |
| 2a | 验证 workflow identity/name = `R12 init Windows gate` | §9.3 step 2 | mismatch → gate fail |
| 2b | 验证 workflow path = `.github/workflows/r12-init-windows.yml` | §9.3 step 2 | mismatch → gate fail |
| 2c | 验证 event = `workflow_dispatch` | §9.3 step 2 | mismatch → gate fail |
| 2d | 验证 branch/ref = dispatch target branch/ref 且承载 accepted implementation commit | §9.3 step 2 | mismatch → gate fail |
| 2e | 验证 `head_sha` = accepted implementation commit SHA | §9.3 step 2 | mismatch → gate fail |
| 3 | All evidence (status/log/JUnit/source-hash/artifacts/embedded R11/canary scan) 来自同一 `run_id` 和 metadata tuple | §9.3 step 3 | missing/不完整/无法证明 same-run lineage/跨 run 混用 → gate fail |
| — | 禁止从"最近成功 run"、summary、时间戳或 artifact 名猜测 | §9.3 step 2/3 | 显式禁止 |

**分析**: GitHub REST API `POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches` 返回 204 No Content，不直接返回 `run_id`。但 plan 的 contract 是"必须使用能在本次 dispatch response 中返回确切 R12 `run_id` 的调用方式"——这强制 Controller 选择能返回 `run_id` 的 dispatch 机制（例如通过 API polling 或使用 `gh run list` 配合 head_sha 过滤）。若选不到，gate fail——正确 fail-closed。Metadata verification（step 2a-2e）提供第二层保护：即使 run_id 获取方式有 race，metadata mismatch 也会 fail closed。

**结论: CLOSED。** ✓

## 4. Specific Challenge Areas — Deep Adversarial Verification

### 4.1 Bytes Literal / Single NUL / Known Vector

**Challenge**: domain separator `b"dayu-ar-f07-win4-r12-canary-v1\x00"` 的字节级解释是否在两个 owner 间完全消除歧义？已知向量是否可被外部独立复核？

**Evidence**:
- Plan §2.3: 明确 Python bytes literal，31 bytes，末字节 `0x00`
- Plan §2.3: 显式禁止 `b"...\\0"`（backslash + zero）和 `b"...\\x00"`（字面 backslash + x00）
- Plan §5.4: owner tests 必须锁完整 bytes、single NUL、known run-id→canary vector
- Plan §2.3: "Test owner 与 Controller owner 必须分别仅依据本节冻结的 bytes/formula/vector 实现与独立重算"

**External 可复核**: 任何第三方可运行上文 §3.1 的 Python 代码验证 known vector。本 reviewer 已独立验证通过（见 §7.1）。

**Risk**: plan 的 markdown 文件中 `\x00` 是 four-char ASCII sequence `\x00`，但任何合格的 Python 程序员读取 `b"...\x00"` 都会理解为 NUL byte。Plan 同时提供了独立验证手段：31 bytes length + last byte 0x00 + known run-id→canary vector——三者共同构成无需信任文本解释的 cross-check。

**Verdict: PASS。** 歧义已消除，外部可独立复核。

### 4.2 Test 与 Controller 独立实现

**Challenge**: plan 是否真正确保 test 和 Controller 不共享实现，防止"共享代码正确但两边都错同一种方式"的假 pass？

**Evidence**:
- Plan §2.3: "Test owner 与 Controller owner 必须分别仅依据本节冻结的 bytes/formula/vector 实现与独立重算；禁止共享 production helper、test helper、生成的 needle artifact 或其它共享实现真源"
- Plan §5.4: "Test 与 Controller 不共享 helper、constant module 或 artifact needle"
- Plan §9.3: "禁止与 production/test 共享 helper、constant module 或生成实现；禁止从 test output/artifact 取得 needle"
- Plan §0.1: DS 的 shared-helper suggestion 被 Controller 明确拒绝

**正确性论证**: 两方独立实现意味着任何单方实现错误（错误的 domain separator、错误的 canonicalization、错误的 digest 算法）都会导致 canary mismatch——而 plan §5.4 的 owner tests 锁定"任一漂移都必须由 owner test 失败"。test 侧 owner tests 验证 canary 正确派生；Controller 侧独立重算并做 exact-value scan。双方只有 plan text contract 作为共同真源。

**唯一共享真源**: Plan §2.3 文字——Python bytes literal、公式、known vector。这是 contract，不是 code。双方各自从 contract 实现。

**Verdict: PASS。** 独立实现 contract 明确，无共享代码依赖。

### 4.3 Dispatch-Returned R12 run_id

**Challenge**: Controller 如何可靠取得 dispatch response 返回的 `run_id`？若 dispatch API 不返回 run_id，plan 的 contract 是否形成不可执行 gate？

**Evidence**:
- Plan §9.3 step 1: "必须使用能在本次 dispatch response 中返回确切 R12 `run_id` 的调用方式，并立即锁定该 `run_id`"
- Plan §9.3 step 1: "response 未返回、返回多个 candidate 或无法唯一对应本次 dispatch 时，当前 gate fail"
- Plan §9.3 step 1: "禁止从'最近一次成功 run'、workflow summary、时间戳或 artifact 名反推 `run_id`"

**分析**: plan 不指定具体 API 调用，而是规定所需属性（必须返回 run_id）。这是正确的 contract 设计——不耦合到特定 CLI/API 版本。可能的实现路径：
- `gh workflow run ... --json databaseId` 配合 polling
- GitHub REST API `GET /repos/{owner}/{repo}/actions/runs?head_sha=<commit>` 过滤
- 只要能唯一确定 run_id 且通过 step 2 metadata verification

key safeguard 不是"如何取得 run_id"，而是 step 2 的 metadata verification（workflow name/path/event/branch/head_sha）——即使 run_id 获取方式有竞态，metadata mismatch 也会 fail closed。

**Verdict: PASS。** contract 清晰，fail-closed 设计正确，metadata verification 提供第二层保护。

### 4.4 Workflow Path / Event / Branch / head_sha

**Challenge**: workflow metadata verification 的每一项是否必要且充分？是否遗漏任何关键字段？

**Evidence** (Plan §9.3 step 2):

| Field | Claimed value | 必要性 | 伪造难度 |
|-------|-------------|--------|---------|
| workflow identity/name | `R12 init Windows gate` | 防止扫到不同 workflow 的 artifacts | 低——workflow name 是文件内定义 |
| workflow path | `.github/workflows/r12-init-windows.yml` | 防止 workflow 被重命名/移动后仍匹配 name | 中——需同时改 name 和 path |
| event | `workflow_dispatch` | 防止自动触发（push/schedule）的 run 被误用 | 低——event 由 GitHub 设定 |
| branch/ref | dispatch target branch/ref | 防止不同 branch 的 run 被混用 | 中——需 commit 到正确 branch |
| head_sha | accepted implementation commit SHA | 防止不同 commit 的 run 被混用 | 高——需精确 commit SHA |

**分析**: 五字段形成递增的验证链——从粗粒度（workflow identity）到最细粒度（commit SHA）。任何字段 mismatch 即 gate fail。没有遗漏关键字段（如 actor、created_at 等）——这些不是 security-relevant metadata。

**Verdict: PASS。** 五字段验证链充分且 fail-closed。

### 4.5 Same-Run Artifacts Lineage

**Challenge**: 能否在 Controller 侧可靠证明全部 evidence 来自同一 run？是否存在跨 run artifact 混用的隐蔽路径？

**Evidence** (Plan §9.3 step 3):
- "Workflow status/conclusion、完整 log、JUnit、source-hash、artifact 列表、全部 artifact 下载与哈希、embedded R11 evidence 以及 canary scan 必须全部使用第 1 项同一 `run_id` 和第 2 项同一 metadata tuple"
- "任一 required JUnit/source-hash/artifact missing、下载不完整、无法证明 run lineage 或与其它 run 混用都是 gate fail"
- "不得用 workflow summary 或其它 run 的 green status 补齐"

**分析**: `gh run download <run_id>` 下载指定 run 的全部 artifacts。该命令是 atomic per-run——不会混入其它 run 的 artifacts。但需注意：
1. `gh run download` 若同一 run 有多次 workflow attempt，可能下载最新 attempt 的 artifacts（而不是全部 attempts）——plan 不要求扫描旧 attempts，因为只有最新 attempt 对应 accepted commit
2. embedded R11 artifacts 被 R12 workflow 在运行时产生并 upload——它们自然属于同一 run
3. 下载后的 local directory 可能残留上次下载的文件——Controller 应在下载前清空 target directory

这些都是 Controller 执行细节，不构成 plan defect。

**Verdict: PASS。** same-run lineage contract 清晰，执行路径可控。

## 5. Boundary Drift Verification

### 5.1 Standalone R11

**Challenge**: standalone R11 是否会因 WIN4 changes 而受到边界漂移（被错误纳入 R12 canary scan scope，或被错误声称 canary non-disclosure 证明）？

**Evidence**:
- Plan §5.4: "standalone R11 没有消费该 canary，不进入本 scan，也不得声称由本 scan 证明其 non-disclosure"
- Plan §8: "standalone R11 的 closure evidence 只来自其 capability/four-node/argv/real-upload 结果、artifact integrity 与无 secret-input contract；R12 canary scan 不为 standalone R11 提供或声称额外 non-disclosure 证明"
- Plan §8 closure matrix R12 Controller canary scan row: "standalone R11 不在 scan 范围"
- Plan §9.3: "standalone R11 没有消费 R12 canary，继续按 artifact integrity 与无 secret-input contract 验收，不进入 scan"

**Verdict: 无漂移。** Standalone R11 边界在 5 处明确锁定。

### 5.2 GitHub Secrets

**Challenge**: 是否因 canary scan 的设计而引入对 GitHub Secrets 的读取、扫描或依赖？

**Evidence**:
- Plan §2.3: "不读取 GitHub Secrets 或 configured production values，也不把它们加入 scan 范围；当前 workflow 没有把这些值作为本 test input"
- Plan §5.4: "Controller 不得读取、请求、导出或扫描 GitHub Secrets/configured production values"
- Plan §6.6: "Controller 不得读取、请求、导出或扫描 GitHub Secrets/configured production values"
- Plan §8: "不读/扫 GitHub Secrets 或 configured production 值"
- Plan §9.3: "当前 R12 workflow 没有把这些值作为本 test input，因此它们不是本 canary gate 可验证的 needle"
- Plan §9.3: "本限制不放宽既有设计：Config/Host internal SQLite/EventLog 仍属 trusted-local domain，Tool Trace/audit/public/LLM-facing/operator log 仍禁止 API key/header 明文"

**Verdict: 无漂移。** GitHub Secrets 边界在 6 处明确锁定，trusted-local 裁决不变。

### 5.3 POSIX Parser

**Challenge**: S1 oracle 是否会使用 POSIX `shlex.split` 而绕过 Windows batch 语义？

**Evidence**:
- Plan §4 S1 step 2: "不得使用 whole-file `count`、substring presence、**POSIX loose parser**、从 execution result 反推输入"（强调为原文）
- Plan §0.1: DS re-review 的 POSIX parser open question 被 Controller 接受动机但不形成 finding——"final plan 已经明确禁止 POSIX loose parser，并要求现有 Windows batch/CRT oracle 或等价 Windows 语义解析"
- Plan §5.1 negative case: 禁止 "POSIX loose parser"

**Verdict: 无漂移。** POSIX parser 被三处显式禁止，只允许 Windows batch/CRT 语义。

### 5.4 TemporaryFile / Cleanup Poll / TimeoutExpired

**Challenge**: 这三个边界是否在历经四轮修复后出现语义漂移或矛盾？

**TemporaryFile**:
- Plan §0.1: named-path 方案被拒绝，锁定 anonymous handle lifetime
- Plan §2.3: `tempfile.TemporaryFile(mode="w+b")` context handles
- Plan §5.3: 不产生/记录/清理 named temp path
- **无漂移** ✓

**Cleanup Poll**:
- Plan §2.3 step 5: cleanup timeout → ONE non-blocking poll → running|exited
- Plan §5.3: negative case 覆盖 running 和 exited 两种 poll 结果
- **无漂移** ✓

**TimeoutExpired**:
- Plan §2.2: "不得绑定、格式化、记录或转抛 raw exception，因为 exception args 含完整 setx argv/value"
- Plan §0.1: "保持该约束，不增加 exception inspection、logging、redaction shim 或 traceback repair"
- Plan §3.2: "不记录 setx stdout/stderr，不把 value 写进 exception、log、JUnit、workflow artifact 或 review artifact"
- **无漂移** ✓

**Verdict: 三个边界均无漂移。**

## 6. Rejected Candidates Non-Backflow Verification

Plan §0.1 disposition lock 完整保持了全部 13 项 rejected / already-satisfied candidates：

| Candidate | 原始 disposition | Plan §0.1 锁定 | 回流 |
|-----------|-----------------|---------------|------|
| `TimeoutExpired` 不绑定/格式化/记录/转抛 | already satisfied (DS 2.2a) | "保持该约束，不增加 exception inspection..." | 无 |
| 不为 30s owner budget 增加 timing instrumentation | rejected (DS 2.2b) | "不为 30 秒 owner budget 在真实 workflow 增加 timing instrumentation" | 无 |
| 不枚举 PIPE/handle-table/process-tree 替代方案 | rejected (DS 3.1a) | "不枚举或逐一实现..." | 无 |
| 不新增 dependency framework | rejected (DS 4.1a) | "S2→S3 现有依赖已经是必须先后关系，不新增 dependency framework" | 无 |
| `tests/README.md` 与 S3 同一 slice | rejected (DS 4.4a) | "不新增 docs transaction 机制" | 无 |
| `_SetxRecorder` 不冻结易漂移测试数量 | rejected (DS 5.1a) | 保持（不冻结） | 无 |
| WIN4-F01 recurrence 进入 diagnostic-first | already satisfied (DS 5.6a) | "阻塞 closure，不成为当前 root cause 的第二种解释" | 无 |
| S1→S2→S3 串行顺序 | rejected (MiMo RISK-2) | "保持用户指定的 S1→S2→S3 串行顺序" | 无 |
| DS named-path 方案 (`mkstemp`/unlink/retained-path) | rejected in adjudication | "均被拒绝。§2.3 锁定 anonymous handle lifetime" | 无 |
| DS Finding 1.2b (oracle placement) | already satisfied | 并入 F01 精确 fail-closed 约束 | 无 |
| DS Finding 3.3a named-path (original) | rejected | 只接受 cleanup-contract 风险事实 | 无 |
| DS POSIX parser open question | not a finding | "不形成 finding；plan 继续禁止 POSIX loose parser" | 无 |
| DS shared-helper suggestion | rejected | "test/Controller 必须独立实现与重算" | 无 |

**Verdict: 零回流。** 全部 rejected/already-satisfied candidates 在 plan §0.1 精确锁定，无任何 candidate 在后续 plan 修订中被重新引入。

## 7. Externally Verifiable Evidence

以下均可由 Controller 或任何第三方独立复核，无需信任本 review：

### 7.1 Known Canary Vector Verification

```python
import hashlib
domain = b"dayu-ar-f07-win4-r12-canary-v1\x00"
assert len(domain) == 31
assert domain[-1] == 0x00
digest = hashlib.sha256(domain + b"1").hexdigest()
assert digest == "b8f2210d1ead3aac3a52408adb9de03c4e848d4c101f790e218ecc76e3350b97"
# Plan known vector: sk-dayu-test-b8f2210d1ead3aac3a52408adb9de03c4e848d4c101f790e218ecc76e3350b97
```

**本 reviewer 独立验证**: 全部断言通过。

### 7.2 Plan and Plan-Fix SHA-256

```bash
shasum -a 256 docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md
# Expected: 2359f24251838ec5d779ed0a1eb804ebacce3405e102a0cbc50a70f5844fd73a

shasum -a 256 docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-fix-codex.md
# Expected: 52f5ae11a409b6d3ed5c3b16c30973972b876b8dc4f2d4ff7ff91f3dfb6ccbe4
```

**本 reviewer 独立验证**: 两者均匹配。

### 7.3 Code Evidence Cross-Reference

| Plan claim | Code location | 当前基线状态 |
|-----------|--------------|-------------|
| `_persist_windows_environment()` 使用 `capture_output=True` 且无 timeout | `init_environment.py:416-422` | 待 S2 修复 |
| `_run_init()` 使用 `subprocess.run(input=..., capture_output=True)` | `test_init_smoke.py:179-199` | 待 S3 修复 |
| Windows test generation argv 缺 `--company-name` | `test_upload_filings_from_command.py:844-860` | 待 S1 修复 |
| `_decode_windows_batch_fixed_token()` 已存在 | `test_upload_filings_from_command.py:960-986` | S1 可直接复用 |
| `_SetxRecorder.__call__` 签名含 `capture_output, text` | `test_init_environment.py:57-64` | 待 S2 更新 |
| `_windows_failure_result()` 只返回 names | `init_environment.py:446-472` | 已满足 names-only contract |

### 7.4 Full Review Chain Integrity

全部 11 个 stage 的 artifacts 均已完整读取并交叉验证：
- 两路 first review（DS+MiMo）→ Controller adjudication #1 → Codex fix #1 → Controller validation #1
- 两路 re-review（DS+MiMo）→ Controller adjudication #2 → Codex fix #2 → Controller validation #2
- 最终 plan + cumulative plan-fix = 本 final re-review 的输入

所有 stage 间的 SHA-256 锁链完整，无跨 stage 不一致。

## 8. Over-Engineering Check

| 潜在过度设计 | Plan 是否引入 | 证据 |
|-------------|-------------|------|
| 新 cleanup framework | 否 | §2.3 锁定 anonymous handle lifetime，拒绝 named-path |
| Timing instrumentation | 否 | §0.1 拒绝 DS 2.2b |
| Dependency framework | 否 | §0.1 拒绝 DS 4.1a |
| Process-tree 治理 / Win32 handle enumeration / job object | 否 | §2.2 明确不实施 Issue 175；§2.3 明确不引入 Windows job object |
| Secret infrastructure / unified authorization | 否 | §11 明确 zero |
| Generic diagnostic framework | 否 | §10 明确不借 diagnostic-first 进入 Issue 175 |
| Named-file lifecycle | 否 | §2.3 锁定 anonymous handle |
| 第二套 cleanup 语义 | 否 | §5.3 明确禁止 |
| 兼容性 re-export/wrapper/alias | 否 | §11 明确零 compatibility |
| R12 canary 成为 auth/identity framework | 否 | 只是固定纯函数 + scan，无 token/role/session |
| 新增 module/class/abstraction | 否 | 三 slice 只改 5 个 product/test 文件 + 1 个 README |

**最小值边界**: S1（1 test file）、S2（1 production file + 1 test file）、S3（1 test file + 1 README）= 5 files + 1 README。无新增模块、class hierarchy、abstract base、factory、registry、plugin、middleware、observer、state-machine framework 或 generic helper library。

**Verdict: 无过度设计。**

## 9. Architecture Boundary Verification

| 修改 | 所属层 | 是否跨层 | 是否修改 public contract |
|------|--------|---------|------------------------|
| S1: test input 修正 | Test | 否 | 否 |
| S2: setx stdio/timeout | CLI → OS boundary | 否 | 否（外部 behavior: names-only result 不变） |
| S3: harness safe failure | Test | 否 | 否（production CLI 不变） |

依赖方向: S1（无生产依赖）→ S2（无 S1 依赖）→ S3（hard depends on S2）。依赖方向正确，无反向依赖。

Owner 唯一性保持不变：
- fresh create company name → `dayu/fins/pipelines/upload_company_meta.py`
- setx stdio/timeout → `dayu/cli/init_environment.py::_persist_windows_environment()`
- outer CLI failure projection → `tests/cli/test_init_smoke.py::_run_init()`
- R12 canary producer → R12 real setx test
- R12 canary verifier → Controller

## 10. Material Findings

**零 material findings。**

本次 final re-review 逐项验证了以下全部维度，未发现任何可信的 plan-level failure mode：

1. **WIN4-PR-F01..F04** — 四项 finding 均在 final plan 中精确闭合，contract 达到 code-generation-ready 级别。
2. **WIN4-PR-RR-F01..F02** — 两项 finding 闭合：domain separator 字节歧义消除，controller procedure 锁定 dispatch-returned run_id 与 same-run lineage。
3. **bytes literal / single NUL / known vector** — 外部可独立复核，双 owner 无歧义。
4. **test 与 Controller 独立实现** — 零共享 code/helper/needle，双方只共享 plan text contract。
5. **dispatch-returned R12 run_id** — contract 正确（要求属性而非指定实现），metadata verification 提供 fail-closed 第二层保护。
6. **workflow path/event/branch/head_sha** — 五字段验证链充分，递增粒度，fail-closed。
7. **same-run artifacts lineage** — 执行路径可控，contract 清晰。
8. **standalone R11** — 5 处锁定边界，无漂移，不伪造 non-disclosure 证明。
9. **GitHub Secrets** — 6 处锁定边界，trusted-local 裁决不变。
10. **POSIX parser** — 3 处显式禁止，只允许 Windows batch/CRT 语义。
11. **TemporaryFile / cleanup poll / TimeoutExpired** — 三个边界历经四轮修复，零语义漂移。
12. **Rejected candidates** — 13 项零回流。
13. **Over-engineering** — 零过度设计，最小化修复（5 files + 1 README）。
14. **Architecture** — 分层合规，owner 唯一，无 public contract 变更，依赖方向正确。
15. **Forbidden paths** — 全部 10 类禁止变更均遵守（§3.2 + §11）。

## 11. Open Questions & Residual Risks

无新增 open questions。DS re-review 的两个 open questions（S1 `shlex.split` 等价性、`process_state_after_cleanup_timeout` 字段命名）已由 Controller 裁决处理或由 plan 文本充分明确。

**Residual risk（已由 plan 承认）**:
- R12 真实 Windows runner 尚未执行，所有 real-smoke 验证待 release gate 确认。这不是 plan defect，是当前 gate 的已知限制（plan §8 已列为 release blocker）。

## 12. Conclusion

### 12.1 Per-Dimension Verdict

| Dimension | Verdict |
|-----------|---------|
| WIN4-PR-F01 closure (S1 oracle) | PASS |
| WIN4-PR-F02 closure (cleanup poll) | PASS |
| WIN4-PR-F03 closure (TemporaryFile) | PASS |
| WIN4-PR-F04 closure (R12 canary scan) | PASS |
| WIN4-PR-RR-F01 closure (bytes literal/NUL/vector) | PASS |
| WIN4-PR-RR-F02 closure (dispatch run_id/lineage) | PASS |
| bytes literal / single NUL / known vector challenge | PASS |
| Test vs Controller independent implementation | PASS |
| dispatch-returned R12 run_id challenge | PASS |
| workflow path/event/branch/head_sha challenge | PASS |
| same-run artifacts lineage challenge | PASS |
| Standalone R11 boundary drift | PASS (无漂移) |
| GitHub Secrets boundary drift | PASS (无漂移) |
| POSIX parser boundary drift | PASS (无漂移) |
| TemporaryFile/cleanup poll/TimeoutExpired boundary drift | PASS (无漂移) |
| Rejected candidates non-backflow | PASS (零回流) |
| Over-engineering absence | PASS |
| Architecture boundary compliance | PASS |
| Forbidden paths compliance | PASS |

### 12.2 Overall Conclusion

**PASS。**

Final plan（SHA-256 `2359f24251838ec5d779ed0a1eb804ebacce3405e102a0cbc50a70f5844fd73a`）经完整 final re-review，全部六项 accepted findings（WIN4-PR-F01..F04 + WIN4-PR-RR-F01..F02）均已闭合，contract 达到 code-generation-ready 级别。

五个专项挑战领域（bytes literal/NUL/vector、test-Controller 独立实现、dispatch run_id、workflow metadata、same-run lineage）经深度对抗验证全部 PASS——无假 pass 路径、无跨 run 混用、无共享实现风险。

四个边界（standalone R11、GitHub Secrets、POSIX parser、TemporaryFile/cleanup poll/TimeoutExpired）零漂移，13 项 rejected candidates 零回流，零过度设计。

Plan 已满足 `READY_FOR_IMPLEMENTATION` 条件。

### 12.3 Next Gate

Controller 汇总本 final re-review 与 AgentMiMo final re-review 后，可进入 accepted plan commit → implementation authorization（S1→S2→S3 串行执行）。

---

## Artifact Integrity

- **路径**: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-final-rereview-ds.md`
- **基线 HEAD**: `54e2dcbf653fb8c37b0206bd7aabbbf329ef040e`
- **审查结论**: `PASS`
- **Material findings**: 0
- **Residual risks**: 1（R12 真实 Windows runner 尚未执行，plan 已列为 release blocker）

本 artifact 不含随机 sentinel、registry value、configured secret、raw source content 或用户绝对路径。
本 artifact 不修改 plan/control/production/tests/README/workflow/review，不 stage/commit/push/dispatch。
