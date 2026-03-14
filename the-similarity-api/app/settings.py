from __future__ import annotations

import os


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings:
    def __init__(self) -> None:
        self.app_name = os.getenv("THE_SIMILARITY_API_NAME", "The Similarity API")
        self.app_version = os.getenv("THE_SIMILARITY_API_VERSION", "0.1.0")
        self.host = os.getenv("THE_SIMILARITY_API_HOST", "127.0.0.1")
        self.port = int(os.getenv("THE_SIMILARITY_API_PORT", "8000"))
        self.allowed_origins = split_csv(
            os.getenv("THE_SIMILARITY_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
        )


settings = Settings()
