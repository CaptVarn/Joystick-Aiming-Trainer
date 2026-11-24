"""Launch the trainer from a source checkout."""

import sys
from pathlib import Path


def main() -> int:
    source = Path(__file__).resolve().parent / "src"
    if not (source / "wraith_trainer" / "application.py").is_file():
        raise SystemExit("The trainer source is missing. Clone or download the full repository.")

    sys.path.insert(0, str(source))
    try:
        from wraith_trainer.application import main as run_trainer
    except ModuleNotFoundError as error:
        if error.name not in {"pygame", "numpy"}:
            raise
        raise SystemExit(
            f"Missing dependency: {error.name}. From the repository folder, run "
            "'python -m pip install .' with the same Python interpreter used to start main.py."
        ) from None
    return run_trainer()


if __name__ == "__main__":
    raise SystemExit(main())
