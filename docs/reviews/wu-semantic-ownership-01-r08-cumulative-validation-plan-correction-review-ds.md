# WU-SEMANTIC-OWNERSHIP-01 / R08 Cumulative Validation Plan Correction — Adversarial Plan Review (DS)

## 1. Gate 与结论

| 项 | 值 |
|---|---|
| umbrella / sub-WU | 既有 `WU-SEMANTIC-OWNERSHIP-01` / `R08`；不是新 WU、feature 或 issue |
| review target | corrected plan `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md` + AgentCodex correction artifact + Controller validation + S1 implementation evidence |
| before accepted plan SHA-256 | `bb37b88b46b2247530d6ce5cafdf875feaee1695a63e7d63f93ada9255e90251` |
| corrected plan SHA-256 | `4ff2c00c5999cf20ff314afd7e9a0fa041c32d2f36c23566d21752887c997e3d` |
| protected 14-path diff SHA-256 | `0d985b85aa65d7c4b06d9ee464cd73fc4a39ef2ee0934f376b0b845a09b20f57` |
| review verdict | **PASS-WITH-FINDINGS** — 4 findings (1 Low-Medium, 3 Low)；无 blocking/high/严重 finding |
| authorized | 本 artifact 写入 `docs/reviews/`；不修改 plan、product、tests、README、control/controller artifact、S1 artifact；不实施 S2；不 stage/commit/push/PR |

## 2. Review scope 与 assumptions tested

### 2.1 已验证的假设

| 假设 | 验证结果 | 证据 |
|---|---|---|
| corrected plan SHA 匹配 AgentCodex 记录 | PASS | 独立重算 `shasum -a 256` → `4ff2c00c...` 精确匹配 |
| protected 14-path diff SHA 精确等于 Controller 锁定值 | PASS | 独立重算 `git diff --binary -- <14路径> \| shasum -a 256` → `0d985b85...` 精确匹配 |
| staged tree 为空 | PASS | `git diff --cached --name-only` 无输出 |
| `git diff --check` 通过 | PASS | exit 0，无 whitespace 错误 |
| Controller §3 九项 correction 全部映射入 plan | PASS | 逐项对照 AgentCodex §4.2 closure table 与 plan 对应节：§2.1/§5.1/§5.3/§5.4/§5.6/§6.1/§6.5/§6.6/§6.7/§6.9/§8/§9 均有对应 |
| §4 product contracts 未改变 | PASS | §4.1 Financial、§4.2 XBRL、§4.3 public projection、§4.4 tool schema 与 accepted plan 一致 |
| S1/S2 production/test allowlist 未改变 | PASS | §5.1 十二 production + 三 tests、§6.1 四 production + 四 tests + 三 regression 未变 |
| R07 no-touch 约束不变 | PASS | §2.2 表格明确 R07 不可回改；§6.7(D) R07 propagation scan 保留 |
| Host truncation owner 不变 | PASS | §6.4 明确 "本R08不修改Host"；stop condition "不得越界改Host" |
| Topic 8-9 no-code 不变 | PASS | §2.3 "Host generic truncation/cursor/fetch_more、Engine、Service、UI" 明确 out-of-scope |
| Issues 142/151/175/177/178 deferred | PASS | §2.3 明确 out-of-scope；§8 stop table 禁止顺手实现 |
| R09-R12 deferred boundaries 不变 | PASS | §2.3 明确 out-of-scope；§7 "依次继续R09、R10、R11、R12" |
| S1→S2 仍是同一累计 destructive cutover | PASS | §5.4 "S1 完成实现后直接在同一未提交 tree 上进入 S2"；§5.6 "S1/S2 之间不 stage、不 commit" |
| ToolDefinition.callable 公开可访问 | PASS | `dayu/fins/tools/fins_tools.py:1040` docstring 明确: "本函数只保留给直接调用 ``ToolDefinition.callable`` 的测试" |
| FrameworkToolName/FrameworkToolPolicyView 存在 | PASS | `dayu/host/__init__.py` 公开导出；`default_framework_tool_policy_view` 在 `dayu/host/tooling.py` |
| `_tool_runtime` helper 已含 `enable_truncation_manager` 参数位 | PASS | `tests/fins/test_fins_storage_provider.py:5814` 当前硬编码 `enable_truncation_manager=False` |
| `coverage json` 支持 `-o` flag | PASS | coverage.py 7.13.5 `--help` 确认 `-o OUTFILE` |
| coverage JSON `summary.percent_covered` 字段名正确 | PASS | coverage.py 7.x JSON schema 确认 |
| `dayu/fins/` 下存在非 Python 文件 | PASS | `dayu/fins/README.md` 存在；S2 README allowlist 会修改它 |

