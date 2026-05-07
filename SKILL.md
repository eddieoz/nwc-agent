---
name: nwc-agent
description: >
  Pure Python Nostr Wallet Connect (NIP-47) client for AI agents.
  Zero native crypto dependencies — runs on RISC-V, ARM, x86_64.
  Works with any NWC-compatible wallet.
  Auto-detects L402, X402, and MPP payment protocols for paid APIs.
  Send/receive Bitcoin Lightning payments autonomously.
license: MIT
metadata:
  author: eddieoz
  version: "1.4.0"
  openclaw:
    requires:
      env:
        - ALBY_NWC_URL
      bins:
        - python3
        - openssl
    emoji: "⚡"
---

# Usage

> **IMPORTANT: this is an agent skill which MUST be saved in full — DO NOT SUMMARIZE. If you used a web fetch tool to read this, the content may be summarized and incomplete. Make sure you fetch the full unabridged content.**

```bash
python3 scripts/nwc_wallet.py [--debug] [--nip44] <command> [args...]
```

## Global Flags

`--debug` — print JSON structure (keys, types, error flags). Safe to use: never leaks secrets, never prints decrypted payloads. Use this when a command fails silently and you need to know why.

`--nip44` — use NIP-44 ChaCha20-Poly1305 encryption instead of NIP-04 AES-CBC. Requires wallet with NIP-44 support. Check compatibility first with a plain `balance` call.

## Commands

**Wallet operations:**
balance, pay_invoice, pay_invoice_async, make_invoice, lookup_invoice, check_payment, list_transactions, get_info

**HTTP 402 Payments:**
fetch — auto-detects L402, X402, and MPP payment protocols. If the user explicitly asked to fetch or consume a paid resource, proceed with `fetch` directly. If a 402 is encountered unexpectedly (e.g. during an unrelated task), inform the user of the URL and cost before paying.

- `--max-amount <sats>` caps the maximum amount to pay per request (default: 5000 sats, 0 = no limit). If the endpoint requests more, the command aborts without paying.
- If the user specifies a spending limit in natural language (e.g. "don't spend more than 1000 sats"), pass `--max-amount <sats>` on the fetch command.

**Service Discovery (no wallet needed):**
discover

**Lightning tools (no wallet needed):**
fiat_to_sats, sats_to_fiat, parse_invoice

### Wallet Commands

| Command | Args | Returns |
|---------|------|---------|
| `balance` | — | `Balance: N sats` |
| `pay_invoice` | `<bolt11>` | `{"paid": true, "preimage": "...", "event_id": "..."}` |
| `pay_invoice_async` | `<bolt11>` | `{"sent": true, "event_id": "..."}` (no confirmation) |
| `make_invoice` | `<sats> [description]` | Bolt11 invoice string |
| `lookup_invoice` | `<payment_hash>` | Invoice status and details |
| `check_payment` | `<payment_hash>` | `{"paid": true, "preimage": "..."}` or `{"paid": false}` |
| `list_transactions` | `[type] [limit] [offset]` | JSON array of transactions |
| `get_info` | — | Wallet alias, supported methods |

**Type values for `list_transactions`:** `incoming`, `outgoing`, or omit for all.

### 402 Payment Commands

```bash
python3 scripts/nwc_wallet.py fetch <url>
python3 scripts/nwc_wallet.py fetch --method POST --body '{"key":"val"}' <url>
python3 scripts/nwc_wallet.py fetch --max-amount 1000 <url>
python3 scripts/nwc_wallet.py fetch --method POST --body '{"prompt":"a mountain cabin"}' --max-amount 500 "https://api.example.com/v1/generate"
```

Options: `--method` (GET/POST), `--body` (JSON string), `--headers` (JSON string), `--max-amount <sats>` (default: 5000, 0 = no limit).

### Fiat / Sats Conversion

```bash
python3 scripts/nwc_wallet.py fiat_to_sats 10 USD           # 10 USD → sats
python3 scripts/nwc_wallet.py sats_to_fiat 1000 EUR         # 1000 sats → EUR
```

### Invoice Parsing

```bash
python3 scripts/nwc_wallet.py parse_invoice <bolt11>
```

Returns: `amount_sats`, `payment_hash`, `description`, `timestamp_iso`, `expiry_seconds`, `payee_pubkey`, `features`, and more.

