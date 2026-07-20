# WU-SEMANTIC-OWNERSHIP-01 R08 Cumulative Validation Plan-Correction — Complete Re-Review (MiMo)

## 1. Review target and scope

| 项 | 值 |
|---|---|
| umbrella / sub-WU | 既有 `WU-SEMANTIC-OWNERSHIP-01` / `R08`；不是新 WU、feature 或 issue |
| review target | `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`（final plan） |
| review scope | complete adversarial re-review of full final plan，not incremental diff |
| final plan SHA-256 | `87cc332828640de8b4cb4550f29251894111ef3471621bebbef828b66a3ce23d` — **PASS**（independently recomputed） |
| protected S1 14-path binary diff SHA-256 | `0d985b85aa65d7c4b06d9ee464cd73fc4a39ef2ee0934f376b0b845a09b20f57` — **PASS**（independently recomputed） |
| staged tree | empty — **PASS** |
| `git diff --check` | exit 0，no output — **PASS** |
| review verdict | **PASS / 0 material finding / 0 blocker** |

本 re-review 是对 final plan 全文的完整 adversarial 复审，验证 `R08-CVPF-01..03` 修复完整性、拒绝项缺席、以及完整 plan 的 code-generation readiness。Reviewer 不修改 plan、product、tests、control 或既有 artifacts。

## 2. Context artifacts read

- 根 `AGENTS.md`
- `docs/phaseflow-umbrella-optimization-control.md`
- `docs/host/issues-implementation-control.md`（R08 相关行段）
- `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`（完整 final plan，861 行）
- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-review-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-review-fix-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-review-fix-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-review-mimo.md`（本轮之前的 MiMo review）
- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-review-ds.md`（本轮之前的 DS review）
- `docs/reviews/wu-semantic-ownership-01-r08-s1-implementation-codex.md`（S1 implementation evidence）
- `docs/reviews/wu-semantic-ownership-01-r08-s1-validation-plan-drift-controller-adjudication.md`

## 3. Hash verification

### 3.1 Final plan SHA-256

```bash
shasum -a 256 docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
```

```text
87cc332828640de8b4cb4550f29251894111ef3471621bebbef828b66a3ce23d
```

与 control doc `next entry point` 和 Codex review-fix artifact 精确一致。**PASS**。

### 3.2 Protected S1 14-path binary diff SHA-256

```bash
git diff --binary -- \
  dayu/fins/domain/financial_result_contract.py \
  dayu/fins/domain/xbrl_result_contract.py \
  dayu/fins/pipelines/sec_fiscal_fields.py \
  dayu/fins/processors/bs_report_form_common.py \
  dayu/fins/processors/bs_six_k_processor.py \
  dayu/fins/processors/financial_base.py \
  dayu/fins/processors/html_financial_statement_common.py \
  dayu/fins/processors/report_form_financial_statement_common.py \
  dayu/fins/processors/sec_processor.py \
  dayu/fins/processors/sec_xbrl_query.py \
  dayu/fins/processors/six_k_form_common.py \
  tests/fins/test_financial_read_contracts.py \
  tests/fins/test_fins_read_runtime.py \
  tests/fins/test_sec_pipeline_download.py \
  | shasum -a 256
```

```text
0d985b85aa65d7c4b06d9ee464cd73fc4a39ef2ee0934f376b0b845a09b20f57
```

与 S1 handoff、plan-drift adjudication、correction artifact、review-fix artifact 和 control doc 精确一致。**PASS**。

## 4. R08-CVPF-01..03 closure verification

### R08-CVPF-01：精确 Python coverage manifest + 可执行 exact-key checker — CLOSED

**Before（Controller adjudication 证据）**：§6.6 使用 `git diff --name-only --diff-filter=ACMR -- dayu/fins`，会混入非 Python path（如 `dayu/fins/README.md`）；没有机械 exact-key threshold checker，只有自然语言"逐项读取"。

