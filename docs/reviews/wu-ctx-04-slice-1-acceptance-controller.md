# WU-CTX-04 Slice 1 acceptance（Controller）

## Gate metadata

- work unit：`WU-CTX-04`
- slice：`1/3`
- accepted plan commit：`1f032b5e2d1aba974304ee4537be76ed4a1174e6`
- implementation artifact：`docs/reviews/wu-ctx-04-slice-1-implementation-codex.md`
- first reviews：`docs/reviews/code-review-20260722-124340.md`、
  `docs/reviews/code-review-20260722-124418.md`
- first adjudication：
  `docs/reviews/wu-ctx-04-slice-1-code-review-controller-adjudication.md`
- fix artifact：`docs/reviews/wu-ctx-04-slice-1-review-fix-codex.md`
- re-reviews：`docs/reviews/code-review-20260722-125826.md`、
  `docs/reviews/code-review-20260722-125901.md`
- decision：`pass`
- blocking open questions：None

## Controller decision

Slice 1 contract-only handoff 通过。strict-native mutex 的机械互斥 owner、Host internal
attachment registry 的 access/lifecycle owner、内部 API value types 与 owner-level tests
均已按 accepted plan 落地，未公开 `Host.attach_session`、未修改 `Host` Protocol、包根
export、scheduler、recovery 或既有 production call path。

首轮 review 共提出 5 个 findings 与 1 个 open question：

- `CR-DS-001` 被接受为低严重度诊断缺口；AgentCodex 已在
  `_close_partial_file_descriptor` owner boundary 修复，外层 typed unavailable contract
  不变，通过 `ExceptionGroup` cause 同时保留 prior native error 与 partial close error 的
  identity、cause 和 traceback。
- `CR-MIMO-001`、`CR-MIMO-002`、`CR-DS-002`、`CR-DS-003` 均按首轮总控
  adjudication `rejected-with-reason`；没有新实际代码证据触发重开。
- recovery 多 lease open question 已关闭：这是计数式 drain contract 的有意能力。

AgentMiMo 与 AgentDS 的独立 re-review 均把 `CR-DS-001` 判定为 `fixed`，并且均未发现
new findings、blocking 或 open questions。Controller 复读修复实现、精确测试与两个
re-review artifact 后同意该结论。

## Accepted implementation

- `dayu/runtime/native_mutex.py`：stdlib-only POSIX `flock` / Windows
  `msvcrt.locking` nonblocking mutex；busy closed set、unsupported/unexpected fail-closed、
  Windows lock-byte、partial FD cleanup、进程退出释放与幂等 handle close。
- `dayu/host/session_attachment.py`：canonical DB/Session key、
  RECOVERING/ACTIVE/CLOSING/CLOSED、唯一 live record、不可变 RW/RO、mutation/new-work/
  recovery lease、共享 attachment cleanup、Host-close mark/drain/release barrier。
- `dayu/host/api.py`：仅增加内部所需的 access mode、rejection reason 与 closed-union
  error detail；未进入 package-root public surface。
- owner contract tests：覆盖 native/process/race/failure/cancellation/close/Host-close 与
  import boundary；MIMO-003 未发现实际测试弱化证据。

## Validation

- Controller independent focused pytest：`44 passed`。
- Controller independent accepted-fix key paths：`2 passed`。
- Controller independent全量 pyright（修复前）：`0 errors, 0 warnings, 0 informations`。
- Controller independent fix-target pyright：`0 errors, 0 warnings, 0 informations`。
- AgentCodex final focused pytest：`44 passed`。
- AgentCodex targeted pyright：`0 errors, 0 warnings, 0 informations`。
- AgentCodex coverage：`native_mutex.py=92%`、`session_attachment.py=86%`。
- AgentCodex runtime suite：`594 passed`；API/export/weak typing matrix：`65 passed`。
- Controller post-fix runtime suite：`595 passed`；Controller post-fix全量 pyright：
  `0 errors, 0 warnings, 0 informations`。
- 两路 re-review 各自复跑 focused pytest：均 `44 passed`；pyright：均 `0 errors`。
- Ruff、tracked/untracked whitespace 与 changed-files audit：通过。

## README decision

本 Slice 不更新 README。`dayu/host/README.md` 只记录当前已实现且稳定的 public contract/
production path；Slice 1 明确是未装配、未公开的 internal checkpoint，提前写入会把未来行为
误写为当前事实。`tests/README.md` 的测试层级、运行方式与维护规则没有变化。accepted plan
要求在 Slice 3 对最终 production wiring 统一执行 README audit。

## Residual risk

- 真实 Windows `msvcrt.locking` 环境验证：classified，owner=`Slice 3 final matrix / CI`。
- `dayu/host/api.py` 全文件 coverage：classified，owner=`Slice 3 final matrix`；本 Slice
  新增 value type 分支已执行。
- public attachment、target recovery、proactive single-operation、scheduler/Host close
  production wiring：不是 Slice 1 缺口，分别属于 accepted Slice 2/3。
- unclassified residual risk：None。

## Completion status

- Slice 1 review loop：`pass`。
- Slice 1 accepted commit：待本 artifact 与当前 gate scope 一并创建。
- next gate after accepted commit：implementation Slice 2/3。
