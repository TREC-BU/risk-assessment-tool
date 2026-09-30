#!/bin/sh
# Rebuild and restart the bot from the current checkout. The bot announces
# the commit below in Slack once it's running.
set -eu
cd "$(dirname "$0")/.."

RISK_COMMIT_SHA="$(git rev-parse HEAD)"
RISK_COMMIT_AUTHOR="$(git log -1 --format=%an)"
RISK_COMMIT_MESSAGE="$(git log -1 --format=%B)"
export RISK_COMMIT_SHA RISK_COMMIT_AUTHOR RISK_COMMIT_MESSAGE

docker compose up -d --build
docker image prune -f
