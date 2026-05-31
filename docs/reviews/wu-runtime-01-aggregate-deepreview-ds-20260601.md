# WU-RUNTIME-01 Aggregate Deep Review — AgentDS

## Scope

- Mode: current changes
- Branch: `refactor/wu-runtime-01-filelock-contraction`
- Base: `main`
- Review date: 2026-06-01
- Output file: `docs/reviews/wu-runtime-01-aggregate-deepreview-ds-20260601.md`
- Design source: `docs/host/design.md`
- Control doc: `docs/host/host-core-followup-implementation-control.md`
- Plan: `docs/host/wu-runtime-01-filelock-contraction-plan.md`
- Included scope: `dayu/runtime/filelock.py`、`tests/runtime/test_filelock.py`、`tests/host/test_audit_sink.py`、`tests/host/test_tool_trace_projection.py`、`docs/host/design.md`、`docs/host/host-core-followup-implementation-control.md`
- Excluded scope: `AGENTS.md` 和 `CLAUDE.md`（pre-existing user changes，不属于 WU committed diff）；`dayu/runtime/lane.py` 中的 `LaneClaimToken.released`（属于 WU-RUNTIME-02）
- Prior review artifacts: 18 份（plan review × 2, plan rereview × 2, plan controller adjudication, slice1 implementation, slice1 fix, slice1 code review × 2, slice1 code rereview × 2, slice1 controller adjudication, slice2 implementation, slice2 code review × 2, slice2 code rereview × 2, slice2 controller adjudication）
- Prior reviews conclusion: Slice 1 `pass`/`pass-with-fixes`，Slice 2 `pass`/`pass-with-fixes`，rereviews 均为 `pass`，controller 均 accepted

## Validation Summary

| 验证项 | 命令 | 结果 |
|---|---|---|
| runtime filelock + import boundary 测试 | `pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q` | 23 passed |
| runtime filelock 覆盖率 | `pytest tests/runtime/test_filelock.py --cov=dayu.runtime.filelock --cov-report=term-missing` | 12 passed，90% |
| host audit + tool trace 测试 | `pytest tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py -q` | 4 passed |
| host import boundary 测试 | `pytest tests/host/test_import_boundary.py -q` | 13 passed |
| 全量组合测试 | `pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py -q` | 36 passed |
| pyright | `pyright` | 0 errors, 0 warnings, 0 informations |

## Contract Decisions Verification

### RuntimeFileLockToken.released — removed

- **生产代码**：`dayu/runtime/filelock.py` 中 `RuntimeFileLockToken` dataclass 不再有 `released` 字段（line 65-74），用私有 `_release_completed: bool` 替代（line 74）。
- **测试确认**：`test_public_api_shape_and_non_goals_are_explicit`（test_filelock.py:272）断言 `"released" not in token_field_names` 且 `public_token_field_names == {"lock_path"}`。
- **设计真源**：`docs/host/design.md`（line 257-259）API shape 不再列出 `released: bool`，line 291-292 说明 token 只暴露 `lock_path` 与 `release()`，不暴露 release 状态。
- **兼容性**：无 compat property、无 wrapper、无 re-export、无 facade。`__all__`（filelock.py:325-332）不含任何 `released` 或 `_release_completed`。
- **残留检查**：`rg "released|_active_token" dayu/` 仅命中 `dayu/runtime/lane.py` 中 `LaneClaimToken.released`（属于 WU-RUNTIME-02）和 `dayu/host/admission.py` 中 `released_active_slot`（Host 语义，与 filelock 无关）。`dayu/runtime/filelock.py` 无 `released` 或 `_active_token` 引用。PASS。

### RuntimeFileLock._active_token — removed

- **生产代码**：`RuntimeFileLock.__slots__`（line 127）为 `("_context_token", "_third_party_lock", "options")`，不再包含 `_active_token`。`acquire()`（line 148-180）不再检查 `_active_token`，不再保存 active token。
- **测试确认**：`test_public_api_shape_and_non_goals_are_explicit` 断言 `"_active_token" not in RuntimeFileLock.__slots__`。
- PASS。

