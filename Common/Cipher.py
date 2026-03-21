from Crypto.Cipher import AES
import hashlib
from Crypto import Random
import random
import base64

class AESCipher(object):
    def __init__(self, key):
       self.bs = AES.block_size
       self.key = hashlib.sha256(key.encode()).digest()

    def encrypt(self, raw):
        raw = self._pad(raw)
        iv = Random.new().read(AES.block_size)
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return base64.b64encode(iv + cipher.encrypt(raw.encode()))

    def decrypt(self, enc):
        enc = base64.b64decode(enc)
        iv = enc[:AES.block_size]
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return self._unpad(cipher.decrypt(enc[AES.block_size:])).decode('utf-8')

    def encrypt_file(self, raw_bytes):
        raw_bytes = self._pad_bytes(raw_bytes)
        iv = Random.new().read(AES.block_size)
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return iv + cipher.encrypt(raw_bytes)

    def decrypt_file(self, enc_bytes):
        iv = enc_bytes[:AES.block_size]
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return self._unpad_bytes(cipher.decrypt(enc_bytes[AES.block_size:]))

    def _pad(self, s):
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
        self.p = p
        self.g = g
        self.private_key = None
        self.public_key = None
        self.create_keys()

    def create_keys(self):
        """
        create public and private keys with the class p and g
        """
        self.private_key = random.randint(1, (self.p - 1))
        self.public_key = pow(self.g, self.private_key, self.p)

    def create_shared_key(self, other_public_key):
        """
        Create shared key and return it
        """
        return pow(other_public_key, self.private_key, self.p)

def main():
    diffie = DiffiHelman()
    diffie.create_keys()
    shared_key = diffie.create_shared_key(106)
    print(shared_key, diffie.private_key, diffie.public_key)

if __name__ == "__main__":
    main()