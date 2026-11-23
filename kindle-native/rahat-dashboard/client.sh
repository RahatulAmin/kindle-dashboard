#!/bin/sh

PATH="$PATH:/usr/sbin:/sbin:/usr/bin:/bin"
export PATH
umask 077

BASE=$(CDPATH= cd "$(dirname "$0")" && pwd) || exit 1
STATE="$BASE/state"
LOG="$STATE/dashboard.log"
FRAME="$STATE/last-good.png"

mkdir -p "$STATE" || exit 1

log() {
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S %z')" "$*" 2>/dev/null >> "$LOG" || :
}

. "$BASE/session.sh" || exit 1

cancelled() {
    if [ -f "$JOB/cancel" ]; then
        log "Action cancelled."
        return 0
    fi
    return 1
}

validate_png() {
    # Match the PNG signature and the IHDR fields and first IDAT chunk for our Pillow output:
    # 758x1024, 8-bit grayscale, standard compression and no interlace.
    prefix=$(od -An -v -tx1 -N 41 "$1" | tr -d '[:space:]') || return 1
    case "$prefix" in
        89504e470d0a1a0a0000000d49484452000002f6000004000800000000????????????????49444154) ;;
        *) return 1 ;;
    esac
    end=$(tail -c 12 "$1" | od -An -v -tx1 | tr -d '[:space:]') || return 1
    [ "$end" = '0000000049454e44ae426082' ]
}

download() {
    if ! command -v curl >/dev/null 2>&1; then
        log "Download failed: curl is unavailable."
        return 1
    fi
    log "Fetching $SERVER_URL$IMAGE_PATH."
    if status=$(
        ulimit -f 2048 || exit 1
        exec curl -q --silent --show-error --noproxy '*' --connect-timeout 5 \
            --max-time 20 --max-filesize 2097152 --output "$PART" \
            --write-out '%{http_code}' "$SERVER_URL$IMAGE_PATH"
    ); then
        if [ "$status" != 200 ]; then
            log "Download failed: HTTP $status. Cache preserved."
            return 1
        fi
    else
        result=$?
        log "Download failed: curl exit $result, HTTP ${status:-unknown}. Cache preserved."
        return 1
    fi
    cancelled && return 1
    if ! validate_png "$PART"; then
        log "Download rejected: expected a complete 758x1024 grayscale PNG. Cache preserved."
        return 1
    fi
    cancelled && return 1
    if ! mv -f "$PART" "$FRAME"; then
        log "Could not save validated image. Cache preserved."
        return 1
    fi
    log "Download verified: HTTP 200, 758x1024 grayscale PNG saved."
}

display() {
    cancelled && return 1
    if [ ! -f "$FRAME" ] || ! validate_png "$FRAME"; then
        log "Display skipped: run Test NAS Connection to cache a valid PNG."
        return 1
    fi
    if ! command -v eips >/dev/null 2>&1; then
        log "Display failed: eips is unavailable."
        return 1
    fi
    if [ "${1:-}" = full ]; then
        set -- -f -g "$FRAME"
    else
        set -- -g "$FRAME"
    fi
    log "Rendering cached PNG ($1)."
    if ! eips "$@" >> "$LOG" 2>&1; then
        log "Display failed: eips returned an error."
        return 1
    fi
    log "eips accepted the image. Check the screen for the result."
}

load_config() {
    SERVER_URL='http://192.0.2.10:8765'
    IMAGE_PATH='/api/kindle/image.png'
    FULLSCREEN_ENABLED=no
    REFRESH_SECONDS=60
    FULL_REFRESH_EVERY=5
    SESSION_LIMIT_SECONDS=120
    if [ -f "$BASE/config.sh" ]; then
        . "$BASE/config.sh" || return 1
    fi
    SERVER_URL=${SERVER_URL%/}
    case "$SERVER_URL" in
        http://*) authority=${SERVER_URL#http://} ;;
        https://*) authority=${SERVER_URL#https://} ;;
        *) log "Invalid SERVER_URL: expected an HTTP or HTTPS origin."; return 1 ;;
    esac
    case "$authority" in
        ''|*[!A-Za-z0-9.:-]*) log "Invalid SERVER_URL: use a hostname or IPv4 address and optional port."; return 1 ;;
    esac
    case "$IMAGE_PATH" in
        /api/kindle/image.png|/api/kindle/dashboard.png) ;;
        *) log "Invalid IMAGE_PATH: use a supported Kindle PNG endpoint."; return 1 ;;
    esac
}

full_config_valid() {
    case "$FULLSCREEN_ENABLED" in yes|no) ;; *) return 1 ;; esac
    for value in "$REFRESH_SECONDS" "$FULL_REFRESH_EVERY" "$SESSION_LIMIT_SECONDS"; do
        case "$value" in ''|*[!0-9]*|0?*|?????*) return 1 ;; esac
    done
    [ "$REFRESH_SECONDS" -ge 30 ] && [ "$REFRESH_SECONDS" -le 3600 ] &&
        [ "$FULL_REFRESH_EVERY" -ge 1 ] && [ "$FULL_REFRESH_EVERY" -le 60 ] &&
        [ "$SESSION_LIMIT_SECONDS" -eq 120 ]
}

MODE=${1:-}
case "$MODE" in
    stop)
        legacy_cleanup || exit 1
        if ! scan_claims stop; then
            log "No dashboard action running."
        fi
        exit 0
        ;;
    start|connection|supervise|worker)
        load_config || exit 1
        ;;
    rehearse|rehearse-session|display) ;;
    *) exit 2 ;;
esac

case "$MODE" in
    start|supervise|worker|rehearse|rehearse-session)
        . "$BASE/fullscreen.sh" || exit 1
        ;;
esac

case "$MODE" in
    start|supervise|worker)
        if [ "$FULLSCREEN_ENABLED" != no ] && ! full_config_valid; then
            log "Invalid full-screen settings; trials require SESSION_LIMIT_SECONDS=120."
            exit 1
        fi
        ;;
esac

case "$MODE" in
    start)
        if [ "$FULLSCREEN_ENABLED" = yes ]; then
            launch_detached supervise
            exit $?
        fi
        ;;
    rehearse)
        launch_detached rehearse-session
        exit $?
        ;;
    worker)
        [ "$FULLSCREEN_ENABLED" = yes ] || exit 1
        JOB=${2:-}
        case "$JOB" in "$SESSIONS"/*) ;; *) exit 1 ;; esac
        identity_live "$JOB" || exit 1
        PART="$JOB/frame.part"
        refresh_loop
        exit $?
        ;;
esac

# A late detached child must acknowledge its live launcher before claiming a slot.
case "$MODE" in
    supervise|rehearse-session) acknowledge_launch "${2:-}" || exit 1 ;;
esac
acquire_claim || exit 1

case "$MODE" in
    supervise|rehearse-session) begin_session "$MODE" "$2" ;;
    display) display ;;
    start) download && display ;;
    connection) download ;;
esac
