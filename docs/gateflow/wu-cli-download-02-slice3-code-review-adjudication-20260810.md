# `WU-CLI-DOWNLOAD-02` Slice 3 Code Review Adjudication

## Gate state

- Work unit: `WU-CLI-DOWNLOAD-02-DL-F12-F14`
- Slice: Slice 3 — DL-F13 HKEX discovery、identity 与 coverage projection
- Input HEAD: `9e037e3fb16eeaa14ceb185009a5ad16015a87aa`
- Implementation artifact: `docs/gateflow/wu-cli-download-02-slice3-implementation-20260810.md`
- Review artifacts:
  - `docs/reviews/wu-cli-download-02-slice3-code-review-mimo-20260810.md`
  - `docs/reviews/wu-cli-download-02-slice3-code-review-ds-20260810.md`
- AgentMiMo verdict: **PASS**
- AgentDS verdict: **PASS**
- Final adjudication: **code-review-pass / accepted for protected commit**

## Controller adjudication

总控完整读取 implementation artifact、两份 review、全部 production diff、关键 owner tests 与三份 README diff。两名 reviewer 均未提出 finding；总控也未发现需要 fix/re-review 的当前 correctness、stability、maintainability 或 scope finding。

直接证据支持以下结论：

- HKEX bare optional quarter discovery 共用一个 `10000 / 3 / -2` results category spec，旧 `13600` production 语义已删除，category spec 去重仍保证一次查询。
- material family 只由 provider category 判定；family 确定后才共同解释 category/title 事实。英文、繁中、简中正例与空 category、双 family、report+quarter、duration 冲突均有 owner tests。
- `CnReportPeriodProjection` 是 candidate identity/coverage 的唯一 owner；ID、窗口、business limit、missing、form、fiscal period 与 report kind 只消费 identity。coverage 只沿 source meta、workflow、typed/public result、JSON、wait 与 CLI 原样投影。
- Q2 result 的 `(H1,Q2)` 不满足 H1 report baseline；Q4 result 的 `(FY,Q4)` 不满足 FY annual report baseline，也不会复制 source 或 manifest item。
- ordinary、skip、failed、rebuild rows 都携带 required coverage；fresh-schema source meta 缺失或畸形 coverage 在 rebuild/CN adapter 边界 fail closed，不存在默认值或旧 schema fallback。
- CN/SEC/generic 的所有 public constructor 已显式迁移；SEC 与不适用来源显式使用空 tuple，公共 JSON 明确输出空 array。
- README 更新属于各自读者职责，没有写 WU、review、future capability 或内部 evidence 标识；Host/Engine/storage schema 未修改。

## Open-question adjudication

### `stock_code_payload` 不属于 selection core-fact conflict tuple

Decision: **not a finding**。

Downloader 在 raw row 进入 selection 前已用 `stock_code_payload` 判断目标股票；同一 document 关联一个或多个股票代码不会改变 PDF source URL、category、title、filing date、language、document identity 或 period projection。把 provider 的多代码集合差异当作 source 内容冲突会错误拒绝同一披露材料。当前 conflict tuple 保留所有会改变 source/selection 语义的事实，边界正确。

### Q4 与 Q1 token 同时命中时收敛为 Q4

Decision: **not a finding**。

冻结 contract 明确合并年度/Q4结果材料可以同时承载全年与第四季业务信息；真实内容可能同时出现全年与三个月指标。Q4 与 Q2/Q3 表示相互冲突的累计期间并 fail closed；Q4 与 Q1 token 共存不改变 final-result identity。当前规则没有用枚举偶然顺序猜测。

### source meta schema 与 download version

Decision: **non-goal / no compatibility work**。

本任务按 fresh schema 起库，并明确禁止旧 schema fallback。旧 meta 缺 required coverage 时 rebuild fail closed 是已接受 contract；本 work unit 不新增 migration、兼容读取、版本 shim 或隐式重下载策略。真实 fresh workspace 行为留待已批准 post-fix evidence gate验证。

## Residual risks

| Risk | Classification | Destination |
|---|---|---|
| 真实 HKEX 全 results 数据规模与边缘 category 文本尚未验证 | covered by later approved gate | production CLI/provider post-fix evidence |
| 通用 substring token 在未知 provider 文本上可能保守丢弃歧义材料 | acceptable fail-closed residual | production evidence；不得在当前 code gate 加 issuer 特例 |
| 旧 workspace 无 coverage 的 source meta 无兼容读取 | accepted fresh-schema boundary | 非本 work unit；只有用户另行授权 migration 才处理 |

无 unclassified residual risk，无 blocking contract question。

## Accepted gate evidence

- Focused owner union: `1065 passed`
- 13 个修改 production 文件整文件 line coverage: `81%–97%`
- Full pyright: `0 errors, 0 warnings, 0 informations`, `PYRIGHT_EXIT=0`
- Changed-files Ruff check/format: pass
- Compileall: pass
- JSON round-trip、wait/CLI owner tests、README guards、`git diff --check`: pass

Slice 3 可以创建 protected commit；不得在该 commit 中加入真实 CLI evidence、aggregate deepreview 或其它 work unit 内容。
