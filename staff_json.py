from docx import Document
import json

DOCX_FILE = "Nominal Roll 2026 updatedg.docx"

doc = Document(DOCX_FILE)
table = doc.tables[0]

headers = [cell.text.strip().lower().replace(" ", "_") for cell in table.rows[0].cells]

records = []

def clean_record(record):
    return {
        "fullName": record.get("fullname", ""),
        "type": record.get("type", "").lower(),
        "directorate": record.get("directorate", "").upper(),
        "service_number": record.get("service_number", "").strip(),
        "rankOrGrade": record.get("rankorgrade", ""),
        "designation": record.get("designation", ""),
        "roles": [],
        "email": record.get("email", "").replace(" ", ""),
        "gender": record.get("gender", ""),
        "batch": record.get("batch", ""),
        "status": record.get("status", "").lower(),
        "actions": [],
        "isActive": True
    }

for row in table.rows[1:]:
    values = [cell.text.strip() for cell in row.cells]
    raw_record = dict(zip(headers, values))

    record = clean_record(raw_record)

    if record["service_number"]:  # skip empty rows
        records.append(record)

# === SAVE JSON ===
with open("staff_import.json", "w") as f:
    json.dump(records, f, indent=4)

print(f"{len(records)} records converted to JSON.")