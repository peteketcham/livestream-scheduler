#!/usr/bin/env bash
# Installs an untracked pre-commit hook that runs the fast quality gates.
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
hook="$(git rev-parse --git-path hooks)/pre-commit"
cat > "$hook" <<HOOK
#!/usr/bin/env bash
exec "$root/scripts/check.sh" --fast
HOOK
chmod +x "$hook"
echo "installed $hook"
