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
    alias(libs.plugins.kotlin.android)
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

    kotlinOptions {
        jvmTarget = "11"
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.appcompat)
    implementation(libs.material)
}
