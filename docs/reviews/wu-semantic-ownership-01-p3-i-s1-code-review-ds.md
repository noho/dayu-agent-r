# Code Review

## Scope

- Mode: current changes
- Branch: phaseflow/host-issues-control
- Base: main (controller validation confirmed S1 scope correction already applied on branch)
- Output file: docs/reviews/wu-semantic-ownership-01-p3-i-s1-code-review-ds.md
- Work unit: WU-SEMANTIC-OWNERSHIP-01 P3-I
- Slice: S1 Public Package Entrypoints And README Truth
- Included scope:
  - `dayu/web/__init__.py`, `dayu/web/__main__.py` (new)
  - `dayu/wechat/__init__.py`, `dayu/wechat/main.py` (new)
  - `dayu/render/__init__.py`, `dayu/render/render.py` (new)
  - `tests/cli/test_public_package_entrypoints.py` (new)
  - `README.md` (modified)
  - `tests/README.md` (modified)
  - `dayu/README.md` (modified)
- Excluded scope:
  - Pre-existing untracked files per task instruction: `docs/cli_ci.md`, `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`, `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`
  - `docs/host/issues-implementation-control.md` (too large to read; used controller validation as reviewed proxy)
  - S2 files (CLI terminal cursor) — not in S1 scope
- Parallel review coverage: 无

## Review Sources

- Plan: `docs/host/wu-semantic-ownership-01-p3-i-public-entrypoints-terminal-watermark-plan.md`
- Implementation report: `docs/reviews/wu-semantic-ownership-01-p3-i-s1-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-i-s1-controller-validation.md`
- Control doc: `docs/host/issues-implementation-control.md` (too large for full read; controller validation treated as reviewed summary)

## Validation Results (Independent Re-run)

```
pytest tests/cli/test_public_package_entrypoints.py -q → 12 passed
python -m pyright dayu/web/ dayu/wechat/ dayu/render/ tests/cli/test_public_package_entrypoints.py → 0 errors, 0 warnings, 0 informations
python -m dayu.web --help → exit 0, correct help output
python -m dayu.wechat.main --help → exit 0, correct help output
python -m dayu.render.render --help → exit 0, correct help output
python -m dayu.web (no args) → exit 1, "尚未提供可运行的 Web UI" to stderr
python -m dayu.wechat.main (no args) → exit 1, "尚未提供可运行的微信登录" to stderr
python -m dayu.render.render input.md output.pdf → exit 1, "尚未提供 Markdown 到 HTML、Word 或 PDF 的转换实现" to stderr
git diff --check → clean
rg "dayu-web|dayu-wechat|dayu-render" README.md → all hits truthful
```

## Findings

### F1-未修复-低-`_normalize_system_exit_code` 跨三个入口模块重复

- **入口/函数**: `dayu.web.__main__._normalize_system_exit_code` / `dayu.wechat.main._normalize_system_exit_code` / `dayu.render.render._normalize_system_exit_code`
- **文件(行号)**:
  - `dayu/web/__main__.py:57-67`
  - `dayu/wechat/main.py:116-126`
  - `dayu/render/render.py:67-77`
- **输入场景**: 三个模块中任意一个需要规范化 argparse `SystemExit.code` 时。
- **实际分支**: 三处代码完全相同的私有函数，各自独立定义。
- **预期行为**: 按 CLAUDE.md "重复逻辑必须抽取"原则，同一语义的 helper 应定义一次、多处复用。
- **实际行为**: 三个入口模块各自维护一份相同的 5 行实现。
- **直接证据**: 三处代码字面量一致：`isinstance(exc.code, int)` 判断 → `return exc.code` 或 `return EXIT_USAGE_ERROR`（行号见上）。
- **影响**: 若未来需要调整 SystemExit code 规范化策略（如增加 `None` → 0 的映射），需要同步修改三处；遗漏任一处会造成三个入口行为不一致。当前函数简单且稳定，实际风险低。
- **建议改法和验证点**: 方案 A（推荐）：接受当前重复，因为 S1 的显式约束是各入口模块只依赖标准库、保持自包含。方案 B：若后续 slice 决定引入共享 CLI helper，可抽取到 `dayu.cli` 公共模块。无论哪种方案，当前行为正确，不需要 S1 内修改。
- **修复风险（低）**: 抽取到共享模块会引入跨包依赖，与 S1 自包含设计冲突。
- **严重程度（低）**: 不影响正确性；纯 maintainability 观察。当前三份代码完全一致且函数极短（5 行），实际漂移风险很低。

## Open Questions

1. **WeChat 子命令非 help 执行路径未显式覆盖**: `test_non_help_execution_returns_controlled_diagnostics` 测试了 `wechat_main()` 无参数路径，但未测试 `wechat_main(("login",))` 或 `wechat_main(("service", "install"))` 等子命令非 help 路径。当前代码中这些路径与无参数路径共享同一个 `print(WECHAT_UNAVAILABLE_DIAGNOSTIC); return EXIT_UNAVAILABLE` 分支，因此无参数测试已经覆盖了该分支。但如果未来 `_build_parser()` 重构为按子命令分支返回不同诊断，缺少子命令级测试可能导致回归未被捕获。建议后续 WeChat 实现 slice 补上子命令非 help 路径的显式测试。

2. **`dayu/web/README.md` 引用**: 旧 README 中有 `详见[dayu/web/README.md](dayu/web/README.md)` 链接，新 README 已删除该引用。当前仓库中确认不存在 `dayu/web/README.md` 文件（`dayu/web/` 目录为本次 S1 新建）。如果后续 Web UI 实现 slice 需要恢复开发文档，应新建该文件并更新 README 链接。

## Residual Risk

- `dayu.render` package-data 资源文件（CSS、HTML、Lua、DOCX、XLSX、Mermaid 模板）仍未创建。pyproject.toml 中已有 package-data glob 指向 `dayu.render`，当前 glob 匹配结果为空，setuptools 构建不会报错，但若未来启用 `include_package_data=True` 或添加 `[tool.setuptools.package-data]` 严格模式，可能触发 warning。由未来 renderer owner 负责补齐。
- 完整 Web UI、WeChat daemon/service、Markdown 渲染转换仍为未实现产品能力，用户可见的 README 限制说明依赖后续 slice 实现后同步更新。若后续 slice 长时间未落地，README 中"尚未实现"的描述可能让用户误以为产品已停滞。
- `_normalize_system_exit_code` 三个副本的同步维护风险（见 F1），但因函数极短且稳定，实际漂移概率低。
