/*
 * ============================================================================
 *  SMART CANE CLIP-ON  |  On-Device Vision Activity
 * ============================================================================
 *  Uses CameraX to grab frames from the phone camera, runs YOLOv8 TFLite
 *  inference ON-DEVICE (no WiFi / hotspot required), draws bounding boxes
 *  on a live overlay, and broadcasts detection summaries to PhoneDashboardActivity.
 *
 *  HOW TO USE
 *  ----------
 *  Launch from PhoneDashboardActivity.  The activity runs as a full-screen
 *  camera viewfinder with a text overlay listing detected objects.
 *
 *  No XML layout needed — UI is built programmatically.
 *
 *  DEPENDENCIES (app/build.gradle.kts)
 *  ------------------------------------
 *  implementation("androidx.camera:camera-camera2:1.3.4")
 *  implementation("androidx.camera:camera-lifecycle:1.3.4")
 *  implementation("androidx.camera:camera-view:1.3.4")
 *  implementation("org.tensorflow:tensorflow-lite:2.14.0")
 *  implementation("org.tensorflow:tensorflow-lite-support:0.4.4")
 *  implementation("org.tensorflow:tensorflow-lite-gpu:2.14.0")
 *  implementation("androidx.localbroadcastmanager:localbroadcastmanager:1.1.0")
 * ============================================================================
 */

package com.smartcane.gateway

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.ImageFormat
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import android.graphics.YuvImage
import android.media.AudioAttributes
import android.os.Build
import android.os.Bundle
import android.speech.tts.TextToSpeech
import android.util.Log
import android.util.Size
import android.view.Surface
import android.view.SurfaceHolder
import android.view.SurfaceView
import android.view.WindowManager
import android.widget.Button
import android.widget.FrameLayout
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.localbroadcastmanager.content.LocalBroadcastManager
import java.io.ByteArrayOutputStream
import java.util.Locale
import java.util.concurrent.Executors

class CaneVisionActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "CaneVision"
        const val ACTION_VISION_RESULT = "com.smartcane.gateway.VISION_RESULT"
        const val EXTRA_DETECTIONS     = "detections"   // String — comma-separated labels
        private const val ALERT_COOLDOWN_MS = 1000L  // 1.0 s between TTS alerts per label
        private const val TTS_MIN_CONFIDENCE  = 0.60f  // default TTS threshold
        // Per-label TTS confidence overrides
        private val TTS_LABEL_THRESHOLDS = mapOf(
            "pothole"    to 0.60f,
            "car"        to 0.70f,
            "motorcycle" to 0.70f,
            "bus"        to 0.70f,
            "bicycle"    to 0.70f,
            "vehicle"    to 0.70f,
            "van"        to 0.70f,
            "bike"       to 0.70f,
            "cart"       to 0.70f,
            "cycle"      to 0.70f,
            "e-rickshaw" to 0.70f,
            "motorbike"  to 0.70f,
            "rickshaw"   to 0.70f,
            "tractor"    to 0.70f
        )
    }

    private var potholeDetector: PotholeDetector? = null
    private var electricPoleDetector: ElectricPoleDetector? = null
    private var stairsDetector: StairsDetector? = null
    private var treeDetector: TreeDetector? = null
    private var carDetector: CarDetector? = null

    private lateinit var previewView: PreviewView
    private lateinit var overlayView: DetectionOverlayView
    private lateinit var statusText:  TextView

    private val inferenceExecutor = Executors.newSingleThreadExecutor()
    private var detector: TfliteObjectDetector? = null
    private val lastAlertMs = mutableMapOf<String, Long>()
    private var tts: TextToSpeech? = null
    private var ttsReady = false
    // Streak tracking — speak only when the same label is top-confidence 2 frames in a row
    private var lastTopLabel: String? = null
    private var topLabelStreak = 0

    // -----------------------------------------------------------------------
    //  Permission request
    // -----------------------------------------------------------------------
    private val cameraPermLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) startCamera()
            else { statusText.text = "Camera permission denied."; }
        }

    // -----------------------------------------------------------------------
    //  Lifecycle
    // -----------------------------------------------------------------------
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // --- Build UI programmatically ---
        previewView = PreviewView(this).apply {
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        }
        overlayView = DetectionOverlayView(this).apply {
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        }
        statusText = TextView(this).apply {
            text  = "Initialising vision..."
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.argb(220, 0, 0, 0))
            textSize = 18f
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            setShadowLayer(8f, 0f, 0f, Color.BLACK)
            setPadding(16, 8, 16, 8)
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.WRAP_CONTENT
            )
        }
        val dashboardBtn = Button(this).apply {
            text = "Dashboard"
            setBackgroundColor(Color.argb(200, 0, 123, 255))
            setTextColor(Color.WHITE)
            textSize = 16f
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                gravity = android.view.Gravity.BOTTOM or android.view.Gravity.END
                setMargins(16, 16, 16, 16)
            }
            setOnClickListener {
                startActivity(Intent(this@CaneVisionActivity, PhoneDashboardActivity::class.java))
            }
        }
        val root = FrameLayout(this).apply {
            addView(previewView)
            addView(overlayView)
            addView(statusText)
            addView(dashboardBtn)
        }
        setContentView(root)

        // Keep screen on — this is a cane assistant, no manual interaction needed
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        // Text-to-Speech engine
        tts = TextToSpeech(this) { status ->
            if (status == TextToSpeech.SUCCESS) {
                val result = tts?.setLanguage(Locale.US)
                if (result == TextToSpeech.LANG_MISSING_DATA || result == TextToSpeech.LANG_NOT_SUPPORTED) {
                    tts?.language = Locale.getDefault()
                }
                tts?.setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ASSISTANCE_ACCESSIBILITY)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                )
                tts?.setSpeechRate(1.0f)
                ttsReady = true
            } else {
                Log.e(TAG, "TTS init failed with status $status — voice alerts disabled")
                runOnUiThread {
                    statusText.text = "⚠ Voice alerts unavailable (TTS engine not found). Install \"Speech Services by Google\" from Play Store."
                }
            }
        }

        // Load TFLite models
        runCatching {
            detector = TfliteObjectDetector(this)
            Log.i(TAG, "TFLite model loaded")
            statusText.text = "Vision active — model loaded"
        }.onFailure {
            statusText.text = "No YOLO TFLite model found in assets.\n" +
                    "Place one of: yolov8n_seg_320_float16.tflite, yolov8s_seg_320_float16.tflite,\n" +
                    "yolov8m_seg_320_float16.tflite, yolov8n_320_float16.tflite,\n" +
                    "yolov8s_320_float16.tflite, yolov8m_320_float16.tflite"
            Log.e(TAG, "Model load failed", it)
        }
        runCatching {
            potholeDetector = PotholeDetector(this)
            Log.i(TAG, "Pothole model loaded")
        }.onFailure {
            Log.e(TAG, "Pothole model load failed", it)
        }
        runCatching {
            electricPoleDetector = ElectricPoleDetector(this)
            Log.i(TAG, "Electric pole model loaded")
        }.onFailure {
            Log.e(TAG, "Electric pole model load failed", it)
        }
        runCatching {
            stairsDetector = StairsDetector(this)
            Log.i(TAG, "Stairs model loaded")
        }.onFailure {
            Log.e(TAG, "Stairs model load failed", it)
        }
        runCatching {
            treeDetector = TreeDetector(this)
            Log.i(TAG, "Tree model loaded")
        }.onFailure {
            Log.e(TAG, "Tree model load failed", it)
        }
        runCatching {
            carDetector = CarDetector(this)
            Log.i(TAG, "Car model loaded")
        }.onFailure {
            Log.e(TAG, "Car model load failed", it)
        }
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
                == PackageManager.PERMISSION_GRANTED) {
            startCamera()
        } else {
            cameraPermLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        inferenceExecutor.shutdown()
        detector?.close()
        potholeDetector?.close()
        electricPoleDetector?.close()
        stairsDetector?.close()
        treeDetector?.close()
        carDetector?.close()
        tts?.stop()
        tts?.shutdown()
    }

    // -----------------------------------------------------------------------
    //  CameraX setup
    // -----------------------------------------------------------------------
    private fun startCamera() {
        val providerFuture = ProcessCameraProvider.getInstance(this)
        providerFuture.addListener({
            val provider = providerFuture.get()

            val preview = Preview.Builder().build().also {
                it.setSurfaceProvider(previewView.surfaceProvider)
            }
            val analysis = ImageAnalysis.Builder()
                .setTargetResolution(Size(320, 240))   // matches model input size — no extra downscale step
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .build()
                .also { it.setAnalyzer(inferenceExecutor, ::analyzeFrame) }

            try {
                provider.unbindAll()
                provider.bindToLifecycle(
                    this,
                    CameraSelector.DEFAULT_BACK_CAMERA,
                    preview,
                    analysis
                )
                statusText.text = "Vision active — scanning environment..."
            } catch (e: Exception) {
                Log.e(TAG, "Camera bind failed", e)
                statusText.text = "Camera error: ${e.message}"
            }
        }, ContextCompat.getMainExecutor(this))
    }

    // -----------------------------------------------------------------------
    //  Per-frame inference
    // -----------------------------------------------------------------------
    private fun analyzeFrame(imageProxy: ImageProxy) {
        val bitmap = imageProxy.toBitmap()
        val bitmapW = bitmap.width.toFloat()
        val bitmapH = bitmap.height.toFloat()
        imageProxy.close()

        // Pre-scale once to model input size — each detector's internal resize becomes a no-op
        // (Bitmap.createScaledBitmap returns the same reference when dimensions already match)
        val scaled = Bitmap.createScaledBitmap(bitmap, 320, 320, true)
        if (scaled !== bitmap) bitmap.recycle()

        val det = detector
        if (det == null) {
            scaled.recycle()
            runOnUiThread {
                statusText.text = "Camera active — no YOLO model loaded. Place a TFLite model in assets and restart."
                overlayView.setResults(emptyList(), bitmapW, bitmapH)
            }
            return
        }

        val results = runCatching { det.detect(scaled) }.getOrElse {
            Log.e(TAG, "Inference failed", it); emptyList()
        }
        val potholeResults = runCatching { potholeDetector?.detect(scaled) ?: emptyList() }.getOrElse { emptyList() }
        val electricPoleResults = runCatching { electricPoleDetector?.detect(scaled) ?: emptyList() }.getOrElse { emptyList() }
        val stairsResults = runCatching { stairsDetector?.detect(scaled) ?: emptyList() }.getOrElse { emptyList() }
        val treeResults = runCatching { treeDetector?.detect(scaled) ?: emptyList() }.getOrElse { emptyList() }
        val carResults  = runCatching { carDetector?.detect(scaled) ?: emptyList() }.getOrElse { emptyList() }
        scaled.recycle()
        val allResults = (results + potholeResults + electricPoleResults + stairsResults + treeResults + carResults)
            .filter { it.label != "truck" }
            .sortedByDescending { it.confidence }   // highest confidence first

        // Update overlay on main thread
        runOnUiThread {
            overlayView.setResults(allResults, bitmapW, bitmapH)
            if (allResults.isEmpty()) {
                statusText.text = "Clear path"
            } else {
                val top3 = allResults.take(3).joinToString(", ") {
                    "${it.label} (${(it.confidence * 100).toInt()}%)"
                }
                statusText.text = "Detected: $top3"
            }
        }

        // Broadcast to PhoneDashboardActivity
        if (allResults.isNotEmpty()) {
            val summary = allResults.take(5).joinToString(",") { it.label }
            LocalBroadcastManager.getInstance(this).sendBroadcast(
                Intent(ACTION_VISION_RESULT).putExtra(EXTRA_DETECTIONS, summary)
            )
            // Streak-gated TTS: only speak when the same top label is seen 2 frames in a row.
            // This prevents rapid label-switching from generating noisy or missed alerts.
            val topDet = allResults.firstOrNull { det ->
                val minConf = TTS_LABEL_THRESHOLDS[det.label] ?: TTS_MIN_CONFIDENCE
                det.confidence >= minConf
            }
            if (topDet != null) {
                if (topDet.label == lastTopLabel) topLabelStreak++ else { lastTopLabel = topDet.label; topLabelStreak = 1 }
                if (topLabelStreak >= 2 &&
                    (System.currentTimeMillis() - (lastAlertMs[topDet.label] ?: 0L)) >= ALERT_COOLDOWN_MS) {
                    fireHazardAlert(topDet)
                }
            } else {
                lastTopLabel = null
                topLabelStreak = 0
            }
        }
    }

    private fun fireHazardAlert(det: DetectionResult) {
        val minConf = TTS_LABEL_THRESHOLDS[det.label] ?: TTS_MIN_CONFIDENCE
        if (det.confidence < minConf) return
        val now = System.currentTimeMillis()
        if (now - (lastAlertMs[det.label] ?: 0L) < ALERT_COOLDOWN_MS) return
        lastAlertMs[det.label] = now
        if (ttsReady) {
            val speakStatus = tts?.speak("${det.label} detected", TextToSpeech.QUEUE_FLUSH, null, det.label)
            if (speakStatus != TextToSpeech.SUCCESS) {
                Log.e(TAG, "TTS speak failed for ${det.label} with code=$speakStatus")
                runOnUiThread {
                    statusText.text = "⚠ Voice alert failed. Check phone TTS engine and media volume."
                }
            }
        }
    }

    // -----------------------------------------------------------------------
    //  ImageProxy → Bitmap  (YUV_420_888 conversion)
    // -----------------------------------------------------------------------
    private fun ImageProxy.toBitmap(): Bitmap {
        val yBuffer = planes[0].buffer
        val vuBuffer = planes[2].buffer
        val ySize  = yBuffer.remaining()
        val vuSize = vuBuffer.remaining()
        val nv21   = ByteArray(ySize + vuSize)
        yBuffer.get(nv21, 0, ySize)
        vuBuffer.get(nv21, ySize, vuSize)
        val yuvImage = YuvImage(nv21, ImageFormat.NV21, width, height, null)
        val out = ByteArrayOutputStream()
        yuvImage.compressToJpeg(Rect(0, 0, width, height), 45, out)
        val bytes = out.toByteArray()
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
    }
}

