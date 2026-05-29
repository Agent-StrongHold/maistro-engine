"""Conductor identity — BIP39/BIP32 HD root of trust (ADR-021).

One 24-word mnemonic backs everything: agent signing, audit log,
DID identity, and future crypto wallet keys. Domain separation
via standard derivation paths.
"""

from __future__ import annotations

from dataclasses import dataclass

from bip_utils import (
    Base58Encoder,
    Bip32Slip10Ed25519,
    Bip39MnemonicGenerator,
    Bip39SeedGenerator,
)
from nacl.signing import SigningKey, VerifyKey

# Multicodec prefix for an Ed25519 public key: varint(0xed) = 0xed 0x01.
# Used by the did:key / multiformats spec; the leading multibase character
# 'z' on the encoded value denotes base58btc.
_ED25519_MULTICODEC_PREFIX = b"\xed\x01"

_PATHS = {
    "signing": "m/0'",
    "bitcoin_cold": "m/44'/0'/0'",
    "bitcoin_hot": "m/44'/0'/1'",
    "evm_cold": "m/44'/60'/0'",
    "evm_hot": "m/44'/60'/1'",
    "solana_cold": "m/44'/501'/0'",
    "identity": "m/44'/9000'/0'",
}


@dataclass(frozen=True)
class DerivedKey:
    path: str
    public_key: bytes
    curve: str = "ed25519"


class ConductorSeed:
    def __init__(self, mnemonic: str) -> None:
        # Hold the mnemonic in a mutable buffer so zero() can overwrite the
        # secret bytes in place rather than merely dropping a reference.
        self._mnemonic: bytearray | None = bytearray(mnemonic.encode("utf-8"))
        self._root: Bip32Slip10Ed25519 | None = Bip32Slip10Ed25519.FromSeed(
            Bip39SeedGenerator(mnemonic).Generate()
        )

    @staticmethod
    def generate() -> ConductorSeed:
        mnemonic = str(Bip39MnemonicGenerator().FromWordsNumber(24))
        return ConductorSeed(mnemonic)

    @staticmethod
    def from_mnemonic(words: list[str] | str) -> ConductorSeed:
        mnemonic = " ".join(words) if isinstance(words, list) else words
        Bip39SeedGenerator(mnemonic).Generate()
        return ConductorSeed(mnemonic)

    def derive(self, path: str) -> DerivedKey:
        node = self._require_root().DerivePath(path)
        pub = node.PublicKey().RawCompressed().ToBytes()
        return DerivedKey(path=path, public_key=pub[1:])

    def derive_named(self, name: str) -> DerivedKey:
        path = _PATHS.get(name)
        if path is None:
            raise ValueError(f"Unknown path name: {name}")
        return self.derive(path)

    def sign(self, path: str, message: bytes) -> bytes:
        priv = self._require_root().DerivePath(path).PrivateKey().Raw().ToBytes()
        return SigningKey(priv).sign(message).signature

    def verify(self, path: str, message: bytes, signature: bytes) -> bool:
        pub = self.public_key(path)
        try:
            VerifyKey(pub).verify(message, signature)
            return True
        except Exception:
            return False

    def public_key(self, path: str) -> bytes:
        return self.derive(path).public_key

    def did_key(self, path: str = "m/44'/9000'/0'") -> str:
        pub = self.public_key(path)
        prefixed = _ED25519_MULTICODEC_PREFIX + pub
        # Multibase base58btc: the 'z' prefix denotes the base58btc alphabet.
        encoded = Base58Encoder.Encode(prefixed)
        return f"did:key:z{encoded}"

    def mnemonic_words(self) -> list[str]:
        if self._mnemonic is None:
            return []
        return self._mnemonic.decode("utf-8").split()

    def zero(self) -> None:
        if self._mnemonic is not None:
            # Overwrite the secret bytes in place before dropping the buffer.
            for i in range(len(self._mnemonic)):
                self._mnemonic[i] = 0
            self._mnemonic = None
        self._root = None

    def _require_root(self) -> Bip32Slip10Ed25519:
        if self._root is None:
            raise RuntimeError("Seed has been zeroed")
        return self._root


PATHS = _PATHS
