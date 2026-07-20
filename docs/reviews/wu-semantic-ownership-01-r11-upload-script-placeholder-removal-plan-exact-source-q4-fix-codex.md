# WU-SEMANTIC-OWNERSHIP-01 / R11 exact-source/Q4 plan-only fix evidence（AgentCodex）

## 1. Gate 与边界

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` 的 R11 continuation；不是新 WU，不进入 R12。
- gate：`R11-PR-BF-RR2-DS-F01`、`R11-PR-BF-RR2-DS-F02`、
  `R11-PR-BF-RR2-DS-F03` 的 Controller-authorized plan-only fix。
- 本 Agent 的 exact write allowlist 只有：
  1. `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`；
  2. 本 evidence artifact。
- 未进入 implementation；未修改 product、tests、README、design、CI、control 或既有 artifact；未复制 OLD 文件；
  未 stage、commit、push 或创建 PR。

动机成立。清屏后的 implementation Agent 若只看到 repo-relative OLD label，会在错误仓库内寻找真源；原 Q4 概括也没有锁定
OLD 的 filename-only marker boundary、exact `季报` substring 和 FY precedence。修复 owner 是 R11 plan 自身的
authority/source-lock、classification rule 与 owner-test matrix，不是下游实现、测试 fixture 或兼容层。

## 2. 输入、before/after 与只读真源锁

### 2.1 Plan before/after

| State | Lines | Bytes | SHA-256 |
|---|---:|---:|---|
| before（Controller immutable reviewed plan） | 886 | 74,647 | `817c9d2fde2112c244e14659e713041748e59d048b77e07be2f0b8def5175a92` |
| after | 892 | 75,434 | `35a15ae9acd3276d8fea95473d295cb01c9b39c591f1bac077ccc1b93029f571` |

before 内容在 mutation 前完整读取并保存在内存快照；after 与该快照做逐行 LCS diff。本次 plan 增量精确为
`8` 行删除、`14` 行新增、`5` 个 hunk，完整 diff 见 §5。

### 2.2 External OLD read-only sources

| Exact external source | Lines | Bytes | Full SHA-256 |
|---|---:|---:|---|
| `/Users/leo/workspace/dayu-agent/dayu/fins/cli_support.py` | 2267 | 73,820 | `248cc859d4dd0fdf8ed7829cc27dad48349227dfbd43f076414770166c93da45` |
| `/Users/leo/workspace/dayu-agent/dayu/fins/upload_recognition.py` | 555 | 20,921 | `5a45618b2545ad0ee024efb428de7e614c96b2c5bb0a222bf1586febc1dff816` |

两份文件均只从上述 absolute path 读取，没有复制到当前 repo、tracked fixture 或任何新兼容 surface。

## 3. Direct OLD Q4 evidence

完整读取了 `upload_recognition.py` 的 pattern 定义以及三个相关完整函数：

- line 53：`_Q4_QUARTERLY_MARKER_PATTERN` 的 pattern 是 exact literal `季报`；
- lines 199—218：`_infer_fiscal_from_filename(filename)` 只把传入的完整 filename 交给 period owner；
- lines 221—252：`_infer_fiscal_period_from_filename(filename)` 先判 `H1`、`FY`，再判 `Q1`—`Q4`；Q4 分支只在
  同一 filename 命中 `季报` 时返回 `Q4`，否则返回 `FY`；
- lines 255—307：`_infer_fiscal_from_path(file_path)` 仅在 filename 自身不足时读取 direct structured parent；
  `20YYQ4` parent 分支仍只对 `file_path.name` 搜索 exact `季报` marker。

对应 OLD tests 已完整读取：

- `/Users/leo/workspace/dayu-agent/tests/fins/test_pipeline_cli.py` 的
  `TestInferFiscalPeriodQ4Disambiguation` 与 `TestInferFiscalFromPath`；
- `/Users/leo/workspace/dayu-agent/tests/fins/test_cli_helpers_coverage.py` 的 filename inference coverage。

使用当前 `.venv/bin/python -B` 直接只读加载 exact OLD `upload_recognition.py`，五个 owner oracle 全部通过：

```text
2024Q4季报.pdf -> Q4
2024Q4季度报告.pdf -> FY
2024Q4年报.pdf -> FY
2021Q4/季报.pdf -> (2021, 'Q4')
2021Q4/季度报告.pdf -> (2021, 'FY')
```

这证明 `季度报告` 不是 Q4 quarterly marker alias，ancestor/path 也不是 marker 输入；无需重开产品裁决。

## 4. Accepted finding closure

### 4.1 `R11-PR-BF-RR2-DS-F01`

- §2.1 authority item 7 现在明确写出两个 external OLD absolute paths；
- §2.2 两个 OLD rows 使用相同 absolute paths，2267/555 lines 与 full SHA 保持不变；
- 未把 OLD 文件复制进当前 repo。

### 4.2 `R11-PR-BF-RR2-DS-F02`

- §2.1 authority item 4 与 §2.2 source-lock label 均改为 exact
  `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`；
- 1269 lines 与 SHA-256
  `30c27562ece3360c7d25e55a6f2b0b189999d35cca8004e83d42de3c8ccda838` 保持不变。

### 4.3 `R11-PR-BF-RR2-DS-F03`

- §5.2 rule 4 明确 marker 只检查 child 完整 filename，不检查 ancestor/path；
- quarterly marker 只认 exact contiguous literal substring `季报`，`季度报告` 不是 alias/宽松 pattern；
- `FY`/annual/年度报告/年报在 Q1—Q4 前判定；
- direct `20YYQ4` parent fallback 仍只检查 child filename 的 exact `季报`；
- §5.3 owner-test matrix 明确锁定 Controller 要求的五个 exact cases。

## 5. 本次 plan 增量精确 diff

```diff
--- plan.before
+++ plan.after
@@ -44,10 +44,11 @@
 1. `AGENTS.md` 的语义所有权、分层、类型、测试、README 与安全约束；
 2. `docs/fins/design.md` §10 与 `docs/ui/design.md` §1—2；
 3. Controller discussion Topic 7 final adjudication；
