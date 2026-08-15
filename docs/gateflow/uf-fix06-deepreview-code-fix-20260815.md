# UF-FIX06 aggregate deepreview code-fix

## Gate 元数据

- Work unit：`UF-FIX06 converter-capability-owner`
- Gate：aggregate deepreview -> fix
- 日期：2026-08-15
- 修复基线：`f61ddb95`
- 裁决输入：`docs/reviews/uf-fix06-deepreview-adjudication-20260815.md`
- Findings 输入：`docs/reviews/deepreview-uf-fix06-ds-20260815.md`
- 状态：`CODE FIX COMPLETE / RE-REVIEW PENDING`
- Artifact：`docs/gateflow/uf-fix06-deepreview-code-fix-20260815.md`
- 下一入口：AgentMiMo 与 AgentDS 对 DS-F1、DS-F2 做 aggregate deepreview re-review

## Scope 与 owner 判断

两个 accepted finding 的动机成立，但都只是文本投影 owner drift，不是 admission、转换、存储或状态机错误：

- DS-F1：`FinsUploadFormatCapability.companion_only_suffixes` 已拥有 companion-only 集合，
  `project_fins_upload_format_text(...)` 却把 `.xsd` 写成第二个文本真源。
- DS-F2：material 的 converter-required、upsert 非空和 delete 空状态由 typed contract 拥有，
  upload tool schema 已投影这些语义，但 `upload_material --files` 仍使用孤立的旧 help 文案。

因此修复边界限定为 `dayu.fins.upload_format_contract` 的文本投影 owner、CLI 参数 help 的直接消费点，
以及 owner/CLI contract 测试。没有修改 runtime admission、workflow、converter、storage、failure contract、
registry、oracle、scenario、design 或 frozen evidence。

## 修改内容

### DS-F1：已修复

- `project_fins_upload_format_text(...)` 改为显式接收 `FinsUploadFormatCapability`。
- filing companion-only 文案从 `capability.companion_only_suffixes` 排序并机械投影，不再写死 `.xsd`。
- owner 级测试使用替代 companion-only 集合 `.schema`，断言文案随 contract 输入变化且不残留 `.xsd`。

### DS-F2：已修复

- `FinsUploadFormatTextProjection` 新增 `material_files`，自足说明：
  `auto/create/update` 至少一个文件、每个文件使用 converter 支持后缀并逐个实际转换成功、
  后缀准入不承诺内容转换成功、`delete` 不得提供文件。
- `upload_tool_files` 机械复用同一个 `material_files`，不再维护独立 material 分支文案。
- `upload_material --files` 直接消费 `FINS_UPLOAD_FORMAT_TEXT.material_files`。
- CLI owner test 同时断言 argparse action 的 exact source 与最终 help 的必要业务语义。

## Changed files

- `dayu/fins/upload_format_contract.py`
- `dayu/cli/arg_parsing.py`
- `tests/fins/test_upload_format_contract.py`
- `tests/cli/test_arg_parsing.py`
- `docs/gateflow/uf-fix06-deepreview-code-fix-20260815.md`

## 验证

### 受影响 focused tests

准确命令：

```bash
source .venv/bin/activate && pytest tests/fins/test_upload_format_contract.py tests/cli/test_arg_parsing.py tests/fins/test_fins_ingestion_tools.py -q
```

结果：`570 passed, 3 warnings in 6.88s`。三条 warning 均来自已安装 `edgar` 包的 deprecated import，
与本次修复无关。

### 受影响文件覆盖率

准确命令：

```bash
source .venv/bin/activate && coverage erase && coverage run -m pytest tests/fins/test_upload_format_contract.py tests/cli/test_arg_parsing.py tests/fins/test_fins_ingestion_tools.py -q && coverage report --include='dayu/fins/upload_format_contract.py,dayu/cli/arg_parsing.py,dayu/fins/tools/upload_tools.py'
```

结果：`570 passed, 3 warnings in 9.35s`；`dayu/fins/upload_format_contract.py 94%`、
`dayu/cli/arg_parsing.py 99%`、`dayu/fins/tools/upload_tools.py 92%`，合计 `97%`。

### 全量类型检查

准确命令：

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。pyright 仅提示当前 `1.1.409` 有可用更新 `1.1.411`，
不影响检查结论。

### Diff 与受保护范围

准确命令：

```bash
git diff --check
git diff --name-only
git status --short -- docs/cli_ci_oracles.json docs/cli_ci_scenarios.json docs/host/design.md docs/engine/design.md
git diff -- docs/cli_ci_oracles.json docs/cli_ci_scenarios.json docs/host/design.md docs/engine/design.md
```

结果：

- `git diff --check`：exit `0`，无输出。
- 写本 artifact 前，`git diff --name-only` 仅列出上述两份生产文件与两份测试文件。
- 两条 protected-file 命令均无输出：`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、
  `docs/host/design.md`、`docs/engine/design.md` 未修改。
- 未修改 registry、oracle、scenario、design、README 或 frozen evidence。
- 未执行 UF-PF06、UF-PF12 或真实 CLI evidence；本 gate 只运行上列 deterministic pytest 与 pyright。
- 未执行 `git commit`。

## README 决策

不修改 README。根 README 已要求用户以即时 `upload_filing/upload_material --help` 为准，
并已说明 filing/material 的既有格式和转换边界；`dayu/fins/README.md` 已声明 material 每项均为
converter-required 且逐个转换；`tests/README.md` 已把 CLI help、LLM-facing schema 和 batch admission
同源投影列入现有 focused matrix。本次只修复这些既有承诺的投影一致性，没有新增用户工作流或架构语义；
同时遵守本 gate 明确的 README 禁改范围。

## Finding status 与 residual risks

- DS-F1：`已修复`，等待独立 re-review 确认。
- DS-F2：`已修复`，等待独立 re-review 确认。
- MiMo-F1：维持 controller 裁决 `DEFERRED / NON-BLOCKING`，failure contract 演进不属于 UF-FIX06。
- MiMo-F2、MiMo-F3：维持 controller 的 rejected-with-reason 裁决。
- UF-FIX07 的显式 primary、重复路径、basename/stem collision：`assigned to later work unit`。
- delete 携带 files 与 material 空 upsert 的 failure 分类精化：`assigned to later work unit`。
- UF-PF06、UF-PF12 的真实全格式/CLI scenario evidence：`assigned to later work unit`，本 gate 未执行。
- 未分类 residual risk：无。

## Completion status

两项 accepted finding 的最小 owner-boundary code fix 已完成，focused tests、覆盖率、全量 pyright 与
diff/protected-scope 审计均通过。当前不是 aggregate deepreview pass；必须先完成 AgentMiMo 与 AgentDS
双路 re-review，再由 Controller 裁决是否接受 deepreview。

双路 re-review 期间 AgentDS 记录一项非阻塞 docstring 精度观察：返回值说明遗漏 material CLI help
消费者。Controller 已同步把说明改为“CLI filing/material help 与 upload tool schema 共用”，不改变生产
行为、类型或投影内容；该行由两路 reviewer 在最终接受前复核。
