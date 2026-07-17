# WU-SEMANTIC-OWNERSHIP-01 / R11 final-plan re-review 3（MiMo route）

## 1. Gate、reviewed target 与 scope

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU、feature 或 issue。
- gate：R11 dual complete final-plan re-review 3（MiMo route）。
- immutable reviewed target：`docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`
  - 892 lines / 75,434 bytes
  - SHA-256 `35a15ae9acd3276d8fea95473d295cb01c9b39c591f1bac077ccc1b93029f571`
- 本 review 完整读取全部 892 行 plan，不是只审 delta。
- 本裁决不授权 implementation、stage、commit、push、PR 或 R12。
- 唯一 write：本 artifact。

## 2. §2.2 Source-lock independent verification

Controller 要求独立重测完整 §2.2 source-lock table。以下为 MiMo 独立验证结果：

### 2.1 Production source locks

| Source | Plan Lines | Actual Lines | Plan SHA-256 | Actual SHA-256 | Match |
|---|---:|---:|---|---|---|
| `AGENTS.md` | 128 | 128 | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` | ✅ |
| `dayu/fins/upload_batch.py` | 376 | 376 | `6767d30cfd788e584cef22e5109b1ae0b787ecaedc8581a4cfcf2c49d5ad6178` | `6767d30cfd788e584cef22e5109b1ae0b787ecaedc8581a4cfcf2c49d5ad6178` | ✅ |
| `dayu/cli/commands/fins.py` | 1057 | 1057 | `0db8ff2dedf541c2b58bc11342a02cd0bf4098bc9fcc19d948efa5cf4afc95a6` | `0db8ff2dedf541c2b58bc11342a02cd0bf4098bc9fcc19d948efa5cf4afc95a6` | ✅ |
| `dayu/cli/arg_parsing.py` | 932 | 932 | `a0e25ad6c58f3f266ef1afc4447c4a7e875d18c23ad346550ccf8cfd283c1c2c` | `a0e25ad6c58f3f266ef1afc4447c4a7e875d18c23ad346550ccf8cfd283c1c2c` | ✅ |
| `dayu/fins/resolver/fmp_company_info.py` | 394 | 394 | `c2abfbe03227d8b98ea639c374cb7aa9c41c98214b0b004cfb7de492be7c46fa` | `c2abfbe03227d8b98ea639c374cb7aa9c41c98214b0b004cfb7de492be7c46fa` | ✅ |
| `pyproject.toml` | 152 | 152 | `e076606fd68ab911291be92cdba1bda9df05835baf8db7f81b1d33d517ce6a25` | `e076606fd68ab911291be92cdba1bda9df05835baf8db7f81b1d33d517ce6a25` | ✅ |
| `requirements.txt` | 12 | 12 | `d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a` | `d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a` | ✅ |

### 2.2 README source locks（grouped row）

| README | Plan Lines | Actual Lines | Plan SHA-256 | Actual SHA-256 | Match |
|---|---:|---:|---|---|---|
| root `README.md` | 348 | 348 | `2f5cebfd3bf82b7099ff11f94e7a1e0df3840ca13fc41324a9d4ae99a02a6e6a`（abbr） | `2f5cebfd3bf82b7099ff11f94e7a1e0df3840ca13fc41324a9d4ae99a02a6e6a` | ✅ |
| `dayu/README.md` | 265 | 265 | `16bbdc87da05f68ad7787086cf5e4646e011a8e8304991cb360916487fa85367` | `16bbdc87da05f68ad7787086cf5e4646e011a8e8304991cb360916487fa85367` | ✅ |
| `dayu/fins/README.md` | 793 | 793 | `a4805995879a5284f2205ef12e1113c1cec89dae55aefa96995b8d2749519767`（abbr） | `a4805995879a5284f2205ef12e1113c1cec89dae55aefa96995b8d2749519767` | ✅ |
| `tests/README.md` | 293 | 293 | `15bb09f8c38c9b659c64d8f6d3cc120abf0d2c7c3ce20b91e9629733fa91fba9`（abbr） | `15bb09f8c38c9b659c64d8f6d3cc120abf0d2c7c3ce20b91e9629733fa91fba9` | ✅ |

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
| Controller control | 2242 | >2242 | `1906ce2f` | drift | ⚠️ | Controller-owned；随 gate transition 合法变化 |
| umbrella optimization control | 302 | 302 | `6d924e91` | `6d924e91` | ✅ | |
| Controller discussion | 731 | 731 | `cd26760d` | `cd26760d` | ✅ | |
| `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md` | 1269 | 1269 | `30c27562` | `30c27562` | ✅ | exact path label ✅ |

Controller control drift 是 gate transition 的预期行为，不是 finding。

### 2.5 External OLD source locks

| Source | Plan Lines | Actual Lines | Plan SHA-256 | Actual SHA-256 | Match |
|---|---:|---:|---|---|---|
| `/Users/leo/workspace/dayu-agent/dayu/fins/cli_support.py` | 2267 | 2267 | `248cc859d4dd0fdf8ed7829cc27dad48349227dfbd43f076414770166c93da45` | `248cc859d4dd0fdf8ed7829cc27dad48349227dfbd43f076414770166c93da45` | ✅ |
| `/Users/leo/workspace/dayu-agent/dayu/fins/upload_recognition.py` | 555 | 555 | `5a45618b2545ad0ee024efb428de7e614c96b2c5bb0a222bf1586febc1dff816` | `5a45618b2545ad0ee024efb428de7e614c96b2c5bb0a222bf1586febc1dff816` | ✅ |

§2.1 authority item 7 现明确写出两个 absolute external paths；§2.2 两个 OLD rows 使用相同 absolute paths。`R11-PR-BF-RR2-DS-F01` 修复正确。

### 2.6 Ruff version 与 baseline

```text
$ source .venv/bin/activate && python -m ruff --version
ruff 0.15.11

