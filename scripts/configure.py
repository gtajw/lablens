"""Create a private local configuration without overwriting an existing one."""

import os
import secrets
from pathlib import Path

target = Path(__file__).resolve().parent.parent / ".env"
if target.exists():
    raise SystemExit(".env already exists; no changes made. Keep your current database password.")
config = "\n".join(
    [
        "# Local development only. Never commit this file.",
        "POSTGRES_PASSWORD=" + secrets.token_urlsafe(32),
        "LABLENS_GATEWAY_SECRET=" + secrets.token_urlsafe(48),
        "LABLENS_ENVIRONMENT=development",
        "LABLENS_PUBLIC_ORIGIN=http://localhost:3000",
        "LABLENS_AI_API_KEY=",
        "LABLENS_AI_MODEL=",
        "",
    ]
)
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as output:
    output.write(config)
print("Created .env with random local credentials. Next: docker compose up --build -d")
