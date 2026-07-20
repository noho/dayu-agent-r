# WU-SEMANTIC-OWNERSHIP-01 / R10 fixed plan — AgentDS 第二路独立完整 re-review

## 1. Review identity 与 target lock

- **reviewer**：AgentDS（第二路独立完整 re-review，不是新 WU）
- **review type**：adversarial plan re-review；不是 plan acceptance 或 implementation authorization
- **target artifact**：`docs/host/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan.md`
- **target lock**：698 lines；SHA-256 `fe180230f5d6c43f250af4cd9ffcff705ab309b9f875c9543215e3ca086a0f9a` —— **已核对一致**
- **baseline HEAD**：`1c2585275f4134d8456a3fda2d84464e4e52c9d7` —— **已核对一致**
- **branch**：`phaseflow/host-issues-control`
- **staged tree**：empty —— **已核对一致**
- **review timestamp**：2026-07-17T18:29:40+08:00（本机系统时钟）

## 2. Prior artifacts consumed

以下全部完整读取并核对 SHA：

| Artifact | Lines | SHA-256 | 核对 |
|---|---|---|---|
| AgentMiMo R10 plan review | 166 | `048c8e5998f6a9868fbc41b89127b26fec987a248d9a8aa89955b94d0634fe16` | ✓ |
| AgentDS R10 plan review (初轮) | 338 | `7bad9a391f19571724d3452c93797acc042c7e44ecedfb7f20c2e38697a956ce` | ✓ |
| R10 plan review Controller adjudication | 106 | `3659ef62964b195cda60d4c4d5e961214594076e75fc0a52adcda4f076493f4f` | ✓ |
| AgentCodex plan-only fix | 120 | `02db30f1d365efd76917b3326893c2e7c58e27c99cb0a63ae8b695f6edb0ffe8` | ✓ |
| Controller fix validation | 107 | `38f184d11cc371216c80dea42a238b9867e7cbf7ffc99f15d93811976478bcd8` | ✓ |
| R10 plan-entry Controller validation | 96 | `885f40461b3b1fd4030437f35ee54eb8ab4227f5e5e1849ce0353d61299136ef` | ✓ |
| `AGENTS.md` | 128 | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` | ✓ |
| `docs/fins/design.md` §8 | 123 | `97033cf1330e6018df2cf7bf676fa550c24e3e99beb99792f718eac31727abdd` | ✓ |

## 3. Production code locks — 全部重算并核对

| File | Lines | 实际 SHA-256 | Plan lock 一致 |
|---|---|---|---|
| `dayu/fins/downloaders/hkexnews_downloader.py` | 1065 | `8c7c1a3b8e1aebc91ec82756754eb7894d6748471b69ce164a9798b260f5eb31` | ✓ |
| `tests/fins/test_hkexnews_downloader.py` | 1213 | `d98266b8016e47a5ba4f77d680196b373933f71b184e559b2b483bd76f9de1d9` | ✓ |
| `tests/fins/test_cn_download_workflow.py` | 1660 | `c2d86d4778002d904df40ab0c5ac67660683e76ea989a692d917650aa09b1e1f` | ✓ |
| `dayu/fins/pipelines/cn_download_protocols.py` | 227 | `a92f283c0284aa1fce77031d73faf3cf9b37f6438b52b91b1cd317c26a6c003e` | ✓ |
| `dayu/fins/pipelines/cn_download_workflow.py` | 806 | `3c27e009897c4c6030520f891f38648876cf3dd6a26c14d27f7ae50473f3c24f` | ✓ |
| `dayu/fins/downloaders/cninfo_downloader.py` | 835 | `baab2ae471fc3f8201fc8bf97447c3fa647abd7dc25788d496d135a82f829d07` | ✓ |
| `tests/fins/test_cninfo_downloader.py` | 1397 | `92e518f52401b0106c7726a7984b0d90c18cb58aba41aee7470c23864ce15399` | ✓ |
| `tests/fins/test_cn_pipeline.py` | 718 | `7f00b257ecc7d128218aeca2505ea8cb6e3f89f624d58c3a8c734e8edf5189ee` | ✓ |
| `tests/fins/test_cn_download_runtime.py` | 704 | `b37a4a86c607f57982536097a16b58a4297b1fcb4d99e406db49e4ec7dc95ba9` | ✓ |

**结论：零 source drift。全部 production/test/README locks 与 plan 一致。**

## 4. R10-PR-F01 逐项 closure 证明

### 4.1 根因回顾

初轮 DS-R10-F01：plan 要求把 raw `Callable[[], bool] | None` 传给 provider，由 HKEX/CNInfo 各自解释 bool、typed cancel 和非取消异常，造成取消解释 owner 分裂。

### 4.2 Fixed plan 的 closure 机制

Fixed plan 把取消事实拆成唯一 owner + 纯运输：

**Owner map（fixed plan §4.1）**：
- raw `Callable[[], bool]` 只由 workflow 既有 `_raise_if_cancelled` 解释（workflow 是唯一 owner）
- workflow 用 `functools.partial(_raise_if_cancelled, module=..., ticker=..., document_id="", cancel_checker=cancel_checker)` 把同一 helper 绑定为 no-arg `cancellation_checkpoint`
- protocol 只运输 `Callable[[], None] | None`
- provider 只调用，不解释返回值、不读取 raw bool、不复制 workflow helper

**代码事实验证**：

`_raise_if_cancelled` 定义在 `cn_download_workflow.py:430-459`，签名确为全 keyword-only：

```python
def _raise_if_cancelled(
    *,
    module: str,
    ticker: str,
    document_id: str,
    cancel_checker: Callable[[], bool] | None,
) -> None:
```

`_is_cancel_requested` 定义在 `cn_download_workflow.py:406-427`，统一解释：bool True 返回 True → `_raise_if_cancelled` 抛新 `CnDownloadCancelledError`；checker 主动抛 `CnDownloadCancelledError` → `isinstance` 匹配 → `raise`（re-raise 保留 identity）；checker 抛非取消异常 → `RuntimeError("取消检查失败: ...") from exc`（保留 cause chain）。

**functools.partial 可实现性验证**：`functools.partial(func, kw1=val1, kw2=val2)` 接受 keyword arguments 并绑定；在 Python 3.11 中完全合法。当 partial 对象以零参数调用时，所有已绑定的 keyword arguments 原样传入 `_raise_if_cancelled`。`partial` 对象是 `Callable[[], None]` 的有效 structural subtype——其 `__call__(*args: Any, **kwargs: Any) -> None` 可接受零参数调用，pyright 在标准配置下接受此赋值。若极严格 pyright 配置报类型不匹配，等价 lambda 替代方案（`lambda: _raise_if_cancelled(...)`）语义相同，不改变 owner map。

**对象 identity 验证**：`functools.partial` 返回同一对象。workflow 将该对象赋值给变量 `checkpoint`，然后传入 `discovery.list_report_candidates(query, profile, cancellation_checkpoint=checkpoint)`。同一个 partial 对象贯穿整个 protocol 调用链和 downloader 内部循环。测试通过 `is` 操作符可断言 `CP1 is CP2 is CP3`。

### 4.3 Exception precedence closure

Fixed plan §5.3 明确 HKEX `list_report_candidates` 的 handler 顺序：

```text
except CnDownloadCancelledError: raise      ← typed cancel passthrough
except HkexnewsProviderProtocolError: raise ← provider protocol passthrough
except RuntimeError as exc:                  ← existing generic wrapper
```

**Caller cancel identity 完整 trace**：

1. raw checker 抛预构造 `CnDownloadCancelledError`
2. `_is_cancel_requested` 中 `isinstance(exc, CnDownloadCancelledError)` → True → `raise`（re-raise，identity 保留）
3. 异常穿透 `_raise_if_cancelled`、partial wrapper、protocol transport
4. 进入 HKEX downloader 的 cumulative loop → 穿透到 `list_report_candidates`
5. `except CnDownloadCancelledError: raise` → 原对象 identity 保留
6. Test 断言：`exc.value is expected_cancel` → True

**Non-cancel cause chain 完整 trace**：

1. raw checker 抛非取消异常（如 `ValueError("db error")`）
2. `_is_cancel_requested` → `except Exception as exc: raise RuntimeError("取消检查失败: ...") from exc`
3. 此为 workflow-owned RuntimeError（`__cause__ is original_error`）
4. 若进入 HKEX generic wrapper → 再加一层 RuntimeError → 两层 cause chain
5. Test 断言：`wrapper.__cause__.__cause__ is original_error`

**Checkpoint normal return**：`_raise_if_cancelled` 在 `_is_cancel_requested` 返回 False 时 `return`，不抛异常。provider 继续正常流程。

### 4.4 结论

R10-PR-F01 已完整闭合。取消解释 owner 唯一（workflow `_raise_if_cancelled`），protocol 只运输 no-arg checkpoint，provider 只在 I/O 边界调用。所有三个分支（normal return、bool true mapping、caller typed cancel identity / non-cancel cause chain）均有明确 trace 和 test contract。

---

## 5. R10-PR-F03 逐项 closure 证明

### 5.1 根因回顾

初轮 DS-R10-F03：CNInfo "既有 discovery I/O 前后" 可被解释为整个方法前后（入口/出口），未唯一指定多 period POST 粒度。

### 5.2 Fixed plan 的 closure 机制

Fixed plan §6.3 把 CNInfo 的请求粒度唯一化为每个 supported fiscal-period POST：

- CNInfo 两个 supported periods 的 exact trace：
  `CP1, POST(period_1), CP2, CP3, POST(period_2), CP4`
- 不是仅方法入口/出口各一次
- checkpoint 抛出后不得 strict-parse/save partial rows、发下一 request、进入 selection 或 HEAD
- CNInfo checkpoint 必须位于现有 period transport `RuntimeError` wrapper 之外，或 typed cancel 在 generic wrapper 前 passthrough
- workflow 原有 discovery 方法前/后检查保留

**代码事实验证**：

CNInfo `list_report_candidates`（`cninfo_downloader.py:267-293`）按 `target_periods` 的 for 循环迭代：

```python
for period in query.target_periods:
    category = _PERIOD_TO_CATEGORY.get(period)
    ...
    try:
        announcements = self._query_announcements(...)
    except RuntimeError as exc:
        raise RuntimeError(...) from exc
    raw_by_period[period] = tuple(announcements)
