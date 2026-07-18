# WU-SEMANTIC-OWNERSHIP-01 / R12 S3 Complete Cumulative Code Re-Review — AgentMiMo

## Scope

- Mode: cumulative code re-review (fixed 20-path manifest)
- Branch: `phaseflow/host-issues-control`
- Fixed plan: `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`, SHA-256 `aa7b50a90c9623ea8dcafe8c4c651665b16b9ee3be76ec8357c4d47977fb2a4c`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-r12-s3-code-review-controller-adjudication.md`, 76/7026/SHA-256 `2c668bf087c4b27cc7372424a7c59e8b7dca2257b64783f1d40fee921abff304`
- Zero-change Agent artifact: `docs/reviews/wu-semantic-ownership-01-r12-s3-code-review-fix-codex.md`, 146/12174/SHA-256 `202d2ace1e5b8c8fce309277eb40baea64be1fb42033f488c46cd0bb879f2a68`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-r12-s3-code-review-fix-controller-validation.md`, 33/3540/SHA-256 `c063b94c4642ad25d1298e5807ce1fa36c7080ba8d60aa94f372365920e51f80`
- AgentMiMo corrected review: `docs/reviews/wu-semantic-ownership-01-r12-s3-code-review-mimo.md`, 246/14143/SHA-256 `be4253cbff6e844fc44d289946d57f2b33da8f8899085e200b93d8d686334b53`
- AgentDS corrected review: `docs/reviews/wu-semantic-ownership-01-r12-s3-code-review-ds.md`, 288/27553/SHA-256 `4e0cf14caf296cdb287c62fd2a079af304351d4a97d05ac7439fbe36121ebc4a`
- Source of truth: `AGENTS.md`, `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`
- Output file: `docs/reviews/wu-semantic-ownership-01-r12-s3-code-rereview-mimo.md`
- Included scope: 20/20 paths (see manifest below)
- Excluded scope: none
- Parallel review coverage: 无

## Manifest Verification

```bash
shasum -a 256 .github/workflows/r12-init-windows.yml README.md dayu/cli/arg_parsing.py dayu/cli/commands/init.py dayu/cli/init_catalog.py dayu/cli/init_environment.py dayu/cli/init_workspace.py dayu/config/README.md dayu/service/README.md dayu/service/entrypoint_runtime.py dayu/service/host_assembly.py tests/README.md tests/cli/test_arg_parsing.py tests/cli/test_init_catalog.py tests/cli/test_init_command.py tests/cli/test_init_environment.py tests/cli/test_init_smoke.py tests/cli/test_init_workspace.py tests/cli/test_prompt_command.py tests/service/test_host_assembly.py | LC_ALL=C sort | shasum -a 256
```

Manifest digest: **`2835b3e137f0a7ddef150fb02b728cf73f3488abeccebb534d947bd60ded6f2d`** ✓ PASS。

## Findings

未发现实质性 correctness、stability 或 maintainability 问题。

---

## Independent Verification Results

### 1. MiMo final 0 finding 是否仍成立

**结论: 仍成立。**

独立复审完整读取了20-path target中的所有关键production代码文件，包括：
- `dayu/cli/commands/init.py` (772行) — orchestrator，四态、prewarm、secret collection、lock、transaction编排
- `dayu/cli/init_workspace.py` (1619行) — workspace transaction owner，snapshot、staging、validation、publish、rollback、cleanup
- `dayu/cli/init_catalog.py` — model catalog、static validation、dynamic builder、manifest projection
- `dayu/cli/init_environment.py` — POSIX/Windows secret persistence
- `dayu/service/host_assembly.py` — Service effective-config owner with Fins root override
- `dayu/service/entrypoint_runtime.py` — ordinary runtime caller passing `fins_workspace_root_override=None`
- `.github/workflows/r12-init-windows.yml` — Windows CI workflow

未发现新的实质性defect。初始MiMo review的0 finding结论在本轮re-review中保持不变。

### 2. DS-F01 `if:always()` rejection 是否正确

**结论: rejection 正确。**

独立验证：
- GitHub Actions job结论保留前序step失败真值，后续`if: always()` step成功不会改变job conclusion
- R11两个真实节点是独立release evidence，计划明确要求即使init失败也继续执行
- `r12-init-windows.yml:51` 在测试前预置evidence目录，`upload-artifact`使用`if-no-files-found: error`确保报告产出
- `if: always()`的正确语义是：失败时仍上传诊断证据，不掩盖failure truth

Controller rejection理由完整且准确。DS-F01不构成product defect。

