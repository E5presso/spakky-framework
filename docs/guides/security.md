# 보안

`spakky-security`는 JWT, 암호화, 해시, 패스워드 해싱을 제공합니다.

---

## JWT (JSON Web Token)

### 토큰 생성 및 서명

```python
from spakky.plugins.security.jwt import JWT
from spakky.plugins.security.key import Key
from datetime import timedelta

# 1. JWT 생성
jwt = JWT()
jwt.set_payload(user_id="user-123", role="admin")
jwt.set_expiration(timedelta(hours=1))

# 2. 서명
key = Key(size=32)  # 32-bytes(256-bit) 키 생성
jwt.sign(key)

# 3. 토큰 문자열
token_string = jwt.export()
print(token_string)  # eyJhbGciOiJIUzI1NiI...
```

### 토큰 파싱

```python
# 기존 토큰 문자열에서 복원
jwt = JWT(token="eyJhbGciOiJIUzI1NiI...")
print(jwt.payload["user_id"])  # user-123
print(jwt.payload["role"])     # admin

# 만료 확인
if jwt.is_expired:
    print("토큰이 만료되었습니다")
```

### 토큰 갱신

```python
jwt.refresh(timedelta(hours=1))  # 만료 시간 연장
assert not jwt.is_expired
```

### 해시 알고리즘 변경

```python
from spakky.plugins.security.hmac_signer import HMACType

jwt.set_hash_type(HMACType.HS512)  # HS256 → HS512
```

---

## Hash

다양한 알고리즘으로 데이터를 해싱합니다.

```python
from spakky.plugins.security.hash import Hash, HashType

# 문자열 해싱
h = Hash("Hello World!", hash_type=HashType.SHA256)
print(h.hex)           # 7F83B1657FF1FC53B92DC18148A1D6...
print(h.b64)           # f4OxZX/x/FO5LcGBSKHWXfwtSx+j1n...
print(h.b64_urlsafe)   # f4OxZX_x_FO5LcGBSKHWXfwtSx-j1n...

# 파일 해싱
with open("document.pdf", "rb") as f:
    file_hash = Hash(f, hash_type=HashType.SHA512)
    print(file_hash.hex)
```

**지원 알고리즘:** `MD5`, `SHA1`, `SHA224`, `SHA256`, `SHA384`, `SHA512`

---

## HMAC 서명

```python
from spakky.plugins.security.hmac_signer import HMAC, HMACType
from spakky.plugins.security.key import Key

key = Key(size=32)
signature = HMAC.sign_text(key, HMACType.HS256, "중요한 데이터")
assert HMAC.verify(key, HMACType.HS256, "중요한 데이터", signature)
```

---

## 암호화

### AES

```python
from spakky.plugins.security.cryptography.aes import Aes
from spakky.plugins.security.key import Key

cipher = Aes(key=Key(size=32))
encrypted = cipher.encrypt("비밀 메시지")
decrypted = cipher.decrypt(encrypted)
assert decrypted == "비밀 메시지"
```

### AES-GCM (인증된 암호화)

```python
from spakky.plugins.security.cryptography.gcm import Gcm
from spakky.plugins.security.key import Key

cipher = Gcm(key=Key(size=32))
encrypted = cipher.encrypt("비밀 메시지")
decrypted = cipher.decrypt(encrypted)
```

### RSA

```python
from spakky.plugins.security.cryptography.rsa import AsymmetricKey, Rsa

cipher = Rsa(key=AsymmetricKey(size=2048))
encrypted = cipher.encrypt("비밀 메시지")
decrypted = cipher.decrypt(encrypted)
```

---

## 패스워드 해싱

### Argon2 (권장)

```python
from spakky.plugins.security.password.argon2 import Argon2PasswordEncoder

# 해싱
encoder = Argon2PasswordEncoder(password="my-password")
hashed = encoder.encode()

# 검증
encoder = Argon2PasswordEncoder(password_hash=hashed)
assert encoder.challenge("my-password")
assert not encoder.challenge("wrong-password")
```

### bcrypt

```python
from spakky.plugins.security.password.bcrypt import BcryptPasswordEncoder

encoder = BcryptPasswordEncoder(password="my-password")
hashed = encoder.encode()

encoder = BcryptPasswordEncoder(password_hash=hashed)
assert encoder.challenge("my-password")
```

### PBKDF2

```python
from spakky.plugins.security.password.pbkdf2 import Pbkdf2PasswordEncoder

encoder = Pbkdf2PasswordEncoder(password="my-password")
hashed = encoder.encode()

encoder = Pbkdf2PasswordEncoder(password_hash=hashed)
assert encoder.challenge("my-password")
```

### scrypt

```python
from spakky.plugins.security.password.scrypt import ScryptPasswordEncoder

encoder = ScryptPasswordEncoder(password="my-password")
hashed = encoder.encode()

encoder = ScryptPasswordEncoder(password_hash=hashed)
assert encoder.challenge("my-password")
```
