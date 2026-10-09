# -*- coding: utf-8 -*-
"""
panel.py — Tarayıcı tabanlı yönetim paneli (bağımlılık yok, http.server ile).

Açılış:  python wioforge.py panel
Adres :  http://localhost:8080

Panelden yapabileceklerin:
  * WioLand'daki orijinal adresleri listele
  * Tüm depoları aynala / kullanıcı isteğiyle kaynağı yeniden oku
  * Site adresinden CloudStream eklentisi üret
  * GitHub'a yayınla
  * Kaynak Depo (upstream) analizi: içindeki depolar, eklentiler, siteler,
    ayarlar, ikonlar ve çalışma durumları + .cs3 içeriği
  * Yerel test sunucusunu başlat
"""

from __future__ import annotations

import io
import json
import mimetypes
import os
import threading
import time
import webbrowser
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Optional
from urllib.parse import parse_qs, urlparse

from . import utils
from .config import Config

_JOBS: Dict[str, Dict[str, Any]] = {}
_JOB_LOCK = threading.Lock()


# ----------------------------------------------------------------------------
# İş (job) yönetimi — uzun süren komutları arka planda çalıştır
# ----------------------------------------------------------------------------

def _new_job(name: str) -> str:
    jid = f"{int(time.time() * 1000)}-{name}"
    with _JOB_LOCK:
        _JOBS[jid] = {"id": jid, "name": name, "status": "running", "log": "", "started": time.time()}
    return jid


def _append_log(jid: str, text: str) -> None:
    with _JOB_LOCK:
        if jid in _JOBS:
            _JOBS[jid]["log"] += text


def _finish_job(jid: str, status: str = "done") -> None:
    with _JOB_LOCK:
        if jid in _JOBS:
            _JOBS[jid]["status"] = status
            _JOBS[jid]["ended"] = time.time()


def _run_job(name: str, fn: Callable[[Config], Any], cfg: Config) -> str:
    jid = _new_job(name)

    def worker():
        buf = io.StringIO()
        try:
            with redirect_stdout(buf), redirect_stderr(buf):
                result = fn(cfg)
            _append_log(jid, buf.getvalue())
            if isinstance(result, (dict, list)):
                _append_log(jid, "\n" + json.dumps(result, ensure_ascii=False, indent=2)[:20000])
            _finish_job(jid, "done")
        except Exception as e:  # noqa: BLE001
            _append_log(jid, buf.getvalue())
            _append_log(jid, f"\n[HATA] {e}\n")
            _finish_job(jid, "error")

    threading.Thread(target=worker, daemon=True).start()
    return jid


# ----------------------------------------------------------------------------
# HTML
# ----------------------------------------------------------------------------

