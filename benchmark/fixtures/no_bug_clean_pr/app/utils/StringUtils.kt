package app.utils

class StringUtils {
    // Extracted helper — pure refactor, no logic change
    fun capitalize(s: String): String {
        if (s.isEmpty()) return s
        return s[0].uppercaseChar() + s.substring(1).lowercase()
    }
}
