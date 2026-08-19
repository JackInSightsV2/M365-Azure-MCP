#!/bin/sh
# Bring up a Secret Service so the device-code token cache is encrypted at rest,
# then run the server. Every step is best-effort: if the keyring cannot start, the
# server still launches and azure-identity falls back to its plaintext cache, so a
# keyring problem degrades gracefully instead of breaking the container.
set -e

: "${ENABLE_KEYRING:=true}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/runtime-app}"
# Keep the keyring store on the same volume as the token cache so an encrypted
# sign-in survives container restarts. Without this the encrypted cache could not be
# decrypted next time and the user would be prompted to sign in again.
export XDG_DATA_HOME="${XDG_DATA_HOME:-/home/app/.IdentityService/xdg-data}"

mkdir -p "$XDG_RUNTIME_DIR" "$XDG_DATA_HOME/keyrings" 2>/dev/null || true
chmod 700 "$XDG_RUNTIME_DIR" 2>/dev/null || true

if [ "$ENABLE_KEYRING" = "true" ] && command -v gnome-keyring-daemon >/dev/null 2>&1; then
    # Run inside a private D-Bus session, unlock the login keyring with
    # KEYRING_PASSWORD (empty by default), then hand off to the server. The password
    # pipe is consumed only by the daemon; the server keeps the container's stdin.
    exec dbus-run-session -- sh -c '
        printf "%s" "${KEYRING_PASSWORD:-}" | \
            gnome-keyring-daemon --unlock --components=secrets >/dev/null 2>&1 || \
            echo "keyring: could not start; using plaintext token cache" >&2
        exec "$@"
    ' sh "$@"
fi

exec "$@"
