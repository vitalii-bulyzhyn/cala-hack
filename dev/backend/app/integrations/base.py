from pydantic import SecretStr


class ProviderRequestError(RuntimeError):
    def __init__(
        self,
        *,
        provider: str,
        code: str,
        message: str,
        retryable: bool,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.code = code
        self.safe_message = message
        self.retryable = retryable
        self.status_code = status_code


class ProviderNotConfigured(RuntimeError):
    def __init__(self, provider: str) -> None:
        super().__init__(f"{provider} credentials are not configured")
        self.provider = provider


def require_secret(secret: SecretStr | None, provider: str) -> str:
    if secret is None:
        raise ProviderNotConfigured(provider)
    value = secret.get_secret_value().strip()
    if not value:
        raise ProviderNotConfigured(provider)
    return value
