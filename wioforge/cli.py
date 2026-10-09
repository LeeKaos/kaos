# -*- coding: utf-8 -*-
"""cli.py — WioForge komut satırı arayüzü (Türkçe)."""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import utils
from .config import Config, CONFIG_FILENAME


BANNER = r"""
 __      __.__      ___________                     
/  \    /  \__| ____\_   _____/__________  ____  ____  
\   \/\/   /  |/  _ \|    __)/  _ \_  __ \/ ___\/ __ \ 
 \        /|  (  <_> )     \(  <_> )  | \/ /_/  >  ___/ 
  \__/\  / |__|\____/|___| / \____/|__|  \___  / \___  >
       \/                  \/            /_____/      \/ 
        Bağımsız CloudStream Depo & Eklenti Yönetimi
"""


def _load_cfg(args) -> Config:
    path = getattr(args, "config", None) or CONFIG_FILENAME
    return Config.load(path)


def _save_cfg(cfg: Config, args) -> None:
    path = getattr(args, "config", None) or CONFIG_FILENAME
    cfg.save(path)


# ----------------------------------------------------------------------------
# Komutlar
# ----------------------------------------------------------------------------

def cmd_init(args) -> int:
    utils.title("WioForge — İlk Kurulum")
    cfg = _load_cfg(args)

    print("Bu adımda kendi GitHub hesabını ve depo adını ayarlayacağız.")
    print("(Boş bırakıp Enter'a basarsan mevcut değer korunur.)\n")

    def ask(label, current, secret=False):
        cur = "******" if (secret and current) else (current or "")
        val = input(f"{label} [{cur}]: ").strip()
        return val if val else current

    cfg.github_user = ask("GitHub kullanıcı adın", cfg.github_user)
    cfg.github_token = ask("GitHub token (repo izni)", cfg.github_token, secret=True)
    cfg.repo_name = ask("Depo adı", cfg.repo_name)
    cfg.plugin_author = ask("Eklenti yazar adı", cfg.plugin_author or cfg.github_user)
    cfg.source_repo = ask("Kaynak depo (upstream)", cfg.source_repo)

    print("\nKorumalı (.cs3 indirilemeyen) eklentiler için politika:")
    print("  1) skip  — atla (yalnızca indirilebilenleri aynala)")
    print("  2) keep  — orijinal adresi koru")
    print("  3) proxy — kendi proxy adresine yönlendir")
    pol = input("Seçim [1]: ").strip() or "1"
    cfg.protected_policy = {"1": "skip", "2": "keep", "3": "proxy"}.get(pol, "skip")
    if cfg.protected_policy == "proxy":
        cfg.proxy_base_url = ask("Proxy taban adresi", cfg.proxy_base_url)

    _save_cfg(cfg, args)
    print()
    utils.ok("Kurulum tamamlandı!")
    print(cfg.summary())
    return 0


def cmd_list(args) -> int:
    cfg = _load_cfg(args)
    from . import mirror
    result = mirror.list_original_addresses(cfg, source=getattr(args, "source", None))

    utils.title("Kaynak Depo — Tüm Orijinal Adresler")
    print(f"\n{utils._c('DEPOLAR', utils.C.BOLD)} ({len(result['repos'])})")
    for r in result["repos"]:
        print(f"  • {r['name'] or '(isimsiz)'}")
        print(f"      repo.json : {r['repo_json']}")
        for pl in r["plugin_lists"]:
            print(f"      liste     : {pl}")

    print(f"\n{utils._c('EKLENTİLER', utils.C.BOLD)} ({len(result['plugins'])})")
    for p in result["plugins"]:
        print(f"  • {p['name']} v{p['version']}  [{p['host']}]")
        print(f"      indir : {p['original_url']}")

    if args.json:
        out = args.json if isinstance(args.json, str) else "orijinal_adresler.json"
        utils.write_json(out, result)
        utils.ok(f"JSON kaydedildi: {out}")
    return 0


def cmd_mirror(args) -> int:
    cfg = _load_cfg(args)
    if getattr(args, "source", None):
        cfg.source_repo = args.source.strip()
    from . import mirror
    summary = mirror.mirror_all(cfg, download=not args.no_download)
    utils.title("Ayna Özeti")
    print(f"  Toplam depo   : {summary['total_repos']}")
    print(f"  Toplam eklenti: {summary['total_plugins']}")
    print(f"  İndirilen     : {summary['downloaded']}")
    print(f"  Atlanan       : {summary['skipped']}")
    print(f"  Klasör        : {cfg.data_dir('mirror')}")
    return 0


