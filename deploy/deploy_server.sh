#!/usr/bin/env bash
# Sync the backend to the server and (re)start it behind Traefik.
#   deploy/deploy_server.sh            # sync + build + restart
#   deploy/deploy_server.sh test       # also run the automated test suite inside the server
# Server address and SSH key come from ~/.config/docintel/server.env (never committed):
#   SSH_HOST=user@host   SSH_KEY=~/.ssh/key   REMOTE_DIR=/docker/docintel
set -euo pipefail
cd "$(dirname "$0")/.."
source ~/.config/docintel/server.env
KEY="${SSH_KEY/#\~/$HOME}"
SSH=(ssh -i "$KEY" -o IdentitiesOnly=yes -o BatchMode=yes "$SSH_HOST")
rsync -az --delete -e "ssh -i $KEY -o IdentitiesOnly=yes -o BatchMode=yes" \
  --exclude .git --exclude 'frontend/' --exclude '.env' --exclude 'dataset/out/' --exclude '__pycache__' \
  --exclude 'evaluation/results/' --exclude 'dataset/samples/' ./ "$SSH_HOST:$REMOTE_DIR/app/"
"${SSH[@]}" "cd $REMOTE_DIR/app && docker compose -f docker-compose.yml -f deploy/docker-compose.server.yml up -d --build --remove-orphans && docker compose ps --format '{{.Service}} {{.State}}'"
if [[ "${1:-}" == "test" ]]; then
  "${SSH[@]}" "cd $REMOTE_DIR/app && mkdir -p evaluation/results && PW=\$(grep ^POSTGRES_PASSWORD .env | cut -d= -f2) && \
    docker compose -f docker-compose.yml -f deploy/docker-compose.server.yml run --rm --no-deps -u 0 -l traefik.enable=false \
      -v $REMOTE_DIR/app/evaluation/results:/results \
      -e TEST_DATABASE_URL=postgresql+psycopg://docintel:\$PW@db:5432/docintel_test -e REDIS_URL=redis://redis:6379/15 \
      api sh -c 'pip install -q -r requirements-dev.txt 2>&1 | grep -v notice; pytest -p no:cacheprovider -rf --durations=5 \
        --junitxml=/results/test-results.xml --cov=app --cov-report=term --cov-report=xml:/results/coverage.xml' 2>&1 | tee /tmp/docintel-pytest.log | tail -60"
  rsync -az -e "ssh -i $KEY -o IdentitiesOnly=yes -o BatchMode=yes" "$SSH_HOST:$REMOTE_DIR/app/evaluation/results/test-results.xml" \
    "$SSH_HOST:$REMOTE_DIR/app/evaluation/results/coverage.xml" evaluation/results/ || true
fi
