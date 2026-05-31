/*
 * ============================================================================
 *  SMART CANE CLIP-ON  |  Stairs Detector (YOLOv8n TFLite)
 * ============================================================================
 *  Loads steps_kerb_float16.tflite — a YOLOv8n detection model trained
 *  on stairs/steps/kerb images, nc=2 (classes: object, stairs).
 *  Output tensor: [1, 6, 2100]  (4 box coords + 2 class scores × 2100 anchors).
 *
 *  ASSET REQUIRED
 *  --------------
 *  app/src/main/assets/steps_kerb_float16.tflite
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

class StairsDetector(context: Context) : AutoCloseable {

    companion object {
        private const val MODEL_FILENAME = "steps_kerb_float16.tflite"
        private const val INPUT_SIZE     = 320
        private const val CONF_THRESHOLD = 0.65f
        private const val IOU_THRESHOLD  = 0.45f
        private const val NUM_COORDS     = 4

        private val labels = arrayOf("object", "stairs")
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

    fun detect(bitmap: Bitmap): List<DetectionResult> {
        val resized  = Bitmap.createScaledBitmap(bitmap, INPUT_SIZE, INPUT_SIZE, true)
        val inputBuf = bitmapToByteBuffer(resized)
        if (resized !== bitmap) resized.recycle()

        val shape   = interpreter.getOutputTensor(0).shape()
        val numCh   = minOf(shape[1], shape[2])
        val numAnch = maxOf(shape[1], shape[2])
        val outBuf  = Array(1) { Array(numCh) { FloatArray(numAnch) } }
        val outputs: MutableMap<Int, Any> = hashMapOf(0 to outBuf)
        interpreter.runForMultipleInputsOutputs(arrayOf(inputBuf), outputs)

        val raw = outBuf[0]
        val candidates = mutableListOf<DetectionResult>()
        val numClasses = numCh - NUM_COORDS

        for (a in 0 until numAnch) {
            var bestScore = CONF_THRESHOLD
            var bestClass = -1
            for (c in 0 until numClasses) {
                val score = raw[NUM_COORDS + c][a]
                if (score > bestScore) {
                    bestScore = score
                    bestClass = c
                }
            }
            if (bestClass == -1) continue

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
                    label       = labels.getOrElse(bestClass) { "stairs" },
                    confidence  = bestScore,
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
