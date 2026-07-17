# WU-SEMANTIC-OWNERSHIP-01 / R11 final-plan source-lock re-review 2（MiMo route）

## 1. Gate、reviewed target 与 scope

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU、feature 或 issue。
- gate：dual complete final-plan re-review 2（MiMo route）。
- reviewed target：886 lines / 74,647 bytes / SHA-256
  `817c9d2fde2112c244e14659e713041748e59d048b77e07be2f0b8def5175a92`。
- 本 review 完整读取全部 886 行 plan，不是只审 delta。
- 本裁决不授权 implementation、stage、commit、push、PR 或 R12。
- 唯一 write：本 artifact。

## 2. §2.2 Source-lock independent verification

Controller adjudication 要求独立重测完整 §2.2 source-lock table。以下为 MiMo 独立验证结果：

### 2.1 Production source locks

| Source | Plan Lines | Actual Lines | Plan SHA-256 | Actual SHA-256 | Match |
|---|---:|---:|---|---|---|
| `AGENTS.md` | 128 | 128 | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` | ✅ |
| `dayu/fins/upload_batch.py` | 376 | 376 | `6767d30cfd788e584cef22e5109b1ae0b787ecaedc8581a4cfcf2c49d5ad6178` | `6767d30cfd788e584cef22e5109b1ae0b787ecaedc8581a4cfcf2c49d5ad6178` | ✅ |
| `dayu/cli/commands/fins.py` | 1057 | 1057 | `0db8ff2dedf541c2b58bc11342a02cd0bf4098bc9fcc19d948efa5cf4afc95a6` | `0db8ff2dedf541c2b58bc11342a02cd0bf4098bc9fcc19d948efa5cf4afc95a6` | ✅ |
| `dayu/cli/arg_parsing.py` | 932 | 932 | `a0e25ad6c58f3f266ef1afc4447c4a7e875d18c23ad346550ccf8cfd283c1c2c` | `a0e25ad6c58f3f266ef1afc4447c4a7e875d18c23ad346550ccf8cfd283c1c2c` | ✅ |
| `dayu/fins/resolver/fmp_company_info.py` | 394 | 394 | `c2abfbe03227d8b98ea639c374cb7aa9c41c98214b0b004cfb7de492be7c46fa` | `c2abfbe03227d8b98ea639c374cb7aa9c41c98214b0b004cfb7de492be7c46fa` | ✅ |
| `pyproject.toml` | 152 | 152 | `e076606fd68ab911291be92cdba1bda9df05835baf8db7f81b1d33d517ce6a25` | `e076606fd68ab911291be92cdba1bda9df05835baf8db7f81b1d33d517ce6a25` | ✅ |
| `requirements.txt` | 12 | 12 | `d15176134f7e1cf651b77174550dba526a5e82ff7c7f60cf15356c1532215d3a` | `d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a` | ✅ |

### 2.2 README source locks（grouped row）

| README | Plan Lines | Actual Lines | Plan SHA-256 | Actual SHA-256 | Match |
|---|---:|---:|---|---|---|
| root `README.md` | 348 | 348 | `2f5cebfd...a6e6a`（abbr） | `2f5cebfd3bf82b7099ff11f94e7a1e0df3840ca13fc41324a9d4ae99a02a6e6a` | ✅ |
| `dayu/README.md` | 265 | 265 | `16bbdc87da05f68ad7787086cf5e4646e011a8e8304991cb360916487fa85367` | `16bbdc87da05f68ad7787086cf5e4646e011a8e8304991cb360916487fa85367` | ✅ |
| `dayu/fins/README.md` | 793 | 793 | `a4805995...9767`（abbr） | `a4805995879a5284f2205ef12e1113c1cec89dae55aefa96995b8d2749519767` | ✅ |
| `tests/README.md` | 293 | 293 | `15bb09f8...1fba9`（abbr） | `15bb09f8c38c9b659c64d8f6d3cc120abf0d2c7c3ce20b91e9629733fa91fba9` | ✅ |

`dayu/README.md` 三路一致性验证：

| Source | Lines | SHA-256 |
|---|---:|---|
| working tree | 265 | `16bbdc87da05f68ad7787086cf5e4646e011a8e8304991cb360916487fa85367` |
| accepted-plan `f7b452f9` | 265 | `16bbdc87da05f68ad7787086cf5e4646e011a8e8304991cb360916487fa85367` |
| R10 baseline `2b14b2fb` | 265 | `16bbdc87da05f68ad7787086cf5e4646e011a8e8304991cb360916487fa85367` |

三路完全一致。`R11-PR-BF-FR-CV-F01` 修复正确。

`requirements.txt` 三路一致性验证：

| Source | Lines | SHA-256 |
|---|---:|---|
| working tree | 12 | `d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a` |
| accepted-plan `f7b452f9` | 12 | `d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a` |
| R10 baseline `2b14b2fb` | 12 | `d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a` |

三路完全一致。`R11-PR-BF-FR-DS-F01` 修复正确。

### 2.3 Design source locks

| Source | Plan Lines | Actual Lines | Plan SHA prefix | Actual SHA prefix | Match |
|---|---:|---:|---|---|---|
| `docs/host/design.md` | 3696 | 3696 | `276d35e1` | `276d35e1` | ✅ |
| `docs/engine/design.md` | 553 | 553 | `f2091260` | `f2091260` | ✅ |
| `docs/tool/design.md` | 134 | 134 | `ddc6efc0` | `ddc6efc0` | ✅ |
| `docs/fins/design.md` | 123 | 123 | `97033cf1` | `97033cf1` | ✅ |
| `docs/ui/design.md` | 111 | 111 | `5a19c829` | `5a19c829` | ✅ |

### 2.4 Control / umbrella / discussion source locks

| Source | Plan Lines | Actual Lines | Plan SHA prefix | Actual SHA prefix | Match | Notes |
|---|---:|---:|---|---|---|---|
| Controller control | 2242 | 2256 | `1906ce2f` | `9ba19002` | ⚠️ drift | Controller-owned；随 gate transition 合法变化，§2.2 明确允许 |
| umbrella optimization control | 302 | 302 | `6d924e91` | `6d924e91` | ✅ | |
| Controller discussion | 731 | 731 | `cd26760d` | `cd26760d` | ✅ | |
| umbrella remediation plan | 1269 | 1269 | `30c27562` | `30c27562` | ✅ | |

Controller control drift 是 gate transition 的预期行为，不是 finding。

### 2.5 OLD source locks

| Source | Plan Lines | Actual Lines | Plan SHA prefix | Actual SHA prefix | Match |
|---|---:|---:|---|---|---|
| `dayu/fins/cli_support.py` | 2267 | 2267 | `248cc859` | `248cc859` | ✅ |
| `dayu/fins/upload_recognition.py` | 555 | 555 | `5a45618b` | `5a45618b` | ✅ |

### 2.6 Ruff version 与 baseline

```text
$ source .venv/bin/activate && python -m ruff --version
ruff 0.15.11

