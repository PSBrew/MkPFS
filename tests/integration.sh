#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

STRATEGY="${1:-}"
SOURCE_DIR="${2:-}"
TARGET_DIR="${3:-}"
FTP_URL="${4:-}"

usage() {
  cat <<'EOT'
Usage:
  ./integration-tests.sh "strategy" "source_dir" "target_dir" "ftp://1.1.1.1:1234/folder/name"

Strategies:
  all          Process everything
  files        Process only .exfat and .ffpkg files
  folders      Process only folders, using both folder strategies
  single-pass  Process only folders with pack folder -> .raw.ffpfs
  two-pass     Process only folders with inner pfs_image.dat -> .raw.ffpfsc
  help         Show this help

Examples:
  ./integration-tests.sh all /games ./tmp/integration-output
  ./integration-tests.sh files /games ./tmp/integration-output
  ./integration-tests.sh single-pass /games ./tmp/integration-output
  ./integration-tests.sh all /games ./tmp/integration-output ftp://1.1.1.1:1234/folder/name

Notes:
  - The script uses "uv run --frozen mkpfs" from the repo one level above this script.
  - If FTP_URL is empty or "-", upload is skipped.
  - Uploaded files are sent with a trailing underscore in the final remote file name.
EOT
}

log() {
  printf '[info] %s\n' "$*"
}

warn() {
  printf '[warn] %s\n' "$*" >&2
}

die() {
  printf '[error] %s\n' "$*" >&2
  exit 1
}

abs_path() {
  local path="$1"

  if [[ -d "$path" ]]; then
    (
      cd "$path"
      pwd
    )
  else
    (
      cd "$(dirname "$path")"
      printf '%s/%s\n' "$(pwd)" "$(basename "$path")"
    )
  fi
}

require_cmd() {
  local name="$1"
  command -v "$name" >/dev/null 2>&1 || die "Missing required command: $name"
}

run_mkpfs() {
  (
    cd "${REPO_DIR}"
    printf '[cmd] %q' uv
    printf ' %q' run --frozen mkpfs "$@"
    printf '\n'
    uv run --frozen mkpfs "$@"
  )
}

run_mkpfs_to_file() {
  local output_file="$1"
  shift

  (
    cd "${REPO_DIR}"
    printf '[cmd] %q' uv
    printf ' %q' run --frozen mkpfs "$@"
    printf ' > %q\n' "${output_file}"
    uv run --frozen mkpfs "$@" >"${output_file}"
  )
}

contains_mode() {
  local needle="$1"

  case "${STRATEGY}" in
    all) return 0 ;;
    "${needle}") return 0 ;;
    *) return 1 ;;
  esac
}

should_run_files() {
  contains_mode files
}

should_run_single_pass() {
  contains_mode folders || contains_mode single-pass
}

should_run_two_pass() {
  contains_mode folders || contains_mode two-pass
}

build_prefix() {
  local commit_id=""
  local stamp=""

  commit_id="$(git -C "${REPO_DIR}" rev-parse --short HEAD 2>/dev/null || true)"
  stamp="$(date '+%d%H%M')"

  if [[ -z "${commit_id}" ]]; then
    commit_id="nogit"
  fi

  printf '%s-%s\n' "${commit_id}" "${stamp}"
}

sanitize_name() {
  local value="$1"
  value="${value// /_}"
  printf '%s\n' "${value}"
}

detect_unpack_root() {
  local unpack_dir="$1"
  local file_count=""
  local dir_count=""
  local first_dir=""

  file_count="$(find "${unpack_dir}" -mindepth 1 -maxdepth 1 -type f | wc -l | tr -d ' ')"
  dir_count="$(find "${unpack_dir}" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')"

  if [[ "${file_count}" == "0" && "${dir_count}" == "1" ]]; then
    first_dir="$(find "${unpack_dir}" -mindepth 1 -maxdepth 1 -type d -print -quit)"
    printf '%s\n' "${first_dir}"
    return 0
  fi

  printf '%s\n' "${unpack_dir}"
}

