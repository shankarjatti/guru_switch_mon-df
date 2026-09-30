#!/usr/bin/env bash
# guru_MON_v1: start the MON flowgraph (every channel its own LO and band)
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/run_hop.sh" --mon "$@"