$ source .venv/bin/activate && python -m ruff check dayu tests utils --output-format json | python -c "import json,sys; print(len(json.load(sys.stdin)))"
144
```

- Ruff 0.15.11，与 plan §8.1 oracle 一致 ✅
- 144 findings ✅
- 未使用 global `ruff 0.15.9` ✅

## 3. Five Q4 owner oracle 独立验证

使用当前 `.venv/bin/python -B` 直接只读加载 external OLD
`/Users/leo/workspace/dayu-agent/dayu/fins/upload_recognition.py`，五个 oracle 精确通过：

```text
2024Q4季报.pdf -> Q4
2024Q4季度报告.pdf -> FY
2024Q4年报.pdf -> FY
2021Q4/季报.pdf -> (2021, 'Q4')
2021Q4/季度报告.pdf -> (2021, 'FY')
```

Plan §5.2 rule 4 现明确：
- Q4 marker 只检查 child 完整 filename，不检查 ancestor/path ✅
- quarterly marker 只认 exact contiguous literal substring `季报`，`季度报告` 不是 alias ✅
- `FY`/annual/年度报告/年报在 Q1—Q4 前判定 ✅
- direct `20YYQ4` parent fallback 仍只检查 child filename 的 exact `季报` ✅

§5.3 owner-test matrix 包含全部五个 exact cases。`R11-PR-BF-RR2-DS-F03` 修复正确。

## 4. All eight findings final closure proof

### `R11-IMP-BF01` — CLOSED

Plan §4 合并原 producer+consumer 为 `R11-I1 atomic cutover` 单一 merged allowlist。§9.1 精确只有两个 implementation slices。WP-A/WP-B 不是独立 state-machine nodes（§9.1 line 774-775）。§5.1/§6.1/§9.1 多处明确禁止 WP-A/WP-B 之间的 checkpoint、acceptance、commit、handoff 或 next-slice transition。

Status：**CLOSED** ✅

### `R11-PR-BF-RR-F01` — CLOSED

§5.1 line 225-231 完整定义顺序编辑期间的 transient inconsistency 边界：不是合法 intermediate tree，不是 pass/failure baseline，不得运行 validation gate。§5.1 line 230-231 定义 safety stop 行为。§9.1 line 793-804 重复加固。§8.1 line 648-655 重复加固。safety stop 在 plan 中出现 8+ 次，覆盖 §5.1、§5.3、§8.1、§9.1。

Status：**CLOSED** ✅

### `R11-PR-BF-FR-DS-F01` — CLOSED

Plan §2.2 line 72 `requirements.txt` 现为 full SHA-256 `d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a`。三路验证（working tree / f7b452f9 / 2b14b2fb）均为 12 lines / 同一 full SHA。旧缩写值 `7e8c14d6...79c93` 零残留。

Status：**CLOSED** ✅

### `R11-PR-BF-FR-DS-F02` — CLOSED

Plan §2.2 line 68 FMP resolver 现为 exact path `dayu/fins/resolver/fmp_company_info.py`。394 lines / SHA-256 `c2abfbe03227d8b98ea639c374cb7aa9c41c98214b0b004cfb7de492be7c46fa`。描述性旧 label `CURRENT FMP resolver` 零残留。

Status：**CLOSED** ✅

### `R11-PR-BF-FR-CV-F01` — CLOSED

Plan §2.2 grouped README row 现为 `348 / 265 / 793 / 293`。`dayu/README.md` hash 现为 full SHA-256。三路验证（working tree / f7b452f9 / 2b14b2fb）均为 265 lines / 同一 full SHA。错误值 111 / `1534bcfd...d9a74` 零残留。

Status：**CLOSED** ✅

### `R11-PR-BF-RR2-DS-F01` — CLOSED

§2.1 authority item 7 现明确写出两个 absolute external paths。§2.2 两个 OLD rows 使用相同 absolute paths，2267/555 lines 与 full SHA 保持不变。未把 OLD 文件复制进当前 repo。MiMo 独立验证 OLD 文件可达且与 plan lock 精确匹配。

Status：**CLOSED** ✅

### `R11-PR-BF-RR2-DS-F02` — CLOSED

§2.1 authority item 4 与 §2.2 source-lock row 均改为 exact path `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`。1269 lines 与 SHA-256 `30c27562ece3360c7d25e55a6f2b0b189999d35cca8004e83d42de3c8ccda838` 保持不变。旧描述性 label `umbrella remediation plan` 零残留。

Status：**CLOSED** ✅

### `R11-PR-BF-RR2-DS-F03` — CLOSED

§5.2 rule 4 现明确四点 Q4 OLD semantics：
1. marker 只检查 child 完整 filename，不检查 ancestor/path
2. quarterly marker 只认 exact contiguous literal substring `季报`
3. `FY`/annual/年度报告/年报在 Q1—Q4 前判定
4. direct `20YYQ4` parent fallback 仍只检查 child filename 的 exact `季报`

§5.3 owner-test matrix 锁定五个 exact cases。五个 Q4 oracle 全部通过（见 §3）。

Status：**CLOSED** ✅

## 5. Two-slice state machine 验证

Plan §9.1 精确描述两个 dependency-ordered implementation slices：

1. `R11-I1 coordinated implementation`（WP-A + WP-B 顺序编辑）
2. 首次 producer+consumer cumulative validation
3. 可选 correction loop（Fins owner targeted correction → combined revalidation）
4. `Controller R11-I1 atomic checkpoint`
5. `R11-I2 packaging/README/Windows implementation`
6. `Controller R11-I2 checkpoint` → cumulative code-review gate

中间不存在 work-package checkpoint、slice acceptance 或中间 commit。

**判定**：state machine 边界清晰，无歧义，无 producer-only gate truth 泄漏。✅

## 6. Sequential edit / safety stop 验证

§5.1 line 225-231、§5.3 line 344-348、§8.1 line 648-655、§9.1 line 793-804 四处一致约束：
- 全部 coordinated edits 完成前，transient inconsistency 不是合法 tree
- 不运行 validation，不做 gate transition
- 真实 blocker 出现时 stop + 报告 failed working evidence
- 不宣称 pass/checkpoint，不自行 rollback，不扩大 scope

**判定**：边界完整，四处一致无矛盾。✅

## 7. Correction loop / combined revalidation 验证

§5.3 line 344-348 与 §9.1 line 806-810 定义同一 correction loop：
- WP-B consumer 暴露 owner gap → 只在 Fins owner 路径做 targeted correction
- CLI 继续机械消费同一 source of truth
- 修复后必须重跑 §5.3 + §6.6 + §8 全部 cumulative validation
- 严禁在 builder/renderer/adapter/test fixture 补偿
- 严禁创建新 sub-WU/slice/commit 或扩大 allowlist

**判定**：correction loop 收敛条件明确，combined revalidation 不缩水。✅

## 8. Semantic owner boundary 验证

§4 semantic owner map 定义 12 个语义事实的唯一 owner 与允许消费者。Fins 仍唯一产生分类/财期/material/skip facts。CLI 只消费 typed plan 并拥有 argv/renderer/publisher/summary。§5.3 atomic checkpoint checklist 冻结 producer-consumer field/enum/optional mapping。

**判定**：owner 边界清晰，无重叠，无 fallback 路径。✅

## 9. Cumulative gates 未弱化验证

| Gate | Plan 要求 | Status |
|---|---|---|
| cumulative closed allowlist | §4 lines 162-208 | ✅ 未变 |
| Fins typed owner | §4 lines 146-160 | ✅ 未变 |
| CLI projection owner | §6.2 lines 381-411 | ✅ 未变 |
| POSIX recorder smoke | §6.6 | ✅ 未变 |
| POSIX real Service/Fins smoke | §6.6 | ✅ 未变 |
| Windows recorder smoke | §7.2 | ✅ 未变 |
| Windows real CLI smoke | §7.2 | ✅ 未变 |
| wheel smoke (5 oracles) | §7.3 | ✅ 未变 |
| changed-file coverage >=80% | §8.2 | ✅ 未变 |
| full pyright 0 errors | §8.1 | ✅ 未变 |
| Ruff 0.15.11 baseline | §8.1 | ✅ 未变 |
| Windows PENDING_RELEASE_BLOCKER | §7.2/§9.2/§9.4 | ✅ 未变 |
| security containment/symlink/atomic/secret | §5.2/§6.3/§8.3 | ✅ 未变 |
| deferred Issues/no-touch | §3.3/§8.3 | ✅ 未变 |
| no-push/PR | §1/§9.3 | ✅ 未变 |

**判定**：所有 cumulative gates 保留完整，未被弱化。✅

## 10. 旧三-slice / 提前 review/commit / compatibility seam 零残留

- 旧三-slice `R11-S1 -> R11-S2 -> R11-S3` 全文中零命中（唯一 bare `S1` 在 line 12，是 Controller artifact 专名）
- §9.1 line 777-779："两个 slices 之间不做 slice acceptance、code-review gate 或 commit"
- §9.2："Agent 不得自行 stage/commit"
- §4 line 209 禁止 old/new dual surface、generic alias/property/wrapper、CLI loose parsing
- §5.1/§6.1/§9.1 反复禁止 compatibility alias/property/wrapper/dead dataclass/union adapter/`hasattr/getattr`

**判定**：零残留。✅

## 11. 安全 / containment / deferred 边界验证

- source/output lexical+resolved containment（§5.2 rule 1、§6.3）
- symlink rejection（§5.2 rule 1/3、§6.3）
- external ancestor symlink allowed（§5.2 rule 1）
- same-directory atomic replace（§6.3）
- POSIX chmod 0o755（§6.3）
- Windows delayed expansion off（§6.5/§8.3）
- argv injection marker（§6.5/§6.6）
- secret non-persistence（§6.3/§6.6/§8.3）
- Issue 142/151/175/177/178 deferred（§3.3）
- R12 deferred（§3.3）
- Topic 8/9 deferred（§3.3）
- Service/host/engine/runtime/storage/FMP/ticker/design/constraints no-touch（§3.3）

**判定**：安全与 deferred 边界完整，未弱化。✅

## 12. New adversarial scan — 全新 finding 搜索

### 12.1 Scope / sequencing / architecture

- Goal（§3.1）清晰，non-goals（§3.3）精确。
- 精确两个 dependency-ordered slices。
- WP-A/WP-B 是 ordered work packages，不是独立 slices。
- I1 atomic cutover 是 producer-consumer contract 切换的最小合法方案。
- I2 只消费 I1 已锁定的 contract，不回改。

无 finding。

### 12.2 Overcoupling / overdesign

- I1 merged allowlist 是 static type contract 原子切换的必要条件，不是功能耦合。
- Frozen typed models（§5.1）无泛化 bag，每个有明确字段集。
- 单一 argv builder（§6.2 rule 7）无多态、无 factory。
- 平台 renderer 无 abstraction layer。
- Windows quoting 保留给真实 runner 反证，不预猜。

无 finding。

### 12.3 Test gap

- §5.3 owner tests 覆盖 27+ 场景（含五个 exact Q4 cases）。
- §6.6 cumulative tests 覆盖 30+ 场景。
- POSIX/Windows recorder + real upload smokes。
- §7.3 wheel smoke 5 oracles。
- §8.2 per-file line coverage >=80%。
- §8.3 14+ scan commands。

无 finding。

### 12.4 Source-lock residual

全部 §2.2 source locks 已在 §2 中独立验证通过。三个 accepted rereview2 findings（DS-F01/02/03）均已修复并由 Controller 验证。无新 source-lock drift。

无 finding。

### 12.5 Hidden assumptions / preflight gaps

以下需在 implementation preflight 中验证（不是 plan finding）：
- `FINS_UPLOAD_FILE_SUFFIXES` 存在性
- `normalize_ticker` 存在性
- `FmpCompanyInfoResolver.resolve_company_info` 方法签名
- `python -m pip wheel --no-deps --no-build-isolation` 可用性

Plan §5.1 已要求 "所有 material preflight 必须在 mutation 前完成"。

### 12.6 Residual completeness

- 旧三-slice 零残留 ✅
- 提前 review/commit/acceptance 零残留 ✅
- compatibility seam 零残留 ✅
- JSON fallback/第二 renderer/兼容 shim 零残留 ✅
- `list2cmdline`/shell=True/setlocal EnableDelayedExpansion 零残留 ✅
- 已裁决产品问题未被重开 ✅
- R12 与 tracker 能力未进入 ✅
- staged tree 为空 ✅
- product/test/README/design/CI diff 为空 ✅

## 13. Residual risks

| Risk | Severity | Tracking |
|---|---|---|
| Windows quoting algorithm 需真实 runner 反证 | 中 | R11 release gate（PENDING_RELEASE_BLOCKER） |
| Implementation agent 需在 mutation 前准备完整协调 patch | 低 | Implementation agent 技术约束 |
| FINS_UPLOAD_FILE_SUFFIXES existence | 低 | Implementation preflight |
| FmpCompanyInfoResolver method signature | 低 | Implementation preflight |

以上均为 implementation preflight 验证点或 release gate 延迟项，不是 plan structure finding。

## 14. Open questions

无。

## 15. Final plan review conclusion

**PASS。零 material finding。零 blocker。**

All eight findings 独立证明 CLOSED：

| Finding | Status |
|---|---|
| `R11-IMP-BF01` | CLOSED |
| `R11-PR-BF-RR-F01` | CLOSED |
| `R11-PR-BF-FR-DS-F01` | CLOSED |
| `R11-PR-BF-FR-DS-F02` | CLOSED |
| `R11-PR-BF-FR-CV-F01` | CLOSED |
| `R11-PR-BF-RR2-DS-F01` | CLOSED |
| `R11-PR-BF-RR2-DS-F02` | CLOSED |
| `R11-PR-BF-RR2-DS-F03` | CLOSED |

- 全部 §2.2 source locks 独立验证通过（含 absolute external OLD paths）。
- 五个 Q4 owner oracle 全部通过。
- Two-slice state machine 边界精确。
- Sequential edit / safety stop 完整。
- Correction loop / combined revalidation 完整。
- Semantic owner boundary 清晰。
- Closed allowlist 未变。
- pyright `0 errors` / coverage >=80% / Ruff 0.15.11 baseline / security / deferred / Windows gates 未弱化。
- README trigger matrix 维护。
- POSIX smoke / Windows PENDING_RELEASE_BLOCKER 未弱化。
- 无新 current material finding。
- 未重开已裁决产品问题。

---

| Item | Count |
|---|---:|
| prior findings closed | 8 |
| accepted/open new findings | 0 |
| blocker | 0 |
| actual accepted residual | 0 |

Windows：`PENDING_RELEASE_BLOCKER`，未改变。
R12、deferred Issue 与统一 authorization framework 未进入。

READY_FOR_CONTROLLER_R11_FINAL_PLAN_REREVIEW3_ADJUDICATION
