# PR190 F15/F16 final closeout

## Scope and adjudication

- Work unit: PR190 init/prompt/interactive 第一轮 Oracle/scenario 闭环的 F14 fresh-rerun follow-up。
- Goal Confirmation 与 owner 裁决：`docs/gateflow/pr-190-f15-f16-goal-confirmation-20260807.md`。
- Accepted plan：`docs/gateflow/pr-190-f15-f16-plan-20260807.md`。
- Product target used for final real observation: `3cfc878aff5f55882c78423c327a24f28f44aaf2`。
- Formal replacement scenarios保持`unadjudicated`；本work unit未修改accepted Oracle/scenario predicate，未标accepted/ready。

## F14 status

F14 accepted coverage frontier修复保持成立，未回滚或稀释：

- Host durable accepted truth中的`compacted_source_refs`仍是唯一累计consumed frontier；terminal EventLog sequence不再反推material coverage。
- protected recent raw turns在第一次accepted compact未覆盖时不被消费；离开recent floor后按canonical Host Run group重新进入后续boundary。
- final fresh observation中FY2025 correction的production evidence位于EventLog sequence 201；第一次accepted compact在245且未覆盖该ref，第二次accepted compact在515且source boundary、accepted mapping均包含该ref。
- 因此本次真实链证明F14 frontier行为未被F15/F16修复破坏。

## F15 root cause and owner fix

### Root cause

previous compacted view pair存在双投影：accepted answer-anchor detail的readable view保留原文本，packed material path经另一套normalization折叠空白；合法空行可令strict validator报`previous answer_anchors block text mismatch`，随后投影成`runner_candidate_invalid`。

### Fix

- Host `compact_material.py`在accepted replacement owner boundary建立唯一canonical renderer/normalization truth。
- packed blocks、readable view与validator消费同一组canonical section atoms；accepted tool evidence保持独立typed exact renderer。
- 没有prompt规避、loose comparison、fallback、兼容分支或validator绕过。
- Host/Engine/product public schema没有变化。

### Evidence

- deterministic owner tests覆盖空行、首尾空白、重复空白、多段Markdown、列表、表格、durable reopen/reconnect与下一ordinary Run freeze/dispatch。
- real run全部28个ordinary Runs为`RUN_SUCCEEDED`，未出现`runner_candidate_invalid`。
- real accepted anchor实际覆盖multiline Markdown、表格和列表，但没有产生detail内部空白行；因此真实run不宣称复现原始blank-line格式，blank-line证据仍由owner tests提供。

## F16 root cause and owner fix

### Root cause

旧harness只等待terminal数量增长，再用interactive进程最终exit 0写`execution_outcome: success`；REPL单Run失败后继续运行，导致`RUN_FAILED`被误分类并继续依赖段。

首次post-implementation fresh run又暴露publication producer问题：业务链为28/28 succeeded和2次compact，但filesystem snapshots/index与workspace-mode Tool Trace发布raw DB paths，final scan正确返回invalid（22 violations）。这份实例保留为non-publishable历史证据，不重标PASS。

- 历史invalid root：`/Users/leo/workspace/.dayu-cli-ci/f15-f16-postfix-SfyZRB98`。
- 历史execution index SHA-256：`701108b7475a35248e46fd39e9879f4dff7c47352d5a98f9b3fc6b13b57c7e37`。
- 历史final scan SHA-256：`7c62ff0e5324b1788780c9a22e9cf112c1cca40db2949859cf93a57ac693ed2f`；该scan为invalid，不能作为publishable PASS。
- 历史context observation SHA-256：`119b99a5e7c0600857ad2b08072fbb7e61417e0d9fc05f8ba09e755a9fcb927c`。

### Fix

- canonical EventLog terminal是逐Run事实owner；tracked helper精确投影`RUN_SUCCEEDED`、`RUN_FAILED`、`RUN_CANCELLED`、`RUN_LOST`与terminal-specific reason，process exit单独记录。
- required Run非success时dependency gate停止后续依赖动作并只执行cleanup/EOT；evidence明确为complete/insufficient/invalid，formal Oracle仍为`unadjudicated`。
- tracked typed classifier成为public evidence raw DB path唯一owner；snapshot producer与final scanner复用同一truth，覆盖main、WAL、SHM及文本路径，scanner保持fail-closed。
- production public Tool Trace analyzer改以canonical cold JSONL为输入；per-scenario Host Tool Trace仍保留production request/response，context compact由EventLog owner独立投影。没有字符串删除、下游fallback或第二真源。
- final publication index先写，随后唯一final-tree scan包含index并独占写report；raw stores只留本机workspace。

### Contract boundary

- Host/Engine、CLI用户入口、财报工具和formal scenario registry的product public schema均未变化。
- CLI CI内部evidence contract被强化：新增逐Run canonical terminal分类、process/Run outcome分离、dependency safe-stop与唯一final publication verdict。

## Independent review

- Plan reviews：MiMo/DeepSeek两路独立plan review，Controller裁决后接受。
- Implementation reviews与复审：
  - `docs/reviews/pr-190-f15-f16-implementation-review-mimo-20260807.md`
  - `docs/reviews/pr-190-f15-f16-implementation-review-ds-20260807.md`
  - `docs/reviews/pr-190-f15-f16-postscan-final-rereview-mimo-20260807.md`
  - `docs/reviews/pr-190-f15-f16-postscan-final-rereview-ds-20260807.md`
  - `docs/reviews/pr-190-f15-f16-real-evidence-fix-rereview-mimo-20260807.md`
  - `docs/reviews/pr-190-f15-f16-real-evidence-fix-rereview-ds-20260807.md`
  - `docs/reviews/pr-190-f15-f16-brace-fix-final-rereview-mimo-20260807.md`
  - `docs/reviews/pr-190-f15-f16-brace-fix-final-rereview-ds-20260807.md`
