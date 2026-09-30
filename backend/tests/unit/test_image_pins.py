"""Every external image is pinned by digest (backend plan V-B3): the compose services of all
profiles, the base images of both Dockerfiles (including their ARG defaults) and the helper
images the backup scripts run. Locally built ``smriti-*`` images are exempt.

The form is ``repo:tag@sha256:<digest>``: the tag stays for readability, the digest (the
multi-arch index from ``docker buildx imagetools inspect <repo:tag>``) is what is pulled."""

import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
PINNED = re.compile(r"^[a-z0-9][a-z0-9._/-]*(:[\w][\w.-]*)?@sha256:[0-9a-f]{64}$")
LOCAL_PREFIX = "smriti-"


def is_pinned(ref: str) -> bool:
    return bool(PINNED.match(ref))


def compose_images(text: str) -> dict[str, str]:
    services = yaml.safe_load(text)["services"]
    return {name: svc["image"] for name, svc in services.items() if "image" in svc}


def dockerfile_images(text: str) -> list[str]:
    """Base images of every ``FROM`` (with ``${ARG}`` resolved to its default) and every
    ``ARG *_IMAGE`` default. Earlier build stages and ``scratch`` are not images to pin."""
    args: dict[str, str] = {}
    stages: set[str] = set()
    images: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if m := re.match(r"ARG\s+(\w+)=(\S+)", line, re.I):
            args[m.group(1)] = m.group(2)
            if m.group(1).endswith("_IMAGE"):
                images.append(m.group(2))
        elif m := re.match(r"FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?", line, re.I):
            ref = re.sub(r"\$\{?(\w+)\}?", lambda a: args.get(a.group(1), a.group(0)), m.group(1))
            if ref not in stages and ref != "scratch":
                images.append(ref)
            if m.group(2):
                stages.add(m.group(2))
    return images


def script_images(text: str) -> list[str]:
    """Defaults of ``${SOMETHING_IMAGE:-repo:tag@sha256:...}`` in a shell script."""
    return re.findall(r"\$\{\w+_IMAGE:-([^}\s]+)\}", text)


def test_the_checker_tells_pinned_from_unpinned() -> None:
    digest = "sha256:" + "0" * 64
    assert is_pinned(f"redis:7.4-alpine@{digest}")
    assert is_pinned(f"prom/prometheus:v3.15.0@{digest}")
    assert is_pinned(f"python@{digest}")
    assert not is_pinned("redis:7.4-alpine")
    assert not is_pinned("redis:latest")
    assert not is_pinned(f"redis:7.4-alpine@{digest[:-1]}")
    dockerfile = (
        "ARG BASE=node:22@" + digest + "\nFROM ${BASE} AS build\nFROM nginx:1.28\n"
        "FROM build\nFROM scratch\n"
    )
    assert dockerfile_images(dockerfile) == [f"node:22@{digest}", "nginx:1.28"]


def test_every_compose_image_is_pinned_by_digest() -> None:
    images = compose_images((REPO / "docker-compose.yml").read_text(encoding="utf-8"))
    external = {s: ref for s, ref in images.items() if not ref.startswith(LOCAL_PREFIX)}
    # Every profile's infrastructure is covered (default, oidc, observability).
    assert {"postgres", "redis", "s3", "keycloak", "prometheus", "grafana"} <= set(external)
    assert {s: ref for s, ref in external.items() if not is_pinned(ref)} == {}


@pytest.mark.parametrize("dockerfile", ["backend/Dockerfile", "frontend/Dockerfile"])
def test_every_dockerfile_base_image_is_pinned_by_digest(dockerfile: str) -> None:
    images = dockerfile_images((REPO / dockerfile).read_text(encoding="utf-8"))
    assert images
    assert [ref for ref in images if not is_pinned(ref)] == []


def test_backup_helper_images_are_pinned_by_digest() -> None:
    scripts = sorted((REPO / "infra" / "backup").glob("*.sh"))
    images = [ref for s in scripts for ref in script_images(s.read_text(encoding="utf-8"))]
    assert images  # the S3 copy runs in a one-off rclone container
    assert [ref for ref in images if not is_pinned(ref)] == []
