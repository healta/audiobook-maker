#!/bin/bash
# Narrates a tiny book with a built image, the way the real service does. Usage: bash tests/smoke.sh IMAGE
set -euo pipefail
image=$1; here=$(cd "$(dirname "$0")" && pwd); data=$(mktemp -d); chmod 777 "$data"
trap 'docker logs smoke 2>&1 | tail -40; docker rm -f smoke >/dev/null 2>&1 || true' EXIT

docker run --rm --network none "$image" check
docker run --rm --network none -v "$here:/opt/app/tests:ro" --entrypoint python "$image" -W ignore -m unittest discover -s tests

docker run -d --name smoke --user 568:568 --cap-drop ALL --security-opt no-new-privileges -p 127.0.0.1:18080:8080 -v "$data:/data" "$image" >/dev/null
for _ in $(seq 30); do [ -d "$data/input" ] && break; sleep 1; done
docker exec -i smoke sh -c 'cat > /data/input/mini.html' < "$here/mini.html"
for _ in $(seq 150); do
  compgen -G "$data/output/*/*.m4b" >/dev/null && break
  [ "$(docker inspect smoke --format '{{.State.Running}}')" = true ] || { echo "the service stopped"; exit 1; }
  sleep 4
done

cat "$data"/output/*/report.txt
grep -q "decodes cleanly, length and chapter marks are right" "$data"/output/*/report.txt
grep -q ", 0 still look odd" "$data"/output/*/report.txt
sleep 3
curl -fsS http://127.0.0.1:18080/ | grep -q "<title>Audiobooks"
curl -fsS http://127.0.0.1:18080/status.json | grep -q '"done_total": 1'
echo "the image works"