- 最终MiMo/DeepSeek均PASS；无P0/P1/P2/P3阻断finding。Controller接受并修复了非JSON花括号path boundary，拒绝解析symlink chain的下游派生建议。

## Deterministic validation

- final owner suite：55 passed。
- final focused CLI lifecycle aggregate：150 passed。
- final affected Host/CLI union：524 passed。
- full pyright `dayu/ tests/ utils/`：0 errors, 0 warnings。
- changed-code Ruff、compileall、registry JSON parse、`git diff --check`：通过。
- 初始implementation gate全量pytest：`4 failed, 6802 passed, 10 skipped, 6 deselected`；四个失败均为frozen publication manifest digest tests，并在detached accepted-plan baseline `580b1427`精确复现，判定为既有基线失败。follow-up仅修改CLI CI helper/tests/docs，未为该失败加入兼容代码。
- modified helper coverage：82%，满足单文件>=80%目标。

## Fresh real production observation

### Execution

- Fresh root：`/Users/leo/workspace/.dayu-cli-ci/f15-f16-postfix-rerun-vNMkeVul`。
- Entrypoint：production `dayu-cli interactive`、POSIX PTY。
- Provider/model：real MiMo plan / `mimo-v2.5-pro-plan`。
- Tool/corpus：production finance tools、真实AAPL corpus与2025 Form 10-K。
- Fake/mock provider/tool：未使用。
- 7个process均exit 0且无timeout；canonical Run独立计数为28 accepted、28 succeeded、0 failed/cancelled/lost/missing/invalid；7个dependency gates全部proceeded，harness invalid为0。
- accepted compact共2次，EventLog sequence分别为245与515。

### Durable result

- 第二次replacement把FY2025 416,161 / 133,050及SEC 2025 10-K来源写入durable EvidenceFacts，并绑定新非空production ref `evidence:event-tool-result-accepted-591f43793c0169916ea4976ccec28ebceb718e71a5a4e55d0cbc60167ffd4e0e`。
- FY2024 391,035 / 123,216保留原FY2024 provenance且只作为历史比较期。
- 21.7% EvidenceFact count为0；所有accepted EvidenceFacts的evidence refs均非空。reference continuity明确禁止21.7%借用FY2024/FY2025 provenance。
- reconnect frozen RunInput绑定sequence-515 compact artifact，投影含FY2025、416,161、FY2024历史状态与21.7%未核验状态；跨进程屏幕回答与durable Memory一致。
- artifact、EventLog、Memory、RunInput与public Tool Trace来自同一accepted truth；手工核对source labels未发现无label current input借旧P label支撑业务事实。

### Publication

- Evidence root：`/Users/leo/workspace/.dayu-cli-ci/f15-f16-postfix-rerun-vNMkeVul/evidence`。
- Observed report：`/Users/leo/workspace/.dayu-cli-ci/f15-f16-postfix-rerun-vNMkeVul/oracle-rerun-observed-behavior.md`；放在evidence tree之外，避免final scan后追加文件破坏封闭性。
- Execution index SHA-256：`426acb373aa4ea0bb12232bcf987e0c23b31b4651bc8bfa56564225b585692d6`。
- Context-compaction observation SHA-256：`a9a1f68107c7e29f84499290149b58a2670b6d3bb5aa9a8f005c230afb646383`。
- Final secret/path scan SHA-256：`617a1be3c5155bf1e518fc3573ab7e897d0bd3af000cf7e43c13a08c3ac1ccec`；status complete，109 files / 31,341,257 bytes，0 secret hit、0 path violation、0 validation error。
- Observed report SHA-256：`cbac55f151ec3091dbe7fd7872353d1ba21b7adf609393b82a3b90e88cd4b702`；单文件exact-secret/path复扫为0 hit、0 violation、0 validation error。
- raw Host/runtime stores保留本机原件且未进入evidence bundle。

## Commits

F14 preserved chain：

- `b222b8b0` `gateflow: accept plan for F14 coverage frontier`
- `6eb41ac1` `fix(host): derive compact frontier from accepted coverage`
- `7dd84a4a` `gateflow: accept F14 aggregate deep review`
- `97c04986` `gateflow: close out F14 coverage frontier`

F15/F16 work unit：

- `580b1427` `docs: accept PR190 F15 F16 repair plan`
- `1a339fd9` `fix: canonicalize compact views and classify CLI evidence`
- `3cfc878a` `fix: sanitize CLI evidence publication paths`

本closeout文档将作为后续独立commit push到同一PR190 branch；最终head由Controller在handoff中给出。

## Remaining risks and user adjudication

- Formal replacement scenarios仍为`unadjudicated`；用户/Oracle总控需审阅本观察报告后裁决，Controller未修改registry readiness。
- real model本次未产生answer-anchor detail空白行；F15该格式只由deterministic owner contract覆盖，未伪称real coverage。
- cold Tool Trace analyzer不解析hot payload；完整production request/response由同bundle的per-scenario Host Tool Trace提供，二者关系已独立review。
- init/prompt/interactive第二轮readiness仍需用户决定：是否接受本fresh observation作为formal replacement candidate，以及何时更新scenario adjudication/registry。当前PR保持draft，不merge、不mark ready、不approve/request reviewers。
