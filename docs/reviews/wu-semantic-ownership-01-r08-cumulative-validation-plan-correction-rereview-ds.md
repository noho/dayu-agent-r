# WU-SEMANTIC-OWNERSHIP-01 / R08 Cumulative Validation Plan Correction — Adversarial Complete Re-Review (DS)

## 1. Gate 与结论

| 项 | 值 |
|---|---|
| umbrella / sub-WU | 既有 `WU-SEMANTIC-OWNERSHIP-01` / `R08`；不是新 WU、feature 或 issue |
| review target | final plan `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`（完整全文，非增量） |
| review type | adversarial complete re-review；不只看增量，对 final plan 全文做独立验证 |
| before corrected-plan SHA-256 | `4ff2c00c5999cf20ff314afd7e9a0fa041c32d2f36c23566d21752887c997e3d` |
| final plan SHA-256（独立重算） | `87cc332828640de8b4cb4550f29251894111ef3471621bebbef828b66a3ce23d` |
| protected S1 14-path binary diff SHA-256（独立重算） | `0d985b85aa65d7c4b06d9ee464cd73fc4a39ef2ee0934f376b0b845a09b20f57` |
| review verdict | **PASS — 零新 finding** |
| authorized | 本 artifact 写入 `docs/reviews/`；不修改 plan、product、tests、README、control/controller/reviewer artifacts、S1 artifact；不实施 S2；不 stage/commit/push/PR |

两路原始 review（DS `PASS-WITH-FINDINGS`、MiMo `PASS`）共 8 findings，Controller 接受 5 个合并为 3 fix groups（`R08-CVPF-01..03`），拒绝 3 个（DS F4、MiMo F2/F3）。AgentCodex 修复后经 Controller validation 确认。本次 re-review 确认：3 fix groups 全部真正关闭、3 rejected 全部缺席、final plan 无新增 gap。

## 2. Review scope 与 assumptions tested

### 2.1 已验证假设

| 假设 | 验证结果 | 直接证据 |
|---|---|---|
| final plan SHA-256 等于 `87cc3328...` | **PASS** | `shasum -a 256` 独立重算，精确匹配 |
| protected 14-path binary diff SHA-256 等于 `0d985b85...` | **PASS** | `git diff --binary -- <14路径> \| shasum -a 256` 独立重算，精确匹配 |
| `git diff --check` 通过 | **PASS** | exit 0，无 whitespace error |
| `git diff --cached --name-only` 为空 | **PASS** | staged tree 空 |
| R08-CVPF-01（coverage manifest/exact-key checker）已关闭 | **PASS** | §6.6 含 Git top-level glob pathspec、NUL manifest、exact-key checker with fail-closed logic |
| R08-CVPF-02（Ruff 消费实际 changed Python manifest）已关闭 | **PASS** | §6.6 含 dayu/fins + tests/fins 双 pathspec、NUL manifest、os.execv 机械 handoff、空 manifest fail |
| R08-CVPF-03（aggregate deepreview fix 失效旧 validation）已关闭 | **PASS** | §7 显式声明旧 validation/content manifest/binary diff hash/两路 aggregate deepreview 全部失效，要求新 hash 上完整重跑 §6.6/§6.7 |
| DS F4（放宽 key-set equality）未实施 | **PASS** | §6.4 保留 `set(post_value) == set(pre_value)`，无 `issubset`/superset 放宽 |
| MiMo F2（§6.6/§6.7 两层描述混淆）未实施 | **PASS** | §6.7 仍是 §6.6 已纳入 scans 的具体展开，无新增重复 scan 路由或第二验证真源声明 |
| MiMo F3（行号/并发兼容）未实施 | **PASS** | plan 无 `行号`、`merge` 兼容文字；S1→S2 仍由同一 Agent 在同一 tree 顺序执行 |
| §6.6 shell 命令块（589-703）zsh 语法通过 | **PASS** | `sed -n '589,703p' <plan> \| zsh -n` exit 0；与 AgentCodex 原始验证一致 |
| coverage checker Python 脚本逻辑正确 | **PASS** | 独立验证：below-threshold→FAIL、missing-key→FAIL、all-pass→PASS、empty-manifest→FAIL |
| Ruff NUL-safe handoff 逻辑正确 | **PASS** | 独立验证：NUL split + os.execv path vector 构造正确、空 manifest 先于 Ruff 失败 |
| `FiscalPeriod`/`FISCAL_PERIODS` 真源存在且值集正确 | **PASS** | `dayu/fins/domain/filing_semantics.py:35,79` 确认为 `FY\|H1\|Q1\|Q2\|Q3\|Q4` |
| `FinancialScale` 真源存在且值集正确 | **PASS** | `dayu/fins/domain/financial_result_contract.py:25` 确认为 `units\|thousands\|millions\|billions` |
| S1/S2 production allowlist 无重叠 | **PASS** | S1 12 文件（processors/domain/pipelines）∩ S2 4 文件（tools）= ∅ |
| S1/S2 test allowlist 共享文件有明确 symbol 边界 | **PASS** | §5.1 以 exact pytest node ID 定义 S1 fiscal node 与 S2 六个 normalize/dedup nodes 边界 |
| `ToolDefinition.callable` 公开可访问 | **PASS** | `fins_tools.py:1040` docstring 确认保留给直接调用 `ToolDefinition.callable` 的测试 |
| S2 生产 allowlist 不含 `error_contract.py` | **PASS** | §6.1 显式声明 "不在allowlist" |
| `dayu/fins/tools/__init__.py` 不导出旧 result type 名 | **PASS** | 当前 `__init__.py` 无 `FinancialStatementResult`/`XbrlQueryResult` 引用 |

