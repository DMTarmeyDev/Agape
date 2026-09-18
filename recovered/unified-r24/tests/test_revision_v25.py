import pathlib, sys, tempfile, unittest
from unittest import mock
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import app

class VersionedAIRevisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old_intakes=app.INTAKES_FILE; self.old_jobs=app.JOBS_FILE
        app.INTAKES_FILE=pathlib.Path(self.tmp.name)/'intakes.json'
        app.JOBS_FILE=pathlib.Path(self.tmp.name)/'jobs.json'
        app.save_intakes([]); app.save_jobs([])
    def tearDown(self):
        app.INTAKES_FILE=self.old_intakes; app.JOBS_FILE=self.old_jobs
        self.tmp.cleanup()

    def test_form_revision_preserves_lineage_and_replaces_requested_value(self):
        intake={'id':'I1','project_name':'Plan','upload_id':'U1','upload':{'preview':'facts'},'project_info':'','instruction':'',
                'ai_fill':{'title':'Plan','fields':{'budget_pricing':{'value':'£25,000','status':'filled'},'industry':{'value':'Flooring','status':'filled'}},
                           'design':{'app':'writer','doc_type':'Business Plan','theme':'Executive Navy','format':'docx'}}}
        app.save_intake(intake)
        improved={'ok':True,'title':'Plan','fields':{'budget_pricing':{'value':'£150,000','status':'filled'},'industry':{'value':'Flooring','status':'filled'}},
                  'design':intake['ai_fill']['design']}
        with mock.patch.object(app,'router_decision',return_value={'router':'agape','provider':'auto','model':'auto'}), \
             mock.patch.object(app,'doc_post',return_value=(200,improved)):
            row=app.revise_intake_with_ai('I1','Change budget to £150,000')
        self.assertEqual(row['ai_fill']['fields']['budget_pricing']['value'],'£150,000')
        self.assertEqual(len(row['form_revisions']),1)
        self.assertEqual(row['form_revisions'][0]['instruction'],'Change budget to £150,000')

    def test_document_revision_creates_child_job_and_keeps_parent(self):
        old={'id':'J1','project_id':0,'project_name':'Plan','intake_id':'I1','quality_mode':'gold','reviewer_count':4,
             'reviewer_ids':[],'lead_reviewer':'auto','router':'agape','instruction':'create plan','project_info':'','template_id':'auto',
             'ui_theme':'forest','document_theme':'Executive Navy','format':'docx','also_pdf':True,'status':'PASS','events':[],
             'result':{'agent':{'draft':'FIRST'},'review':{'revised_draft':'FINAL GOLD DRAFT'}}}
        app.save_jobs([old])
        captured={}
        def fake_new(payload):
            captured.update(payload); return {'id':'J2',**payload}
        with mock.patch.object(app,'new_job',side_effect=fake_new):
            row=app.revise_job_with_ai('J1','Shorten executive summary','standard')
        self.assertEqual(row['id'],'J2')
        self.assertEqual(captured['revision_of'],'J1')
        self.assertEqual(captured['lineage_root'],'J1')
        self.assertEqual(captured['revision_number'],2)
        self.assertIn('FINAL GOLD DRAFT',captured['project_info'])
        self.assertIn('Shorten executive summary',captured['instruction'])

if __name__=='__main__': unittest.main(verbosity=2)
