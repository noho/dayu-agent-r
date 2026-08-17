# UF-FIX01 fiscal-period prevalidation residual — Plan Review Adjudication

## Gate 元数据

- work unit：`UF-FIX01-fiscal-period-prevalidation-residual`
- gate：`plan review -> fix`
- 日期：2026-08-18
- reviewed plan：`docs/gateflow/uf-fix01-fiscal-period-prevalidation-residual-plan-20260817.md`
- MiMo artifact：`docs/reviews/plan-review-20260818-000654.md`
- DS artifact：`docs/reviews/plan-review-20260818-001109.md`
- aggregate decision：`fail; plan amendment required`
- current gate：`fix`
- next entry point：`fix`
- completion status：`findings-adjudicated`
- artifact path：`docs/gateflow/uf-fix01-fiscal-period-prevalidation-residual-plan-review-adjudication-20260818.md`

## Review evidence validation

- 两路 reviewer 均以 UF-A21 exact result、shared admission 代码、CLI/tool test seam 和 Host/Engine design 为直接证据。
- DS 实测 S1 baseline `499 passed`、S2 六文件 `757 passed`、全仓 pyright `0/0/0`；coverage 显示
  `filing_semantics.py=70%`、`ingestion_runtime.py=91%`、`docling_upload_service.py=89%`。
- 两路均确认 root cause、owner 与 market-neutral admission 方向成立，无需重做 goal confirmation 或架构方案。

## Finding adjudication

| ID | 来源 | 决定 | Fix requirement |
|---|---|---|---|
| M-001 | MiMo | `accepted` | 不让 `derive_report_kind` 消费 optional owner 结果。把其参数收窄为 `FiscalPeriod`，只投影 report kind；非法/缺失已在 admission 收口。 |
| M-002 | MiMo | `accepted` | 类型保护不得停在 validated dataclass；upload 专用 `build_cn_filing_ids` / `build_sec_filing_ids` 的 period 参数同步收窄为 `FiscalPeriod`。 |
| M-003 | MiMo | `accepted` | 删除两个 upload ID builder 内的 `strip().upper()`；它们直接消费 canonical typed value，不保留第二份 normalization。CN download 自有 `cn_form_utils.build_cn_filing_ids` 不在范围。 |
| M-004 | MiMo | `accepted` | plan 写出 exact try/except：调用 `normalize_fiscal_period(raw)`；`ValueError` 映射通用 code；owner 返回 `None` 视为 required invariant breach，不允许异常逃逸为 runtime failure。 |
| M-005 | MiMo | `accepted` | S1 明列更新 closed enum set、exact usage message 与旧名称全仓扫描。 |
| D-F1 | DS | `accepted` | 现有 CLI UF-024 exact expected reason 与 S1 usage contract 同 slice 更新；`tests/cli/test_fins_commands.py` 加入 S1 allowed files 和验证命令，S1 commit 不携带已知红。 |
| D-F2 | DS | `accepted` | S1 不修改 `filing_semantics.py` production；只补 owner tests。coverage include 固定为最终实际修改的 production 文件，预期为 `ingestion_runtime.py`、`docling_upload_service.py`，若 S2 修改 `upload_tools.py` 则加入。 |
| D-F3 | DS | `accepted` | S2 修改 `upload_tools.py` fiscal_period description，自足列出全部六值及 filing/material requiredness；增加 schema exact assertion。 |

## Open-question adjudication

- CLI/tool 通用 text helper 会在 request 构造前 strip：`accepted` 作为测试描述约束。入口测试必须说明它证明
  “最终 request 共享 canonical contract”，owner-level raw whitespace 行为由 domain test 直接证明，不把通用 trim helper 冒充业务 owner。
- `tests/README.md` 无专用更新约束：按项目顶层触发规则与当前章节职责判断，仍在 S2 检查并按需更新。

## Required plan amendment

1. S1 allowed files 加 `tests/cli/test_fins_commands.py`，移除 `filing_semantics.py` production allowed change。
2. S1 exact changes 写明 `FiscalPeriod` 贯穿 validated/static dataclass、derive helper 与两个 upload ID builders；删除 builder normalization。
3. S1 写明 exact domain-error mapping、None invariant、旧 enum/code/message/duplicate parser/normalization 扫描。
4. S1 验证包含 CLI 文件，保证更新 UF-024 后全绿。
5. S2 allowed files 加 `dayu/fins/tools/upload_tools.py`；schema 描述与测试同步完整闭集。
6. coverage 命令给出最终 exact include 集合；不得为 `filing_semantics.py` 无关分支扩 scope。
7. residual risks 删除“build ID helper 保留 normalization”；它已纳入当前 fix。

## Residual risks

- UF-PF01/UF-PF12 真实 calibration、冻结 evidence/oracle/scenario：`assigned to later work unit`。
- material optional fiscal metadata：`assigned to later work unit`。
- download aliases：`rejected-with-reason`，独立 filter owner 有意承诺。
- 旧 durable 非法 period：`assigned to later work unit`，无兼容升级授权。
- AgentCodex plan generation 两次无产出：workflow execution risk；本次 fix 任务将缩窄为已裁决的机械 plan amendment。

## Completion status

所有 review findings 已裁决；当前没有需用户决策的 open question。plan 未修复前不得进入 re-review 或 accepted plan commit。
