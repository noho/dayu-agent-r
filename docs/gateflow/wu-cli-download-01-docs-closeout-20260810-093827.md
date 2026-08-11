# WU-CLI-DOWNLOAD-01 documentation closeout

## Gate 状态

- 基线：`5f5b19949817eaeaa309cf5f75135f57a29e4c14`。
- 阶段：四个 implementation slices 已接受后的 documentation closeout。
- 结果：指定三份 README 已按当前 production owner contract 更新；停在原 MiMo / DS 双路 docs review 入口。
- 未执行 commit、push、PR、真实 CLI 或 provider 请求。

## 第一性原理与边界裁决

当前变化只影响 `download` 的最终用户稳定行为、`dayu.fins` package contract 和既有测试事实。`UI -> Service -> Host -> Engine` 主链、Fins direct 边界与 `dayu.runtime` 层中立边界均未改变，因此 `dayu/README.md` 只回读、不修改。未发现需要扩展 base plan §7.2 closeout allowlist 的直接证据。

实际修改范围：

- `README.md`
- `dayu/fins/README.md`
- `tests/README.md`
- 本 closeout artifact

## 文档投影

### 根 README

- 记录 `download` 静态 ticker/forms/date 校验发生在 workspace 解析、runtime 启动和 provider 访问前；用法错误以 `2` 退出且无 workspace/runtime 副作用。
- 记录 single ticker、market-specific forms canonicalization / stable dedupe，以及包含边界的日期窗口展开。
- 记录 SEC User-Agent prerequisite 与 `SEC_USER_AGENT` 配置示例。
- 记录 `--overwrite` 只替换本轮单目标且不删除非目标旧文档。
- 记录 `--rebuild` 只从既有本地 source 重建 download meta/manifest，不发 provider 请求，也不新增、删除或替换 source 内容。
- 记录 Ctrl-C 等待 canonical cancelled terminal、退出码 `130`，以及用户可见 final summary 字段。

### Fins README

- 删除 download adapter 消费 `rebuild_processed` 的旧述，明确 typed `FinsDownloadRequest.rebuild_local_artifacts` 与 preprocess `rebuild_processed` 的独立 owner。
- 记录 typed terminal summary、SEC UA/provider policy 与封闭失败分类。
- 记录 same-process per-ticker condition reservation、cross-process blocking writer lock、recovery nonblocking try-lock 和统一 release/notify。
- 记录 published/staged `MISSING` / `COMPLETE` / `REPAIR_REQUIRED` integrity classification、malformed SHA-256 strict failure、whole-tree preflight、single selected repair-first 和多处/未选中 corruption mutation 前 fail closed。
- 记录 repair unconditional transport、Phase B 原 overwrite policy/identity revalidation，以及 provider/PDF/Docling I/O 不进入 writer reservation。
- 删除 CN/HK `asyncio.to_thread` 不可强中断旧述，记录 process-backed Docling cancellation、输出校验和临时目录清理。

### tests README

- 删除 production persisted-summary adapter 消费 download `rebuild_processed` 的旧测试事实。
- 在既有 `tests/fins/` 事实段中概括 invocation、selection、non-delete overwrite、local-only rebuild、missing-period、UA/provider、canonical cancellation、typed summary、process cancellation、writer concurrency 和 integrity/repair owner coverage。
- 并发事实只描述 Event/barrier 驱动的确定性矩阵，不写 work unit 名称、时间敏感计数或未来测试计划。

## 验证证据

以下命令均在仓库根目录执行。

1. 基线与初始状态：

   ```bash
   git status --short --branch && git rev-parse HEAD
   ```

   Exit code `0`；初始分支为 `codex/download-oracle`，工作树干净，HEAD 与上述基线一致。

2. 本地 Markdown 链接存在性：

   ```bash
   rg -o '\[[^]]+\]\([^)]+\)' README.md dayu/fins/README.md tests/README.md
   test -f dayu/README.md && test -f dayu/config/README.md && test -f dayu/engine/README.md && test -f docs/host/design.md
   ```

   Exit code 均为 `0`；三份 README 的四个相对链接均存在。唯一外部链接是既有 GitHub Issue 链接，本次未新增或修改。

3. 根 README 公开契约回归：

   ```bash
   source .venv/bin/activate && pytest tests/cli/test_arg_parsing.py::test_root_readme_matches_current_cli_public_contract -q
   ```

   Exit code `0`；`1 passed`，另有三条 edgartools deprecation warning，与本次文档修改无关。

4. 旧述清除与必备事实 grep：

   ```bash
   if rg -n 'Production download adapter 必须消费 `FinsDownloadRequest\.rebuild_processed`|production persisted-summary adapter 消费 `rebuild_processed`|CN/HK Docling convert 当前通过 `asyncio\.to_thread' README.md dayu/fins/README.md tests/README.md; then exit 1; fi
   rg -n '退出码 `2`|SEC_USER_AGENT|`--overwrite` 只替换|`--rebuild` 只根据|最终摘要' README.md
   rg -n 'blocking writer lock|nonblocking try-lock|`MISSING`|`REPAIR_REQUIRED`|whole-tree preflight|rebuild_local_artifacts=true|FinsResultSummary|独立子进程' dayu/fins/README.md
   rg -n 'static canonicalization|Download owner coverage|blocking lock|REPAIR_REQUIRED|whole-tree repair-first' tests/README.md
   ```

   Exit code `0`；三个已知旧述均为零命中，所需稳定事实均命中。`rebuild_processed` 仅保留在 preprocess 的合法 owner contract 中。

5. diff 与边界检查：

   ```bash
   git diff --check
   git diff --exit-code -- dayu/README.md
   git diff --name-only
   ```

   Exit code 均为 `0`；无 whitespace error，`dayu/README.md` 零 diff；写 artifact 前 name-only 精确为 `README.md`、`dayu/fins/README.md`、`tests/README.md`。

未运行 Ruff、format、pyright 或 production owner suite：本 gate 未修改 Python、schema、产品或测试代码；已运行唯一直接读取根 README 的契约测试。该裁决不把 docs-only 验证冒充 implementation 回归，四 slices 的 production validation 仍以已接受 implementation artifact 为真源。

## 残余风险

- 文档只投影当前已接受代码，不新增运行时保证；MiMo / DS 仍需分别审查用户手册边界、package semantic ownership、旧述是否完全清除及 tests README 是否仅描述既有事实。
- 未联网验证既有外部 GitHub Issue 链接；本次没有修改该链接，所有相对链接已做本地存在性检查。

## 下一 Gate

停在原 MiMo / DS 双路 docs review 门。review 前不 commit、push、创建 PR 或修改其它 artifact。
