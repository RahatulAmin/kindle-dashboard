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
KINDLE_EXTENSION = "/mnt/us/extensions/rahat-dashboard"
ACTION_SCRIPTS = {
    "Test NAS Connection": "test-connection.sh",
    "Test Native Image Display": "test-display.sh",
    "Rehearse Power Button Recovery": "test-recovery.sh",
    "Start Dashboard": "start.sh",
    "Stop / Restore Kindle": "stop.sh",
}
FILES = {
    "config.xml", "menu.json", "config.sh.example", "test-connection.sh",
    "test-display.sh", "test-recovery.sh", "start.sh", "stop.sh", "client.sh", "fullscreen.sh", "session.sh", "README.md",
}


def test_kual_metadata_and_zip():
    config = ElementTree.parse(EXT / "config.xml")
    assert config.getroot().tag == "extension"
    assert config.findtext("information/id") == "rahat-dashboard"
    menu = config.find("menus/menu")
    assert menu.text == "menu.json" and menu.attrib["type"] == "json"
    items = json.loads((EXT / menu.text).read_text())["items"][0]["items"]
    assert len(items) == len(ACTION_SCRIPTS)
    assert {item["name"]: item["action"] for item in items} == {
        label: f"/bin/sh {KINDLE_EXTENSION}/{script}"
        for label, script in ACTION_SCRIPTS.items()
    }
    for script in ACTION_SCRIPTS.values():
        assert (EXT / script).is_file()

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
    shutil.copytree(EXT, ext, ignore=shutil.ignore_patterns("state", "config.sh", "extensions"))
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


def claims(state):
    return list((state / "sessions").glob("*"))


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
    assert not claims(extension / "state")
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
    assert not claims(extension / "state")
    assert "Action cancelled" in (extension / "state/dashboard.log").read_text()


def wait_for(check, timeout=8):
    from time import monotonic, sleep

    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if check():
            return
        sleep(0.03)
    raise AssertionError("timed out waiting for native supervisor")


