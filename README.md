# NWC Agent

Zero-dependency Lightning wallet for autonomous AI agents. Pure Python.
Runs on RISC-V, ARM, x86. No Node.js, no native compilation, no C extensions.

## Quickstart

```bash
pip install -r requirements.txt
export NWC_URL="nostr+walletconnect://..."  # from Alby Hub or any NIP-47 wallet
python3 scripts/nwc_wallet.py balance
# → Balance: 42000 sats
```

That's it. Three pure-Python dependencies. Works anywhere Python 3.8+ runs.

## How it Works

AI agents need spending power to perform real-world actions — booking services,
paying for API calls, settling machine-to-machine invoices. For an agent to be
truly autonomous, it needs the ability to spend money.

Every existing Lightning wallet library requires either Node.js (and its 300MB
`node_modules` tree) or compiled secp256k1 C extensions that assume x86_64 with
glibc. Try installing any of them on a RISC-V board running musl libc and
you'll spend hours fighting toolchain errors.

This project closes that gap. It implements every cryptographic primitive in
pure Python — secp256k1 point arithmetic, BIP-340 Schnorr signatures,
ChaCha20-Poly1305 encryption, HKDF — all in auditable, readable code. If Python
runs, the wallet runs.

On top of basic wallet operations, it auto-detects three HTTP 402 payment
protocols (L402, X402, MPP), enabling agents to pay for API access at the
protocol level — the same way browsers handle HTTP authentication, but with
Bitcoin Lightning.

The interface is designed for LLM function-calling frameworks, not humans.
Every command returns structured JSON to stdout. Every error goes to stderr.

[Read the architecture deep-dive →](docs/architecture.md)

## Sponsorship

If nwc-agent has helped you build something useful, consider
[sponsoring the work](https://github.com/sponsors/eddieoz).

## Installation

**Prerequisites:** Python 3.8+, OpenSSL, a NIP-47 wallet (Alby Hub, LNCURL,
CoinOS, Rizful).

```bash
git clone https://github.com/eddieoz/nwc-agent.git
cd nwc-agent
pip install -r requirements.txt
```

**Configure your wallet connection:**

```bash
# Get your NWC URL from your wallet (Alby Hub: Settings → App Connections → New)
cp .env.example .env
# Paste your NWC URL into .env
```

**⚠️ Your NWC URL contains your wallet's private key. Never commit it, share
it, or log it. Set spending limits in your wallet before use.**

**Verify:**

```bash
python3 scripts/nwc_wallet.py balance
```

## Basic Workflow

| Operation | Command | What it does |
|-----------|---------|--------------|
| **Check balance** | `balance` | Returns wallet balance in satoshis |
| **Pay invoice** | `pay_invoice <bolt11>` | Pay and wait for confirmation (~5-15s) |
| **Create invoice** | `make_invoice <sats> [desc]` | Generate invoice to receive payment |
| **Fetch paid API** | `fetch <url>` | Auto-detect 402 protocol, pay, get resource |

```bash
# Pay an invoice synchronously
python3 scripts/nwc_wallet.py pay_invoice lnbc100n1p...

# Create an invoice to receive 1000 sats
python3 scripts/nwc_wallet.py make_invoice 1000 "for coffee"

# Access an L402-protected API (auto-detects protocol, pays, returns result)
python3 scripts/nwc_wallet.py fetch https://api.example.com/v1/generate

# Discover paid APIs that accept Lightning
python3 scripts/nwc_wallet.py discover -q "image generation"
```

## The Library

| Script | Purpose |
|--------|---------|
| `nwc_wallet.py` | Core wallet CLI — all operations: balance, pay, invoice, fetch |
| `nwc_bolt11.py` | BOLT-11 invoice parser and creator |
| `nwc_l402.py` | L402 protocol handler (WWW-Authenticate parser) |
| `nwc_x402.py` | X402 protocol handler (PAYMENT-REQUIRED parser) |
| `nwc_mpp.py` | MPP protocol handler (draft-lightning-charge-00) |
| `nwc_fetch.py` | Protocol dispatcher — auto-detect + pay + retry |
| `nwc_fiat.py` | Fiat/satoshi conversion (CoinGecko API) |
| `nwc_discover.py` | 402index.io service discovery |

[Full payment protocol reference →](docs/l402-protocol.md)

## Philosophy

- **Zero dependencies beyond pure Python.** Every dependency is an attack
  surface. Three packages. No native code. Readable in one sitting.
- **Runs where Python runs.** No architecture lock-in. RISC-V, ARM, x86 —
  if Python 3.8+ and OpenSSL exist, the wallet works.
- **Agent-first design.** Structured JSON out. Structured errors. Designed
  for LLM function-calling, not human interactive use.
- **Auditable by construction.** The entire crypto stack is ~1,400 lines of
  Python. You can verify there are no hidden network calls, no obfuscated
  blobs, no auto-updating dependency trees.

## Contributing

We welcome contributions that respect the project's philosophy.

- **AI agents:** Read [AGENTS.md](AGENTS.md) before submitting. This repo
  accepts agent contributions but quality is non-negotiable.
- **Humans:** See [docs/testing.md](docs/testing.md) for test setup, and
  use the [PR template](.github/PULL_REQUEST_TEMPLATE.md).
- **Architecture rules:** No new dependencies without overwhelming
  justification. Pure Python only. Python 3.8+ compatibility.

## License

MIT — free to use, modify, and redistribute. See [LICENSE](LICENSE).

## Community

- **Issues:** [github.com/eddieoz/nwc-agent/issues](https://github.com/eddieoz/nwc-agent/issues)
- **Author:** [EddieOz](https://eddieoz.com)
- **Specifications:** [NIP-47 (Nostr Wallet Connect)](https://nips.nostr.com/47),
  [L402 Protocol](https://docs.lightning.engineering/the-lightning-network/l402)
