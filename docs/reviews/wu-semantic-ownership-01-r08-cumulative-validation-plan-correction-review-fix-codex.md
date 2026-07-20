# WU-SEMANTIC-OWNERSHIP-01 / R08 Cumulative Validation Plan-Correction Review Fix — AgentCodex

## 1. Gate result

| 项 | 结果 |
|---|---|
| umbrella / sub-WU | 既有 `WU-SEMANTIC-OWNERSHIP-01` / `R08`；不是新 WU、feature 或 issue |
| gate | same-R08 cumulative validation plan-correction review fix |
| Controller adjudication | `docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-review-controller-adjudication.md` |
| before corrected-plan SHA-256 | `4ff2c00c5999cf20ff314afd7e9a0fa041c32d2f36c23566d21752887c997e3d` |
| final plan SHA-256 | `87cc332828640de8b4cb4550f29251894111ef3471621bebbef828b66a3ce23d` |
| protected 14-path binary diff SHA-256 | `0d985b85aa65d7c4b06d9ee464cd73fc4a39ef2ee0934f376b0b845a09b20f57` |
| accepted fix groups | `R08-CVPF-01..03`：`3/3 已修复` |
| rejected / no-fix | DS F4、MiMo F2、MiMo F3：`3/3 未实施` |
| decision | `FIXED / READY FOR CONTROLLER-DISPATCHED DUAL COMPLETE RE-REVIEW` |
| stop | 未进入 S2 implementation、commit、push、PR 或后续 gate |

本 gate 只把 Controller 接受的三组 plan findings 修入 corrected plan，并新增本 artifact。product、tests、S1 artifact、control、Controller/reviewer artifacts、README、design 均未由本 gate 修改；未 stage、commit、push 或创建 PR。

## 2. 第一性原理与 owner 判断

三组 accepted finding 的动机均成立：coverage 与 Ruff 的实际修改集合属于 Git working-tree diff，不能由人工 allowlist 或下游 checker 猜测；coverage 阈值属于 coverage JSON 对同一 repo-relative path 的 exact-key contract，不能用 basename、suffix 或绝对路径 fallback 补偿；aggregate deepreview fix 改变 reviewed tree 后，只有唯一累计 validation owner 能重新建立“该 hash 可接受”的事实。

因此修复只落在命令 manifest/checker 与 aggregate gate state machine 的 plan owner boundary。没有改 product contract、测试语义、Host/Fins public key-set proof、共享测试文件切片或 §6.6/§6.7 的 scan ownership。

## 3. 读取范围

已完整读取并据此修复：

- 根 `AGENTS.md`；
- 主 control `docs/host/issues-implementation-control.md`；
- `docs/phaseflow-umbrella-optimization-control.md`；
- 完整 corrected plan；
- AgentCodex cumulative-validation correction artifact；
- AgentDS 与 AgentMiMo 两份完整 review；
- Controller adjudication `docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-review-controller-adjudication.md`。

## 4. Finding closure

### R08-CVPF-01：已修复

Before：§6.6 只以自然语言要求从未限制后缀的 `git diff --name-only -- dayu/fins` 生成 manifest，再人工逐项查看 coverage JSON；S2 修改 `dayu/fins/README.md` 后会把非 Python path 混入，且没有机械 exact-key threshold checker。

After：§6.6 现在从 repository root 使用 Git top-level glob pathspec `:(top,glob)dayu/fins/**/*.py` 直接生成 NUL-separated、repo-relative、实际 changed production Python manifest。可复制执行的 Python checker：

- 对 manifest 每个 path 只做 coverage JSON `files[path]` exact lookup；
- 逐文件打印 `PASS/FAIL path: percent` ledger；
- manifest 为空、path 非 repo-relative `dayu/fins/*.py` contract、exact key 缺失或 `<80.00%` 均非零退出；
- 明确禁止 basename/suffix/absolute-path/规范化 loose fallback；路径不一致只能修正 coverage invocation/working directory后重跑；
- 保留 aggregate threshold、changed-line、pragma/omit、fake-only padding、skip/xfail 与阈值豁免禁令。

状态：`CLOSED`。

### R08-CVPF-02：已修复

Before：§6.6 Ruff 命令仍是不可执行占位符 `<S1+S2全部实际修改的Python文件>`，可能漏掉 changed tests，且空集合会被误当成功。

