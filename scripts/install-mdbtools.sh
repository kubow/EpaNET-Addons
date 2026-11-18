#!/usr/bin/env bash
# Build a project-local MDBTools fallback; no root or system installation needed.
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project_dir=$(cd -- "$script_dir/.." && pwd)
tool_dir="$project_dir/.tools"
odbc_dir="$tool_dir/unixodbc"
mdb_dir="$tool_dir/mdbtools"

if [[ -x "$mdb_dir/bin/mdb-json" ]]; then
  echo "MDBTools is already available at $mdb_dir/bin/mdb-json"
  exit 0
fi
mkdir -p "$tool_dir/src"
if [[ ! -d "$tool_dir/src/unixODBC/.git" ]]; then
  git clone --depth 1 https://github.com/lurcher/unixODBC.git "$tool_dir/src/unixODBC"
fi
if [[ ! -d "$tool_dir/src/mdbtools/.git" ]]; then
  git clone --depth 1 https://github.com/mdbtools/mdbtools.git "$tool_dir/src/mdbtools"
fi
cd "$tool_dir/src/unixODBC"
autoreconf -fi
./configure --prefix="$odbc_dir"
make -j2
make install
cd "$tool_dir/src/mdbtools"
autoreconf -fi
CPPFLAGS="-I$odbc_dir/include" LDFLAGS="-L$odbc_dir/lib" ./configure --prefix="$mdb_dir" --disable-man --with-unixodbc="$odbc_dir"
make -j2
make install
echo "MDBTools ready: $mdb_dir/bin/mdb-json"
