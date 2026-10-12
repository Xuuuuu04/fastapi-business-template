"""
真实迁移源码验证共同祖先、独立对象、跨分支依赖和未知SQL，合并不重写旧脚本。
"""

from pathlib import Path

import pytest
from fastapi_project.development.evidence import system_fingerprint
from fastapi_project.development.migration_graph import read_graph
from fastapi_project.development.migration_merge import migration_plan, write_merge


# 合成脚本只写临时项目，版本声明与DDL都来自真实Python源码。
def revision(project: Path, identity: str, parent, body: str, *, depends=None) -> Path:
    folder = project / "server/migrations/versions"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (identity + ".py")
    path.write_text(
        "import sqlalchemy as sa\nfrom alembic import op\n"
        + f"revision = {identity!r}\ndown_revision = {parent!r}\ndepends_on = {depends!r}\n"
        + "def upgrade():\n"
        + "".join("    " + line + "\n" for line in body.splitlines())
        + "def downgrade():\n    pass\n"
    )
    return path


# 独立表生成唯一新合并头，旧脚本全部保持字节不变。
def test_independent_heads_generate_incremental_merge(tmp_path: Path) -> None:
    revision(tmp_path, "base", None, "pass")
    revision(tmp_path, "left", "base", 'op.create_table("sample_a", sa.Column("id", sa.Integer()))')
    revision(
        tmp_path, "right", "base", 'op.create_table("sample_b", sa.Column("id", sa.Integer()))'
    )
    before = {item.path: item.path.read_bytes() for item in read_graph(tmp_path).values()}
    plan = migration_plan(tmp_path)
    assert plan["mergeable"] and plan["anchor"] == "base"
    target = write_merge(tmp_path, plan)
    assert target and target.is_file()
    assert all(path.read_bytes() == content for path, content in before.items())
    assert len(migration_plan(tmp_path)["heads"]) == 1


# 同列竞争和新列索引不是独立操作，同表不同列仍可连接。
@pytest.mark.parametrize(
    "other,mergeable",
    [
        ('op.add_column("sample", sa.Column("first", sa.String()))', False),
        ('op.add_column("sample", sa.Column("second", sa.String()))', True),
        ('op.create_index("ix_first", "sample", ["first"])', False),
    ],
)
def test_column_and_index_conflicts(tmp_path: Path, other: str, mergeable: bool) -> None:
    revision(tmp_path, "base", None, "pass")
    revision(tmp_path, "left", "base", 'op.add_column("sample", sa.Column("first", sa.Integer()))')
    revision(tmp_path, "right", "base", other)
    plan = migration_plan(tmp_path)
    assert plan["mergeable"] is mergeable
    if not mergeable:
        assert plan["conflicts"]
        with pytest.raises(ValueError, match="冲突"):
            write_merge(tmp_path, plan)


# 外键依赖另一头新表时必须声明依赖，不能靠版本号排序碰巧成功。
def test_foreign_key_requires_dependency(tmp_path: Path) -> None:
    revision(tmp_path, "base", None, "pass")
    revision(tmp_path, "left", "base", 'op.create_table("sample_a", sa.Column("id", sa.Integer()))')
    body = (
        'op.create_table("sample_b", '
        'sa.Column("parent", sa.Integer(), sa.ForeignKey("sample_a.id")))'
    )
    revision(tmp_path, "right", "base", body)
    assert migration_plan(tmp_path)["conflicts"]
    revision(tmp_path, "right", "base", body, depends="left")
    assert migration_plan(tmp_path)["mergeable"]


# 动态分支、任意SQL和未知函数不能被已识别DDL掩盖。
@pytest.mark.parametrize(
    "body",
    [
        'op.execute("ALTER TABLE sample ADD x INTEGER")',
        "helper.apply_changes()",
        'if check_flag():\n    op.drop_table("sample")',
    ],
)
def test_unknown_ddl_refuses_auto_merge(tmp_path: Path, body: str) -> None:
    revision(tmp_path, "base", None, "pass")
    revision(tmp_path, "left", "base", "pass")
    revision(tmp_path, "right", "base", body)
    plan = migration_plan(tmp_path)
    assert plan["unknown"] and not plan["mergeable"]


# 足迹不变但类型改变，也必须重新分析，预览不授权随后改动的新代码。
def test_preview_rechecks_source_bytes(tmp_path: Path) -> None:
    revision(tmp_path, "base", None, "pass")
    path = revision(
        tmp_path, "left", "base", 'op.create_table("sample_a", sa.Column("id", sa.Integer()))'
    )
    revision(
        tmp_path, "right", "base", 'op.create_table("sample_b", sa.Column("id", sa.Integer()))'
    )
    plan = migration_plan(tmp_path)
    path.write_text(path.read_text().replace("sa.Integer()", "sa.String()"))
    with pytest.raises(ValueError, match="变化"):
        write_merge(tmp_path, plan)


# 测试引擎源码变化会使整轮证据过期，不仅检查业务包自己的源文件。
@pytest.mark.parametrize(
    "name", ["resources.py", "postgres_setup.py", "environment.py", "check_profile.py"]
)
def test_test_engine_files_participate_in_current_source(tmp_path: Path, name: str) -> None:
    path = tmp_path / "server/tests" / name
    path.parent.mkdir(parents=True)
    path.write_text("# 合成旧测试引擎\n")
    before = system_fingerprint(tmp_path)
    path.write_text("# 合成修改后的测试引擎\n")
    assert system_fingerprint(tmp_path) != before
