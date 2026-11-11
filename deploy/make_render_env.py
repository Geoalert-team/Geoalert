"""
Makes the settings file for Render from deploy/render.env.example and your
backend/.env. Run it yourself, from the Geoalert folder:

    python deploy\\make_render_env.py

It writes geoalert-render.env to your Downloads folder, outside the project so
it can't be committed, and lists the lines you still have to fill in. The file
holds passwords: delete it once Render has the settings.
"""
import argparse
import re
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FROM_ENV = ['DB_NAME', 'DB_USER', 'DB_PASSWORD', 'DB_HOST',
            'SUPABASE_S3_ENDPOINT', 'SUPABASE_S3_BUCKET', 'SUPABASE_S3_REGION',
            'SUPABASE_S3_KEY', 'SUPABASE_S3_SECRET']


def read_env(path):
    values = {}
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        m = re.match(r'\s*([A-Z0-9_]+)\s*=(.*)$', line)
        if m and m.group(2).strip():
            values[m.group(1)] = m.group(2).strip()
    return values


def main():
    parser = argparse.ArgumentParser(description='Make the settings file to paste into Render.')
    parser.add_argument('--env', type=Path, default=ROOT / 'backend' / '.env')
    parser.add_argument('--out', type=Path, default=Path.home() / 'Downloads' / 'geoalert-render.env')
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit(f'{args.out} already exists. Delete it first, or give another name with --out.')

    env = read_env(args.env)
    lines, missing = [], []
    for line in (ROOT / 'deploy' / 'render.env.example').read_text(encoding='utf-8').splitlines():
        m = re.match(r'([A-Z0-9_]+)=(.*)$', line)
        if m:
            key, value = m.groups()
            if key == 'SECRET_KEY':
                value = secrets.token_urlsafe(64)
            elif key in FROM_ENV and key in env:
                value = env[key]
            if value == '__FILL_IN__':
                missing.append(key)
            line = f'{key}={value}'
        lines.append(line)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'Written: {args.out}')
    if missing:
        print('Still to fill in:', ', '.join(missing))
    print('It holds passwords: delete it once Render has the settings.')


if __name__ == '__main__':
    main()
