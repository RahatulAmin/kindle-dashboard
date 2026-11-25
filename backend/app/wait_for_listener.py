"""Fail the service preflight until its configured IPv4 address can be bound."""

import socket

from app.core.config import Settings


def main():
    settings = Settings()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind((settings.app_host, settings.app_port))
        except OSError as error:
            raise SystemExit(f"Waiting for dashboard listener address: {error}") from error


if __name__ == "__main__":
    main()
