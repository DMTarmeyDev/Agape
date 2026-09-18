from __future__ import annotations
import os, subprocess, sys, tempfile, threading, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fake_integration import start, getj


def main():
    temp = Path(tempfile.mkdtemp(prefix='agu-r24-browser-'))
    (temp / 'security').mkdir()
    (temp / 'security' / 'local-session-token.txt').write_text('test', encoding='utf-8')
    servers = [start(18797, temp), start(18820, temp), start(18800, temp)]
    fake_local = temp / 'localappdata'; fake_local.mkdir()
    env = os.environ.copy()
    env.update({
        'AGAPE_CORE_URL':'http://127.0.0.1:18797',
        'AGAPE_WORK_URL':'http://127.0.0.1:18820',
        'AGAPE_DOC_URL':'http://127.0.0.1:18800',
        'AGAPE_UNIFIED_DATA':str(temp / 'unified'),
        'LOCALAPPDATA':str(fake_local),
    })
    proc = subprocess.Popen([sys.executable, str(BASE / 'app.py'), '--port', '18841'], env=env)
    try:
        for _ in range(60):
            try:
                if getj('http://127.0.0.1:18841/api/health').get('ok'): break
            except Exception: time.sleep(.1)
        else: raise RuntimeError('UNIFIED_NOT_READY')

        source = temp / 'source.txt'
        source.write_text('GreenStep business plan. Competitor information is missing and should be researched.', encoding='utf-8')
        errors=[]
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True, executable_path='/usr/bin/chromium')
            page=browser.new_page(viewport={'width':1440,'height':1100})
            page.on('pageerror', lambda e: errors.append('pageerror:'+str(e)))
            page.on('console', lambda m: errors.append('console:'+m.text) if m.type=='error' else None)
            r=page.goto('http://127.0.0.1:18841/', wait_until='domcontentloaded', timeout=30000)
            assert r and r.ok

            page.locator('#setupOverlay').wait_for(state='visible')
            page.locator('#setupFinish').click()
            page.wait_for_function("document.querySelector('#setupOverlay').classList.contains('hidden')", timeout=10000)

            page.wait_for_function("document.querySelector('#projectSelect').options.length >= 2")
            page.locator('#projectSelect').select_option('5')
            page.locator('#projectNext').click()
            page.locator('#uploadCard').wait_for(state='visible')
            page.locator('#sourceFile').set_input_files(str(source))
            page.locator('#understoodCard').wait_for(state='visible', timeout=15000)
            page.locator('#researchMissing').wait_for(state='visible')
            page.locator('#researchMissing').click()
            page.wait_for_function("document.querySelector('#missingSummary').innerText.includes('Brief complete')", timeout=15000)
            page.locator('#goAhead').click()
            page.locator('#createCard').wait_for(state='visible')

            assert page.locator('#jobReviewerCount').input_value()=='10'
            page.wait_for_function("document.querySelectorAll('#jobReviewerList [data-reviewer-id]').length === 10")
            assert '10/10' in page.locator('#jobReviewerStatus').inner_text()
            page.locator('#createGold').click()
            page.wait_for_function("document.querySelector('#workState').textContent === 'Complete'", timeout=20000)
            assert '10/10 requested independent reviewers used' in page.locator('#resultPanel').inner_text()
            assert page.locator('#resultPanel a[href*="/download"]').count() >= 1

            page.get_by_role('button', name='Settings', exact=True).click()
            page.locator('#settingsReviewerCount').select_option('3')
            page.locator('#settingsReviewerAuto').uncheck()
            checks=page.locator('#settingsReviewerList [data-reviewer-id]')
            for i in range(checks.count()): checks.nth(i).uncheck()
            for i in range(3): checks.nth(i).check()
            page.locator('#saveReviewerSetting').click()
            page.wait_for_timeout(300)
            browser.close()

        if errors: raise AssertionError('BROWSER_ERRORS='+' | '.join(errors[:10]))
        print('R2_4_BROWSER_SMOKE=PASS')
        print('FIRST_RUN_SETUP=PASS')
        print('MISSING_INFO_AI_BUTTON=PASS')
        print('TOP10_MODEL_SELECTOR_UI=PASS')
        print('TOP10_GOLD_REVIEW_UI=PASS')
        print('CUSTOM_REVIEWER_SETTINGS_UI=PASS')
        print('PAGE_ERRORS=0')
    finally:
        proc.terminate()
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill()
        for server in servers:
            server.shutdown(); server.server_close()

if __name__=='__main__': main()
