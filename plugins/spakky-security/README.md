# Spakky Security

Security utilities plugin for [Spakky Framework](https://github.com/E5presso/spakky-framework).

## Installation

```bash
pip install spakky-security
```

Or install via Spakky extras:

```bash
pip install spakky[security]
```

## Features

- **Password Hashing**: Argon2, bcrypt, scrypt, PBKDF2
- **Symmetric Encryption**: AES-CBC, AES-GCM
- **Asymmetric Encryption**: RSA
- **JWT Tokens**: Create, sign, verify, and parse JWT tokens
- **HMAC Signing**: Secure message authentication
- **Key Generation**: Cryptographically secure random keys

## Usage

### Password Hashing

```python
from spakky_security.password.argon2 import Argon2PasswordEncoder
from spakky_security.password.bcrypt import BcryptPasswordEncoder
from spakky_security.password.scrypt import ScryptPasswordEncoder
from spakky_security.password.pbkdf2 import Pbkdf2PasswordEncoder

# Argon2 (recommended)
encoder = Argon2PasswordEncoder(password="my_password")
hashed = encoder.encode()  # Returns formatted hash string

# Verify password
encoder_verify = Argon2PasswordEncoder(password_hash=hashed)
is_valid = encoder_verify.verify("my_password")

# bcrypt
bcrypt_encoder = BcryptPasswordEncoder(password="my_password")
hashed = bcrypt_encoder.encode()

# scrypt
scrypt_encoder = ScryptPasswordEncoder(password="my_password")
hashed = scrypt_encoder.encode()

# PBKDF2
pbkdf2_encoder = Pbkdf2PasswordEncoder(password="my_password")
hashed = pbkdf2_encoder.encode()
```

### Symmetric Encryption (AES)

```python
from spakky_security.cryptography.aes import Aes
from spakky_security.cryptography.gcm import Gcm
from spakky_security.key import Key

# Generate a 256-bit key
key = Key(size=32)

# AES-CBC
aes = Aes(key)
encrypted = aes.encrypt("Hello, World!")
decrypted = aes.decrypt(encrypted)  # "Hello, World!"

# AES-GCM (authenticated encryption)
gcm = Gcm(key)
encrypted = gcm.encrypt("Hello, World!")
decrypted = gcm.decrypt(encrypted)  # "Hello, World!"
```

### Asymmetric Encryption (RSA)

```python
from spakky_security.cryptography.rsa import Rsa, AsymmetricKey

# Generate RSA key pair (supports 1024, 2048, 4096, 8192 bits)
asymmetric_key = AsymmetricKey(size=2048)
rsa = Rsa(key=asymmetric_key)

# Encrypt with public key
encrypted = rsa.encrypt("Secret message")

# Decrypt with private key
decrypted = rsa.decrypt(encrypted)  # "Secret message"

# Export keys
public_key = asymmetric_key.public_key
private_key = asymmetric_key.private_key  # Returns Key or None

# Import from PEM (passphrase optional)
imported_key = AsymmetricKey(key=private_key_pem, passphrase="optional")
rsa_imported = Rsa(key=imported_key)
```

### JWT Tokens

```python
from spakky_security.jwt import JWT
from spakky_security.hmac_signer import HMACType
from spakky_security.key import Key
from datetime import timedelta

# Create a JWT
jwt = JWT()
jwt.set_payload(user_id=123, role="admin")
jwt.set_expiration(timedelta(hours=1))

# Sign the token (default: HS256)
key = Key(size=32)
jwt.sign(key)
token_string = str(jwt)

# Use different hash algorithm
jwt.set_hash_type(HMACType.HS512)
jwt.sign(key)

# Parse and verify a token
parsed_jwt = JWT(token=token_string)
is_valid = parsed_jwt.verify(key)

# Access claims
user_id = parsed_jwt.payload.get("user_id")
is_expired = parsed_jwt.is_expired
```

### HMAC Signing

```python
from spakky_security.hmac_signer import HMAC, HMACType
from spakky_security.key import Key

key = Key(size=32)

# Sign a message (static method)
signature = HMAC.sign_text(key, HMACType.HS256, "message to sign")

# URL-safe signature
signature_safe = HMAC.sign_text(key, HMACType.HS256, "message", url_safe=True)

# Verify signature (static method)
is_valid = HMAC.verify(key, HMACType.HS256, "message to sign", signature)
```

### Key Generation

```python
from spakky_security.key import Key

# Generate random key
key = Key(size=32)  # 256-bit key

# Access key data
raw_bytes = key.binary
base64_encoded = key.b64
url_safe_base64 = key.b64_urlsafe
hex_encoded = key.hex

# Create key from existing data
key_from_bytes = Key(binary=existing_bytes)
key_from_base64 = Key(base64=encoded_string)
```

## Components

| Component | Description |
|-----------|-------------|
| `Argon2PasswordEncoder` | Argon2 password hashing (recommended) |
| `BcryptPasswordEncoder` | bcrypt password hashing |
| `ScryptPasswordEncoder` | scrypt password hashing |
| `Pbkdf2PasswordEncoder` | PBKDF2 password hashing |
| `Aes` | AES-CBC encryption/decryption |
| `Gcm` | AES-GCM authenticated encryption |
| `Rsa` | RSA asymmetric encryption |
| `JWT` | JSON Web Token creation and validation |
| `HMAC` | HMAC message signing and verification |
| `Key` | Secure key generation and management |

## Security Best Practices

1. **Use Argon2 for passwords**: It's the winner of the Password Hashing Competition
2. **Use AES-GCM for encryption**: Provides both confidentiality and integrity
3. **Generate secure keys**: Always use `Key(size=N)` for cryptographic keys
4. **Set JWT expiration**: Always set an expiration time for tokens
5. **Store keys securely**: Use environment variables or secret managers

## License

MIT
