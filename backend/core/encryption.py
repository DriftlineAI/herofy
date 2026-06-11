"""
Fernet symmetric encryption for sensitive fields.

Provides encryption/decryption for sensitive data like interaction bodies.
Uses the same pattern as OAuth token encryption in config.py.

Key generation:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Example:
    from core.encryption import encrypt_field, decrypt_field

    encrypted_body = encrypt_field("sensitive message")
    decrypted_body = decrypt_field(encrypted_body)
"""

from cryptography.fernet import Fernet, InvalidToken

from .logging import get_logger

logger = get_logger("Encryption")

# Module-level cipher instance (lazy initialized)
_cipher: Fernet | None = None
_initialized: bool = False


def _get_cipher() -> Fernet | None:
    """Get or initialize Fernet cipher from settings."""
    global _cipher, _initialized

    if _initialized:
        return _cipher

    # Lazy import to avoid circular dependency
    from config import settings

    _initialized = True

    if not settings.body_encryption_key:
        logger.warning(
            "body_encryption_key_not_configured",
            message="Encryption disabled - body_encryption_key not set",
        )
        return None

    try:
        _cipher = Fernet(settings.body_encryption_key.encode())
        logger.info("encryption_cipher_initialized")
        return _cipher
    except Exception as e:
        logger.error("cipher_initialization_failed", error=str(e))
        return None


def encrypt_field(plaintext: str | None) -> str:
    """
    Encrypt a string field using Fernet symmetric encryption.

    Args:
        plaintext: Plain text string to encrypt

    Returns:
        Base64-encoded ciphertext, or original text if encryption not configured

    Raises:
        Exception: If encryption is configured but fails (to prevent plaintext storage)
    """
    if not plaintext:
        return plaintext or ""

    cipher = _get_cipher()
    if not cipher:
        # Graceful degradation: return plaintext if not configured
        # This is intentional for development mode
        return plaintext

    try:
        encrypted_bytes = cipher.encrypt(plaintext.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")
    except Exception as e:
        # If encryption is configured but fails, raise to prevent plaintext storage
        logger.error("encryption_failed", error=str(e))
        raise


def decrypt_field(ciphertext: str | None) -> str:
    """
    Decrypt a Fernet-encrypted field.

    Args:
        ciphertext: Base64-encoded ciphertext

    Returns:
        Decrypted plaintext, or ciphertext if encryption not configured

    Note:
        InvalidToken exceptions return ciphertext (may be legacy plaintext).
        Other exceptions are raised to surface decryption issues.
    """
    if not ciphertext:
        return ciphertext or ""

    cipher = _get_cipher()
    if not cipher:
        # Encryption not configured - assume plaintext
        return ciphertext

    try:
        decrypted_bytes = cipher.decrypt(ciphertext.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except InvalidToken:
        # May be plaintext from before encryption was enabled
        # This is expected during migration periods
        logger.debug("decryption_invalid_token", message="Data may be unencrypted")
        return ciphertext
    except Exception as e:
        # Unexpected error - raise to surface the issue
        logger.error("decryption_failed", error=str(e))
        raise


def encrypt_dict_fields(data: dict, fields: list[str]) -> dict:
    """
    Encrypt specified fields in a dictionary.

    Args:
        data: Dictionary containing fields to encrypt
        fields: List of field names to encrypt

    Returns:
        New dictionary with encrypted fields
    """
    encrypted = data.copy()
    for field in fields:
        if field in encrypted and encrypted[field]:
            encrypted[field] = encrypt_field(str(encrypted[field]))
    return encrypted


def decrypt_dict_fields(data: dict, fields: list[str]) -> dict:
    """
    Decrypt specified fields in a dictionary.

    Args:
        data: Dictionary containing encrypted fields
        fields: List of field names to decrypt

    Returns:
        New dictionary with decrypted fields
    """
    decrypted = data.copy()
    for field in fields:
        if field in decrypted and decrypted[field]:
            decrypted[field] = decrypt_field(str(decrypted[field]))
    return decrypted


def is_encryption_enabled() -> bool:
    """Check if encryption is properly configured."""
    return _get_cipher() is not None
