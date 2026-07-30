# WU-CLI-INIT-01 S5-B Implementation

## Gate metadata

- Work unit：`WU-CLI-INIT-01`
- slice：`S5-B live provider matrix`
- gate：implementation / oracle correction
- baseline commit：`44171fdfbf2cd09add62be0465052723db21efeb`
- 日期：2026-07-30
- 状态：**PASS**
- frozen oracle：`cli.init.workspace-initialization@1`
- artifact path：
  `docs/reviews/wu-cli-init-01-s5b-implementation-codex.md`

## Scope 与裁决

用户已明确裁决：Host SQLite 及其 WAL 持久化 resolved credential 明文是允许的
canonical durable fact，不是 finding。此前把这类事实判为 persistence violation、
`internal_product_bug` 和 overall failure 的 oracle 不成立。

本次语义 owner 是
`utils/smoke_cli_init_provider_matrix.py::scan_persisted_secrets` 及其 report
projection/reconciliation，不是 Host。修改范围为：

- `utils/smoke_cli_init_provider_matrix.py`
- `tests/cli/test_smoke_cli_init_provider_matrix.py`
- `docs/cli_ci.md`
- 本 implementation artifact 与对应 fix artifact
- 同一既有 run 的唯一正式 `matrix-report.json`

未修改 `dayu/**`、frozen manifest、oracle JSON 或 raw evidence；未删除、重写 Host
SQLite/WAL；未执行 init、prompt、provider 或任何外部请求；未生成 unsafe backup。

## Implementation decisions

持久化扫描现在投影两个互斥语义通道：

1. `accepted_observations`
   - Host SQLite/WAL 中的 exact credential value；
   - 只记录稳定 `observation_code`、artifact class 和 count；
   - 不影响 `passed`、internal contract、availability 或 overall verdict。
2. `violations`
   - init-owned config、report、log、trace 与其它非 Host SQLite durable artifact
     中的 exact credential value；
   - 任意位置的 exact secret canary；
   - symlink、特殊文件、I/O/竞态或 bounded scan 失败；
   - 进入 row internal contract、availability 与 overall verdict。

init-owned config 因而只能持久化 secret ref，不能持久化 resolved value。正式 row
report 和 matrix report 继续执行 credential/canary/Authorization/Bearer、
request-id value 与已知绝对 root 扫描。

same-run reconciliation 不沿用旧 oracle 写回的
`internal_contract_valid=false` / `internal_product_bug`。它从 publication、
effective identity、config digest、profile 与只读 Host canonical observation
重新计算 internal contract 和 external availability；该读取不启动任何 provider。

## DS follow-up review adjudication

| Finding | 裁决 | Owner 证据与处理 |
| --- | --- | --- |
| DS F01 non-requestable reconciliation 只做路径替换 | accepted | `_reconcile_terminal_summary` 现在复用 `_redact_sensitive_text`；credential、known legacy canary placeholder、Authorization/Bearer、request-id 与显式 roots 由同一 owner 脱敏 |
| DS F02 live expected/effective identity 自引用 | accepted | expected provider family 来自 `InitModelChoice`；静态 provider model 来自冻结 package、动态 provider model 来自 init-owned publication，均经 `ConfigLoader` 解析；effective 只从 production assembly `ordinary` identity 派生 |
| DS F03 legacy canary prefix 可能误报 | rejected-with-reason | prefix scan 是不知道旧 exact canary 时的 intentional fail-closed contract；不降低为宽松扫描 |
| DS F04 刚写入 bool 后再从 JSON 读回 | accepted（non-blocking） | 使用局部 typed bool 直接传给 availability classifier |

F02 的独立 package truth 明确区分 config model id 与 provider model：例如
`gpt-5.4-thinking` 的 provider model 是 `gpt-5.4`。preflight 未完成、production
assembly 不存在时，expected/effective identity 均为 `None`；已声明请求却缺任一
identity 时 no-fallback fail closed，绝不把实际值伪装成 expected。

Controller final follow-up 进一步确认 retained report 中旧 `row.no_fallback` 也属于失效
派生值。`reconcile_existing_report` 现在无条件覆盖它：

- requestable：expected 使用上述独立 truth，effective 使用 row 中 retained assembly
  ordinary identity，runner calls/run binding/request/response 使用只读 Host
  observation，然后重新调用 `evaluate_no_fallback`；
- non-requestable：只在无 request、无 expected/effective identity、无 runner call、
  无 run/trace binding 且无 response 时通过；
- 旧 `passed/fallback_observed/reason_codes` 完全不参与裁决。

Ollama 的 package record 只含 `YOUR_MODEL_HERE` template，不能作为动态 expected。
其 `qwen3:8b` expected 来自 init-owned `workspace/config/models.json`，该输入独立于
assembly actual 且受 publication contract 约束；实现没有硬编码该值。

## Same-run reconciliation

原位重算：

`workspace/tmp/wu-cli-init-01/20260730T112936Z-a86f5ccdeab5/matrix-report.json`

结果：

- row count：15
- Host SQLite accepted observation：10 个聚合 records，分布于 10 rows
- accepted observation `count` 汇总：20 次 exact-byte matches
- persistence violation records/rows：0 / 0
- internal contract valid rows：15
- canonical no-fallback valid rows：15
- overall exit：0
- row secret scan failures：0
- final report secret scan：pass
- credential/canary/Authorization/Bearer/request-id value：均未出现
- project/run/15 个 workspace 已知绝对 root：均未出现
- unsafe backup count：0

accepted observations 全部属于 `workspace/host_sqlite`；既有 run 未产生需要记录的
WAL observation，但 live policy 与 deterministic tests 同时覆盖 SQLite/WAL。
每个 record 的 `count` 是 bounded scanner 对 exact credential bytes 的匹配次数；
20 次 matches 不代表、也不用于推断 20 个业务事件。

## Validation

- focused pytest + coverage：`71 passed`
- `utils/smoke_cli_init_provider_matrix.py`：81%
- `tests/cli/test_smoke_cli_init_provider_matrix.py`：99%
- combined focused coverage：87%
- full pyright：`0 errors, 0 warnings, 0 informations`
- scoped ruff：pass
- `git diff --check`：pass
- frozen manifest：未修改

## Docs decision

`docs/cli_ci.md` 已明确 accepted observation 与 violation 的边界，以及 report、
request-id 和绝对路径脱敏义务。`tests/README.md` 的测试层级、运行方式和读者工作流
未变化，因此无需更新。

## Residual risks 与 uncovered areas

- retained Host SQLite 仍含裁决允许的 credential 明文；分类为
  `accepted observation`，owner 是既有 Host durable contract，本 slice 不修改。
- 既有 run 没有可保留到 report 的原始 canary UUID；legacy reconciliation 继续用
  稳定 canary marker fail closed，新 live run 使用完整 exact canary。
- 未重新调用 provider；这是明确非目标，provider 可用性结论完全复用 retained raw
  evidence。

以上风险均已按用户裁决分类，没有未分类 residual risk。按用户要求，本次不 commit。
