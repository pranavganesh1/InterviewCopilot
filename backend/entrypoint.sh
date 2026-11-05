#!/bin/sh
set -e
# Auto-migrate on every start — the dev DB can never drift from the models.
alembic upgrade head
exec "$@"
