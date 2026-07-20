# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-S1 Controller validation

## Entry and scope locks

- accepted plan commit：`15979f5d32738148bf53daf9defe2dca59b8360c`。
- changed test：`tests/cli/test_upload_filings_from_command.py`。
- implementation artifact：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-implementation-codex.md`，SHA-256 `ee0a714359388de70f2ef991341f512b89d46455b90e53d9c986c7ccd98532f5`。
- binary test diff SHA-256：`9c16a8c737eac8f0bdc816dd8e400a4987957fcbc03b1d70bcf661e0a00712e6`。
- Controller control-doc是本gate外的既有状态更新；production、README、workflow、S2/S3 files零diff；staged tree empty。

## Independent semantic validation

修改位于正确owner。Fresh create缺company-name仍由Fins pipeline fail closed；S1没有修改production owner，而是让Windows real-smoke向public CLI提交与既有POSIX smoke相同的合法`Apple Inc.`输入。

Pre-execution oracle在generation成功后、`cmd.exe`执行前读取strict UTF-8/CRLF script，锁定固定header、唯一`REM Regenerate:`、唯一业务行与固定post-command lines。它以test-local full-line splitter复用现有batch percent/caret decoder与CRT argument parser，逐token要求`python -m dayu.cli upload_filing`、恰好一个`--company-name`及精确下一值；没有whole-file count、substring、POSIX parser或execution-result反推。

平台无关negative test覆盖comment-only、非`upload_filing`业务command、两条业务command与重复company-name；真实smoke仍保留fresh storage、real cmd、exit/terminal/source artifact assertions，并从同一owner assertion向artifact写`company_name_supplied=true`。

新增full-line parser是测试证据owner内的必要最小逻辑：它不复制production renderer，不生成脚本，只把已存在的独立batch与CRT token oracle组合为line-level proof；production/CLI/Fins没有新abstraction或fallback。

## Controller rerun

- `pytest tests/cli/test_upload_filings_from_command.py tests/fins/test_sec_pipeline_upload_filing_stream.py -q`：`29 passed, 2 skipped, 3 warnings`。
- full `python -m pyright dayu tests utils`：`0 errors, 0 warnings, 0 informations`。
- scoped Ruff：PASS。
- `git diff --check`：PASS；staged empty；production/README/workflow diff scan零输出。
- AgentCodex另报告focused owner set `182 passed, 7 skipped`、required owner nodes `2 passed`、broader CLI `520 passed, 7 skipped`、broader Fins `95 passed`；full Ruff 142-entry baseline tuple hash前后相同。
- 本地两个real Windows tests保持platform skip，未据此声明remote closure。

## Decision

结论：`PASS / READY_FOR_DUAL_COMPLETE_CODE_REVIEW / NOT_ACCEPTED_FOR_COMMIT_YET`。

下一gate由AgentMiMo/AgentDS完整code review immutable S1 diff、implementation artifact与Controller validation。必须挑战parser反例、pre-execution ordering、Fins owner零改动、test-only overdesign与Windows实际argv语义。Review前不得fix、stage、commit、push或dispatch。
