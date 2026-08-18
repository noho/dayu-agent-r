# UF-FIX01 fiscal-period prevalidation residual — S2 Code Review Adjudication

## Gate metadata

- work unit：`UF-FIX01-fiscal-period-prevalidation-residual`
- slice：`S2-entry-contracts-docs`
- base：`f6b2d04c`
- MiMo review：`docs/reviews/code-review-20260818-015216.md`
- DS review：`docs/reviews/code-review-20260818-020808.md`
- final status：`fix-required`
- next entry point：AgentCodex S2 review fix

## Findings adjudication

| Source / finding | Controller decision | Required action / reason |
|---|---|---|
| MiMo 001：schema 应增加 `enum` | `rejected-with-reason` | `fiscal_period` 是 filing/material 共享字段，material optional metadata 当前没有六值闭集 admission；增加 enum 会未经授权收窄 material。accepted plan 要求自足 description，不要求 schema enum。 |
| MiMo 002：`upload_runner is None` 不是 runner 零调用证明 | `accepted` | 删除结构性常量断言；在现有 static-admission guard runtime 中装配 module-level forbidden/recording `FinsUploadRunner` seam，并断言非法输入零调用。runner 未被调用即可证明其后的 converter 不可达。 |
| DS 001：schema “只支持六值”未限域 upload_kind | `accepted` | 最小改为“上传 filing 时必填且只支持 FY、H1、Q1、Q2、Q3、Q4；上传 material 时可选”，同步 exact schema test 与 tests README，禁止修改 material admission。 |
| DS 002：canonical observation 测试固化三层 private/raw 表示 | `accepted` | 改为 runner contract boundary：合法 raw tool request 经 prepare/activate 后，由 recording runner 接收 `ValidatedFinsUploadFilingRequest` 并断言 `normalized_fiscal_period`；不得断言 raw request 必须保持非 canonical，也不得 import `_DirectUploadProducer`。使用可控 executor 并在断言后 abandon/清理 observation。 |

## Open-question adjudication

1. durable `_upload_request_summary` 使用 raw fiscal period，而 pipeline 使用 canonical：`deferred-with-owner`。
   这是既有 legacy job summary 语义，不是本 S2 schema/test diff 引入；若要改需把 durable audit/raw 与 canonical
   business fact 的字段契约单独澄清并扩展 production/test scope。本轮不在未审 plan 中修改 `ingestion_runtime.py`。
2. tool failure reason 使用 CLI 风格 `--fiscal-period`：`rejected-with-reason`。usage projection 当前是 CLI/tool
   共用 closed contract，用户目标要求入口复用同一真源和具体 reason；为 tool 另做文案分支会制造第二真源。

## Other evidence disposition

- reviewer 全量 `tests/fins tests/cli` 发现 5 个失败，已在 base `f6b2d04c` 独立 worktree 复现，归类为
  pre-existing / unrelated；本 work unit 不改 `test_init_workspace.py` 或 `test_upload_filings_from_command.py`。
- coverage reviewer 复测为 `92%/89%/93%`，implementation 的 affected suite 口径为 `91%/89%/93%`；两者均
  超过 80%，差异来自测试集合，不构成 finding。最终 closeout 以 accepted plan 的 822-test exact command 复测。

## Fix acceptance criteria

- 只改 `dayu/fins/tools/upload_tools.py`、`tests/fins/test_fins_ingestion_tools.py`、`tests/README.md` 和 S2 fix artifact；
  若其余 S2 文件无需响应 finding，不得改动。
- schema 对 filing 六值闭集自足，material 仅保留 optional 声明。
- invalid tool path 在已装配 forbidden runner 下仍无 state/executor/observation/job/workspace mutation，runner calls 为空。
- valid tool path 通过 recording runner 只断言 typed canonical contract，不 pin raw/private producer 表示，并清理 observation。
- focused tests、S1+S2 affected suite、coverage、全仓 pyright 与 diff-check 通过后再 re-review。
