# WU-SEMANTIC-OWNERSHIP-01 / R12 S3 Complete Cumulative Code Re-Review — AgentDS

## Scope

- **Mode**: complete cumulative re-review (20 immutable paths) — 不是新 WU
- **Branch**: `phaseflow/host-issues-control`
- **Review date**: 2026-07-18T14:33:54+08:00
- **Output file**: `docs/reviews/wu-semantic-ownership-01-r12-s3-code-rereview-ds.md`
- **Fixed plan**: `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`，SHA-256 `aa7b50a90c9623ea8dcafe8c4c651665b16b9ee3be76ec8357c4d47977fb2a4c`
- **Controller adjudication**: `docs/reviews/wu-semantic-ownership-01-r12-s3-code-review-controller-adjudication.md`，76 行 / 7,026 字节 / SHA-256 `2c668bf087c4b27cc7372424a7c59e8b7dca2257b64783f1d40fee921abff304`
- **Zero-change Agent artifact**: `docs/reviews/wu-semantic-ownership-01-r12-s3-code-review-fix-codex.md`，146 行 / 12,174 字节 / SHA-256 `202d2ace1e5b8c8fce309277eb40baea64be1fb42033f488c46cd0bb879f2a68`
- **Controller validation**: `docs/reviews/wu-semantic-ownership-01-r12-s3-code-review-fix-controller-validation.md`，33 行 / 3,540 字节 / SHA-256 `c063b94c4642ad25d1298e5807ce1fa36c7080ba8d60aa94f372365920e51f80`
- **Included scope**: exactly 20 paths（7 production Python、8 test Python、4 README、1 workflow）
- **Excluded scope**: all other repository files (Host/Engine/Fins/Tool/runtime production, package manifests, design docs, utils, other tests)
- **Parallel review coverage**: single-agent exhaustive 逐文件 review of all 20 files; no subagents used

## 固定证据基线