def cmd_update(args) -> int:
    utils.info("Otomatik güncelleme başlatılıyor (upstream yeniden çekiliyor)...")
    return cmd_mirror(args)


def cmd_generate(args) -> int:
    cfg = _load_cfg(args)
    from . import generator
    proj = generator.generate_project(
        cfg,
        args.site,
        provider_name=args.name,
        tv_types=args.types.split(",") if args.types else None,
        sample_query=args.query,
        icon_url=args.icon or "",
    )
    utils.title("Üretim Tamamlandı")
    print(f"  Sağlayıcı : {proj.provider_class}")
    print(f"  Paket     : {proj.package}")
    print(f"  Klasör    : {proj.output_dir}")
    print(f"\nSonraki adım: 'wioforge publish' ile GitHub'a yükle.")
    return 0


def cmd_publish(args) -> int:
    cfg = _load_cfg(args)
    from . import publisher
    if args.target == "mirror":
        ok = publisher.publish_mirror(cfg)
    else:
        gen_dir = cfg.data_dir("generated")
        target = args.path
        if not target:
            if not os.path.isdir(gen_dir):
                utils.err("Üretilmiş proje yok. Önce 'wioforge generate <site>' çalıştır.")
                return 1
            subs = [os.path.join(gen_dir, d) for d in os.listdir(gen_dir) if os.path.isdir(os.path.join(gen_dir, d))]
            if not subs:
                utils.err("Üretilmiş proje yok.")
                return 1
            target = max(subs, key=os.path.getmtime)
        utils.info(f"Yayınlanacak proje: {target}")
        ok = publisher.publish(cfg, target)
    return 0 if ok else 1


def cmd_serve(args) -> int:
    cfg = _load_cfg(args)
    from . import server
    directory = args.dir or cfg.data_dir("mirror")
    server.serve(cfg, directory=directory, port=args.port)
    return 0


def cmd_panel(args) -> int:
    cfg = _load_cfg(args)
    from . import panel
    panel.run_panel(cfg, port=args.port, open_browser=not args.no_browser)
    return 0


def cmd_inspect(args) -> int:
    """Kaynak depoyu (upstream) analiz eder: eklentiler, siteler, ikonlar, durum."""
    cfg = _load_cfg(args)
    from . import inspector
    report = inspector.inspect_upstream(
        cfg,
        source_repo=args.source or cfg.source_repo,
        download_cs3=not args.no_download,
        download_icons=not args.no_icons,
        test_sites=not args.no_sites,
    )
    s = report["summary"]
    utils.title("Kaynak Depo Analizi \u2014 \u00d6zet")
    print(f"  Kaynak depo     : {report['source_repo']}")
    print(f"  Depo say\u0131s\u0131      : {s['total_repos']}")
    print(f"  Eklenti say\u0131s\u0131   : {s['total_plugins']}")
    print(f"  \u00c7al\u0131\u015f\u0131yor      : {s['working']}")
    print(f"  \u00c7al\u0131\u015fm\u0131yor      : {s['broken']}")
    print(f"  \u0130kon           : {s['icons']}")
    print(f"  Site            : {s['sites_working']}/{s['sites_total']} eri\u015filebilir")
    print(f"\n  Detayl\u0131 rapor  : {cfg.data_dir('inspect', 'inspect.json')}")

    if args.json:
        out = args.json if isinstance(args.json, str) else "inspect.json"
        utils.write_json(out, report)
        utils.ok(f"JSON kaydedildi: {out}")
    return 0


def cmd_builder(args) -> int:
    """CloudStream-Builder deposunu indir/incele (extractor kütüphanesi)."""
    cfg = _load_cfg(args)
    from . import builder as builder_mod

    if args.show:
        data = builder_mod.read_builder_file(cfg, args.show)
        if not data:
            utils.err(f"Builder dosyası bulunamadı: {args.show}")
            return 1
        print(data["content"])
        return 0

    report = builder_mod.fetch_builder(cfg, source_repo=args.source)
    if report.get("error"):
        utils.err(f"Builder alınamadı: {report.get('error')}")
        return 1

    utils.title("CloudStream-Builder — Özet")
    print(f"  Kaynak depo : {report['source_repo']}")
    print(f"  Dal (branch): {report['branch']}")
    print(f"  Dosya       : {report['total_files']} ({utils.human_size(report['total_size'])})")
    c = report["counts"]
    print(f"  JSON config : {c.get('oce_configs', 0)}")
    print(f"  OCE Kotlin  : {c.get('oce_kotlin', 0)}")
    print(f"  OCE çekirdek: {c.get('oce_core', 0)}")
    print(f"  Yerli       : {c.get('turk', 0)}")
    print(f"  Referans    : {c.get('references', 0)}")
    print(f"  Script      : {c.get('scripts', 0)}")
    print(f"\n  Rapor: {cfg.data_dir('builder', 'builder.json')}")

    if args.json:
        out = args.json if isinstance(args.json, str) else "builder.json"
        utils.write_json(out, report)
        utils.ok(f"JSON kaydedildi: {out}")
    return 0


