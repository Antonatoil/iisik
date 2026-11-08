#!/bin/bash
set -euo pipefail
BIN=/opt/kafka/bin
for topic in tutor.events.v1 tutor.events.dlq.v1; do
  "$BIN/kafka-topics.sh" --bootstrap-server kafka:9092 --create --if-not-exists \
    --topic "$topic" --partitions 6 --replication-factor 1
  "$BIN/kafka-topics.sh" --bootstrap-server kafka:9092 --describe --topic "$topic"
done