-4. umbrella remediation plan §7、§18、§20—22；
+4. `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md` §7、§18、§20—22；
 5. `docs/phaseflow-umbrella-optimization-control.md` 与当前 Controller control truth；
 6. 当前 CURRENT production code/tests/READMEs；
-7. 两个指定 OLD 文件只作为用户工作流与分类规则证据。
+7. 两个指定 OLD 文件 `/Users/leo/workspace/dayu-agent/dayu/fins/cli_support.py` 与
+   `/Users/leo/workspace/dayu-agent/dayu/fins/upload_recognition.py` 只作为用户工作流与分类规则证据。

 已裁决产品问题不重开。OLD 不拥有当前架构、API、类型或兼容需求；不得复制其 dict/`Any`、CLI/IO 混层、
 `subprocess.list2cmdline`、非原子写或其它历史实现。
@@ -61,7 +62,7 @@
 | umbrella optimization control | 302 | `6d924e919a4ba797e6213879aadca7bdd4f47a37418630e1ee43cb1995e461db` |
 | Controller discussion | 731 | `cd26760d626415c52caa13a724144b4d98f2a2b2fc159772e6d807833c01533a` |
 | Host / Engine / Tool / Fins / UI design | 3696 / 553 / 134 / 123 / 111 | `276d35e1...43e9` / `f2091260...f31` / `ddc6efc0...ea7c` / `97033cf1...7abdd` / `5a19c829...ed973` |
-| umbrella remediation plan | 1269 | `30c27562ece3360c7d25e55a6f2b0b189999d35cca8004e83d42de3c8ccda838` |
+| `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md` | 1269 | `30c27562ece3360c7d25e55a6f2b0b189999d35cca8004e83d42de3c8ccda838` |
 | CURRENT `dayu/fins/upload_batch.py` | 376 | `6767d30cfd788e584cef22e5109b1ae0b787ecaedc8581a4cfcf2c49d5ad6178` |
 | CURRENT `dayu/cli/commands/fins.py` | 1057 | `0db8ff2dedf541c2b58bc11342a02cd0bf4098bc9fcc19d948efa5cf4afc95a6` |
 | CURRENT `dayu/cli/arg_parsing.py` | 932 | `a0e25ad6c58f3f266ef1afc4447c4a7e875d18c23ad346550ccf8cfd283c1c2c` |
@@ -69,8 +70,8 @@
 | CURRENT `pyproject.toml` | 152 | `e076606fd68ab911291be92cdba1bda9df05835baf8db7f81b1d33d517ce6a25` |
 | root / `dayu/` / Fins / tests README | 348 / 265 / 793 / 293 | `2f5cebfd...a6e6a` / `16bbdc87da05f68ad7787086cf5e4646e011a8e8304991cb360916487fa85367` / `a4805995...9767` / `15bb09f8...1fba9` |
 | CURRENT `requirements.txt` | 12 | `d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a` |
-| OLD `dayu/fins/cli_support.py` | 2267 | `248cc859d4dd0fdf8ed7829cc27dad48349227dfbd43f076414770166c93da45` |
-| OLD `dayu/fins/upload_recognition.py` | 555 | `5a45618b2545ad0ee024efb428de7e614c96b2c5bb0a222bf1586febc1dff816` |
+| OLD `/Users/leo/workspace/dayu-agent/dayu/fins/cli_support.py` | 2267 | `248cc859d4dd0fdf8ed7829cc27dad48349227dfbd43f076414770166c93da45` |
+| OLD `/Users/leo/workspace/dayu-agent/dayu/fins/upload_recognition.py` | 555 | `5a45618b2545ad0ee024efb428de7e614c96b2c5bb0a222bf1586febc1dff816` |

 进入 implementation 前，Controller 必须以 accepted-plan commit 的 parent 重新锁定所有 production/test/README/CI
 输入。Controller-owned control 文件可因 gate transition 合法变化；任一 production contract、owner、allowlist 或依赖