### 2.2 本 review 不做裁决的假设（需 S2 实施期验证）

- S2 累计测试集能否将 7 个 processor 文件（S1 诊断 41%–67%）驱动到逐文件 ≥80%：属于 R08-S2 implementation gate 的 coverage closure，不在 plan-review 范围内
- pre-Host callable → Host envelope → fetch-more 三段公开 seam 在 S2 新 `PublicXbrlQueryResult` shape 下是否完全可观测：可行性探测已在旧 contract 上完成，正式验证需 S2 产生 `fact_count` 后执行
- 累计 coverage JSON 的 `files` key 路径格式与 `git diff --name-only` repo-relative 输出一致：两者均从 repo root 运行，coverage.py 7.x 默认使用相对路径；若不一致，plan 已要求修正后重跑

## 3. R08-CVPF-01..03 逐项关闭验证

### R08-CVPF-01：coverage manifest 与 exact-key checker — CLOSED

- **Before**：§6.6 以自然语言要求从未限制后缀的 `git diff --name-only -- dayu/fins` 生成 manifest，再人工逐项查看 coverage JSON
- **After**：Git top-level glob pathspec `:(top,glob)dayu/fins/**/*.py` 直接生成 NUL-separated repo-relative manifest；可执行 Python checker 逐文件 exact-key lookup，manifest 空/key 缺失/<80.00% 均非零退出；明确禁止 basename/suffix/absolute-path/路径规范化 loose fallback
- **独立验证**：checker 逻辑在 below-threshold、missing-key、all-pass、empty-manifest 四个场景下行为正确；Git pathspec 在当前 tree 精确返回 11 个实际 changed production `.py` 文件，不含 README

### R08-CVPF-02：Ruff 机械消费 NUL manifest — CLOSED

- **Before**：`python -m ruff check <S1+S2全部实际修改的Python文件>` 是不可直接执行占位符，可能遗漏 tests
- **After**：双 pathspec `dayu/fins/**/*.py` + `tests/fins/**/*.py` 生成 NUL manifest，Python consumer 以 `os.execv` 机械传给 ruff；空 manifest 在 Ruff 前 exit 1
- **独立验证**：os.execv 将 `[python, -m, ruff, check, path1, path2, ...]` 作为完整 argv 传给当前 Python 环境；NUL split 逻辑正确；空 manifest 检测在 Ruff 调用前执行

### R08-CVPF-03：aggregate deepreview fix 失效旧 validation — CLOSED

- **Before**：§7 对 aggregate deepreview accepted fix 只写 `fix/re-review`，未显式使旧 validation/hash/deepreview 失效
- **After**：§7 显式声明 "旧累计 validation、changed-path content manifest、binary diff hash 与两路 aggregate deepreview 即全部失效。必须在新 hash 上重跑完整 §6.6 与 §6.7...全绿并锁定新 hash 后，再由两路 reviewer 对完整 aggregate tree 进行 re-review。只有两路 aggregate re-review 与 Controller 逐条 adjudication 全部关闭后，才可授权 accepted local implementation commit"
- **独立验证**：§7 失效条款覆盖全部关键 artifact（validation、manifest、hash、deepreview）；重跑要求覆盖 §6.6 与 §6.7 全部命令（tests、coverage、pyright、Ruff、scans、diff check）；re-review 要求双路完整；§9 checklist 同步该条件

