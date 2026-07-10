# WU-SEMANTIC-OWNERSHIP-01 P3-G Aggregate Deepreview Controller Adjudication

## 结论

P3-G accepted，无 aggregate fix gate。

两路 aggregate deepreview 均返回 PASS，未发现 material finding：

- `docs/reviews/wu-semantic-ownership-01-p3-g-aggregate-deepreview-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-p3-g-aggregate-deepreview-ds.md`

## Controller 裁决

本轮 accepted findings：0。

P3-G 关闭的 source findings：

- AgentDS 7：SEC form normalization drift。
- AgentDS 8：`fiscal_period` / `form_type` / `quality` / `data_quality` naked strings。
- AgentMiMo BI-1：CN/HK downloader-owned report filtering and fiscal inference。
- AgentMiMo SS-10：SEC download rejection registry hidden dict shape。
- AgentCodex 11：XBRL facts result `total` recomputed by read runtime。

## 验证依据

Aggregate validation artifact：

- `docs/reviews/wu-semantic-ownership-01-p3-g-aggregate-validation.md`

验证结果：

- Aggregate tests：`174 passed, 3 warnings`
- Pyright：`0 errors`
- `git diff --check`：pass
- Source scans：
  - `form_type_utils` 零命中。
  - `CnFiscalPeriod = Literal["FY"...]` 零命中。
  - Rejection registry public contract 无 `dict[str, dict[str, str]]` 残留；非 registry nested dict 命中已分类为无关。
  - `"total": len(deduped_facts)` 零命中。

## Residual Risk

- S4 `xbrl_result_contract.py` coverage 为 `80%`，刚好满足 gate；后续若扩展 validator 分支，应补更细测试。
- 旧 workspace 中坏 `_download_rejections.json` 会 fail closed；本 WU 按新 contract 起库，不做兼容迁移。
- `DocumentSummary.form_type` 保持 `Optional[str]`，用于承载 SEC/CN/HK/material forms；SEC-only 校验已落在更窄 producer/decode 边界。

## 下一步

提交 P3-G aggregate artifacts。P3-G 不关闭 umbrella WU；controller 继续进入下一 sub WU / 后续全仓 deepreview 轮次。