write_dir_manifest() {
  local root_dir="$1"
  local output_file="$2"

  : >"${output_file}"

  (
    cd "${root_dir}"
    find . -type f | LC_ALL=C sort | while IFS= read -r rel_path; do
      local clean_path=""
      local hash_value=""
      clean_path="${rel_path#./}"
      hash_value="$(shasum -a 256 "${clean_path}" | awk '{print $1}')"
      printf '%s  %s\n' "${hash_value}" "${clean_path}"
    done
  ) >>"${output_file}"
}

compare_dirs() {
  local source_dir="$1"
  local unpack_dir="$2"
  local report_prefix="$3"
  local unpack_root=""
  local source_manifest=""
  local unpack_manifest=""

  unpack_root="$(detect_unpack_root "${unpack_dir}")"
  source_manifest="${report_prefix}.source.sha256"
  unpack_manifest="${report_prefix}.unpacked.sha256"

  write_dir_manifest "${source_dir}" "${source_manifest}"
  write_dir_manifest "${unpack_root}" "${unpack_manifest}"

  if ! diff -u "${source_manifest}" "${unpack_manifest}" >"${report_prefix}.manifest.diff"; then
    warn "Directory checksum mismatch: ${report_prefix}.manifest.diff"
    return 1
  fi

  rm -f "${report_prefix}.manifest.diff"
}

compare_file() {
  local source_file="$1"
  local unpack_dir="$2"
  local report_prefix="$3"
  local source_hash=""
  local unpack_hash=""
  local unpacked_file=""
  local unpacked_count=""
  local source_manifest=""
  local unpack_manifest=""

  unpacked_count="$(find "${unpack_dir}" -type f | wc -l | tr -d ' ')"

  if [[ "${unpacked_count}" == "1" ]]; then
    unpacked_file="$(find "${unpack_dir}" -type f -print -quit)"
  else
    unpacked_file="$(find "${unpack_dir}" -type f -name "$(basename "${source_file}")" -print -quit)"
  fi

  [[ -n "${unpacked_file}" ]] || die "Could not identify unpacked file for ${source_file}"

  source_hash="$(shasum -a 256 "${source_file}" | awk '{print $1}')"
  unpack_hash="$(shasum -a 256 "${unpacked_file}" | awk '{print $1}')"

  source_manifest="${report_prefix}.source.sha256"
  unpack_manifest="${report_prefix}.unpacked.sha256"

  printf '%s  %s\n' "${source_hash}" "$(basename "${source_file}")" >"${source_manifest}"
  printf '%s  %s\n' "${unpack_hash}" "$(basename "${unpacked_file}")" >"${unpack_manifest}"

  if [[ "${source_hash}" != "${unpack_hash}" ]]; then
    warn "File checksum mismatch for ${source_file}"
    return 1
  fi
}

upload_file() {
  local artifact_path="$1"
  local remote_url=""

  if [[ -z "${FTP_URL}" || "${FTP_URL}" == "-" ]]; then
    return 0
  fi

  remote_url="${FTP_URL%/}/$(basename "${artifact_path}")_"
  log "Uploading $(basename "${artifact_path}") -> ${remote_url}"
  curl --fail --silent --show-error --ftp-create-dirs -T "${artifact_path}" "${remote_url}"
}

