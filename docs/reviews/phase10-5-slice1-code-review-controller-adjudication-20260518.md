# P10.5 Slice 1 Code Review Controller Adjudication

## Gate

当前 gate：P10.5 Slice 1 code review adjudication。

## Inputs

- Approved plan: `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md`
- Implementation artifact: `docs/reviews/phase10-5-slice1-implementation-codex-20260518.md`
- MiMo code review: `docs/reviews/phase10-5-slice1-code-review-mimo-20260518.md`
- DS code review: `docs/reviews/phase10-5-slice1-code-review-ds-20260518.md`
- Design truth: `docs/host/design.md`
- Control truth: `docs/host/implementation-control.md`

## Verdict

MiMo 与 DS code review 均为 PASS，blocking count = 0。Slice 1 implementation 严格限定在 public opener type surface、
export boundary、options、`HostClosedError`、terminal `HostEvent` type surface、focused tests 与必要 Host README 同步范围内；
未进入 Slice 2 runtime wiring、scheduler wakeup、live fanout、Session wrappers、steer / retry / replay、`resolve_wait`、compactor
wiring 或 ToolRuntime behavior。

总控裁决：P10.5 Slice 1 code review gate 通过，不要求当前 slice fix；进入 accepted Slice 1 local commit。

## Finding Decisions

### N1. Legacy symbols still importable as `dayu.host.<name>`

来源：MiMo N1、DS Finding 1。

裁决：accepted deferred to later slice / cleanup, not current Slice 1 fix。

理由：当前 Slice 1 已收口 `__all__` 与 star import 的普通 Service-facing export boundary。直接导入旧符号仍存在是为了避免在
Slice 1 越界迁移多个低层测试文件；后续 Slice 3 / package-root cleanup 在触及这些测试时必须迁移到内部 module path 并移除
包根模块属性。该 residual 不影响 Slice 1 typed public surface，但必须在 P10.5 phase closeout 前重新检查。

### N2. `_start_run` internal primitive not yet created

来源：DS Finding 2。

裁决：deferred to Slice 3。

理由：Slice 1 只负责从普通 Service-facing `__all__` 移除 `start_run`；`start_run` -> `_start_run` 的内部 primitive 重命名与旧测试迁移属于
Slice 3 request contract / admission boundary。

### N3. `HostClosedError` closed-handle behavior not yet tested

来源：DS Finding 3。

裁决：deferred to Slice 2。

理由：Slice 1 只新增异常类型与 public handle Protocol。concrete handle lifecycle、closed gate 与 post-close method behavior 属于 Slice 2
production composition root / lifecycle implementation。

### N4. FAILED / CANCELLED terminal payload optionality

来源：DS Finding 4。

裁决：accepted as Slice 4 implementation decision within current plan。

理由：Design truth 只要求 terminal `HostEvent` 提供 typed display fields；是否强制 failed / cancelled display text 非空应由 Slice 4 live
fanout 根据 actual terminal facts 决定，不阻塞 Slice 1 type surface。

### N5. `HostCommandHandleOptions` / `HostCommandFacet` still in `__all__`

来源：DS Finding 5。

裁决：accepted deferred to later export cleanup。

理由：当前 plan 只明确要求移除 concrete command handle / factory / local execution options / run-level stream 等普通 Service-facing 入口。
两个低层 support type 仍被现有低层测试使用；后续迁移低层测试到 internal module paths 后应一并复查是否仍需留在 package root。

## Validation Evidence

Implementation agent reported:

- `source .venv/bin/activate && pytest tests/host/test_public_open_host_options.py tests/host/test_package_exports.py -q`
  - `13 passed`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - `0 errors, 0 warnings, 0 informations`

Controller checked:

- `git diff --check`
  - passed

## Residual Risk Tracking

- Package-root direct imports for deprecated low-level symbols remain possible until later slice migrates existing tests and removes module attributes.
  Owner: Slice 3 / P10.5 export cleanup before phase closeout.
- Concrete `HostClosedError` behavior is unimplemented until Slice 2.
  Owner: Slice 2.
- `HostEvent` failed / cancelled display payload semantics remain to be finalized in live event mapping.
  Owner: Slice 4.

## Next Gate

Create accepted Slice 1 local commit, record commit hash in `docs/host/implementation-control.md`, then enter P10.5 implementation Slice 2 handoff.
