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
import android.os.Handler
import android.os.Looper
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.atomic.AtomicReference

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
    private val latestPacket = AtomicReference<String?>(null)
    private val uiHandler = Handler(Looper.getMainLooper())
    private val renderRunnable = object : Runnable {
        override fun run() {
            latestPacket.getAndSet(null)?.let { updateSensorUI(it) }
            uiHandler.postDelayed(this, 50)
        }
    }

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
            latestPacket.set(packet)  // always keep only the freshest packet
        }
    }

    private val connectionReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val status = intent.getStringExtra(CaneSosService.EXTRA_STATUS) ?: return
            val error  = intent.getStringExtra(CaneSosService.EXTRA_ERROR)
            runOnUiThread {
                tvBleStatus.text = when (status) {
                    "connected"    -> "WiFi: CONNECTED"
                    "disconnected" -> if (error != null) "WiFi: DISCONNECTED — $error" else "WiFi: DISCONNECTED"
                    "connecting"   -> "WiFi: CONNECTING..."
                    else           -> "WiFi: $status"
                }
                tvBleStatus.setTextColor(when (status) {
                    "connected"    -> Color.parseColor("#4CAF50")
                    "disconnected" -> Color.parseColor("#F44336")
                    else           -> Color.parseColor("#FF9800")
                })
                if (status == "disconnected" && error != null) {
                    addLog("WiFi error: $error")
                }
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
        uiHandler.postDelayed(renderRunnable, 50)

        if (!allPermissionsGranted()) permLauncher.launch(allPermissions)
        else window.decorView.post { startCaneService() }
    }

    override fun onDestroy() {
        super.onDestroy()
        uiHandler.removeCallbacks(renderRunnable)
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
        runCatching { ContextCompat.startForegroundService(this, intent) }
            .onFailure { e ->
                runCatching { startService(intent) }
                    .onFailure { e2 ->
                        addLog("ERROR: Could not start service — ${e2.message}")
                        tvBleStatus.text = "ERROR: Service failed to start — ${e2.message}"
                        tvBleStatus.setTextColor(Color.parseColor("#F44336"))
                    }
            }
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

        // parts[0] = VL53L0X ToF (mm → convert to cm) → Drop/Step sensor
        // parts[1] = TF-Luna LiDAR (cm) → Forward sensor
        val tofMm   = parts[0].trim().toIntOrNull() ?: 0
        val tofCm   = tofMm / 10
        val lidarCm = parts[1].trim().toIntOrNull() ?: 0
        val fall    = parts[2].trim().toIntOrNull() ?: 0
        val light   = parts[3].trim().toIntOrNull() ?: 0

        tvDistFwd.text    = "FORWARD\n$lidarCm cm"
        tvDistDrop.text   = "DROP / STEP\n$tofCm cm"
        tvLight.text      = "AMBIENT LIGHT:  ${luxLabel(light)}"
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
                tofCm > 50 -> {  // ToF > 50 cm → drop/step alert
                    addLog("⚠ Drop/Step: $tofCm cm")
                    runCatching { toneGen.startTone(ToneGenerator.TONE_CDMA_EMERGENCY_RINGBACK, 1000) }
                    vibrate(longArrayOf(0, 500))
                    lastAlertAt = now
                }
                lidarCm in 1..49 -> {  // LiDAR < 50 cm → forward obstacle alert
                    addLog("⚠ Obstacle ahead: $lidarCm cm")
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
    private fun cmReadable(cm: Int) = "$cm cm"

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
        val BG       = Color.parseColor("#0A0E14")
        val CARD_BG  = Color.parseColor("#131920")
        val ACCENT   = Color.parseColor("#3FB950")
        val TEXT_PRI = Color.parseColor("#E6EDF3")
        val TEXT_SEC = Color.parseColor("#7D8590")
        val DIVIDER  = Color.parseColor("#21262D")

        fun roundedBg(color: Int, radius: Float = 16f) =
            android.graphics.drawable.GradientDrawable().apply {
                setColor(color); cornerRadius = radius
            }

        val scroll = ScrollView(this)
        val root   = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(28, 44, 28, 32)
            setBackgroundColor(BG)
        }

        fun heading(text: String, emoji: String = "") = TextView(this).apply {
            this.text  = if (emoji.isNotEmpty()) "$emoji  $text" else text
            textSize   = 11f
            typeface   = Typeface.DEFAULT_BOLD
            setTextColor(TEXT_SEC)
            letterSpacing = 0.12f
            setPadding(4, 28, 0, 6)
        }

        fun valueCard(init: TextView.() -> Unit) = TextView(this).apply {
            textSize  = 17f
            setTextColor(TEXT_PRI)
            setPadding(20, 18, 20, 18)
            background = roundedBg(CARD_BG)
            val lp = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT)
            lp.setMargins(0, 0, 0, 6)
            layoutParams = lp
            init()
        }

        // --- Title ---
        root.addView(TextView(this).apply {
            text      = "🦯 Smart Cane"
            textSize  = 24f
            typeface  = Typeface.DEFAULT_BOLD
            setTextColor(ACCENT)
            gravity   = Gravity.CENTER_HORIZONTAL
            setPadding(0, 4, 0, 4)
        })
        root.addView(TextView(this).apply {
            text     = "Live Sensor Dashboard"
            textSize = 12f
            setTextColor(TEXT_SEC)
            gravity  = Gravity.CENTER_HORIZONTAL
            setPadding(0, 0, 0, 4)
        })
        root.addView(TextView(this).apply {
            text     = "v1.1-wifi-tts"
            textSize = 10f
            setTextColor(Color.parseColor("#3FB950"))
            gravity  = Gravity.CENTER_HORIZONTAL
            setPadding(0, 0, 0, 20)
        })

        // --- IP row: input + button side by side ---
        val prefs  = getSharedPreferences(CaneSosService.PREF_NAME, MODE_PRIVATE)
        val ipRow  = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            background  = roundedBg(CARD_BG)
            setPadding(4, 4, 4, 4)
            val lp = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT)
            lp.setMargins(0, 8, 0, 12)
            layoutParams = lp
        }
        val ipInput = android.widget.EditText(this).apply {
            setText(prefs.getString(CaneSosService.PREF_ESP32_IP, CaneSosService.DEFAULT_IP))
            hint      = "ESP32 IP address"
            inputType = android.text.InputType.TYPE_CLASS_TEXT
            setTextColor(TEXT_PRI)
            setHintTextColor(TEXT_SEC)
            background = null
            setPadding(20, 16, 12, 16)
            textSize = 15f
            val lp = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            layoutParams = lp
        }
        val applyBtn = Button(this).apply {
            text      = "CONNECT"
            background = roundedBg(Color.parseColor("#238636"), 12f)
            setTextColor(Color.WHITE)
            textSize  = 13f
            typeface  = Typeface.DEFAULT_BOLD
            setPadding(28, 0, 28, 0)
            stateListAnimator = null
            val lp = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.MATCH_PARENT)
            lp.setMargins(8, 8, 8, 8)
            layoutParams = lp
            setOnClickListener {
                val ip = ipInput.text.toString().trim()
                if (ip.isNotEmpty()) {
                    getSharedPreferences(CaneSosService.PREF_NAME, MODE_PRIVATE)
                        .edit().putString(CaneSosService.PREF_ESP32_IP, ip).apply()
                }
                startCaneService()
            }
        }
        ipRow.addView(ipInput)
        ipRow.addView(applyBtn)
        root.addView(heading("CONNECTION", ""))
        root.addView(ipRow)

        // --- WiFi status ---
        tvBleStatus = valueCard { text = "WiFi: Not connected" }
        root.addView(heading("Connection", "🔗"))
        root.addView(tvBleStatus)

        // --- Fall alert ---
        tvFall = valueCard {
            text    = "Fall: None"
            setTextColor(Color.parseColor("#8B949E"))
        }
        root.addView(heading("FALL DETECTION", "🚨"))
        root.addView(tvFall)

        // --- Zone ---
        tvZone = valueCard { text = "Zone: --" }
        root.addView(heading("OBSTACLE ZONE", "⚠️"))
        root.addView(tvZone)

        // --- Distances + light in a 2-col grid ---
        root.addView(heading("SENSORS", "📡"))
        fun sensorRow(left: TextView, right: TextView) = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            val lp = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT)
            lp.setMargins(0, 0, 0, 6)
            layoutParams = lp
            val half = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1f)
            half.setMargins(0, 0, 6, 0)
            left.layoutParams = half
            val half2 = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1f)
            right.layoutParams = half2
            addView(left); addView(right)
        }
        tvDistFwd  = valueCard { text = "Forward\n--" }
        tvDistDrop = valueCard { text = "Drop/Step\n--" }
        tvLight    = valueCard { text = "Light\n--" }
        root.addView(sensorRow(tvDistFwd, tvDistDrop))
        root.addView(tvLight)

        // --- Vision ---
        tvVision = valueCard { text = "Vision: inactive" }
        root.addView(heading("OBJECT DETECTION", "👁️"))
        root.addView(tvVision)

        // --- Last update ---
        tvLastUpdate = TextView(this).apply {
            text = "No data yet"
            textSize = 12f
            setTextColor(TEXT_SEC)
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(0, 12, 0, 4)
        }
        root.addView(tvLastUpdate)

        // --- Buttons ---
        root.addView(heading("ACTIONS", ""))
        val btnRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            val lp = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT)
            lp.setMargins(0, 4, 0, 0)
            layoutParams = lp
        }

        fun actionBtn(label: String, color: String, onClick: () -> Unit) = Button(this).apply {
            text = label
            background = roundedBg(Color.parseColor(color), 12f)
            setTextColor(Color.WHITE)
            textSize = 12f
            typeface = Typeface.DEFAULT_BOLD
            stateListAnimator = null
            val lp = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            lp.setMargins(0, 0, 8, 0)
            layoutParams = lp
            setPadding(8, 24, 8, 24)
            setOnClickListener { onClick() }
        }

        btnRow.addView(actionBtn("👁️ VISION", "#6E40C9") {
            startActivity(Intent(this, CaneVisionActivity::class.java))
        })
        btnRow.addView(actionBtn("🧭 NAVIGATE", "#1A7F37") {
            startActivity(Intent(this, NavigationActivity::class.java))
        })
        btnRow.addView(actionBtn("🚨 SOS", "#B91C1C") {
            startActivity(Intent(this, SosContactsActivity::class.java))
        })
        root.addView(btnRow)

        // --- Log ---
        root.addView(heading("EVENT LOG", "📋"))
        logContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = roundedBg(CARD_BG)
            setPadding(16, 12, 16, 12)
        }
        root.addView(logContainer)

        scroll.addView(root)
        setContentView(scroll)
    }
}
