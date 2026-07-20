# WU-SEMANTIC-OWNERSHIP-01 / R08 coverage-statement drift implementation evidence

## 1. Verdict

`STOPPED / PREFIX_SIX_EXACT_DRIFT`

本 artifact 记录同一 R08 implementation task 的 fail-closed stopped evidence，不代表 implementation
通过，也不授权完整 acceptance validation、code review、aggregate deepreview、commit 或后续 work unit。

Fresh prefix-five 精确匹配 accepted plan；只实施 candidate 6 授权 delta 后，fresh prefix-six 的测试全部
通过且 coverage 已超过 80%，但 numerator 实测为 `391`，不等于授权的 `390`。根据 exact stop
condition，AgentCodex 保留现场并停止，没有降低门槛、增加第七项、修改 production 或继续执行后续验证。

## 2. Gate、lineage 与 re-entry locks

当前 gate 是既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 内部 R08 coverage-statement drift
implementation continuation，不是新 WU。

| 项目 | 复核结果 |
|---|---|
| HEAD / authorization transition | `cc06174bb165ab347de1fb6cb9524ba193ff26af` |
| accepted plan commit | `261df95f54dbb8cece3919b898dc26ebe1582141` |
| final plan SHA-256 | `115a6429653e4011cf68fc9f3f7e9d7d08431696e0c1a80269c56d2de71dc401` |
| stopped `dayu/fins + tests` binary diff | `3d9df8fefc485d0d19421fe6d2a3fe0402bf6f27d3b821d51125e039fa52ddf0` |
| `read_runtime_helpers.py` entry | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` |
| `read_runtime.py` actual owner | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` |
| guards entry | `553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d` |
| shared runtime test | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` |
| S1 artifact | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` |
| S2 artifact | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` |
| staged tree | empty |

复核命令：

```bash
git rev-parse HEAD
git log -6 --oneline --decorate
git merge-base --is-ancestor 261df95f54dbb8cece3919b898dc26ebe1582141 HEAD
git show -s --format='%H %s' 261df95f54dbb8cece3919b898dc26ebe1582141
git show -s --format='%H %s' cc06174b
shasum -a 256 \
  docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md \
  dayu/fins/tools/read_runtime_helpers.py \
  dayu/fins/tools/read_runtime.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py \
  tests/fins/test_fins_read_runtime.py \
  docs/reviews/wu-semantic-ownership-01-r08-s1-implementation-codex.md \
  docs/reviews/wu-semantic-ownership-01-r08-s2-cumulative-implementation-codex.md
git diff --binary -- dayu/fins tests | shasum -a 256
git diff --cached --name-only
```

全部 lock 在任何 proof 或 test mutation 前精确匹配；candidate 6 当时不存在，staged tree 为空。

## 3. Retained deletion 与 actual-owner source/AST proof

Source proof 命令与结果：

```bash
if rg -n '\b_collect_available_document_types\b' dayu tests; then
  echo 'FAIL old helper definition/caller/import remains'
  exit 1
fi
echo 'PASS old helper source matches=0'
```

```text
PASS old helper source matches=0
```

随后执行 accepted plan §6.7.G 的完整 AST proof。该 proof 遍历 `dayu/**/*.py` 与 `tests/**/*.py`，
精确统计旧 `_collect_available_document_types` 的 definition、caller、import，并解析
`dayu/fins/tools/read_runtime.py` 中实际 owner。结果为：

```text
PASS old helper definition/caller/import=0; actual typed/sorted owner definition/caller=1
```

AST proof 同时确认：

- actual owner 精确为 `_collect_available_document_types_for_source_documents`；
- 输入/返回 annotation 精确为 `list[_SourceDocumentSummary] -> list[str]`；
- owner 直接调用 `resolve_document_type_for_source`；
- owner 只有一个 `return sorted(...)`；
- actual owner definition 与 caller 各一个。

原五个 exact candidate nodes 也在 prefix-five 前逐项存在：

```text
test_list_documents_projects_stable_document_type_and_filter_contract
test_read_section_projects_minimal_navigation_payload_and_rejects_unknown_ref
test_get_table_projects_self_describing_data_shapes_and_rejects_unknown_ref
test_query_xbrl_facts_selects_default_concepts_from_typed_taxonomy
test_search_next_section_projection_ranks_business_evidence_per_query
```

## 4. Fresh prefix-five proof

命令：

```bash
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
  tests/fins/test_fins_storage_provider.py
