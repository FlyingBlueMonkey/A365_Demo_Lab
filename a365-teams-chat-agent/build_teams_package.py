import argparse
import json
import struct
import zlib
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile


def icon_png(size: int, outline: bool) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    rows = bytearray()
    for row in range(size):
        rows.append(0)
        for column in range(size):
            horizontal, vertical = column * 32 // size, row * 32 // size
            bubble = 5 <= horizontal <= 26 and 6 <= vertical <= 22
            tail = 8 <= horizontal <= 12 and 22 <= vertical <= 26
            interior = 7 <= horizontal <= 24 and 8 <= vertical <= 20
            line = 10 <= horizontal <= 21 and vertical in {12, 16}
            mark = (bubble or tail) and (not interior or line)
            pixel = (255, 255, 255, 255) if mark else ((0, 0, 0, 0) if outline else (8, 127, 140, 255))
            rows.extend(pixel)
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def build_package(bot_id: str, app_id: str, website: str, privacy_url: str, terms_url: str, output: Path) -> None:
    values = {
        "TEAMS_BOT_CLIENT_ID": str(UUID(bot_id)),
        "TEAMS_APP_ID": str(UUID(app_id)),
        "WEBSITE_URL": website,
        "PRIVACY_URL": privacy_url,
        "TERMS_URL": terms_url,
    }
    for address in (website, privacy_url, terms_url):
        parsed = urlsplit(address)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Developer, privacy, and terms URLs must be public HTTPS URLs without credentials")
    template = json.loads(Path(__file__).with_name("teams").joinpath("manifest.json").read_text(encoding="utf-8"))

    def substitute(value):
        if isinstance(value, dict):
            return {key: substitute(item) for key, item in value.items()}
        if isinstance(value, list):
            return [substitute(item) for item in value]
        if isinstance(value, str):
            for key, replacement in values.items():
                value = value.replace("{{" + key + "}}", replacement)
        return value

    manifest = substitute(template)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        archive.writestr("color.png", icon_png(192, False))
        archive.writestr("outline.png", icon_png(32, True))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the group-chat Teams app package without credentials.")
    parser.add_argument("--bot-id", required=True)
    parser.add_argument("--app-id", help="Stable Teams app GUID; defaults to the bot client ID.")
    parser.add_argument("--website", required=True)
    parser.add_argument("--privacy-url", required=True)
    parser.add_argument("--terms-url", required=True)
    parser.add_argument("--output", type=Path, default=Path("teams-app.zip"))
    args = parser.parse_args()
    build_package(args.bot_id, args.app_id or args.bot_id, args.website, args.privacy_url, args.terms_url, args.output)
    print(f"Created {args.output}")


if __name__ == "__main__":
    main()