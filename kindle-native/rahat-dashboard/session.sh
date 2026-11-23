#!/bin/sh
# Each claim has its own directory. Concurrent callers can both decline, but
# neither can remove or acquire the other caller's live claim.

SESSIONS="$STATE/sessions"
BOOT_ID=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null) || return 1
case "$BOOT_ID" in ''|*[!a-f0-9-]*) return 1 ;; esac

process_ticks() {
    stat_line=$(cat "/proc/$1/stat" 2>/dev/null) || return 1
    # The executable name in field 2 can contain spaces and parentheses.
    set -- ${stat_line##*) }
    case "$1" in Z|X) return 1 ;; esac
    [ "$#" -ge 20 ] || return 1
    printf '%s\n' "${20}"
}

identity_live() {
    ident=${1##*/}
    case "$ident" in *.*.*) ;; *) return 2 ;; esac
    boot=${ident%%.*}
    pair=${ident#*.}
    pid=${pair%%.*}
    ticks=${pair#*.}
    case "$boot" in ''|*[!a-f0-9-]*) return 2 ;; esac
    case "$pid" in ''|0|*[!0-9]*) return 2 ;; esac
    case "$ticks" in ''|*[!0-9]*) return 2 ;; esac
    [ "$boot" = "$BOOT_ID" ] || return 1
    if current=$(process_ticks "$pid"); then
        [ "$current" = "$ticks" ]
    elif kill -0 "$pid" 2>/dev/null; then
        # An unreadable live process is ambiguous. A readable zombie is dead.
        stat_line=$(cat "/proc/$pid/stat" 2>/dev/null) || return 2
        case "${stat_line##*) }" in Z\ *|X\ *) return 1 ;; *) return 2 ;; esac
    else
        [ ! -d "/proc/$pid" ] && return 1
        return 2
    fi
}

remove_claim() {
    rm -f "$1/frame.part" "$1/cancel" "$1/monitor-ready" "$1/input-event" \
        "$1/power-pressed" "$1/proof" "$1/worker-allowed" "$1/worker-owner"
    rmdir "$1" 2>/dev/null
}

claim_state() {
    identity_live "$1"
    result=$?
    [ "$result" -eq 1 ] || return "$result"
    if [ -f "$1/worker-owner" ]; then
        worker_owner=$(cat "$1/worker-owner" 2>/dev/null) || return 2
        identity_live "$worker_owner"
        return $?
    fi
    return 1
}

legacy_cleanup() {
    legacy="$STATE/active"
    [ -d "$legacy" ] || return 0
    # Legacy locks had no owner record. Check for an older client before
    # removing an empty directory. Preserve anything with unknown contents.
    for entry in /proc/[0-9]*/cmdline; do
        [ "$entry" = "/proc/$$/cmdline" ] && continue
        args=$(tr '\000' '\n' 2>/dev/null < "$entry") || continue
        if printf '%s\n' "$args" | grep -Fx "$BASE/client.sh" >/dev/null ||
            { printf '%s\n' "$args" | grep -Fx './client.sh' >/dev/null &&
                [ "$(readlink "${entry%/cmdline}/cwd" 2>/dev/null)" = "$BASE" ]; }; then
            log "A client may still own the legacy state/active directory."
            return 1
        fi
    done
    if rmdir "$legacy" 2>/dev/null; then
        log "Removed empty legacy state/active directory."
    else
        log "Preserved nonempty legacy state/active directory; restart and inspect it before retrying."
        return 1
    fi
}

scan_claims() {
    busy=no
    for claim in "$SESSIONS"/*; do
        [ -d "$claim" ] || continue
        [ "$claim" = "${JOB:-}" ] && continue
        claim_state "$claim"
        result=$?
        case "$result" in
            0)
                busy=yes
                if [ "$1" = stop ] && { : > "$claim/cancel"; } 2>/dev/null; then
                    log "Stop requested for ${claim##*/}."
                fi
                ;;
            1)
                if remove_claim "$claim"; then
                    log "Cleared stale session ${claim##*/}."
                elif [ -d "$claim" ]; then
                    log "Preserved unexpected files in stale session ${claim##*/}."
                    busy=yes
                fi
                ;;
            *)
                log "Session identity uncertain; preserving ${claim##*/}."
                busy=yes
                ;;
        esac
    done
    [ "$busy" = yes ]
}

acquire_claim() {
    legacy_cleanup || return 1
    own_ticks=$(process_ticks "$$") || return 1
    JOB="$SESSIONS/$BOOT_ID.$$.$own_ticks"
    PART="$JOB/frame.part"
    mkdir -p "$SESSIONS" && mkdir "$JOB" || return 1
    trap cleanup 0
    trap 'exit 1' HUP INT TERM
    if scan_claims start; then
        log "Action skipped: another session holds a live or uncertain claim."
        return 1
    fi
}

cleanup() {
    if [ -d "$JOB" ] && ! remove_claim "$JOB"; then
        log "Session cleanup could not remove ${JOB##*/}; preserving unexpected files."
    fi
}
