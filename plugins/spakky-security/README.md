# Spakky Security

[Spakky Framework](https://github.com/E5presso/spakky-framework)를 위한 보안 유틸리티 플러그인입니다.

## 설치

```bash
pip install spakky-security
```

Spakky extras로도 설치할 수 있습니다.

```bash
pip install spakky[security]
```

## 주요 기능

- **패스워드 해싱**: Argon2, bcrypt, scrypt, PBKDF2
- **대칭키 암호화**: AES-CBC, AES-GCM
- **비대칭키 암호화**: RSA
- **JWT 토큰**: JWT token 생성, 서명, 검증, 파싱
- **HMAC 서명**: 안전한 메시지 인증
- **Key 생성**: 암호학적으로 안전한 random key

## 사용법

### 패스워드 해싱

```python
from spakky.plugins.security.password.argon2 import Argon2PasswordEncoder
from spakky.plugins.security.password.bcrypt import BcryptPasswordEncoder
from spakky.plugins.security.password.scrypt import ScryptPasswordEncoder
from spakky.plugins.security.password.pbkdf2 import Pbkdf2PasswordEncoder

# Argon2(권장)
encoder = Argon2PasswordEncoder(password="my_password")
hashed = encoder.encode()  # Returns formatted hash string

# password 검증
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

### 대칭키 암호화 (AES)

```python
from spakky.plugins.security.cryptography.aes import Aes
from spakky.plugins.security.cryptography.gcm import Gcm
from spakky.plugins.security.key import Key

# 256-bit key 생성
key = Key(size=32)

# AES-CBC
aes = Aes(key)
encrypted = aes.encrypt("Hello, World!")
decrypted = aes.decrypt(encrypted)  # "Hello, World!"

# AES-GCM(authenticated encryption)
gcm = Gcm(key)
encrypted = gcm.encrypt("Hello, World!")
decrypted = gcm.decrypt(encrypted)  # "Hello, World!"
```

### 비대칭키 암호화 (RSA)

```python
from spakky.plugins.security.cryptography.rsa import Rsa, AsymmetricKey

# RSA key pair 생성(1024, 2048, 4096, 8192 bits 지원)
asymmetric_key = AsymmetricKey(size=2048)
rsa = Rsa(key=asymmetric_key)

# public key로 암호화
encrypted = rsa.encrypt("Secret message")

# private key로 복호화
decrypted = rsa.decrypt(encrypted)  # "Secret message"

# key 내보내기
public_key = asymmetric_key.public_key
private_key = asymmetric_key.private_key  # Returns Key or None

# PEM에서 가져오기(passphrase 선택)
imported_key = AsymmetricKey(key=private_key_pem, passphrase="선택")
rsa_imported = Rsa(key=imported_key)
```

### JWT 토큰

```python
from spakky.plugins.security.jwt import JWT
from spakky.plugins.security.hmac_signer import HMACType
from spakky.plugins.security.key import Key
from datetime import timedelta

# JWT 생성
jwt = JWT()
jwt.set_payload(user_id=123, role="admin")
jwt.set_expiration(timedelta(hours=1))

# token 서명(기본값: HS256)
key = Key(size=32)
jwt.sign(key)
token_string = jwt.export()

# 다른 hash algorithm 사용
jwt.set_hash_type(HMACType.HS512)
jwt.sign(key)

# token 파싱 및 검증
parsed_jwt = JWT(token=token_string)
is_valid = parsed_jwt.verify(key)

# claim 접근
user_id = parsed_jwt.payload.get("user_id")
is_expired = parsed_jwt.is_expired
```

### HMAC 서명

```python
from spakky.plugins.security.hmac_signer import HMAC, HMACType
from spakky.plugins.security.key import Key

key = Key(size=32)

# message 서명(static method)
signature = HMAC.sign_text(key, HMACType.HS256, "message to sign")

# URL-safe signature
signature_safe = HMAC.sign_text(key, HMACType.HS256, "message", url_safe=True)

# signature 검증(static method)
is_valid = HMAC.verify(key, HMACType.HS256, "message to sign", signature)
```

### Key 생성

```python
from spakky.plugins.security.key import Key

# random key 생성
key = Key(size=32)  # 256-bit key

# key data 접근
raw_bytes = key.binary
base64_encoded = key.b64
url_safe_base64 = key.b64_urlsafe
hex_encoded = key.hex

# 기존 data에서 key 생성
key_from_bytes = Key(binary=existing_bytes)
key_from_base64 = Key(base64=encoded_string)
```

## 구성 요소

| 컴포넌트 | 설명 |
|-----------|-------------|
| `Argon2PasswordEncoder` | Argon2 password hashing(권장) |
| `BcryptPasswordEncoder` | bcrypt password hashing |
| `ScryptPasswordEncoder` | scrypt password hashing |
| `Pbkdf2PasswordEncoder` | PBKDF2 password hashing |
| `Aes` | AES-CBC encryption/decryption |
| `Gcm` | AES-GCM authenticated encryption |
| `Rsa` | RSA asymmetric encryption |
| `JWT` | JSON Web Token 생성 및 검증 |
| `HMAC` | HMAC message signing 및 verification |
| `Key` | 안전한 key 생성 및 관리 |

## 보안 권장 사항

1. **패스워드에는 Argon2 사용**: Password Hashing Competition 우승 알고리즘입니다
2. **암호화에는 AES-GCM 사용**: confidentiality와 integrity를 모두 제공합니다
3. **안전한 key 생성**: 암호학적 key에는 항상 `Key(size=N)`을 사용하세요
4. **JWT expiration 설정**: token에는 항상 expiration time을 설정하세요
5. **key 안전 저장**: 환경변수나 secret manager를 사용하세요

## 라이선스

MIT
