dependencies {
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.recyclerview:recyclerview:1.3.2")
}

version = 1

cloudstream {
    description = "beltur — Düzce Beltur – Yöresel Ürünler"
    authors = listOf("LeeKaos")
    status = 1
    tvTypes = listOf("Movie", "TvSeries")
    requiresResources = false
    language = "tr"
    iconUrl = "https://www.google.com/s2/favicons?domain=duzcebeltur.com&sz=128"
}

android {
    buildFeatures {
        buildConfig = true
        viewBinding = false
    }
}
