# WU-CTX-04 Slice 1 code review fix artifact（AgentCodex）

## Gate metadata

- work unit：`WU-CTX-04`
- gate：implementation Slice 1 code review `fix`
- accepted finding：仅 `CR-DS-001`
- controller adjudication：
  `docs/reviews/wu-ctx-04-slice-1-code-review-controller-adjudication.md`
- branch：`feat/wu-ctx-04`
- status：`fix complete；等待独立 re-review`
- blocking open questions：None
- artifact path：`docs/reviews/wu-ctx-04-slice-1-review-fix-codex.md`
- stop boundary：本 artifact 完成后停止，不进入 re-review、accepted slice commit、Slice 2、push 或 PR。

## First-principles judgment 与 root cause

`CR-DS-001` 动机成立，但不改变原 severity 裁决：双失败时系统仍以
`StrictNativeMutexUnavailableError` fail closed，descriptor 也仍被消费，因此 busy / unavailable
与资源安全 contract 没有失效；缺陷属于低严重度的生产诊断结构丢失。

直接根因位于 partial descriptor lifecycle 的唯一 owner
`dayu.runtime.native_mutex._close_partial_file_descriptor`：旧实现把 close exception 设为外层
unavailable exception 的唯一 cause，却只把 prior native exception 的类型名写入 note。单一 cause
槽无法同时保存两个独立失败事实，字符串 note 也不拥有原异常 message、identity 或 traceback。
该判断直接来自函数的数据流，不依赖日志或下游迹象。

修复必须发生在该 owner boundary；Host registry、API、adapter 或测试夹具均不拥有 native acquire
与 partial cleanup 的组合错误语义，不能在下游补偿。

## Implementation decision

- `_close_partial_file_descriptor` 的 `prior_error` 从过宽的 `BaseException | None` 收窄为
  `Exception | None`，与所有调用点的 `except Exception` 真源一致。
- 当 prior native exception 与 close exception 同时存在时，外层仍抛出
  `StrictNativeMutexUnavailableError`，其 cause 使用 Python 3.11 内建 `ExceptionGroup`，按
  `[prior_error, close_error]` 顺序保留两个原始异常对象。两个成员各自已有的 traceback 与嵌套
  cause 均保持可达；没有字符串拼接、类型名替代、`Any`、`object`、`getattr`、`hasattr` 或兼容 shim。
- 当 `prior_error is None`（明确 busy 后 partial close 失败）时，仍由同一外层 typed unavailable
  exception 直接 chain 到 close exception；既有 busy + close failure fail-closed contract 不变。
- 未新增 public type、schema、Host state、fallback 或额外持久化语义。使用 stdlib
  `ExceptionGroup` 是表达两个独立 exception/traceback 的最小严格设计；另造异常容器类型会扩大
  public surface，字符串 note 则不能满足结构化可达要求。

## Changed files

- `dayu/runtime/native_mutex.py`：仅修改 partial descriptor 双失败的结构化异常 cause。
- `tests/runtime/test_native_mutex.py`：新增 non-busy native lock failure + close failure 精确测试；
  测试 fake 保存原始异常 identity，既有 busy + close failure 测试保留且继续执行。
- `docs/reviews/wu-ctx-04-slice-1-review-fix-codex.md`：本 fix artifact。

未修改 control doc、既有 review artifacts、Host registry/API、README 或任何 Slice 2 文件。

## Exact contract assertions

新增 `test_native_lock_and_partial_close_failures_preserve_structured_chain` 同时注入 POSIX non-busy
`EIO` native lock failure 与真实消费 descriptor 后的 `EIO` close failure，并精确断言：

1. 外层异常类型仍为 `StrictNativeMutexUnavailableError`；
2. 外层 cause 是含两个成员的 `ExceptionGroup`；
3. 第一个成员是 native lock unavailable error，其 cause 与 fake 抛出的原始 `OSError` identity 相同；
4. 第二个成员与 close fake 抛出的原始 `OSError` identity 相同；
5. prior wrapper、原始 native `OSError` 与原始 close `OSError` 的 traceback 均非空；
6. partial descriptor close 只调用一次。

既有 `test_partial_fd_cleanup_failure_overrides_busy_outcome` 未删除、未弱化，继续证明明确 busy 后
close 失败不能返回 `None`，必须 fail closed 为 typed unavailable。

## Validation

- 关键双路径：
  `pytest tests/runtime/test_native_mutex.py::test_native_lock_and_partial_close_failures_preserve_structured_chain tests/runtime/test_native_mutex.py::test_partial_fd_cleanup_failure_overrides_busy_outcome -q`
  → `2 passed in 0.04s`。
