# WU-SEMANTIC-OWNERSHIP-01 / R11-I2 wheel smoke plan-drift Controller adjudication

## 1. Verdict

`PLAN FIX REQUIRED / IMPLEMENTATION PAUSED`。

Controller 接受 `R11-I2-VAL-PD-F02`。当前产品/README/test实现没有暴露新缺陷；失败来自 accepted plan 把两个互斥 oracle合并：用 `--no-deps` 只安装 wheel，却要求完整 `dayu.cli` import graph运行。I2 implementation保持 stopped，只有 plan-only correction可继续。

## 2. Direct evidence 与 semantic owner

accepted plan §7.3 当前顺序：

1. fresh venv；
2. `pip install --no-deps <built-wheel>`；
3. 在该 venv 运行 `python -m dayu.cli --help` 与 `upload_filings_from --help`。

wheel build、extract 与 no-deps install均成功；首个 help 在既有 `dayu.engine.runners.openai.runner` import `aiohttp` 时失败：`ModuleNotFoundError: No module named 'aiohttp'`。

`pyproject.toml [project].dependencies` 直接声明 `aiohttp>=3.9.0` 以及其它 runtime dependencies。`--no-deps` 的语义就是不安装这些已声明依赖，所以该失败不能归因于 CLI eager import，也不能通过 lazy import、fallback、sys.path、fixture shim或扩大 I2 生产范围修复。

唯一正确 owner 是 packaging smoke plan：

- wheel 内容/metadata/entrypoint/package残留由 build + archive/RECORD/METADATA负向 oracle独立验证；
- 可运行性 smoke必须在 fresh venv 中按当前受支持平台 constraints 安装 wheel及其声明的 runtime dependencies，再运行 `pip check` 和两个真实 help。

当前执行平台是 Darwin arm64 / Python 3.11 `.venv`，已有 owner lock `constraints/lock-macos-arm64-py311.txt`。因此 local exact install 应从 built wheel执行：

```bash
workspace/tmp/r11-wheel-venv/bin/python -m pip install \
  --constraint constraints/lock-macos-arm64-py311.txt \
  <exact-built-wheel>
workspace/tmp/r11-wheel-venv/bin/python -m pip check
```

不得保留先装 `--no-deps` 再对同版本重复 install 的偶然 pip行为；fresh venv只做一次 constrained normal install。`python -m pip wheel --no-deps --no-build-isolation` 保持不变，因为它只构建当前 project wheel，不负责 runtime install。

## 3. Finding ledger

| id | severity | status | plan owner fix |
|---|---|---|---|
| `R11-I2-VAL-PD-F02` | HIGH | ACCEPTED / OPEN | §7.3 isolated wheel install/help smoke 与 §8/§10相关验证 wording |

blocking question `0`；design/user decision conflict `0`；new WU `0`。

## 4. Protected stopped tree

- HEAD：`de476c452411e9d325d43b608de22b7236edfedb`；
- plan before-fix SHA-256：`20f35e55573321ddfa474f772742097bb55963165936195de73785c39bc031dd`；
- stopped product/test/README/packaging diff SHA-256：`6c8284c6fdcfc4661a0bcd00f1c155d34985fa4af81fa400158ce3a034acd0e6`；
- corrected shared test SHA-256：`d3a4abcc22093ff6c4e06edebf249282f1fbac9d9eb3a575c618f28210742658`；
- corrected tests README SHA-256：`478efffcbf5d3e4f172ec5a7373e49996cf62f3b85a485fdcd60af7623f1c4c1`；
- renderer/workflow SHA-256：`dfe0508d...aea65` / `4026da55...0953`；
- focused `153 passed, 2 skipped`、I2 `82 passed, 2 skipped`、POSIX real smokes pass、Windows local `1 passed, 2 skipped`；
- staged set空。

所有 stopped implementation/test/README/packaging/workflow、Controller control/artifacts均 read-only during plan gate。

## 5. Plan-only authorization

AgentCodex 只可修改：

1. `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`
2. 新增 `docs/reviews/wu-semantic-ownership-01-r11-i2-wheel-smoke-plan-drift-fix-codex.md`

plan fix必须：

- 将 §7.3 fresh venv install从 `--no-deps` 改为 exact built wheel + `constraints/lock-macos-arm64-py311.txt` 的一次 normal constrained install；
- 增加 `pip check`，再运行两个 help与 package importability oracle；
- 保留 wheel build `--no-deps --no-build-isolation` 与全部 archive negative oracles；
- 同步 §8、§10、stop conditions/validation说明，明确 dependency install失败是真实 packaging gate failure；
- 不改 Windows workflow install command、产品范围、22/8/15 counts、shared-node contract、review/commit sequence或 deferred owners。

artifact须记录 exact before/after命令、protected stopped-tree locks与 no-test/no-implementation proof，以 `READY_FOR_DUAL_COMPLETE_WHEEL_SMOKE_PLAN_REVIEW` 结束。不得继续 implementation/test、stage、commit、push、PR或 R12。

AUTHORIZED_R11_I2_WHEEL_SMOKE_PLAN_FIX_ONLY
