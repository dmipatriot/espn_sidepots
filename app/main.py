import argparse, yaml
from pathlib import Path

def load_config() -> dict:
    with open(Path(__file__).parents[1] / "config" / "league.yaml", "r") as f:
        return yaml.safe_load(f)

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["pir","efficiency","survivor","all"], default="all")
    p.add_argument("--weeks", default="auto", help="auto | N | A-B | A,B,C")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()

def main():
    cfg = load_config()
    args = parse_args()
    print("Stub OK. Handing off to Codex via PRs.")

if __name__ == "__main__":
    main()
