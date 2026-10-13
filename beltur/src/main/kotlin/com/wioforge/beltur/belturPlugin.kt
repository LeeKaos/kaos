package com.wioforge.beltur

import android.content.Context
import com.lagradost.cloudstream3.plugins.CloudstreamPlugin
import com.lagradost.cloudstream3.plugins.Plugin

@CloudstreamPlugin
class belturPlugin: Plugin() {
    override fun load(context: Context) {
        // Sağlayıcı(lar)ı kaydet
        registerMainAPI(belturProvider())
    }
}
