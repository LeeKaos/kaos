# -*- coding: utf-8 -*-
"""
analyzer.py — Verilen bir site adresini çözümler.

Amaç: https://www.dizimom.wiki gibi bir adres verildiğinde sitenin
  * başlığını / dilini,
  * arama formunu ve arama URL kalıbını (?s=, /?q=, /search/ ...),
  * arama sonuç sayfasındaki öğe (kart) yapısını,
  * detay sayfası ve oynatıcı ipuçlarını
tespit edip CloudStream eklentisi üretiminde kullanılacak bir "site profili"
(JSON) oluşturmak.

Bağımlılık yoktur; yalnızca standart kütüphane kullanılır. Küçük bir DOM ağacı
kurulur ve tekrarlanan "kart" yapıları sezgisel olarak bulunur.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field, asdict
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, quote_plus

from . import utils


# ----------------------------------------------------------------------------
# Minimal DOM ağacı
# ----------------------------------------------------------------------------

class DomNode:
    __slots__ = ("tag", "attrs", "children", "parent", "text_parts")

    def __init__(self, tag: str, attrs: Dict[str, str], parent: Optional["DomNode"]):
        self.tag = tag
        self.attrs = attrs
        self.children: List["DomNode"] = []
        self.parent = parent
        self.text_parts: List[str] = []

    @property
    def classes(self) -> List[str]:
        return (self.attrs.get("class") or "").split()

    @property
    def cls_key(self) -> str:
        return self.classes[0] if self.classes else ""

    def text(self) -> str:
        out: List[str] = []
        stack = [self]
        while stack:
            n = stack.pop()
            if n.text_parts:
                out.append("".join(n.text_parts))
            stack.extend(n.children)
        return " ".join(" ".join(out).split())

    def iter_all(self):
        stack = [self]
        while stack:
            n = stack.pop()
            yield n
            stack.extend(n.children)

    def find_all(self, tag: Optional[str] = None) -> List["DomNode"]:
        return [n for n in self.iter_all() if tag is None or n.tag == tag]

    def first(self, tag: str) -> Optional["DomNode"]:
        for n in self.iter_all():
            if n.tag == tag:
                return n
        return None

    def get(self, attr: str, default: str = "") -> str:
        return self.attrs.get(attr, default) or default


class DomBuilder(HTMLParser):
    VOID = {"img", "br", "hr", "input", "meta", "link", "source", "area",
            "base", "col", "embed", "param", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = DomNode("root", {}, None)
        self.stack: List[DomNode] = [self.root]

    def handle_starttag(self, tag, attrs):
        node = DomNode(tag, dict(attrs), self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        node = DomNode(tag, dict(attrs), self.stack[-1])
        self.stack[-1].children.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].text_parts.append(data)


def parse_dom(html: str) -> DomNode:
    b = DomBuilder()
    try:
        b.feed(html)
    except Exception:  # noqa: BLE001
        pass
    return b.root


# ----------------------------------------------------------------------------
# Site profili
# ----------------------------------------------------------------------------

@dataclass
class SiteProfile:
    url: str
    domain: str
    title: str = ""
    search_url_template: str = ""
    search_param: str = "s"
    search_method: str = "get"
    result_selector_hint: str = ""
    result_title_selector: str = "h2, h3, .title, .name"
    result_poster_selector: str = "img"
    detail_url_pattern: str = ""
    episode_url_pattern: str = ""
    poster_attr: str = "src"
    has_main_page: bool = True
    is_wordpress: bool = False
    sample_query: str = "breaking"
    sample_results: List[Dict[str, str]] = field(default_factory=list)
    detected_links: int = 0
    card_class: str = ""
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ----------------------------------------------------------------------------
# Yardımcılar
# ----------------------------------------------------------------------------

NAV_HINTS = ("menu", "nav", "header", "footer", "sidebar", "breadcrumb",
             "social", "pagination", "widget", "comment", "logo")

CONTENT_HINTS = ("item", "card", "post", "film", "dizi", "movie", "episode",
                 "box", "result", "thumb", "cover", "poster", "single",
                 "product", "entry", "cat", "video", "serie", "show")

SEARCH_PARAMS = ("s", "q", "query", "search", "keyword", "ara", "arama", "kelime")


def _normalize_url(url: str) -> str:
    if not url.startswith("http"):
        url = "https://" + url
    return url.rstrip("/")


def _is_content_href(href: str, base_url: str) -> bool:
    if not href or href.startswith(("#", "javascript", "mailto", "tel")):
        return False
    full = urljoin(base_url + "/", href)
    if urlparse(base_url).netloc not in full:
        return False
    path = urlparse(full).path.strip("/")
    if not path:
        return False
    # İçerik linkleri genelde slug içerir (tire) veya izle/film/dizi/bolum
    return ("-" in path) or any(k in path.lower() for k in
                                ("izle", "film", "dizi", "bolum", "watch", "episode", "movie", "serie"))


def _detect_search_form(root: DomNode, base_url: str) -> Tuple[str, str, str]:
    best_param = ""
    best_action = ""
    best_method = "get"
    for form in root.find_all("form"):
        for inp in form.find_all("input"):
            name = inp.get("name").strip()
            typ = inp.get("type", "text").lower()
            if typ in ("text", "search") and name:
                if name in SEARCH_PARAMS or not best_param:
                    best_param = name
                    best_action = form.get("action") or base_url
                    best_method = form.get("method", "get").lower()
                    if name in ("s", "q", "search"):
                        break
    if not best_param:
        best_param = "s"
    if not best_action:
        best_action = base_url + "/"
    action = urljoin(base_url + "/", best_action)
    sep = "&" if "?" in action else "?"
    return f"{action}{sep}{best_param}={{query}}", best_param, best_method


def _detect_cards(root: DomNode, base_url: str) -> Tuple[str, str, str, List[Dict[str, str]]]:
    """
    Tekrarlanan 'kart' yapısını bulur.
    Döner: (kart_seçici, başlık_seçici, poster_seçici, örnekler)
    """
    signatures: Counter = Counter()
    card_nodes: Dict[str, List[DomNode]] = {}

    for node in root.iter_all():
        if node.tag not in ("div", "article", "li", "section", "a"):
            continue
        cls = node.cls_key
        if not cls:
            continue
        low = cls.lower()
        if any(h in low for h in NAV_HINTS):
            continue
        # İçinde içerik linki + resim var mı?
        links = [a for a in node.find_all("a") if _is_content_href(a.get("href", ""), base_url)]
        imgs = node.find_all("img")
        if not links or not imgs:
            continue
        # Aşırı büyük kapsayıcıları (tüm sayfa) ele
        if len(node.find_all("a")) > 40:
            continue
        sig = cls
        signatures[sig] += 1
        card_nodes.setdefault(sig, []).append(node)

    if not signatures:
        return "", "h2, h3, .title, .name", "img", []

    # İçerik ipucu içeren ve en çok tekrar eden sınıfı seç
    def score(item):
        sig, count = item
        bonus = 3 if any(h in sig.lower() for h in CONTENT_HINTS) else 0
        return (bonus, count)

    best_sig, _ = max(signatures.items(), key=score)
    nodes = card_nodes[best_sig]

    # Başlık seçici tahmini
    title_sel = "h2, h3, h4, .title, .name, .episode-title"
    for n in nodes:
        for h in ("h1", "h2", "h3", "h4"):
            if n.first(h):
                title_sel = f"{h}, .title, .name"
                break
        else:
            continue
        break

    # Poster attribute
    poster_attr = "src"
    for n in nodes:
        img = n.first("img")
        if img and (img.get("data-src") or img.get("data-lazy-src")):
            poster_attr = "data-src"
            break

    samples: List[Dict[str, str]] = []
    seen = set()
    for n in nodes:
        a = next((x for x in n.find_all("a") if _is_content_href(x.get("href", ""), base_url)), None)
        if not a:
            continue
        href = urljoin(base_url + "/", a.get("href"))
        if href in seen:
            continue
        seen.add(href)
        img = n.first("img")
        poster = ""
        if img:
            poster = img.get(poster_attr) or img.get("src") or img.get("data-src") or ""
        title = ""
        for h in ("h1", "h2", "h3", "h4"):
            hn = n.first(h)
            if hn:
                title = hn.text()
                break
        if not title:
            title = a.get("title") or a.text()
        samples.append({"title": title[:120], "url": href, "poster": poster})
        if len(samples) >= 12:
            break

    # Detay kalıbı
    pattern = ""
    for s in samples:
        m = re.match(r"^(/[^/]+/)", urlparse(s["url"]).path)
        if m:
            pattern = m.group(1) + "{slug}"
            break

    return best_sig, title_sel, poster_attr, samples


# ----------------------------------------------------------------------------
# Çözümleme
# ----------------------------------------------------------------------------

def analyze_site(url: str, *, sample_query: str = "breaking") -> SiteProfile:
    base = _normalize_url(url)
    prof = SiteProfile(url=base, domain=urlparse(base).netloc, sample_query=sample_query)

    utils.info(f"Ana sayfa çekiliyor: {base}")
    html = utils.http_get(base, timeout=30)
    if not html:
        prof.notes.append("Ana sayfa indirilemedi (Cloudflare/engel olabilir).")
        prof.search_url_template = base + "/?s={query}"
        return prof

    home = parse_dom(html)
    title_el = home.first("title")
    prof.title = title_el.text().strip() if title_el else ""
    prof.is_wordpress = ("wp-content" in html or "wp-login.php" in html or "wp-json" in html)
    if prof.is_wordpress:
        prof.notes.append("WordPress tespit edildi (arama parametresi genelde 's').")

    tmpl, param, method = _detect_search_form(home, base)
    prof.search_url_template = tmpl
    prof.search_param = param
    prof.search_method = method

    search_url = tmpl.replace("{query}", quote_plus(sample_query))
    utils.info(f"Arama sayfası çekiliyor: {search_url}")
    shtml = utils.http_get(search_url, timeout=30)
    if shtml:
        sroot = parse_dom(shtml)
        prof.detected_links = len(sroot.find_all("a"))
        card_sig, title_sel, poster_attr, samples = _detect_cards(sroot, base)
        prof.card_class = card_sig
        prof.result_title_selector = title_sel
        prof.poster_attr = poster_attr
        prof.sample_results = samples
        if card_sig:
            prof.result_selector_hint = f".{card_sig}, article, .post"
        else:
            prof.result_selector_hint = "article, .post, .result-item"
            prof.notes.append("Kart yapısı otomatik bulunamadı; seçiciyi elle ayarla.")
        for s in samples:
            if re.search(r"\d+-sezon-\d+-bolum", s["url"]):
                prof.episode_url_pattern = "/{slug}-{sezon}-sezon-{bolum}-bolum-izle/"
                break
    else:
        prof.notes.append("Arama sayfası indirilemedi; seçiciler elle ayarlanmalı.")
        prof.result_selector_hint = "article, .post, .result-item"

    return prof


def profile_to_selector_config(prof: SiteProfile) -> Dict[str, Any]:
    return {
        "site_url": prof.url,
        "domain": prof.domain,
        "title": prof.title,
        "search_url_template": prof.search_url_template,
        "search_param": prof.search_param,
        "result_selector": prof.result_selector_hint,
        "result_link_selector": "a",
        "result_title_selector": prof.result_title_selector,
        "result_poster_selector": "img",
        "poster_attr": prof.poster_attr,
        "detail_url_pattern": prof.detail_url_pattern,
        "episode_url_pattern": prof.episode_url_pattern,
        "notes": prof.notes,
    }
