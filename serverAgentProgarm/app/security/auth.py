# app/security/auth.py（新增）-- 哈希与校验是纯函数，可单测
import bcrypt
import secrets
from fastapi import HTTPException,Header
from app.storage.db import SessionLocal
from app.storage.models import User, AuthToken
import hashlib
from datetime import datetime, timezone
from datetime import timedelta


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))

# app/security/auth.py 追加（伪代码骨架）
def save_token(token_hash, user_id, now , expires_at):
    with SessionLocal() as session:
        session.add(AuthToken(token_hash = token_hash,created_at=now,user_id= user_id, expires_at= expires_at))
        session.commit()


def create_token(user_id: int, ttl_hours: int = 12) -> str:
    token = secrets.token_urlsafe(32)  # 高熵随机，不靠用户输入
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=ttl_hours)

    # 待实现的数据库写入动作：创建 AuthToken(token_hash=..., user_id=...,
    # created_at=now, expires_at=expires_at)，add 后 commit。
    save_token(token_hash, user_id, now, expires_at)
    return token

def get_current_user(
    authorization: str | None = Header(default=None),
) -> User:
    #   1) 解析 "Bearer <token>"，SHA256 后查 auth_tokens
    #   2) 校验未过期（now < expires_at）且未注销（revoked_at is None）
    #   3) 任一失败 -> raise 401（HTTPException）
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    token = authorization.removeprefix("Bearer ").strip()

    # 2. 对 Token 计算哈希
    token_hash = hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

    # 3. 根据哈希查 Token
    with SessionLocal() as session:
        auth_token = (
            session.query(AuthToken)
            .filter(AuthToken.token_hash == token_hash)
            .first()
        )

        if auth_token is None:
            raise HTTPException(status_code=401, detail="Token 无效")

        # 4. 检查 Token 是否注销或过期
        if auth_token.revoked_at is not None:
            raise HTTPException(status_code=401, detail="Token 已注销")

        if datetime.now(timezone.utc) >= auth_token.expires_at:
            raise HTTPException(status_code=401, detail="Token 已过期")

        # 5. 根据 user_id 找用户
        user = session.get(User, auth_token.user_id)

        if user is None:
            raise HTTPException(status_code=401, detail="用户不存在")
    return user



if __name__ == "__main__":
    password_hash = hash_password("12345")
    print(password_hash)
    print(bcrypt.gensalt())
    print(verify_password("1234", password_hash))