@pytest.fixture
def fullscreen(extension, monkeypatch, tmp_path):
    setsid = shutil.which("setsid", path=os.defpath)
    if not setsid:
        pytest.skip("setsid is unavailable")
    tools = tmp_path / "tools"
    (tools / "setsid").unlink()
    (tools / "setsid").symlink_to(setsid)
    state = extension / "state"
    framework = tmp_path / "framework"
    framework.write_text("start/running")
    calls = tmp_path / "framework-calls"
    home = tmp_path / "home-calls"
    draws = tmp_path / "draws"
    fail_draw = tmp_path / "fail-draw"
    events = tmp_path / "handoff-events"
    power = tmp_path / "power"
    power.write_text("active")
    slow_draw = tmp_path / "slow-draw"
    for var, path in {
        "FRAMEWORK": framework,
        "FRAMEWORK_CALLS": calls,
        "HOME_CALLS": home,
        "DRAWS": draws,
        "FAIL_DRAW": fail_draw,
        "EVENTS": events,
        "POWER": power,
        "SLOW_DRAW": slow_draw,
        "FRAME": state / "last-good.png",
    }.items():
        monkeypatch.setenv(var, str(path))

    (tools / "initctl").write_text(
        """#!/bin/sh
case "$*" in
    'status framework') printf 'framework '; cat "$FRAMEWORK"; printf '\n' ;;
    'stop --no-wait framework')
        [ -s "$FRAME" ] || exit 10
        echo stop >> "$FRAMEWORK_CALLS"
        printf stop/waiting > "$FRAMEWORK" ;;
    'start --no-wait framework')
        echo start >> "$FRAMEWORK_CALLS"
        echo start >> "$EVENTS"
        printf start/running > "$FRAMEWORK" ;;
    *) exit 11 ;;
esac
"""
    )
    (tools / "lipc-set-prop").write_text(
        """#!/bin/sh
[ "$*" = 'com.lab126.appmgrd start app://com.lab126.booklet.home' ] || exit 12
echo home >> "$HOME_CALLS"
echo home >> "$EVENTS"
"""
    )
    (tools / "lipc-get-prop").write_text(
        """#!/bin/sh
case "$*" in
    'com.lab126.powerd state') cat "$POWER" ;;
    'com.lab126.appmgrd activeApp')
        if [ -f "$HOME_CALLS" ] && [ "$(wc -l < "$HOME_CALLS")" -ge 2 ]; then
            echo com.lab126.booklet.home
        else
            echo com.lab126.booklet.reader
        fi ;;
    *) exit 16 ;;
esac
"""
    )
    (tools / "lipc-get-prop").chmod(0o755)
    (tools / "eips").write_text(
        """#!/bin/sh
[ "$(cat "$FRAMEWORK")" = stop/waiting ] || { echo draw-while-running >> "$EVENTS"; exit 13; }
if [ "$*" = -c ]; then
    echo clear >> "$EVENTS"
    exit 0
fi
[ ! -f "$FAIL_DRAW" ] || exit 14
echo draw >> "$EVENTS"
case "$*" in
    '-f -g '*) echo full >> "$DRAWS" ;;
    '-g '*) echo partial >> "$DRAWS" ;;
    *) exit 15 ;;
esac
if [ -f "$SLOW_DRAW" ]; then
    exec /bin/sleep 30
fi
"""
    )
    (tools / "sleep").write_text(
        '#!/bin/sh\nexec /bin/sleep .025\n'
    )
    (tools / "sleep").chmod(0o755)
    sysfs = tmp_path / "input-sysfs"
    dev = tmp_path / "input-dev"
    (sysfs / "event0/device").mkdir(parents=True)
    (sysfs / "event0/device/name").write_text("gpio-keys")
    dev.mkdir()
    fifo = dev / "event0"
    os.mkfifo(fifo)
    clock = tmp_path / "uptime"
    clock.write_text("1000.00 0.00\n")
    module = extension / "fullscreen.sh"
    module.write_text(module.read_text().replace(
        "INPUT_SYSFS=/sys/class/input", f"INPUT_SYSFS='{sysfs}'",
    ).replace("INPUT_DEV=/dev/input", f"INPUT_DEV='{dev}'").replace(
        "< /proc/uptime", f"< '{clock}'",
    ))

    def log():
        target = state / "dashboard.log"
        return target.read_text() if target.exists() else ""

    def config(url, limit=120):
        configure(extension, url)
        with (extension / "config.sh").open("a") as config_file:
            config_file.write(
                f"FULLSCREEN_ENABLED=yes\nREFRESH_SECONDS=30\nFULL_REFRESH_EVERY=2\nSESSION_LIMIT_SECONDS={limit}\n"
            )

    def press():
        # 32-bit evdev layout: 8 timestamp bytes, then type/code/value.
        os.write(fd, bytes.fromhex("00000000000000000100740001000000"))

    def rehearse():
        run(extension, "test-recovery.sh")
        wait_for(lambda: "Recovery rehearsal armed" in log())
        press()
        wait_for(lambda: (state / "recovery-verified").is_file() and not claims(state))

    fd = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)
    try:
        yield {
            "ext": extension, "state": state, "framework": framework, "calls": calls,
            "home": home, "draws": draws, "fail_draw": fail_draw, "press": press, "clock": clock,
            "rehearse": rehearse, "config": config, "log": log,
            "events": events, "power": power, "slow_draw": slow_draw,
        }
    finally:
        if claims(state):
            run(extension, "stop.sh")
            wait_for(lambda: not claims(state))
        os.close(fd)


def test_fullscreen_gate_and_initial_download(fullscreen):
    test = fullscreen
    png = render_png(Settings(_env_file=None))
    with server(png, status=404) as url:
        test["config"](url)
        run(test["ext"], "start.sh")
        wait_for(lambda: "Run Rehearse Power Button Recovery" in test["log"]())
        assert not test["calls"].exists()
        wait_for(lambda: not claims(test["state"]))

        test["rehearse"]()
        assert not test["calls"].exists()
        run(test["ext"], "start.sh")
        wait_for(lambda: "HTTP 404" in test["log"]())
        wait_for(lambda: not claims(test["state"]))
        assert not test["calls"].exists()
        assert test["framework"].read_text() == "start/running"


