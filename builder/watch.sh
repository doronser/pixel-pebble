#!/bin/bash
set -u

QUEUE_DIR="/queue"
STORAGE_DIR="/storage"

echo "pebble builder: watching ${QUEUE_DIR}"

while true; do
  for job_dir in "${QUEUE_DIR}"/*/; do
    [ -d "$job_dir" ] || continue
    job_id="$(basename "$job_dir")"
    out_dir="${STORAGE_DIR}/${job_id}"
    mkdir -p "$out_dir"

    if [ -f "${out_dir}/status.json" ]; then
      continue
    fi

    echo "{\"state\": \"building\"}" > "${out_dir}/status.json"
    echo "Building job ${job_id}..."

    if (cd "$job_dir" && pebble build) > "${out_dir}/build.log" 2>&1; then
      pbw_file="$(find "${job_dir}/build" -maxdepth 1 -iname '*.pbw' | head -n1)"
      if [ -n "$pbw_file" ]; then
        cp "$pbw_file" "${out_dir}/watchface.pbw"
        echo "{\"state\": \"done\"}" > "${out_dir}/status.json"
        echo "Job ${job_id} done."
      else
        echo "{\"state\": \"error\", \"message\": \"build succeeded but no .pbw found\"}" > "${out_dir}/status.json"
      fi
    else
      echo "{\"state\": \"error\", \"message\": \"pebble build failed, see build.log\"}" > "${out_dir}/status.json"
      echo "Job ${job_id} failed."
    fi

    rm -rf "$job_dir"
  done
  sleep 2
done
