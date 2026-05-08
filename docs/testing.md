# Testing

How to validate the nwc-agent wallet implementation.

## Prerequisites

- Python 3.8+
- OpenSSL (for ECDH key derivation)
- A configured NWC URL pointing to a NIP-47-compatible wallet
  (Alby Hub, LNCURL, CoinOS, or Rizful)
- Test wallet with a small balance (100-1000 sats recommended)

## Dependencies

```bash
pip install -r requirements.txt
# pyaes, websocket-client, pyyaml
```

## Test Categories

### Unit Tests (no wallet needed)

Tests that don't require a real NWC connection:

```bash
# Invoice parsing (pure BOLT-11 decoding)
python3 -c "from scripts.nwc_bolt11 import parse_bolt11; print(parse_bolt11('lnbc2500u1pvjluez...'))"

# Protocol detection (mock HTTP responses)
python3 -c "from scripts.nwc_fetch import detect_protocol; ..."
```

### Integration Tests (requires NWC wallet)

Tests that require a real wallet connection:

```bash
# Verify wallet connectivity
python3 scripts/nwc_wallet.py balance

# Test invoice creation
python3 scripts/nwc_wallet.py make_invoice 1 "test"

# Test fiat conversion (no wallet needed, uses CoinGecko API)
python3 scripts/nwc_wallet.py fiat_to_sats 1 USD

# Test service discovery (no wallet needed, uses 402index.io)
python3 scripts/nwc_wallet.py discover -q "test"
```

### L402 Payment Tests (requires wallet with balance)

```bash
# Test fetch with a known 402 endpoint
python3 scripts/nwc_wallet.py fetch "https://wiki.402.xyz/wiki/Bitcoin"

# Test credential reuse
# After first fetch, save macaroon+preimage and retry with curl
```

## RISC-V Hardware Testing

To test on physical RISC-V hardware (LicheeRV Nano):

```bash
# Cross-compilation is NOT needed — pure Python
scp -r nwc-agent root@<riscv-device>:/root/
ssh root@<riscv-device>
cd /root/nwc-agent
pip install -r requirements.txt
# Configure NWC URL on device
echo 'ALBY_NWC_URL="nostr+walletconnect://..."' > .env
# Run balance check
python3 scripts/nwc_wallet.py balance
```

## Required Environment Variables

For integration tests:

| Variable | Purpose | Required |
|----------|---------|----------|
| `ALBY_NWC_URL` | Wallet connection string | Yes (for wallet tests) |
| `SKILL_DIR` | Skill directory for config resolution | No (auto-detected) |

## Mock Mode (future)

For testing without a real wallet, the configuration resolver will skip missing
sources and report which were tried. Use `--debug` to see the resolution chain:

```bash
python3 scripts/nwc_wallet.py --debug balance
# Shows: "Trying config source 1: .env → found"
# or:     "Trying config source 1: .env → not found, skipping"
```

## What to Test Before Submitting a PR

1. `python3 scripts/nwc_wallet.py balance` — wallet connectivity
2. `python3 scripts/nwc_wallet.py parse_invoice <bolt11>` — invoice parsing
3. `python3 scripts/nwc_wallet.py fiat_to_sats 1 USD` — fiat conversion
4. Any changed modules' specific functionality
5. No regressions: commands that worked before must still work
