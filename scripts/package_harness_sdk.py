"""Build a participant-only source ZIP after local protocol verification."""
from pathlib import Path
import hashlib,json,re,zipfile
ROOT=Path(__file__).resolve().parents[1]
NAME='rsagi-harness-starter-v0.1.0'
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
    report=json.loads((ROOT/'reports/harness-api-validation-20261019.json').read_text())
    assert report['status']=='participant_protocol_mock_passed' and report['testsRun']==17
    for key in ['failures','errors','skipped','nonLoopbackNetworkAttempts','liveProviderCalls','subprocessesStarted','strictCertified']:
        assert not report[key]
    for name,expected in report['sourceSha256'].items():assert sha((ROOT/name).read_bytes())==expected
    paths=[*sorted((ROOT/'sdk').rglob('*.py')),*sorted((ROOT/'api').glob('*.json')),ROOT/'api/build_spec.py',
      ROOT/'sdk/pyproject.toml',*sorted((ROOT/'docs').glob('*.md')),ROOT/'config/perception-policy.json',
      ROOT/'scripts/verify_harness_api.py',Path(__file__).resolve(),ROOT/'README.md',ROOT/'LICENSE',
      ROOT/'CONTRIBUTING.md',ROOT/'CHANGELOG.md',ROOT/'.gitignore',ROOT/'.github/workflows/ci.yml']
    files={}
    for path in paths:
        if '__pycache__' in path.parts:continue
        assert path.is_file() and not path.is_symlink()
        name=path.relative_to(ROOT).as_posix();data=path.read_bytes()
        for pattern in [rb'sk-[A-Za-z0-9_-]{20,}',rb'(?i)Bearer\s+[A-Za-z0-9_-]{32,}',rb'-----BEGIN [A-Z ]*PRIVATE KEY-----']:
            if re.search(pattern,data):raise RuntimeError('Potential credential in '+name)
        files[name]=data
    files['manifest.json']=(json.dumps({'name':NAME,'mode':'protocol_mock','strictCertified':False,
      'files':{name:{'bytes':len(data),'sha256':sha(data)} for name,data in sorted(files.items())}},ensure_ascii=False,indent=2)+'\n').encode()
    files['SHA256SUMS']=''.join(sha(data)+'  '+name+'\n' for name,data in sorted(files.items())).encode()
    output=ROOT/'artifacts'/(NAME+'.zip');output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,data in sorted(files.items()):
            item=zipfile.ZipInfo(NAME+'/'+name,(2026,10,19,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED;item.external_attr=0o100644<<16
            archive.writestr(item,data)
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        for name,data in files.items():assert archive.read(NAME+'/'+name)==data
    digest=sha(output.read_bytes());output.with_suffix('.zip.sha256').write_text(digest+'  '+output.name+'\n')
    print(json.dumps({'artifact':output.relative_to(ROOT).as_posix(),'sha256':digest,'files':len(files),'strictCertified':False},indent=2))
if __name__=='__main__':main()
