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
    trap 'if [ -n "$reader" ]; then kill "$reader" 2>/dev/null || :; fi' 0
    trap 'exit 1' HUP INT TERM
    if ! { exec 3< "$POWER_DEVICE"; }; then
        log "Power monitor cannot open $POWER_DEVICE."
        return 1
    fi
    log "Power monitor opened $POWER_DEVICE in $MODE."
    : > "$JOB/monitor-ready" || return 1
    while :; do
        dd bs=16 count=1 <&3 > "$JOB/input-event" 2>/dev/null &
        reader=$!
        while kill -0 "$reader" 2>/dev/null; do
            identity_live "$JOB" || return 1
            sleep 1
        done
        if ! wait "$reader" || [ ! -s "$JOB/input-event" ]; then
            log "Power monitor read failed or input device closed."
            return 1
        fi
        reader=
        fields=$(od -An -v -tx1 -j 8 -N 8 "$JOB/input-event" | tr -d '[:space:]')
        case "$fields" in
            0100740001000000)
                log "KEY_POWER press observed in $MODE on $POWER_DEVICE."
                if ! { : > "$JOB/power-pressed"; } 2>/dev/null; then
                    log "Unable to publish KEY_POWER marker."
                    return 1
                fi
                log "KEY_POWER recovery marker published."
                return 0
                ;;
            01007400????????) log "KEY_POWER non-press event: $fields." ;;
        esac
    done
}

framework_state() {
    bounded 4 initctl status framework 2>/dev/null
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

# Bound service requests so a stuck LIPC or Upstart command cannot hold the
# restoration path indefinitely. The framework status query is also bounded.
bounded() (
    limit=$1
    shift
    "$@" &
    command_pid=$!
    while kill -0 "$command_pid" 2>/dev/null; do
        if [ "$limit" -le 0 ]; then
            kill -KILL "$command_pid" 2>/dev/null || :
            return 124
        fi
        sleep 1
        limit=$((limit - 1))
    done
    wait "$command_pid"
)

restore_framework() {
    log "Restoring Kindle framework."
    remaining=60
    restore_start=$(uptime_seconds) || restore_start=
    retry=0
    last_state=
    while [ "$remaining" -gt 0 ]; do
        restore_now=$(uptime_seconds) || restore_now=
        if [ -n "$restore_start" ] && [ -n "$restore_now" ] &&
            [ "$((restore_now - restore_start))" -ge 60 ]; then
            break
        fi
        state=$(framework_state) || state=
        if [ "$state" != "$last_state" ] || [ "$remaining" -eq 60 ]; then
            log "Framework restoration status: ${state:-unavailable}."
            last_state=$state
        fi
        case "$state" in
            'framework start/running'*) break ;;
            'framework stop/waiting'*|'')
                if [ "$retry" -le 0 ]; then
                    bounded 4 initctl start --no-wait framework >/dev/null 2>&1
                    log "Framework start request exit=$?."
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
    log "Framework reports start/running. Requesting Home repaint."
    if command -v lipc-set-prop >/dev/null 2>&1; then
        for pause in 2 4; do
            sleep "$pause"
            bounded 4 lipc-set-prop com.lab126.appmgrd start app://com.lab126.booklet.home >/dev/null 2>&1
            log "Home repaint request exit=$? (0 means accepted, not visibly confirmed)."
        done
    else
        log "Home repaint request unavailable: lipc-set-prop absent."
    fi
    log "Framework is running. If needed, wake the Kindle to repaint Home."
}

terminate_child() {
    child=$1
    group=$2
    [ -n "$child" ] || return 0
    if [ "$group" = yes ]; then
        kill -TERM "-$child" 2>/dev/null || kill -TERM "$child" 2>/dev/null || :
    else
        kill -TERM "$child" 2>/dev/null || :
    fi
    ticks=3
    while kill -0 "$child" 2>/dev/null && [ "$ticks" -gt 0 ]; do
        sleep 1
        ticks=$((ticks - 1))
    done
    if [ "$group" = yes ]; then
        kill -KILL "-$child" 2>/dev/null || :
    fi
    if kill -0 "$child" 2>/dev/null; then
        log "Child $child did not exit after TERM; issuing KILL."
        kill -KILL "$child" 2>/dev/null || :
    fi
    ticks=2
    while kill -0 "$child" 2>/dev/null && [ "$ticks" -gt 0 ]; do
        sleep 1
        ticks=$((ticks - 1))
    done
    kill -0 "$child" 2>/dev/null && return 1
    wait "$child" 2>/dev/null || :
}

