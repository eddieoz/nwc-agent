#!/usr/bin/env python3
"""
Nostr Wallet Connect (NIP-47) Python Client for any NIP-47 compatible wallet.
Zero external crypto dependency — pure Python secp256k1 + ChaCha20-Poly1305.
Requires: pyaes, websocket-client, pyyaml (pip install -r requirements.txt)
"""
import asyncio
import base64
import hashlib
import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import threading
import time
from binascii import hexlify, unhexlify

import pyaes
import yaml
from websocket import create_connection

# ─── Module-level state ─────────────────────────────────────────────────
DEBUG = False

# ─── secp256k1 constants ───────────────────────────────────────────────
SECP256K1_P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
SECP256K1_GX = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
SECP256K1_GY = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8
# Cache generator point
G = (SECP256K1_GX, SECP256K1_GY)

# NWC constants
NWC_REQUEST_KIND = 23194
NWC_RESPONSE_KIND = 23195
MAX_RETRIES = 2  # per relay
DEFAULT_TIMEOUT = 15  # seconds for relay responses
USE_NIP44 = False  # Set True for NIP-44 (ChaCha20-Poly1305) — requires wallet with NIP-44 support (Alby Hub >= 1.8.0)


def mod_inverse(a, p):
    """Modular inverse using pow (Python 3.8+)."""
    return pow(a, p - 2, p)


def point_add(p1, p2):
    """Add two secp256k1 points. Points are (x, y) tuples or None for infinity."""
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2:
        if y1 != y2:
            return None  # P + (-P) = O
        # Point doubling
        m = (3 * x1 * x1) * mod_inverse(2 * y1, SECP256K1_P) % SECP256K1_P
    else:
        m = (y2 - y1) * mod_inverse(x2 - x1, SECP256K1_P) % SECP256K1_P
    x3 = (m * m - x1 - x2) % SECP256K1_P
    y3 = (m * (x1 - x3) - y1) % SECP256K1_P
    return (x3, y3)


def point_mul(k, point):
    """Multiply point by scalar k using double-and-add."""
    if k == 0:
        return None
    result = None
    addend = point
    while k:
        if k & 1:
            result = point_add(result, addend)
        addend = point_add(addend, addend)
        k >>= 1
    return result


def bytes_to_int(b):
    return int.from_bytes(b, 'big')


def int_to_bytes(i, length=0):
    """Convert int to big-endian bytes, minimal length if not specified."""
    if length > 0:
        return i.to_bytes(length, 'big')
    if i == 0:
        return b'\x00'
    byte_len = (i.bit_length() + 7) // 8
    return i.to_bytes(byte_len, 'big')


def tagged_hash(tag, data):
    """BIP-340 tagged hash: SHA256(SHA256(tag) || SHA256(tag) || data)"""
    tag_hash = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(tag_hash + tag_hash + data).digest()


def schnorr_deterministic_nonce(privkey_bytes, msg32, pubkey_x):
    """Derive a deterministic nonce for BIP-340 Schnorr signing.
    
    Uses a simplified RFC 6979 approach: k = SHA256(privkey || msg32 || pubkey_x).
    This eliminates the random nonce loop (timing channel) and prevents
    catastrophic nonce reuse that would leak the private key.
    
    Produces signatures byte-for-byte compatible with any BIP-340 verifier.
    """
    h = hashlib.sha256(privkey_bytes + msg32 + pubkey_x).digest()
    k = bytes_to_int(h) % SECP256K1_N
    if k == 0:
        k = 1  # RFC 6979 fallback
    return k


def schnorr_sign(privkey_bytes, msg32, use_rfc6979=True):
    """BIP-340 Schnorr signature over secp256k1.
    
    Args:
        privkey_bytes: 32-byte private key
        msg32: 32-byte message hash to sign
        use_rfc6979: If True (default), use deterministic nonces (RFC 6979).
                     Set False for the legacy random nonce (os.urandom).
    """
    d = bytes_to_int(privkey_bytes)
    if d == 0 or d >= SECP256K1_N:
        raise ValueError("Invalid private key")

    # Compute P = d*G and check y parity
    P = point_mul(d, G)
    if P is None:
        raise ValueError("P is point at infinity")

    # If P.y is odd, negate d (BIP-340: use even-y pubkey for signing)
    if P[1] % 2 != 0:
        d = SECP256K1_N - d

    # x-only pubkey
    pubkey_x = int_to_bytes(P[0], 32)

    # Generate nonce k
    if use_rfc6979:
        k = schnorr_deterministic_nonce(privkey_bytes, msg32, pubkey_x)
    else:
        k = bytes_to_int(os.urandom(32))
        while k == 0 or k >= SECP256K1_N:
            k = bytes_to_int(os.urandom(32))

    # R = k*G
    R = point_mul(k, G)
    if R is None:
        raise RuntimeError("R is point at infinity")
    Rx, Ry = R

    # Negate k if Ry is odd (BIP-340)
    if Ry % 2 != 0:
        k = SECP256K1_N - k
        Ry = SECP256K1_P - Ry

    # e = tagged_hash("BIP0340/challenge", Rx_bytes || Px_bytes || msg32)
    e_bytes = tagged_hash("BIP0340/challenge",
                          int_to_bytes(Rx, 32) + pubkey_x + msg32)
    e = bytes_to_int(e_bytes) % SECP256K1_N

    # s = k + e*d mod n
    s = (k + e * d) % SECP256K1_N

    # Signature: Rx (32 bytes) || s (32 bytes)
    return int_to_bytes(Rx, 32) + int_to_bytes(s, 32)


