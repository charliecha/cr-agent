// NEW version (after PR): signature changed to require includeDeleted
// This is the "after" state — the bug is that UserService still calls old signature
package app.repository

data class User(val id: Int, val name: String, val deleted: Boolean = false)

class UserRepository {
    private val users = listOf(
        User(1, "Alice"),
        User(2, "Bob", deleted = true),
    )

    // CHANGED: added includeDeleted parameter (breaking change)
    fun getUser(id: Int, includeDeleted: Boolean = false): User? {
        return users.find { it.id == id && (includeDeleted || !it.deleted) }
    }
}
