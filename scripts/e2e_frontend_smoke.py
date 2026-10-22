import io
import json
import time
import urllib.request

import openpyxl


def main():
    print("Testing full lifecycle through Nginx frontend proxy at http://localhost:3000...")

    # 1. Generate synthetic workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Employees"
    ws.append(["emp_id", "full_name", "country", "salary"])
    ws.append(["E001", "Alice Smith", "US", 95000])
    ws.append(["E002", "Bob Jones", "UK", 85000])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    content = buf.read()

    # 2. Upload via multipart/form-data
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = io.BytesIO()
    body.write(f"--{boundary}\r\n".encode())
    body.write(b'Content-Disposition: form-data; name="file"; filename="e2e_smoke.xlsx"\r\n')
    body.write(
        b"Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n"
    )
    body.write(content)
    body.write(f"\r\n--{boundary}--\r\n".encode())
    payload = body.getvalue()

    req = urllib.request.Request("http://localhost:3000/api/v1/sources/upload", data=payload)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    res = json.loads(urllib.request.urlopen(req).read().decode())
    source_id = res["source_id"]
    print("1. Uploaded workbook through frontend proxy:", source_id)
    assert len(res["sheets"]) == 1
    assert res["sheets"][0]["name"] == "Employees"

    # 3. Trigger profiling job
    req = urllib.request.Request(
        f"http://localhost:3000/api/v1/sources/{source_id}/profile",
        data=b"",
        method="POST",
    )
    job = json.loads(urllib.request.urlopen(req).read().decode())
    job_id = job["job_id"]
    print("2. Triggered profiling job:", job_id)

    # Poll profiling job
    for _ in range(20):
        url = f"http://localhost:3000/api/v1/jobs/{job_id}"
        job_res = json.loads(urllib.request.urlopen(url).read().decode())
        if job_res["status"] in ("COMPLETED", "COMPLETED_WITH_ERRORS"):
            print("3. Profiling finished with status:", job_res["status"])
            assert job_res["result"]["sheets"][0]["populated_rows"] == 2
            break
        time.sleep(1)

    # 4. Create mapping
    map_data = json.dumps(
        {
            "source_id": source_id,
            "source_entity": "Employee",
            "source_sheet": "Employees",
            "source_field": "emp_id",
            "target_entity": "Worker",
            "target_field": "worker_id",
            "mapping_type": "direct",
        }
    ).encode()
    req = urllib.request.Request(
        "http://localhost:3000/api/v1/mappings",
        data=map_data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    mapping = json.loads(urllib.request.urlopen(req).read().decode())
    mapping_id = mapping["mapping_id"]
    print("4. Created field mapping:", mapping_id, "status:", mapping["status"])
    assert mapping["status"] == "proposed"

    # 5. Approve mapping
    req = urllib.request.Request(
        f"http://localhost:3000/api/v1/mappings/{mapping_id}/approve",
        data=b"",
        method="POST",
    )
    approved = json.loads(urllib.request.urlopen(req).read().decode())
    print(
        "5. Approved field mapping:",
        mapping_id,
        "status:",
        approved["status"],
        "version:",
        approved["version"],
    )
    assert approved["status"] == "approved"
    assert approved["version"] == 2

    # 6. Queue preview dry run
    prev_data = json.dumps({"source_id": source_id, "mapping_id": mapping_id}).encode()
    req = urllib.request.Request(
        "http://localhost:3000/api/v1/migrations/preview",
        data=prev_data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    prev_job = json.loads(urllib.request.urlopen(req).read().decode())
    prev_job_id = prev_job["job_id"]
    print("6. Queued preview dry-run job:", prev_job_id)

    # Poll preview job
    for _ in range(20):
        url = f"http://localhost:3000/api/v1/jobs/{prev_job_id}"
        pj_res = json.loads(urllib.request.urlopen(url).read().decode())
        if pj_res["status"] in ("COMPLETED", "COMPLETED_WITH_ERRORS"):
            eligible = pj_res["result"].get(
                "eligible_records", pj_res["result"].get("migrated_rows")
            )
            print("7. Preview finished with status:", pj_res["status"], "eligible:", eligible)
            assert eligible == 2
            assert (
                pj_res["result"]["equus_writes"] is False
                or pj_res["result"]["equus_writes"] == "disabled"
            )
            break
        time.sleep(1)

    # 7. Export CSV through proxy
    csv_url = f"http://localhost:3000/api/v1/reports/{prev_job_id}/export"
    csv_bytes = urllib.request.urlopen(csv_url).read()
    csv_text = csv_bytes.decode()
    print("8. Exported safe CSV through proxy (length:", len(csv_text), "bytes)")
    assert "worker_id" in csv_text

    # 8. Reconciliation through proxy
    recon_url = f"http://localhost:3000/api/v1/reports/{prev_job_id}/reconciliation"
    recon = json.loads(urllib.request.urlopen(recon_url).read().decode())
    print(
        "9. Reconciliation result - source:",
        recon.get("source_records"),
        "accepted:",
        recon.get("accepted_records"),
    )
    assert recon["source_records"] == 2
    assert recon["accepted_records"] == 2

    print("\nALL 9 END-TO-END MIGRATION LIFECYCLE PHASES VERIFIED SUCCESSFULLY VIA FRONTEND PROXY!")


if __name__ == "__main__":
    main()
