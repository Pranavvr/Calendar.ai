# ADR 0004 — Default VPC with public subnets, no NAT gateway

**Status:** Accepted
**Date:** 2026-08-14

## Context

Fargate tasks need outbound internet access to reach OpenAI, Google, ECR, and Secrets
Manager. The textbook layout puts tasks in private subnets behind a NAT gateway.

A NAT gateway costs roughly $32/month in `us-east-1` before data processing charges. The
entire stack targets $28-43/month. NAT alone would be the single largest line item and
would roughly double the bill.

## Options

**Custom VPC, private subnets, NAT gateway.** The correct production answer. Tasks have
no public IP and no inbound path from the internet at all.

**Custom VPC, private subnets, VPC endpoints instead of NAT.** Endpoints cover ECR, S3,
Secrets Manager, and CloudWatch, but not OpenAI or Google — those are third-party
internet endpoints, so NAT is still required. Endpoints would reduce data charges, not
remove the gateway.

**Default VPC, public subnets, tasks with public IPs, restricted by security group.**
Free. Tasks are addressable from the internet at the IP level, with the security group as
the only barrier.

## Decision

Use the account's default VPC. Tasks run in public subnets with `assign_public_ip = true`,
and inbound is restricted by security group to port 8000 from the ALB's security group
only.

## Consequences

Tasks have public IP addresses. Nothing can reach them except via the ALB security group,
but the barrier is a single security group rule rather than the absence of a route. A
misconfigured rule is immediately internet-exposed, where in a private subnet it would
not be.

There is no network isolation story to describe. This project cannot claim
defence-in-depth at the network layer, and should not pretend to.

The database is the part that mattered most, and it is handled separately: RDS is
`publicly_accessible = false` and reachable only from the task security group, so the
weakest link is not the data store.

Using the *default* VPC additionally means depending on account-level state Terraform does
not manage. If the default VPC were deleted, the configuration breaks.

## What would change this

Handling anyone else's data, any compliance requirement, or a second environment where
$32/month is marginal against the total. The migration is not trivial — new VPC, subnets,
route tables, NAT, and RDS moves to a new subnet group — so this is a decision worth
revisiting before the resource count grows rather than after.
