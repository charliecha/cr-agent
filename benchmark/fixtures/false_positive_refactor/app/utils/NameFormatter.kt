package app.utils

object NameFormatter {

    fun formatName(first: String, last: String): String {
        val capitalized = capitalizeName(first) + " " + capitalizeName(last)
        return capitalized.trim()
    }

    private fun capitalizeName(part: String): String {
        if (part.isEmpty()) return part
        return part[0].uppercaseChar() + part.substring(1).lowercase()
    }
}
