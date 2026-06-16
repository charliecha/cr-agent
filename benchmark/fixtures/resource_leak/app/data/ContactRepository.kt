package app.data

import android.content.ContentResolver
import android.database.Cursor
import android.net.Uri
import android.provider.ContactsContract

data class Contact(val id: Long, val name: String, val phone: String)

class ContactRepository(private val contentResolver: ContentResolver) {

    // BUG: Cursor is never closed — resource leak on every call.
    // Should use cursor.use { } or an explicit cursor.close() in finally.
    fun loadContacts(nameFilter: String): List<Contact> {
        val uri: Uri = ContactsContract.CommonDataKinds.Phone.CONTENT_URI
        val projection = arrayOf(
            ContactsContract.CommonDataKinds.Phone._ID,
            ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME,
            ContactsContract.CommonDataKinds.Phone.NUMBER,
        )
        val selection = "${ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME} LIKE ?"
        val selectionArgs = arrayOf("%$nameFilter%")

        val cursor: Cursor? = contentResolver.query(uri, projection, selection, selectionArgs, null)

        val contacts = mutableListOf<Contact>()
        if (cursor != null && cursor.moveToFirst()) {
            do {
                val id = cursor.getLong(0)
                val name = cursor.getString(1)
                val phone = cursor.getString(2)
                contacts.add(Contact(id, name, phone))
            } while (cursor.moveToNext())
        }
        // MISSING: cursor?.close()
        return contacts
    }

    fun loadAllContacts(): List<Contact> = loadContacts("")
}
