/*
 * ============================================================================
 *  SMART CANE CLIP-ON  |  MODULE B: MAIN ACTIVITY
 * ============================================================================
 *  Requests all runtime permissions needed by CaneSosService.
 *  Once granted, starts the foreground BLE service automatically.
 *
 *  HOW TO USE IN ANDROID STUDIO:
 *    1. File > New > New Project > Empty Views Activity (Kotlin, min SDK 26)
 *    2. Replace the generated MainActivity.kt with this file
 *    3. Copy CaneSosService.kt (Android_SOS_Service.kt) into the same package
 *    4. Replace AndroidManifest.xml with the one provided
 *    5. Replace the SOS_CONTACT and CANE_MAC constants in CaneSosService.kt
 * ============================================================================
 */

package com.smartcane.gateway

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat

class MainActivity : AppCompatActivity() {

    // All permissions required by the service, split by API level
    private val requiredPermissions: Array<String>
        get() = buildList {
            // BLE (API 31+)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                add(Manifest.permission.BLUETOOTH_CONNECT)
                add(Manifest.permission.BLUETOOTH_SCAN)
            }
            add(Manifest.permission.ACCESS_FINE_LOCATION)
            add(Manifest.permission.SEND_SMS)

            // POST_NOTIFICATIONS needed for foreground service on API 33+
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                add(Manifest.permission.POST_NOTIFICATIONS)
            }
        }.toTypedArray()

    // -------------------------------------------------------------------------
    //  Permission launcher — called after user taps Allow / Deny
    // -------------------------------------------------------------------------
    private val permissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { results ->
            val allGranted = results.values.all { it }
            if (allGranted) {
                startCaneService()
                updateStatusText("Service running. Monitoring for falls...")
            } else {
                val denied = results.filterValues { !it }.keys.joinToString("\n")
                updateStatusText("Denied — service cannot start.\n\nMissing:\n$denied")
            }
        }

    // -------------------------------------------------------------------------
    //  UI
    // -------------------------------------------------------------------------
    private lateinit var statusText: TextView
    private lateinit var startBtn: Button
    private lateinit var stopBtn: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        statusText = findViewById(R.id.tvStatus)
        startBtn   = findViewById(R.id.btnStart)
        stopBtn    = findViewById(R.id.btnStop)

        startBtn.setOnClickListener { checkAndStart() }
        stopBtn.setOnClickListener  { stopCaneService() }

        // Auto-start if permissions are already granted from a previous run
        if (allPermissionsGranted()) {
            startCaneService()
            updateStatusText("Service running. Monitoring for falls...")
        } else {
            updateStatusText("Tap START to request permissions and begin monitoring.")
        }
    }

    // -------------------------------------------------------------------------
    //  Permission check + service control
    // -------------------------------------------------------------------------
    private fun checkAndStart() {
        if (allPermissionsGranted()) {
            startCaneService()
            updateStatusText("Service running. Monitoring for falls...")
        } else {
            permissionLauncher.launch(requiredPermissions)
        }
    }

    private fun allPermissionsGranted() = requiredPermissions.all {
        ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
    }

    private fun startCaneService() {
        val intent = Intent(this, CaneSosService::class.java)
        ContextCompat.startForegroundService(this, intent)
        startBtn.isEnabled = false
        stopBtn.isEnabled  = true
    }

    private fun stopCaneService() {
        stopService(Intent(this, CaneSosService::class.java))
        startBtn.isEnabled = true
        stopBtn.isEnabled  = false
        updateStatusText("Service stopped.")
    }

    private fun updateStatusText(msg: String) {
        statusText.text = msg
    }

    // -------------------------------------------------------------------------
    //  VIBECODER: receive broadcasted packets here to update live UI
    //  Uncomment and wire up a LocalBroadcastReceiver if you want the
    //  MainActivity to display live dist_fwd / fall_flag values.
    // -------------------------------------------------------------------------
}