```

每个 period 的 `_query_announcements` 内部有自己的分页循环（line 460-489，page_num 1..50），但 fixed plan 的 checkpoint 粒度在 period 级别（`_query_announcements` 调用前后），不在内部分页循环中。这是因为 plan 明确约定"不改变 CNInfo query、period iteration、分页、筛选、HTTP retry 或业务错误语义"。

**Exact trace 实现位置**：

```python
for period in query.target_periods:
    ...
    if cancellation_checkpoint is not None:
        cancellation_checkpoint()       # CP1, CP3
    try:
        announcements = self._query_announcements(...)
    except CnDownloadCancelledError:
        raise                            # typed cancel passthrough
    except RuntimeError as exc:
        raise RuntimeError(...) from exc # existing wrapper
    if cancellation_checkpoint is not None:
        cancellation_checkpoint()       # CP2, CP4
    raw_by_period[period] = tuple(announcements)
```

两个 supported periods 产生 exact trace `CP1, POST(p1), CP2, CP3, POST(p2), CP4`。

### 5.3 Test matrix closure

Fixed plan §8 的新增/收紧测试行：

| Test case | 覆盖场景 | 断言要点 |
|---|---|---|
| CNInfo checkpoint sequence | 两个 periods 正常返回 | exact `CP1, POST(p1), CP2, CP3, POST(p2), CP4`；POST params/order 与 baseline 相同 |
| CNInfo response cancel | p1 后 CP2 抛 typed cancel | exact `CP1, POST(p1), CP2`；不发 `POST(p2)`；cancel identity 不被 period RuntimeError wrapper 改写 |
| CNInfo before-next cancel | p1 后 CP2 返回、p2 前 CP3 抛 | exact `CP1, POST(p1), CP2, CP3`；只有一个 POST；无 partial publication |

### 5.4 结论

R10-PR-F03 已完整闭合。CNInfo 请求粒度唯一化为每个 supported fiscal-period POST 前/后，exact trace 明确，test contract 覆盖 normal、response-cancel、before-next-cancel 三个时点。

---

## 6. R10-PR-F02 zero-waiver 确认

Controller 在当前 baseline 运行了 focused coverage pre-check：

```text
dayu/fins/pipelines/cn_download_protocols.py  Stmts 40  Miss 0  Branch 0  Cover 100%
```

Fixed plan 保留四个 modified production file 各自 branch coverage `>=80%`。无 N/A waiver、omit、pragma、padding 或 coverage compatibility branch。`DS-R10-F02` 维持 `REJECTED-WITH-REASON`。**确认 zero-waiver 保留。**

---

## 7. 专项攻击区域逐项验证

### 7.1 functools.partial 对 keyword-only helper 的可实现性/类型

**攻击路径**：`_raise_if_cancelled` 所有参数为 keyword-only（`def _raise_if_cancelled(*, module: str, ...)` → None），`functools.partial` 能否正确绑定并产生 `Callable[[], None]`？

**验证**：

1. Python 3.11 的 `functools.partial(func, kw1=val1, kw2=val2)` 在 C 层面和 Python 层面都完全支持 keyword argument 绑定。当零参数调用 partial 对象时，已绑定 keyword args 原样传入 func。
2. Type-wise：`functools.partial` 的 `__call__` 签名为 `(*args: Any, **kwargs: Any) -> _T`。该签名是 `() -> None` 的有效 structural supertype——零参数调用始终合法。pyright 标准配置接受此赋值。
3. 若极端 pyright 配置报类型不匹配，等价 `lambda: _raise_if_cancelled(module=..., ticker=..., document_id="", cancel_checker=cancel_checker)` 语义完全相同，不影响 owner map、identity、cause chain 等核心合同。
4. 方案不依赖任何 ambient state、mutable setter 或 dynamic dispatch。

**结论**：可实现，类型安全，有零成本替代方案。**无 finding。**

### 7.2 Checkpoint 构造与 identity

**攻击路径**：checkpoint 对象是否在整个 discovery 调用中保持唯一 identity？是否存在构造时捕获 stale state 的风险？

**验证**：

1. workflow 中：`checkpoint = functools.partial(_raise_if_cancelled, module=module, ticker=normalized_ticker, document_id="", cancel_checker=cancel_checker)` 只执行一次。同一对象传入 `discovery.list_report_candidates(query, profile, cancellation_checkpoint=checkpoint)`。
2. 对象 identity：`checkpoint is checkpoint` 恒为 True。test 可断言 `CP1 is CP2 is CP3`。
3. `cancel_checker` 在 partial 中按引用捕获——每次调用 checkpoint 时，`_raise_if_cancelled` 都会调用当前 raw checker 的最新状态。无 stale state 风险。
4. `module`、`ticker`、`document_id` 在 partial 构造时绑定，这些是日志标识，在整个 discovery 调用期间不变。

**结论**：identity 保证成立。**无 finding。**

### 7.3 HKEX 每个真实 request 前后 exact ordering

**攻击路径**：fixed plan 的 `CPn, GET(r), CPn+1` ordering 在 `_http_get_json` retry/backoff/throttle 下是否 conservable？

**验证**：

1. Cumulative loop 中 checkpoint 紧邻 `_http_get_json(...)` 调用前、且仅在 helper 成功返回后再次调用。不进入 retry 内部。
2. `_http_get_json` 内部重试（line 449-461 of hkexnews_downloader.py）保持不变。retry exhaustion 以 RuntimeError 终止，不产生成功响应，因而不伪造 after-response checkpoint。
3. 单轮 exact trace：`CP1, _http_get_json(rowRange=100)成功, CP2`
4. 多轮 exact trace：`CP1, GET(100), CP2, CP3, GET(200), CP4, ...`——这里 `GET(n)` 指一次成功的 cumulative semantic request，包含内部可能的重试。
5. Per-language isolation：每个 language 从 100 开始独立的 cumulative 循环。language 间不共享 range/count。

**结论**：ordering 精确且 conservable。**无 finding。**

### 7.4 CNInfo 每个真实 request 前后 exact ordering

**攻击路径**：CNInfo 的 `_query_announcements` 内部有分页循环（多页 POST），若 checkpoint 在 per-period 级别而非 per-page 级别，取消响应窗口是否过大？

**验证**：

1. Fixed plan §6.3 明确 trace：`CP1, POST(p1), CP2, CP3, POST(p2), CP4`。"POST(p1)" 指一个 fiscal period 的完整 `_query_announcements` 调用，包含内部可能的多页 POST。
2. Plan §6.3 明确"不改变 CNInfo query、period iteration、分页、筛选、HTTP retry 或业务错误语义"。在 per-page 级别添加 checkpoint 会改变分页语义并引入 HKEX 式的取消状态机到 CNInfo——这是 plan 明确禁止的。
3. 最大取消响应窗口 = 一个 period 全部分页完成的时间（最多 50 页 × retry × timeout）。这是 CNInfo 现有分页实现的固有特性，不是 checkpoint seam 的设计缺陷。
4. 若需要在 period 内部中断分页，属于未来独立的 CNInfo pagination redesign，不在 R10 scope 内。

**结论**：ordering 在 per-period 级别正确且与 scope 边界一致。**无 finding。**

### 7.5 Exception wrapper precedence

**攻击路径**：HKEX `list_report_candidates` 的 exception handler 顺序是否确保 typed cancel/provider error 不被 generic RuntimeError 抹平？

**验证**：

Fixed plan §5.3 的 precedence：

```text
except CnDownloadCancelledError: raise      ← 第1优先级
except HkexnewsProviderProtocolError: raise ← 第2优先级
except RuntimeError as exc:                  ← 第3优先级，generic wrapper
```

- `CnDownloadCancelledError` 和 `HkexnewsProviderProtocolError` 都是 `Exception` 的子类，不是 `RuntimeError` 的子类（`CnDownloadCancelledError` 在 `cn_download_models.py` 中定义，需确认其基类）。

**代码事实**：`CnDownloadCancelledError` 定义在 `cn_download_models.py`。根据 `cn_download_workflow.py:21` 的 import：

```python
from dayu.fins.pipelines.cn_download_models import (
    CnDownloadCancelledError,
    ...
)
```

需要确认 `CnDownloadCancelledError` 的基类。从 `cn_download_workflow.py:459` 的 `raise CnDownloadCancelledError("操作已被取消")` 来看，它必须是 `Exception` 的子类。若它继承自 `RuntimeError`，则 `except CnDownloadCancelledError: raise` 必须在 `except RuntimeError` 之前才能生效——而这正是 plan 要求的顺序。若它继承自 `Exception` 但不继承 `RuntimeError`，则顺序无关紧要。

无论哪种情况，plan 的显式 `except CnDownloadCancelledError: raise` 放在 generic `except RuntimeError` 之前都保证 typed cancel 不被抹平。

**CNInfo wrapper 同样受保护**：plan §5.3 要求 CNInfo 的 checkpoint 调用位于现有 period `RuntimeError` wrapper 之外，或用 `except CnDownloadCancelledError: raise` 放在 generic wrapper 之前。

**结论**：precedence 正确且完备。**无 finding。**

### 7.6 Caller cancel identity

**攻击路径**：caller 预构造的 `CnDownloadCancelledError` 对象 identity 是否跨 protocol/HKEX generic wrapper 保留？

**验证**（完整 trace 已在 §4.3 中详述）：

1. raw checker 抛 `expected_cancel = CnDownloadCancelledError(...)`
2. `_is_cancel_requested` 中 `isinstance(exc, CnDownloadCancelledError)` → True → `raise`（bare raise，保留原 traceback 和对象 identity）
3. 异常穿透 `_raise_if_cancelled`、partial wrapper、protocol transport
4. HKEX `except CnDownloadCancelledError: raise`（bare raise again）
5. Test：`exc.value is expected_cancel` → `True`（`is` 操作符验证对象 identity）

**Python `raise` 语义确认**：在 `except` 块中使用 bare `raise` 会重新抛出当前异常，保留原始 traceback 和对象 identity（PEP 3134 / Python 3.11 docs）。两个 bare `raise`（分别在 `_is_cancel_requested` 和 HKEX handler）都不会改变对象 identity。

**结论**：caller cancel identity 完整保留。**无 finding。**

### 7.7 Non-cancel cause chain

**攻击路径**：raw checker 的非取消异常是否正确保留为 workflow RuntimeError 的 direct cause？若再经 HKEX generic wrapper，两层 cause chain 是否完整？

**验证**（完整 trace 已在 §4.3 中详述）：

1. raw checker 抛非取消异常（如 `ValueError("db error")`）
2. `_is_cancel_requested` → `raise RuntimeError("取消检查失败: ...") from exc`
3. `workflow_rte.__cause__ is original_error` → True
4. 若穿透 HKEX generic wrapper → `raise RuntimeError("披露易公告分类查询失败...") from workflow_rte`
5. `hkex_wrapper.__cause__ is workflow_rte` 且 `workflow_rte.__cause__ is original_error` → True

**关键设计点**：`_raise_if_cancelled` 的 non-cancel failure 语义不属于 provider protocol failure。Plan §5.3 明确指出"raw checker 自身的非取消故障只由 workflow 既有语义包装为带直接 cause 的 RuntimeError；provider 不把它归类为 provider protocol failure"。两层 cause chain 的 test 只适用于"若经过 HKEX generic wrapper"场景——CNInfo 场景（checkpoint 在 period wrapper 之外）只有单层 cause chain。

**结论**：non-cancel cause chain 完整。**无 finding。**

### 7.8 Partial-no-publication

**攻击路径**：取消/失败后是否任何 partial rows/candidates/HEAD 均不发布？

**验证**：

Fixed plan §6.2 和 §8 覆盖所有 partial-no-publication 场景：

| 场景 | 保护机制 |
|---|---|
| cancel before first GET | CP1 抛 → zero HTTP，无 rows/candidates/HEAD |
| cancel after response | `CP2` 抛 → 不 strict-parse/publish partial，不发下一 range，无 HEAD |
| cancel before later round | `CP3` 抛 → 只有第一 GET，无 partial complete/HEAD |
| cancel after final round | 即使响应完整也不 parse/return candidates，取消优先 |
| HTTP initial failure | retry exhaustion → 既有 RuntimeError，无 candidates |
| HTTP later failure | 首轮 true，后续 retry exhaustion → 不返回首轮 partial，无 HEAD |
| CNInfo response cancel | p1 POST 后 CP2 抛 → 不发 `POST(p2)`，无 partial candidates/HEAD |
| CNInfo before-next cancel | p2 前 CP3 抛 → 只有一个 POST，无 partial publication |

核心机制：
- 每轮 `latest_rows = snapshot.rows`（替换，不使用 extend/+=）
- 只有最终 complete snapshot 进入 `_parse_announcement`
- checkpoint 抛出立即传播，跳过后续 parse/save/HEAD

**结论**：所有取消/失败路径均无 partial publication。**无 finding。**

### 7.9 Strict parser

**攻击路径**：parser 类型检查是否有遗漏的 coercion 路径或 Python `bool`/`int` 陷阱？

**验证**：

Fixed plan §5.2 的 parser contract（逐项对照）：

1. top-level 必须是 dict；5 个 required fields（`hasNextRow`、`rowRange`、`loadedRecord`、`recordCnt`、`result`）
2. `hasNextRow` 只接受 JSON bool；拒绝 `"true"`、`0/1`、null
3. `rowRange`、`loadedRecord`、`recordCnt` 只接受 JSON int 且非负；**先显式拒绝 bool**（Python `isinstance(True, int)` → True 陷阱）
4. `result` 只接受字符串化 JSON array；拒绝空字符串、malformed JSON、非 list、非 object row
5. `response_row_range == requested_row_range`
6. `loadedRecord == len(rows)`、`loadedRecord <= recordCnt`、`loadedRecord <= requested_row_range`
7. `hasNextRow=true` → `loadedRecord < recordCnt`；`hasNextRow=false` → `loadedRecord == recordCnt == len(rows)`

覆盖全部类型错误（string/int/float/null/list/dict）、负值、矛盾、missing fields。明确删除 `_coerce_non_negative_int`（通用 coercion）、`_extract_title_search_total_count`（8 个 generic aliases）、integral float coercion 路径。

**结论**：parser 完备、无 coercion 漏洞。**无 finding。**

### 7.10 Progress detection

**攻击路径**：no-progress 检测是否会拒绝合法 terminal snapshot？是否会允许无限 doubling？

**验证**：

Fixed plan §6.2 的四层防护：

1. **response range equality**（§5.2 item 5）：若 provider clamp range，第一轮就 typed fail
2. **loadedRecord monotonic**（§6.2 bullet 3）：`hasNextRow=true` 连续响应间 `loadedRecord` 必须严格增加
3. **no-progress typed fail**（§6.2 bullet 3 补充）：range/recordCnt 增长但 loaded 不变 → typed fail
4. **terminal precedence**（§6.2 bullet 4）：最新自洽 terminal snapshot 覆盖跨轮 progress 比较

最坏情况分析：provider 持续 `hasNextRow=true` 且 `loadedRecord` 每次只增加 1 条。理论最大轮次 = 初始 `recordCnt` + 增长量。这是一个大但有限的值。若 provider 返回 `hasNextRow=true` 而 loaded 不增加 → 第二轮即 typed fail。

合法 terminal：round 1 `loaded=100, count=150, true` → round 2 `loaded=100, count=100, false`（数据变化）。Terminal precedence 确保接受最新自洽 snapshot，不检查跨轮 progress。

**结论**：有限失败保证成立，不拒绝合法 terminal。**无 finding。**

### 7.11 Terminal / final-only behavior

**攻击路径**：partial rows 是否可能通过 extend/append/dedup 进入 selection？

**验证**：

Fixed plan §6.2：
- "每轮赋值 `latest_rows = snapshot.rows`，不使用 `extend`/`+=`"——语义赋值替换
- "只有 complete 后才把 final rows 交给 `_parse_announcement(...)`、stock match 与 selection"——conditional publication
- "不比较 row identity、不要求旧 rows 是新 rows 的 exact prefix，也不在本地 dedup"——唯一权威是最后完整 snapshot
- "相同稳定 query 下新公告可插入或记录可撤回；唯一权威结果是最后一次完整 snapshot"——承认 provider 数据可变的现实

**结论**：terminal/final-only 保护完备。**无 finding。**

### 7.12 Query invariance

**攻击路径**：循环中 query params 是否可能漂移（date、sort、category、filter）？

**验证**：

Fixed plan §6.1：
- 每个 language/category 先构造一次 immutable base params
- 每轮只从 base params 派生新 dict 并写入 `rowRange=str(current_row_range)`
- 不得在循环中重新推断或改变 language、stock、category、sort、from/to date、filter
- Test：每轮 params 去除 `rowRange` 后 dict exact equality

**结论**：query invariance 保证成立。**无 finding。**

### 7.13 Allowlist 完整性

**攻击路径**：allowlist 是否有遗漏的 production/test/README 路径？

**验证**：

Fixed plan §4.2 allowlist vs. 实现需要：

| 需要 | 对应 allowlist 文件 | 状态 |
|---|---|---|
| HKEX cumulative protocol owner | `dayu/fins/downloaders/hkexnews_downloader.py` | ✓ |
| Protocol 签名 | `dayu/fins/pipelines/cn_download_protocols.py` | ✓ |
| Workflow checkpoint 构造 | `dayu/fins/pipelines/cn_download_workflow.py` | ✓ |
| CNInfo 签名 + checkpoint | `dayu/fins/downloaders/cninfo_downloader.py` | ✓ |
| HKEX owner tests | `tests/fins/test_hkexnews_downloader.py` | ✓ |
| Workflow tests | `tests/fins/test_cn_download_workflow.py` | ✓ |
| CNInfo tests | `tests/fins/test_cninfo_downloader.py` | ✓ |
| Pipeline test doubles (2 fakes) | `tests/fins/test_cn_pipeline.py` | ✓ |
| Runtime test doubles (1 fake) | `tests/fins/test_cn_download_runtime.py` | ✓ |
| Captured fixture | `tests/fins/fixtures/hkexnews/title_search_protocol_shape.json` | ✓ |
| Fins README | `dayu/fins/README.md` | ✓ |
| Test README | `tests/README.md` | ✓ |

Test double 签名核对：

| Fake | 文件 | 行号 | 当前签名 | 迁移需求 |
|---|---|---|---|---|
| `_FakeDiscoveryClient` | `test_cn_download_workflow.py` | 278 | `(self, query, profile)` | 加 keyword-only `cancellation_checkpoint` |
| `_FailingDownloadDiscoveryClient` | `test_cn_download_workflow.py` | 322 | 继承 `_FakeDiscoveryClient` | 隐式覆盖 |
| `_PipelineDownloadFakeDiscoveryClient` | `test_cn_pipeline.py` | 58 | `(self, query, profile)` | 加 keyword-only `cancellation_checkpoint` |
| `_PipelineDownloadFakeHkDiscoveryClient` | `test_cn_pipeline.py` | 144 | `(self, query, profile)` | 加 keyword-only `cancellation_checkpoint` |
| `_RuntimeFakeDiscoveryClient` | `test_cn_download_runtime.py` | 109 | `(self, query, profile)` | 加 keyword-only `cancellation_checkpoint` |

**结论**：allowlist 完整且闭合。**无 finding。**

### 7.14 Coverage 可执行性

Fixed plan §10.3 的逐文件 coverage 命令完全可执行。Controller 已在 baseline pre-check：protocol 文件 `Stmts 40 Miss 0 Branch 0 Cover 100%`。四个 modified production file 各自需要 `>=80%` branch coverage，无 N/A waiver/padding。**无 finding。**

### 7.15 Smoke 计划

Fixed plan §9.3 的 non-destructive smoke 设计完整：opt-in、只读 GET、记录 query/rounds/field summary/raw hashes/manifest path、控制请求间隔。外部 endpoint 不可达只记录环境限制，不豁免 local deterministic gates。endpoint 可达却证明 cap/clamp/stall → stop（§12 condition 4）。**无 finding。**

### 7.16 Security retention

Fixed plan §11.2 明确保留：HTTP timeout、retry 上限、throttle、公开 HTTPS endpoint、PDF magic/size 校验、stock matching、error 不含 raw body/secret/local path。不新增 permission schema/auth profile/DNS/egress framework。captured fixture 只用公开 GET，不保存 cookie/auth/header。**无 finding。**

### 7.17 Deferred / forbidden scope

Fixed plan §10.6 对最终 diff 执行 deferred scope audit（changed hunks only）。明确禁止：Issue 142/151/175/177/178、R11/R12、Web/WeChat/render、Topic 8/9、authorization/auth profile、storage transaction、direct-stream terminal。**无 finding。**

---

## 8. Architecture boundary review

| Boundary | Owner | Consumer | 验证 |
|---|---|---|---|
| HKEX official response parse、cumulative state、progress、complete/error decision | `hkexnews_downloader.py` | CN/HK workflow（只消费 candidates 或 typed failure） | ✓ 不泄漏到 selection/workflow/storage |
| raw cancel_checker bool/typed cancel/non-cancel 解释 | workflow `_raise_if_cancelled` | protocol（只运输 no-arg checkpoint） | ✓ provider 不解释 raw bool |
| checkpoint 对象生命周期与 identity | workflow（构造一次） | protocol（原样运输） | ✓ 同一对象贯穿 |
| checkpoint transport signature | `cn_download_protocols.py` | HKEX/CNInfo downloader（只调用） | ✓ 签名 `Callable[[], None] \| None` |
| provider I/O boundary checkpoint ordering | HKEX/CNInfo downloader | workflow 不规定 provider 内部 I/O 次序 | ✓ 每个 semantic request 前/后 |
| raw announcement → 财报 candidate | `cn_report_selection.py` | 不变 | ✓ 不改变 |
| HTTP retry/throttle/timeout | 既有 HKEX/CNInfo HTTP helper | 不变 | ✓ 不改变 |
| README | 对应 README | 不产生业务事实 | ✓ |

**结论**：架构边界清晰，无跨层泄漏，无双向依赖。

---

## 9. Best-practice review

- **Testability**：全部 deterministic tests 使用 `httpx.MockTransport`，checkpoint 通过 direct parameter injection。不做 ambient context/mutable setter/constructor-only 注入。
- **Maintainability**：HKEX cumulative protocol 只留在 provider-private model/state machine。workflow 只把既有语义绑定为 no-arg checkpoint。零 generic abstraction。
- **Observability**：取消日志由 `_raise_if_cancelled` 统一输出。provider protocol error 消息包含业务可读 context。smoke manifest 记录每轮 fields/hashes。
- **Failure handling**：三层防护——checkpoint cancel → typed error propagation；provider protocol contradiction → typed error；HTTP failure → existing retry + RuntimeError。
- **Minimal dependency exposure**：shared protocol 只增加一个 keyword-only 参数。CNInfo 同步接受同一签名但不获得 HKEX state machine。

**结论**：符合项目最佳实践。

---

## 10. Optimal-solution review

Fixed plan 的方案（workflow-owned no-arg checkpoint + protocol transport + provider I/O boundary call）是该约束空间下的最小可行解：

- **不能只改 downloader**：downloader 内的多轮同步请求无法获得 workflow 的 raw cancel_checker（当前 `list_report_candidates` 不传该参数）
- **不能引入 ambient context**：`ContextVar`/thread-local/global variable 违反编码约束
- **不能引入 generic framework**：callback/factory/cancellation framework 违反 non-goals
- **不能把 bool 解释下沉**：多个 provider 各自解释 bool 造成 owner 分裂，是 F01 的根因

方案比初轮 plan（raw `Callable[[], bool]` transport）更优，因为：
- 取消解释 owner 唯一（workflow `_raise_if_cancelled`）
- provider 不复制工作流 helper
- 不需要 shared cancellation module

**结论**：方案是最优路径。

---

## 11. Overengineering review

Fixed plan 增加的内容全部是 closing F01/F03 的最小必要变更：
- `cancellation_checkpoint` keyword-only 参数：closes F01（取消 owner 分裂）
- `functools.partial` 绑定：closes F01（无新 helper/framework）
- per-period CNInfo checkpoint granularity：closes F03（请求粒度唯一化）
- test matrix 扩展：closes 两个 finding 的 verification contract

未增加：generic pagination framework、第二 completeness owner、新配置项、新 public schema、callback/factory abstraction、speculative watchdog/hard cap/date recursion/generic pagination/compatibility。

**结论**：无过度设计。

---

## 12. Overcoupling review

- HKEX state machine 与 CNInfo 独立：HKEX 拥有 cumulative state，CNInfo 只调用同一 checkpoint at period boundary，不共享 state
- Workflow 与 provider 通过 protocol 解耦：workflow 不 import HKEX/CNInfo helper
- Test doubles 通过 structural typing 迁移：加一个 keyword-only 参数，不引入 concrete dependency
- Exception 类型不跨层耦合：`CnDownloadCancelledError` 在 protocol 两侧都有显式 passthrough handler

**结论**：无过度耦合。

---

## 13. Open questions

无。所有关键设计决策已由 Controller adjudication 裁决并写入 fixed plan。`functools.partial` 的类型安全性和 CNInfo pagination 内部的取消窗口已在 §7.1 和 §7.4 中验证，属于 plan scope boundary 内的正确设计决策。

## 14. Residual risks

| Risk | Plan 处理 | Destination |
|---|---|---|
| 外部 HKEX endpoint DNS/网络/challenge/限流不可用 | §9.3 / §12：记录环境限制，local gates 仍必须通过 | R10 completion report |
| Provider 可能未来引入 rowRange hard cap/clamp/stall | §12 stop condition 4：停止，记录 evidence-driven residual | 未来独立 HKEX provider WU |
| `functools.partial` 在极端 pyright 配置下的类型兼容 | §7.1 验证通过；等价 lambda 替代方案可用 | implementation agent 自行选择 |
| CNInfo per-page 取消不可观察 | §7.4 验证：属于 CNInfo 分页 redesign scope，当前 per-period 粒度是正确 scope 边界 | 未来 CNInfo pagination WU |
| Live smoke `>100` query 在当前市场条件下可能不存在 | §9.3/§12 分流：记录 query 选择依据或环境限制；local fixture gate 不可豁免 | R10 completion report |

## 15. New material finding 数

**0。**

本次完整 re-review 对所有 attack areas（functools.partial 类型/可实现性、checkpoint 构造与 identity、HKEX/CNInfo exact ordering、exception wrapper precedence、caller cancel identity、non-cancel cause chain、partial-no-publication、strict parser、progress、terminal/final-only、query invariance、allowlist、coverage、smoke、security、deferred）逐项验证，均未发现新的 material finding。

初轮 DS-R10-F01/F03 已在 fixed plan 中完整闭合（见 §4、§5）。F02 zero-waiver 保留（见 §6）。Fixed plan 的 698 lines、SHA-256 `fe180230f5d6c43f250af4cd9ffcff705ab309b9f875c9543215e3ca086a0f9a` 是 code-generation-ready 的。

## 16. Final plan review conclusion

**Verdict：`PASS`**

### 通过理由

1. **Target lock 一致**：SHA-256 `fe180230...`，698 lines。全部 9 个 production/test source locks 无 drift。
2. **R10-PR-F01 closure**：取消解释 owner 唯一（workflow `_raise_if_cancelled`），protocol 只运输 `Callable[[], None] | None`，provider 只在 I/O boundary 调用。Bool true mapping、caller typed cancel identity、non-cancel cause chain、checkpoint normal return 全覆盖。
3. **R10-PR-F03 closure**：CNInfo 请求粒度唯一化为每个 supported fiscal-period POST 前/后。Exact trace 明确（`CP1, POST(p1), CP2, CP3, POST(p2), CP4`）。Normal、response-cancel、before-next-cancel 全覆盖。
4. **F02 zero-waiver**：`cn_download_protocols.py` baseline `Stmts 40 Miss 0 Branch 0 Cover 100%`，无 N/A waiver/padding。
5. **全 attack area 零 finding**：functools.partial、checkpoint identity、HKEX/CNInfo ordering、exception precedence、caller cancel identity、non-cancel cause chain、partial-no-publication、strict parser、progress、terminal/final-only、query invariance、allowlist、coverage、smoke、security、deferred 全部验证通过。
6. **架构边界清晰**：无跨层泄漏、无双向依赖、无过度设计/过度耦合。
7. **No forbidden patterns**：无 hard cap、date recursion、generic pagination、compatibility、speculative watchdog、Issue/R11/R12/Web/WeChat/render/Topic 8/9/auth。
8. **Validation matrix 可执行**：所有命令有具体路径和预期结果。

### 下一 gate

按 §13 deferred gates：当前停在 `READY_FOR_CONTROLLER_VALIDATION`（Codex fix 完成 + Controller fix validation 完成）。本 re-review 完成双路 re-review 的 AgentDS 路径。下一 gate 应是 AgentMiMo 完成其 fixed-plan re-review 后，由 Controller 进行 final finding adjudication（如有），然后 accepted plan commit，最后 R10-S1 implementation。

---

## 17. Review integrity statement

- 本 review 完整读取 target plan (698 lines)、全部 5 个 prior review/adjudication/fix/validation artifacts（初轮 DS/MiMo review、Controller adjudication、Codex fix、Controller fix validation）、全部 9 个 production/test source files，以及 `AGENTS.md` 和 `docs/fins/design.md` §8。
- 所有 SHA-256 均重新计算并与 plan lock 核对一致。
- 未修改 target、control、fix、code、tests、README、design 或任何其它文件。
- 未 stage、commit、push、PR。
- 所有验证结论均附直接代码证据（文件名、行号、签名）。
- 未发现新的 material finding。
