plugins {
    id("com.android.application")
}

val agapeBaseUrl = (providers.gradleProperty("agapeBaseUrl").orNull
    ?: System.getenv("AGAPE_BASE_URL")
    ?: "https://agape-alpha.tail2a2d28.ts.net/").trimEnd('/') + "/"

android {
    namespace = "dev.dmtarmey.agape"
    compileSdk = 36

    defaultConfig {
        applicationId = "dev.dmtarmey.agape"
        minSdk = 29
        targetSdk = 36
        versionCode = 251
        versionName = "5.6.1-r2.5.1-alpha"
        buildConfigField("String", "AGAPE_BASE_URL", "\"${agapeBaseUrl.replace("\"", "\\\"")}\"")
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
