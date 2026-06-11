"""
Token Manager with Fernet encryption.
Handles encryption/decryption of OAuth tokens at rest.
"""

from cryptography.fernet import Fernet, InvalidToken

from core.logging import get_logger
from config import settings

logger = get_logger("TokenManager")


class TokenManager:
    """
    Manages encryption/decryption of OAuth tokens.

    Uses Fernet (symmetric encryption) from cryptography library.
    Key is stored in environment variable OAUTH_ENCRYPTION_KEY.

    Key generation (one-time setup):
        from cryptography.fernet import Fernet
        print(Fernet.generate_key().decode())
    """

    def __init__(self, encryption_key: str | None = None):
        """
        Initialize TokenManager.

        Args:
            encryption_key: Base64-encoded Fernet key (defaults to settings)
        """
        key = encryption_key or getattr(settings, "oauth_encryption_key", None)

        if not key:
            logger.warning(
                "oauth_encryption_key_not_set",
                message="Tokens will be stored UNENCRYPTED",
            )
            self._cipher = None
        else:
            try:
                self._cipher = Fernet(key.encode() if isinstance(key, str) else key)
                logger.info("token_encryption_enabled")
            except Exception as e:
                logger.error("fernet_init_failed", error=str(e))
                raise ValueError(f"Invalid encryption key: {e}")

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a token.

        Args:
            plaintext: Token to encrypt

        Returns:
            Base64-encoded encrypted token (or plaintext if encryption disabled)
        """
        if not self._cipher:
            logger.warning(
                "encryption_skipped", reason="No encryption key configured"
            )
            return plaintext

        try:
            encrypted = self._cipher.encrypt(plaintext.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error("encryption_failed", error=str(e))
            raise ValueError(f"Encryption failed: {e}")

    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt a token.

        Args:
            ciphertext: Encrypted token

        Returns:
            Decrypted token

        Raises:
            ValueError: If decryption fails (invalid key or corrupted data)
        """
        if not self._cipher:
            logger.warning(
                "decryption_skipped", reason="No encryption key configured"
            )
            return ciphertext

        try:
            decrypted = self._cipher.decrypt(ciphertext.encode())
            return decrypted.decode()
        except InvalidToken:
            logger.error("decryption_failed", reason="Invalid token or key")
            raise ValueError(
                "Failed to decrypt token - invalid key or corrupted data"
            )
        except Exception as e:
            logger.error("decryption_failed", error=str(e))
            raise ValueError(f"Decryption failed: {e}")

    @property
    def is_enabled(self) -> bool:
        """Check if encryption is enabled."""
        return self._cipher is not None
