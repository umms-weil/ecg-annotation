#!/bin/bash

set -euo pipefail

# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

BASE_DIR=""

USERS=(
  "sardara"
  "ghamid"
  "kwheels"
  "gangidi"
)

# Add the adjudicator here when needed.
ADJUDICATORS=(
  "pwalczyk"
)

# Preview without creating folders.
DRY_RUN=False

# Permission changes on mounted Turbo/SMB storage may not be supported from
# macOS. Leave false unless Data Ops confirms POSIX ACL/chown support.
APPLY_PERMISSIONS=false

# Optional institutional group used only when APPLY_PERMISSIONS=true.
ACCESS_GROUP=""

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

run_cmd() {
  if [ "$DRY_RUN" = true ]; then
    printf '[DRY RUN]'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

create_user_folder() {
  local record_output_dir="$1"
  local user="$2"
  local user_output_dir="${record_output_dir}/${user}"

  run_cmd mkdir -p "$user_output_dir"

  if [ "$APPLY_PERMISSIONS" = true ]; then
    if [ -n "$ACCESS_GROUP" ]; then
      run_cmd chown "${user}:${ACCESS_GROUP}" "$user_output_dir"
    else
      run_cmd chown "$user" "$user_output_dir"
    fi

    run_cmd chmod 700 "$user_output_dir"
  fi

  echo "Created/verified:"
  echo "  $user_output_dir"
}

# ---------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------

if [ ! -d "$BASE_DIR" ]; then
  echo "ERROR: BASE_DIR does not exist:"
  echo "  $BASE_DIR"
  exit 1
fi

echo "Base directory:"
echo "  $BASE_DIR"
echo

if [ "$DRY_RUN" = true ]; then
  echo "DRY RUN enabled; no changes will be made."
  echo
fi

if [ "$APPLY_PERMISSIONS" = true ]; then
  echo "WARNING: permission changes are enabled."

  if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: Permission changes require root/sudo."
    exit 1
  fi
fi

# ---------------------------------------------------------------------
# Discover unique encounter/output/file_tag directories
#
# Expected waveform structure:
#
#   BASE_DIR/
#     MRN/
#       CSN/
#         GEVITAL/
#           waveform_file.h5
#         GEWAVE/
#           waveform_file.h5
#
# Expected app output:
#
#   MRN/
#     CSN/
#       output/
#         waveform_file/
#           user/
#
# Matching GEWAVE and GEVITAL files share one output folder.
# ---------------------------------------------------------------------

temporary_paths="$(mktemp)"
trap 'rm -f "$temporary_paths"' EXIT

while IFS= read -r -d '' h5_path; do
  namespace_dir="$(dirname "$h5_path")"
  namespace_name="$(basename "$namespace_dir")"

  # Only process expected waveform namespaces.
  case "$namespace_name" in
    GEWAVE|GEVITAL)
      ;;
    *)
      echo "Skipping H5 outside GEWAVE/GEVITAL:"
      echo "  $h5_path"
      continue
      ;;
  esac

  encounter_dir="$(dirname "$namespace_dir")"
  h5_filename="$(basename "$h5_path")"
  h5_stem="${h5_filename%.*}"

  record_output_dir="${encounter_dir}/output/${h5_stem}"

  # GEWAVE and GEVITAL may contain the same file tag, so collect paths first
  # and remove duplicates before creating folders.
  printf '%s\n' "$record_output_dir" >> "$temporary_paths"

done < <(
  find "$BASE_DIR" \
    -type d -name output -prune -o \
    -type f \( -iname "*.h5" -o -iname "*.hdf5" \) -print0
)

sort -u "$temporary_paths" -o "$temporary_paths"

record_count=0

while IFS= read -r record_output_dir; do
  [ -n "$record_output_dir" ] || continue

  record_count=$((record_count + 1))

  echo
  echo "Waveform output directory:"
  echo "  $record_output_dir"

  run_cmd mkdir -p "$record_output_dir"

  for user in "${USERS[@]}"; do
    create_user_folder "$record_output_dir" "$user"
  done

  for adjudicator in "${ADJUDICATORS[@]}"; do
    create_user_folder "$record_output_dir" "$adjudicator"
  done

done < "$temporary_paths"

echo
echo "Done."
echo "Processed ${record_count} unique waveform record(s)."