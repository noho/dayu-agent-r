# PR 190 F11/F12 S2 Accepted Checkpoint

## Gate result

- Slice：S2 — Engine generic structured output 与 config capability
- Baseline：`c8be3e5184b8b797c59458027e991f0284cbb3b5`
- Controller decision：**ACCEPTED**
- Next gate：S2 intended-files commit/push，随后进入 S3 Host compactor v3 vertical migration

## Accepted implementation

- Engine 拥有 provider-neutral `none/json_object/json_schema` capability、两个封闭 typed request
  variant 与严格 capability/request matrix；request 不含冗余 `mode` 或 `digest`。
- `AsyncRunner.call`、唯一 OpenAI-compatible Runner、Agent loop 和 payload builder 都要求显式
  `structured_output`；`None` 是合法值但不能靠省略表达。
- OpenAI-compatible transport 精确投影 `response_format`，provider 拒绝不 downgrade、不重试，
  structured-output 不进入 extra/provider extension。
- runtime config → Service → Host → RunnerSpec 全链路显式；Service owner test 锁定 runtime 与
  Engine 两个必要 enum 的完整值域和逐值机械映射。
- DeepSeek catalog 显式为 `json_object`；MiMo 与未证明 provider 为 `none`；当前无虚标
  `json_schema` catalog row。
- workspace init manifest 与 raw-byte hash 从同一 publication truth 更新。
- F11 引入的两个 Host Tool Trace canonical identity import 已在 architecture test 中以精确
  repo-relative path 登记，没有复制 identity 或宽泛 basename 豁免。

## Review adjudication

- MiMo initial review：PASS，无 finding；其违规 stash 窗口内观察全部作废并已在 artifact
  明确记录。
- DS initial review：两项 LOW finding；总控接受并完成 owner refinement。
  - DS-LOW-01：CLOSED；payload builder 无 default，owner test 锁定 required signature。
  - DS-LOW-02：CLOSED；Service owner test 锁定双 enum 同构，生产层无第三 enum/helper。
- Controller-discovered S1 import-boundary regression：CLOSED；两个指定 Host nodes 均 PASS。
- MiMo re-review：PASS，无新 finding。
- DS re-review：PASS，原两项 LOW 均 CLOSED，无新 finding。

## Accepted validation

- Required Host regression nodes：`2 passed`。
- Owner/payload focused：`35 passed`。
- Affected modified tests：稳定复跑 `1361 passed, 3 warnings`。
- Full Engine：`602 passed`。
- Full pyright：`0 errors, 0 warnings, 0 informations`。
- Modified production branch coverage：每个文件 `80%–100%`，合计 90%。
- Ruff、compileall、JSON、publication hashes、`git diff --check`：PASS。
- 一次 Host watchdog 时序失败已隔离复跑 PASS，随后完整 affected suite PASS；未因非同源、
  不可复现观察修改 cancellation owner。

## Durable artifacts

- `docs/gateflow/pr-190-f11-f12-s2-structured-output-implementation-20260805.md`
- `docs/reviews/pr-190-f11-f12-s2-mimo-code-review-20260805.md`
- `docs/reviews/pr-190-f11-f12-s2-ds-code-review-20260805.md`
- `docs/gateflow/pr-190-f11-f12-s2-code-review-adjudication-20260805.md`
- `docs/gateflow/pr-190-f11-f12-s2-review-fix-20260805.md`
- `docs/reviews/pr-190-f11-f12-s2-mimo-rereview-20260805.md`
- `docs/reviews/pr-190-f11-f12-s2-ds-rereview-20260805.md`

## Scope boundary

S2 未实现 Host compact v3 schema/prompt/parser，没有执行真实 provider observation，没有修改
frozen oracle/scenario registry。上述工作分别属于已接受的 S3、S4、S5 gate。
