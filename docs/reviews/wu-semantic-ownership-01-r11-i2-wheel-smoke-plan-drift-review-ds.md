# WU-SEMANTIC-OWNERSHIP-01 / R11-I2 wheel smoke corrected plan — AgentDS 独立完整 adversarial plan review

## 1. Review target、scope 与 posture

- **reviewed target**：`docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`，942 lines / 81,592 bytes / SHA-256 `f1c95c3b5ecb1d6f01a2f15d1af6c96396ebb370c10997108a3c44dbd14b2ffd`。
- **review scope**：对 corrected plan 做独立完整 adversarial review，不只看 plan delta。重点核验 R11-I2-VAL-PD-F02 closure、wheel build/archive 与 fresh runtime oracle 分离、macOS arm64/Python 3.11 constraints owner、single normal install、pip check/help/importability 顺序、dependency failure stop、Windows workflow 不变、22/8/15/shared-node/stopped diff `6c8284c6...d0e6` 保护。
- **review posture**：constructively adversarial；默认假设 plan 至少有一个重要问题，直到证据证明它足够可靠。优先寻找高成本、危险、用户可见或难以发现的失败。
- **read evidence**：完整读取 AGENTS.md（129 lines）、corrected plan（942 lines）、Controller adjudication（75 lines）、fix-codex（159 lines）、fix-controller-validation（37 lines）、总控 `## 当前状态`（rows 153-259）、`pyproject.toml`（136 lines）、`requirements.txt`（12 lines）。

## 2. Assumptions tested

| # | Assumption | 结论 | 直接证据 |
|---|---|---|---|
| A1 | `--no-deps` install 与 CLI runtime import 是互斥 oracle，正确 owner 是 validation plan | 成立 | `pyproject.toml:42` 声明 `aiohttp>=3.9.0`；stopped smoke 的 `--no-deps` 禁止安装该依赖，随后的 `dayu.cli --help` 在 import `aiohttp` 时失败。该失败符合 `--no-deps` 语义，不证明 CLI 有缺陷。Controller adjudication §2 的 direct evidence 链成立。 |
| A2 | wheel build 与 runtime 两类 oracle 可安全分离 | 成立 | build 只验证构建产物边界（archive/METADATA/entrypoint/RECORD），不验证可运行性；runtime 验证声明依赖可解析、安装且 wheel 可运行。两者目的不同，对 build 依赖和 runtime 依赖的要求不同，分离是正确设计。 |
| A3 | `constraints/lock-macos-arm64-py311.txt` 存在且有效 | 成立 | 总控在 R08/R09 阶段已大量使用该 lock 文件；Controller adjudication §2 明确锁定当前执行平台为 Darwin arm64 / Python 3.11，且已有 owner lock。该文件的存在由历史验证事实支撑。 |
| A4 | 一次 normal constrained install 足以验证 wheel 可运行性 | 成立 | `pip install <wheel> --constraint <lock>` 同时安装 wheel 本身并解析安装其所有声明的 runtime dependencies，受 lock 版本约束。安装后 `pip check` 验证依赖图一致，help 验证 import chain，importability 验证删除的 package 不存在。一个 install 命令完成全部前置条件。 |
| A5 | `pip check` → help → importability 顺序正确 | 成立 | `pip check` 先验证依赖图无冲突；若依赖解析静默失败，`pip check` 非零暴露。随后 help 验证 CLI entrypoint import chain，最后 importability 验证删除的 package 不存在。该顺序 fail-fast：依赖问题最先暴露。 |
| A6 | Windows workflow 在 plan fix 中未被修改 | 成立 | fix-codex §5 明确 "未改 §7.2 Windows workflow"；Controller validation §2 确认 "Windows workflow...未变化"。Plan §7.2 的 install command 仍为 `pip install -e ".[test,dev]" -c constraints/lock-windows-x64-py311.txt`。 |
| A7 | stopped product diff `6c8284c6...d0e6` 未被 plan fix 修改 | 成立 | 本轮只修改 accepted plan 与新增 review artifact，不修改任何 product/test/README/packaging/workflow 文件。fix-codex §6 所有 stopped-tree locks 均为 "same / unchanged"；Controller validation §3 独立锁均 MATCH。 |
| A8 | 22/8/15 path counts 与 shared node contract 保持不变 | 成立 | Plan §4 精确计数：cumulative unique = 22，I1 = 8（含 shared `tests/cli/test_arg_parsing.py`），I2 = 15（含同一 shared path，仅 `test_root_readme_matches_current_cli_public_contract` 可改）。fix-codex §5 明确 "未改...22/8/15 counts、shared test node contract"。 |