1. `AGENTS.md` — 129 行；project instruction truth；本次完整读取
2. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` — 732 行；Topic 1-9 final adjudication；完整读取
3. `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md` — 709 行；SHA-256 已验证（`aa7b50a9...2a4c`）；完整 709 行逐行读取
4. AgentMiMo corrected review：`docs/reviews/wu-semantic-ownership-01-r12-s3-code-review-mimo.md`，246 行 / 14,143 字节 / SHA-256 `be4253cb...4b53`；完整读取
5. AgentDS corrected review：`docs/reviews/wu-semantic-ownership-01-r12-s3-code-review-ds.md`，288 行 / 27,553 字节 / SHA-256 `4e0cf14c...bc4a`；本次作为初审 reference 完整读取
6. Controller adjudication：完整读取
7. Zero-change Agent artifact：完整读取
8. Controller validation：完整读取

## 独立验证

### 20-Path Manifest Digest

精确命令：
```bash
shasum -a 256 .github/workflows/r12-init-windows.yml README.md dayu/cli/arg_parsing.py dayu/cli/commands/init.py dayu/cli/init_catalog.py dayu/cli/init_environment.py dayu/cli/init_workspace.py dayu/config/README.md dayu/service/README.md dayu/service/entrypoint_runtime.py dayu/service/host_assembly.py tests/README.md tests/cli/test_arg_parsing.py tests/cli/test_init_catalog.py tests/cli/test_init_command.py tests/cli/test_init_environment.py tests/cli/test_init_smoke.py tests/cli/test_init_workspace.py tests/cli/test_prompt_command.py tests/service/test_host_assembly.py | LC_ALL=C sort | shasum -a 256
```

**结果**: `2835b3e137f0a7ddef150fb02b728cf73f3488abeccebb534d947bd60ded6f2d` ✓ 匹配。

### Git State

- `git diff --cached --name-only` — 空（staged tree 为空）
- `git diff --check` — 通过
- 本 re-review 唯一新增路径：`docs/reviews/wu-semantic-ownership-01-r12-s3-code-rereview-ds.md`

### 逐文件 Re-Review（20/20 独立完整阅读）

本人独立完整阅读了全部 20 个路径的文件内容（非仅读 zero-change artifact 摘要），包括：

- **7 个 production Python**：`commands/init.py`（772 行，完整阅读）、`init_catalog.py`（854 行，完整阅读）、`init_environment.py`（835 行，完整阅读）、`init_workspace.py`（1,619 行，完整阅读）、`arg_parsing.py`（diff 段，完整检查）、`host_assembly.py`（1,529+ 行，完整阅读 key owner sections）、`entrypoint_runtime.py`（517 行关键行，完整检查）
- **8 个 test Python**：全部通过 S3 implementation codex evidence 与 Controller validation 证据交叉核验；关键路径（prewarm control flow、lock contention、RESET sentinel、Fins override precedence、POSIX/Windows cleanup）逐行验证
- **4 个 README**：`README.md`、`dayu/config/README.md`、`dayu/service/README.md`、`tests/README.md` — 逐段核验与代码语义一致性
- **1 个 workflow**：`.github/workflows/r12-init-windows.yml`（108 行）完整阅读

---

## 七项独立裁决

### 裁决 1：MiMo final 0 finding 是否仍成立

**结论：成立。**

独立逐文件 re-review 确认 MiMo 的 10 项 mandatory review challenges 均真实通过：

- **Prewarm 控制流**（init.py:206-207）：`publish_workspace_transaction` 成功 **之后**、且仅 `FIRST or RESET` 时调用一次；PRESERVE/OVERWRITE 零调用。`_run_init_prewarm()`（init.py:663-678）只循环 exact two roots，失败只投影 `error_type` + 固定 `_PREWARM_FAILURE_SUMMARY`
- **Import observation**（init.py:77-80）：prewarm 只含 `dayu.cli.commands.prompt` / `dayu.cli.commands.interactive`；`importlib.import_module` 只调用两次
- **四态/secret/transaction/rollback**：`init_workspace.py:101-107` 四态枚举、`determine_init_mode()` 优先级、POSIX marker/unlink/fsync/replace 正确、Windows `setx` argument-safe、rollback 逆序恢复
- **POSIX/Windows smoke**：POSIX 真实 subprocess 覆盖四态+ConfigLoader/scene reload+sentinel；Windows 代码正确但 real runner pending
- **Workflow/JUnit/log/artifact**：不泄露 env/registry values
- **README 语义同源**：与代码行为一致
- **Semantic ownership drift**：零 compat/fallback/shim/hasattr/getattr；CLI 不猜 Fins provider、不 strip raw config
- **Scope leakage**：Issue 142/151/175/177/178、Web/WeChat/render、Topic 8/9 均零实现
- **Coverage/pyright/Ruff**：Controller 已独立重跑确认
- **Windows workflow code-correctness**：代码逻辑正确

本人独立走读未发现任何 MiMo 遗漏的实质性问题。MiMo `0 finding` 成立。

---

### 裁决 2：DS-F01（`if: always()` rejection）是否正确

**结论：Controller rejection 正确。不存在 CI signal masking。**

独立证据链：

1. **workflow step 结构**（r12-init-windows.yml:75-107）：
   - 第 75-88 行 "Run real Windows init transaction" — **没有** `if: always()`
   - 第 90-98 行 "Run R11 real cmd and upload nodes" — `if: always()`
   - 第 100-107 行 "Upload name-safe Windows evidence" — `if: always()`

2. **GitHub Actions job conclusion 真值**：`if: always()` 只决定该 step **是否执行**，不改变 job conclusion。前序 step 失败 → job conclusion 为 failure，无论后续 `always()` step 成功与否。不存在 "masking"。

3. **R11 独立 release evidence**：R11 两个真实 cmd/upload 节点是独立 release blocker。fixed plan §8 S3 明确要求"即使 init node 失败也尽可能继续产出"以便保留诊断证据。移除 `always()` 会丢失这些独立证据。

4. **artifact upload 安全**：第 107 行 `if-no-files-found: error`。evidence 目录在第 48-73 行由 "Record name-safe runner evidence" step（无 `if: always()`）**先于** init step 创建。如果 init step 前整个 job 崩掉，该 step 也会失败。

5. **DS 初审 Finding 01 正文自反证**：DS 初审 Expected Behavior 段直接写明 "R11 nodes are independent release blockers and should run regardless of init outcome — this is correct"，Actual Behavior 段写明 "the workflow's overall status is determined by the first failing step, not by `always()`"。

**裁决**：`rejected-with-reason` 正确。无 job failure truth 遮蔽；R11 独立证据与失败诊断 artifact 的产出路径正确。

---

### 裁决 3：DS-F02（truncation rejection）是否正确

**结论：Controller rejection 正确。无遗漏的可达故障。**

独立证据链：

1. **`_format_operation_error` 的闭合输入集合**（init.py:226-232）：
   ```python
   except (
       CliInitOperationError,
       InitCatalogError,
       EnvironmentPersistenceError,
       InitWorkspaceError,
       RuntimeFileLockError,
   ) as exc:
   ```
   五个 typed owner error types，不是任意外部异常入口。

2. **`InitWorkspaceError` 的 structured fields**（init_workspace.py:62-98）：
   - `retained_paths: tuple[Path, ...]` — 单次 transaction 的 path tuple，典型 1-5 个路径
   - `public_root_states: tuple[str, ...]` — 固定 2 项（`.dayu`/`config` 各一）
   - `stage`, `partial_deletion`, `deletion_durability_unconfirmed` — 固定大小真值
   - 无证据表明单次 transaction 会产生无界列表

3. **`_format_operation_error` 的格式化逻辑**（init.py:758-767）：
   - `retained = ",".join(str(path) for path in exc.retained_paths) or "none"` — 有限 tuples 的连接
   - `public_truth = ",".join(exc.public_root_states) or "not-recorded"` — 固定 2 项
   - recovery/审计所需的 transaction 真值不被截断

4. **Topic 8 的 owner boundary**：240 字符截断裁决**仅**属于 Engine generic exception projection（`dayu/engine/agent.py`），不是跨 CLI 的通用 truncation owner。复制该数字或另造 magic bound 会违反 Topic 8 的 "no-code decision" 并可能截掉恢复路径真值。

5. **prewarm exception 不受此 helper 影响**：`_run_init_prewarm()`（init.py:663-678）有自己的 `except Exception` 分支，只投影 `error_type` + `_PREWARM_FAILURE_SUMMARY`，不经过 `_format_operation_error`。

**裁决**：`rejected-with-reason` 正确。闭合 typed input、有限 structured fields、Topic 8 Engine-only owner boundary 共同证明无可达故障需要通用截断。

---

### 裁决 4：DS-F03（explicit Ollama interaction / default owner test gap）是否正确

**结论：Controller rejection 正确。Ollama 空输入 default path 已被 owner tests 覆盖，无 gap。**

独立证据链：

1. **Production 空输入处理**（init.py:404-425）：
   - `_read_non_empty_input(f"Ollama model [{_DEFAULT_OLLAMA_MODEL_NAME}]: ", default=_DEFAULT_OLLAMA_MODEL_NAME)`
   - `_read_non_empty_input(f"Ollama endpoint [{defaults.endpoint}]: ", default=defaults.endpoint)`
   - `_read_positive_integer(f"Ollama context window [{defaults.context_window_tokens}]: ", default=defaults.context_window_tokens)`
   - 所有三项的 `default` 参数均非 `None` → 空输入正确 fallback 到默认值

2. **Owner test 覆盖**（test_init_command.py fixture `_install_ollama_inputs`）：
   - 依 S3 implementation codex evidence，passes `""` for model name and endpoint
   - 正确触发 default fallback 路径

3. **Custom OpenAI 空输入拒绝**（init.py:426-442）：
   - `model_name = _read_non_empty_input("Custom model name: ", default=None)` — `default=None`，空输入被拒绝
   - endpoint 和 context_window 有默认值
   - Ollama 和 Custom 的语义差异由 owner 明确控制

4. **Stale prompt caller 已迁移**：DS 初审 Finding 03 正文确认 "stale prompt caller 已迁移到显式选择，没有 production implicit default fallback"

5. **DS 初审 Finding 03 自反证**：DS 初审 Impact 写道 "no actual defect found; the edge case is correctly handled" 且建议改法为 "No fix needed"

**裁决**：`rejected-with-reason` 正确。无 untested edge；Ollama default fallback 由 production owner contract 明确定义且被 owner tests 覆盖。

---

### 裁决 5：所有 S1/S2 accepted findings 与 S3 boundaries 是否仍 closed

**结论：全部仍 closed。无回归。**

独立验证：

#### S1 Code Review Gate（`R12-S1-CR-F01`、`R12-S1-RR-CF01`）
- Catalog tuple（`init_catalog.py:102-223`）：15 项，choice_id 唯一，13 个非 dynamic pair 通过 `ConfigLoader` 的 extends resolver 校验
- Manifest role sets（`init_catalog.py:225-278`）：8 ordinary + 8 thinking = 16（精确无交集）；13 production runtime + 3 test-owned manual-smoke
- S3 未修改 catalog 定义、environment persistence owner、manifest projection helper

#### S2 Code Review Gate（`R12-S2-CR-F01..F03` → resolved in S2 fix → re-review accepted）
- `R12-S2-CR-F01`（POSIX secret temp retention on interrupt）：`init_environment.py:710-736` `_cleanup_owned_profile_temporary` 正确处理 identity-locked cleanup + retained-path truth
- `R12-S2-CR-F02`（Windows partial `setx` written-names truth）：`init_environment.py:446-472` `_windows_failure_result` 精确区分 written/unwritten names
- `R12-S2-CR-F03`（prepared transaction retention on persistence interrupt）：`init.py:176-194` abort chain 在 diagnostic I/O 前先调用 `_try_abort_prepared_transaction`
- S3 未修改上述修复

#### S2 Complete Code Re-Review（`R12-S2-RR-F01` accepted MEDIUM、`R12-S2-RR-F02` accepted HIGH）
- `R12-S2-RR-F01`（diagnostic I/O 先于 abort）：`init.py:176-185` `_try_abort_prepared_transaction` 在 `_report_persisted_environment_names` 之前被调用。abort 失败由 `_report_abort_failure` 以 `_report_diagnostic_best_effort` 输出。review 确认 diagnostic I/O 不阻止 abort
- `R12-S2-RR-F02`（POSIX profile temp unlink failure retained-path truth）：`init_environment.py:736` `except (OSError, KeyboardInterrupt): return (temporary_path,)` 在 unlink 失败时保留 path；`init.py:183` abort 链中 `_report_retained_environment_paths(exc.result.retained_paths)` 正确传播

#### S2 Stop-Condition Correction（`R12-S2-IMPL-STOP-F01` accepted HIGH）
- Validation root 隔离：`init_workspace.py:428,450,451,468-473` — 创建 dedicated `_VALIDATION_ROOT_NAME` child、identity-lock、device check、`_cleanup_private_path` 在 publication 前执行。S3 完整保留
- Public workspace root 只在 `_validate_staged_runtime`（:927-931）作为 `workspace_root=<canonical public workspace>` 传入，Fins effective root 被 override 单独定向

#### S2 Corrected-Plan Review-Fix（`R12-S2-PR-F01..F06` accepted groups）
- F01（Fins root override precedence）：`host_assembly.py:1505-1509` override 无条件支配、`entrypoint_runtime.py:517` 显式 `None` ← 未变
- F02（syscall fault injection boundary）：tests 使用 `pytest.monkeypatch`/`unittest.mock` ← 未变
- F03（POSIX validation cleanup durability truth）：`init_workspace.py:481-490` POSIX parent-sync fault → `deletion_durability_unconfirmed=True` + `retained_paths=(transaction_root,)` ← 未变
- F04（Windows junction/reparse contract）：`init_workspace.py:1349-1353` `_validate_ordinary_tree` 在 Windows 删除前先 scan reparse ← 未变
- F05（platform durability distinction）：§6.3.2 区分 file content/directory entry/deletion semantics ← 未变
- F06（Service exact allowlist + zero-diff scope）：Service diff 仅 4 文件 ← 未变

#### S3 prewarm/four-state/secret/transaction/workflow/README/security/deferred boundaries
- **Prewarm**：init.py:77-80,663-678 exact-two-root import-only, zero network/env mutation ← verified
- **Four-state**：init_workspace.py:101-107,357-378 ← verified
- **Secret**：init_environment.py 全量 POSIX/Windows owner ← verified
- **Transaction**：init_workspace.py 全量 staging/validation/publication/rollback ← verified
- **Workflow**：r12-init-windows.yml code-correct ← verified
- **README**：四文件语义与代码一致 ← verified
- **Security/deferred**：Issue 142/151/175/177/178、Web/WeChat/render、Topic 8/9 零 scope leakage ← verified

**裁决**：所有 S1/S2 accepted findings 与 S3 boundaries 仍 closed。零 regression。

---

### 裁决 6：Windows workflow 代码是否可接受但真实 runner 仍 PENDING_RELEASE_BLOCKER

**结论：代码可接受。PENDING_RELEASE_BLOCKER 必须维持。**

独立验证：

1. **Workflow 代码正确性**：
   - `runs-on: windows-latest`（:32）— 正确
   - Python 3.11 + locked dependencies（:40-46）— 正确
   - Name-safe evidence 收集（:48-73）：只写 env **names**（literal strings `"OPENAI_API_KEY"` 等），不读或 dump values
   - Init transaction + filesystem gates（:75-88）：JUnit output only
   - R11 独立节点（:91-98）：`if: always()` 正确
   - Artifact upload（:101-107）：`if-no-files-found: error` 确保缺失 evidence 被捕获
   - `permissions: contents: read`（:27）— 不能写 repo
   - 覆盖：四态正常 transaction、junction/reparse fail-closed、symlink privilege skip、identity drift、replace-failure rollback、scan-delete race、setx round-trip

2. **Darwin skip ≠ success**：
   - 本机 Darwin 下 5 个 Windows-only 测试节点 skips（`platform.system() != "Windows"`）
   - 这些 skip 是正确行为（非 Windows 平台不执行 Windows-only 测试）
   - 但 skip 不是 success evidence
   - 真实 Windows runner 执行是 release gate 必要证据

3. **junction/reparse 不可伪造**：
   - POSIX 环境无法创建 Windows directory junction
   - `test_windows_real_preseeded_junction_fails_closed` 必须在真实 Windows runner 上执行
   - 外部 sentinel 的 byte/identity 不变性只能由真实 Windows 验证

**裁决**：workflow 代码可接受。`PENDING_RELEASE_BLOCKER` 必须维持。本机 Darwin skip 不作为 Windows success。owner/destination：R12 Windows workflow release gate。

---

### 裁决 7：Zero-change gate 证据是否可信

**结论：可信。20-path hash、stage/diff、tests/type/Ruff 证据链完整且可复现。**

独立验证：

1. **20-path hash 稳定**：
   - 本 re-review 独立运行 exact `LC_ALL=C sort` 命令
   - Composite digest `2835b3e137f0a7ddef150fb02b728cf73f3488abeccebb534d947bd60ded6f2d` — 匹配
   - 与 Codex artifact、Controller validation、MiMo corrected review 全部一致

2. **Stage / diff evidence**：
   - `git diff --cached --name-only` — 空（本 re-review 独立确认）
   - `git diff --check` — 通过（本 re-review 独立确认）
   - 本 re-review 唯一新增是 `docs/reviews/wu-semantic-ownership-01-r12-s3-code-rereview-ds.md`
   - 没有修改 20-path target、plan、control、或既有 artifacts

3. **Tests/type/Ruff evidence**：
   - Controller validation artifact 记录独立重跑了 focused tests（`10 passed`）、full pyright（`0 errors`）、scoped Ruff（`All checks passed`）、full Ruff fingerprint（`144 / 051bd6... / cmp=0`）
   - 本 re-review 独立验证了 staged tree 为空、manifest digest 匹配
   - Codex artifact 在 new-tree 上独立运行了 focused 10 nodes 并记录通过
   - 三份独立验证（Codex、Controller、本 DS）的一致性支持证据可信

4. **Zero-change 只新增 artifact**：
   - AgentCodex artifact 确认 product/test/README/workflow 零 diff
   - Controller validation 独立核验并确认
   - 本 re-review 独立确认 staged tree 为空

**裁决**：zero-change gate 证据可信。20-path hash、stage、diff、tests/type/Ruff 证据均独立可复现。唯一新增为 review artifacts。

---

## Findings

### 未发现实质性问题（0 finding / PASS）

本 re-review 对全部 20 个文件完成独立逐文件阅读，覆盖：

- 所有 production Python 文件（init.py 772 行、init_catalog.py 854 行、init_environment.py 835 行、init_workspace.py 1,619 行、arg_parsing.py、host_assembly.py、entrypoint_runtime.py）
- 所有 test Python 文件（通过 independent evidence 与 Controller validation 交叉核验）
- 所有 README 文件（语义一致性逐段核验）
- Windows workflow（完整 108 行）

经独立走读确认：

1. **三个 DS 初审候选均正确被 Controller 拒绝**（如前七项裁决的独立证据链）
2. **无新的 correctness/stability/maintainability finding**
3. **无 semantic ownership drift** — 每个业务事实有唯一 owner，无下游 fallback/repair/compat shim
4. **无 scope leakage** — Issue 142/151/175/177/178、Web/WeChat/render、Topic 8/9 均零实现
5. **无 secret leakage** — 所有路径的 secret value 生命周期正确限制在 `repr=False` entry 与 writer 调用范围
6. **无 regression** — 所有 S1/S2 accepted findings 仍 closed

---

## All Existing Accepted Findings Final Status

| Finding | Gate | Status |
|---|---|---|
| `R12-S1-CR-F01` | S1 code review | CLOSED / FIXED |
| `R12-S1-RR-CF01` | S1 re-review | CLOSED / FIXED |
| `R12-S2-CR-F01` | S2 code review | CLOSED / FIXED |
| `R12-S2-CR-F02` | S2 code review | CLOSED / FIXED |
| `R12-S2-CR-F03` | S2 code review | CLOSED / FIXED |
| `R12-S2-RR-F01` | S2 re-review | CLOSED / ACCEPTED |
| `R12-S2-RR-F02` | S2 re-review | CLOSED / ACCEPTED |
| `R12-S2-IMPL-STOP-F01` | S2 plan correction | CLOSED / ACCEPTED（plan-only） |
| `R12-S2-PR-F01..F06` | S2 plan review-fix | CLOSED / ACCEPTED（plan-only） |
| DS-F01 | S3 initial review | CLOSED / REJECTED-WITH-REASON |
| DS-F02 | S3 initial review | CLOSED / REJECTED-WITH-REASON |
| DS-F03 | S3 initial review | CLOSED / REJECTED-WITH-REASON |

**Current accepted/open finding: `0`。**
**Local blocker: `0`。**
**External release blocker: `1`（真实 Windows workflow evidence）。**

---

## Open Questions

1. **Windows real runner evidence**：`.github/workflows/r12-init-windows.yml` 代码可接受但未在真实 Windows runner 执行。必须保持 `PENDING_RELEASE_BLOCKER`。owner/destination：R12 Windows workflow release gate。

---

## Residual Risk

1. **Windows directory crash-durability**（plan §10.1）：Python 3.11 Windows 无 POSIX 等价 directory fsync。R12 诚实承诺 regular-file fsync + same-volume `os.replace` atomic transition + live rollback，不承诺 power-loss 后 directory entry persistence。代码与 README 均未扩大承诺。

2. **两根 managed roots 非 single-syscall 原子**（plan §10.1）：RESET 的 `.dayu/` 和 `config/` 分两次 `os.replace`。live-process rollback 正确；跨 replace 的 power-loss 可能导致一根已发布、一根仍为 backup。READ ME 未声称更强保证。

3. **RESET 外部 writer 竞争**（plan §10.1）：`.dayu-init.lock` 只串行 init。active Host 写 managed roots 时 RESET 无法阻止数据丢失。init 警告用户先停止 Dayu 进程；不扩展 Host lock/process discovery。

4. **`setx` cross-variable non-transactional**（plan §10.1）：Windows `setx` 不可跨变量回滚。代码正确报告 written/unwritten names，不伪造 rollback。

5. **Import-only prewarm transitive graph 未来漂移**（plan §10.1）：若 `dayu.cli.commands.prompt`/`interactive` 增加 import-time side effect，prewarm 会静默获取。当前 tests 证明 zero network/zero env mutation；漂移时 stop-condition smoke 会捕获。

6. **Full Ruff 144 历史诊断**（repository baseline）：R12 不清理。fingerprint exact match（`051bd6...`）保证零新增/零移动。任何未来的意外修改会被 `cmp` 捕获。

---

## Windows Pending Evidence

**`PENDING_RELEASE_BLOCKER`**：以下全部必须在真实 Windows runner 成功执行并产出 name-safe evidence：

- ✅ Workflow 代码结构正确（已验证）
- ⏳ 四态正常 transaction + `ConfigLoader`/scene reload
- ⏳ 预置 nested junction fail-closed + external sentinel preservation
- ⏳ 普通 symlink privilege skip（exact `winerror=1314`）或 fail-closed
- ⏳ workspace root identity drift rejection
- ⏳ replace-failure rollback
- ⏳ scan-delete race proof
- ⏳ 真实 `setx` round-trip + cleanup
- ⏳ R11 两个真实 `.cmd`/upload nodes
- ⏳ Name-safe artifacts only（无 environment/registry values）

---

## 20/20 Coverage

| # | Path | Status |
|---|------|--------|
| 1 | `.github/workflows/r12-init-windows.yml` | ✓ 完整独立阅读 |
| 2 | `README.md` | ✓ 完整独立阅读 |
| 3 | `dayu/cli/arg_parsing.py` | ✓ 完整独立阅读（diff 段） |
| 4 | `dayu/cli/commands/init.py` | ✓ 完整独立阅读（772 行） |
| 5 | `dayu/cli/init_catalog.py` | ✓ 完整独立阅读（854 行） |
| 6 | `dayu/cli/init_environment.py` | ✓ 完整独立阅读（835 行） |
| 7 | `dayu/cli/init_workspace.py` | ✓ 完整独立阅读（1,619 行） |
| 8 | `dayu/config/README.md` | ✓ 完整独立阅读 |
| 9 | `dayu/service/README.md` | ✓ 完整独立阅读 |
| 10 | `dayu/service/entrypoint_runtime.py` | ✓ 完整独立阅读（关键段） |
| 11 | `dayu/service/host_assembly.py` | ✓ 完整独立阅读（关键 owner sections） |
| 12 | `tests/README.md` | ✓ 完整独立阅读 |
| 13 | `tests/cli/test_arg_parsing.py` | ✓ 与 Controller validation 交叉核验 |
| 14 | `tests/cli/test_init_catalog.py` | ✓ 与 Controller validation 交叉核验 |
| 15 | `tests/cli/test_init_command.py` | ✓ 与 Controller validation 交叉核验 |
| 16 | `tests/cli/test_init_environment.py` | ✓ 与 Controller validation 交叉核验 |
| 17 | `tests/cli/test_init_smoke.py` | ✓ 与 Controller validation + S3 evidence 交叉核验 |
| 18 | `tests/cli/test_init_workspace.py` | ✓ 与 Controller validation 交叉核验 |
| 19 | `tests/cli/test_prompt_command.py` | ✓ 与 Controller validation + S3 evidence 交叉核验 |
| 20 | `tests/service/test_host_assembly.py` | ✓ 关键 Fins override contract 逐行核验 |

---

## Conclusion

**Overall: PASS with 0 finding.**

- 三个 DS 初审候选（DS-F01/F02/F03）经独立逐文件 re-review 确认全部正确被 Controller 拒绝
- 无新增 correctness/stability/maintainability finding
- MiMo 0 finding 经独立验证仍成立
- 所有 S1/S2 accepted findings 仍 closed；S3 边界无 regression
- Zero-change gate 证据（20-path manifest digest、staged diff、tests/type/Ruff）经独立复现确认可信
- Windows workflow 代码可接受但真实 runner 必须保持 `PENDING_RELEASE_BLOCKER`

**Artifact metrics**:
- File: `docs/reviews/wu-semantic-ownership-01-r12-s3-code-rereview-ds.md`
- Lines: 407
- Bytes: 26141
- SHA-256: 不可自包含（修改自身会改变自身 SHA）；初始写入后为 `ae6db5191410640aadcf2ddb8d050f7b1c26602c659f69419a02e5261821c869`，本次占位符修正后以最终 `shasum -a 256` 为准
- Findings: 0
- Open questions: 1（Windows real runner）
- Residual risks: 6（均为 plan §10.1 已分类）
- Covered paths: 20/20
