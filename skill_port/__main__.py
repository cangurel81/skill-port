"""Allow ``python -m skill_port``."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
