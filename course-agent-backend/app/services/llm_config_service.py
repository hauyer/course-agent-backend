from contextvars import ContextVar, Token
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.llm_config import LlmConfig
from app.models.user import User
from app.services.integration_config_service import decrypt_secret, encrypt_secret
from app.utils.security import verify_password


_active_llm_runtime: ContextVar[dict | None] = ContextVar(
    "active_llm_runtime",
    default=None,
)


class LlmConfigurationInvalidError(RuntimeError):
    """The saved user key cannot be decrypted with the current local secret."""


def _invalid_config_message() -> str:
    return "已保存的大模型密钥无法解密，请在设置中验证密码并重新接入 API"


def verify_current_password(*, user: User, current_password: str) -> None:
    if not verify_password(current_password, user.password_hash):
        raise ValueError("当前密码不正确")


def _normalize_base_url(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("API 地址必须是有效的 http 或 https 地址")
    if parsed.username or parsed.password:
        raise ValueError("API 地址中不能包含用户名或密码")
    return normalized


def get_llm_config(db: Session, *, user_id: int) -> LlmConfig | None:
    return db.query(LlmConfig).filter(LlmConfig.user_id == user_id).first()


def save_llm_config(
    db: Session,
    *,
    user: User,
    current_password: str,
    provider: str,
    model_name: str,
    base_url: str | None,
    api_key: str,
) -> LlmConfig:
    verify_current_password(user=user, current_password=current_password)
    normalized_model = model_name.strip()
    normalized_key = api_key.strip()
    if not normalized_model:
        raise ValueError("模型名称不能为空")
    if not normalized_key:
        raise ValueError("API 密钥不能为空")

    config = get_llm_config(db, user_id=user.id)
    if config is None:
        config = LlmConfig(user_id=user.id)
        db.add(config)

    config.provider = provider
    config.model_name = normalized_model
    config.base_url = _normalize_base_url(base_url)
    config.api_key_encrypted = encrypt_secret(normalized_key)
    config.enabled = True
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(config)
    return config


def disable_llm_config(
    db: Session,
    *,
    user: User,
    current_password: str,
) -> None:
    verify_current_password(user=user, current_password=current_password)
    config = get_llm_config(db, user_id=user.id)
    if config is not None:
        config.enabled = False
        db.commit()


def serialize_llm_config(config: LlmConfig | None) -> dict:
    if config is None:
        return {
            "configured": False,
            "enabled": False,
            "invalid": False,
            "error_message": None,
            "provider": None,
            "model_name": None,
            "base_url": None,
            "api_key_hint": None,
        }
    try:
        key = decrypt_secret(config.api_key_encrypted)
    except RuntimeError:
        return {
            "configured": False,
            "enabled": False,
            "invalid": True,
            "error_message": _invalid_config_message(),
            "provider": config.provider,
            "model_name": config.model_name,
            "base_url": config.base_url,
            "api_key_hint": None,
        }
    return {
        "configured": True,
        "enabled": bool(config.enabled),
        "invalid": False,
        "error_message": None,
        "provider": config.provider,
        "model_name": config.model_name,
        "base_url": config.base_url,
        "api_key_hint": f"••••{key[-4:]}" if key else None,
    }


def load_user_llm_runtime(user_id: int) -> dict | None:
    db = SessionLocal()
    try:
        config = get_llm_config(db, user_id=user_id)
        if config is None or not config.enabled:
            return None
        try:
            api_key = decrypt_secret(config.api_key_encrypted)
        except RuntimeError as exc:
            raise LlmConfigurationInvalidError(_invalid_config_message()) from exc
        return {
            "provider": config.provider,
            "model_name": config.model_name,
            "base_url": config.base_url,
            "api_key": api_key,
        }
    finally:
        db.close()


def set_active_llm_runtime(runtime: dict | None) -> Token:
    return _active_llm_runtime.set(runtime)


def reset_active_llm_runtime(token: Token) -> None:
    _active_llm_runtime.reset(token)


def get_active_llm_runtime() -> dict | None:
    return _active_llm_runtime.get()
