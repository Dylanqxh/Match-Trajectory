"""Real, local runtime smoke checks. Contains no application or model calls."""
from pathlib import Path
import importlib.metadata as metadata
import json
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.shared import Pt
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
import pypdfium2 as pdfium
import pytesseract
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ENV = Path(os.environ['MATCH_TRAJECTORY_ENV_ROOT'])
PATHS = json.loads((ENV/'manifests/paths.json').read_text(encoding='utf-8-sig'))
OUT = ROOT/'artifacts/environment-smoke'
OUT.mkdir(parents=True, exist_ok=True)
report = {'python':sys.version, 'checks':{}, 'failures':[]}


def check(name, fn):
    try:
        report['checks'][name] = fn()
        print('PASS', name, flush=True)
    except Exception as exc:
        report['checks'][name] = {'error':str(exc)}
        report['failures'].append(name)
        print('FAIL', name, str(exc), flush=True)


def imports():
    names = ['fastapi','pydantic','sqlalchemy','alembic','httpx','cryptography',
             'pypdfium2','pillow','python-docx','playwright','pytest','ruff']
    return {name:metadata.version(name) for name in names}


def api_database():
    api=FastAPI()
    @api.get('/health')
    def health():
        return {'status':'ok'}
    assert TestClient(api).get('/health').json()=={'status':'ok'}
    engine=create_engine('sqlite:///'+str(OUT/'smoke.sqlite'))
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE IF NOT EXISTS smoke (value TEXT)'))
        conn.execute(text('DELETE FROM smoke'))
        conn.execute(text("INSERT INTO smoke VALUES ('ok')"))
        assert conn.execute(text('SELECT value FROM smoke')).scalar_one()=='ok'
    engine.dispose()
    return {'fastapi':'ok','sqlite':'ok'}


def pdf_text(path):
    with pdfium.PdfDocument(path) as pdf:
        values=[]
        for index, page in enumerate(pdf):
            tp = page.get_textpage()
            try:
                values.append(tp.get_text_range())
            finally:
                tp.close()
            if index == 0:
                bitmap = page.render(scale=1.4)
                try:
                    bitmap.to_pil().save(path.with_suffix('.page-1.png'))
                finally:
                    bitmap.close()
        return '\n'.join(values), len(pdf)


def browser_pdf():
    font=Path(PATHS['fonts'])/'NotoSansCJKsc-Regular.otf'
    assert font.exists(), 'Bundled CJK font missing'
    html=OUT/'chromium.html'
    html.write_text('<!doctype html><meta charset="utf-8"><style>@font-face{font-family:Smoke;src:url("'+font.as_uri()+'")}body{font-family:Smoke;font-size:20px}</style><h1>环境测试：数据开发与后端研发</h1><p>Match Trajectory 12345</p>',encoding='utf-8')
    target=OUT/'chromium.pdf'
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page()
        page.goto(html.as_uri())
        page.evaluate('document.fonts.ready')
        assert page.evaluate('document.fonts.check("20px Smoke")')
        page.pdf(path=str(target),format='A4',print_background=True)
        page.screenshot(path=str(OUT/'chromium.png'),full_page=True)
        browser.close()
    value,pages=pdf_text(target)
    assert '数据开发' in value and '12345' in value, repr(value)
    assert pages==1
    return {'pages':pages,'file':str(target),'cjk_text':'ok'}


def ocr():
    pytesseract.pytesseract.tesseract_cmd=PATHS['tesseract']
    image=Image.new('RGB',(1300,180),'white')
    font=ImageFont.truetype(str(Path(PATHS['fonts'])/'NotoSansCJKsc-Regular.otf'),62)
    ImageDraw.Draw(image).text((35,35),'环境测试 数据开发 12345',font=font,fill='black')
    image.save(OUT/'ocr.png')
    value=pytesseract.image_to_string(image,lang='chi_sim+eng',config='--psm 6')
    assert '12345' in value and ('数据' in value or '开发' in value), repr(value)
    return {'languages':['chi_sim','eng'],'recognized':value.strip()}


def word():
    document=Document()
    style=document.styles['Normal']
    style.font.name='Microsoft YaHei'
    style.font.size=Pt(14)
    document.add_heading('环境测试',0)
    document.add_paragraph('数据开发与后端研发 Match Trajectory 12345')
    target=OUT/'editable.docx'
    document.save(target)
    assert '数据开发' in '\n'.join(p.text for p in Document(target).paragraphs)
    office_out=OUT/'office'
    office_out.mkdir(exist_ok=True)
    profile=ENV/'office-smoke-profile'
    command=[PATHS['soffice'],'-env:UserInstallation='+profile.as_uri(),'--headless','--convert-to','pdf','--outdir',str(office_out),str(target)]
    completed=subprocess.run(command,capture_output=True,text=True,timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert completed.returncode==0, completed.stdout+completed.stderr
    converted=office_out/'editable.pdf'
    assert converted.exists(), completed.stdout+completed.stderr
    value,pages=pdf_text(converted)
    assert '12345' in value and '数据开发' in value, repr(value)
    return {'docx_editable':True,'converted_pdf':str(converted),'pages':pages}


def node():
    completed=subprocess.run([str(Path(PATHS['node'])/'node.exe'),str(ROOT/'tools/verify-node.mjs')],capture_output=True,text=True,timeout=60)
    assert completed.returncode==0, completed.stdout+completed.stderr
    return json.loads(completed.stdout.strip())


for name, fn in [('imports',imports),('api_and_sqlite',api_database),('node_react_vite',node),('chromium_pdf',browser_pdf),('ocr',ocr),('editable_docx_to_pdf',word)]:
    check(name,fn)
report['output_dir']=str(OUT)
(ENV/'manifests/runtime-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=True,indent=2))
raise SystemExit(bool(report['failures']))
