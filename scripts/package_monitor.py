"""Package only the Maritime worker's code and dependencies, never local secrets."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main():
    root = Path(__file__).resolve().parent.parent
    archive = root / ".maritime" / "custom-monitor.zip"
    archive.parent.mkdir(exist_ok=True)
    with ZipFile(archive, "w", ZIP_DEFLATED) as bundle:
        for source, destination in (
            ("maritime/Dockerfile", "Dockerfile"),
            ("scripts/monitor-requirements.txt", "monitor-requirements.txt"),
            ("scripts/maritime_monitor.py", "scripts/maritime_monitor.py"),
            ("scripts/check_sources.py", "scripts/check_sources.py"),
            ("scripts/calendar_feed.py", "scripts/calendar_feed.py"),
            ("scripts/public_sources.py", "scripts/public_sources.py"),
            ("scripts/club_directory.py", "scripts/club_directory.py"),
            ("scripts/club_sites.py", "scripts/club_sites.py"),
            ("scripts/instagram_monitor.py", "scripts/instagram_monitor.py"),
            ("config/club-directory.json", "config/club-directory.json"),
            ("config/instagram-watchlist.json", "config/instagram-watchlist.json"),
            ("config/monitored-sources.json", "config/monitored-sources.json"),
        ):
            bundle.write(root / source, destination)
    print(archive.relative_to(root))


if __name__ == "__main__":
    main()
