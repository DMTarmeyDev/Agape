import json
import os
import tempfile
import types
import sys
import unittest
from pathlib import Path
from unittest import mock

os.environ['AGAPE_UNIFIED_DATA'] = tempfile.mkdtemp(prefix='agape-unified-r2-test-')
import app


class AgapeUnifiedR24Tests(unittest.TestCase):
    def setUp(self):
        app.save_intakes([])
        app.save_jobs([])
        app.atomic_json(app.SETTINGS_FILE, dict(app.DEFAULT_SETTINGS))

    def test_build_is_r24(self):
        self.assertEqual(app.BUILD, 'AGAPE-UNIFIED-R4.7-TARGETED-VALIDATION-REPAIR')
        self.assertEqual(app.DEFAULT_PORT, 8852)


    def test_transient_document_timeout_retries_without_fake_validation_repair(self):
        timeout_payload={'error':'timed out'}
        success={'ok':True,'draft':'done','files':[{'ok':True,'file':'x.docx'}]}
        with mock.patch.object(app,'_doc_agent_create',side_effect=[(0,timeout_payload),(200,success)]) as create, mock.patch.object(app.time,'sleep',return_value=None), mock.patch.object(app,'add_event'):
            got,history=app.create_with_validation_repair({'doc_type':'Business Proposal','instructions':'facts'},'J-TIMEOUT',max_repairs=2)
        self.assertTrue(got['ok'])
        self.assertEqual(create.call_count,2)
        self.assertEqual(history,[])

    def test_timeout_failure_has_transient_error_name_not_validation_repair_name(self):
        timeout_payload={'error':'timed out'}
        with mock.patch.object(app,'_doc_agent_create',return_value=(0,timeout_payload)), mock.patch.object(app.time,'sleep',return_value=None), mock.patch.object(app,'add_event'):
            with self.assertRaisesRegex(RuntimeError,'AI_DOCUMENT_CREATE_TRANSIENT_FAILURE_AFTER_RETRIES'):
                app.create_with_validation_repair({'doc_type':'Business Proposal','instructions':'facts'},'J-TIMEOUT',max_repairs=0)

    def test_no_ready_provider_stops_immediately_as_action_required(self):
        payload={'error':'NO_READY_AI_PROVIDER: [{"provider":"chatgpt","phase":"preflight"}]'}
        with mock.patch.object(app,'_doc_agent_create',return_value=(500,payload)) as create, mock.patch.object(app.time,'sleep',return_value=None), mock.patch.object(app,'add_event'):
            with self.assertRaisesRegex(RuntimeError,'ACTION_REQUIRED: No usable AI provider is ready'):
                app.create_with_validation_repair({'doc_type':'Business Proposal','instructions':'facts'},'J-NOPROVIDER',max_repairs=2)
        self.assertEqual(create.call_count,1)


    def test_multi_review_unavailable_is_returned_not_raised(self):
        states=[(200,{'ok':True,'state':'unavailable','stage':'Gold review unavailable','progress':100,'error':'NO_READY_REVIEW_PROVIDER','errors':[{'provider':'chatgpt'}]})]
        with mock.patch.object(app,'doc_get',side_effect=states), mock.patch.object(app.time,'sleep',return_value=None), mock.patch.object(app,'add_event'):
            got=app.wait_multi_review('REV-NONE','JOB-NONE',timeout=1)
        self.assertEqual(got['state'],'unavailable')
        self.assertEqual(got['error'],'NO_READY_REVIEW_PROVIDER')

    def test_templates_preserved(self):
        rows = app.load_templates()
        ids = {x['id'] for x in rows}
        self.assertIn('business-plan', ids)
        self.assertIn('software-project', ids)

    def test_job_progress_never_moves_backwards(self):
        row={'id':'J-PROG','status':'RUNNING','stage':'Creating','message':'Working','progress':60,'events':[]}
        app.save_jobs([row])
        self.assertEqual(app.update_progress('J-PROG',20),60.0)
        self.assertEqual(app.update_progress('J-PROG',72.5),72.5)
        self.assertEqual(app.get_job('J-PROG')['progress'],72.5)

    def test_new_job_starts_with_progress(self):
        app.save_intake({'id':'AGI-P','project_id':0,'project_name':'Progress','upload_id':'UP','ai_fill':{}})
        with mock.patch('threading.Thread.start',return_value=None):
            job=app.new_job({'project_id':0,'intake_id':'AGI-P','quality_mode':'standard'})
        self.assertGreaterEqual(job['progress'],1)
        self.assertLess(job['progress'],10)

    def test_document_only_job_allowed_with_intake(self):
        row={'id':'AGI-1','project_id':0,'project_name':'One Upload Plan','source_name':'source.docx','upload_id':'U1','ai_fill':{},'field_count':17,'none_count':0}
        app.save_intake(row)
        with mock.patch.object(app,'project_by_id',return_value=None), mock.patch('threading.Thread.start',return_value=None):
            job=app.new_job({'project_id':0,'intake_id':'AGI-1','quality_mode':'standard'})
        self.assertEqual(job['intake_id'],'AGI-1')
        self.assertEqual(job['quality_mode'],'standard')

    def test_ai_fill_structured_form(self):
        got=app.ai_fill_to_structured_form({'fields':{'target_audience':{'value':'UK SMEs'},'budget':{'value':'None'},'blank':{'value':''}}})
        self.assertEqual(got['target_audience'],'UK SMEs')
        self.assertEqual(got['budget'],'None')
        self.assertNotIn('blank',got)

    def test_quality_status_sorts_connected_models(self):
        fake={'providers':[{'id':'slow','connected':True,'review_score':8.2,'name':'Slow','recommended_model':'s'}, {'id':'top','connected':True,'review_score':10,'name':'Top','recommended_model':'t'}, {'id':'off','connected':False,'review_score':99}]}
        with mock.patch.object(app,'doc_get',return_value=(200,fake)):
            q=app.quality_status()
        self.assertTrue(q['gold_ready'])
        self.assertEqual(q['providers'][0]['id'],'top')

    def test_intake_upload_then_fills_all_fields(self):
        upload={'ok':True,'upload':{'id':'UP1','name':'brief.docx','preview':'Brief facts'}}
        fields={f'f{i}':{'value':'value','status':'supplied'} for i in range(17)}
        fill={'ok':True,'title':'Gold Brief','fields':fields,'design':{'app':'writer','doc_type':'Business Proposal','theme':'Executive Navy','format':'docx','filename':'gold-brief'},'best_model_selection':{'provider':'chatgpt','model':'top','utility_score':10}}
        calls=[]
        def fake_post(path, body, timeout=1200):
            calls.append((path,body))
            if path=='/api/upload-instruction': return 200,upload
            if path=='/api/ai-fill-form': return 200,fill
            raise AssertionError(path)
        with mock.patch.object(app,'doc_post',side_effect=fake_post), mock.patch.object(app,'project_by_id',return_value=None):
            row=app.create_document_intake({'name':'brief.docx','data_base64':'AAAA','project_id':0})
        self.assertEqual(row['field_count'],17)
        self.assertEqual(row['upload_id'],'UP1')
        self.assertTrue(calls[1][1]['force_fill_missing'])
        self.assertEqual(calls[1][1]['ai_provider'],'auto')


    def test_saved_project_title_seeds_high_confidence_brief_facts(self):
        info="""Saved Agape project selected as the source for AI brief filling.
Project name: GreenStep Commercial Interiors Business Plan 2027
User-provided project notes:
1. Budget is £150,000
"""
        got=app.deterministic_source_fields('GreenStep Commercial Interiors Business Plan 2027',info,'')
        self.assertEqual(got['organisation'],'GreenStep Commercial Interiors')
        self.assertEqual(got['industry'],'Commercial interiors')
        self.assertEqual(got['product_service'],'Commercial interiors')
        self.assertEqual(got['document_purpose'],'Business plan')
        self.assertEqual(got['timeline'],'2027')
        self.assertEqual(got['budget_pricing'],'£150,000')

    def test_all_none_ai_fill_cannot_erase_saved_project_facts(self):
        upload={'ok':True,'upload':{'id':'UP-SEED','name':'greenstep.txt','preview':'GreenStep source'}}
        ids=['organisation','recipient','industry','geography','product_service','problem_need','document_purpose','decision_requested','target_audience','value_proposition','budget_pricing','timeline','success_metrics','competitors_alternatives','constraints','tone','research_focus']
        fields={fid:{'value':'None','status':'assumption','reason':'No reliable or relevant value was available.'} for fid in ids}
        fill={'ok':True,'title':'GreenStep Commercial Interiors Business Plan 2027','fields':fields,'design':{'app':'writer','doc_type':'Business Proposal','theme':'Executive Navy','format':'docx','filename':'greenstep'},'best_model_selection':{'provider':'ollama','model':'local'}}
        captured={}
        def fake_post(path,body,timeout=1200):
            if path=='/api/upload-instruction': return 200,upload
            if path=='/api/ai-fill-form':
                captured.update(body)
                return 200,fill
            raise AssertionError(path)
        info='Saved Agape project selected as the source for AI brief filling.\nProject name: GreenStep Commercial Interiors Business Plan 2027\nUser-provided project notes:\n1. Budget is £150,000'
        with mock.patch.object(app,'doc_post',side_effect=fake_post), mock.patch.object(app,'project_by_id',return_value=None):
            row=app.create_document_intake({'name':'greenstep.txt','data_base64':'AAAA','project_id':0,'source_mode':'project','project_name':'GreenStep Commercial Interiors Business Plan 2027','project_info':info})
        self.assertGreaterEqual(row['established_count'],6)
        self.assertLess(row['none_count'],17)
        self.assertEqual(row['ai_fill']['fields']['budget_pricing']['value'],'£150,000')
        self.assertEqual(row['ai_fill']['fields']['document_purpose']['value'],'Business plan')
        self.assertEqual(captured['structured_form']['timeline'],'2027')

    def test_document_intake_prepare_request_id_is_idempotent(self):
        upload={'ok':True,'upload':{'id':'UP-IDEM','name':'brief.docx','preview':'facts'}}
        fields={f'f{i}':{'value':'value','status':'supplied'} for i in range(17)}
        fill={'ok':True,'fields':fields,'design':{},'best_model_selection':{}}
        calls=[]
        def fake_post(path,body,timeout=1200):
            calls.append(path)
            return (200,upload) if path=='/api/upload-instruction' else (200,fill)
        body={'prepare_request_id':'WEB-IDEMPOTENT-ONE','name':'brief.docx','data_base64':'AAAA','project_id':0}
        with mock.patch.object(app,'doc_post',side_effect=fake_post), mock.patch.object(app,'project_by_id',return_value=None):
            first=app.create_document_intake(body)
            second=app.create_document_intake(body)
        self.assertEqual(first['id'],second['id'])
        self.assertEqual(calls.count('/api/upload-instruction'),1)
        self.assertEqual(calls.count('/api/ai-fill-form'),1)

    def test_no_route_still_blocks_without_document_or_workspace(self):
        project={'id':1,'name':'Unknown'}
        bundle={'template':{},'loop_settings':{'settings':{}}}
        route,_=app.determine_route(project,bundle,'do it',app.template_by_id('auto'))
        self.assertEqual(route,'blocked')

    def test_ui_is_one_upload_two_choice_flow(self):
        html=(app.WEB_ROOT/'index.html').read_text(encoding='utf-8')
        for marker in ('Upload one document. Let Agape build the rest.','Choose one source document','CREATE NOW','GOLD STANDARD','What Agape filled from the document'):
            self.assertIn(marker,html)

    def test_router_setup_defaults_to_agape(self):
        st=app.load_settings()
        self.assertFalse(st['setup_complete'])
        self.assertEqual(st['router'],'agape')

    def test_router_status_exposes_both_choices(self):
        fake_services={'core':{'ok':True},'document':{'ok':True},'work':{'ok':True}}
        with mock.patch.object(app,'get_services',return_value=fake_services), mock.patch.object(app.importlib.util,'find_spec',return_value=None):
            st=app.router_status()
        self.assertEqual(st['selected'],'agape')
        self.assertEqual({x['id'] for x in st['options']},{'agape','litellm'})
        self.assertTrue(next(x for x in st['options'] if x['id']=='agape')['recommended'])

    def test_litellm_router_adapter_selects_concrete_model(self):
        candidate={'actual_model':'ollama/qwen2.5-coder:7b','document_provider':'ollama','document_model':'qwen2.5-coder:7b','api_base':'http://127.0.0.1:11434','source':'ollama'}
        class FakeRouter:
            def __init__(self, model_list, **kwargs): self.model_list=model_list
            def get_available_deployment(self, model, messages=None): return self.model_list[0]
            def completion(self, **kwargs):
                mid=self.model_list[0]['model_info']['id']
                msg=types.SimpleNamespace(content='OK')
                return types.SimpleNamespace(_hidden_params={'model_id':mid},choices=[types.SimpleNamespace(message=msg)])
        fake_mod=types.SimpleNamespace(Router=FakeRouter)
        with mock.patch.object(app.importlib.util,'find_spec',return_value=object()), mock.patch.object(app,'litellm_candidates',return_value=[candidate]), mock.patch.dict(sys.modules,{'litellm':fake_mod}):
            d=app.litellm_route_decision('coding',execute_test=True)
        self.assertEqual(d['router'],'litellm')
        self.assertEqual(d['provider'],'ollama')
        self.assertEqual(d['model'],'qwen2.5-coder:7b')
        self.assertEqual(d['strategy'],'cost-based-routing')
        self.assertEqual(d['test_response'],'OK')

    def test_litellm_cannot_be_saved_until_ready(self):
        fake={'ok':True,'selected':'agape','setup_complete':False,'options':[{'id':'agape','ready':True},{'id':'litellm','ready':False}]}
        with mock.patch.object(app,'router_status',return_value=fake):
            with self.assertRaisesRegex(ValueError,'LITELLM_ROUTER_NOT_READY'):
                app.save_settings({'router':'litellm'})

    def test_setup_can_save_agape_as_default(self):
        with mock.patch.object(app,'router_status',return_value={'options':[{'id':'agape','ready':True},{'id':'litellm','ready':False}]}):
            st=app.save_settings({'router':'agape','setup_complete':True})
        self.assertTrue(st['setup_complete'])
        self.assertEqual(st['router'],'agape')

    def test_intake_uses_selected_router_decision(self):
        upload={'ok':True,'upload':{'id':'UP2','name':'brief.docx','preview':'Brief facts'}}
        fields={f'f{i}':{'value':'value','status':'supplied'} for i in range(17)}
        fill={'ok':True,'title':'Gold Brief','fields':fields,'design':{'app':'writer','doc_type':'Business Proposal','theme':'Executive Navy','format':'docx','filename':'gold-brief'}}
        calls=[]
        def fake_post(path, body, timeout=1200):
            calls.append((path,body))
            return (200,upload) if path=='/api/upload-instruction' else (200,fill)
        decision={'router':'litellm','provider':'ollama','model':'qwen2.5-coder:7b','litellm_model':'ollama/qwen2.5-coder:7b','strategy':'cost-based-routing'}
        with mock.patch.object(app,'doc_post',side_effect=fake_post), mock.patch.object(app,'project_by_id',return_value=None), mock.patch.object(app,'router_decision',return_value=decision):
            row=app.create_document_intake({'name':'brief.docx','data_base64':'AAAA','project_id':0})
        self.assertEqual(row['router'],'litellm')
        self.assertEqual(calls[1][1]['ai_provider'],'ollama')
        self.assertEqual(calls[1][1]['ai_model'],'qwen2.5-coder:7b')

    def test_job_records_router_snapshot(self):
        row={'id':'AGI-R','project_id':0,'project_name':'Router Test','source_name':'source.docx','upload_id':'U1','ai_fill':{},'field_count':17,'none_count':0}
        app.save_intake(row)
        with mock.patch.object(app,'project_by_id',return_value=None), mock.patch('threading.Thread.start',return_value=None):
            job=app.new_job({'project_id':0,'intake_id':'AGI-R','quality_mode':'standard','router':'agape'})
        self.assertEqual(job['router'],'agape')

    def test_ui_contains_first_run_and_settings_router_choice(self):
        html=(app.WEB_ROOT/'index.html').read_text(encoding='utf-8')
        for marker in ('FIRST-RUN SETUP','Choose how Agape selects AI models','settingsRouterChoices','Save router'):
            self.assertIn(marker,html)

    def test_research_router_ranks_company_sources_for_uk_business(self):
        plan=app.research_router.recommend_sources('UK company competitor market business plan directors ownership',10)
        ids=[x['id'] for x in plan['sources']]
        self.assertEqual(len(ids),10)
        self.assertIn('companies_house',ids[:4])
        self.assertIn('ons',ids)

    def test_research_router_ranks_procurement_for_flooring_tender(self):
        plan=app.research_router.recommend_sources('UK commercial flooring public sector tender procurement framework',10)
        ids=[x['id'] for x in plan['sources']]
        self.assertIn('uk_procurement',ids[:3])

    def test_research_router_social_subject_includes_social_sources(self):
        plan=app.research_router.recommend_sources('brand sentiment customer community reviews social media trend',10)
        ids={x['id'] for x in plan['sources']}
        self.assertTrue({'x','youtube','reddit'} & ids)

    def test_intake_stores_top_10_research_plan(self):
        upload={'ok':True,'upload':{'id':'UPR','name':'brief.docx','preview':'UK technology company market investment competitor research'}}
        fields={f'f{i}':{'value':'UK technology market','status':'supplied'} for i in range(17)}
        fill={'ok':True,'title':'Research Brief','fields':fields,'design':{'app':'writer','doc_type':'Business Proposal','theme':'Executive Navy','format':'docx','filename':'research-brief'}}
        def fake_post(path, body, timeout=1200):
            return (200,upload) if path=='/api/upload-instruction' else (200,fill)
        with mock.patch.object(app,'doc_post',side_effect=fake_post), mock.patch.object(app,'project_by_id',return_value=None):
            row=app.create_document_intake({'name':'brief.docx','data_base64':'AAAA','project_id':0})
        self.assertEqual(row['research_plan']['selected_count'],10)
        self.assertEqual(len(row['research_plan']['sources']),10)

    def test_job_snapshots_research_plan(self):
        plan=app.research_router.recommend_sources('UK company market',10)
        row={'id':'AGI-RS','project_id':0,'project_name':'Research Test','source_name':'source.docx','upload_id':'U1','ai_fill':{},'field_count':17,'none_count':0,'research_plan':plan}
        app.save_intake(row)
        with mock.patch.object(app,'project_by_id',return_value=None), mock.patch('threading.Thread.start',return_value=None):
            job=app.new_job({'project_id':0,'intake_id':'AGI-RS','quality_mode':'standard'})
        self.assertEqual(job['research_plan']['selected_count'],10)

    def test_ui_contains_research_source_manager(self):
        html=(app.WEB_ROOT/'index.html').read_text(encoding='utf-8')
        for marker in ('Research sources','researchSourceGrid','Top research sources Agape selected','Install secure credential support'):
            self.assertIn(marker,html)

    def test_ui_has_go_ahead_and_ai_gap_fill_actions(self):
        html=(app.WEB_ROOT/'index.html').read_text(encoding='utf-8')
        js=(app.WEB_ROOT/'app.js').read_text(encoding='utf-8')
        for marker in ('Find Missing Information with AI','Go ahead → choose quality','Questions only you can answer','saveUserAnswers'):
            self.assertIn(marker,html)
        self.assertIn('researchMissingInformation',js)
        self.assertIn("researchBtn.style.display=none?'inline-flex':'none'",js)

    def test_intake_exposes_unresolved_questions(self):
        upload={'ok':True,'upload':{'id':'UPQ','name':'brief.docx','preview':'Brief facts'}}
        fields={f'f{i}':{'value':'value','status':'supplied'} for i in range(16)}
        fields['competitors_alternatives']={'value':'None','status':'assumption','reason':'Needs current market research'}
        fill={'ok':True,'title':'Gap Brief','fields':fields,'design':{'app':'writer','doc_type':'Business Proposal','theme':'Executive Navy','format':'docx','filename':'gap-brief'}}
        def fake_post(path, body, timeout=1200):
            return (200,upload) if path=='/api/upload-instruction' else (200,fill)
        with mock.patch.object(app,'doc_post',side_effect=fake_post), mock.patch.object(app,'project_by_id',return_value=None):
            row=app.create_document_intake({'name':'brief.docx','data_base64':'AAAA','project_id':0})
        self.assertEqual(row['none_count'],1)
        self.assertEqual(row['unresolved_questions'][0]['field_id'],'competitors_alternatives')

    def test_missing_information_ai_research_reuses_upload_and_resolves_gap(self):
        fields={f'f{i}':{'value':'value','status':'supplied'} for i in range(16)}
        fields['competitors_alternatives']={'value':'None','status':'assumption','reason':'Needs research'}
        intake={'id':'AGI-GAP','project_id':0,'project_name':'Gap Test','upload_id':'UP-GAP','upload':{'preview':'Market brief'},'project_info':'Saved facts','instruction':'Make it gold standard','ai_fill':{'ok':True,'title':'Gap Test','fields':fields,'design':{'app':'writer','doc_type':'Business Proposal','theme':'Executive Navy','format':'docx','filename':'gap-test'}},'field_count':17,'none_count':1,'research_plan':app.research_router.recommend_sources('UK market competitor business plan',10)}
        app.save_intake(intake)
        improved_fields=dict(fields);improved_fields['competitors_alternatives']={'value':'Competitor A, Competitor B','status':'researched','reason':'Verified from current public research'}
        improved={'ok':True,'title':'Gap Test','fields':improved_fields,'design':intake['ai_fill']['design'],'best_model_selection':{'provider':'chatgpt','model':'top'}}
        calls=[]
        def fake_post(path,body,timeout=1200):
            calls.append((path,body,timeout));return 200,improved
        with mock.patch.object(app,'doc_post',side_effect=fake_post), mock.patch.object(app,'router_decision',return_value={'router':'agape','provider':'auto','model':'auto'}):
            row=app.improve_intake_with_ai('AGI-GAP')
        self.assertEqual(row['none_count'],0)
        self.assertEqual(row['last_gap_fill']['resolved'],1)
        self.assertEqual(calls[0][0],'/api/public-research')
        self.assertIn('questions',calls[0][1])
        self.assertEqual(calls[1][0],'/api/ai-fill-form')
        self.assertTrue(calls[1][1]['research_enabled'])
        self.assertEqual(calls[1][1]['research_depth'],'balanced')
        self.assertEqual(calls[1][1]['instruction_upload_ids'],['UP-GAP'])
        self.assertIn('research_evidence',calls[1][1])
        self.assertNotIn('competitors_alternatives',calls[1][1]['structured_form'])

    def test_user_can_answer_remaining_private_question(self):
        intake={'id':'AGI-ANS','project_id':0,'project_name':'Private Test','upload_id':'U','ai_fill':{'fields':{'budget_pricing_commercial_terms':{'value':'None','status':'assumption'}}},'field_count':1,'none_count':1}
        app.save_intake(intake)
        row=app.apply_intake_answers('AGI-ANS',{'budget_pricing_commercial_terms':'£25,000 pilot budget'})
        self.assertEqual(row['none_count'],0)
        self.assertEqual(row['ai_fill']['fields']['budget_pricing_commercial_terms']['status'],'supplied')
        self.assertEqual(row['unresolved_questions'],[])


    def test_default_gold_review_team_is_three_for_speed(self):
        st=app.load_settings()
        self.assertEqual(st['gold_reviewer_count'],3)
        self.assertEqual(st['gold_reviewer_ids'],[])
        self.assertEqual(st['gold_lead_reviewer'],'auto')

    def test_auto_gold_team_uses_up_to_requested_connected_reviewers(self):
        providers=[{'id':f'p{i}','review_score':10-i/10,'connected':True} for i in range(6)]
        team=app.choose_gold_review_team(providers,{'reviewer_count':10,'reviewer_ids':[],'lead_reviewer':'auto'})
        self.assertEqual(team['mode'],'automatic')
        self.assertEqual(team['requested_count'],10)
        self.assertEqual(team['used_count'],6)
        self.assertEqual(team['reviewers'],[f'p{i}' for i in range(6)])

    def test_custom_gold_team_uses_exact_selected_reviewers(self):
        providers=[{'id':'chatgpt','review_score':10},{'id':'claude','review_score':9.9},{'id':'gemini','review_score':9.8},{'id':'xai','review_score':9.7}]
        team=app.choose_gold_review_team(providers,{'reviewer_count':10,'reviewer_ids':['gemini','chatgpt','xai'],'lead_reviewer':'gemini'})
        self.assertEqual(team['mode'],'custom')
        self.assertEqual(team['reviewers'],['gemini','chatgpt','xai'])
        self.assertEqual(team['used_count'],3)
        self.assertEqual(team['lead_reviewer'],'gemini')

    def test_job_auto_mode_can_override_custom_saved_default(self):
        app.save_settings({'gold_reviewer_ids':['chatgpt','claude','gemini']})
        providers=[{'id':'chatgpt','review_score':10},{'id':'claude','review_score':9.9},{'id':'gemini','review_score':9.8},{'id':'xai','review_score':9.7}]
        team=app.choose_gold_review_team(providers,{'reviewer_count':2,'reviewer_ids':[],'lead_reviewer':'auto'})
        self.assertEqual(team['mode'],'automatic')
        self.assertEqual(team['reviewers'],['chatgpt','claude'])

    def test_custom_gold_team_keeps_available_reviewers_and_defers_runtime_fallback(self):
        providers=[{'id':'chatgpt','review_score':10},{'id':'claude','review_score':9.9}]
        team=app.choose_gold_review_team(providers,{'reviewer_ids':['gemini','chatgpt']})
        self.assertEqual(team['reviewers'],['chatgpt'])
        self.assertEqual(team['unavailable_selected'],['gemini'])
        self.assertEqual(team['used_count'],1)

    def test_settings_persist_review_team(self):
        st=app.save_settings({'gold_reviewer_count':7,'gold_reviewer_ids':['chatgpt','claude','gemini'],'gold_lead_reviewer':'claude'})
        self.assertEqual(st['gold_reviewer_count'],7)
        self.assertEqual(st['gold_reviewer_ids'],['chatgpt','claude','gemini'])
        self.assertEqual(st['gold_lead_reviewer'],'claude')

    def test_job_records_reviewer_selector_snapshot(self):
        row={'id':'AGI-REV','project_id':0,'project_name':'Review Selector','source_name':'source.docx','upload_id':'U1','ai_fill':{},'field_count':17,'none_count':0}
        app.save_intake(row)
        with mock.patch.object(app,'project_by_id',return_value=None), mock.patch('threading.Thread.start',return_value=None):
            job=app.new_job({'project_id':0,'intake_id':'AGI-REV','quality_mode':'gold','reviewer_count':8,'reviewer_ids':['chatgpt','claude'],'lead_reviewer':'claude'})
        self.assertEqual(job['reviewer_count'],8)
        self.assertEqual(job['reviewer_ids'],['chatgpt','claude'])
        self.assertEqual(job['lead_reviewer'],'claude')

    def test_ui_contains_gold_model_selector(self):
        html=(app.WEB_ROOT/'index.html').read_text(encoding='utf-8')
        js=(app.WEB_ROOT/'app.js').read_text(encoding='utf-8')
        for marker in ('Gold Standard model selector','jobReviewerCount','jobReviewerAuto','jobReviewerList','settingsReviewerCount','settingsReviewerList','Save review team'):
            self.assertIn(marker,html)
        for marker in ('reviewerConfig','choose_gold_review_team','Automatic Top'):
            self.assertTrue(marker in js or marker in (app.ROOT/'app.py').read_text(encoding='utf-8'))

    def test_result_files_only_from_job_result(self):
        td=Path(tempfile.mkdtemp());f=td/'a.docx';f.write_bytes(b'x')
        self.assertEqual(app.allowed_result_files({'result':{'files':[{'file':str(f)}]}}),[f.resolve()])



    def test_async_document_create_polls_until_ready(self):
        calls=[]
        def fake_post(path, body, timeout=1200):
            calls.append(('post',path,timeout))
            self.assertEqual(path,'/api/agent-create/start')
            return 202,{'ok':True,'job_id':'DOC-1'}
        states=[
            (200,{'ok':True,'state':'working','stage':'Creating document with AI','progress':8}),
            (200,{'ok':True,'state':'ready','stage':'Document ready','progress':100,'result':{'ok':True,'draft':'done','files':[]}}),
        ]
        def fake_get(path,timeout=15):
            calls.append(('get',path,timeout))
            return states.pop(0)
        with mock.patch.object(app,'doc_post',side_effect=fake_post), mock.patch.object(app,'doc_get',side_effect=fake_get), mock.patch.object(app,'add_event'), mock.patch.object(app.time,'sleep',return_value=None):
            status,result=app._doc_agent_create({'title':'X'},'JOB-ASYNC')
        self.assertEqual(status,200)
        self.assertTrue(result['ok'])
        self.assertEqual(calls[0][1],'/api/agent-create/start')
        self.assertIn('/api/agent-create/status?id=DOC-1',calls[1][1])

    def test_async_document_create_returns_worker_validation_error_for_repair(self):
        err='GENERATED_DOCUMENT_VALIDATION_FAILED={"missing": ["Sources / Evidence"], "short": []}'
        with mock.patch.object(app,'doc_post',return_value=(202,{'ok':True,'job_id':'DOC-2'})), mock.patch.object(app,'doc_get',return_value=(200,{'ok':True,'state':'failed','error':err})), mock.patch.object(app,'add_event'), mock.patch.object(app.time,'sleep',return_value=None):
            status,result=app._doc_agent_create({'title':'X'},'JOB-ASYNC')
        self.assertEqual(status,500)
        self.assertEqual(app._validation_failure_details(result)['missing'],['Sources / Evidence'])

    def test_validation_failure_parser_extracts_missing_and_short_sections(self):
        payload={'error':'GENERATED_DOCUMENT_VALIDATION_FAILED={"missing": ["Recommendation / Next Step", "Sources / Evidence"], "short": ["TAM / SAM / SOM", "Customer Personas"]}'}
        got=app._validation_failure_details(payload)
        self.assertEqual(got['missing'],['Recommendation / Next Step','Sources / Evidence'])
        self.assertEqual(got['short'],['TAM / SAM / SOM','Customer Personas'])

    def test_agent_create_validation_failure_auto_repairs_and_retries(self):
        calls=[]
        failure={'error':'GENERATED_DOCUMENT_VALIDATION_FAILED={"missing": ["Recommendation / Next Step", "Sources / Evidence"], "short": ["TAM / SAM / SOM", "Customer Personas"]}'}
        success={'ok':True,'draft':'complete','audit':{'ok':True},'files':[{'ok':True,'file':'x.docx'}]}
        def fake_post(path, body, timeout=1200):
            calls.append((path,dict(body)))
            if len(calls)==1:return 500,failure
            return 200,success
        with mock.patch.object(app,'doc_post',side_effect=fake_post), mock.patch.object(app,'add_event'), mock.patch.object(app,'router_decision',return_value={'provider':'auto','model':'auto'}):
            result,history=app.create_with_validation_repair({'instructions':'base','doc_type':'Business Proposal','ai_provider':'auto','ai_model':'auto'},'JOB-1')
        self.assertTrue(result['ok'])
        self.assertEqual(len(history),1)
        repaired=calls[1][1]['instructions']
        for marker in ('Recommendation / Next Step','Sources / Evidence','TAM / SAM / SOM','Customer Personas','AGAPE TARGETED VALIDATION REPAIR PASS'):
            self.assertIn(marker,repaired)
        self.assertTrue(calls[1][1]['research_enabled'])
        self.assertEqual(calls[1][1]['research_depth'],'deep')

    def test_business_quality_contract_prevents_thin_required_sections(self):
        text=app._business_quality_contract('Business Proposal')
        for marker in ('TAM / SAM / SOM','Customer Personas','Recommendation / Next Step','Sources / Evidence'):
            self.assertIn(marker,text)


if __name__=='__main__':
    unittest.main()
