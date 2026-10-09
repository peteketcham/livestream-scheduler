#!/usr/bin/env bash
# livestream-scheduler installer for the owner's home Ubuntu Server (24.04 LTS).
# Idempotent; run with sudo. See specs/001-youtube-livestream-scheduler/contracts/deployment.md.
#
#   sudo deploy/install.sh vX.Y.Z --config-repo <git URL> [--config-ref main]
#   sudo deploy/install.sh config-pull [--ref <branch|tag|sha>]
#   sudo deploy/install.sh restore <backup.tar.gz[.age]>
set -euo pipefail

UV_VERSION="${UV_VERSION:-0.12.17}"
APP_REPO="${APP_REPO:-https://github.com/peteketcham/livestream-scheduler.git}"
APP=/opt/livestream-scheduler
CONF=/etc/livestream-scheduler
CREDS=/etc/livestream-scheduler-credentials
BACKUPS=/var/backups/livestream-scheduler
SVC_USER=livestream-scheduler
UV=/usr/local/bin/uv

die() { echo "install.sh: $*" >&2; exit 1; }
info() { echo "==> $*"; }

require_root() { [[ $EUID -eq 0 ]] || die "run with sudo"; }

check_host() {
  [[ -r /etc/os-release ]] || die "cannot read /etc/os-release"
  # shellcheck disable=SC1091
  . /etc/os-release
  [[ "${ID:-}" == "ubuntu" ]] || die "Ubuntu Server is required (found ${ID:-unknown})"
  local sd
  sd="$(systemctl --version | awk 'NR==1 {print $2}')"
  if (( sd < 250 )); then
    die "systemd ${sd} is too old (need >= 250 for LoadCredential=); Ubuntu 22.04 is not supported — use 24.04 LTS"
  fi
  if [[ "$(timedatectl show -p NTPSynchronized --value 2>/dev/null || echo no)" != "yes" ]]; then
    echo "warning: system clock is not NTP-synchronized (timedatectl); scheduling and OAuth need accurate time" >&2
  fi
}

install_packages() {
  info "installing packages"
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git curl ca-certificates sqlite3 age >/dev/null
}

install_uv() {
  if [[ -x $UV ]] && [[ "$($UV --version | awk '{print $2}')" == "$UV_VERSION" ]]; then
    return
  fi
  info "installing uv ${UV_VERSION}"
  curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
}

create_user_and_dirs() {
  id -u "$SVC_USER" >/dev/null 2>&1 || {
    info "creating system user $SVC_USER"
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SVC_USER"
  }
  install -d -m 0700 -o root -g root "$CREDS"
  install -d -m 0700 -o "$SVC_USER" -g "$SVC_USER" "$BACKUPS"
}

install_app() {
  local tag="$1"
  if [[ -d $APP/.git ]]; then
    git -C "$APP" fetch --tags --quiet
  else
    info "cloning app $tag"
    git clone --quiet "$APP_REPO" "$APP"
  fi
  git -C "$APP" -c advice.detachedHead=false checkout --quiet "$tag"
  info "building environment (uv sync --frozen --no-dev)"
  (cd "$APP" && UV_PYTHON_INSTALL_DIR="$APP/.uv-python" "$UV" sync --frozen --no-dev --python 3.12 --quiet)
  chmod -R a+rX "$APP"
}

install_config() {
  local repo="$1" ref="$2"
  if [[ ! -d $CONF/.git ]]; then
    [[ -n $repo ]] || die "--config-repo is required on first install"
    info "cloning config repo"
    rm -rf "$CONF"
    git clone --quiet --branch "$ref" "$repo" "$CONF"
  fi
  chown -R root:"$SVC_USER" "$CONF"
  chmod -R u=rwX,g=rX,o= "$CONF"
}

prompt_credentials() {
  if [[ ! -s $CREDS/oauth-client.json ]]; then
    read -r -p "Path to the downloaded OAuth client JSON (Desktop app): " path
    [[ -f $path ]] || die "no such file: $path"
    install -m 0600 -o root -g root "$path" "$CREDS/oauth-client.json"
  fi
  local name prompt value
  for name in calendar-url smtp-password; do
    [[ -s $CREDS/$name ]] && continue
    if [[ $name == calendar-url ]]; then prompt="Secret iCal address of the stream calendar: "; else prompt="SMTP password: "; fi
    read -r -s -p "$prompt" value; echo
    [[ -n $value ]] || die "$name cannot be empty"
    umask 077
    printf '%s' "$value" > "$CREDS/$name"
    chmod 0600 "$CREDS/$name"
  done
}

