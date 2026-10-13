"""
每种非快速检查都核对规则保护与交付身份，局部测试不能绕过已确认预期或模拟标记。
"""

from fastapi_check.quality.docs import check_development_rules
from fastapi_check.quality.rules import PROJECT

from app.setup.application import application_modules
from shared.modules.catalog import Catalog


# 离线读取声明和原件，不创建服务或读取运行数据库。
def check_development(delivery: bool) -> list[str]:
    problems = check_development_rules(Catalog(application_modules()), PROJECT, delivery=delivery)
    texts = [problem.text() for problem in problems]
    for text in texts:
        print(text, flush=True)
    return texts