@@ -270,8 +271,11 @@
 3. 候选 symlink、resolved escape 或非普通文件不得读取；进入 `skipped` 并给出明确安全原因。unsupported suffix 不进入
    recognized/material；测试固定其可读 skip/ignore contract，不能在 CLI 二次判定。
 4. fiscal year 使用首个 `20YY`；period 依 OLD patterns 支持 `Q1..Q4`、`1Q..4Q`、中文一至四季度、`H1` /
-   half-year/半年/中报/中期报告、`FY`/annual/年度报告/年报。Q4 含“季报”保留 Q4，否则为 FY。先看文件名；
-   文件名不足时只允许从直接 structured parent `20YYQn`/`20YYH1` 补齐，纯年份 parent 不能猜 period。
+   half-year/半年/中报/中期报告、`FY`/annual/年度报告/年报。Q4 marker 只检查 child 完整 filename，不检查
+   ancestor/path；quarterly marker 只认 exact contiguous literal substring `季报`，不把 `季度报告` 当 alias 或宽松
+   pattern；`FY`/annual/年度报告/年报在 Q1—Q4 前判定。先看 child 完整 filename；文件名不足时只允许从直接
+   structured parent `20YYQn`/`20YYH1` 补齐，纯年份 parent 不能猜 period；direct `20YYQ4` parent fallback 仍只检查
+   child filename 的 exact `季报`，命中为 Q4，否则为 FY。
 5. 当前 `upload_filings_from` 已有 explicit `--fiscal-year` / `--fiscal-period` 是用户事实：对应字段有值时逐字段覆盖
    推断值，无值时才用 OLD inference。filing 最终缺 year 或 period 则 skipped；material 可保留可选 fiscal fields。
    不从 mtime、排序、文件内容或 sibling 猜 metadata。
@@ -309,7 +313,9 @@
 ```

 owner tests 必须覆盖：supported/unsupported、non-recursive/explicit recursive/structured auto-recursive、文件名与父目录
-推断、Q4 分流、material routing precedence/name、explicit fiscal precedence、annual=5、periodic=latest-year/max6、
+推断、Q4 分流（至少精确断言 `2024Q4季报.pdf -> Q4`、`2024Q4季度报告.pdf -> FY`、`2024Q4年报.pdf -> FY`、
+`2021Q4/季报.pdf -> Q4`、`2021Q4/季度报告.pdf -> FY`）、material routing precedence/name、explicit fiscal
+precedence、annual=5、periodic=latest-year/max6、
 presentation=6、call=count(filtered reports)、zero recognized filings 时全部 call candidates typed skipped、financial
 statements no cap、同期优先级/tie、stable ordering、每类 skip reason、external-ancestor symlink allowed、source root-self
 symlink rejected、root 内 component/candidate symlink rejected、escape rejected、auto/create/update、
```

该 diff 之外，plan 的产品裁决、两个 implementation slices、allowlist、validation、Windows `PENDING_RELEASE_BLOCKER`、
security/deferred/no-code 边界保持不变。

## 6. Validation evidence

| Validation | Result |
|---|---|
| external `wc -l -c` + full `shasum -a 256` | PASS；见 §2.2 exact locks |
| exact plan labels assertion | PASS；CLI path `2` 次、recognition path `2` 次、remediation path `2` 次；旧 descriptive/relative row label 均不存在 |
| Q4 plan clauses + five exact owner cases assertion | PASS；12 个 required clause/case 全部存在 |
| direct OLD five-case oracle | PASS；见 §3 exact output |
| `git diff --check` | PASS；exit `0`，stdout 为空 |
| `git diff --cached --name-only` | PASS；exit `0`，stdout 为空，staged tree 为空 |
| product/test/README/design/CI scoped `git status --short` | PASS；exit `0`，stdout 为空 |
| product/test/README/design/CI scoped unstaged + staged `git diff --name-only` | PASS；exit `0`，stdout 为空 |
| before/after in-memory exact plan diff | PASS；仅 §5 的 5 个 hunk |

本 gate 只改 plan/evidence 文档，没有代码、schema、测试或 README 变更；因此未运行 product pytest、coverage、pyright、Ruff
或 implementation smoke，也没有把这些 implementation gates 虚报为本 plan-only gate 的结果。Windows release blocker、
security/deferred gates 与两个 implementation slices 均未执行或弱化，继续由后续获授权 gate 负责。

READY_FOR_CONTROLLER_R11_EXACT_SOURCE_Q4_PLAN_FIX_VALIDATION
