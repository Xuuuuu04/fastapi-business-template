"""
生成 Mermaid 图时共用的文字处理：转义标签、生成节点编号、定义节点样式。
标签中的输入文本一律转义，不把业务数据当成图语言执行。
"""

import re

MAX_LABEL = 80

STYLES = [
    "    classDef compute fill:#eef6ff,stroke:#4a78b5",
    "    classDef read fill:#f2fbf2,stroke:#4a9a4a",
    "    classDef save fill:#fff4e5,stroke:#c07a1a",
    "    classDef call fill:#f5f0ff,stroke:#7a5ab5",
    "    classDef model fill:#ffeef4,stroke:#b54a7a",
    "    classDef ok fill:#eaf7ea,stroke:#3c8c3c",
    "    classDef failed fill:#fdeaea,stroke:#c03c3c,stroke-width:2px",
    "    classDef skipped fill:#f2f2f2,stroke:#999,stroke-dasharray:4 3,color:#777",
    "    classDef running fill:#fff8d6,stroke:#b59a1a",
]


# 转义节点标签中的特殊字符，并限制长度。
def label(text: str, *, limit: int | None = MAX_LABEL) -> str:
    clean = " ".join(str(text).split())
    if limit is not None and len(clean) > limit:
        clean = clean[:limit] + "……"
    for old, new in (("&", "&amp;"), ('"', "&quot;"), ("<", "&lt;"), (">", "&gt;"), ("`", "'")):
        clean = clean.replace(old, new)
    return clean


# 把任意名称转成合法的节点编号。
def node_id(prefix: str, text: str) -> str:
    return prefix + "_" + re.sub(r"[^A-Za-z0-9_]", "_", text)
