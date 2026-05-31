# WU-RUNTIME-01 PR Review — AgentDS 2026-06-01

PR: https://github.com/noho/dayu-agent-r/pull/100
Branch: `refactor/wu-runtime-01-filelock-contraction`
Base: `main`
Reviewer: AgentDS
Review scope: PR diff only（排除本地未提交的 AGENTS.md / CLAUDE.md user changes）
Parallel PR review: `docs/reviews/wu-runtime-01-pr-review-mimo-20260601.md`（MiMo）

## Conclusion

**pass**

WU-RUNTIME-01 完整实现目标：RuntimeFileLock contract 收缩一致、design doc 同步、runtime tests / Host regression tests / import boundary tests / pyright 全部通过、无过度设计、无 scope 泄漏。Control doc `ready-to-open-draft-PR` 状态合理。0 个 blocking finding。

---

## Validation 复核

独立运行验证（当前分支已 checkout）：

| 验证项 | 命令 | 结果 |
|---|---|---|
| runtime filelock + import boundary | `pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q` | 23 passed |
| host audit + tool trace | `pytest tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py -q` | 13 passed |
| 全量组合 | `pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py -q` | 36 passed |
| runtime coverage | `pytest tests/runtime/test_filelock.py --cov=dayu.runtime.filelock --cov-report=term-missing` | 90%（>= 80% 阈值） |
| pyright | `pyright dayu/runtime/filelock.py tests/runtime/test_filelock.py tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py` | 0 errors, 0 warnings, 0 informations |

与 PR description 声明的验证结果一致。

---

## Findings

### DS-PR-1 — 中 — 测试文件直接 import 第三方 `FileLock` 用于 `cast()`

**入口/文件**: `tests/runtime/test_filelock.py:15` — `from filelock import FileLock`

**Evidence**: 测试文件 import `FileLock` 仅用于 `cast(FileLock, test_stub)` 类型断言（lines 174-177, 226-229, 244-247），不调用其方法，不绕过 runtime wrapper。生产 import boundary 测试 `test_third_party_filelock_import_is_confined_to_runtime_filelock` 只扫描 `dayu/` 目录，此测试 import 不构成生产边界突破。

**Risk**: 低。允许测试文件 import `FileLock` 偏离 plan 字面约束（"第三方 `filelock` import 仍只在 `dayu.runtime.filelock`"），但该约束的实质意义是防止生产代码直接依赖第三方库。测试中为 typed test double 需要 `cast()` 是合理的最低限度方案。此 finding 已在 Slice 1 DS code review Finding 2、aggregate DS deepreview Finding 1 中记录为 accepted residual。

**Required fix**: 无。已通过 aggregate controller adjudication 归为 accepted residual。

**Blocking**: 否

---

### DS-PR-2 — 低 — Control doc 修改与 plan "Explicitly forbidden" 声明不一致

**入口/文件**: `docs/host/host-core-followup-implementation-control.md`

**Evidence**: `docs/host/wu-runtime-01-filelock-contraction-plan.md` Section 3 "Explicitly forbidden" 声明 control doc "本 WU 当前 plan 不修改总控文档；后续由 controller 在 gate 状态推进时单独维护"。PR 中 control doc 实际变更包括：gate 状态（`draft-PR-pass` → `ready-to-open-draft-PR`）、active work unit（`none selected` → `WU-RUNTIME-01`）、WU-RUNTIME-01 状态（`未开始` → `已完成`）、RR-HCF-01 状态（`deferred-with-owner` → `closed`）、review artifacts 列表和 plan artifacts / implementation commits。均为 gateflow controller 状态推进的标准维护，不引入设计偏移。

**Risk**: 低。这是 gateflow 流程的正常行为——controller 在 gate 推进时维护总控文档。Plan Explicitly forbidden 约束的实质意图是阻止 implementation agent 修改 control doc，不约束 controller 自身的状态推进。

**Required fix**: 建议在 `docs/host/wu-runtime-01-filelock-contraction-plan.md` 或 gateflow 约定中明确："Explicitly forbidden" 约束只针对 implementation agent，不约束 controller 状态推进。可在后续 gateflow 文档更新时处理，不阻塞当前 PR。

**Blocking**: 否

---

### DS-PR-3 — 低 — Control doc gate 为 `ready-to-open-draft-PR`，但 draft PR 已打开

**入口/文件**: `docs/host/host-core-followup-implementation-control.md:119`