python -m coverage json -o workspace/tmp/r08-prefix-five-proof-coverage.json
python - workspace/tmp/r08-prefix-five-proof-coverage.json <<'PY'
import json
from pathlib import Path
import sys

target = "dayu/fins/tools/read_runtime_helpers.py"
summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["files"][target]["summary"]
covered = summary["covered_lines"]
statements = summary["num_statements"]
percent = summary["percent_covered"]
print(f"PREFIX_FIVE_PROOF {target}: {covered}/{statements} = {percent:.8f}%")
if covered != 387 or statements != 485 or percent >= 80.0:
    raise SystemExit(1)
PY
shasum -a 256 workspace/tmp/r08-prefix-five-proof-coverage.json
```

Exact result：

```text
collected 391 items
391 passed, 3 existing edgartools warnings
PREFIX_FIVE_PROOF dayu/fins/tools/read_runtime_helpers.py: 387/485 = 79.79381443%
43986a2d9aca926a26396d420feea966be1526bc98da1c2fd1620335282b59fb  workspace/tmp/r08-prefix-five-proof-coverage.json
```

因此 prefix-five 精确满足 `387/485 = 79.79381443% < 80.00%`，candidate 6 mutation gate 打开。

## 5. 唯一 guards delta

只修改 `tests/fins/test_read_runtime_semantic_ownership_guards.py`：

1. 在既有 `dayu.fins.tools.read_runtime_helpers` import block 新增唯一 production symbol import
   `resolve_document_type_for_source`；
2. 在原五个连续 owner nodes 后新增唯一节点
   `test_document_type_resolver_projects_material_other_and_cn_categories`；
3. 节点具有完整中文 docstring，并直接断言：
   - `UNLISTED_MATERIAL + SourceKind.MATERIAL.value -> material`；
   - `None + SourceKind.FILING.value -> other`；
   - `FY + SourceKind.FILING.value -> annual_report`。

没有 direct `_resolve_document_type`、mapping constant、fake repository、monkeypatch、compatibility
input、参数化 omnibus、empty execution、skip/xfail 或 coverage pragma/omit。本轮没有修改 production、
shared/其它 tests、README、plan、control、prior reviews 或 S1/S2 artifacts。

Candidate 6 后 guards SHA-256：

```text
cc4c5267241093e55d80e648f8d1013f7b71f52ace1f244447869d3afced9274
```

## 6. Fresh prefix-six proof 与 exact drift

命令：

```bash
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
  tests/fins/test_fins_storage_provider.py
python -m coverage json -o workspace/tmp/r08-prefix-six-proof-coverage.json
python - workspace/tmp/r08-prefix-six-proof-coverage.json <<'PY'
import json
from pathlib import Path
import sys

target = "dayu/fins/tools/read_runtime_helpers.py"
summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["files"][target]["summary"]
covered = summary["covered_lines"]
statements = summary["num_statements"]
percent = summary["percent_covered"]
print(f"PREFIX_SIX_PROOF {target}: {covered}/{statements} = {percent:.8f}%")
if covered != 390 or statements != 485 or percent < 80.0:
    raise SystemExit(1)
