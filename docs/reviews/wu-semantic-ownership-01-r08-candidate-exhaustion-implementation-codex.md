# WU-SEMANTIC-OWNERSHIP-01 R08 Candidate Exhaustion Implementation（STOPPED）

## 1. 结论

本次是既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 内 R08 candidate-exhaustion
implementation continuation，不是新 WU 或新 slice。

最终状态：**STOPPED / RETURN TO CONTROLLER**。

唯一授权的 production deletion 与紧随其后的 §6.7.G source/AST proof 均完成；但第一个
fresh exclude-candidate-5 proof 得到
`381/485 = 78.56%`，不等于 accepted plan / authorization 锁定的
`382/482 = 79.25%`。coverage checker 退出码为 `1`，因此强制 stop condition 已触发。
未运行 all-five proof、完整 §6.6/§6.7、full pyright、Ruff、完整 scans 或
`git diff --check`；未修改测试、coverage 配置、README 或其它 production symbol，也未
stage、commit、push 或创建 PR。

## 2. 第一性原理与语义 owner

动机成立。`dayu/fins/tools/read_runtime_helpers.py::_collect_available_document_types` 在
authorization entry tree 中只有一个 definition、零 caller、零 import，是与实际 suggestion
producer 重复的不可达 owner。真实业务 owner 是
`dayu/fins/tools/read_runtime.py::_collect_available_document_types_for_source_documents`：它接收
typed `list[_SourceDocumentSummary]`，调用共享
`resolve_document_type_for_source`，并以 `return sorted(doc_types)` 输出 `list[str]`。

因此唯一正确实现是删除重复 helper definition，保留 actual typed/sorted owner；不应直测 private
helper、增加 caller/wrapper/alias/re-export、在下游补偿，或修改 coverage/test contract。

## 3. Re-entry locks

执行命令：

```bash
git branch --show-current
git merge-base --is-ancestor 65fd8d5c852e1baf6ad8173e9eddf353ffe6b3b5 HEAD
shasum -a 256 docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
git diff --binary -- dayu/fins tests | shasum -a 256
shasum -a 256 dayu/fins/tools/read_runtime_helpers.py dayu/fins/tools/read_runtime.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py \
  tests/fins/test_fins_read_runtime.py
git diff --cached --name-only
test -z "$(git diff --cached --name-only)"
test ! -e docs/reviews/wu-semantic-ownership-01-r08-candidate-exhaustion-implementation-codex.md
git status --short --untracked-files=all
```

命令组退出码 `0`。全部 locks 精确匹配：

| Lock | 结果 |
|---|---|
| branch | `phaseflow/host-issues-control` |
| accepted plan ancestor | `git merge-base --is-ancestor ... HEAD` exit `0` |
| plan SHA-256 | `0145d1de9b3bbe93ff200e792a40b4e850c36346b43e80a5f6e239cac745a3e9` |
| stopped `dayu/fins + tests` binary diff SHA-256 | `65a924066d45b4e90f2ef2e6767b96c8ce8e4fbd2c5b1d9ea698875c94706dff` |
| helper before SHA-256 | `46e87c63a6a7baac20996139203064da95e261c4ef08b04f80821215f1a50b93` |
| `read_runtime.py` SHA-256 | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` |
| guards SHA-256 | `553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d` |
| shared test SHA-256 | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` |
| staged tree | empty |
| target implementation artifact before run | absent |

Entry HEAD 为 `b2173f9d74f06521520b8fa0baf3522f543d78d8`。

## 4. 唯一 implementation delta

先用以下只读命令确认完整 definition 边界：

```bash
rg -n -C 8 '^def _collect_available_document_types|^def ' \
  dayu/fins/tools/read_runtime_helpers.py | sed -n '1,220p'
sed -n '388,426p' dayu/fins/tools/read_runtime_helpers.py
```

两条命令均 exit `0`。随后只用 `apply_patch` 删除
`dayu/fins/tools/read_runtime_helpers.py::_collect_available_document_types` 从 `def` 到
`return sorted(doc_types)` 的完整 definition。没有修改该文件其它 symbol 或 import。

Helper after SHA-256：
`1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b`。

## 5. 删除后立即执行的 §6.7.G proof

### 5.1 Source proof