### 2.2 本 review 未验证的假设（需 S2 实施期验证）

- S2 累计测试集能否将 7 个处理器文件 (当前 41%–67%) 驱动到逐文件 ≥80%
- pre-Host callable → Host envelope → fetch-more 三段公开 seam 在 S2 新 `PublicXbrlQueryResult` 下是否完全可观测
- 累计 coverage JSON 路径格式与 `git diff --name-only` 输出是否可直接匹配

## 3. Controller §4 六项 challenge points 逐项审查

### 3.1 changed-production manifest 是否只含 Python

**审查结论：PASS — 但 manifest 生成命令存在次要歧义，见 F1。**

`git diff --name-only --diff-filter=ACMR -- dayu/fins` 会包含 `dayu/fins/README.md`（S2 README allowlist 明确要求修改它）。Plan 文本写的是 "changed production Python 文件" 但 shell 命令没有 `| grep '\.py$'` 过滤。实际 changed production manifest 当前为 11 个 `.py` 文件（全部在 `dayu/fins/` 下），S2 后将新增最多 4 个 tools `.py` 文件。该歧义不会导致 coverage gate 误报（README 不在 coverage JSON 中，不会触发假阳性），但可能让 implementation agent 困惑 manifest 是否应手动过滤。

### 3.2 coverage JSON 逐文件阈值是否可执行

**审查结论：PASS — coverage.py 7.13.5 JSON 格式已确认，但缺少自动化 checker，见 F2。**

`summary.percent_covered` 是 coverage.py JSON 的正确字段路径。Plan 的 `coverage json -o workspace/tmp/r08-cumulative-coverage.json` 命令语法正确。Manifest 生成 + JSON 读取的两步流程可手动执行，但没有提供等价于 `python -c "import json; ..."` 的自动化判定脚本；implementation agent 可能用 ad-hoc 方式判定，增加人为失误风险。

### 3.3 累计测试与 test diff allowlist 是否无歧义

**审查结论：PASS — 无歧义。**

§6.6 累计 validation 命令分为四个明确 tier：
1. S1 focused owner matrix（含 `-k` 过滤器，精确到 contract keywords）
2. S2 focused/public matrix（含 shared test file 的 normalize/dedup `-k` 排除 + 单 node 精确选择）
3. 三段 forced-truncation + AAPL/HTML/no-statement smokes（精确到 node ID）
4. 完整 Fins regression + 逐文件 coverage（限定 8 个 allowlist test 文件）

S1 test allowlist（3 文件）、S2 test allowlist（4 文件）、zero-diff regression（3 文件）清晰分离。S1/S2 shared test file `test_fins_read_runtime.py` 的 symbol 边界在 §5.1 逐 node 列出。无歧义。

### 3.4 S1/S2 symbol/entry boundary

**审查结论：PASS — 边界清晰，无残留矛盾。**

- S2 entry condition（§6.1）：14-path hash 匹配 + tree 未 stage/commit + 无其他 scope 混入。该检查在 S2 开始前执行，是精确的 binary 边界。
- shared `test_fins_read_runtime.py` symbol boundary（§5.1）：S1 只迁移 1 个 fiscal node + 2 个 import/fixture；S2 只迁移 6 个 normalize/dedup nodes。每个 node 以 exact pytest node ID 列出。
- S1 artifact 定位为 "blocked intermediate evidence"（§5.4），不声明 acceptable product state；消除了旧 plan 中 S1 独立 gate 的边界矛盾。
- S2 期间允许修改 S1 test 文件以补充 coverage（§6.6 "只能在 §5.1/§6.1 已有 test allowlist 中修改"），但需与对应 owner 直接相关。该 clause 是必要的 coverage closure 路径，不构成边界矛盾。

### 3.5 immutable code review→fix/re-review→aggregate deepreview→commit 顺序

**审查结论：PASS — 顺序正确，但有一个 revalidation cascade gap，见 F3。**

§6.9 完整顺序：
```
累计 validation 全绿 → Controller lock (content manifest + binary diff hash)
→ MiMo/DS 并发完整 code review（同一 immutable cumulative tree）
→ Controller adjudication → AgentCodex fix accepted findings
→ 新 hash 上重跑完整累计 validation → 双路完整 re-review
→ Controller 逐条关闭 → §7 aggregate deepreview
→ deepreview findings fix/re-review → Controller authorize commit
```

