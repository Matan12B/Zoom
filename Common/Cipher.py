from Crypto.Cipher import AES
import hashlib
from Crypto import Random
import random
import base64

class AESCipher(object):
    def __init__(self, key):
       # AES has a fixed 16-byte block size.
       self.bs = AES.block_size
       # SHA-256 converts the supplied string into a 32-byte key.
       # A 32-byte AES key means this class uses AES-256.
       # CBC provides confidentiality but not integrity/authentication;
       # a production system would normally use an authenticated mode such as GCM.
       self.key = hashlib.sha256(key.encode()).digest()

    def encrypt(self, raw):
        # CBC can only encrypt complete blocks, so apply PKCS#7-style padding.
        raw = self._pad(raw)
        # CBC requires a fresh unpredictable 16-byte initialization vector (IV)
        # for every encryption. The IV is public and is stored before the ciphertext.
        iv = Random.new().read(AES.block_size)
        # AES-256-CBC: 256-bit key, Cipher Block Chaining mode.
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        # Base64 makes encrypted text safe to pass through the string protocol.
        # Base64 is encoding, not encryption.
        return base64.b64encode(iv + cipher.encrypt(raw.encode()))

    def decrypt(self, enc):
        # Recover the raw IV + ciphertext bytes from their Base64 representation.
        enc = base64.b64decode(enc)
        iv = enc[:AES.block_size]
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return self._unpad(cipher.decrypt(enc[AES.block_size:])).decode('utf-8')

    def encrypt_file(self, raw_bytes):
        # Binary media uses the same AES-256-CBC scheme, but does not need Base64.
        raw_bytes = self._pad_bytes(raw_bytes)
        iv = Random.new().read(AES.block_size)
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return iv + cipher.encrypt(raw_bytes)

    def decrypt_file(self, enc_bytes):
        # The first AES block is the IV; all remaining bytes are ciphertext.
        iv = enc_bytes[:AES.block_size]
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return self._unpad_bytes(cipher.decrypt(enc_bytes[AES.block_size:]))

    def _pad(self, s):
        # Add N bytes whose value is N so the length becomes a multiple of 16.
        return s + (self.bs - len(s) % self.bs) * chr(self.bs - len(s) % self.bs)

    @staticmethod
    def _unpad(s):
        return s[:-ord(s[len(s)- 1 :])]

    def _pad_bytes(self, b):
        pad_len = self.bs - len(b) % self.bs
        return b + bytes([pad_len] * pad_len)

    @staticmethod
    def _unpad_bytes(b: bytes) -> bytes:
        return b[:-b[-1]]

class DiffiHelman:
    def __init__(self, p=797, g=100):
        # p is the public prime modulus and g is the public generator.
        # These small values and Python's random module are suitable for this
        # educational project, but are not secure enough for production use.
        self.p = p
        self.g = g
        # The private key stays local. The public key is sent to the peer.
        self.private_key = None
        self.public_key = None
        self.create_keys()

    def create_keys(self):
        """
        Create a private value and its public Diffie-Hellman value:
        public_key = g^private_key mod p.
        """
        self.private_key = random.randint(1, (self.p - 1))
        self.public_key = pow(self.g, self.private_key, self.p)

    def create_shared_key(self, other_public_key):
        """
        Combine the peer's public key with this side's private key.
        Both peers calculate the same result without sending it over the network.
        """
        return str(pow(other_public_key, self.private_key, self.p))

def main():
    diffie = DiffiHelman()
    diffie.create_keys()
    shared_key = diffie.create_shared_key(106)
    print(shared_key, diffie.private_key, diffie.public_key)

if __name__ == "__main__":
    main()
