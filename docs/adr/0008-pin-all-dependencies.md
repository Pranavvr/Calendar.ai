# ADR 0008 — All dependencies are locked to exact versions

**Status:** Accepted
**Date:** 2026-08-14

## Context

`requirements.txt` listed 18 packages with no version constraints. Every build resolved
whatever was current at that moment, so the image built today was not the image built next
month.

This was not theoretical. CI went red with no code change: `pip install ruff` picked up
0.16.1, which had promoted isort, flake8-datetimez, and pyupgrade rules into its default
rule set. Two pre-existing files that no branch had touched suddenly failed lint, and
`main` was broken by an upstream release.

Lint is the harmless version of this. The same surprise from `langchain` or `fastapi`
breaks production.

## Options

**Stay unpinned.** Zero maintenance, and you get security patches automatically. Also
means no build is reproducible and any upstream release can break you at any time.

**Pin direct dependencies only.** Fixes the obvious case, leaves transitive dependencies
free to move. Since most of the tree is transitive, most of the risk remains.

**Full lockfile.** Every transitive dependency pinned. Reproducible. Requires a deliberate
step to take any update, including security updates.

## Decision

Full lockfiles. Direct dependencies are declared in `requirements.in` and
`requirements-dev.in`; the `.txt` files are generated and pin the complete closure — 70
packages for production, 6 for dev.

CI reads the ruff pin out of the lockfile rather than repeating it, so the version exists
in exactly one place.

## Consequences

A build is reproducible, and the environment can be reconstructed from the lockfiles. That
mattered sooner than expected: a `git reset --hard` across the commit that untracked
`.venv` deleted the virtualenv, and it was rebuilt from the lockfiles rather than
reconstructed by guesswork.

Splitting prod from dev also made the real dependency surface visible, which surfaced three
packages that were installed but never imported — `langchain-anthropic`, the `langchain`
umbrella, and `google-auth-oauthlib`, left over from the desktop-OAuth flow that Authlib
replaced. They had been invisible partly because 12,307 vendored `.venv` files were tracked
in git, drowning any signal.

**Security updates now require a deliberate bump.** Nothing tells us a pinned package has
a CVE. This is the real cost of the decision and it is currently unmitigated.

`jupyter` is excluded from the dev lock as well as the prod one: notebooks are gitignored
personal notes, CI never runs them, and locking it added ~60 packages to every CI install.

`pip-tools` is deliberately not in the lock, since locking the tool that generates the lock
with itself is circular.

## What would change this

Adding Dependabot or Renovate, which is the missing half of this decision — pinning
without automated update PRs trades one risk for another. That is the obvious next step,
and it is not done.