session_cleanup() {
    status=$1
    trap '' HUP INT TERM
    log "Supervisor $$ terminating: $EXIT_REASON (exit=$status, restore=$RESTORE)."
    worker_ended=yes
    terminate_child "$WORKER" yes || worker_ended=no
    terminate_child "$MONITOR" no || log "Power monitor did not exit within the cleanup budget."
    if [ "$RESTORE" = yes ]; then
        restore_framework || log "Automatic framework restoration did not complete."
    fi
    if [ "$worker_ended" = yes ]; then
        log "Supervisor $$ finished recovery and is releasing its session claim."
        cleanup
    else
        log "Supervisor $$ finished recovery; retaining the claim while the worker is still live."
    fi
}

uptime_seconds() {
    read -r uptime unused < /proc/uptime || return 1
    seconds=${uptime%%.*}
    case "$seconds" in ''|*[!0-9]*) return 1 ;; esac
    printf '%s\n' "$seconds"
}

start_monitor() {
    POWER_DEVICE=$(find_power_key) || {
        log "No readable PW2 power-key device found. Full-screen blocked."
        return 1
    }
    if [ "$1" = supervise ]; then
        proof=$(cat "$PROOF" 2>/dev/null) || proof=
        if [ "$proof" != "v2 $BOOT_ID $POWER_DEVICE" ]; then
            log "Run Rehearse Power Button Recovery on this boot before full-screen."
            return 1
        fi
    fi

    power_monitor &
    MONITOR=$!
    log "Power monitor started (pid=$MONITOR, mode=$MODE)."
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
        printf 'v2 %s %s\n' "$BOOT_ID" "$POWER_DEVICE" > "$JOB/proof" &&
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

    trial_start=$(uptime_seconds) || { log "Trial clock unavailable."; return 1; }
    trial_deadline=$((trial_start + SESSION_LIMIT_SECONDS))
    RESTORE=yes
    EXIT_REASON="framework shutdown failed or was interrupted"
    log "120-second deadline armed at uptime=$trial_start (expires=$trial_deadline)."
    log "Requesting Kindle framework stop after validating the first frame."
    bounded 6 initctl stop --no-wait framework
    result=$?
    log "Framework stop request exit=$result."
    [ "$result" -eq 0 ] || return 1
    remaining=30
    until framework_stopped; do
        trial_now=$(uptime_seconds) || return 1
        if [ "$trial_now" -ge "$trial_deadline" ]; then
            EXIT_REASON="120-second trial expired during framework shutdown"
            log "Session time limit reached before the first foreground draw."
            return 1
        fi
        cancelled && return 1
        [ -f "$JOB/power-pressed" ] && return 1
        [ "$remaining" -gt 0 ] || { log "Framework stop timed out."; return 1; }
        sleep 1
        remaining=$((remaining - 1))
    done
    log "Framework confirmed stop/waiting."
    sleep 2
    trial_now=$(uptime_seconds) || return 1
    if [ "$trial_now" -ge "$trial_deadline" ]; then
        EXIT_REASON="120-second trial expired during framework shutdown"
        log "Session time limit reached before the first foreground draw."
        return 1
    fi
    if cancelled || [ -f "$JOB/power-pressed" ] || ! kill -0 "$MONITOR" 2>/dev/null; then
        return 1
    fi
    : > "$JOB/worker-allowed" || return 1
    setsid /bin/sh "$BASE/client.sh" worker "$JOB" >> "$LOG" 2>&1 </dev/null &
    WORKER=$!
    log "Full-screen worker $WORKER started. Press the power button once to restore Home."

    while :; do
        if [ ! -d "$JOB" ]; then
            EXIT_REASON="action storage disappeared"
            return 1
        fi
        if [ -f "$JOB/power-pressed" ]; then
            EXIT_REASON="physical power press"
            log "Physical power press requested framework restoration."
            return 0
        fi
        if cancelled; then
            EXIT_REASON="manual stop"
            return 0
        fi
        trial_now=$(uptime_seconds) || { EXIT_REASON="trial clock failed"; return 1; }
        if [ "$trial_now" -ge "$trial_deadline" ]; then
            EXIT_REASON="120-second trial expired"
            log "Session time limit reached at uptime=$trial_now. Restoring the framework."
            return 0
        fi
        if ! kill -0 "$WORKER" 2>/dev/null; then
            wait "$WORKER"
            log "Display worker exited (exit=$?). Restoring the framework."
            EXIT_REASON="display worker exited"
            return 1
        fi
        if ! kill -0 "$MONITOR" 2>/dev/null; then
            [ -f "$JOB/power-pressed" ] && continue
            wait "$MONITOR"
            log "Power monitor exited (exit=$?). Restoring the framework."
            EXIT_REASON="power monitor exited"
            return 1
        fi
        sleep 1
    done
}