核心约束到位：任一 fix 使旧 hash/review 失效；两路 reviewer 审查完整累计 diff 而非仅 S2 增量；S1/S2 不做中间 commit。唯一 gap 是 deepreview 后的 revalidation cascade 未显式写回 §6.6（见 F3）。

### 3.6 forced truncation/R07/security/deferred/no-code 是否保持

**审查结论：PASS — 全部保持，forced-truncation 有一个次要 contract fragility，见 F4。**

- **Forced truncation**：§6.4 设计完整，三段公开 seam (pre-Host callable → Host envelope → fetch-more) + stop condition + 禁止越界改 Host。`ToolDefinition.callable` 公开可访问（代码证据确认）。
- **R07 no-touch**：§2.2 不可回改表 + §6.7(D) `git diff -U0` 逐 symbol 核验 + guard tests 保留。
- **Security**：§6.7(E) retained-security/no-touch scan 显式列出 R06/R07 storage/identity/revision/snapshot/citation/containment/symlink/atomic publication/recovery/Host truncation owner。
- **Deferred/no-code**：§2.3 out-of-scope + §8 stop conditions + §10 plan-correction gate 自检均保持。R09-R12/Issues 142/151/175/177/178/Topic 8-9/统一 authorization 均未进入。

## 4. Findings

### F1-未修复-低-covered-production manifest 命令缺少 .py 后缀过滤

- **位置**: §6.6 累计 validation gate，coverage enforcement 段落
- **问题类型**: 可实施性 gap
- **当前写法**:
  ```
  Coverage enforcement 必须从当前 `git diff --name-only --diff-filter=ACMR -- dayu/fins`
  生成实际 changed production manifest
  ```
- **反例/失败场景**: S2 按 §6.2 README allowlist 修改 `dayu/fins/README.md` 后，该命令会把 `dayu/fins/README.md` 包含在 manifest 中。Implementation agent 若机械读取 JSON 查找该路径会发现 coverage JSON 中不存在 README，可能误报为 "缺失文件" 导致 gate 失败，或浪费排查时间。
- **为什么有问题**: Plan 文本写 "changed production Python 文件" 但 shell 命令没有等价过滤。`dayu/fins/README.md` 是 `dayu/fins/` 下唯一非 Python 文件，歧义范围有限，但仍构成实施指令不精确。
- **直接证据**:
  - `find dayu/fins -type f -not -name '*.py' -not -name '__pycache__'` → `dayu/fins/README.md` 存在
  - §6.2 "README diff闭集: `dayu/fins/README.md`" → S2 会修改此文件
  - §6.6 manifest 命令未加 `| grep '\.py$'` 或等价的 Python-only 过滤
- **影响**: Implementation agent 困惑 / 需要自行判断过滤规则 / gate 可能因误读 manifest 失败
- **建议改法和验证点**: 在 manifest 生成命令后追加 `| grep '\.py$'`，或在 coverage enforcement 文本中明确 "从 manifest 中排除非 `.py` 后缀文件"。验证：S2 后运行 manifest 命令，确认只包含 `.py` 文件。
- **修复风险**: 低（单行 shell 管道追加，不影响任何逻辑）
- **严重程度**: 低

### F2-未修复-低-coverage 逐文件阈值缺少自动化判定脚本

- **位置**: §6.6 累计 validation gate，coverage enforcement 段落
- **问题类型**: 可实施性 gap
- **当前写法**:
  ```
  逐项读取 `workspace/tmp/r08-cumulative-coverage.json`：每个实际 changed production Python
  文件都必须出现在 coverage JSON 中且 `summary.percent_covered >= 80.00`。缺失文件与任一低于
  阈值的文件都使 gate 失败。
  ```