### _context_token — context manager cleanup guard only

- **`__enter__()`**（line 189-190）：`if self._context_token is not None: raise RuntimeFileLockError("...不支持嵌套")`。这是 nested context manager misuse 的 fail-fast guard，只检查私有 slot，不读取任何 public lifecycle 状态。
- **`acquire()`**（line 148-180）：**不读取也不写入 `_context_token`**。手动 `acquire()` 路径与 context manager lifecycle 完全解耦。
- **`__exit__()`**（line 210-215）：通过 `_context_token` 找到 `__enter__()` 返回的同一 token 调用 `release()`，并在 `finally` 块中清空 `_context_token`，保证异常路径也清理。
- **`_context_token` 不暴露**：不在 `__all__` 中（line 325-332），不在 `RuntimeFileLockToken` fields 中（test_filelock.py:287 断言），外部不可访问。
- 这**不是**旧 `_active_token` acquire gate 的复辟：旧 gate 在 `acquire()` 中基于 `released` 拒绝所有同实例 acquire（包括手动 acquire）；新 guard 只在 `__enter__()` 中拒绝嵌套 context，手动 acquire 不受限（`test_manual_release_allows_same_instance_reacquire` 确认）。
- PASS。

### release 失败行为 — 不标记成功，允许 retry

- **生产代码**：`RuntimeFileLockToken.release()`（line 91-114）中 `self._release_completed = True`（line 105）只在 `self._third_party_lock.release()` 成功返回后执行。底层 release 抛错（line 103-104）时直接 raise，不设置 `_release_completed`。
- **测试确认**：`test_release_failure_does_not_complete_and_allows_retry`（test_filelock.py:238-256）：第一次 release 失败抛 `RuntimeFileLockError`，第二次 release 同样失败抛 `RuntimeFileLockError`，`third_party_lock.release_calls == 2`——证明失败被重试，未标记成功。
- **设计真源**：`docs/host/design.md` line 292："第三方 release 失败时不得把 token 标记为成功 release，后续调用必须仍能再次尝试底层 release"。
- PASS。

### 幂等 release

- **生产代码**：`if self._release_completed: return`（line 98-99）保证成功 release 后的重复调用是空操作。
- **测试确认**：`test_release_is_idempotent`（test_filelock.py:200-209）验证重复 release 不抛错；`test_release_success_before_marker_failure_remains_idempotent`（test_filelock.py:212-235）验证底层 release 成功、marker restore 失败后，重复 release 不再调用底层 release（`release_calls == 1`）。
- PASS。

### Host 调用面一致性

- **audit**：`dayu/host/audit.py` 未修改（确认 diff 不含）。`test_jsonl_line_contains_required_audit_fields`（test_audit_sink.py:317）通过 `LogAuditSinkOptions(lock_path=lock_path)` 显式传入 lock path，验证 JSONL append 成功、lock marker 存在、checkpoint 正确。
- **tool trace**：`dayu/host/tool_trace.py` 未修改（确认 diff 不含）。`test_tool_call_chain_projects_hot_rows_and_cold_lines`（test_tool_trace_projection.py:255）通过 `ToolTraceSinkOptions(lock_path=lock_path)` 显式传入 lock path，验证 cold JSONL 追加、hot row 写入、lock marker 存在、checkpoint 正确。
- 两测试均不导入第三方 `filelock`、不读取 token、不 mock runtime internals。
- PASS。

## Findings

### 编号-1-中 — 测试文件直接导入第三方 `FileLock` 用于类型 cast

