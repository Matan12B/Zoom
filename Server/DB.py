import sqlite3
import os
import hashlib
import hmac


class DB:
    def __init__(self):
        # Store the SQLite file beside this module, regardless of launch directory.
        _here = os.path.dirname(os.path.abspath(__file__))
        self.DBname = os.path.join(_here, "UserManagementDB.db")
        # conn is the database connection; curr executes SQL statements.
        self.conn = None
        self.curr = None
        self._createDB()

    def _createDB(self):
        """
        connect db and create table if not exist
        """
        self.conn = sqlite3.connect(self.DBname, check_same_thread=False)
        self.curr = self.conn.cursor()

        sql = (
            "CREATE TABLE IF NOT EXISTS users ("
            "userName TEXT PRIMARY KEY, "
            "password TEXT)"
        )

        self.curr.execute(sql)
        self.conn.commit()

    def close(self):
        """
        Commit changes and close DB
        """
        self.conn.commit()
        self.conn.close()

    def user_exists(self, userName):
        """
        return user row if exists else None
        """
        sql = "SELECT userName FROM users WHERE userName = ?"
        self.curr.execute(sql, (userName,))
        return self.curr.fetchone()

    def hash_password(self, password):
        """
        Create a salted PBKDF2 password hash for database storage.
        :param password:
        :return: "salt_in_hex$hash_in_hex"
        """
        # A new 16-byte cryptographically random salt is generated for every
        # password. Therefore, equal passwords normally produce different hashes.
        salt = os.urandom(16)
        # PBKDF2-HMAC-SHA256 deliberately performs 100,000 iterations. This makes
        # each password guess more expensive and slows brute-force attacks.
        hashed = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            salt,
            100000
        )
        # The salt is not secret. It must be stored so login can calculate the
        # same hash again. Hex encoding makes both byte values safe to store as TEXT.
        return f"{salt.hex()}${hashed.hex()}"

    def verify_password(self, password, saved_password):
        """
        Hash the entered password with the stored salt and compare the results.
        :param password:
        :param saved_password: Database value in "salt_hex$hash_hex" format.
        :return:
        """
        result = False
        try:
            # Recover the exact salt and expected hash used during registration.
            salt_hex, hash_hex = saved_password.split("$")
            salt = bytes.fromhex(salt_hex)
            saved_hash = bytes.fromhex(hash_hex)

            # Use the same algorithm, salt, and iteration count as hash_password().
            check_hash = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode(),
                salt,
                100000
            )

            # compare_digest avoids leaking comparison progress through timing.
            result = hmac.compare_digest(check_hash, saved_hash)
        except Exception:
            pass
        return result

    def add_user(self, userName, password):
        """
        add user to db
        """
        userName = userName.strip()
        password = password.strip()
        result = False

        if not userName or not password:
            pass
        elif len(userName) > 15 or len(password) > 10:
            pass
        elif self.user_exists(userName):
            pass
        else:
            # Only the salt and derived hash are stored, never the plain password.
            hashed_password = self.hash_password(password)
            sql = "INSERT INTO users VALUES (?, ?)"
            self.curr.execute(sql, (userName, hashed_password))
            self.conn.commit()
            result = True

        return result

    def update_password(self, userName, new_password):
        """
        update user password
        """
        userName = userName.strip()
        new_password = new_password.strip()
        result = False

        if not userName or not new_password:
            pass
        elif len(new_password) > 10:
            pass
        elif not self.user_exists(userName):
            pass
        else:
            hashed_password = self.hash_password(new_password)
            sql = "UPDATE users SET password = ? WHERE userName = ?"
            self.curr.execute(sql, (hashed_password, userName))
            self.conn.commit()
            result = True

        return result

    def verify_user(self, userName, password):
        """
        check if username and password match
        """
        sql = "SELECT password FROM users WHERE userName = ?"
        self.curr.execute(sql, (userName,))
        row = self.curr.fetchone()

        result = False
        if row:
            result = self.verify_password(password, row[0])

        return result

    def get_all_users(self):
        """
        return list of all usernames
        """
        sql = "SELECT userName FROM users"
        self.curr.execute(sql)

        names = []
        for user in self.curr.fetchall():
            names.append(user[0])

        return names


if __name__ == "__main__":
    myDB = DB()
    print("Adding user:", myDB.add_user("user1", "123456"))
    print("Verify נכון:", myDB.verify_user("user1", "123456"))
    print("Verify לא נכון:", myDB.verify_user("user1", "111111"))
    print("All users:", myDB.get_all_users())
    myDB.close()
