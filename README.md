# NWC Agent — Zero-Dependency Lightning Wallet for Autonomous AI

A pure Python Nostr Wallet Connect (NIP-47) client that enables AI agents and
autonomous devices to send and receive Bitcoin Lightning payments through any
NIP-47-compatible wallet (Alby Hub, LNCURL, CoinOS, Rizful).
No native compilation. No Node.js. No third-party cryptographic libraries.
Runs anywhere Python 3.8+ and OpenSSL exist — RISC-V single-board computers,
ARM appliances, x86 servers, containers.

## Why This Exists

AI agents are evolving from chatbots that answer questions into autonomous
systems that perform real-world actions: booking services, paying for API
calls, settling machine-to-machine invoices. For an agent to be truly
autonomous, it needs the ability to **spend money** — to pay for the resources
it consumes and the services it orchestrates.

But there's a gap. Every existing Lightning wallet library requires either
Node.js (and its 300MB `node_modules` tree), or a compiled secp256k1 native
extension that assumes x86_64 with glibc. Try installing any of them on a
RISC-V board running musl libc and you'll spend hours fighting toolchain
errors.

This project closes that gap. It implements every cryptographic primitive in
pure Python — the same Python that ships on every Linux system, regardless of
CPU architecture.

## The Architecture Advantage

### Runs on Everything

| Architecture | Status | Notes |
|-------------|--------|-------|
| **RISC-V 64-bit** (musl) | ✅ Verified | LicheeRV Nano, 898 sats balance confirmed |
| **AArch64** (ARM64) | ✅ Supported | Raspberry Pi 4/5, Apple Silicon |
| **x86_64** (glibc/musl) | ✅ Supported | Any Linux server or container |

Because the entire crypto stack is pure Python — secp256k1 point arithmetic,
BIP-340 Schnorr signatures, ChaCha20-Poly1305, HKDF — the code is **portable by
construction**. If Python runs, the wallet runs. No `gcc`, no `cmake`, no
cross-compilation toolchain, no `ldd` debugging at midnight.

### Supply Chain Resilience

Modern software supply chains are under relentless, accelerating attack.

**2024 was the wake-up call.** The xz backdoor (CVE-2024-3094) nearly
compromised SSH on every major Linux distribution — stopped only because a
Microsoft engineer noticed 500ms of latency in SSH logins. PyTorch-nightly was
hijacked via dependency confusion. Ledger Connect Kit fell to a phishing attack
on a former employee.

**2025 turned the screw.** The `tj-actions/changed-files` GitHub Action — used
by over 23,000 repositories — was compromised on March 14, 2025
(CVE-2025-30066). Attackers exfiltrated CI/CD secrets and access tokens in
plaintext, cascading through a second compromised action (`reviewdog`).
Sonatype identified over **454,600 new malicious packages** across registries
in 2025 alone, doubling the prior year. npm alone saw more than 10,800
malicious packages — a 100% increase.

**2026 broke the model.** In twelve days in late March 2026, five major
open-source packages were compromised in a coordinated wave:

- **Axios** (npm, March 30) — The most-downloaded HTTP client in the JavaScript
  ecosystem was hijacked via account takeover. A Remote Access Trojan was
  planted in the official package, radiating into millions of downstream
  projects.
- **LiteLLM** (PyPI, March 24) — The LLM API gateway used by AI agents to call
  OpenAI, Anthropic, and other providers was compromised in the TeamPCP
  campaign. Payload: credential stealers targeting API keys.
- **Telnyx** (PyPI, March 27) — Same campaign, same attacker.
- **Trivy** and **Checkmarx** — Security scanning tools themselves were
  compromised, eroding the very instrumentation meant to catch supply chain
  attacks.
- **Lazarus Group** (February 2026) — North Korean state actors planted
  malicious npm and PyPI packages disguised as crypto job tooling, deploying
  RATs and data stealers.

The LiteLLM case is not hypothetical for autonomous agents: it is the bridge
between LLM function-calling and every major API provider. A compromised LLM
gateway that steals API keys doesn't just leak data — it drains every connected
account.

Every dependency is an attack surface. When an autonomous agent holds spending
power, the stakes are existential — a compromised dependency doesn't just leak
data, it drains funds.

**Our dependency tree, in full:**