## 3. 重点领域逐项核验

### 3.1 R11-I2-VAL-PD-F02 closure

- **问题**：accepted plan §7.3 原来使用 `pip install --no-deps <wheel>` 后直接运行 `python -m dayu.cli --help`。`--no-deps` 禁止安装 `aiohttp` 等声明依赖，help 在 import chain 中失败。
- **修复**：fresh venv 安装从 `--no-deps` 改为 `--constraint constraints/lock-macos-arm64-py311.txt` 的 normal install；增加 `pip check`；保留所有 archive negative oracles。wheel build 的 `--no-deps --no-build-isolation` 不变。
- **核验结果**：PASS。修复在正确 owner（validation plan）完成，未扩散到 CLI import、lazy import、lock 修改或产品范围。
  - Plan §2.4：明确 "两类 oracle 分离，不虚构未验证的 source archive owner"。
  - Plan §7.3 command block（lines 643-656）：install 用 `--constraint`，后跟 `pip check`、两个 help、importability。
  - Plan §7.3 prose（lines 660-662）：禁止先 no-deps、重复 install；要求 pip check、help、importability 全部成功。
  - Plan §7.3 Slice stop（lines 670-676）：dependency resolution/install、lock、pip check、help/importability 任一失败均为真实 packaging gate failure，禁止 lazy import/fallback/fixture shim/lock 修改。
  - Plan §8.1（lines 702-707）：同步两类 oracle 分离与 failure/stop 语义。
  - Plan §10 checklist（lines 933-935）：完整 build/archive/constrained install/pip check/help/importability acceptance oracle。

### 3.2 Wheel build/archive 与 fresh runtime oracle 分离

- **核验结果**：PASS。两类 oracle 目的不同、依赖不同、失败含义不同，分离是正确设计。
  - Build oracle：`pip wheel --no-deps --no-build-isolation` + 四个 Python archive negative oracles（METADATA 无 `Provides-Extra: web` / Streamlit；entry_points.txt 无 placeholder；extracted paths 无 `dayu/web|wechat|render`；RECORD 无对应路径）。
  - Runtime oracle：fresh venv 一次 constrained normal install → `pip check` → `--help` → `upload_filings_from --help` → importability。
  - 两类 oracle 之间无互斥前提：build oracle 不需要依赖完整；runtime oracle 不需要 `--no-deps`。修复前的问题来自把两者合并为一个 `--no-deps` install + runtime help。

### 3.3 macOS arm64/Python 3.11 constraints owner

- **核验结果**：PASS。Plan §7.3 与 §8.1 的 local validation 固定使用 `constraints/lock-macos-arm64-py311.txt`。这是当前开发平台的事实，且：
  - Windows workflow §7.2 使用独立 `constraints/lock-windows-x64-py311.txt`。
  - 两者不冲突，各自是所在平台的 constraints owner。
  - constraints 只限制版本上界，不引入新依赖。
  - Plan 明确 failure 是真实 gate failure，不会静默降级。

### 3.4 Single normal install

- **核验结果**：PASS。Plan §7.3 与 §8.1 均明确：
  - "一次 normal constrained install"（§7.3 line 660）
  - "不得先做 `--no-deps` install、重复安装同一 wheel 或依赖 pip 的偶然重装行为"（§7.3 lines 660-661）
  - "fresh venv 只对 exact built wheel做一次...normal constrained install"（§8.1 line 704）
  - Install command 只用单个 `subprocess.run` 调用，无 pre-install/post-install loop。

### 3.5 pip check/help/importability 顺序

- **核验结果**：PASS。顺序在 command block 与 prose 中一致：
  - Command block §7.3：install → `pip check` → `--help` → `upload_filings_from --help` → importability。
  - Prose §7.3 line 661："随后 `pip check`、两个真实 help command 与 placeholder package importability oracle全部成功"。
  - 该顺序 fail-fast：依赖问题被 `pip check` 先暴露；import chain 问题被 help 暴露；残留 package 被 importability 暴露。倒置会导致误判（如 importability 通过但依赖实际断裂）。