PY
```

Exact result：

```text
collected 392 items
392 passed, 3 existing edgartools warnings
PREFIX_SIX_PROOF dayu/fins/tools/read_runtime_helpers.py: 391/485 = 80.61855670%
checker exit code: 1
b4c103423956543069ef89434cb7190d3e32b2847cff9f6320dc0a6c6f7b4dee  workspace/tmp/r08-prefix-six-proof-coverage.json
```

测试与阈值关系均通过，但 exact numerator drift：计划要求 `390/485 = 80.41237113%`，实际为
`391/485 = 80.61855670%`。因此 verdict 只能是 `STOPPED / PREFIX_SIX_EXACT_DRIFT`。

## 7. Fresh JSON 同源 root evidence

只读比较两个 fresh coverage JSON 的 `executed_lines`，结果为：

```text
PREFIX_FIVE covered_lines=387 num_statements=485 percent_covered=79.79381443298969
PREFIX_SIX covered_lines=391 num_statements=485 percent_covered=80.61855670103093
NEWLY_COVERED_LINES [344, 346, 348, 442]
344:         return "material"
346:         return "other"
348:         return _CN_FORM_TYPE_TO_DOCUMENT_TYPE[form_type]
442:         return None
```

第 `344/346/348` 行是 accepted finding 识别的三个 `_resolve_document_type` 分类分支。第 `442` 行位于
`_normalize_form_type_for_matching`：candidate 6 的 `form_type=None` public-owner 调用先经过
`resolve_document_type_for_source -> _normalize_form_type_for_matching(None)`，因此额外执行
`if normalized is None: return None`，之后才进入 `_resolve_document_type(...)->"other"`。

这份 direct fresh JSON/source evidence 证明，prefix-six 相对 prefix-five 的实际增量是四个 statements，
不是计划预测的三个；不是测试失败、display rounding 或 denominator drift。AgentCodex 不自行放宽 exact
lock，也不把 `391/485` 冒充授权通过，等待 Controller 裁决。

## 8. Final stopped-tree evidence

| 项目 | stopped result |
|---|---|
| prefix-five JSON SHA-256 | `43986a2d9aca926a26396d420feea966be1526bc98da1c2fd1620335282b59fb` |
| prefix-six JSON SHA-256 | `b4c103423956543069ef89434cb7190d3e32b2847cff9f6320dc0a6c6f7b4dee` |
| current guards SHA-256 | `cc4c5267241093e55d80e648f8d1013f7b71f52ace1f244447869d3afced9274` |
| cumulative `dayu/fins + tests` binary diff | `e40de2a03ad1240ef78bf9d36e28195f54a9166f344dd03c73bf1d0e6f63f33f` |
| `read_runtime_helpers.py` | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b`，no-touch |
| `read_runtime.py` | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657`，no-touch |
| shared runtime test | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692`，no-touch |
| S1 artifact | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748`，no-touch |
| S2 artifact | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648`，no-touch |
| staged tree | empty |
| `git diff --check` | PASS |

README decision：本 continuation 只增加一个 owner contract test，且当前 gate 已因 exact proof drift 停止；
没有用户可见 contract、工具 schema、安装/CLI 工作流、测试职责或分层关系变化，因此不修改任何 README。

## 9. 未执行项、残余风险与 stop status

由于 prefix-six exact drift 已触发 stop condition，以下项目明确**没有运行**：

- prefix-six 之后的完整 §6.6 focused/aggregate/full Fins tests；
- 三段 forced-truncation、真实 AAPL/HTML/no-statement acceptance smokes；
- final 15 changed production exact-key coverage checker；
- full pyright；
- changed Python scoped Ruff；
- final §6.7 README/source/AST/propagation/security/scope/no-touch scans。

也没有 stage、commit、push、创建 PR、实施 R09-R12、Issues 142/151/175/177/178、统一 authorization
或 Topic 8-9 code。

唯一 current residual 是 exact proof arithmetic 与 fresh execution evidence 不一致。Owner/destination 是
R08 Controller adjudication；在 Controller 更新或重新授权 exact boundary 前，当前 implementation 不得继续。

Stop status：保留 candidate 6 授权 delta、两个 fresh JSON 与本 stopped artifact，停回 Controller。