```
pyaes              — Pure Python AES (auditable ~500 lines)
websocket-client   — WebSocket implementation (standard library pattern)
pyyaml             — YAML parser (used only for config file reading)
```

That's it. Three packages. No native extensions. No build step. Every byte of
executable cryptography is visible in a single ~1,020-line Python file. You can
read the entire wallet implementation in one sitting and verify there are no
network calls to unknown hosts, no obfuscated blobs, no auto-updating
dependency trees.

### Supply Chain Attack Surface Comparison

| Wallet Solution | Dependencies | Native Code | Attack Surface |
|----------------|-------------|-------------|---------------|
| **nwc-agent** (this) | 3 (pure Python) | 0 lines | Minimal |
| @getalby/sdk (Node.js) | 200+ transitive | secp256k1 native | High |
| python_nwc (reference) | secp256k1 + pycryptodome | C extensions | Medium |
| LND (gRPC) | Full Go toolchain | Entire LND stack | Very High |

## Autonomous Agent Integration

This wallet was designed to be invoked by AI agents, not humans. Every command
returns structured JSON to stdout. Every error goes to stderr. The interface is
parseable by any LLM function-calling framework.

### Agent Usage Patterns

**Pattern 1: Direct CLI Invocation**
The agent calls the wallet as a subprocess:
```bash
python3 nwc_wallet.py pay_invoice lnbc100n1p...
# {"paid": true, "preimage": "a1b2c3...", "event_id": "def789..."}
```

**Pattern 2: Python Library**
Import the module directly in agent code:
```python
from nwc_wallet import parse_nwc_url, _prepare_nwc_event, nwc_request
import asyncio

result = asyncio.run(nwc_request(nwc_url, "get_balance"))
print(f"Balance: {result['result']['balance'] // 1000} sats")
```

**Pattern 3: Hermes/OpenClaw Skill**
Deploy as an agent skill with automatic tool registration:
```yaml
# SKILL.md frontmatter
openclaw:
  tools:
    - name: alby_balance
      command: python3 scripts/nwc_wallet.py balance
    - name: alby_pay
      command: python3 scripts/nwc_wallet.py pay_invoice
```

### Why Autonomous Payments Matter

Autonomous devices — IoT sensors, edge compute nodes, AI inference boxes —
increasingly need to participate in economic networks without human
intervention:

- **Machine-to-Machine (M2M) Payments**: A RISC-V camera node pays for cloud
  GPU inference time per frame
- **Agentic Commerce**: An AI agent books a VPS, deploys code, and pays the
  invoice — all without human approval per transaction
- **Bandwidth Markets**: A mesh network node sells excess bandwidth to
  neighbors for sats
- **API Monetization**: Any device can become a paid API endpoint (L402
  protocol), receiving Lightning payments for services rendered

Each of these requires a wallet that can run on constrained, heterogeneous
hardware — exactly the gap this project fills.

## Technical Specifications

### Cryptographic Stack (All Pure Python)

| Component | Algorithm | Lines | Standard |
|-----------|----------|-------|----------|
| Elliptic curve | secp256k1 point arithmetic | 40 | SEC 2 |
| Key derivation | ECDH (OpenSSL CLI helper) | 35 | ANSI X9.63 |
| Signatures | BIP-340 Schnorr (RFC 6979 deterministic) | 55 | Bitcoin |
| NIP-44 encryption | ChaCha20-Poly1305 + HKDF | 120 | Nostr NIP-44 v2 |
| NIP-04 encryption | AES-256-CBC (pyaes) | 45 | Nostr NIP-04 |
| DER encoding | ASN.1 DER for EC keys | 55 | X.690 |
| Nostr events | Kind 23194/23195 signing | 25 | NIP-47 |
| WebSocket relay | websocket-client | 75 | RFC 6455 |

**Total: ~1,400 lines of auditable Python.** No C extensions. No assembly.

### Wallet Commands

| Command | NWC Method / Source | Description |
|---------|---------------------|-------------|
| `balance` | `get_balance` | Wallet balance in satoshis |
| `pay_invoice` | `pay_invoice` | Pay bolt11, wait for confirmation |
| `pay_invoice_async` | `pay_invoice` | Fire-and-forget payment |
| `make_invoice` | `make_invoice` | Create receive invoice |
| `lookup_invoice` | `lookup_invoice` | Query invoice by payment_hash |
| `check_payment` | `lookup_invoice` | Verify payment settled, return preimage |
| `list_transactions` | `list_transactions` | Transaction history |
| `get_info` | `get_info` | Wallet metadata |

