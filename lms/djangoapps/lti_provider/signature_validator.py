from lti_provider.models import LtiConsumer

from oauthlib.oauth1 import SignatureOnlyEndpoint
from oauthlib.oauth1 import RequestValidator


class SignatureValidator(RequestValidator):
    def __init__(self):
        self.signatureEndpoint = SignatureOnlyEndpoint(self)

    enforce_ssl = False

    def get_client_secret(self, client_key, request):
        consumer = LtiConsumer.objects.get(key=client_key)
        if consumer:
            return consumer.secret
        return None

    def check_client_key(self, key):
        return LtiConsumer.objects.filter(key=key).count()

    def check_nonce(self, nonce):
        return True

    def validate_timestamp_and_nonce(self, client_key, timestamp, nonce,
                                     request, request_token=None,
                                     access_token=None):
        return True

    def validate_client_key(self, client_key, request):
        return True

    def verify(self, request):
        method = u'POST'
        url = request.build_absolute_uri()
        headers = {"Content-Type": request.META['CONTENT_TYPE']}
        parameters = request.body

        result, request = self.signatureEndpoint.validate_request(url, method, parameters, headers)
        return result
