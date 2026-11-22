# Dashboard NAS environment

Inspected on 2026-11-22 as the deployment user (UID/GID 1000).

| Check | Result |
| --- | --- |
| Checkout | `/srv/kindle-dashboard/project`, existing Git repository, initially empty with no commits |
| Ubuntu root | 39 GB total, 4.0 GB available, 90% used |
| the data volume | `/dev/sda1` mounted at `/srv`, ext4, read-write, writable by the deployment user, 168 GB available |
| Tools | Python 3.12.3, Node 26.13.1 via NVM, npm 11.20.0 |
| Docker | Available, engine 27.3.1, Compose 2.29.7, daemon reports `/var/lib/docker` |
| TCP 8765 | No listener at inspection |

Docker image layers and BuildKit cache would consume space from the system partition. Cold builds can use gigabytes across base layers, package installs, intermediate stages and cache. With 4 GB available on a shared NAS, Docker build and deployment are deferred. Local dependencies and artifacts use the data volume, with an initial budget below 1 GB. The existing NAS services and Docker configuration are outside this project's scope.
