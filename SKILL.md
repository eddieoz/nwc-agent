---
name: nwc-agent
description: >
  Zero-dependency Nostr Wallet Connect (NIP-47) client for AI agents.
  Pure Python crypto — runs on RISC-V, ARM, x86_64. Works with any
  NWC-compatible wallet: Alby Hub, LNCURL, CoinOS, Rizful.
  Send/receive Bitcoin Lightning payments autonomously.
license: MIT
metadata:
  author: eddieoz
  version: "1.2.0"
  openclaw:
    requires:
      env:
        - ALBY_NWC_URL
      bins:
        - python3
        - openssl
    emoji: "⚡"
---

# NWC Agent — Lightning Wallet for Autonomous AI

## Overview

Zero-dep Nostr Wallet Connect client for AI agents. Pure Python secp256k1 +
Schnorr + ChaCha20-Poly1305 — runs on any architecture. Compatible with any
NIP-47 wallet provider.

## Features

- Check wallet balance
- Pay Lightning invoices (synchronous + async fire-and-forget)
- Create receive invoices
- Look up invoices and verify payments
- List transactions (incoming/outgoing/all)
- Wallet metadata

## Setup

### Prerequisites

- Any NIP-47 compatible wallet (Alby Hub, LNCURL, CoinOS, Rizful)
- Python 3.8+, OpenSSL

### Installation

```bash
pip install -r requirements.txt
```

### Configuration

Copy the template and add your NWC URL:
```bash
cp .env.example .env
# Edit .env — add your NWC URL from any NIP-47 wallet
```

Or set globally in `~/.env` or as `ALBY_NWC_URL` environment variable.

Resolution order: `$SKILL_DIR/.env` → `~/.env` → `/root/.picoclaw/.security.yml` → `$ALBY_NWC_URL`

## Commands

Run: `python3 scripts/nwc_wallet.py [--debug] <command> [args...]`

| Command | Args | Description |
|---------|------|-------------|
| `balance` | — | Check wallet balance in sats |
| `pay_invoice` | `<bolt11>` | Pay invoice, wait for confirmation |
| `pay_invoice_async` | `<bolt11>` | Fire-and-forget payment |
| `make_invoice` | `<sats> [desc]` | Create receive invoice |
| `lookup_invoice` | `<payment_hash>` | Look up invoice details |
| `check_payment` | `<payment_hash>` | Check if payment settled |
| `list_transactions` | `[type] [limit] [offset]` | List transactions |
| `get_info` | — | Wallet alias, methods |

## ⚠️ Security

- NWC URL = wallet private key. **NEVER** share or commit.
- Set spending limits in your wallet before use.
- Rotate NWC URL immediately if leaked.

## Gotchas

- `pay_invoice_async` returns immediately — use `check_payment` to verify
- Budget must be sufficient (set in wallet app)
- OpenSSL required for ECDH (available on all standard distros)

## Architecture

Zero external crypto libraries. Pure Python:
- secp256k1 point arithmetic (double-and-add)
- BIP-340 Schnorr signatures
- NIP-44 v2: ChaCha20-Poly1305 + HKDF
- NIP-04: AES-256-CBC (pyaes)
- Nostr kind 23194/23195 event signing
- WebSocket relay communication

Only pip deps: pyaes, websocket-client, pyyaml.

## References

- [NIP-47](https://nips.nostr.com/47) — NWC protocol
- [NIP-44](https://nips.nostr.com/44) — Encryption standard
- [BIP-340](https://github.com/bitcoin/bips/blob/master/bip-0340.mediawiki) — Schnorr signatures
- [python_nwc](https://github.com/supertestnet/python_nwc) — Original reference implementation
- [Alby Hub](https://albyhub.com) — Popular NWC wallet provider