- **入口/函数**: `tests/runtime/test_filelock.py:15` — `from filelock import FileLock`
- **输入场景**: 测试需要构造 `RuntimeFileLockToken(lock_path=..., third_party_lock=cast(FileLock, test_stub))` 以注入 `_CountingThirdPartyLock` / `_FailingThirdPartyLock` 替身。
- **实际分支**: 测试文件 import `FileLock` 只用于 `cast()` 类型断言，不调用其方法，不绕过 runtime wrapper。
- **直接证据**: test_filelock.py:15 导入，line 174-177、226-229、244-247 使用 `cast(FileLock, ...)`。
- **影响**: 不是生产 import boundary 突破（import boundary 测试 `test_third_party_filelock_import_is_confined_to_runtime_filelock` 只扫描 `dayu/` 目录），不引入安全或正确性风险。但违反了 plan §4 "第三方 `filelock` import 仍只在 `dayu.runtime.filelock`" 的字面约束，且测试替身耦合到第三方类型的 `cast()` 而非 protocol/interface。
- **建议改法和验证点**: 可接受为当前切片的最小测试方案。替代方案（定义 `Protocol` 类、用 `Any` cast、在 `dayu.runtime.filelock` 导出测试用替身工厂）均引入不必要的抽象或类型弱化。此方案已在 Slice 1 DS code review Finding 2 以类似形式提起，controller 将其归类为 accepted residual。
- **修复风险（低）**: 若后续要求完全消除测试文件中的 `FileLock` import，可通过引入 `_LockProtocol` 协议或把替身构造移到 `filelock.py` 的 `_TEST_ONLY` 导出。但这属于类型洁癖而非正确性修复。
- **严重程度（中）**: 非 blocking，但需在 artifact 中记录为已知偏差。

## Overdesign Check

| 检查项 | 结果 |
|---|---|
| 是否只做了 contract 收缩？ | 是。唯一生产代码变更 `dayu/runtime/filelock.py`：删除 `released`、移除 `_active_token`、增加 `_release_completed`（私有幂等 guard）、增加 `_context_token`（私有 context cleanup guard）、增加 `__enter__()` fail-fast（nested context guard）。无新 public field/method/class。 |
| 是否扩大了 stale lock / break lock / async wrapper / durable lease / Host recovery？ | 否。diff 不含任何 stale lock 探测、owner pid 解析、强制 break lock、async context manager、线程池隐藏、durable lease、fencing token、Host recovery 或 EventLog ordering 代码。 |
| 是否修改了 Host production source？ | 否。`dayu/host/audit.py` 和 `dayu/host/tool_trace.py` 未变。 |
| 是否让 RuntimeFileLock 承担 lane / admission / checkpoint 语义？ | 否。`_context_token` 只在 `__enter__`/`__exit__` 内使用，不参与 lane 语义、admission gate、checkpoint 或任何 Host 治理决策。 |
| 是否有兼容性代码（wrapper/facade/re-export）？ | 否。无 `released` property、`_active_token` compat alias、旧接口转发或 re-export。 |
| 是否在 `dayu.runtime.filelock` 中引入了对 Engine/Host/Service/UI/Fins 的 import？ | 否。import 列表（line 10-16）只有标准库和第三方 `filelock`。 |
| 计划外修改？ | Slice 1 DS review Finding 1（nested `__enter__` 覆盖 `_context_token`）触发了最小修复：`__enter__()` 增加 fail-fast guard。该修复只增加一个 `if` + `raise`，不恢复 `_active_token` gate，不影响 `acquire()`，在 controller adjudication 中 accepted。不算 overdesign。 |
| 测试膨胀？ | 否。Slice 1 runtime tests 从 ~22 个变为 12 个（删除了 3 个旧 gate 测试、合并了 manual acquire 测试、新增 nested context fail-fast 测试和 public shape 测试）。Slice 2 host tests 只增加了最小断言（`lock_path`、`checkpoint`、`lock_path.exists()`）。 |
| `docs/host/design.md` 变更范围？ | 只删除 `RuntimeFileLockToken` API shape 中的 `released: bool`，并在 release 段落补充 token 不暴露 release 状态和 release 失败行为说明。不涉及其它章节。 |
| 控制文档变更范围？ | `docs/host/host-core-followup-implementation-control.md` 只更新 WU-RUNTIME-01 状态（gate → implementation、artifacts 列表、RR-HCF-01 状态），属于 controller gate 推进的标准维护，不引入设计偏移。 |

**结论：无过度设计。** 所有变更严格按 plan §4（Public Contract Decision）和 §5（Implementation Decisions）执行，唯一的 deviation（nested context fail-fast）是最小正确性修复，已通过 controller adjudication。

