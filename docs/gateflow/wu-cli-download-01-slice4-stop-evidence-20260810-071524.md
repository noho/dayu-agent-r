# WU-CLI-DOWNLOAD-01 Slice 4 Implementation Stop Evidence

## 1. 状态与结论

- Work unit：`WU-CLI-DOWNLOAD-01`
- Slice：Slice 4 — Storage concurrency 与 integrity repair
- Gate：implementation
- Baseline HEAD：`93eb073e597899b3c25234eaf50923ba1d6c0219`
- Evidence timestamp：`2026-08-10 07:15:24 +0800`
- Decision：`STOP / plan amendment required`
- Rollback：按implementation stop condition回滚本轮全部production/test试改；只保留本证据文档。
- 禁止动作：未commit、未push、未创建PR，未修改README、base plan、旧evidence/review artifact、Oracle/registry、真实CLI/provider、Host/Engine或PR190。

动机成立，且新证据表明当前allowlist不足以实现DL-F10的真实pipeline repair。这不是通过修改filing workflow、存储classification或测试fixture可以局部解决的问题；root cause是SEC/CN顶层workflow在任一filing Phase A之前已发布company-only ticker batch，而storage的strict complete-tree validator会拒绝该batch复制的已损坏source。

## 2. 触发过程

本轮先按已接受plan完成owner/implementer inventory，并在当时的试改上得到以下中间验证：

- Slice 4 affected union：`585 passed, 3 warnings`。
- full pyright：`0 errors, 0 warnings, 0 informations`。
- deterministic thread/process/race subset：10轮，每轮`7 passed`，无sleep。
- 临时AST gate：PASS，仅声称syntax-level evidence。

但上述affected union尚未包含“真实公开pipeline从已损坏published source启动repair”的owner用例。补上该用例后，以下命令稳定失败：

```bash
source .venv/bin/activate
pytest -q \
  tests/fins/test_sec_pipeline_download.py::test_sec_digest_corruption_repairs_unconditionally_with_overwrite_false
```

用例使用真实storage public contract创建完整SEC source，然后把published primary file改为同字节数的不同内容，因此meta结构、size、manifest与identity均合法，只有物理digest mismatch。随后调用真实`SecPipeline.download(ticker="AAPL", overwrite=False, ...)`。预期是Phase A得到`REPAIR_REQUIRED`并强制unconditional replacement；实际在进入单filing workflow前失败。

失败主因：

```text
ValueError:
source file.sha256 与 physical file 不一致:
fil_0000000000-25-000001/sample-10k.htm
```

发生位置是company batch的`commit_batch`，不是filing Phase B。

## 3. 直接call-chain证据

### 3.1 SEC

```text
SecPipeline.download
  -> collect_download_result_from_events
  -> SecPipeline.download_stream
  -> sec_download_workflow.run_download_stream_impl
       -> begin_batch(normalized_ticker)          # line 457
       -> _upsert_company_meta(..., batch=...)    # lines 459-465
       -> commit_batch(company_batch)             # line 469
            -> _validate_complete_source_tree     # storage line 605
                 -> validate filing/material tree # storage lines 716-717
                 -> digest compare                # storage lines 976-981
       -> _filter_filings / _download_single_filing_stream  # 尚未到达
```

文件证据：

- `dayu/fins/pipelines/sec_download_workflow.py:457-469`：顶层workflow在filing selection/filing Phase A前开启并提交company-only batch。
- `dayu/fins/storage/_fs_storage_infra.py:603-605`：任何batch提交都先strict校验整个staging source tree。
- `dayu/fins/storage/_fs_storage_infra.py:716-717,950-981`：校验遍历filing/material并比对物理size/digest；company-only batch也不例外。

因此，当published target为`REPAIR_REQUIRED`时，`begin_batch`会复制该损坏tree，随后company-only commit必然在filing workflow获得修复机会前失败。

### 3.2 CN/HK对称风险

`dayu/fins/pipelines/cn_download_workflow.py:193-205`存在同构顺序：在单filing阶段机之前`begin_batch -> upsert company -> commit_batch`。同一storage strict validator会对已损坏CN/HK source产生相同拦截。这不是SEC特例。

## 4. Owner与allowlist裁决

该顺序的语义owner是：

- `dayu/fins/pipelines/sec_download_workflow.py`：SEC company publication、filing selection与single-filing dispatch顺序owner。
- `dayu/fins/pipelines/cn_download_workflow.py`：CN/HK company publication与single-filing dispatch顺序owner。

两者均不在base Slice 4 production allowlist，也不在当前amendment新增allowlist。`sec_pipeline.py` / `cn_pipeline.py`只是facade/composition owner；在其中复制或绕过workflow顺序会形成glue seam和第二套orchestration。

下列“修复”均不合法：

- 放宽`_validate_complete_source_tree`、只校验本轮改动target或允许未修复corruption随company batch重新publication：违反strict validator与stop condition。
- 在`sec_pipeline.py` / `cn_pipeline.py`重写顶层workflow、特判digest failure或捕获后重试：违反语义owner、禁止glue/fallback。
- 在company batch持锁期间执行provider/PDF/Docling repair：违反锁外I/O硬约束。
- 通过timeout、compat、fake capability或production timing hook规避：均被明确禁止。

因此命中以下stop conditions：

1. 正确owner不在production allowlist，需要扩scope。
2. 在当前allowlist内无法证明真实public pipeline repair call graph。
3. 继续实现只能放宽validator或引入下游补偿/glue，两者均被禁止。

## 5. Plan amendment必须裁决的问题

下一轮plan fix至少需要：

1. 显式决定是否将以下两个production owner加入Slice 4 allowlist：
   - `dayu/fins/pipelines/sec_download_workflow.py`
   - `dayu/fins/pipelines/cn_download_workflow.py`
2. 用单一owner顺序规范解决company publication与target repair的先后关系。合法方向必须保持：
   - 不在provider/PDF/Docling I/O期间持有writer。
   - selected corrupted target必须先获得Phase A/B repair机会，之前不得有必然被strict validator拒绝的ticker batch commit。
   - company-only/no-filing路径仍有清晰、唯一的durable company语义。
   - 不放宽complete-tree validator，不变更publication atomicity。
3. 枚举SEC在filing repair前的其它batch mutation，尤其是filtered 6-K rejected artifact路径。当同target source已损坏但当前候选又被过滤时，必须明确“source repair”与“rejected artifact持久化”哪个先发生，不得留给implementation自行猜测。
4. 在既有allowed tests中增加真实顶层pipeline用例：
   - SEC/CN分别从size/digest/missing physical corruption启动，`overwrite=False`成功repair，且production strict snapshot可读。
   - 证明company batch不再在repair Phase A之前因损坏tree失败。
   - no-filing、filtered/rejected、unselected-corruption的durable outcome和error owner。
   - 失败repair保留old bytes/meta/manifest/company事实。

## 6. 回滚边界

本证据产出后，回滚自baseline HEAD之后本轮引入的所有production/test变更，包括临时AST脚本和新建`source_integrity.py`。不保留部分implementation，避免将未通过真实pipeline repair的中间状态交给下一gate。

回滚后预期workspace只有本文档一个未跟踪文件；HEAD保持`93eb073e597899b3c25234eaf50923ba1d6c0219`。下一入口是Slice 4 plan amendment，不是implementation或code review。
