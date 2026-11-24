import ast
import symtable
import unittest
from pathlib import Path

class BatchPathScopeTests(unittest.TestCase):
    def test_path_is_not_shadowed_inside_run_job(self):
        path=Path(__file__).resolve().parent.parent/"scripts"/"batch.py"
        table=symtable.symtable(path.read_text(encoding="utf8"),str(path),"exec")
        job=next(c for c in table.get_children() if c.get_name()=="run_job")
        self.assertTrue(job.lookup("Path").is_global())
        self.assertFalse(job.lookup("Path").is_local())
if __name__=="__main__": unittest.main()