```bash
if rg -n '\b_collect_available_document_types\b' dayu tests; then
  echo 'FAIL old helper definition/caller/import remains'
  exit 1
fi
echo 'PASS old helper source matches=0'
```

结果：`PASS old helper source matches=0`，exit `0`。

### 5.2 AST proof

紧接 source proof，在同一命令组中 `source .venv/bin/activate`，按 accepted plan §6.7.G
逐个 AST parse `dayu/**/*.py` 与 `tests/**/*.py`，统计 old symbol definition/caller/import，
并检查 actual owner cardinality、annotations、resolver 调用与 sorted return。

结果：

```text
PASS old helper definition/caller/import=0; actual typed/sorted owner definition/caller=1
```

命令组 exit `0`。具体不变量：

- old definition/caller/import：`0/0/0`；
- actual owner definition/caller：`1/1`；
- input/output annotation：`list[_SourceDocumentSummary] -> list[str]`；
- `resolve_document_type_for_source` 调用仍存在；
- `sorted(...)` return 精确一个。

## 6. 删除后 no-touch / content locks

执行命令：

```bash
shasum -a 256 dayu/fins/tools/read_runtime_helpers.py dayu/fins/tools/read_runtime.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py \
  tests/fins/test_fins_read_runtime.py \
  docs/reviews/wu-semantic-ownership-01-r08-s1-implementation-codex.md \
  docs/reviews/wu-semantic-ownership-01-r08-s2-cumulative-implementation-codex.md
git diff --binary -- dayu/fins tests | shasum -a 256
git diff --name-only -- dayu/fins tests
git diff --name-only -- dayu/fins tests | wc -l
git diff --cached --name-only
test -z "$(git diff --cached --name-only)"
git status --short --untracked-files=all
```

命令组 exit `0`。结果：tracked changed path 仍为原 23 路径，staged 为空；除 helper
definition deletion 外没有新增 product/test/README path delta。内容锁如下：

| Target | SHA-256 |
|---|---|
| `read_runtime_helpers.py` after | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` |
| `read_runtime.py` | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` |
| guards | `553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d` |
| shared test | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` |
| S1 artifact | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` |
| S2 artifact | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` |
| final `dayu/fins + tests` binary diff | `3d9df8fefc485d0d19421fe6d2a3fe0402bf6f27d3b821d51125e039fa52ddf0` |

## 7. Fresh exclude-candidate-5 proof：失败并触发 stop

从 repository root 精确执行：

```bash
set -e
source .venv/bin/activate
python -m coverage erase
python -m coverage run -m pytest \
  tests/fins/test_financial_read_contracts.py \
  tests/fins/test_sec_pipeline_download.py \
  tests/fins/test_fins_read_runtime.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py \
  tests/fins/test_processor_read_consistency.py \
  tests/fins/test_processor_registry.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/fins/test_fins_storage_provider.py \
  --deselect tests/fins/test_read_runtime_semantic_ownership_guards.py::test_search_next_section_projection_ranks_business_evidence_per_query
python -m coverage json -o workspace/tmp/r08-candidate-4-proof-coverage.json
python - workspace/tmp/r08-candidate-4-proof-coverage.json <<'PY'
import json
from pathlib import Path
import sys

target = "dayu/fins/tools/read_runtime_helpers.py"
summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["files"][target]["summary"]
covered = summary["covered_lines"]
statements = summary["num_statements"]
percent = summary["percent_covered"]
print(f"CANDIDATE_4_PROOF {target}: {covered}/{statements} = {percent:.2f}%")
if covered != 382 or statements != 482 or percent >= 80.0:
    raise SystemExit(1)
