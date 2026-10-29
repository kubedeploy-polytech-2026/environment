#!/usr/bin/env bash

validate_rollout_timeout() {
  : "${ROLLOUT_TIMEOUT_SECONDS:=600}"
  if [[ ! "$ROLLOUT_TIMEOUT_SECONDS" =~ ^[1-9][0-9]{0,3}$ ]] || (( ROLLOUT_TIMEOUT_SECONDS > 3600 )); then
    echo 'ROLLOUT_TIMEOUT_SECONDS must be an integer from 1 to 3600' >&2
    exit 2
  fi
}
