# Security policy

## Reporting a vulnerability

Please report vulnerabilities through GitHub's private security advisory feature rather than a
public issue. Include affected versions, reproduction steps, and the potential impact when
possible.

## Operational guidance

The stdio transport is the safest default for local use. Keep HTTP transports bound to loopback
when possible. Any remote deployment should use `MCP_API_KEY`, TLS, and network access controls;
the API key is not a replacement for either TLS or a firewall. Grant the Azure identity and
Microsoft Graph application only the permissions required for the intended tools.

The HTTP transports authenticate callers with a single shared bearer token (`MCP_API_KEY`) and
validate browser origins against `CORS_ALLOWED_ORIGINS`. This server is not an OAuth resource
server, so the authorization changes in the 2026-07-28 MCP specification — issuer validation per
RFC 9207, and Client ID Metadata Documents replacing Dynamic Client Registration — do not apply
to it. Rotate `MCP_API_KEY` on the same schedule you would use for any other shared secret, and
terminate TLS in front of the server so the token is never sent in the clear.