After：§6.6 使用两个 Git top-level glob pathspec 直接生成 `dayu/fins/**/*.py` 与 `tests/fins/**/*.py` 的实际 changed NUL manifest；Python consumer 以 NUL 拆分并通过 `os.execv` 把完整 path vector 机械传给同一虚拟环境的 `python -m ruff check`。空 manifest 在调用 Ruff 前 exit `1`；零diff allowlist path不会被伪加入。

状态：`CLOSED`。

### R08-CVPF-03：已修复

Before：§6.9 已明确 code-review fix 后新 hash 的完整累计 revalidation，但 §7 对 aggregate deepreview accepted fix 只写 `fix/re-review`，未显式使旧 validation/hash/deepreview失效。

After：§7 明确任一 aggregate deepreview accepted fix 改变 reviewed tree 后，旧累计 validation、changed-path content manifest、binary diff hash 与两路 aggregate deepreview全部失效；必须在新 hash 上完整重跑 §6.6/§6.7 的 focused/aggregate/full Fins tests、real smokes、逐文件 coverage、full pyright、实际 changed Python Ruff、全部 scans 与 diff check，然后进行双路完整 aggregate re-review，最后由 Controller 逐条关闭。§9 checklist 同步这一 gate 条件。

状态：`CLOSED`。

最终 closure：accepted fix groups `3/3 CLOSED`；accepted source findings `5/5 COVERED`；新增 accepted/deferred/blocking finding `0/0/0`。

## 5. Rejected / no-fix 缺席证据

| Finding | Controller disposition | 本 gate 证据 |
|---|---|---|
| DS F4 | REJECT | §6.4 仍精确保留 `set(post_value) == set(pre_value)` 与原 stop condition；未放宽为 superset，未实现 DS F4 |
| MiMo F2 | REJECT | 未增加“§6.7 是第二命令真源”或重复 scan 路由；§6.7 仍是 §6.6 已纳入 scans 的具体展开 |
| MiMo F3 | REJECT | 未加入行号、并发、merge seam、import-block compatibility 或额外切片；S1→S2 仍由同一 Agent 在同一 tree 顺序执行 |

同时未实施 DS F4 或 MiMo F2/F3 的任何替代 residual/fallback 文案。

## 6. Plan command syntax / feasibility validation

### 6.1 Git pathspec

- `git diff --name-only --diff-filter=ACMR -- ':(top,glob)dayu/fins/**/*.py'`：exit `0`，当前精确输出 11 个受保护 changed production `.py`，不含 `dayu/fins/README.md`。
- `git ls-files -- ':(top,glob)dayu/fins/**/*.py'` 的根级过滤探测命中 `dayu/fins/__init__.py` 等根级模块，证明 `**/*.py` 同时覆盖根级与递归 Python path。

### 6.2 Exact-key coverage checker

使用与 plan 相同 checker body，通过 process-substitution 提供不落盘的合成 manifest/JSON，验证结果：

| Case | Exit | Ledger |
|---|---:|---|
| 两文件分别 `80.00%` / `99.50%` | `0` | 两文件逐项 `PASS` |
| 第二文件 exact key 缺失 | `1` | 第一文件 `PASS`，第二文件 `FAIL ... exact coverage JSON key is missing` |
| 两文件分别 `79.99%` / `100.00%` | `1` | 第一文件 `FAIL 79.99%`，第二文件仍逐项 `PASS` |
| 空 manifest | `1` | `FAIL manifest: no changed dayu/fins Python files` |

`sed -n '589,703p' <plan> | zsh -n`：exit `0`，完整 §6.6 shell block（含 heredoc 与多行 Ruff command）语法通过。

### 6.3 NUL-safe Ruff handoff

- 将当前实际 `dayu/fins/**/*.py` + `tests/fins/**/*.py` NUL diff manifest交给 plan 相同 consumer：exit `0`，`All checks passed!`。
- 将空 NUL manifest交给同一 consumer：exit `1`，`FAIL Ruff manifest: no changed dayu/fins or tests/fins Python files`。

因此命令不是文档占位符；Git pathspec、NUL split、机械 argv handoff、empty-set failure与 Ruff exit propagation均已直接验证。

## 7. Protected scope、hash 与 diff evidence

### 7.1 Protected 14 paths

受保护对象仍为 S1 artifact 锁定的 11 个 production 与 3 个 tests：

