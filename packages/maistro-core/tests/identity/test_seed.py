"""Tests for maistro.identity — BIP39/BIP32 HD root of trust."""

from __future__ import annotations

import pytest
from bip_utils import Base58Decoder

from maistro.identity import PATHS, ConductorSeed


def test_generate_24_words() -> None:
    seed = ConductorSeed.generate()
    words = seed.mnemonic_words()
    assert len(words) == 24
    assert all(isinstance(w, str) and len(w) > 0 for w in words)


def test_from_mnemonic_list() -> None:
    seed = ConductorSeed.generate()
    words = seed.mnemonic_words()
    restored = ConductorSeed.from_mnemonic(words)
    assert restored.mnemonic_words() == words


def test_from_mnemonic_string() -> None:
    seed = ConductorSeed.generate()
    mnemonic = " ".join(seed.mnemonic_words())
    restored = ConductorSeed.from_mnemonic(mnemonic)
    assert restored.mnemonic_words() == seed.mnemonic_words()


def test_deterministic_derivation() -> None:
    seed = ConductorSeed.generate()
    words = seed.mnemonic_words()
    seed2 = ConductorSeed.from_mnemonic(words)

    for name in PATHS:
        k1 = seed.derive_named(name)
        k2 = seed2.derive_named(name)
        assert k1.public_key == k2.public_key, f"{name} not deterministic"
        assert k1.path == k2.path


def test_sign_and_verify() -> None:
    seed = ConductorSeed.generate()
    msg = b"hello conductor"
    sig = seed.sign("m/0'", msg)
    assert isinstance(sig, bytes)
    assert len(sig) == 64
    assert seed.verify("m/0'", msg, sig) is True


def test_verify_wrong_message() -> None:
    seed = ConductorSeed.generate()
    sig = seed.sign("m/0'", b"correct")
    assert seed.verify("m/0'", b"wrong", sig) is False


def test_verify_wrong_path() -> None:
    seed = ConductorSeed.generate()
    sig = seed.sign("m/0'", b"message")
    assert seed.verify("m/44'/9000'/0'", b"message", sig) is False


def test_different_seeds_produce_different_keys() -> None:
    s1 = ConductorSeed.generate()
    s2 = ConductorSeed.generate()
    assert s1.public_key("m/0'") != s2.public_key("m/0'")


def test_did_key_format() -> None:
    seed = ConductorSeed.generate()
    did = seed.did_key()
    assert did.startswith("did:key:z")
    assert len(did) > 20


def test_did_key_deterministic() -> None:
    seed = ConductorSeed.generate()
    did1 = seed.did_key()
    did2 = seed.did_key()
    assert did1 == did2

    restored = ConductorSeed.from_mnemonic(seed.mnemonic_words())
    assert restored.did_key() == did1


def test_did_key_custom_path() -> None:
    seed = ConductorSeed.generate()
    did_identity = seed.did_key("m/44'/9000'/0'")
    did_signing = seed.did_key("m/0'")
    assert did_identity != did_signing


def test_did_key_spec_compliant_decoding() -> None:
    """did:key must be base58btc (z-prefix) of multicodec 0xed01 + 32-byte pubkey.

    Per the did:key spec / multiformats: Ed25519 public keys use the
    multicodec varint 0xed01 followed by the raw 32-byte key, multibase-
    encoded with base58btc whose prefix character is 'z'.
    """
    seed = ConductorSeed.generate()
    pub = seed.public_key("m/44'/9000'/0'")
    assert len(pub) == 32

    did = seed.did_key("m/44'/9000'/0'")
    assert did.startswith("did:key:z")

    # Strip the did:key: scheme; the 'z' is the base58btc multibase prefix.
    multibase = did[len("did:key:") :]
    assert multibase[0] == "z"
    decoded = Base58Decoder.Decode(multibase[1:])

    # multicodec prefix for Ed25519 public key is varint(0xed) = 0xed 0x01
    assert decoded[:2] == b"\xed\x01"
    # remaining bytes are exactly the raw public key
    assert decoded[2:] == pub
    assert len(decoded) == 34


def test_zero_clears_mnemonic_material() -> None:
    """zero() must actually destroy the secret, not just the derivation root."""
    seed = ConductorSeed.generate()
    seed.zero()

    # The 24-word master secret must no longer be retrievable.
    assert seed.mnemonic_words() == []


def test_zero_prevents_operations() -> None:
    seed = ConductorSeed.generate()
    seed.zero()
    with pytest.raises(RuntimeError, match="zeroed"):
        seed.sign("m/0'", b"test")
    with pytest.raises(RuntimeError, match="zeroed"):
        seed.derive("m/0'")
    with pytest.raises(RuntimeError, match="zeroed"):
        seed.public_key("m/0'")


def test_derive_named_unknown() -> None:
    seed = ConductorSeed.generate()
    with pytest.raises(ValueError, match="Unknown path name"):
        seed.derive_named("nonexistent")


def test_all_named_paths_derive() -> None:
    seed = ConductorSeed.generate()
    for name in PATHS:
        key = seed.derive_named(name)
        assert len(key.public_key) == 32
        assert key.curve == "ed25519"
