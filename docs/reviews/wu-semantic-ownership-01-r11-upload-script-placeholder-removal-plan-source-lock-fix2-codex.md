# WU-SEMANTIC-OWNERSHIP-01 / R11 final-plan source-lock fix2 evidence（AgentCodex）

## 1. Gate、授权与完整输入

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` / R11 plan remediation continuation；不是新 WU、feature 或 issue。
- accepted findings：`R11-PR-BF-FR-DS-F02`、`R11-PR-BF-FR-CV-F01`。
- 授权边界：只修改 plan §2.2 的两个 source-lock cells，并新增本 evidence；不授权 implementation、产品/测试/
  README/design/CI 修改、control/既有 artifact 修改、测试、pyright、coverage、Ruff、stage、commit、push 或 PR。
- 写入方式：两次写入均只使用 `apply_patch`。

本轮完整读取输入 identity：

| Artifact | Lines | Bytes | SHA-256 |
|---|---:|---:|---|
| `AGENTS.md` | 128 | 10,036 | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` |
| plan（修复前） | 886 | 74,571 | `59156239ff4d73bfeaa1cb78a593c2b75504804102a07e851b1239803a4de51f` |
| MiMo source-lock re-review | 236 | 15,062 | `973775da67b11190e70a3c6f108d7605d9993786617f078ecc1e63493c1a5a00` |
| DS source-lock re-review | 508 | 27,710 | `f9eedd8e6277d57ce03f9e0406227cd2197e042696d481415a7ce041071ba972` |
| Controller adjudication | 101 | 5,495 | `131b6a65f0a87b615aba486968a627e2b49d52a7a48a147fd536fec6b7323dfc` |

## 2. 修复前直接 source truth

### 2.1 FMP resolver

精确 owner path 是 `dayu/fins/resolver/fmp_company_info.py`：

```text
394 lines / 13,216 bytes
SHA-256 c2abfbe03227d8b98ea639c374cb7aa9c41c98214b0b004cfb7de492be7c46fa
```

因此 `R11-PR-BF-FR-DS-F02` 的根因只是 plan label 缺少精确 path；原 394 与 full hash 均正确，不应修改。

### 2.2 `dayu/README.md` 三路锁定

| Source | Lines | SHA-256 |
|---|---:|---|
| working tree `dayu/README.md` | 265 | `16bbdc87da05f68ad7787086cf5e4646e011a8e8304991cb360916487fa85367` |
| accepted-plan `f7b452f992b4797b32fea7c6f7212b5ec4345ec1:dayu/README.md` | 265 | `16bbdc87da05f68ad7787086cf5e4646e011a8e8304991cb360916487fa85367` |
| R10 baseline `2b14b2fbc89654267e3d33daa2ae410ceff45e68:dayu/README.md` | 265 | `16bbdc87da05f68ad7787086cf5e4646e011a8e8304991cb360916487fa85367` |

三路完全一致，没有 source drift。`R11-PR-BF-FR-CV-F01` 的根因是 plan 创建时的 measurement/copy error，正确
owner-side 修复是只改 grouped README row 的第二组 lines/hash cells。

## 3. Exact two-cell plan diff