def _html_page(cfg: Config) -> str:
    mirror = utils.read_json(cfg.data_dir("mirror.json"), default=None) or {}
    inspect = utils.read_json(cfg.data_dir("inspect.json"), default=None) or {}
    builder = utils.read_json(cfg.data_dir("builder.json"), default=None) or {}
    status = {
        "github_user": cfg.github_user,
        "repo_name": cfg.repo_name,
        "source_repo": cfg.source_repo,
        "repo_url": cfg.repo_html_url,
        "raw_repo": f"{cfg.raw_builds_base}/repo.json" if cfg.raw_base else "",
        "total_plugins": mirror.get("total_plugins", 0),
        "downloaded": mirror.get("downloaded", 0),
        "skipped": mirror.get("skipped", 0),
        "mirror_time": mirror.get("generated_at", 0),
        "inspect_exists": bool(inspect.get("summary")),
        "inspect_source": inspect.get("source_repo", ""),
        "builder_exists": bool(builder.get("total_files")),
    }
    return _TEMPLATE.replace("__STATUS__", json.dumps(status, ensure_ascii=False)).replace(
        "__CFG__", json.dumps({
            "github_user": cfg.github_user,
            "github_token": cfg.github_token,
            "repo_name": cfg.repo_name,
            "source_repo": cfg.source_repo,
            "repos_db_url": cfg.repos_db_url,
            "protected_policy": cfg.protected_policy,
            "proxy_base_url": cfg.proxy_base_url,
            "server_port": cfg.server_port,
        }, ensure_ascii=False)
    )


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WioForge — CloudStream Depo Paneli</title>
<style>
  :root{--bg:#0f1117;--card:#171a23;--card2:#1e2230;--fg:#e6e9ef;--mut:#8b93a7;
        --acc:#7c5cff;--acc2:#22c55e;--warn:#f59e0b;--err:#ef4444;--bd:#2a2f3e}
  *{box-sizing:border-box}
  body{margin:0;font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif;background:var(--bg);color:var(--fg)}
  header{padding:18px 24px;background:linear-gradient(90deg,#1a1030,#12141c);border-bottom:1px solid var(--bd);
         display:flex;align-items:center;gap:14px;flex-wrap:wrap}
  header h1{margin:0;font-size:20px}
  .badge{background:var(--acc);padding:3px 10px;border-radius:999px;font-size:12px}
  .wrap{max-width:1180px;margin:0 auto;padding:22px;display:grid;grid-template-columns:1fr 1fr;gap:18px}
  @media(max-width:900px){.wrap{grid-template-columns:1fr}}
  .card{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:18px}
  .card h2{margin:0 0 12px;font-size:15px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em}
  .full{grid-column:1/-1}
  label{display:block;font-size:13px;color:var(--mut);margin:10px 0 4px}
  input,select{width:100%;padding:10px;border-radius:9px;border:1px solid var(--bd);background:var(--card2);color:var(--fg);font-size:14px}
  button{cursor:pointer;border:none;border-radius:9px;padding:11px 15px;font-size:14px;font-weight:600;
         background:var(--acc);color:#fff;margin:6px 6px 0 0;transition:.15s}
  button:hover{filter:brightness(1.15)}
  button.sec{background:var(--card2);border:1px solid var(--bd);color:var(--fg)}
  button.ok{background:var(--acc2)}
  button.warn{background:var(--warn);color:#1a1200}
  button.sm{padding:7px 12px;font-size:13px}
  .stat{display:flex;gap:10px;flex-wrap:wrap}
  .stat .s{background:var(--card2);border:1px solid var(--bd);border-radius:10px;padding:12px 16px;min-width:110px}
  .stat .s b{display:block;font-size:22px}
  .stat .s span{font-size:12px;color:var(--mut)}
  pre{background:#0a0c12;border:1px solid var(--bd);border-radius:10px;padding:14px;max-height:420px;overflow:auto;
      font-size:12.5px;line-height:1.5;white-space:pre-wrap;word-break:break-word}
  .muted{color:var(--mut);font-size:13px}
  .pill{display:inline-block;background:var(--card2);border:1px solid var(--bd);border-radius:8px;padding:4px 9px;font-size:12px;margin:3px 3px 0 0}
  a{color:#a99bff}
  .row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
  .spinner{display:none;width:16px;height:16px;border:2px solid #fff5;border-top-color:#fff;border-radius:50%;animation:sp .8s linear infinite}
  @keyframes sp{to{transform:rotate(360deg)}}
  .tabs{max-width:1180px;margin:0 auto;display:flex;gap:6px;padding:12px 22px 0;flex-wrap:wrap}
  .tab{padding:9px 16px;border-radius:10px 10px 0 0;background:var(--card);border:1px solid var(--bd);border-bottom:none;
       cursor:pointer;font-size:14px;color:var(--mut)}
  .tab.active{background:var(--card2);color:var(--fg);font-weight:600}
  .hide{display:none}
  .tblwrap{max-height:540px;overflow:auto;border:1px solid var(--bd);border-radius:10px}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--bd);vertical-align:middle}
  th{position:sticky;top:0;background:#12141c;color:var(--mut);font-weight:600;z-index:1}
  tr.pl{cursor:pointer}
  tr.pl:hover{background:var(--card2)}
  tr.pl.sel{background:#241f3a}
  .ico{width:28px;height:28px;border-radius:7px;object-fit:cover;background:#0a0c12;border:1px solid var(--bd)}
  .pill.g{background:#14351f;color:#5ee08a}
  .pill.r{background:#3a1717;color:#ff8a8a}
  .pill.y{background:#3a2f12;color:#ffcf6b}
  .pill.b{background:#1b2440;color:#9db4ff}
  .okc{color:var(--acc2)}.err{color:var(--err)}.warnc{color:var(--warn)}
  .site{font-size:12px;color:#a99bff;word-break:break-all}
  .chips{display:flex;gap:6px;flex-wrap:wrap}
  .chip{background:var(--card2);border:1px solid var(--bd);border-radius:999px;padding:3px 9px;font-size:11.5px}
  .kv{display:grid;grid-template-columns:150px 1fr;gap:6px 12px;font-size:13px}
  .kv .k{color:var(--mut)}
  .det-head{display:flex;gap:14px;align-items:center;margin-bottom:12px}
  .det-head img{width:64px;height:64px;border-radius:12px;object-fit:cover;background:#0a0c12;border:1px solid var(--bd)}
  .det-head h3{margin:0;font-size:18px}
  .det-sec{margin-top:14px}
  .det-sec h4{margin:0 0 6px;font-size:13px;color:var(--mut);text-transform:uppercase;letter-spacing:.05em}
  .listbox{background:#0a0c12;border:1px solid var(--bd);border-radius:10px;padding:10px;max-height:220px;overflow:auto;font-size:12.5px}
  .listbox div{padding:2px 0;word-break:break-all}
  .searchbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
  .searchbar input{max-width:320px}
  .toggle{display:flex;gap:6px;align-items:center;font-size:13px;color:var(--mut)}
</style>
</head>
<body>
<header>
  <h1>⚡ WioForge</h1>
  <span class="badge">CloudStream Depo &amp; Eklenti Paneli</span>
  <span class="muted" id="hdrStatus"></span>
</header>

<div class="tabs">
  <div class="tab active" data-tab="genel" onclick="showTab('genel')">🏠 Genel</div>
  <div class="tab" data-tab="kaynak" onclick="showTab('kaynak')">🔎 Kaynak Depo Analizi</div>
  <div class="tab" data-tab="builder" onclick="showTab('builder')">🧩 Builder</div>
  <div class="tab" data-tab="log" onclick="showTab('log')">📜 Günlük</div>
</div>

<!-- ============================ GENEL ============================ -->
<div class="wrap" id="tab-genel">

  <div class="card">
    <h2>Durum</h2>
    <div class="stat" id="stats"></div>
    <p class="muted" id="repoLine" style="margin-top:12px"></p>
  </div>

  <div class="card">
    <h2>GitHub Ayarları</h2>
    <label>GitHub Kullanıcı Adı</label>
    <input id="github_user" placeholder="kullanici">
    <label>Kişisel Erişim Token'ı (repo izni)</label>
    <input id="github_token" type="password" placeholder="ghp_...">
    <label>Depo Adı</label>
    <input id="repo_name" placeholder="WioRepo">
    <label>Kaynak Depo (upstream)</label>
    <input id="source_repo">
    <div class="row" style="margin-top:12px">
      <button class="ok" onclick="saveCfg()">💾 Kaydet</button>
    </div>
  </div>

  <div class="card full">
    <h2>İşlemler</h2>
    <div class="row">
      <button class="sec" onclick="run('list')">🔍 Orijinal Adresleri Bul</button>
      <button onclick="run('mirror')">📦 Depoları Aynala</button>
      <button onclick="run('update')">🔄 Otomatik Güncelle</button>
      <button class="ok" onclick="run('publish_mirror')">🚀 Aynayı GitHub'a Yükle</button>
    </div>
    <div class="row" style="margin-top:14px">
      <input id="site_url" placeholder="https://www.dizimom.wiki" style="flex:1;min-width:240px">
      <input id="provider_name" placeholder="Provider adı (ör. DiziMom)" style="max-width:230px">
      <button class="ok" onclick="run('generate')">🧩 Eklenti Üret</button>
      <button onclick="run('publish_generated')">🚀 Eklentiyi Yükle</button>
    </div>
    <div class="row" style="margin-top:14px">
      <button class="sec" onclick="run('serve')">🖥️ Yerel Test Sunucusu</button>
      <button class="warn" onclick="run('status')">📊 Durumu Yenile</button>
      <span class="spinner" id="spinner"></span>
    </div>
  </div>

</div>

<!-- ====================== KAYNAK DEPO ANALİZİ ====================== -->
<div class="wrap hide" id="tab-kaynak">

  <div class="card full">
    <h2>Kaynak Depo (Upstream) Analizi</h2>
    <p class="muted" style="margin-top:0">
      Bir CloudStream deposu (upstream) linki gir. Panel; içindeki tüm depoları ve eklentileri bulur,
      her eklentinin <b>sitelerini</b>, <b>ayarlarını</b>, <b>resmini (ikon)</b> ve <b>çalışıp çalışmadığını</b>
      gösterir. Ayrıca her <b>.cs3 dosyasının içeriğini</b> (manifest + sınıflar + metinler) çözümler.
    </p>
    <div class="row">
      <input id="inspect_source" style="flex:1;min-width:280px" placeholder="https://github.com/Wiojelt/WioLand">
      <button class="ok" onclick="runInspect(false)">🔎 Analiz Et</button>
      <button class="sec" onclick="runInspect(true)">⚡ Hızlı (site testi yok)</button>
      <button class="sec" onclick="loadInspect()">🔄 Raporu Yenile</button>
    </div>
    <div class="row" style="margin-top:10px">
      <span class="spinner" id="spinner2"></span>
      <span class="muted" id="inspectMeta"></span>
    </div>
  </div>

  <div class="card full" id="inspectSummaryCard" style="display:none">
    <h2>Özet</h2>
    <div class="stat" id="inspectStats"></div>
    <div id="inspectRepos" style="margin-top:14px"></div>
  </div>

  <div class="card full" id="inspectListCard" style="display:none">
    <h2>Eklentiler</h2>
    <div class="searchbar">
      <input id="inspSearch" placeholder="Ara: ad, site, sınıf..." oninput="renderTable()">
      <label class="toggle"><input type="checkbox" id="onlyWorking" onchange="renderTable()" style="width:auto"> Sadece çalışanlar</label>
      <label class="toggle"><input type="checkbox" id="onlyMainSite" onchange="renderTable()" style="width:auto"> Sadece ana sitesi olanlar</label>
      <span class="muted" id="inspCount"></span>
    </div>
    <div class="tblwrap">
      <table>
        <thead><tr>
          <th style="width:36px"></th>
          <th>Ad</th><th>Sürüm</th><th>Dil</th>
          <th>Ana Site</th><th>.cs3</th><th>Site Durumu</th>
        </tr></thead>
        <tbody id="inspBody"></tbody>
      </table>
    </div>
  </div>

  <div class="card full" id="inspectDetailCard" style="display:none">
    <h2>Eklenti Detayı</h2>
    <div id="inspectDetail"></div>
  </div>

</div>

<!-- ======================= CLOUDSTREAM-BUILDER ======================= -->
<div class="wrap hide" id="tab-builder">

  <div class="card full">
    <h2>GitHub'a Yayınla / CloudStream Kısa Kodu</h2>
    <p class="muted">Genel sekmesinde ürettiğiniz eklenti projesini seçin. GitHub hesabınızda herkese açık depo yoksa oluşturulur ve proje yüklenir. GitHub kullanıcı adı ve token Genel sekmesinden alınır.</p>
    <label>Üretilmiş proje</label>
    <select id="builderProject"><option value="">Projeler yükleniyor...</option></select>
    <label>GitHub depo adı</label>
    <input id="builderRepo" placeholder="kaos" maxlength="100">
    <label>CloudStream kısa kodu (isteğe bağlı)</label>
    <input id="builderShortcode" placeholder="!kaos" maxlength="65">
    <p class="muted">! kodları py.md üzerinden çalışır. Kodun kaydı bu harici serviste yapılmalıdır; buraya yazmak kodu rezerve etmez. Doğrulama kodun yayınlanan depo adresine yönlendiğini kontrol eder.</p>
    <div class="row">
      <button class="ok" onclick="runBuilderPublish('builder_publish')">🚀 Depo Oluştur / Projeyi Yükle</button>
      <a class="muted" href="https://py.md/" target="_blank" rel="noopener noreferrer">Kısa kod servisini aç</a>
      <button class="sec" onclick="runBuilderPublish('builder_shortcode')">Kısa Kodu Doğrula</button>
    </div>
    <div id="builderPublication" style="margin-top:14px"></div>
  </div>


  <div class="card full">
    <h2>CloudStream-Builder (Eklenti Oluşturucu Kütüphanesi)</h2>
    <p class="muted" style="margin-top:0">
      <b>Wiojelt/CloudStream-Builder</b> deposunu indirir ve içeriğini gösterir:
      <b>OCE JSON config'leri</b>, <b>OCE Kotlin extractor'ları</b>, <b>yerli (Türk) extractor'lar</b>,
      <b>çekirdek motorlar</b>, <b>referans rehberleri</b> ve <b>yardımcı script'ler</b>.
      Bir extractor veya rehbere tıklayarak içeriğini okuyabilirsin.
    </p>
    <div class="row">
      <input id="builder_source" style="flex:1;min-width:280px" placeholder="https://github.com/Wiojelt/CloudStream-Builder">
      <button class="ok" onclick="runBuilder()">⬇️ İndir / Güncelle</button>
      <button class="sec" onclick="loadBuilder()">🔄 Raporu Yenile</button>
    </div>
    <div class="row" style="margin-top:10px">
      <span class="spinner" id="spinner3"></span>
      <span class="muted" id="builderMeta"></span>
    </div>
  </div>

  <div class="card full" id="builderSummaryCard" style="display:none">
    <h2>Özet</h2>
    <div class="stat" id="builderStats"></div>
    <div id="builderIndex" style="margin-top:14px"></div>
  </div>

  <div class="card full" id="builderFilesCard" style="display:none">
    <h2>Extractor Kütüphanesi &amp; Dosyalar</h2>
    <div class="searchbar">
      <input id="builderSearch" placeholder="Ara: extractor, host, dosya..." oninput="renderBuilder()">
      <select id="builderCat" onchange="renderBuilder()" style="max-width:290px">
        <option value="all">Tüm kategoriler</option>
        <option value="extractors">Extractor'lar (JSON + Kotlin + Yerli)</option>
        <option value="oce_configs">OCE JSON Config</option>
        <option value="oce_kotlin">OCE Kotlin Extractor</option>
        <option value="oce_core">OCE Çekirdek</option>
        <option value="turk">Yerli (Türk) Extractor</option>
        <option value="references">Referans Rehberleri</option>
        <option value="scripts">Yardımcı Script'ler</option>
        <option value="skill">Skill / Katalog</option>
        <option value="other">Diğer</option>
      </select>
      <span class="muted" id="builderCount"></span>
    </div>
    <div class="tblwrap">
      <table>
        <thead><tr><th>Ad</th><th>Tür</th><th>Host / URL</th><th>Dosya</th><th>Boyut</th></tr></thead>
        <tbody id="builderBody"></tbody>
      </table>
    </div>
  </div>

  <div class="card full" id="builderViewCard" style="display:none">
    <h2 id="builderViewTitle">Dosya</h2>
    <pre id="builderViewBody" style="max-height:560px"></pre>
    <div class="row" style="margin-top:10px">
      <button class="sec sm" onclick="document.getElementById('builderViewCard').style.display='none'">Kapat</button>
    </div>
  </div>

</div>

<!-- ============================= LOG ============================= -->
<div class="wrap hide" id="tab-log">
  <div class="card full">
    <h2>Günlük / Çıktı</h2>
    <pre id="log">Hazır. Bir işlem seç.</pre>
  </div>
</div>

<script>
const STATUS = __STATUS__;
const CFG = __CFG__;

// ------------------------- Sekmeler -------------------------
function showTab(name){
  for(const t of ['genel','kaynak','builder','log']){
    document.getElementById('tab-'+t).classList.toggle('hide', t!==name);
  }
  document.querySelectorAll('.tab').forEach(el=>el.classList.toggle('active', el.dataset.tab===name));
  if(name==='kaynak'){ loadInspect(); }
  if(name==='builder'){ loadBuilder(); loadBuilderPublication(); }
}

// ------------------------- Genel -------------------------
function render(){
  document.getElementById('stats').innerHTML = `
    <div class="s"><b>${STATUS.total_plugins}</b><span>Toplam Eklenti</span></div>
    <div class="s"><b>${STATUS.downloaded}</b><span>İndirilen .cs3</span></div>
    <div class="s"><b>${STATUS.skipped}</b><span>Atlanan</span></div>
    <div class="s"><b>${STATUS.mirror_time?new Date(STATUS.mirror_time*1000).toLocaleString('tr-TR'):'-'}</b><span>Son Ayna</span></div>`;
  document.getElementById('hdrStatus').textContent = STATUS.github_user ? ('@'+STATUS.github_user+'/'+STATUS.repo_name) : 'GitHub ayarlanmadı';
  document.getElementById('repoLine').innerHTML = STATUS.raw_repo
    ? 'CloudStream depo adresi: <a href="'+STATUS.raw_repo+'" target="_blank">'+STATUS.raw_repo+'</a>'
    : 'Önce GitHub ayarlarını kaydet.';
  for(const k of ['github_user','github_token','repo_name','source_repo']){
    const el=document.getElementById(k); if(el) el.value = CFG[k]||'';
  }
  const isrc = document.getElementById('inspect_source');
  if(isrc) isrc.value = STATUS.inspect_source || CFG.source_repo || 'https://github.com/Wiojelt/WioLand';
  const bsrc = document.getElementById('builder_source');
  if(bsrc) bsrc.value = 'https://github.com/Wiojelt/CloudStream-Builder';
}
render();

async function saveCfg(){
  const body={};
  for(const k of ['github_user','github_token','repo_name','source_repo']) body[k]=document.getElementById(k).value;
  const r=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const j=await r.json(); log(j.message||'Kaydedildi'); setTimeout(()=>location.reload(),800);
}

// ------------------------- İşlem çalıştırma -------------------------
let timer=null;
async function run(cmd){
  const payload={cmd};
  if(['list','mirror','update'].includes(cmd)) payload.source=document.getElementById('source_repo').value.trim();
  payload.site_url=document.getElementById('site_url')?.value||'';
  payload.provider_name=document.getElementById('provider_name')?.value||'';
  document.getElementById('spinner').style.display='inline-block';
  showTab('log');
  log('İşlem başlatıldı, çıktı bekleniyor...');
  const r=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const j=await r.json();
  if(j.job){ poll(j.job); } else { log(j.message||'Hata'); }
}
async function poll(job){
  const r=await fetch('/api/job?id='+encodeURIComponent(job));
  const j=await r.json();
  log(j.log && j.log.trim() ? j.log : 'Çalışıyor...');
  if(j.status==='running'){ timer=setTimeout(()=>poll(job),900); }
  else { document.getElementById('spinner').style.display='none'; if(j.status==='done') setTimeout(()=>location.reload(),1500); }
}
function log(t){ const el=document.getElementById('log'); el.textContent=t; el.scrollTop=el.scrollHeight; }

// ------------------------- Kaynak Depo Analizi -------------------------
let INSPECT = null;
let INSPECT_TIMER = null;

async function runInspect(quick){
  const src = document.getElementById('inspect_source').value.trim();
  document.getElementById('spinner2').style.display='inline-block';
  document.getElementById('inspectMeta').textContent = 'Analiz başlatılıyor...';
  const payload = {cmd:'inspect', source: src, no_sites: quick};
  const r = await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const j = await r.json();
  if(j.job){ pollInspect(j.job); } else { document.getElementById('inspectMeta').textContent = j.message||'Hata'; }
}

async function pollInspect(job){
  const r = await fetch('/api/job?id='+encodeURIComponent(job));
  const j = await r.json();
  const lines = (j.log||'').trim().split('\n');
  document.getElementById('inspectMeta').textContent = lines[lines.length-1] || 'Çalışıyor...';
  if(j.status==='running'){ INSPECT_TIMER = setTimeout(()=>pollInspect(job), 1200); }
  else {
    document.getElementById('spinner2').style.display='none';
    document.getElementById('inspectMeta').textContent = 'Analiz tamamlandı.';
    loadInspect();
  }
}

async function loadInspect(){
  try{
    const r = await fetch('/api/inspect_data');
    const j = await r.json();
    if(!j.exists){ document.getElementById('inspectMeta').textContent = j.message || 'Rapor yok.'; return; }
    INSPECT = j;
    renderInspect();
  }catch(e){ document.getElementById('inspectMeta').textContent = 'Rapor yüklenemedi.'; }
}

function fmtDate(ts){ return ts ? new Date(ts*1000).toLocaleString('tr-TR') : '-'; }
function esc(s){ return String(s==null?'':s).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function siteState(s){ return s.state || (s.ok ? 'ok' : 'dead'); }

function renderInspect(){
  const s = INSPECT.summary || {};
  document.getElementById('inspectSummaryCard').style.display='';
  document.getElementById('inspectListCard').style.display='';
  document.getElementById('inspectStats').innerHTML = `
    <div class="s"><b>${s.total_repos||0}</b><span>Depo</span></div>
    <div class="s"><b>${s.total_plugins||0}</b><span>Eklenti</span></div>
    <div class="s"><b class="okc">${s.working||0}</b><span>Çalışıyor</span></div>
    <div class="s"><b class="${s.broken?'err':''}">${s.broken||0}</b><span>Çalışmıyor</span></div>
    <div class="s"><b>${s.icons||0}</b><span>İkon</span></div>
    <div class="s"><b class="okc">${s.sites_working||0}</b><span>Açık Site</span></div>
    <div class="s"><b class="warnc">${s.sites_protected||0}</b><span>Korumalı Site</span></div>
    <div class="s"><b>${s.sites_total||0}</b><span>Toplam Site</span></div>
    <div class="s"><b>${fmtDate(INSPECT.generated_at)}</b><span>Analiz Zamanı</span></div>`;

  let rh = '<div class="kv" style="grid-template-columns:1fr">';
  rh += '<div class="muted">Kaynak: <a href="'+esc(INSPECT.source_repo)+'" target="_blank">'+esc(INSPECT.source_repo)+'</a></div>';
  rh += '<div class="chips" style="margin-top:8px">';
  for(const r of (INSPECT.repos||[])){
    rh += '<span class="chip">'+(r.ok?'✅':'⚠️')+' '+esc(r.name||r.repo_json)+' · '+r.plugin_count+' eklenti</span>';
  }
  rh += '</div></div>';
  document.getElementById('inspectRepos').innerHTML = rh;

  renderTable();
}

function pluginSearchBlob(p){
  return [p.name,p.internal_name,p.primary_site,(p.sites||[]).map(x=>x.host).join(' '),
          (p.classes||[]).join(' '),p.description,p.language].join(' ').toLowerCase();
}

function renderTable(){
  if(!INSPECT) return;
  const q = (document.getElementById('inspSearch').value||'').toLowerCase().trim();
  const onlyW = document.getElementById('onlyWorking').checked;
  const onlyMain = document.getElementById('onlyMainSite').checked;
  const rows = [];
  for(let i=0;i<(INSPECT.plugins||[]).length;i++){
    const p = INSPECT.plugins[i];
    if(onlyW && !p.cs3_ok) continue;
    if(onlyMain && !p.primary_site) continue;
    if(q && pluginSearchBlob(p).indexOf(q)===-1) continue;
    rows.push({i,p});
  }
  document.getElementById('inspCount').textContent = rows.length + ' / ' + (INSPECT.plugins||[]).length + ' eklenti';
  const body = document.getElementById('inspBody');
  body.innerHTML = rows.map(({i,p})=>{
    const icon = p.icon_local ? ('/api/asset?f='+encodeURIComponent(p.icon_local)) : '';
    const cs3 = p.cs3_ok ? '<span class="pill g">çalışıyor</span>' : '<span class="pill r">çalışmıyor</span>';
    const sites = p.sites||[];
    const okSites = sites.filter(x=>siteState(x)==='ok').length;
    const protSites = sites.filter(x=>siteState(x)==='protected').length;
    const cls = okSites ? 'g' : (protSites ? 'y' : 'r');
    const sitePill = sites.length ? `<span class="pill ${cls}">${okSites}✓${protSites?' '+protSites+'🛡':''} / ${sites.length}</span>` : '<span class="pill y">-</span>';
    const mainSite = p.primary_site ? `<span class="site">${esc(p.primary_site)}</span>` : '<span class="muted">-</span>';
    return `<tr class="pl" onclick="showDetail(${i})">
      <td>${icon?`<img class="ico" src="${icon}" loading="lazy" onerror="this.style.visibility='hidden'">`:'<div class="ico"></div>'}</td>
      <td><b>${esc(p.name)}</b><br><span class="muted">${esc(p.internal_name)}</span></td>
      <td>v${p.version}</td>
      <td>${esc(p.language||'-')}</td>
      <td>${mainSite}</td>
      <td>${cs3}</td>
      <td>${sitePill}</td>
    </tr>`;
  }).join('') || '<tr><td colspan="7" class="muted">Sonuç yok.</td></tr>';
}

function showDetail(i){
  const p = INSPECT.plugins[i];
  document.querySelectorAll('tr.pl').forEach(el=>el.classList.remove('sel'));
  const card = document.getElementById('inspectDetailCard');
  card.style.display='';
  const icon = p.icon_local ? ('/api/asset?f='+encodeURIComponent(p.icon_local)) : '';
  const statusTxt = p.status==1?'✅ Aktif':(p.status==0?'⛔ Kapalı':'Durum: '+p.status);
  const sites = (p.sites||[]).map(s=>{
    const stt = siteState(s);
    let col='muted', st='test edilmedi';
    if(stt==='ok'){ col='okc'; st='HTTP '+s.http_status+' ✓ açık'; }
    else if(stt==='protected'){ col='warnc'; st='HTTP '+s.http_status+' 🛡 korumalı (bot engeli)'; }
    else if(stt==='dead'){ col='err'; st='HTTP '+s.http_status+' ✗ erişilemez'; }
    const role = s.role==='aux'?'<span class="pill b">yardımcı</span> ':'';
    return `<div>${role}<a href="${esc(s.url)}" target="_blank">${esc(s.url)}</a> — <span class="${col}">${st}</span></div>`;
  }).join('') || '<div class="muted">Site bulunamadı.</div>';

  const classes = (p.classes||[]).map(c=>`<div>${esc(c)}</div>`).join('') || '<div class="muted">-</div>';
  const strings = (p.strings||[]).map(c=>`<div>${esc(c)}</div>`).join('') || '<div class="muted">-</div>';
  const allUrls = (p.all_urls||[]).map(c=>`<div><a href="${esc(c)}" target="_blank">${esc(c)}</a></div>`).join('') || '<div class="muted">-</div>';

  document.getElementById('inspectDetail').innerHTML = `
    <div class="det-head">
      ${icon?`<img src="${icon}" onerror="this.style.visibility='hidden'">`:'<div class="ico" style="width:64px;height:64px"></div>'}
      <div>
        <h3>${esc(p.name)}</h3>
        <div class="muted">${esc(p.internal_name)} · v${p.version} · ${statusTxt}</div>
        <div class="chips" style="margin-top:6px">
          ${(p.tv_types||[]).map(t=>`<span class="chip">${esc(t)}</span>`).join('')}
          ${(p.authors||[]).map(a=>`<span class="chip">👤 ${esc(a)}</span>`).join('')}
          <span class="chip">🌐 ${esc(p.language||'-')}</span>
        </div>
      </div>
    </div>
    <p>${esc(p.description||'')}</p>

    <div class="det-sec"><h4>Ayarlar / Bilgiler</h4>
      <div class="kv">
        <div class="k">Paket / Sınıf</div><div>${esc(p.plugin_class_name||'-')}</div>
        <div class="k">API sürümü</div><div>${esc(p.api_version||'-')}</div>
        <div class="k">Kaynak gereği</div><div>${p.requires_resources?'Evet':'Hayır'}</div>
        <div class="k">Durum</div><div>${statusTxt}</div>
        <div class="k">Türler</div><div>${esc((p.tv_types||[]).join(', ')||'-')}</div>
        <div class="k">Yazarlar</div><div>${esc((p.authors||[]).join(', ')||'-')}</div>
        <div class="k">Dosya boyutu</div><div>${p.file_size?Math.round(p.file_size/1024)+' KB':'-'}</div>
        <div class="k">Hash</div><div style="word-break:break-all">${esc(p.file_hash||'-')}</div>
        <div class="k">.cs3 adresi</div><div style="word-break:break-all"><a href="${esc(p.url)}" target="_blank">${esc(p.url)}</a></div>
        <div class="k">Depo</div><div style="word-break:break-all"><a href="${esc(p.repository_url)}" target="_blank">${esc(p.repository_url)}</a></div>
      </div>
    </div>

    <div class="det-sec"><h4>Siteler (${(p.sites||[]).length})</h4><div class="listbox">${sites}</div></div>

    <div class="det-sec"><h4>.cs3 İçeriği — Manifest</h4>
      <pre>${esc(JSON.stringify(p.manifest||{}, null, 2))}</pre>
    </div>

    <div class="det-sec"><h4>Sınıflar (${(p.classes||[]).length})</h4><div class="listbox">${classes}</div></div>

    <div class="det-sec"><h4>Metinler / Ayarlar (${(p.strings||[]).length})</h4><div class="listbox">${strings}</div></div>

    <div class="det-sec"><h4>Tüm Adresler (${(p.all_urls||[]).length})</h4><div class="listbox">${allUrls}</div></div>

    <div class="row" style="margin-top:14px">
      <button class="sec sm" onclick="document.getElementById('inspectDetailCard').style.display='none'">Kapat</button>
    </div>
  `;
  card.scrollIntoView({behavior:'smooth', block:'start'});
}

// ------------------------- CloudStream-Builder -------------------------
let BUILDER = null;


async function loadBuilderPublication(){
  const el=document.getElementById('builderPublication');
  try{
    const r=await fetch('/api/builder_publication');
    if(!r.ok) throw new Error('Yayın bilgisi alınamadı.');
    const data=await r.json();
    const select=document.getElementById('builderProject');
    const selected=select.value;
    select.replaceChildren(new Option('Proje seçin',''));
    for(const name of data.projects||[]) select.add(new Option(name,name));
    if(selected) select.value=selected;
    if(!data.projects?.length) select.options[0].text='Önce Genel sekmesinden eklenti üretin';
    const p=data.publication;
    el.replaceChildren();
    if(!p) return;
    if(!document.getElementById('builderShortcode').value) document.getElementById('builderShortcode').value=p.shortcode?.code||'';
    for(const [label,url] of [['GitHub deposu',p.repo_url],['CloudStream depo adresi',p.manifest_url],['Derleme durumu',p.actions_url]]){
      const row=document.createElement('p');
      row.append(label+': ');
      const a=document.createElement('a');
      if(url?.startsWith('https://')){a.href=url;a.target='_blank';a.rel='noopener noreferrer';}
      a.textContent=url||'';row.append(a);el.append(row);
    }
    const note=document.createElement('p');
    note.textContent=p.message||'';el.append(note);
    const short=document.createElement('p');
    short.textContent=(p.shortcode?.code||'Kısa kod')+' — '+(p.shortcode?.verified?'Hedef doğrulandı. ': 'Doğrulanmadı. ')+(p.shortcode?.message||'');
    el.append(short);
  }catch(e){el.textContent=e.message;}
}
async function runBuilderPublish(cmd){
  const payload={cmd,project:document.getElementById('builderProject').value,
    repo:document.getElementById('builderRepo').value.trim(),shortcode:document.getElementById('builderShortcode').value.trim()};
  const el=document.getElementById('builderPublication');
  if(cmd==='builder_publish'&&(!payload.project||!payload.repo)){el.textContent='Proje seçin ve GitHub depo adını girin.';return;}
  if(cmd==='builder_shortcode'&&!payload.shortcode){el.textContent='Doğrulanacak kısa kodu girin.';return;}
  try{
    const r=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const j=await r.json();
    if(!j.job) throw new Error(j.message||'İşlem başlatılamadı.');
    showTab('log');document.getElementById('spinner').style.display='inline-block';
    log('Yayın işlemi başlatıldı...');poll(j.job);
  }catch(e){el.textContent=e.message;}
}

async function runBuilder(){
  const src = document.getElementById('builder_source').value.trim();
  document.getElementById('spinner3').style.display='inline-block';
  document.getElementById('builderMeta').textContent = 'Builder indiriliyor...';
  const payload = {cmd:'builder', source: src};
  const r = await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const j = await r.json();
  if(j.job){ pollBuilder(j.job); } else { document.getElementById('builderMeta').textContent = j.message||'Hata'; }
}

async function pollBuilder(job){
  const r = await fetch('/api/job?id='+encodeURIComponent(job));
  const j = await r.json();
  const lines = (j.log||'').trim().split('\n');
  document.getElementById('builderMeta').textContent = lines[lines.length-1] || 'Çalışıyor...';
  if(j.status==='running'){ setTimeout(()=>pollBuilder(job), 1200); }
  else {
    document.getElementById('spinner3').style.display='none';
    document.getElementById('builderMeta').textContent = 'Builder hazır.';
    loadBuilder();
  }
}

async function loadBuilder(){
  try{
    const r = await fetch('/api/builder_data');
    const j = await r.json();
    if(!j.exists){ document.getElementById('builderMeta').textContent = j.message || 'Builder yok.'; return; }
    BUILDER = j;
    renderBuilderSummary();
  }catch(e){ document.getElementById('builderMeta').textContent = 'Builder raporu yüklenemedi.'; }
}

function renderBuilderSummary(){
  const c = BUILDER.counts||{};
  document.getElementById('builderSummaryCard').style.display='';
  document.getElementById('builderFilesCard').style.display='';
  document.getElementById('builderStats').innerHTML = `
    <div class="s"><b>${BUILDER.total_files||0}</b><span>Dosya</span></div>
    <div class="s"><b>${c.oce_configs||0}</b><span>JSON Config</span></div>
    <div class="s"><b>${c.oce_kotlin||0}</b><span>OCE Kotlin</span></div>
    <div class="s"><b>${c.oce_core||0}</b><span>OCE Çekirdek</span></div>
    <div class="s"><b>${c.turk||0}</b><span>Yerli Extractor</span></div>
    <div class="s"><b>${c.references||0}</b><span>Referans</span></div>
    <div class="s"><b>${c.scripts||0}</b><span>Script</span></div>
    <div class="s"><b>${fmtDate(BUILDER.fetched_at)}</b><span>İndirme Zamanı</span></div>`;
  let h = '<div class="muted">Kaynak: <a href="'+esc(BUILDER.source_repo)+'" target="_blank">'+esc(BUILDER.source_repo)+'</a> ('+esc(BUILDER.branch||'')+')</div>';
  if((BUILDER.index_rows||[]).length){
    h += '<div class="det-sec"><h4>Extractor Kataloğu (INDEX.md)</h4><div class="listbox">';
    for(const row of BUILDER.index_rows){
      h += '<div>'+(row.extractors||[]).map(e=>'<span class="chip">'+esc(e)+'</span>').join(' ')
         + ' <span class="site">'+esc((row.hosts||[]).join(', '))+'</span>'
         + (row.note?' <span class="muted">— '+esc(row.note)+'</span>':'')+'</div>';
    }
    h += '</div></div>';
  }
  document.getElementById('builderIndex').innerHTML = h;
  renderBuilder();
}

function builderRows(){
  if(!BUILDER) return [];
  const cat = document.getElementById('builderCat').value;
  const q = (document.getElementById('builderSearch').value||'').toLowerCase().trim();
  const rows = [];
  if(cat==='all' || cat==='extractors'){
    for(const e of (BUILDER.extractors||[])){
      if(cat==='extractors' && !['json-config','kotlin','turk'].includes(e.kind)) continue;
      rows.push({name:e.name, kind:e.kind, host:e.main_url||'', file:e.file, size:e.size});
    }
  }
  if(cat!=='extractors'){
    const cats = (cat==='all') ? ['oce_core','references','scripts','skill','other','oce_docs'] : [cat];
    for(const ck of cats){
      const c = (BUILDER.categories||{})[ck];
      if(!c) continue;
      for(const f of (c.files||[])){
        rows.push({name:f.path.split('/').pop(), kind:ck, host:'', file:f.path, size:f.size});
      }
    }
  }
  return rows.filter(r=>{
    if(!q) return true;
    return (r.name+' '+r.kind+' '+r.host+' '+r.file).toLowerCase().indexOf(q)!==-1;
  });
}

function renderBuilder(){
  if(!BUILDER) return;
  const rows = builderRows();
  document.getElementById('builderCount').textContent = rows.length + ' dosya';
  document.getElementById('builderBody').innerHTML = rows.map(r=>{
    const fesc = esc(r.file).replace(/'/g, "\\'");
    return `<tr class="pl" onclick="viewBuilderFile('${fesc}')">
      <td><b>${esc(r.name)}</b></td>
      <td><span class="pill b">${esc(r.kind)}</span></td>
      <td>${r.host?`<span class="site">${esc(r.host)}</span>`:'<span class="muted">-</span>'}</td>
      <td><span class="muted">${esc(r.file)}</span></td>
      <td>${Math.round((r.size||0)/102.4)/10} KB</td>
    </tr>`;
  }).join('') || '<tr><td colspan="5" class="muted">Sonuç yok.</td></tr>';
}

async function viewBuilderFile(f){
  const card = document.getElementById('builderViewCard');
  card.style.display='';
  document.getElementById('builderViewTitle').textContent = f;
  document.getElementById('builderViewBody').textContent = 'Yükleniyor...';
  try{
    const r = await fetch('/api/builder_file?f='+encodeURIComponent(f));
    const t = await r.text();
    document.getElementById('builderViewBody').textContent = t;
  }catch(e){ document.getElementById('builderViewBody').textContent = 'Dosya yüklenemedi.'; }
  card.scrollIntoView({behavior:'smooth', block:'start'});
}
</script>
</body>
</html>
"""


# ----------------------------------------------------------------------------
# HTTP işleyici
# ----------------------------------------------------------------------------

def _make_handler(cfg: Config):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str = "text/html; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def log_message(self, fmt, *args):  # noqa: A003
            pass

        def _serve_asset(self, name: str):
            # Yol geçişini engelle: yalnızca dosya adı (basename)
            safe = os.path.basename(name or "")
            if not safe:
                self._send(404, b"404")
                return
            assets_dir = cfg.data_dir("inspect", "assets")
            path = os.path.join(assets_dir, safe)
            if not os.path.isfile(path):
                self._send(404, b"404")
                return
            ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
            try:
                with open(path, "rb") as fh:
                    data = fh.read()
            except OSError:
                self._send(404, b"404")
                return
            self._send(200, data, ctype)

        def _serve_builder_file(self, relpath: str):
            from . import builder as builder_mod
            data = builder_mod.read_builder_file(cfg, relpath)
            if not data:
                self._send(404, b"404")
                return
            ctype = mimetypes.guess_type(relpath)[0] or "text/plain"
            if ctype.startswith("text/") or ctype in ("application/json", "application/javascript"):
                ctype += "; charset=utf-8"
            self._send(200, data["content"].encode("utf-8", errors="replace"), ctype)

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            if path in ("/", "/index.html"):
                self._send(200, _html_page(cfg).encode())
            elif path == "/api/status":
                self._json(utils.read_json(cfg.data_dir("mirror.json"), default={}) or {})
            elif path == "/api/inspect_data":
                report = utils.read_json(cfg.data_dir("inspect.json"), default=None)
                if not report or not report.get("summary"):
                    self._json({"exists": False, "message": "Henüz analiz raporu yok. 'Analiz Et' düğmesine bas."})
                else:
                    report["exists"] = True
                    self._json(report)
            elif path == "/api/asset":
                qs = parse_qs(parsed.query)
                self._serve_asset((qs.get("f") or [""])[0])
            elif path == "/api/builder_publication":
                from . import builder_publish
                self._json(builder_publish.status(cfg))
            elif path == "/api/builder_data":
                report = utils.read_json(cfg.data_dir("builder.json"), default=None)
                if not report or not report.get("total_files"):
                    self._json({"exists": False, "message": "Henüz builder indirilmedi. 'İndir / Güncelle' düğmesine bas."})
                else:
                    report["exists"] = True
                    self._json(report)
            elif path == "/api/builder_file":
                qs = parse_qs(parsed.query)
                self._serve_builder_file((qs.get("f") or [""])[0])
            elif path == "/api/job":
                qs = parse_qs(parsed.query)
                jid = (qs.get("id") or [""])[0]
                with _JOB_LOCK:
                    self._json(_JOBS.get(jid, {"status": "unknown", "log": ""}))
            else:
                self._send(404, b"404")

        def do_POST(self):
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length", 0))
            try:
                data = json.loads(self.rfile.read(length).decode() or "{}")
            except Exception:  # noqa: BLE001
                data = {}

            if path == "/api/config":
                for k in ("github_user", "github_token", "repo_name", "source_repo"):
                    if k in data:
                        setattr(cfg, k, data[k])
                cfg.save()
                self._json({"message": "Ayarlar kaydedildi."})
            elif path == "/api/run":
                self._handle_run(data)
            else:
                self._send(404, b"404")

        def _handle_run(self, data: Dict[str, Any]):
            cmd = data.get("cmd", "")
            # İçe aktarımlar (döngüsel importu önlemek için burada)
            from . import mirror as mirror_mod
            from . import generator as gen_mod
            from . import publisher as pub_mod
            from . import server as srv_mod
            from . import inspector as insp_mod

            if cmd == "list":
                source = (data.get("source") or "").strip() or cfg.source_repo
                jid = _run_job("list", lambda c: mirror_mod.list_original_addresses(c, source=source), cfg)
            elif cmd in ("mirror", "update"):
                source = (data.get("source") or "").strip() or cfg.source_repo
                job_cfg = replace(cfg, source_repo=source)
                jid = _run_job(cmd, lambda c: mirror_mod.mirror_all(c, download=True), job_cfg)
            elif cmd == "publish_mirror":
                jid = _run_job("publish_mirror", lambda c: pub_mod.publish_mirror(c), cfg)
            elif cmd == "inspect":
                source = (data.get("source") or "").strip() or cfg.source_repo
                if not source:
                    self._json({"message": "Kaynak depo (upstream) adresi gerekli."})
                    return
                no_sites = bool(data.get("no_sites"))
                jid = _run_job(
                    "inspect",
                    lambda c: insp_mod.inspect_upstream(
                        c, source,
                        download_cs3=True, download_icons=True, test_sites=not no_sites,
                    ),
                    cfg,
                )
            elif cmd == "builder_publish":
                from . import builder_publish
                jid = _run_job("builder_publish", lambda c: builder_publish.publish_project(
                    c, data.get("project", ""), data.get("repo", ""), data.get("shortcode", "")), cfg)
            elif cmd == "builder_shortcode":
                from . import builder_publish
                jid = _run_job("builder_shortcode", lambda c: builder_publish.verify_published_shortcode(
                    c, data.get("shortcode", "")), cfg)
            elif cmd == "builder":
                from . import builder as builder_mod
                bsource = (data.get("source") or "").strip() or None
                jid = _run_job(
                    "builder",
                    lambda c: builder_mod.fetch_builder(c, source_repo=bsource),
                    cfg,
                )
            elif cmd == "generate":
                site = (data.get("site_url") or "").strip()
                if not site:
                    self._json({"message": "Site adresi gerekli."})
                    return
                pname = (data.get("provider_name") or "").strip() or None
                jid = _run_job(
                    "generate",
                    lambda c: gen_mod.generate_project(c, site, provider_name=pname).__dict__,
                    cfg,
                )
            elif cmd == "publish_generated":
                gen_dir = cfg.data_dir("generated")
                subdirs = [os.path.join(gen_dir, d) for d in os.listdir(gen_dir)] if os.path.isdir(gen_dir) else []
                subdirs = [d for d in subdirs if os.path.isdir(d)]
                if not subdirs:
                    self._json({"message": "Önce bir eklenti üret."})
                    return
                latest = max(subdirs, key=os.path.getmtime)
                jid = _run_job("publish_generated", lambda c: pub_mod.publish(c, latest), cfg)
            elif cmd == "serve":
                try:
                    srv_mod.serve_background(cfg)
                    jid = _run_job("serve", lambda c: {"message": f"Sunucu http://localhost:{c.server_port} adresinde çalışıyor."}, cfg)
                except OSError as e:
                    self._json({"message": f"Port kullanımda: {e}"})
                    return
            elif cmd == "status":
                jid = _run_job("status", lambda c: utils.read_json(c.data_dir("mirror.json"), default={}) or {}, cfg)
            else:
                self._json({"message": f"Bilinmeyen komut: {cmd}"})
                return
            self._json({"job": jid})

    return Handler


def run_panel(cfg: Config, port: Optional[int] = None, open_browser: bool = True) -> None:
    port = port or cfg.server_port
    utils.title("WioForge Web Paneli")
    utils.info(f"Panel adresi: http://localhost:{port}")
    utils.info("Durdurmak için Ctrl+C")

    if open_browser:
        try:
            threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{port}")).start()
        except Exception:  # noqa: BLE001
            pass

    httpd = ThreadingHTTPServer(("", port), _make_handler(cfg))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        utils.info("Panel kapatıldı.")
