package app.ui

import app.repository.UserRepository

class ProfileFragment {
    private val repo = UserRepository()

    fun loadProfile(userId: Int) {
        val userName = repo.findUserName(userId)

        // BUG: !! on nullable return — crashes if userId not found
        val uppercased = userName!!.uppercase()
        showName(uppercased)
    }

    private fun showName(name: String) {
        println("Hello, $name")
    }
}
