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
import android.os.Bundle
import android.util.Log
import android.view.Surface
import android.view.SurfaceHolder
import android.view.SurfaceView
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
import java.util.concurrent.Executors

class CaneVisionActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "CaneVision"
        const val ACTION_VISION_RESULT = "com.smartcane.gateway.VISION_RESULT"
        const val EXTRA_DETECTIONS     = "detections"   // String — comma-separated labels
    }

    private lateinit var previewView: PreviewView
    private lateinit var overlayView: DetectionOverlayView
    private lateinit var statusText:  TextView

    private val inferenceExecutor = Executors.newSingleThreadExecutor()
    private var detector: TfliteObjectDetector? = null

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
            setBackgroundColor(Color.argb(160, 0, 0, 0))
            textSize = 14f
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

        // Load TFLite model if available
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

        val det = detector
        if (det == null) {
            runOnUiThread {
                statusText.text = "Camera active — no YOLO model loaded. Place a TFLite model in assets and restart."
                overlayView.setResults(emptyList(), bitmap.width.toFloat(), bitmap.height.toFloat())
            }
            imageProxy.close()
            return
        }

        val results = runCatching { det.detect(bitmap) }.getOrElse {
            Log.e(TAG, "Inference failed", it); emptyList()
        }
        imageProxy.close()

        // Update overlay on main thread
        runOnUiThread {
            overlayView.setResults(results, bitmap.width.toFloat(), bitmap.height.toFloat())
            if (results.isEmpty()) {
                statusText.text = "Clear path"
            } else {
                val top3 = results.take(3).joinToString(", ") {
                    "${it.label} (${(it.confidence * 100).toInt()}%)"
                }
                statusText.text = "Detected: $top3"
            }
        }

        // Broadcast to PhoneDashboardActivity
        if (results.isNotEmpty()) {
            val summary = results.take(5).joinToString(",") { it.label }
            LocalBroadcastManager.getInstance(this).sendBroadcast(
                Intent(ACTION_VISION_RESULT).putExtra(EXTRA_DETECTIONS, summary)
            )
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
        yuvImage.compressToJpeg(Rect(0, 0, width, height), 85, out)
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
        strokeWidth = 4f
        color       = Color.CYAN
    }
    private val labelPaint = Paint().apply {
        style    = Paint.Style.FILL
        color    = Color.argb(200, 0, 0, 0)
        textSize = 36f
    }
    private val textPaint = Paint().apply {
        color    = Color.WHITE
        textSize = 36f
    }

    fun setResults(list: List<DetectionResult>, bitmapW: Float, bitmapH: Float) {
        results = list
        srcW    = bitmapW
        srcH    = bitmapH
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val scaleX = width  / srcW
        val scaleY = height / srcH
        for (det in results) {
            val box = RectF(
                det.boundingBox.left   * srcW * scaleX,
                det.boundingBox.top    * srcH * scaleY,
                det.boundingBox.right  * srcW * scaleX,
                det.boundingBox.bottom * srcH * scaleY
            )
            
            // Draw segmentation mask if available
            det.mask?.let { maskBitmap ->
                canvas.drawBitmap(maskBitmap, null, box, null)
            }

            canvas.drawRect(box, boxPaint)
            val label = "${det.label} ${(det.confidence * 100).toInt()}%"
            canvas.drawRect(box.left, box.top - 42f, box.left + labelPaint.measureText(label) + 8f, box.top, labelPaint)
            canvas.drawText(label, box.left + 4f, box.top - 8f, textPaint)
        }
    }
}
