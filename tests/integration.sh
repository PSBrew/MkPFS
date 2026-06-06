#!/usr/bin/env bash

# Re-exec with bash when launched from another shell (for example, zsh in IDE run configs).
if [[ -z "${BASH_VERSION:-}" ]]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "${SCRIPT_PATH}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

STRATEGY="${1:-}"
SOURCE_DIR="${2:-}"
TARGET_DIR="${3:-}"
FTP_URL=""
FORCE_REBUILD="false"
TEMP_DIRS=()

usage() {
  cat <<'EOT'
Usage:
  ./tests/integration.sh "strategy" "source_dir" "target_dir" ["ftp://1.1.1.1:1234/folder/name" | "-"] [--force]

Strategies:
  all          Process everything
  files        Process only .exfat and .ffpkg files
  folders      Process only folders, using both folder strategies
  single-pass  Process only folders with pack folder -> .raw.ffpfs
  two-pass     Process only folders with inner pfs_image.dat -> .raw.ffpfsc
  help         Show this help

Examples:
  ./tests/integration.sh all /games ./tmp/integration-output
  ./tests/integration.sh files /games ./tmp/integration-output
  ./tests/integration.sh single-pass /games ./tmp/integration-output
  ./tests/integration.sh all /games ./tmp/integration-output ftp://1.1.1.1:1234/folder/name
  ./tests/integration.sh all /games ./tmp/integration-output --force
  ./tests/integration.sh all /games ./tmp/integration-output - --force

Notes:
  - The script uses "uv run --frozen mkpfs" from the repo one level above this script.
  - If FTP_URL is empty or "-", upload is skipped.
  - Use --force to rebuild outputs even when target artifacts already exist.
  - Uploaded files are sent with a trailing underscore in the final remote file name.
EOT
}

log() {
  printf '[info] %s\n' "$*"
}

log_item_start() {
  local item_name="$1"
  local item_kind="$2"
  local blue='\033[34m'
  local reset='\033[0m'

  # Blue marker to make per-item processing boundaries easy to spot in long logs.
  printf '%b[game] ==== START %s (%s) ====%b\n' "${blue}" "${item_name}" "${item_kind}" "${reset}"
}

warn() {
  printf '[warn] %s\n' "$*" >&2
}

die() {
  printf '[error] %s\n' "$*" >&2
  exit 1
}

register_temp_dir() {
  local temp_dir="$1"
  TEMP_DIRS+=("${temp_dir}")
}

cleanup_temp_dirs() {
  local temp_dir=""
  local cleaned_count=0

  set +e
  for temp_dir in "${TEMP_DIRS[@]-}"; do
    if [[ -n "${temp_dir}" && -d "${temp_dir}" ]]; then
      rm -rf -- "${temp_dir}"
      cleaned_count=$((cleaned_count + 1))
    fi
  done
  set -e

  TEMP_DIRS=()

  if [[ "${cleaned_count}" -gt 0 ]]; then
    log "Cleaned ${cleaned_count} temporary staging director$( [[ "${cleaned_count}" -eq 1 ]] && printf 'y' || printf 'ies' )"
  fi
}

abs_path() {
  local path="$1"
  local dir_part=""
  local base_part=""

  if [[ -d "$path" ]]; then
    cd "$path" >/dev/null 2>&1 || die "Could not resolve directory path: $path"
    pwd
    return 0
  else
    dir_part="$(dirname -- "$path")"
    base_part="$(basename -- "$path")"
    [[ -n "$base_part" ]] || die "Could not resolve basename for path: $path"
    cd "$dir_part" >/dev/null 2>&1 || die "Could not resolve parent directory: $dir_part"
    printf '%s/%s\n' "$(pwd)" "$base_part"
    return 0
  fi
}

is_valid_strategy() {
  case "$1" in
    all | files | folders | single-pass | two-pass) return 0 ;;
    *) return 1 ;;
  esac
}

