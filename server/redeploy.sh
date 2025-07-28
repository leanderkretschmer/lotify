#!/bin/bash
set -e

CONTAINER_NAME=lotify-server
IMAGE_NAME=lotify-server

if [ $(docker ps -aq -f name=$CONTAINER_NAME) ]; then
    docker stop $CONTAINER_NAME || true
    docker rm $CONTAINER_NAME || true
fi

docker rmi $IMAGE_NAME || true

echo "Baue Docker-Image..."
docker build -t $IMAGE_NAME .

echo "Starte Container..."
docker run -d --name $CONTAINER_NAME -p 8080:8080 $IMAGE_NAME

echo "Lotify-Server wurde komplett neu aufgesetzt." 