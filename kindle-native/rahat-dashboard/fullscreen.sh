#!/bin/sh
# Sourced by client.sh. This module controls only the "framework" Upstart job.

PROOF="$STATE/recovery-verified"
INPUT_SYSFS=/sys/class/input
INPUT_DEV=/dev/input

find_power_key() {
    for event in "$INPUT_SYSFS"/event*; do
        name=$(cat "$event/device/name" 2>/dev/null) || continue
        case "$name" in
            *onkey*|*gpio-keys*)
                node="$INPUT_DEV/${event##*/}"
                if [ -r "$node" ]; then
                    printf '%s\n' "$node"
                    return 0
                fi
                ;;
        esac
    done
    return 1
}

power_monitor() {
    reader=
    trap 'if [ -n "$reader" ]; then kill "$reader" 2>/dev/null || :; wait "$reader" 2>/dev/null || :; fi' 0
    trap 'exit 1' HUP INT TERM
    exec 3< "$POWER_DEVICE" || return 1
    : > "$JOB/monitor-ready" || return 1
    while :; do
        dd bs=16 count=1 <&3 > "$JOB/input-event" 2>/dev/null &
        reader=$!
        wait "$reader" || return 1
        reader=
        [ -s "$JOB/input-event" ] || return 1
        fields=$(od -An -v -tx1 -j 8 -N 8 "$JOB/input-event" | tr -d '[:space:]')
        # 32-bit little-endian input_event, EV_KEY / KEY_POWER / press.
        if [ "$fields" = 0100740001000000 ]; then
            : > "$JOB/power-pressed" || return 1
            return 0
        fi
    done
}

framework_state() {
    command initctl status framework 2>/dev/null
}

framework_running() {
    case "$(framework_state)" in
        'framework start/running'*) return 0 ;;
        *) return 1 ;;
    esac
}

framework_stopped() {
    case "$(framework_state)" in
        'framework stop/waiting'*) return 0 ;;
        *) return 1 ;;
    esac
}

restore_framework() {
    log "Restoring Kindle framework."
    # Wait for an in-progress stop to finish before requesting start. Recovery
    # does not depend on logging or the user-storage mount being available.
    remaining=60
    retry=0
    while [ "$remaining" -gt 0 ]; do
        state=$(framework_state) || state=
        case "$state" in
            'framework start/running'*) break ;;
            'framework stop/waiting'*|'')
                if [ "$retry" -le 0 ]; then
                    command initctl start --no-wait framework >/dev/null 2>&1 || :
                    retry=5
                fi
                ;;
        esac
        sleep 1
        retry=$((retry - 1))
        remaining=$((remaining - 1))
    done
    if ! framework_running; then
        log "Framework did not report running. Use the documented physical restart."
        return 1
    fi
    if command -v lipc-set-prop >/dev/null 2>&1; then
        for pause in 2 4; do
            sleep "$pause"
            command lipc-set-prop com.lab126.appmgrd start app://com.lab126.booklet.home >/dev/null 2>&1 || :
        done
    fi
    log "Framework is running. If needed, wake the Kindle to repaint Home."
}

session_cleanup() {
    trap '' HUP INT TERM
    if [ -n "$MONITOR" ]; then
        kill "$MONITOR" 2>/dev/null || :
        wait "$MONITOR" 2>/dev/null || :
    fi
    if [ -n "$WORKER" ]; then
        # The worker owns a separate session. Only its group receives signals.
        if kill -TERM "-$WORKER" 2>/dev/null; then
            sleep 2
            kill -KILL "-$WORKER" 2>/dev/null || :
        fi
        wait "$WORKER" 2>/dev/null || :
    fi
    if [ "$RESTORE" = yes ]; then
        restore_framework || :
    fi
    cleanup
}

start_monitor() {
    POWER_DEVICE=$(find_power_key) || {
        log "No readable PW2 power-key device found. Full-screen blocked."
        return 1
    }
    BOOT_ID=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null) || return 1
    [ -n "$BOOT_ID" ] || return 1
    if [ "$1" = supervise ]; then
        proof=$(cat "$PROOF" 2>/dev/null) || proof=
        if [ "$proof" != "$BOOT_ID $POWER_DEVICE" ]; then
            log "Run Rehearse Power Button Recovery on this boot before full-screen."
            return 1
        fi
    fi

    power_monitor &
    MONITOR=$!
    n=5
    while [ "$n" -gt 0 ] && kill -0 "$MONITOR" 2>/dev/null; do
        [ -f "$JOB/monitor-ready" ] && return 0
        n=$((n - 1))
        sleep 1
    done
    log "Power monitor failed to arm. Framework left running."
    return 1
}

