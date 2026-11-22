import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest
from PIL import Image

from app.core.config import ROOT, Settings
from app.rendering.kindle import render_png

NATIVE = ROOT / "kindle-native"
EXT = NATIVE / "rahat-dashboard"
ACTIONS = {
    "Test NAS Connection": "./test-connection.sh",
    "Test Native Image Display": "./test-display.sh",
    "Start Dashboard": "./start.sh",
    "Stop / Restore Kindle": "./stop.sh",
}
FILES = {
    "config.xml", "menu.json", "config.sh.example", "test-connection.sh",
    "test-display.sh", "start.sh", "stop.sh", "client.sh", "README.md",
}


def test_kual_metadata_and_zip():
    config = ElementTree.parse(EXT / "config.xml")
    assert config.getroot().tag == "extension"
    assert config.findtext("information/id") == "rahat-dashboard"
    menu = config.find("menus/menu")
    assert menu.text == "menu.json" and menu.attrib["type"] == "json"
    items = json.loads((EXT / menu.text).read_text())["items"][0]["items"]
    assert {item["name"]: item["action"] for item in items} == ACTIONS
    for item in items:
        assert (EXT / item["action"]).is_file()

    with ZipFile(NATIVE / "rahat-dashboard.zip") as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {f"extensions/rahat-dashboard/{name}" for name in FILES}
        for info in archive.infolist():
            name = Path(info.filename).name
            data = archive.read(info)
            assert data == (EXT / name).read_bytes() and b"\r" not in data
            assert (info.external_attr >> 16) & 0o777 == (0o755 if name.endswith(".sh") else 0o644)


@pytest.mark.parametrize("shell", [("sh",), ("busybox", "ash")])
def test_posix_scripts_parse(shell):
    if not shutil.which(shell[0]):
        pytest.skip(f"{shell[0]} is unavailable")
    for path in sorted(EXT.glob("*.sh")) + [EXT / "config.sh.example"]:
        subprocess.run([*shell, "-n", str(path)], check=True)


@pytest.fixture
def extension(tmp_path, monkeypatch):
    if not shutil.which("curl"):
        pytest.skip("curl is unavailable")
    ext = tmp_path / "extension with spaces"
    shutil.copytree(EXT, ext, ignore=shutil.ignore_patterns("state", "config.sh"))
    tools = tmp_path / "tools"
    tools.mkdir()
    monkeypatch.setenv("PATH", str(tools) + ":" + os.environ["PATH"])
    (tools / "eips").write_text(
        '#!/bin/sh\n[ "$#" = 2 ] && [ "$1" = -g ] && [ -s "$2" ] || exit 42\n'
        'printf "%s\\n" "$2" >> "$EIPS_CALLS"\n'
    )
    (tools / "eips").chmod(0o755)
    monkeypatch.setenv("EIPS_CALLS", str(tmp_path / "eips-calls"))
    for name in ("initctl", "lipc-set-prop", "pkill", "setsid"):
        tool = tools / name
        tool.write_text('#!/bin/sh\ntouch "$UNSAFE_CALLS"\nexit 51\n')
        tool.chmod(0o755)
    unsafe_calls = tmp_path / "unsafe"
    monkeypatch.setenv("UNSAFE_CALLS", str(unsafe_calls))
    yield ext
    assert not unsafe_calls.exists()


@contextmanager
def server(payload, *, status=200, started=None, release=None):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.path in ("/api/kindle/image.png", "/api/kindle/dashboard.png")
            assert "Cookie" not in self.headers and "Authorization" not in self.headers
            if started:
                started.set()
                assert release.wait(6)
            self.send_response(status)
            if status == 302:
                self.send_header("Location", "/api/kindle/image.png")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as http:
        worker = Thread(target=http.serve_forever, daemon=True)
        worker.start()
        try:
            yield f"http://127.0.0.1:{http.server_port}"
        finally:
            http.shutdown()
            worker.join(timeout=3)


def configure(ext, url, path="/api/kindle/image.png"):
    (ext / "config.sh").write_text(f"SERVER_URL='{url}'\nIMAGE_PATH='{path}'\n")


def run(ext, action, expected=0):
    result = subprocess.run(["sh", str(ext / action)], timeout=24, capture_output=True, text=True)
    assert result.returncode == expected, result.stderr


def test_connection_display_and_start(extension, tmp_path):
    settings = Settings(_env_file=None)
    png = render_png(settings)
    cache = extension / "state/last-good.png"
    calls = tmp_path / "eips-calls"

    run(extension, "test-display.sh", expected=1)
    with server(png) as url:
        configure(extension, url)
        run(extension, "test-connection.sh")
    assert not calls.exists()
    assert cache.read_bytes() == png
    with Image.open(cache) as image:
        assert (image.format, image.mode, image.size) == ("PNG", "L", (758, 1024))
        image.verify()

    run(extension, "test-display.sh")
    with server(png) as url:
        configure(extension, url, "/api/kindle/dashboard.png")
        run(extension, "start.sh")
    run(extension, "stop.sh")
    assert calls.read_text().splitlines() == [str(cache), str(cache)]
    assert not (extension / "state/active").exists()
    assert "Download verified" in (extension / "state/dashboard.log").read_text()


def test_failure_preserves_valid_cache(extension, tmp_path):
    png = render_png(Settings(_env_file=None))
    cache = extension / "state/last-good.png"
    with server(png) as offline_url:
        configure(extension, offline_url)
        run(extension, "test-connection.sh")
    for payload, status in ((png, 404), (png, 302), (b"<html>error</html>", 200),
                            (png[:-12], 200), (png[:33] + png[-12:], 200)):
        with server(payload, status=status) as url:
            configure(extension, url)
            run(extension, "test-connection.sh", expected=1)
        assert cache.read_bytes() == png
    configure(extension, offline_url)
    run(extension, "start.sh", expected=1)
    assert cache.read_bytes() == png
    assert not (tmp_path / "eips-calls").exists()
    curl = tmp_path / "tools/curl"
    curl.write_text(
        '#!/bin/sh\ncase "$*" in\n  *"--connect-timeout 5 --max-time 20 "*) exit 28;;\nesac\nexit 50\n'
    )
    curl.chmod(0o755)
    run(extension, "test-connection.sh", expected=1)
    assert cache.read_bytes() == png
    log = (extension / "state/dashboard.log").read_text()
    assert all(line in log for line in ("HTTP 404", "HTTP 302", "Download rejected", "curl exit 28"))


def test_stop_cancels_in_flight_attempt(extension, tmp_path):
    png = render_png(Settings(_env_file=None))
    with server(png) as url:
        configure(extension, url)
        run(extension, "test-connection.sh")
    started, release = Event(), Event()
    with server(png, started=started, release=release) as url:
        configure(extension, url)
        with subprocess.Popen(["sh", str(extension / "start.sh")]) as process:
            try:
                assert started.wait(4)
                run(extension, "test-connection.sh", expected=1)
                run(extension, "stop.sh")
            finally:
                release.set()
            assert process.wait(timeout=5) == 1
    assert (extension / "state/last-good.png").read_bytes() == png
    assert not (tmp_path / "eips-calls").exists()
    assert not (extension / "state/active").exists()
    assert "Action cancelled" in (extension / "state/dashboard.log").read_text()