**最终 closure：`3/3 CLOSED`；accepted source findings `5/5 COVERED`。**

## 4. 拒绝项缺席确认

| Finding | Controller disposition | 本 review 独立验证 |
|---|---|---|
| DS F4 | REJECT — strict Host/Fins public key-set proof retained | §6.4 保留 `set(post_value) == set(pre_value)`、stop condition、禁止越界改 Host；无 `issubset` 或 superset 放宽 |
| MiMo F2 | REJECT — §6.7 是 §6.6 详细 scan truth | §6.7 仍是 §6.6 纳入 scans 的具体命令展开；无新增重复 scan 路由、第二验证真源声明或执行混淆文字 |
| MiMo F3 | REJECT — sequential symbol-based shared-file edit | 无行号兼容、并发 seam、merge 策略或 import-block compatibility 文字；S1→S2 仍由同一 Agent 在同一 tree 顺序执行 |

同时确认：无上述三个 rejected finding 的任何替代 residual、fallback 文案或弱化实现。

## 5. 完整 plan 深度审查

### 5.1 Scope 与 owner

- §2.2 不可回改的 owner 表精确界定 R06/R07/R08 边界
- §2.3 out-of-scope 完整列出 R09-R12、Issues 142/151/175/177/178、统一 authorization、Host/Engine/Service/UI
- §4 product contracts（Financial producer、XBRL processor-internal、Public typed projection、Tool schema/description）自足闭合，字段/类型/必填性/枚举/闭集均在当前节完整定义
- Owner 链一致：producer domain → actual processor → public projection → tool description，每层只消费上一层，不回写

### 5.2 测试覆盖

- S1 owner tests（§5.3）：financial exact keys、optional reason、七值闭集、complete/partial matrix、actual producer contract、method absent/None/empty→`statement_not_found`、XBRL exact keys、flat params、bool rejection、producer 无 count
- S2 owner/public tests（§6.5）：public exact keys、producer→public 逐项相等、citation Mapping→dict 独立复制、flat query params、fiscal_period shared enum、normalize/dedup immutability、唯一 count 同源、tool description 自足性、real smokes（AAPL XBRL、HTML financial、no-statement）、forced-truncation 三段公开链
- S1/S2 test allowlist 无重叠（除 shared `test_fins_read_runtime.py` 有明确 symbol 边界）
- 零 diff regression tests（§6.1）明确列出并纳入累计 gate

### 5.3 累计状态机

```
S1 producer/processor implementation（blocked intermediate evidence）
→ S2 public projection implementation（同一 tree，不 commit）
→ §6.6 累计 validation gate（唯一真源）
→ Controller lock（content manifest + binary diff hash）
→ MiMo/DS 并发完整 code review
→ Controller adjudication
→ AgentCodex fix accepted findings
→ 新 hash 完整 revalidation
→ 双路 re-review
→ Controller 逐条关闭
→ Aggregate deepreview（§7）
→ Deepreview fix → 新 hash 完整 revalidation → 双路 aggregate re-review → Controller 逐条关闭
→ Controller 授权 single exact-scope local implementation commit
```

状态机完整且自洽：每一步的前置条件、失败处置、禁止补救均在 §5.4/§5.6/§6.9/§7/§8 明确定义。

### 5.4 S1→S2 顺序

- §5.4 明确 S1 不是独立 validation/review gate："S1 完成实现后直接在同一未提交 tree 上进入 S2"
- §5.6 明确 "S1 与 S2 是同一次破坏性 contract cutover；中间 commit 会把旧 public consumer 与新 producer 组合声明为可接受历史状态"
- §6.1 S2 entry condition：14-path binary diff SHA-256 匹配 + tree 未 stage/commit + 无其它 scope 混入
- 实施由同一 AgentCodex 在同一 tree 上严格顺序执行，不存在并发或 merge conflict

### 5.5 No-touch / deferred boundaries

