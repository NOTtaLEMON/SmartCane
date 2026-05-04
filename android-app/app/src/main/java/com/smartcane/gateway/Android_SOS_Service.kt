/*
 * ============================================================================
 *  SMART CANE CLIP-ON  |  MODULE B: ANDROID GATEWAY ("Bridge")
 * ============================================================================
 *  Tech      : Kotlin (min SDK 26)
 *  Role      : Background service that listens to the ESP32 over WiFi
 *              (WebSocket), parses packets, grabs GPS, and fires an SOS SMS
 *              on fall detection.
 *
 *  PACKET FORMAT (from ESP32):
 *      "dist_fwd,dist_drop,fall_flag,light_val"   e.g. "045,180,1,550"
 *
 *  REQUIRED AndroidManifest.xml entries:
 *  ------------------------------------------------------------------
 *  <uses-permission android:name="android.permission.INTERNET"/>
 *  <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION"/>
 *  <uses-permission android:name="android.permission.SEND_SMS"/>
 *  <uses-permission android:name="android.permission.FOREGROUND_SERVICE"/>
 *  <uses-permission android:name="android.permission.POST_NOTIFICATIONS"/>
 *
 *  <service android:name=".CaneSosService"
 *           android:foregroundServiceType="dataSync"
 *           android:exported="false"/>
 *  ------------------------------------------------------------------
 *
 *  ESP32 IP: Set via SharedPreferences (key: "esp32_ip") or pass as
 *  intent extra "esp32_ip" when starting the service.
 * ============================================================================
 */

package com.smartcane.gateway

import android.Manifest
import android.annotation.SuppressLint
import android.app.*
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.location.Location
import android.location.LocationManager
import android.os.Build
import android.os.IBinder
import android.telephony.SmsManager
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import androidx.localbroadcastmanager.content.LocalBroadcastManager
import kotlinx.coroutines.*
import okhttp3.*
import java.util.concurrent.TimeUnit

class CaneSosService : Service() {

    companion object {
        private const val TAG = "CaneSOS"
        private const val CHANNEL_ID = "cane_sos_channel"
        private const val NOTIF_ID   = 1337

        // --- VIBECODER: replace with emergency contact ---
        const val SOS_CONTACT = "+911234567890"

        // Rate-limit: don't spam SMS
        private const val SMS_COOLDOWN_MS = 60_000L

        // SharedPreferences key for ESP32 IP
        const val PREF_NAME    = "cane_prefs"
        const val PREF_ESP32_IP = "esp32_ip"
        const val DEFAULT_IP   = "192.168.1.100"

        // LocalBroadcast action + extras — received by PhoneDashboardActivity
        const val ACTION_SENSOR_DATA = "com.smartcane.gateway.SENSOR_DATA"
        const val EXTRA_PACKET       = "packet"
    }

    private var okClient: OkHttpClient? = null
    private var webSocket: WebSocket?   = null
    private var lastSmsAt = 0L
    private val serviceScope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var reconnectJob: Job? = null

    // -------------------------------------------------------------------------
    //  Service lifecycle
    // -------------------------------------------------------------------------
    override fun onCreate() {
        super.onCreate()
        startAsForeground("Connecting to ESP32...")
        connectToESP32()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == FallTriggerTest.ACTION_TEST_FALL) triggerSos()

        // Allow updating IP at runtime
        intent?.getStringExtra("esp32_ip")?.let { ip ->
            getSharedPreferences(PREF_NAME, MODE_PRIVATE).edit()
                .putString(PREF_ESP32_IP, ip).apply()
            reconnect()
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        webSocket?.close(1000, "Service stopped")
        okClient?.dispatcher?.executorService?.shutdown()
        serviceScope.cancel()
        super.onDestroy()
    }

    // -------------------------------------------------------------------------
    //  WebSocket connection
    // -------------------------------------------------------------------------
    private fun getEsp32Ip(): String =
        getSharedPreferences(PREF_NAME, MODE_PRIVATE)
            .getString(PREF_ESP32_IP, DEFAULT_IP) ?: DEFAULT_IP

    private fun connectToESP32() {
        val ip  = getEsp32Ip()
        val url = "ws://$ip:81"
        Log.d(TAG, "Connecting WebSocket: $url")

        okClient = OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(30,    TimeUnit.SECONDS)
            .retryOnConnectionFailure(false)
            .build()

        val request = Request.Builder().url(url).build()
        webSocket = okClient!!.newWebSocket(request, wsListener)
    }