process_artifact() {
  local source_path="$1"
  local source_kind="$2"
  local artifact_path="$3"
  local pack_mode="$4"
  local inspect_path="$5"
  local tree_path="$6"
  local unpack_dir="$7"
  local report_prefix="$8"
  local temp_dat_path="${9:-}"

  mkdir -p "$(dirname "${artifact_path}")"
  mkdir -p "$(dirname "${inspect_path}")"
  mkdir -p "${unpack_dir}"

  log "Building $(basename "${artifact_path}")"

  if [[ "${pack_mode}" == "file" ]]; then
    run_mkpfs pack file --verify "${source_path}" "${artifact_path}"
  elif [[ "${pack_mode}" == "single-pass" ]]; then
    run_mkpfs pack folder --verify "${source_path}" "${artifact_path}"
  elif [[ "${pack_mode}" == "two-pass" ]]; then
    [[ -n "${temp_dat_path}" ]] || die "Missing temp_dat_path for two-pass build"
    run_mkpfs pack folder --verify --no-compress --no-adjust-output-file-extension "${source_path}" "${temp_dat_path}"
    run_mkpfs pack file --verify "${temp_dat_path}" "${artifact_path}"
    rm -f "${temp_dat_path}"
  else
    die "Unknown pack mode: ${pack_mode}"
  fi

  log "Verifying $(basename "${artifact_path}")"

  if [[ "${source_kind}" == "dir" ]]; then
    run_mkpfs verify "${artifact_path}" --source-dir "${source_path}"
  else
    run_mkpfs verify "${artifact_path}"
  fi

  log "Inspecting $(basename "${artifact_path}")"
  run_mkpfs_to_file "${inspect_path}" inspect "${artifact_path}" --format json
  run_mkpfs_to_file "${tree_path}" tree "${artifact_path}"

  log "Unpacking $(basename "${artifact_path}")"
  rm -rf "${unpack_dir}"
  mkdir -p "${unpack_dir}"
  run_mkpfs unpack "${artifact_path}" "${unpack_dir}" --overwrite

  log "Comparing checksums for $(basename "${artifact_path}")"
  if [[ "${source_kind}" == "dir" ]]; then
    compare_dirs "${source_path}" "${unpack_dir}" "${report_prefix}"
  else
    compare_file "${source_path}" "${unpack_dir}" "${report_prefix}"
  fi

  rm -rf "${unpack_dir}"
  upload_file "${artifact_path}"
}

process_file_input() {
  local source_file="$1"
  local prefix="$2"
  local name=""
  local game_name=""
  local artifact_path=""
  local inspect_path=""
  local tree_path=""
  local unpack_dir=""
  local report_prefix=""

  name="$(basename "${source_file}")"
  game_name="$(sanitize_name "${name%.*}")"

  artifact_path="${TARGET_DIR}/${prefix}-${game_name}.ffpfsc"
  inspect_path="${TARGET_DIR}/reports/${prefix}-${game_name}.ffpfsc.inspect.json"
  tree_path="${TARGET_DIR}/reports/${prefix}-${game_name}.ffpfsc.tree.txt"
  unpack_dir="${TARGET_DIR}/work/${prefix}-${game_name}.ffpfsc.unpack"
  report_prefix="${TARGET_DIR}/reports/${prefix}-${game_name}.ffpfsc"

  process_artifact \
    "${source_file}" \
    "file" \
    "${artifact_path}" \
    "file" \
    "${inspect_path}" \
    "${tree_path}" \
    "${unpack_dir}" \
    "${report_prefix}"
}

process_folder_single_pass() {
  local source_dir="$1"
  local prefix="$2"
  local game_name=""
  local artifact_path=""
  local inspect_path=""
  local tree_path=""
  local unpack_dir=""
  local report_prefix=""

  game_name="$(sanitize_name "$(basename "${source_dir}")")"

  artifact_path="${TARGET_DIR}/${prefix}-${game_name}.raw.ffpfs"
  inspect_path="${TARGET_DIR}/reports/${prefix}-${game_name}.raw.ffpfs.inspect.json"
  tree_path="${TARGET_DIR}/reports/${prefix}-${game_name}.raw.ffpfs.tree.txt"
  unpack_dir="${TARGET_DIR}/work/${prefix}-${game_name}.raw.ffpfs.unpack"
  report_prefix="${TARGET_DIR}/reports/${prefix}-${game_name}.raw.ffpfs"

  process_artifact \
    "${source_dir}" \
    "dir" \
    "${artifact_path}" \
    "single-pass" \
    "${inspect_path}" \
    "${tree_path}" \
    "${unpack_dir}" \
    "${report_prefix}"
}