# ─── DER Encoding ──────────────────────────────────────────────────────

def _der_encode_sequence(data):
    return b'\x30' + _der_length(len(data)) + data


def _der_encode_integer(val):
    if val == 0:
        return bytes([2, 1, 0])
    b = int_to_bytes(val)
    if b[0] & 0x80:
        b = b'\x00' + b
    return b'\x02' + _der_length(len(b)) + b


def _der_encode_octet_string(data):
    return b'\x04' + _der_length(len(data)) + data


def _der_encode_bit_string(data):
    return b'\x03' + _der_length(len(data) + 1) + b'\x00' + data


def _der_encode_explicit(tag, data):
    """Encode data in an EXPLICIT context-specific tag."""
    return bytes([0xa0 | tag]) + _der_length(len(data)) + data


def _der_length(length):
    if length < 128:
        return bytes([length])
    bl = int_to_bytes(length)
    return bytes([0x80 | len(bl)]) + bl


def _make_ec_private_key_der(privkey_bytes):
    """Create DER-encoded ECPrivateKey for secp256k1."""
    priv_int = bytes_to_int(privkey_bytes)
    pub = point_mul(priv_int, G)
    if pub is None:
        raise ValueError("Invalid private key")

    pubkey_bytes = b'\x04' + int_to_bytes(pub[0], 32) + int_to_bytes(
        pub[1], 32)

    priv_octet = _der_encode_octet_string(privkey_bytes)
    ver_int = _der_encode_integer(1)
    param_oid = bytes.fromhex(
        "a00706052b8104000a")  # [0] EXPLICIT OID for secp256k1
    pub_bitstring = _der_encode_explicit(1,
                                         _der_encode_bit_string(pubkey_bytes))

    inner = ver_int + priv_octet + param_oid + pub_bitstring
    return _der_encode_sequence(inner)


def _find_bitstring_xonly(der):
    """Recursively find a BIT STRING with 33-byte compressed point, return x-only pubkey."""
    i = 0
    while i < len(der):
        tag = der[i]
        if i + 1 >= len(der):
            break

        if der[i + 1] & 0x80:
            num_len = der[i + 1] & 0x7f
            if i + 1 + num_len >= len(der):
                break
            vlen = 0
            for j in range(num_len):
                vlen = (vlen << 8) | der[i + 2 + j]
            hdr_len = 2 + num_len
        else:
            vlen = der[i + 1]
            hdr_len = 2

        val_start = i + hdr_len
        if val_start + vlen > len(der):
            break

        if tag == 0x03:  # BIT STRING
            if vlen >= 1:
                unused = der[val_start]
                point_data = bytes(der[val_start + 1:val_start + vlen])
                if len(point_data) == 33 and point_data[0] in (0x02, 0x03):
                    return point_data[1:33]  # x-only pubkey
        elif tag in (0x30, 0x31):  # SEQUENCE or SET - recurse
            result = _find_bitstring_xonly(der[val_start:val_start + vlen])
            if result:
                return result

        i += hdr_len + vlen

    return None


def ecprivkey_from_bytes(privkey_bytes):
    """Load a raw 32-byte private key and return (ec_der, xonly_pubkey_bytes)."""
    ec_der = _make_ec_private_key_der(privkey_bytes)

    r = subprocess.run([
        "openssl", "ec", "-pubout", "-inform", "DER", "-conv_form",
        "compressed", "-outform", "DER"
    ],
                       capture_output=True,
                       timeout=10,
                       input=ec_der)
    if r.returncode != 0:
        raise RuntimeError(f"openssl pubkey failed: {r.stderr.decode()}")

    der = r.stdout
    x_bytes = _find_bitstring_xonly(der)
    if x_bytes:
        return ec_der, x_bytes
    raise RuntimeError("Could not parse compressed pubkey")


