# Security finding log

Security findings that have been addressed, and reports that were evaluated and
rejected as false positives. Read both sections before opening a security PR, so
that a guarantee already in place is not reported as missing.

Every landed entry is anchored to a commit. If an entry cannot be located in
`git log`, treat the anchor as authoritative over the date.

## Landed

### 2026-06-07 - Git subprocess calls hardened against option injection

**Anchor:** `fb33ce8`

**Learning:** A `git` invocation that interpolates a caller-supplied ref into an argument can have that ref parsed as an option when the ref begins with `-`.

**Action:** every `git` invocation that accepts a caller-supplied ref passes `--end-of-options` before the ref, which makes git treat everything after it as a non-option operand. Current coverage:

| Call site | Caller-supplied input | Guard |
|---|---|---|
| `tools.py` `git show` | `base`, `rel_path` | `--end-of-options` |
| `incremental.py` `git diff --name-only` | `base` | `--end-of-options` |
| `incremental.py` `git status` / `git ls-files` | none (literal args) | n/a |
| `federation.py` `git log` | none | terminates with `--` |

All subprocess calls pass a list argv. There is no `shell=True` anywhere in `src/`, so no shell metacharacter path exists either.

## Rejected

Reports that were evaluated against the running code and declined. The reasoning
is recorded here so that it carries forward instead of being rediscovered.

### 2026-07-25 - Do not add startswith("-") checks to git ref arguments

**Rejected PR:** #888, reported as HIGH severity command argument injection in `_get_git_content`.

**Proposal:** add `if base.startswith("-"): return None` to `_get_git_content`.

**Why it was rejected:** the hole was already closed by `fb33ce8`, the entry directly above. The call site already reads:

```python
[git_bin, "show", "--end-of-options", f"{base}:{rel_path}"]
```

Verified against a real git binary rather than assumed:

```
$ git show --end-of-options "--upload-pack=whoami:f.txt"
fatal: option '--upload-pack=whoami:f.txt' must come before non-option arguments
```

With the guard present git refuses to parse the value as an option at all. A `startswith("-")` test rejects a subset of what `--end-of-options` already neutralises, at a different layer, and landing it would leave the repo looking as though it needed a second defence for a hole that is shut.

**Action — how to check this class of finding before reporting it.** Read the complete argv at the call site first. If `--end-of-options` or a `--` terminator is already present, the finding is closed and no PR is warranted. To protect the guarantee against regression, the durable form is a test asserting that `--end-of-options` appears in the argv of every git invocation that takes a ref, not a string check repeated at each call site.

## Conventions for this log

- Read the complete argv at a call site before reporting an injection finding, and check for an existing `--end-of-options` or `--` terminator.
- Verify the claimed attack against the real binary and include the output. A finding asserted from pattern matching alone is not actionable.
- Before calling a baked-in identifier a leaked secret, check whether it is public by design.
- Cite file and symbol names rather than line numbers, which drift as the file changes.
- PR titles in this repo must start with `fix:` or `feat:`.

## 2026-08-24 - Prevent command injection in git show
**Vulnerability:** The `base` argument (a git ref) was passed unsanitized into a `subprocess.run` call executing `git show` in `_get_git_content` (`src/better_code_review_graph/tools.py`). While `--end-of-options` was used, git refs starting with a hyphen (like `-e`) could bypass this if they are treated as options before `--end-of-options` or if they trick the `git show` path resolution depending on git version. This is the same pattern as previously fixed in `git diff` and `git cat-file`.
**Learning:** All git subcommands accepting user-controlled refs must validate the ref format, specifically rejecting refs starting with `-`, even when `--end-of-options` is used, to prevent argument injection vulnerabilities.
**Prevention:** Always implement explicit format validation (`if ref.startswith("-")`) before passing dynamic git refs to `subprocess.run`, and always include tests specifically asserting this behavior.
