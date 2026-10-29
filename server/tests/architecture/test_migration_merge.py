from pathlib import Path

import pytest
from fastapi_project.development.evidence import system_fingerprint
from fastapi_project.development.migration_graph import read_graph
from fastapi_project.development.migration_merge import migration_plan, write_merge


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
