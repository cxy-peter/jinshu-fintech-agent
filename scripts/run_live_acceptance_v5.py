"""Resolve local evaluator explicitly, without modifying the upstream engine/scripts package.
Run in the isolated real-services stack. This wrapper is not evidence of a successful live run.
"""
import importlib.util,runpy,sys
from pathlib import Path
scripts=Path(__file__).resolve().parent
sys.path.insert(0,str(scripts.parent))
spec=importlib.util.spec_from_file_location('scripts.evaluate_v4',scripts/'evaluate_v4.py')
module=importlib.util.module_from_spec(spec);sys.modules['scripts.evaluate_v4']=module
spec.loader.exec_module(module)
runpy.run_path(str(scripts/'live_acceptance.py'),run_name='__main__')
