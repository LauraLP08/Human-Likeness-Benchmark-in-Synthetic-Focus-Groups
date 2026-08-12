"""
Validate every JSON file in agents/twin2k500/ against the local Appendix B mirror.

Exit code 0 = all valid. Exit code 1 = at least one file failed.
"""
import json
import sys
from pathlib import Path

from twin2k500_schema_mirror import AgentPayload

ROOT = Path(__file__).resolve().parent.parent
AGENT_DIR = ROOT / "agents" / "twin2k500"


def main() -> int:
    files = sorted(p for p in AGENT_DIR.glob("twin_*.json"))
    print(f"[twin2k500_validate] Validating {len(files)} agent files ...")

    failures: list[tuple[str, str]] = []
    for f in files:
        try:
            data = json.loads(f.read_text())
            AgentPayload.model_validate(data)
        except Exception as exc:                    # noqa: BLE001
            failures.append((f.name, repr(exc)))

    if failures:
        print(f"[twin2k500_validate] FAILED — {len(failures)} files invalid:")
        for name, err in failures[:20]:
            print(f"  {name}: {err}")
        if len(failures) > 20:
            print(f"  ... and {len(failures) - 20} more")
        return 1

    print("[twin2k500_validate] OK — all files conform to schema.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
