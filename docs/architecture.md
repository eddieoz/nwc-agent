# Architecture — Crypto Stack, Supply Chain, and Platform Support

Deep technical reference for the cryptographic implementation, supply-chain
resilience analysis, and multi-architecture portability strategy.

## Cryptographic Stack (All Pure Python)

The wallet implements every cryptographic primitive in auditable Python.
No C extensions. No assembly. No foreign binaries except OpenSSL CLI for ECDH
(which ships on every Linux distribution).

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

**Total: ~1,400 lines of auditable Python.** The entire wallet implementation
fits in `scripts/nwc_wallet.py`. You can read it in one sitting and verify
there are no network calls to unknown hosts, no obfuscated blobs, no
auto-updating dependency trees.

## Platform Support

Because the entire crypto stack is pure Python, the code is **portable by
construction**. If Python 3.8+ and OpenSSL run, the wallet runs. No `gcc`,
no `cmake`, no cross-compilation toolchain.

| Architecture | Status | Notes |
|-------------|--------|-------|
| **RISC-V 64-bit** (musl) | ✅ Verified | LicheeRV Nano, balance confirmed |
| **AArch64** (ARM64) | ✅ Supported | Raspberry Pi 4/5, Apple Silicon |
| **x86_64** (glibc/musl) | ✅ Supported | Any Linux server or container |

## Performance on RISC-V (LicheeRV Nano, 1GHz C906)

| Operation | Time | Notes |
|-----------|------|-------|
| secp256k1 point multiplication | ~2ms | Double-and-add, 256 iterations |
| BIP-340 Schnorr sign | ~3ms | Includes nonce generation |
| ECDH (OpenSSL subprocess) | ~15ms | Cold start dominated |
| NWC balance request (end-to-end) | ~3s | WebSocket round-trip to relay |
| NIP-44 encrypt/decrypt | ~5ms | ChaCha20 + Poly1305 |

## Supply Chain Resilience

Modern software supply chains are under relentless, accelerating attack.
Every dependency is an attack surface. When an autonomous agent holds spending
power, the stakes are existential — a compromised dependency doesn't just leak
data, it drains funds.

### Threat Timeline (2024–2026)

**2024 — The wake-up call:**
- xz backdoor (CVE-2024-3094) — nearly compromised SSH on every major Linux
  distribution, stopped only because a Microsoft engineer noticed 500ms of
  latency in SSH logins
- PyTorch-nightly hijacked via dependency confusion
- Ledger Connect Kit fell to a phishing attack on a former employee

**2025 — The escalation:**
- `tj-actions/changed-files` GitHub Action — used by 23,000+ repositories —
  compromised on March 14, 2025 (CVE-2025-30066). Attackers exfiltrated
  CI/CD secrets and access tokens in plaintext
- Sonatype identified over **454,600 new malicious packages** across
  registries in 2025 alone, doubling the prior year
- npm alone: 10,800+ malicious packages — a 100% increase

**2026 — The model broke.** In twelve days in late March 2026, five major
open-source packages were compromised in a coordinated wave:

- **Axios** (npm, March 30) — Most-downloaded HTTP client in JavaScript,
  hijacked via account takeover. RAT planted in the official package,
  radiating into millions of downstream projects
- **LiteLLM** (PyPI, March 24) — LLM API gateway used by AI agents to call
  OpenAI, Anthropic, and other providers. Compromised in TeamPCP campaign.
  Payload: credential stealers targeting API keys
- **Telnyx** (PyPI, March 27) — Same campaign, same attacker
- **Trivy** and **Checkmarx** — Security scanning tools themselves were
  compromised, eroding the instrumentation meant to catch supply chain attacks
- **Lazarus Group** (February 2026) — North Korean state actors planted
  malicious npm and PyPI packages disguised as crypto job tooling

The LiteLLM case is not hypothetical for autonomous agents: it is the bridge
between LLM function-calling and every major API provider. A compromised LLM
gateway that steals API keys doesn't just leak data — it drains every
connected account.

### Our Dependency Tree

```
pyaes              — Pure Python AES (auditable ~500 lines)
websocket-client   — WebSocket implementation (standard library pattern)
pyyaml             — YAML parser (used only for config file reading)
```

Three packages. No native extensions. No build step. Every byte of executable
cryptography is visible in a single Python file.

### Attack Surface Comparison