PY
```

Pytest 结果：`390 passed, 1 deselected, 3 warnings in 21.47s`。三个 warnings 均为既有
`edgar.files` deprecation warnings：

1. `edgar.files.html_documents` / `HtmlDocument` 将在 v6.0 移除；
2. `edgar.files.html` 将在 v6.0 移除；
3. `edgar.files.htmltools` / `ChunkedDocument` 将在 v6.0 移除。

Coverage JSON 写入成功，但 checker 输出：

```text
CANDIDATE_4_PROOF dayu/fins/tools/read_runtime_helpers.py: 381/485 = 78.56%
```

最终命令组 exit `1`。与 authorization 的 exact proof 对比：

| 项 | 必须值 | 实测值 | 结论 |
|---|---:|---:|---|
| covered lines | `382` | `381` | mismatch |
| statements | `482` | `485` | mismatch |
| percent | `79.25%` | `78.56%` | mismatch；仍低于 80%，但 exact lock 不成立 |

现场证据保留：

| Evidence | SHA-256 |
|---|---|
| `.coverage` | `d17547b23e45ee22610d9d90d9ad825931371634696a1eb11fea2203e651aa2b` |
| `workspace/tmp/r08-candidate-4-proof-coverage.json` | `f6f72ca0946a743d85ca89cfa7b1c108d0965bf74aeeef44000cf600c2c38b6e` |

## 8. Stop 后命令与一次只读 harness 错误

为记录最终 hashes/status，首次执行以下只读命令组：

```bash
git rev-parse HEAD
shasum -a 256 .coverage workspace/tmp/r08-candidate-4-proof-coverage.json
shasum -a 256 dayu/fins/tools/read_runtime_helpers.py dayu/fins/tools/read_runtime.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py \
  tests/fins/test_fins_read_runtime.py \
  docs/reviews/wu-semantic-ownership-01-r08-s1-implementation-codex.md \
  docs/reviews/wu-semantic-ownership-01-r08-s2-cumulative-implementation-codex.md
git diff --binary -- dayu/fins tests | shasum -a 256
git diff --name-only -- dayu/fins tests | while IFS= read -r path; do shasum -a 256 "$path"; done
git diff --cached --name-only
git status --short --untracked-files=all
```

该命令组 exit `127`。原因是 zsh 的特殊数组变量 `path` 与 `PATH` 绑定，循环赋值后导致循环内
`shasum` 及后续 `git` 报 `command not found`。在报错前，HEAD、coverage evidence hashes、核心
内容锁与 diff hash 已成功输出。该错误只影响留证 shell harness，不修改 repository 或 coverage
evidence。

随后只修正循环变量名并重跑同一只读留证：

```bash
git diff --name-only -- dayu/fins tests | while IFS= read -r changed_file; do
  shasum -a 256 "$changed_file"
done
git diff --cached --name-only
test -z "$(git diff --cached --name-only)"
git status --short --untracked-files=all
```

结果 exit `0`，staged 为空，最终 status 仅包含原 23 个 tracked paths、原 S1/S2 untracked
artifacts；写入本 artifact 后再增加本 artifact 这一条 untracked path。

## 9. Final changed paths 与 content SHA-256

| Changed path | Content SHA-256 |
|---|---|
| `dayu/fins/README.md` | `50c07ae625188c470c2818405d445772d073bc67496dcb58f57362720479dd4f` |
| `dayu/fins/domain/financial_result_contract.py` | `55a87fadce62b1c8d58ac206038d3f5144eaaaf30d4ef9ec82323c5240d7a34b` |
| `dayu/fins/domain/xbrl_result_contract.py` | `81844c4b08cae67f185e862ec69eafcb14ef848eec247bdbf127511a625fc2db` |
| `dayu/fins/pipelines/sec_fiscal_fields.py` | `f99725e34f3ccbf52a2b8f152d403e3bddfc62f811597130e0df1d19752e0191` |
| `dayu/fins/processors/bs_report_form_common.py` | `78a6503405196022ed9a20936ea17707b36d5bb8940371388319f58fd0266506` |
| `dayu/fins/processors/bs_six_k_processor.py` | `745727883a2a35af717295506b9b57c6d8c130d976db5be2ee309602b177ede5` |
| `dayu/fins/processors/financial_base.py` | `c591e7538f68dc9cf25f50dbea0a061d7e658a4348bc30b5f4e0fd9769c9a374` |
| `dayu/fins/processors/html_financial_statement_common.py` | `c9a4795fedb7db0454e0ade0513289c68053ef78f535b1483df8dac433379628` |
| `dayu/fins/processors/report_form_financial_statement_common.py` | `c5cbe60cf34a2b623658656c925d4afe81874793822c2fe978f6c77467948fcd` |
| `dayu/fins/processors/sec_processor.py` | `f56fd3a35164eefc99d9e2d0f732f09f5823ad53287b96cd6107e107194e4f7b` |
| `dayu/fins/processors/sec_xbrl_query.py` | `3e787b8a08a5486474b1f72e71c8f4fd93c1bf01aafbc11bf32d9512a1a223f8` |
| `dayu/fins/processors/six_k_form_common.py` | `6fb5758cdc26dae6811f64e5ca0df8008c2030698bcb8fa1187aa368edc9c139` |
| `dayu/fins/tools/fins_tools.py` | `ab096833a249868b50dc25dde23a6a9c512bfe5fe757c7520df791dc077f7a4e` |
| `dayu/fins/tools/read_runtime.py` | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` |
| `dayu/fins/tools/read_runtime_helpers.py` | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` |
| `dayu/fins/tools/result_types.py` | `f7ee9d1c31e2e9e62c87bb717da229d0f3182e91af15ea9ac45121da76bd1d83` |
| `tests/README.md` | `6c0614afd2b4a6c1a78988cc4512e2b4d0e21528f8e5cc5af69959de8dfe0454` |
| `tests/fins/test_financial_read_contracts.py` | `75f6e7f6fee615eca9c1c26bc5af768ffc527677c66d9cf5b76cbaac5879c0a4` |
| `tests/fins/test_fins_read_runtime.py` | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` |
| `tests/fins/test_fins_storage_provider.py` | `a2885ce6fd62909a2760d900a46181984ea83e7351037905e28581eb5f27b872` |
| `tests/fins/test_processor_read_consistency.py` | `da55b5eb32a18eeef425a264fe9a172d888f9c2608dad9d9a0a098e4fe955459` |
| `tests/fins/test_read_runtime_semantic_ownership_guards.py` | `553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d` |
| `tests/fins/test_sec_pipeline_download.py` | `f82c1416deac4f95cbe3e3feb4547410d077d41139fa0d8ac1915ca6d44a0c21` |

