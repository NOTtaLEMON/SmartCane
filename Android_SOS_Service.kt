/*
 * ============================================================================
 *  SMART CANE CLIP-ON  |  MODULE B: ANDROID GATEWAY ("Bridge")
 * ============================================================================
 *  Tech      : Kotlin (min SDK 26)
 *  Role      : Background service that listens to the ESP32 over BLE,
 *              parses packets, grabs GPS, and fires an SOS SMS on fall.
 *
 *  PACKET FORMAT (from ESP32):
 *      "dist_fwd,dist_drop,fall_flag,light_val"   e.g. "045,180,1,550"
 *
 *  REQUIRED AndroidManifest.xml entries:
 *  ------------------------------------------------------------------
 *  <uses-permission android:name="android.permission.BLUETOOTH_CONNECT"/>
 *  <uses-permission android:name="android.permission.BLUETOOTH_SCAN"/>
 *  <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION"/>
 *  <uses-permission android:name="android.permission.SEND_SMS"/>
 *  <uses-permission android:name="android.permission.FOREGROUND_SERVICE"/>
 *  <uses-permission android:name="android.permission.POST_NOTIFICATIONS"/>
 *
 *  <service android:name=".CaneSosService"
 *           android:foregroundServiceType="connectedDevice"
 *           android:exported="false"/>
 *  ------------------------------------------------------------------
 *
 *  BLE UUIDs: replace with the ones you advertise from the ESP32.
 * ============================================================================
 */

package com.smartcane.gateway

import android.Manifest
import android.annotation.SuppressLint
import android.app.*
import android.bluetooth.*
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import android.os.Build
import android.os.IBinder
import android.telephony.SmsManager
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import androidx.localbroadcastmanager.content.LocalBroadcastManager
import java.util.UUID

class CaneSosService : Service() {

    companion object {
        private const val TAG = "CaneSOS"
        private const val CHANNEL_ID = "cane_sos_channel"
        private const val NOTIF_ID   = 1337

        // --- VIBECODER: paste your ESP32 BLE UUIDs here ---
        val SERVICE_UUID: UUID        = UUID.fromString("0000ffe0-0000-1000-8000-00805f9b34fb")
        val CHARACTERISTIC_UUID: UUID = UUID.fromString("0000ffe1-0000-1000-8000-00805f9b34fb")
        val CCCD_UUID: UUID           = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")

        // --- VIBECODER: replace with emergency contact & MAC of your cane ---
        const val SOS_CONTACT    = "+911234567890"
        const val CANE_MAC       = "AA:BB:CC:DD:EE:FF"

        // Rate-limit: don't spam SMS
        private const val SMS_COOLDOWN_MS = 60_000L

        // LocalBroadcast action + extras — received by PhoneDashboardActivity
        const val ACTION_SENSOR_DATA = "com.smartcane.gateway.SENSOR_DATA"
        const val EXTRA_PACKET       = "packet"
    }

    private var gatt: BluetoothGatt? = null
    private var lastSmsAt = 0L

    // ---------------------------------------------------------------------
    //  Service lifecycle
    // ---------------------------------------------------------------------
    override fun onCreate() {
        super.onCreate()
        startAsForeground()
        connectToCane()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == FallTriggerTest.ACTION_TEST_FALL) triggerSos()
        return START_STICKY
    }
    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        try { gatt?.close() } catch (_: SecurityException) {}
        super.onDestroy()
    }

    private fun startAsForeground() {
        val nm = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "Smart Cane", NotificationManager.IMPORTANCE_LOW)
            )
        }
        val notif = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Smart Cane active")
            .setContentText("Listening for BLE packets...")
            .setSmallIcon(android.R.drawable.ic_menu_compass)
            .build()
        startForeground(NOTIF_ID, notif)
    }

    // ---------------------------------------------------------------------
    //  BLE connect + subscribe
    // ---------------------------------------------------------------------
    @SuppressLint("MissingPermission")
    private fun connectToCane() {
        if (!hasPerm(Manifest.permission.BLUETOOTH_CONNECT)) {
            Log.e(TAG, "Missing BLUETOOTH_CONNECT"); return
        }
        val adapter = (getSystemService(BLUETOOTH_SERVICE) as BluetoothManager).adapter
        val device: BluetoothDevice = adapter.getRemoteDevice(CANE_MAC)
        gatt = device.connectGatt(this, true, gattCallback)
    }

    private val gattCallback = object : BluetoothGattCallback() {
        @SuppressLint("MissingPermission")
        override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
            if (newState == BluetoothProfile.STATE_CONNECTED) g.discoverServices()
        }

        @SuppressLint("MissingPermission")
        override fun onServicesDiscovered(g: BluetoothGatt, status: Int) {
            val ch = g.getService(SERVICE_UUID)?.getCharacteristic(CHARACTERISTIC_UUID) ?: return
            g.setCharacteristicNotification(ch, true)
            ch.getDescriptor(CCCD_UUID)?.apply {
                value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                g.writeDescriptor(this)
            }
        }

        override fun onCharacteristicChanged(g: BluetoothGatt, ch: BluetoothGattCharacteristic) {
            val packet = ch.value?.toString(Charsets.UTF_8)?.trim() ?: return
            handlePacket(packet)
        }
    }

    // ---------------------------------------------------------------------
    //  Packet parser
    //  Format: "dist_fwd,dist_drop,fall_flag,light_val"
    // ---------------------------------------------------------------------
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

    // ---------------------------------------------------------------------
    //  SOS: grab GPS + send SMS with Google Maps URL
    // ---------------------------------------------------------------------
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
        val targets  = contacts.ifEmpty { listOf(SOS_CONTACT) }   // fallback to hardcoded
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

    // ---------------------------------------------------------------------
    private fun hasPerm(p: String) =
        ContextCompat.checkSelfPermission(this, p) == PackageManager.PERMISSION_GRANTED
}