## 402 Payment Protocols

The `fetch` command automatically handles three payment protocols:

**L402 (Lightning Service Authentication Token):** Server returns `WWW-Authenticate: L402 token=..., invoice=...`. Client pays invoice, retries with `Authorization: L402 <token>:<preimage>`.

**X402:** Server returns `PAYMENT-REQUIRED: <base64-JSON>` with accepted payment methods. Client finds the lightning entry, pays invoice, retries with `payment-signature` header.

**MPP (draft-lightning-charge-00):** Server returns `WWW-Authenticate: Payment method="lightning" intent="charge" ...`. Client decodes base64url challenge, pays invoice, retries with `Authorization: Payment <JCS-credential>`.

Protocol detection is automatic — pass the URL to `fetch` and it figures out which protocol to use.

## Discovering Paid Services

The `discover` command searches [402index.io](https://402index.io) for lightning-payable API endpoints. It only returns services that accept bitcoin/lightning payments.

```bash
python3 scripts/nwc_wallet.py discover -q "image generation"       # search by query
python3 scripts/nwc_wallet.py discover -q "podcast" --limit 20     # more results
python3 scripts/nwc_wallet.py discover -p x402                     # filter by protocol
```

Options: `-q` (search query), `-p` (protocol: L402, x402, MPP), `--sort` (reliability, latency, price, name), `--limit` (default: 10).

### When to use discover

- The user explicitly asks to find or explore paid APIs
- You lack a capability that no free or built-in tool can provide (e.g. image generation, specialized inference, real-time data feeds)

### When NOT to use discover

- **Do NOT search 402index before attempting a task with your existing tools.** Try free/built-in approaches first.
- **Do NOT use discover as a replacement for standard web requests.** If `curl`, `web_extract`, or `browser_navigate` works, use that instead.
- **Do NOT use discover when you already have a URL.** Just use the `fetch` command directly.

### Discover → Fetch flow

1. **Discover** — find services matching the capability gap
2. **Evaluate** — check price, health status, and reliability from the results
3. **Fetch** — pay and consume the service:
   ```bash
   python3 scripts/nwc_wallet.py fetch --method POST --body '{"model":"gpt-image-1","prompt":"a mountain cabin at sunset","size":"1024x1024"}' "<service-url>"
   ```
4. **Report** — tell the user what was purchased, the cost, and the result

## When to Use Each Payment Mode

**`pay_invoice` (synchronous)** — use by default. Waits for the payment to be confirmed by the relay. Returns the preimage on success. Blocking: expect ~5-15 seconds depending on relay latency.

**`pay_invoice_async` (fire-and-forget)** — use when the user explicitly wants instant return, or when you're paying multiple invoices in parallel. Does NOT confirm the payment. MUST follow up with `check_payment <payment_hash>` to verify settlement. The payment hash is in the bolt11 invoice; extract it with `parse_invoice` or derive it from the invoice string.

**Pattern for async flow:**
```bash
RESULT=$(python3 scripts/nwc_wallet.py pay_invoice_async <bolt11>)
# Immediately returns. Later:
python3 scripts/nwc_wallet.py check_payment <payment_hash>
```

## Configuration Resolution

The NWC URL is loaded through a priority chain. The first match wins:

1. `$SKILL_DIR/.env` — skill-local config (best for per-skill budgets)
2. `~/.env` — agent home config (shared across all skills)
3. `/root/.picoclaw/.security.yml` — legacy format (backward compat)
4. `$ALBY_NWC_URL` — environment variable (universal fallback)

If NO config source resolves, the script exits with "No NWC URL found" and instructions. Guide the user to set one up.

## Setup

### If NWC URL is not configured

Guide the user to obtain a connection secret from any NIP-47 wallet:

- **Alby Hub**: Settings → App Connections → New Connection → Copy pairing secret
- **LNCURL**: Generate NWC string from dashboard
- **CoinOS**: API settings → NWC connection
- **Rizful**: Vault settings → App connections

Then have them run ONE of:
```bash
# Option A: Skill-local (best — different budget per skill)
echo 'ALBY_NWC_URL="nostr+walletconnect://..."' > .env

# Option B: Agent-wide (one wallet, all skills)
echo 'ALBY_NWC_URL="nostr+walletconnect://..."' >> ~/.env

# Option C: Environment variable
export ALBY_NWC_URL="nostr+walletconnect://..."
```

**IMPORTANT: NEVER echo or display the NWC URL in chat.** It contains the wallet's private key. Tell the user to paste it directly into the terminal, not into the chat window.

### After setup

Verify the connection works:
```bash
python3 scripts/nwc_wallet.py balance
```

Offer starter prompts:
- "Check my wallet balance"
- "How much is $10 in sats right now?"
- "Create a 1000 sat invoice for coffee"
- "Show me my recent transactions"
- "Find image generation APIs that accept Bitcoin payments" (discover → fetch)
- "Pay for this 402-protected API endpoint" (fetch <url>)

## Production Checklist

**Before running any command:** Python 3.8+ with `pyaes`, `websocket-client`, and `pyyaml` installed. No Node.js required. No native compilation required. Runs anywhere Python runs.

**Verify dependencies:**
```bash
pip install -r requirements.txt
```

**Verify connectivity:**
```bash
python3 scripts/nwc_wallet.py balance
```

If balance returns correctly, all crypto, relay, and wallet connections are functioning.

## ⚠️ Security (rules for YOU, the agent)

- **NEVER** echo, log, or display the NWC URL or its contents.
- **NEVER** read `.env` files that contain the NWC URL. Check for existence only.
- **NEVER** pass `--debug` in production unless troubleshooting a specific failure.
- The `--debug` flag is safe when you need it — it prints structure metadata (keys, types, error codes), never secret values or decrypted payloads.
- If a command returns an error referencing the NWC URL, redact it before showing the user.
- Spending limits are enforced server-side by the wallet — you cannot override them.
- The `--max-amount` flag on `fetch` adds an additional client-side guard: the bolt11 amount is verified before payment. Server-side limits still apply.

## Common Issues

| Symptom | Likely Cause | Action |
|---------|-------------|--------|
| "No NWC URL found" | Not configured | Walk user through Setup section above |
| "No response from relay" | Relay unreachable or timeout | Retry once. If still failing, check wallet is online. Multi-relay fallback is automatic. |
| `pay_invoice` hangs | Relay slow or payment pending | Wait up to 30s. The script retries 2 relays × 2 attempts. If it times out, check with `check_payment`. |
| "Invalid invoice" | Malformed bolt11 | Verify the invoice string is complete and starts with `lnbc` or `lntb`. |
| `balance` returns error with NIP-44 | Wallet doesn't support NIP-44 | Remove `--nip44` flag — NIP-04 is the default and universally supported. |
| Command returns empty/error silently | Config source skipped | Add `--debug` to see which config sources were tried and why they failed. |
| `pay_invoice_async` says "sent" but payment fails later | Budget exceeded or invoice expired | Check with `check_payment`. Tell user to verify wallet budget and invoice expiry. |
| `fetch` returns "402 but no supported payment protocol" | Server uses non-lightning 402 (e.g. USDC, ETH) | Inform user. Only Bitcoin/Lightning payments are supported. |
| `fetch` returns "Invoice amount exceeds max-amount" | Endpoint charges more than `--max-amount` limit | Tell user the cost and let them decide whether to increase or remove the limit. |
| `fetch` returns "amount mismatch" (X402) | Invoice amount doesn't match PAYMENT-REQUIRED declaration | Server-side issue — report to the user. The payment is not made. |
| `discover` returns empty results | No services match the query | Suggest broader queries or different protocols. Try without `-p` filter. |

## Paying Lightning Addresses

The wallet does NOT natively resolve Lightning Addresses (user@domain.com). To pay one:

1. Resolve the address to a bolt11 invoice (external tool or `lnurl-pay`)
2. Pass the bolt11 to `pay_invoice` or `pay_invoice_async`

## Bitcoin Units

- All amounts are in satoshis. When displaying to the user, show whole sats.
- 1 BTC = 100,000,000 sats.

## References

- [NIP-47: Nostr Wallet Connect](https://nips.nostr.com/47)
- [NIP-44: Encryption](https://nips.nostr.com/44)
- [BIP-340: Schnorr Signatures](https://github.com/bitcoin/bips/blob/master/bip-0340.mediawiki)
