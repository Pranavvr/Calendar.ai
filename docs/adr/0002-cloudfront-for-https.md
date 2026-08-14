# ADR 0002 — CloudFront fronts the ALB purely to obtain HTTPS

**Status:** Accepted
**Date:** 2026-08-14

## Context

Google's OAuth requires HTTPS on redirect URIs when the requested scopes are sensitive.
The Calendar scope is sensitive, so plain HTTP is not an option — sign-in simply fails.

ACM issues free certificates, but only for domains you control, and no domain was owned.

## Options

**Buy a domain, use Route 53 and ACM.** The conventional answer. Roughly $12/year for the
domain plus $0.50/month for the hosted zone, and a clean URL. Against a budget where the
whole stack targets under $40/month, and for a project torn down most of the time, the
recurring hosted-zone cost buys nothing but aesthetics.

**CloudFront with its default `*.cloudfront.net` certificate.** Free, no domain required,
TLS terminated at the edge.

**Self-signed certificate on the ALB.** Google rejects it.

## Decision

CloudFront in front of the ALB, using the default certificate. Traffic is
browser → HTTPS → CloudFront → HTTP → ALB → HTTP → task, with TLS terminated at the edge
and the backend legs staying inside AWS.

## Consequences

The public URL is an opaque `dXXXXX.cloudfront.net`, which is ugly and changes if the
distribution is recreated — and the Google OAuth redirect URI has to be updated by hand
when it does. That manual step is called out in `deploy.sh`.

CloudFront's origin read timeout caps at 60 seconds without a quota increase, which
directly constrains how long an agent run may take. See ADR 0003.

Fronting with CloudFront also created a bypass: the ALB's own DNS name remained reachable
over plain HTTP, so TLS could be skipped entirely. That is not a consequence of choosing
CloudFront so much as a gap it introduced, and closing it required restricting the ALB to
CloudFront's prefix list plus a shared secret header.

An extra network hop is added, which for a 40-60s request is noise.

## What would change this

Buying a domain — at which point ACM plus Route 53 is strictly better and the ugly URL,
the manual redirect-URI step, and the 60s ceiling all go away. Also: needing a WAF
attached at the ALB, or needing request timeouts above 60s.
