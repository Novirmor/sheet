from dataclasses import dataclass

__all__ = ["SHEET_API_MEMBERS", "api_help_html", "api_member", "api_member_names"]


@dataclass(frozen=True, slots=True)
class ApiMember:
    name: str
    signature: str
    description: str


SHEET_API_MEMBERS = (
    ApiMember("get", 'sheet.get("A1")', "Calculated cell value."),
    ApiMember("raw", 'sheet.raw("A1")', "Original cell input."),
    ApiMember("set", 'sheet.set("A1", value)', "Set one cell."),
    ApiMember("write", 'sheet.write("A1", rows)', "Write a rectangular list."),
    ApiMember("range", 'sheet.range("A1:C3")', "Read a rectangular range."),
    ApiMember("clear", 'sheet.clear("A1:C3")', "Clear a range."),
    ApiMember("dataframe", 'sheet.dataframe("A1:C3", headers=True)', "Read a range into Pandas."),
    ApiMember(
        "write_dataframe",
        'sheet.write_dataframe("A1", frame, include_header=True, include_index=False)',
        "Write a Pandas DataFrame.",
    ),
    ApiMember("rows", "sheet.rows", "Number of sheet rows."),
    ApiMember("columns", "sheet.columns", "Number of sheet columns."),
)


def api_member_names() -> list[str]:
    return [member.name for member in SHEET_API_MEMBERS]


def api_member(name: str) -> ApiMember | None:
    return next((member for member in SHEET_API_MEMBERS if member.name == name), None)


def api_help_html() -> str:
    entries = "".join(
        f"<p><code>{member.signature}</code><br>{member.description}</p>"
        for member in SHEET_API_MEMBERS
    )
    return f"""
<h3>Sheet API</h3>
{entries}
 <p><code>pd</code> and <code>px</code> provide Pandas and Plotly Express.
Use <code>display(value)</code> for bounded scalar and DataFrame previews. Displayed Plotly figures
open in your browser; <code>fig.show()</code> remains available.</p>
<p>Run Script, Run Selection, and Console commands share one session. Each command sees a fresh
sheet snapshot, while Python variables persist until Restart Session. Fresh Run is isolated.
<code>input()</code> is not supported.</p>
<hr>
<p><b>Security:</b> scripts run in a separate local Python process. They can access your machine
with your user permissions.</p>
"""
