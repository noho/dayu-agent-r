# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4 Corrected Aggregate Deepreview（AgentDS 第二路）

## Verdict

**PASS / 0 new finding / 0 backflow finding / 0 blocker / 0 open question**

本 review 是既有 `WU-SEMANTIC-OWNERSHIP-01` umbrella WU 的 AR-F07 WIN4 corrected aggregate 第二路完整 deepreview（AgentDS），不是新 WU。独立从零复核旧 WIN4 S1/S2 全部 implementation、RF01 test correction、真实 Windows evidence、全链 Controller adjudication、全部 accepted-commit validation，以及六个 product/test/README paths 的完整 aggregate 组合行为。

## Scope

- Mode: Current Changes Mode（corrected aggregate deepreview）
- Umbrella: `WU-SEMANTIC-OWNERSHIP-01`
- Continuation: `AR-F07` WIN4 real-Windows S1+S2+RF01 corrected aggregate
- Branch: `phaseflow/host-issues-control`
- Aggregate base: `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9`
- Current HEAD: `de68672b803c4e355d2a18b0fbc2890497053230`
- Output file: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-corrected-aggregate-deepreview-ds.md`
- Review date/time: 2026-07-20T10:26:43+08:00
- Included scope（exact six product/test/README paths）:
  - `README.md`
  - `dayu/cli/commands/init.py`
  - `tests/README.md`
  - `tests/cli/test_init_command.py`
  - `tests/cli/test_prompt_command.py`
  - `tests/cli/test_upload_filings_from_command.py`
- Excluded scope: 全部 control/review/plan artifacts、`.github/workflows/`、`dayu/fins/`、`dayu/cli/init_environment.py`、`tests/cli/test_init_smoke.py`、`dayu/cli/output.py` 及其他非 allowlist 路径。Protected paths 相对 base 的 diff 经 `git diff --stat` 确认为零。
- Parallel review coverage: 无。本 review 是 Controller 授权的第二路独立完整 aggregate deepreview（AgentDS），与 AgentMiMo 第一路并行独立执行。
- Staged/worktree: clean（`git status --short` 零输出）。

## Governance Inputs

本 review 完整读取以下治理输入：

- `AGENTS.md` / `CLAUDE.md`（项目指令与架构硬约束）
- `docs/phaseflow-umbrella-optimization-control.md`（umbrella 总控约束）
- `docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`（§13 amended plan，含 RF01 correction）
- WIN4-RW S1 全部 review/fix/rereview/accepted-commit artifacts（Controller 已全部闭合）
- WIN4-RW S2 全部 implementation/plan-drift/review/fix/rereview/accepted-commit artifacts（Controller 已全部闭合）
- WIN4-RW 第一次 aggregate deepreview chain（DS + MiMo + Controller adjudication）
- WIN4-RW aggregate re-review chain（DS + MiMo + Controller adjudication）
- Fresh Windows evidence Controller adjudication（RF01 发现与裁决）
- RF01 plan correction 全链（plan review/fix/rereview + Controller adjudication）
- RF01 test oracle implementation 全链（code review/fix/rereview + Controller adjudication）
- RF01 accepted-commit Controller validation
- S1 accepted commit: `9eeb467ab45ca945882234026ef95301cd5b609d`
- S2 accepted commit: `40b461410da48333670e0ca54385aa0d9dc4c79a`
- RF01 accepted implementation commit: `329068411a1669730c0a5ec4ed3bde0b0ed9b8e5`

本 review 不重新裁决已闭合的 S1、S2、RF01 独立 review 链 findings；只检查六路径 corrected aggregate 中是否存在交叉回归、语义所有权漂移、过度耦合、未覆盖边界、deferred scope 渗漏或 review backflow。

## Immutable State Verification

| Item | Expected | Fresh Actual | Status |
|------|----------|-------------|--------|
| Aggregate base | `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9` | `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9` | ✓ MATCH |
| Current HEAD | `de68672b803c4e355d2a18b0fbc2890497053230` | `de68672b803c4e355d2a18b0fbc2890497053230` | ✓ MATCH |
| Six-path aggregate binary diff SHA-256 | `9dfe8f046e49c9666d0348cb5c6dec4f70e58320f5954dc68e8b4d843d112fdd` | `9dfe8f046e49c9666d0348cb5c6dec4f70e58320f5954dc68e8b4d843d112fdd` | ✓ MATCH |
| Sorted path-list SHA-256 (`LC_ALL=C sort`) | `c63b3b4e3153be8bcc814d40f9fb2aeb8a0e478f621302378502e3d0c31138cf` | `c63b3b4e3153be8bcc814d40f9fb2aeb8a0e478f621302378502e3d0c31138cf` | ✓ MATCH |
| Latest accepted implementation | `329068411a1669730c0a5ec4ed3bde0b0ed9b8e5` | `329068411a1669730c0a5ec4ed3bde0b0ed9b8e5` | ✓ MATCH |
| S1 accepted commit | `9eeb467ab45ca945882234026ef95301cd5b609d` | `9eeb467ab45ca945882234026ef95301cd5b609d` | ✓ MATCH |
| S2 accepted commit | `40b461410da48333670e0ca54385aa0d9dc4c79a` | `40b461410da48333670e0ca54385aa0d9dc4c79a` | ✓ MATCH |
| Staged tree | empty | empty | ✓ PASS |
| `git diff --check` | PASS | PASS | ✓ PASS |

### Per-file content SHA-256

| File | SHA-256 | Previous Aggregate (d4e092d1) | Delta |
|------|---------|-------------------------------|-------|
| `README.md` | `7cf41485076a96ba80f9ebeb7969c951f18e7478fe789db7a74adc8fde274cce` | `7cf41485...` | 零 diff |
| `dayu/cli/commands/init.py` | `b0601a962034d322f82edef2fbab7ce49e4b4a212b55bd81bbf276823d97e4c4` | `b0601a96...` | 零 diff |
| `tests/README.md` | `c5de013136b2c816f26d685511921dac9852775df7c0afed0352e2061d1b25fe` | `c5de0131...` | 零 diff |
| `tests/cli/test_init_command.py` | `1541fb84398339b202c1ae0f623e85f85c89bd4adc411083183456197bf9e5f8` | `1541fb84...` | 零 diff |
| `tests/cli/test_prompt_command.py` | `8b9f7df20ebcd36f71c9639e52b42e22d8f8b3511ed44d1f75f918a5ee0ec60a` | `8b9f7df2...` | 零 diff |
| `tests/cli/test_upload_filings_from_command.py` | `3827b569fea759e6feaaba657b27a41a3303bde787d784e52677dd49a69ad110` | `71855b78...` | **RF01 fix** |

前五个文件与第一次 aggregate deepreview (HEAD `d4e092d1`) 完全一致——S1/S2 payload 未被 RF01 改动。唯一变化是 `test_upload_filings_from_command.py` 中的 RF01 test correction（17 lines changed，仅限 `test_windows_generated_script_runs_real_cli_into_temp_storage` 函数内的 snapshot assertion block）。

### 六路径间 delta 归因

从 `d4e092d1`（第一次 aggregate HEAD）到 `de68672b`（当前 HEAD），唯一的 code delta 是 commit `32906841`:

```
git diff d4e092d1..de68672b --stat -- tests/cli/test_upload_filings_from_command.py
 1 file changed, 12 insertions(+), 5 deletions(-)