```text
dayu/fins/domain/financial_result_contract.py
dayu/fins/domain/xbrl_result_contract.py
dayu/fins/pipelines/sec_fiscal_fields.py
dayu/fins/processors/bs_report_form_common.py
dayu/fins/processors/bs_six_k_processor.py
dayu/fins/processors/financial_base.py
dayu/fins/processors/html_financial_statement_common.py
dayu/fins/processors/report_form_financial_statement_common.py
dayu/fins/processors/sec_processor.py
dayu/fins/processors/sec_xbrl_query.py
dayu/fins/processors/six_k_form_common.py
tests/fins/test_financial_read_contracts.py
tests/fins/test_fins_read_runtime.py
tests/fins/test_sec_pipeline_download.py
```

`git diff --binary -- <上述14路径> | shasum -a 256`：

```text
0d985b85aa65d7c4b06d9ee464cd73fc4a39ef2ee0934f376b0b845a09b20f57  -
```

与 Controller 锁定值精确一致。

### 7.2 Checks

- `shasum -a 256 docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`：`87cc332828640de8b4cb4550f29251894111ef3471621bebbef828b66a3ce23d`。
- `git diff --check`：exit `0`，无输出。
- `git diff --check -- docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`：exit `0`，无输出。
- `git diff --no-index --check /dev/null docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-review-fix-codex.md`：预期因新增 diff 返回 exit `1`，无 whitespace error 输出。
- `git diff --cached --name-only`：exit `0`，无输出；staged tree为空。
- 未运行 pytest、coverage session或full pyright：本 gate只修 plan；S2尚未实施，当前tree仍是已裁决的S1 blocked intermediate state。实际 changed files scoped Ruff只为验证新命令的可执行性而运行，并已通过。

### 7.3 Final status

最终 `git status --short --untracked-files=all`：

```text
 M dayu/fins/domain/financial_result_contract.py
 M dayu/fins/domain/xbrl_result_contract.py
 M dayu/fins/pipelines/sec_fiscal_fields.py
 M dayu/fins/processors/bs_report_form_common.py
 M dayu/fins/processors/bs_six_k_processor.py
 M dayu/fins/processors/financial_base.py
 M dayu/fins/processors/html_financial_statement_common.py
 M dayu/fins/processors/report_form_financial_statement_common.py
 M dayu/fins/processors/sec_processor.py
 M dayu/fins/processors/sec_xbrl_query.py
 M dayu/fins/processors/six_k_form_common.py
 M docs/host/issues-implementation-control.md
 M docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
 M tests/fins/test_financial_read_contracts.py
 M tests/fins/test_fins_read_runtime.py
 M tests/fins/test_sec_pipeline_download.py
?? docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-codex.md
?? docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-controller-validation.md
?? docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-review-controller-adjudication.md
?? docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-review-ds.md
?? docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-review-fix-codex.md
?? docs/reviews/wu-semantic-ownership-01-r08-cumulative-validation-plan-correction-review-mimo.md
?? docs/reviews/wu-semantic-ownership-01-r08-s1-implementation-codex.md
?? docs/reviews/wu-semantic-ownership-01-r08-s1-validation-plan-drift-controller-adjudication.md
```

本 gate 入口已存在其余 dirty paths；本 gate 的唯一内容 delta 是 corrected plan 从 before hash 变为 final hash，以及新增本 review-fix artifact。staged tree最终仍为空。

## 8. README / product / residuals

- README decision：不更新。用户与 Controller 明确禁止，本 gate也没有改变产品current contract或最终用户入口。
- Product/tests decision：不修改；S2未开始，protected 14-path hash不变。
- Control/controller/reviewer/design decision：不修改。
- Residual risk：累计 S1+S2 implementation/validation尚未执行；这是同一 R08 的下一实施 gate，不是本 plan-fix 的豁免。当前唯一待完成项是 Controller派发MiMo/DS对 final plan的两路完整 re-review。
- Deferred boundaries：R09-R12、Issues 142/151/175/177/178、Topic 8-9、统一 authorization、Host/Engine/Service/UI、push/PR均未进入。

## 9. Completion / next entry point

`R08-CVPF-01..03` 已全部且仅按 Controller adjudication关闭，final plan与受保护 implementation tree hash均已记录。本 gate在此停止回 Controller；下一入口是Controller派发AgentMiMo/AgentDS对完整 final plan的双路re-review，不进入S2。