rehearse_recovery() {
    rm -f "$PROOF"
    start_monitor rehearse || return 1
    log "Recovery rehearsal armed. Press the power button briefly within 45 seconds, then wake the Kindle."
    elapsed=0
    while [ "$elapsed" -lt 45 ]; do
        [ -f "$JOB/power-pressed" ] && break
        cancelled && return 1
        kill -0 "$MONITOR" 2>/dev/null || break
        sleep 1
        elapsed=$((elapsed + 1))
    done
    if [ -f "$JOB/power-pressed" ]; then
        printf '%s %s\n' "$BOOT_ID" "$POWER_DEVICE" > "$JOB/proof" &&
            mv -f "$JOB/proof" "$PROOF" || return 1
        log "Recovery rehearsal passed. Physical KEY_POWER press verified for this boot."
        return 0
    fi
    log "Recovery rehearsal did not detect KEY_POWER. Full-screen blocked."
    return 1
}

supervise() {
    if [ "$FULLSCREEN_ENABLED" != yes ] || ! framework_running; then
        log "Full-screen blocked: opt-in and a running Kindle framework are required."
        return 1
    fi
    for utility in eips initctl setsid curl; do
        if ! command -v "$utility" >/dev/null 2>&1; then
            log "Full-screen blocked: $utility is unavailable."
            return 1
        fi
    done

    start_monitor supervise || return 1
    download || return 1
    if cancelled || [ -f "$JOB/power-pressed" ] || ! kill -0 "$MONITOR" 2>/dev/null; then
        log "Full-screen cancelled or recovery unavailable before framework shutdown."
        return 1
    fi
    framework_running || return 1

    RESTORE=yes
    log "Requesting Kindle framework stop after validating the first frame."
    command initctl stop --no-wait framework >> "$LOG" 2>&1 || return 1
    remaining=30
    until framework_stopped; do
        cancelled && return 1
        [ -f "$JOB/power-pressed" ] && return 1
        [ "$remaining" -gt 0 ] || { log "Framework stop timed out."; return 1; }
        sleep 1
        remaining=$((remaining - 1))
    done
    if cancelled || [ -f "$JOB/power-pressed" ] || ! kill -0 "$MONITOR" 2>/dev/null; then
        return 1
    fi
    sleep 2
    : > "$JOB/worker-allowed" || return 1
    setsid /bin/sh "$BASE/client.sh" worker >> "$LOG" 2>&1 </dev/null &
    WORKER=$!
    log "Full-screen worker started. Press the power button once to restore Home."

    elapsed=0
    while :; do
        if [ ! -d "$JOB" ]; then
            log "Action storage disappeared. Restoring the framework."
            return 1
        fi
        if [ -f "$JOB/power-pressed" ]; then
            log "Physical power press requested framework restoration."
            return 0
        fi
        cancelled && return 0
        if ! kill -0 "$WORKER" 2>/dev/null; then
            log "Display worker exited. Restoring the framework."
            return 1
        fi
        if ! kill -0 "$MONITOR" 2>/dev/null; then
            log "Power monitor exited. Restoring the framework."
            return 1
        fi
        if [ "$SESSION_LIMIT_SECONDS" -gt 0 ] && [ "$elapsed" -ge "$SESSION_LIMIT_SECONDS" ]; then
            log "Session time limit reached. Restoring the framework."
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
}

rotate_log() {
    if [ "$(wc -c < "$LOG")" -ge 131072 ]; then
        mv -f "$LOG" "$LOG.1"
    fi
}

refresh_loop() {
    [ -f "$JOB/worker-allowed" ] || return 1
    display full || return 1
    count=0
    while sleep "$REFRESH_SECONDS"; do
        rotate_log
        if ! download; then
            cancelled && return 0
            log "Keeping the last verified image on screen."
        fi
        count=$((count + 1))
        if [ "$count" -ge "$FULL_REFRESH_EVERY" ]; then
            display full || return 1
            count=0
        else
            display || return 1
        fi
    done
    return 1
}

launch_detached() {
    if ! command -v setsid >/dev/null 2>&1; then
        log "Cannot detach: setsid is unavailable."
        return 1
    fi
    launch="$STATE/launch.$$"
    mkdir "$launch" || return 1
    setsid /bin/sh "$BASE/client.sh" "$1" "$launch/ready" </dev/null >/dev/null 2>&1 &
    n=5
    while [ "$n" -gt 0 ]; do
        if [ -f "$launch/ready" ]; then
            rm -f "$launch/ready"
            rmdir "$launch" 2>/dev/null || :
            return 0
        fi
        sleep 1
        n=$((n - 1))
    done
    rmdir "$launch" 2>/dev/null || :
    log "Detached client did not acknowledge launch."
    return 1
}

begin_session() {
    # Acknowledge the launch only after setsid created a session and we hold the job lock.
    : > "$2" || return 1
    MONITOR=
    WORKER=
    RESTORE=no
    trap session_cleanup 0
    if [ "$1" = rehearse-session ]; then
        rehearse_recovery
    else
        supervise
    fi
}
