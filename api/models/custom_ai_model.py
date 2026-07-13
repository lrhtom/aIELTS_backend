"""User-supplied custom AI models (bring-your-own OpenAI-compatible endpoint).

Each row is one third-party model a user configured: a name (used both as the display
label and as the ``model`` field sent in the request body), the chat/completions base
URL, and their API key stored ENCRYPTED (never plaintext, never returned to the client
— see :mod:`api.core.crypto`). Selected globally via the ``custom:<id>`` provider
string; because the call uses the user's own key, it is not billed in AT.
"""
from django.db import models

from .user import User
from api.core.crypto import encrypt_secret, decrypt_secret, mask_secret


class CustomAIModel(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='custom_ai_models', verbose_name='用户',
    )
    # `name` doubles as the request-body `model` id (e.g. "gpt-4o-mini") and the UI label.
    name = models.CharField(max_length=120, verbose_name='模型名称')
    # OpenAI-compatible chat/completions endpoint the server POSTs to.
    base_url = models.CharField(max_length=500, verbose_name='接口链接')
    # Fernet ciphertext of the SK key — decrypted on demand right before the call.
    api_key_encrypted = models.TextField(verbose_name='加密密钥')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'custom_ai_models'
        verbose_name = '自定义AI模型'
        verbose_name_plural = '自定义AI模型'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} - {self.name}'

    # ── key helpers (plaintext never persisted / never serialized) ───────────
    def set_api_key(self, plaintext: str) -> None:
        self.api_key_encrypted = encrypt_secret(plaintext)

    def get_api_key(self) -> str:
        return decrypt_secret(self.api_key_encrypted)

    @property
    def key_masked(self) -> str:
        """Display-safe form like ``sk-****9f2a`` — safe to return to the client."""
        return mask_secret(self.get_api_key())

    @property
    def provider_id(self) -> str:
        """The provider string that selects this model globally: ``custom:<id>``."""
        return f'custom:{self.pk}'
