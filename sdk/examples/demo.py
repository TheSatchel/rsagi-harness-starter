"""One Harness by default; optional two-client barrier regression. Protocol mock."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from rsagi_harness import CompetitionClient
from rsagi_harness.mock import MockArena,MockServer
from baseline import run

def main(teams=1):
    if teams not in (1,2):raise ValueError('Use one Harness, or two for the optional barrier check')
    arena=MockArena(teams=('alpha',) if teams==1 else ('alpha','beta'),rounds=12)
    with MockServer(arena) as server:
        with ThreadPoolExecutor(max_workers=teams) as pool:
            futures=[pool.submit(run,CompetitionClient(server.url,arena.tokens[team],expected_match_id=arena.match_id,allow_mock=True)) for team in arena.teams]
            for future in futures:future.result(timeout=20)
        assert arena.finished and arena.logical_tick==60 and len(arena.steps)==12
        summary={'mode':'protocol_mock','teams':teams,'barrier_rounds':len(arena.steps),'mock_ticks':arena.logical_tick,
          'synthetic_model_operations':arena.provider_calls,
          'model_proposed_policy_activations':sum(e['type']=='HARNESS_POLICY_ACTIVATED' for e in arena.audit),
          'native_minecraft':False,'real_model':False,'human_view_capture':False,'strict_certified':False}
    print(json.dumps(summary,indent=2));return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--teams',type=int,choices=(1,2),default=1)
    main(parser.parse_args().teams)
