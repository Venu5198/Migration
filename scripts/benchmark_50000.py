"""Generated-data benchmark; no client data is read or written."""

import os
import tempfile
import time
import tracemalloc
from pathlib import Path

from openpyxl import Workbook

from app.services.profiling import profile_workbook

ROWS = 50_000


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "benchmark.xlsx"
        workbook = Workbook(write_only=True)
        sheet = workbook.create_sheet("Assignments")
        sheet.append(["Employee ID", "Assignment ID", "Country"])
        for number in range(ROWS):
            sheet.append([f"E{number:06d}", f"A{number:06d}", "India"])
        workbook.save(path)
        tracemalloc.start()
        started = time.perf_counter()
        result = profile_workbook(path)
        duration = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        print(
            {
                "rows": ROWS,
                "profile_seconds": round(duration, 3),
                "peak_python_mib": round(peak / 1024 / 1024, 2),
                "profiled_rows": result["sheets"][0]["populated_rows"],
                "python": os.sys.version.split()[0],
            }
        )


if __name__ == "__main__":
    main()
