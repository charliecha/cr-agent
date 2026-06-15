package app.repository

class UserRepository {
    private val names = mapOf(1 to "Alice", 2 to "Bob")
    fun findUserName(id: Int): String? = names[id]
}
