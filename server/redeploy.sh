#!/bin/bash
set -e

echo "Stoppe und entferne alle Lotify-Container und Images..."
docker-compose down --rmi all -v || true

echo "Baue alles neu..."
docker-compose build
docker-compose up -d

echo "Lotify-Server (API:8080) und WebUI (Port 80) wurden komplett neu aufgesetzt." 