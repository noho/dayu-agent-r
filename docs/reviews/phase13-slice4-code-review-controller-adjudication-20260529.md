# Phase 13 Slice 4 Code Review Controller Adjudication

## Gate

Phase 13 Slice 4 `Public Outbox Read / Drain API And Offline Smoke` code review adjudication。

## Inputs

- Implementation artifact: `docs/reviews/phase13-slice4-implementation-codex-20260529.md`
- AgentMiMo review: `docs/reviews/phase13-slice4-code-review-mimo-20260529.md`
- AgentDS review: `docs/reviews/phase13-slice4-code-review-ds-20260529.md`
- Accepted plan: `docs/host/phase13-audit-tool-trace-outbox-plan.md`
- Design truth: `docs/host/design.md`

## Verdict

**PASS**。两路 code review 均为 PASS，无 blocking findings。Slice 4 可以进入 accepted local commit。

## Controller Decision

### MiMo F001: drain exact replay public path 未显式测试

裁决：non-blocking test-hardening。

理由：durable helper 已覆盖 drain exact replay，Slice 4 public tests 覆盖 conflict、EventLog 不写、drain state 与 smoke 去重窗口。缺少 public exact replay 断言不会改变当前 correctness。可在后续测试维护中补充，不要求当前 fix pass。

### MiMo F002: `tests/README.md` 未更新

裁决：not an issue。

理由：新增测试仍属于已有 Host public API / smoke test 类型，没有新增测试分层、运行方式或维护约定。根据 README 触发规则，检查后无需更新 `tests/README.md`。

### DS NB-1: catch-up 外围 `except Exception` 过宽

裁决：accepted residual。

理由：Outbox public read/drain 的契约需要在 projection catch-up 失败时返回 `FAILED` 状态，而不是把已有 projected rows 完全遮蔽。`ProjectionRunner` 内部可记录 structured failure row；外围 catch 只覆盖无法写 failure row 的逃逸异常，并把异常类型名与消息暴露给调用方。当前不引入新的 public error enum，避免扩大 API surface。若未来 Service 需要程序化区分 projection failure 类型，再做结构化错误枚举。

### DS NB-2: smoke 测试 white-box 依赖 durable 内部

裁决：accepted test coupling。

理由：这些测试用于证明 drain 不写 EventLog、close flush 写入 outbox projection row，需要 white-box 验证 durable side effect。它们不污染生产 API，也不要求兼容 wrapper，当前可接受。

### DS NB-3: seen ids 数量上限缺少 public test

裁决：non-blocking test-hardening。

理由：public request validation 已集中在 dataclass `__post_init__`，并覆盖 limit 越界、负 cursor、重复 seen ids 等同类边界。seen ids 最大长度测试可后续补充，不阻塞 gate。

## Validation Required Before Commit

Controller 在创建 accepted commit 前需重新运行：

- `source .venv/bin/activate && pytest tests/host/test_public_outbox_api.py tests/host/test_public_offline_outbox_smoke.py tests/host/test_package_exports.py tests/host/test_open_host_runtime.py -q`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
- `git diff --check`

## Outcome

无需 fix pass。通过验证后创建 accepted Slice 4 local commit。Phase 13 accepted plan 仅包含 Slice 1-4；Slice 4 accepted 后进入 Phase 13 final readiness / ready-to-open-draft-PR gate。