```

其余 34 个 changed files 全部是 `docs/` 下的 control/review/plan/adjudication/evidence artifacts，不属 product/test/README payload。

## Fresh Verification Results

| Check | Command | Result |
|-------|---------|--------|
| Focused CLI tests (3 target files) | `pytest tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_upload_filings_from_command.py -x -q` | `106 passed, 2 skipped, 3 warnings` |
| Full CLI tests | `pytest tests/cli/ -q` | `552 passed, 7 skipped, 3 warnings` |
| init.py coverage | `pytest tests/cli/test_init_command.py --cov=dayu.cli.commands.init` | `92%` (311 statements, 26 missed; ≥80% threshold) |
| Full pyright (4 target Python files) | `pyright dayu/cli/commands/init.py tests/cli/test_*.py` | `0 errors, 0 warnings, 0 informations` |
| Scoped Ruff (4 Python files) | `ruff check dayu/cli/commands/init.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_upload_filings_from_command.py` | `All checks passed!` |
| `git diff --check` | `git diff --check base..HEAD -- <six paths>` | PASS |
| Staged tree | `git diff --cached --stat` | empty |

## Findings

### 0. 未发现实质性问题

经完整六路径 corrected aggregate deepreview，在以下全部 10 个审查维度及附加交叉验证中均未发现 material finding：

---

#### 1. WIN4-RW-S1: process-exit + public storage published-fact success owner（含 RF01 correction）

- **入口/函数**: `test_windows_generated_script_runs_real_cli_into_temp_storage`
- **文件**: `tests/cli/test_upload_filings_from_command.py:912-1041`
- **审查结论**: PASS，零 finding

**直接证据链**：

1. **旧 display assertion 已彻底删除**：`assert "Fins result" in execution.stdout` 在 S1 中删除。display-added-diff scan（`rg 'Fins result|Fins summary|Fins progress|Fins succeeded|Fins failure|Fins cancelled|execution\.(stdout|stderr).*in '` over diff-added lines）零命中。未新增任何 stdout/stderr display text、prefix、substring、regex 或 parser 断言。

2. **Process exit 仍为第一道真源**：`assert execution.returncode == 0, execution.stderr`（line 981）保留。stderr 仅作断言失败诊断，不作业务成功判断。

3. **Public storage typed facts**（lines 982-1017）：
   - `FsCompanyMetaRepository(storage).get_company_meta("AAPL")` → exact ticker + company name（line 982-984）
   - `FsSourceDocumentRepository(storage).list_source_document_ids("AAPL", SourceKind.FILING)` → 唯一性断言（lines 985-990）
   - `read_source_snapshot(..., materialize_files=False)` 在 `with` context manager 内消费（lines 992-1017）

4. **RF01 correction: primary vs raw-source ownership 正确分离**（lines 1003-1017）：
   ```python
   # primary 归属 Fins owner —— 按 snapshot.primary_filename 精确过滤
   primary_descriptors = tuple(
       descriptor for descriptor in descriptors
       if descriptor.name == snapshot.primary_filename
   )
   assert len(primary_descriptors) == 1  # zero/multiple → fail closed

   # raw source 归属 test fixture —— 按 source_path.name 独立过滤
   raw_source_descriptors = tuple(
       descriptor for descriptor in descriptors
       if descriptor.name == source_path.name
   )
   assert len(raw_source_descriptors) == 1  # zero/multiple → fail closed
   raw_source_descriptor = raw_source_descriptors[0]
   assert raw_source_descriptor.sha256 is not None
   assert raw_source_descriptor.sha256 == hashlib.sha256(fixture).hexdigest()
   ```

   **Owner boundary 分析**：
   - `snapshot.primary_filename` → Fins upload owner 选择 primary document（当前为 Docling JSON，未来可变）。Test 不硬编码 primary 文件名，不假设 primary == raw source。
   - `source_path.name` → test fixture 拥有 raw source identity。Test 独立证明 raw source 在 published descriptors 中唯一存在。
   - `raw_source_descriptor.sha256 == hashlib.sha256(fixture).hexdigest()` → 内容完整性证明，不依赖文件名或 display text。
   - 两个 filter 的 `len == 1` 断言对 zero/multiple hits 均 fail closed。
   - Test 不从 private meta、physical tree、`rglob` 或 raw JSON 反推 publication facts。

5. **Physical integrity**（line 1018-1020）：`portfolio/` 下 `rglob` 保留为 physical artifact count，不承担业务 success 语义。

6. **Company-name pre-execution oracle**（line 967-970）：`_assert_single_windows_upload_company_name()` 逐 token 证明 exact one `Apple Inc.`，comment/零条/多条 fail closed，未修改。

7. **New imports 全部来自 public contract**：`SourceKind`（`dayu.fins.domain.enums`）、`FsCompanyMetaRepository` 与 `FsSourceDocumentRepository`（`dayu.fins.storage`）均为既有 Fins public export，CLI test 只消费稳定 public contract。

8. **Fins production code 零 diff**：`git diff --stat base..HEAD -- dayu/fins/` 为空，确认未修改 Fins owner contract。

9. **`dayu/cli/output.py` 零 diff**：确认未修改 CLI output owner。

10. **POSIX test display assertion**（line 842 `assert execution.stdout.count("Fins succeeded") == 2`）：该行在 `test_upload_filings_from_creates_posix_shell_script` 函数中（使用 `/bin/sh`），系 POSIX-only pre-existing 测试，不在 WIN4 S1/S2/RF01 的 scope 内，未被我方修改。作为观察记录，不是 finding。

---

#### 2. WIN4-RW-S2: stdin capability secret-input owner 组合行为

- **入口/函数**: `_read_secret_input` → `_collect_environment_persistence_plan`
- **文件**: `dayu/cli/commands/init.py:468-543`
- **审查结论**: PASS，零 finding（与第一次 aggregate 完全一致，未被 RF01 改动）

直接证据与第一次 aggregate DS deepreview §1.2 完全一致：

1. Capability 分流以 `sys.stdin.isatty()` 为唯一判断条件，平台中立。
2. TTY 路径 → `getpass.getpass(prompt)`，line 480 唯一命中点。
3. Redirected 路径 → `sys.stderr.write(prompt)` + `sys.stderr.flush()` + `sys.stdin.readline()` 一次。
4. Line ending 处理：LF→移除 `\n`；CRLF→先 `\n` 再 `\r`；bare CR→不移除保留 trailing `\r`。
5. EOF 收敛：TTY `EOFError` 与 redirected `readline() == ""` 均转为同一 value-free `CliInitOperationError("secret input ended before completion")`。
6. `KeyboardInterrupt` 不捕获、不改写，由 CLI owner 映射为 exit 130。
7. Required 空行 fail closed；optional 空行 skip。
8. Forbidden patterns scan 全部零命中。
9. `init.py` 相对 base 零 diff（SHA `b0601a96...` 与第一次 aggregate 一致）。

---

#### 3. RF01 Test Correction 与 S1/S2 组合行为

- **审查结论**: PASS，零 finding

**组合分析**：

| 维度 | S1 (test_upload) | S2 (init + secret input) | RF01 (upload oracle fix) | 交叉影响 |
|------|------------------|--------------------------|--------------------------|---------|
| 文件 | `test_upload_filings_from_command.py` | `init.py`, `test_init_command.py`, `test_prompt_command.py` | `test_upload_filings_from_command.py`（同 S1 文件，同函数） | 零新增跨文件依赖 |
| Owner | OS process exit + Fins public storage | stdin capability + secret value lifecycle | primary/raw-source descriptor ownership | 独立 |
| 生产代码改动 | 无 | `init.py` `_read_secret_input()` 及其 2 个 call sites | 无 | 无交叉 |
| Import 关系 | `dayu.fins.storage`, `dayu.fins.domain.enums` | `sys`, `getpass` | `hashlib`（新增，标准库） | 零新增跨模块 import |
| Semantic owner | Fins → public repository contracts | CLI → stdin capability | Fins → primary_filename; test fixture → raw source name | 清晰独立 |

**关键验证**：RF01 correction 仅修改了 `test_windows_generated_script_runs_real_cli_into_temp_storage` 函数内的 assertion block（同一个 `with` 块）。它不引入新的 import 链（`hashlib` 已在同文件 line 9 导入）、不创建新 helper、不改变函数签名、不修改 `_assert_single_windows_upload_company_name`、不改变 subprocess 调用参数、不改变 oracle artifact 结构。

RF01 与 S1 在同一函数内共存但语义独立：S1 建立了 process exit + public storage facts 的真源链，RF01 修正了该链中 primary/raw-source descriptor 的 owner 归属。两者不互相覆盖、不产生条件竞争、不引入 hidden dependency。

---

#### 4. R11/R12 Workflow 不变性

- **审查结论**: PASS，零 finding

`.github/workflows/r11-upload-script-windows.yml` 与 `.github/workflows/r12-init-windows.yml` 相对 base 零 diff（`git diff --stat` 确认）。两个 workflow 的现有 triggers、locked install、JUnit always-upload、test collection、argv/setx/redirected-handle/artifact/canary contract 均未改变。

---

#### 5. Storage Snapshot Lifetime

- **文件**: `tests/cli/test_upload_filings_from_command.py:992-1017`
- **审查结论**: PASS，零 finding

`read_source_snapshot(..., materialize_files=False)` 在 `with` context manager 内消费（lines 992-1017）。所有 snapshot 属性断言（ticker、document_id、source_kind、files、primary/raw-source descriptors、sha256）均在 `with` 块内执行。块后只有 `rglob("*")`（physical artifact count，line 1018-1020）和 oracle artifact 写入（lines 1022-1041），不访问 snapshot。CLI test 不重复增加 Fins close-after-use owner test。

---

#### 6. LLM/Public/Audit/Tool Trace Non-Disclosure

- **审查结论**: PASS，零 finding

1. Secret value 在以下输出通道中零命中：
   - stdout：`assert required_secret not in captured.out` / `assert optional_secret not in captured.out`（dynamic owner tests，非固定 blacklist）
   - stderr：`assert required_secret not in redirected_stderr.getvalue()` / `assert optional_secret not in redirected_stderr.getvalue()`
   - exception text：`assert raw_exception_value not in str(raised.value)`（EOF error）/ `assert raw_exception_value not in captured.err`
   - `_read_secret_input` 不把 secret 写回任何输出流

2. Config/Host internal SQLite/EventLog 仍属 trusted-local domain，本次 diff 不读取、不迁移、不重写、不扩大 durable secret 范围。

3. Tool Trace/audit/public/LLM-facing/operator log 继续禁止 API key/header 明文；本次 diff 不创建新的 projection 或放宽既有裁决。

4. RF01 correction 不涉及任何 secret 处理——它只修改 public descriptor assertion，不读取、写入或投影任何 credential。

---

#### 7. SQLite/EventLog/Config Trusted-Local 裁决

- **审查结论**: PASS，零 finding

本次六路径 diff 不涉及 SQLite/EventLog 读写、config schema 变更或 durable secret 扩大。Config loader、Host durable state、LLM-facing projection 的 trusted-local 裁决不变。RF01 correction 不新增 durable store 或 projection。

---

#### 8. 无 Display 成功 Oracle

- **审查结论**: PASS，零 finding

旧 `assert "Fins result" in execution.stdout` 已删除。RF01 correction 不恢复、不新增、不替代任何 display assertion。业务成功仅由 `execution.returncode == 0` + public Fins storage typed facts 证明。display-add-diff scan 零命中。

POSIX test `test_upload_filings_from_creates_posix_shell_script` 中 line 842 的 `assert execution.stdout.count("Fins succeeded") == 2` 是 pre-existing POSIX-only assertion，不在本次 WIN4 scope 内，未被修改。

---

#### 9. 无 Production pytest/mock Fallback

- **审查结论**: PASS，零 finding

Production `_read_secret_input()` 仅使用标准库 `sys.stdin.isatty()`、`sys.stdin.readline()`、`sys.stderr.write()`/`flush()` 与 `getpass.getpass()`。无 test-only production seam、无 callback/factory/profile 参数、无 `hasattr`/`getattr` 探测、无 `sys.__stdin__` 模拟。

RF01 correction 仅修改 test file，不修改任何 production code。

---

#### 10. 无 Unified Secret/Authorization Infrastructure

- **审查结论**: PASS，零 finding

`_read_secret_input()` 只拥有 secret 值的读取和 EOF/interrupt 语义，不拥有 environment persistence、registry、Config、Host durable state、authorization 或通用 secret lifecycle。未新增 `dayu.runtime` secret helper、credential broker、zeroization 或 unified authorization infrastructure。deferred scan 在 changed paths 中零命中。

---

#### 11. Deferred Issues 142/151/175/177/178 与 Web/WeChat/render 无渗漏

- **审查结论**: PASS，零 finding

Deferred scan（`rg 'Issue 142|Issue 151|Issue 175|Issue 177|Issue 178|web_tools_storage_states'`）在全部 changed production/test paths/README 中零命中。`dayu/web/`、`dayu/wechat/`、`dayu/render/` 的删除已在 R11 独立完成，不在本次 WIN4 diff 范围。Web/WeChat/render placeholder 能力未恢复。

`init.py:353` 中的 "Web/WeChat/Host" 是 pre-existing 用户指令文本（提示停止活动进程），不是 deferred scope 渗漏。

---

#### 12. Semantic Ownership Drift

- **审查结论**: PASS，零 finding

逐一核验 semantic owner map（含 RF01 correction）：

| 语义 | 唯一 owner | 当前实现 | 漂移？ |
|------|-----------|---------|--------|
| secret input 能力分流 | `_read_secret_input()` | `sys.stdin.isatty()` 精确分流 | 无 |
| secret value EOF/interrupt | `_read_secret_input()` | 两种 EOF 收敛为同一 value-free error | 无 |
| environment persistence plan | `_collect_environment_persistence_plan()` | 两处复用 `_read_secret_input` | 无 |
| upload success oracle | OS process exit + Fins public storage repositories | `returncode == 0` + typed repository contracts | 无（已从 display consumer 迁走） |
| primary document selection | Fins upload owner (`docling_upload_service.py`) | `snapshot.primary_filename` → test 不硬编码、不假设 | **无（RF01 修正了此前 test 越权）** |
| raw source publication proof | snapshot descriptors (public) + fixture bytes (test) | `source_path.name` 精确过滤 + SHA-256 比对 | 无 |
| company-name requirement | Fins pipelines | Fins production 零 diff，fail-closed 不变 | 无 |
| company-name pre-execution oracle | `_assert_single_windows_upload_company_name` | 逐 token 证明 exact one `Apple Inc.` | 无 |

RF01 correction 的核心贡献是**修复了 test consumer 对 Fins primary-document 选择权的越权**——旧代码 `assert snapshot.primary_filename == source_path.name` 错误地把 test fixture 的 raw source basename 强加为 Fins primary。新代码正确承认 Fins owner 选择 primary，test 只消费 public snapshot 并独立证明 raw source 的存在与完整性。这是 semantic ownership 的**正向收束**，不是漂移。

---

#### 13. Overcoupling

- **审查结论**: PASS，零 finding

- `_TtySecretInput` 在两个 test 文件中独立定义——这是 §13.3 的明确要求（test-local 解耦），不是耦合。
- CLI test 只消费 Fins public storage contract，不依赖 Fins 内部实现、raw JSON、private core path 或 `rglob` 反推业务事实。
- 六路径之间无新增跨层依赖、无反向 import、无 shared mutable state、无过宽公共契约。
- RF01 correction 只修改单一 test 函数的 assertion block，不引入新 helper、新 import 链或跨文件共享。

---

#### 14. Cross-Slice State/Owner Handoff

- **审查结论**: PASS，零 finding

三条 owner boundary 在六路径中互相独立且正确接合：

```
S2 (secret input)
  │
  │ _read_secret_input() → capability 分流 → value → _collect_environment_persistence_plan()
  │                                                                                     │
  │                                              typed plan → persist → workspace config │
  │                                                                                     │
  └──────────────────────────────────────┬──────────────────────────────────────────────┘
                                         │
                                    CLI 进程
                                         │
                    ┌────────────────────┼────────────────────┐
                    │                    │                    │
              S1 (upload)         RF01 (oracle)       R11/R12 (workflow)
              process exit        descriptor           fresh dispatch
              + repo facts        owner fix            + evidence
