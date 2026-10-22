import csv
from io import StringIO


def safe_csv(value: object) -> str:
    text = "" if value is None else str(value)
    stripped = text.lstrip(" \t\r\n")
    if stripped.startswith(("=", "+", "-", "@", "\t", "\r", "|", "%")):
        return f"'{text}"
    return text


def preview_csv(result: dict) -> str:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["sheet", "row", "target_entity", "field", "value"])
    for record in result.get("records", []):
        for field, value in record.get("proposed", {}).items():
            writer.writerow(
                [record["sheet"], record["row"], record["target_entity"], field, safe_csv(value)]
            )
    return output.getvalue()
