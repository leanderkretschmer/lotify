#!/bin/bash
set -e

echo "Starte Lotify-Server und WebUI via docker-compose..."
docker-compose down || true
docker-compose build
docker-compose up -d

echo "Lotify-Server (API:8080) und WebUI (Port 80) laufen jetzt." 