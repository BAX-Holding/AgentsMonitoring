"""Developer acceptance: baseline regressions + disabled cross-site guard must fail.

Run in the source checkout, not a wheel; mutations exist only in this subprocess's memory.
No production processes, configs or source files are modified.
"""
from pathlib import Path
import subprocess
import sys
from unittest import TestLoader, TextTestRunner

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agentsmon import db,detect,dashboard,wizard
from test_db_no_fd_leak import NoFdLeak
from test_detection_regressions import ModelIdentity
from test_plugin_http import PluginHTTPGuard

for module,path in ((db,'db.py'),(detect,'detect.py'),(wizard,'wizard.py')):
    source=subprocess.check_output(['git','show','303aea9:agentsmon/'+path]).decode()
    exec(compile(source,'baseline-'+path,'exec'),module.__dict__)
model=TextTestRunner(verbosity=2).run(TestLoader().loadTestsFromTestCase(ModelIdentity))
sqlite=TextTestRunner(verbosity=2).run(TestLoader().loadTestsFromTestCase(NoFdLeak))
dashboard._action_allowed=lambda headers:True
guard=TextTestRunner(verbosity=2).run(TestLoader().loadTestsFromTestCase(PluginHTTPGuard))
assert not model.wasSuccessful() and not sqlite.wasSuccessful() and not guard.wasSuccessful()
print('PASS: original model/SQLite defects and a removed action guard are detected as red.')
