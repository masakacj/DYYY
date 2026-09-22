#!/usr/bin/env bash
set -Eeuo pipefail

USER_NAME="chatgpt-debug"
ALLOW_FROM="${CHATGPT_SSH_FROM:-192.168.233.137}"
PUBLIC_KEY='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAW68vnFh8Q/PPmC5T1SQoXXnUXdNHL5oHg2xvQsf8jy chatgpt-debug-192.168.233.127'
MARKER='chatgpt-debug-192.168.233.127'
MODE="${1:-install}"

need_root() {
  if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1; then
      exec sudo -E bash "$0" "$@"
    fi
    echo "Please run this script as root." >&2
    exit 1
  fi
}

install_pkg() {
  local pkg="$1"
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y "$pkg"
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y "$pkg"
  elif command -v yum >/dev/null 2>&1; then
    yum install -y "$pkg"
  elif command -v apk >/dev/null 2>&1; then
    apk add --no-cache "$pkg"
  else
    echo "Unsupported package manager. Please install '$pkg' manually." >&2
    exit 1
  fi
}

ensure_ssh_server() {
  if ! command -v sshd >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1; then
      install_pkg openssh-server
    elif command -v apk >/dev/null 2>&1; then
      install_pkg openssh
    else
      install_pkg openssh-server
    fi
  fi

  if command -v systemctl >/dev/null 2>&1; then
    if systemctl list-unit-files ssh.service >/dev/null 2>&1; then
      systemctl enable --now ssh
    elif systemctl list-unit-files sshd.service >/dev/null 2>&1; then
      systemctl enable --now sshd
    fi
  elif command -v rc-service >/dev/null 2>&1; then
    rc-service sshd start || true
    rc-update add sshd default || true
  fi
}

ensure_sudo() {
  if ! command -v sudo >/dev/null 2>&1; then
    install_pkg sudo
  fi
}

create_user() {
  if id "$USER_NAME" >/dev/null 2>&1; then
    return 0
  fi

  if command -v useradd >/dev/null 2>&1; then
    useradd -m -s /bin/bash "$USER_NAME"
  elif command -v adduser >/dev/null 2>&1; then
    adduser -D -s /bin/bash "$USER_NAME"
  else
    echo "Neither useradd nor adduser is available." >&2
    exit 1
  fi
}

user_home() {
  awk -F: -v user="$USER_NAME" '$1 == user { print $6; exit }' /etc/passwd
}

install_access() {
  ensure_ssh_server
  ensure_sudo
  create_user

  passwd -l "$USER_NAME" >/dev/null 2>&1 || true

  local home_dir
  home_dir="$(user_home)"
  install -d -o "$USER_NAME" -g "$USER_NAME" -m 0700 "$home_dir/.ssh"

  local auth="$home_dir/.ssh/authorized_keys"
  touch "$auth"
  chown "$USER_NAME:$USER_NAME" "$auth"
  chmod 0600 "$auth"

  local tmp
  tmp="$(mktemp)"
  grep -vF "$MARKER" "$auth" >"$tmp" || true
  printf 'from="%s",no-agent-forwarding,no-port-forwarding,no-X11-forwarding %s\n'     "$ALLOW_FROM" "$PUBLIC_KEY" >>"$tmp"
  install -o "$USER_NAME" -g "$USER_NAME" -m 0600 "$tmp" "$auth"
  rm -f "$tmp"

  install -d -m 0750 /etc/sudoers.d
  printf '%s ALL=(ALL) NOPASSWD:ALL\n' "$USER_NAME" >"/etc/sudoers.d/$USER_NAME"
  chmod 0440 "/etc/sudoers.d/$USER_NAME"

  if command -v visudo >/dev/null 2>&1; then
    visudo -cf "/etc/sudoers.d/$USER_NAME" >/dev/null
  fi

  if command -v sshd >/dev/null 2>&1; then
    sshd -t
  fi

  echo
  echo "SSH debug access installed."
  echo "User: $USER_NAME"
  echo "Allowed source: $ALLOW_FROM only"
  echo "Public key fingerprint:"
  printf '%s\n' "$PUBLIC_KEY" | ssh-keygen -lf - 2>/dev/null || true
  echo
  echo "To revoke later:"
  echo "  curl -fsSL <same-script-url> | bash -s -- remove"
}

remove_access() {
  rm -f "/etc/sudoers.d/$USER_NAME"

  if id "$USER_NAME" >/dev/null 2>&1; then
    if command -v userdel >/dev/null 2>&1; then
      userdel -r "$USER_NAME" 2>/dev/null || userdel "$USER_NAME" 2>/dev/null || true
    elif command -v deluser >/dev/null 2>&1; then
      deluser --remove-home "$USER_NAME" 2>/dev/null || deluser "$USER_NAME" 2>/dev/null || true
    fi
  fi

  echo "SSH debug access removed."
}

need_root "$@"

case "$MODE" in
  install|"")
    install_access
    ;;
  remove|uninstall|revoke)
    remove_access
    ;;
  *)
    echo "Usage: $0 [install|remove]" >&2
    exit 2
    ;;
esac
