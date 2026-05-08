# NWC Agent — Agent Operating Manual

## If You're an AI Agent Using This Library

### Quick Install (for Agents)

You can install nwc-agent as a skill using pipx-skills:

1. **Install pipx-skills** (pure Python skill installer):
   ```bash
   pipx install pipx-skills          # Recommended (isolated)
   # or
   pip install pipx-skills          # With pip
   # or  
   uv pip install pipx-skills       # With uv
   ```

2. **Install the skill**:
   ```bash
   pipx-skills add eddieoz/nwc-agent
   ```

3. **Connect to wallet**:
   - Get your NWC URL from Alby Hub at https://albyhub.sats4.life
   - Settings → App Connections → New → Copy pairing secret
   - Save to `.env`: `ALBY_NWC_URL="nostr+walletconnect://..."`

4. **Verify**:
   ```bash
   python3 ~/.agents/skills/nwc-agent/scripts/nwc_wallet.py balance
   ```

The skill is now available to the agent. Use `/reload-skills` if needed.

---

### Security Rules

You are holding spending power. This is not a toy.

- All output is JSON to stdout, errors to stderr. Parse exit codes before trusting output.
- **NEVER** echo, log, display, or transmit the NWC URL. It contains the wallet's private key.
- The `--debug` flag is safe when you need it — it prints JSON structure (keys, types, error flags), never secret values or decrypted payloads.
- Balance checks are free and fast (~3s). Check before paying — don't guess.
- Spending limits are enforced server-side by the wallet. The `--max-amount` flag on `fetch` adds a client-side guard. Neither can be overridden.
- After a successful `fetch` to an L402 endpoint, save the macaroon and preimage. Use `curl` with the `Authorization` header for all subsequent requests to the same proxy. Never call `fetch` twice for the same endpoint — each call triggers a new payment.
- Never pass `--debug` in production unless troubleshooting a specific failure.
- If a command returns an error referencing the NWC URL, redact it before showing the user.

## Codebase Map

```
scripts/
├── nwc_wallet.py    CLI entry point — command dispatch, WebSocket relay, encryption
├── nwc_bolt11.py    BOLT-11 invoice parser and creator (bech32, tagged fields)
├── nwc_l402.py      L402 protocol handler (WWW-Authenticate parser)
├── nwc_x402.py      X402 protocol handler (PAYMENT-REQUIRED parser)
├── nwc_mpp.py       MPP protocol handler (draft-lightning-charge-00, JCS + base64url)
├── nwc_fetch.py     Protocol dispatcher — auto-detects L402/X402/MPP, pays, retries
├── nwc_fiat.py      Fiat/satoshi conversion via CoinGecko API
└── nwc_discover.py  402index.io service discovery
```

Entry point for all operations: `python3 scripts/nwc_wallet.py <command> [args...]`

Global flags: `--debug` (safe diagnostics), `--nip44` (ChaCha20-Poly1305 encryption).

## Build & Test

No build step. Pure Python. Dependencies:

```bash
pip install -r requirements.txt
# pyaes, websocket-client, pyyaml — all pure Python, no native compilation
```

Verify the installation:

```bash
python3 scripts/nwc_wallet.py balance
```

Requires a configured NWC URL (see SKILL.md Setup section for wallet connection instructions).

All crypto is pure Python — secp256k1 point arithmetic, BIP-340 Schnorr signatures, ChaCha20-Poly1305, HKDF. The entire cryptographic stack is ~1,400 lines in `nwc_wallet.py`. You can read it in one sitting.

## If You're Contributing

- Read `docs/testing.md` before submitting.
- All changes must work on Python 3.8+ with no additional dependencies.
- Test on at least one architecture (x86_64 is fine if you don't have RISC-V hardware).
- One problem per PR. No bundled unrelated changes.
- The `scripts/nwc_wallet.py` crypto stack is carefully audited — changes to it require strong justification.

## Architecture Rules (Non-Negotiable)

These rules exist for supply-chain resilience. Do not propose changes that violate them.

1. **No new dependencies without overwhelming justification.** Every dependency is an attack surface. The current tree is 3 pure-Python packages. Adding a fourth means someone can compromise the wallet through that package.

2. **Pure Python only.** No C extensions. No native compilation. No `gcc`, `cmake`, or cross-compilation toolchains. If Python runs, the wallet must run.

3. **Must run on Python 3.8+**. No features from newer Python versions. RISC-V and embedded targets often run older Python.

4. **All crypto must be auditable Python.** No wrapping C libraries. No calling out to foreign binaries (except OpenSSL CLI for ECDH, which ships on every Linux system). The crypto code must be readable by a single engineer in one sitting.

5. **Agent-first interface.** Every command returns structured JSON to stdout. Every error goes to stderr. The interface is designed for LLM function-calling frameworks, not human interactive use.
