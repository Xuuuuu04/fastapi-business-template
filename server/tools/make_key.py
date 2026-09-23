"""
生成一把服务密钥：打印密钥原文（只显示这一次）和可以放进 APP_API_KEYS 的配置。
用法：
  uv run python -m tools.make_key --name reporting --org-id north --permissions product_catalog.read
"""

import argparse
import json

from shared.access.keys import hash_key, new_key


# 生成密钥并打印配置。
def main() -> None:
    parser = argparse.ArgumentParser(description="生成服务密钥")
    parser.add_argument("--name", required=True, help="密钥名称，例如调用方系统的名字")
    parser.add_argument(
        "--permissions", nargs="+", required=True, help="权限，例如 product_catalog.read"
    )
    parser.add_argument("--org-id", default="", help="可访问的组织代码；* 只供全组织管理员使用")
    args = parser.parse_args()
    key = new_key()
    config = {
        "name": args.name,
        "key_sha256": hash_key(key),
        "permissions": args.permissions,
        "org_id": args.org_id,
    }
    print("密钥原文（只显示这一次，请交给调用方保管）：")
    print(key)
    print("\n放进 APP_API_KEYS 列表中的配置：")
    print(json.dumps(config, ensure_ascii=False))


if __name__ == "__main__":
    main()
