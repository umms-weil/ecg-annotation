#!/bin/bash

#
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
#
# After running, folders like:
#   /BASE_DIR/subject_DEID1/output/jdoe/
#   /BASE_DIR/subject_DEID1/output/asmith/
# will exist and be restricted to the listed user/group.
#
# Note: This script does not modify annotation files; it only creates folders and sets permissions.
#


# Set these before running
# Bae Directory for data
BASE_DIR="/Users/pwalczyk/Documents/Projects/Uconn-CPR/AnnotationSoftware/ecg-annotation/software/data/TestSubject"
# List of Users
USERS=("sardara" "ghamid")
# List of admin/dev usernames
DEVELOPERS=("pwalczyk" "joblackm")

SUBJECTS=($(find "$BASE_DIR" -maxdepth 1 -mindepth 1 -type d))
echo "Found ${#SUBJECTS[@]} subjects in $BASE_DIR"
for subject_path in "${SUBJECTS[@]}"; do
  subject_name=$(basename "$subject_path")
  output_dir="$subject_path/output"
  mkdir -p "$output_dir"  # Ensure output directory exists

  # Give developers traverse access to output dir
  for dev in "${DEVELOPERS[@]}"; do
    setfacl -m u:$dev:rx "$output_dir"
  done

  for user in "${USERS[@]}"; do
    user_output="$output_dir/$user"
    mkdir -p "$user_output"
    chown "$user:$user" "$user_output"
    chmod 700 "$user_output"
    # Give each developer/admin full access to user folder via ACL
    for dev in "${DEVELOPERS[@]}"; do
      setfacl -m u:$dev:rwx "$user_output"
      echo "Set ACL for $dev on $user_output"
    done
    echo "Created: $user_output, owner: $user, ACLs for developers"
  done
done