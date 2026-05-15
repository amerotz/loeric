#!/usr/bin/env bash

HEADER=$(cat <<'EOF'
# This file is part of LOERIC.
#
# LOERIC is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# LOERIC is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with LOERIC. If not, see <https://www.gnu.org/licenses/>.
EOF
)

find . -name "*.py" -type f | while read -r file; do
  if grep -q "GNU General Public License" "$file"; then
    echo "Skipping (already has header): $file"
    continue
  fi

  tmp=$(mktemp)

  echo "$HEADER" > "$tmp"
  echo "" >> "$tmp"
  cat "$file" >> "$tmp"

  mv "$tmp" "$file"

  echo "Updated: $file"
done
