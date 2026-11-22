#!/bin/sh

PATH="$PATH:/usr/sbin:/sbin:/usr/bin:/bin"
export PATH
umask 077

BASE=$(CDPATH= cd "$(dirname "$0")" && pwd) || exit 1
STATE="$BASE/state"
LOG="$STATE/dashboard.log"
FRAME="$STATE/last-good.png"
JOB="$STATE/active"
PART="$JOB/frame.part"

mkdir -p "$STATE" || exit 1

log() {
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S %z')" "$*" >> "$LOG"
}

cleanup() {
    rm -f "$PART" "$JOB/cancel"
    rmdir "$JOB" 2>/dev/null || :
}

cancelled() {
    if [ -f "$JOB/cancel" ]; then
        log "Action cancelled; Kindle framework left running."
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
    log "Rendering cached PNG with eips -g."
    if ! eips -g "$FRAME" >> "$LOG" 2>&1; then
        log "Display failed: eips returned an error."
        return 1
    fi
    log "eips accepted the image. Check the screen for the result."
}

case "${1:-}" in
    stop)
        if [ -d "$JOB" ] && { : > "$JOB/cancel"; } 2>/dev/null; then
            log "Stop requested. A download may take up to 20 seconds to exit."
        else
            log "No dashboard action running."
        fi
        log "Kindle framework remains running. Return Home or sleep and wake to repaint."
        exit 0
        ;;
    connection|display|start) ;;
    *) exit 2 ;;
esac

if ! mkdir "$JOB" 2>/dev/null; then
    log "Action skipped: another test is active or left an active marker."
    exit 1
fi
trap cleanup 0
trap 'exit 1' HUP INT TERM

if [ "$1" = display ]; then
    display
    exit $?
fi

SERVER_URL='http://192.0.2.10:8765'
IMAGE_PATH='/api/kindle/image.png'
if [ -f "$BASE/config.sh" ]; then
    . "$BASE/config.sh" || exit 1
fi
SERVER_URL=${SERVER_URL%/}
case "$SERVER_URL" in
    http://*) authority=${SERVER_URL#http://} ;;
    https://*) authority=${SERVER_URL#https://} ;;
    *) log "Invalid SERVER_URL: expected an HTTP or HTTPS origin."; exit 1 ;;
esac
case "$authority" in
    ''|*[!A-Za-z0-9.:-]*) log "Invalid SERVER_URL: use a hostname or IPv4 address and optional port."; exit 1 ;;
esac
case "$IMAGE_PATH" in
    /api/kindle/image.png|/api/kindle/dashboard.png) ;;
    *) log "Invalid IMAGE_PATH: use a supported Kindle PNG endpoint."; exit 1 ;;
esac

download || exit 1
if [ "$1" = start ]; then
    display
fi
