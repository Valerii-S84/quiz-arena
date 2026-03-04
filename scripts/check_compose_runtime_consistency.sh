#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$ROOT_DIR"

EXPECTED_COMPOSE_FILE="${ROOT_DIR}/docker-compose.prod.yml"
NAME_REGEX='^(quiz_arena_|quizarena-)'

usage() {
  cat <<'USAGE'
Usage: scripts/check_compose_runtime_consistency.sh [--expected-compose-file <path>] [--name-regex <regex>]

Checks that all running Quiz Arena containers come from one Docker Compose config file.
Fails if runtime is mixed across multiple compose config sources.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --expected-compose-file)
      if [[ $# -lt 2 ]]; then
        echo "ERROR: --expected-compose-file requires a value" >&2
        exit 2
      fi
      EXPECTED_COMPOSE_FILE="$2"
      shift 2
      ;;
    --name-regex)
      if [[ $# -lt 2 ]]; then
        echo "ERROR: --name-regex requires a value" >&2
        exit 2
      fi
      NAME_REGEX="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is required" >&2
  exit 1
fi

if [[ ! -f "$EXPECTED_COMPOSE_FILE" ]]; then
  echo "ERROR: expected compose file does not exist: $EXPECTED_COMPOSE_FILE" >&2
  exit 1
fi

if command -v realpath >/dev/null 2>&1; then
  EXPECTED_COMPOSE_FILE="$(realpath "$EXPECTED_COMPOSE_FILE")"
else
  compose_dir="$(cd "$(dirname "$EXPECTED_COMPOSE_FILE")" && pwd)"
  EXPECTED_COMPOSE_FILE="${compose_dir}/$(basename "$EXPECTED_COMPOSE_FILE")"
fi

declare -a expected_services=()
while IFS= read -r service; do
  [[ -n "$service" ]] && expected_services+=("$service")
done < <(docker compose -f "$EXPECTED_COMPOSE_FILE" config --services)

if [[ ${#expected_services[@]} -eq 0 ]]; then
  echo "ERROR: unable to resolve services from compose file: $EXPECTED_COMPOSE_FILE" >&2
  exit 1
fi

services_csv=""
for service in "${expected_services[@]}"; do
  if [[ -z "$services_csv" ]]; then
    services_csv="$service"
  else
    services_csv="${services_csv},${service}"
  fi
done

declare -a rows=()
while IFS= read -r row; do
  [[ -n "$row" ]] && rows+=("$row")
done < <(
  docker ps --format '{{.Names}}\t{{.Label "com.docker.compose.project"}}\t{{.Label "com.docker.compose.project.config_files"}}\t{{.Label "com.docker.compose.service"}}' \
    | awk -F '\t' -v name_regex="$NAME_REGEX" -v allowed_services="$services_csv" '
      function is_allowed_service(service, csv, count, i, parts) {
        count = split(csv, parts, ",")
        for (i = 1; i <= count; i++) {
          if (service == parts[i]) {
            return 1
          }
        }
        return 0
      }
      $1 ~ name_regex && is_allowed_service($4, allowed_services) {
        print $0
      }
    '
)

if [[ ${#rows[@]} -eq 0 ]]; then
  echo "INFO: no running containers matched runtime filter; skipping consistency check."
  exit 0
fi

print_rows() {
  printf '%-30s %-16s %-70s %-12s\n' "container" "project" "config_files" "service"
  printf '%s\n' "----------------------------------------------------------------------------------------------------------------------------------"
  local row name project config service
  for row in "${rows[@]}"; do
    IFS=$'\t' read -r name project config service <<< "$row"
    printf '%-30s %-16s %-70s %-12s\n' "$name" "$project" "$config" "$service"
  done
}

declare -A unique_projects=()
declare -A unique_configs=()
declare -a invalid_label_rows=()
for row in "${rows[@]}"; do
  IFS=$'\t' read -r _name project config _service <<< "$row"
  if [[ -z "$project" || -z "$config" ]]; then
    invalid_label_rows+=("$row")
    continue
  fi
  unique_projects["$project"]=1
  unique_configs["$config"]=1
done

if [[ ${#invalid_label_rows[@]} -gt 0 ]]; then
  echo "ERROR: one or more containers are missing compose labels" >&2
  print_rows >&2
  exit 1
fi

if [[ ${#unique_projects[@]} -ne 1 ]]; then
  echo "ERROR: runtime uses multiple compose projects; expected exactly one" >&2
  print_rows >&2
  exit 1
fi

if [[ ${#unique_configs[@]} -ne 1 ]]; then
  echo "ERROR: runtime is mixed across multiple compose config sources" >&2
  print_rows >&2
  exit 1
fi

runtime_config=""
for value in "${!unique_configs[@]}"; do
  runtime_config="$value"
done

if [[ "$runtime_config" != "$EXPECTED_COMPOSE_FILE" ]]; then
  echo "ERROR: runtime compose config mismatch" >&2
  echo "expected: $EXPECTED_COMPOSE_FILE" >&2
  echo "actual:   $runtime_config" >&2
  print_rows >&2
  exit 1
fi

echo "OK: compose runtime is consistent."
echo "project: ${!unique_projects[*]}"
echo "config:  $runtime_config"
