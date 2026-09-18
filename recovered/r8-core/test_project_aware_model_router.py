import unittest
import model_router

class ProjectAwareModelRouterTests(unittest.TestCase):
    def setUp(self):
        self.models=[{'name':'qwen2.5-coder:1.5b-instruct'},{'name':'qwen2.5-coder:7b'}]
        self.project={'id':7,'name':'Agape'}
    def test_requires_project_for_project_mode(self):
        r=model_router.choose_project_model(self.models,'fix tests',None,[],{},[],[],{})
        self.assertFalse(r['project_loaded'])
        self.assertEqual(r['reason'],'PROJECT_REQUIRED')
    def test_complex_project_prefers_7b(self):
        files=[{'path':f'src/f{i}.py','size':30000} for i in range(45)]
        r=model_router.choose_project_model(self.models,'repair failing integration tests',self.project,[{'content':'database failure'}],{'goal':'refactor API and fix security','workspace':'C:/x'},[],[{'status':'open','title':'test failure'}],{'ok':True,'files':files})
        self.assertEqual(r['model'],'qwen2.5-coder:7b')
        self.assertGreaterEqual(r['context']['complexity_score'],4)
        self.assertIn('Python',r['context']['languages'])
    def test_light_project_can_prefer_small_model(self):
        files=[{'path':'hello.py','size':300}]
        r=model_router.choose_project_model(self.models,'explain this project',self.project,[],{'goal':'small example'},[],[],{'ok':True,'files':files})
        self.assertEqual(r['model'],'qwen2.5-coder:1.5b-instruct')
    def test_project_history_is_used(self):
        runs=[{'model':'qwen2.5-coder:7b','status':'PASS'},{'model':'qwen2.5-coder:7b','status':'PASS'}]
        r=model_router.choose_project_model(self.models,'fix code',self.project,[],{},runs,[],{'ok':True,'files':[{'path':'a.py','size':5000} for _ in range(20)]})
        score=next(x for x in r['scores'] if x['model']=='qwen2.5-coder:7b')
        self.assertTrue(any('project-history' in x for x in score['signals']))

if __name__=='__main__': unittest.main()
