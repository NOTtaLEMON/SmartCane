/*
 * ============================================================================
 *  SMART CANE CLIP-ON  |  YOLOv8 TFLite Object Detector
 * ============================================================================
 *  Loads the first valid YOLO TFLite asset and runs COCO 80-class detection.
 *  Output tensor: [1, 84, 2100] (detect) or [1, 116, 2100] (seg) â€” handled
 *  automatically.  Only RELEVANT_CLASSES are returned.
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

data class DetectionResult(
    val label: String,
    val confidence: Float,
    val boundingBox: RectF,         // normalized [0,1]
    val mask: Bitmap? = null        // unused â€” kept for overlay compat
)

class TfliteObjectDetector(context: Context) : AutoCloseable {

    companion object {
        // Tried in order; first file with size > 1 KB wins (skips 29-byte stubs)
        private val MODEL_CANDIDATES = arrayOf(
            "smartcane_segmentation_320_float16.tflite",
            "yolov8n_seg_320_float16.tflite",
            "yolov8n_320_float16.tflite",
            "yolov8s_320_float16.tflite",
            "yolov8m_320_float16.tflite"
        )
        private const val INPUT_SIZE      = 320
        private const val CONF_THRESHOLD  = 0.25f   // default fallback
        private const val IOU_THRESHOLD   = 0.45f
        private const val NUM_COORDS      = 4
        private const val NUM_COCO_CLASSES = 80

        private val RELEVANT_CLASSES = setOf(
            0,   // person
            1,   // bicycle
            2,   // car
            3,   // motorcycle
            5,   // bus
            7,   // truck — kept in detection, filtered in activity
            9,   // traffic light
            11,  // stop sign
            13,  // bench
            15,  // cat
            16,  // dog
            56,  // chair
            57,  // couch
            58,  // potted plant
            60,  // dining table
            63   // laptop
        )

        // Per-class confidence thresholds — lower for critical navigation hazards
        private val CLASS_CONFIDENCE_THRESHOLDS = mapOf(
            0  to 0.30f,  // person
            1  to 0.30f,  // bicycle
            2  to 0.25f,  // car
            3  to 0.25f,  // motorcycle
            5  to 0.25f,  // bus
            7  to 0.25f,  // truck — kept, filtered in activity
            9  to 0.20f,  // traffic light
            11 to 0.25f,  // stop sign
            13 to 0.35f,  // bench
            15 to 0.35f,  // cat
            16 to 0.35f,  // dog
            56 to 0.35f,  // chair
            57 to 0.35f,  // couch
            58 to 0.35f,  // potted plant
            60 to 0.35f,  // dining table
            63 to 0.35f   // laptop
        )

        // Friendly display labels for smart-cane relevant classes
        private val SMART_CANE_LABELS = mapOf(
            0  to "person",        1  to "bicycle",
            2  to "car",           3  to "motorcycle",
            5  to "bus",           7  to "truck",
            9  to "traffic light", 11 to "stop sign",
            13 to "bench",         15 to "cat",
            16 to "dog",           56 to "chair",
            57 to "couch",         58 to "potted plant",
            60 to "dining table",  63 to "laptop"
        )

        private val COCO_LABELS = arrayOf(
            "person","bicycle","car","motorcycle","airplane","bus","train","truck","boat",
            "traffic light","fire hydrant","stop sign","parking meter","bench","bird","cat",
            "dog","horse","sheep","cow","elephant","bear","zebra","giraffe","backpack",
            "umbrella","handbag","tie","suitcase","frisbee","skis","snowboard","sports ball",
            "kite","baseball bat","baseball glove","skateboard","surfboard","tennis racket",
            "bottle","wine glass","cup","fork","knife","spoon","bowl","banana","apple",
            "sandwich","orange","broccoli","carrot","hot dog","pizza","donut","cake","chair",
            "couch","potted plant","bed","dining table","toilet","tv","laptop","mouse",
            "remote","keyboard","cell phone","microwave","oven","toaster","sink","refrigerator",
            "book","clock","vase","scissors","teddy bear","hair drier","toothbrush"
        )

        private fun labelForClassIndex(c: Int) =
            SMART_CANE_LABELS[c] ?: COCO_LABELS.getOrElse(c) { "object" }

        private fun loadModel(context: Context): Interpreter {
            for (fname in MODEL_CANDIDATES) {
                val interp = runCatching {
                    val fd = context.assets.openFd(fname)
                    if (fd.declaredLength < 1024L) { fd.close(); return@runCatching null }
                    val model = FileInputStream(fd.fileDescriptor).channel
                        .map(FileChannel.MapMode.READ_ONLY, fd.startOffset, fd.declaredLength)
                    fd.close()
                    val gpu = runCatching { GpuDelegate() }.getOrNull()
                    val opts = Interpreter.Options().apply {
                        if (gpu != null) addDelegate(gpu) else numThreads = 4
                    }
                    Interpreter(model, opts)
                }.getOrNull()
                if (interp != null) return interp
            }
            throw IllegalStateException("No valid YOLO TFLite model found in assets.")
        }
    }

    private val interpreter = loadModel(context)

    fun detect(bitmap: Bitmap): List<DetectionResult> {
        val resized  = Bitmap.createScaledBitmap(bitmap, INPUT_SIZE, INPUT_SIZE, true)
        val inputBuf = bitmapToByteBuffer(resized)
        if (resized !== bitmap) resized.recycle()

        // min/max handles both [1, 84, 2100] and transposed [1, 2100, 84] formats
        val shape    = interpreter.getOutputTensor(0).shape()
        val numCh    = min(shape[1], shape[2])   // channels (84 or 116)
        val numAnch  = max(shape[1], shape[2])   // anchors  (2100)
        val outBuf   = Array(1) { Array(numCh) { FloatArray(numAnch) } }
        val outputs: MutableMap<Int, Any> = hashMapOf(0 to outBuf)
        interpreter.runForMultipleInputsOutputs(arrayOf(inputBuf), outputs)

        val raw = outBuf[0]
        val candidates = mutableListOf<DetectionResult>()

        for (a in 0 until numAnch) {
            var bestScore = -1f
            var bestClass = -1
            for (c in 0 until NUM_COCO_CLASSES) {
                if (c !in RELEVANT_CLASSES) continue
                val score = raw[NUM_COORDS + c][a]
                val threshold = CLASS_CONFIDENCE_THRESHOLDS[c] ?: CONF_THRESHOLD
                if (score >= threshold && score > bestScore) {
                    bestScore = score
                    bestClass = c
                }
            }
            if (bestClass == -1) continue

            val cx = raw[0][a]; val cy = raw[1][a]
            val w  = raw[2][a]; val h  = raw[3][a]
            candidates.add(DetectionResult(
                label       = labelForClassIndex(bestClass),
                confidence  = bestScore,
                boundingBox = RectF(
                    ((cx - w / 2f) / INPUT_SIZE).coerceIn(0f, 1f),
                    ((cy - h / 2f) / INPUT_SIZE).coerceIn(0f, 1f),
                    ((cx + w / 2f) / INPUT_SIZE).coerceIn(0f, 1f),
                    ((cy + h / 2f) / INPUT_SIZE).coerceIn(0f, 1f)
                )
            ))
        }
        return nonMaxSuppression(candidates).sortedByDescending { it.confidence }
    }

    private fun bitmapToByteBuffer(bitmap: Bitmap): ByteBuffer {
        val buf = ByteBuffer.allocateDirect(INPUT_SIZE * INPUT_SIZE * 3 * 4)
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

    // Class-aware NMS: only suppresses same-label overlapping boxes
    private fun nonMaxSuppression(dets: List<DetectionResult>): List<DetectionResult> {
        val sorted  = dets.sortedByDescending { it.confidence }
        val removed = BooleanArray(sorted.size)
        val kept    = mutableListOf<DetectionResult>()
        for (i in sorted.indices) {
            if (removed[i]) continue
            kept.add(sorted[i])
            for (j in i + 1 until sorted.size) {
                if (!removed[j] && sorted[i].label == sorted[j].label
                    && iou(sorted[i].boundingBox, sorted[j].boundingBox) > IOU_THRESHOLD) {
                    removed[j] = true
                }
            }
        }
        return kept
    }

    private fun iou(a: RectF, b: RectF): Float {
        val iw = max(0f, min(a.right, b.right)   - max(a.left, b.left))
        val ih = max(0f, min(a.bottom, b.bottom) - max(a.top,  b.top))
        val inter = iw * ih
        val union = (a.right - a.left) * (a.bottom - a.top) +
                    (b.right - b.left) * (b.bottom - b.top) - inter
        return if (union <= 0f) 0f else inter / union
    }

    override fun close() {
        interpreter.close()
    }
}