| Wallet Solution | Dependencies | Native Code | Attack Surface |
|----------------|-------------|-------------|---------------|
| **nwc-agent** (this) | 3 (pure Python) | 0 lines | Minimal |
| @getalby/sdk (Node.js) | 200+ transitive | secp256k1 native | High |
| python_nwc (reference) | secp256k1 + pycryptodome | C extensions | Medium |
| LND (gRPC) | Full Go toolchain | Entire LND stack | Very High |

## Security Architecture

```
┌─────────────────────────────────────────────────────┐
│  NWC URL (contains wallet private key)              │
│  ↓                                                  │
│  Config resolution: .env → ~/.env → legacy → env var│
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

### Key Security Properties

- **NWC URL never logged** — only event IDs and balance amounts appear in output
- **Debug mode is safe** — `--debug` prints JSON structure (keys, types, error
  flags), never secrets
- **RFC 6979 deterministic nonces** — eliminates nonce reuse risk in Schnorr
  signatures
- **NIP-44 support** — `--nip44` flag enables ChaCha20-Poly1305 authenticated
  encryption (requires Alby Hub >= 1.8.0)
- **Spending limits enforced server-side** — wallet-level budget caps prevent
  drain
- **No persistent state on device** — key material derived fresh each invocation
- **Constant-time MAC comparison** — NIP-44 Poly1305 verification
- **WebSocket safety** — `try/finally` ensures connections always close
- **Config error visibility** — `--debug` surfaces skipped config sources

## Network Protocol

- **Protocol**: Nostr Wallet Connect (NIP-47)
- **Relay transport**: WebSocket Secure (wss://)
- **Multi-relay**: Tries all relays from NWC URL sequentially
- **Timeout**: 8s per relay attempt, 2 retries
- **Response wait**: Subscribes to kind 23195 on same connection

## Security Audit (2026-05-07)

A formal security assessment was performed covering the entire codebase.
Five findings were identified and resolved:

| Finding | Severity | Resolution |
|---------|----------|------------|
| NIP-04 AES-CBC lacks authentication | High | NIP-44 flag added; NIP-04 kept for backward compatibility |
| Silent error suppression in config loader | Medium | `--debug` now surfaces skipped config sources |
| Debug mode leaked decrypted payloads | Medium | `_debug_event()` prints structure, never values |
| Schnorr nonce loop timing side-channel | Low | RFC 6979 deterministic nonces (default on) |
| WebSocket resource leak | Low | `try/finally` on all connection paths |

All findings resolved. No critical vulnerabilities identified. The custom
secp256k1 implementation was reviewed and found appropriate for the embedded
RISC-V target where native crypto libraries are unavailable.

## Prior Art & Acknowledgments

This project builds on two prior implementations. Neither worked on RISC-V as
shipped — our contribution was stripping every native dependency while
preserving full protocol compatibility.

### python_nwc (supertestnet)

[github.com/supertestnet/python_nwc](https://github.com/supertestnet/python_nwc) —
The original Python NWC reference client.

**What we adopted:**
- Fire-and-forget payment pattern paired with verification
- Full NWC command surface: `get_balance`, `make_invoice`, `lookup_invoice`,
  `get_info`, `list_transactions`
- WebSocket relay communication over Nostr kind 23194/23195 events

**Why we diverged — dependency replacement:**

| python_nwc | nwc-agent (ours) |
|---|---|
| `secp256k1.PrivateKey` | Pure Python point_mul, point_add (40 lines) |
| `secp256k1.schnorr_sign` | Pure Python BIP-340 (50 lines) |
| `Crypto.Cipher.AES` | `pyaes` (pure Python AES) |
| Direct `threading` pattern | Single-connection subscribe-then-send |
| Single relay | Multi-relay fallback |

### alby-bitcoin-payments (Node.js skill)

The predecessor skill that used `@getalby/sdk` via Node.js. Established the
agent-facing skill interface and security model.

**What we adopted:**
- Skill structure: `SKILL.md` frontmatter, `_meta.json` registry metadata
- Configuration resolution order
- NWC URL security warnings
- Wallet as agent-invokable tool concept

**Why we diverged:**
Node.js is not available on RISC-V targets. The `@getalby/sdk` dependency tree
is ~200 packages with native secp256k1 bindings. We preserved the skill
interface but replaced the entire runtime, then expanded to support any
NIP-47 wallet beyond Alby.
