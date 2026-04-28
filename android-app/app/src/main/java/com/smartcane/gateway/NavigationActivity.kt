/*
 * ============================================================================
 *  SMART CANE CLIP-ON  |  Navigation Activity
 * ============================================================================
 *  AI-assisted navigation for visually impaired users.
 *
 *  Features:
 *    1. Voice input  — tap mic button, say destination aloud
 *    2. Text input   — type destination manually
 *    3. Launches Google Maps in WALKING navigation mode
 *       (Google Maps' own voice turn-by-turn guides the user)
 *    4. "Last destination" saved in SharedPreferences for quick re-use
 *
 *  No XML layout — built programmatically.
 *  No Google Maps API key required (uses implicit Intent to Maps app).
 * ============================================================================
 */

package com.smartcane.gateway

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.net.Uri
import android.os.Bundle
import android.speech.RecognizerIntent
import android.view.Gravity
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity

class NavigationActivity : AppCompatActivity() {

    companion object {
        private const val PREFS_NAME     = "SmartCanePrefs"
        private const val KEY_LAST_DEST  = "last_destination"
    }

    private lateinit var etDestination: EditText
    private lateinit var tvLastDest:    TextView

    // -----------------------------------------------------------------------
    //  Voice recognition result handler
    // -----------------------------------------------------------------------
    private val voiceLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            if (result.resultCode == RESULT_OK) {
                val matches = result.data
                    ?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)
                if (!matches.isNullOrEmpty()) {
                    val heard = matches[0]
                    etDestination.setText(heard)
                    Toast.makeText(this, "Heard: $heard", Toast.LENGTH_SHORT).show()
                }
            }
        }

    // -----------------------------------------------------------------------
    //  Lifecycle
    // -----------------------------------------------------------------------
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        buildUI()
    }

    // -----------------------------------------------------------------------
    //  Navigation logic
    // -----------------------------------------------------------------------
    private fun navigateTo(destination: String) {
        if (destination.isBlank()) {
            Toast.makeText(this, "Please enter a destination", Toast.LENGTH_SHORT).show()
            return
        }
        // Save as last destination
        getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit().putString(KEY_LAST_DEST, destination).apply()
        tvLastDest.text = "Last: $destination"

        // Launch Google Maps walking navigation
        // "google.navigation:q=<destination>&mode=w"  (w = walking)
        val uri    = Uri.parse("google.navigation:q=${Uri.encode(destination)}&mode=w")
        val intent = Intent(Intent.ACTION_VIEW, uri).apply {
            setPackage("com.google.android.apps.maps")
        }
        try {
            startActivity(intent)
        } catch (e: ActivityNotFoundException) {
            // Maps not installed — fall back to browser/web Maps
            val webUri    = Uri.parse("https://www.google.com/maps/dir/?api=1&destination=${Uri.encode(destination)}&travelmode=walking")
            val webIntent = Intent(Intent.ACTION_VIEW, webUri)
            startActivity(webIntent)
        }
    }

    private fun startVoiceInput() {
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_PROMPT, "Say your destination")
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
        }
        try {
            voiceLauncher.launch(intent)
        } catch (e: ActivityNotFoundException) {
            Toast.makeText(this, "Voice input not available on this device", Toast.LENGTH_SHORT).show()
        }
    }

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

        // Title
        root.addView(TextView(this).apply {
            text     = "Navigation"
            textSize = 22f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.WHITE)
            gravity  = Gravity.CENTER_HORIZONTAL
        })

        root.addView(TextView(this).apply {
            text     = "Type or say your destination.\nGoogle Maps will guide you with voice turn-by-turn."
            textSize = 14f
            setTextColor(Color.GRAY)
            setPadding(0, 8, 0, 24)
        })

        // --- Destination input ---
        etDestination = EditText(this).apply {
            hint      = "e.g. Apollo Hospital, Chennai"
            textSize  = 16f
            setTextColor(Color.WHITE)
            setHintTextColor(Color.GRAY)
            setBackgroundColor(Color.parseColor("#1E1E1E"))
            setPadding(16, 16, 16, 16)
            val lp = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
            layoutParams = lp
        }
        root.addView(etDestination)

        // --- Last destination ---
        val lastDest = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getString(KEY_LAST_DEST, null)
        tvLastDest = TextView(this).apply {
            text     = if (lastDest != null) "Last: $lastDest" else ""
            textSize = 12f
            setTextColor(Color.parseColor("#64B5F6"))
            setPadding(4, 4, 4, 16)
            setOnClickListener {
                if (lastDest != null) etDestination.setText(lastDest)
            }
        }
        root.addView(tvLastDest)

        // --- Button row ---
        val btnRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            val lp = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
            lp.setMargins(0, 8, 0, 0)
            layoutParams = lp
        }

        btnRow.addView(Button(this).apply {
            text = "🎤  VOICE"
            setBackgroundColor(Color.parseColor("#1565C0"))
            setTextColor(Color.WHITE)
            val lp = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            lp.setMargins(0, 0, 8, 0)
            layoutParams = lp
            setOnClickListener { startVoiceInput() }
        })

        btnRow.addView(Button(this).apply {
            text = "NAVIGATE"
            setBackgroundColor(Color.parseColor("#2E7D32"))
            setTextColor(Color.WHITE)
            val lp = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            layoutParams = lp
            setOnClickListener { navigateTo(etDestination.text.toString().trim()) }
        })
        root.addView(btnRow)

        // --- Tips ---
        root.addView(TextView(this).apply {
            text = "\nTips:\n" +
                   "• Keep your phone volume up for Maps voice guidance\n" +
                   "• Say landmark names for best results (e.g. \"AIIMS Delhi\")\n" +
                   "• Vision detection continues while navigating — just press BACK to return here"
            textSize = 13f
            setTextColor(Color.parseColor("#9E9E9E"))
            setPadding(0, 24, 0, 0)
        })

        scroll.addView(root)
        setContentView(scroll)
    }
}
