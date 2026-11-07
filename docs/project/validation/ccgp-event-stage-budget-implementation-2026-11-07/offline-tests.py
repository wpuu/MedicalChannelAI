import ipaddress,json,os,sys,tempfile,unittest
from pathlib import Path
ROOT=Path('/workspace/MedicalChannelAI-p0')
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'web/pipeline'))
def offline(event,args):
    if event=='import' and (args[0]=='vercel' or args[0].startswith('vercel.')):
        raise ImportError('REAL_SDK_FORBIDDEN')
    if event in ('socket.connect','socket.getaddrinfo'):
        value=args[1][0] if event=='socket.connect' else args[0]
        if value!='localhost':
            try: local=ipaddress.ip_address(value).is_loopback
            except (ValueError,TypeError):local=False
            if not local:raise RuntimeError('EXTERNAL_NETWORK_FORBIDDEN')
    if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
        mode=args[1] or ''
        if any(c in mode for c in 'wax+') or args[2] & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):
            path=Path(os.fsdecode(args[0])).resolve()
            if path.is_relative_to(ROOT):raise RuntimeError('REPOSITORY_TEST_OUTPUT_FORBIDDEN')
sys.addaudithook(offline)
os.chdir(ROOT/'web/pipeline')
if len(sys.argv)>1 and sys.argv[1]=='script':
    import runpy
    sys.argv=sys.argv[2:]
    runpy.run_path(sys.argv[0],run_name='__main__')
    raise SystemExit(0)
if sys.argv[1:] == ['full']:
    suite=unittest.defaultTestLoader.discover('tests')
else:
    suite=unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:])
result=unittest.TextTestRunner(verbosity=1).run(suite)
print(json.dumps({'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'successful':result.wasSuccessful(),'external_network_blocked':True,'real_sdk_import_blocked':True,'repository_test_output_blocked':True}))
raise SystemExit(not result.wasSuccessful())