**Evidence**: Control doc `gate: ready-to-open-draft-PR`，next entry point 为 "draft PR gate：用户已授权到达 ready-to-open-draft-PR 后自动 push、创建 draft PR 并推进 PR review / fix / re-review 直到 draft-PR-pass"。当前 PR #100 已作为 draft 打开（`gh pr view 100 --json isDraft` → `true`）。按状态约定，`ready-to-open-draft-PR` 是"本轮 work unit 已完成本地 gate，等待进入 draft PR gate"，但草案 PR 已实际打开，gate 应处于 draft-PR-pass 前的过渡状态。

**Risk**: 极低。这是 control doc 状态追踪的微小 lag，不影响代码正确性、测试或 PR 合并决策。"next entry point" 描述完整 PR 流程，语义清晰。

**Required fix**: 可在 PR review 通过后将 gate 推进到 `draft-PR-pass` 时一并修正。不阻塞当前 PR。

**Blocking**: 否

---

### DS-PR-4 — 低 — `__exit__` 在 `_context_token` 为 None 时静默返回

**入口/文件**: `dayu/runtime/filelock.py:210-215`

**Evidence**: 当 `_context_token` 为 None 时（正常流程不应发生——`__enter__` 总会设置且嵌套 context 被 fail-fast 拒绝），`__exit__` 会静默返回而不抛错。此行为未在测试中显式覆盖。

**Risk**: 极低。唯一可能触发该分支的场景是 `__enter__` 中 `acquire()` 抛异常——此时 Python 不会调用 `__exit__`。当前实现是防御性编程，比旧实现（直接从 `_active_token` 读取）更安全。

**Required fix**: 无。当前实现正确。

**Blocking**: 否

---

### DS-PR-5 — advisory — Host regression 测试 lock-path 断言最小但充分

**Evidence**: `tests/host/test_audit_sink.py:361` 和 `tests/host/test_tool_trace_projection.py:353` 各新增 `assert lock_path.exists()` 断言，验证 runtime marker restore 在 Host 调用面上生效。同时 checkpoint 断言（audit:360, tool trace:351）证明 projection 正常推进。

**Risk**: 无。Plan 只要求"证明 Host 调用面通过 `with file_lock(...)` 工作"，不需要新增测试函数或覆盖多进程 contention。当前最小断言满足 Slice 2 目标。

**Required fix**: 无。

**Blocking**: 否

---

## Overdesign Check

| 检查项 | 结果 |
|---|---|
| production source 只修改 `dayu/runtime/filelock.py`？ | 是。Host 未修改。 |
| 删除 public `released`，移除 `_active_token`？ | 完全删除。`rg "released\|_active_token" dayu/runtime/filelock.py` 无命中。 |
| `_release_completed` 只在 release 成功后设置？ | 是。`filelock.py:105` 在 `self._third_party_lock.release()` 成功返回后执行。 |
| `_context_token` 只服务 context manager cleanup？ | 是。仅在 `__enter__`/`__exit__` 使用，`acquire()` 不读写。 |
| 无 stale lock / break lock / async wrapper / durable lease / Host recovery？ | 是。diff 不含任何相关代码。 |
| 无兼容 property / wrapper / facade / re-export？ | 是。`__all__` 不含 `released` / `_release_completed` / `_active_token` / `_context_token`。 |
| 无 import 反向依赖？ | 是。`dayu.runtime.filelock` 只 import 标准库和第三方 `filelock`。 |
| design.md 同步？ | 是。`RuntimeFileLockToken` API shape 删除 `released: bool`，release 段落补充失败不标成功语义。 |
| control doc 修改范围？ | 仅 gateflow 状态推进（gate / status / artifacts / RR-HCF-01），不含设计变更。 |
| 测试膨胀？ | 否。runtime tests 从 ~22 个精简为 12 个，host tests 单函数增加 ~5 行断言。 |

**结论：无过度设计。**

---

## Import Boundary 复核

- 第三方 `filelock` import 只在 `dayu/runtime/filelock.py:16`（生产）和 `tests/runtime/test_filelock.py:15`（测试 `cast()` only）
- `tests/runtime/test_import_boundary.py` 未修改，持续通过
- `tests/host/test_import_boundary.py` 未修改，持续通过
- Host production source（`dayu/host/audit.py`、`dayu/host/tool_trace.py`）不 import `filelock`
- `__all__` 不含私有字段

---

## Control Doc / Artifacts Readiness

