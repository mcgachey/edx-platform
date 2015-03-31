from django.test import TestCase

from lti_provider.models import LtiConsumer
from lti_provider.signature_validator import SignatureValidator

class SignatureValidatorTest(TestCase):
    """
    Tests for the custom SignatureValidator class that uses the oauthlib library
    to check message signatures. Note that these tests mock out the library
    itself, since we assume it to be correct.
    """

    def test_valid_client_key(self):
        key = 'valid_key'
        self.assertTrue(SignatureValidator().check_client_key(key))

    def test_long_client_key(self):
        key = '0123456789012345678901234567890123456789'
        self.assertFalse(SignatureValidator().check_client_key(key))

    def test_empty_client_key(self):
        key = ''
        self.assertFalse(SignatureValidator().check_client_key(key))

    def test_null_client_key(self):
        key = None
        self.assertFalse(SignatureValidator().check_client_key(key))

    def test_valid_nonce(self):
        nonce = '0123456789012345678901234567890123456789012345678901234567890123'
        self.assertTrue(SignatureValidator().check_nonce(nonce))

    def test_long_nonce(self):
        nonce = '01234567890123456789012345678901234567890123456789012345678901234'
        self.assertFalse(SignatureValidator().check_nonce(nonce))

    def test_empty_nonce(self):
        nonce = ''
        self.assertFalse(SignatureValidator().check_nonce(nonce))

    def test_null_nonce(self):
        nonce = None
        self.assertFalse(SignatureValidator().check_nonce(nonce))

    def test_validate_existing_key(self):
        LtiConsumer.objects.create(key='client_key', secret='client_secret')
        self.assertTrue(SignatureValidator().validate_client_key('client_key', None))

    def test_validate_missing_key(self):
        self.assertFalse(SignatureValidator().validate_client_key('client_key', None))

    def test_get_existing_client_secret(self):
        LtiConsumer.objects.create(key='client_key', secret='client_secret')
        secret = SignatureValidator().get_client_secret('client_key', None)
        self.assertEqual(secret, 'client_secret')

    def test_get_missing_client_secret(self):
        secret = SignatureValidator().get_client_secret('client_key', None)
        self.assertIsNone(secret)

