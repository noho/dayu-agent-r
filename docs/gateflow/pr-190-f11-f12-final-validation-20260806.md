# PR 190 F11/F12 Final Validation

## Gate

- Work unit: 关闭 F11 public compactor response identity 与 F12 minimal fresh compaction v3 contract。
- Validation head: `d51a87135ba07d98b6a3d20296152495c9ececb9`。
- Branch / remote parity: `codex/interactive-oracle`、local HEAD 与 `github/codex/interactive-oracle` exact match。
- Worktree before validation artifact: clean。
- Date: 2026-08-06。

## Final test results

### Complete repository

```bash
source .venv/bin/activate
pytest -q
```

Result: **6727 passed, 11 skipped, 6 deselected, 3 warnings** in 229.56s. 三条 warning 均来自已安装 `edgar` package 的 deprecation notice；无 test failure。

### Final owner coverage

```bash
pytest -q \
  tests/host/test_compaction_contract.py \
  tests/host/test_llm_compaction.py \
  tests/host/test_compaction_cancellation_scope.py \
  tests/host/test_compaction_operation.py \
  tests/host/test_dispatch_scheduler.py \
  tests/host/test_engine_ingest_mapping.py \
  tests/host/test_open_host_runtime.py \
  tests/host/test_public_compact_smoke.py \
  --cov=dayu.host.compact_structure \
  --cov=dayu.host.llm_compaction \
  --cov-report=term-missing \
  --cov-fail-under=80
```

Result: **389 passed, 1 skipped**；`compact_structure.py` 89%，`llm_compaction.py` 86%，合计 exact 87.71%。两个本轮最终修改的 production owner 都达到单文件 `>=80%`。

PR-review fix 的独立定点结果保持：

- compaction owner suites：53 passed；
- Tool Trace analysis owner suites：32 passed；
- rejected + successful response identity 的 typed / JSON / Markdown 同源断言 PASS。

### Diagnostic reruns and classification

一次过窄的 53-test coverage 命令只能覆盖 `llm_compaction.py` 68%，combined 79.20%；这不是 product failure，而是该文件的 Engine/Host lifecycle 分支由 operation/dispatch/public smoke owner tests 覆盖。使用上述真实 owner-suite union 后得到单文件 86%，不通过 padding、omit 或 waiver 达标。

一次 `tests/host` 全量 coverage 诊断得到 2412 passed、2 skipped、6 deselected、16 failed，同时仍测得 `llm_compaction.py` 86.50%。失败分类：

- 15 项 process-backed ToolRuntime case 在 coverage instrumentation/order 下触发 Python multiprocessing `PicklingError`；随后不带 coverage 独立重跑整个 `test_toolruntime_executor.py`，**68 passed**。
- `test_cancel_session_runs_scoped_to_session` 在 coverage run 中观察到重复 cancel reason；随后独立重跑，**1 passed**。
- 同一 final head 的完整仓库非 coverage run 已 **6727 passed**。

因此这些是 coverage instrumentation/order interaction 与既有 timing flake，不是 F11/F12 product regression，也不作为 coverage 证明；最终 coverage 证明只采用上方 389-test clean owner union。

## Type and static validation

- `python -m pyright dayu/ tests/ utils/`：**0 errors, 0 warnings, 0 informations**。
- 从 work-unit base `3087b1b983a97ce5012d54e818795f4755434a98` 到 validation head 的全部 changed Python files 执行 Ruff：**All checks passed**。
- `python -m compileall -q dayu tests utils`：PASS。
- `python -m json.tool docs/cli_ci_oracles.json`：PASS。
- `python -m json.tool docs/cli_ci_scenarios.json`：PASS。
- `git diff --check`：PASS。

额外执行 full-repository `ruff check .`，如实得到 89 个既有 repository-wide lint errors。它们不在本 F11/F12 work-unit changed-file set；本 work unit 的 changed-file Ruff 为零。按用户 non-goal 不顺手修改无关历史 lint debt，owner 为各既有模块维护者。

## Prompt / schema publication identity

