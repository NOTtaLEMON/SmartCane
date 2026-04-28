/*
 * ============================================================================
 *  SMART CANE CLIP-ON  |  MODULE B: app/build.gradle.kts
 * ============================================================================
 *  Paste this as your app-level build.gradle.kts in Android Studio.
 *  (The file Android Studio generates is at  app/build.gradle.kts)
 * ============================================================================
 */

plugins {
    alias(libs.plugins.android.application)
}

android {
    namespace   = "com.smartcane.gateway"
    compileSdk  = 35

    defaultConfig {
        applicationId = "com.smartcane.gateway"
        minSdk        = 26          // Android 8 — safe lower bound for BLE APIs
        targetSdk     = 35
        versionCode   = 1
        versionName   = "1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.appcompat)
    implementation(libs.material)

    // ── On-device YOLOv8 TFLite inference ──────────────────────────────────
    implementation("org.tensorflow:tensorflow-lite:2.16.1")
    implementation("org.tensorflow:tensorflow-lite-support:0.4.4")
    implementation("org.tensorflow:tensorflow-lite-gpu:2.16.1")

    // ── CameraX (live camera feed for on-device vision) ────────────────────
    implementation("androidx.camera:camera-camera2:1.3.4")
    implementation("androidx.camera:camera-lifecycle:1.3.4")
    implementation("androidx.camera:camera-view:1.3.4")

    // ── Local broadcasts (service ↔ activity data pipe) ────────────────────
    implementation("androidx.localbroadcastmanager:localbroadcastmanager:1.1.0")

    // ── SOS contacts persistence ────────────────────────────────────────────
    implementation("com.google.code.gson:gson:2.10.1")

    // ── Coroutines (async work) ─────────────────────────────────────────────
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")
}