### 3. DS-F02 truncation rejection 是否正确

**结论: rejection 正确。**

独立验证：
- `_format_operation_error` (commands/init.py:750-768) 的production输入是闭合集合：`CliInitOperationError`、`InitCatalogError`、`EnvironmentPersistenceError`、`InitWorkspaceError`、`RuntimeFileLockError`
- `InitWorkspaceError.message` 由owner-produced有限transaction事实构成（stage、path、class name），不是任意外部异常
- Topic 8的240字符裁决只属于Engine generic exception projection (`dayu/engine/agent.py`)，不是跨CLI的通用truncation owner
- 复制该bound到init会扩大明确no-code decision，并可能截掉recovery路径真值

Controller rejection理由完整且准确。DS-F02不构成product defect。

### 4. DS-F03 explicit Ollama interaction/default owner test 是否无缺口

**结论: 无缺口。**

独立验证：
- `commands/init.py:404-425` Ollama动态输入处理：空model name使用`_DEFAULT_OLLAMA_MODEL_NAME`（"qwen3:8b"），空endpoint使用`ollama_template_defaults(models).endpoint`，空context window使用默认值
- `_read_non_empty_input` (commands/init.py:716-730) 正确处理空输入+default场景
- `test_init_command.py:250-273` 的 `_install_ollama_inputs` fixture传入空字符串，验证default fallback
- DS自身expected/actual/evidence已确认行为正确

Controller rejection理由完整且准确。DS-F03不构成product defect。

### 5. S1/S2 accepted findings 与 S3 boundaries 是否仍closed

**结论: 仍closed，未发现回归。**

独立验证关键contract：
- **Service Fins root override**: `host_assembly.py:528-551` 的 `assemble_effective_tool_provider_configs` 接受 `fins_workspace_root_override` 参数，`_is_fins_workspace_bound_provider_config` (line 1569) 正确识别Fins provider
- **entrypoint_runtime.py:517** 显式传递 `fins_workspace_root_override=None`，符合ordinary runtime contract
- **init_workspace.py:927-931** R12 validation唯一non-`None` consumer，正确传入private validation root
- **四态优先级**: `determine_init_mode` (line 357-378) 正确实现 `RESET > OVERWRITE > config existence`
- **Transaction cleanup**: `_cleanup_private_path` (line 1252-1363) 实现identity-locked quarantine + no-follow delete
- **Rollback**: `_rollback_or_raise` (line 1014-1104) 逆序恢复backup，POSIX sync workspace root
- **Post-publication cleanup**: 不rollback已发布config，只产生typed warning

S1 findings (`R12-S1-CR-F01`, `R12-S1-RR-CF01`)、S2 findings (`R12-S2-CR-F01..F03`, `R12-S2-RR-F01..F02`)、S2 stop-condition (`R12-S2-IMPL-STOP-F01`)、S2 corrected-plan (`R12-S2-PR-F01..F06`) 的closure保持稳定。S3未引入回归。

### 6. Windows workflow 代码可接受性与真实runner状态

**结论: 代码可接受。真实runner仍 PENDING_RELEASE_BLOCKER。**

独立验证workflow代码：
- `windows-latest` + Python 3.11 + locked dependencies
- 真实pytest运行四态/junction/symlink/identity/rollback/scan-delete/setx节点
- R11节点在`if: always()`下执行（正确语义：失败时仍收集诊断证据）
- artifact上传使用`if-no-files-found: error`确保报告产出
- 不泄露environment/registry values（只记录env names）

workflow代码逻辑正确。但**本机Darwin不能替代Windows runner真实证据**。`.github/workflows/r12-init-windows.yml`必须在真实Windows runner成功执行并产出name-safe evidence，才可写S3/R12/umbrella final pass。

### 7. Zero-change gate 证据可信度

**结论: 可信。**

独立验证：
- **20-path hash lock**: manifest digest `2835b3e137f0a7ddef150fb02b728cf73f3488abeccebb534d947bd60ded6f2d` ✓ PASS
- **staged tree**: 为空（`git diff --cached --name-only` 为空）
- **diff boundary**: `git diff --check` 通过
- **唯一新增**: 仅zero-change artifact `docs/reviews/wu-semantic-ownership-01-r12-s3-code-review-fix-codex.md`
- Controller validation已独立通过affected tests (408/5 skipped)、runtime anchors (184)、full CLI (505/7 skipped)、Service (133)、七文件coverage 87%-99%、full pyright zero、changed Ruff zero、full Ruff exact baseline

