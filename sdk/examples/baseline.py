"""Replace scheduling hooks to build your harness. Store no semantic world notes."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from rsagi_harness import CompetitionClient,run_harness

def run(client):
    run_harness(client)

if __name__=='__main__':run(CompetitionClient.from_env())
