#!/usr/bin/env bash
set -euo pipefail

APP_URL="${APP_URL:-http://localhost:8000}"

has_command() {
  command -v "$1" >/dev/null 2>&1
}

compose() {
  if docker compose version >/dev/null 2>&1; then
    docker compose "$@"
    return
  fi

  if has_command docker-compose; then
    docker-compose "$@"
    return
  fi

  echo "Docker Compose is not available. Install Docker Desktop and run this script again."
  exit 1
}

install_docker_desktop_on_macos() {
  if has_command docker; then
    return
  fi

  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "Docker is not installed. Install Docker for your OS, then run this script again:"
    echo "https://docs.docker.com/installation/"
    exit 1
  fi

  if ! has_command brew; then
    echo "Docker is not installed, and Homebrew is not available to install it automatically."
    echo "Install Docker Desktop from https://docs.docker.com/installation/mac/ and run this script again."
    exit 1
  fi

  echo "Docker is not installed. Installing Docker Desktop with Homebrew..."
  if brew install --cask docker-desktop; then
    return
  fi

  echo "Could not install the docker-desktop cask. Trying the older docker cask name..."
  if brew install --cask docker; then
    return
  fi

  echo "Homebrew could not install Docker Desktop automatically."
  echo "Install it manually from https://docs.docker.com/installation/mac/ and run this script again."
  exit 1
}

start_docker_desktop() {
  if docker info >/dev/null 2>&1; then
    return
  fi

  if [[ "$(uname -s)" == "Darwin" ]]; then
    echo "Starting Docker Desktop..."
    open -a Docker || true
  fi

  echo "Waiting for Docker to become ready..."
  for _ in {1..90}; do
    if docker info >/dev/null 2>&1; then
      echo "Docker is ready."
      return
    fi
    sleep 2
  done

  echo "Docker did not become ready in time. Open Docker Desktop, finish any prompts, then run this script again."
  exit 1
}

wait_for_app() {
  echo "Waiting for the app at ${APP_URL}..."
  for _ in {1..60}; do
    if curl -fsS "${APP_URL}/healthz" >/dev/null 2>&1; then
      echo "Application is up: ${APP_URL}"
      return
    fi
    sleep 2
  done

  echo "Containers started, but the app did not answer yet. Showing status:"
  compose ps
  exit 1
}

install_docker_desktop_on_macos
start_docker_desktop

echo "Building and starting Postgres plus the application..."
compose up --build -d
wait_for_app

echo
echo "Useful commands:"
echo "  Stop:  docker compose down"
echo "  Logs:  docker compose logs -f app"
echo "  DB:    docker compose exec db psql -U crm_user -d customer_imports"
