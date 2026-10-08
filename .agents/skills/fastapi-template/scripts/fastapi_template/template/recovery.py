"""
已回收框架补丁的精确升级证明：只有旧模板、产品补丁、新实现三份摘要都一致时才接收。
其他本地变化仍由原三份比较报告冲突。接入配置和模块声明始终明确列为人工处理。
"""

import hashlib
from typing import Any

# 每项由本批只读补丁审查与框架验收确认，不匹配的内容不能沿用这个证明。
RECOVERED: dict[str, dict[str, Any]] = {
    "server/app/api/identity.py": {
        "base": "13348681d553c3236960bfbdb1d822002616c6033211bf4d2fc42e09e6583d6e",
        "manual_review": ["server/service/user_access/module.py"],
        "products": ["efc6000d2a1919f1a6f0a2dce3f8b9731c2b431588f9988adbef5e18c83f2d5d"],
        "replacement": "ab68fff7697ca5ceb9e83957b2e6de05463ccf87caeec0965cb5f922c82b651e",
    },
    "server/app/setup/worker.py": {
        "base": "026978b2b1e7f036d3211773786b18e3c057e5b6521eca1685f904f4690df5fc",
        "manual_review": [],
        "products": ["afd38c61d4a48e60e4b449ffd5ce6b37d597415d364b1300a2f5c71829cc8060"],
        "replacement": "d0555894062704661a6719ec694686a11c9492631b662887f30e852c027ffe58",
    },
    "server/shared/db/access.py": {
        "base": "cef27f892e472bf05bc5e838373a10974bb321b655e106a1c8b78a8e8ff066a0",
        "manual_review": ["server/.env"],
        "products": ["60f80beffe2cb4c00f16a377d32185b7b0f369539f06e2d300c64ba4012f0fee"],
        "replacement": "28a1efdcb477e22119a517db0440d8807fa92a72525740568dc1bd4e55210333",
    },
    "server/shared/files/gate.py": {
        "base": "1e55015d7c343750292d1c26c3c5041bf467adc9f9e56a19710334f3e7d857e7",
        "manual_review": [],
        "products": ["278a1ba41d035e513a4fdf43778d0af515a8fd339a6e8920957de3828b5910e5"],
        "replacement": "067aecf6f0f2eb4c944e76acefcb1cd760d46d9b13dbea1ad0fc3e78cf277296",
    },
    "server/shared/jobs/plan.py": {
        "base": "033f49eddcdd07294258d55a96b3d3e68580c9f9354343a113b80659004f51fe",
        "manual_review": [],
        "products": [
            "033f49eddcdd07294258d55a96b3d3e68580c9f9354343a113b80659004f51fe",
            "fc043c2f9c8846f508f9aadeb2b48469f9e9e93f654e6625a60e5fcc928c4cbb",
        ],
        "replacement": "0e21294533f93d87ddec38682e7f60341b07e1d6b461d1e4ba214477b91cb586",
    },
    "server/shared/jobs/schedule.py": {
        "base": "9444b4cd45ba7acb1c2b12630f79364513765a79812050eeb9ad3eb6b4e5a5ef",
        "manual_review": ["server/.env"],
        "products": [
            "104b3654e22b0ae24c2c8347ca1faa44546aea5ca110acaae0e5be95ca7ab52f",
            "12ceb10bff7a6b9c3cb4dd8781378f9635c08301d7727aa136e27f618f284a2f",
        ],
        "replacement": "a6be40fbdc2228b9768b68c529944dbc511f10febedb21c67421c74eb5e66293",
    },
    "server/shared/jobs/worker.py": {
        "base": "08de9c9878523559b2b4f009aebb2d89c3ff15f564bf7ed8adbb3fa6d54c4d95",
        "manual_review": ["server/.env"],
        "products": ["a460aed7c9613ea64aa9cda8a525fd094e15ae73a64061e55b14386d2fd1b4d6"],
        "replacement": "6cab45ea7aa802487b81d29a9531880df12cef9a0050c8141bb366b06cd99596",
    },
    "server/shared/modules/catalog.py": {
        "base": "1733b048996d2772dd16253c2708e319147d2b36a9202d2914b3708f9364be78",
        "manual_review": [],
        "products": [
            "0f22b305a8c98d92ce055f56f2038c25601329cd409c070cf8b7947c43091194",
            "1733b048996d2772dd16253c2708e319147d2b36a9202d2914b3708f9364be78",
        ],
        "replacement": "b0dffd5bb746d9cbf5aa0bfa314dce749ca0f8e2206deb4af698109920d84042",
    },
    "server/shared/modules/checks.py": {
        "base": "1770d5425a7e4eb08bf632c1995fd3ba37c345602c32f8ceaed74e4607770a11",
        "manual_review": [],
        "products": [
            "1770d5425a7e4eb08bf632c1995fd3ba37c345602c32f8ceaed74e4607770a11",
            "a3d18802e7a23d19c18f24d9a3fd3e8e7c7696a90b5754c89ae3d0bd009f74bd",
        ],
        "replacement": "03113b3515d4e4a4a3b917165b403e5d33e31a91bbcb892770069ed297bab980",
    },
    "server/shared/remote_calls/README.md": {
        "base": "540738fd5aaa385b2da72ac71c59110ba7c320cf2756e58505cd8f98cf7b7da4",
        "manual_review": [],
        "products": ["e54bed3631fa27f02473b20570749e8bd08905a8b395910d569054801367b099"],
        "replacement": "541cad52aa1287acc37d3c63d499de37cf4b7d3f293424581e881302121ea5cd",
    },
    "server/shared/remote_calls/gate.py": {
        "base": "580cf7d1e0294a89726b52b2aed1dd31bbd3509c919a1b1be5ae346f255bb2a6",
        "manual_review": [],
        "products": ["069c37fa0d4eb9c163b075d3cb96f08ffc58f17331e669a5b89d0d0ead05a420"],
        "replacement": "49550a1565017a4f7c607f0788dad8084dadbb5d830ad168381521bd9a02f7b1",
    },
    "server/shared/remote_calls/service.py": {
        "base": "301b5e5de768cb633a33804539bc9e769a8dae6b960acc5aca92b5e6293ca5b9",
        "manual_review": [],
        "products": ["0dce2864ea0e2993dea679684e724ce19d4ffeeebabc7966beea4b043205668b"],
        "replacement": "46123c7250d120e919729c007693af52a65d674a09ee5d7c7300a0aa905b354b",
    },
}


# 同时匹配三份原文，证明中不保存产品配置、凭据或业务数据。
def recovered_patch(
    name: str, old: bytes | None, local: bytes | None, new: bytes | None
) -> tuple[str, ...] | None:
    proof = RECOVERED.get(name)
    if proof is None or old is None or local is None or new is None:
        return None
    if (
        hashlib.sha256(old).hexdigest() != proof["base"]
        or hashlib.sha256(local).hexdigest() not in proof["products"]
        or hashlib.sha256(new).hexdigest() != proof["replacement"]
    ):
        return None
    return tuple(proof["manual_review"])