- R06 transaction/publication owner：§2.2 不可回改表明确
- R07 identity/revision/snapshot/citation/provenance：§2.2 不可回改表 + §6.1 显式禁止修改 + §6.7.D R07 propagation scan
- Host truncation owner：§6.4 明确 "本 R08 不修改 Host、不私造 cursor/fetch_more、不静默丢弃超限 facts"
- R09-R12、Issues 142/151/175/177/178：§2.3 out-of-scope + §8 stop table
- `dayu/config/prompts/**`：§6.1 明确 "不改，只纳入 negative scan"

### 5.6 兼容 shim / 阈值弱化

- §4.3 明确 "不保留 re-export、alias、wrapper 或其它 compatibility path"
- §5.2 step 4 明确 "删除 `build_statement_locator` 及引用，不保留 wrapper/re-export"
- §5.4 明确 "不新增 compatibility field/type、lazy import、cast、ignore、test shim、skip/xfail、默认值或临时 adapter"
- §6.6 coverage checker 明确 "不得使用 aggregate `--fail-under`、changed-line coverage、pragma/omit、fake-only padding、skip/xfail 或阈值豁免"
- §8 stop table 逐项列出禁止补救方式
- 全文无 `hasattr`、`getattr`、`compat`、`fallback`、`shim`、`skip`、`xfail` 等弱化手段

**确认：final plan 无兼容 shim、无阈值弱化、无边界渗透。**

## 6. §6.6 命令可执行性与 fail-closed 验证

### 6.1 Shell 语法

```bash
sed -n '589,703p' docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md | zsh -n
# exit 0
```

精确边界 589（`source .venv/bin/activate`）到 703（`git diff --check`），不含 Markdown fence。`zsh -n` 通过，与 AgentCodex 原始验证一致。

### 6.2 Coverage manifest 与 checker

- Git pathspec `:(top,glob)dayu/fins/**/*.py` 当前精确返回 11 个 repo-relative `.py` 路径，不含 `dayu/fins/README.md`
- `**/*.py` 同时覆盖根级与递归 Python path（`git ls-files` 探测确认）
- Checker 对 manifest 空、path 非 `dayu/fins/*.py` contract、exact key 缺失、`<80.00%` 四种场景均非零退出
- Checker 使用 `os.fsdecode()` 处理 NUL 分隔字节，`read_text(encoding="utf-8")` 读取 JSON，均为标准正确方式

### 6.3 Ruff NUL-safe handoff

- 双 pathspec 直接生成 `dayu/fins/**/*.py` + `tests/fins/**/*.py` 的 NUL manifest
- Python consumer 以 NUL split 后构造完整 argv vector：`[python, -m, ruff, check, path1, path2, ...]`
- 空 manifest 在 `os.execv` 前 exit 1，不会把空路径集传给 Ruff 导致误报成功
- 零 diff allowlist 文件不会被伪加入（Git diff 自然排除）

### 6.4 累计 pytest 矩阵

累计 gate 命令分为四个清晰 tier：
1. S1 focused owner matrix（含 `-k` keyword filter）
2. S2 focused/public matrix（完整 allowlist tests 集）
3. Forced-truncation + AAPL/HTML/no-statement real smokes（exact node ID）
4. R08 aggregate matrix + full Fins regression + coverage session

每层可独立失败，fail-fast 阻止后续命令执行。覆盖 pyright、Ruff、scans、diff check，完整性无遗漏。

## 7. Findings

**零 new finding。**

经完整全文 adversarial re-review，独立重算两个 hash 精确匹配，`R08-CVPF-01..03` 全部真正关闭，DS F4/MiMo F2/F3 全部缺席，coverage/Ruff 命令可复制执行且 fail-closed，aggregate deepreview fix invalidation 完整，scope/owner/测试/累计状态机/S1→S2 顺序/no-touch/deferred boundaries 均无矛盾或 gap，无兼容 shim 或阈值弱化。

以下为 review 中检验但判定为不构成 finding 的项目：

