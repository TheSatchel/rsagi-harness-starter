"""Two real HTTP SDK clients against a synthetic local protocol mock."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from rsagi_harness import CompetitionClient
from rsagi_harness.mock import MockArena,MockServer
from baseline import run

def main():
    arena=MockArena(rounds=12)
    with MockServer(arena) as server:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(run,CompetitionClient(server.url,arena.tokens[team],allow_mock=True)) for team in arena.teams]
            for future in futures:future.result(timeout=20)
        assert arena.finished and arena.logical_tick==60 and len(arena.steps)==12
        summary={'mode':'protocol_mock','teams':2,'barrier_rounds':len(arena.steps),'mock_ticks':arena.logical_tick,
          'synthetic_model_operations':arena.provider_calls,
          'model_proposed_policy_activations':sum(e['type']=='HARNESS_POLICY_ACTIVATED' for e in arena.audit),
          'native_minecraft':False,'real_model':False,'human_view_capture':False,'strict_certified':False}
    print(json.dumps(summary,indent=2));return summary

if __name__=='__main__':main()
