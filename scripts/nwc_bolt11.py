#!/usr/bin/env python3
"""
BOLT-11 Invoice Parser — pure Python, zero dependencies.

Decodes Lightning Network invoices per BOLT#11 specification.
Extracts: payment_hash, amount_sats, timestamp, description, expiry,
payee_pubkey, route hints, features, fallback addresses, payment secret.

Usage:
    from nwc_bolt11 import parse_invoice
    info = parse_invoice("lnbc100n1p...")
    print(info['amount_sats'])   # 100
    print(info['payment_hash'])  # hex string
"""

import json
import sys
from datetime import datetime, timezone

# ─── Bech32 ────────────────────────────────────────────────────────────
BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
CHARSET_MAP = {c: i for i, c in enumerate(BECH32_CHARSET)}

_POLYMOD_GEN = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]


def _polymod(values):
    chk = 1
    for v in values:
        b = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ v
        for i in range(5):
            if (b >> i) & 1:
                chk ^= _POLYMOD_GEN[i]
    return chk


def _hrp_expand(hrp):
    return [x >> 5 for x in hrp.encode()] + [0
                                             ] + [x & 31 for x in hrp.encode()]


def _bech32_verify(hrp, data):
    return _polymod(_hrp_expand(hrp) + data) == 1


def decode_bech32(bech_str):
    """Decode a bech32 string. Returns (hrp, data_5bit_values) or (None,
    None).

    BOLT-11 note: the '1' separator for data is the LAST '1' in the string.
    """
    if not bech_str:
        return None, None

    bech_str = bech_str.strip().lower()
    pos = bech_str.rfind('1')
    if pos < 1 or pos + 7 > len(bech_str):
        return None, None

    hrp = bech_str[:pos]
    data_str = bech_str[pos + 1:]

    data = []
    for ch in data_str:
        if ch not in CHARSET_MAP:
            return None, None
        data.append(CHARSET_MAP[ch])

    if not _bech32_verify(hrp, data):
        return None, None

    return hrp, data[:-6]  # Strip checksum


# ─── Amount Parsing ────────────────────────────────────────────────────

def _parse_amount_from_hrp(hrp):
    """Parse BOLT-11 amount from the HRP.

    HRP format: ln[bc|tb|bcrt][amount_multiplier][amount_digits]
    - 'm' (milli): 0.001 BTC = 100,000 sats
    - 'u' (micro): 0.000001 BTC = 100 sats
    - 'n' (nano): 0.000000001 BTC = 0.001 sats → 1 msat
    - 'p' (pico): 0.000000000001 BTC = 0.000001 sats
    If no amount, the invoice is "any amount" (0 sats in amount field).

    Returns dict with has_amount, amount_sats, amount_msat, currency.
    """
    import re
    m = re.match(r'^(ln)(bc(?:rt)?|tb)(?:(\d+)([munp])?)?$', hrp)
    if not m:
        return {'currency': 'unknown', 'has_amount': False}

    currency = m.group(2)

    if not m.group(3):
        return {'currency': currency, 'has_amount': False}

    digits = int(m.group(3))
    multiplier = m.group(4)

    # BOLT-11 multipliers. These are Bitcoin-denominated.
    # To get satoshis: (digits * multiplier_BTC * 100_000_000)
    scale = {
        'm': 100_000,  # milli → sats
        'u': 100,  # micro → sats
        'n': 0,  # nano → < 1 sat (use msat)
        'p': 0,  # pico → < 1 msat (use msat)
    }
    msat_scales = {
        'm': 100_000_000_000,
        'u': 100_000_000,
        'n': 100_000,
        'p': 100,
    }

    if multiplier in ('m', 'u'):
        return {
            'currency': currency,
            'has_amount': True,
            'amount_sats': digits * scale[multiplier],
            'amount_msat': 0,
        }
    elif multiplier in ('n', 'p'):
        msat = digits * msat_scales[multiplier]
        return {
            'currency': currency,
            'has_amount': True,
            'amount_sats': msat // 1000,
            'amount_msat': msat % 1000,
        }

    return {'currency': currency, 'has_amount': False}