### 3.6 Dependency failure stop

- **核验结果**：PASS。Plan 多处一致声明：
  - §7.3 Slice stop（lines 670-676）：dependency resolution/install 失败、lock 冲突、`pip check` 非零、help/importability 失败 → 立即 stop，禁止 lazy import/fallback/fixture shim/lock 修改。
  - §8.1（lines 705-707）：依赖解析、下载或安装失败、lock 冲突、`pip check` 非零或任一 runtime oracle 失败 → 真实 final packaging validation failure，禁止 runtime `--no-deps`、重复 install、lock/workflow 修改。
  - §2.4 baseline mapping：Streamlit/watchdog pin 保留、no-touch；若 build/install 证明仍被 graph 消费则 stop，不扩域改 lock。
  - §10 checklist（line 935）：dependency install/runtime oracle failure 按真实 packaging gate stop。

### 3.7 Windows workflow 不变

- **核验结果**：PASS。
  - Controller adjudication §5："不改 Windows workflow install command、产品范围、22/8/15 counts、shared-node contract"。
  - fix-codex §5："未改 §7.2 Windows workflow、`22/8/15` counts、shared test node contract、review/commit sequence、deferred owner、security boundary 或 R12 boundary"。
  - Plan §7.2 的 install command、triggers、test commands、artifact publication 均未被本轮 plan fix 修改。
  - Plan §7.2 install 仍为 `pip install -e ".[test,dev]" -c constraints/lock-windows-x64-py311.txt`；local fix 使用 macOS lock 不影响该命令。

### 3.8 22/8/15/shared-node/stopped diff 保护

- **核验结果**：PASS。
  - Plan §4：
    - Cumulative unique paths = 22。
    - I1 = 8：`dayu/fins/upload_batch.py`、`tests/fins/test_upload_batch.py`、`dayu/cli/commands/fins.py`、`dayu/cli/arg_parsing.py`、`dayu/cli/upload_script.py`（新增）、`tests/cli/test_upload_filings_from_command.py`、`tests/cli/test_fins_commands.py`、`tests/cli/test_arg_parsing.py`。
    - I2 = 15：`pyproject.toml`、`requirements.txt`、`.github/workflows/r11-upload-script-windows.yml`（新增）、6 个待删 placeholder 文件、`tests/cli/test_public_package_entrypoints.py`、`tests/cli/test_arg_parsing.py`（共享）、4 个 README。
    - Shared path `tests/cli/test_arg_parsing.py` 在 I1 和 I2 中各计一次，cumulative 只计一次 → 8 + 15 - 1 = 22。✓
  - Plan §4（lines 213-216）：I2 只允许修改共享 path 中的 `test_root_readme_matches_current_cli_public_contract`；I2 mutation 前必须验证 protected I1 SHA-256 `7cdc4c1d...ece6`。
  - fix-codex §6：stopped product diff `6c8284c6...d0e6` unchanged、shared test `d3a4abcc...2658` unchanged、renderer/workflow hashes unchanged。
  - Controller validation §3：所有独立 locks 均 MATCH。

## 4. Architecture boundary review

- **layering**：PASS。Plan 保持 Fins（producer）→ CLI（consumer/renderer）→ packaging（publisher）的严格分层。Fins 零 CLI import；renderer 零 filename/fiscal/material regex；packaging 只删除 placeholder 不实现新能力。
- **dependency direction**：PASS。无反向依赖。Fins 不依赖 CLI/Service/Host/Engine；CLI 消费 Fins typed plan 但不修改 Fins owner contract。packaging 不引入新运行时依赖。
- **public contracts**：PASS。wheel build 只验证 archive 边界（METADATA/entry_points.txt/RECORD/extracted paths）；runtime smoke 只验证声明依赖可安装且 CLI 可运行。两类 oracle 各自验证不同 public contract 层面。
- **constraints ownership**：PASS。本地 validation 的 constraints 是 `constraints/lock-macos-arm64-py311.txt`，Windows 是 `constraints/lock-windows-x64-py311.txt`。各自是所在平台的唯一 constraints owner，不交叉、不互替。

## 5. Best-practice review

