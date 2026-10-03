#!/usr/bin/env bash
# End-of-session notifier: plays a ping and shows a desktop notification.
#
#   tools/notify_done.sh [TITLE] [MESSAGE]
#
# WSL2: Windows toast + amplified notify sound via powershell.exe (works without interop on PATH).
# Native Linux: notify-send + paplay/aplay. Always falls back to the terminal bell.
set -u

TITLE="${1:-Decomp}"
MESSAGE="${2:-Session finished}"

PS=/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe
SRC_WAV="/mnt/c/Windows/Media/Windows Notify System Generic.wav"
PING_WAV="${XDG_CACHE_HOME:-$HOME/.cache}/notify_done/ping.wav"

# The stock sound peaks at ~32% of full scale; cache a copy normalised to ~98%
# (about +10 dB). Windows' own volume still caps the final loudness.
make_loud_ping() {
    [ -f "$PING_WAV" ] && return 0
    [ -f "$SRC_WAV" ] || return 1
    mkdir -p "$(dirname "$PING_WAV")"
    python3 - "$SRC_WAV" "$PING_WAV" <<'PY'
import array, sys, wave
src, dst = sys.argv[1:]
with wave.open(src) as w:
    params = w.getparams()
    a = array.array("h", w.readframes(w.getnframes()))
gain = 0.98 * 32767 / max(1, max(abs(x) for x in a))
a = array.array("h", (max(-32768, min(32767, int(x * gain))) for x in a))
with wave.open(dst, "wb") as w:
    w.setparams(params)
    w.writeframes(a.tobytes())
PY
}

if [ -x "$PS" ]; then
    # PowerShell single-quoted strings escape ' as ''
    t=${TITLE//\'/\'\'}
    m=${MESSAGE//\'/\'\'}
    if make_loud_ping; then
        wav=$(wslpath -w "$PING_WAV")
    else
        wav='C:\Windows\Media\Windows Notify System Generic.wav'
    fi
    "$PS" -NoProfile -NonInteractive -Command "
        (New-Object System.Media.SoundPlayer '$wav').PlaySync()
        try {
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
            [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime] | Out-Null
            \$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
            \$xml.LoadXml('<toast><visual><binding template=\"ToastGeneric\"><text></text><text></text></binding></visual><audio silent=\"true\"/></toast>')
            \$n = \$xml.GetElementsByTagName('text')
            \$n.Item(0).AppendChild(\$xml.CreateTextNode('$t')) | Out-Null
            \$n.Item(1).AppendChild(\$xml.CreateTextNode('$m')) | Out-Null
            \$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
            [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier(\$app).Show([Windows.UI.Notifications.ToastNotification]::new(\$xml))
        } catch {
            Add-Type -AssemblyName System.Windows.Forms
            \$b = New-Object System.Windows.Forms.NotifyIcon
            \$b.Icon = [System.Drawing.SystemIcons]::Information
            \$b.Visible = \$true
            \$b.ShowBalloonTip(5000, '$t', '$m', 'Info')
            Start-Sleep -Seconds 5
            \$b.Dispose()
        }
    " >/dev/null 2>&1 && exit 0
fi

if command -v notify-send >/dev/null 2>&1 && [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
    notify-send "$TITLE" "$MESSAGE"
    for snd in /usr/share/sounds/freedesktop/stereo/complete.oga /usr/share/sounds/freedesktop/stereo/bell.oga; do
        if [ -f "$snd" ]; then
            { command -v paplay >/dev/null && paplay "$snd"; } || { command -v aplay >/dev/null && aplay -q "$snd"; }
            exit 0
        fi
    done
    exit 0
fi

printf '\a%s: %s\n' "$TITLE" "$MESSAGE"