- **反例/失败场景**: Implementation agent 手工打开 JSON、目视检查每个文件的 `percent_covered`、手工比较阈值。文件数少（S1 11 + S2 最多 4 = 15）时可行，但人为判断 `79.95` vs `80.00`、路径格式不匹配（如 coverage JSON 用绝对路径而 manifest 用相对路径）时容易出错。
- **为什么有问题**: Plan 未提供等价于单行判定的自动化脚本（如 `python -c "import json, sys; data=json.load(open('...')); ..."`）。§6.6 明确禁止 aggregate `--fail-under` 是正确的，但逐文件 enforcement 的机械执行方式欠明确。
- **直接证据**: §6.6 只描述了 "逐项读取" 的 prose procedure，没有 `python -c` 单行 checker 或其他可复制粘贴的判定命令；同一节的 focused test、coverage run、pyright、Ruff、scans 均有精确可复制的 shell 命令，唯独 coverage enforcement 是自然语言描述。
- **影响**: Controller validation 时缺乏机械可复现的判定步骤；不同 agent 可能对 "逐项读取" 有不同实现
- **建议改法和验证点**: 在 §6.6 追加等价于以下的可执行判定命令：
  ```bash
  python -c "
  import json, sys, subprocess
  manifest = subprocess.check_output(['git','diff','--name-only','--diff-filter=ACMR','--','dayu/fins']).decode().split()
  manifest = [f for f in manifest if f.endswith('.py')]
  data = json.load(open('workspace/tmp/r08-cumulative-coverage.json'))
  files = {f: s['summary']['percent_covered'] for f,s in data.get('files',{}).items()}
  failed = []
  for f in manifest:
      matched = next((p for p in files if f in p or p.endswith('/'+f.split('/')[-1])), None)
      if matched is None: failed.append(f'{f}: missing from coverage')
      elif files[matched] < 80.0: failed.append(f'{f}: {files[matched]:.1f}%')
  if failed:
      print('FAILED:', *failed, sep='\n  ')
      sys.exit(1)
  print(f'PASS: {len(manifest)} files all >= 80%')
  "
  ```
  或简化为要求 implementation agent 产出判定脚本作为 artifact 附件。
- **修复风险**: 低（脚本可能因路径格式差异需要调适，但逻辑简单）
- **严重程度**: 低

### F3-未修复-低-中-aggregate deepreview 后未显式要求重跑 §6.6 完整累计 validation

- **位置**: §7 aggregate deepreview 与 §6.9 commit 边界
- **问题类型**: 验证闭环 gap
- **当前写法**:
  §7 "所有finding完成fix/re-review和Controller adjudication后才可进入accepted local implementation commit"
  §6.9 "只有累计 code review/fix/re-review闭环、aggregate deepreview及其必要fix/re-review全部通过后，Controller才可授权"
- **反例/失败场景**: Aggregate deepreview 发现一个 production code 问题（例如 `fact_count` 在某个边缘路径有第二个赋值点），AgentCodex 修复后只重跑了 AST scan，未重跑 full pyright 或逐文件 coverage。修复引入新 pyright 错误或降低某文件 coverage 至 80% 以下，Controller 在不知情下授权 commit。
- **为什么有问题**: §6.6 被声明为 "唯一累计/aggregate validation 真源"（§7 首句），但 §7 的 deepreview fix/re-review 段落没有显式写 "修复后必须重跑 §6.6 完整累计 validation"。当前措辞 "fix/re-review" 的 scope 由 implementation agent 自行理解，可能只跑 targeted 验证而非完整矩阵。
- **直接证据**:
  - §6.9: code review fix 后显式要求 "在新 hash 上重跑完整累计 validation"
  - §7: deepreview fix 后只说 "完成fix/re-review和Controller adjudication"，缺少 "重跑 §6.6 完整累计 validation" 的等价约束
  - §6.6 被 §7 首句声明为唯一累计/aggregate validation 真源，意味着任何 production change 后逻辑上必须重跑，但文本未显式写
- **影响**: Deepreview fix 可能引入未被完整 validation matrix 捕获的 regression
- **建议改法和验证点**: 在 §7 末尾（或 §6.9 deepreview 后）追加一句："所有 deepreview accepted finding 修复完成后，必须在新 hash 上重跑 §6.6 完整累计 validation（含 focused/aggregate/full-Fins tests、逐文件 coverage、full pyright、scoped Ruff、全部 scans、`git diff --check`），失败则继续 fix/re-review 循环。"
- **修复风险**: 低（纯文本约束追加，不改变 plan logic）
- **严重程度**: 低-中

### F4-未修复-低-forced-truncation 测试的 Host key-set 断言对 Host envelope 格式演化脆弱

- **位置**: §6.4 forced-truncation 验证设计，第 4 步
- **问题类型**: 测试脆弱性
- **当前写法**:
  ```
  Host completed value 必须满足 `set(post_value) == set(pre_value)`，除 `facts`
  外每个顶层 public sibling 都与 pre-Host value 逐项相等
  ```