    private fun reconnect() {
        reconnectJob?.cancel()
        webSocket?.close(1000, "Reconnecting")
        okClient?.dispatcher?.executorService?.shutdown()
        webSocket = null
        okClient  = null
        connectToESP32()
    }

    private fun scheduleReconnect() {
        reconnectJob?.cancel()
        reconnectJob = serviceScope.launch {
            delay(5_000)
            connectToESP32()
        }
    }

    private val wsListener = object : WebSocketListener() {
        override fun onOpen(ws: WebSocket, response: Response) {
            Log.d(TAG, "WebSocket connected")
            updateNotification("WiFi connected — monitoring for falls")
        }

        override fun onMessage(ws: WebSocket, text: String) {
            handlePacket(text.trim())
        }

        override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) {
            Log.e(TAG, "WebSocket error: ${t.message}")
            updateNotification("WiFi disconnected — retrying in 5s...")
            scheduleReconnect()
        }

        override fun onClosed(ws: WebSocket, code: Int, reason: String) {
            Log.d(TAG, "WebSocket closed: $reason")
            if (code != 1000) scheduleReconnect()
        }
    }

    // -------------------------------------------------------------------------
    //  Packet parser
    //  Format: "dist_fwd,dist_drop,fall_flag,light_val"
    // -------------------------------------------------------------------------
    private fun handlePacket(raw: String) {
        val parts = raw.split(",")
        if (parts.size != 4) return
        val fallFlag = parts[2].trim().toIntOrNull() ?: 0

        Log.d(TAG, "packet=$raw")

        // Broadcast sensor data to PhoneDashboardActivity
        LocalBroadcastManager.getInstance(this).sendBroadcast(
            Intent(ACTION_SENSOR_DATA).putExtra(EXTRA_PACKET, raw)
        )

        if (fallFlag == 1) triggerSos()
    }

    // -------------------------------------------------------------------------
    //  SOS: grab GPS + send SMS with Google Maps URL
    // -------------------------------------------------------------------------
    @SuppressLint("MissingPermission")
    internal fun triggerSos() {
        val now = System.currentTimeMillis()
        if (now - lastSmsAt < SMS_COOLDOWN_MS) return
        lastSmsAt = now

        val loc = lastKnownLocation()
        val mapsUrl = if (loc != null)
            "https://maps.google.com/?q=${loc.latitude},${loc.longitude}"
        else
            "location unavailable"

        val body = "SOS: Smart-Cane user may have fallen. $mapsUrl"

        // Send to all contacts managed in SosContactsActivity
        val contacts = SosContactsActivity.loadContacts(this)
        val targets  = contacts.ifEmpty { listOf(SOS_CONTACT) }
        targets.forEach { sendSms(it, body) }
        Log.w(TAG, "SOS SMS sent to ${targets.size} contact(s) -> $body")
    }

    @SuppressLint("MissingPermission")
    private fun lastKnownLocation(): Location? {
        if (!hasPerm(Manifest.permission.ACCESS_FINE_LOCATION)) return null
        val lm = getSystemService(LOCATION_SERVICE) as LocationManager
        return listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)
            .mapNotNull { runCatching { lm.getLastKnownLocation(it) }.getOrNull() }
            .maxByOrNull { it.time }
    }

    private fun sendSms(to: String, body: String) {
        if (!hasPerm(Manifest.permission.SEND_SMS)) return
        val sms = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S)
            getSystemService(SmsManager::class.java) else SmsManager.getDefault()
        val parts = sms.divideMessage(body)
        sms.sendMultipartTextMessage(to, null, parts, null, null)
    }

    // -------------------------------------------------------------------------
    //  Foreground notification
    // -------------------------------------------------------------------------
    private fun startAsForeground(text: String) {
        val nm = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "Smart Cane", NotificationManager.IMPORTANCE_LOW)
            )
        }
        val notif = buildNotification(text)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(NOTIF_ID, notif, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(NOTIF_ID, notif)
        }
    }

    private fun updateNotification(text: String) {
        val nm = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        nm.notify(NOTIF_ID, buildNotification(text))
    }

    private fun buildNotification(text: String) =
        NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Smart Cane active")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_menu_compass)
            .build()

    // -------------------------------------------------------------------------
    private fun hasPerm(p: String) =
        ContextCompat.checkSelfPermission(this, p) == PackageManager.PERMISSION_GRANTED
}
