# M4.3E — Evidence Contract and Evidence Gaps

## Architectural boundary

> Helix may consume and reason over infrastructure telemetry at arbitrary depth, but it does not duplicate the infrastructure collection capabilities of an ASM platform. Limited collection is permitted only for zero-knowledge bootstrap necessary to establish initial ASM seeds.

Helix owns corporate intelligence, evidence normalization/correlation, attribution decisions, evidence gaps, and advisory analyst reasoning. ASM/customer systems own infrastructure collection. Helix can consume all supplied telemetry.

## Initial evidence waterfall
1. RDAP / WHOIS
2. IP / ASN ownership
3. TLS certificate
4. HTTP legal/privacy/operator evidence

This order describes attribution efficacy, not a requirement that Helix fetch these sources.

## Trust rule
An evidence request is not evidence. An LLM suggestion is not evidence. Neither may become a recursive pivot. Only observations evaluated by deterministic attribution policy can create trusted facts.

## NTT checkpoint
Preserve the September 2026 NTT zero-knowledge run as baseline. After ASM evidence ingestion and evidence-gap integration, rerun progressively with supplied RDAP/WHOIS, ASN, certificate, HTTP/legal/privacy, then advisory LLM analysis.