| 检查项 | 状态 |
|---|---|
| Plan artifact | `docs/host/wu-runtime-01-filelock-contraction-plan.md` — accepted（929d01c） |
| Slice 1 implementation artifact | accepted（7b5b3aa） |
| Slice 2 implementation artifact | accepted（51648be） |
| Aggregate deepreview | DS + MiMo 双审通过，controller adjudication accepted（6980c96） |
| Plan review artifacts | 5 份（2 reviews + 2 rereviews + 1 adjudication），all pass/accepted |
| Slice 1 review artifacts | 5 份（implementation + fix + 2 code reviews + 2 rereviews + 1 adjudication），all pass/accepted |
| Slice 2 review artifacts | 5 份（implementation + 2 code reviews + 2 rereviews + 1 adjudication），all pass/accepted |
| PR review artifacts | MiMo PR review（pass-with-fixes, 0 blocking）+ 本文档（DS） |
| Control doc gate | `ready-to-open-draft-PR` — 合理；PR 正在执行 PR review gate |
| Draft PR status | 已打开为 draft（PR #100），isDraft: true, mergeable: MERGEABLE |
| Blocking open questions | none |

**结论：control doc `ready-to-open-draft-PR` 状态合理。** Gate 前进到 `draft-PR-pass` 的等待条件是两份 PR review（DS + MiMo）均通过，controller 裁决后推进。

---

## Residual Risk

| 编号 | 风险 | 分类 | Owner |
|---|---|---|---|
| RR1 | 同一 `RuntimeFileLock` 实例 reentrant / nested `acquire()` 行为不承诺（设计真源 non-goal） | accepted residual | 设计真源 |
| RR2 | Lock marker 文件不是 Host truth；marker restore 失败只 debug log | accepted residual | 设计真源 |
| RR3 | `tests/runtime/test_filelock.py` import `FileLock` 用于 `cast()` — 偏离 plan 字面约束 | accepted residual（aggregate controller adjudication） | 测试维护者 |
| RR4 | 白盒测试 `test_context_manager_release_failure_clears_context_token` 直接写入 `lock._context_token` | accepted residual（Slice 1 controller adjudication） | 测试维护者 |
| RR5 | `dayu.runtime.lane.LaneClaimToken.released` 仍为 public field | deferred to WU-RUNTIME-02 | WU-RUNTIME-02 owner |
| RR6 | 多进程 contention 回归不属于当前测试范围 | accepted residual | 集成测试 |
| RR7 | Control doc 修改与 plan "Explicitly forbidden" 声明不一致 | accepted residual（gateflow 流程正常行为） | gateflow 约定 |

---

## MiMo PR Review Findings 复核

| MiMo Finding | DS 复核 |
|---|---|
| F-1: Control doc 修改与 plan Explicitly Forbidden 不一致 | 确认。本质是 gateflow 约定边界问题，非代码问题。已在 DS-PR-2 独立记录。 |
| F-2: 20 个 review artifact 文件 | 确认。这是 gateflow 流程产物，每个 artifact 有独立 review gate 价值。不阻塞 PR。 |
| F-3: `__exit__` token 为 None 时行为 | 确认。当前实现为正确的防御性编程，无实际风险。已在 DS-PR-4 独立记录。 |
| F-4: Host regression 只覆盖 happy path | 建议结论与 DS 不一致。测试确实包含 `lock_path.exists()` 和 checkpoint 断言，覆盖了 plan 要求的最小调用面验证。DS 认为覆盖充分。 |
| F-5: Coverage 90%，未覆盖行是错误路径 | 确认。90% >= 80% 阈值，未覆盖行均在异常处理分支。 |

---

## PR Readiness

| 检查项 | 状态 |
|---|---|
| WU-RUNTIME-01 目标完整实现 | ✅ |
| RuntimeFileLock contract 与 design doc 一致 | ✅ |
| Host production source 未修改 | ✅ |
| Runtime tests pass | ✅ 23 passed |
| Host regression tests pass | ✅ 13 passed |
| Import boundary tests pass | ✅ 36 passed（全部） |
| Coverage >= 80% | ✅ 90% |
| pyright | ✅ 0 errors |
| 无过度设计 | ✅ |
| 无 scope 泄漏 | ✅ |
| 无兼容性代码 | ✅ |
| 无反向依赖 | ✅ |
| Control doc 状态合理 | ✅ |
| Gateflow commit 链完整 | ✅ |
| 遗漏文件 | 无 |
| 错误 commit | 无 |
| CI 风险 | 无（所有验证在本地已通过） |

**0 blocking findings。PR ready to advance to draft-PR-pass after controller adjudication。**