```

无 handoff gap、无 orphan state、无重复真源。

---

#### 15. Adversarial Failure Pass

- **审查结论**: PASS，零 finding

逐一验证 adversarial failure scenarios：

| Scenario | Behavior | Evidence |
|----------|----------|----------|
| TTY `getpass` 返回空 → required | `CliInitOperationError`（caller 拒绝空值） | `init.py:511-512` |
| Redirected `readline` 返回 `"\n"` → required | `value = ""`（LF 移除后）→ `CliInitOperationError` | `init.py:489-490, 511-512` |
| Redirected `readline` 返回 `""`（EOF）| `CliInitOperationError("secret input ended before completion")`，value-free | `init.py:487-488` |
| TTY `getpass` 抛 `EOFError` | 同上 error，value-free；原始 exception 值不进入 error text | `init.py:481-482`；`test_secret_input_eof_paths_share_value_free_owner_error` |
| `KeyboardInterrupt`（TTY） | 原样透传 → CLI exit 130，不发布 workspace | `init.py:224-225`；`test_secret_input_keyboard_interrupt_maps_to_cli_exit_130[tty]` |
| `KeyboardInterrupt`（redirected） | 同上 | `test_secret_input_keyboard_interrupt_maps_to_cli_exit_130[redirected]` |
| Upload process returncode != 0 | `assert execution.returncode == 0` fail → stderr 诊断输出，不投影为 success | `test_upload:981` |
| Zero published documents | `len(document_ids) == 1` fail → AssertionError | `test_upload:990` |
| Multiple published documents | 同上 fail closed | `test_upload:990` |
| Zero primary descriptors | `len(primary_descriptors) == 1` fail | `test_upload:1008` |
| Zero raw source descriptors | `len(raw_source_descriptors) == 1` fail | `test_upload:1014` |
| Raw source SHA-256 mismatch | `assert raw_source_descriptor.sha256 == hashlib.sha256(fixture).hexdigest()` fail | `test_upload:1017` |
| `raw_source_descriptor.sha256 is None` | 显式 `is not None` 断言先于比较 | `test_upload:1016` |
| `snapshot.primary_filename` 与 `source_path.name` 相同（退化场景）| 两个独立 filter 各返回同一 descriptor；`len == 1` 各自通过 | 合法，不失败 |
| `snapshot.primary_filename` 不存在于 descriptors | `len(primary_descriptors) == 0` → fail | `test_upload:1008` |
| `source_path.name` 不存在于 descriptors | `len(raw_source_descriptors) == 0` → fail | `test_upload:1014` |

所有 adversary scenarios 均 fail closed，无静默成功路径。

---

#### 16. README Boundary

- **审查结论**: PASS，零 finding

- 根 `README.md`：S2 变更已在该文件 line 95-100 记录 TTY vs redirected stdin 行为差异。RF01 不改变用户可见行为，README 无需更新。
- `tests/README.md`：S1+S2 owner test 矩阵已记录（lines 66-69）。RF01 correction 是 S1 test 的 owner 收束（从错误 ownership 修正为正确 ownership），不改变测试矩阵描述中已记录的 public repository contract 验证方式。

---

#### 17. Security Mechanisms 保留

- **审查结论**: PASS，零 finding

现有 security mechanisms 全部保留：
- Config/Host SQLite/EventLog 仍属 trusted-local domain。
- Tool Trace/audit/public/LLM-facing/operator diagnostics 仍禁止 API key/header 明文。
- 无 unified tool authorization framework。
- RF01 correction 不涉及 security mechanism 变更。

---

#### 18. Correctness/Stability/Maintainability

- **审查结论**: PASS，零 finding

- **Correctness**: RF01 correction 正确地将 primary/raw-source descriptor ownership 分离，test 不再越权指定 Fins primary。SHA-256 内容完整性验证独立于文件名，提供了比旧 `== source_path.name` 更严格的正确性保证。
- **Stability**: 旧测试在 Fins 选择不同 primary document（如未来切换到其他格式）时会 false fail；新测试对 Fins primary 选择无假设，只验证 test fixture 的 raw source 确实被发布且内容完整。这是稳定性提升。
- **Maintainability**: primary/raw-source 分离后，两个 concern 独立演化。test fixture 改变 source filename 不会误触发 primary assertion；Fins 改变 primary 选择不会误触发 raw source assertion。

---

## Open Questions

无。

## Residual Risk

| # | Risk | Severity | Owner | Destination |
|---|------|----------|-------|-------------|
| R1 | Darwin owner tests 不能证明 CPython 3.11 Windows console 与 redirected OS handle 组合 | 中 | WIN4-RW §13.8 | fresh R11/R12 workflow_dispatch |
| R2 | caller-owned pipe/OS handle/process memory 按输入本质暂存 secret | 低 | 独立安全设计 WU | 不在本 WU scope |
| R3 | fresh R11 storage facts 或 R12 secret 读取后出现新 failure | 中 | Controller §13.9 diagnostic-first stop gate | 必须回 Controller |
| R4 | Full Ruff 142 项为 entry 既有 baseline | 信息 | 独立 Ruff cleanup WU | 本轮精确证明六元组零新增 |
| R5 | S1 `test_windows_generated_script_runs_real_cli_into_temp_storage` 与 `test_windows_cmd_script_round_trips_adversarial_argv_with_real_cmd` 被 `@pytest.mark.skipif(os.name != "nt")` 标记，本机 macOS 无法执行 | 中 | WIN4-RW | Fresh R11/R12 闭合 |
| R6 | `init.py` coverage 92%：interactive custom OpenAI 输入路径（line 427-436）与 catalog exception handlers（line 191-210）未被自动化 owner tests 覆盖 | 低 | CLI smoke / 独立 coverage WU | 由 CLI 真实 smoke 间接验证 |
| R7 | POSIX test `test_upload_filings_from_creates_posix_shell_script` line 842 仍使用 `execution.stdout.count("Fins succeeded")` display assertion | 信息 | 独立 sub-WU（若需要） | Pre-existing，不在 WIN4 scope |

## Finding Ledger

| Category | Count | Disposition |
|----------|-------|-------------|
| Accepted current aggregate findings | `0` | CLOSED |
| New findings | `0` | N/A |
| Backflow findings | `0` | N/A |
| Rejected candidates | `0` | N/A |
| Needs-evidence/local blocker | `0` | N/A |
| Design contradiction | `0` | N/A |
| Open question | `0` | N/A |
| Unclassified residual | `0` | N/A |

所有旧 review findings（第一次 aggregate DS/MiMo + re-review DS/MiMo + RF01 独立 code review/code re-review）均已闭合。当前 corrected aggregate 零新增、零回流。

## Evidence Summary

| 验证项 | 结果 |
|--------|------|
| Six-path aggregate binary diff SHA-256 | `9dfe8f046e49c9666d0348cb5c6dec4f70e58320f5954dc68e8b4d843d112fdd` ✓ |
| Sorted path-list SHA-256 (`LC_ALL=C sort`) | `c63b3b4e3153be8bcc814d40f9fb2aeb8a0e478f621302378502e3d0c31138cf` ✓ |
| Full CLI tests | `552 passed, 7 skipped` |
| Focused tests (3 target files) | `106 passed, 2 skipped` |
| init.py coverage | `92%` (≥80%) |
| Full pyright (4 target Python files) | `0 errors, 0 warnings, 0 informations` |
| Scoped Ruff (4 Python files) | `All checks passed!` |
| `git diff --check` | PASS |
| Staged tree | empty |
| display-added-diff scan (Windows test) | 零命中 |
| Forbidden patterns scan | 零命中 |
| Anti-patterns scan | 零命中 |
| Deferred issues scan | 零命中 |
| Protected paths diff | 零 diff |
| `getpass.getpass` call sites | 仅 TTY 分支 line 480 一次 |
| Workflow files diff | 零 diff |
| test_init_smoke.py diff | 零 diff |
| init_environment.py diff | 零 diff |
| dayu/cli/output.py diff | 零 diff |
| Fins production diff | 零 diff |
| RF01 primary ≠ raw source owner 分离 | 正确，fail-closed |
| RF01 SHA-256 内容完整性 | 独立于文件名，exact match |
| S1/S2/RF01 组合行为 | 无交叉回归、无 overcoupling、无 semantic ownership drift |

## Next Gate

Controller adjudication。若 Controller 接受本 aggregate deepreview PASS（与 AgentMiMo 并行 DS 路结果对齐），则：

1. 关闭 WIN4 corrected aggregate deepreview gate。
2. AgentCodex 处理全部 accepted aggregate findings（当前为零，仍需 zero-change record）。
3. Controller validation。
4. 双路完整 aggregate re-review（corrected）。
5. Accepted evidence commit。
6. 之后才可 push 与 fresh R11/R12 workflow_dispatch。

真实 Windows closure 必须等待 §13.8 fresh R11/R12 rerun，并由 Controller 按 §9.3 执行独立 same-run canary scan。Local PASS 不声称 cross-platform closure。

不得直接 remote、PR review、merge 或 closeout。

## Review Metadata

- Reviewer: AgentDS
- Review type: corrected aggregate deepreview（第二路，非新 WU）
- Review date: 2026-07-20
- Review time: 10:26:43 +0800
- Aggregate base: `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9`
- Current HEAD: `de68672b803c4e355d2a18b0fbc2890497053230`
- Six-path aggregate binary diff SHA-256: `9dfe8f046e49c9666d0348cb5c6dec4f70e58320f5954dc68e8b4d843d112fdd`
- Sorted path-list SHA-256: `c63b3b4e3153be8bcc814d40f9fb2aeb8a0e478f621302378502e3d0c31138cf`
- Latest accepted implementation: `329068411a1669730c0a5ec4ed3bde0b0ed9b8e5`