validate_target_dir() {
  local path="$1"

  if [[ -f "$path" ]]; then
    die "target_dir points to a file, expected a directory path: $path"
  fi

  if [[ "$path" == *.sh || "$path" == *.sh/ ]]; then
    die "target_dir looks like a shell script path: $path"
  fi

  if [[ "$path" == *'/./'* || "$path" == *'..'* ]]; then
    warn "target_dir contains path traversal-like segments: $path"
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

parse_optional_args() {
  local arg=""

  FTP_URL=""
  FORCE_REBUILD="false"

  for arg in "$@"; do
    if [[ -z "${arg}" ]]; then
      continue
    fi

    case "${arg}" in
      --force)
        FORCE_REBUILD="true"
        ;;
      *)
        if [[ -n "${FTP_URL}" ]]; then
          die "Unknown or duplicate optional argument: ${arg}"
        fi
        FTP_URL="${arg}"
        ;;
    esac
  done
}

build_prefix() {
  local commit_id=""

  commit_id="$(env -u GIT_DIR -u GIT_WORK_TREE git -C "${REPO_DIR}" rev-parse --short HEAD 2>/dev/null || true)"

  if [[ -z "${commit_id}" ]]; then
    commit_id="nogit"
  fi

  printf '%s\n' "${commit_id}"
}

sanitize_name() {
  local value="$1"
  value="${value// /_}"
  printf '%s\n' "${value}"
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
  local temp_dat_path="${5:-}"
  local pfs_file=""
  local temp_dat_dir=""
  local file_count=""

  mkdir -p "$(dirname "${artifact_path}")"

  if [[ -f "${artifact_path}" ]]; then
    if [[ "${FORCE_REBUILD}" == "true" ]]; then
      log "--force enabled, replacing existing artifact: $(basename "${artifact_path}")"
      rm -f "${artifact_path}"
    else
      log "Skipping existing artifact: $(basename "${artifact_path}")"
      return 0
    fi
  fi

  log "Building $(basename "${artifact_path}")"

  if [[ "${pack_mode}" == "file" ]]; then
    run_mkpfs pack file "${source_path}" "${artifact_path}"
  elif [[ "${pack_mode}" == "single-pass" ]]; then
    run_mkpfs pack folder "${source_path}" "${artifact_path}"
  elif [[ "${pack_mode}" == "two-pass" ]]; then
    # Two-pass builds stage an uncompressed image as an exact pfs_image.dat file.
    [[ -n "${temp_dat_path}" ]] || die "Missing temp_dat_path for two-pass build"
    [[ "$(basename "${temp_dat_path}")" == "pfs_image.dat" ]] || die "Two-pass temp path must end with pfs_image.dat: ${temp_dat_path}"

    pfs_file="${temp_dat_path}"
    temp_dat_dir="$(dirname "${pfs_file}")"
    mkdir -p "${temp_dat_dir}"
    rm -f "${pfs_file}"

    log "Two-pass staging file: ${pfs_file}"

    run_mkpfs pack folder --no-compress --no-adjust-output-file-extension "${source_path}" "${pfs_file}"

    if [[ ! -f "${pfs_file}" ]]; then
      die "Expected ${pfs_file} to exist after first pass"
    fi

    # Ensure the staging folder contains only pfs_image.dat.
    file_count="$(find "${temp_dat_dir}" -maxdepth 1 -type f | wc -l | tr -d '[:space:]')"
    if [[ "${file_count}" -ne 1 ]]; then
      die "Temporary directory ${temp_dat_dir} must contain exactly one file (pfs_image.dat), found ${file_count}"
    fi

    # Verify that the first-pass pfs_image.dat contains the full source folder.
    log "Verifying first-pass output $(basename "${pfs_file}") contains all source files"
    run_mkpfs verify "${pfs_file}" --source-dir "${source_path}"
    log "Skipping tree for first-pass staging file $(basename "${pfs_file}")"

    run_mkpfs pack file "${pfs_file}" "${artifact_path}"
  else
    die "Unknown pack mode: ${pack_mode}"
  fi

  log "Verifying $(basename "${artifact_path}")"

  # For two-pass mode, verify that the final artifact contains pfs_image.dat
  # For other modes, use the source_kind to determine verification approach
  if [[ "${pack_mode}" == "two-pass" && -n "${pfs_file}" ]]; then
    run_mkpfs verify "${artifact_path}" --source-file "${pfs_file}"
    rm -rf "$(dirname "${pfs_file}")"
  elif [[ "${source_kind}" == "dir" ]]; then
    run_mkpfs verify "${artifact_path}" --source-dir "${source_path}"
  else
    run_mkpfs verify "${artifact_path}"
  fi

  if [[ "${pack_mode}" == "single-pass" ]]; then
    log "Skipping tree for raw folder artifact $(basename "${artifact_path}")"
  else
    log "Tree $(basename "${artifact_path}")"
    run_mkpfs tree "${artifact_path}"
  fi

  upload_file "${artifact_path}"
}

