"""Create local Docker credentials once without overwriting existing values."""
from pathlib import Path
import secrets


def write_env_file(path):
    content = (
        'POSTGRES_DB=finsight\n'
        'POSTGRES_USER=finsight\n'
        f'POSTGRES_PASSWORD={secrets.token_hex(32)}\n'
        f'SECRET_KEY={secrets.token_hex(32)}\n'
        f'JWT_SECRET_KEY={secrets.token_hex(32)}\n'
        'API_PORT=5000\n'
        'CORS_ORIGINS=\n'
    )
    try:
        with path.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(content)
    except FileExistsError:
        return False
    return True


if __name__ == '__main__':
    path = Path(__file__).resolve().parents[1] / '.env.docker'
    created = write_env_file(path)
    print('Created .env.docker with random local credentials.' if created else 'Kept existing .env.docker unchanged.')
