# WU-RUNTIME-01 Aggregate Controller Adjudication

## 结论

WU-RUNTIME-01 aggregate deepreview 通过。当前分支相对 `main` 的已提交 diff 可进入 `ready-to-open-draft-PR`。

## Review 结果

- `docs/reviews/wu-runtime-01-aggregate-deepreview-mimo-20260601.md`：`pass`，0 个 blocking finding。
- `docs/reviews/wu-runtime-01-aggregate-deepreview-ds-20260601.md`：`pass`，0 个 blocking finding，1 个 medium non-blocking finding。

## Finding 裁决

| Finding | 裁决 | 理由 |
|---|---|---|
| DS Aggregate Finding 1：`tests/runtime/test_filelock.py` 直接 import 第三方 `FileLock` 用于 `cast()` | accepted residual | 基于设计目标和第一性原理，生产 import boundary 的风险是 `dayu.*` 业务 / runtime 外层直接依赖第三方 `filelock`；当前 import 只在 runtime wrapper 单元测试中为构造 typed test double 服务，不进入 production code。替代方案需要新增 Protocol、测试 seam 或弱化类型，反而扩大设计。本 residual owner 为 runtime test maintenance，若未来项目要求测试也禁止直接 import，可单独收敛测试 typing。 |

## 通过依据

- `RuntimeFileLockToken.released` 已从 public API、设计真源和 runtime tests 中删除，无兼容 property / wrapper / facade。
- `_active_token` 与 acquire gate 已移除；`acquire()` 不读写 `_context_token`。
- `_context_token` 只服务 context manager cleanup，nested context 只做最小 fail-fast，未恢复旧 lifecycle truth。
- `docs/host/design.md` 已同步 public API shape 与 release 失败不标成功语义。
- Host production source 未修改；Slice 2 只通过 Host tests 验证 explicit `lock_path` 调用面。
- 没有 stale lock、break lock、async wrapper、durable lease、Host recovery、lane 或 audit/tool trace behavior 重构。

## 验证

已由 implementation / review agents 运行并复核：

```bash
source .venv/bin/activate && pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q
source .venv/bin/activate && pytest tests/runtime/test_filelock.py --cov=dayu.runtime.filelock --cov-report=term-missing
source .venv/bin/activate && pytest tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py -q
source .venv/bin/activate && pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py -q
source .venv/bin/activate && pyright
```

结果：runtime / import boundary / Host regression tests 通过，`dayu.runtime.filelock` 覆盖率 90%，pyright 0 errors。

## Residual Risk

| 风险 | 状态 | Owner / Destination |
|---|---|---|
| 同一 `RuntimeFileLock` 实例手动 `acquire()` reentrant 行为不承诺 | closed | 设计真源明确 non-goal；context manager nested misuse 已最小 fail-fast。 |
| Lock marker 文件不是 Host truth | closed | 设计真源明确 marker 只属于普通文件互斥可见痕迹，不驱动 Host truth。 |
| runtime filelock 单元测试直接 import `FileLock` 用于 `cast()` | deferred-with-owner | runtime test maintenance；当前不修，避免为测试 typing 引入额外 seam。 |
| `dayu.runtime.lane` 的 `LaneClaimToken.released` | deferred-with-owner | WU-RUNTIME-02；不属于本 work unit。 |

## 下一步

更新总控文档为 `ready-to-open-draft-PR`。用户已在本轮开头授权到达该 gate 后自动进入 draft PR gate 并推进到 `draft-PR-pass`；因此 accepted deepreview commit 后可继续 push、创建 draft PR、执行 PR review / fix / re-review。
