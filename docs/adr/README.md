# Architecture Decision Records

Why things are the way they are. A reader who disagrees with a decision should still
come away confident it was made deliberately.

Each record states the constraint that forced a choice, the options that were genuinely
on the table, what was chosen, what it costs, and — the section that matters most — **what
would change the decision**. A decision without a revisit condition is a guess.

| # | Decision | Uncomfortable part |
| --- | --- | --- |
| [0001](0001-account-per-environment.md) | Environments are separate AWS accounts, so names carry no environment suffix | No dev environment exists; changes go local → production |
| [0002](0002-cloudfront-for-https.md) | CloudFront fronts the ALB purely to get HTTPS | Opaque URL, manual OAuth redirect update, 60s origin ceiling |
| [0003](0003-synchronous-schedule-endpoint.md) | `POST /schedule` is synchronous | The timeout sits *at* expected latency, not above it |
| [0004](0004-default-vpc-no-nat.md) | Default VPC, public subnets, no NAT gateway | Tasks hold public IPs; a security group is the only barrier |
| [0005](0005-jwt-session-cookie.md) | Session is a JWT in an httpOnly cookie | No revocation before expiry; rotating the secret logs everyone out |
| [0006](0006-encrypted-refresh-tokens-in-postgres.md) | Refresh tokens in Postgres, encrypted at the column level | Key rotation forces every user to re-authorize |
| [0007](0007-tools-closed-over-per-user-client.md) | Tools close over a pre-authorized client; the model never sees identity | A token refresh round-trip on every request |
| [0008](0008-pin-all-dependencies.md) | All dependencies locked to exact versions | Security updates need a deliberate bump; no Dependabot yet |
| [0009](0009-in-process-rate-limiting.md) | Rate limiting is in-process | Correct only while `desired_count` is 1 |
| [0010](0010-evals-score-final-calendar-state.md) | Evals score the calendar, not the model's description | Costs money, so behaviour regressions are not caught in CI |

## Conventions

- One decision per record. If it needs "and", it is two records.
- Never rewrite an accepted record to reflect a new decision. Write a new one and mark the
  old `Superseded by ADR NNNN`. That you changed your mind, and why, is the valuable part.
- Quantify. Dollar figures, latencies, instance sizes.
- State the downside plainly. A record listing only benefits is marketing, and a reader
  will notice.

Written with the `adr` skill in [.claude/skills/adr/](../../.claude/skills/adr/SKILL.md).