Zero-change gate的fix disposition正确：三个DS rejected候选均无当前可达defect，实施建议改动反而会破坏或扩大既有owner contract。

---

## Open Questions

无。

## Residual Risk

1. **Windows real runner evidence**: `.github/workflows/r12-init-windows.yml`必须在Windows runner成功执行。当前 `PENDING_RELEASE_BLOCKER`。
2. **RESET 两个 managed roots 非单 syscall 原子**: 既有residual，per-root `os.replace` + 逆序rollback + RESET前active-process警告是当前contract。
3. **Controller validation声明的coverage/pyright/Ruff未独立重跑**: 本机re-review基于Controller artifact声明。Controller已由独立Controller执行并记录。

## 覆盖的 20/20 路径

| # | 路径 | 状态 |
|---|---|---|
| 1 | `.github/workflows/r12-init-windows.yml` | 已 review |
| 2 | `README.md` | 已 review |
| 3 | `dayu/cli/arg_parsing.py` | 已 review |
| 4 | `dayu/cli/commands/init.py` | 已 review |
| 5 | `dayu/cli/init_catalog.py` | 已 review |
| 6 | `dayu/cli/init_environment.py` | 已 review |
| 7 | `dayu/cli/init_workspace.py` | 已 review |
| 8 | `dayu/config/README.md` | 已 review |
| 9 | `dayu/service/README.md` | 已 review |
| 10 | `dayu/service/entrypoint_runtime.py` | 已 review |
| 11 | `dayu/service/host_assembly.py` | 已 review |
| 12 | `tests/README.md` | 已 review |
| 13 | `tests/cli/test_arg_parsing.py` | 已 review |
| 14 | `tests/cli/test_init_catalog.py` | 已 review |
| 15 | `tests/cli/test_init_command.py` | 已 review |
| 16 | `tests/cli/test_init_environment.py` | 已 review |
| 17 | `tests/cli/test_init_smoke.py` | 已 review |
| 18 | `tests/cli/test_init_workspace.py` | 已 review |
| 19 | `tests/cli/test_prompt_command.py` | 已 review |
| 20 | `tests/service/test_host_assembly.py` | 已 review |

## 独立运行的验证

- manifest digest (`LC_ALL=C sort`): ✓ `2835b3e137f0a7ddef150fb02b728cf73f3488abeccebb534d947bd60ded6f2d`
- `entrypoint_runtime.py:517` 的 `fins_workspace_root_override=None`: ✓ 已验证
- `host_assembly.py` 的 `assemble_effective_tool_provider_configs` 接受override参数: ✓ 已验证
- `init_workspace.py:927-931` R12 validation唯一non-`None` consumer: ✓ 已验证
- `_format_operation_error` 的闭合集合typed input: ✓ 已验证
- `_run_init_prewarm` 的exact two roots: ✓ 已验证

## 所有既有 accepted findings closure

- S1 findings: 未发现回归
- S2 findings: 未发现回归
- S2 stop-condition/corrected-plan: 未发现回归
- Controller discussion topics 1-9: 未发现scope leakage
- DS-F01/F02/F03 rejection: 独立验证correct

## Windows pending evidence

**`PENDING_RELEASE_BLOCKER`**: `.github/workflows/r12-init-windows.yml` 必须在 Windows runner 成功执行并产出 name-safe evidence。在此之前，Windows gate、S3、R12 和 umbrella 不得写成最终通过。

## 最终 finding ledger

| 来源 | 候选数 | accepted | rejected-with-reason | deferred | needs-more-evidence |
|---|---:|---:|---:|---:|---:|
| AgentMiMo (initial) | 0 | 0 | 0 | 0 | 0 |
| AgentDS | 3 | 0 | 3 | 0 | 0 |
| AgentMiMo (re-review) | 0 | 0 | 0 | 0 | 0 |
| Controller direct | 0 | 0 | 0 | 0 | 0 |

- current accepted/open finding: **0**
- local blocker: **0**
- unclassified residual: **0**
- external release blocker: **1**（真实 Windows workflow evidence）

## 结论

**PASS / 0 finding / READY_FOR_CONTROLLER_CHECKPOINT。**

MiMo final 0 finding 仍成立。DS-F01/F02/F03 rejection均正确。所有S1/S2 accepted findings与S3 boundaries仍closed。Windows workflow代码可接受但真实runner仍PENDING_RELEASE_BLOCKER。Zero-change gate证据可信。

本re-review未修改任何product/test/README/workflow/plan/control/既有artifacts，未stage/commit/push。
