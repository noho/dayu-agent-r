# WU-SEMANTIC-OWNERSHIP-01 / R10 plan entry Controller validation

## 1. Gate 与动机判断

- 当前是同一 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的内部 remediation sub-WU R10，不是新 WU、
  issue 或 feature。
- 用户对 umbrella remediation continuation 的 goal confirmation 已完成；R09 completion commit
  `1c2585275f4134d8456a3fda2d84464e4e52c9d7` 成功后，顺序依赖允许进入 R10 独立 plan gate。
- Controller verdict：`READY_FOR_AGENTCODEX_PLAN`，不是 plan acceptance 或 implementation authorization。

动机基于直接代码证据成立：

1. `docs/fins/design.md` 明确规定 HKEX title search 使用官方 cumulative `rowRange`；只有
   `hasNextRow=false`、`loadedRecord == recordCnt == len(rows)` 才能声明 complete。
2. 当前 `HkexnewsDiscoveryClient._query_period_announcements` 每个 language 只请求一次固定
   `rowRange="100"`。
3. 当前 `_HkexnewsRowsPage` 只有 `rows` 与猜测性的 `total_count`；
   `_extract_title_search_total_count` 扫描八个 generic total aliases。
4. 当前 `_raise_if_title_search_truncated` 把 `row_count >= 100` 且 generic total 缺失当作不可证明
   complete，并没有读取官方 `hasNextRow`、`loadedRecord`、`recordCnt` 或续取累计 snapshot。
5. 当前 tests 固化单页 100 / generic total fail-closed contract；这与已裁决设计真源直接冲突，必须让
   tests 跟 owner contract 迁移，不能在下游补偿。

因此这不是可忽略的小优化，而是 provider discovery completeness 的 owner-level correctness 修复。

## 2. Source locks

- branch：`phaseflow/host-issues-control`。
- HEAD：`1c2585275f4134d8456a3fda2d84464e4e52c9d7`。
- staged tree：empty。
- 当前 working tree 只含 Controller 对
  `docs/host/issues-implementation-control.md` 的 R10 gate transition；Agent 不得修改或覆盖。

| Source | Lines | SHA-256 |
|---|---:|---|
| `dayu/fins/downloaders/hkexnews_downloader.py` | 1065 | `8c7c1a3b8e1aebc91ec82756754eb7894d6748471b69ce164a9798b260f5eb31` |
| `tests/fins/test_hkexnews_downloader.py` | 1213 | `d98266b8016e47a5ba4f77d680196b373933f71b184e559b2b483bd76f9de1d9` |
| `tests/fins/test_cn_download_workflow.py` | 1660 | `c2d86d4778002d904df40ab0c5ac67660683e76ea989a692d917650aa09b1e1f` |
| `docs/fins/design.md` | 123 | `97033cf1330e6018df2cf7bf676fa550c24e3e99beb99792f718eac31727abdd` |
| umbrella remediation plan | 1269 | `30c27562ece3360c7d25e55a6f2b0b189999d35cca8004e83d42de3c8ccda838` |

## 3. Plan owner、scope 与硬边界

### Owner

`dayu/fins/downloaders/hkexnews_downloader.py` 是 HKEX provider exact cumulative protocol 与
completeness proof 的唯一 owner。只有当 typed response model 确需被现有 CN/HK workflow 直接复用时，
plan 才可考虑已有 `dayu/fins/pipelines/cn_download_models.py`；默认应保持 provider-private typed model。

### Required plan outcomes

- 初始 `rowRange=100`。
- 每轮严格解析官方 `hasNextRow`、`loadedRecord`、`recordCnt` 与 rows；缺失、类型错误、负值、布尔伪装
  或矛盾必须 typed fail。
- `hasNextRow=true` 时保持全部 query/sort/date/filter 不变，仅把 range 扩为
  `max(current_range * 2, recordCnt)`。
- 每轮是 cumulative snapshot，只保留最新 rows，禁止 page append。
- record count 变大时使用最新 provider facts；range/loaded/rows 必须形成可证明进展，否则 typed fail，
  避免无限循环。
- 只有 `hasNextRow=false` 且 `loadedRecord == recordCnt == len(rows)` 才返回 complete。
- 取消在每轮前后检查，不把 partial 当 complete。
- 删除 `_raise_if_title_search_truncated`、generic total alias guessing、100 条即失败语义。

### Non-goals / forbidden design

- 不增加 fixed hard cap、日期递归、page append/dedup 补偿、下游 completeness checker 或 generic pagination
  framework。
- 不修改 R09 stream owner、R06 transaction owner、storage、Service、CLI、Host、Engine、Web/WeChat/render。
- 不实施 Issue 142、151、175、177、178、Topic 8/9 或统一 tool authorization。
- 不为旧 total schema/tests 添加兼容分支、loose parser 或 fallback。

## 4. Plan quality gates

AgentCodex plan 必须是 code-generation-ready 的单 slice闭环，并至少给出：

1. exact allowed product/test/README paths 与 source locks；
2. official field typed model、parser、state/progress invariant、next-range formula 和 error type/message owner；
3. query invariance 与 cumulative snapshot behavior 的可执行 tests；
4. 100 exact complete、>100 两/多轮、overlapping cumulative prefix、不重复、recordCnt增长、字段缺失/类型
   错误/矛盾、无进展、取消前后、HTTP/error propagation；
5. focused workflow regression、full Fins、full pyright、Ruff、single-file coverage `>=80%`、diff/source scans；
6. README trigger decision；
7. non-destructive official endpoint smoke 或可审计 captured fixture 的具体 owner/生成/读取方式；外部端点不可用
   只可记录环境限制，不能替代本地 protocol fixture gate；
8. security retention 与 deferred/no-touch scans；
9. stop conditions：若官方实测出现 rowRange 无法解决的 cap，停止并记录 evidence-driven residual，不自行添加
   第二分页机制。

## 5. Authorized output

本 gate 只授权 AgentCodex 新增：

`docs/host/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan.md`

不得修改代码、测试、README、design、control、prior artifacts，不得 stage、commit、push 或进入
implementation。完成后由 Controller validation，再进入 AgentMiMo / AgentDS 并发 plan review。
