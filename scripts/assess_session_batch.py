import argparse
import os
import glob

from scripts.assess_session import assess_session
from assessment.report import generate_report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--logs-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    
    os.makedirs(args.output_dir, exist_ok=True)
    
    run_dirs = glob.glob(os.path.join(args.logs_dir, "*"))
    
    summary_lines = ["run_id,recommendation,failed_tracks"]
    
    for rdir in run_dirs:
        if not os.path.isdir(rdir): continue
        run_id = os.path.basename(rdir)
        try:
            res = assess_session(rdir)
            out_dir = os.path.join(args.output_dir, run_id)
            generate_report(res, out_dir)
            rec = res.recommendation.recommendation if res.recommendation else "UNKNOWN"
            failed = "|".join(res.recommendation.failed_tracks) if res.recommendation else ""
            summary_lines.append(f"{run_id},{rec},{failed}")
            print(f"Processed {run_id}: {rec}")
        except Exception as e:
            print(f"Failed to assess {run_id}: {str(e)}")
            summary_lines.append(f"{run_id},ERROR,{str(e)}")
            
    with open(os.path.join(args.output_dir, "batch_summary.csv"), "w", encoding="utf-8") as f:
        f.write("\n".join(summary_lines))
        
    with open(os.path.join(args.output_dir, "batch_summary.md"), "w", encoding="utf-8") as f:
        f.write("# Batch Assessment Summary\n\n")
        f.write("run_id | recommendation | failed_tracks\n")
        f.write("--- | --- | ---\n")
        for line in summary_lines[1:]:
            parts = line.split(",")
            f.write(f"{parts[0]} | {parts[1]} | {parts[2]}\n")

if __name__ == "__main__":
    main()