- Slice 1 focused pytest：
  `pytest tests/runtime/test_native_mutex.py tests/runtime/test_import_boundary.py tests/host/test_session_attachment_registry.py -q`
  → `44 passed in 1.45s`。
- targeted pyright：
  `python -m pyright dayu/runtime/native_mutex.py dayu/host/session_attachment.py tests/runtime/test_native_mutex.py tests/host/test_session_attachment_registry.py`
  → `0 errors, 0 warnings, 0 informations`。
- 两个新增 production module coverage：
  `pytest tests/runtime/test_native_mutex.py tests/host/test_session_attachment_registry.py --cov=dayu.runtime.native_mutex --cov=dayu.host.session_attachment --cov-report=term-missing -q`
  → `30 passed in 0.51s`；`dayu/runtime/native_mutex.py=92%`，
  `dayu/host/session_attachment.py=86%`，均未回归且保持 `>=80%`。
- targeted Ruff：
  `python -m ruff check dayu/runtime/native_mutex.py dayu/host/session_attachment.py tests/runtime/test_native_mutex.py tests/runtime/test_import_boundary.py tests/host/test_session_attachment_registry.py`
  → `All checks passed!`。
- final git diff / whitespace / changed-files audit：见下节最终审计结果。

以上命令均在 `source .venv/bin/activate` 后运行。

## Final audit

- `git diff --check` → exit `0`，tracked diff 无 whitespace error。
- 对三个授权且 untracked 的文件分别运行
  `git diff --no-index --check /dev/null <file>` → 均无 whitespace error 输出；exit `1` 仅表示
  文件相对 `/dev/null` 存在预期差异。
- `git diff --stat` 仍只列出 preflight 时已经存在的四个 tracked dirty file：
  `dayu/host/api.py`、`dayu/runtime/__init__.py`、
  `docs/host/issues-implementation-control.md`、`tests/runtime/test_import_boundary.py`；本 fix
  未写入这些文件。
- 对三个授权文件执行 no-index diff/stat 并检查完整内容：
  `dayu/runtime/native_mutex.py`、`tests/runtime/test_native_mutex.py` 与本 artifact 均为预期差异。
- 最终 `git status --short` 与 preflight 集合相比只新增本次授权创建的 fix artifact；其余既有
  dirty / untracked path 集合不变。changed-files audit 未发现 control doc、既有 review artifact、
  Host registry/API、README 或 Slice 2 文件被本 fix 新增或改写。

## README decision

不修改 README。此次修复没有新增测试层级、测试运行方式或维护规则，不触发
`tests/README.md` 的更新边界；也没有用户可见入口、分层、装配或公共行为变化。用户同时明确禁止
修改 README。

## Unhandled findings 与依据

- `CR-MIMO-001`：总控已 `rejected-with-reason`；Microsoft `_locking` 证据确认 `_LK_NBLCK`
  contention 的 `EACCES` fake 合法，本 fix 不改 Windows errno 测试。
- `CR-MIMO-002`：总控已 `rejected-with-reason`；release retry 只遍历仍 fail-closed 的 record，
  额外状态不属于当前必要修复。
- `CR-MIMO-OQ-001`：总控已 `rejected-with-reason`；多个 recovery work lease 是计数式 drain
  contract 的有意能力。
- `CR-DS-002`：总控已 `rejected-with-reason`；Host close API 不要求聚合多个 release 错误，
  本 fix 不扩大 Host error contract。
- `CR-DS-003`：总控已 `rejected-with-reason`；`ATTACHMENT_CLOSING` 属于 Host registry 全局
  closing gate 的有意语义。

本 fix 不重新裁决、不接受也不处理上述 finding。

## Residual risks 与 uncovered areas

- `covered by later approved slice`：真实 Windows 环境的 `msvcrt.locking`、lock-byte 与 cleanup
  组合验证仍由 WU-CTX-04 Slice 3 final matrix / CI owner 承担；本 fix 没有改变 Windows backend
  分支，只改变跨 backend 共用 cleanup helper 的异常结构。
- `covered by later approved slice`：`dayu/host/api.py` 全文件 coverage 与 Host close failure matrix
  仍按总控裁决留给 Slice 2/3；本 fix 未修改 Host 代码。
- 当前 fix 的结构化异常链已由 exact identity + traceback assertions 覆盖，没有未分类 residual risk。

## Completion status

- `CR-DS-001` fix-side 状态：`已修复`；最终 finding 状态等待 AgentMiMo 与 AgentDS 独立 re-review。
- fix gate validation：`pass`。
- next entry point：`re-review`，但按用户明确 stop boundary 本 Agent 不进入该 gate。