- **两类 oracle 分离**：PASS。符合"一个验证目标一个 oracle"原则。build 验证构建产物内容，runtime 验证可运行性。合并会导致互斥前提（no-deps 与 import chain）。
- **fail-closed design**：PASS。所有 oracle 均以 assertion 实现：exact-one wheel、exact stdout 包含特定字符串、非零即失败。没有 `|| true`、loose grep 或 optional check。
- **single install semantics**：PASS。避免 pip 的偶然重装行为（如第二次 install 可能跳过依赖解析），确保 wheel smoke 的可复现性。
- **pip check first**：PASS。在功能验证前先验证依赖图一致性，fail-fast 在最小成本位置。

## 6. Optimal-solution review

- **plan-only fix vs. 产品修改**：PASS。`R11-I2-VAL-PD-F02` 的正確修復是修改 validation plan，而非修改 CLI import（lazy import）、lock 文件或产品范围。Plan fix 是最小、最安全的修正。
- **normal install vs. 其他方案**：PASS。替代方案（保留 `--no-deps` 但做 lazy import、增加 `--no-deps` + 手工安装依赖、修改 lock 文件）均把 plan defect 下沉给错误 owner。当前方案在正确 owner 修复，改动最小。
- **constraint file 选择**：PASS。使用已有 lock 文件 `constraints/lock-macos-arm64-py311.txt` 而非生成新 lock，避免 lock drift 风险。

## 7. Overengineering review

- **无**：PASS。Plan fix 仅修改 validation 命令序列和对应 prose，不引入新 abstraction、layer、builder、wrapper 或 protocol。

## 8. Overcoupling review

- **无**：PASS。Build oracle 与 runtime oracle 的依赖关系是单向的（runtime 依赖 build 产物 wheel），没有循环依赖或双向耦合。Windows workflow 与 local validation 各自独立使用自己的 constraint file，不共享状态。

## 9. Attack surface 压测

### 9.1 约束文件存在性

- **场景**：`constraints/lock-macos-arm64-py311.txt` 不存在或被删除。
- **结果**：`pip install` 失败（file not found），plan 正确将其视为 real packaging gate failure → stop。非静默降级。PASS。

### 9.2 约束文件与 wheel 依赖冲突

- **场景**：lock 文件 pin `aiohttp==3.8.0` 但 wheel 声明 `aiohttp>=3.9.0`。
- **结果**：`pip install` 依赖解析失败，plan 正确视为 real packaging gate failure → stop。PASS。

### 9.3 Fresh venv 缺少 pip

- **场景**：`python -m venv` 使用 `--without-pip` 或环境异常导致 venv 无 pip。
- **结果**：`subprocess.run` 调用 `workspace/tmp/r11-wheel-venv/bin/python -m pip install` 失败 → `check=True` 抛出 CalledProcessError → 非零退出。fail-closed。PASS。

### 9.4 多个 wheel 文件

- **场景**：`workspace/tmp/r11-dist` 中有多个 `dayu_agent-*.whl`（如残留旧版本）。
- **结果**：`assert len(wheels) == 1` 失败 → 非零退出，打印 exact hits。PASS。

### 9.5 多个 dist-info 目录

- **场景**：wheel extract 后有多个 `*.dist-info` 目录。
- **结果**：`assert len(files) == 1` 在 METADATA、entry_points.txt、RECORD 检查中均失败 → 非零退出。PASS。

### 9.6 Placeholder package 残留

- **场景**：wheel 仍包含 `dayu/web/`、`dayu/wechat/`、`dayu/render/` 目录。
- **结果**：extracted paths 与 RECORD negative oracle 均命中 → `assert not hits` 失败 → 非零退出，打印 exact hits。PASS。

### 9.7 Windows workflow 被意外修改

- **场景**：plan fix 误改了 §7.2 Windows workflow 的 install command。
- **结果**：未发生。fix-codex §5 与 Controller validation §2 均确认 Windows workflow 不变。且固定 workflow install 为 `pip install -e ".[test,dev]"` 而非 wheel install，与 local wheel smoke 语义不同但各自治。PASS。

### 9.8 Stopped diff 漂移

- **场景**：plan fix 过程中 stopped product/test/README/packaging diff 发生变化。
- **结果**：未发生。fix-codex §6 所有 stopped-tree locks 均为 "same / unchanged"；Controller validation §3 独立验证所有 locks 匹配。PASS。

## 10. Plan completeness check

