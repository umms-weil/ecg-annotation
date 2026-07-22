#!/bin/bash

# setup_annotator_folders.sh
#
# This script automates the creation of per-user annotation output folders for every subject in a data base directory.
# For each subject found in the base directory, it creates an /output/{username} subfolder for each annotator/user listed.
# Folder permissions are set so that only the named user (and optionally a group) can access their own annotation files.
# Intended for use by Data Ops. BEFORE annotation begins / when new users or subjects are added.
#
# Usage:
#   - Edit BASE_DIR to be the path to your main waveforms/subjects directory.
#   - Edit the USERS array to include your annotator uniqnames.
#   - Optionally edit GROUP for your institutional data group.
#   - Run as root or with sudo for chown operations.
#
# Example:
#   ./setup_annotator_folders.sh
# Note: This script does not modify annotation files; it only creates folders and sets permissions.
#
# setup_annotator_folders_h5.sh
#
# Create per-user annotation folders for each H5 waveform file.
#
# Expected app layout:
#
#   BASE_DIR/
#     MRN/
#       CSN/
#         GEVITAL/
#           waveform_file.h5
#           output/
#             waveform_file/
#               sardara/
#               ghamid/
#               ...
#
# This matches processing.py:
#
#   output_path = os.path.join(root, "output", h5_stem)
#   user folder = output_path / user_name
#
# This script is non-destructive:
#   - creates folders with mkdir -p
#   - changes folder ownership/permissions
#   - does not remove annotation CSVs
#
# setup_annotator_folders_h5.sh
#
# Create per-user annotation folders for each H5 waveform file.
#
# Expected app layout:
#
#   BASE_DIR/
#     MRN/
#       CSN/
#         GEVITAL/
#           waveform_file.h5
#           output/
#             waveform_file/
#               sardara/
#               ghamid/
#               ...
#
# This matches processing.py:
#
#   output_path = os.path.join(root, "output", h5_stem)
#   user folder = output_path / user_name
#
# This script is non-destructive:
#   - creates folders with mkdir -p
#   - changes folder ownership/permissions
#   - does not remove annotation CSVs
#

set -euo pipefail

# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

BASE_DIR="/Users/pwalczyk/Documents/Projects/Uconn-CPR/AnnotationSoftware/ecg-annotation/software/data/TestSubject"

USERS=("sardara" "ghamid" "kwheels" "gangidi")

DEVELOPERS=("pwalczyk")

# Set to true to preview actions without changing anything.
DRY_RUN=false

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

run_cmd() {
  if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] $*"
  else
    "$@"
  fi
}

set_acl_for_user() {
  local target_path="$1"
  local acl_user="$2"
  local acl_perms="$3"

  if command -v setfacl >/dev/null 2>&1; then
    run_cmd setfacl -m "u:${acl_user}:${acl_perms}" "$target_path"
  else
    echo "WARNING: setfacl not found. Skipping ACL for ${acl_user} on ${target_path}."
    echo "         On macOS, you may need chmod +a instead of setfacl."
  fi
}

# ---------------------------------------------------------------------
# Validate base directory
# ---------------------------------------------------------------------

if [ ! -d "$BASE_DIR" ]; then
  echo "ERROR: BASE_DIR does not exist:"
  echo "  $BASE_DIR"
  exit 1
fi

echo "Base directory:"
echo "  $BASE_DIR"
echo

echo "Users:"
printf '  %s\n' "${USERS[@]}"
echo

echo "Developers:"
printf '  %s\n' "${DEVELOPERS[@]}"
echo

if [ "$DRY_RUN" = true ]; then
  echo "Running in DRY RUN mode. No changes will be made."
  echo
fi

# ---------------------------------------------------------------------
# Find H5 files, excluding output directories
# ---------------------------------------------------------------------

echo "Searching for H5 files..."

h5_count=0

while IFS= read -r -d '' h5_path; do
  h5_count=$((h5_count + 1))

  h5_dir="$(dirname "$h5_path")"
  h5_file="$(basename "$h5_path")"
  h5_stem="${h5_file%.*}"

  output_dir="${h5_dir}/output"
  h5_output_dir="${output_dir}/${h5_stem}"

  echo
  echo "H5 file:"
  echo "  $h5_path"
  echo "Output folder:"
  echo "  $h5_output_dir"

  # Create output and per-H5 output directories.
  run_cmd mkdir -p "$h5_output_dir"

  # Developers need traverse/list access through output folders.
  for dev in "${DEVELOPERS[@]}"; do
    set_acl_for_user "$output_dir" "$dev" "rx"
    set_acl_for_user "$h5_output_dir" "$dev" "rx"
  done

  # Create per-user folders.
  for user in "${USERS[@]}"; do
    user_output="${h5_output_dir}/${user}"

    run_cmd mkdir -p "$user_output"

    # The annotator needs traverse access through parent output folders.
    # x is enough for traversal without allowing directory listing.
    set_acl_for_user "$output_dir" "$user" "x"
    set_acl_for_user "$h5_output_dir" "$user" "x"

    # User owns their own annotation folder.
    run_cmd chown "$user:$user" "$user_output"

    # Folder private to user by normal UNIX permissions.
    run_cmd chmod 700 "$user_output"

    # Developers/admins get full access via ACL.
    for dev in "${DEVELOPERS[@]}"; do
      set_acl_for_user "$user_output" "$dev" "rwx"
      echo "Set developer ACL for $dev on $user_output"
    done

    echo "Created/verified user folder:"
    echo "  $user_output"
  done

done < <(
  find "$BASE_DIR" \
    -type d -name output -prune -o \
    -type f -name "*.h5" -print0
)

echo
echo "Done."
echo "Found and processed ${h5_count} H5 file(s)."