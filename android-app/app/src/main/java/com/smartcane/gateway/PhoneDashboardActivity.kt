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
            updateSensorUI(packet)
        }
    }

    private val visionReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val detections = intent.getStringExtra(CaneVisionActivity.EXTRA_DETECTIONS) ?: return
            tvVision.text = "Detected: $detections"
        }
    }

    // -----------------------------------------------------------------------
    //  Lifecycle
    // -----------------------------------------------------------------------
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        buildUI()
        registerReceivers()

        if (allPermissionsGranted()) startCaneService()
        else permLauncher.launch(allPermissions)
    }

    override fun onDestroy() {
        super.onDestroy()
        LocalBroadcastManager.getInstance(this).unregisterReceiver(sensorReceiver)
        LocalBroadcastManager.getInstance(this).unregisterReceiver(visionReceiver)
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
    }

    // -----------------------------------------------------------------------
    //  Sensor UI update
    // -----------------------------------------------------------------------
    private fun updateSensorUI(raw: String) {
        val parts = raw.split(",")
        if (parts.size != 4) return

        val distFwd  = parts[0].trim().toIntOrNull() ?: 0
        val distDrop = parts[1].trim().toIntOrNull() ?: 0
        val fall     = parts[2].trim().toIntOrNull() ?: 0
        val light    = parts[3].trim().toIntOrNull() ?: 0

        tvBleStatus.text = "WiFi: Connected"
        tvBleStatus.setTextColor(Color.parseColor("#00C853"))

        tvDistFwd.text   = "Forward: ${mmReadable(distFwd)}"
        tvDistDrop.text  = "Drop/Step: ${mmReadable(distDrop)}"
        tvLight.text     = "Light: ${luxLabel(light)}"
        tvLastUpdate.text = "Last packet: ${timeNow()}"

        val zone = zoneLabel(distFwd)
        tvZone.text = "Zone: $zone"
        tvZone.setBackgroundColor(zoneColor(zone))

        if (fall == 1) {
            tvFall.text = "⚠ FALL DETECTED"
            tvFall.setBackgroundColor(Color.RED)
            tvFall.setTextColor(Color.WHITE)
            buzzAlert()
        } else {
            tvFall.text = "Fall: None"
            tvFall.setBackgroundColor(Color.TRANSPARENT)
            tvFall.setTextColor(Color.DKGRAY)
        }

        if (distFwd < 300) {
            addLog("CRITICAL obstacle at ${mmReadable(distFwd)}")
            buzzShort()
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

    private fun buzzAlert() {
        runCatching { toneGen.startTone(ToneGenerator.TONE_CDMA_EMERGENCY_RINGBACK, 1500) }
        vibrate(longArrayOf(0, 300, 100, 300, 100, 500))
    }

    private fun buzzShort() {
        vibrate(longArrayOf(0, 80))
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

    private fun zoneLabel(mm: Int) = when {
        mm < 300  -> "CRITICAL"
        mm < 800  -> "WARNING"
        mm < 1500 -> "CAUTION"
        else      -> "CLEAR"
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
            setPadding(24, 48, 24, 24)
            setBackgroundColor(Color.parseColor("#121212"))
        }

        fun heading(text: String) = TextView(this).apply {
            this.text  = text
            textSize   = 13f
            typeface   = Typeface.DEFAULT_BOLD
            setTextColor(Color.parseColor("#BDBDBD"))
            setPadding(0, 16, 0, 4)
        }

        fun valueCard(init: TextView.() -> Unit) = TextView(this).apply {
            textSize  = 18f
            setTextColor(Color.WHITE)
            setPadding(16, 12, 16, 12)
            setBackgroundColor(Color.parseColor("#1E1E1E"))
            init()
        }

        // --- Title ---
        root.addView(TextView(this).apply {
            text      = "Smart Cane Dashboard"
            textSize  = 22f
            typeface  = Typeface.DEFAULT_BOLD
            setTextColor(Color.WHITE)
            gravity   = Gravity.CENTER_HORIZONTAL
        })

        // --- WiFi IP input ---
        val prefs   = getSharedPreferences(CaneSosService.PREF_NAME, MODE_PRIVATE)
        val ipInput = android.widget.EditText(this).apply {
            setText(prefs.getString(CaneSosService.PREF_ESP32_IP, CaneSosService.DEFAULT_IP))
            hint        = "ESP32 IP (e.g. 192.168.1.100)"
            inputType   = android.text.InputType.TYPE_CLASS_TEXT
            setTextColor(Color.WHITE)
            setHintTextColor(Color.GRAY)
            setBackgroundColor(Color.parseColor("#2A2A2A"))
            setPadding(16, 12, 16, 12)
        }
        val applyBtn = Button(this).apply {
            text = "Connect"
            setBackgroundColor(Color.parseColor("#1565C0"))
            setTextColor(Color.WHITE)
            setOnClickListener {
                val ip = ipInput.text.toString().trim()
                if (ip.isNotEmpty()) {
                    prefs.edit().putString(CaneSosService.PREF_ESP32_IP, ip).apply()
                    startCaneService()
                }
            }
        }
        root.addView(heading("ESP32 IP Address"))
        root.addView(ipInput)
        root.addView(applyBtn)

        // --- WiFi status ---
        tvBleStatus = valueCard { text = "WiFi: Connecting..." }
        root.addView(heading("Connection"))
        root.addView(tvBleStatus)

        // --- Fall alert ---
        tvFall = valueCard {
            text    = "Fall: None"
            setTextColor(Color.DKGRAY)
        }
        root.addView(heading("Fall Detection"))
        root.addView(tvFall)

        // --- Zone ---
        tvZone = valueCard { text = "Zone: --" }
        root.addView(heading("Obstacle Zone"))
        root.addView(tvZone)

        // --- Distances + light ---
        root.addView(heading("Sensor Readings"))
        tvDistFwd  = valueCard { text = "Forward: --" };  root.addView(tvDistFwd)
        tvDistDrop = valueCard { text = "Drop/Step: --" }; root.addView(tvDistDrop)
        tvLight    = valueCard { text = "Light: --" };    root.addView(tvLight)

        // --- Vision ---
        tvVision = valueCard { text = "Vision: inactive" }
        root.addView(heading("Object Detection"))
        root.addView(tvVision)

        // --- Last update ---
        tvLastUpdate = TextView(this).apply {
            text = "No data yet"
            textSize = 12f
            setTextColor(Color.GRAY)
        }
        root.addView(tvLastUpdate)

        // --- Buttons ---
        root.addView(heading("Actions"))
        val btnRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }

        fun actionBtn(label: String, color: String, onClick: () -> Unit) = Button(this).apply {
            text = label
            setBackgroundColor(Color.parseColor(color))
            setTextColor(Color.WHITE)
            val lp = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            lp.setMargins(4, 0, 4, 0)
            layoutParams = lp
            setOnClickListener { onClick() }
        }

        btnRow.addView(actionBtn("VISION", "#1565C0") {
            startActivity(Intent(this, CaneVisionActivity::class.java))
        })
        btnRow.addView(actionBtn("NAVIGATE", "#2E7D32") {
            startActivity(Intent(this, NavigationActivity::class.java))
        })
        btnRow.addView(actionBtn("SOS CONTACTS", "#B71C1C") {
            startActivity(Intent(this, SosContactsActivity::class.java))
        })
        root.addView(btnRow)

        // --- Log ---
        root.addView(heading("Event Log"))
        logContainer = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(logContainer)

        scroll.addView(root)
        setContentView(scroll)
    }
}
