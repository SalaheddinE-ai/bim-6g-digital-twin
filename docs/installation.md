# Installation (WSL2 Ubuntu)

```bash
sudo apt update && sudo apt install -y build-essential git curl llvm unzip
curl -LsSf https://astral.sh/uv/install.sh | sh && source $HOME/.local/bin/env
cd ~/projects/bim-6g-digital-twin
uv python install 3.12
uv venv --python 3.12 .venv && source .venv/bin/activate
uv pip install -r requirements.lock
cp .env.example .env
python scripts/check_env.py
python -m pytest
```

Keep the repo on the Linux filesystem (`~/projects`), not on `/mnt/c` or another Windows drive.
To regenerate the lock after editing `pyproject.toml`:
`uv pip compile pyproject.toml --extra bim --extra rt --extra dev --python-version 3.12 -o requirements.lock`
