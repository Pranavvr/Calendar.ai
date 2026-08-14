# ADR 0001 — Environments are separate AWS accounts, so resource names carry no environment suffix

**Status:** Accepted
**Date:** 2026-08-14

## Context

Every resource name in `terraform/` derives from `var.project_name` — `cal-ai-cluster`,
`cal-ai-db`, `cal-ai-alb`, and so on. None carries a `-prod` or `-dev` suffix.

That looks like an oversight, and it needs to be either justified or fixed, because
it determines what adding a second environment costs later.

The relevant fact: all of these namespaces are scoped **per account per region**, not
globally. There is no S3 bucket anywhere in the configuration, which is the usual
resource whose name is globally unique.

## Options

**One account, environment-prefixed names** (`cal-ai-dev-cluster` vs `cal-ai-prod-cluster`).
Cheapest to set up, no cross-account plumbing. But isolation is only as good as the IAM
policies, which are easy to get wrong, and cost separation depends on tagging discipline
holding forever.

**Account per environment.** AWS's own recommended topology, via Organizations. Because
the account is the namespace, identical names coexist and the same Terraform targets a
different environment by pointing at a different account. Overhead is real: account
provisioning, cross-account roles, centralised logging.

**One account, one environment.** What exists today, without admitting it.

## Decision

Structure for account-per-environment. Resource names are deliberately un-suffixed, and
`var.aws_profile` is the seam that selects the target account.

Only production is actually deployed. A second environment would be a second account
plus a second tfvars file, with no code change.

## Consequences

Environment isolation is structural rather than policy-based: a dev credential cannot
reach production, because IAM is account-scoped. Blast radius is bounded — a `destroy`
against the wrong target cannot cross an account boundary. Quotas and cost attribution
separate for free.

The cost is that there is no dev environment today, so changes are tested locally and
then in production. For a single developer tearing down nightly, that is acceptable; for
anyone else it would not be.

`Environment` is still a hardcoded tag value rather than a variable. That is the one
loose end.

## What would change this

A second engineer, or needing a staging environment that survives long enough to demo.
Either makes the second account worth provisioning. If cost pressure ever made a second
account unjustifiable, the fallback is prefixed names in one account — and that migration
means renaming live resources, which for RDS identifiers means replacement.
