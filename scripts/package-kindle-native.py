"""Build a reproducible ZIP with only the files needed on Kindle USB storage."""

from pathlib import Path
from stat import S_IFREG
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

NATIVE = Path(__file__).resolve().parents[1] / "kindle-native"
EXTENSION = "rahat-dashboard"
FILES = (
    "config.xml", "menu.json", "config.sh.example", "test-connection.sh",
    "test-display.sh", "test-recovery.sh", "start.sh", "stop.sh", "client.sh", "fullscreen.sh", "README.md",
)


def package() -> Path:
    destination = NATIVE / f"{EXTENSION}.zip"
    payload = {name: (NATIVE / EXTENSION / name).read_bytes() for name in FILES}
    for name, data in payload.items():
        if b"\r" in data or not data.endswith(b"\n"):
            raise ValueError(f"{name}: expected LF line endings")
    staging = destination.with_suffix(".zip.part")
    with ZipFile(staging, "w", compression=ZIP_DEFLATED) as archive:
        for name, data in payload.items():
            info = ZipInfo(f"extensions/{EXTENSION}/{name}")
            info.create_system = 3
            mode = 0o755 if name.endswith(".sh") else 0o644
            info.external_attr = (S_IFREG | mode) << 16
            archive.writestr(info, data, compress_type=ZIP_DEFLATED)
    staging.replace(destination)
    return destination


if __name__ == "__main__":
    print(package())
