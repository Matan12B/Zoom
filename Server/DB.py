import sqlite3
import os
import hashlib
import hmac


class DB:
    def __init__(self):
        _here = os.path.dirname(os.path.abspath(__file__))
        self.DBname = os.path.join(_here, "UserManagementDB.db")
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
        Return hashed password with salt.
        :param password:
        :return:
        """
        salt = os.urandom(16)
        hashed = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            salt,
            100000
        )
        return f"{salt.hex()}${hashed.hex()}"

    def verify_password(self, password, saved_password):
        """
        Check if password matches saved hash.
        :param password:
        :param saved_password:
        :return:
        """
        try:
            salt_hex, hash_hex = saved_password.split("$")
            salt = bytes.fromhex(salt_hex)
            saved_hash = bytes.fromhex(hash_hex)

            check_hash = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode(),
                salt,
                100000
            )

            return hmac.compare_digest(check_hash, saved_hash)
        except Exception:
            return False

    def add_user(self, userName, password):
        """
        add user to db
        """
        userName = userName.strip()
        password = password.strip()

        if not userName or not password:
            return False

        if len(userName) > 15 or len(password) > 10:
            return False

        if self.user_exists(userName):
            return False

        hashed_password = self.hash_password(password)

        sql = "INSERT INTO users VALUES (?, ?)"
        self.curr.execute(sql, (userName, hashed_password))
        self.conn.commit()
        return True

    def update_password(self, userName, new_password):
        """
        update user password
        """
        userName = userName.strip()
        new_password = new_password.strip()

        if not userName or not new_password:
            return False

        if len(new_password) > 10:
            return False

        if not self.user_exists(userName):
            return False

        hashed_password = self.hash_password(new_password)

        sql = "UPDATE users SET password = ? WHERE userName = ?"
        self.curr.execute(sql, (hashed_password, userName))
        self.conn.commit()
        return True

    def verify_user(self, userName, password):
        """
        check if username and password match
        """
        sql = "SELECT password FROM users WHERE userName = ?"
        self.curr.execute(sql, (userName,))
        row = self.curr.fetchone()

        if not row:
            return False

        return self.verify_password(password, row[0])

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