# ADR 0006 — Google refresh tokens live in Postgres, encrypted at the column level

**Status:** Accepted
**Date:** 2026-08-14

## Context

The agent acts on a user's calendar in response to a request, so it needs durable
authorization. Google supplies a refresh token, obtained with `access_type=offline`.

That token grants read/write access to a real person's calendar and **does not expire**.
It is the most sensitive value the system holds — more sensitive than the session JWT,
which at least ages out in 7 days.

## Options

**One Secrets Manager secret per user.** Purpose-built, audited, rotatable. At $0.40 per
secret per month it makes per-user cost scale with headcount, and it puts a network call
in the path of every agent run.

**Plaintext column in Postgres.** What existed. RDS `storage_encrypted = true` protects
the disk, which sounds sufficient until you consider that it only defends against someone
stealing the physical volume. Any path that can *read the table* — SQL injection, a leaked
read-only credential, a snapshot restored into another account — yields directly usable
tokens.

**Encrypted column in Postgres.** Application-level encryption with a key held outside the
database. A database read alone is no longer enough.

**KMS envelope encryption.** A KMS-managed data key per record. Strongest option, with
CloudTrail audit trail per decrypt. Adds ~$1/month per key plus per-request charges and a
KMS call in the request path.

## Decision

Store tokens in Postgres, Fernet-encrypted at the column level. Fernet comes from
`cryptography`, already a transitive dependency, so this added no package.

The key is a separate Secrets Manager secret from `JWT_SECRET`, injected as
`TOKEN_ENCRYPTION_KEY`.

## Consequences

Reading the table is no longer sufficient to use a token — an attacker needs the database
*and* the key, which live behind different IAM permissions.

Two secrets rotate independently, which is the point of separating them: rotating session
signing should not invalidate every stored calendar authorization, and vice versa.

Fernet includes a random IV, so identical tokens produce different ciphertexts. Equal
values in the column therefore cannot reveal that two rows share a token.

Decryption is deliberately strict, with no fallback to treating an unreadable value as
plaintext. Such a fallback is the obvious convenience for migrating existing rows, and it
would turn a key problem into an undetected downgrade to plaintext. No database with
plaintext tokens exists, so nothing needed migrating.

**Rotating `TOKEN_ENCRYPTION_KEY` makes every stored token undecryptable** and forces all
users to sign in again. There is no key-versioning scheme, so rotation is a user-visible
event.

There is no per-decrypt audit trail. KMS would give one; Fernet does not.

## What would change this

A compliance requirement for audited key usage or hardware-backed keys, which means KMS.
Also: if key rotation ever needed to be routine rather than exceptional, a version prefix
on the ciphertext would be required so two keys can be valid at once.