**After（final plan §6.6）**：
- Manifest 使用 `git diff --name-only -z --diff-filter=ACMR -- ':(top,glob)dayu/fins/**/*.py'`，直接过滤到 Python only。
- Inline Python checker：对 manifest 每个 path 做 `coverage_files[path]` exact-key lookup；逐文件打印 `PASS/FAIL path: percent` ledger；manifest 空、path 不以 `dayu/fins/` 开头或不以 `.py` 结尾、exact key 缺失、`<80.00%` 均 `SystemExit(1)`。
- 明确禁止 basename/suffix/absolute-path/规范化 loose fallback。
- Codex review-fix artifact §6.2 验证了四类 case（正常、缺 key、低于阈值、空 manifest）均正确 exit。

**结论**：R08-CVPF-01 已按 Controller 裁决完整修复，checker 可复制执行且 fail-closed。

### R08-CVPF-02：NUL-safe 实际 changed Python Ruff manifest — CLOSED

**Before（Controller adjudication 证据）**：§6.6 Ruff 命令为 `<S1+S2全部实际修改的Python文件>` 占位符，不可直接执行，可能遗漏 tests，空集合静默成功。

**After（final plan §6.6）**：
- 使用 `git diff --name-only -z --diff-filter=ACMR -- ':(top,glob)dayu/fins/**/*.py' ':(top,glob)tests/fins/**/*.py'` 生成 NUL-separated manifest。
- Python consumer 以 `Path.read_bytes().split(b"\0")` 拆分，空 manifest 在调用 Ruff 前 `SystemExit(1)`。
- 非空时通过 `os.execv` 把完整 path vector 机械传给 `python -m ruff check`，Ruff exit code 直接传播。
- Codex review-fix artifact §6.3 验证了正常和空 manifest 两类 case。

**结论**：R08-CVPF-02 已按 Controller 裁决完整修复，命令可复制执行且 fail-closed。

### R08-CVPF-03：aggregate deepreview fix 后完整 revalidation cascade — CLOSED

**Before（Controller adjudication 证据）**：§6.9 已明确 code-review fix 后新 hash 的完整累计 revalidation，但 §7 对 aggregate deepreview accepted fix 只写 `fix/re-review`，未显式使旧 validation/hash/deepreview 失效。

**After（final plan §7）**：

> 任一 aggregate deepreview accepted finding 的修复只要改变 reviewed tree，旧累计 validation、changed-path content manifest、binary diff hash 与两路 aggregate deepreview 即全部失效。必须在新 hash 上重跑完整 §6.6 与 §6.7……全绿并锁定新 hash 后，再由两路 reviewer 对完整 aggregate tree 进行 re-review。只有两路 aggregate re-review 与 Controller 逐条 adjudication 全部关闭后，才可授权 accepted local implementation commit。

§9 checklist 第 16 项同步此条件。

**结论**：R08-CVPF-03 已按 Controller 裁决完整修复，aggregate deepreview fix 的 revalidation cascade 完整。

## 5. Rejected finding absence verification

### DS F4：放宽 forced-truncation key-set equality — REJECTED, NOT IMPLEMENTED

§6.4 仍精确保留 `set(post_value) == set(pre_value)` 与原 stop condition。未放宽为 superset，未修改 §6.4 断言或 stop condition。**确认未实施**。

### MiMo F2：§6.6/§6.7 scans 两层描述混淆 — REJECTED, NOT IMPLEMENTED

§6.7 仍是 §6.6 纳入 scans 的具体展开，未增加"§6.7 是第二命令真源"或重复 scan 路由。§7 首句"§6.6 是唯一累计/aggregate validation 真源"保留。**确认未实施**。

### MiMo F3：共享 test file 并发/行号偏移 — REJECTED, NOT IMPLEMENTED

§5.1 仍只以 symbol/node 名称定义边界，未加入行号、并发、merge seam、import-block compatibility 或额外切片。S1→S2 仍由同一 Agent 在同一 tree 顺序执行。**确认未实施**。

同时未实施 DS F4 或 MiMo F2/F3 的任何替代 residual/fallback 文案。

## 6. Complete plan adversarial review

### 6.1 Scope and ownership