$ source .venv/bin/activate && python -m ruff check dayu tests utils --output-format json | shasum -a 256
051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea  -

$ source .venv/bin/activate && python -m ruff check dayu tests utils --output-format json | python -c "import json,sys; print(len(json.load(sys.stdin)))"
144
```

- Ruff 0.15.11，与 plan §8.1 oracle 一致 ✅
- 144 findings，SHA-256 与 plan 锁定 baseline 一致 ✅
- 不把 global 0.15.9 重报为 drift ✅

### 2.7 Accepted-plan commit parent

```text
$ git rev-parse f7b452f9^
2b14b2fbc89654267e3d33daa2ae410ceff45e68
```

parent 精确等于 R10 completion baseline ✅。

## 3. Five findings independent closure proof

### `R11-IMP-BF01` — CLOSED

**原始问题**：原 Fins producer 与原 CLI consumer/renderer 必须合并为一个 atomic implementation slice；不得有 producer-only gate truth。

**独立证明**：
- §4 明确 `R11-I1 atomic cutover` 合并原 producer/consumer slices（line 200-203）。
- §9.1 "严格顺序精确两个 implementation slices"（line 773），`R11-I1` 的 WP-A/WP-B 不构成独立 slices 或 state-machine nodes（line 774-775）。
- §5.3 "以下 focused owner tests ... 只能在 §5 WP-A 与 §6 WP-B 的全部 coordinated edits 已完成、tree 不再依赖旧 generic contract 后运行；它们不是 WP-A checkpoint"（line 302-303）。
- §6.6 "以下 tests/smokes 只能在 WP-A+WP-B 已共同 cutover 后运行"（line 483）。
- 无 producer-only checkpoint 语言；首次 validation 必须在全部 coordinated edits 完成后。

Status：**CLOSED** ✅

### `R11-PR-BF-RR-F01` — CLOSED

**原始问题**：sequential edit 与 transient gate truth/safety stop 边界需要完整定义。

**独立证明**：
- §5.1 "顺序编辑期间可以短暂出现'新 producer + 旧 consumer'等 transient inconsistency，但它不是合法 intermediate tree，也不是 pass/failure baseline"（line 226-228）。
- §5.1 "在 WP-A/WP-B 全部 coordinated edits 完成前，不得运行或宣称 tests、pyright、coverage、Ruff、diff/diffcheck/scans validation"（line 228-229）。
- §5.1 "若编辑期间出现真实 allowlist/source/design/security blocker，必须立即 stop 并按 §5.3/§9.1 报告 failed working evidence；不得继续冒险，也不得把这一 safety stop 解释为 checkpoint/pass 许可"（line 230-231）。
- §9.1 state machine 图中明确 "若出现真实 blocker：stop + 报告当前 diff 为 failed working evidence；不宣称 pass/checkpoint、不 rollback/扩 scope"（line 782）。
- §8.1 重复强调相同边界（line 648-655）。
- safety stop 在 plan 中出现 8 次以上，覆盖 §5.1、§5.3、§8.1、§9.1。

Status：**CLOSED** ✅

### `R11-PR-BF-FR-DS-F01` — CLOSED

**原始问题**：`requirements.txt` source lock 使用描述性 label 而非精确值，可能制造虚假 drift signal。

**独立证明**：
- Plan §2.2 line 71 现为：`| CURRENT requirements.txt | 12 | d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a |`
- 三路验证（working tree / f7b452f9 / 2b14b2fb）均为 12 lines / 同一 full SHA。
- 旧描述性 label 零残留。

Status：**CLOSED** ✅

### `R11-PR-BF-FR-DS-F02` — CLOSED

**原始问题**：FMP resolver source lock 使用描述性 label `CURRENT FMP resolver` 而非精确文件路径。

**独立证明**：
- Plan §2.2 line 68 现为：`| CURRENT dayu/fins/resolver/fmp_company_info.py | 394 | c2abfbe03227d8b98ea639c374cb7aa9c41c98214b0b004cfb7de492be7c46fa |`
- 实际文件验证：394 lines / SHA-256 `c2abfbe03227d8b98ea639c374cb7aa9c41c98214b0b004cfb7de492be7c46fa`，完全匹配。
- 描述性旧 label `CURRENT FMP resolver` 零残留。
- lines/hash 未被修改，只改了 label cell。

Status：**CLOSED** ✅

### `R11-PR-BF-FR-CV-F01` — CLOSED

**原始问题**：grouped README row 中 `dayu/README.md` 的 lines/hash 使用了错误值（111 lines / `1534bcfd...d9a74`），实际为 265 lines。

**独立证明**：
- Plan §2.2 line 70 现为：`| root / dayu/ / Fins / tests README | 348 / 265 / 793 / 293 | 2f5cebfd...a6e6a / 16bbdc87da05f68ad7787086cf5e4646e011a8e8304991cb360916487fa85367 / a4805995...9767 / 15bb09f8...1fba9 |`
- 三路验证（working tree / f7b452f9 / 2b14b2fb）均为 265 lines / 同一 full SHA。
- root/Fins/tests README 的 lines 与 hash cells 未被修改。
- 错误值 111 / `1534bcfd...d9a74` 零残留。

Status：**CLOSED** ✅

## 4. Plan architecture review

### 4.1 Two-slice state machine

Plan 定义严格顺序两个 implementation slices：
1. `R11-I1 atomic Fins+CLI cutover`：合并 WP-A（Fins owner contract）与 WP-B（CLI consumer/renderer cutover）。
2. `R11-I2 packaging/README/Windows gate`：placeholder deletion、wheel metadata、README 更新、Windows workflow。

WP-A/WP-B 不是独立 slices（§9.1 line 774-775）。两个 slices 之间不做 slice acceptance、code-review gate 或 commit（§9.1 line 813）。code review 只在两个 implementation slices 全部完成后执行一次（§9.2 line 828）。

**判定**：state machine 边界清晰，无过度耦合，无 producer-only gate truth 泄漏。

### 4.2 Correction loop 与 combined revalidation

§5.3/§9.1 定义了 correction loop：
- WP-B 首次消费暴露 Fins typed gap 时，状态保持在 `R11-I1 coordinated implementation`。
- 只在 Fins owner 路径 `dayu/fins/upload_batch.py` 与 `tests/fins/test_upload_batch.py` 做 targeted correction。
- 修复后必须重跑 §5.3、§6.6、§8 对 producer+consumer 的全部 cumulative contract/tests/scans/smoke/coverage/full pyright/Ruff。
- 不得只重跑 owner tests；不得在 builder/renderer/adapter/test fixture 补偿；不得创建新 sub-WU/slice/commit。

**判定**：correction loop 收敛条件明确，combined revalidation 覆盖完整，无下游补偿路径。

### 4.3 Semantic owner boundary

§4 semantic owner map 定义 12 个语义事实的唯一 owner 与允许消费者：
- Fins 唯一产生分类/财期/material/skip facts。
- CLI 只消费 typed plan 并拥有 argv/renderer/publisher/summary。
- 不得在 renderer、README、fixture 或 Service 下游补 OLD 规则。

§5.3 atomic checkpoint checklist 冻结 producer-consumer field/enum/optional mapping（328-342），consumer 不得自行推断。

**判定**：owner 边界清晰，无重叠，无 fallback 路径。

### 4.4 Security gates

Plan 保留/加强了以下安全边界：
- source/output lexical+resolved containment（§5.2 rule 1、§6.3）
- symlink rejection（§5.2 rule 1/3、§6.3）
- same-directory atomic replace（§6.3）
- POSIX chmod 0o755（§6.3）
- Windows delayed expansion off（§6.5）
- argv injection marker（§6.5/§6.6）
- secret non-persistence（§6.3/§6.6/§8.3）

**判定**：安全边界完整，未弱化。

### 4.5 Deferred / no-touch boundary

§3.3 明确列出 deferred items：
- Issue 142/151/175/177/178 不实现。
- R12 不进入。
- 真实 Web/WeChat/render 不实现。
- Topic 8/9 不实现。
- 不改 `dayu/service/**`、`dayu/host/**`、`dayu/engine/**`、`dayu/runtime/**`。

§8.3 deferred diff scan 验证零 production diff。

**判定**：deferred 边界清晰，未被侵入。

### 4.6 Windows release gate

§7.2 定义最小 Windows workflow：
- `windows-latest`、Python 3.11、`cmd.exe /d /c`。
- `workflow_dispatch` + `pull_request.paths` 精确匹配 closed allowlist。
- recorder smoke + CLI grammar smoke + temp-storage smoke。
- artifact 14-day retention、`if-no-files-found: error`。
- `PENDING_RELEASE_BLOCKER` 直到真实 GitHub run 通过。

**判定**：Windows gate 未被弱化，release blocker 定位正确。

## 5. Rejected reviewer observations

### Ruff version drift — NOT A FINDING

前次 re-review 中，reviewer 在未激活 `.venv` 时运行 `ruff --version` 得到全局 `ruff 0.15.9`，误报为 drift。Plan §8.1 与 AGENTS 均要求 `source .venv/bin/activate`。MiMo 独立验证 activated `.venv` 下为 `ruff 0.15.11`，与 plan oracle 一致。

这不是 finding，也不是 residual。

### Controller control live drift — EXPECTED STATE

Controller control 文件 hash 从 `1906ce2f` 变为 `9ba19002`，lines 从 2242 增至 2256。§2.2 明确允许："Controller-owned control 文件可因 gate transition 合法变化"。

这不是 finding，也不是 residual。

## 6. Adversarial review — new findings scan

### 6.1 Scope / non-goal / ownership

- Goal（§3.1）清晰：OLD-aligned upload_filings_from + placeholder deletion。
- Non-goals（§3.3）精确列出 deferred items。
- Semantic owner map（§4）12 行，无重叠。
- Closed allowlist（§4）精确到文件路径，两个 slices 分配明确。

无 finding。

### 6.2 Architecture boundary

- `R11-I1` 不修改 Service/host/engine/runtime/storage schema/FMP resolver/ticker normalizer（§5.3 stop condition）。
- `R11-I2` 不回改或扩张 `R11-I1` 产品范围（§7.1）。
- Fins production 零 CLI import（§8.3 反向依赖检查）。
- 不引入第二 renderer、JSON fallback、兼容 seam。

无 finding。

### 6.3 Overcoupling

- WP-A/WP-B 在同一 atomic slice 内顺序编辑，不要求跨文件事务原子写（§5.1 line 224）。
- 两个 slices 之间无中间 commit 或 handoff。
- correction loop 只修改两个 Fins owner 路径，不扩散到 CLI。

无 finding。

### 6.4 Overengineering

- Frozen typed models（§5.1）：`UploadBatchPlanRequest`、`UploadBatchFilingEntry`、`UploadBatchMaterialEntry`、`UploadBatchSkippedEntry`、`UploadBatchPlan`。每个有明确字段集，无泛化 bag。
- 单一 argv builder（§6.2 rule 7）：无多态、无 factory。
- 平台 renderer（§6.4/§6.5）：POSIX 用 `shlex.quote`/`shlex.join`；Windows 用 evidence-driven algorithm。无 abstraction layer。

无 finding。

### 6.5 Test gaps

- §5.3 owner tests 覆盖 27+ 场景。
- §6.6 cumulative tests 覆盖 30+ 场景。
- POSIX recorder smoke + real upload smoke。
- Windows recorder smoke + CLI grammar smoke。
- §8.2 per-file line coverage >=80%。
- §8.3 14+ scan commands。

无 finding。

### 6.6 Hidden assumptions

- Plan 假设 `FINS_UPLOAD_FILE_SUFFIXES` 已存在于 current Fins（§5.2 rule 3："候选用当前 `FINS_UPLOAD_FILE_SUFFIXES`，不是复制 OLD 后缀表"）。实际 `dayu/fins/upload_batch.py` 376 lines，需在 implementation 中验证该常量存在。
- Plan 假设 `normalize_ticker` 已存在于 current codebase（§6.2 rule 3）。CLI `arg_parsing.py` 932 lines，需在 implementation 中验证。
- Plan 假设 `FmpCompanyInfoResolver.resolve_company_info(canonical)` 是现有 public method（§6.2 rule 4）。
- Plan 假设 `python -m pip wheel --no-deps --no-build-isolation` 在 `.venv` 中可用（§7.3）。

这些是 implementation preflight 验证点，不是 plan finding。Plan 已要求 "所有 material preflight 必须在 mutation 前完成"（§5.1 line 222-223）。

### 6.7 Sequencing risks

- §5.1 明确 "顺序编辑期间可以短暂出现'新 producer + 旧 consumer'等 transient inconsistency"（line 226-227）。
- §5.1 明确 "不得运行或宣称 tests、pyright、coverage、Ruff、diff/diffcheck/scans validation"（line 228-229）。
- §9.1 state machine 图中 "全部 coordinated edits 完成前的 transient inconsistency 不是 gate truth"（line 781）。

Sequencing 约束完整，无 finding。

### 6.8 Rollback safety

- §5.1 "不得自行 rollback"（line 357）。safety stop 时保留当前 diff 为 failed working evidence。
- §6.3 publisher 失败或 `KeyboardInterrupt` 清理 temp，旧 target 保持 byte-for-byte（line 439-440）。

Rollback 边界清晰，无 finding。

## 7. Residual risks

| Risk | Description | Tracking |
|---|---|---|
| Windows release gate | R11 本地可标 `PENDING_RELEASE_BLOCKER`，但 umbrella aggregate/PR closeout 必须等待真实 GitHub run | §9.4 / umbrella §7.3/§22 |
| Windows quoting algorithm | 具体 quote/escape 算法不在 plan 中臆定，保留给真实 runner 反证 | §6.5 |
| FINS_UPLOAD_FILE_SUFFIXES existence | 需在 implementation preflight 验证 | §5.2 rule 3 |
| normalize_ticker existence | 需在 implementation preflight 验证 | §6.2 rule 3 |
| FmpCompanyInfoResolver.resolve_company_info method | 需在 implementation preflight 验证 | §6.2 rule 4 |

以上均为 implementation preflight 验证点或 release gate 延迟项，不是 plan structure finding。

## 8. Open questions

无。所有前次 findings 已 CLOSED；plan 的 design decisions 有明确 owner 和 evidence 支撑。

## 9. Final plan review conclusion

**PASS**

五个 findings 全部独立证明 CLOSED：

| Finding | Status |
|---|---|
| `R11-IMP-BF01` | CLOSED |
| `R11-PR-BF-RR-F01` | CLOSED |
| `R11-PR-BF-FR-DS-F01` | CLOSED |
| `R11-PR-BF-FR-DS-F02` | CLOSED |
| `R11-PR-BF-FR-CV-F01` | CLOSED |

- 全部 §2.2 source locks 独立验证通过。
- FMP resolver exact path/394/hash ✅。
- `dayu/README.md` working+f7b452f9+2b14b2fb 三路 265/full hash ✅。
- `requirements.txt` 三路 full hash ✅。
- Ruff 0.15.11 + baseline SHA 144 findings ✅。
- Two-slice state machine 边界精确。
- Sequential edit / safety stop 完整。
- Correction loop / combined revalidation 完整。
- pyright `0 errors` / coverage >=80% / Ruff / security / deferred / Windows gates 未弱化。
- 无新 current material finding。
- 未重开已裁决产品问题。

---

| Item | Count |
|---|---:|
| prior findings closed | 5 |
| accepted/open new findings | 0 |
| blocker | 0 |
| actual accepted residual | 0 |

Windows：`PENDING_RELEASE_BLOCKER`，未改变。
R12、deferred Issue 与统一 authorization framework 未进入。

READY_FOR_CONTROLLER_R11_FINAL_PLAN_REREVIEW2_ADJUDICATION