install_units() {
  info "installing systemd units and lss"
  install -m 0644 "$APP"/deploy/systemd/livestream-scheduler.service /etc/systemd/system/
  install -m 0644 "$APP"/deploy/systemd/livestream-scheduler.timer /etc/systemd/system/
  install -m 0644 "$APP"/deploy/systemd/livestream-scheduler-backup.service /etc/systemd/system/
  install -m 0644 "$APP"/deploy/systemd/livestream-scheduler-backup.timer /etc/systemd/system/
  install -m 0755 "$APP"/deploy/lss /usr/local/bin/lss
  systemctl daemon-reload
}

next_steps() {
  cat <<EOF

Installed. Timers are NOT enabled yet. Next:
  lss config check && lss notify test
  # one-time consent, from your laptop:  ssh -L 8765:localhost:8765 <this server>
  lss connect --no-browser --port 8765        # open the printed URL on the laptop; choose Minnehaha UMC
  lss sync --dry-run && lss sync
  sudo systemctl enable --now livestream-scheduler.timer livestream-scheduler-backup.timer
EOF
}

cmd_install() {
  local tag="" repo="" ref="main"
  while (( $# )); do
    case "$1" in
      --config-repo) repo="$2"; shift 2 ;;
      --config-ref) ref="$2"; shift 2 ;;
      v*) tag="$1"; shift ;;
      *) die "unknown argument: $1" ;;
    esac
  done
  [[ -n $tag ]] || die "usage: install.sh vX.Y.Z --config-repo <URL> [--config-ref main]"
  require_root
  check_host
  install_packages
  install_uv
  create_user_and_dirs
  install_app "$tag"
  install_config "$repo" "$ref"
  prompt_credentials
  install_units
  next_steps
}

cmd_config_pull() {
  local ref=""
  while (( $# )); do
    case "$1" in
      --ref) ref="$2"; shift 2 ;;
      *) die "unknown argument: $1" ;;
    esac
  done
  require_root
  [[ -d $CONF/.git ]] || die "$CONF is not a config checkout; run the installer first"
  git -C "$CONF" fetch --quiet origin
  local target
  target="$(git -C "$CONF" rev-parse "${ref:-origin/$(git -C "$CONF" rev-parse --abbrev-ref HEAD)}")"
  local stage
  stage="$(mktemp -d /etc/livestream-scheduler.stage.XXXXXX)"
  trap 'git -C "$CONF" worktree remove --force "$stage" >/dev/null 2>&1 || rm -rf "$stage"' EXIT
  git -C "$CONF" worktree add --quiet --detach "$stage" "$target"
  chown -R root:"$SVC_USER" "$stage"
  chmod -R u=rwX,g=rX,o= "$stage"
  chmod 0755 "$stage"
  info "validating $target in staging"
  if ! /usr/local/bin/lss --config "$stage/config.yaml" config check; then
    die "new config failed validation; $CONF is unchanged ($(git -C "$CONF" rev-parse --short HEAD))"
  fi
  git -C "$CONF" -c advice.detachedHead=false checkout --quiet "$target"
  chown -R root:"$SVC_USER" "$CONF"
  chmod -R u=rwX,g=rX,o= "$CONF"
  info "config now at $(git -C "$CONF" rev-parse --short HEAD)"
}

cmd_restore() {
  local archive="${1:-}"
  [[ -f $archive ]] || die "usage: install.sh restore <backup.tar.gz[.age]>"
  require_root
  local copy=/var/lib/livestream-scheduler.restore-input
  install -m 0600 -o "$SVC_USER" -g "$SVC_USER" "$archive" "$copy"
  /usr/local/bin/lss restore "$copy" || { rm -f "$copy"; die "restore failed; nothing changed"; }
  rm -f "$copy"
  local restored=/var/lib/livestream-scheduler/restored-credentials
  if [[ -d $restored ]]; then
    for f in "$restored"/*; do
      local name; name="$(basename "$f")"
      [[ $name == oauth-client ]] && name=oauth-client.json
      install -m 0600 -o root -g root "$f" "$CREDS/$name"
    done
    rm -rf "$restored"
    info "credentials restored into $CREDS"
  fi
}

case "${1:-}" in
  config-pull) shift; cmd_config_pull "$@" ;;
  restore) shift; cmd_restore "$@" ;;
  ""|-h|--help) sed -n '2,8p' "$0" ;;
  *) cmd_install "$@" ;;
esac