- **反例/失败场景**: Host 未来为 cursor envelope 新增一个顶层 metadata key（如 `truncation_revision` 或 `envelope_version`），该 key 不属于 Fins 业务 contract 且不改变 `fact_count` 语义。当前断言 `set(post_value) == set(pre_value)` 会因多出的 key 而失败，导致 R08 gate 被一个与 R08 无关的 Host 变更阻塞。Plan 的 stop condition（"若实施时 post-Host key set 改变...立即 stop 回 Controller"）能捕获该情况，但 stop 后的处置（是修 Host、修 Fins 测试、还是裁决为 Host contract change）没有预定义路径。
- **为什么有问题**: 测试的正确意图是验证 Host 不改变 Fins business keys。但 `set(post_value) == set(pre_value)` 是 strict equality，不允许 Host 添加任何 governance-level key。如果 Host 的 cursor envelope 格式在 R08 与 S2 实施之间的时间窗口内演化，该断言产生 false positive failure。当前可行性探测是在旧 public contract 上执行的，pre/post key sets 完全相同 (`citation|data_quality|deduped_fact_count|document_id|facts|query_params|reason|ticker|total`)，但这个相等性是 Host 当前实现的快照，不是 Host 的 documented contract guarantee。
- **直接证据**:
  - §6.4 可行性探测结果："pre-Host 顶层 keys 与 post-Host 顶层 keys 完全相同"
  - §6.4 stop condition："若实施时 post-Host key set 改变...立即 stop 回 Controller"
  - Plan 未引用 Host truncation envelope format 的 documented contract（仅基于当前行为观察）
- **影响**: R08 gate 可能因无关 Host 变更 false-positive 失败；stop 后处置路径未预定义
- **建议改法和验证点**:
  1. 将断言从 strict key-set equality 放宽为 superset relation + business-keys equality：`assert set(pre_value.keys()).issubset(set(post_value.keys()))`，然后只对 pre_value 中每个 business key 做逐项相等断言
  2. 或在 plan 中预登记 "如果 Host 新增 governance-only key 导致 `set(post_value) != set(pre_value)`，Controller 可直接裁决为 Host contract evolution 并更新测试的 expected key set，不触发 stop"
  3. 至少将该脆弱性记录为 residual risk，使 Controller 在遇到时不意外
- **修复风险**: 低（断言逻辑调整或 residual risk 登记）
- **严重程度**: 低

## 5. Open questions

无。Plan 中所有假设在可验证范围内均被确认或已有明确 stop condition。以下两点为 residual risk 而非 open question：

## 6. Residual risks

| 风险 | 分类 | 建议跟踪 destination |
|---|---|---|
| S2 累计测试集（8 个 allowlist test 文件）能否将 7 个处理器文件从当前 41%–67% 驱动到逐文件 ≥80% | coverage closure risk | R08-S2 cumulative implementation gate；如不足需在 allowlist 内补 behavior tests |
| Host truncation envelope 格式在 S2 实施窗口内演化导致 F4 false positive | external dependency risk | R08-S2 forced-truncation smoke；若触发，Controller 按 F4 建议裁决 |
| `coverage json` 输出路径格式（绝对/相对）与 `git diff --name-only` manifest 格式不一致导致匹配失败 | tooling risk | R08-S2 cumulative validation gate；manifest 路径均为 repo-relative（`dayu/fins/...`），coverage JSON 默认也是 relative，概率低 |

## 7. Final plan review conclusion

**PASS-WITH-FINDINGS**

Corrected plan 在结构上 code-generation-ready。Controller §3 九项 mandatory correction 全部准确映射入 plan 对应节；§4 product contracts、S1/S2 allowlists、R07 no-touch、Host truncation owner、Topic 8-9 no-code、deferred Issues 与 R09-R12 boundaries 均未改变。两个 SHA（corrected plan `4ff2c00c...`、protected 14-path diff `0d985b85...`）独立重算精确匹配。

四项 finding 均为低或低-中严重度，不构成 blocking 条件：
- **F1**（manifest `.py` 过滤）和 **F2**（coverage checker 自动化）是实施清晰度改进，可在 Controller validation 或 S2 implementation 阶段就地修正
- **F3**（deepreview revalidation cascade）是文本补全，不影响 plan 整体逻辑
- **F4**（Host key-set assertion 脆弱性）是测试设计细化，有明确的 stop condition 兜底

无一 finding 要求重开 plan correction、修改 product contract、扩大 allowlist、削弱 coverage/pyright/scans 约束或提前进入 S2。建议 Controller 在接受 plan correction 时裁决是否将 F1-F4 纳入 plan 修正或登记为 S2 implementation 期注意事项。
