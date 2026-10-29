from shared.public import Module, contract
from tests.framework.sample_modules import CalcInput, CalcResult, NoteStore, calc_flow

records = Module(
    "sample_records",
    "记录样例",
    "1",
    store=NoteStore,
    provides={
        contract(
            f"sample_records.{name}",
            name,
            input=CalcInput,
            output=CalcResult,
            access="sample_records.use",
            effect="command",
        ): calc_flow
        for name in (
            "create_record",
            "get_record",
            "list_records",
            "delete_record",
            "clean_records",
        )
    },
    kind="capability",
)
accounts = Module(
    "sample_accounts",
    "身份样例",
    "1",
    store=NoteStore,
    provides={
        contract(
            "sample_accounts.login",
            "身份样例",
            input=CalcInput,
            output=CalcResult,
            access="sample_accounts.use",
            effect="command",
        ): calc_flow
    },
    kind="capability",
)
MODULES = [accounts, records]