- **R08 scope**：收窄 financial/XBRL 的 LLM-facing contract，建立单一 public typed projection。§2.2 不可回改 owner 表完整，§2.3 out-of-scope 完整。
- **Owner boundary**：§3 inventory 清晰，§4 contracts 精确。Financial producer result 由 `financial_result_contract` 持有，XBRL raw query result 由 `xbrl_result_contract` 持有，public result 由 `result_types.py` projection/helper 持有。
- **No scope creep**：§2.3 明确排除 R09-R12、Issues 142/151/175/177/178、Host/Engine/Service/UI、统一 authorization。§8 stop table 禁止顺手实现。

**结论：PASS**。

### 6.2 Product contracts (§4)

- §4.1 Financial contract：七字段 + optional reason + 七值闭集 + terminal validator。完整且 code-generation-ready。
- §4.2 XBRL contract：`XbrlQueryParams` + `XbrlFactsResult`，flat shape，`fiscal_period` 消费 `FISCAL_PERIODS` 真源，`min_value/max_value` 显式拒绝 bool。完整。
- §4.3 Public projection：`PublicFinancialStatementResult` / `PublicXbrlQueryResult`，精确字段，citation `Mapping[str, JsonValue]` 输入独立 dict 输出。完整。
- §4.4 Tool schema/description：七值 reason 动作矩阵、`fiscal_period.enum` 从 `sorted(FISCAL_PERIODS)` 派生、最小示例使用 `SEC_EDGAR`。完整。

**结论：PASS**。

### 6.3 S1→S2 state machine and sequencing

- §5.4 明确 S1 是 blocked intermediate evidence，不是 independent validation/review gate。
- §5.6 明确 S1→S2 顺序固定，无中间 stage/commit。
- §6.1 S2 entry condition 精确：14-path hash 不变 + tree 未 stage/commit + 无其它 scope 混入。
- §6.9 累计 code review → fix/re-review → aggregate deepreview → commit 顺序完整。
- §7 aggregate deepreview fix revalidation cascade 已补齐。

**结论：PASS**。

### 6.4 Coverage/Ruff commands 可执行性

- Coverage manifest：Git top-level glob pathspec `:(top,glob)dayu/fins/**/*.py`，NUL-separated，inline exact-key checker。
- Ruff manifest：Git top-level glob pathspec `dayu/fins/**/*.py` + `tests/fins/**/*.py`，NUL-separated，`os.execv` handoff，空 manifest fail。
- Codex review-fix artifact §6.1-6.3 直接验证了 Git pathspec、checker 四类 case、Ruff handoff 两类 case。
- Shell syntax check `sed -n '589,703p' <plan> | zsh -n`：exit 0。

**结论：PASS**。

### 6.5 No-touch / deferred boundaries

- R07 no-touch：§2.2 表格 + §6.1 "R07 snapshot acquire/borrow/release、cache/revision、citation 与 source-changed symbols 也不允许修改" + §6.7(D) propagation scan。
- Host truncation owner：§6.4 "本R08不修改Host" + stop condition。
- Topic 8-9 no-code：§2.3 out-of-scope + §6.9 checklist。
- Deferred Issues：§2.3 + §8 stop table。
- R09-R12：§2.3 + §7 "依次继续R09、R10、R11、R12"。

**结论：PASS**。

### 6.6 无兼容 shim / 阈值弱化

- §2.3 明确禁止 "compatibility re-export/wrapper、fallback、shim、双写字段、loose parsing、`getattr/hasattr` 补偿、默认 reason、历史 payload 分支"。
- §6.6 coverage 阈值固定 `80.00%`，禁止 changed-line/aggregate/pragma/omit/fake-only/skip/xfail/豁免。
- §6.6 pyright 必须 `0 errors`。
- §6.6 scoped Ruff 必须归零。
- S1/S2 不做中间 checkpoint commit。

**结论：PASS**。

### 6.7 Code-fact cross-verification