def cmd_builder_publish(args) -> int:
    from . import builder_publish
    report = builder_publish.publish_project(_load_cfg(args), args.project, args.repo, args.shortcode)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_builder_shortcode(args) -> int:
    from . import builder_publish
    report = builder_publish.verify_published_shortcode(_load_cfg(args), args.shortcode)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_independent(args) -> int:
    from . import independent
    cfg = _load_cfg(args)
    request = utils.read_json(args.request, default={})
    if request.get("catalog"):
        report = independent.catalog(cfg, str(request.get("source", "")).strip())
    elif request.get("verify_shortcode"):
        report = independent.verify_shortcode(cfg, request.get("id", ""), request.get("shortcode", ""))
    elif request.get("publish"):
        report = independent.publish(cfg, request.get("id", ""))
    else:
        report = independent.prepare(cfg, request)
    utils.write_json(args.result, report)
    return 0


def cmd_info(args) -> int:
    cfg = _load_cfg(args)
    utils.title("WioForge — Durum")
    print(cfg.summary())
    print(f"  Yapılandırma dosyası: {getattr(args, 'config', None) or CONFIG_FILENAME}")
    summary = utils.read_json(cfg.data_dir("mirror.json"), default=None)
    if summary:
        print(f"\n  Son ayna: {summary.get('downloaded')} indirildi / "
              f"{summary.get('total_plugins')} toplam eklenti")
    else:
        print("\n  Henüz ayna oluşturulmadı.")
    return 0


# ----------------------------------------------------------------------------
# Ayrıştırıcı
# ----------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="wioforge",
        description="WioForge — Bağımsız CloudStream Depo & Eklenti Yönetimi (WioLand'dan bağımsız)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnekler:
  python wioforge.py init                          # İlk kurulum
  python wioforge.py list --json adresler.json     # Orijinal adresleri bul
  python wioforge.py mirror                        # Tüm depoları aynala
  python wioforge.py update                        # Otomatik güncelle
  python wioforge.py generate https://www.dizimom.wiki --name DiziMom
  python wioforge.py publish --target generated    # Eklentiyi GitHub'a yükle
  python wioforge.py publish --target mirror       # Aynayı GitHub'a yükle
  python wioforge.py serve                         # Yerel test sunucusu
  python wioforge.py inspect --source https://github.com/Wiojelt/WioLand
                                                   # Upstream analizi (eklenti+site+ikon)
  python wioforge.py builder                       # CloudStream-Builder extractor kütüphanesi
  python wioforge.py panel                         # Web paneli aç