rotate_log() {
    if [ "$(wc -c < "$LOG")" -ge 131072 ]; then
        mv -f "$LOG" "$LOG.1"
    fi
}

refresh_loop() {
    [ -f "$JOB/worker-allowed" ] || return 1
    worker_ticks=$(process_ticks "$$") || return 1
    printf '%s.%s.%s\n' "$BOOT_ID" "$$" "$worker_ticks" > "$JOB/worker-owner" || return 1
    display full || return 1
    count=0
    while :; do
        delay=$REFRESH_SECONDS
        while [ "$delay" -gt 0 ]; do
            identity_live "$JOB" || return 1
            [ ! -f "$JOB/cancel" ] || return 0
            sleep 1
            delay=$((delay - 1))
        done
        identity_live "$JOB" || return 1
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
    launcher_ticks=$(process_ticks "$$") || return 1
    launch="$STATE/launch.$BOOT_ID.$$.$launcher_ticks"
    mkdir "$launch" || return 1
    setsid /bin/sh "$BASE/client.sh" "$1" "$launch" </dev/null >/dev/null 2>&1 &
    launcher_child=$!
    n=5
    while [ "$n" -gt 0 ]; do
        if [ -f "$launch/ready" ] && { : > "$launch/go"; }; then
            log "Detached $1 acknowledged (launcher child=$launcher_child)."
            return 0
        fi
        kill -0 "$launcher_child" 2>/dev/null || break
        sleep 1
        n=$((n - 1))
    done
    rm -f "$launch/ready"
    rmdir "$launch" 2>/dev/null || :
    log "Detached client did not acknowledge launch; no active claim was acquired."
    return 1
}

acknowledge_launch() {
    handshake=$1
    case "$handshake" in "$STATE"/launch.*) ;; *) return 1 ;; esac
    identity_live "${handshake##*/launch.}" || return 1
    : > "$handshake/ready" || return 1
    remaining=6
    while [ "$remaining" -gt 0 ] && [ -d "$handshake" ]; do
        if [ -f "$handshake/go" ]; then
            rm -f "$handshake/ready" "$handshake/go"
            rmdir "$handshake" || return 1
            return 0
        fi
        sleep 1
        remaining=$((remaining - 1))
    done
    log "Detached child exited before launch confirmation."
    return 1
}

begin_session() {
    MONITOR=
    WORKER=
    RESTORE=no
    EXIT_REASON="preflight or rehearsal"
    trap 'session_cleanup "$?"' 0
    trap 'EXIT_REASON="signal HUP"; exit 129' HUP
    trap 'EXIT_REASON="signal INT"; exit 130' INT
    trap 'EXIT_REASON="signal TERM"; exit 143' TERM
    log "Supervisor $$ began $1 (${JOB##*/})."
    if [ "$1" = rehearse-session ]; then
        rehearse_recovery
    else
        supervise
    fi
}
