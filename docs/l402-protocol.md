# Payment Protocol Reference — L402, X402, MPP

The `fetch` command in `nwc_wallet.py` automatically detects and handles three
HTTP 402 payment protocols. No flags needed — pass the URL and the dispatcher
figures out which protocol to use.

## Protocol Comparison

| Protocol | Challenge Header | Auth Header | Spec |
|----------|-----------------|-------------|------|
| **L402** | `WWW-Authenticate: L402 token=..., invoice=...` | `Authorization: L402 <macaroon>:<preimage>` | LSAT |
| **X402** | `PAYMENT-REQUIRED: <base64-JSON>` | `payment-signature: <base64-JSON>` | X402 |
| **MPP** | `WWW-Authenticate: Payment method="lightning" intent="charge" ...` | `Authorization: Payment <JCS-credential>` | draft-lightning-charge-00 |

## L402 (Lightning Service Authentication Token)

The most common protocol. Used by the Smart Wikipedia and Weather Intel proxies,
among others.

### Flow

1. Client requests a protected resource
2. Server responds with `402 Payment Required` + `WWW-Authenticate: L402 token=<macaroon>, invoice=<bolt11>`
3. Client extracts the bolt11 invoice and pays it via NWC wallet
4. Client retries the request with `Authorization: L402 <macaroon>:<preimage>`
5. Server validates the preimage against the paid invoice, grants access

### Credential Reuse

After the first successful `fetch`, the macaroon and preimage are valid for
all subsequent requests to the same proxy until the macaroon expires. **Do not
call `fetch` repeatedly** — use `curl` with the saved credentials:

```bash
# First request: pay once
RESULT=$(python3 scripts/nwc_wallet.py fetch "https://proxy.example.com/resource")

# Extract credentials
PREIMAGE=$(echo "$RESULT" | jq -r '.preimage')
MACAROON=$(echo "$RESULT" | jq -r '.macaroon')

# All subsequent requests: reuse (no new payment)
curl -s "https://proxy.example.com/resource?topic=bitcoin" \
  -H "Authorization: L402 ${MACAROON}:${PREIMAGE}"
```

### Endpoint Instructions

Many L402 proxies include an `instructions` block in the 402 response body
specifying the exact auth header format. The `fetch` command handles this
automatically, but if reusing credentials manually, match the format from the
instructions.

### Known Proxies

| Proxy | Endpoint | Pricing | Notes |
|-------|----------|---------|-------|
| Smart Wikipedia | `/wiki/{article}` | 2 sats | Returns curated article summaries |
| Weather Intel | `/weather/{location}` | 1 sat | Current conditions + forecast |

See `references/lightningenable-l402-proxies.md` in the skill directory for
detailed endpoint documentation, quirks, and sample responses.

## X402

An alternative 402 protocol using base64-encoded JSON challenges.

### Flow

1. Client requests a protected resource
2. Server responds with `402 Payment Required` + `PAYMENT-REQUIRED: <base64-JSON>`
3. Client decodes the JSON, finds the `lightning` entry in payment methods
4. Client pays the invoice from the lightning entry
5. Client retries with `payment-signature` header containing base64-encoded proof

### Amount Verification

X402 includes the expected amount in the `PAYMENT-REQUIRED` body. The client
verifies the invoice amount matches before paying. If there's a mismatch, the
payment is aborted — this is a server-side issue that should be reported.

## MPP (Multi-Party Payments)

Based on the `draft-lightning-charge-00` specification. Uses JCS (JSON
Canonicalization Scheme) credentials.

### Flow

1. Client requests a protected resource
2. Server responds with `WWW-Authenticate: Payment method="lightning" intent="charge" ...`
3. Client decodes the base64url-encoded challenge
4. Client pays the invoice from the challenge
5. Client constructs a JCS credential and retries with `Authorization: Payment <credential>`

## Protocol Detection

Detection is fully automatic in `scripts/nwc_fetch.py`:

```python
# The dispatcher checks response headers in order:
# 1. WWW-Authenticate with "L402" → L402 handler
# 2. PAYMENT-REQUIRED header → X402 handler
# 3. WWW-Authenticate with "Payment" + "lightning" → MPP handler
```

If the server returns a 402 with no recognized payment protocol (e.g., USDC or
ETH-based 402), `fetch` reports "no supported payment protocol" — only
Bitcoin/Lightning payments are supported.

## Debugging Payment Flows

To inspect raw 402 responses and diagnose payment issues:

```bash
# See raw challenge headers
curl -s -i "https://proxy.example.com/resource"

# Use fetch with debug to see protocol detection
python3 scripts/nwc_wallet.py --debug fetch "https://proxy.example.com/resource"
```

See `references/debugging-l402-flows.md` in the skill directory for a complete
troubleshooting guide covering common issues: reused invoices, expired
macaroons, amount mismatches, and credential persistence.
