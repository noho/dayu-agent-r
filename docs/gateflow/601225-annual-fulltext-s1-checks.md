# 601225 年报全文 S1：实施检查证据

- Gate：implementation S1；仅报告验证事实，不裁决 gate。
- 分支：fix/601225-annual-fulltext；HEAD：7709c015db26c095f16cb77b5d383411cd76b652。
- 执行环境：每组命令先 `source .venv/bin/activate`；Python 3.11；pypdf 锁与安装均为 6.1.3。
- 真实完整受影响集：731 passed，3 个既有 edgartools DeprecationWarning，pytest exit 0。
- pyright：0 errors / 0 warnings，exit 0；pip check：No broken requirements found，exit 0。
- 安装：`python -m pip install -e '.[test,dev,browser]' -c constraints/lock-macos-arm64-py311.txt`，exit 0；原输出 install.log。
- 原始完整输出：`workspace/tmp/601225-validation/final-2/01..05.stdout.txt`、对应 stderr、commands.json、coverage.json、coverage-check.json。

## 实际最终命令与退出

```text
pytest -q tests/fins/test_cn_annual_report_facts.py tests/fins/test_cn_annual_report_source.py tests/fins/test_source_integrity_preflight.py tests/fins/test_cninfo_downloader.py tests/fins/test_cn_report_selection.py tests/fins/test_cn_download_models.py tests/fins/test_cn_download_identity.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/fins/test_hkexnews_downloader.py tests/fins/test_cn_pipeline.py tests/fins/test_f5_workflow_rebuild.py tests/fins/test_hk_period_rebuild.py --cov=dayu/fins --cov=tests/fins --cov-report=term-missing --cov-report=json:workspace/tmp/601225-validation/final-2/coverage.json
```
- exit：0；输出：final-2/01.stdout.txt / .stderr.txt。

```text
python utils/validate_601225_annual_fulltext.py coverage --coverage workspace/tmp/601225-validation/final-2/coverage.json --output workspace/tmp/601225-validation/final-2/coverage-check.json
```
- exit：0；输出：final-2/02.stdout.txt / .stderr.txt。

```text
pyright
```
- exit：0；输出：final-2/03.stdout.txt / .stderr.txt。

```text
python -m pip check
```
- exit：0；输出：final-2/04.stdout.txt / .stderr.txt。

```text
python -c import pypdf; assert pypdf.__version__ == "6.1.3"; print(pypdf.__version__)
```
- exit：0；输出：final-2/05.stdout.txt / .stderr.txt。

## coverage 的实际收集差异

按 P5.5 原模块名 source 命令执行两次，均在 collection 阶段出现 NumPy `cannot load module more than once per process`，exit 2；未产生 coverage.json。保留 checks-full-first.log / checks-full-second.log。相同 13 文件 test 集改用目录 source `--cov=dayu/fins --cov=tests/fins` 后正常执行；没有排除代码、降低门槛或预导入生产模块。目录收集范围更广，最终辅助工具仍精确核以下 12 个生产文件及实际修改/新增测试。之前失败的普通实现/夹具与辅助工具启动尝试日志均保留在同 validation 根，未作为成功证据。

## 逐文件覆盖率

| 文件 | 可执行语句 | 覆盖率 |
| --- | ---: | ---: |
| `dayu/fins/downloaders/cninfo_downloader.py` | 388 | 90.72% |
| `dayu/fins/downloaders/hkexnews_downloader.py` | 461 | 85.03% |
| `dayu/fins/pipelines/cn_annual_report_facts.py` | 36 | 100.00% |
| `dayu/fins/pipelines/cn_annual_report_source.py` | 68 | 98.53% |
| `dayu/fins/pipelines/cn_download_filing_workflow.py` | 300 | 92.33% |
| `dayu/fins/pipelines/cn_download_identity.py` | 66 | 100.00% |
| `dayu/fins/pipelines/cn_download_models.py` | 182 | 96.15% |
| `dayu/fins/pipelines/cn_download_protocols.py` | 40 | 100.00% |
| `dayu/fins/pipelines/cn_download_source_upsert.py` | 78 | 85.90% |
| `dayu/fins/pipelines/cn_download_workflow.py` | 339 | 92.04% |
| `dayu/fins/pipelines/cn_report_selection.py` | 303 | 91.75% |
| `dayu/fins/storage/source_integrity.py` | 131 | 85.50% |
| `tests/fins/test_cn_annual_report_facts.py` | 49 | 100.00% |
| `tests/fins/test_cn_annual_report_source.py` | 100 | 100.00% |
| `tests/fins/test_cn_download_identity.py` | 151 | 99.34% |
| `tests/fins/test_cn_download_models.py` | 60 | 100.00% |
| `tests/fins/test_cn_download_runtime.py` | 1058 | 99.34% |
| `tests/fins/test_cn_download_workflow.py` | 1951 | 97.90% |
| `tests/fins/test_cn_pipeline.py` | 894 | 98.21% |
| `tests/fins/test_cn_report_selection.py` | 135 | 100.00% |
| `tests/fins/test_cninfo_downloader.py` | 795 | 94.34% |
| `tests/fins/test_f5_workflow_rebuild.py` | 230 | 100.00% |
| `tests/fins/test_hkexnews_downloader.py` | 678 | 92.48% |
| `tests/fins/test_source_integrity_preflight.py` | 26 | 100.00% |

全部精确路径均有 JSON entry 且 >=80%；不是用总体 35% 代替逐文件门槛。总体包含大量未运行的未修改文件，不能用于本 slice 裁决。

## P6 与权限边界

四次真实公开 CLI、原 raw/transport/wire、真实 Docling、摘要保留和 repeat 比较在 S1 implementation artifact 与独立 `workspace/tmp/601225-cli-s1/` 记录；本 checks artifact 不用单测、baseline 432 或 seed 替代公开入口验收。

- 未 commit/push/PR/comment/issue，未派发、清理或终止其它 Agent/任务。
- 冻结计划 SHA256 保持 `7a2acac94ca5592b5848a3ca78c77be55e2f79766f69f83db558f0017d615aaf`；旧 review artifacts 与总控 state 未由本 owner 修改。
- code review / 双路 deepreview、实际退出复核和 gate 裁决由总控负责。

交付前独立 observer 参数拒绝补齐 `--forms=...` 等等号写法（四个正式 argv 均不含这些参数），再次激活 venv 运行 pyright，实际 exit 0 / 0 errors / 0 warnings；原输出 `workspace/tmp/601225-validation/pyright-delivery.log`。utils 依项目约束免单测/coverage，未改生产/测试代码或正式验收数据。