| 检验项 | 判定 | 理由 |
|---|---|---|
| `diff-filter=ACMR` 不含 Type-changed (T) | 不构成 finding | R08 不涉及文件类型变更；即使发生，pyright/full regression 会捕获 |
| 无显式 re-review max-cycle count | 不构成 finding | §7 "任一...全部失效" 是 hard invalidation guard；Controller 有权终止循环 |
| coverage JSON path 格式与 git diff 路径对齐是隐式假设 | 不构成 finding | plan §6.6 已写 "若 JSON key 不是同一 repo-relative exact path，必须修正...不得放宽匹配"，已是显式约束 |
| `dayu/fins/tools/__init__.py` 不在 allowlist | 不构成 finding | 当前 `__init__.py` 不导出旧/新 result type 名；S2 类型重命名无需修改它 |
| §6.6 coverage run 仅 8 个 allowlist test 文件，不包括完整 Fins regression | 不构成 finding | 完整 `pytest tests/fins -q` 已在同一 gate 中独立运行；coverage session 聚焦 changed production files 的行为覆盖 |
| `fins_tools.py` 当前硬编码 tool description 含 `total`/`deduped_fact_count` | 不构成 finding | `fins_tools.py` 在 S2 allowlist 中，§4.4/§6.2 step 5 明确要求改为消费 owner metadata/helper；§6.7.B negative scan 会捕获遗漏 |

## 8. Open questions

无。Plan 中所有可验证假设均已确认；需 S2 实施期验证的假设已登记为 residual risk（见 §2.2 与 §9）。

## 9. Residual risks

| 风险 | 分类 | 建议跟踪 destination |
|---|---|---|
| S2 累计测试集（8 allowlist test 文件）能否将 7 个 processor 文件从 S1 诊断 41%–67% 驱动到逐文件 ≥80% | coverage closure risk | R08-S2 cumulative implementation gate；如不足需在 allowlist 内补 behavior tests |
| Host truncation envelope 格式在 S2 实施窗口内演化导致 `set(post_value)==set(pre_value)` false positive | external dependency risk | R08-S2 forced-truncation smoke；plan 已有 stop condition 兜底 |
| coverage JSON `files` key 路径与 `git diff --name-only` repo-relative 输出格式不一致 | tooling risk | R08-S2 cumulative validation gate；plan 已要求修正后重跑，不得放宽匹配 |

以上均为 S2 实施期可验证的 residual risk，不构成 plan 层面的 gap。

## 10. Final plan review conclusion

**PASS**

Final plan 经过完整全文 adversarial re-review，独立重算 SHA-256 与 protected diff hash 均精确匹配。三个 fix groups（`R08-CVPF-01..03`）全部真正关闭且可复制执行、fail-closed；三个 rejected findings（DS F4、MiMo F2/F3）全部确认未实施。Aggregate deepreview fix 失效条款完整覆盖旧 validation/hash/review。Scope、owner、测试、累计状态机、S1→S2 顺序、no-touch/deferred boundaries 均自洽且无矛盾。无兼容 shim、阈值弱化、边界渗透或新增 gap。

Plan 是 code-generation-ready 的。Controller 可派发 AgentMiMo/AgentDS 两路完整 re-review 或直接进入 S2 implementation gate。

---

**Review artifact metadata**

- 独立重算 plan SHA-256：`87cc332828640de8b4cb4550f29251894111ef3471621bebbef828b66a3ce23d`
- 独立重算 protected S1 14-path binary diff SHA-256：`0d985b85aa65d7c4b06d9ee464cd73fc4a39ef2ee0934f376b0b845a09b20f57`
- 验证命令：
  ```bash
  shasum -a 256 docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
  git diff --binary -- dayu/fins/domain/financial_result_contract.py dayu/fins/domain/xbrl_result_contract.py dayu/fins/pipelines/sec_fiscal_fields.py dayu/fins/processors/bs_report_form_common.py dayu/fins/processors/bs_six_k_processor.py dayu/fins/processors/financial_base.py dayu/fins/processors/html_financial_statement_common.py dayu/fins/processors/report_form_financial_statement_common.py dayu/fins/processors/sec_processor.py dayu/fins/processors/sec_xbrl_query.py dayu/fins/processors/six_k_form_common.py tests/fins/test_financial_read_contracts.py tests/fins/test_fins_read_runtime.py tests/fins/test_sec_pipeline_download.py | shasum -a 256
  sed -n '589,703p' docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md | zsh -n
  ```
- 停止状态：未 stage、commit、push、PR；未修改任何 plan、product、tests、control、controller/reviewer artifacts、README 或 design。
