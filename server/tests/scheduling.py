import os

import pytest

LONG_TESTS = (
    "test_real_two_package_merge_and_dual_database_evidence",
    "test_new_project_path",
    "test_200_members_wait_join_and_frozen_sources",
    "test_three_package_skeleton_to_real_with_error_position",
    "test_real_task_commands_use_fresh_database_evidence",
    "test_real_v2_product_upgrade_and_incremental_databases",
    "test_new_operation_and_pipeline_check_without_manual_edits",
)


def schedule(items: list[pytest.Item]) -> None:
    if int(os.environ.get("APP_TEST_WORKERS", "0")) < 1:
        return
    priority = {name: index for index, name in enumerate(LONG_TESTS)}
    long = sorted(
        (item for item in items if item.name in priority), key=lambda item: priority[item.name]
    )
    short = [item for item in items if item.name not in priority]
    ordered = []
    for item in long:
        ordered.append(item)
        if short:
            ordered.append(short.pop(0))
    items[:] = [*ordered, *short]