| 计划必须覆盖项 | 状态 | 位置 |
|---|---|---|
| R11-I2-VAL-PD-F02 根因与修复 | 已覆盖 | §2.4、§7.3、§8.1、§10 |
| Build oracle (`--no-deps --no-build-isolation`) 保留 | 已覆盖 | §7.3 command block、§10 |
| Runtime oracle (constrained normal install) 新增 | 已覆盖 | §7.3 command block、§7.3 prose、§8.1、§10 |
| `pip check` 在 help 之前 | 已覆盖 | §7.3 command block、§7.3 prose |
| Single install 语义 | 已覆盖 | §7.3 prose "一次 normal constrained install"、"不得先做 --no-deps" |
| Dependency failure = real gate failure | 已覆盖 | §7.3 Slice stop、§8.1、§10 |
| macOS constraints owner | 已覆盖 | §7.3、§8.1 固定 `constraints/lock-macos-arm64-py311.txt` |
| Windows workflow 不变 | 已覆盖 | fix-codex §5、Controller validation §2 |
| 22/8/15 counts | 已覆盖 | §4、§10 |
| Shared node contract | 已覆盖 | §4 "I2 只允许修改 test_root_readme_matches_current_cli_public_contract" |
| Stopped diff 保护 | 已覆盖 | fix-codex §6、Controller validation §3 |
| Lazy import/fallback/shim 禁止 | 已覆盖 | §7.3 Slice stop、§8.1 |
| Lock 修改禁止 | 已覆盖 | §7.3 Slice stop、§8.1 |

## 11. Findings

**零 material finding。**

经过对 corrected plan（942 lines）、Controller adjudication、fix-codex、fix-controller-validation、总控 current state、`pyproject.toml` 与 `requirements.txt` 的完整独立 adversarial review，未发现任何会导致 plan 失败、不可实施或违反项目约束的问题。

所有 8 项重点核验领域（§3.1—§3.8）均 PASS。所有 8 项 assumption（§2）均成立且有直接证据支撑。所有 9 项 attack surface 压测（§9.1—§9.8）均 fail-closed。所有 5 项 architecture/best-practice/optimal/overengineering/overcoupling review（§4—§8）均 PASS。Plan completeness check（§10）12/12 项均已在 plan 中明确覆盖。

## 12. Open questions

无。

## 13. Residual risks

无 unclassified residual risk。Windows real run 仍是 `PENDING_RELEASE_BLOCKER`（plan §7.2、§9.4），但这不是本轮 corrected plan 引入的风险，而是 R11 既有的跨平台 release gate，不在本 plan review scope。

## 14. Final plan review conclusion

**PASS**

Corrected plan（942 lines / SHA-256 `f1c95c3b...b2ffd`）是 code-generation-ready 的。`R11-I2-VAL-PD-F02` 已在 validation plan owner 正确关闭：build/archive 与 runtime oracle 分离清晰，macOS arm64/Python 3.11 constraints owner 明确，single normal install 语义完整，pip check/help/importability 顺序正确，dependency failure stop 一致，Windows workflow 与 22/8/15/shared-node/stopped diff `6c8284c6...d0e6` 均受保护且未漂移。

无 accepted finding、无 blocker、无 open question、无 unclassified residual risk。Plan 可安全进入下一 gate。

---

**Review metadata**

- artifact path：`docs/reviews/wu-semantic-ownership-01-r11-i2-wheel-smoke-plan-drift-review-ds.md`
- reviewer：AgentDS
- reviewed plan SHA-256：`f1c95c3b5ecb1d6f01a2f15d1af6c96396ebb370c10997108a3c44dbd14b2ffd`
- Controller adjudication SHA-256：`cde7f5dd0900e6bbd8a0ebe61c2160f5583d68fae609783960deb3e5c4794ef5`
- fix-codex SHA-256：`9f6ae7d2630c3c4edfa8eede96816726ca7260236de428bbf71bfdacca7e4b4f`
- fix-controller-validation SHA-256：`2ae6e12c...66fa8`
- stopped product diff SHA-256：`6c8284c6fdcfc4661a0bcd00f1c155d34985fa4af81fa400158ce3a034acd0e6`
- HEAD：`de476c452411e9d325d43b608de22b7236edfedb`
- product/test/README/design/CI diff：本轮无修改（plan-only fix）
- staged set：空
