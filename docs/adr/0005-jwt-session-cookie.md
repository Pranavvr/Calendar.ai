# ADR 0005 — Session is a JWT in an httpOnly cookie, with no revocation

**Status:** Accepted
**Date:** 2026-08-14

## Context

After Google OAuth completes, the browser needs to stay signed in. The session must
survive page loads and identify the user on `/me` and `/schedule`.

## Options

**JWT in an httpOnly cookie.** Stateless: no database read to authenticate a request.
Signed with HS256 so tampering is detectable. But a JWT is valid until it expires — there
is no server-side record to invalidate.

**Server-side sessions in Postgres.** A session row per login, revocable instantly by
deleting it. Costs a database read on every authenticated request and a table to expire.

**JWT in `localStorage`.** Convenient for a JavaScript client, and readable by any script
on the page, which makes XSS directly equivalent to account takeover. Rejected outright.

## Decision

A JWT in an httpOnly, `SameSite=Lax`, `Secure` cookie. HS256, 7 day TTL, signed with
`JWT_SECRET` from Secrets Manager. The cookie name is distinct from Starlette's OAuth
state cookie.

## Consequences

**A session cannot be revoked before it expires.** `POST /auth/google/logout` clears the
cookie in that browser, but the token itself stays valid for up to 7 days — a copy taken
beforehand still works. For a personal calendar app the exposure is bounded and accepted;
for anything multi-tenant it would not be.

`SameSite=Lax` means the cookie is not sent on cross-site POSTs, which covers CSRF on
`/schedule` without a token scheme.

`Secure` defaults to on and is only disabled explicitly for local HTTP. The default is
deliberately the safe direction: forgetting to enable it in production sends a 7-day
calendar-access token in cleartext, while forgetting to disable it locally merely means
sign-in does not work on `localhost`.

`logout` must delete the cookie with the same attributes used to set it. Without that the
browser treats it as a different cookie and the session survives logout — an easy and
silent bug.

Rotating `JWT_SECRET` signs everyone out. That is the only available revocation
mechanism, and it is all-or-nothing.

## What would change this

Needing to revoke one user immediately — a compromised account, an abuse ban, a breach
response. The natural next step is a short-lived access token plus a refresh token with a
server-side record, which keeps most of the statelessness while making revocation
possible. A second user other than the developer would be enough to justify it.
