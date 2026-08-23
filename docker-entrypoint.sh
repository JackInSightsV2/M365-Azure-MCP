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
    # Run inside a private D-Bus session. Start the login daemon (which unlocks the
    # login keyring with KEYRING_PASSWORD, empty by default), publish its address to
    # the bus so the Secret Service is activatable, then register the secrets
    # component. Only after this does azure-identity encrypt the token cache; every
    # step is best effort, so on failure the server still runs with a plaintext cache.
    # The password pipes are consumed only by the daemons; the server keeps stdin.
    exec dbus-run-session -- sh -c '
        eval "$(printf "%s\n" "${KEYRING_PASSWORD:-}" | gnome-keyring-daemon --daemonize --login 2>/dev/null)" || true
        export GNOME_KEYRING_CONTROL SSH_AUTH_SOCK
        dbus-update-activation-environment --all >/dev/null 2>&1 || true
        printf "%s\n" "${KEYRING_PASSWORD:-}" | gnome-keyring-daemon --start --components=secrets >/dev/null 2>&1 \
            || echo "keyring: could not start; using plaintext token cache" >&2
        exec "$@"
    ' sh "$@"
fi

exec "$@"