process_file_input() {
  local source_file="$1"
  local prefix="$2"
  local name=""
  local game_name=""
  local artifact_path=""

  name="$(basename "${source_file}")"
  game_name="$(sanitize_name "${name%.*}")"

  artifact_path="${TARGET_DIR}/${prefix}-${game_name}.ffpfsc"

  process_artifact \
    "${source_file}" \
    "file" \
    "${artifact_path}" \
    "file"
}

process_folder_single_pass() {
  local source_dir="$1"
  local prefix="$2"
  local game_name=""
  local artifact_path=""

  game_name="$(sanitize_name "$(basename "${source_dir}")")"

  artifact_path="${TARGET_DIR}/${prefix}-${game_name}.raw.ffpfs"

  process_artifact \
    "${source_dir}" \
    "dir" \
    "${artifact_path}" \
    "single-pass"
}

process_folder_two_pass() {
  local source_dir="$1"
  local prefix="$2"
  local game_name=""
  local artifact_path=""
  local temp_dir=""
  local temp_dat_path=""

  game_name="$(sanitize_name "$(basename "${source_dir}")")"

  artifact_path="${TARGET_DIR}/${prefix}-${game_name}.raw.ffpfsc"

  if [[ -f "${artifact_path}" ]]; then
    if [[ "${FORCE_REBUILD}" == "true" ]]; then
      log "--force enabled, replacing existing artifact: $(basename "${artifact_path}")"
      rm -f "${artifact_path}"
    else
      log "Skipping existing artifact: $(basename "${artifact_path}")"
      return 0
    fi
  fi

  # Use OS temp for per-item staging to avoid clutter under target output.
  temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/mkpfs-two-pass.${prefix}-${game_name}.XXXXXX")"
  register_temp_dir "${temp_dir}"
  temp_dat_path="${temp_dir}/pfs_image.dat"

  process_artifact \
    "${source_dir}" \
    "dir" \
    "${artifact_path}" \
    "two-pass" \
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

  parse_optional_args "${@:4}"

  is_valid_strategy "${STRATEGY}" || die "Unknown strategy: ${STRATEGY}"

  [[ -n "${SOURCE_DIR}" ]] || die "Missing source_dir"
  [[ -n "${TARGET_DIR}" ]] || die "Missing target_dir"
  [[ -d "${SOURCE_DIR}" ]] || die "Source directory does not exist: ${SOURCE_DIR}"

  require_cmd uv
  require_cmd git
  require_cmd curl
  require_cmd find
  require_cmd mktemp

  SOURCE_DIR="$(abs_path "${SOURCE_DIR}")"
  validate_target_dir "${TARGET_DIR}"
  TARGET_DIR="$(abs_path "${TARGET_DIR}")"
  validate_target_dir "${TARGET_DIR}"
  mkdir -p "${TARGET_DIR}"

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

  if [[ "${FORCE_REBUILD}" == "true" ]]; then
    log "Force rebuild enabled"
  fi

  while IFS= read -r -d '' entry; do
    processed=1

    if [[ -f "${entry}" ]]; then
      lower_name="$(printf '%s' "${entry##*/}" | tr '[:upper:]' '[:lower:]')"
      if [[ "${lower_name}" == *.exfat || "${lower_name}" == *.ffpkg ]]; then
        log_item_start "$(basename "${entry}")" "file"
        if should_run_files; then
          process_file_input "${entry}" "${prefix}"
        else
          log "Skipping file input: $(basename "${entry}")"
        fi
      else
        log "Skipping unsupported file: $(basename "${entry}")"
      fi
    elif [[ -d "${entry}" ]]; then
      log_item_start "$(basename "${entry}")" "folder"
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

trap cleanup_temp_dirs EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

main "$@"
