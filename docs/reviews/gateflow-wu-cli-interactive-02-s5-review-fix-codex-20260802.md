# WU-CLI-INTERACTIVE-02 S5/F13 Code Review Fix

## Gate facts

- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Slice：S5 / F13
- Gate：accepted-finding fix
- Branch：`codex/interactive-oracle`
- Accepted base / current HEAD：`ce7ef846f7b8aac2d0b942bb487819fe0210b746`
- Controller adjudication：
  `docs/reviews/gateflow-wu-cli-interactive-02-s5-code-review-adjudication-20260802.md`
- Completion status：`fix-complete / ready-for-simultaneous-re-review`
- Artifact path：
  `docs/reviews/gateflow-wu-cli-interactive-02-s5-review-fix-codex-20260802.md`

## Scope and owner decision

本轮只修复 Controller accepted 的两个低严重度 public discovery contract 缺口：

1. `dayu.engine.contracts.runner_identity` 是成功 Runner response identity 类型的 owner；
   `ProviderRequestIdAvailability` 与 `SuccessfulRunnerResponseIdentity` 已由该模块定义，且已由
   `dayu.engine.contracts` 和 `dayu.engine` 显式导出，因此 owner module 的 `__all__` 必须同步包含二者。
2. `dayu.host.context_events` 是 durable compactor proposal manifest reference 的 owner；
   `CompactorProposalManifestReference` 已由该模块定义并由 Host 内部消费者直接导入，因此该 owner
   module 的 `__all__` 必须包含该类型。

修复位于语义 owner boundary，并由对应 owner-level test 直接断言；没有在消费者、adapter 或 package
root 添加 fallback / compatibility / 重算。`dayu.host` package root 未新增 re-export。

## Changed files

本 fix 修改四个既有 tracked files：

- `dayu/engine/contracts/runner_identity.py`
- `dayu/host/context_events.py`
- `tests/engine/contracts/test_runner_identity.py`
- `tests/host/test_context_compact_events.py`

并新增本唯一 fix artifact。既有 53-file S5 implementation diff、implementation artifact、MiMo/DeepSeek
review artifacts 与 Controller adjudication artifact 全部保留。

## Exact fix diff

```diff
--- a/dayu/engine/contracts/runner_identity.py
+++ b/dayu/engine/contracts/runner_identity.py
@@
-__all__ = ["RunnerRequestIdentity", "build_runner_request_identity"]
+__all__ = [
+    "ProviderRequestIdAvailability",
+    "RunnerRequestIdentity",
+    "SuccessfulRunnerResponseIdentity",
+    "build_runner_request_identity",
+]

--- a/dayu/host/context_events.py
+++ b/dayu/host/context_events.py
@@
     "CONTEXT_COMPACTION_ATTEMPT_REJECTED",
     "CONTEXT_COMPACTION_FAILED",
     "CONTEXT_COMPACTION_REQUESTED",
+    "CompactorProposalManifestReference",
     "ContextBudgetEvaluatedPayload",

--- a/tests/engine/contracts/test_runner_identity.py
+++ b/tests/engine/contracts/test_runner_identity.py
@@
+import dayu.engine.contracts.runner_identity as runner_identity_contract
@@
+def test_runner_identity_owner_exports_successful_response_contracts() -> None:
+    """Runner identity owner 必须直接导出成功响应身份公共契约。
+
+    :returns: ``None``。
+    :raises AssertionError: 任一公共类型未由 owner 模块导出时抛出。
+    """
+
+    assert "ProviderRequestIdAvailability" in runner_identity_contract.__all__
+    assert "SuccessfulRunnerResponseIdentity" in runner_identity_contract.__all__

--- a/tests/host/test_context_compact_events.py
+++ b/tests/host/test_context_compact_events.py
@@
+import dayu.host.context_events as context_events_module
@@
+def test_context_events_owner_exports_compactor_manifest_reference() -> None:
+    """Context event owner 必须直接导出 compactor manifest 引用契约。
+
+    :returns: ``None``。
+    :raises AssertionError: manifest 引用类型未由 owner 模块导出时抛出。
+    """
+
+    assert "CompactorProposalManifestReference" in context_events_module.__all__
```

