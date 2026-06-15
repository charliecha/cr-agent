package app.service

import app.repository.UserRepository

class UserService(private val repo: UserRepository) {

    // BUG: still calling getUser(id) with old single-arg signature.
    // After the repo change, this silently filters out deleted users
    // even when the caller (admin screen) expects to see them.
    fun getUserById(id: Int): String {
        val user = repo.getUser(id)   // ← should be getUser(id, includeDeleted = true) for admin
        return user?.name ?: "Not found"
    }
}
