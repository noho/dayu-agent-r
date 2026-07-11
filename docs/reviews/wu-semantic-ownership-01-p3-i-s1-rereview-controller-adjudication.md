# WU-SEMANTIC-OWNERSHIP-01 P3-I S1 re-review controller adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P3-I - Public CLI/package entrypoints and terminal display watermark`
- Slice: `S1 - Public Package Entrypoints And README Truth`
- Gate: re-review controller adjudication
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-i-s1-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-i-s1-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-i-s1-rereview-ds.md`

## Controller decision

P3-I S1 re-review is accepted.

AgentMiMo and AgentDS both returned `pass`. Both verified:

- DS F1 is closed.
- The duplicate `_normalize_system_exit_code` implementations in `dayu.web`, `dayu.wechat`, and `dayu.render` were replaced by the layer-neutral `dayu.runtime.argparse_exit.normalize_argparse_system_exit_code`.
- The new runtime helper is typed, standard-library-only, and does not import Host / Engine / Service / UI / Fins.
- Public entrypoint behavior remains unchanged.
- `dayu/cli/main.py` keeps a separate helper with different semantics (`None -> 0`, non-int -> 1), so it is not an unclosed duplicate of the argparse-specific helper.
- No new material findings were introduced.

## Accepted finding status

| Finding | Status |
| --- | --- |
| DS F1 - `_normalize_system_exit_code` repeated across three package entrypoint modules | closed |

## Validation accepted

The controller accepts the following validation evidence:

- Focused public entrypoint tests: `12 passed`.
- Module help smoke for `python -m dayu.web --help`, `python -m dayu.wechat.main --help`, and `python -m dayu.render.render --help`: exit `0`.
- Console script help smoke for `dayu-web --help`, `dayu-wechat --help`, and `dayu-render --help`: exit `0`.
- Pyright over `dayu/ tests/ utils/`: `0 errors`.
- `git diff --check`: clean.
- README audit for `dayu-web|dayu-wechat|dayu-render`: all hits are truthful or explicitly unavailable.

## Residual risks

- Full Web UI, WeChat login/daemon/service, and Markdown render conversion remain unimplemented by design for S1.
- `dayu.render` package-data resource files remain deferred until a future real renderer owner provides actual assets.

## Next gate

Proceed to accepted S1 commit, then P3-I S2 implementation by AgentCodex.
