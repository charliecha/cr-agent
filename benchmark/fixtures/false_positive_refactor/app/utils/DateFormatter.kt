package app.utils

import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

object DateFormatter {

    private const val ISO_DATE_PATTERN = "yyyy-MM-dd"
    private const val DISPLAY_DATE_PATTERN = "MMM dd, yyyy"
    private const val DISPLAY_DATETIME_PATTERN = "MMM dd, yyyy HH:mm"

    private val isoDateFormat = SimpleDateFormat(ISO_DATE_PATTERN, Locale.US)
    private val displayDateFormat = SimpleDateFormat(DISPLAY_DATE_PATTERN, Locale.US)
    private val displayDateTimeFormat = SimpleDateFormat(DISPLAY_DATETIME_PATTERN, Locale.US)

    fun formatAsIsoDate(date: Date): String {
        return isoDateFormat.format(date)
    }

    fun formatAsDisplayDate(date: Date): String {
        return displayDateFormat.format(date)
    }

    fun formatAsDisplayDateTime(date: Date): String {
        return displayDateTimeFormat.format(date)
    }

    fun parseIsoDate(dateString: String): Date? {
        return try {
            isoDateFormat.parse(dateString)
        } catch (e: Exception) {
            null
        }
    }

    fun getRelativeTimeString(date: Date): String {
        val now = System.currentTimeMillis()
        val diff = now - date.time
        val seconds = diff / 1000
        val minutes = seconds / 60
        val hours = minutes / 60
        val days = hours / 24

        return when {
            days > 7 -> formatAsDisplayDate(date)
            days > 0 -> "$days day${if (days > 1) "s" else ""} ago"
            hours > 0 -> "$hours hour${if (hours > 1) "s" else ""} ago"
            minutes > 0 -> "$minutes minute${if (minutes > 1) "s" else ""} ago"
            else -> "just now"
        }
    }
}
