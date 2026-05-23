/*
 * ============================================================================
 *  SMART CANE CLIP-ON  |  Pothole Detector (YOLOv8n TFLite)
 * ============================================================================
 *  Loads pothole_detector_320_float16.tflite — a YOLOv8n detection model
 *  trained on 3029 pothole images.  Output tensor: [1, 12, 2100]
 *  (4 box coords + 8 class scores × 2100 anchors).  Only class index 4
 *  (pothole in our Smart Cane taxonomy) is returned.
 *
 *  ASSET REQUIRED
 *  --------------
 *  app/src/main/assets/pothole_detector_320_float16.tflite
 * ============================================================================
 */

package com.smartcane.gateway

import android.content.Context
import android.graphics.Bitmap
import android.graphics.RectF
import org.tensorflow.lite.Interpreter
import org.tensorflow.lite.gpu.GpuDelegate
import java.io.FileInputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.channels.FileChannel
import kotlin.math.max
import kotlin.math.min

class PotholeDetector(context: Context) : AutoCloseable {

    companion object {
        private const val MODEL_FILENAME = "pothole_detector_320_float16.tflite"
        private const val INPUT_SIZE     = 320
        private const val POTHOLE_CLASS  = 4
        private const val CONF_THRESHOLD = 0.40f
        private const val IOU_THRESHOLD  = 0.45f
        private const val NUM_COORDS     = 4
        private const val NUM_CLASSES    = 8
    }

    private val gpuDelegate = runCatching { GpuDelegate() }.getOrNull()
    private val interpreter: Interpreter

    init {
        val assetFd = context.assets.openFd(MODEL_FILENAME)
        val inputStream = FileInputStream(assetFd.fileDescriptor)
        val model = inputStream.channel.map(
            FileChannel.MapMode.READ_ONLY,
            assetFd.startOffset,
            assetFd.declaredLength
        )
        val opts = Interpreter.Options().apply {
            if (gpuDelegate != null) addDelegate(gpuDelegate)
            else numThreads = 4
        }
        interpreter = Interpreter(model, opts)
        inputStream.close()
        assetFd.close()
    }

    /**
     * Run pothole detection on [bitmap].
     * Returns only pothole detections sorted by confidence (highest first).
     */
    fun detect(bitmap: Bitmap): List<DetectionResult> {
        val resized  = Bitmap.createScaledBitmap(bitmap, INPUT_SIZE, INPUT_SIZE, true)
        val inputBuf = bitmapToByteBuffer(resized)

        // Output: [1, 12, 2100]
        val output = Array(1) { Array(NUM_COORDS + NUM_CLASSES) { FloatArray(2100) } }
        interpreter.run(inputBuf, output)

        val raw = output[0]
        val candidates = mutableListOf<DetectionResult>()

        for (a in 0 until 2100) {
            val score = raw[NUM_COORDS + POTHOLE_CLASS][a]
            if (score < CONF_THRESHOLD) continue

            val cx = raw[0][a]
            val cy = raw[1][a]
            val w  = raw[2][a]
            val h  = raw[3][a]

            val x1 = ((cx - w / 2f) / INPUT_SIZE).coerceIn(0f, 1f)
            val y1 = ((cy - h / 2f) / INPUT_SIZE).coerceIn(0f, 1f)
            val x2 = ((cx + w / 2f) / INPUT_SIZE).coerceIn(0f, 1f)
            val y2 = ((cy + h / 2f) / INPUT_SIZE).coerceIn(0f, 1f)

            candidates.add(
                DetectionResult(
                    label       = "Pothole",
                    confidence  = score,
                    boundingBox = RectF(x1, y1, x2, y2)
                )
            )
        }

        return nms(candidates).sortedByDescending { it.confidence }
    }

    private fun bitmapToByteBuffer(bitmap: Bitmap): ByteBuffer {
        val buf = ByteBuffer.allocateDirect(1 * INPUT_SIZE * INPUT_SIZE * 3 * 4)
            .order(ByteOrder.nativeOrder())
        val pixels = IntArray(INPUT_SIZE * INPUT_SIZE)
        bitmap.getPixels(pixels, 0, INPUT_SIZE, 0, 0, INPUT_SIZE, INPUT_SIZE)
        for (px in pixels) {
            buf.putFloat(((px shr 16) and 0xFF) / 255f)
            buf.putFloat(((px shr 8)  and 0xFF) / 255f)
            buf.putFloat(( px         and 0xFF) / 255f)
        }
        buf.rewind()
        return buf
    }

    private fun nms(dets: List<DetectionResult>): List<DetectionResult> {
        val sorted  = dets.sortedByDescending { it.confidence }.toMutableList()
        val kept    = mutableListOf<DetectionResult>()
        val removed = BooleanArray(sorted.size)
        for (i in sorted.indices) {
            if (removed[i]) continue
            kept.add(sorted[i])
            for (j in i + 1 until sorted.size) {
                if (!removed[j] && iou(sorted[i].boundingBox, sorted[j].boundingBox) > IOU_THRESHOLD) {
                    removed[j] = true
                }
            }
        }
        return kept
    }

    private fun iou(a: RectF, b: RectF): Float {
        val interX1 = max(a.left, b.left)
        val interY1 = max(a.top, b.top)
        val interX2 = min(a.right, b.right)
        val interY2 = min(a.bottom, b.bottom)
        val interW  = max(0f, interX2 - interX1)
        val interH  = max(0f, interY2 - interY1)
        val interArea = interW * interH
        val unionArea = (a.right - a.left) * (a.bottom - a.top) +
                        (b.right - b.left) * (b.bottom - b.top) - interArea
        return if (unionArea <= 0f) 0f else interArea / unionArea
    }

    override fun close() {
        interpreter.close()
        gpuDelegate?.close()
    }
}