def test_fullscreen_refresh_offline_and_power_recovery(fullscreen):
    test = fullscreen
    test["rehearse"]()
    png = render_png(Settings(_env_file=None))
    with server(png) as url:
        test["config"](url)
        run(test["ext"], "start.sh")
        wait_for(lambda: test["draws"].exists() and len(test["draws"].read_text().splitlines()) >= 3)
        assert test["draws"].read_text().splitlines()[:3] == ["full", "partial", "full"]
        assert test["framework"].read_text() == "stop/waiting"
    wait_for(lambda: "Keeping the last verified image" in test["log"]())
    assert (test["state"] / "last-good.png").read_bytes() == png
    test["press"]()
    wait_for(lambda: not claims(test["state"]))
    assert test["calls"].read_text().splitlines() == ["stop", "start"]
    assert test["home"].read_text().splitlines() == ["home", "home"]
    assert "KEY_POWER press observed in supervise" in test["log"]()
    assert "KEY_POWER recovery marker published" in test["log"]()
    assert "Physical power press requested" in test["log"]()
    assert "Framework confirmed stop/waiting" in test["log"]()
    assert "Home repaint request exit=0" in test["log"]()
    assert "terminating: physical power press" in test["log"]()


@pytest.mark.parametrize("reason", ["worker error", "stop action", "time limit"])
def test_fullscreen_always_restores(fullscreen, reason):
    test = fullscreen
    test["rehearse"]()
    with server(render_png(Settings(_env_file=None))) as url:
        test["config"](url)
        run(test["ext"], "start.sh")
        wait_for(lambda: test["draws"].exists())
        if reason == "worker error":
            test["fail_draw"].touch()
        elif reason == "stop action":
            run(test["ext"], "stop.sh")
        elif reason == "time limit":
            # The power monitor stays blocked in a read, so no touch or key
            # notification can drive recovery.
            test["clock"].write_text("1120.00 0.00\n")
        wait_for(lambda: not claims(test["state"]))
    assert test["framework"].read_text() == "start/running"
    assert test["calls"].read_text().splitlines() == ["stop", "start"]
    if reason == "worker error":
        assert "Display worker exited" in test["log"]()
    elif reason == "time limit":
        assert "Session time limit reached" in test["log"]()


def test_fullscreen_restores_without_user_storage(fullscreen, tmp_path):
    test = fullscreen
    test["rehearse"]()
    with server(render_png(Settings(_env_file=None))) as url:
        test["config"](url)
        run(test["ext"], "start.sh")
        wait_for(lambda: test["draws"].exists())
        test["state"].rename(tmp_path / "disconnected-user-storage")
        wait_for(lambda: test["home"].exists() and test["home"].read_text().count("home") == 2)
    assert test["framework"].read_text() == "start/running"
    assert test["calls"].read_text().splitlines() == ["stop", "start"]


def test_lock_cleanup_checks_boot_and_process_start(extension):
    import uuid

    state = extension / "state"
    old = state / "active"
    old.mkdir(parents=True)
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    ticks = int(Path("/proc/self/stat").read_text().rsplit(") ", 1)[1].split()[19])
    prefix = f"{boot}.{os.getpid()}."
    live = state / "sessions" / f"{prefix}{ticks}"
    reused = state / "sessions" / f"{prefix}{ticks + 1}"
    prior_boot = state / "sessions" / f"{uuid.uuid4()}.{os.getpid()}.{ticks}"
    orphan_worker = state / "sessions" / f"{prefix}{ticks + 2}"
    for marker in (live, reused, prior_boot, orphan_worker):
        marker.mkdir(parents=True, exist_ok=True)
    (orphan_worker / "worker-owner").write_text(live.name)
    run(extension, "stop.sh")
    assert not old.exists()
    assert live.exists() and (live / "cancel").exists()
    assert orphan_worker.exists()
    assert not reused.exists() and not prior_boot.exists()
    log = (state / "dashboard.log").read_text()
    assert "Cleared stale session" in log
    assert "Removed empty legacy" in log


def test_unknown_stale_files_are_preserved(extension):
    state = extension / "state"
    claim = state / "sessions/00000000-0000-0000-0000-000000000000.99.0"
    claim.mkdir(parents=True)
    unknown = claim / "unexpected"
    unknown.write_text("preserve me")
    run(extension, "stop.sh")
    assert unknown.read_text() == "preserve me"
    assert "Preserved unexpected files" in (state / "dashboard.log").read_text()


def test_failed_detach_never_claims_a_session(fullscreen, tmp_path):
    test = fullscreen
    setsid = tmp_path / "tools/setsid"
    setsid.unlink()
    setsid.write_text("#!/bin/sh\nexit 88\n")
    setsid.chmod(0o755)
    with server(render_png(Settings(_env_file=None))) as url:
        test["config"](url)
        run(test["ext"], "start.sh", expected=1)
        assert not claims(test["state"])
        assert not list(test["state"].glob("launch.*"))
        assert "no active claim was acquired" in test["log"]()
        run(test["ext"], "test-connection.sh")
    assert not test["calls"].exists()