# ─── BOLT-11 Tagged Field Decoder ──────────────────────────────────────

_TAG_NAMES = {
    1: 'payment_hash',
    3: 'route_hint',
    5: 'features',
    6: 'expiry',
    7: 'route_hint',  # alternate
    8: 'route_hint',  # alternate
    9: 'fallback_address',
    13: 'description',
    16: 'payment_secret',
    19: 'payee_pubkey',
    23: 'description_hash',
    24: 'min_final_cltv_expiry',
    25: 'channel_hint',
    26: 'node_id',
}


def _decode_tagged_fields(data_5bit):
    """Decode BOLT-11 tagged fields from 5-bit values (without checksum).

    Tag format:
      - tag: 5 bits
      - data_length: 10 bits (2 bech32 chars): first * 32 + second
      - data: data_length * 5 bits

    Returns dict.
    """
    fields = {}
    pos = 0
    n = len(data_5bit)

    while pos + 3 <= n:
        tag = data_5bit[pos]
        pos += 1

        if pos + 1 >= n:
            break

        # Data length encoded as 10 bits (2 bech32 chars)
        data_len = data_5bit[pos] * 32 + data_5bit[pos + 1]
        pos += 2

        if pos + data_len > n:
            break

        # Extract data words and convert to bytes
        data_words = data_5bit[pos:pos + data_len]
        pos += data_len

        value = _words_to_bytes(data_words)

        # Store in fields dict
        tag_name = _TAG_NAMES.get(tag, f'tag_{tag}')

        if tag == 1:  # payment_hash
            fields['payment_hash'] = value.hex()
        elif tag == 13:  # description
            fields['description'] = value.decode('utf-8', errors='replace')
        elif tag == 16:  # payment_secret
            fields['payment_secret'] = value.hex()
        elif tag == 19:  # payee_pubkey
            fields['payee_pubkey'] = value.hex()
        elif tag == 23:  # description_hash
            fields['description_hash'] = value.hex()
        elif tag in (6, 24):  # expiry, min_final_cltv_expiry
            fields[tag_name] = int.from_bytes(value, 'big')
        elif tag == 9:  # fallback_address
            fields['fallback_address'] = _decode_fallback(value)
        elif tag in (3, 7, 8):  # route hints
            if 'route_hints' not in fields:
                fields['route_hints'] = []
            fields['route_hints'].append(_decode_route_hint(value))
        elif tag == 5:  # features
            fields['features'] = _decode_features(value)
        else:
            # Store raw hex for unknown tags
            fields[tag_name] = value.hex()

    return fields


def _words_to_bytes(words):
    """Convert 5-bit words to 8-bit bytes."""
    bits = []
    for w in words:
        for i in range(4, -1, -1):
            bits.append((w >> i) & 1)

    result = bytearray()
    for i in range(0, len(bits) - len(bits) % 8, 8):
        b = 0
        for j in range(8):
            b = (b << 1) | bits[i + j]
        result.append(b)
    return bytes(result)


def _decode_fallback(data):
    """Decode fallback on-chain address."""
    if len(data) < 1:
        return {'error': 'empty'}
    version = data[0]
    return {
        'version': version,
        'address_data': data[1:].hex(),
        'is_p2pkh': version == 0 and len(data) == 21,
        'is_p2sh': version == 5 and len(data) == 21,
        'is_p2wpkh': version == 0 and len(data) == 21,
        'is_p2wsh': version == 0 and len(data) == 33,
    }


def _decode_route_hint(data):
    """Extract route hint pubkey."""
    return {
        'pubkey': data[:33].hex() if len(data) >= 33 else data.hex(),
        'raw_hex': data.hex(),
    }


def _decode_features(data):
    """Decode feature bit vector."""
    features = []
    for byte_idx, byte in enumerate(data):
        for bit in range(8):
            if (byte >> bit) & 1:
                features.append(byte_idx * 8 + bit)
    return features


# ─── Signature ─────────────────────────────────────────────────────────