### 402 Payment Protocol Commands

| Command | Source | Description |
|---------|--------|-------------|
| `fetch` | L402/X402/MPP auto-detect | Pay for 402-protected APIs, retry with payment proof |
| `parse_invoice` | BOLT-11 decoder | Decode invoice: amount, hash, description, expiry |
| `fiat_to_sats` | CoinGecko API | Convert fiat (USD, EUR, etc.) to satoshis |
| `sats_to_fiat` | CoinGecko API | Convert satoshis to fiat |
| `discover` | 402index.io | Find paid API services accepting Lightning |

**Supported payment protocols:**
- **L402** (LSAT) — `WWW-Authenticate: L402 token=... invoice=...` → pay → `Authorization: L402 <token>:<preimage>`
- **X402** — `PAYMENT-REQUIRED: <base64-JSON>` → pay → `payment-signature: <base64-JSON>`
- **MPP** (draft-lightning-charge-00) — `WWW-Authenticate: Payment method="lightning" intent="charge" ...` → pay → `Authorization: Payment <JCS-credential>`

Protocol detection is fully automatic — no flags needed. The dispatcher checks response headers and routes to the correct handler.

### Network Protocol

- **Protocol**: Nostr Wallet Connect (NIP-47)
- **Relay transport**: WebSocket Secure (wss://)
- **Multi-relay**: Tries all relays from NWC URL sequentially
- **Timeout**: 8s per relay attempt, 2 retries
- **Response wait**: Subscribes to kind 23195 on same connection

### Security Architecture

```
┌─────────────────────────────────────────────────────┐
│  NWC URL (contains wallet private key)              │
│  ↓                                                  │
│  /root/.picoclaw/.security.yml (rw-------)          │
│  or ALBY_NWC_URL environment variable               │
│  ↓                                                  │
│  parse_nwc_url() → wallet_pubkey, relay, secret     │
│  ↓                                                  │
│  ECDH(secret, wallet_pubkey) → shared AES key       │
│  ↓                                                  │
│  Encrypt request → Nostr event (kind 23194) → Relay │
│  ↓                                                  │
│  Relay → Nostr event (kind 23195) → Decrypt response│
└─────────────────────────────────────────────────────┘
```

Key security properties:
- **NWC URL never logged** — only event IDs and balance amounts appear in output
- **Debug mode is safe** — `--debug` prints JSON structure (keys, types, error flags), never secrets
- **RFC 6979 deterministic nonces** — eliminates nonce reuse risk in Schnorr signatures
- **NIP-44 support** — `--nip44` flag enables ChaCha20-Poly1305 authenticated encryption (requires Alby Hub >= 1.8.0)
- **Spending limits enforced server-side** — wallet-level budget caps prevent drain
- **No persistent state on device** — key material derived fresh each invocation
- **Constant-time MAC comparison** — NIP-44 Poly1305 verification
- **WebSocket safety** — `try/finally` ensures connections always close, no descriptor leaks
- **Config error visibility** — `--debug` surfaces which config sources were skipped and why

### Performance on RISC-V (LicheeRV Nano, 1GHz C906)

| Operation | Time | Notes |
|-----------|------|-------|
| secp256k1 point multiplication | ~2ms | Double-and-add, 256 iterations |
| BIP-340 Schnorr sign | ~3ms | Includes nonce generation |
| ECDH (OpenSSL subprocess) | ~15ms | Cold start dominated |
| NWC balance request (end-to-end) | ~3s | WebSocket round-trip to relay2.getalby.com |
| NIP-44 encrypt/decrypt | ~5ms | ChaCha20 + Poly1305 |

## Quick Start

### Prerequisites
- Python 3.8+
- OpenSSL (for ECDH key derivation)
- A NWC pairing secret from any NIP-47-compatible wallet
  (Alby Hub, LNCURL, CoinOS, Rizful, etc.)

### Installation
```bash
git clone https://github.com/eddieoz/nwc-agent
cd nwc-agent
pip install -r requirements.txt
```
### Configuration

The wallet loads its NWC URL through a priority-gated chain. The first match
wins — set a default globally, override per-skill.

| Priority | Location | Type | Best for |
|----------|----------|------|----------|
| 1 (highest) | `$SKILL_DIR/.env` | Skill-local config | Per-skill wallet isolation |
| 2 | `~/.env` | Agent home config | Shared across all skills |
| 3 | `/root/.picoclaw/.security.yml` | Legacy format | Backward compatibility |
| 4 (fallback) | `$ALBY_NWC_URL` | Environment variable | Universal catch-all |

**Quick start — any of these works:**

```bash
# Option A: Skill-local (best for different budgets per skill)
cp .env.example .env
# Edit .env, paste your NWC URL
echo 'ALBY_NWC_URL="nostr+walletconnect://..."' > .env

# Option B: Agent home (one wallet, all skills)
echo 'ALBY_NWC_URL="nostr+walletconnect://..."' >> ~/.env

# Option C: Legacy (existing picoclaw/Hermes users)
# Already works if configured — no changes needed

# Option D: Environment variable
export ALBY_NWC_URL="nostr+walletconnect://..."
```

**Get your NWC URL:**
For Alby Hub: Settings → App Connections → New Connection → Copy pairing secret.
For LNCURL, CoinOS, or other NIP-47 wallets, consult that wallet's documentation
for generating an NWC connection string.
The secret starts with `nostr+walletconnect://` and contains your wallet's
public key and relay addresses.

**⚠️ Your NWC URL contains your wallet's private key. Never commit it, share
it, or log it. Set spending limits in your wallet before use.**

### Usage
```bash
# Check balance
python3 scripts/nwc_wallet.py balance
# Balance: 898 sats

# Pay an invoice (waits for confirmation)
python3 scripts/nwc_wallet.py pay_invoice lnbc100n1p...

# Pay and return immediately (verify later)
python3 scripts/nwc_wallet.py pay_invoice_async lnbc100n1p...

# Verify payment
python3 scripts/nwc_wallet.py check_payment <payment_hash>

# Create invoice to receive
python3 scripts/nwc_wallet.py make_invoice 1000 "coffee"

# List recent transactions
python3 scripts/nwc_wallet.py list_transactions outgoing 10 0

# Debug mode (safe — shows structure, never secrets)
python3 scripts/nwc_wallet.py --debug balance

# NIP-44 encryption (ChaCha20-Poly1305, requires Alby Hub >= 1.8.0)
python3 scripts/nwc_wallet.py --nip44 balance

# Fetch a 402-protected API endpoint (auto-detects L402/X402/MPP)
python3 scripts/nwc_wallet.py fetch https://api.example.com/v1/generate

# Fetch with POST body and spending limit
python3 scripts/nwc_wallet.py fetch --method POST --body '{"prompt":"a mountain cabin"}' --max-amount 500 "https://api.example.com/v1/generate"

# Fiat / sats conversion
python3 scripts/nwc_wallet.py fiat_to_sats 10 USD
python3 scripts/nwc_wallet.py sats_to_fiat 1000 EUR

# Parse a bolt11 invoice
python3 scripts/nwc_wallet.py parse_invoice lnbc2500u1pvjluez...

# Discover paid APIs on 402index.io
python3 scripts/nwc_wallet.py discover -q "image generation"
python3 scripts/nwc_wallet.py discover -p x402 --limit 20
```

## Security Audit

A formal security assessment was performed on 2026-05-07 covering the entire
codebase. The audit identified and resolved five findings:

| Finding | Severity | Resolution |
|---------|----------|------------|
| NIP-04 AES-CBC lacks authentication | High | NIP-44 flag added; NIP-04 kept for backward compatibility |
| Silent error suppression in config loader | Medium | `--debug` now surfaces skipped config sources |
| Debug mode leaked decrypted payloads | Medium | `_debug_event()` prints structure, never values |
| Schnorr nonce loop timing side-channel | Low | RFC 6979 deterministic nonces (default on) |
| WebSocket resource leak | Low | `try/finally` on all connection paths |

All findings have been resolved. No critical vulnerabilities were identified.
The custom secp256k1 implementation was reviewed and found appropriate for the
embedded RISC-V target where native crypto libraries are unavailable.

NIP-44 (ChaCha20-Poly1305) is fully implemented for both send and receive.
It becomes the default by adding `--nip44` — activate when your wallet
supports NIP-44 (Alby Hub >= 1.8.0, check your wallet's docs for others).

## Project Structure

```
nwc-agent/
├── scripts/
│   ├── nwc_wallet.py      ← Core wallet + CLI (pure Python, zero crypto deps)
│   ├── nwc_bolt11.py      ← BOLT-11 invoice parser (bech32, tagged fields)
│   ├── nwc_l402.py        ← L402 protocol handler (WWW-Authenticate parser)
│   ├── nwc_x402.py        ← X402 protocol handler (PAYMENT-REQUIRED parser)
│   ├── nwc_mpp.py         ← MPP protocol handler (JCS + base64url)
│   ├── nwc_fetch.py       ← Protocol dispatcher (auto-detect + urllib)
│   ├── nwc_fiat.py        ← Fiat/satoshi conversion (CoinGecko API)
│   └── nwc_discover.py    ← 402index.io service discovery
├── requirements.txt       ← 3 packages: pyaes, websocket-client, pyyaml
├── .env.example           ← Template for credentials (copy to .env)
├── .gitignore             ← Blocks .env, __pycache__
├── README.md              ← This file
├── SKILL.md               ← Agent skill definition (commands + protocols)
└── _meta.json             ← Skill registry metadata
```

## References & Acknowledgments

This project builds on two prior implementations. Neither worked on RISC-V as
shipped — our contribution was stripping every native dependency while
preserving full protocol compatibility.

### python_nwc (supertestnet)

**[github.com/supertestnet/python_nwc](https://github.com/supertestnet/python_nwc)** — The original Python NWC reference client. This is where the NIP-47 interaction patterns were established.

**What we adopted:**
- Fire-and-forget payment pattern (`tryToPayInvoice`) paired with `didPaymentSucceed` for verification — now exposed as `pay_invoice` (sync) and `pay_invoice_async`
- The full NWC command surface: `get_balance`, `make_invoice`, `lookup_invoice`, `get_info`, `list_transactions`
- WebSocket relay communication over Nostr kind 23194/23195 events

**Why we diverged:**
`python_nwc` depends on `secp256k1` (C extension requiring compilation) and `pycryptodome` (C extension — 300K+ lines of C). Neither compiles on musl-based RISC-V without a cross-compilation toolchain. We replaced the entire dependency tree:

| python_nwc | nwc-agent (ours) |
|---|---|
| `secp256k1.PrivateKey` | Pure Python point_mul, point_add (40 lines) |
| `secp256k1.schnorr_sign` | Pure Python BIP-340 (50 lines) |
| `Crypto.Cipher.AES` | `pyaes` (pure Python AES) |
| Direct `threading` pattern | Single-connection subscribe-then-send (avoids thread safety issues on constrained devices) |
| Single relay | Multi-relay fallback (critical — our wallet was only on relay2) |

### alby-bitcoin-payments (Node.js skill)

**[OpenClaw skill registry](https://clawhub.ai/skills/alby-lightning)** — The predecessor skill that used `@getalby/sdk` via Node.js. This established the agent-facing skill interface and the security model (NWC URL in `.security.yml`, spending limits in Alby Hub).

**What we adopted:**
- Skill structure: `SKILL.md` frontmatter, `_meta.json` registry metadata
- Configuration resolution order: security file → environment variable
- Security warnings about NWC URL containing wallet private key
- The concept of the wallet as an agent-invokable tool rather than a human CLI

**Why we diverged:**
Node.js is not available on our RISC-V target. The `@getalby/sdk` dependency tree is ~200 packages with native secp256k1 bindings — completely non-portable to embedded architectures. We preserved the skill interface but replaced the entire runtime, then expanded to support any NIP-47 wallet beyond Alby.

### Protocol Standards

- [NIP-47: Nostr Wallet Connect](https://nips.nostr.com/47) — Wallet RPC over Nostr
- [NIP-44: Encryption](https://nips.nostr.com/44) — ChaCha20-Poly1305 for Nostr DMs
- [BIP-340: Schnorr Signatures](https://github.com/bitcoin/bips/blob/master/bip-0340.mediawiki) — Used for Nostr event signing
- [Alby Hub](https://albyhub.com) — Self-custodial Lightning wallet implementing NWC

## License

MIT — free to use, modify, and redistribute.
