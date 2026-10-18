from django.contrib.auth.hashers import check_password, identify_hasher, make_password
from django.test import SimpleTestCase


class PasswordHashingTests(SimpleTestCase):
    """F1: passwords are stored as bcrypt hashes."""

    def test_new_passwords_are_bcrypt(self):
        hashed = make_password('Correct-Horse-9')
        self.assertTrue(hashed.startswith('bcrypt_sha256$'), hashed[:20])
        self.assertTrue(check_password('Correct-Horse-9', hashed))
        self.assertFalse(check_password('wrong', hashed))

    def test_each_hash_is_salted(self):
        self.assertNotEqual(make_password('same'), make_password('same'))

    def test_long_passwords_are_not_cut_at_72_bytes(self):
        base = 'x' * 72
        hashed = make_password(base + 'A')
        self.assertFalse(check_password(base + 'B', hashed))

    def test_old_pbkdf2_hashes_still_verify_and_ask_for_upgrade(self):
        old = make_password('legacy-pass', hasher='pbkdf2_sha256')
        upgraded = []
        self.assertTrue(check_password('legacy-pass', old, setter=upgraded.append))
        self.assertEqual(upgraded, ['legacy-pass'])  # Django re-hashes with bcrypt
        self.assertEqual(identify_hasher(old).algorithm, 'pbkdf2_sha256')
