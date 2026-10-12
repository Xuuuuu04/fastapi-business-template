"""
把实际源码的违规导入显示为红色依赖，未登记的动态依赖另列问题，不猜调用关系。
"""

from pathlib import Path

from shared.modules.validation.imports import check_imports, imported


# 现有静态检查提供问题出处，源码导入提供明确目标，不从文字说明猜包名。
def dependency_issues(project: Path) -> tuple[list[dict], list[dict]]:
    root = project / "server"
    issues, edges = [], []
    for problem in check_imports(root, strict=True):
        issues.append(
            {
                "source": "server/" + problem.path,
                "line": problem.line,
                "rule": problem.rule,
                "message": problem.message,
            }
        )
        parts = Path(problem.path).parts
        path = root / problem.path
        if len(parts) < 2 or parts[0] != "service" or not path.is_file():
            continue
        for name, line in imported(path):
            targets = name.split(".")
            if (
                line == problem.line
                and len(targets) >= 2
                and targets[0] == "service"
                and targets[1] != parts[1]
            ):
                edges.append(
                    {
                        "source": parts[1],
                        "target": targets[1],
                        "kind": "invalid",
                        "count": 1,
                        "reason": problem.message,
                        "location": "server/" + problem.path + f":{line}",
                    }
                )
    return issues, edges
