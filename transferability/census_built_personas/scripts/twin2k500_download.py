"""
Download Twin-2K-500 from Hugging Face into a local cache.
Idempotent: re-running will use the cached files.
"""
from pathlib import Path
from datasets import load_dataset

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "twin2k500" / "raw"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    print(f"[twin2k500_download] Cache directory: {CACHE_DIR}")

    print("[twin2k500_download] Loading 'full_persona' subset ...")
    full = load_dataset(
        "LLM-Digital-Twin/Twin-2K-500",
        "full_persona",
        cache_dir=str(CACHE_DIR),
    )
    print(f"  full_persona['data']: {len(full['data'])} rows")

    print("[twin2k500_download] Loading 'wave_split' subset ...")
    wave = load_dataset(
        "LLM-Digital-Twin/Twin-2K-500",
        "wave_split",
        cache_dir=str(CACHE_DIR),
    )
    print(f"  wave_split['data']: {len(wave['data'])} rows")

    print("[twin2k500_download] Done.")


if __name__ == "__main__":
    main()
