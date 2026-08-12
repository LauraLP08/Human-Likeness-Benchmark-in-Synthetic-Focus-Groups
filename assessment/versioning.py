import sys
import platform
import datetime
import os
import hashlib
from typing import Dict, Any

def get_file_hash(filepath: str) -> str:
    if not os.path.exists(filepath):
        return None
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

def generate_manifest(session_dir: str, run_id: str, topic: str) -> Dict[str, Any]:
    manifest = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "session_dir": session_dir,
        "run_id": run_id,
        "topic": topic,
        "python_version": sys.version,
        "platform": platform.platform(),
        "assessment_framework_version": "1.0.1",
        "dictionary_versions": {
            "overvalidation_phrases": "1.0",
            "topic_grocery": "1.0",
            "concreteness_proxy": "1.0"
        },
        "packages": {},
        "file_hashes": {}
    }
    
    for fname in ["transcript.json", "moderator_log.json", "run_metadata.json", "session_state_final.json"]:
        h = get_file_hash(os.path.join(session_dir, fname))
        if h:
            manifest["file_hashes"][fname] = h
            
    for pkg in ["numpy", "scipy", "sklearn", "pandas", "networkx", "spacy"]:
        try:
            mod = __import__(pkg)
            manifest["packages"][pkg] = getattr(mod, "__version__", "unknown")
        except ImportError:
            pass
            
    return manifest
