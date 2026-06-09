# WU-TOOLS-01-F01-02 Draft PR Gate Blocked

## Metadata

- Work unit: `WU-TOOLS-01-F01-02`
- Gate: push / create draft PR
- Branch: `work/wu-tools-01-f01-02-cancellation`
- Remote: `github` (`https://github.com/noho/dayu-agent-r.git`)
- Date: 2026-06-08

## Local State

Local gates completed:

- Accepted plan commit: `af3ac6b8`
- Slice 1 accepted commit: `872a809e`
- Slice 2 accepted commit: `f7cd11a9`
- Slice 3 accepted commit: `6cc2ffca`
- Slice 4 accepted commit: `bc919866`
- Slice 5 accepted commit: `68f5fd40`
- Accepted deepreview commit: `627b2ca9`
- Ready-to-open draft PR bookkeeping commit: `c926c53e`

The local worktree was clean before the first push attempt.

## Blocking Evidence

Push attempt:

```bash
git push -u github work/wu-tools-01-f01-02-cancellation
```

Result:

```text
fatal: unable to access 'https://github.com/noho/dayu-agent-r.git/': LibreSSL SSL_connect: SSL_ERROR_SYSCALL in connection to github.com:443
```

Escalated push retry produced the same result.

Connectivity check:

```bash
curl -I https://github.com
```

Result:

```text
curl: (35) LibreSSL SSL_connect: SSL_ERROR_SYSCALL in connection to github.com:443
```

GitHub CLI auth check:

```bash
gh auth status
```

Result:

```text
The token in keyring is invalid.
To re-authenticate, run: gh auth refresh -h github.com
```

SSH probe:

```bash
ssh -T git@github.com
```

Result:

```text
Connection closed by 198.18.1.89 port 443
```

## Controller Decision

Draft PR gate is blocked by external GitHub connectivity and local GitHub CLI authentication state. No code, test, review, or control-doc finding remains open locally.

Do not recreate the branch through GitHub contents APIs because that would lose the accepted local commit chain referenced by the control document. The correct continuation is to restore GitHub HTTPS connectivity and valid GitHub authentication, then push the local branch as-is and create a draft PR from that branch.

## Resume Entry Point

After network/auth is restored:

```bash
git push -u github work/wu-tools-01-f01-02-cancellation
gh pr create --draft --base main --head work/wu-tools-01-f01-02-cancellation
```

Then update `docs/host/issues-implementation-control.md` with the draft PR URL and continue PR review gates.
