---
name: nwc-agent
description: >
  Zero-dependency Nostr Wallet Connect (NIP-47) client for AI agents.
  Pure Python crypto — runs on RISC-V, ARM, x86_64. Works with any
  NWC-compatible wallet: Alby Hub, LNCURL, CoinOS, Rizful.
  NIP-44 (ChaCha20-Poly1305) supported via --nip44 flag.
  Send/receive Bitcoin Lightning payments autonomously.
license: MIT
metadata:
  author: eddieoz
  version: "1.3.0"
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

> **IMPORTANT: this is an agent skill. Use the exact commands below — do not improvise alternative approaches.**

```bash
python3 scripts/nwc_wallet.py [--debug] [--nip44] <command> [args...]
```

## Global Flags

`--debug` — print JSON structure (keys, types, error flags). Safe to use: never leaks secrets, never prints decrypted payloads. Use this when a command fails silently and you need to know why.

`--nip44` — use NIP-44 ChaCha20-Poly1305 encryption instead of NIP-04 AES-CBC. Requires wallet with NIP-44 support (Alby Hub >= 1.8.0). Check compatibility first with a plain `balance` call.

## Commands

**Wallet operations:**

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
- "Check your wallet balance"
- "Create a 1000 sat invoice"
- "Send 100 sats to a Lightning Address"

## ⚠️ Security (rules for YOU, the agent)

- **NEVER** echo, log, or display the NWC URL or its contents.
- **NEVER** read `.env` files that contain the NWC URL. Check for existence only.
- **NEVER** pass `--debug` in production unless troubleshooting a specific failure.
- The `--debug` flag is safe when you need it — it prints structure metadata (keys, types, error codes), never secret values or decrypted payloads.
- If a command returns an error referencing the NWC URL, redact it before showing the user.
- Spending limits are enforced server-side by the wallet — you cannot override them.

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
