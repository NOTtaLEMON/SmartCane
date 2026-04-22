/*
 * ============================================================================
 *  SMART CANE CLIP-ON  |  MODULE B: FALL TRIGGER TEST HELPER
 * ============================================================================
 *  A standalone Kotlin file to test the SMS + GPS logic without needing
 *  a real ESP32 or BLE connection.
 *
 *  HOW TO USE:
 *    1. Add this file to the same package as CaneSosService.kt
 *    2. In your MainActivity, add a "Test Fall" button and call:
 *         FallTriggerTest.simulateFall(this)
 *    3. Check your SOS_CONTACT phone — you should receive the SMS.
 *    4. REMOVE this file (or the button) before your final presentation.
 * ============================================================================
 */

package com.smartcane.gateway

import android.content.Context
import android.content.Intent
import android.util.Log

object FallTriggerTest {

    private const val TAG = "FallTriggerTest"

    /**
     * Simulates receiving a packet where fall_flag == 1.
     * Starts the service (if not already running) and immediately
     * sends a fake packet to trigger the SOS flow.
     */
    fun simulateFall(context: Context) {
        Log.d(TAG, "Simulating fall packet: 045,180,1,550")

        // Start the service so it is alive to receive our test broadcast
        val serviceIntent = Intent(context, CaneSosService::class.java)
        context.startForegroundService(serviceIntent)

        // VIBECODER: if you implement LocalBroadcastManager in CaneSosService,
        // send the fake packet as a broadcast here instead of the direct call below.

        // Direct test: call triggerSos() via reflection is messy.
        // Simplest approach — just start the service with a test action:
        val testIntent = Intent(context, CaneSosService::class.java).apply {
            action = ACTION_TEST_FALL
        }
        context.startService(testIntent)
    }

    const val ACTION_TEST_FALL = "com.smartcane.gateway.TEST_FALL"
}

/*
 * ---- ADD THIS BLOCK to CaneSosService.onStartCommand() ----
 *
 *   override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
 *       if (intent?.action == FallTriggerTest.ACTION_TEST_FALL) {
 *           triggerSos()   // <-- calls the private method directly for testing
 *       }
 *       return START_STICKY
 *   }
 *
 * Also change triggerSos() from private to internal so the test can call it.
 * ----------------------------------------------------------------
 */