def _decode_signature(data_5bit):
    """Extract the 65-byte recovery signature (last 104 words)."""
    if len(data_5bit) < 104:
        return None

    sig_words = data_5bit[-104:]
    sig_bytes = _words_to_bytes(sig_words)

    # Recovery format: recovery_id(1) + r(32) + s(32)
    if len(sig_bytes) != 65:
        return None

    return {
        'recovery_id': sig_bytes[0],
        'r': sig_bytes[1:33].hex(),
        's': sig_bytes[33:65].hex(),
    }


# ─── Timestamp ─────────────────────────────────────────────────────────

def _decode_timestamp(data_5bit):
    """Extract timestamp (first 7 words = 35 bits)."""
    if len(data_5bit) < 7:
        return 0

    bits = []
    for w in data_5bit[:7]:
        for i in range(4, -1, -1):
            bits.append((w >> i) & 1)

    ts = 0
    for b in bits[:35]:
        ts = (ts << 1) | b
    return ts


# ─── Main Parser ───────────────────────────────────────────────────────

def parse_invoice(invoice_str):
    """Parse a BOLT-11 Lightning invoice.

    Args:
        invoice_str: Full bolt11 string (e.g., 'lnbc2500u1pvjluez...')

    Returns:
        dict with payment info. Key fields:
            payment_request, currency, network, has_amount, amount_sats,
            timestamp, timestamp_iso, expiry_seconds, expires_at_iso,
            payment_hash, description, payment_secret, payee_pubkey,
            route_hints, features, fallback_address, signature, valid.
    """
    if not invoice_str or not isinstance(invoice_str, str):
        raise ValueError("Empty or invalid invoice string")

    hrp, data_5bit = decode_bech32(invoice_str)
    if hrp is None:
        raise ValueError("Invalid bech32 encoding or checksum")

    if not (hrp.startswith('lnbc') or hrp.startswith('lntb')):
        raise ValueError(f"Unknown currency prefix in HRP: {hrp}")

    # Parse amount from HRP
    amount_info = _parse_amount_from_hrp(hrp)

    # Timestamp: first 7 words
    timestamp = _decode_timestamp(data_5bit)
    ts_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)

    # Tagged fields: after timestamp (skip 7 words), before signature (last
    # 104)
    tagged_fields_5bit = data_5bit[7:-104] if len(
        data_5bit) >= 111 else data_5bit[7:]

    fields = _decode_tagged_fields(tagged_fields_5bit)
    signature = _decode_signature(data_5bit)

    # Build result
    currency = amount_info['currency']
    result = {
        'payment_request': invoice_str,
        'currency': currency,
        'network': _network_name(currency),
        'has_amount': amount_info.get('has_amount', False),
        'amount_sats': amount_info.get('amount_sats'),
        'amount_msat': amount_info.get('amount_msat', 0),
        'timestamp': timestamp,
        'timestamp_iso': ts_dt.isoformat(),
        'expiry_seconds': fields.get('expiry', 3600),
        'expires_at_iso':
        datetime.fromtimestamp(timestamp + fields.get('expiry', 3600),
                               tz=timezone.utc).isoformat(),
        'payment_hash': fields.get('payment_hash', ''),
        'valid': True,
    }

    # Optional fields
    for k in ('description', 'description_hash', 'payment_secret',
              'payee_pubkey', 'min_final_cltv_expiry', 'features'):
        if k in fields:
            result[k] = fields[k]

    if 'route_hints' in fields:
        result['route_hints'] = fields['route_hints']

    if 'fallback_address' in fields:
        result['fallback_address'] = fields['fallback_address']

    if signature:
        result['signature'] = signature

    if not result.get('payment_hash'):
        result['valid'] = False

    return result


def _network_name(currency):
    return {'bc': 'mainnet', 'tb': 'testnet', 'bcrt': 'regtest'}.get(
        currency, 'unknown')


# ─── CLI ───────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 nwc_bolt11.py <bolt11_invoice>",
              file=sys.stderr)
        sys.exit(1)

    try:
        result = parse_invoice(sys.argv[1])
        print(json.dumps(result, indent=2))
        sys.exit(0 if result['valid'] else 1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
