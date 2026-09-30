#!/usr/bin/env bash
# Build libtwinrx_engine.so against the project's UHD 3.15 (not the system UHD).
set -e
cd "$(dirname "$0")"
U=$HOME/uhd-3.15
g++ -std=c++17 -O2 -Wall -Wextra -fPIC -shared twinrx_engine.cpp \
    -I"$U/include" -L"$U/lib" -Wl,-rpath,"$U/lib" -luhd -lboost_system -lpthread \
    -o "${OUT:-libtwinrx_engine.so}"
echo "built $(pwd)/${OUT:-libtwinrx_engine.so}"
