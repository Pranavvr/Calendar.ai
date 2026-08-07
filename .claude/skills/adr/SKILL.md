---
name: adr
description: Write or update an Architecture Decision Record for cal-ai. Use when a design choice is made that a reader would otherwise question — infrastructure topology, auth mechanism, cost tradeoff, or anything where the obvious option was rejected.
---

# Architecture Decision Records

An ADR captures **why** a choice was made, so the reasoning survives after the person who
made it has forgotten. For this project they serve a second purpose: they are the artifact
that makes design choices defensible in an interview. A reader who disagrees with the
decision should still come away thinking it was made deliberately.

Records live in `docs/adr/`, numbered and kebab-cased:
`docs/adr/0003-cloudfront-for-https.md`

## Format

```markdown
# ADR NNNN — <decision, stated as a choice not a topic>

**Status:** Accepted | Superseded by ADR NNNN
**Date:** YYYY-MM-DD

## Context

The constraint that forced a decision. What was true about the system, the budget, or an
external dependency that made this a real fork rather than an obvious default. Be concrete
and quantified — "a NAT gateway is ~$32/mo against a ~$40/mo total budget" beats "cost was
a concern."

## Options

Each option that was genuinely on the table, with its actual drawback. If an option was
never really viable, leave it out rather than padding the list.

## Decision

What was chosen, in one or two sentences.

## Consequences

What this costs. State the downside plainly — an ADR that lists only benefits is marketing,
and a reader will notice. Include what is now harder or foreclosed.

## What would change this

The condition under which the decision should be revisited: a user count, a cost threshold,
a second engineer, a compliance requirement. **This section is the most important one.** It
demonstrates the decision was scoped rather than guessed, and it is the thing an interviewer
probes for.
```

## Rules

- One decision per record. If it needs "and", it is two ADRs.
- Write in past tense about the decision, present tense about consequences.
- Never rewrite an accepted ADR to reflect a new decision. Write a new one and mark the old
  `Superseded by ADR NNNN`. The superseded record stays — the fact that you changed your
  mind, and why, is itself valuable.
- Quantify. Dollar figures, latencies, instance sizes, request counts.
- No decision is too small if a reader would otherwise ask "why on earth did you do that."
- Do not invent rationale. Much of the reasoning for this project already exists in code
  comments and commit messages — go read those first and transcribe faithfully. If the real
  reason was "it was cheapest and this is a portfolio project," write that. Honest beats
  impressive.

## Records to write for cal.ai

Sourced from decisions already made and visible in the code. Roughly descending order of
how likely each is to be questioned:

1. **Account-per-environment topology** — why resource names are deliberately un-suffixed
   (the AWS account is the namespace), and why a second environment means a second account
   rather than name prefixes in one.
2. **CloudFront in front of the ALB for HTTPS** — Google requires HTTPS redirect URIs for
   sensitive scopes; the default `*.cloudfront.net` certificate avoids buying a domain.
   See the comment block at the top of `terraform/cloudfront.tf`.
3. **Synchronous `/schedule` with a 60s origin timeout** — versus a 202-plus-polling job
   queue. Note that 60s is CloudFront's maximum without a quota increase, and that agent
   runs take 40–60s, so the ceiling sits uncomfortably close to expected latency.
4. **The default VPC, no NAT gateway** — cost, and what it forecloses (private subnets).
5. **JWT in an httpOnly cookie** — versus server-side sessions; the revocation tradeoff.
6. **Refresh tokens in Postgres** rather than Secrets Manager per user — cost and quota
   reasoning, and what encryption is and is not in place.
7. **Tools closed over a per-user Calendar client** — why user identity is bound outside
   the model's reach, and what class of prompt-injection attack that eliminates.
8. **Pinning ruff, and CI dependency pinning generally** — prompted by a real incident
   where ruff 0.16 expanded its default rule set and turned CI red with no code change.

Number them in the order written, not the order listed here.
