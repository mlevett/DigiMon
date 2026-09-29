"""Build the portable DigiMon Python application without third-party tools."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main():
    root = Path(__file__).resolve().parent
    destination = root / "dist" / "DigiMon.pyz"
    destination.parent.mkdir(exist_ok=True)
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        archive.writestr("__main__.py", "from aprs_watch.__main__ import main\nraise SystemExit(main())\n")
        for source in sorted((root / "aprs_watch").glob("*.py")):
            archive.write(source, source.relative_to(root))
    print(f"Built {destination}")


if __name__ == "__main__":
    main()
