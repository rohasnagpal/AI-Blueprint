import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import run_migrations


def main() -> None:
    run_migrations()
    print("Migrations applied successfully.")


if __name__ == "__main__":
    main()
