# 보안

Spakky의 보안 관련 표면은 provider-neutral 인증/인가 계약과 provider 플러그인으로 나뉩니다. 이 가이드는 암호화, 해시, HMAC, 패스워드 해싱처럼 애플리케이션 코드에서 직접 사용할 수 있는 `spakky-cryptography` 유틸리티를 다룹니다.

JWT bearer 검증은 애플리케이션 유틸리티가 아니라 `spakky-oidc` provider와 `spakky-auth` port를 통해 처리합니다.

---

## Hash

다양한 알고리즘으로 데이터를 해싱합니다.

```python
from spakky.plugins.cryptography.hash import Hash, HashType

h = Hash("Hello World!", hash_type=HashType.SHA256)
print(h.hex)
print(h.b64)
print(h.b64_urlsafe)

with open("document.pdf", "rb") as f:
    file_hash = Hash(f, hash_type=HashType.SHA512)
    print(file_hash.hex)
```

**지원 알고리즘:** `MD5`, `SHA1`, `SHA224`, `SHA256`, `SHA384`, `SHA512`

---

## HMAC 서명

```python
from spakky.plugins.cryptography.hmac_signer import HMAC, HMACType
from spakky.plugins.cryptography.key import Key

key = Key(size=32)
signature = HMAC.sign_text(key, HMACType.HS256, "중요한 데이터")
assert HMAC.verify(key, HMACType.HS256, "중요한 데이터", signature)
```

---

## 암호화

### AES

```python
from spakky.plugins.cryptography.cryptography.aes import Aes
from spakky.plugins.cryptography.key import Key

cipher = Aes(key=Key(size=32))
encrypted = cipher.encrypt("비밀 메시지")
decrypted = cipher.decrypt(encrypted)
assert decrypted == "비밀 메시지"
```

### AES-GCM (인증된 암호화)

```python
from spakky.plugins.cryptography.cryptography.gcm import Gcm
from spakky.plugins.cryptography.key import Key

cipher = Gcm(key=Key(size=32))
encrypted = cipher.encrypt("비밀 메시지")
decrypted = cipher.decrypt(encrypted)
```

### RSA

```python
from spakky.plugins.cryptography.cryptography.rsa import AsymmetricKey, Rsa

cipher = Rsa(key=AsymmetricKey(size=2048))
encrypted = cipher.encrypt("비밀 메시지")
decrypted = cipher.decrypt(encrypted)
```

---

## 패스워드 해싱

### Argon2 (권장)

```python
from spakky.plugins.cryptography.password.argon2 import Argon2PasswordEncoder

encoder = Argon2PasswordEncoder(password="my-password")
hashed = encoder.encode()

encoder = Argon2PasswordEncoder(password_hash=hashed)
assert encoder.challenge("my-password")
assert not encoder.challenge("wrong-password")
```

### bcrypt

```python
from spakky.plugins.cryptography.password.bcrypt import BcryptPasswordEncoder

encoder = BcryptPasswordEncoder(password="my-password")
hashed = encoder.encode()

encoder = BcryptPasswordEncoder(password_hash=hashed)
assert encoder.challenge("my-password")
```

### PBKDF2

```python
from spakky.plugins.cryptography.password.pbkdf2 import Pbkdf2PasswordEncoder

encoder = Pbkdf2PasswordEncoder(password="my-password")
hashed = encoder.encode()

encoder = Pbkdf2PasswordEncoder(password_hash=hashed)
assert encoder.challenge("my-password")
```

### scrypt

```python
from spakky.plugins.cryptography.password.scrypt import ScryptPasswordEncoder

encoder = ScryptPasswordEncoder(password="my-password")
hashed = encoder.encode()

encoder = ScryptPasswordEncoder(password_hash=hashed)
assert encoder.challenge("my-password")
```
