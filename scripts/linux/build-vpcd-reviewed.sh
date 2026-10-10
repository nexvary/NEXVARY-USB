#!/usr/bin/env bash
# Build an external GPL-3.0-or-later dependency in a new local directory.
# No driver installation, service stop, or system configuration mutation.
set -euo pipefail
build_dir="${1:-nexvary-vpcd-dependency}"
if [[ -e "$build_dir" ]]; then
  echo "Destination already exists; choose a new directory." >&2
  exit 1
fi
mkdir -p "$build_dir"
git -C "$build_dir" init -q
git -C "$build_dir" remote add origin https://github.com/frankmorgner/vsmartcard.git
git -C "$build_dir" fetch --depth 1 origin 8a411e3672e843f9bb9fd750fc8dc56a26bb3bc8
git -C "$build_dir" checkout --detach -q FETCH_HEAD
src="$build_dir/virtualsmartcard/src"
gcc -shared -fPIC -O2 -DVPCDSLOTS=2 -DVPCDPORT=35963   -DHAVE_DECL_MSG_NOSIGNAL=1 -DHAVE_ARPA_INET_H=1   $(pkg-config --cflags libpcsclite) -I "$src/vpcd"   "$src/ifd-vpcd/ifd-vpcd.c" "$src/vpcd/vpcd.c" "$src/vpcd/lock.c"   -o "$build_dir/libifdvpcd-nexvary-reviewed.so"
echo "Built external vpcd driver; source and GPL notices retained in $build_dir."
echo "Use its absolute .so path as LIBPATH in the isolated reader configuration."
