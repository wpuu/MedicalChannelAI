from pathlib import Path
import copy,hashlib,json,os,shlex,subprocess,sys,unittest
import yaml
root=Path('/workspace/MedicalChannelAI-p0')
path='.github/workflows/regional-medical-refresh.yml'
before=subprocess.check_output(['git','show',f'8b3eba8:{path}'],cwd=root).decode()
after=(root/path).read_text()
added_path="      - 'web/pipeline/tests/test_regional_cli_completeness.py'\n"
added_module='            tests.test_regional_cli_completeness \\\n'
assert after.count(added_path)==1 and after.count(added_module)==1
assert after.replace(added_path,'').replace(added_module,'')==before
old=yaml.load(before,Loader=yaml.BaseLoader);new=yaml.load(after,Loader=yaml.BaseLoader)
step=new['jobs']['refresh']['steps'][1]
assert step['name']=='Verify regional classification and CCGP parser regressions'
run=step['run'];assert run.startswith('set -euo pipefail\ncd web/pipeline\n')
argv=shlex.split(run.split('\n',2)[2].replace('\\\n',' '));assert argv[:3]==['python3','-m','unittest']
modules=argv[3:];assert len(modules)==8 and len(set(modules))==8
assert modules.count('tests.test_regional_cli_completeness')==1
normalized=copy.deepcopy(new)
normalized['on']['push']['paths'].remove('web/pipeline/tests/test_regional_cli_completeness.py')
normalized['jobs']['refresh']['steps'][1]['run']=old['jobs']['refresh']['steps'][1]['run']
assert normalized==old
Path('/tmp/mcai-ci-structure.json').write_text(json.dumps({'yaml_parser':'Existing PyYAML BaseLoader (preserves on key)','workflow_path':path,'before_sha256':hashlib.sha256(before.encode()).hexdigest(),'after_sha256':hashlib.sha256(after.encode()).hexdigest(),'only_two_added_lines':True,'other_yaml_structure_unchanged':True,'set_e_preserved':True,'modules':modules,'module_count':len(modules),'workflow_executed':False,'apply_allowed':False,'migration_usable':False},indent=2)+'\n')

def offline(event,args):
 if event=='import' and (args[0]=='vercel' or args[0].startswith('vercel.')):
  raise ImportError('REAL_SDK_IMPORT_FORBIDDEN')
 if event in ('socket.connect','socket.getaddrinfo'):
  raise RuntimeError('NETWORK_FORBIDDEN')
sys.addaudithook(offline)
os.chdir(root/'web/pipeline');sys.path.insert(0,str(Path.cwd()))
result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(modules))
Path('/tmp/mcai-ci-results.json').write_text(json.dumps({'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'passed':result.wasSuccessful(),'module_count':len(modules),'modules':modules,'python_version':sys.version.split()[0],'network_guard':'socket.connect and socket.getaddrinfo forbidden; real vercel SDK imports forbidden','workflow_executed':False,'full1079_rerun':False,'frozen10_original3_rerun':False,'apply_allowed':False,'migration_usable':False},indent=2)+'\n')
raise SystemExit(0 if result.wasSuccessful() else 1)