""",
    )
    p.add_argument("--config", help="Yapılandırma dosyası (varsayılan: wioforge.json)")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("init", help="İlk kurulumu yap").set_defaults(func=cmd_init)

    sp = sub.add_parser("list", help="Kaynak depodaki tüm orijinal adresleri bul")
    sp.add_argument("--source", help="Kaynak depo veya JSON adresi (varsayılan: kayıtlı kaynak)")
    sp.add_argument("--json", nargs="?", const=True, help="Sonucu JSON olarak kaydet")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("mirror", help="Tüm depoları aynala (bağımsız kopya oluştur)")
    sp.add_argument("--source", help="Kaynak depo adresi (varsayılan: kayıtlı kaynak)")
    sp.add_argument("--no-download", action="store_true", help=".cs3 indirme, yalnızca meta veri")
    sp.set_defaults(func=cmd_mirror)

    sp = sub.add_parser("update", help="Kaynağı yeniden indirip aynayı güncelle")
    sp.add_argument("--source", help="Kaynak depo adresi (varsayılan: kayıtlı kaynak)")
    sp.add_argument("--no-download", action="store_true")
    sp.set_defaults(func=cmd_update)

    sp = sub.add_parser("generate", help="Site adresinden CloudStream eklentisi üret")
    sp.add_argument("site", help="Hedef site adresi (ör. https://www.dizimom.wiki)")
    sp.add_argument("--name", help="Sağlayıcı adı (ör. DiziMom)")
    sp.add_argument("--types", help="Türler, virgülle (Movie,TvSeries,Anime,Live)")
    sp.add_argument("--query", default="breaking", help="Analiz için örnek arama")
    sp.add_argument("--icon", help="Eklenti ikon URL'i")
    sp.set_defaults(func=cmd_generate)

    sp = sub.add_parser("publish", help="Üretilen çıktıyı GitHub'a yükle")
    sp.add_argument("--target", choices=["generated", "mirror"], default="generated")
    sp.add_argument("--path", help="Yayınlanacak klasör (opsiyonel)")
    sp.set_defaults(func=cmd_publish)

    sp = sub.add_parser("serve", help="Yerel test sunucusu başlat")
    sp.add_argument("--dir", help="Sunulacak klasör")
    sp.add_argument("--port", type=int, help="Port")
    sp.set_defaults(func=cmd_serve)

    sp = sub.add_parser("panel", help="Web panelini aç")
    sp.add_argument("--port", type=int, help="Port")
    sp.add_argument("--no-browser", action="store_true", help="Tarayıcıyı açma")
    sp.set_defaults(func=cmd_panel)

    sp = sub.add_parser("inspect", help="Kaynak depoyu (upstream) analiz et: eklentiler, siteler, ikonlar, durum")
    sp.add_argument("--source", help="Kaynak depo adresi (varsayılan: yapılandırmadaki)")
    sp.add_argument("--no-download", action="store_true", help=".cs3 indirme, yalnızca meta veri")
    sp.add_argument("--no-icons", action="store_true", help="İkonları indirme")
    sp.add_argument("--no-sites", action="store_true", help="Siteleri test etme (hızlı)")
    sp.add_argument("--json", nargs="?", const=True, help="Sonucu JSON olarak kaydet")
    sp.set_defaults(func=cmd_inspect)

    sp = sub.add_parser("builder", help="CloudStream-Builder deposunu indir/incele (extractor kütüphanesi)")
    sp.add_argument("--source", help="Builder depo adresi (varsayılan: Wiojelt/CloudStream-Builder)")
    sp.add_argument("--show", help="Builder içindeki bir dosyayı yazdır (ör. cloudstream-builder/SKILL.md)")
    sp.add_argument("--json", nargs="?", const=True, help="Sonucu JSON olarak kaydet")
    sp.set_defaults(func=cmd_builder)

    sp = sub.add_parser("builder-publish", help="Builder projesi için depo oluştur ve GitHub'a yükle")
    sp.add_argument("--project", required=True, help="Üretilmiş proje klasörünün adı")
    sp.add_argument("--repo", required=True, help="GitHub depo adı")
    sp.add_argument("--shortcode", default="", help="CloudStream kısa kodu (örnek: !kaos)")
    sp.set_defaults(func=cmd_builder_publish)

    sp = sub.add_parser("builder-shortcode", help="Yayınlanan deponun CloudStream kısa kodunu doğrula")
    sp.add_argument("--shortcode", required=True)
    sp.set_defaults(func=cmd_builder_shortcode)

    sp = sub.add_parser("independent", help="Kişisel depo hazırla veya yayınla")
    sp.add_argument("--request", required=True)
    sp.add_argument("--result", required=True)
    sp.set_defaults(func=cmd_independent)

    sub.add_parser("info", help="Durumu göster").set_defaults(func=cmd_info)
    return p


def main(argv=None) -> int:
    # Windows'ta çıktı dosyaya/boruya yönlendirildiğinde oluşan
    # "'charmap' codec can't encode character" hatasını önle.
    try:
        utils._setup_io()
    except Exception:  # noqa: BLE001
        pass
    if os.name == "nt":
        os.system("")  # Windows'ta ANSI renklerini etkinleştir
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        print(BANNER)
        parser.print_help()
        return 0

    try:
        return args.func(args)
    except KeyboardInterrupt:
        utils.warn("İptal edildi.")
        return 130
    except Exception as e:  # noqa: BLE001
        utils.err(f"Beklenmeyen hata: {e}")
        if os.environ.get("WIOFORGE_DEBUG"):
            raise
        return 1
