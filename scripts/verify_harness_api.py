"""Exercise loopback HTTP contract; never start Minecraft or a real provider."""
from pathlib import Path
from datetime import datetime,timezone
import contextlib,hashlib,io,json,socket,sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]

def main():
    sys.path.insert(0,str(ROOT/'sdk/src'));sys.path.insert(0,str(ROOT/'sdk/examples'))
    spec=json.loads((ROOT/'api/openapi.json').read_text());refs=[]
    def walk(value):
        if isinstance(value,dict):
            if '$ref' in value:
                target=value['$ref'];assert target.startswith('#/')
                node=spec
                for name in target[2:].split('/'):node=node[name.replace('~1','/').replace('~0','~')]
                refs.append(target)
            for child in value.values():walk(child)
        elif isinstance(value,list):
            for child in value:walk(child)
    walk(spec)
    assert len(spec['paths'])==7 and spec['openapi']=='3.1.1'
    perception=json.loads((ROOT/'config/perception-policy.json').read_text())
    assert perception['debug_ui']['vanilla_f3_allowed'] is True
    assert perception['structured_world_state_allowed'] is False
    original_connect=socket.create_connection;outside=[]
    def loopback_only(address,*args,**kwargs):
        if address[0] not in ('127.0.0.1','localhost','::1'):
            outside.append('external-network-attempt');raise AssertionError('Only loopback allowed')
        return original_connect(address,*args,**kwargs)
    output=io.StringIO()
    with patch('socket.create_connection',side_effect=loopback_only),patch('http.client.HTTPSConnection') as provider,patch('subprocess.Popen') as process:
        provider.side_effect=process.side_effect=AssertionError('No live provider or subprocess in protocol verification')
        suite=unittest.defaultTestLoader.discover(str(ROOT/'sdk/tests'))
        result=unittest.TextTestRunner(stream=output,verbosity=2,buffer=True).run(suite)
        if not result.wasSuccessful():print(output.getvalue());raise SystemExit(1)
        from demo import main as demo
        with contextlib.redirect_stdout(io.StringIO()):demonstration=demo()
    assert not outside and provider.call_count==process.call_count==0
    assert demonstration['mock_ticks']==60 and demonstration['synthetic_model_operations']==10
    paths=[*sorted((ROOT/'sdk').rglob('*.py')),*sorted((ROOT/'api').glob('*.json')),ROOT/'api/build_spec.py',ROOT/'config/perception-policy.json',ROOT/'sdk/pyproject.toml',Path(__file__).resolve()]
    paths=[p for p in paths if '__pycache__' not in p.parts]
    report={'verifiedAt':datetime.now(timezone.utc).isoformat(),'status':'participant_protocol_mock_passed',
      'testsRun':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
      'openapiVersion':spec['openapi'],'endpointCount':7,'internalReferencesVerified':len(refs),
      'openapiExternalValidatorRun':False,'demo':demonstration,'nonLoopbackNetworkAttempts':0,'liveProviderCalls':0,'subprocessesStarted':0,
      'nativeMinecraftVerified':False,'humanViewCaptureVerified':False,'strictCertified':False,
      'sourceSha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
      'limits':['Protocol mock only, no native capture/execution or real inference',
        'Restricted model-proposed configuration changes, not arbitrary code hot updates or storage isolation certification',
        'No eight-team TPS or deterministic native replay certification',
        'OpenAPI internal references checked; no external full spec validator was available']}
    (ROOT/'reports').mkdir(exist_ok=True)
    (ROOT/'reports/harness-api-validation-20261019.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['status','testsRun','endpointCount','demo','liveProviderCalls','subprocessesStarted','strictCertified']},indent=2))

if __name__=='__main__':main()
