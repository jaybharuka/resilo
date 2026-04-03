"""
Field-level encryption for sensitive data at rest.

Uses Fernet (symmetric encryption) from cryptography library.
Encryption key must be provided via ENCRYPTION_KEY environment variable.
"""

import os
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
import logging
from sqlalchemy import String, TypeDecorator

log = logging.getLogger("encryption")


def get_encryption_key() -> bytes:
    """
    Get the encryption key from environment variable.
    
    Key should be a valid Fernet key (base64-encoded 32 bytes).
    Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    
    Raises:
        RuntimeError: If ENCRYPTION_KEY is not set or invalid
    """
    key_str = os.getenv("ENCRYPTION_KEY")
    
    if not key_str:
        raise RuntimeError(
            "ENCRYPTION_KEY environment variable is required for field-level encryption. "
            "Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    
    try:
        # Validate that it's a valid Fernet key
        key_bytes = key_str.encode() if isinstance(key_str, str) else key_str
        Fernet(key_bytes)
        return key_bytes
    except Exception as e:
        raise RuntimeError(f"Invalid ENCRYPTION_KEY format: {e}")


def encrypt_value(value: Optional[str]) -> Optional[str]:
    """
    Encrypt a string value using Fernet.
    
    Args:
        value: String to encrypt (None returns None)
    
    Returns:
        Encrypted value as base64 string, or None if input is None
    """
    if value is None:
        return None
    
    try:
        key = get_encryption_key()
        cipher = Fernet(key)
        encrypted = cipher.encrypt(value.encode())
        return encrypted.decode()
    except Exception as e:
        log.error(f"Encryption failed: {e}")
        raise


def decrypt_value(encrypted_value: Optional[str]) -> Optional[str]:
    """
    Decrypt a Fernet-encrypted string value.
    
    Args:
        encrypted_value: Encrypted value as base64 string (None returns None)
    
    Returns:
        Decrypted string, or None if input is None
    """
    if encrypted_value is None:
        return None
    
    try:
        key = get_encryption_key()
        cipher = Fernet(key)
        decrypted = cipher.decrypt(encrypted_value.encode())
        return decrypted.decode()
    except InvalidToken:
        log.error("Decryption failed: invalid token (wrong key or corrupted data)")
        raise
    except Exception as e:
        log.error(f"Decryption failed: {e}")
        raise


class EncryptedString(TypeDecorator):
    """
    SQLAlchemy column type that automatically encrypts/decrypts string values.
    
    Usage:
        class User(Base):
            full_name: Mapped[Optional[str]] = mapped_column(EncryptedString(255))
    
    Values are encrypted on write and decrypted on read automatically.
    """
    impl = String
    cache_ok = True
    
    def process_bind_param(self, value, dialect):
        """Encrypt value before storing in database."""
        if value is None:
            return None
        return encrypt_value(value)
    
    def process_result_value(self, value, dialect):
        """Decrypt value when reading from database."""
        if value is None:
            return None
        return decrypt_value(value)
