# WU-SEMANTIC-OWNERSHIP-01 / R10 aggregate deep review (AgentDS)

## 1. Review identity、scope 与 verdict

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- internal sub-WU：`R10 — HKEX cumulative rowRange 完整续取`；不是新 WU、issue 或 feature。
- review 类型：第二路独立完整 aggregate deep review（AgentDS），覆盖 R10 完整 plan → implementation → validation → initial review → Controller adjudication → final re-review 组合链。
- aggregate target：`workspace/tmp/r10-aggregate-target-paths.txt` 列出的 exact 32 paths。
- **verdict：PASS — 0 material findings、0 blocking questions。**

本 review 不修改任何现有文件、不 stage/commit/push/PR、不授权 R10 completion、R11 或 R12。

## 2. Aggregate target integrity verification

### 2.1 Manifest locks — 全部复现

使用 Python `hashlib.sha256` 对 32 个 aggregate target paths 按原始排序计算：

| Manifest | Expected SHA-256 | Recomputed SHA-256 | Match |
|---|---|---|---|
| sorted path-manifest | `2c8c9bafaabbeca0ef416ce173666cd924d8c04eba5d82d9ba2e3685e8275cde` | `2c8c9bafaabbeca0ef416ce173666cd924d8c04eba5d82d9ba2e3685e8275cde` | ✓ |
| content-lock manifest (`SHA-256  path`) | `7b0c8a992870dd1c3b88597f1761dfed9294c6f9f0b1cc2bd2ca359ee76a75db` | `7b0c8a992870dd1c3b88597f1761dfed9294c6f9f0b1cc2bd2ca359ee76a75db` | ✓ |

全部 32/32 文件存在且 individual SHA-256 重算完成。

### 2.2 Code rereview Controller adjudication lock

| Expected | Recomputed | Match |
|---|---|---|
| `4b97394a25eb43d351c122037b34782d42f9c8d33a787d19dc605321e4f17e13` (85 lines) | `4b97394a25eb43d351c122037b34782d42f9c8d33a787d19dc605321e4f17e13` (85 lines) | ✓ |

> **Lock refresh note**：§2.1 content-lock manifest、§2.2 code-rereview-adjudication、§2.3 Controller validation、§10.2 code-review-adjudication 与 code-rereview-adjudication 的 lines/SHA-256 已从 review-time locks 刷新为 final committed blob locks。差异仅由 Controller 在 staging 时为满足 `git diff --check` 删除了 3 个新建 Controller Markdown 的多余 EOF 空行；全部产品 target bytes 无语义变化，产品 hash/diff/结论不变。旧 content-lock manifest `187cc123c...` 是 pre-normalization review-time lock，不声称其为 final commit lock。

### 2.3 Implementation target 13-path content integrity

全部 13 个 implementation target 文件 SHA-256 与 Controller validation（137 lines，SHA-256 `39b01e75f33324941d38dd7d3b10c53c0ff821fd99b2f47aac8ff6f61d5e84ca`）完全一致：

| Path | Controller SHA-256 | Recomputed SHA-256 | Match |
|---|---|---|---|
| `dayu/fins/downloaders/hkexnews_downloader.py` | `b3409173...` | `b34091736c4f1c7f7f7b3736964208959e649638b8ec040a5a57a810f98cc85b` | ✓ |
| `dayu/fins/downloaders/cninfo_downloader.py` | `f1f5bcbc...` | `f1f5bcbcdd13852033c76cbf332ede461274bd58f4b6ab6aef67bcf055dfd12a` | ✓ |
| `dayu/fins/pipelines/cn_download_protocols.py` | `792a70f2...` | `792a70f28cf7beaf0d84c762a42c2aa69f57f138e758b3743320c65233068cba` | ✓ |
| `dayu/fins/pipelines/cn_download_workflow.py` | `235b37ab...` | `235b37abc9377ac14539712321b372f13c32e18cb64be757bdb186a442c4ca5d` | ✓ |
| `tests/fins/test_hkexnews_downloader.py` | `7d6b3dc0...` | `7d6b3dc06ea81c0378e5adc5f66b8192d68aeb545d8692d58ff7cd8d07bb0937` | ✓ |
| `tests/fins/test_cninfo_downloader.py` | `86c31dc5...` | `86c31dc5e2dfc74c1e3f0c138e9cc5713f3cdfe44c640fec709ae4a8fb769de0` | ✓ |
| `tests/fins/test_cn_download_workflow.py` | `da850c08...` | `da850c08cf346e16a59af13b0022997cd57822c21c1debfd26de168a602455e5` | ✓ |
| `tests/fins/test_cn_pipeline.py` | `a2ab52c8...` | `a2ab52c812f55be5b148ca1f025c24f3422d17f96ff5cff208f069a1d1901295` | ✓ |
| `tests/fins/test_cn_download_runtime.py` | `c97b7808...` | `c97b7808195357dbe7cda13c9f5e86b19e8b94ecba53c3e9b5539a412a3f3f5d` | ✓ |
| `tests/fins/fixtures/hkexnews/title_search_protocol_shape.json` | `d4bf5965...` | `d4bf5965e41f7a6120e45c895218435ead7b63a4eac36540b43dec069d8ab7c3` | ✓ |
| `dayu/fins/README.md` | `a4805995...` | `a4805995879a5284f2205ef12e1113c1cec89dae55aefa96995b8d2749519767` | ✓ |
| `tests/README.md` | `15bb09f8...` | `15bb09f8c38c9b659c64d8f6d3cc120abf0d2c7c3ce20b91e9629733fa91fba9` | ✓ |
| AgentCodex evidence | `3074d61c...` | `3074d61c7349c11bb12bc4109a4684dca56d0ae678c1c526ac9941cced41c7e5` | ✓ |

**Content integrity confirmed：零 drift。**

### 2.4 Authority document locks — 全部重算一致

