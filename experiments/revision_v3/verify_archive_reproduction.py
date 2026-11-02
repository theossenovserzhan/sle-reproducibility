"""Fresh extraction regenerates article tables/response without private data."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess,sys,tempfile,zipfile

ROOT=Path(__file__).resolve().parent
TARGETS=('generated_v3_results.tex','generated_v3_supplement.tex','response_to_reviewers.tex','generated_v3_response_values.tex')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    archive=ROOT/'output/TBIOM_R1_v3_package.zip'
    stage=Path(tempfile.mkdtemp(prefix='archive_reproduction_',dir=ROOT/'tmp')).resolve()
    assert stage.is_relative_to((ROOT/'tmp').resolve())
    with zipfile.ZipFile(archive) as source:
        for info in source.infolist():
            target=(stage/info.filename).resolve()
            assert target.is_relative_to(stage),info.filename
        assert source.testzip() is None
        manifest=json.loads(source.read('TBIOM_R1_v3/CONTENTS_SHA256.json'))
        for relative,metadata in manifest.items():
            data=source.read('TBIOM_R1_v3/'+relative)
            assert len(data)==metadata['bytes'] and hashlib.sha256(data).hexdigest()==metadata['sha256']
        source.extractall(stage)
    study=stage/'TBIOM_R1_v3/revision_v3'
    before={name:sha(study/'manuscript_v3'/name) for name in TARGETS}
    with (ROOT/'logs/archive_reproduction.log').open('w') as stream:
        for script in ('build_v3_final_tables.py','update_response_v3.py'):
            subprocess.run([sys.executable,script],cwd=study,stdout=stream,stderr=subprocess.STDOUT,timeout=60,check=True)
    after={name:sha(study/'manuscript_v3'/name) for name in TARGETS}
    assert before==after,(before,after)
    assert before=={name:sha(ROOT/'manuscript_v3'/name) for name in TARGETS}
    qa=json.loads((ROOT/'results/pdf_visual_qa.json').read_text())
    pdfs={name:sha(study/f'output/pdf/{name}.pdf') for name in qa['pdfs']}
    assert all(digest==qa['pdfs'][name]['sha256'] for name,digest in pdfs.items())
    result={'all_pass':True,'checked_utc':datetime.now(timezone.utc).isoformat(),'method':'Fresh ZIP extraction, all-member SHA/CRC, regeneration of all four current TeX table/response files with no biometric data or MPC runtime; exact byte comparison to extracted and working originals.',
      'tested_tables_and_response_sha256':after,'tested_pdf_sha256':pdfs,'private_data_required':False,
      'scope':'Critical immutable-content hashes remain verified when the archive is repackaged only to add this audit/log; final package manifest separately verifies every final member and ZIP CRC.',
      'reproduction_stage':stage.relative_to(ROOT).as_posix()}
    (ROOT/'results/archive_reproduction_audit.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
