import argparse
import os
import shlex
import subprocess
import sys

from dotenv import dotenv_values

READY = (
    "for _ in $(seq 60); do "
    "curl -fsS http://127.0.0.1:8000/health/ready && exit 0; sleep 2; "
    "done; exit 1"
)


def target() -> tuple[str, str]:
    values = {**dotenv_values(".env"), **os.environ}
    host, folder = values.get("DEPLOY_HOST"), values.get("DEPLOY_DIR")
    if not host or not folder:
        sys.exit("server/.env 里要写 DEPLOY_HOST（ssh 能连上的主机）和 DEPLOY_DIR（服务器上的仓库目录）")
    return host, folder


def update(folder: str) -> str:
    return (
        f"cd {shlex.quote(folder)} && git pull --ff-only && cd server && "
        "APP_CODE_VERSION=$(git rev-parse --short HEAD) "
        "docker compose -f deploy/compose.yaml --env-file .env up -d --build"
    )


def step(title: str, command: list[str]) -> None:
    print(f"== {title}", flush=True)
    if subprocess.run(command).returncode != 0:
        sys.exit(f"{title}失败，已停止")


def main() -> None:
    argparse.ArgumentParser(description="推送当前分支，服务器拉取后重建并重启，等到服务就绪").parse_args()
    host, folder = target()
    step("推送代码", ["git", "push"])
    step("服务器拉取并重启", ["ssh", host, update(folder)])
    step("等服务就绪", ["ssh", host, READY])
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    print(f"已上线 {commit.stdout.strip()}")


if __name__ == "__main__":
    main()
