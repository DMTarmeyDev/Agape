import json, pathlib, sys, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agape_mainframe import security

class SecurityApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=pathlib.Path(tempfile.mkdtemp(prefix='agape-security-test-'))
        security.SECURITY_ROOT=self.tmp
        security.APPROVED_FILE=self.tmp/'approved-installers.json'
        security.AUDIT_FILE=self.tmp/'installer-audit.jsonl'
        security.APPROVAL_DIR=self.tmp/'approvals'
    def test_empty_approval_list(self):
        self.assertEqual(security.approved_installers(),[])
    def test_reads_only_expected_fields(self):
        security.APPROVED_FILE.write_text(json.dumps({'schema':1,'approved':[{'id':'exact:abc','kind':'exact_package','name':'Agape','sha256':'abc','approved_at':'2026-09-16T18:00:00','secret':'no'}]}),encoding='utf-8')
        rows=security.approved_installers()
        self.assertEqual(rows[0]['id'],'exact:abc')
        self.assertNotIn('secret',rows[0])
    def test_revoke_removes_exact_approval_and_audits(self):
        security.APPROVED_FILE.write_text(json.dumps({'schema':1,'approved':[{'id':'exact:abc','kind':'exact_package','name':'Agape','sha256':'abc'}]}),encoding='utf-8')
        r=security.revoke_approval('exact:abc')
        self.assertTrue(r['removed']);self.assertEqual(r['approved'],[])
        self.assertIn('approval_revoked',security.AUDIT_FILE.read_text(encoding='utf-8'))
    def test_revoke_unknown_is_safe(self):
        r=security.revoke_approval('exact:none')
        self.assertFalse(r['removed'])
    def test_reads_batch_exact_approval_file(self):
        security.APPROVAL_DIR.mkdir(parents=True,exist_ok=True)
        (security.APPROVAL_DIR/'exact-abc.approved').write_text('id=exact:abc\nkind=exact_package\nname=Agape Mainframe V2.2\nversion=2.2.0\nsha256=abc\nsignature_status=Unsigned\napproved_at=2026-09-16T18:00:00\n',encoding='utf-8')
        rows=security.approved_installers()
        self.assertEqual(rows[0]['sha256'],'abc')
        r=security.revoke_approval('exact:abc')
        self.assertTrue(r['removed']);self.assertFalse((security.APPROVAL_DIR/'exact-abc.approved').exists())
    def test_blank_revoke_rejected(self):
        with self.assertRaisesRegex(ValueError,'APPROVAL_ID_REQUIRED'):
            security.revoke_approval('')

if __name__=='__main__':unittest.main(verbosity=2)
