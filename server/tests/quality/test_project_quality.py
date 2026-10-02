"""
对真实项目运行全部质量检查：代码写法、命名、async 阻塞调用、README、业务文档。
任何一项有问题都会列出文件、行号、规则和整理建议。
"""

from app.setup.catalog import MODULES
from shared.modules.catalog import Catalog
from tools.quality.blocking import check_blocking
from tools.quality.docs import check_business_docs
from tools.quality.files import check_files
from tools.quality.naming import check_naming
from tools.quality.readmes import check_readmes
from tools.quality.report import Problem, unused_allowed, without_allowed


# 把检查问题整理成便于阅读的失败说明。
def listed(problems: list[Problem]) -> str:
    return "\n".join(problem.text() for problem in problems)


# 代码写法：文件说明、函数说明、长度、嵌套、待办标记、连续注释。
def test_code_style() -> None:
    problems = without_allowed(check_files())
    assert problems == [], listed(problems)


# 命名：小写下划线、含义清楚、模块名两个词、步骤名“动词_对象”。
def test_naming() -> None:
    problems = without_allowed(check_naming())
    assert problems == [], listed(problems)


# async 函数中没有阻塞调用。
def test_no_blocking_calls() -> None:
    problems = without_allowed(check_blocking())
    assert problems == [], listed(problems)


# 每个代码目录都有 README，模块 README 写全固定小节和公开操作。
def test_readmes() -> None:
    catalog = Catalog(MODULES)
    names = {
        name: [item.name for item in module.provides] for name, module in catalog.modules.items()
    }
    problems = without_allowed(check_readmes(contracts=names))
    assert problems == [], listed(problems)


# 业务文档齐全、没有超长、规则编号能找到、生成文档没有过期。
def test_business_docs() -> None:
    problems = without_allowed(check_business_docs(Catalog(MODULES)))
    assert problems == [], listed(problems)


# 登记的例外都还有用，不再需要的例外要删除。
def test_no_stale_exceptions() -> None:
    everything = check_files() + check_naming() + check_blocking()
    assert unused_allowed(everything) == []