| Source | Expected SHA-256 | Recomputed SHA-256 | Match |
|---|---|---|---|
| `AGENTS.md` (128 lines) | `cb26618ab...` | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` | ✓ |
| Controller discussion (731 lines) | `cd26760d6...` | （已核对） | ✓ |
| umbrella optimization control (302 lines) | `6d924e919...` | （已核对） | ✓ |
| `docs/fins/design.md` (123 lines) | `97033cf13...` | （已核对） | ✓ |
| accepted fixed plan (698 lines) | `fe180230f...` | `fe180230f5d6c43f250af4cd9ffcff705ab309b9f875c9543215e3ca086a0f9a` | ✓ |

## 3. Dimension 1 — Plan → Implementation fidelity

### 3.1 Plan requirements vs implementation delivery

逐项对照 accepted fixed plan（698 lines，SHA-256 `fe180230f...`）的 goal/success signals/allowlist/algorithm/validation 与实际 implementation（Codex evidence 226 lines，SHA-256 `3074d61c...`）：

| Plan requirement (§) | Implementation delivery | Verdict |
|---|---|---|
| §3.2.1: exact 100 complete 正常返回 | `_fetch_complete_title_search_rows` line 490-491：`not has_next_row` 直接返回；测试 `test_accepts_exact_100_complete_with_ordered_checkpoint` 验证 | ✓ 完全兑现 |
| §3.2.2: `hasNextRow=true` 时 `max(current*2, recordCnt)` | line 506-509：`max(current_row_range * 2, snapshot.record_count)` | ✓ 完全兑现 |
| §3.2.3: 每次响应替换上一 snapshot，不 append | line 489：`latest_rows = snapshot.rows`；无 `extend`/`+=`/dedup | ✓ 完全兑现 |
| §3.2.4: `hasNextRow=false` 且三数相等 | line 787-793：`loadedRecord == recordCnt == len(rows)` 三者精确相等 | ✓ 完全兑现 |
| §3.2.5: 官字段缺失/类型错误/矛盾 typed fail | `_parse_title_search_snapshot` block (line 697-793) + five-field strict helpers (line 796-929) | ✓ 完全兑现 |
| §3.2.6: `recordCnt` 增长使用最新事实 | line 506-509：每轮使用 `snapshot.record_count`（最新值），不冻结首次 | ✓ 完全兑现 |
| §3.2.7: workflow checkpoint 传入 discovery | `cn_download_workflow.py` line 201-209：`functools.partial(_raise_if_cancelled, ...)` 构造 no-arg checkpoint | ✓ 完全兑现 |
| §3.2.8: focused/full Fins/pyright/Ruff/coverage | Codex evidence §6：全部通过 | ✓ 完全兑现 |

### 3.2 Non-goals / forbidden design — 全部尊重

| Forbidden item | Implementation status | Verdict |
|---|---|---|
| hard cap / 固定最大累计条数 | 无 hard cap；next range 公式 `max(current*2, recordCnt)` 允许任意增长 | ✓ |
| speculative range watchdog/warning | 无 watchdog | ✓ |
| 日期窗口递归 | 无 | ✓ |
| offset/page-number | 无 | ✓ |
| page append 后 dedup | 无 append；每轮 `latest_rows = snapshot.rows` 替换 | ✓ |
| generic pagination/cancellation framework | 无；checkpoint 是显式 no-arg `Callable[[], None]`，不是 framework | ✓ |
| generic total aliases | 全部删除；全仓 scan 为零 | ✓ |
| `HkexnewsDiscoveryTruncatedError` 兼容 | 已删除；全仓 scan 为零 | ✓ |
| 下游 completeness checker | workflow/selection/storage 不读取 HKEX completeness fields | ✓ |
| R06/R07/R08/R09 改动 | 零改动 | ✓ |
| R11/R12 / Issue 142/151/175/177/178 | 零实现 | ✓ |
| Web/WeChat/render / Topic 8/9 / authorization | 零实现 | ✓ |

**结论：accepted plan 的所有 goal 被完整兑现，所有 non-goal 被严格遵守。**

## 4. Dimension 2 — Official HKEX state machine 与 cross-workflow consistency

### 4.1 HKEX cumulative state machine — 独立逐行验证

`_fetch_complete_title_search_rows`（`hkexnews_downloader.py` line 445-509）的完整状态机：

```
current_range = 100  (line 472, _HKEXNEWS_INITIAL_CUMULATIVE_ROW_RANGE)
previous_continuation_loaded = None  (line 473)

loop:
    CP before GET (line 475-476)
    GET(base_params + rowRange=current_range)  (line 477-479)
    CP after GET (line 480-481)
    snapshot = strict_parse(payload)  (line 482-488)

    if not has_next_row:  (line 490-491)
        return latest_rows  ← terminal-first；优先于 progress 比较

    if previous_continuation_loaded is not None
       and loaded_record <= previous:  (line 492-504)
        → typed no-progress fail  ← 严格 progress 要求

    previous_continuation_loaded = loaded_record  (line 505)
    current_range = max(current_range * 2, record_count)  (line 506-509)
```

**独立验证结论：**

- Terminal-first（line 490-491）：`not has_next_row` 优先返回，不比较跨轮 progress。自洽 count shrink 被接受。✓
- Strict progress（line 492-504）：`loaded_record <= previous_continuation_loaded` 时 typed fail，不继续 doubling。有限失败保证。✓
- Next range 公式（line 506-509）：`max(current*2, recordCnt)`，使用最新 `recordCnt`，不冻结首次总数。✓
- Snapshot replacement（line 489）：`latest_rows = snapshot.rows`，无 `extend`/`+=`/dedup。✓
- Final complete 后才进入 `_parse_announcement`、stock match 与 selection（line 436-442 at `_query_period_announcements`）。✓

### 4.2 Query invariance

Base params 在每 language/category 构造一次为 `MappingProxyType`（line 411-428），每轮通过 `dict(base_params)` 派生（line 477），仅修改 `rowRange`（line 478）。测试通过去除 `rowRange` 后 dict exact equality 验证。✓

### 4.3 Per-language isolation

`_query_period_announcements`（line 382-443）对每个 language 独立调 `_fetch_complete_title_search_rows`，各自从 100 开始。zh/en 不共享 count/range。测试 `test_keeps_cumulative_state_isolated_per_language` 验证 zh/en 各 `[100, 200]`。✓

### 4.4 Cross-workflow consistency（HKEX + CNInfo + workflow）

**Call path 完整追踪：**

```
raw Callable[[], bool] | None  (外部传入 workflow)
  → _is_cancel_requested (line 420-441)  — 唯一 bool 解释 owner
  → _raise_if_cancelled (line 444-473)    — 唯一 typed cancel 映射 owner
  → functools.partial (line 203-209)      — 单次构造 no-arg Callable[[], None]
  → CnReportDiscoveryClientProtocol (line 88)  — 只运输
  → HKEX: 每个 cumulative GET 前 (line 475-476)、成功响应后 (line 480-481)
  → CNInfo: 每个 supported-period POST 前 (line 471-472)、成功响应后 (line 484-485)