// ---------------------------------------------------------------------------
//  Bounding-box overlay view (draws on top of the camera preview)
// ---------------------------------------------------------------------------
class DetectionOverlayView(context: android.content.Context) :
    android.view.View(context) {

    private var results: List<DetectionResult> = emptyList()
    private var srcW = 1f
    private var srcH = 1f

    private val boxPaint = Paint().apply {
        style       = Paint.Style.STROKE
        strokeWidth = 6f
        color       = Color.CYAN
    }
    private val labelBgPaint = Paint().apply {
        style = Paint.Style.FILL
        color = Color.argb(235, 0, 0, 0)
    }
    private val textPaint = Paint().apply {
        color    = Color.WHITE
        textSize = 52f
        typeface = android.graphics.Typeface.DEFAULT_BOLD
        setShadowLayer(6f, 0f, 0f, Color.BLACK)
    }

    fun setResults(list: List<DetectionResult>, bitmapW: Float, bitmapH: Float) {
        results.forEach { it.mask?.recycle() }
        results = list
        srcW    = bitmapW
        srcH    = bitmapH
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (srcW == 0f || srcH == 0f) return
        // Coords are normalized [0,1] — scale directly to view dimensions
        val scaleX = width.toFloat()
        val scaleY = height.toFloat()
        for (det in results) {
            val box = RectF(
                det.boundingBox.left   * scaleX,
                det.boundingBox.top    * scaleY,
                det.boundingBox.right  * scaleX,
                det.boundingBox.bottom * scaleY
            )

            det.mask?.let { canvas.drawBitmap(it, null, box, null) }

            canvas.drawRect(box, boxPaint)

            val label = "${det.label}  ${(det.confidence * 100).toInt()}%"
            val textW = textPaint.measureText(label) + 16f
            val textH = textPaint.textSize + 12f
            val bgTop = (box.top - textH).coerceAtLeast(0f)
            val textStartX = (box.left).coerceAtMost(width.toFloat() - textW)
            canvas.drawRect(textStartX, bgTop, textStartX + textW, bgTop + textH, labelBgPaint)
            canvas.drawText(label, textStartX + 8f, bgTop + textH - 8f, textPaint)
        }
    }
}
