/*
 * ============================================================================
 *  SMART CANE CLIP-ON  |  SOS Contacts Activity
 * ============================================================================
 *  Lets the user manage a list of emergency contacts.
 *  Contacts are persisted in SharedPreferences as a JSON array.
 *  CaneSosService reads this list and SMS-blasts all contacts on fall.
 *
 *  No XML layout — built programmatically.
 *
 *  DEPENDENCY (app/build.gradle.kts)
 *  -----------------------------------
 *  implementation("com.google.code.gson:gson:2.10.1")
 * ============================================================================
 */

package com.smartcane.gateway

import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.view.Gravity
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken

class SosContactsActivity : AppCompatActivity() {

    companion object {
        private const val PREFS_NAME    = "SmartCanePrefs"
        private const val KEY_CONTACTS  = "sos_contacts"

        /** Load the SOS contact list from SharedPreferences. Called by CaneSosService. */
        fun loadContacts(context: Context): List<String> {
            val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            val json  = prefs.getString(KEY_CONTACTS, null) ?: return emptyList()
            return runCatching {
                Gson().fromJson<List<String>>(json, object : TypeToken<List<String>>() {}.type)
                    ?: emptyList()
            }.getOrElse { emptyList() }
        }

        private fun saveContacts(context: Context, contacts: List<String>) {
            context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                .edit()
                .putString(KEY_CONTACTS, Gson().toJson(contacts))
                .apply()
        }
    }

    private val contacts: MutableList<String> = mutableListOf()
    private lateinit var contactsContainer: LinearLayout

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        contacts.clear()
        contacts.addAll(loadContacts(this))

        buildUI()
    }

    // -----------------------------------------------------------------------
    //  UI builder
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
            text      = "SOS Emergency Contacts"
            textSize  = 20f
            typeface  = Typeface.DEFAULT_BOLD
            setTextColor(Color.WHITE)
            gravity   = Gravity.CENTER_HORIZONTAL
        })

        // Subtitle
        root.addView(TextView(this).apply {
            text     = "All contacts below receive an SMS with your GPS location when a fall is detected."
            textSize = 13f
            setTextColor(Color.GRAY)
            setPadding(0, 8, 0, 16)
        })

        // --- Input row: number + Add button ---
        val inputRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val etNumber = EditText(this).apply {
            hint        = "+91 XXXXXXXXXX"
            textSize    = 16f
            setTextColor(Color.WHITE)
            setHintTextColor(Color.GRAY)
            setBackgroundColor(Color.parseColor("#1E1E1E"))
            setPadding(12, 12, 12, 12)
            inputType   = android.text.InputType.TYPE_CLASS_PHONE
            val lp = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            layoutParams = lp
        }
        val btnAdd = Button(this).apply {
            text = "ADD"
            setBackgroundColor(Color.parseColor("#1565C0"))
            setTextColor(Color.WHITE)
            setOnClickListener {
                val num = etNumber.text.toString().trim()
                if (num.length < 7) {
                    Toast.makeText(this@SosContactsActivity, "Enter a valid number", Toast.LENGTH_SHORT).show()
                    return@setOnClickListener
                }
                if (num in contacts) {
                    Toast.makeText(this@SosContactsActivity, "Already in list", Toast.LENGTH_SHORT).show()
                    return@setOnClickListener
                }
                contacts.add(num)
                saveContacts(this@SosContactsActivity, contacts)
                etNumber.text.clear()
                refreshContactRows()
            }
        }
        inputRow.addView(etNumber)
        inputRow.addView(btnAdd)
        root.addView(inputRow)

        // --- Contacts list ---
        root.addView(TextView(this).apply {
            text     = "Saved contacts"
            textSize = 13f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.parseColor("#BDBDBD"))
            setPadding(0, 20, 0, 6)
        })
        contactsContainer = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(contactsContainer)

        refreshContactRows()

        scroll.addView(root)
        setContentView(scroll)
    }

    // -----------------------------------------------------------------------
    //  Rebuild the list of contact rows
    // -----------------------------------------------------------------------
    private fun refreshContactRows() {
        contactsContainer.removeAllViews()
        if (contacts.isEmpty()) {
            contactsContainer.addView(TextView(this).apply {
                text     = "No contacts saved yet."
                textSize = 14f
                setTextColor(Color.GRAY)
            })
            return
        }
        for (number in contacts.toList()) {   // snapshot to avoid CME
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                setPadding(12, 8, 12, 8)
                setBackgroundColor(Color.parseColor("#1E1E1E"))
                val lp = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                )
                lp.setMargins(0, 0, 0, 6)
                layoutParams = lp
            }
            row.addView(TextView(this).apply {
                text     = number
                textSize = 16f
                setTextColor(Color.WHITE)
                val lp = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                layoutParams = lp
            })
            row.addView(Button(this).apply {
                text = "REMOVE"
                setBackgroundColor(Color.parseColor("#B71C1C"))
                setTextColor(Color.WHITE)
                textSize = 12f
                setOnClickListener {
                    AlertDialog.Builder(this@SosContactsActivity)
                        .setTitle("Remove contact?")
                        .setMessage("Remove $number from SOS list?")
                        .setPositiveButton("Remove") { _, _ ->
                            contacts.remove(number)
                            saveContacts(this@SosContactsActivity, contacts)
                            refreshContactRows()
                        }
                        .setNegativeButton("Cancel", null)
                        .show()
                }
            })
            contactsContainer.addView(row)
        }
    }
}
