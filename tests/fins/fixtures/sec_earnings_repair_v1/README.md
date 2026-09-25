# SEC 业绩补源回归夹具 v1

只供 Dayu 分类与下载契约测试使用，不作为投资分析底稿或 KPI 来源。

数据链路：

1. `data/source_manifest/sources.json`：对交接中六个本地诊断文件的只读无损复制，记录原路径、披露日、提取时间、大小与 SHA-256。两份 ATAT 拒绝文件仅用于分类重演。
2. `data/source_manifest/downloaded_sources.json`：通过公开 Dayu CLI 在新临时 workspace 回源六个 accession，再经 storage 读取十二份 HTML；保留精确 CLI 参数、SEC URL、时间和 hash。原诊断文件与新下载文件同名时，逐字节一致才复用 Raw。
3. `data/raw/`：十二份未经转换、筛选正文或汇总的完整 HTML。没有计算字段，没有覆盖原始财务数字。
4. `../../test_sec_earnings_repair.py`：可重复审核逻辑。只在 pytest 的临时 workspace 运行；HTTP fixture 响应来自 Raw，索引与 submissions 为显式合成的选择夹具。分类 owner、120 行抽取、附件选择、CLI、事务、hash/fingerprint、meta/manifest 和 processed 失效标记使用生产实现。
5. `workpapers/validation.json` 与测试日志：修复前后分类、六次真实回源、四次真实旧完整封面补源、重复增量、hash 和范围核对结果。最终交接见 `docs/reviews/sec-earnings-repair-20260910.md`。

旧缓存测试由生产 CLI 临时使用历史“空附件选择/强信号漏判”行为生成，随后恢复新规则，从公开 CLI 执行 `--overwrite`。不会手工改 meta 或 manifest。真实旧缓存烟测则使用正式仓储生成历史完整封面夹具，再运行不带测试替身的公开 CLI；其命令及临时脚本路径记录在审核 JSON 中。

重跑离线审核：

```bash
source .venv/bin/activate
pytest -q tests/fins/test_sec_earnings_repair.py
```

重新回源时应使用一个新的临时 workspace，按下载来源清单中的 ticker/form/start/end 调用 Dayu；通过 source/blob repository 读取文件并核对 hash。若源文件发生变化或提取逻辑改变，应另建新版本 Raw，不覆盖 v1。正常测试不访问原诊断路径、不发真实网络请求，不进行经营指标提取。
