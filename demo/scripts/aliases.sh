# Source once per shell to get the short `demo` command:  source ./demo/scripts/aliases.sh
alias demo="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/demo.sh"
echo "demo is ready. Try: demo verify, demo up, demo test"