| Plan claim | Code evidence | Status |
|---|---|---|
| S1 已删除 `StatementLocator` from domain | `grep StatementLocator dayu/fins/domain/` 零命中 | PASS |
| S1 已删除 `build_statement_locator` from processors | `grep build_statement_locator dayu/fins/processors/` 零命中 | PASS |
| S1 已删除 `_build_financials_payload` from pipelines | `grep _build_financials_payload dayu/fins/pipelines/` 零命中 | PASS |
| S2 尚未迁移 `result_types.py` | `grep FinancialStatementResult dayu/fins/tools/result_types.py` 仍返回旧类型名 | PASS（expected） |
| S2 尚未迁移 tools count fields | `grep total.*deduped dayu/fins/tools/result_types.py` 仍有 `total: int` / `deduped_fact_count: int` | PASS（expected） |
| `sec_filing` 不在 tools/prompts 中 | `grep sec_filing dayu/fins/tools/ dayu/config/prompts/` 零命中 | PASS |
| `StatementLocator` 仍在 S2-owned consumer 中 | `grep StatementLocator dayu/fins/tools/result_types.py` 有 import 和 usage | PASS（expected blocked intermediate） |

**结论**：S1 实现与 plan claims 一致；S2 未迁移状态与 plan 的 blocked intermediate定位一致。

### 6.8 Shared test file boundary

§5.1 以 symbol/node 名称定义 S1/S2 边界：
- S1：`test_sec_fiscal_inference_consumes_countless_xbrl_contract`（已迁移，per S1 implementation artifact）
- S2：六个 normalize/dedup nodes（尚未迁移）

S1 与 S2 不同修改同一 import block 的不同行（S1 删除 `StatementLocator` import，S2 将添加 `PublicFinancialStatementResult` import），但同一 Agent 顺序执行可正确处理。Controller 已拒绝 MiMo F3 的行号偏移 concern。

**结论：PASS**（residual risk 低，已在 §6.10 记录）。

### 6.9 Forced-truncation composition (§6.4)

§6.4 设计完整：pre-Host callable → Host cursor envelope → fetch-more remainder 三段公开链路。Test 机制使用现有 `_tool_runtime` helper + `enable_truncation_manager` 参数 + 命名常量 `_FORCED_XBRL_MAX_ITEMS = 1`。Stop condition 明确。

**结论：PASS**。

## 7. Open questions

无。

## 8. Residual risks

| 风险 | 严重程度 | 跟踪目的地 |
|---|---|---|
| S2 累计测试集能否将 7 个处理器文件从当前 41%–67% 驱动到逐文件 ≥80% | 中 | R08-S2 cumulative implementation gate |
| pre-Host callable → Host envelope → fetch-more 三段 seam 在新 `PublicXbrlQueryResult` 下是否完全可观测 | 中 | R08-S2 forced-truncation smoke |
| S1/S2 顺序修改共享 test file import 区域的行号偏移 | 低 | R08-S2 implementation（同一 Agent 顺序执行） |
| Host truncation envelope 格式在 S2 实施窗口内演化导致 key-set 断言 false positive | 低 | R08-S2 forced-truncation smoke；stop condition 兜底 |
| Coverage JSON 路径格式与 git diff 输出格式隐式对齐 | 低 | R08-S2 cumulative validation gate |

上述均为 S2 implementation 期的已知 residual risk，不构成当前 plan correction 的 blocker。

## 9. Plan review conclusion

**PASS / 0 material finding / 0 blocker**

Final plan 是 code-generation-ready 的。R08-CVPF-01..03 全部按 Controller 裁决完整修复：coverage manifest 使用 Git top-level glob pathspec 生成精确 Python-only manifest 并配可复制执行的 exact-key fail-closed checker；Ruff manifest 使用 NUL-safe Git pathspec + `os.execv` handoff + 空 manifest 失败；aggregate deepreview fix 的 revalidation cascade 已在 §7 和 §9 完整补齐。

DS F4、MiMo F2、MiMo F3 三项拒绝项均未实施，无替代 residual/fallback 文案。

完整 plan 的 scope、owner、product contracts、S1/S2 allowlists、cumulative state machine、S1→S2 sequencing、no-touch/deferred boundaries、无兼容 shim/阈值弱化、forced-truncation composition、code-generation handoff checklist 全部通过 adversarial 审查。

两个受保护 hash 独立重算精确匹配。Staged tree 为空。`git diff --check` 通过。

当前 gate 只完成双路完整 re-review 中的 MiMo 路；Controller adjudication 后才可进入后续 gate。