process_folder_two_pass() {
  local source_dir="$1"
  local prefix="$2"
  local game_name=""
  local artifact_path=""
  local inspect_path=""
  local tree_path=""
  local unpack_dir=""
  local report_prefix=""
  local temp_dat_path=""

  game_name="$(sanitize_name "$(basename "${source_dir}")")"

  artifact_path="${TARGET_DIR}/${prefix}-${game_name}.raw.ffpfsc"
  inspect_path="${TARGET_DIR}/reports/${prefix}-${game_name}.raw.ffpfsc.inspect.json"
  tree_path="${TARGET_DIR}/reports/${prefix}-${game_name}.raw.ffpfsc.tree.txt"
  unpack_dir="${TARGET_DIR}/work/${prefix}-${game_name}.raw.ffpfsc.unpack"
  report_prefix="${TARGET_DIR}/reports/${prefix}-${game_name}.raw.ffpfsc"
  temp_dat_path="${TARGET_DIR}/work/${prefix}-${game_name}.pfs_image.dat"

  process_artifact \
    "${source_dir}" \
    "dir" \
    "${artifact_path}" \
    "two-pass" \
    "${inspect_path}" \
    "${tree_path}" \
    "${unpack_dir}" \
    "${report_prefix}" \
    "${temp_dat_path}"
}

main() {
  local prefix=""
  local entry=""
  local processed=0
  local lower_name=""

  if [[ -z "${STRATEGY}" || "${STRATEGY}" == "help" || "${STRATEGY}" == "--help" || "${STRATEGY}" == "-h" ]]; then
    usage
    exit 0
  fi

  [[ -n "${SOURCE_DIR}" ]] || die "Missing source_dir"
  [[ -n "${TARGET_DIR}" ]] || die "Missing target_dir"
  [[ -d "${SOURCE_DIR}" ]] || die "Source directory does not exist: ${SOURCE_DIR}"

  require_cmd uv
  require_cmd git
  require_cmd curl
  require_cmd shasum
  require_cmd diff
  require_cmd find
  require_cmd awk

  SOURCE_DIR="$(abs_path "${SOURCE_DIR}")"
  mkdir -p "${TARGET_DIR}/reports" "${TARGET_DIR}/work"
  TARGET_DIR="$(abs_path "${TARGET_DIR}")"

  prefix="$(build_prefix)"

  log "Repo dir: ${REPO_DIR}"
  log "Strategy: ${STRATEGY}"
  log "Source dir: ${SOURCE_DIR}"
  log "Target dir: ${TARGET_DIR}"
  log "Build prefix: ${prefix}"

  if [[ -n "${FTP_URL}" && "${FTP_URL}" != "-" ]]; then
    log "FTP upload enabled: ${FTP_URL}"
  else
    log "FTP upload disabled"
  fi

  while IFS= read -r -d '' entry; do
    processed=1

    if [[ -f "${entry}" ]]; then
      lower_name="$(printf '%s' "${entry##*/}" | tr '[:upper:]' '[:lower:]')"
      if [[ "${lower_name}" == *.exfat || "${lower_name}" == *.ffpkg ]]; then
        if should_run_files; then
          process_file_input "${entry}" "${prefix}"
        else
          log "Skipping file input: $(basename "${entry}")"
        fi
      else
        log "Skipping unsupported file: $(basename "${entry}")"
      fi
    elif [[ -d "${entry}" ]]; then
      if should_run_single_pass; then
        process_folder_single_pass "${entry}" "${prefix}"
      else
        log "Skipping single-pass folder build: $(basename "${entry}")"
      fi

      if should_run_two_pass; then
        process_folder_two_pass "${entry}" "${prefix}"
      else
        log "Skipping two-pass folder build: $(basename "${entry}")"
      fi
    fi
  done < <(find "${SOURCE_DIR}" -mindepth 1 -maxdepth 1 -print0)

  [[ "${processed}" == "1" ]] || die "No inputs found in ${SOURCE_DIR}"

  log "Integration run completed successfully"
}

main "$@"
