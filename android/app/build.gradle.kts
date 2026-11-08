// ============================================================================
//  SMSATBOX · Android App 模块构建脚本
//  版本号来源：version.properties（CI 会按 Tag 覆盖）
// ============================================================================
import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// 读取版本号：与全平台保持一致
val versionProps = Properties().apply {
    val f = rootProject.file("version.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}
val appVersionName: String = versionProps.getProperty("VERSION_NAME", "1.0.6")
val appVersionCode: Int = versionProps.getProperty("VERSION_CODE", "10006").toInt()

android {
    namespace = "com.smsatbox.app"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.smsatbox.app"
        // 兼容 Android 7.0 (API 24) 及以上。
        // 注：鸿蒙 4.2 底层是 Android 11/12（API 30/31），远高于此，完全支持。
        minSdk = 24
        targetSdk = 34
        versionCode = appVersionCode
        versionName = appVersionName

        // 内嵌 GitHub 仓库坐标，供独立升级使用（绝不经过 Server）
        buildConfigField("String", "GITHUB_OWNER", "\"beibing173\"")
        buildConfigField("String", "GITHUB_REPO", "\"smsatbox\"")
        buildConfigField("String", "APP_VERSION", "\"$appVersionName\"")
    }

    buildFeatures {
        buildConfig = true
        viewBinding = true
    }

    signingConfigs {
        create("release") {
            // CI 会生成 keystore/smsatbox.jks；本地无此文件时回退到 debug 签名
            val ksFile = rootProject.file("keystore/smsatbox.jks")
            if (ksFile.exists()) {
                storeFile = ksFile
                storePassword = System.getenv("KEYSTORE_PASSWORD") ?: "smsatbox"
                keyAlias = System.getenv("KEY_ALIAS") ?: "smsatbox"
                keyPassword = System.getenv("KEY_PASSWORD") ?: "smsatbox"
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            // 有正式密钥就用它，否则退回 debug 签名（保证 CI 无密钥也能出包）
            signingConfig = if (rootProject.file("keystore/smsatbox.jks").exists()) {
                signingConfigs.getByName("release")
            } else {
                signingConfigs.getByName("debug")
            }
        }
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    packaging {
        resources.excludes += setOf("/META-INF/{AL2.0,LGPL2.1}")
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")
    implementation("androidx.recyclerview:recyclerview:1.3.2")
    implementation("androidx.swiperefreshlayout:swiperefreshlayout:1.1.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.4")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.json:json:20240303")

    testImplementation("junit:junit:4.13.2")
}