```diff
--- plan.before
+++ plan.final
@@ -65,9 +65,9 @@
 | CURRENT `dayu/fins/upload_batch.py` | 376 | `6767d30cfd788e584cef22e5109b1ae0b787ecaedc8581a4cfcf2c49d5ad6178` |
 | CURRENT `dayu/cli/commands/fins.py` | 1057 | `0db8ff2dedf541c2b58bc11342a02cd0bf4098bc9fcc19d948efa5cf4afc95a6` |
 | CURRENT `dayu/cli/arg_parsing.py` | 932 | `a0e25ad6c58f3f266ef1afc4447c4a7e875d18c23ad346550ccf8cfd283c1c2c` |
-| CURRENT FMP resolver | 394 | `c2abfbe03227d8b98ea639c374cb7aa9c41c98214b0b004cfb7de492be7c46fa` |
+| CURRENT `dayu/fins/resolver/fmp_company_info.py` | 394 | `c2abfbe03227d8b98ea639c374cb7aa9c41c98214b0b004cfb7de492be7c46fa` |
 | CURRENT `pyproject.toml` | 152 | `e076606fd68ab911291be92cdba1bda9df05835baf8db7f81b1d33d517ce6a25` |
-| root / `dayu/` / Fins / tests README | 348 / 111 / 793 / 293 | `2f5cebfd...a6e6a` / `1534bcfd...d9a74` / `a4805995...9767` / `15bb09f8...1fba9` |
+| root / `dayu/` / Fins / tests README | 348 / 265 / 793 / 293 | `2f5cebfd...a6e6a` / `16bbdc87da05f68ad7787086cf5e4646e011a8e8304991cb360916487fa85367` / `a4805995...9767` / `15bb09f8...1fba9` |
 | CURRENT `requirements.txt` | 12 | `d15176134f7e1cf651b77175450dba526a5e82ff7c7f60cf15356c1532215d3a` |
 | OLD `dayu/fins/cli_support.py` | 2267 | `248cc859d4dd0fdf8ed7829cc27dad48349227dfbd43f076414770166c93da45` |
 | OLD `dayu/fins/upload_recognition.py` | 555 | `5a45618b2545ad0ee024efb428de7e614c96b2c5bb0a222bf1586febc1dff816` |
```

Exactness proof：从 final plan 只反向替换上述两个 exact final literals 后，重建结果精确等于修复前 identity
`886 lines / 74,571 bytes / SHA-256 59156239ff4d73bfeaa1cb78a593c2b75504804102a07e851b1239803a4de51f`。
因此 plan 其它字符、marker、gate、owner、scope、slice、validation、Windows、deferred 与 security 文本均未改变。

修复后 plan identity：

```text
886 lines / 74,647 bytes
SHA-256 817c9d2fde2112c244e14659e713041748e59d048b77e07be2f0b8def5175a92
```

## 4. Grouped README row 未授权 cells 保持不变

| Cell | Before | Final | Working-tree full source SHA-256 |
|---|---|---|---|
| root README | `348` / `2f5cebfd...a6e6a` | `348` / `2f5cebfd...a6e6a` | `2f5cebfd3bf82b7099ff11f94e7a1e0df3840ca13fc41324a9d4ae99a02a6e6a` |
| `dayu/` README | `111` / `1534bcfd...d9a74` | `265` / `16bbdc87da05f68ad7787086cf5e4646e011a8e8304991cb360916487fa85367` | `16bbdc87da05f68ad7787086cf5e4646e011a8e8304991cb360916487fa85367` |
| Fins README | `793` / `a4805995...9767` | `793` / `a4805995...9767` | `a4805995879a5284f2205ef12e1113c1cec89dae55aefa96995b8d2749519767` |
| tests README | `293` / `15bb09f8...1fba9` | `293` / `15bb09f8...1fba9` | `15bb09f8c38c9b659c64d8f6d3cc120abf0d2c7c3ce20b91e9629733fa91fba9` |

除获授权的第二组 cell 外，第一、第三、第四组 lines/hash cell 逐字符不变。

## 5. Final scope 与 integrity checks

```text
git diff --name-only -- README.md dayu tests pyproject.toml requirements.txt .github \
  docs/fins/design.md docs/ui/design.md docs/host/design.md docs/engine/design.md docs/tool/design.md
=> empty（product/test/README/design/CI diff 为空）

git diff --cached --name-only
=> empty（staged tree 为空）

git diff --check
=> exit 0，stdout/stderr 为空
```

- 本轮 write manifest 精确为 plan 与本 evidence；Controller-owned control、既有 review/auth/stop/adjudication artifacts
  均未触碰。
- 未运行 tests、pyright、coverage 或 Ruff，符合本 gate 的明确禁令。
- 未 stage、commit、push 或创建 PR。

READY_FOR_CONTROLLER_R11_FINAL_PLAN_SOURCE_LOCK_FIX2_VALIDATION