## Import Boundary Verification

- 第三方 `filelock` import 只在 `dayu/runtime/filelock.py:16`：`from filelock import FileLock, Timeout`。
- 测试文件 `tests/runtime/test_filelock.py:15` import `FileLock` 仅用于 `cast()`——不构成生产 import boundary 突破（import boundary 测试 `test_third_party_filelock_import_is_confined_to_runtime_filelock` 只扫描 `dayu/` 目录）。
- `tests/runtime/test_import_boundary.py` 全部通过。
- `tests/host/test_import_boundary.py` 全部通过。
- Host production source（`dayu/host/audit.py`、`dayu/host/tool_trace.py`）未导入 `filelock`。
- `__all__`（filelock.py:325-332）不包含 `_context_token`、`_release_completed`、`_active_token` 或 `released`。

## Control Doc / Artifacts Readiness

| 检查项 | 状态 |
|---|---|
| Plan gate | accepted（929d01c） |
| Slice 1 implementation gate | accepted（7b5b3aa） |
| Slice 2 implementation gate | accepted（51648be） |
| Plan review artifacts | 2 plan reviews + 2 rereviews + controller adjudication（all pass/accepted） |
| Slice 1 review artifacts | 2 code reviews + 2 rereviews + controller adjudication（all pass/accepted） |
| Slice 2 review artifacts | 2 code reviews + 2 rereviews + controller adjudication（all pass/accepted） |
| Aggregate deepreview | 本文档（DS），另需 MiMo 独立 aggregate review |
| Control doc state | gate = `implementation`，next entry point = aggregate deepreview |
| Blocking open questions | 无 |

**结论：artifacts 齐备，足以进入 ready-to-open-draft-PR 前状态。** 触发条件：controller 收到两份 aggregate deepreview（DS + MiMo）后，按控制文档约定裁决。

## Residual Risks

| 编号 | 风险 | 分类 | Owner |
|---|---|---|---|
| RR1 | 同一 `RuntimeFileLock` 实例的 reentrant / nested `acquire()` 行为不承诺（非目标）。设计真源明确 wrapper 不承诺 reentrant lock 语义，交由第三方 `FileLock` 决定。 | accepted residual | 设计真源 |
| RR2 | Lock marker 文件不是 Host truth；marker restore 失败只 debug log，不升级为 durable failure。 | accepted residual | 设计真源 |
| RR3 | 测试文件 `tests/runtime/test_filelock.py` 直接 import `FileLock` 用于 `cast()`——非 production boundary 突破，但偏离 plan 字面约束。 | accepted residual（DS Finding 1） | 测试维护者 |
| RR4 | `test_context_manager_release_failure_clears_context_token` 直接访问私有 `_context_token`——低风险白盒测试，`_context_token` 不暴露在 public API。 | accepted residual（Slice 1 DS Finding 2, controller accepted） | 测试维护者 |
| RR5 | `dayu.runtime.lane` 中 `LaneClaimToken.released` 仍为 public field——属于 WU-RUNTIME-02，不在本 WU 范围内。 | deferred to WU-RUNTIME-02 | WU-RUNTIME-02 owner |
| RR6 | 多进程 contention 回归不属于当前测试覆盖范围（runtime tests 覆盖 non-blocking timeout 包装，host tests 覆盖单进程调用面）。 | accepted residual | 集成测试 |

## Conclusion

**pass**

WU-RUNTIME-01 完整 diff 审查结论：实现严格按 accepted plan 执行，只收缩 RuntimeFileLock wrapper 的 public contract（删除 `released`、移除 `_active_token`、增加私有 context manager cleanup guard）、不引入过度设计（无 stale lock takeover / break lock / async wrapper / durable lease / Host recovery）、无兼容 wrapper/facade/re-export、无生产 import boundary 突破。Runtime tests（90% coverage）、host regression tests、import boundary tests、pyright 全部通过。`docs/host/design.md` 同步更新，与控制文档一致。所有 prior review findings 已 closed 或 accepted residual。

**Blocking findings: 0**