def ecdh_raw(privkey_bytes, pubkey_x_bytes):
    """Derive raw ECDH shared secret (no hashing). Used for NIP-44."""
    x = bytes_to_int(pubkey_x_bytes)
    y_sq = (pow(x, 3, SECP256K1_P) + 7) % SECP256K1_P
    y = pow(y_sq, (SECP256K1_P + 1) // 4, SECP256K1_P)
    if y % 2 != 0:
        y = SECP256K1_P - y

    pubkey_bytes = b'\x04' + pubkey_x_bytes + int_to_bytes(y, 32)
    ec_der = _make_ec_private_key_der(privkey_bytes)

    with tempfile.NamedTemporaryFile(suffix='.der', delete=True) as pf:
        algo_id = bytes.fromhex("301006072a8648ce3d020106052b8104000a")
        pubkey_bits = _der_encode_bit_string(pubkey_bytes)
        spki = _der_encode_sequence(algo_id + pubkey_bits)
        pf.write(spki)
        pf.flush()

        r = subprocess.run([
            "openssl", "pkeyutl", "-derive", "-inkey", "/dev/stdin",
            "-keyform", "DER", "-peerkey", pf.name, "-peerform", "DER"
        ],
                           capture_output=True,
                           timeout=10,
                           input=ec_der)
        if r.returncode != 0:
            raise RuntimeError(f"ECDH failed: {r.stderr.decode()}")
        return r.stdout


def ecdh_shared_secret(privkey_bytes, pubkey_x_bytes):
    """Derive ECDH shared secret: SHA256(ECDH(privkey, pubkey)). Used for NIP-04."""
    raw = ecdh_raw(privkey_bytes, pubkey_x_bytes)
    return hashlib.sha256(raw).digest()


# ─── NWC URL Parsing ───────────────────────────────────────────────────

def parse_nwc_url(url):
    """Parse a nostr+walletconnect:// URL."""
    rest = url[len("nostr+walletconnect://"):]
    if '?' in rest:
        pubkey, query = rest.split('?', 1)
    else:
        pubkey, query = rest, ""

    params = {}
    for part in query.split('&'):
        if '=' in part:
            k, v = part.split('=', 1)
            if k not in params:
                params[k] = [v]
            else:
                if isinstance(params[k], list):
                    params[k].append(v)
                else:
                    params[k] = [params[k], v]

    relays = params.get('relay', [])
    if isinstance(relays, str):
        relays = [relays]

    secret = params.get('secret', [None])[0]

    return {
        'wallet_pubkey': pubkey,
        'relays': relays,
        'secret': secret
    }


# ─── Encryption (NIP-04 + NIP-44) ─────────────────────────────────────

def encrypt_nwc_payload(plaintext, shared_key):
    """Encrypt payload with AES-256-CBC (NIP-04 format).
    shared_key = raw ECDH x-coordinate (32 bytes), NOT SHA256 hashed.
    Output: base64(ciphertext)?iv=base64(iv) — matches Go go-nostr library.
    """
    iv = os.urandom(16)
    aes = pyaes.AESModeOfOperationCBC(shared_key, iv)

    block_size = 16
    pad_len = block_size - (len(plaintext) % block_size)
    padded = plaintext + bytes([pad_len] * pad_len)

    ciphertext = b''
    for i in range(0, len(padded), block_size):
        ciphertext += aes.encrypt(padded[i:i + block_size])

    return base64.b64encode(ciphertext).decode(
    ) + "?iv=" + base64.b64encode(iv).decode()


def encrypt_nwc_payload_nip44(plaintext_bytes, raw_ecdh):
    """Encrypt payload with NIP-44 v2 (ChaCha20-Poly1305).
    Returns base64: version(2) || nonce(32) || ciphertext || mac(32).
    """
    nonce = os.urandom(32)
    conversation_key = _hkdf_extract(salt=b'nip44-v2', ikm=raw_ecdh)
    msg_keys = _hkdf_expand(conversation_key, info=nonce, length=76)
    chacha_key = msg_keys[:32]
    chacha_nonce = msg_keys[32:44]
    hmac_key = msg_keys[44:76]

    unpadded_len = len(plaintext_bytes)
    if unpadded_len < 1 or unpadded_len > 65535:
        raise ValueError(f"Invalid plaintext length: {unpadded_len}")

    padded_len = _calc_padded_len(unpadded_len)
    padded = unpadded_len.to_bytes(2, 'big') + plaintext_bytes + b'\x00' * (
        padded_len - unpadded_len)

    ciphertext = _chacha20_xor(chacha_key, chacha_nonce, padded)
    mac = _hmac_sha256(hmac_key, nonce + ciphertext)

    payload = bytes([2]) + nonce + ciphertext + mac
    return base64.b64encode(payload).decode()


def decrypt_nwc_payload(encrypted, shared_key, raw_ecdh=None):
    """Decrypt NWC payload. Handles NIP-04 (AES-CBC) and NIP-44 (ChaCha20-Poly1305).
    shared_key = raw ECDH x-coordinate for NIP-04 (Go uses raw, not SHA256).
    raw_ecdh = raw ECDH x-coordinate for NIP-44 HKDF.
    """
    # Legacy format: base64(ciphertext)?iv=base64(iv)
    if '?iv=' in encrypted:
        parts = encrypted.split("?iv=")
        iv = base64.b64decode(parts[1])
        ciphertext = base64.b64decode(parts[0])

        aes = pyaes.AESModeOfOperationCBC(shared_key, iv)
        plaintext = b''
        for i in range(0, len(ciphertext), 16):
            plaintext += aes.decrypt(ciphertext[i:i + 16])
        pad_len = plaintext[-1]
        return plaintext[:-pad_len].decode()

    raw = base64.b64decode(encrypted)

    # NIP-04: base64(IV(16) || ciphertext) — ciphertext is multiple of 16
    if len(raw) >= 16 and (len(raw) - 16) % 16 == 0:
        iv = raw[:16]
        ciphertext = raw[16:]

        aes = pyaes.AESModeOfOperationCBC(shared_key, iv)
        plaintext = b''
        for i in range(0, len(ciphertext), 16):
            plaintext += aes.decrypt(ciphertext[i:i + 16])
        pad_len = plaintext[-1]
        return plaintext[:-pad_len].decode()

    # NIP-44: version(2) || nonce(32) || ciphertext || mac(32)
    if len(raw) >= 99 and raw[0] == 2:
        if raw_ecdh is None:
            raise ValueError(
                "NIP-44 decryption requires raw ECDH shared secret")
        return _nip44_decrypt(raw, raw_ecdh)

    raise ValueError(f"Cannot decrypt payload: {len(raw)} bytes")


# ─── Pure Python ChaCha20 + Poly1305 + HKDF ─────────────────────────────

def _rotl32(v, c):
    return ((v << c) | (v >> (32 - c))) & 0xFFFFFFFF


def _chacha20_quarter_round(a, b, c, d):
    a = (a + b) & 0xFFFFFFFF
    d ^= a
    d = _rotl32(d, 16)
    c = (c + d) & 0xFFFFFFFF
    b ^= c
    b = _rotl32(b, 12)
    a = (a + b) & 0xFFFFFFFF
    d ^= a
    d = _rotl32(d, 8)
    c = (c + d) & 0xFFFFFFFF
    b ^= c
    b = _rotl32(b, 7)
    return a, b, c, d


def _chacha20_block(key, nonce, counter):
    """Generate 64-byte ChaCha20 keystream block."""
    state = [
        0x61707865, 0x3320646e, 0x79622d32, 0x6b206574,
        int.from_bytes(key[0:4], 'little'),
        int.from_bytes(key[4:8], 'little'),
        int.from_bytes(key[8:12], 'little'),
        int.from_bytes(key[12:16], 'little'),
        int.from_bytes(key[16:20], 'little'),
        int.from_bytes(key[20:24], 'little'),
        int.from_bytes(key[24:28], 'little'),
        int.from_bytes(key[28:32], 'little'), counter & 0xFFFFFFFF,
        int.from_bytes(nonce[0:4], 'little'),
        int.from_bytes(nonce[4:8], 'little'),
        int.from_bytes(nonce[8:12], 'little'),
    ]
    working = list(state)
    for _ in range(10):
        # Column rounds
        working[0], working[4], working[8], working[12] = _chacha20_quarter_round(
            working[0], working[4], working[8], working[12])
        working[1], working[5], working[9], working[13] = _chacha20_quarter_round(
            working[1], working[5], working[9], working[13])
        working[2], working[6], working[10], working[14] = _chacha20_quarter_round(
            working[2], working[6], working[10], working[14])
        working[3], working[7], working[11], working[15] = _chacha20_quarter_round(
            working[3], working[7], working[11], working[15])
        # Diagonal rounds
        working[0], working[5], working[10], working[15] = _chacha20_quarter_round(
            working[0], working[5], working[10], working[15])
        working[1], working[6], working[11], working[12] = _chacha20_quarter_round(
            working[1], working[6], working[11], working[12])
        working[2], working[7], working[8], working[13] = _chacha20_quarter_round(
            working[2], working[7], working[8], working[13])
        working[3], working[4], working[9], working[14] = _chacha20_quarter_round(
            working[3], working[4], working[9], working[14])
    out = b''
    for i in range(16):
        val = (working[i] + state[i]) & 0xFFFFFFFF
        out += val.to_bytes(4, 'little')
    return out


def _chacha20_xor(key, nonce, data, initial_counter=0):
    """ChaCha20 XOR ciphertext/plaintext."""
    result = bytearray()
    counter = initial_counter
    for i in range(0, len(data), 64):
        block = _chacha20_block(key, nonce, counter)
        chunk = data[i:i + 64]
        for j in range(len(chunk)):
            result.append(chunk[j] ^ block[j])
        counter += 1
    return bytes(result)


def _poly1305_mac(key, data):
    """Poly1305 MAC. key is 32 bytes (r || s)."""
    r_bytes = key[:16]
    s_bytes = key[16:32]

    r = list(r_bytes)
    r[3] &= 15
    r[7] &= 15
    r[11] &= 15
    r[15] &= 15
    r[4] &= 252
    r[8] &= 252
    r[12] &= 252

    r_int = int.from_bytes(bytes(r), 'little')

    accumulator = 0
    p = (1 << 130) - 5

    for i in range(0, len(data), 16):
        block = data[i:i + 16]
        n = int.from_bytes(block + b'\x01', 'little')
        accumulator = (accumulator + n) % p
        accumulator = (accumulator * r_int) % p

    s_int = int.from_bytes(s_bytes, 'little')
    accumulator = (accumulator + s_int) & ((1 << 128) - 1)

    return accumulator.to_bytes(16, 'little')


def _hmac_sha256(key, data):
    """HMAC-SHA256."""
    import hmac as _hmac
    return _hmac.new(key, data, hashlib.sha256).digest()


def _hkdf_extract(salt, ikm):
    """HKDF-Extract: HMAC-SHA256(salt, ikm)."""
    return _hmac_sha256(salt, ikm)


def _hkdf_expand(prk, info, length):
    """HKDF-Expand: generates `length` bytes of output key material."""
    n = (length + 31) // 32
    t = b''
    okm = b''
    for i in range(1, n + 1):
        t = _hmac_sha256(prk, t + info + bytes([i]))
        okm += t
    return okm[:length]


def _calc_padded_len(unpadded_len):
    """NIP-44 padding length calculation."""
    if unpadded_len <= 0:
        raise ValueError("Invalid unpadded length")
    next_power = 1 << ((unpadded_len - 1).bit_length())
    if next_power <= 256:
        chunk = 32
    else:
        chunk = next_power // 8
    if unpadded_len <= 32:
        return 32
    return chunk * (((unpadded_len - 1) // chunk) + 1)


def _nip44_decrypt(payload, raw_ecdh):
    """Decrypt NIP-44 v2 payload (ChaCha20-Poly1305)."""
    if len(payload) < 99:
        raise ValueError(f"NIP-44 payload too short: {len(payload)} bytes")

    version = payload[0]
    if version != 2:
        raise ValueError(f"Unsupported NIP-44 version: {version}")

    nonce = payload[1:33]
    ciphertext = payload[33:-32]
    mac = payload[-32:]

    conversation_key = _hkdf_extract(salt=b'nip44-v2', ikm=raw_ecdh)
    if len(conversation_key) != 32:
        raise ValueError("Invalid conversation_key length")

    msg_keys = _hkdf_expand(conversation_key, info=nonce, length=76)
    chacha_key = msg_keys[:32]
    chacha_nonce = msg_keys[32:44]
    hmac_key = msg_keys[44:76]

    expected_mac = _hmac_sha256(hmac_key, nonce + ciphertext)
    if not _constant_time_compare(mac, expected_mac):
        raise ValueError("NIP-44 MAC verification failed")

    plaintext = _chacha20_xor(chacha_key, chacha_nonce, ciphertext)

    if len(plaintext) < 2:
        raise ValueError("Decrypted data too short")
    unpadded_len = int.from_bytes(plaintext[:2], 'big')
    unpadded = plaintext[2:2 + unpadded_len]
    if len(unpadded) != unpadded_len:
        raise ValueError("Invalid plaintext length in padding")

    return unpadded.decode()


def _constant_time_compare(a, b):
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= x ^ y
    return result == 0


# ─── Nostr Event Creation ──────────────────────────────────────────────

def create_nostr_event(pubkey_bytes, kind, tags, content, privkey_bytes):
    """Create and sign a Nostr event (Schnorr/BIP-340)."""
    created_at = int(time.time())

    event = [
        0,
        hexlify(pubkey_bytes).decode(), created_at, kind, tags, content
    ]

    serialized = json.dumps(event, separators=(',', ':'), ensure_ascii=False)
    msg32 = hashlib.sha256(serialized.encode()).digest()

    sig = schnorr_sign(privkey_bytes, msg32)

    return {
        'id': hexlify(msg32).decode(),
        'pubkey': hexlify(pubkey_bytes).decode(),
        'created_at': created_at,
        'kind': kind,
        'tags': tags,
        'content': content,
        'sig': hexlify(sig).decode()
    }


# ─── NWC Protocol Core ─────────────────────────────────────────────────

def _debug_event(result, label):
    """Log event structure without exposing secrets.
    
    Prints keys/shape of the response so developers can debug protocol flow
    without leaking preimages, balances, or decrypted payloads to stderr.
    """
    if not DEBUG:
        return
    try:
        if isinstance(result, dict):
            safe = {
                'type': result.get('result_type', 'unknown'),
                'has_result': 'result' in result,
                'has_error': 'error' in result,
                'result_keys': list(result.get('result', {}).keys())
                if isinstance(result.get('result'), dict) else [],
            }
        else:
            safe = {'raw_type': type(result).__name__}
        print(f"[DEBUG] {label}: {json.dumps(safe)}", file=sys.stderr)
    except Exception:
        pass  # Never let debug code crash production


def _prepare_nwc_event(nwc_url, method, params=None):
    """Create client key material, encrypt payload, return (event, config).
    
    Encryption format is controlled by the global USE_NIP44 flag.
    Default: NIP-04 (AES-256-CBC). Set USE_NIP44=True for NIP-44
    (ChaCha20-Poly1305, requires wallet with NIP-44 support). Use --nip44 CLI flag.
    """
    config = parse_nwc_url(nwc_url)

    client_privkey = unhexlify(config['secret'])
    wallet_pubkey = unhexlify(config['wallet_pubkey'])
    _, client_pubkey_x = ecprivkey_from_bytes(client_privkey)
    shared_key = ecdh_raw(client_privkey, wallet_pubkey)

    if params is None:
        params = {}

    request_payload = json.dumps({"method": method, "params": params})
    if USE_NIP44:
        encrypted = encrypt_nwc_payload_nip44(request_payload.encode(), shared_key)
    else:
        encrypted = encrypt_nwc_payload(request_payload.encode(), shared_key)

    event = create_nostr_event(client_pubkey_x, NWC_REQUEST_KIND,
                               [["p",
                                 hexlify(wallet_pubkey).decode()]], encrypted,
                               client_privkey)

    return event, config, shared_key


async def nwc_request(nwc_url, method, params=None):
    """Make a NWC request to a NIP-47 wallet and wait for response."""
    event, config, shared_key = _prepare_nwc_event(nwc_url, method, params)
    return await _listen_for_response(event, config, shared_key)


async def _listen_for_response(event, config, shared_key):
    """Send event to relay and listen for kind 23195 response.
    Tries all relays from NWC URL, not just the first.
    Uses single WebSocket connection: subscribe first, then send, then poll.
    """
    relays = config['relays']
    event_id = event['id']
    _, client_pubkey_x = ecprivkey_from_bytes(
        unhexlify(config['secret']))
    pubkey_hex = hexlify(client_pubkey_x).decode()
    raw_ecdh = shared_key  # same value for NIP-44

    for relay_url in relays:
        for attempt in range(MAX_RETRIES):
            ws = None
            try:
                ws = create_connection(relay_url, timeout=10)
                ws.settimeout(DEFAULT_TIMEOUT)

                # Subscribe first on same connection
                sub_id = hexlify(os.urandom(8)).decode()
                ws.send(
                    json.dumps([
                        "REQ", sub_id, {
                            "kinds": [NWC_RESPONSE_KIND],
                            "#p": [pubkey_hex],
                            "#e": [event_id],
                            "limit": 1,
                        }
                    ]))

                # Then send the event
                ws.send(json.dumps(["EVENT", event]))

                # Read responses until we get our EVENT or timeout
                deadline = time.time() + 8
                while time.time() < deadline:
                    try:
                        resp = ws.recv()
                    except Exception:
                        break
                    try:
                        data = json.loads(resp)
                    except Exception:
                        continue
                    if (isinstance(data, list) and len(data) >= 3
                            and data[0] == "EVENT"):
                        try:
                            resp_event = data[2]
                            if (isinstance(resp_event, dict)
                                    and resp_event.get('kind')
                                    == NWC_RESPONSE_KIND):
                                content = resp_event['content']
                                if DEBUG:
                                    print(
                                        f"[DEBUG] NWC response received "
                                        f"({len(content)} bytes encrypted)",
                                        file=sys.stderr)
                                decrypted = decrypt_nwc_payload(
                                    content, shared_key, raw_ecdh)
                                result = json.loads(decrypted)
                                _debug_event(result, "NWC response")
                                return result
                        except Exception:
                            if DEBUG:
                                import traceback
                                traceback.print_exc(file=sys.stderr)
                            continue
            except Exception as e:
                if DEBUG:
                    import traceback
                    traceback.print_exc(file=sys.stderr)
                time.sleep(1)
            finally:
                if ws:
                    try:
                        ws.close()
                    except Exception:
                        pass

    raise RuntimeError("No response from relay")


def nwc_send_fire_and_forget(nwc_url, method, params=None):
    """Send an NWC event without waiting for response.
    Like python_nwc's tryToPayInvoice — returns immediately.
    User must call lookup_invoice/check_payment to verify.
    """
    event, config, shared_key = _prepare_nwc_event(nwc_url, method, params)
    relay_url = config['relays'][0]

    ws = None
    try:
        ws = create_connection(relay_url, timeout=10)
        ws.send(json.dumps(["EVENT", event]))
    finally:
        if ws:
            try:
                ws.close()
            except Exception:
                pass

    return {"sent": True, "event_id": event['id']}


# ─── NWC Wallet Commands ───────────────────────────────────────────────

async def cmd_balance(nwc_url):
    """Check wallet balance (synchronous — waits for response)."""
    result = await nwc_request(nwc_url, "get_balance")
    if 'error' in result:
        err = result['error']
        return json.dumps({"error": err.get('message', str(err))})
    balance_msat = result.get('result', {}).get('balance', 0)
    return f"Balance: {balance_msat // 1000} sats"


async def cmd_pay_invoice(nwc_url, bolt11):
    """Pay a bolt11 invoice and wait for confirmation.
    Blocks until relay confirms or timeout (25s).
    """
    result = await nwc_request(nwc_url, "pay_invoice",
                               {"invoice": bolt11})
    resp = result.get('result', {})
    preimage = resp.get('preimage', '')
    return json.dumps({
        "paid": bool(preimage),
        "preimage": preimage,
        "event_id": result.get('event_id', '')
    })


def cmd_pay_invoice_async(nwc_url, bolt11):
    """Pay a bolt11 invoice, fire-and-forget. 
    Use check_payment to verify completion.
    """
    return json.dumps(
        nwc_send_fire_and_forget(nwc_url, "pay_invoice",
                                 {"invoice": bolt11}))


async def cmd_lookup_invoice(nwc_url, payment_hash):
    """Look up an invoice by payment_hash."""
    result = await nwc_request(nwc_url, "lookup_invoice",
                               {"payment_hash": payment_hash})
    return json.dumps(result.get('result', {}))


async def cmd_check_payment(nwc_url, payment_hash):
    """Check if payment was received. Returns preimage if paid."""
    result = await nwc_request(nwc_url, "lookup_invoice",
                               {"payment_hash": payment_hash})
    resp = result.get('result', {})
    preimage = resp.get('preimage', '')
    if preimage:
        return json.dumps({
            "paid": True,
            "preimage": preimage,
            "settled_at": resp.get('settled_at')
        })
    return json.dumps({
        "paid": False,
        "reason": resp.get('error', 'not settled yet')
    })


async def cmd_make_invoice(nwc_url, amount_sats, description=""):
    """Create an invoice to receive payment."""
    if amount_sats <= 0:
        return json.dumps({"error": "Amount must be positive (sats)"})
    result = await nwc_request(nwc_url, "make_invoice", {
        "amount": amount_sats * 1000,
        "description": description
    })
    return json.dumps(result.get('result', {}))


async def cmd_get_info(nwc_url):
    """Get wallet info (alias, color, supported methods)."""
    result = await nwc_request(nwc_url, "get_info")
    return json.dumps(result.get('result', {}))


async def cmd_list_transactions(nwc_url, tx_type=None, limit=20, offset=0):
    """List wallet transactions. tx_type: 'incoming', 'outgoing', or None for all."""
    params = {"limit": limit, "offset": offset}
    if tx_type:
        params["type"] = tx_type
    result = await nwc_request(nwc_url, "list_transactions", params)
    return json.dumps(result.get('result', {}))


# ─── CLI Interface ─────────────────────────────────────────────────────

def load_nwc_url():
    """Load NWC URL through priority-gated chain.
    
    Resolution order (first match wins):
    1. Skill-local .env           — $SKILL_DIR/.env
    2. Agent home .env            — ~/.env
    3. Security file (legacy)     — /root/.picoclaw/.security.yml
    4. Environment variable       — $ALBY_NWC_URL
    """
    import configparser

    # 1. Skill-local .env
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    skill_env = os.path.join(skill_dir, '.env')
    try:
        if os.path.isfile(skill_env):
            cfg = configparser.ConfigParser()
            with open(skill_env) as f:
                cfg.read_string('[DEFAULT]\n' + f.read())
            nwc_url = cfg.get('DEFAULT', 'ALBY_NWC_URL', fallback=None)
            if nwc_url and nwc_url.strip('"\' '):
                if DEBUG:
                    print(f"[DEBUG] NWC URL from skill .env: {skill_env}",
                          file=sys.stderr)
                return nwc_url.strip('"\' ')
    except Exception as e:
        if DEBUG:
            print(f"[DEBUG] skill .env read skipped ({type(e).__name__})",
                  file=sys.stderr)

    # 2. Agent home .env
    home_env = os.path.expanduser('~/.env')
    try:
        if os.path.isfile(home_env):
            cfg = configparser.ConfigParser()
            with open(home_env) as f:
                cfg.read_string('[DEFAULT]\n' + f.read())
            nwc_url = cfg.get('DEFAULT', 'ALBY_NWC_URL', fallback=None)
            if nwc_url and nwc_url.strip('"\' '):
                if DEBUG:
                    print(f"[DEBUG] NWC URL from home .env: {home_env}",
                          file=sys.stderr)
                return nwc_url.strip('"\' ')
    except Exception as e:
        if DEBUG:
            print(f"[DEBUG] home .env read skipped ({type(e).__name__})",
                  file=sys.stderr)

    # 3. Legacy security file
    security_file = "/root/.picoclaw/.security.yml"
    try:
        with open(security_file) as f:
            data = yaml.safe_load(f)
        nwc_url = data.get('alby_nwc_url')
        if nwc_url:
            if DEBUG:
                print(f"[DEBUG] NWC URL from security.yml: {security_file}",
                      file=sys.stderr)
            return nwc_url
    except Exception as e:
        if DEBUG:
            print(f"[DEBUG] security.yml read skipped ({type(e).__name__})",
                  file=sys.stderr)

    # 4. Environment variable
    nwc_url = os.getenv('ALBY_NWC_URL')
    if nwc_url:
        if DEBUG:
            print("[DEBUG] NWC URL from ALBY_NWC_URL env var",
                  file=sys.stderr)
        return nwc_url

    return None


def main():
    global DEBUG, USE_NIP44

    nwc_url = load_nwc_url()
    if not nwc_url:
        print(
            "ERROR: No NWC URL found. Checked:\n"
            "  1. Skill-local .env\n"
            "  2. ~/.env\n"
            "  3. /root/.picoclaw/.security.yml\n"
            "  4. ALBY_NWC_URL environment variable\n"
            "Add ALBY_NWC_URL=nostr+walletconnect://... to any of these.",
            file=sys.stderr)
        sys.exit(1)

    # Parse --debug and --nip44 flags (can appear anywhere in args)
    args = [a for a in sys.argv[1:] if a not in ('--debug', '--nip44')]
    if '--debug' in sys.argv:
        DEBUG = True
    if '--nip44' in sys.argv:
        USE_NIP44 = True

    if len(args) < 1:
        print("Usage: nwc_wallet.py [--debug] [--nip44] <command> [args...]")
        print("Commands: balance, pay_invoice <bolt11>, pay_invoice_async <bolt11>,")
        print("          make_invoice <sats> [description],")
        print("          lookup_invoice <payment_hash>, check_payment <payment_hash>,")
        print("          list_transactions [type] [limit] [offset], get_info,")
        print("          fetch <url> [--method POST] [--body JSON] [--headers JSON] [--max-amount SATS],")
        print("          fiat_to_sats <amount> <currency>, sats_to_fiat <sats> <currency>,")
        print("          parse_invoice <bolt11>, discover [-q QUERY] [-p PROTOCOL]")
        sys.exit(1)

    cmd = args[0]

    try:
        if cmd == "balance":
            result = asyncio.run(cmd_balance(nwc_url))
        elif cmd == "pay_invoice":
            if len(args) < 2:
                print("Usage: nwc_wallet.py pay_invoice <bolt11>",
                      file=sys.stderr)
                sys.exit(1)
            result = asyncio.run(cmd_pay_invoice(nwc_url, args[1]))
        elif cmd == "pay_invoice_async":
            if len(args) < 2:
                print("Usage: nwc_wallet.py pay_invoice_async <bolt11>",
                      file=sys.stderr)
                sys.exit(1)
            result = cmd_pay_invoice_async(nwc_url, args[1])
        elif cmd == "make_invoice":
            if len(args) < 2:
                print(
                    "Usage: nwc_wallet.py make_invoice <sats> [description]",
                    file=sys.stderr)
                sys.exit(1)
            desc = args[2] if len(args) > 2 else ""
            result = asyncio.run(
                cmd_make_invoice(nwc_url, int(args[1]), desc))
        elif cmd == "lookup_invoice":
            if len(args) < 2:
                print(
                    "Usage: nwc_wallet.py lookup_invoice <payment_hash>",
                    file=sys.stderr)
                sys.exit(1)
            result = asyncio.run(cmd_lookup_invoice(nwc_url, args[1]))
        elif cmd == "check_payment":
            if len(args) < 2:
                print(
                    "Usage: nwc_wallet.py check_payment <payment_hash>",
                    file=sys.stderr)
                sys.exit(1)
            result = asyncio.run(cmd_check_payment(nwc_url, args[1]))
        elif cmd == "list_transactions":
            tx_type = args[1] if len(args) > 1 else None
            limit = int(args[2]) if len(args) > 2 else 20
            offset = int(args[3]) if len(args) > 3 else 0
            result = asyncio.run(
                cmd_list_transactions(nwc_url, tx_type, limit, offset))
        elif cmd == "get_info":
            result = asyncio.run(cmd_get_info(nwc_url))
        elif cmd == "fetch":
            # fetch <url> [--method POST] [--body JSON] [--headers JSON] [--max-amount SATS]
            method = 'GET'
            body = None
            headers = None
            max_amount = 0
            url = None
            i = 1
            while i < len(args):
                if args[i] == '--method' and i + 1 < len(args):
                    method = args[i + 1].upper()
                    i += 2
                elif args[i] == '--body' and i + 1 < len(args):
                    body = args[i + 1]
                    i += 2
                elif args[i] == '--headers' and i + 1 < len(args):
                    headers = args[i + 1]
                    i += 2
                elif args[i] == '--max-amount' and i + 1 < len(args):
                    max_amount = int(args[i + 1])
                    i += 2
                else:
                    url = args[i]
                    i += 1
            if not url:
                print("Usage: nwc_wallet.py fetch <url> [--method POST] [--body JSON] [--headers JSON] [--max-amount SATS]", file=sys.stderr)
                sys.exit(1)
            from nwc_fetch import cmd_fetch
            result = cmd_fetch(nwc_url, url, method, body, headers, max_amount)
        elif cmd == "fiat_to_sats":
            if len(args) < 3:
                print("Usage: nwc_wallet.py fiat_to_sats <amount> <currency>", file=sys.stderr)
                sys.exit(1)
            from nwc_fiat import fiat_to_sats
            r = fiat_to_sats(float(args[1]), args[2])
            result = json.dumps(r)
        elif cmd == "sats_to_fiat":
            if len(args) < 3:
                print("Usage: nwc_wallet.py sats_to_fiat <sats> <currency>", file=sys.stderr)
                sys.exit(1)
            from nwc_fiat import sats_to_fiat
            r = sats_to_fiat(int(args[1]), args[2])
            result = json.dumps(r)
        elif cmd == "parse_invoice":
            if len(args) < 2:
                print("Usage: nwc_wallet.py parse_invoice <bolt11>", file=sys.stderr)
                sys.exit(1)
            from nwc_bolt11 import parse_invoice
            result = json.dumps(parse_invoice(args[1]))
        elif cmd == "discover":
            query = None
            protocol = None
            sort = 'reliability'
            limit = 10
            i = 1
            while i < len(args):
                if args[i] == '-q' and i + 1 < len(args):
                    query = args[i + 1]
                    i += 2
                elif args[i] == '-p' and i + 1 < len(args):
                    protocol = args[i + 1]
                    i += 2
                elif args[i] == '--sort' and i + 1 < len(args):
                    sort = args[i + 1]
                    i += 2
                elif args[i] == '--limit' and i + 1 < len(args):
                    limit = int(args[i + 1])
                    i += 2
                else:
                    i += 1
            from nwc_discover import discover
            r = discover(q=query or '', protocol=protocol,
                         sort=sort, limit=limit)
            result = json.dumps(r)
        else:
            print(f"Unknown command: {cmd}", file=sys.stderr)
            sys.exit(1)

        print(result)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        if DEBUG:
            import traceback
            traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
