#!/bin/sh
set -eu
for suffix in a t l p r n x; do
  echo "Lab6: creating outbox/inbox in tutor_$suffix (IF NOT EXISTS)"
  psql -h postgres -U lab_admin -d "tutor_$suffix" -v ON_ERROR_STOP=1 -f /lab6/migration.sql
done
