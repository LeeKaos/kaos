// Site: https://duzcebeltur.com
// Bu dosyadaki seçicileri (selector) sitenin gerçek HTML yapısına göre
// gerektiğinde elle düzenleyebilirsin. TODO yorumları sana ipucu verir.
package com.wioforge.beltur

import com.lagradost.cloudstream3.*
import com.lagradost.cloudstream3.utils.ExtractorLink
import com.lagradost.cloudstream3.utils.loadExtractor
import org.jsoup.nodes.Element
import org.jsoup.nodes.Document

class belturProvider : MainAPI() {
    override var mainUrl = "https://duzcebeltur.com"
    override var name = "beltur"
    override val supportedTypes = setOf(TvType.Movie, TvType.TvSeries)

    override var lang = "tr"
    override val hasMainPage = true

    // ------------------------------------------------------------------
    // Ana sayfa (isteğe bağlı). Boş bırakırsan arama yine çalışır.
    // ------------------------------------------------------------------
    override val mainPage = mainPageOf(
        "$mainUrl/" to "Son Eklenenler"
    )

    override suspend fun getMainPage(page: Int, request: MainPageRequest): HomePageResponse {
        val document = app.get(request.data).document
        val items = document.select("article, .post, .result-item")
            .mapNotNull { it.toSearchResult() }
        return newHomePageResponse(request, items, hasNext = false)
    }

    // ------------------------------------------------------------------
    // Arama
    // ------------------------------------------------------------------
    override suspend fun search(query: String): List<SearchResponse> {
        val url = "https://duzcebeltur.com/?s={query}".replace("{query}", query)
        val document = app.get(url).document
        return document.select("article, .post, .result-item")
            .mapNotNull { it.toSearchResult() }
    }

    private fun Element.toSearchResult(): SearchResponse? {
        val linkEl = this.selectFirst("a") ?: return null
        val href = linkEl.attr("href").takeIf { it.isNotBlank() } ?: return null
        val title = (this.selectFirst("h2, h3, .title, .name")?.text()
            ?: linkEl.attr("title")
            ?: linkEl.text()).trim()
        if (title.isBlank()) return null
        val poster = this.selectFirst("img")?.let {
            it.attr("img").ifBlank { it.attr("src") }
        }

        return newMovieSearchResponse(title, absUrl(href), TvType.Movie) {
            this.posterUrl = poster
        }
    }

    // ------------------------------------------------------------------
    // Detay sayfası
    // ------------------------------------------------------------------
    override suspend fun load(url: String): LoadResponse? {
        val document = app.get(url).document
        val title = (document.selectFirst("h1")?.text()
            ?: document.title()).trim()
        val poster = document.selectFirst("meta[property=og:image]")?.attr("content")
        val description = document.selectFirst("meta[name=description]")?.attr("content")

        // TODO: Bölüm listesi (dizi ise). Sitenin yapısına göre güncelle.
        val episodes = document.select(".episodes a, .bolumler a, .episode a")
            .mapNotNull { el ->
                val epUrl = el.attr("href").takeIf { it.isNotBlank() } ?: return@mapNotNull null
                val epName = el.text().trim().ifBlank { "Bölüm" }
                newEpisode(absUrl(epUrl)) { this.name = epName }
            }

        return if (episodes.isNotEmpty()) {
            newTvSeriesLoadResponse(title, url, TvType.TvSeries, episodes) {
                this.posterUrl = poster
                this.plot = description
            }
        } else {
            newMovieLoadResponse(title, url, TvType.Movie, url) {
                this.posterUrl = poster
                this.plot = description
            }
        }
    }

    // ------------------------------------------------------------------
    // Oynatma linkleri
    // ------------------------------------------------------------------
    override suspend fun loadLinks(
        data: String,
        isCasting: Boolean,
        subtitleCallback: (SubtitleFile) -> Unit,
        callback: (ExtractorLink) -> Unit
    ): Boolean {
        val document = app.get(data).document
        var found = false

        // 1) Doğrudan iframe / video kaynakları
        document.select("iframe[src], video source[src], video[src]").forEach { el ->
            val src = el.attr("src").ifBlank { el.attr("data-src") }
            if (src.isNotBlank()) {
                found = true
                loadExtractor(absUrl(src), subtitleCallback, callback)
            }
        }

        // 2) data-* içinde saklanan kaynaklar (yaygın)
        document.select("[data-src], [data-video], [data-url], [data-file]").forEach { el ->
            listOf("data-src", "data-video", "data-url", "data-file").forEach { attr ->
                val v = el.attr(attr)
                if (v.isNotBlank() && (v.startsWith("http") || v.contains(".m3u8") || v.contains(".mp4"))) {
                    found = true
                    loadExtractor(absUrl(v), subtitleCallback, callback)
                }
            }
        }

        // TODO: Sitenin oynatıcısı özel bir API kullanıyorsa buraya ekle.
        return found
    }

    private fun absUrl(url: String): String {
        if (url.startsWith("http")) return url
        if (url.startsWith("//")) return "https:$url"
        return "$mainUrl${if (url.startsWith("/")) "" else "/"}$url"
    }
}