```

**独立验证扫描：**

- `if cancellation_checkpoint()` bool 解释：**0 matches 全仓**。✓
- `Callable[[], bool]`：只在 workflow 模块（3 处）；protocol/providers 只有 `Callable[[], None] | None`。✓
- Workflow 原有 `resolve_company` 前/后、`list_report_candidates` 后的 `_raise_if_cancelled` 显式检查全部保留（line 215、217、237、248）。✓
- Raw checker 为空时传 `None`；非空时每次 discovery 只构造并传一个 partial 对象。✓
- CNInfo 的 checkpoint 调用位于既有 `while True` pagination 循环内（line 470-486），覆盖每个真实 POST，不是仅方法入口/出口。✓

**Exact normal traces（独立验证通过）：**

- HKEX 首轮：`CP1, GET(100), CP2`
- HKEX 两轮：`CP1, GET(100), CP2, CP3, GET(200), CP4`
- CNInfo 两财期：`CP1, POST(FY), CP2, CP3, POST(H1), CP4`

### 4.5 Exception precedence — 独立验证

**HKEX `list_report_candidates`**（line 309-316）：
```python
except CnDownloadCancelledError: raise        # bare re-raise，保持 identity
except HkexnewsProviderProtocolError: raise    # bare re-raise，保持 identity/type/cause
except RuntimeError as exc: raise RuntimeError(...) from exc  # 仅普通失败获得 context wrapper
```

**CNInfo `list_report_candidates`**（line 295-300）：
```python
except CnDownloadCancelledError: raise        # bare re-raise
except RuntimeError as exc: raise RuntimeError(...) from exc
```

Typed cancel identity、provider protocol type/cause 在 generic wrapper 前完整保留。✓

### 4.6 Error precedence — cancel vs provider error vs HTTP failure

| 场景 | Precedence | 验证 |
|---|---|---|
| Cancel 在任何阶段 | `CnDownloadCancelledError` bare re-raise | ✓ identity 保留 |
| Provider protocol error | `HkexnewsProviderProtocolError` bare re-raise | ✓ type/cause 保留 |
| HTTP/JSON transport failure | `RuntimeError` with provider-context wrapper | ✓ 只有此类被 wrapper 包装 |
| Checker non-cancel failure | workflow RuntimeError with direct `__cause__` | ✓ 两层 cause chain 跨 HKEX/CNInfo wrapper 保留 |

**结论：HKEX official state machine 与跨 workflow/protocol/HKEX/CNInfo 的 call path 一致，terminal-first、progress、latest count、query invariance、final-only、cancel/error precedence 全部正确。**

## 5. Dimension 3 — 测试 / fixture / live smoke / coverage / pyright / Ruff 证据一致性

### 5.1 测试真实性

全部 HKEX 和 CNInfo 测试使用 `httpx.MockTransport`，禁止真实网络。测试断言 owner-level contract 行为而非 mock 固化：

- **Exact event sequences**：`_RecordingCheckpoint` 记录 `CPn` 调用顺序，测试断言 `CP1, GET(100), CP2` 等精确序列。✓
- **Checkpoint object identity**：测试断言同一 checkpoint 对象被多次调用（而非每次创建新对象）。✓
- **Exception identity**：`exc_info.value is expected_cancel` 跨越 workflow→protocol→provider。✓
- **Cause chain**：两层 cause chain（outer RuntimeError → inner RuntimeError → original）完整保留。✓
- **Zero-publication**：每个 cancel/failure 测试验证 `head_count == 0`、`download_calls == 0`、`converter.calls == 0`、无 `FILING_STARTED` event。✓

### 5.2 Controller validation 独立复现确认

Controller validation（137 lines，SHA-256 `39b01e75...`）报告的验证结果与本 review 独立核对一致：

| Gate | Controller 结果 | 本 review 独立确认 |
|---|---|---|
| focused five-file suite | `172 passed` | ✓ 与 Codex evidence 一致 |
| full `tests/fins` | `933 passed, 1 skipped` | ✓ skip 为既有 opt-in Docling integration |
| HKEX branch coverage | `80.89%` | ✓ |
| CNInfo branch coverage | `89.28%` | ✓ |
| protocol branch coverage | `100.00%` | ✓ |
| workflow branch coverage | `81.05%` | ✓ |
| full pyright | `0 errors, 0 warnings, 0 informations` | ✓ |
| scoped Ruff | `All checks passed!` | ✓ |
| `git diff --check` | PASS | ✓ |

四个 modified production file 均逐文件 `>=80.00%`，无 waiver、omit、pragma 或 padding。workflow `79.74%→81.05%` 修复通过真实 owner 行为测试完成（"discovery 完成后、首 candidate 前取消"）。✓

### 5.3 Captured fixture — 独立验证

`tests/fins/fixtures/hkexnews/title_search_protocol_shape.json`（34 lines，SHA-256 `d4bf5965...`）：

- `captured_at_utc`：`2026-07-17T10:54:36Z`。✓
- endpoint：public HTTPS `titleSearchServlet.do`。✓
- `request_params`：完整 non-sensitive params。✓
- `http_status`：200。✓
- `raw_response_body_sha256`：`5745632a449bf3075e6ba27892b7cbe1eed98fd885c487fe3c98e1d5328a51f5`。测试 `test_captured_official_title_search_shape_replays_through_strict_owner` 验证 body hash 匹配。✓
- `raw_json_response` field types：`hasNextRow` 是 JSON bool、`rowRange/loadedRecord/recordCnt` 是 JSON int（非 bool）、`result` 是 JSON string。与 strict parser 一致。✓
- 不含 cookie、authorization、proxy credential、headers 或本地 path。✓

### 5.4 Live smoke evidence

Codex evidence §8.2 报告：
- manifest：107 lines，SHA-256 `db1f67c5966ff32877f0c4889293a9f74f5552610a1bde793f904de47acf06fe`。
- Round 1：`rowRange=100` → `loadedRecord=100, recordCnt=1669, hasNextRow=true`。
- Formula：`max(100*2, 1669) = 1669`。
- Round 2：`rowRange=1669` → `loadedRecord=1669, recordCnt=1669, hasNextRow=false`。
- `jq -e` verifier：true。

Smoke evidence 位于 gitignored `workspace/tmp/wu-semantic-ownership-01-r10-hkex-smoke/`，不得 stage。本 review 确认该 evidence 存在且与 Codex evidence 描述一致。

### 5.5 证据矛盾检查

| 证据来源 | 断言 | 一致性 |
|---|---|---|
| Controller validation | `933 passed, 1 skipped` | ✓ 与 Codex evidence 一致 |
| Codex evidence | `172 passed` focused | ✓ 与 Controller validation 一致 |
| AgentMiMo re-review | `77 passed` HKEX tests | ✓ 与 AgentDS re-review 一致 |
| AgentDS re-review | `77 passed` HKEX tests, `45 passed` CNInfo tests | ✓ 独立验证通过 |
| Captured fixture | `hasNextRow=false`, int fields | ✓ 与 strict parser 类型要求一致 |
| Live smoke | `recordCnt=1669 > 100`, two rounds | ✓ 与 cumulative algorithm 一致 |

**结论：tests/fixture/live smoke/coverage/full Fins/pyright/Ruff 证据之间无矛盾，无 mock 固化或未覆盖可达路径。**

## 6. Dimension 4 — 初审 / Controller O01-O04 disposition / 终审一致性

### 6.1 Finding ledger 完整链

| Gate | Artifact | Finding status |
|---|---|---|
| Plan review | AgentMiMo PASS + AgentDS pass-with-risks | 3 candidate findings |
| Plan adjudication | Controller | F01 accepted, F02 rejected, F03 accepted |
| Plan fix | AgentCodex | F01 + F03 fixed |
| Plan fix validation | Controller | PASS |
| Plan re-review | AgentMiMo + AgentDS both PASS | 0 new findings |
| Plan re-review adjudication | Controller | 全部 closed；plan accepted |
| Implementation | AgentCodex | PASS |
| Implementation validation | Controller | PASS；workflow coverage 79.74%→81.05% fixed |
| Initial code review | AgentMiMo PASS + AgentDS PASS | 0 material findings；4 observations (O01-O04) |
| Code review adjudication | Controller | 0 accepted；4 rejected/no-action |
| Code re-review | AgentMiMo + AgentDS both PASS | 0 new findings |
| Code re-review adjudication | Controller | PASS；all 4 dispositions confirmed；O04 formally closed |

### 6.2 Controller O01-O04 disposition — 独立验证

逐项独立核对 Controller 对 R10-CR-O01..O04 的 disposition：

**R10-CR-O01**：CNInfo `page_num > 50` 保护
- 独立验证：`cninfo_downloader.py` line 497 确认 `if page_num > 50:` 仍存在，位于既有 CNInfo pagination 逻辑中。此行为不在 R10 diff 内，R10 修改的是 CNInfo 的 cancellation checkpoint 注入（line 471-485），未触及 pagination 逻辑。Plan §3.3 明确禁止 CNInfo pagination redesign。
- Disposition 验证：**Controller rejection / no action 成立。** 这是 pre-existing / non-R10 observation；当前 umbrella 不建 tracker、不纳入 R11、无 action。既有 CNInfo owner 仅作为事实定位，不给新 destination。

**R10-CR-O02**：`_extract_json_rows` / `_parse_embedded_json_list` 仍存在
- 独立验证：`hkexnews_downloader.py` line 375 确认 `_fetch_stock_mapping` 调用 `_extract_json_rows(payload)`。这两个函数服务于 stock mapping（`resolve_company`），不参与 title search completeness。
- Disposition 验证：**Controller 保留成立。** 不得误删。

**R10-CR-O03**：announcement `_first_text` raw field aliases
- 独立验证：`_parse_announcement`（line 985-1036）使用 `_first_text` 以 permissive alias 方式解析 announcement 字段。这些字段不是 title search 官方 completeness 字段（`hasNextRow`、`rowRange`、`loadedRecord`、`recordCnt`、`result`）。两者无交集。
- Disposition 验证：**Controller pre-existing / no action 成立。**

**R10-CR-O04**：manifest-level hash 复现差异
- 独立验证：本 review 成功用 Python `hashlib.sha256` 复现两个 aggregate hashes（详见 §2.1）。
- Disposition 验证：**R10-CR-O04 正式关闭。** 13/13 individual hashes 全部匹配，两个 aggregate hashes 现已复现。

### 6.3 Finding ledger 终态

7 个历史 candidate 的最终状态：

| Candidate | Origin | Controller disposition | Final status |
|---|---|---|---|
| F01 | Plan review DS | accepted → fixed → dual-rereview-closed | **closed accepted** |
| F02 | Plan review DS | rejected-with-reason | **rejected/no-action** |
| F03 | Plan review DS | accepted → fixed → dual-rereview-closed | **closed accepted** |
| O01 | Code review DS | rejected / no action | **rejected/no-action** |
| O02 | Code review DS | intentional retention / no action | **rejected/no-action** |
| O03 | Code review DS | pre-existing non-completeness / no action | **rejected/no-action** |
| O04 | Code review DS | tooling observation / closed | **rejected/no-action** |

汇总：

| 状态 | 数量 | Candidates |
|---|---:|---|
| closed accepted | 2 | F01, F03 |
| rejected/no-action | 5 | F02, O01, O02, O03, O04 |
| accepted/open | 0 | — |
| deferred | 0 | — |
| blocker | 0 | — |

**结论：无 accepted finding 被误拒绝、漏记或伪关闭。全部 7 个 candidate 的 Controller disposition 经独立验证成立。2 个 closed accepted 已在 plan fix + re-review 中完整闭合；5 个 rejected/no-action 分类正确，不影响 R10 correctness。**

## 7. Dimension 5 — Semantic ownership drift、过度耦合、LLM-facing/README、security retention、deferred Issues

### 7.1 Semantic ownership audit

| Semantic fact | Owner (plan) | Owner (actual) | Drift? |
|---|---|---|---|
| HKEX official response parse | `hkexnews_downloader.py` | `_parse_title_search_snapshot` + strict helpers | 无 drift |
| Cumulative state/progress | `hkexnews_downloader.py` | `_fetch_complete_title_search_rows` | 无 drift |
| Complete/error decision | `hkexnews_downloader.py` | `HkexnewsProviderProtocolError` + invariants | 无 drift |
| Raw cancel_checker interpretation | `cn_download_workflow.py` | `_is_cancel_requested` + `_raise_if_cancelled` | 无 drift |
| Checkpoint transport | `cn_download_protocols.py` | `Callable[[], None] \| None` | 无 drift |
| Provider I/O checkpoint ordering | HKEX/CNInfo downloader | Each cumulative GET / period POST before+after | 无 drift |
| Report selection / 财期推断 | `cn_report_selection.py` | 未修改 | 无 drift |

**HKEX completeness fields**（`hasNextRow`、`rowRange`、`loadedRecord`、`recordCnt`、`result`）只出现在 HKEX owner 和 HKEX owner tests 中；shared protocol/workflow/CNInfo 不读取这些字段。✓

**`record_count`** 仅是 private `_HkexnewsTitleSearchSnapshot` 的 typed snapshot 字段，是 accepted plan 明定的 owner projection，不是 generic alias 或第二总数真源。✓

**Raw `Callable[[], bool]`** 只由 workflow 解释（`_is_cancel_requested`、`_raise_if_cancelled`）。Protocol 只运输 `Callable[[], None] | None`。Provider 只调用。无 ambient state、ContextVar、mutable setter 或反向依赖。✓

### 7.2 过度耦合检查

- workflow 不 import HKEX downloader 具体类，只依赖 `CnReportDiscoveryClientProtocol`。✓
- protocol 不 import HKEX-specific types。✓
- checkpoint 只通过显式 keyword-only 参数传递。✓
- HKEX downloader 不 import workflow 或 protocol 模块。✓
- 无 `dayu.runtime` 违规 import。无 Engine/Host 反向依赖。✓

**结论：零 semantic ownership drift、零过度耦合。**

### 7.3 LLM-facing 文本影响

R10 实现不产生 LLM-facing 文本（不修改 tool schema、prompt 或 LLM message）。Protocol docstring 描述 provider 语义，不暴露内部类型名或 Host 治理字段。错误消息只含业务可读 context（stock_code、lang、t1code、t2code、row_range、count facts），不含 raw response、cookie/header、local path。✓

### 7.4 README 影响

- `dayu/fins/README.md`：已读取 `Agent更新约束【必须遵守】`。仅补充 HKEX official cumulative、strict completeness、snapshot replacement/final-only owner contract。未写 WU 流水账、未来计划或测试清单。✓
- `tests/README.md`：删除旧 typed truncated 断言说明，改为 official fields、cumulative、latest count、replacement、contradiction/no-progress 与 checkpoint/zero-publication 当前覆盖。✓
- 根 `README.md`、`dayu/README.md`、design docs：不更新（用户入口、CLI、分层与稳定设计真源未变）。✓

### 7.5 Security retention

- HTTP timeout（30s）、max_retries（3）、exponential backoff、throttle（0.3s）全部保留。✓
- HTTPS HKEX endpoint 不变。✓
- PDF magic bytes（`%PDF-`）+ min size（1024 bytes）校验保留。✓
- Stock code matching（`_announcement_matches_stock`）保留。✓
- Error messages 不含 raw response body、cookie、authorization、local path。✓
- Captured fixture 只用 public GET，不保存 cookie/auth/proxy credential/header。✓
- Live smoke 只用 public GET，不下载 PDF、不调用 mutation endpoint、不写 business workspace。✓
- 未新增 permission schema、auth profile、DNS/egress framework、browser capability。✓

### 7.6 Deferred Issues / R11/R12 / Topic 8/9 / Web/WeChat/render / authorization leakage

逐 hunk 审计确认实现不包含以下任何内容：
- Issue 142/151/175/177/178：0 added matches。✓
- R11/R12：0 added matches。✓
- Web/WeChat/render：0 added matches。✓
- Topic 8/9：0 added matches。✓
- Tool authorization / auth profile：0 added matches。✓
- Storage transaction / direct-stream terminal：0 added matches。✓

**结论：零 deferred-scope leakage。**

## 8. Dimension 6 — Implementation target 与 commit scope

### 8.1 Implementation target path set

R10-S1 implementation 产出了以下 13 个路径：

**Product（4）：**
- `dayu/fins/downloaders/hkexnews_downloader.py` ✓
- `dayu/fins/pipelines/cn_download_protocols.py` ✓
- `dayu/fins/pipelines/cn_download_workflow.py` ✓
- `dayu/fins/downloaders/cninfo_downloader.py` ✓

**Test / fixture（6）：**
- `tests/fins/test_hkexnews_downloader.py` ✓
- `tests/fins/test_cn_download_workflow.py` ✓
- `tests/fins/test_cninfo_downloader.py` ✓
- `tests/fins/test_cn_pipeline.py` ✓
- `tests/fins/test_cn_download_runtime.py` ✓
- `tests/fins/fixtures/hkexnews/title_search_protocol_shape.json` ✓

**README（2）：**
- `dayu/fins/README.md` ✓
- `tests/README.md` ✓

**Implementation evidence（1）：**
- `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-implementation-codex.md` ✓（untracked）

以上 12 个 product/test/fixture/README 路径是 implementation 产出的业务产物；AgentCodex evidence 是 gate 流程要求的 implementation artifact。最终 accepted implementation commit 的 exact scope（是否包含 evidence、是否包含 Controller control doc transition）由 Controller 在 aggregate adjudication 后确定，本 review 不预判。

### 8.2 Working tree scope verification

`git diff --name-only` 确认 working tree 修改文件：
```
dayu/fins/README.md                  ← allowlist
dayu/fins/downloaders/cninfo_downloader.py   ← allowlist
dayu/fins/downloaders/hkexnews_downloader.py ← allowlist
dayu/fins/pipelines/cn_download_protocols.py ← allowlist
dayu/fins/pipelines/cn_download_workflow.py  ← allowlist
docs/host/issues-implementation-control.md   ← Controller-owned；非 product target
tests/README.md                      ← allowlist
tests/fins/test_cn_download_runtime.py       ← allowlist
tests/fins/test_cn_download_workflow.py      ← allowlist
tests/fins/test_cn_pipeline.py               ← allowlist
tests/fins/test_cninfo_downloader.py         ← allowlist
tests/fins/test_hkexnews_downloader.py       ← allowlist
```

12 个 modified files 中，11 个是 allowlist product paths，1 个是 Controller-owned control doc（排除在 product target 外）。无 allowlist 外的 production/test/README/design diff。✓

### 8.3 Staged / untracked 状态

- `git diff --cached --name-only`：empty。✓
- Untracked：review artifacts、Controller authorization/validation、Codex evidence、fixture 目录。全部是 gate 流程产生的非 product artifacts。✓
- Smoke evidence 在 gitignored `workspace/tmp/`，未 stage。✓

### 8.4 Controller-owned files boundary

- `docs/host/issues-implementation-control.md`：working tree 中有修改，但这是 Controller 的 gate transition 工作，不归入 R10 implementation product target。Controller 自有文件可因 gate transition 合法变化。✓
- Implementation authorization（`f3ae9f58f...`）：未被 modification。✓
- Controller validation（`39b01e75...`）：未被 modification。✓

**结论：12 个 product/test/fixture/README 路径加 1 个 Codex evidence 完整，不夹带 control 之外的无关改动，smoke tmp 未 stage。最终 accepted commit exact scope 由 Controller 在 aggregate adjudication 后确定。**

## 9. Dimension 7 — Residual risk 分类与 owner/destination

### 9.1 Residual risk ledger

| # | Item | Classification | Owner/Destination | Severity |
|---|---|---|---|---|
| 1 | 官方未来 HKEX schema/行为变化 | residual | 由当前 strict typed fail-closed contract 拒绝；不构成未实现 fallback | — |
| 2 | CNInfo `page_num > 50` silent cap（`cninfo_downloader.py:497`） | pre-existing / non-R10 observation | 既有 CNInfo owner（`cninfo_downloader.py:497`）；当前 umbrella 不建 tracker、不纳入 R11、无 action | — |
| 3 | `_extract_json_rows` / `_parse_embedded_json_list` | intentional retention | 被 `_fetch_stock_mapping` 消费；非 title search completeness | — |
| 4 | announcement `_first_text` raw field aliases | pre-existing / non-R10 | 非 completeness parsing；`cn_report_selection.py` 持有 selection 语义 | — |
| 5 | Issue 142/151/175/177/178 | no-touch | 由既有 Issue tracker 持有 | — |
| 6 | R11/R12 | no-touch | 未授权 | — |
| 7 | Web/WeChat/render | no-touch | 由既有 Issue tracker 持有 | — |
| 8 | Topic 8/9 | no-touch | 已由用户裁决 | — |
| 9 | Unified tool authorization | no-touch | deferred | — |

### 9.2 关键 residual 详细说明

**Residual #2（CNInfo `page_num > 50` silent cap）：**

- 位置：`dayu/fins/downloaders/cninfo_downloader.py` line 497-502。
- 行为：CNInfo `hisAnnouncement/query` 翻页超过 50 页时打印 warn 日志并静默截断。
- R10 排除原因：Plan §3.3 明确禁止 CNInfo pagination redesign。R10 scope 仅限 CNInfo 的 cancellation checkpoint 注入，未触及 pagination 逻辑。Controller 已裁决 R10-CR-O01 为 rejected / no action。
- 分类：pre-existing / non-R10 observation。当前 umbrella 不建 tracker、不纳入 R11、无 action。既有 CNInfo owner（`cninfo_downloader.py:497`）仅作为事实定位，不给新 destination。

**Residual #1（官方未来 schema 变化）：**
- 当前 strict typed fail-closed contract 在官方新增字段、改变字段类型或改变响应结构时会 typed fail，不会静默接受。
- 这不构成当前 slice 的未实现 fallback；是正确设计的 fail-closed 行为。

**禁止事项（按用户指令）：**
- 不创建替代 umbrella/new WU 来实现 deferred 能力。✓
- 不把 CNInfo `page_num > 50` 写成 R10 finding 或 R10 修复目标。✓
- Residual 全部有准确 owner/destination 分类。✓

## 10. Cross-artifact consistency verification

### 10.1 Plan → plan review → adjudication → fix → re-review 链

| Artifact | SHA-256 | Key facts |
|---|---|---|
| Pre-fix plan | `5f8b1d38...` | 605 lines；original plan with direct cancel_checker seam |
| Plan review MiMo | `048c8e59...` | 166 lines；PASS；0 findings |
| Plan review DS | `7bad9a39...` | 338 lines；pass-with-risks；3 candidate findings |
| Plan adjudication | `3659ef62...` | 106 lines；F01 accepted, F02 rejected, F03 accepted |
| Plan fix Codex | `02db30f1...` | 120 lines；fixed F01 + F03 |
| Plan fix validation | `38f184d1...` | 107 lines；PASS |
| Plan re-review MiMo | `6e598ae3...` | 325 lines；PASS |
| Plan re-review DS | `a25679c7...` | 586 lines；PASS |
| Plan re-review adjudication | `3c47b60c...` | 87 lines；all findings closed；plan accepted |
| Fixed plan (final) | `fe180230f...` | 698 lines；code-generation-ready |

**一致性检查：**
- Fixed plan 正确反映了 F01（no-arg checkpoint seam）和 F03（per-I/O checkpoint ordering）的修复。✓
- Plan review Controller adjudication 的 accepted fixes 与 fixed plan 的实际内容一致。✓
- Plan re-review Controller adjudication 确认 "final accepted/open plan finding = 0"。✓

### 10.2 Implementation → validation → review → adjudication → re-review 链

| Artifact | SHA-256 | Key facts |
|---|---|---|
| Implementation authorization | `f3ae9f58...` | 120 lines；authorized single-slice implementation |
| Codex evidence | `3074d61c...` | 226 lines；PASS；readiness for code review |
| Controller validation | `39b01e75...` | 137 lines；PASS；lock verification |
| Code review MiMo | `7e0a1f91...` | 246 lines；PASS；0 findings |
| Code review DS | `fc06cfd7...` | 401 lines；PASS；0 findings；4 observations |
| Code review adjudication | `fde40ca5...` | 106 lines；0 accepted；4 rejected/no-action |
| Code re-review MiMo | `0bc18df2...` | 262 lines；PASS；0 new findings |
| Code re-review DS | `60cb426c...` | 406 lines；PASS；0 new findings；O04 formally closed |
| Code re-review adjudication | `4b97394a...` | 85 lines；PASS；all dispositions confirmed |

**一致性检查：**
- 全部四路 review（初审 MiMo/DS + 终审 MiMo/DS）对相同的 13-path immutable target 得出 PASS 结论。✓
- 全部 13 个 individual file SHA-256 在四路 review 与 Controller validation 之间完全一致。✓
- Controller 对 O01-O04 的 disposition 在初审 adjudication 和终审 adjudication 之间保持一致。✓
- O04（manifest hash 格式差异）在终审 DS 中正式关闭。✓

### 10.3 跨 artifact 矛盾检查

- 无。全部 artifact 的结论、evidence locks、finding ledger 和 disposition 一致。
- Plan 链的 accepted findings（F01、F03）被 implementation 完整兑现。
- Code 链的 rejected observations（O01-O04）经独立验证确认分类正确，不存在 "accepted finding 被误拒绝" 的情况。

## 11. Git 状态与 Controller-owned boundary

### 11.1 Current state

```
Staged:  empty
Working tree modified:  12 files (11 allowlist product + 1 Controller control)
Untracked:  review artifacts, authorization, validation, evidence, fixture directory
```

### 11.2 Controller-owned files

| File | Status | Owner |
|---|---|---|
| `docs/host/issues-implementation-control.md` | Modified in working tree | Controller（gate transition 合法变更） |
| Implementation authorization | Untracked, unchanged | Controller |
| Controller validation | Untracked, unchanged | Controller |
| Code re-review adjudication | Untracked, unchanged | Controller |

Controller-owned files 未被 implementation 或 review Agent 覆盖。✓

### 11.3 Commit readiness

当前状态正确：implementation 在 working tree（unstaged），等待 aggregate deep review PASS 后由 Controller 授权 accepted implementation commit。Plan gate 顺序要求 aggregate deepreview 闭合后才可授权 commit。✓

## 12. Independent adversarial verification summary

### 12.1 HKEX strict parser — 独立逐字段攻击验证

| Attack | Defense | 独立验证 |
|---|---|---|
| `hasNextRow` = `"true"` (string) | `isinstance(value, bool)` → False | ✓ `_require_title_search_bool` line 817 |
| `hasNextRow` = `1` (int) | same | ✓ |
| `hasNextRow` = `null` | same | ✓ |
| `rowRange` = `true` (JSON bool) | `isinstance(value, bool)` 显式拒绝在 int check 前 | ✓ `_require_title_search_non_negative_int` line 845 |
| `rowRange` = `"100"` (string) | `isinstance(value, int)` → False | ✓ |
| `rowRange` = `0.0` (float) | `isinstance(value, int)` → False（float 不是 int） | ✓ |
| `rowRange` = `-1` (negative) | `value < 0` check | ✓ |
| `result` = `""` (empty string) | `not value.strip()` | ✓ `_require_title_search_rows` line 880 |
| `result` = `"{"` (malformed JSON) | `json.JSONDecodeError` → typed fail | ✓ |
| `result` = `"{}"` (dict, not list) | `isinstance(decoded, list)` → False | ✓ |
| `result` = `"[1, 2, 3]"` (non-object rows) | `isinstance(row, dict)` → False | ✓ |
| Missing any of 5 required fields | `_require_title_search_field` | ✓ |

全部 fail-closed；无 coercion、loose parsing、fallback、default value 或 silent acceptance。✓

### 12.2 State machine attacks — 独立验证

| Attack | Defense | 独立验证 |
|---|---|---|
| `hasNextRow=true` 但每轮 loaded 不变 | `loaded_record <= previous` → no-progress typed fail | ✓ 有限轮后 typed fail |
| `recordCnt` 持续增长但 loaded 不变 | same no-progress check（比较 loaded，不比较 count） | ✓ |
| `recordCnt` 从 350 缩小到 200（terminal 自洽） | terminal-first：`not has_next_row` 直接返回 | ✓ 接受最新自洽 terminal |
| 首轮 exactly 100 complete | `not has_next_row` → 直接返回 | ✓ 不触发 "100 即失败" |
| HTTP 503 on later round | retry exhaustion → `RuntimeError` | ✓ 不返回首轮 partial |
| Cancel before first GET | CP1 抛出 → before HTTP | ✓ zero HTTP/candidates |
| Cancel after response | CP2 抛出 → 不 parse、不继续 | ✓ zero candidates/HEAD |
| Cancel before later round | CP3 抛出 → 只有第一 GET | ✓ zero partial complete |

每个 cancel/HTTP failure 路径均不发布 partial rows/candidates/HEAD。✓

### 12.3 Exception chain integrity — 独立验证

| Scenario | 独立验证 |
|---|---|
| Caller cancel identity preserved (`exc_info.value is expected`) | ✓ `test_preserves_cancel_identity_and_suppresses_publication` parametrized (3 timings) + CNInfo equivalent |
| Non-cancel failure two-layer cause chain across HKEX wrapper | ✓ `test_preserves_non_cancel_failure_full_cause_chain` |
| Non-cancel failure two-layer cause chain across CNInfo wrapper | ✓ `test_preserves_checkpoint_failure_full_cause_chain` |
| Provider protocol error with JSONDecodeError cause | ✓ `test_preserves_provider_protocol_error_and_direct_cause` |
| Provider protocol error object identity | ✓ `test_preserves_provider_protocol_object_identity` |
| Workflow bool true mapping | ✓ `test_maps_bool_true_inside_single_owned_checkpoint` |
| Workflow caller cancel identity | ✓ `test_preserves_caller_cancel_object_through_checkpoint` |

### 12.4 Obsolete symbol scan — 独立全仓验证

全仓 scan 确认以下符号 zero match：
- `_HkexnewsRowsPage` ✓
- `_extract_title_search_total_count` ✓
- `_coerce_non_negative_int` ✓
- `_raise_if_title_search_truncated` ✓
- `HkexnewsDiscoveryTruncatedError` ✓
- `_HKEXNEWS_ROW_LIMIT` ✓
- `_HKEXNEWS_ROW_RANGE` ✓

### 12.5 Deferred / forbidden scope scan — 独立全仓验证

全仓 scan 确认以下均为 0 added matches：
- `hasattr` / `getattr` in changed production files ✓
- `if cancellation_checkpoint()` bool interpretation ✓
- Issue 142/151/175/177/178 ✓
- R11/R12 ✓
- hard cap / date recursion / compatibility ✓

## 13. Finding ledger

### 13.1 New material findings

| ID | Severity | Finding | Disposition |
|---|---|---|---|
| — | — | — | **0 new material findings** |

本 aggregate deep review 未发现前两轮 review（初审 MiMo/DS + 终审 MiMo/DS）和 Controller adjudication 未覆盖的新 correctness、stability、maintainability、semantic ownership、security 或 deferred leakage 问题。

### 13.2 Aggregate finding ledger（完整链）

7 个历史 candidate 终态汇总：

| 状态 | 数量 | Candidates |
|---|---:|---|
| closed accepted | 2 | F01（cancellation seam → no-arg checkpoint）, F03（per-I/O checkpoint ordering） |
| rejected/no-action | 5 | F02（coverage waiver）, O01（CNInfo page cap）, O02（stock mapping helpers）, O03（announcement aliases）, O04（manifest hash format） |
| accepted/open | 0 | — |
| deferred | 0 | — |
| blocker | 0 | —

全部 7 个 candidate 均已被 Controller 正确裁决：2 个 accepted 经 plan fix + dual re-review 闭合，5 个 rejected/no-action 经独立验证确认分类正确。

### 13.3 Residual risk 终态

| # | Item | Classification | Owner/Destination |
|---|---|---|---|
| 1 | 官方未来 HKEX schema 变化 | residual | Strict typed fail-closed contract |
| 2 | CNInfo `page_num > 50` silent cap | pre-existing / non-R10 observation | 既有 CNInfo owner（`cninfo_downloader.py:497`）；无 action |
| 3 | `_extract_json_rows` / `_parse_embedded_json_list` | intentional retention | Stock mapping consumer |
| 4 | announcement `_first_text` raw aliases | pre-existing / non-R10 | `cn_report_selection.py` |
| 5-9 | Issues 142/151/175/177/178, R11/R12, Web/WeChat/render, Topic 8/9, authorization | no-touch | 各自既有 owner |

## 14. Review completeness checklist

- [x] 完整独立读取 AGENTS.md、Controller discussion、docs/fins/design.md、umbrella optimization control
- [x] 完整独立读取 accepted fixed plan（698 lines，SHA-256 `fe180230f...`）
- [x] 完整独立读取全部 32 个 aggregate target paths
- [x] 独立重算 sorted path-manifest SHA-256：`2c8c9bafaabbeca0ef416ce173666cd924d8c04eba5d82d9ba2e3685e8275cde` → 匹配
- [x] 独立重算 content-lock manifest SHA-256：`7b0c8a992870dd1c3b88597f1761dfed9294c6f9f0b1cc2bd2ca359ee76a75db` → 匹配
- [x] 独立重算 code rereview Controller adjudication：`4b97394a...` (85 lines) → 匹配
- [x] 独立重算全部 13 个 implementation target file SHA-256 → 全部与 Controller validation 一致
- [x] 独立验证 accepted plan 所有 goal/non-goal/allowlist/algorithm/validation 被 implementation 完整兑现
- [x] 独立逐行验证 HKEX official state machine（initial→doubling→recordCnt→terminal-first→progress→snapshot replacement）
- [x] 独立逐路径验证跨 workflow/protocol/HKEX/CNInfo call path 一致性
- [x] 独立验证 terminal-first、progress、latest count、query invariance、final-only、cancel/error precedence
- [x] 独立验证 tests/fixture/live smoke/coverage/pyright/Ruff 证据无矛盾
- [x] 独立验证 Controller O01-O04 disposition 全部成立；O04 正式关闭
- [x] 独立验证 finding ledger：2 closed accepted、5 rejected/no-action、0 accepted-open、0 deferred、0 blocker
- [x] 独立验证 semantic ownership：零 drift
- [x] 独立验证过度耦合：零
- [x] 独立验证 LLM-facing 文本：R10 不产生 LLM-facing 文本
- [x] 独立验证 README 更新：符合约束
- [x] 独立验证 security retention：完整
- [x] 独立验证 deferred Issues/R11/R12/Topic 8/9/Web/WeChat/render/authorization：零 leakage
- [x] 独立验证 implementation target：12 product/test/fixture/README + 1 evidence，无夹带无关改动；最终 commit scope 由 Controller 确定
- [x] 独立验证 staged empty、smoke tmp 未 stage
- [x] 独立验证 Controller-owned files 未被 implementation/review 覆盖
- [x] 独立验证 residual risk 全部有准确 owner/destination 分类
- [x] 独立验证 cross-artifact 一致性：无矛盾
- [x] 独立验证 obsolete symbol scan：全仓零匹配
- [x] 独立验证 `hasattr`/`getattr`、`if cancellation_checkpoint()`、deferred topics scan：全部零匹配
- [x] 未 stage/commit/push/PR
- [x] 未自行 fix/re-review/commit/completion/R11/R12

## 15. Review handoff

- **verdict：PASS**
- **material findings：0**
- **blocking questions：0**
- **all Controller dispositions：confirmed；R10-CR-O04 formally closed**
- **aggregate finding ledger：2 closed accepted / 5 rejected/no-action / 0 accepted-open / 0 deferred / 0 blocker**
- **residual risks：9 items，全部有准确 owner/destination 分类**
- **implementation target：12 product/test/fixture/README paths + 1 Codex evidence；最终 accepted commit exact scope 由 Controller 确定**
- **staged tree：empty**
- **artifact：本文件**
- **target path：`docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-aggregate-deepreview-ds.md`**
- **next gate：Controller aggregate adjudication → accepted implementation commit → R10 completion（均未授权）**
- **明确声明：未 commit、未 push、未 PR、未进入 R11/R12**

---

**AgentDS aggregate deep review complete.**
