/*
 * ============================================================================
 *  SMART CANE CLIP-ON  |  Phone Dashboard Activity
 * ============================================================================
 *  Main screen for the phone app.  Replaces the laptop Streamlit dashboard
 *  when walking outdoors.  Displays:
 *    • BLE connection status + real-time ESP32 sensor readings
 *    • Forward obstacle distance + zone (CLEAR / CAUTION / WARNING / CRITICAL)
 *    • Drop / step-down alert
 *    • Ambient light level
 *    • Fall-detected alarm (flashes red, plays alert sound)
 *    • Latest YOLO detections (from CaneVisionActivity running in background)
 *    • Buttons: Open Vision | Navigate | SOS Contacts
 *
 *  No XML layout — built programmatically.
 *
 *  Receives data via LocalBroadcast from:
 *    • CaneSosService       → ACTION_SENSOR_DATA  (ESP32 packets)
 *    • CaneVisionActivity   → ACTION_VISION_RESULT (detection labels)
 * ============================================================================
 */

package com.smartcane.gateway

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.media.AudioAttributes
import android.media.ToneGenerator
import android.media.AudioManager
import android.os.Build
import android.os.Bundle
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.localbroadcastmanager.content.LocalBroadcastManager
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class PhoneDashboardActivity : AppCompatActivity() {

    // -----------------------------------------------------------------------
    //  UI views
    // -----------------------------------------------------------------------
    private lateinit var tvBleStatus:    TextView
    private lateinit var tvDistFwd:      TextView
    private lateinit var tvZone:         TextView
    private lateinit var tvDistDrop:     TextView
    private lateinit var tvLight:        TextView
    private lateinit var tvFall:         TextView
    private lateinit var tvVision:       TextView
    private lateinit var tvLastUpdate:   TextView
    private lateinit var logContainer:   LinearLayout

    private var lastAlertAt = 0L

    private val toneGen by lazy {
        ToneGenerator(AudioManager.STREAM_ALARM, 80)
    }

    // -----------------------------------------------------------------------
    //  Permissions needed for the full feature set
    // -----------------------------------------------------------------------
    private val allPermissions: Array<String>
        get() = buildList {
            add(Manifest.permission.ACCESS_FINE_LOCATION)
            add(Manifest.permission.SEND_SMS)
            add(Manifest.permission.CAMERA)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU)
                add(Manifest.permission.POST_NOTIFICATIONS)
        }.toTypedArray()

    private val permLauncher =
        registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { results ->
            val allGranted = results.values.all { it }
            if (allGranted) startCaneService()
            else tvBleStatus.text = "Some permissions denied — limited functionality"
        }

    // -----------------------------------------------------------------------
    //  LocalBroadcast receivers
    // -----------------------------------------------------------------------
    private val sensorReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val packet = intent.getStringExtra(CaneSosService.EXTRA_PACKET) ?: return
            runOnUiThread { updateSensorUI(packet) }
        }
    }

    private val connectionReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val status = intent.getStringExtra(CaneSosService.EXTRA_STATUS) ?: return
            runOnUiThread {
                tvBleStatus.text = when (status) {
                    "connected"    -> "WiFi: CONNECTED"
                    "disconnected" -> "WiFi: DISCONNECTED"
                    "connecting"   -> "WiFi: CONNECTING..."
                    else           -> "WiFi: $status"
                }
                tvBleStatus.setTextColor(when (status) {
                    "connected"    -> Color.parseColor("#4CAF50")
                    "disconnected" -> Color.parseColor("#F44336")
                    else           -> Color.parseColor("#FF9800")
                })
            }
        }
    }

    private val visionReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val detections = intent.getStringExtra(CaneVisionActivity.EXTRA_DETECTIONS) ?: return
            runOnUiThread { tvVision.text = "Detected: $detections" }
        }
    }

    // -----------------------------------------------------------------------
    //  Lifecycle
    // -----------------------------------------------------------------------
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        buildUI()
        registerReceivers()

        if (!allPermissionsGranted()) permLauncher.launch(allPermissions)
    }

    override fun onDestroy() {
        super.onDestroy()
        LocalBroadcastManager.getInstance(this).unregisterReceiver(sensorReceiver)
        LocalBroadcastManager.getInstance(this).unregisterReceiver(visionReceiver)
        LocalBroadcastManager.getInstance(this).unregisterReceiver(connectionReceiver)
        runCatching { toneGen.release() }
    }

    // -----------------------------------------------------------------------
    //  Helpers
    // -----------------------------------------------------------------------
    private fun allPermissionsGranted() = allPermissions.all {
        ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
    }

    private fun getEsp32Ip(): String =
        getSharedPreferences(CaneSosService.PREF_NAME, MODE_PRIVATE)
            .getString(CaneSosService.PREF_ESP32_IP, CaneSosService.DEFAULT_IP)
            ?: CaneSosService.DEFAULT_IP

    private fun startCaneService() {
        val ip = getEsp32Ip()
        val intent = Intent(this, CaneSosService::class.java).putExtra("esp32_ip", ip)
        ContextCompat.startForegroundService(this, intent)
        tvBleStatus.text = "WiFi: Connecting to $ip..."
    }

    private fun registerReceivers() {
        val lbm = LocalBroadcastManager.getInstance(this)
        lbm.registerReceiver(sensorReceiver, IntentFilter(CaneSosService.ACTION_SENSOR_DATA))
        lbm.registerReceiver(visionReceiver, IntentFilter(CaneVisionActivity.ACTION_VISION_RESULT))
        lbm.registerReceiver(connectionReceiver, IntentFilter(CaneSosService.ACTION_CONNECTION_STATUS))
    }

    // -----------------------------------------------------------------------
    //  Sensor UI update
    // -----------------------------------------------------------------------
    private fun updateSensorUI(raw: String) {
        val parts = raw.split(",")
        if (parts.size != 4) return

        // parts[0] = VL53L0X ToF (mm)  → Drop/Step sensor
        // parts[1] = TF-Luna LiDAR (cm) → Forward sensor
        val tofMm   = parts[0].trim().toIntOrNull() ?: 0
        val lidarCm = parts[1].trim().toIntOrNull() ?: 0
        val fall    = parts[2].trim().toIntOrNull() ?: 0
        val light   = parts[3].trim().toIntOrNull() ?: 0

        tvDistFwd.text    = "Forward: ${cmReadable(lidarCm)}"
        tvDistDrop.text   = "Drop/Step: ${mmReadable(tofMm)}"
        tvLight.text      = "Light: ${luxLabel(light)}"
        tvLastUpdate.text = "Last packet: ${timeNow()}"

        val zone = zoneLabelCm(lidarCm)
        tvZone.text = "Zone: $zone"
        tvZone.setBackgroundColor(zoneColor(zone))

        // Fall: UI update only — no sound/vibration
        if (fall == 1) {
            tvFall.text = "⚠ FALL DETECTED"
            tvFall.setBackgroundColor(Color.RED)
            tvFall.setTextColor(Color.WHITE)
        } else {
            tvFall.text = "Fall: None"
            tvFall.setBackgroundColor(Color.TRANSPARENT)
            tvFall.setTextColor(Color.DKGRAY)
        }

        // Alerts — throttled to once per 2 seconds to avoid spam
        val now = System.currentTimeMillis()
        if (now - lastAlertAt > 2000) {
            when {
                tofMm > 500 -> {  // ToF > 50 cm → drop/step alert
                    addLog("⚠ Drop/Step: ${mmReadable(tofMm)}")
                    runCatching { toneGen.startTone(ToneGenerator.TONE_CDMA_EMERGENCY_RINGBACK, 1000) }
                    vibrate(longArrayOf(0, 500))
                    lastAlertAt = now
                }
                lidarCm in 1..49 -> {  // LiDAR < 50 cm → forward obstacle alert
                    addLog("⚠ Obstacle ahead: ${cmReadable(lidarCm)}")
                    runCatching { toneGen.startTone(ToneGenerator.TONE_CDMA_EMERGENCY_RINGBACK, 1000) }
                    lastAlertAt = now
                }
            }
        }
    }

    private fun addLog(msg: String) {
        val tv = TextView(this).apply {
            text      = "[${timeNow()}] $msg"
            textSize  = 12f
            setTextColor(Color.parseColor("#FF6D00"))
            setPadding(4, 2, 4, 2)
        }
        logContainer.addView(tv, 0)   // prepend so latest is at top
        if (logContainer.childCount > 50) logContainer.removeViewAt(logContainer.childCount - 1)
    }


    private fun vibrate(pattern: LongArray) {
        val v = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            (getSystemService(VIBRATOR_MANAGER_SERVICE) as VibratorManager).defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            getSystemService(VIBRATOR_SERVICE) as Vibrator
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            v.vibrate(VibrationEffect.createWaveform(pattern, -1))
        } else {
            @Suppress("DEPRECATION")
            v.vibrate(pattern, -1)
        }
    }

    // -----------------------------------------------------------------------
    //  Pure functions (mirrors laptop dashboard logic)
    // -----------------------------------------------------------------------
    private fun mmReadable(mm: Int) = if (mm >= 1000) "${"%.2f".format(mm / 1000.0)} m" else "$mm mm"

    private fun cmReadable(cm: Int) = if (cm >= 100) "${"%.2f".format(cm / 100.0)} m" else "$cm cm"

    private fun zoneLabelCm(cm: Int) = when {
        cm in 1..29  -> "CRITICAL"
        cm in 30..79 -> "WARNING"
        cm in 80..149 -> "CAUTION"
        else         -> "CLEAR"
    }

    private fun zoneColor(zone: String) = when (zone) {
        "CRITICAL" -> Color.RED
        "WARNING"  -> Color.parseColor("#FF6D00")
        "CAUTION"  -> Color.parseColor("#FFD600")
        else       -> Color.parseColor("#00C853")
    }

    private fun luxLabel(v: Int) = when {
        v < 200 -> "Very Dark"
        v < 500 -> "Dim"
        v < 800 -> "Moderate"
        else    -> "Bright"
    }

    private fun timeNow() =
        SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())

    // -----------------------------------------------------------------------
    //  Programmatic UI
    // -----------------------------------------------------------------------
    private fun buildUI() {
        val scroll = ScrollView(this)
        val root   = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 48, 32, 32)
            setBackgroundColor(Color.parseColor("#0D1117"))  // GitHub dark theme
        }

        fun heading(text: String, emoji: String = "") = TextView(this).apply {
            this.text  = if (emoji.isNotEmpty()) "$emoji $text" else text
            textSize   = 16f
            typeface   = Typeface.DEFAULT_BOLD
            setTextColor(Color.parseColor("#C9D1D9"))  // GitHub light text
            setPadding(0, 24, 0, 8)
        }

        fun valueCard(init: TextView.() -> Unit) = TextView(this).apply {
            textSize  = 18f
            setTextColor(Color.parseColor("#F0F6FC"))  // GitHub white text
            setPadding(20, 16, 20, 16)
            setBackgroundColor(Color.parseColor("#161B22"))  // GitHub card color
            elevation = 4f  // Add shadow
            init()
        }

        // --- Title ---
        root.addView(TextView(this).apply {
            text      = "🦯 Smart Cane v2.0"
            textSize  = 26f
            typeface  = Typeface.DEFAULT_BOLD
            setTextColor(Color.parseColor("#3FB950"))  // Green
            gravity   = Gravity.CENTER_HORIZONTAL
            setPadding(0, 0, 0, 16)
        })

        // --- WiFi IP input ---
        val prefs   = getSharedPreferences(CaneSosService.PREF_NAME, MODE_PRIVATE)
        val ipInput = android.widget.EditText(this).apply {
            setText(prefs.getString(CaneSosService.PREF_ESP32_IP, CaneSosService.DEFAULT_IP))
            hint        = "ESP32 IP (e.g. 192.168.1.100)"
            inputType   = android.text.InputType.TYPE_CLASS_TEXT
            setTextColor(Color.parseColor("#F0F6FC"))
            setHintTextColor(Color.parseColor("#8B949E"))
            setBackgroundColor(Color.parseColor("#21262D"))
            setPadding(20, 16, 20, 16)
            textSize = 16f
        }
        val applyBtn = Button(this).apply {
            text = "🔗 Connect"
            setBackgroundColor(Color.parseColor("#238636"))  // GitHub green
            setTextColor(Color.WHITE)
            textSize = 16f
            setPadding(32, 16, 32, 16)
            setOnClickListener {
                val ip = ipInput.text.toString().trim()
                if (ip.isNotEmpty()) {
                    getSharedPreferences(CaneSosService.PREF_NAME, MODE_PRIVATE)
                        .edit().putString(CaneSosService.PREF_ESP32_IP, ip).apply()
                }
                startCaneService()
            }
        }
        root.addView(heading("ESP32 IP Address", "📡"))
        root.addView(ipInput)
        root.addView(applyBtn)

        // --- WiFi status ---
        tvBleStatus = valueCard { text = "WiFi: Not connected" }
        root.addView(heading("Connection", "🔗"))
        root.addView(tvBleStatus)

        // --- Fall alert ---
        tvFall = valueCard {
            text    = "Fall: None"
            setTextColor(Color.parseColor("#8B949E"))
        }
        root.addView(heading("Fall Detection", "🚨"))
        root.addView(tvFall)

        // --- Zone ---
        tvZone = valueCard { text = "Zone: --" }
        root.addView(heading("Obstacle Zone", "⚠️"))
        root.addView(tvZone)

        // --- Distances + light ---
        root.addView(heading("Sensor Readings", "📊"))
        tvDistFwd  = valueCard { text = "Forward: --" };  root.addView(tvDistFwd)
        tvDistDrop = valueCard { text = "Drop/Step: --" }; root.addView(tvDistDrop)
        tvLight    = valueCard { text = "Light: --" };    root.addView(tvLight)

        // --- Vision ---
        tvVision = valueCard { text = "Vision: inactive" }
        root.addView(heading("Object Detection", "👁️"))
        root.addView(tvVision)

        // --- Last update ---
        tvLastUpdate = TextView(this).apply {
            text = "No data yet"
            textSize = 14f
            setTextColor(Color.parseColor("#8B949E"))
            setPadding(0, 16, 0, 8)
        }
        root.addView(tvLastUpdate)

        // --- Buttons ---
        root.addView(heading("Actions", "🎮"))
        val btnRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }

        fun actionBtn(label: String, color: String, onClick: () -> Unit) = Button(this).apply {
            text = label
            setBackgroundColor(Color.parseColor(color))
            setTextColor(Color.WHITE)
            textSize = 14f
            val lp = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            lp.setMargins(8, 0, 8, 0)
            layoutParams = lp
            setPadding(16, 12, 16, 12)
            setOnClickListener { onClick() }
        }

        btnRow.addView(actionBtn("👁️ VISION", "#8957E5") {
            startActivity(Intent(this, CaneVisionActivity::class.java))
        })
        btnRow.addView(actionBtn("🧭 NAVIGATE", "#238636") {
            startActivity(Intent(this, NavigationActivity::class.java))
        })
        btnRow.addView(actionBtn("🚨 SOS CONTACTS", "#DA3633") {
            startActivity(Intent(this, SosContactsActivity::class.java))
        })
        root.addView(btnRow)

        // --- Log ---
        root.addView(heading("Event Log", "📝"))
        logContainer = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(logContainer)

        scroll.addView(root)
        setContentView(scroll)
    }
}