| Asset | Before | Final | Final SHA-256 |
|---|---:|---:|---|
| `conversation_compaction.md` | 2,510 bytes | 822 bytes | `97479acc0cc686cb9a72d18b310aff58cabba4d4b223c6773a12249b5ed333e5` |
| `conversation_compaction_user.md` | 13,919 bytes | 4,301 bytes | `59b50e13ea636c434fcabe26adf6d9ed22665dfcba03533ebcf5e9b524b87b76` |
| `conversation_compaction.json` manifest | — | — | `a3ad3ec2b30bc9037b5a4aa7b288d8a2462870d5bac77217a6aa708d58aa52db` |
| `cli_init_workspace_manifest_v1.json` | — | — | `d95de68e69b0aacc712ec6bf468c8604a91460a17f3e2497f397182517a6a9f8` |

此前 PR body 中的 user-prompt `3,337 bytes` 是 supplemental source-kind/self-contained repair 文本之前的中间值；final truth 是 **4,301 bytes**，仍比 13,919-byte v2 prompt 减少 69.1%，且当前 prompt 自足性由 accepted S3 reviews/tests 拥有。PR body 必须在 closeout 更新为 final 值。

## Oracle / scenario and immutable evidence integrity

- `docs/cli_ci_oracles.json`: `3404e241dbd71c6244da24b0dbb080022d4c57b36f040ac3456e7a18dbc97acf`。
- `docs/cli_ci_scenarios.json`: `f4363fc5e7026ad075f4b7f855342cae493a4852d21bd72ef6e53b3f2d588e37`。
- Registry state: both remain `calibration`; three replacement scenarios remain `unadjudicated` for Oracle-controller review。
- Immutable evidence root: `/Users/leo/workspace/.dayu-cli-ci/interactive-memory-v3-20260805T-s4-restart-uOZytY`。
- `digest.json`: `38f0b01f12c2ab55ce1af3c16080b71013d1a19512d65051f5532b747f71da0d` exact recheck PASS。
- `observed-report.md`: `bbaa52a04100932c09e0a8e20d19c81ed6d865378db502bc6d4f1936c9694411` exact recheck PASS。
- Public root has zero `dayu_host.sqlite3` and four non-secret `runtime_lanes.sqlite3`; four credential-bearing Host DB files remain in the separate quarantine recorded by S4 evidence artifacts。
- S4 accepted secret scan: 0 findings；public/canonical F11 identity equality: 0 mismatches。

## Docs decision

- `docs/host/design.md`: updated for canonical F11 Tool Trace response identity and F12 Host-owned v3 acceptance/coverage/audit/repair/durable truth。
- `docs/engine/design.md`: updated only for the directly affected provider-neutral structured-output request/capability transport contract。
- `dayu/host/README.md`, `dayu/config/README.md`, `dayu/engine/README.md`, `dayu/README.md`, `tests/README.md`, `docs/cli_ci.md`: updated at their triggered owner gates and reviewed。
- Root `README.md`: not updated because CLI command, installation, workspace location and end-user workflow did not change。
- Final PR-review fix did not change prompt/schema/design/README and therefore required no new docs update。

## Residual risks and owners

1. **Oracle adjudication pending — Oracle controller.** Three replacement scenarios remain unadjudicated; implementation and observation PASS do not make them ready automatically。
2. **Repository-wide historical Ruff debt — existing module owners.** 89 full-repo findings predate/outside the F11/F12 changed-file set; current work-unit changed files are clean。
3. **Coverage instrumentation/process interaction — Runtime/ToolRuntime test owner.** Isolated ToolRuntime and cancel reruns pass, and full suite passes; preserve as non-blocking test-infrastructure/timing observation rather than modifying unrelated runtime code。
4. **Fresh schema compatibility — deployment/session owner.** v2 compact artifacts are intentionally not supported by reader alias/shim, as explicitly confirmed by the user; deployments must treat this as fresh schema state。
5. **Natural-language quality — real-provider/Oracle owner.** Host deterministically validates shape, provenance, caps and accepted truth but does not pretend to prove arbitrary prose quality; real observation is complete, final oracle judgment remains external。

All residuals are classified. No blocking open question remains.

## Completion status

Final validation: **PASS**。Next Gateflow entry point: commit/push this validation artifact, verify existing draft PR 190 on that exact head, then record `draft-PR-pass` and final closeout。