@pytest.mark.parametrize("limit", [0, 60, 121])
def test_restricted_trial_rejects_other_session_limits(fullscreen, limit):
    test = fullscreen
    test["config"]("http://127.0.0.1:1", limit=limit)
    run(test["ext"], "start.sh", expected=1)
    assert "Invalid full-screen settings" in test["log"]()
    assert not claims(test["state"])
    assert not test["calls"].exists()


def test_late_detached_child_leaves_no_claim(fullscreen, tmp_path):
    import shlex

    test = fullscreen
    setsid = tmp_path / "tools/setsid"
    real = setsid.resolve()
    attempted = tmp_path / "late-launch-attempted"
    setsid.unlink()
    setsid.write_text(
        "#!/bin/sh\n/bin/sleep .5\n"
        f"{shlex.quote(str(real))} \"$@\"\n"
        f"touch {shlex.quote(str(attempted))}\n"
    )
    setsid.chmod(0o755)
    with server(render_png(Settings(_env_file=None))) as url:
        test["config"](url)
        run(test["ext"], "start.sh", expected=1)
        wait_for(attempted.exists)
        assert not claims(test["state"])
        assert not list(test["state"].glob("launch.*"))
        run(test["ext"], "test-connection.sh")
    assert not test["calls"].exists()


def test_signal_restores_framework_and_reports_home_request_failure(fullscreen, tmp_path):
    import signal

    test = fullscreen
    (tmp_path / "tools/lipc-set-prop").write_text("#!/bin/sh\nexit 5\n")
    test["rehearse"]()
    with server(render_png(Settings(_env_file=None))) as url:
        test["config"](url)
        run(test["ext"], "start.sh")
        wait_for(lambda: test["draws"].exists())
        claim, = claims(test["state"])
        pid = int(claim.name.split(".")[1])
        os.kill(pid, signal.SIGTERM)
        wait_for(lambda: not claims(test["state"]))
    assert test["framework"].read_text() == "start/running"
    assert test["calls"].read_text().splitlines() == ["stop", "start"]
    assert "terminating: signal TERM" in test["log"]()
    assert test["log"]().count("Home repaint request exit=5") == 4


def test_monitor_exit_triggers_recovery(fullscreen):
    import re
    import signal

    test = fullscreen
    test["rehearse"]()
    with server(render_png(Settings(_env_file=None))) as url:
        test["config"](url)
        run(test["ext"], "start.sh")
        wait_for(lambda: test["draws"].exists())
        match = re.search(r"Power monitor started \(pid=(\d+), mode=supervise\)", test["log"]())
        assert match
        os.kill(int(match[1]), signal.SIGTERM)
        wait_for(lambda: not claims(test["state"]))
    assert test["calls"].read_text().splitlines() == ["stop", "start"]
    assert "terminating: power monitor exited" in test["log"]()


def test_recovery_stops_inflight_draw_and_clears_only_before_framework_start(fullscreen):
    test = fullscreen
    test["rehearse"]()
    test["slow_draw"].touch()
    with server(render_png(Settings(_env_file=None))) as url:
        test["config"](url)
        run(test["ext"], "start.sh")
        wait_for(lambda: test["draws"].exists())
        test["press"]()
        wait_for(lambda: not claims(test["state"]))

    assert test["events"].read_text().splitlines() == ["draw", "clear", "start", "home", "home"]
    log = test["log"]()
    assert log.index("is quiescent") < log.index("Clearing dashboard frame") < log.index("Framework start request")
    assert "App-manager reports Home active. Visible Home unverified." in log


def test_recovery_reuses_running_framework_and_waits_for_wake(fullscreen):
    test = fullscreen
    test["rehearse"]()
    with server(render_png(Settings(_env_file=None))) as url:
        test["config"](url)
        run(test["ext"], "start.sh")
        wait_for(lambda: test["draws"].exists())
        test["power"].write_text("screenSaver")
        test["framework"].write_text("start/running")
        test["press"]()
        wait_for(lambda: "Home navigation deferred while asleep" in test["log"]())
        assert not test["home"].exists()
        test["power"].write_text("active")
        wait_for(lambda: not claims(test["state"]))

    assert test["calls"].read_text().splitlines() == ["stop"]
    assert test["events"].read_text().splitlines() == ["draw", "home", "home"]
    assert "Visible Home unverified." in test["log"]()
