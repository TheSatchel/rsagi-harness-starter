"""Connect to an already running mod; --step is a manual control smoke test."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from rsagi_harness.mod_client import ModClient

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--step',action='store_true');args=parser.parse_args()
    client=ModClient.from_env();print(json.dumps(client.status(),ensure_ascii=False,indent=2))
    if args.step:
        client.attach()
        try:
            client.step({'vel':[0,0,.1]},'人工连接测试：小幅转动视角。')
            observation=client.capture();Path('rsagi-player-view.png').write_bytes(observation.png)
            print(json.dumps({'frame':observation.receipt,'manual_test':True,'model_called':False},ensure_ascii=False,indent=2))
        finally:client.detach()

if __name__=='__main__':main()
