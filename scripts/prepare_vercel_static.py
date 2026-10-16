from pathlib import Path
import shutil


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE = PROJECT_ROOT / "app" / "static"
DESTINATION = PROJECT_ROOT / "public" / "static"


def main():
    if DESTINATION.exists():
        shutil.rmtree(DESTINATION)
    shutil.copytree(SOURCE, DESTINATION)
    print(f"Prepared Vercel static assets in {DESTINATION.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()