Untracked protected artifacts：

| Path | Content SHA-256 |
|---|---|
| `docs/reviews/wu-semantic-ownership-01-r08-s1-implementation-codex.md` | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` |
| `docs/reviews/wu-semantic-ownership-01-r08-s2-cumulative-implementation-codex.md` | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` |

## 10. README decision

README trigger 已检查。本次新增 delta 只是零 caller private dead-helper definition deletion，不改变
用户可见 contract、tool schema、安装/CLI 工作流、测试职责或分层关系。按 accepted plan §6.8，
不修改 `dayu/fins/README.md`、`tests/README.md`、根 `README.md` 或 `dayu/README.md`。当前两个
README tracked changes均是受保护的 stopped cumulative tree 内容，本次未触碰。

## 11. 未运行 gates 与 residual risks

由于第一个 exact proof 已失败，下列命令/验证均按 stop condition **未运行**：

- fresh all-five proof；
- 再次 `coverage erase` 后的 focused、aggregate 与完整 `tests/fins -q`；
- forced-truncation、AAPL、HTML、no-statement real smokes；
- 15-file exact-key whole-file coverage checker；
- full pyright、scoped Ruff；
- §5.5/§6.7 的 source/AST/LLM/README/security/unique-count/no-touch 完整 scans；
- `git diff --check`。

Residual risk / Controller decision needed：

1. accepted plan 的 deletion arithmetic/exact proof 与本 tree 实测不一致：expected
   `382/482`，actual `381/485`。当前证据只证明 exact lock 失败；未获授权定位这 `-1 covered / +3
   statements` 差异的 root cause。
2. all-five 是否能达到 `>=388/482` 未验证，不能宣称 candidate 5 为 first/shortest
   threshold-crossing prefix。
3. 完整 acceptance gate 未运行，当前 cumulative tree 不能进入 immutable code review lock。
4. 三个 edgar deprecation warnings 仍存在；它们没有导致本次测试失败，但本 gate 未获授权处理。

## 12. Handoff

保留唯一 helper deletion、`.coverage` 与 candidate-4 JSON 现场以及本 artifact，立即停回
Controller。Controller 必须先裁决 exact proof drift；不得把本 artifact 当作 implementation PASS，
不得进入 code review、aggregate deepreview、accepted implementation commit、R09-R12、push 或 PR。