## Finding status and self-review

| Finding | Controller decision | Fix status | Direct evidence |
|---|---|---|---|
| MiMo 001：Runner identity owner `__all__` 缺两个公共类型 | `accepted-low` | `已修复` | owner `__all__` 新增两个名字；owner test 对两个名字分别直接断言 |
| MiMo 002：Context event owner `__all__` 缺 manifest reference | `accepted-low` | `已修复` | owner `__all__` 新增该名字；owner test 直接断言 |

两项 rejected finding 保持 Controller 原裁决且未实现：DeepSeek 001 为 `rejected-speculative`，本 fix
未添加注释、未拆模块、未改变 import graph；DeepSeek 002 为 `rejected-non-finding`，本 fix 未新增
cross-validation、比较源或 compatibility 文本。

Controller 在 fix 期间指出两个新增 test 函数的初始单句 docstring 不满足项目函数 docstring 硬约束。
本轮仅补充无参数函数所需的 `:returns: ``None``` 与 `:raises AssertionError:`，未虚构参数、未扩大测试
语义；补充后重新运行对应 export nodes 并通过。

Self-review 确认：

- 未修改 `dayu/host/__init__.py`，未新增 `dayu.host` package re-export；
- 未实现两项 rejected DeepSeek finding；
- 未修改业务逻辑、schema、状态机、LLM-facing 文本或上层 package root re-export contract；
- 未修改 README、S6、registry、scenario、oracle 或其它 docs；
- 未执行 stash、checkout、reset、rebase、commit、push 或 PR 操作。

## Validation

所有 Python 命令均先执行 `source .venv/bin/activate`。

| Validation | Result |
|---|---|
| 两个新增 owner export nodes | `2 passed in 0.33s` |
| S5 Engine + compaction focused 12-file suite | `540 passed in 4.27s` |
| S5 冻结 owner-level / behavior 14-file suite | `621 passed in 5.85s` |
| `python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| Exact mechanical inventory | identity `27`；builder `8`；overlap `2`；builder-only `6`；union `33` |
| Exact overlap paths | `tests/host/test_compaction_operation.py`、`tests/host/test_dispatch_scheduler.py` |
| Exact builder-only paths | 冻结的 `test_compact_material.py`、`test_compaction_terminal.py`、`test_context_compact_events.py`、`test_memory_projection.py`、`test_proactive_compaction_operation.py`、`test_run_input_builder.py` |
| `git diff --check` | pass |

Exact 33-file inventory 使用 accepted plan §10.5 的五类 `rg` pattern、`sort -u`、`comm` 与两个
expected-path `diff -u` 原样验证；所有 count assertion 与 path assertion 均 exit 0。

## Docs decision

不更新 README。此次修复只补齐已经存在且已经由上层 Engine package 显式导出的 owner module discovery
surface，以及 Host 内部 owner module discovery surface；不改变用户可见安装、CLI、工作流、分层关系、
schema 或运行行为。用户同时明确禁止 docs/README/S6 改动。

## Residual risks and uncovered areas

- 两个 accepted export findings：`fixed in current slice`。
- 六个 clean-base phase5 scheduler-test race：`assigned to later work unit`；本 fix 未改变 scheduler/timing。
- awaiting-entrypoint clean-base `callback_execution_port` 断裂：`assigned to later work unit`；本 fix 未改变该路径。
- 五条 registry claim、parser-derived inventory/readiness proof：`covered by later approved slice`（S6）。
- 真实 provider successful compaction identity evidence、行为项 29 与 G06：
  `covered by later approved slice`（S6 / external validation）。

没有未分类 residual risk，也没有 blocking open question。

## Next gate

按 Controller adjudication，下一 gate 是 MiMo 与 DeepSeek 对当前稳定 workspace 做 simultaneous independent
re-review。用户明确禁止本轮 commit / push / PR，因此本 fix 在未提交状态结束。
